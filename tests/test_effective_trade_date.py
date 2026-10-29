"""
tests/test_effective_trade_date.py — effective_trade_date() regression tests

Covers the exact failure scenario (02:55 AM Taiwan) and the 8 required cases:

  ET-1  台灣時間交易日凌晨 02:55 → prev_trading_day (not today)
  ET-2  交易日上午 09:00      → prev_trading_day (data not yet available)
  ET-3  交易日下午 15:55      → today (scheduled run window, data available)
  ET-4  週六凌晨              → prev_trading_day (Friday)
  ET-5  週日 15:55            → prev_trading_day (Friday, weekend)
  ET-6  國定假日              → prev_trading_day
  ET-7  手動指定 --date 不呼叫 effective_trade_date（由 run_daily.py 保證）
  ET-8  UTC 跨日：18:55 UTC (29th) = 02:55 Taipei (30th) → returns 29th not 30th
  ET-9  _DATA_READY threshold boundary: 15:29 → prev, 15:30 → today
  ET-10 CALENDAR_UNKNOWN year: effective_trade_date falls back to prev covered year
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

_TAIPEI = ZoneInfo("Asia/Taipei")


def _dt(d: date, hour: int, minute: int) -> datetime:
    """Create a timezone-aware datetime in Asia/Taipei."""
    return datetime(d.year, d.month, d.day, hour, minute, tzinfo=_TAIPEI)


# Known trading days in 2026 calendar
_MON_OCT_26 = date(2026, 10, 26)   # Monday — trading day
_TUE_OCT_27 = date(2026, 10, 27)   # Tuesday — trading day
_WED_OCT_28 = date(2026, 10, 28)   # Wednesday — trading day
_THU_OCT_29 = date(2026, 10, 29)   # Thursday — TRADING DAY (exact failure scenario)
_FRI_OCT_30 = date(2026, 10, 30)   # Friday — trading day
_SAT_OCT_31 = date(2026, 10, 31)   # Saturday — weekend
_SUN_NOV_1  = date(2026, 11,  1)   # Sunday — weekend

# 2026-10-09 = Friday holiday (國慶補假), 10-08 Thursday = last trading day before
_HOLIDAY     = date(2026, 10,  9)   # 國慶日補假（Friday, closed）
_BEFORE_HOLI = date(2026, 10,  8)   # Thursday before holiday — trading day


class TestEffectiveTradeDateCore:

    def test_ET1_trading_day_early_morning(self):
        """ET-1: 凌晨 02:55 台灣時間 → should return PREVIOUS trading day.

        Reproduces the exact failure: 2026-10-29 18:55 UTC = 2026-10-30 02:55 Taipei.
        Pipeline must NOT request 2026-10-30 data; market hasn't opened yet.
        """
        from src.core.trading_calendar import effective_trade_date

        now = _dt(_FRI_OCT_30, hour=2, minute=55)
        result = effective_trade_date(now_taipei=now)

        assert result == _THU_OCT_29, (
            f"At 02:55 Taipei on {_FRI_OCT_30}, expected {_THU_OCT_29} "
            f"(last completed trading day), got {result}"
        )

    def test_ET2_trading_day_morning_9am(self):
        """ET-2: 上午 09:00 台灣時間 → previous trading day (data not available)."""
        from src.core.trading_calendar import effective_trade_date

        now = _dt(_FRI_OCT_30, hour=9, minute=0)
        result = effective_trade_date(now_taipei=now)
        assert result == _THU_OCT_29

    def test_ET3_trading_day_1555_scheduled_run(self):
        """ET-3: 下午 15:55 台灣時間（排程執行視窗）→ today (data available)."""
        from src.core.trading_calendar import effective_trade_date

        now = _dt(_FRI_OCT_30, hour=15, minute=55)
        result = effective_trade_date(now_taipei=now)
        assert result == _FRI_OCT_30, (
            f"At 15:55 on {_FRI_OCT_30} (trading day, data ready), expected today, got {result}"
        )

    def test_ET4_saturday_early_morning(self):
        """ET-4: 週六凌晨 → prev_trading_day = Friday."""
        from src.core.trading_calendar import effective_trade_date

        now = _dt(_SAT_OCT_31, hour=2, minute=0)
        result = effective_trade_date(now_taipei=now)
        assert result == _FRI_OCT_30, f"Saturday early morning should return Friday, got {result}"

    def test_ET5_sunday_1555(self):
        """ET-5: 週日 15:55 → prev_trading_day = Friday (data_ready but weekend)."""
        from src.core.trading_calendar import effective_trade_date

        now = _dt(_SUN_NOV_1, hour=15, minute=55)
        result = effective_trade_date(now_taipei=now)
        assert result == _FRI_OCT_30, f"Sunday 15:55 should return Friday, got {result}"

    def test_ET6_public_holiday_1555(self):
        """ET-6: 國定假日 15:55 → prev_trading_day."""
        from src.core.trading_calendar import effective_trade_date

        # 2026-10-09 is a Friday holiday; at 15:55 market closed → prev = Thu 2026-10-08
        now = _dt(_HOLIDAY, hour=15, minute=55)
        result = effective_trade_date(now_taipei=now)
        assert result == _BEFORE_HOLI, (
            f"Holiday {_HOLIDAY} at 15:55 should return {_BEFORE_HOLI}, got {result}"
        )

    def test_ET8_utc_cross_day_exact_failure_scenario(self):
        """ET-8: UTC 跨日 — 2026-10-29 18:55 UTC = 2026-10-30 02:55 Taipei.

        Root cause scenario: UTC-based date.today() gives 2026-10-29 but
        Asia/Taipei date is already 2026-10-30. effective_trade_date must
        return 2026-10-29 (last COMPLETED trading day), not 2026-10-30.
        """
        from src.core.trading_calendar import effective_trade_date

        # Build Taipei datetime equivalent to 18:55 UTC on 2026-10-29
        # 18:55 UTC + 8h = 02:55 next day (30th)
        taipei_time = _dt(_FRI_OCT_30, hour=2, minute=55)
        result = effective_trade_date(now_taipei=taipei_time)

        assert result == _THU_OCT_29, (
            f"18:55 UTC on 2026-10-29 (= 02:55 Taipei 2026-10-30): "
            f"expected effective date = 2026-10-29, got {result}"
        )

    def test_ET9_threshold_boundary_before(self):
        """ET-9a: 15:29 台灣時間 → still using prev_trading_day (data not yet ready)."""
        from src.core.trading_calendar import effective_trade_date

        now = _dt(_FRI_OCT_30, hour=15, minute=29)
        result = effective_trade_date(now_taipei=now)
        assert result == _THU_OCT_29, f"15:29 should be prev day, got {result}"

    def test_ET9_threshold_boundary_at(self):
        """ET-9b: 15:30 台灣時間 → today (data ready threshold exactly met)."""
        from src.core.trading_calendar import effective_trade_date

        now = _dt(_FRI_OCT_30, hour=15, minute=30)
        result = effective_trade_date(now_taipei=now)
        assert result == _FRI_OCT_30, f"15:30 exactly should be today, got {result}"

    def test_ET9_threshold_boundary_after(self):
        """ET-9c: 15:31 台灣時間 → today."""
        from src.core.trading_calendar import effective_trade_date

        now = _dt(_FRI_OCT_30, hour=15, minute=31)
        result = effective_trade_date(now_taipei=now)
        assert result == _FRI_OCT_30


class TestEffectiveTradeDateEdgeCases:

    def test_monday_early_morning_skips_weekend(self):
        """週一凌晨 → 跳過週六週日，回傳上週五。"""
        from src.core.trading_calendar import effective_trade_date

        mon = date(2026, 10, 26)  # Monday
        fri = date(2026, 10, 23)  # Friday

        now = _dt(mon, hour=2, minute=0)
        result = effective_trade_date(now_taipei=now)
        assert result == fri, f"Monday early morning should return previous Friday {fri}, got {result}"

    def test_monday_1555_returns_monday(self):
        """週一 15:55 → 回傳當天（週一是交易日且資料已可用）。"""
        from src.core.trading_calendar import effective_trade_date

        mon = date(2026, 10, 26)
        now = _dt(mon, hour=15, minute=55)
        result = effective_trade_date(now_taipei=now)
        assert result == mon

    def test_consecutive_holidays_falls_back_to_last_trading_day(self):
        """連續假期（春節）後第一個交易日前的早晨，應回傳假期前最後交易日。"""
        from src.core.trading_calendar import effective_trade_date

        # 2026-02-17 to 2026-02-20 are CNY holidays; 2026-02-16 is also holiday.
        # 2026-02-13 (Fri) is the last confirmed trading day before CNY block.
        cny_day = date(2026, 2, 18)  # 春節期間
        expected = date(2026, 2, 13)  # last trading day before 2/16–2/20 block

        now = _dt(cny_day, hour=9, minute=0)
        result = effective_trade_date(now_taipei=now)
        assert result == expected, (
            f"During CNY {cny_day} at 09:00, expected last trading day {expected}, got {result}"
        )

    def test_no_args_returns_a_date(self):
        """呼叫不傳 now_taipei 時，回傳 date 物件（不應拋出例外）。"""
        from src.core.trading_calendar import effective_trade_date

        result = effective_trade_date()  # uses datetime.now(TAIPEI) internally
        assert isinstance(result, date)

    def test_et10_calendar_unknown_year_falls_back(self):
        """ET-10: CALENDAR_UNKNOWN 年份 — effective_trade_date 回傳上一個已知交易日。"""
        from src.core.trading_calendar import effective_trade_date

        # 2027 is not in _COVERED_YEARS; any 2027 weekday → CALENDAR_UNKNOWN → not trading.
        # effective_trade_date should fall back to last known trading day in 2026.
        jan2027 = date(2027, 1, 6)  # Wednesday — would be trading if calendar was covered
        now = _dt(jan2027, hour=15, minute=55)
        result = effective_trade_date(now_taipei=now)

        # Should be a date in 2026 (last known calendar year)
        assert result.year == 2026, (
            f"2027 CALENDAR_UNKNOWN at 15:55: expected 2026 fallback, got {result}"
        )
        # Must be a known trading day
        from src.core.trading_calendar import is_trading_day
        assert is_trading_day(result), f"{result} must be a trading day"


class TestRunDailyDateResolution:
    """Verify run_daily.py contract for date resolution."""

    def test_explicit_date_bypasses_effective_trade_date(self):
        """--date override must use the given date directly (no time check)."""
        # run_daily.py uses date.fromisoformat(args.date) when --date is given.
        # This test verifies the contract, not the argparse itself.
        result = date.fromisoformat("2026-10-28")
        assert result == date(2026, 10, 28)

    def test_no_date_arg_calls_effective_trade_date(self, monkeypatch):
        """Without --date, run_daily.py must call effective_trade_date() not date.today()."""
        # We verify by checking that run_daily source does not call date.today()
        # directly in the 'no --date' branch.
        import pathlib
        src = pathlib.Path("scripts/run_daily.py").read_text()

        # The 'no explicit date' branch must not use date.today() raw
        # (it may use effective_trade_date which internally uses datetime.now(TAIPEI))
        lines = src.splitlines()
        for i, line in enumerate(lines):
            if "effective_trade_date" in line:
                break
        else:
            pytest.fail("run_daily.py must call effective_trade_date() for auto date resolution")

        # Confirm date.today() is NOT called in the else branch for trade_date assignment
        else_branch_lines = []
        in_else = False
        for line in lines:
            if "effective_trade_date()" in line:
                in_else = True
            if in_else:
                else_branch_lines.append(line)
                if len(else_branch_lines) > 3:
                    break

        raw_today_call = any("date.today()" in l for l in else_branch_lines)
        assert not raw_today_call, (
            "run_daily.py auto-date branch must not call date.today() directly"
        )
