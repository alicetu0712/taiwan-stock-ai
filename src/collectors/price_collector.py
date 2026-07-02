"""
price_collector.py — 每日股價資料蒐集

資料來源：
  - TWSE OpenAPI（上市）
  - TPEx OpenAPI（上櫃）
每個交易日收盤後自動更新。
"""

import logging
import time
from datetime import date, datetime
from typing import Optional

import pandas as pd
import requests

from config import HTTP_HEADERS, HTTP_RETRY, HTTP_TIMEOUT, TWSE_API, TPEX_API, EXCLUDE_KEYWORDS

logger = logging.getLogger(__name__)


def _get(url: str, timeout: int = HTTP_TIMEOUT) -> Optional[list]:
    for attempt in range(HTTP_RETRY):
        try:
            resp = requests.get(url, headers=HTTP_HEADERS, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            return data
        except Exception as e:
            logger.warning(f"[Attempt {attempt+1}] GET {url} failed: {e}")
            if attempt < HTTP_RETRY - 1:
                time.sleep(2 ** attempt)
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
    for row in data:
        sid = str(row.get("Code", "")).strip()
        name = str(row.get("Name", "")).strip()
        if not sid or _is_excluded(name, sid):
            continue
        try:
            records.append({
                "stock_id":   sid,
                "name":       name,
                "market":     "TWSE",
                "date":       trade_date or date.today(),
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
    for row in data:
        sid = str(row.get("SecuritiesCompanyCode", "")).strip()
        name = str(row.get("CompanyName", "")).strip()
        if not sid or _is_excluded(name, sid):
            continue
        try:
            records.append({
                "stock_id":   sid,
                "name":       name,
                "market":     "TPEx",
                "date":       trade_date or date.today(),
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


def fetch_all_prices(trade_date: Optional[date] = None) -> pd.DataFrame:
    """合併上市 + 上櫃當日行情。"""
    twse = fetch_twse_daily(trade_date)
    tpex = fetch_tpex_daily(trade_date)
    all_df = pd.concat([twse, tpex], ignore_index=True)
    # 移除重複（同代號）
    all_df = all_df.drop_duplicates(subset="stock_id", keep="first")
    # 過濾收盤價為 0 或 NaN
    all_df = all_df[all_df["close"].notna() & (all_df["close"] > 0)]
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
