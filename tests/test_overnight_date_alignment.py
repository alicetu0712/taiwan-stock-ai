"""
tests/test_overnight_date_alignment.py — US/TW trading calendar date mapping

PRD §23-A: Date Alignment tests
  - TW Tuesday → correct completed US session (Monday)
  - TW Monday → previous completed US session (prior Friday)
  - US holiday → skip to prior US trading day
  - Taiwan holiday has no effect on US mapping
  - No future US session used
  - DST boundary cases (March, November)
  - Result date always < tw_execution_date
"""

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.us_trading_calendar import (
    is_us_trading_day,
    prev_us_trading_day,
    tw_exec_to_us_market_date,
    us_session_close_utc,
)


class TestIsUsTradingDay:

    def test_weekday_non_holiday(self):
        assert is_us_trading_day(date(2026, 10, 21)) is True   # Wednesday

    def test_saturday_not_trading(self):
        assert is_us_trading_day(date(2026, 10, 24)) is False

    def test_sunday_not_trading(self):
        assert is_us_trading_day(date(2026, 10, 25)) is False

    def test_nyse_holiday_not_trading(self):
        assert is_us_trading_day(date(2026, 11, 26)) is False   # Thanksgiving

    def test_christmas_not_trading(self):
        assert is_us_trading_day(date(2026, 12, 25)) is False

    def test_uncovered_year_fail_closed(self):
        assert is_us_trading_day(date(2030, 6, 15)) is False


class TestTwExecToUsMarketDate:

    def test_tw_tuesday_maps_to_us_monday(self):
        # TW Tue 2026-10-20 → US Mon 2026-10-19 (regular trading day)
        result = tw_exec_to_us_market_date(date(2026, 10, 20))
        assert result == date(2026, 10, 19)

    def test_tw_monday_maps_to_prior_us_friday(self):
        # TW Mon 2026-10-19 → US Fri 2026-10-16 (skip weekend)
        result = tw_exec_to_us_market_date(date(2026, 10, 19))
        assert result == date(2026, 10, 16)

    def test_tw_wednesday_maps_to_us_tuesday(self):
        result = tw_exec_to_us_market_date(date(2026, 10, 21))
        assert result == date(2026, 10, 20)

    def test_us_holiday_skipped(self):
        # TW 2026-11-27 (Fri after TW market) → US prior is 2026-11-26 Thanksgiving = holiday
        # → should skip to 2026-11-25 Wednesday
        result = tw_exec_to_us_market_date(date(2026, 11, 27))
        assert result == date(2026, 11, 25)

    def test_result_strictly_before_tw_exec(self):
        for tw_date in [
            date(2026, 10, 19),
            date(2026, 10, 20),
            date(2026, 10, 21),
            date(2026, 10, 22),
        ]:
            us_date = tw_exec_to_us_market_date(tw_date)
            assert us_date is not None
            assert us_date < tw_date, f"{us_date} must be < {tw_date}"

    def test_no_future_us_session(self):
        # Result must ALWAYS be strictly before tw_exec_date
        for tw_date in [
            date(2026, 10, 19),
            date(2026, 10, 26),
            date(2026, 11, 2),
        ]:
            us_date = tw_exec_to_us_market_date(tw_date)
            if us_date is not None:
                assert us_date < tw_date

    def test_uncovered_year_returns_none(self):
        result = tw_exec_to_us_market_date(date(2030, 6, 15))
        assert result is None


class TestUsSessionCloseUtc:
    """
    Verify DST-correct UTC conversion for US session close (16:00 ET).

    During EDT (summer, UTC-4): 16:00 ET = 20:00 UTC
    During EST (winter, UTC-5): 16:00 ET = 21:00 UTC

    DST 2026: EDT ends first Sunday November = Nov 1, 2026
    """

    def test_summer_edt_16_00_et_is_20_00_utc(self):
        # October is EDT (UTC-4)
        close = us_session_close_utc(date(2026, 10, 20))
        assert close.hour == 20
        assert close.minute == 0

    def test_winter_est_16_00_et_is_21_00_utc(self):
        # December is EST (UTC-5)
        close = us_session_close_utc(date(2026, 12, 15))
        assert close.hour == 21
        assert close.minute == 0

    def test_available_at_before_tw_open(self):
        # TW opens 09:00 CST = 01:00 UTC next calendar day
        # US close (20:00 or 21:00 UTC) < TW next-day open (01:00 UTC) → always safe
        from zoneinfo import ZoneInfo
        from datetime import datetime
        TW = ZoneInfo("Asia/Taipei")
        UTC = ZoneInfo("UTC")
        for us_date in [date(2026, 10, 20), date(2026, 12, 15)]:
            close_utc = us_session_close_utc(us_date)
            # TW execution open = next calendar day 09:00 CST
            from datetime import timedelta
            tw_open_et_naive = us_date + timedelta(days=1)
            tw_open_utc = datetime(
                tw_open_et_naive.year, tw_open_et_naive.month, tw_open_et_naive.day,
                1, 0, 0, tzinfo=UTC,
            )
            assert close_utc < tw_open_utc, f"{close_utc} must be before {tw_open_utc}"
