"""
tests/test_overnight_execution_guidance.py — ExecutionGuidanceEngine + persistence

PRD §23-D: Execution Guidance matrix
PRD §23-E: Persistence (unique constraint)
PRD §23-F: Failure / graceful degradation
"""

import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import Base, OvernightMarketContext
from src.engines.live_decision import LiveStatus
from src.engines.overnight_risk import (
    OVERNIGHT_RULE_VERSION, DQ_COMPLETE, DQ_UNKNOWN,
    RISK_GREEN, RISK_YELLOW, RISK_RED, RISK_UNKNOWN,
)
from src.engines.execution_guidance import (
    ExecutionGuidance, evaluate_execution_guidance,
)


# ── ExecutionGuidance matrix (PRD §23-D) ─────────────────────────────────────

class TestExecutionGuidanceMatrix:

    def _g(self, signal, live, overnight):
        return evaluate_execution_guidance(signal, live, overnight).guidance

    # PRD explicit cases
    def test_buy_green_in_range_is_proceed(self):
        assert self._g("buy", LiveStatus.IN_RANGE, RISK_GREEN) == ExecutionGuidance.PROCEED

    def test_buy_yellow_in_range_is_wait_open(self):
        assert self._g("buy", LiveStatus.IN_RANGE, RISK_YELLOW) == ExecutionGuidance.WAIT_OPEN_CONFIRMATION

    def test_buy_red_in_range_is_wait_stabilization(self):
        assert self._g("buy", LiveStatus.IN_RANGE, RISK_RED) == ExecutionGuidance.WAIT_STABILIZATION

    def test_buy_red_rapid_drop_is_wait_stabilization(self):
        assert self._g("buy", LiveStatus.RAPID_DROP, RISK_RED) == ExecutionGuidance.WAIT_STABILIZATION

    def test_buy_red_watching_low_is_wait_reconfirmation(self):
        assert self._g("buy", LiveStatus.WATCHING_LOW, RISK_RED) == ExecutionGuidance.WAIT_RECONFIRMATION

    def test_buy_red_entry_reconfirmed_is_proceed_not_blocked(self):
        # PRD: "不要因 Overnight RED 永久封鎖 ENTRY_RECONFIRMED"
        assert self._g("buy", LiveStatus.ENTRY_RECONFIRMED, RISK_RED) == ExecutionGuidance.PROCEED

    def test_buy_green_entry_reconfirmed_is_proceed(self):
        assert self._g("buy", LiveStatus.ENTRY_RECONFIRMED, RISK_GREEN) == ExecutionGuidance.PROCEED

    # Non-BUY signals
    def test_wait_signal_is_not_applicable(self):
        assert self._g("wait", LiveStatus.IN_RANGE, RISK_GREEN) == ExecutionGuidance.NOT_APPLICABLE

    def test_sell_signal_is_not_applicable(self):
        assert self._g("sell", LiveStatus.IN_RANGE, RISK_GREEN) == ExecutionGuidance.NOT_APPLICABLE

    # CANCEL always INVALIDATED
    def test_cancel_is_invalidated_regardless_of_overnight(self):
        for risk in (RISK_GREEN, RISK_YELLOW, RISK_RED, RISK_UNKNOWN):
            assert self._g("buy", LiveStatus.CANCEL, risk) == ExecutionGuidance.INVALIDATED

    # ABOVE_RANGE / CHASING never proceed
    def test_above_range_is_do_not_chase(self):
        for risk in (RISK_GREEN, RISK_YELLOW, RISK_RED, RISK_UNKNOWN):
            assert self._g("buy", LiveStatus.ABOVE_RANGE, risk) == ExecutionGuidance.DO_NOT_CHASE

    def test_chasing_is_do_not_chase(self):
        for risk in (RISK_GREEN, RISK_YELLOW, RISK_RED, RISK_UNKNOWN):
            assert self._g("buy", LiveStatus.CHASING, risk) == ExecutionGuidance.DO_NOT_CHASE

    # DATE_UNKNOWN / NO_RANGE
    def test_date_unknown_is_data_insufficient(self):
        assert self._g("buy", LiveStatus.DATE_UNKNOWN, RISK_GREEN) == ExecutionGuidance.DATA_INSUFFICIENT

    def test_no_range_is_data_insufficient(self):
        assert self._g("buy", LiveStatus.NO_RANGE, RISK_GREEN) == ExecutionGuidance.DATA_INSUFFICIENT

    # Caution flag for ENTRY_RECONFIRMED + RED
    def test_entry_reconfirmed_red_has_caution_flag(self):
        result = evaluate_execution_guidance("buy", LiveStatus.ENTRY_RECONFIRMED, RISK_RED)
        assert result.guidance == ExecutionGuidance.PROCEED
        assert result.caution is True
        assert result.caution_text != ""

    def test_entry_reconfirmed_green_has_no_caution(self):
        result = evaluate_execution_guidance("buy", LiveStatus.ENTRY_RECONFIRMED, RISK_GREEN)
        assert result.caution is False


# ── Persistence (PRD §23-E) ──────────────────────────────────────────────────

@pytest.fixture
def db_factory():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    yield factory
    engine.dispose()


@pytest.fixture
def patched_db(db_factory):
    def _sess(engine=None):
        return db_factory()
    with patch("src.database.get_session", side_effect=_sess):
        yield db_factory


class TestOvernightContextPersistence:

    def _insert_ctx(self, factory, execution_date=date(2026, 10, 22),
                    rule_version=OVERNIGHT_RULE_VERSION, risk_level=RISK_GREEN):
        s = factory()
        ctx = OvernightMarketContext(
            execution_date=execution_date,
            us_market_date=date(2026, 10, 21),
            risk_level=risk_level,
            data_quality=DQ_COMPLETE,
            risk_reasons_json="[]",
            overnight_rule_version=rule_version,
        )
        s.add(ctx)
        s.commit()
        s.close()
        return ctx

    def test_unique_constraint_same_date_and_version(self, db_factory):
        """Same execution_date + overnight_rule_version must not be inserted twice."""
        from sqlalchemy.exc import IntegrityError
        self._insert_ctx(db_factory)
        with pytest.raises(IntegrityError):
            self._insert_ctx(db_factory)

    def test_different_version_allowed(self, db_factory):
        """Different rule_version is allowed for same execution_date."""
        self._insert_ctx(db_factory, rule_version="overnight_v1")
        s = db_factory()
        ctx2 = OvernightMarketContext(
            execution_date=date(2026, 10, 22),
            us_market_date=date(2026, 10, 21),
            risk_level=RISK_GREEN,
            data_quality=DQ_COMPLETE,
            risk_reasons_json="[]",
            overnight_rule_version="overnight_v2",
        )
        s.add(ctx2)
        s.commit()   # must not raise
        s.close()

    def test_get_overnight_context_returns_existing(self, patched_db):
        """get_overnight_context returns existing DB row."""
        self._insert_ctx(patched_db)
        from src.services.overnight_service import get_overnight_context
        result = get_overnight_context(date(2026, 10, 22))
        assert result is not None
        assert result.risk_level == RISK_GREEN

    def test_get_overnight_context_returns_none_if_missing(self, patched_db):
        from src.services.overnight_service import get_overnight_context
        result = get_overnight_context(date(2026, 10, 22))
        assert result is None


# ── Graceful degradation (PRD §23-F) ─────────────────────────────────────────

class TestGracefulDegradation:

    def test_api_failure_produces_unknown_not_crash(self, patched_db):
        """External API failure → UNKNOWN context, no exception raised."""
        from src.services.overnight_service import ensure_overnight_context
        from src.collectors.overnight_collector import fetch_overnight_context, OvernightFetchResult, IndexSessionResult

        bad_result = IndexSessionResult(
            ticker="^GSPC", us_date=None, close=None,
            prev_close=None, return_pct=None, ok=False, reason="fetch_error",
        )
        mock_fetch = OvernightFetchResult(
            us_market_date=date(2026, 10, 21),
            sp500=bad_result, nasdaq=bad_result, sox=bad_result, vix=bad_result,
        )

        with patch("src.collectors.overnight_collector.fetch_overnight_context", return_value=mock_fetch):
            ctx = ensure_overnight_context(date(2026, 10, 22))

        assert ctx is not None
        assert ctx.risk_level == RISK_UNKNOWN

    def test_ensure_overnight_never_raises(self, patched_db):
        """ensure_overnight_context must never raise, even with total failure."""
        from src.services.overnight_service import ensure_overnight_context
        with patch(
            "src.services.overnight_service._build_and_persist",
            side_effect=RuntimeError("total failure"),
        ):
            # Should not raise; falls back to _persist_unknown
            ctx = ensure_overnight_context(date(2026, 10, 22))
            # ctx may be None if _persist_unknown also fails, which is acceptable

    def test_risk_unknown_does_not_produce_green(self, patched_db):
        """UNKNOWN context must never yield GREEN risk_level."""
        from src.services.overnight_service import ensure_overnight_context
        from src.collectors.overnight_collector import OvernightFetchResult, IndexSessionResult
        bad = IndexSessionResult(
            ticker="^GSPC", us_date=None, close=None,
            prev_close=None, return_pct=None, ok=False, reason="fetch_error",
        )
        mock_fetch = OvernightFetchResult(
            us_market_date=date(2026, 10, 21),
            sp500=bad, nasdaq=bad, sox=bad, vix=bad,
        )
        with patch("src.collectors.overnight_collector.fetch_overnight_context", return_value=mock_fetch):
            ctx = ensure_overnight_context(date(2026, 10, 22))
        assert ctx is not None
        assert ctx.risk_level != RISK_GREEN

    def test_idempotent_ensure(self, patched_db):
        """ensure_overnight_context called twice returns same row (no duplicate insert)."""
        from src.services.overnight_service import ensure_overnight_context
        from src.collectors.overnight_collector import OvernightFetchResult, IndexSessionResult

        ok_result = IndexSessionResult(
            ticker="^GSPC", us_date=date(2026, 10, 21), close=5000.0,
            prev_close=5050.0, return_pct=-1.0, ok=True, reason="ok",
        )
        mock_fetch = OvernightFetchResult(
            us_market_date=date(2026, 10, 21),
            sp500=ok_result, nasdaq=ok_result, sox=ok_result, vix=ok_result,
        )

        with patch("src.collectors.overnight_collector.fetch_overnight_context", return_value=mock_fetch):
            ctx1 = ensure_overnight_context(date(2026, 10, 22))
            # Second call: should return existing without re-fetching
            ctx2 = ensure_overnight_context(date(2026, 10, 22))

        assert ctx1 is not None
        assert ctx2 is not None
        assert ctx1.id == ctx2.id   # same DB row


# ── source_timestamp wiring ──────────────────────────────────────────────────

class TestSourceTimestamp:

    def test_ok_result_carries_source_timestamp(self):
        """IndexSessionResult with ok=True must have source_timestamp populated by _extract_session."""
        from src.collectors.overnight_collector import _fetch_index_history, _extract_session
        from datetime import datetime

        # Build a minimal synthetic rows list with a real Unix timestamp
        import time as _time
        ts_unix = int(_time.mktime((2026, 10, 21, 16, 0, 0, 0, 0, -1)))  # ~16:00 local
        rows = [
            {"date": date(2026, 10, 20), "close": 4980.0, "timestamp": ts_unix - 86400},
            {"date": date(2026, 10, 21), "close": 5000.0, "timestamp": ts_unix},
        ]
        result = _extract_session("^GSPC", rows, date(2026, 10, 21))
        assert result.ok is True
        assert result.source_timestamp is not None
        assert isinstance(result.source_timestamp, datetime)

    def test_failed_result_has_no_source_timestamp(self):
        """Missing/stale result should have source_timestamp=None."""
        from src.collectors.overnight_collector import _extract_session

        rows = [{"date": date(2026, 10, 20), "close": 4980.0, "timestamp": 1729468800}]
        result = _extract_session("^GSPC", rows, date(2026, 10, 21))
        assert result.ok is False
        assert result.source_timestamp is None

    def test_source_timestamp_stored_in_db(self, patched_db):
        """ensure_overnight_context must persist non-None source_timestamp when ok=True."""
        from src.services.overnight_service import ensure_overnight_context
        from src.collectors.overnight_collector import OvernightFetchResult, IndexSessionResult
        from datetime import datetime
        from zoneinfo import ZoneInfo

        ts = datetime(2026, 10, 21, 20, 0, 0, tzinfo=ZoneInfo("UTC"))
        ok_result = IndexSessionResult(
            ticker="^GSPC", us_date=date(2026, 10, 21), close=5000.0,
            prev_close=5050.0, return_pct=-1.0, ok=True, reason="ok",
            source_timestamp=ts,
        )
        mock_fetch = OvernightFetchResult(
            us_market_date=date(2026, 10, 21),
            sp500=ok_result, nasdaq=ok_result, sox=ok_result, vix=ok_result,
        )
        with patch("src.collectors.overnight_collector.fetch_overnight_context", return_value=mock_fetch):
            ctx = ensure_overnight_context(date(2026, 10, 22))

        assert ctx is not None
        assert ctx.source_timestamp is not None


# ── UNKNOWN retry policy ─────────────────────────────────────────────────────

class TestUnknownRetryPolicy:

    def _make_bad_fetch(self):
        from src.collectors.overnight_collector import OvernightFetchResult, IndexSessionResult
        bad = IndexSessionResult(
            ticker="^GSPC", us_date=None, close=None,
            prev_close=None, return_pct=None, ok=False, reason="fetch_error",
        )
        return OvernightFetchResult(
            us_market_date=date(2026, 10, 21),
            sp500=bad, nasdaq=bad, sox=bad, vix=bad,
        )

    def test_complete_context_is_never_retried(self, patched_db):
        """COMPLETE context must not be replaced even if called again."""
        from src.services.overnight_service import ensure_overnight_context, _should_retry_unknown
        from src.collectors.overnight_collector import OvernightFetchResult, IndexSessionResult
        from datetime import datetime
        from zoneinfo import ZoneInfo

        ts = datetime(2026, 10, 21, 20, 0, 0, tzinfo=ZoneInfo("UTC"))
        ok_r = IndexSessionResult(
            ticker="^GSPC", us_date=date(2026, 10, 21), close=5000.0,
            prev_close=5050.0, return_pct=0.5, ok=True, reason="ok",
            source_timestamp=ts,
        )
        mock_fetch = OvernightFetchResult(
            us_market_date=date(2026, 10, 21),
            sp500=ok_r, nasdaq=ok_r, sox=ok_r, vix=ok_r,
        )
        with patch("src.collectors.overnight_collector.fetch_overnight_context", return_value=mock_fetch):
            ctx1 = ensure_overnight_context(date(2026, 10, 22))

        assert not _should_retry_unknown(ctx1), "COMPLETE context must not be retried"

    def test_unknown_retry_increments_count(self, patched_db):
        """Retry of UNKNOWN context increments retry_count in the new persisted row."""
        from src.services.overnight_service import ensure_overnight_context, _should_retry_unknown
        from unittest.mock import patch as _patch

        bad_fetch = self._make_bad_fetch()

        # Force _should_retry_unknown to return True so retry triggers regardless of wall time
        with _patch("src.collectors.overnight_collector.fetch_overnight_context", return_value=bad_fetch):
            ctx1 = ensure_overnight_context(date(2026, 10, 22))

        assert ctx1 is not None
        assert ctx1.retry_count == 0

        # Force retry by patching _should_retry_unknown
        with _patch("src.services.overnight_service._should_retry_unknown", return_value=True):
            with _patch("src.collectors.overnight_collector.fetch_overnight_context", return_value=bad_fetch):
                ctx2 = ensure_overnight_context(date(2026, 10, 22))

        assert ctx2 is not None
        assert ctx2.retry_count == 1  # incremented from 0

    def test_unknown_freeze_stops_retry_at_max(self, patched_db):
        """After MAX_RETRY_COUNT retries, _should_retry_unknown returns False."""
        from src.services.overnight_service import _should_retry_unknown, MAX_RETRY_COUNT
        from src.engines.overnight_risk import DQ_UNKNOWN, RISK_UNKNOWN, OVERNIGHT_RULE_VERSION
        from src.database import OvernightMarketContext

        ctx = OvernightMarketContext(
            execution_date=date(2026, 10, 22),
            risk_level=RISK_UNKNOWN,
            data_quality=DQ_UNKNOWN,
            overnight_rule_version=OVERNIGHT_RULE_VERSION,
            risk_reasons_json="[]",
            retry_count=MAX_RETRY_COUNT,  # at limit
        )
        assert not _should_retry_unknown(ctx)
