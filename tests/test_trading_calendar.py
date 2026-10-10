"""
tests/test_trading_calendar.py — Taiwan Trading Calendar tests

Tests the 5 specified dates:
  2026-10-08 → 正常交易日
  2026-10-09 → 國慶補假休市
  2026-10-10 → 週六休市
  2026-10-11 → 週日休市
  2026-10-12 → 正常交易日
"""

from datetime import date

import pytest

from src.core.trading_calendar import (
    MarketStatus,
    TaiwanTradingCalendar,
    is_market_closed,
    is_trading_day,
    last_trading_day,
    market_status,
    next_trading_day,
    prev_trading_day,
)

cal = TaiwanTradingCalendar()


class TestMarketStatus:
    def test_normal_trading_day_thu(self):
        """2026-10-08 (Thu) is a normal trading day."""
        d = date(2026, 10, 8)
        assert market_status(d) == MarketStatus.TRADING_DAY

    def test_national_holiday_substitute(self):
        """2026-10-09 (Fri) is National Day substitute holiday — HOLIDAY, not TRADING_DAY."""
        d = date(2026, 10, 9)
        assert market_status(d) == MarketStatus.HOLIDAY

    def test_saturday_weekend(self):
        """2026-10-10 (Sat) is a weekend."""
        d = date(2026, 10, 10)
        assert market_status(d) == MarketStatus.WEEKEND

    def test_sunday_weekend(self):
        """2026-10-11 (Sun) is a weekend."""
        d = date(2026, 10, 11)
        assert market_status(d) == MarketStatus.WEEKEND

    def test_normal_trading_day_mon(self):
        """2026-10-12 (Mon) is the next normal trading day after the long weekend."""
        d = date(2026, 10, 12)
        assert market_status(d) == MarketStatus.TRADING_DAY


class TestIsTradingDay:
    def test_thu_is_trading(self):
        assert is_trading_day(date(2026, 10, 8)) is True

    def test_holiday_not_trading(self):
        assert is_trading_day(date(2026, 10, 9)) is False

    def test_saturday_not_trading(self):
        assert is_trading_day(date(2026, 10, 10)) is False

    def test_sunday_not_trading(self):
        assert is_trading_day(date(2026, 10, 11)) is False

    def test_mon_is_trading(self):
        assert is_trading_day(date(2026, 10, 12)) is True


class TestIsMarketClosed:
    def test_trading_day_not_closed(self):
        assert is_market_closed(date(2026, 10, 8)) is False

    def test_holiday_is_closed(self):
        assert is_market_closed(date(2026, 10, 9)) is True

    def test_saturday_is_closed(self):
        assert is_market_closed(date(2026, 10, 10)) is True

    def test_sunday_is_closed(self):
        assert is_market_closed(date(2026, 10, 11)) is True

    def test_next_monday_not_closed(self):
        assert is_market_closed(date(2026, 10, 12)) is False


class TestPrevTradingDay:
    def test_from_holiday_goes_to_thu(self):
        """prev_trading_day(10/09) should return 10/08 (skipping the holiday itself)."""
        result = prev_trading_day(date(2026, 10, 9))
        assert result == date(2026, 10, 8)

    def test_from_saturday_goes_to_thu(self):
        """prev_trading_day(10/10) should return 10/08 (10/09 is holiday, 10/10 is weekend)."""
        result = prev_trading_day(date(2026, 10, 10))
        assert result == date(2026, 10, 8)

    def test_from_sunday_goes_to_thu(self):
        """prev_trading_day(10/11) should return 10/08."""
        result = prev_trading_day(date(2026, 10, 11))
        assert result == date(2026, 10, 8)

    def test_from_monday_goes_to_thu(self):
        """prev_trading_day(10/12) should return 10/08."""
        result = prev_trading_day(date(2026, 10, 12))
        assert result == date(2026, 10, 8)


class TestNextTradingDay:
    def test_from_thu_goes_to_mon(self):
        """next_trading_day(10/08) should return 10/12 (10/09 holiday, 10/10-11 weekend)."""
        result = next_trading_day(date(2026, 10, 8))
        assert result == date(2026, 10, 12)

    def test_from_holiday_goes_to_mon(self):
        """next_trading_day(10/09) should return 10/12."""
        result = next_trading_day(date(2026, 10, 9))
        assert result == date(2026, 10, 12)


class TestLastTradingDay:
    def test_on_trading_day_returns_self(self):
        """last_trading_day includes the date itself if it's a trading day."""
        result = last_trading_day(date(2026, 10, 8))
        assert result == date(2026, 10, 8)

    def test_on_holiday_returns_prev(self):
        result = last_trading_day(date(2026, 10, 9))
        assert result == date(2026, 10, 8)

    def test_on_weekend_returns_prev(self):
        result = last_trading_day(date(2026, 10, 10))
        assert result == date(2026, 10, 8)


class TestDataValidatorWithCalendar:
    """Integration test: DataValidator should reject holiday dates with MARKET_CLOSED."""

    def test_holiday_rejected_even_with_data(self):
        import pandas as pd
        from src.validators.data_validator import DataValidator

        validator = DataValidator()
        # Fake a 200-row dataframe to bypass count check
        df = pd.DataFrame({
            "stock_id": [str(i).zfill(4) for i in range(200)],
            "close":    [100.0] * 200,
            "volume":   [10000.0] * 200,
        })
        valid, msg = validator.validate_price_data(df, date(2026, 10, 9))
        assert not valid, "Holiday should be rejected regardless of data count"
        assert "MARKET_CLOSED" in msg

    def test_weekend_rejected(self):
        import pandas as pd
        from src.validators.data_validator import DataValidator

        validator = DataValidator()
        df = pd.DataFrame({
            "stock_id": [str(i).zfill(4) for i in range(200)],
            "close":    [100.0] * 200,
            "volume":   [10000.0] * 200,
        })
        valid, msg = validator.validate_price_data(df, date(2026, 10, 10))
        assert not valid
        assert "MARKET_CLOSED" in msg

    def test_trading_day_passes_with_good_data(self):
        import pandas as pd
        from src.validators.data_validator import DataValidator

        validator = DataValidator()
        df = pd.DataFrame({
            "stock_id": [str(i).zfill(4) for i in range(200)],
            "close":    [100.0] * 200,
            "volume":   [10000.0] * 200,
        })
        valid, msg = validator.validate_price_data(df, date(2026, 10, 8))
        assert valid

    def test_trading_day_low_count_is_data_incomplete(self):
        import pandas as pd
        from src.validators.data_validator import DataValidator

        validator = DataValidator()
        df = pd.DataFrame({
            "stock_id": ["0050", "0051"],
            "close":    [100.0, 200.0],
            "volume":   [10000.0, 5000.0],
        })
        valid, msg = validator.validate_price_data(df, date(2026, 10, 8))
        assert not valid
        assert "DATA_INCOMPLETE" in msg
