"""
price_collector.py — 每日股價資料蒐集

資料來源：
  - TWSE OpenAPI（上市）
  - TPEx OpenAPI（上櫃）
  - yfinance（備援：當 TWSE/TPEx API 尚未更新當日資料時）
每個交易日收盤後自動更新。
"""

import logging
import time
from datetime import date, datetime, timedelta
from typing import Optional

import pandas as pd
import requests

from config import HTTP_HEADERS, HTTP_RETRY, HTTP_TIMEOUT, TWSE_API, TPEX_API, EXCLUDE_KEYWORDS

logger = logging.getLogger(__name__)


def _get(url: str, timeout: int = HTTP_TIMEOUT) -> Optional[list]:
    for attempt in range(HTTP_RETRY):
        try:
            resp = requests.get(url, headers=HTTP_HEADERS, timeout=timeout, verify=False)
            resp.raise_for_status()
            data = resp.json()
            return data
        except Exception as e:
            logger.warning(f"[Attempt {attempt+1}] GET {url} failed: {e}")
            if attempt < HTTP_RETRY - 1:
                time.sleep(2 ** attempt)
    return None


def _parse_roc_date(roc_str: str) -> Optional[date]:
    """將民國日期字串（如 '1150706'）轉為西元 date，失敗回傳 None。"""
    try:
        s = str(roc_str).strip()
        if len(s) == 7:
            return date(int(s[:3]) + 1911, int(s[3:5]), int(s[5:7]))
    except Exception:
        pass
    return None


def _is_excluded(name: str, stock_id: str) -> bool:
    """排除 ETF、權證等非股票標的。"""
    name_upper = str(name).upper()
    if any(kw in name_upper for kw in EXCLUDE_KEYWORDS):
        return True
    # 代號超過4碼通常是權證/衍生品
    if len(str(stock_id).strip()) > 4 and not str(stock_id).strip().isdigit():
        return True
    return False


def fetch_twse_daily(trade_date: Optional[date] = None) -> pd.DataFrame:
    """抓取上市股票當日全市場行情。"""
    logger.info("Fetching TWSE daily prices...")
    data = _get(TWSE_API["daily_all"])
    if not data:
        logger.error("TWSE daily_all API returned no data.")
        return pd.DataFrame()

    records = []
    _api_date: Optional[date] = None  # 從第一筆取得 API 實際交易日
    for row in data:
        sid = str(row.get("Code", "")).strip()
        name = str(row.get("Name", "")).strip()
        if not sid or _is_excluded(name, sid):
            continue
        try:
            if _api_date is None:
                _api_date = _parse_roc_date(row.get("Date", ""))
            records.append({
                "stock_id":   sid,
                "name":       name,
                "market":     "TWSE",
                "date":       trade_date or _api_date or date.today(),
                "open":       _to_float(row.get("OpeningPrice")),
                "high":       _to_float(row.get("HighestPrice")),
                "low":        _to_float(row.get("LowestPrice")),
                "close":      _to_float(row.get("ClosingPrice")),
                "change_pct": _to_float(row.get("ChangePercent")),
                "volume":     _to_float(row.get("TradeVolume")),   # 千股
                "amount":     _to_float(row.get("TradeValue")),    # 元 → 轉百萬
            })
        except Exception:
            continue

    df = pd.DataFrame(records)
    if not df.empty and "amount" in df.columns:
        df["amount"] = df["amount"] / 1_000_000   # 轉換為百萬元
        df["volume"] = df["volume"] / 1_000        # 轉換為千股
    logger.info(f"TWSE: {len(df)} stocks fetched.")
    return df


def fetch_tpex_daily(trade_date: Optional[date] = None) -> pd.DataFrame:
    """抓取上櫃股票當日全市場行情。"""
    logger.info("Fetching TPEx daily prices...")
    data = _get(TPEX_API["daily_all"])
    if not data:
        logger.error("TPEx daily_all API returned no data.")
        return pd.DataFrame()

    records = []
    _api_date_tpex: Optional[date] = None
    for row in data:
        sid = str(row.get("SecuritiesCompanyCode", "")).strip()
        name = str(row.get("CompanyName", "")).strip()
        if not sid or _is_excluded(name, sid):
            continue
        try:
            if _api_date_tpex is None:
                _api_date_tpex = _parse_roc_date(row.get("Date", ""))
            records.append({
                "stock_id":   sid,
                "name":       name,
                "market":     "TPEx",
                "date":       trade_date or _api_date_tpex or date.today(),
                "open":       _to_float(row.get("Open")),
                "high":       _to_float(row.get("High")),
                "low":        _to_float(row.get("Low")),
                "close":      _to_float(row.get("Close")),
                "change_pct": _to_float(row.get("Change")),
                "volume":     _to_float(row.get("TradeVolume")),
                "amount":     _to_float(row.get("TradeValue")),
            })
        except Exception:
            continue

    df = pd.DataFrame(records)
    if not df.empty and "amount" in df.columns:
        df["amount"] = df["amount"] / 1_000_000
        df["volume"] = df["volume"] / 1_000
    logger.info(f"TPEx: {len(df)} stocks fetched.")
    return df


def _fetch_yahoo_one(ticker: str, target_date: date) -> Optional[dict]:
    """用 Yahoo Finance chart API 抓單一股票當日 OHLCV。不依賴 yfinance 套件。"""
    import calendar
    day_start = int(datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0).timestamp())
    day_end   = day_start + 86400
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
           f"?period1={day_start}&period2={day_end}&interval=1d")
    headers = {**HTTP_HEADERS, "Accept": "application/json"}
    try:
        resp = requests.get(url, headers=headers, timeout=10, verify=False)
        if resp.status_code != 200:
            return None
        j = resp.json()
        result = j.get("chart", {}).get("result")
        if not result:
            return None
        meta = result[0].get("meta", {})
        indicators = result[0].get("indicators", {})
        q = indicators.get("quote", [{}])[0]
        adjclose_list = indicators.get("adjclose", [{}])
        adjclose = adjclose_list[0].get("adjclose", []) if adjclose_list else []
        timestamps = result[0].get("timestamp", [])
        if not timestamps or not q.get("close"):
            return None
        idx = 0  # 只取第一筆（當日）
        close = (adjclose[idx] if adjclose and idx < len(adjclose) else None) or q["close"][idx]
        if not close:
            return None
        return {
            "open":   q.get("open",   [None])[idx],
            "high":   q.get("high",   [None])[idx],
            "low":    q.get("low",    [None])[idx],
            "close":  close,
            "volume": q.get("volume", [None])[idx],
        }
    except Exception:
        return None


def fetch_yfinance_daily(stale_df: pd.DataFrame, target_date: date) -> pd.DataFrame:
    """Yahoo Finance HTTP 備援：當 TWSE/TPEx API 尚未更新當日資料時使用。
    只補抓「分析過的股票 + 0050/0056 benchmark」，避免逐一呼叫 6000+ 股。
    不依賴 yfinance 套件（避免 macOS segfault），直接呼叫 Yahoo chart API。
    """
    # 取得需要補抓的 stock_id 清單（AnalysisResult + benchmarks）
    try:
        from src.database import get_session
        from sqlalchemy import text
        s = get_session()
        result = s.execute(text("SELECT DISTINCT stock_id FROM analysis_results")).fetchall()
        s.close()
        tracked_ids = {r[0] for r in result} | {"0050", "0056"}
    except Exception as e:
        logger.warning(f"無法讀取 AnalysisResult，改用全部股票: {e}")
        tracked_ids = None

    # 用 stale_df 建立 stock_id → market 對應
    sid_to_market = {str(row["stock_id"]): str(row.get("market", "TWSE"))
                     for _, row in stale_df.iterrows()}

    suffix_map = {"TWSE": ".TW", "TPEx": ".TWO"}
    rows_info = []
    for sid, market in sid_to_market.items():
        if tracked_ids is not None and sid not in tracked_ids:
            continue
        suffix = suffix_map.get(market, ".TW")
        rows_info.append((sid, market, f"{sid}{suffix}"))

    logger.info(f"Yahoo 備援：補抓 {len(rows_info)} 支追蹤股票…")
    records = []
    ok = fail = 0
    for sid, market, ticker in rows_info:
        data = _fetch_yahoo_one(ticker, target_date)
        if data and data.get("close") and data["close"] > 0:
            records.append({
                "stock_id":   sid,
                "market":     market,
                "date":       target_date,
                "open":       _to_float(data.get("open")),
                "high":       _to_float(data.get("high")),
                "low":        _to_float(data.get("low")),
                "close":      _to_float(data["close"]),
                "volume":     _to_float(data.get("volume", 0)) / 1000 if data.get("volume") else None,
                "amount":     None,
                "change_pct": None,
            })
            ok += 1
        else:
            fail += 1
        time.sleep(0.05)

    df = pd.DataFrame(records)
    logger.info(f"Yahoo 備援: 成功 {ok} 筆 / 失敗 {fail} 筆 ({target_date})")
    return df


def fetch_all_prices(trade_date: Optional[date] = None) -> pd.DataFrame:
    """合併上市 + 上櫃當日行情；若 API 未更新則自動啟用 yfinance 備援。"""
    twse = fetch_twse_daily(trade_date)
    tpex = fetch_tpex_daily(trade_date)
    all_df = pd.concat([twse, tpex], ignore_index=True)
    # 移除重複（同代號）
    all_df = all_df.drop_duplicates(subset="stock_id", keep="first")
    # 過濾收盤價為 0 或 NaN
    all_df = all_df[all_df["close"].notna() & (all_df["close"] > 0)]

    # yfinance 備援：API 回傳日期 < 今天 → 嘗試抓今日資料
    today = date.today()
    if trade_date is None and not all_df.empty:
        api_date = all_df["date"].iloc[0]
        if isinstance(api_date, str):
            api_date = date.fromisoformat(api_date)
        if hasattr(api_date, "date"):
            api_date = api_date.date()
        if api_date < today:
            logger.info(f"TWSE/TPEx API 仍回傳 {api_date}（今日 {today}），啟用 yfinance 備援…")
            yf_df = fetch_yfinance_daily(all_df, today)
            if not yf_df.empty:
                yf_date = yf_df["date"].iloc[0]
                if hasattr(yf_date, "date"):
                    yf_date = yf_date.date()
                if yf_date == today:
                    logger.info(f"yfinance 備援成功：{len(yf_df)} 筆 ({today})")
                    return yf_df
            logger.warning("yfinance 備援無今日資料，仍使用 TWSE/TPEx 舊資料。")

    logger.info(f"Total stocks fetched: {len(all_df)}")
    return all_df


def fetch_stock_info() -> dict:
    """從 TWSE t187ap03_L 取得上市股票基本資料（資本額、發行股數）。
    回傳 {stock_id: {"capital_b": float, "outstanding_shares_k": float}}
    """
    data = _get(TWSE_API["listed_stocks"])
    if not data:
        return {}
    result = {}
    for row in data:
        sid = str(row.get("公司代號", "")).strip()
        if not sid:
            continue
        capital_raw = _to_float(str(row.get("實收資本額", "")).replace(",", ""))
        shares_raw  = _to_float(str(row.get("已發行普通股數或TDR原股發行股數", "")).replace(",", ""))
        result[sid] = {
            "capital_b":           round(capital_raw / 1e8, 2) if capital_raw else None,
            "outstanding_shares_k": round(shares_raw / 1000, 0) if shares_raw else None,
        }
    return result


def fetch_market_summary() -> dict:
    """抓取大盤摘要（加權指數、成交金額等）。"""
    data = _get(TWSE_API["market_index"])
    if not data:
        return {}
    try:
        row = data[0]
        taiex  = _to_float(row.get("TAIEX"))
        change = _to_float(row.get("Change"))
        tv     = _to_float(row.get("TradeValue"))
        if taiex:
            pct = round(change / (taiex - change) * 100, 2) if change and (taiex - change) != 0 else None
            return {
                "index_name":       "加權指數",
                "index_close":      taiex,
                "index_change_pct": pct,
                "total_amount_b":   round(tv / 1e9, 1) if tv else 0,
            }
    except Exception as e:
        logger.warning(f"market_summary parse error: {e}")
    return {}


def fetch_price_history_finmind(
    stock_id: str,
    start_date: str,
    end_date: Optional[str] = None,
    token: str = "",
) -> pd.DataFrame:
    """用 FinMind 取得個股歷史股價（用於回測 / 初始化）。"""
    try:
        from FinMind.data import DataLoader
        dl = DataLoader()
        if token:
            dl.login_by_token(api_token=token)
        df = dl.taiwan_stock_price(
            stock_id=stock_id,
            start_date=start_date,
            end_date=end_date or date.today().isoformat(),
        )
        if df.empty:
            return pd.DataFrame()
        df = df.rename(columns={
            "date": "date", "open": "open", "max": "high",
            "min": "low", "close": "close", "Trading_Volume": "volume",
            "Trading_money": "amount", "spread": "change_pct",
        })
        df["stock_id"] = stock_id
        df["date"] = pd.to_datetime(df["date"]).dt.date
        return df[["stock_id", "date", "open", "high", "low", "close", "volume", "amount", "change_pct"]]
    except Exception as e:
        logger.warning(f"FinMind price history failed ({stock_id}): {e}")
        return pd.DataFrame()


def _to_float(val) -> Optional[float]:
    if val is None:
        return None
    try:
        s = str(val).replace(",", "").strip()
        if s in ("--", "-", "", "N/A"):
            return None
        return float(s)
    except (ValueError, TypeError):
        return None
