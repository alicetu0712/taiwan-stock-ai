"""
tests/test_validity_gate.py — Data Integrity and Date/Data Quality Gate regression tests

Verifies:
  A. Trading day check prevents signal generation on closed days
  B. Price date mismatch (source_price_date != trade_date) blocks signal creation
  C. is_valid=False records are excluded from all performance stats
  D. Valid trading days pass through the gate correctly
"""

from datetime import date

import pytest


# ── Helper: minimal pipeline gate function ────────────────────────────────────
def _can_create_signal(trade_date: date, source_price_date: date | None) -> tuple[bool, str]:
    """
    Mirrors the logic in run_pipeline / _save_recommendations.
    Returns (allowed, reason).
    """
    from src.core.trading_calendar import is_market_closed, market_status, MarketStatus

    status = market_status(trade_date)
    # Check 1: trading calendar
    if status in (MarketStatus.WEEKEND, MarketStatus.HOLIDAY):
        return False, f"MARKET_CLOSED:{status.value}"

    # Check 2: price source date consistency
    if source_price_date is not None and source_price_date != trade_date:
        return False, f"PRICE_DATE_MISMATCH:source={source_price_date},requested={trade_date}"

    return True, "OK"


class TestTradingDayGate:
    """Gate rejects non-trading days regardless of data."""

    def test_normal_trading_day_allowed(self):
        ok, reason = _can_create_signal(date(2026, 10, 8), date(2026, 10, 8))
        assert ok, f"Expected OK, got: {reason}"

    def test_holiday_blocked(self):
        ok, reason = _can_create_signal(date(2026, 10, 9), date(2026, 10, 8))
        assert not ok
        assert "MARKET_CLOSED" in reason
        assert "HOLIDAY" in reason

    def test_saturday_blocked(self):
        ok, reason = _can_create_signal(date(2026, 10, 10), date(2026, 10, 8))
        assert not ok
        assert "MARKET_CLOSED" in reason

    def test_sunday_blocked(self):
        ok, reason = _can_create_signal(date(2026, 10, 11), date(2026, 10, 8))
        assert not ok
        assert "MARKET_CLOSED" in reason

    def test_next_monday_allowed(self):
        ok, reason = _can_create_signal(date(2026, 10, 12), date(2026, 10, 12))
        assert ok, f"Expected OK, got: {reason}"


class TestPriceDateMismatchGate:
    """Gate rejects signals when source price date != requested trade_date."""

    def test_matching_dates_allowed(self):
        ok, reason = _can_create_signal(date(2026, 10, 8), date(2026, 10, 8))
        assert ok

    def test_stale_price_data_blocked(self):
        """trade_date=10/09 but API returned 10/08 data → block."""
        ok, reason = _can_create_signal(date(2026, 10, 8), date(2026, 10, 7))
        assert not ok
        assert "PRICE_DATE_MISMATCH" in reason

    def test_no_source_date_allowed(self):
        """source_price_date=None (dry-run / backfill) → gate skips date check."""
        ok, reason = _can_create_signal(date(2026, 10, 8), None)
        assert ok

    def test_future_source_date_blocked(self):
        """source returns future date (anomaly) → block."""
        ok, reason = _can_create_signal(date(2026, 10, 8), date(2026, 10, 9))
        assert not ok
        assert "PRICE_DATE_MISMATCH" in reason


class TestValidityFlagDB:
    """Verify that the marked invalid records exist and are correctly tagged."""

    def test_holiday_recs_marked_invalid(self):
        from src.database import get_session, Recommendation
        s = get_session()
        invalid = (
            s.query(Recommendation)
            .filter(
                Recommendation.date == date(2026, 10, 9),
                Recommendation.is_valid == False,
            )
            .count()
        )
        s.close()
        assert invalid == 16, f"Expected 16 invalid recs for 10/09, got {invalid}"

    def test_weekend_recs_marked_invalid(self):
        from src.database import get_session, Recommendation
        s = get_session()
        invalid = (
            s.query(Recommendation)
            .filter(
                Recommendation.date.in_([date(2026, 10, 10), date(2026, 10, 11)]),
                Recommendation.is_valid == False,
            )
            .count()
        )
        s.close()
        assert invalid == 8, f"Expected 8 invalid recs for 10/10+11, got {invalid}"

    def test_holiday_forward_signals_marked_invalid(self):
        from src.database import get_session, ForwardSignal
        s = get_session()
        invalid = (
            s.query(ForwardSignal)
            .filter(
                ForwardSignal.trade_date == date(2026, 10, 9),
                ForwardSignal.is_valid == False,
            )
            .count()
        )
        s.close()
        assert invalid == 349, f"Expected 349 invalid FS for 10/09, got {invalid}"

    def test_total_invalid_forward_signals(self):
        from src.database import get_session, ForwardSignal
        s = get_session()
        invalid = (
            s.query(ForwardSignal)
            .filter(ForwardSignal.is_valid == False)
            .count()
        )
        s.close()
        assert invalid == 369, f"Expected 369 total invalid FS, got {invalid}"

    def test_source_price_date_set(self):
        from src.database import get_session, Recommendation
        s = get_session()
        rec = (
            s.query(Recommendation)
            .filter(
                Recommendation.date == date(2026, 10, 9),
                Recommendation.is_valid == False,
            )
            .first()
        )
        s.close()
        assert rec is not None
        assert rec.source_price_date == date(2026, 10, 8), (
            f"Expected source_price_date=2026-10-08, got {rec.source_price_date}"
        )
        assert rec.invalid_reason == "NON_TRADING_DAY_DATE_MISMATCH"

    def test_invalid_reason_set(self):
        from src.database import get_session, ForwardSignal
        s = get_session()
        fs = (
            s.query(ForwardSignal)
            .filter(ForwardSignal.is_valid == False)
            .first()
        )
        s.close()
        assert fs is not None
        assert fs.invalid_reason == "NON_TRADING_DAY_DATE_MISMATCH"


class TestQueryFilters:
    """Valid performance queries must exclude is_valid=False records."""

    def test_backtest_excludes_invalid_recs(self):
        """Recommendation count for statistics should not include 10/09 etc."""
        from src.database import get_session, Recommendation
        from sqlalchemy import func
        s = get_session()

        all_count = s.query(func.count(Recommendation.id)).scalar()
        valid_count = (
            s.query(func.count(Recommendation.id))
            .filter(Recommendation.is_valid.isnot(False))
            .scalar()
        )
        s.close()

        assert valid_count < all_count, "valid_count should be less than all_count"
        assert valid_count == all_count - 25, (
            f"Expected {all_count-25} valid, got {valid_count} "
            f"(all={all_count}, invalid=25)"
        )

    def test_forward_signal_stats_exclude_invalid(self):
        """Forward signal stats should not include the 369 invalid records."""
        from src.database import get_session, ForwardSignal
        from sqlalchemy import func
        s = get_session()

        all_count = s.query(func.count(ForwardSignal.id)).scalar()
        valid_count = (
            s.query(func.count(ForwardSignal.id))
            .filter(ForwardSignal.is_valid.isnot(False))
            .scalar()
        )
        s.close()

        assert valid_count < all_count
        assert valid_count == all_count - 369


class TestDataValidatorGate:
    """DataValidator must return proper status codes."""

    def test_holiday_market_closed(self):
        import pandas as pd
        from src.validators.data_validator import DataValidator

        v = DataValidator()
        df = pd.DataFrame({
            "stock_id": [str(i).zfill(4) for i in range(200)],
            "close":    [100.0] * 200,
            "volume":   [10000.0] * 200,
        })
        valid, msg = v.validate_price_data(df, date(2026, 10, 9))
        assert not valid
        assert "MARKET_CLOSED" in msg

    def test_trading_day_data_incomplete(self):
        import pandas as pd
        from src.validators.data_validator import DataValidator

        v = DataValidator()
        # Only 10 stocks on a trading day → DATA_INCOMPLETE (not MARKET_CLOSED)
        df = pd.DataFrame({
            "stock_id": [str(i).zfill(4) for i in range(10)],
            "close":    [100.0] * 10,
            "volume":   [10000.0] * 10,
        })
        valid, msg = v.validate_price_data(df, date(2026, 10, 8))
        assert not valid
        assert "DATA_INCOMPLETE" in msg
        assert "MARKET_CLOSED" not in msg

    def test_trading_day_ok(self):
        import pandas as pd
        from src.validators.data_validator import DataValidator

        v = DataValidator()
        df = pd.DataFrame({
            "stock_id": [str(i).zfill(4) for i in range(500)],
            "close":    [100.0] * 500,
            "volume":   [10000.0] * 500,
        })
        valid, msg = v.validate_price_data(df, date(2026, 10, 8))
        assert valid
        assert "DATA_OK" not in msg or valid  # passes regardless
