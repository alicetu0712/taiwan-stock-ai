"""
tests/test_outcome_service.py — ForwardOutcomeEvaluation persistence tests

Tests upsert behavior, unique constraints, and horizon immutability.
Uses an in-memory SQLite database.
"""

import sys
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database import Base, ForwardOutcomeEvaluation
from src.services.outcome_service import (
    _get_or_create_row,
    _apply_entry,
    _write_bundle,
    _fill_horizons,
)
from src.engines.outcome_evaluation import (
    EntryResult, HorizonBundle,
    FORWARD_OUTCOME_PROTOCOL_VERSION,
    PATH_BASELINE, PATH_AWARE,
    EXEC_EXECUTED, EXEC_EXPIRED_BEFORE_ENTRY,
    ODQ_COMPLETE, ODQ_INCOMPLETE_HORIZON, ODQ_BENCHMARK_MISSING,
    OUTCOME_T1_FIRST, OUTCOME_NEITHER,
    EPT_BASELINE_NEXT_OPEN,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def engine():
    eng = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()


def _make_row(session, signal_id=1, path=PATH_BASELINE, stock="2368",
              sig_date=date(2026, 10, 21)):
    """Helper: create a raw ForwardOutcomeEvaluation row via _get_or_create_row."""
    return _get_or_create_row(
        session,
        forward_signal_id     = signal_id,
        sig_eval_id           = None,
        stock_id              = stock,
        signal_date           = sig_date,
        path_type             = path,
        overnight_context_id  = None,
        overnight_rule_version= None,
        overnight_risk_level  = None,
        live_rule             = None,
        exclusion_reason      = None,
    )


def _baseline_entry():
    return EntryResult(
        entry_status              = EXEC_EXECUTED,
        entry_date                = date(2026, 10, 22),
        entry_timestamp           = None,
        entry_price               = 198.0,
        entry_price_type          = EPT_BASELINE_NEXT_OPEN,
        entry_quote_quality       = None,
        mae_mfe_start_date        = date(2026, 10, 22),
        entry_day_excursion_excluded = False,
        benchmark_entry_date      = date(2026, 10, 22),
        benchmark_entry_price     = 175.0,
        benchmark_entry_price_type= "NEXT_OPEN",
        benchmark_timing_approximation = False,
        exclusion_reason          = None,
    )


def _complete_bundle_20d():
    return HorizonBundle(
        n_days                = 20,
        return_pct            = 5.0,
        alpha_pct             = 2.0,
        mae_pct               = -3.0,
        mfe_pct               = 8.0,
        target_stop_outcome   = OUTCOME_T1_FIRST,
        target_hit_date       = date(2026, 11, 15),
        stop_hit_date         = None,
        data_quality          = ODQ_COMPLETE,
    )


def _incomplete_bundle():
    return HorizonBundle(
        n_days=20,
        return_pct=None, alpha_pct=None, mae_pct=None, mfe_pct=None,
        target_stop_outcome=None, target_hit_date=None, stop_hit_date=None,
        data_quality=ODQ_INCOMPLETE_HORIZON,
    )


# ── Unique constraint ─────────────────────────────────────────────────────────

class TestUniqueConstraint:

    def test_duplicate_signal_path_version_raises(self, session):
        row1 = ForwardOutcomeEvaluation(
            forward_signal_id=1, stock_id="2368",
            signal_date=date(2026, 10, 21), path_type=PATH_BASELINE,
            outcome_protocol_version=FORWARD_OUTCOME_PROTOCOL_VERSION,
        )
        session.add(row1)
        session.commit()

        row2 = ForwardOutcomeEvaluation(
            forward_signal_id=1, stock_id="2368",
            signal_date=date(2026, 10, 21), path_type=PATH_BASELINE,
            outcome_protocol_version=FORWARD_OUTCOME_PROTOCOL_VERSION,
        )
        session.add(row2)
        with pytest.raises(Exception):
            session.commit()

    def test_different_path_type_allowed(self, session):
        row1 = ForwardOutcomeEvaluation(
            forward_signal_id=1, stock_id="2368",
            signal_date=date(2026, 10, 21), path_type=PATH_BASELINE,
            outcome_protocol_version=FORWARD_OUTCOME_PROTOCOL_VERSION,
        )
        row2 = ForwardOutcomeEvaluation(
            forward_signal_id=1, stock_id="2368",
            signal_date=date(2026, 10, 21), path_type=PATH_AWARE,
            outcome_protocol_version=FORWARD_OUTCOME_PROTOCOL_VERSION,
        )
        session.add_all([row1, row2])
        session.commit()
        count = session.query(ForwardOutcomeEvaluation).count()
        assert count == 2


# ── Upsert (_get_or_create_row) ───────────────────────────────────────────────

class TestUpsertBehavior:

    def test_first_call_creates_row(self, session):
        row = _make_row(session, signal_id=10)
        session.flush()
        assert row.forward_signal_id == 10
        assert row.path_type == PATH_BASELINE

    def test_second_call_returns_same_row(self, session):
        row1 = _make_row(session, signal_id=10)
        session.flush()
        row2 = _make_row(session, signal_id=10)
        assert row1.id == row2.id

    def test_protocol_version_set_on_creation(self, session):
        row = _make_row(session, signal_id=11, path=PATH_AWARE)
        assert row.outcome_protocol_version == FORWARD_OUTCOME_PROTOCOL_VERSION

    def test_two_paths_per_signal(self, session):
        _make_row(session, signal_id=20, path=PATH_BASELINE)
        _make_row(session, signal_id=20, path=PATH_AWARE)
        session.flush()
        count = session.query(ForwardOutcomeEvaluation).filter_by(forward_signal_id=20).count()
        assert count == 2


# ── Entry application ─────────────────────────────────────────────────────────

class TestApplyEntry:

    def test_apply_executed_entry(self, session):
        row = _make_row(session)
        entry = _baseline_entry()
        changed = _apply_entry(row, entry)
        assert changed is True
        assert row.entry_status == EXEC_EXECUTED
        assert row.entry_price == 198.0
        assert row.mae_mfe_start_date == date(2026, 10, 22)
        assert row.entry_day_excursion_excluded is False

    def test_apply_same_entry_not_changed(self, session):
        row = _make_row(session)
        entry = _baseline_entry()
        _apply_entry(row, entry)
        changed = _apply_entry(row, entry)  # identical second apply
        assert changed is False

    def test_expired_entry_applied(self, session):
        row = _make_row(session, path=PATH_AWARE)
        entry = EntryResult(
            entry_status=EXEC_EXPIRED_BEFORE_ENTRY,
            entry_date=None, entry_timestamp=None, entry_price=None,
            entry_price_type=None, entry_quote_quality=None,
            mae_mfe_start_date=None, entry_day_excursion_excluded=None,
            benchmark_entry_date=None, benchmark_entry_price=None,
            benchmark_entry_price_type=None, benchmark_timing_approximation=None,
            exclusion_reason=None,
        )
        changed = _apply_entry(row, entry)
        assert changed is True
        assert row.entry_status == EXEC_EXPIRED_BEFORE_ENTRY
        assert row.entry_price is None


# ── Bundle writing ────────────────────────────────────────────────────────────

class TestWriteBundle:

    def test_write_20d_bundle(self, session):
        row = _make_row(session)
        bundle = _complete_bundle_20d()
        _write_bundle(row, bundle, "_20d")

        assert row.return_20d == 5.0
        assert row.alpha_20d == 2.0
        assert row.mae_20d == -3.0
        assert row.mfe_20d == 8.0
        assert row.target_stop_outcome_20d == OUTCOME_T1_FIRST
        assert row.target_hit_date_20d == date(2026, 11, 15)
        assert row.stop_hit_date_20d is None
        assert row.outcome_data_quality_20d == ODQ_COMPLETE

    def test_write_60d_bundle(self, session):
        row = _make_row(session)
        bundle = HorizonBundle(
            n_days=60,
            return_pct=8.0, alpha_pct=3.0, mae_pct=-4.0, mfe_pct=12.0,
            target_stop_outcome=OUTCOME_NEITHER, target_hit_date=None, stop_hit_date=None,
            data_quality=ODQ_COMPLETE,
        )
        _write_bundle(row, bundle, "_60d")

        assert row.return_60d == 8.0
        assert row.alpha_60d == 3.0
        assert row.outcome_data_quality_60d == ODQ_COMPLETE


# ── Horizon-level immutability ────────────────────────────────────────────────

class TestHorizonImmutability:

    def _make_fs_stub(self, stop=None, t1=None):
        """Minimal ForwardSignal stub."""
        fs = MagicMock()
        fs.stop_price = stop
        fs.target1 = t1
        return fs

    def test_20d_bundle_not_overwritten_after_lock(self, session):
        row = _make_row(session)
        _apply_entry(row, _baseline_entry())
        session.flush()

        # Manually set 20D lock
        row.return_20d = 5.0
        row.alpha_20d = 2.0
        row.horizon_20d_matured_at = datetime(2026, 11, 20, 0, 0, 0)
        session.flush()

        # Attempt fill with new bundle that returns 99.0 — must be ignored
        new_bundle = HorizonBundle(
            n_days=20,
            return_pct=99.0, alpha_pct=99.0, mae_pct=0, mfe_pct=99.0,
            target_stop_outcome=OUTCOME_T1_FIRST,
            target_hit_date=date(2026, 11, 10), stop_hit_date=None,
            data_quality=ODQ_COMPLETE,
        )

        with patch("src.engines.outcome_evaluation.compute_horizon_bundle",
                   return_value=new_bundle):
            _fill_horizons(
                row=row,
                entry_result=_baseline_entry(),
                fs=self._make_fs_stub(),
                stock_dates=[],
                close_map={},
                high_map={},
                low_map={},
                b_dates=[],
                b_close_map={},
            )

        # 20D must be unchanged because it was locked
        assert row.return_20d == 5.0
        assert row.alpha_20d == 2.0

    def test_incomplete_bundle_does_not_set_lock(self, session):
        row = _make_row(session)
        _apply_entry(row, _baseline_entry())
        session.flush()

        with patch("src.engines.outcome_evaluation.compute_horizon_bundle",
                   return_value=_incomplete_bundle()):
            _fill_horizons(
                row=row,
                entry_result=_baseline_entry(),
                fs=self._make_fs_stub(),
                stock_dates=[],
                close_map={},
                high_map={},
                low_map={},
                b_dates=[],
                b_close_map={},
            )

        assert row.horizon_20d_matured_at is None
        assert row.horizon_60d_matured_at is None

    def test_lock_timestamp_persisted(self, session):
        row = _make_row(session, signal_id=3)
        session.flush()

        now = datetime(2026, 12, 1, 12, 0, 0)
        row.horizon_20d_matured_at = now
        session.commit()

        refetch = session.query(ForwardOutcomeEvaluation).filter_by(id=row.id).one()
        assert refetch.horizon_20d_matured_at == now
        assert refetch.horizon_60d_matured_at is None

    def test_60d_remains_mutable_when_only_20d_locked(self, session):
        row = _make_row(session, signal_id=4)
        row.horizon_20d_matured_at = datetime(2026, 11, 20)
        session.flush()

        assert row.horizon_60d_matured_at is None  # 60D still writable


# ── Signal-level counts ────────────────────────────────────────────────────────

class TestPersistenceCounts:

    def test_different_signals_are_independent(self, session):
        for sig_id in [1, 2, 3]:
            row = ForwardOutcomeEvaluation(
                forward_signal_id=sig_id, stock_id="2368",
                signal_date=date(2026, 10, 21), path_type=PATH_BASELINE,
                outcome_protocol_version=FORWARD_OUTCOME_PROTOCOL_VERSION,
            )
            session.add(row)
        session.commit()

        assert session.query(ForwardOutcomeEvaluation).count() == 3
