"""
dedup_utils.py — 共用的「交易日冷卻去重」邏輯

所有需要對重疊樣本去重的地方（Scorecard / ResearchBacktest / Evidence）
都應 import 此模組，避免各自維護相同但略有差異的實作。
"""

import bisect
import logging

logger = logging.getLogger(__name__)


def dedup_by_trading_days(
    signals: list,
    n_trading_days: int,
    sorted_dates_map: dict = None,
    market_calendar: list = None,
) -> list:
    """
    Per-stock trading-day cooldown dedup on (stock_id, date) tuples.

    Keeps the earliest signal for each stock; any subsequent signal within
    n_trading_days (counted in *trading* days, not calendar days) is dropped.

    Counting priority:
      1. sorted_dates_map[stock_id] — stock's own price dates (most precise)
      2. market_calendar            — Taiwan market proxy, e.g. sorted 0050 dates

    Fail-closed: if neither source is available for a stock, the independence of
    the signal cannot be confirmed → signal is excluded (not kept). A warning is
    logged. No calendar-day approximation is used.

    Args:
        signals:          list of (stock_id, date), sorted ascending by date
                          within each stock_id (globally sorted by date also works)
        n_trading_days:   minimum trading-day gap required to keep a signal
        sorted_dates_map: {stock_id: [date, ...]} sorted ascending; optional
        market_calendar:  [date, ...] sorted ascending (e.g. 0050 dates); optional

    Returns:
        Subsequence of signals that pass the cooldown filter, in input order.
    """
    sorted_dates_map = sorted_dates_map or {}
    last_kept: dict = {}
    result = []
    for stock_id, d in signals:
        prev = last_kept.get(stock_id)
        if prev is None:
            result.append((stock_id, d))
            last_kept[stock_id] = d
        else:
            sdates = sorted_dates_map.get(stock_id, [])
            if sdates:
                tdays = bisect.bisect_right(sdates, d) - bisect.bisect_right(sdates, prev)
            elif market_calendar:
                tdays = bisect.bisect_right(market_calendar, d) - bisect.bisect_right(market_calendar, prev)
            else:
                logger.warning(
                    "dedup_by_trading_days: no trading calendar for %s at %s "
                    "(prev kept: %s); signal excluded (fail-closed)",
                    stock_id, d, prev,
                )
                continue  # independence unknown → exclude from independent sample
            if tdays >= n_trading_days:
                result.append((stock_id, d))
                last_kept[stock_id] = d
    return result
