"""
S78C.8B — Shared Fixture Architecture verification tests (SF01–SF16).

Verifies the contracts of the new Shared Fixture infrastructure added to conftest.py:
  - Guard identity fixture (ci_guard_identity, get_active_guard)
  - File-backed isolated database (IsolatedFileDb, ci_file_conn, ci_file_conn_with_data)
  - Schema consistency (_apply_schema refactor)
  - Synthetic seed determinism
  - Connection ownership and cleanup

All tests use synthetic data or in-memory databases only.
No production DB access. No historical evidence fabricated.
"""
from __future__ import annotations

import os
import sqlite3

import pytest

import tests.conftest as _cf


class TestSharedFixtureArchitecture:

    # ------------------------------------------------------------------
    # SF01 — Guard identity
    # ------------------------------------------------------------------

    def test_sf01_guard_identity_matches_active_guard(self, ci_guard_identity):
        """SF01: ci_guard_identity fixture returns the installed _guarded_connect."""
        assert ci_guard_identity is _cf._guarded_connect
        assert sqlite3.connect is ci_guard_identity

    # ------------------------------------------------------------------
    # SF02 — Fail-closed on mismatch
    # ------------------------------------------------------------------

    def test_sf02_missing_guard_identity_fails_closed(self):
        """SF02: get_active_guard() raises AssertionError when Guard identity mismatches.

        Uses a controlled sentinel (not a database connection, not production path).
        patch is exception-safe; guard is restored by __exit__.
        """
        from unittest.mock import patch

        _sentinel = lambda *a, **k: None  # noqa: E731  # distinct non-guard callable

        with patch("sqlite3.connect", new=_sentinel):
            with pytest.raises(AssertionError, match="GUARD FAILURE"):
                _cf.get_active_guard()

        # Guard restored by patch context exit
        assert sqlite3.connect is _cf._guarded_connect

    # ------------------------------------------------------------------
    # SF03 — In-memory database through Guard
    # ------------------------------------------------------------------

    def test_sf03_in_memory_database_created_through_guard(self, ci_safe_conn):
        """SF03: ci_safe_conn creates in-memory DB through Guard; schema present, zero rows."""
        rows = ci_safe_conn.execute(
            "SELECT COUNT(*) FROM daily_prices"
        ).fetchone()[0]
        assert rows == 0
        assert sqlite3.connect is _cf._guarded_connect

    # ------------------------------------------------------------------
    # SF04 — File-backed path inside registered root
    # ------------------------------------------------------------------

    def test_sf04_file_backed_path_inside_registered_root(self, tmp_path):
        """SF04: File-backed database path is under a registered pytest temp root."""
        db_path = str(tmp_path / "sf04.db")
        resolved = os.path.realpath(db_path)

        registered_roots = list(_cf._PYTEST_TEMP_ROOT)
        assert len(registered_roots) >= 1, "No registered temp roots found"
        is_under_root = any(
            resolved.startswith(root + os.sep) or resolved == root
            for root in registered_roots
        )
        assert is_under_root, (
            f"Path {resolved!r} not under any registered root: {registered_roots}"
        )

        # Guard allows opening this path (no exception)
        with _cf.IsolatedFileDb(db_path) as conn:
            conn.execute("SELECT 1").fetchone()

    # ------------------------------------------------------------------
    # SF05 — Schema contract
    # ------------------------------------------------------------------

    def test_sf05_schema_matches_declared_contract(self, ci_safe_conn):
        """SF05: daily_prices table has the expected canonical column set."""
        rows = ci_safe_conn.execute("PRAGMA table_info(daily_prices)").fetchall()
        col_names = {row[1] for row in rows}
        required = {"id", "date", "stock_id", "open", "high", "low", "close", "volume"}
        assert required.issubset(col_names), (
            f"Schema missing columns: {required - col_names}"
        )

    # ------------------------------------------------------------------
    # SF06 — Synthetic seed determinism
    # ------------------------------------------------------------------

    def test_sf06_synthetic_seed_deterministic_records(self, ci_conn_with_data):
        """SF06: Synthetic seed contains exactly 12 records with expected fixed values."""
        total = ci_conn_with_data.execute(
            "SELECT COUNT(*) FROM daily_prices"
        ).fetchone()[0]
        assert total == 12, f"Expected 12 seed rows, got {total}"

        # Verify specific pinned values from _SYNTHETIC_DAILY_PRICES
        row = ci_conn_with_data.execute(
            "SELECT close FROM daily_prices WHERE stock_id='2330' AND date='2026-10-29'"
        ).fetchone()
        assert row is not None
        assert row[0] == 2415.0

        row2 = ci_conn_with_data.execute(
            "SELECT close FROM daily_prices WHERE stock_id='2330' AND date='2026-11-06'"
        ).fetchone()
        assert row2 is not None
        assert row2[0] == 2135.0

        row3 = ci_conn_with_data.execute(
            "SELECT close FROM daily_prices WHERE stock_id='0050' AND date='2026-10-29'"
        ).fetchone()
        assert row3 is not None
        assert row3[0] == 190.5

    # ------------------------------------------------------------------
    # SF07 — Same seed produces identical records
    # ------------------------------------------------------------------

    def test_sf07_same_seed_produces_identical_records(self, ci_conn_with_data, tmp_path):
        """SF07: In-memory and file-backed seeded DBs produce identical logical datasets."""
        rows_mem = set(
            ci_conn_with_data.execute(
                "SELECT date, stock_id, close FROM daily_prices ORDER BY date, stock_id"
            ).fetchall()
        )

        with _cf.IsolatedFileDb(str(tmp_path / "sf07.db"), seed=True) as conn2:
            rows_file = set(
                conn2.execute(
                    "SELECT date, stock_id, close FROM daily_prices ORDER BY date, stock_id"
                ).fetchall()
            )

        assert rows_mem == rows_file, (
            f"Seed profiles diverged. Symmetric diff: {rows_mem.symmetric_difference(rows_file)}"
        )
        assert len(rows_mem) == 12

    # ------------------------------------------------------------------
    # SF08 — Independent factory invocations
    # ------------------------------------------------------------------

    def test_sf08_different_invocations_independent(self, tmp_path):
        """SF08: Two IsolatedFileDb instances do not share mutable state."""
        path_a = str(tmp_path / "sf08a.db")
        path_b = str(tmp_path / "sf08b.db")

        with _cf.IsolatedFileDb(path_a, seed=True) as conn_a:
            with _cf.IsolatedFileDb(path_b) as conn_b:
                # Write sentinel to conn_a only
                conn_a.execute(
                    "INSERT INTO daily_prices (date, stock_id, close) "
                    "VALUES ('2099-01-01', 'SENTINEL', 1.0)"
                )
                conn_a.commit()
                sentinel_in_b = conn_b.execute(
                    "SELECT COUNT(*) FROM daily_prices WHERE stock_id='SENTINEL'"
                ).fetchone()[0]
        assert sentinel_in_b == 0, "IsolatedFileDb instances share state unexpectedly"

    # ------------------------------------------------------------------
    # SF09 — Separate tests do not contaminate (two adjacent methods)
    # ------------------------------------------------------------------

    def test_sf09a_write_visible_within_same_test(self, ci_file_conn_with_data):
        """SF09a: Sentinel row written to ci_file_conn_with_data is visible within this test."""
        ci_file_conn_with_data.execute(
            "INSERT INTO daily_prices (date, stock_id, close) "
            "VALUES ('2099-01-01', 'SF09', 1.0)"
        )
        ci_file_conn_with_data.commit()
        count = ci_file_conn_with_data.execute(
            "SELECT COUNT(*) FROM daily_prices WHERE stock_id='SF09'"
        ).fetchone()[0]
        assert count == 1

    def test_sf09b_no_contamination_from_prior_test(self, ci_file_conn_with_data):
        """SF09b: Function-scoped fixture is fresh — no row from SF09a is visible."""
        count = ci_file_conn_with_data.execute(
            "SELECT COUNT(*) FROM daily_prices WHERE stock_id='SF09'"
        ).fetchone()[0]
        assert count == 0, (
            f"Contamination detected: {count} SF09 row(s) visible in a fresh fixture"
        )

    # ------------------------------------------------------------------
    # SF10 — Transaction rollback
    # ------------------------------------------------------------------

    def test_sf10_transaction_rollback_preserves_state(self, ci_file_conn_with_data):
        """SF10: Rolling back a transaction restores pre-transaction row count."""
        before = ci_file_conn_with_data.execute(
            "SELECT COUNT(*) FROM daily_prices"
        ).fetchone()[0]
        assert before == 12

        ci_file_conn_with_data.execute(
            "INSERT INTO daily_prices (date, stock_id, close) "
            "VALUES ('2099-01-01', 'ROLLBACK', 1.0)"
        )
        ci_file_conn_with_data.rollback()

        after = ci_file_conn_with_data.execute(
            "SELECT COUNT(*) FROM daily_prices"
        ).fetchone()[0]
        assert after == before, f"Rollback failed: expected {before}, got {after}"

    # ------------------------------------------------------------------
    # SF11 — File-backed close / reopen
    # ------------------------------------------------------------------

    def test_sf11_file_backed_close_reopen_persists(self, tmp_path):
        """SF11: File-backed database preserves records across close and reopen."""
        db_path = str(tmp_path / "sf11.db")

        conn1 = sqlite3.connect(db_path)
        _cf._apply_schema(conn1)
        _cf._seed(conn1)
        conn1.close()

        conn2 = sqlite3.connect(db_path)
        rows = conn2.execute("SELECT COUNT(*) FROM daily_prices").fetchone()[0]
        conn2.close()
        assert rows == 12

    # ------------------------------------------------------------------
    # SF12 — Normal cleanup
    # ------------------------------------------------------------------

    def test_sf12_normal_cleanup_closes_conn_and_removes_file(self, tmp_path):
        """SF12: IsolatedFileDb removes the owned DB file on normal context exit."""
        db_path = str(tmp_path / "sf12.db")

        with _cf.IsolatedFileDb(db_path) as conn:
            conn.execute("SELECT 1").fetchone()
            path_exists_during = os.path.exists(db_path)

        assert path_exists_during, "DB file missing during active context"
        assert not os.path.exists(db_path), "DB file not removed after normal exit"
        with pytest.raises(Exception):
            conn.execute("SELECT 1")  # closed connection must raise

    # ------------------------------------------------------------------
    # SF13 — Exception cleanup
    # ------------------------------------------------------------------

    def test_sf13_exception_cleanup_closes_conn_and_removes_file(self, tmp_path):
        """SF13: IsolatedFileDb removes the owned DB file after exception inside context."""
        db_path = str(tmp_path / "sf13.db")

        with pytest.raises(RuntimeError, match="synthetic_sf13_exception"):
            with _cf.IsolatedFileDb(db_path) as conn:
                conn.execute("SELECT 1").fetchone()
                raise RuntimeError("synthetic_sf13_exception")

        assert not os.path.exists(db_path), "DB file not removed after exception exit"
        with pytest.raises(Exception):
            conn.execute("SELECT 1")

    # ------------------------------------------------------------------
    # SF14 — Caller parent directory and sentinel preserved
    # ------------------------------------------------------------------

    def test_sf14_parent_dir_and_sentinel_preserved(self, tmp_path):
        """SF14: IsolatedFileDb never removes parent directory or pre-existing sentinel."""
        parent = tmp_path / "sf14_parent"
        parent.mkdir()
        sentinel = parent / "sentinel.txt"
        sentinel.write_text("sf14_content")
        db_path = str(parent / "sf14.db")

        with _cf.IsolatedFileDb(db_path):
            pass

        assert parent.exists(), "Parent directory was removed by IsolatedFileDb"
        assert sentinel.exists(), "Sentinel file was removed by IsolatedFileDb"
        assert sentinel.read_text() == "sf14_content", "Sentinel content modified"
        assert not (parent / "sf14.db").exists(), "DB file should have been removed"

    # ------------------------------------------------------------------
    # SF15 — Forbidden path still blocked
    # ------------------------------------------------------------------

    def test_sf15_synthetic_forbidden_path_blocked(self):
        """SF15: Production DB path remains blocked through the Guard after all fixture use."""
        with pytest.raises(AssertionError, match="ISOLATION GUARD"):
            sqlite3.connect("data/platform.db")

    # ------------------------------------------------------------------
    # SF16 — Guard identity intact after fixture lifecycle
    # ------------------------------------------------------------------

    def test_sf16_guard_identity_intact_after_fixture_lifecycle(
        self, ci_guard_identity, ci_file_conn
    ):
        """SF16: Guard identity is unchanged after ci_file_conn and ci_guard_identity lifecycle."""
        # ci_file_conn uses sqlite3.connect internally — verify guard still active
        ci_file_conn.execute("SELECT COUNT(*) FROM daily_prices").fetchone()
        assert sqlite3.connect is _cf._guarded_connect
        assert ci_guard_identity is _cf._guarded_connect
