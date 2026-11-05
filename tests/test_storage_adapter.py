"""
tests/test_storage_adapter.py — Unit tests for SQLiteResearchStorage adapter.

SA01–SA15: SQLiteResearchStorage interface tests (via in-memory or temp SQLite)
SA16–SA20: health_check / get_storage_info
SA21–SA25: PostgreSQLResearchStorage stub safety
SA26–SA30: get_research_storage factory
"""

from __future__ import annotations

import os
from datetime import date, datetime, timezone

import pytest

from src.research.hybrid_forward_db import (
    ConflictError,
    HybridForwardDecision,
    HybridForwardOutcome,
    HybridForwardRunLog,
    RunStatus,
    compute_decision_hash,
)
from src.research.storage_adapter import (
    PostgreSQLResearchStorage,
    SQLiteResearchStorage,
    StorageHealthStatus,
    get_research_storage,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

TRADE_DATE = date(2026, 11, 6)
RUN_ID = "test-run"


def _make_decision(
    stock_id: str = "2330",
    hybrid_action: str = "DIRECT_NEXT_OPEN",
    rule_reason: str = "P3_bull_rising",
    rule_priority: int = 3,
) -> HybridForwardDecision:
    return HybridForwardDecision(
        stock_id=stock_id,
        trade_date=TRADE_DATE,
        rule_version="hybrid_v1",
        research_version="v2_research_v2",
        v2_entry_label="ENTRY_READY",
        hybrid_action=hybrid_action,
        rule_reason=rule_reason,
        rule_priority=rule_priority,
        market_regime="bull",
        ma20_slope_pct=0.5,
        ma20_trend="rising",
        ma20_gap_pct=1.2,
        feature_cutoff_date=TRADE_DATE,
        input_data_as_of=TRADE_DATE,
        input_data_hash="abc123",
        decision_hash=compute_decision_hash(hybrid_action, rule_reason, rule_priority, "hybrid_v1"),
        capture_classification="PROSPECTIVE",
        captured_at=datetime(2026, 11, 6, 8, 0, 0, tzinfo=timezone.utc),
        run_id=RUN_ID,
    )


def _make_outcome(decision_id: int) -> HybridForwardOutcome:
    return HybridForwardOutcome(
        decision_id=decision_id,
        stock_id="2330",
        trade_date=TRADE_DATE,
        rule_version="hybrid_v1",
        horizon="20d",
        maturity_date=date(2026, 12, 11),
        maturity_trading_days=20,
        v1_net_return=1.5,
        v2_net_return=1.5,
        hybrid_net_return=1.5,
        hybrid_vs_v1_delta=0.0,
        hybrid_vs_v2_delta=0.0,
        data_source_version="2026-12-11",
        calculation_version="1.0",
        outcome_status="MATURED",
        calculated_at=datetime(2026, 12, 15, tzinfo=timezone.utc),
    )


def _make_run_log(status: str = RunStatus.SUCCESS) -> HybridForwardRunLog:
    return HybridForwardRunLog(
        run_id=RUN_ID,
        trade_date=TRADE_DATE,
        started_at=datetime(2026, 11, 6, 8, 0, tzinfo=timezone.utc),
        finished_at=datetime(2026, 11, 6, 8, 1, tzinfo=timezone.utc),
        input_data_date=TRADE_DATE,
        inserted_count=1,
        skipped_count=0,
        conflict_count=0,
        error_count=0,
        outcome_filled_count=0,
        status=status,
        error_summary=None,
    )


@pytest.fixture
def tmp_db(tmp_path):
    return str(tmp_path / "test_research.db")


@pytest.fixture
def store(tmp_db):
    with SQLiteResearchStorage(tmp_db) as s:
        yield s


# ── SA01–SA05: Context manager & schema ──────────────────────────────────────

class TestSQLiteContextManager:
    def test_SA01_context_manager_opens_and_closes(self, tmp_db):
        with SQLiteResearchStorage(tmp_db) as s:
            info = s.get_storage_info()
            assert info["backend"] == "sqlite"
        # After exit, connection should be closed
        assert s._conn is None

    def test_SA02_ensure_schema_creates_tables(self, tmp_db):
        with SQLiteResearchStorage(tmp_db) as s:
            health = s.health_check()
            assert health["tables_missing"] == []
            assert set(health["tables_present"]) == {
                "hybrid_forward_decision",
                "hybrid_forward_outcome",
                "hybrid_forward_run_log",
            }

    def test_SA03_double_ensure_schema_idempotent(self, tmp_db):
        with SQLiteResearchStorage(tmp_db) as s:
            s.ensure_schema()
            s.ensure_schema()
            health = s.health_check()
            assert health["tables_missing"] == []

    def test_SA04_raises_if_not_open(self, tmp_db):
        s = SQLiteResearchStorage(tmp_db)
        with pytest.raises(RuntimeError, match="not open"):
            s.insert_decision(_make_decision())

    def test_SA05_wal_mode_enabled(self, tmp_db):
        with SQLiteResearchStorage(tmp_db) as s:
            mode = s._c.execute("PRAGMA journal_mode").fetchone()[0]
            assert mode in ("wal", "WAL")


# ── SA06–SA10: insert_decision append-only semantics ─────────────────────────

class TestInsertDecision:
    def test_SA06_insert_returns_row_id(self, store):
        d = _make_decision()
        row_id = store.insert_decision(d)
        assert isinstance(row_id, int)
        assert row_id > 0

    def test_SA07_idempotent_repeat_returns_none(self, store):
        d = _make_decision()
        store.insert_decision(d)
        result = store.insert_decision(d)
        assert result is None

    def test_SA08_conflict_raises_conflict_error(self, store):
        d = _make_decision(hybrid_action="DIRECT_NEXT_OPEN")
        store.insert_decision(d)
        d_conflict = _make_decision(hybrid_action="WAIT_PULLBACK")
        with pytest.raises(ConflictError):
            store.insert_decision(d_conflict)

    def test_SA09_original_record_unchanged_after_conflict(self, store):
        d = _make_decision(hybrid_action="DIRECT_NEXT_OPEN")
        store.insert_decision(d)
        d_conflict = _make_decision(hybrid_action="WAIT_PULLBACK")
        try:
            store.insert_decision(d_conflict)
        except ConflictError:
            pass
        row = store._c.execute(
            "SELECT hybrid_action FROM hybrid_forward_decision WHERE stock_id='2330'"
        ).fetchone()
        assert row[0] == "DIRECT_NEXT_OPEN"  # original unchanged

    def test_SA10_multiple_stocks_same_date(self, store):
        stocks = ["2330", "2317", "2412"]
        for s in stocks:
            d = _make_decision(stock_id=s)
            row_id = store.insert_decision(d)
            assert row_id is not None
        count = store._c.execute("SELECT COUNT(*) FROM hybrid_forward_decision").fetchone()[0]
        assert count == 3


# ── SA11–SA13: insert_outcome ─────────────────────────────────────────────────

class TestInsertOutcome:
    def test_SA11_insert_outcome_returns_row_id(self, store):
        d = _make_decision()
        did = store.insert_decision(d)
        o = _make_outcome(decision_id=did)
        row_id = store.insert_outcome(o)
        assert isinstance(row_id, int)

    def test_SA12_outcome_idempotent(self, store):
        d = _make_decision()
        did = store.insert_decision(d)
        o = _make_outcome(decision_id=did)
        store.insert_outcome(o)
        result = store.insert_outcome(o)
        assert result is None

    def test_SA13_decision_table_unchanged_after_outcome_insert(self, store):
        d = _make_decision()
        did = store.insert_decision(d)
        o = _make_outcome(decision_id=did)
        store.insert_outcome(o)
        # Verify decision row is unchanged
        row = store._c.execute(
            "SELECT hybrid_action FROM hybrid_forward_decision WHERE id=?", (did,)
        ).fetchone()
        assert row[0] == "DIRECT_NEXT_OPEN"


# ── SA14–SA15: upsert_run_log ─────────────────────────────────────────────────

class TestRunLog:
    def test_SA14_upsert_run_log_creates_entry(self, store):
        log = _make_run_log(RunStatus.SUCCESS)
        store.upsert_run_log(log)
        row = store._c.execute(
            "SELECT status FROM hybrid_forward_run_log WHERE run_id=?", (RUN_ID,)
        ).fetchone()
        assert row[0] == RunStatus.SUCCESS

    def test_SA15_upsert_run_log_updates_status(self, store):
        log = _make_run_log(RunStatus.SUCCESS)
        store.upsert_run_log(log)
        log_updated = HybridForwardRunLog(
            run_id=RUN_ID,
            trade_date=TRADE_DATE,
            started_at=log.started_at,
            finished_at=log.finished_at,
            input_data_date=TRADE_DATE,
            inserted_count=2,
            skipped_count=1,
            conflict_count=0,
            error_count=0,
            outcome_filled_count=1,
            status=RunStatus.SUCCESS,
            error_summary=None,
        )
        store.upsert_run_log(log_updated)
        row = store._c.execute(
            "SELECT inserted_count, outcome_filled_count FROM hybrid_forward_run_log WHERE run_id=?",
            (RUN_ID,),
        ).fetchone()
        assert row[0] == 2
        assert row[1] == 1


# ── SA16–SA20: health_check & storage_info ────────────────────────────────────

class TestHealthCheck:
    def test_SA16_healthy_after_schema_created(self, store):
        h = store.health_check()
        assert h["status"] == StorageHealthStatus.HEALTHY
        assert h["tables_missing"] == []

    def test_SA17_degraded_if_table_missing(self, tmp_db):
        # Create schema normally, then drop one table
        with SQLiteResearchStorage(tmp_db) as s:
            s._c.execute("DROP TABLE IF EXISTS hybrid_forward_outcome")
            s._c.commit()
            # Check health in same connection while table is missing
            h = s.health_check()
            assert h["status"] == StorageHealthStatus.DEGRADED
            assert "hybrid_forward_outcome" in h["tables_missing"]

    def test_SA18_no_path_in_storage_info(self, store):
        info = store.get_storage_info()
        # Must not expose full path
        assert "/" not in info.get("db_name", "")
        assert info["is_production"] is False

    def test_SA19_health_includes_timestamp(self, store):
        h = store.health_check()
        assert "last_checked_utc" in h
        # Verify parseable ISO timestamp
        datetime.fromisoformat(h["last_checked_utc"].replace("Z", "+00:00"))

    def test_SA20_storage_info_reports_file_exists(self, store, tmp_db):
        info = store.get_storage_info()
        assert info["file_exists"] is True
        assert info["file_size_kb"] is not None


# ── SA21–SA25: PostgreSQL stub safety ────────────────────────────────────────

class TestPostgreSQLStub:
    def test_SA21_raises_not_implemented_on_insert(self):
        with pytest.raises((ValueError, NotImplementedError)):
            pg = PostgreSQLResearchStorage("postgresql://fake/db")
            with pg:
                pg.ensure_schema()

    def test_SA22_health_check_returns_blocked(self):
        pg = PostgreSQLResearchStorage.__new__(PostgreSQLResearchStorage)
        pg._pg_url = "postgresql://fake/db"
        h = pg.health_check()
        assert h["status"] == StorageHealthStatus.BLOCKED

    def test_SA23_requires_pg_url_env_or_arg(self):
        old = os.environ.pop("RESEARCH_PG_URL", None)
        try:
            with pytest.raises(ValueError, match="RESEARCH_PG_URL"):
                PostgreSQLResearchStorage()
        finally:
            if old is not None:
                os.environ["RESEARCH_PG_URL"] = old

    def test_SA24_storage_info_not_production(self):
        pg = PostgreSQLResearchStorage.__new__(PostgreSQLResearchStorage)
        pg._pg_url = "postgresql://fake/db"
        info = pg.get_storage_info()
        assert info["is_production"] is False

    def test_SA25_pg_raises_not_implemented_on_all_write_ops(self):
        pg = PostgreSQLResearchStorage.__new__(PostgreSQLResearchStorage)
        pg._pg_url = "postgresql://fake/db"
        d = _make_decision()
        for op in [
            lambda: pg.ensure_schema(),
            lambda: pg.insert_decision(d),
            lambda: pg.upsert_run_log(_make_run_log()),
            lambda: pg.get_operational_summary(),
        ]:
            with pytest.raises(NotImplementedError):
                op()


# ── SA26–SA30: get_research_storage factory ──────────────────────────────────

class TestStorageFactory:
    def test_SA26_default_returns_sqlite_storage(self, tmp_db):
        store = get_research_storage(db_path=tmp_db)
        assert isinstance(store, SQLiteResearchStorage)

    def test_SA27_explicit_sqlite_returns_sqlite_storage(self, tmp_db):
        old = os.environ.get("RESEARCH_STORAGE_BACKEND")
        os.environ["RESEARCH_STORAGE_BACKEND"] = "sqlite"
        try:
            store = get_research_storage(db_path=tmp_db)
            assert isinstance(store, SQLiteResearchStorage)
        finally:
            if old is None:
                os.environ.pop("RESEARCH_STORAGE_BACKEND", None)
            else:
                os.environ["RESEARCH_STORAGE_BACKEND"] = old

    def test_SA28_postgresql_requires_pg_url(self):
        old_backend = os.environ.get("RESEARCH_STORAGE_BACKEND")
        old_url = os.environ.pop("RESEARCH_PG_URL", None)
        os.environ["RESEARCH_STORAGE_BACKEND"] = "postgresql"
        try:
            with pytest.raises(ValueError, match="RESEARCH_PG_URL"):
                get_research_storage()
        finally:
            if old_backend is None:
                os.environ.pop("RESEARCH_STORAGE_BACKEND", None)
            else:
                os.environ["RESEARCH_STORAGE_BACKEND"] = old_backend
            if old_url is not None:
                os.environ["RESEARCH_PG_URL"] = old_url

    def test_SA29_factory_blocks_pg_url_equal_to_neon_url(self):
        old_backend = os.environ.get("RESEARCH_STORAGE_BACKEND")
        old_neon = os.environ.get("NEON_URL")
        os.environ["RESEARCH_STORAGE_BACKEND"] = "postgresql"
        os.environ["RESEARCH_PG_URL"] = "postgresql://prod/neon"
        os.environ["NEON_URL"] = "postgresql://prod/neon"
        try:
            with pytest.raises(ValueError, match="SECURITY"):
                get_research_storage()
        finally:
            if old_backend is None:
                os.environ.pop("RESEARCH_STORAGE_BACKEND", None)
            else:
                os.environ["RESEARCH_STORAGE_BACKEND"] = old_backend
            os.environ.pop("RESEARCH_PG_URL", None)
            if old_neon is None:
                os.environ.pop("NEON_URL", None)
            else:
                os.environ["NEON_URL"] = old_neon

    def test_SA30_factory_sqlite_uses_context_manager(self, tmp_db):
        store = get_research_storage(db_path=tmp_db)
        with store as s:
            assert s._conn is not None
        assert s._conn is None
