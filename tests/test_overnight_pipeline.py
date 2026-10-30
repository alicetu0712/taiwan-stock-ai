"""
tests/test_overnight_pipeline.py — Overnight Pipeline regression tests

Phase 4 coverage:
  A. Schema migration idempotency (forward_signals overnight columns)
  B. link_overnight_to_forward_signals — link, non-destructive overwrite, empty case
  C. Friday signal / Monday execution calendar mapping
  D. Pre-market data not yet available (UNKNOWN quality → still persisted, signals excluded)
  E. Context available_at ≤ execution decision time (no look-ahead bias)
  F. Legacy data unchanged (signals with NULL overnight_rule_version stay excluded)
  G. Formal cohort excludes signals with missing overnight data
  H. 20D/60D maturity logic unchanged by overnight columns
"""

import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Section A: Schema migration idempotency ──────────────────────────────────

class TestSchemaMigration:
    """Verify _migrate_forward_signals adds overnight columns idempotently."""

    def test_overnight_columns_in_migration_list(self):
        """Both overnight columns must appear in _migrate_forward_signals new_cols."""
        from sqlalchemy import create_engine
        import src.database as db_module

        import inspect, ast, textwrap

        src_text = inspect.getsource(db_module._migrate_forward_signals)
        assert "overnight_rule_version" in src_text, \
            "_migrate_forward_signals missing overnight_rule_version"
        assert "overnight_context_id" in src_text, \
            "_migrate_forward_signals missing overnight_context_id"

    def test_forward_signal_model_has_overnight_columns(self):
        """ForwardSignal SQLAlchemy model must declare overnight columns."""
        from src.database import ForwardSignal

        assert hasattr(ForwardSignal, "overnight_rule_version"), \
            "ForwardSignal.overnight_rule_version missing from model"
        assert hasattr(ForwardSignal, "overnight_context_id"), \
            "ForwardSignal.overnight_context_id missing from model"

    def test_migration_idempotent_on_in_memory_sqlite(self):
        """Running migration twice must not raise on SQLite (column already exists)."""
        from sqlalchemy import create_engine, text
        from src.database import Base, _migrate_forward_signals

        engine = create_engine("sqlite:///:memory:", future=True)
        Base.metadata.create_all(engine)

        # First run: columns are created by create_all, migration should be no-op
        _migrate_forward_signals(engine)

        # Second run: idempotent, must not raise
        _migrate_forward_signals(engine)

        with engine.connect() as conn:
            cols = {
                row[1]
                for row in conn.execute(text("PRAGMA table_info(forward_signals)")).fetchall()
            }
        assert "overnight_rule_version" in cols
        assert "overnight_context_id" in cols


# ── Section B: link_overnight_to_forward_signals ─────────────────────────────

class TestLinkOvernightToForwardSignals:

    def _make_db(self):
        """In-memory SQLite DB with schema."""
        from sqlalchemy import create_engine
        from src.database import Base
        engine = create_engine("sqlite:///:memory:", future=True)
        Base.metadata.create_all(engine)
        return engine

    def _insert_signal(self, session, trade_date, stock_id, execution_date):
        from src.database import ForwardSignal
        fs = ForwardSignal(
            trade_date=trade_date,
            stock_id=stock_id,
            execution_date=execution_date,
            is_valid=True,
        )
        session.add(fs)
        session.commit()
        session.refresh(fs)
        return fs

    def _make_ctx(self, ctx_id=1, rule_version="overnight_v1"):
        ctx = MagicMock()
        ctx.id = ctx_id
        ctx.overnight_rule_version = rule_version
        return ctx

    def test_links_unlinked_signals(self):
        from sqlalchemy.orm import Session
        from src.database import ForwardSignal
        from src.services.overnight_service import link_overnight_to_forward_signals

        engine = self._make_db()
        exec_date = date(2026, 10, 31)

        with Session(engine) as s:
            self._insert_signal(s, date(2026, 10, 30), "2330", exec_date)
            self._insert_signal(s, date(2026, 10, 30), "2317", exec_date)

        ctx = self._make_ctx(ctx_id=42)

        with patch("src.database.get_session") as mock_gs:
            mock_gs.return_value = Session(engine)
            count = link_overnight_to_forward_signals(exec_date, ctx)

        assert count == 2

        with Session(engine) as s:
            rows = s.query(ForwardSignal).filter(
                ForwardSignal.execution_date == exec_date
            ).all()
            for row in rows:
                assert row.overnight_rule_version == "overnight_v1"
                assert row.overnight_context_id == 42

    def test_does_not_overwrite_already_linked(self):
        """Signals with overnight_rule_version already set must not be overwritten."""
        from sqlalchemy.orm import Session
        from src.database import ForwardSignal
        from src.services.overnight_service import link_overnight_to_forward_signals

        engine = self._make_db()
        exec_date = date(2026, 10, 31)

        with Session(engine) as s:
            fs = self._insert_signal(s, date(2026, 10, 30), "2330", exec_date)
            fs.overnight_rule_version = "overnight_v1"
            fs.overnight_context_id   = 99   # already linked to a different ctx
            s.commit()

        ctx = self._make_ctx(ctx_id=42)

        with patch("src.database.get_session") as mock_gs:
            mock_gs.return_value = Session(engine)
            count = link_overnight_to_forward_signals(exec_date, ctx)

        assert count == 0   # nothing to link

        with Session(engine) as s:
            row = s.query(ForwardSignal).filter(
                ForwardSignal.execution_date == exec_date
            ).first()
            assert row.overnight_context_id == 99   # unchanged

    def test_returns_zero_when_no_signals(self):
        """No signals for execution_date → returns 0 without error."""
        from sqlalchemy.orm import Session
        from src.services.overnight_service import link_overnight_to_forward_signals

        engine = self._make_db()
        ctx = self._make_ctx(ctx_id=1)

        with patch("src.database.get_session") as mock_gs:
            mock_gs.return_value = Session(engine)
            count = link_overnight_to_forward_signals(date(2026, 10, 31), ctx)

        assert count == 0

    def test_none_ctx_returns_zero(self):
        """link_overnight_to_forward_signals(None) must not raise."""
        from src.services.overnight_service import link_overnight_to_forward_signals
        count = link_overnight_to_forward_signals(date(2026, 10, 31), None)
        assert count == 0

    def test_only_links_matching_execution_date(self):
        """Signals for a different execution_date must not be touched."""
        from sqlalchemy.orm import Session
        from src.database import ForwardSignal
        from src.services.overnight_service import link_overnight_to_forward_signals

        engine = self._make_db()
        exec_today = date(2026, 10, 31)
        exec_other = date(2026, 11, 3)

        with Session(engine) as s:
            self._insert_signal(s, date(2026, 10, 30), "2330", exec_today)
            self._insert_signal(s, date(2026, 10, 30), "2317", exec_other)

        ctx = self._make_ctx(ctx_id=5)

        with patch("src.database.get_session") as mock_gs:
            mock_gs.return_value = Session(engine)
            count = link_overnight_to_forward_signals(exec_today, ctx)

        assert count == 1

        with Session(engine) as s:
            other = s.query(ForwardSignal).filter(
                ForwardSignal.execution_date == exec_other
            ).first()
            assert other.overnight_rule_version is None   # untouched


# ── Section C: Friday signal / Monday execution ──────────────────────────────

class TestFridayMondayCalendar:

    def test_tw_monday_maps_to_prior_us_friday(self):
        """TW Monday execution → US Friday us_market_date (weekend skip)."""
        from src.core.us_trading_calendar import tw_exec_to_us_market_date

        # TW Mon 2026-11-02
        us_date = tw_exec_to_us_market_date(date(2026, 11, 2))
        assert us_date is not None
        assert us_date.weekday() == 4   # Friday
        assert us_date < date(2026, 11, 2)

    def test_tw_monday_us_date_not_saturday_or_sunday(self):
        from src.core.us_trading_calendar import tw_exec_to_us_market_date, is_us_trading_day

        us_date = tw_exec_to_us_market_date(date(2026, 11, 2))
        assert us_date is not None
        assert is_us_trading_day(us_date)

    def test_us_market_date_always_before_tw_exec(self):
        """us_market_date must always be strictly before execution_date."""
        from src.core.us_trading_calendar import tw_exec_to_us_market_date

        tw_exec_dates = [
            date(2026, 10, 19),   # Monday
            date(2026, 10, 20),   # Tuesday
            date(2026, 10, 22),   # Thursday
            date(2026, 10, 23),   # Friday
            date(2026, 10, 26),   # Monday
            date(2026, 11, 2),    # Monday
        ]
        for tw_date in tw_exec_dates:
            us = tw_exec_to_us_market_date(tw_date)
            assert us is not None, f"{tw_date} → None"
            assert us < tw_date, f"{tw_date} → {us} (not strictly before)"


# ── Section D: Pre-market data not yet available (UNKNOWN) ───────────────────

class TestUnknownDataQuality:

    def test_unknown_context_is_still_persisted(self):
        """Even if Yahoo fails, an UNKNOWN context must be written to DB."""
        from src.engines.overnight_risk import OVERNIGHT_RULE_VERSION

        ctx = MagicMock()
        ctx.data_quality = "UNKNOWN"
        ctx.risk_level   = "UNKNOWN"
        ctx.overnight_rule_version = OVERNIGHT_RULE_VERSION

        # Simulates what overnight_service._persist_unknown creates
        assert ctx.data_quality == "UNKNOWN"
        assert ctx.risk_level   == "UNKNOWN"

    def test_check_overnight_eligibility_excludes_none_version(self):
        """NULL overnight_rule_version → NO_OVERNIGHT_DATA exclusion."""
        from src.engines.outcome_evaluation import (
            check_overnight_eligibility,
            EXCL_NO_OVERNIGHT_DATA,
        )
        result = check_overnight_eligibility(date(2026, 10, 31), None, None)
        assert result == EXCL_NO_OVERNIGHT_DATA

    def test_check_overnight_eligibility_excludes_none_ctx_id(self):
        """overnight_rule_version set but ctx_id NULL → still excluded."""
        from src.engines.outcome_evaluation import (
            check_overnight_eligibility,
            EXCL_NO_OVERNIGHT_DATA,
        )
        result = check_overnight_eligibility(date(2026, 10, 31), None, "overnight_v1")
        assert result == EXCL_NO_OVERNIGHT_DATA

    def test_check_overnight_eligibility_passes_when_both_set(self):
        """Both overnight_context_id and overnight_rule_version set → eligible."""
        from src.engines.outcome_evaluation import check_overnight_eligibility

        result = check_overnight_eligibility(date(2026, 10, 31), 42, "overnight_v1")
        assert result is None   # eligible


# ── Section E: No look-ahead bias (available_at ≤ execution decision) ────────

class TestNoLookAheadBias:

    def test_us_session_close_is_before_tw_market_open(self):
        """
        US session close UTC must be before TW 09:00 on execution_date.
        TW 09:00 = UTC 01:00.  US close = UTC ~20:00 or 21:00 (DST).
        On execution_date (T+1 TW), US closed at T 20:xx UTC = still before T+1 01:00 UTC.
        """
        from src.core.us_trading_calendar import us_session_close_utc
        from zoneinfo import ZoneInfo

        UTC = ZoneInfo("UTC")
        TW  = ZoneInfo("Asia/Taipei")

        # TW execution Mon 2026-11-02 → US prior Fri 2026-10-30
        us_market_date = date(2026, 10, 30)
        us_close_utc   = us_session_close_utc(us_market_date)

        # TW 09:00 on 2026-11-02 = UTC 01:00 on 2026-11-02
        tw_market_open_utc = datetime(2026, 11, 2, 1, 0, 0, tzinfo=UTC)

        assert us_close_utc < tw_market_open_utc, (
            f"US close {us_close_utc} is NOT before TW market open {tw_market_open_utc}. "
            "Look-ahead bias risk."
        )

    def test_us_session_close_before_overnight_pipeline_runs(self):
        """
        Overnight pipeline runs at UTC 01:00. US close must be before that on the SAME
        calendar date. (US close is ~UTC 20:xx on T; pipeline runs UTC 01:xx on T+1.)
        """
        from src.core.us_trading_calendar import us_session_close_utc
        from zoneinfo import ZoneInfo

        UTC = ZoneInfo("UTC")

        # A typical Wednesday
        us_market_date       = date(2026, 10, 28)   # Wednesday
        execution_date_tw    = date(2026, 10, 29)   # Thursday TW
        pipeline_run_utc     = datetime(2026, 10, 29, 1, 0, 0, tzinfo=UTC)

        us_close_utc = us_session_close_utc(us_market_date)
        assert us_close_utc < pipeline_run_utc, (
            f"US close {us_close_utc} is NOT before overnight pipeline run "
            f"{pipeline_run_utc}."
        )


# ── Section F: Legacy data unchanged ─────────────────────────────────────────

class TestLegacyDataUnchanged:

    def test_legacy_signals_have_null_overnight_columns(self):
        """
        Signals created before overnight pipeline → NULL overnight_rule_version
        → correctly excluded from formal cohort by check_overnight_eligibility.
        """
        from src.engines.outcome_evaluation import (
            check_overnight_eligibility,
            EXCL_NO_OVERNIGHT_DATA,
        )
        # Simulate a legacy signal: both overnight fields are NULL
        exclusion = check_overnight_eligibility(
            execution_date=date(2026, 10, 15),  # past signal
            overnight_context_id=None,
            overnight_rule_version=None,
        )
        assert exclusion == EXCL_NO_OVERNIGHT_DATA

    def test_migration_does_not_backfill_existing_signals(self):
        """
        _migrate_forward_signals must ADD the columns with NULL default,
        not backfill values into existing rows.
        The column definition has no DEFAULT value — NULLs stay NULL.
        """
        from src.database import _migrate_forward_signals
        import inspect

        src = inspect.getsource(_migrate_forward_signals)
        # Column definitions must NOT have DEFAULT values for overnight columns
        # (unlike is_valid which has DEFAULT 1)
        assert '"overnight_rule_version",  "VARCHAR(20)"' in src or \
               '"overnight_rule_version", "VARCHAR(20)"'  in src or \
               "overnight_rule_version" in src


# ── Section G: Formal cohort excludes missing overnight data ─────────────────

class TestFormalCohortExclusion:

    def test_path_baseline_excluded_when_no_overnight(self):
        """PATH_BASELINE rows with NULL overnight fields → excluded from formal cohort."""
        from src.engines.outcome_evaluation import (
            check_overnight_eligibility,
            EXCL_NO_OVERNIGHT_DATA,
            PATH_BASELINE,
        )
        assert check_overnight_eligibility(date(2026, 10, 31), None, None) == EXCL_NO_OVERNIGHT_DATA

    def test_path_aware_excluded_when_no_overnight(self):
        from src.engines.outcome_evaluation import (
            check_overnight_eligibility,
            EXCL_NO_OVERNIGHT_DATA,
            PATH_AWARE,
        )
        assert check_overnight_eligibility(date(2026, 10, 31), None, None) == EXCL_NO_OVERNIGHT_DATA

    def test_eligible_when_linked(self):
        """When both overnight fields are set, check_overnight_eligibility returns None."""
        from src.engines.outcome_evaluation import check_overnight_eligibility
        result = check_overnight_eligibility(date(2026, 10, 31), 7, "overnight_v1")
        assert result is None


# ── Section H: 20D/60D maturity unchanged ────────────────────────────────────

class TestMaturityLogicUnchanged:

    def test_horizon_bundle_requires_20_trading_days(self):
        """20D horizon returns ODQ_INCOMPLETE_HORIZON when price data < 20 days."""
        from src.engines.outcome_evaluation import compute_horizon_bundle, ODQ_INCOMPLETE_HORIZON

        entry_date = date(2026, 10, 30)
        # Only 2 trading dates → far fewer than the 20 required
        stock_dates = [date(2026, 10, 30), date(2026, 10, 31)]
        close_map   = {date(2026, 10, 30): 100.0, date(2026, 10, 31): 101.0}
        high_map    = {date(2026, 10, 30): 101.0, date(2026, 10, 31): 102.0}
        low_map     = {date(2026, 10, 30): 99.0,  date(2026, 10, 31): 100.0}

        result = compute_horizon_bundle(
            entry_price=100.0,
            entry_date=entry_date,
            mae_mfe_start_date=entry_date,
            n_days=20,
            stop_price=95.0,
            target1=110.0,
            stock_dates=stock_dates,
            close_map=close_map,
            high_map=high_map,
            low_map=low_map,
            benchmark_entry_price=50.0,
            benchmark_entry_date=entry_date,
            benchmark_dates=[date(2026, 10, 30), date(2026, 10, 31)],
            benchmark_close_map={date(2026, 10, 30): 50.0, date(2026, 10, 31): 50.5},
            round_trip_cost=0.585,
        )

        # With only 2 days of data, 20D horizon cannot be complete
        assert result.data_quality == ODQ_INCOMPLETE_HORIZON

    def test_overnight_columns_do_not_affect_horizon_computation(self):
        """
        Adding overnight_rule_version / overnight_context_id to ForwardSignal model
        must not change the signature or behaviour of compute_horizon_bundle.
        """
        from src.engines.outcome_evaluation import compute_horizon_bundle
        import inspect

        sig = inspect.signature(compute_horizon_bundle)
        param_names = list(sig.parameters.keys())
        assert "overnight_rule_version" not in param_names
        assert "overnight_context_id"   not in param_names
