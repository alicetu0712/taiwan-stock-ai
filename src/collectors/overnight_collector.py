"""
overnight_collector.py — US overnight market data via Yahoo Finance chart API

Fetches a rolling window of daily closes for US indices, then extracts:
  - The exact target session (us_market_date)
  - The prior session (for return calculation)

Exact-session validation:
  Yahoo timestamps are converted to America/New_York date.
  If the date does not match the requested us_market_date, the result is
  marked MISSING — no silent nearest-date fallback.

Reuses the same Yahoo Finance chart API pattern as price_collector._fetch_yahoo_one,
adapted for US index tickers and multi-day history.

Tickers:
  ^GSPC  → S&P 500
  ^IXIC  → Nasdaq Composite
  ^SOX   → Philadelphia Semiconductor Index
  ^VIX   → CBOE Volatility Index
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

import requests

from config import HTTP_HEADERS

logger = logging.getLogger(__name__)

ET  = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

# Tickers for Phase 1
_US_INDEX_TICKERS = {
    "sp500":  "^GSPC",
    "nasdaq": "^IXIC",
    "sox":    "^SOX",
    "vix":    "^VIX",
}

# Fetch a 14-calendar-day window to cover weekends and holidays
_FETCH_WINDOW_DAYS = 14


@dataclass
class IndexSessionResult:
    """Single ticker result for one session date."""
    ticker:    str
    us_date:   Optional[date]    # actual session date found in Yahoo response
    close:     Optional[float]
    prev_close: Optional[float]  # prior session close (for return calculation)
    return_pct: Optional[float]  # (close - prev_close) / prev_close * 100
    ok:        bool              # True = exact session match and data valid
    reason:    str               # "ok" | "missing" | "stale" | "fetch_error"


@dataclass
class OvernightFetchResult:
    """Aggregated fetch result for one execution_date."""
    us_market_date:  Optional[date]
    sp500:           IndexSessionResult
    nasdaq:          IndexSessionResult
    sox:             IndexSessionResult
    vix:             IndexSessionResult
    source_name:     str = "yahoo_finance_v8"
    fetched_at:      datetime = field(default_factory=lambda: datetime.now(UTC))


def _fetch_index_history(ticker: str, target_date: date) -> list[dict]:
    """
    Fetch up to _FETCH_WINDOW_DAYS of daily history ending on/after target_date.
    Returns list of dicts: [{date: date, close: float, timestamp: int}, ...]
    sorted ascending by date.

    Uses Yahoo Finance v8 chart API with 1d interval.
    """
    window_start = target_date - timedelta(days=_FETCH_WINDOW_DAYS)
    # Add 2 days buffer past target to capture any after-hours adjustments
    window_end = target_date + timedelta(days=2)

    period1 = int(datetime(window_start.year, window_start.month, window_start.day,
                           0, 0, 0, tzinfo=UTC).timestamp())
    period2 = int(datetime(window_end.year, window_end.month, window_end.day,
                           23, 59, 59, tzinfo=UTC).timestamp())

    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        f"?period1={period1}&period2={period2}&interval=1d"
    )
    headers = {**HTTP_HEADERS, "Accept": "application/json"}
    try:
        resp = requests.get(url, headers=headers, timeout=15, verify=False)
        if resp.status_code != 200:
            logger.warning(f"overnight_collector: {ticker} HTTP {resp.status_code}")
            return []
        j = resp.json()
        result = j.get("chart", {}).get("result")
        if not result:
            return []

        timestamps = result[0].get("timestamp", [])
        q = result[0].get("indicators", {}).get("quote", [{}])[0]
        closes = q.get("close", [])

        if not timestamps or not closes:
            return []

        rows = []
        for ts, cl in zip(timestamps, closes):
            if cl is None:
                continue
            dt_et = datetime.fromtimestamp(ts, tz=ET)
            rows.append({"date": dt_et.date(), "close": cl, "timestamp": ts})

        rows.sort(key=lambda x: x["date"])
        return rows

    except Exception as exc:
        logger.warning(f"overnight_collector: {ticker} fetch error: {exc}")
        return []


def _extract_session(
    ticker: str,
    rows: list[dict],
    target_date: date,
) -> IndexSessionResult:
    """
    Extract close and return_pct for target_date from history rows.

    Exact-session rule:
      - Row date must exactly equal target_date (America/New_York).
      - If not found → reason="missing".
      - If the last row date ≠ target_date (stale) → reason="stale".
      - No nearest-date fallback.
    """
    if not rows:
        return IndexSessionResult(ticker=ticker, us_date=None, close=None,
                                  prev_close=None, return_pct=None,
                                  ok=False, reason="fetch_error")

    # Find exact target row and its predecessor
    target_row = None
    prev_row = None
    for i, row in enumerate(rows):
        if row["date"] == target_date:
            target_row = row
            prev_row = rows[i - 1] if i > 0 else None
            break

    if target_row is None:
        # Check if the most recent row is older than target → stale
        last_date = rows[-1]["date"] if rows else None
        reason = "stale" if (last_date and last_date < target_date) else "missing"
        return IndexSessionResult(ticker=ticker, us_date=last_date, close=None,
                                  prev_close=None, return_pct=None,
                                  ok=False, reason=reason)

    close = target_row["close"]
    prev_close = prev_row["close"] if prev_row else None
    return_pct = None
    if close is not None and prev_close is not None and prev_close != 0:
        return_pct = (close - prev_close) / prev_close * 100

    return IndexSessionResult(
        ticker=ticker,
        us_date=target_date,
        close=close,
        prev_close=prev_close,
        return_pct=return_pct,
        ok=True,
        reason="ok",
    )


def fetch_overnight_context(us_market_date: date) -> OvernightFetchResult:
    """
    Fetch all US index data for one us_market_date.

    Each index is validated for exact session match.
    Failures do not raise — they produce IndexSessionResult.ok=False.
    Caller (overnight_service) is responsible for deriving data_quality and risk_level.
    """
    results: dict[str, IndexSessionResult] = {}
    for key, ticker in _US_INDEX_TICKERS.items():
        rows = _fetch_index_history(ticker, us_market_date)
        results[key] = _extract_session(ticker, rows, us_market_date)

    return OvernightFetchResult(
        us_market_date=us_market_date,
        sp500=results["sp500"],
        nasdaq=results["nasdaq"],
        sox=results["sox"],
        vix=results["vix"],
    )
