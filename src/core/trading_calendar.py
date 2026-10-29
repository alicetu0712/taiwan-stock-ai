"""
trading_calendar.py — Taiwan Stock Exchange (TWSE) trading calendar

Rules (priority order):
  1. Weekends (Sat/Sun) → WEEKEND
  2. Known official holidays → HOLIDAY
  3. Otherwise weekday → TRADING_DAY
  4. If we cannot confirm (future year with no data) → CALENDAR_UNKNOWN

Holiday source: TWSE official announcements.
Update _TWSE_HOLIDAYS when TWSE releases next year's schedule (usually Oct-Nov).

Data quality gate constants live here so every consumer uses the same vocabulary.
"""

import logging
from datetime import date, datetime, timedelta
from enum import Enum
from zoneinfo import ZoneInfo

_TAIPEI = ZoneInfo("Asia/Taipei")

_log = logging.getLogger(__name__)
_calendar_expiry_warned: set = set()  # years already warned; avoids log spam


class MarketStatus(str, Enum):
    TRADING_DAY      = "TRADING_DAY"
    WEEKEND          = "WEEKEND"
    HOLIDAY          = "HOLIDAY"
    CALENDAR_UNKNOWN = "CALENDAR_UNKNOWN"


# ── Official TWSE closure dates ───────────────────────────────
# Source: TWSE market operations calendar announcements.
# Excludes weekends (handled separately).
# Verify and extend each year when TWSE publishes the new schedule.

_TWSE_HOLIDAYS: frozenset = frozenset([
    # ── 2026 ──────────────────────────────────────────────────
    date(2026,  1,  1),   # 元旦
    date(2026,  1,  2),   # 元旦補假
    date(2026,  2, 16),   # 農曆除夕前補班/連假（春節）
    date(2026,  2, 17),   # 春節初一
    date(2026,  2, 18),   # 春節初二
    date(2026,  2, 19),   # 春節初三（替代週六）
    date(2026,  2, 20),   # 春節補假
    date(2026,  2, 27),   # 和平紀念日補假（228 週六補前一日）
    date(2026,  4,  3),   # 兒童節（清明節前一天）
    date(2026,  4,  6),   # 清明節補假
    date(2026,  6, 19),   # 端午節
    date(2026,  9, 25),   # 中秋節
    date(2026, 10,  9),   # 國慶日補假（10/10 週六，補休前一個週五）
    # ── 2025 ──────────────────────────────────────────────────
    date(2025,  1,  1),   # 元旦
    date(2025,  1, 27),   # 除夕
    date(2025,  1, 28),   # 春節初一
    date(2025,  1, 29),   # 春節初二
    date(2025,  1, 30),   # 春節初三
    date(2025,  1, 31),   # 春節初四
    date(2025,  2, 28),   # 和平紀念日
    date(2025,  4,  3),   # 兒童節
    date(2025,  4,  4),   # 清明節
    date(2025,  5,  1),   # 勞動節（TWSE 2025 有休市，需確認年度公告）
    date(2025,  5, 30),   # 端午節
    date(2025, 10,  9),   # 國慶日補假（如適用）
    date(2025, 10, 10),   # 國慶日
])

# Years for which we have confident holiday data
_COVERED_YEARS: frozenset = frozenset([2025, 2026])


class TaiwanTradingCalendar:
    """
    Minimal Taiwan trading calendar.

    Usage:
        cal = TaiwanTradingCalendar()
        if cal.is_trading_day(date.today()):
            run_pipeline()
        status = cal.market_status(d)  # MarketStatus enum
    """

    def market_status(self, d: date) -> MarketStatus:
        """Return the market status for date d."""
        # 1. Weekends are always closed
        if d.weekday() >= 5:
            return MarketStatus.WEEKEND

        # 2. If we have holiday data for this year, check it
        if d.year in _COVERED_YEARS:
            if d in _TWSE_HOLIDAYS:
                return MarketStatus.HOLIDAY
            return MarketStatus.TRADING_DAY

        # 3. Year not covered — emit a one-time WARNING then return UNKNOWN (fail-closed).
        if d.year not in _calendar_expiry_warned:
            _calendar_expiry_warned.add(d.year)
            max_covered = max(_COVERED_YEARS) if _COVERED_YEARS else 0
            _log.warning(
                "CALENDAR_UNKNOWN for year %d — _COVERED_YEARS only extends to %d. "
                "Add %d TWSE holidays to _TWSE_HOLIDAYS in trading_calendar.py "
                "(TWSE publishes next year's schedule around Oct-Nov). "
                "Pipeline will skip all days in %d until updated. Use --force to bypass.",
                d.year, max_covered, d.year, d.year,
            )
        return MarketStatus.CALENDAR_UNKNOWN

    def is_trading_day(self, d: date) -> bool:
        """
        True only if d is a confirmed TWSE trading day.
        Fail-closed: CALENDAR_UNKNOWN returns False — do not generate formal signals
        for years not covered by _TWSE_HOLIDAYS. Use --force to override.
        """
        return self.market_status(d) == MarketStatus.TRADING_DAY

    def is_market_closed(self, d: date) -> bool:
        """True if we are confident the market is closed (WEEKEND or HOLIDAY)."""
        return self.market_status(d) in (MarketStatus.WEEKEND, MarketStatus.HOLIDAY)

    def last_trading_day(self, d: date, max_lookback: int = 14) -> date | None:
        """Return the most recent confirmed trading day on or before d."""
        candidate = d
        for _ in range(max_lookback):
            if self.is_trading_day(candidate):
                return candidate
            candidate -= timedelta(days=1)
        return None  # no trading day found within lookback window

    def next_trading_day(self, d: date, max_lookahead: int = 14) -> date | None:
        """Return the next confirmed trading day after d (exclusive)."""
        candidate = d + timedelta(days=1)
        for _ in range(max_lookahead):
            if self.is_trading_day(candidate):
                return candidate
            candidate += timedelta(days=1)
        return None

    def prev_trading_day(self, d: date, max_lookback: int = 14) -> date | None:
        """Return the most recent trading day strictly before d."""
        candidate = d - timedelta(days=1)
        for _ in range(max_lookback):
            if self.is_trading_day(candidate):
                return candidate
            candidate -= timedelta(days=1)
        return None


# Module-level singleton
_calendar = TaiwanTradingCalendar()


def market_status(d: date) -> MarketStatus:
    return _calendar.market_status(d)


def is_trading_day(d: date) -> bool:
    return _calendar.is_trading_day(d)


def is_market_closed(d: date) -> bool:
    return _calendar.is_market_closed(d)


def last_trading_day(d: date) -> date | None:
    return _calendar.last_trading_day(d)


def prev_trading_day(d: date) -> date | None:
    return _calendar.prev_trading_day(d)


def next_trading_day(d: date) -> date | None:
    return _calendar.next_trading_day(d)


# ── Data-availability threshold ───────────────────────────────────────────────
# TWSE publishes official closing data around 15:00-15:30 Asia/Taipei.
# The scheduled pipeline runs at 15:55 (safely after publication).
# Before this hour:minute we consider today's data NOT yet available.
_DATA_READY_HOUR: int   = 15
_DATA_READY_MINUTE: int = 30


def effective_trade_date(now_taipei: datetime | None = None) -> date:
    """Return the most recent trading day whose closing data is expected available.

    Rules:
      1. If today (Asia/Taipei) is a confirmed trading day AND current time
         is >= _DATA_READY_HOUR:_DATA_READY_MINUTE (15:30 Taiwan) → return today.
      2. Otherwise → return the most recent completed trading day before today.

    This prevents the pipeline from requesting data for a day the market hasn't
    closed yet (e.g., running at 02:55 Taiwan time the following morning).

    The DQ gate (PRICE_DATE_MISMATCH) provides a second layer of defence and
    must never be weakened.

    Args:
        now_taipei: override for testing; defaults to datetime.now(Asia/Taipei).
    """
    if now_taipei is None:
        now_taipei = datetime.now(_TAIPEI)

    today = now_taipei.date()
    is_today_trading = _calendar.is_trading_day(today)
    data_ready = (
        now_taipei.hour > _DATA_READY_HOUR
        or (now_taipei.hour == _DATA_READY_HOUR
            and now_taipei.minute >= _DATA_READY_MINUTE)
    )

    if is_today_trading and data_ready:
        return today

    # Fall back to the most recent confirmed trading day strictly before today.
    prev = _calendar.prev_trading_day(today)
    if prev is not None:
        return prev

    _log.warning(
        "effective_trade_date: prev_trading_day(%s) not found within lookback. "
        "Returning today as fallback.",
        today,
    )
    return today
