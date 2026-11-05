"""
tests/test_cross_runner_persistence.py — Cross-runner persistence tests.

Simulates the GitHub Actions Option A (artifact cache) scenario:
  Run A: writes decisions to SQLite file
  Run B: "new runner" opens the same SQLite file (simulates artifact restore)
  Run C: same runner repeats — verifies idempotency
  Run D: same PK, different hash — verifies ConflictError is raised

These tests prove that if the SQLite file is preserved between runners
(e.g. via GitHub Actions artifact cache), the historical decisions remain
safe, complete, and verifiable.

CR01–CR08: core cross-runner scenarios
CR09–CR12: decision_hash integrity across runs
CR13–CR16: outcome separation across runs
CR17–CR20: operational summary across runs
"""

from __future__ import annotations

import shutil
import sqlite3
from datetime import date, datetime, timezone
from typing import List, Optional

from src.research.hybrid_forward_db import (
    ConflictError,
    HybridForwardDecision,
    HybridForwardOutcome,
    HybridForwardRunLog,
    OutcomeStatus,
    RunStatus,
    compute_decision_hash,
    ensure_schema,
    get_operational_summary,
    insert_decision,
    insert_outcome,
    upsert_run_log,
)
from src.research.storage_adapter import SQLiteResearchStorage, StorageHealthStatus

# ── Test constants ────────────────────────────────────────────────────────────

FREEZE_DATE = date(2026, 11, 5)
RUN_A_DATE  = date(2026, 11, 6)
RUN_B_DATE  = date(2026, 11, 7)
RUN_C_DATE  = date(2026, 11, 6)  # Same as Run A (idempotency test)
RUN_D_DATE  = date(2026, 11, 6)  # Same as Run A (conflict test)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_decision(
    stock_id: str = "2330",
    trade_date: date = RUN_A_DATE,
    hybrid_action: str = "DIRECT_NEXT_OPEN",
    rule_reason: str = "P3_bull_rising",
    run_id: str = "run-a",
) -> HybridForwardDecision:
    return HybridForwardDecision(
        stock_id=stock_id,
        trade_date=trade_date,
        rule_version="hybrid_v1",
        research_version="v2_research_v2",
        v2_entry_label="ENTRY_READY",
        hybrid_action=hybrid_action,
        rule_reason=rule_reason,
        rule_priority=3,
        market_regime="bull",
        ma20_slope_pct=0.5,
        ma20_trend="rising",
        ma20_gap_pct=1.2,
        feature_cutoff_date=trade_date,
        input_data_as_of=trade_date,
        input_data_hash="aabbccdd",
        decision_hash=compute_decision_hash(hybrid_action, rule_reason, 3, "hybrid_v1"),
        capture_classification="PROSPECTIVE",
        captured_at=datetime(trade_date.year, trade_date.month, trade_date.day, 8, 0, tzinfo=timezone.utc),
        run_id=run_id,
    )


def _make_run_log(
    run_id: str, trade_date: date, status: str = RunStatus.SUCCESS, n: int = 1
) -> HybridForwardRunLog:
    return HybridForwardRunLog(
        run_id=run_id,
        trade_date=trade_date,
        started_at=datetime(trade_date.year, trade_date.month, trade_date.day, 8, 0, tzinfo=timezone.utc),
        finished_at=datetime(trade_date.year, trade_date.month, trade_date.day, 8, 1, tzinfo=timezone.utc),
        input_data_date=trade_date,
        inserted_count=n,
        skipped_count=0,
        conflict_count=0,
        error_count=0,
        outcome_filled_count=0,
        status=status,
        error_summary=None,
    )


def _simulate_runner_run(db_path: str, decisions: List[HybridForwardDecision], run_id: str) -> dict:
    """Simulate one runner execution. Returns summary with counts."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)

    inserted = 0
    skipped = 0
    conflicts = 0

    for d in decisions:
        try:
            result = insert_decision(conn, d)
            if result is None:
                skipped += 1
            else:
                inserted += 1
        except ConflictError:
            conflicts += 1

    trade_date = decisions[0].trade_date if decisions else date.today()
    log = HybridForwardRunLog(
        run_id=run_id,
        trade_date=trade_date,
        started_at=datetime(trade_date.year, trade_date.month, trade_date.day, 8, 0, tzinfo=timezone.utc),
        finished_at=datetime(trade_date.year, trade_date.month, trade_date.day, 8, 1, tzinfo=timezone.utc),
        input_data_date=trade_date,
        inserted_count=inserted,
        skipped_count=skipped,
        conflict_count=conflicts,
        error_count=0,
        outcome_filled_count=0,
        status=RunStatus.CONFLICT if conflicts > 0 else RunStatus.SUCCESS,
        error_summary=None,
    )
    upsert_run_log(conn, log)
    conn.commit()
    conn.close()

    return {"inserted": inserted, "skipped": skipped, "conflicts": conflicts}


def _simulate_artifact_copy(src_db: str, dst_db: str) -> None:
    """Simulate GitHub Actions artifact upload → download: copy the file."""
    shutil.copy2(src_db, dst_db)


# ── CR01–CR08: Core cross-runner persistence ─────────────────────────────────

class TestCrossRunnerBasicPersistence:
    def test_CR01_run_a_writes_decisions(self, tmp_path):
        """Run A writes decisions; they must be readable immediately after."""
        db_a = str(tmp_path / "run_a.db")
        decisions = [_make_decision(stock_id=s) for s in ["2330", "2317", "2412"]]
        result = _simulate_runner_run(db_a, decisions, "run-a")
        assert result["inserted"] == 3
        assert result["conflicts"] == 0

        # Verify directly
        conn = sqlite3.connect(db_a)
        n = conn.execute("SELECT COUNT(*) FROM hybrid_forward_decision").fetchone()[0]
        conn.close()
        assert n == 3

    def test_CR02_run_b_reads_run_a_decisions_after_artifact_restore(self, tmp_path):
        """
        Run B: Simulates GitHub Actions artifact restore.
        After copying db_a → db_b, Run B can read all decisions from Run A.
        """
        db_a = str(tmp_path / "run_a.db")
        db_b = str(tmp_path / "run_b.db")  # simulates artifact restore

        # Run A writes
        decisions_a = [_make_decision(stock_id=s, run_id="run-a") for s in ["2330", "2317"]]
        _simulate_runner_run(db_a, decisions_a, "run-a")

        # Artifact copy (upload Run A, download as Run B)
        _simulate_artifact_copy(db_a, db_b)

        # Run B: new runner, reads restored file
        decisions_b = [_make_decision(stock_id="2412", trade_date=RUN_B_DATE, run_id="run-b")]
        _simulate_runner_run(db_b, decisions_b, "run-b")

        # Verify: db_b has all 3 decisions (2 from A + 1 from B)
        conn = sqlite3.connect(db_b)
        n = conn.execute("SELECT COUNT(*) FROM hybrid_forward_decision").fetchone()[0]
        stocks = {r[0] for r in conn.execute("SELECT stock_id FROM hybrid_forward_decision").fetchall()}
        conn.close()

        assert n == 3
        assert stocks == {"2330", "2317", "2412"}

    def test_CR03_run_b_original_decision_hashes_preserved(self, tmp_path):
        """Decision hashes from Run A must be bit-for-bit identical in Run B's restored file."""
        db_a = str(tmp_path / "run_a.db")
        db_b = str(tmp_path / "run_b.db")

        d = _make_decision(stock_id="2330", run_id="run-a")
        _simulate_runner_run(db_a, [d], "run-a")
        _simulate_artifact_copy(db_a, db_b)

        # Read hash from restored DB
        conn = sqlite3.connect(db_b)
        row = conn.execute(
            "SELECT decision_hash FROM hybrid_forward_decision WHERE stock_id='2330'"
        ).fetchone()
        conn.close()

        assert row[0] == d.decision_hash

    def test_CR04_run_a_run_log_preserved_in_run_b(self, tmp_path):
        """Run A's run log entries must be present in Run B's restored DB."""
        db_a = str(tmp_path / "run_a.db")
        db_b = str(tmp_path / "run_b.db")

        _simulate_runner_run(db_a, [_make_decision()], "run-a")
        _simulate_artifact_copy(db_a, db_b)

        conn = sqlite3.connect(db_b)
        log = conn.execute(
            "SELECT run_id, status FROM hybrid_forward_run_log WHERE run_id='run-a'"
        ).fetchone()
        conn.close()

        assert log is not None
        assert log[0] == "run-a"
        assert log[1] == RunStatus.SUCCESS

    def test_CR05_multiple_runs_accumulate_decisions(self, tmp_path):
        """Simulates 5 sequential trading days of data accumulation."""
        db_path = str(tmp_path / "platform.db")

        trade_dates = [
            date(2026, 11, 6), date(2026, 11, 7), date(2026, 11, 10),
            date(2026, 11, 11), date(2026, 11, 12),
        ]

        for i, td in enumerate(trade_dates):
            decisions = [
                _make_decision(stock_id=f"23{30+j:02d}", trade_date=td, run_id=f"run-{i}")
                for j in range(3)  # 3 stocks per day
            ]
            result = _simulate_runner_run(db_path, decisions, f"run-{i}")
            assert result["inserted"] == 3

        conn = sqlite3.connect(db_path)
        total = conn.execute("SELECT COUNT(*) FROM hybrid_forward_decision").fetchone()[0]
        days = conn.execute("SELECT COUNT(DISTINCT trade_date) FROM hybrid_forward_decision").fetchone()[0]
        conn.close()

        assert total == 15   # 5 days × 3 stocks
        assert days == 5

    def test_CR06_artifact_copy_preserves_wal_state(self, tmp_path):
        """Copied file must be a valid, openable SQLite database."""
        db_a = str(tmp_path / "run_a.db")
        db_b = str(tmp_path / "run_b.db")

        _simulate_runner_run(db_a, [_make_decision()], "run-a")
        _simulate_artifact_copy(db_a, db_b)

        # Must open without error
        conn = sqlite3.connect(db_b)
        try:
            conn.execute("SELECT 1").fetchone()
        finally:
            conn.close()

    def test_CR07_storage_adapter_works_on_restored_db(self, tmp_path):
        """SQLiteResearchStorage works correctly on a restored (artifact-copy) file."""
        db_a = str(tmp_path / "run_a.db")
        db_b = str(tmp_path / "run_b.db")

        _simulate_runner_run(db_a, [_make_decision()], "run-a")
        _simulate_artifact_copy(db_a, db_b)

        with SQLiteResearchStorage(db_b) as store:
            health = store.health_check()
            assert health["status"] == StorageHealthStatus.HEALTHY
            summary = store.get_operational_summary()
            assert summary["total_decisions"] == 1

    def test_CR08_operational_summary_correct_after_multiple_runs(self, tmp_path):
        """get_operational_summary returns correct counts after sequential runs."""
        db_path = str(tmp_path / "platform.db")

        for i, td in enumerate([date(2026, 11, 6), date(2026, 11, 7), date(2026, 11, 10)]):
            decisions = [_make_decision(stock_id=f"23{30+j}", trade_date=td, run_id=f"run-{i}") for j in range(2)]
            _simulate_runner_run(db_path, decisions, f"run-{i}")

        conn = sqlite3.connect(db_path)
        summary = get_operational_summary(conn)
        conn.close()

        assert summary["total_decisions"] == 6
        assert summary["prospective_decisions"] == 6
        assert summary["latest_run"] is not None


# ── CR09–CR12: Decision hash integrity ────────────────────────────────────────

class TestDecisionHashIntegrity:
    def test_CR09_idempotent_re_run_produces_zero_conflicts(self, tmp_path):
        """
        Run C: Same decisions re-run on same date.
        Must produce 0 insertions and 0 conflicts (idempotent).
        """
        db_path = str(tmp_path / "platform.db")
        decisions = [_make_decision(stock_id="2330")]

        result_a = _simulate_runner_run(db_path, decisions, "run-a")
        result_c = _simulate_runner_run(db_path, decisions, "run-c")

        assert result_a["inserted"] == 1
        assert result_c["inserted"] == 0
        assert result_c["skipped"] == 1
        assert result_c["conflicts"] == 0

    def test_CR10_idempotent_does_not_create_duplicate_rows(self, tmp_path):
        db_path = str(tmp_path / "platform.db")
        d = _make_decision()
        _simulate_runner_run(db_path, [d], "run-a")
        _simulate_runner_run(db_path, [d], "run-c")

        conn = sqlite3.connect(db_path)
        n = conn.execute("SELECT COUNT(*) FROM hybrid_forward_decision").fetchone()[0]
        conn.close()
        assert n == 1

    def test_CR11_conflict_detected_same_key_different_hash(self, tmp_path):
        """
        Run D: Same (stock_id, trade_date, rule_version) but different hybrid_action.
        Must raise ConflictError and NOT overwrite the original.
        """
        db_path = str(tmp_path / "platform.db")
        d_original = _make_decision(hybrid_action="DIRECT_NEXT_OPEN")
        _simulate_runner_run(db_path, [d_original], "run-a")

        d_different = _make_decision(hybrid_action="WAIT_PULLBACK")
        result_d = _simulate_runner_run(db_path, [d_different], "run-d")
        assert result_d["conflicts"] == 1
        assert result_d["inserted"] == 0

    def test_CR12_original_hash_survives_conflict_attempt(self, tmp_path):
        """Original record's decision_hash must not change after a conflict attempt."""
        db_path = str(tmp_path / "platform.db")
        d_original = _make_decision(hybrid_action="DIRECT_NEXT_OPEN")
        _simulate_runner_run(db_path, [d_original], "run-a")

        d_different = _make_decision(hybrid_action="WAIT_PULLBACK")
        _simulate_runner_run(db_path, [d_different], "run-d")

        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT decision_hash, hybrid_action FROM hybrid_forward_decision WHERE stock_id='2330'"
        ).fetchone()
        conn.close()

        assert row[1] == "DIRECT_NEXT_OPEN"
        assert row[0] == d_original.decision_hash


# ── CR13–CR16: Outcome separation across runs ─────────────────────────────────

class TestOutcomeSeparationCrossRun:
    def test_CR13_outcome_insert_does_not_modify_decision(self, tmp_path):
        db_path = str(tmp_path / "platform.db")
        d = _make_decision()

        conn_a = sqlite3.connect(db_path)
        ensure_schema(conn_a)
        did = insert_decision(conn_a, d)
        conn_a.commit()
        conn_a.close()

        # Simulate outcome fill in a new connection (like a new runner run)
        conn_b = sqlite3.connect(db_path)
        conn_b.row_factory = sqlite3.Row
        o = HybridForwardOutcome(
            decision_id=did,
            stock_id="2330",
            trade_date=RUN_A_DATE,
            rule_version="hybrid_v1",
            horizon="20d",
            maturity_date=date(2026, 12, 11),
            maturity_trading_days=20,
            v1_net_return=2.1,
            v2_net_return=2.1,
            hybrid_net_return=2.1,
            hybrid_vs_v1_delta=0.0,
            hybrid_vs_v2_delta=0.0,
            data_source_version="2026-12-11",
            calculation_version="1.0",
            outcome_status=OutcomeStatus.MATURED,
            calculated_at=datetime(2026, 12, 15, tzinfo=timezone.utc),
        )
        insert_outcome(conn_b, o)
        conn_b.commit()
        conn_b.close()

        # Verify decision row is unchanged
        conn_c = sqlite3.connect(db_path)
        row = conn_c.execute(
            "SELECT hybrid_action, run_id FROM hybrid_forward_decision WHERE id=?", (did,)
        ).fetchone()
        conn_c.close()
        assert row[0] == "DIRECT_NEXT_OPEN"
        assert row[1] == "run-a"

    def test_CR14_outcome_idempotent_across_runs(self, tmp_path):
        """Outcome fill called twice from two separate connections must be idempotent."""
        db_path = str(tmp_path / "platform.db")
        d = _make_decision()

        conn = sqlite3.connect(db_path)
        ensure_schema(conn)
        did = insert_decision(conn, d)
        conn.commit()
        conn.close()

        def _fill_outcome(db_path: str, decision_id: int) -> Optional[int]:
            c = sqlite3.connect(db_path)
            o = HybridForwardOutcome(
                decision_id=decision_id, stock_id="2330", trade_date=RUN_A_DATE,
                rule_version="hybrid_v1", horizon="20d",
                maturity_date=date(2026, 12, 11), maturity_trading_days=20,
                v1_net_return=2.1, v2_net_return=2.1, hybrid_net_return=2.1,
                hybrid_vs_v1_delta=0.0, hybrid_vs_v2_delta=0.0,
                data_source_version="2026-12-11", calculation_version="1.0",
                outcome_status=OutcomeStatus.MATURED,
                calculated_at=datetime(2026, 12, 15, tzinfo=timezone.utc),
            )
            result = insert_outcome(c, o)
            c.commit()
            c.close()
            return result

        result1 = _fill_outcome(db_path, did)
        result2 = _fill_outcome(db_path, did)
        assert result1 is not None
        assert result2 is None  # idempotent skip

    def test_CR15_decision_count_unchanged_after_outcome_fills(self, tmp_path):
        db_path = str(tmp_path / "platform.db")
        stocks = ["2330", "2317", "2412"]
        dids = []

        conn = sqlite3.connect(db_path)
        ensure_schema(conn)
        for s in stocks:
            did = insert_decision(conn, _make_decision(stock_id=s))
            dids.append(did)
        conn.commit()
        conn.close()

        # Fill outcomes in a "new runner run"
        conn2 = sqlite3.connect(db_path)
        for did in dids:
            o = HybridForwardOutcome(
                decision_id=did, stock_id="2330", trade_date=RUN_A_DATE,
                rule_version="hybrid_v1", horizon="20d",
                maturity_date=date(2026, 12, 11), maturity_trading_days=20,
                v1_net_return=1.0, v2_net_return=1.0, hybrid_net_return=1.0,
                hybrid_vs_v1_delta=0.0, hybrid_vs_v2_delta=0.0,
                data_source_version="2026-12-11", calculation_version="1.0",
                outcome_status=OutcomeStatus.MATURED,
                calculated_at=datetime(2026, 12, 15, tzinfo=timezone.utc),
            )
            insert_outcome(conn2, o)
        conn2.commit()
        conn2.close()

        conn3 = sqlite3.connect(db_path)
        n_decisions = conn3.execute("SELECT COUNT(*) FROM hybrid_forward_decision").fetchone()[0]
        n_outcomes = conn3.execute("SELECT COUNT(*) FROM hybrid_forward_outcome").fetchone()[0]
        conn3.close()

        assert n_decisions == 3
        assert n_outcomes == 3

    def test_CR16_decision_id_fk_linkage_preserved_after_copy(self, tmp_path):
        """After artifact copy, decision_id FK in outcome still resolves correctly."""
        db_a = str(tmp_path / "run_a.db")
        db_b = str(tmp_path / "run_b.db")

        d = _make_decision()
        conn = sqlite3.connect(db_a)
        ensure_schema(conn)
        did = insert_decision(conn, d)
        o = HybridForwardOutcome(
            decision_id=did, stock_id="2330", trade_date=RUN_A_DATE,
            rule_version="hybrid_v1", horizon="20d",
            maturity_date=date(2026, 12, 11), maturity_trading_days=20,
            v1_net_return=1.5, v2_net_return=1.5, hybrid_net_return=1.5,
            hybrid_vs_v1_delta=0.0, hybrid_vs_v2_delta=0.0,
            data_source_version="2026-12-11", calculation_version="1.0",
            outcome_status=OutcomeStatus.MATURED,
            calculated_at=datetime(2026, 12, 15, tzinfo=timezone.utc),
        )
        insert_outcome(conn, o)
        conn.commit()
        conn.close()

        # Artifact copy
        _simulate_artifact_copy(db_a, db_b)

        # Verify FK linkage in restored DB
        conn_b = sqlite3.connect(db_b)
        row = conn_b.execute(
            """
            SELECT d.hybrid_action, o.hybrid_net_return
            FROM hybrid_forward_outcome o
            JOIN hybrid_forward_decision d ON d.id = o.decision_id
            WHERE d.stock_id = '2330'
            """
        ).fetchone()
        conn_b.close()
        assert row is not None
        assert row[0] == "DIRECT_NEXT_OPEN"
        assert row[1] == 1.5


# ── CR17–CR20: Operational summary across runs ────────────────────────────────

class TestSummaryAcrossRuns:
    def test_CR17_latest_run_reflects_most_recent(self, tmp_path):
        db_path = str(tmp_path / "platform.db")
        d1 = _make_decision(stock_id="2330", trade_date=date(2026, 11, 6), run_id="run-mon")
        d2 = _make_decision(stock_id="2330", trade_date=date(2026, 11, 7), run_id="run-tue")
        _simulate_runner_run(db_path, [d1], "run-mon")
        _simulate_runner_run(db_path, [d2], "run-tue")

        conn = sqlite3.connect(db_path)
        summary = get_operational_summary(conn)
        conn.close()

        assert summary["latest_run"]["trade_date"] == str(date(2026, 11, 7))

    def test_CR18_consecutive_failures_count_resets_on_success(self, tmp_path):
        db_path = str(tmp_path / "platform.db")
        conn = sqlite3.connect(db_path)
        ensure_schema(conn)

        # Two failures then one success
        for i, status in enumerate([RunStatus.FAILED, RunStatus.FAILED, RunStatus.SUCCESS]):
            td = date(2026, 11, 6 + i)
            upsert_run_log(conn, _make_run_log(f"run-{i}", td, status))
        conn.commit()
        summary = get_operational_summary(conn)
        conn.close()

        assert summary["consecutive_failures"] == 0

    def test_CR19_conflict_count_accumulates_correctly(self, tmp_path):
        db_path = str(tmp_path / "platform.db")

        d_original = _make_decision(hybrid_action="DIRECT_NEXT_OPEN")
        _simulate_runner_run(db_path, [d_original], "run-a")

        d_conflict = _make_decision(hybrid_action="WAIT_PULLBACK")
        _simulate_runner_run(db_path, [d_conflict], "run-d")

        conn = sqlite3.connect(db_path)
        total_conflicts = conn.execute(
            "SELECT SUM(conflict_count) FROM hybrid_forward_run_log"
        ).fetchone()[0] or 0
        conn.close()

        assert total_conflicts == 1

    def test_CR20_prospective_count_tracks_correctly(self, tmp_path):
        db_path = str(tmp_path / "platform.db")
        stocks = ["2330", "2317", "2412", "2881"]

        for s in stocks:
            _simulate_runner_run(
                db_path,
                [_make_decision(stock_id=s, trade_date=date(2026, 11, 6))],
                f"run-{s}",
            )

        conn = sqlite3.connect(db_path)
        summary = get_operational_summary(conn)
        conn.close()

        assert summary["prospective_decisions"] == 4
        assert summary["prospective_stocks"] == 4
