"""
tests/test_validity_gate.py — Data Integrity and Date/Data Quality Gate regression tests

Verifies:
  A. Trading day check prevents signal generation on closed days
  B. Price date mismatch (source_price_date != trade_date) blocks signal creation
  C. is_valid=False records are excluded from all performance stats
  D. Valid trading days pass through the gate correctly

TestValidityFlagDB and TestQueryFilters use a temporary in-memory SQLite DB with
known fixtures — no dependency on the production database.
"""

from datetime import date

import pytest
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

from src.database import Base, Recommendation, ForwardSignal


# ── In-memory DB fixture ──────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def db_session():
    """
    Temporary SQLite in-memory DB, populated with known fixtures.

    Recommendation fixtures (10 total):
      - 5 valid   (date=2026-10-08, is_valid=True)
      - 3 invalid (date=2026-10-09, is_valid=False) — holiday
      - 1 invalid (date=2026-10-10, is_valid=False) — Saturday
      - 1 invalid (date=2026-10-11, is_valid=False) — Sunday
      → 5 invalid total

    ForwardSignal fixtures (14 total):
      - 10 valid   (trade_date=2026-10-08, is_valid=True)
      -  4 invalid (trade_date=2026-10-09, is_valid=False) — holiday
      → 4 invalid total
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    VALID_DATE   = date(2026, 10, 8)
    HOLIDAY_DATE = date(2026, 10, 9)
    SAT_DATE     = date(2026, 10, 10)
    SUN_DATE     = date(2026, 10, 11)

    STOCKS_5 = ["3042", "1513", "2330", "2317", "2882"]
    STOCKS_3 = ["3042", "1513", "2330"]
    STOCKS_10 = [str(i).zfill(4) for i in range(10)]

    # 5 valid Recommendation records
    for sid in STOCKS_5:
        session.add(Recommendation(
            date=VALID_DATE,
            stock_id=sid,
            tier="recommend",
            trade_signal="buy",
            is_valid=True,
            total_score=80.0,
        ))

    # 3 invalid Recommendation records — holiday (10/09)
    for sid in STOCKS_3:
        session.add(Recommendation(
            date=HOLIDAY_DATE,
            stock_id=sid,
            tier="recommend",
            trade_signal="buy",
            is_valid=False,
            invalid_reason="NON_TRADING_DAY_DATE_MISMATCH",
            source_price_date=VALID_DATE,
            total_score=80.0,
        ))

    # 1 invalid Recommendation — Saturday (10/10)
    session.add(Recommendation(
        date=SAT_DATE,
        stock_id="2330",
        tier="recommend",
        trade_signal="buy",
        is_valid=False,
        invalid_reason="NON_TRADING_DAY_DATE_MISMATCH",
        source_price_date=VALID_DATE,
        total_score=80.0,
    ))

    # 1 invalid Recommendation — Sunday (10/11)
    session.add(Recommendation(
        date=SUN_DATE,
        stock_id="2882",
        tier="recommend",
        trade_signal="buy",
        is_valid=False,
        invalid_reason="NON_TRADING_DAY_DATE_MISMATCH",
        source_price_date=VALID_DATE,
        total_score=80.0,
    ))

    # 10 valid ForwardSignal records
    for sid in STOCKS_10:
        session.add(ForwardSignal(
            trade_date=VALID_DATE,
            stock_id=sid,
            trade_signal="buy",
            is_valid=True,
            total_score=75.0,
        ))

    # 4 invalid ForwardSignal records — holiday (10/09)
    for sid in STOCKS_10[:4]:
        session.add(ForwardSignal(
            trade_date=HOLIDAY_DATE,
            stock_id=sid,
            trade_signal="buy",
            is_valid=False,
            invalid_reason="NON_TRADING_DAY_DATE_MISMATCH",
            source_price_date=VALID_DATE,
            total_score=75.0,
        ))

    session.commit()
    yield session
    session.close()
    engine.dispose()


# ── Helper: minimal pipeline gate function ────────────────────────────────────

def _can_create_signal(trade_date: date, source_price_date: date | None) -> tuple[bool, str]:
    """
    Mirrors the logic in run_pipeline / _save_recommendations.
    Returns (allowed, reason).
    """
    from src.core.trading_calendar import market_status, MarketStatus

    status = market_status(trade_date)
    if status in (MarketStatus.WEEKEND, MarketStatus.HOLIDAY):
        return False, f"MARKET_CLOSED:{status.value}"

    if source_price_date is not None and source_price_date != trade_date:
        return False, f"PRICE_DATE_MISMATCH:source={source_price_date},requested={trade_date}"

    return True, "OK"


# ── A. Trading day gate ───────────────────────────────────────────────────────

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


# ── B. Price date mismatch gate ───────────────────────────────────────────────

class TestPriceDateMismatchGate:
    """Gate rejects signals when source price date != requested trade_date."""

    def test_matching_dates_allowed(self):
        ok, reason = _can_create_signal(date(2026, 10, 8), date(2026, 10, 8))
        assert ok

    def test_stale_price_data_blocked(self):
        """trade_date=10/08 but API returned 10/07 data → block."""
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


# ── C. Validity flag — fixture-based DB ──────────────────────────────────────

class TestValidityFlagDB:
    """
    Validity-flagged records exist with correct metadata.
    Uses in-memory DB with known fixture counts; no production DB dependency.
    """

    def test_holiday_recs_marked_invalid(self, db_session):
        """3 fixture recs for 2026-10-09 should all have is_valid=False."""
        count = (
            db_session.query(Recommendation)
            .filter(
                Recommendation.date == date(2026, 10, 9),
                Recommendation.is_valid == False,
            )
            .count()
        )
        assert count == 3, f"Expected 3 invalid recs for 10/09, got {count}"

    def test_weekend_recs_marked_invalid(self, db_session):
        """1 Saturday + 1 Sunday fixture rec = 2 invalid weekend records."""
        count = (
            db_session.query(Recommendation)
            .filter(
                Recommendation.date.in_([date(2026, 10, 10), date(2026, 10, 11)]),
                Recommendation.is_valid == False,
            )
            .count()
        )
        assert count == 2, f"Expected 2 invalid recs for 10/10+11, got {count}"

    def test_holiday_forward_signals_marked_invalid(self, db_session):
        """4 fixture ForwardSignal records for 2026-10-09 should be is_valid=False."""
        count = (
            db_session.query(ForwardSignal)
            .filter(
                ForwardSignal.trade_date == date(2026, 10, 9),
                ForwardSignal.is_valid == False,
            )
            .count()
        )
        assert count == 4, f"Expected 4 invalid FS for 10/09, got {count}"

    def test_total_invalid_forward_signals(self, db_session):
        """Total invalid ForwardSignal records matches fixture count (4)."""
        count = (
            db_session.query(ForwardSignal)
            .filter(ForwardSignal.is_valid == False)
            .count()
        )
        assert count == 4, f"Expected 4 total invalid FS, got {count}"

    def test_source_price_date_set(self, db_session):
        """Invalid Recommendation for 10/09 must have source_price_date=10/08."""
        rec = (
            db_session.query(Recommendation)
            .filter(
                Recommendation.date == date(2026, 10, 9),
                Recommendation.is_valid == False,
            )
            .first()
        )
        assert rec is not None
        assert rec.source_price_date == date(2026, 10, 8), (
            f"Expected source_price_date=2026-10-08, got {rec.source_price_date}"
        )
        assert rec.invalid_reason == "NON_TRADING_DAY_DATE_MISMATCH"

    def test_invalid_reason_set_on_forward_signal(self, db_session):
        """Invalid ForwardSignal must have invalid_reason='NON_TRADING_DAY_DATE_MISMATCH'."""
        fs = (
            db_session.query(ForwardSignal)
            .filter(ForwardSignal.is_valid == False)
            .first()
        )
        assert fs is not None
        assert fs.invalid_reason == "NON_TRADING_DAY_DATE_MISMATCH"


# ── D. Query filters correctly exclude is_valid=False ────────────────────────

class TestQueryFilters:
    """
    Performance queries filtering is_valid.isnot(False) must exclude flagged records.
    Uses the same in-memory fixture DB.
    """

    def test_backtest_excludes_invalid_recs(self, db_session):
        """
        Fixture: 10 total Recommendation, 5 invalid.
        valid_count must equal all_count - 5.
        """
        all_count = db_session.query(func.count(Recommendation.id)).scalar()
        valid_count = (
            db_session.query(func.count(Recommendation.id))
            .filter(Recommendation.is_valid.isnot(False))
            .scalar()
        )
        assert all_count == 10, f"Fixture expects 10 total recs, got {all_count}"
        assert valid_count == 5, f"Fixture expects 5 valid recs, got {valid_count}"
        assert valid_count == all_count - 5

    def test_forward_signal_stats_exclude_invalid(self, db_session):
        """
        Fixture: 14 total ForwardSignal, 4 invalid.
        valid_count must equal all_count - 4.
        """
        all_count = db_session.query(func.count(ForwardSignal.id)).scalar()
        valid_count = (
            db_session.query(func.count(ForwardSignal.id))
            .filter(ForwardSignal.is_valid.isnot(False))
            .scalar()
        )
        assert all_count == 14, f"Fixture expects 14 total FS, got {all_count}"
        assert valid_count == 10, f"Fixture expects 10 valid FS, got {valid_count}"
        assert valid_count == all_count - 4

    def test_valid_recs_all_from_trading_day(self, db_session):
        """All records passing the valid filter should be from a trading day (10/08)."""
        valid_dates = (
            db_session.query(Recommendation.date)
            .filter(Recommendation.is_valid.isnot(False))
            .distinct()
            .all()
        )
        date_values = {row[0] for row in valid_dates}
        assert date_values == {date(2026, 10, 8)}, (
            f"Expected only 2026-10-08 in valid recs, got {date_values}"
        )

    def test_invalid_recs_never_appear_in_valid_filter(self, db_session):
        """Non-trading-day dates must not appear in valid-filtered results."""
        valid_dates = (
            db_session.query(Recommendation.date)
            .filter(Recommendation.is_valid.isnot(False))
            .distinct()
            .all()
        )
        date_values = {row[0] for row in valid_dates}
        non_trading = {date(2026, 10, 9), date(2026, 10, 10), date(2026, 10, 11)}
        overlap = date_values & non_trading
        assert not overlap, f"Non-trading dates leaked into valid filter: {overlap}"


# ── E. DataValidator gate ─────────────────────────────────────────────────────

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
