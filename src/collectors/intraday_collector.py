"""
intraday_collector.py — 盤中即時股價（TWSE MIS API）

資料來源：台灣證券交易所 mis.twse.com.tw
- 無需認證，免費使用
- 盤中每次請求回傳最新成交資訊（約 5 秒延遲）
- 休市時回傳上一交易日收盤資料

欄位說明：
  z  最新成交價（盤中無新成交時為 "-"）
  o  開盤價
  h  最高價
  l  最低價
  v  累計成交量（千股）
  t  最後更新時間（HH:MM:SS）
  n  股票名稱
  c  股票代號
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

_TWSE_API = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
_BATCH_SIZE = 30        # 每次最多查 30 支，避免 URL 過長
_TIMEOUT    = 8         # 秒
_CACHE_TTL  = 8         # 秒：快取存活時間（避免同一秒重複打 API）

_price_cache: Dict[str, dict] = {}
_cache_ts: float = 0.0


@dataclass
class IntradayQuote:
    stock_id:   str
    name:       str
    price:      Optional[float]   # 最新成交價（盤中可能為 None）
    open:       Optional[float]
    high:       Optional[float]
    low:        Optional[float]
    volume:     Optional[float]   # 千股
    update_time: Optional[str]    # "HH:MM:SS" 台灣時間
    is_trading:  bool = False     # True = 有新成交（z 欄位有值）
    source:      str  = "twse_mis"
    fetched_at:  str  = field(default_factory=lambda: datetime.now().strftime("%H:%M:%S"))


def _parse_float(val: str) -> Optional[float]:
    try:
        f = float(val)
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None


def _build_ex_ch(stock_ids: List[str], market_map: Dict[str, str]) -> str:
    parts = []
    for sid in stock_ids:
        mkt = market_map.get(sid, "TWSE")
        prefix = "tse" if mkt == "TWSE" else "otc"
        parts.append(f"{prefix}_{sid}.tw")
    return "|".join(parts)


def fetch_intraday(
    stock_ids: List[str],
    market_map: Optional[Dict[str, str]] = None,
    force: bool = False,
) -> Dict[str, IntradayQuote]:
    """
    批次查詢多支股票的盤中即時行情。

    Args:
        stock_ids:  股票代號列表
        market_map: {stock_id: "TWSE"/"TPEx"}，預設全部視為 TWSE
        force:      忽略快取強制重新抓取

    Returns:
        {stock_id: IntradayQuote}
    """
    global _price_cache, _cache_ts

    if market_map is None:
        market_map = {}

    if not stock_ids:
        return {}

    # 快取未過期且不強制刷新，直接回傳
    if not force and (time.time() - _cache_ts) < _CACHE_TTL:
        return {sid: _price_cache[sid] for sid in stock_ids if sid in _price_cache}

    result: Dict[str, IntradayQuote] = {}

    for i in range(0, len(stock_ids), _BATCH_SIZE):
        batch = stock_ids[i : i + _BATCH_SIZE]
        ex_ch = _build_ex_ch(batch, market_map)
        try:
            resp = requests.get(
                _TWSE_API,
                params={"ex_ch": ex_ch, "json": "1", "delay": "0"},
                timeout=_TIMEOUT,
                headers={"Referer": "https://mis.twse.com.tw/"},
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning(f"intraday fetch failed for batch {batch[:3]}…: {e}")
            continue

        for item in data.get("msgArray", []):
            sid = item.get("c", "").strip()
            if not sid:
                continue
            z_raw = item.get("z", "-")
            price = _parse_float(z_raw) if z_raw != "-" else None
            quote = IntradayQuote(
                stock_id    = sid,
                name        = item.get("n", ""),
                price       = price,
                open        = _parse_float(item.get("o")),
                high        = _parse_float(item.get("h")),
                low         = _parse_float(item.get("l")),
                volume      = _parse_float(item.get("v")),
                update_time = item.get("t"),
                is_trading  = price is not None,
            )
            result[sid] = quote

    _price_cache = result
    _cache_ts = time.time()
    return result


def best_price(quote: IntradayQuote) -> Optional[float]:
    """
    回傳最佳代表價格：
    有新成交用 z（最新成交），無成交用 (high+low)/2，都沒有用 open。
    """
    if quote.price is not None:
        return quote.price
    if quote.high is not None and quote.low is not None:
        return round((quote.high + quote.low) / 2, 2)
    return quote.open
