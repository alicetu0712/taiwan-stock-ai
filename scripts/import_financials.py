"""
scripts/import_financials.py — MOPS 財務資料批量匯入

資料來源：公開資訊觀測站 (mops.twse.com.tw) — 官方 API，無需 token，無 IP 限制。
  t164sb04 — 合併損益表（EPS、毛利率、營益率、淨利率）
  t164sb03 — 合併資產負債表（負債比、流動比率、ROE/ROA 計算用）

執行方式（在 stock_platform/ 目錄下）：
  python3 scripts/import_financials.py              # 全部股票
  python3 scripts/import_financials.py --limit 50   # 前 50 支測試
  python3 scripts/import_financials.py --stock 2330 # 單支股票
  python3 scripts/import_financials.py --missing    # 只補尚無資料的股票
  python3 scripts/import_financials.py --years 5    # 取 5 年（預設 7 年）

預估時間（全部 ~666 支，每支 7 年 × 2 API × 0.5s）：約 25 分鐘
"""

import sys
import time
import random
import argparse
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import init_db, get_session, Stock, FinancialQuarter
from src.collectors.mops_collector import fetch_multi_year

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("import_financials")


def upsert_annual_data(session, stock_id: str, records: list) -> int:
    """將年度財務資料寫入 financial_quarters（quarter=0）。已存在則更新。"""
    n = 0
    for rec in records:
        year = rec["year"]
        existing = (
            session.query(FinancialQuarter)
            .filter_by(stock_id=stock_id, year=year, quarter=0)
            .first()
        )
        if existing:
            for field in ("eps", "roe", "roa", "gross_margin", "op_margin",
                          "net_margin", "debt_ratio", "current_ratio"):
                new_val = rec.get(field)
                if new_val is not None:
                    setattr(existing, field, new_val)
        else:
            session.add(FinancialQuarter(
                stock_id      = stock_id,
                year          = year,
                quarter       = 0,
                eps           = rec.get("eps"),
                roe           = rec.get("roe"),
                roa           = rec.get("roa"),
                gross_margin  = rec.get("gross_margin"),
                op_margin     = rec.get("op_margin"),
                net_margin    = rec.get("net_margin"),
                debt_ratio    = rec.get("debt_ratio"),
                current_ratio = rec.get("current_ratio"),
            ))
            n += 1
    session.commit()
    return n


def main():
    parser = argparse.ArgumentParser(description="MOPS 財務資料匯入")
    parser.add_argument("--limit",   type=int,  default=0,   help="最多處理幾支（0=全部）")
    parser.add_argument("--stock",   type=str,  default="",  help="指定單支股票代號")
    parser.add_argument("--years",   type=int,  default=7,   help="取幾年資料（預設 7）")
    parser.add_argument("--missing", action="store_true",    help="只補尚無年度財務資料的股票")
    args = parser.parse_args()

    engine  = init_db()
    session = get_session(engine)

    # 決定要處理的股票清單
    if args.stock:
        stock_ids = [args.stock.strip()]
    elif args.missing:
        from sqlalchemy import func
        has_data = {
            r.stock_id
            for r in session.query(FinancialQuarter.stock_id)
            .filter(FinancialQuarter.quarter == 0)
            .distinct()
            .all()
        }
        all_stocks = [r.stock_id for r in session.query(Stock.stock_id).all()]
        stock_ids = [s for s in all_stocks if s not in has_data]
        logger.info(f"[--missing] 全部 {len(all_stocks)} 支，已有 {len(has_data)} 支，待補 {len(stock_ids)} 支")
    else:
        query = session.query(Stock.stock_id)
        if args.limit > 0:
            query = query.limit(args.limit)
        stock_ids = [r.stock_id for r in query.all()]

    total = len(stock_ids)
    logger.info("=" * 60)
    logger.info(f"MOPS 財務資料匯入 — 共 {total} 支 × {args.years} 年")
    logger.info("=" * 60)

    inserted_total = 0
    failed = []

    for i, sid in enumerate(stock_ids, 1):
        pct = i / total * 100
        records = fetch_multi_year(sid, n_years=args.years)

        if not records:
            logger.warning(f"[{pct:5.1f}%] {sid}：無資料")
            failed.append(sid)
        else:
            n = upsert_annual_data(session, sid, records)
            inserted_total += n
            r0 = records[0]
            logger.info(
                f"[{pct:5.1f}%] {sid}：{len(records)} 年 "
                f"EPS={r0['eps']} ROE={r0['roe']} ROA={r0['roa']} "
                f"GM={r0['gross_margin']} 負債比={r0['debt_ratio']} "
                f"（新增 {n} 筆）"
            )

    # 統計
    from sqlalchemy import func
    total_rows = (
        session.query(func.count(FinancialQuarter.id))
        .filter(FinancialQuarter.quarter == 0)
        .scalar()
    )
    session.close()

    logger.info("=" * 60)
    logger.info(f"匯入完成！")
    logger.info(f"  本次新增：{inserted_total} 筆")
    logger.info(f"  DB 年度資料總計：{total_rows} 筆")
    if failed:
        logger.warning(f"  無資料股票（{len(failed)} 支）：{failed[:20]}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
