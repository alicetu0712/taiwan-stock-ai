"""
us_trading_calendar.py — NYSE / US Equity Market trading calendar

Purpose:
  Map Taiwan execution_date → latest completed US regular session date.
  Rule: us_market_date = prev_us_trading_day(tw_execution_date)

  Taiwan opens 09:00 CST (UTC+8) = 01:00 UTC.
  US regular session closes 16:00 ET (EDT=UTC-4 / EST=UTC-5).
  In either DST regime, US session close occurs before TW open —
  so the prior US session is always available before TW market opens.

Holiday source: NYSE official market closures.
Update _NYSE_HOLIDAYS when NYSE releases next year's schedule.
"""

from datetime import date, timedelta
from zoneinfo import ZoneInfo

# ── NYSE Official Closure Dates ───────────────────────────────────────────────
# Excludes weekends (handled separately by weekday check).
# When a holiday falls on Saturday, NYSE typically observes the prior Friday.
# When a holiday falls on Sunday, NYSE typically observes the following Monday.

_NYSE_HOLIDAYS: frozenset = frozenset([
    # ── 2026 ──────────────────────────────────────────────────────────────────
    date(2026,  1,  1),   # New Year's Day
    date(2026,  1, 19),   # Martin Luther King Jr. Day (3rd Monday)
    date(2026,  2, 16),   # Presidents' Day (3rd Monday)
    date(2026,  4,  3),   # Good Friday (Easter = Apr 5)
    date(2026,  5, 25),   # Memorial Day (last Monday)
    date(2026,  6, 19),   # Juneteenth
    date(2026,  7,  3),   # Independence Day observed (Jul 4 = Saturday)
    date(2026,  9,  7),   # Labor Day (1st Monday)
    date(2026, 11, 26),   # Thanksgiving Day (4th Thursday)
    date(2026, 12, 25),   # Christmas Day
    # ── 2025 ──────────────────────────────────────────────────────────────────
    date(2025,  1,  1),   # New Year's Day
    date(2025,  1, 20),   # Martin Luther King Jr. Day (3rd Monday)
    date(2025,  2, 17),   # Presidents' Day (3rd Monday)
    date(2025,  4, 18),   # Good Friday (Easter = Apr 20)
    date(2025,  5, 26),   # Memorial Day (last Monday)
    date(2025,  6, 19),   # Juneteenth
    date(2025,  7,  4),   # Independence Day
    date(2025,  9,  1),   # Labor Day (1st Monday)
    date(2025, 11, 27),   # Thanksgiving Day (4th Thursday)
    date(2025, 12, 25),   # Christmas Day
])

_COVERED_YEARS: frozenset = frozenset([2025, 2026])

# US Eastern timezone — handles EDT/EST/DST automatically
ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")


def is_us_trading_day(d: date) -> bool:
    """
    Return True only if d is a confirmed NYSE trading day.
    Fail-closed: years outside _COVERED_YEARS return False.
    """
    if d.weekday() >= 5:   # Saturday=5, Sunday=6
        return False
    if d.year not in _COVERED_YEARS:
        return False
    return d not in _NYSE_HOLIDAYS


def prev_us_trading_day(d: date, max_lookback: int = 14) -> date | None:
    """
    Return the most recent confirmed US trading day strictly before d.
    Returns None if no trading day found within max_lookback calendar days.
    """
    candidate = d - timedelta(days=1)
    for _ in range(max_lookback):
        if is_us_trading_day(candidate):
            return candidate
        candidate -= timedelta(days=1)
    return None


def tw_exec_to_us_market_date(tw_exec_date: date) -> date | None:
    """
    Map a Taiwan execution date to the latest completed US regular session.

    Rule: the most recent US trading day strictly before tw_exec_date.
    This is safe regardless of DST because US session close (16:00 ET)
    always precedes Taiwan open (09:00 CST = 01:00 UTC next calendar day).

    Returns None if mapping cannot be determined (year not in covered range,
    or no US trading day found within 14 calendar days).
    """
    return prev_us_trading_day(tw_exec_date)


def us_session_close_utc(us_date: date):
    """
    Return the US regular session close time (16:00 America/New_York) as a
    timezone-aware UTC datetime. Handles EDT/EST automatically via zoneinfo.
    """
    from datetime import datetime
    close_et = datetime(us_date.year, us_date.month, us_date.day, 16, 0, 0, tzinfo=ET)
    return close_et.astimezone(UTC)
