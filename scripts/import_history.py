"""
scripts/import_history.py — 歷史資料批量匯入

資料來源：
  • 股價：TWSE STOCK_DAY（免費，每次回傳一支股票一個月）
  • 法人：TWSE T86（免費，每次回傳所有股票單日買賣超）
  • 財務：FinMind（需付費帳號，預設跳過）
  • 股票清單：FinMind TaiwanStockInfo（免費）

執行方式（在 stock_platform/ 目錄下）：
  python scripts/import_history.py                   # 預設：2 年股價 + 60 天法人，500 檔
  python scripts/import_history.py --years 1         # 縮短為 1 年
  python scripts/import_history.py --limit 200       # 只匯入前 200 檔
  python scripts/import_history.py --chip-days 90    # 法人資料匯入 90 天
  python scripts/import_history.py --skip-price      # 只匯入法人
  python scripts/import_history.py --skip-chip       # 只匯入股價
  python scripts/import_history.py --financial       # 加入財務資料（需 FinMind 付費）

預估時間（預設設定）：
  股價（500 檔 × 24 個月）：約 50-60 分鐘
  法人（60 天）：           約 2-3 分鐘
  合計：                    約 55-65 分鐘
"""

import sys
import time
import argparse
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import List, Tuple

import requests
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import FINMIND_TOKEN
from src.database import init_db, get_session, DailyPrice, InstitutionalData, Stock

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("import_history")

TWSE_STOCK_DAY = "https://www.twse.com.tw/exchangeReport/STOCK_DAY"
TWSE_T86       = "https://www.twse.com.tw/fund/T86"
FINMIND_API    = "https://api.finmindtrade.com/api/v4/data"
HEADERS        = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}


# ── 日期工具 ──────────────────────────────────────────────────

def roc_to_date(roc_str: str) -> date:
    """民國日期 (115/06/01) → Python date"""
    p = roc_str.strip().split("/")
    return date(int(p[0]) + 1911, int(p[1]), int(p[2]))


def parse_num(s: str) -> float:
    try:
        return float(str(s).replace(",", "").strip())
    except (ValueError, AttributeError):
        return 0.0


def trading_months(years: int) -> List[Tuple[int, int]]:
    """過去 N 年的 (year, month) 清單"""
    today = date.today()
    result = []
    for i in range(years * 12, -1, -1):
        y = today.year - (i // 12)
        m = today.month - (i % 12)
        if m <= 0:
            m += 12
            y -= 1
        if y > 0:
            result.append((y, m))
    return sorted(set(result))


def trading_months_n(n_months: int) -> List[Tuple[int, int]]:
    """過去 N 個月的 (year, month) 清單（含當月）"""
    today = date.today()
    result = []
    for i in range(n_months - 1, -1, -1):
        y = today.year
        m = today.month - i
        while m <= 0:
            m += 12
            y -= 1
        result.append((y, m))
    return sorted(set(result))


def weekdays_range(start: date, end: date) -> List[date]:
    """產生週一到週五的日期清單"""
    days, d = [], start
    while d <= end:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


# ── Step 1: 股票清單 ──────────────────────────────────────────

def get_stock_list(limit: int) -> pd.DataFrame:
    logger.info(f"[清單] 取得 TWSE 股票清單（via TWSE OpenAPI）...")
    try:
        r = requests.get(
            "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL",
            headers=HEADERS, timeout=15)
        data = r.json()
        records = []
        for row in data:
            sid = str(row.get("Code", "")).strip()
            name = str(row.get("Name", "")).strip()
            if not sid or len(sid) != 4 or not sid.isdigit():
                continue
            records.append({"stock_id": sid, "stock_name": name})
        df = pd.DataFrame(records).drop_duplicates("stock_id").reset_index(drop=True)
        total = len(df)
        df = df.head(limit)
        logger.info(f"[清單] 共 {total} 檔，匯入前 {len(df)} 檔")
        return df
    except Exception as e:
        logger.error(f"[清單] TWSE 取得失敗：{e}")
        return pd.DataFrame()


def upsert_stocks(session, df: pd.DataFrame):
    n = 0
    for _, row in df.iterrows():
        if not session.query(Stock).filter_by(stock_id=row["stock_id"]).first():
            session.add(Stock(
                stock_id=row["stock_id"],
                name=row.get("stock_name", row["stock_id"]),
                market="TWSE",
                industry=row.get("industry_category", ""),
            ))
            n += 1
    session.commit()
    logger.info(f"[清單] 新增 {n} 筆至 stocks 表")


# ── Step 2: 歷史股價 ──────────────────────────────────────────

def fetch_monthly_price(stock_id: str, year: int, month: int) -> List[dict]:
    date_str = f"{year}{month:02d}01"
    try:
        r = requests.get(TWSE_STOCK_DAY,
            params={"response": "json", "date": date_str, "stockNo": stock_id},
            headers=HEADERS, timeout=10)
        body = r.json()
        if body.get("stat") != "OK" or not body.get("data"):
            return []
        records = []
        for row in body["data"]:
            try:
                d      = roc_to_date(row[0])
                close  = parse_num(row[6])
                if close <= 0:
                    continue
                change = parse_num(row[7])
                prev   = close - change
                chg_pct = round(change / prev * 100, 2) if prev else 0
                records.append({
                    "stock_id":  stock_id,
                    "date":      d,
                    "open":      parse_num(row[3]),
                    "high":      parse_num(row[4]),
                    "low":       parse_num(row[5]),
                    "close":     close,
                    "volume":    parse_num(row[1]) / 1000,       # 股 → 千股
                    "amount":    parse_num(row[2]) / 1_000_000,  # 元 → 百萬
                    "change_pct": chg_pct,
                })
            except Exception:
                continue
        return records
    except Exception:
        return []


def import_price_history(session, stock_list: pd.DataFrame, years: int, delay: float, n_months: int = 0):
    months = trading_months_n(n_months) if n_months > 0 else trading_months(years)
    total  = len(stock_list)
    total_calls = total * len(months)
    eta_min = total_calls * delay / 60

    logger.info(f"[股價] 開始：{total} 檔 × {len(months)} 個月 = {total_calls} 次呼叫")
    logger.info(f"[股價] 預估時間：約 {eta_min:.0f} 分鐘")

    inserted = 0
    call_idx = 0

    for idx, (_, row) in enumerate(stock_list.iterrows()):
        sid  = row["stock_id"]
        name = row.get("stock_name", sid)
        s_ins = 0

        for (y, m) in months:
            call_idx += 1
            records = fetch_monthly_price(sid, y, m)

            for rec in records:
                if not session.query(DailyPrice).filter_by(
                    stock_id=rec["stock_id"], date=rec["date"]
                ).first():
                    session.add(DailyPrice(**rec))
                    s_ins += 1

            if records:
                session.commit()

            time.sleep(delay)

        inserted += s_ins
        pct = (idx + 1) / total * 100
        logger.info(f"[股價] [{pct:5.1f}%] {sid} {name}  +{s_ins} 筆  累計 {inserted}")

    logger.info(f"[股價] 完成：共新增 {inserted} 筆")


# ── Step 3: 歷史法人 ──────────────────────────────────────────

def fetch_t86(trade_date: date) -> List[dict]:
    """TWSE T86：全市場三大法人單日買賣超（支援歷史日期）。"""
    date_str = trade_date.strftime("%Y%m%d")
    try:
        r = requests.get(TWSE_T86,
            params={"response": "json", "date": date_str, "selectType": "ALLBUT0999"},
            headers=HEADERS, timeout=10)
        body = r.json()
        if body.get("stat") != "OK" or not body.get("data"):
            return []
        # 欄位：[代號, 名稱, 外資買, 外資賣, 外資超(4), ..., 投信超(10), 自營超(11), ..., 三大超(18)]
        records = []
        for row in body["data"]:
            try:
                sid = str(row[0]).strip()
                if not sid.isdigit() or len(sid) != 4:
                    continue
                records.append({
                    "stock_id":   sid,
                    "date":       trade_date,
                    "foreign_net": parse_num(row[4]),   # 外陸資買賣超
                    "trust_net":   parse_num(row[10]),  # 投信買賣超
                    "dealer_net":  parse_num(row[11]),  # 自營商買賣超
                    "total_net":   parse_num(row[18]),  # 三大法人合計
                })
            except Exception:
                continue
        return records
    except Exception:
        return []


def import_chip_history(session, chip_days: int, delay: float):
    end   = date.today()
    start = end - timedelta(days=int(chip_days * 1.5))
    days  = weekdays_range(start, end)[-chip_days:]

    logger.info(f"[法人] 開始：{len(days)} 個交易日（{days[0]} ~ {days[-1]}）")

    inserted = 0
    for i, d in enumerate(days):
        records = fetch_t86(d)
        n = 0
        for rec in records:
            if not session.query(InstitutionalData).filter_by(
                stock_id=rec["stock_id"], date=d
            ).first():
                session.add(InstitutionalData(**rec))
                n += 1
        session.commit()
        inserted += n
        logger.info(f"[法人] [{i+1}/{len(days)}] {d}  +{n} 筆（{len(records)} 檔）")
        time.sleep(delay)

    logger.info(f"[法人] 完成：共新增 {inserted} 筆")


# ── Step 4: 財務資料（FinMind 付費）─────────────────────────

def check_finmind_financial() -> bool:
    if not FINMIND_TOKEN:
        return False
    try:
        r = requests.get(FINMIND_API, params={
            "dataset": "TaiwanStockFinancialStatements",
            "stock_id": "2330", "start_date": "2025-01-01",
            "token": FINMIND_TOKEN,
        }, headers=HEADERS, timeout=10)
        d = r.json()
        return d.get("status") == 200 and len(d.get("data", [])) > 0
    except Exception:
        return False


def import_financial_data(session, stock_list: pd.DataFrame, years: int, delay: float):
    from src.database import FinancialQuarter, MonthlyRevenue
    start_date = (date.today() - timedelta(days=years * 365)).strftime("%Y-%m-%d")
    total = len(stock_list)
    ins_q, ins_mv = 0, 0

    logger.info(f"[財務] 開始：{total} 檔")

    for i, (_, row) in enumerate(stock_list.iterrows()):
        sid = row["stock_id"]

        # 季報
        try:
            r = requests.get(FINMIND_API, params={
                "dataset": "TaiwanStockFinancialStatements",
                "stock_id": sid, "start_date": start_date, "token": FINMIND_TOKEN,
            }, headers=HEADERS, timeout=15)
            data = r.json().get("data", [])
            df = pd.DataFrame(data) if data else pd.DataFrame()
            if not df.empty and "type" in df.columns:
                pivot = df.pivot_table(index="date", columns="type", values="value", aggfunc="last")
                for date_str, prow in pivot.iterrows():
                    try:
                        if "-Q" in str(date_str):
                            y, q = str(date_str).split("-Q")
                            y, q = int(y), int(q)
                        else:
                            dt = pd.to_datetime(date_str)
                            y, q = dt.year, (dt.month - 1) // 3 + 1
                        if not session.query(FinancialQuarter).filter_by(
                            stock_id=sid, year=y, quarter=q
                        ).first():
                            session.add(FinancialQuarter(
                                stock_id=sid, year=y, quarter=q,
                                eps=float(prow.get("EPS", 0) or 0),
                                gross_margin=float(prow.get("GrossProfit", 0) or 0),
                            ))
                            ins_q += 1
                    except Exception:
                        continue
        except Exception:
            pass

        time.sleep(delay)

        # 月營收
        try:
            r = requests.get(FINMIND_API, params={
                "dataset": "TaiwanStockMonthRevenue",
                "stock_id": sid, "start_date": start_date, "token": FINMIND_TOKEN,
            }, headers=HEADERS, timeout=15)
            for rec in r.json().get("data", []):
                try:
                    dt = pd.to_datetime(rec["date"])
                    if not session.query(MonthlyRevenue).filter_by(
                        stock_id=sid, year=dt.year, month=dt.month
                    ).first():
                        session.add(MonthlyRevenue(
                            stock_id=sid, year=dt.year, month=dt.month,
                            revenue=float(rec.get("revenue", 0) or 0),
                            yoy_growth=float(rec.get("revenue_year_on_year", 0) or 0),
                        ))
                        ins_mv += 1
                except Exception:
                    continue
        except Exception:
            pass

        session.commit()
        time.sleep(delay)

        if (i + 1) % 20 == 0 or (i + 1) == total:
            logger.info(f"[財務] [{i+1}/{total}] {sid}  季報 {ins_q} 筆 | 月營收 {ins_mv} 筆")

    logger.info(f"[財務] 完成：季報 {ins_q} 筆，月營收 {ins_mv} 筆")


# ── 主流程 ────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="歷史資料批量匯入")
    parser.add_argument("--years",      type=int,   default=2,    help="股價歷史年數（預設 2）")
    parser.add_argument("--months",     type=int,   default=0,    help="股價歷史月數，優先於 --years（0=不啟用）")
    parser.add_argument("--limit",      type=int,   default=500,  help="匯入股票數上限（預設 500）")
    parser.add_argument("--chip-days",  type=int,   default=60,   help="法人資料天數（預設 60）")
    parser.add_argument("--delay",      type=float, default=0.4,  help="API 呼叫間隔秒（預設 0.4）")
    parser.add_argument("--skip-price", action="store_true")
    parser.add_argument("--skip-chip",  action="store_true")
    parser.add_argument("--financial",  action="store_true", help="匯入財務（需 FinMind 付費帳號）")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("AI Taiwan Equity Research Platform — 歷史資料匯入")
    period_desc = f"{args.months} 個月" if args.months > 0 else f"{args.years} 年"
    logger.info(f"設定：{period_desc}股價 | 前 {args.limit} 檔 | 法人 {args.chip_days} 天")
    logger.info("=" * 60)

    engine  = init_db()
    session = get_session(engine)

    stock_list = get_stock_list(args.limit)
    if stock_list.empty:
        logger.error("無法取得股票清單，中止。")
        sys.exit(1)

    upsert_stocks(session, stock_list)

    if not args.skip_price:
        import_price_history(session, stock_list, args.years, args.delay, n_months=args.months)

    if not args.skip_chip:
        import_chip_history(session, args.chip_days, args.delay)

    if args.financial:
        if check_finmind_financial():
            import_financial_data(session, stock_list, args.years, args.delay)
        else:
            logger.warning(
                "[財務] FinMind 免費帳號無法存取財務資料。\n"
                "       升級後重新執行：python scripts/import_history.py --financial --skip-price --skip-chip"
            )

    # 統計
    from sqlalchemy import func
    price_cnt = session.query(func.count(DailyPrice.id)).scalar()
    chip_cnt  = session.query(func.count(InstitutionalData.id)).scalar()
    stock_cnt = session.query(func.count(Stock.stock_id)).scalar()
    session.close()

    logger.info("=" * 60)
    logger.info("✅ 匯入完成！")
    logger.info(f"   股票檔數：{stock_cnt:,} 檔")
    logger.info(f"   股價紀錄：{price_cnt:,} 筆")
    logger.info(f"   法人紀錄：{chip_cnt:,} 筆")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
