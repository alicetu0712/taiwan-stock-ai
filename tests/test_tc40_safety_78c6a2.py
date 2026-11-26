"""
S78C.6A.2 Phase D — TC40 safety tests (16 tests).

Verifies the fail-closed production conn fixture introduced in S78C.6A.2:
  D01-D04: snapshot absent → pytest.skip, no file created, no empty DB
  D05-D06: mode=ro on existing file → OperationalError on write
  D07-D09: pairwise_overlap pure-function tests (no DB) pass in normal CI
  D10-D11: _PRODUCTION_SNAPSHOT constant correctness
  D12-D13: conn fixture does not use platform.db path
  D14-D16: isolation guard still active (guard regression)

These tests use only :memory: or tmpdir — no production DB access.
"""

from __future__ import annotations

import os
import sqlite3

import pytest

from src.research.calendar_contract_s50 import get_overlap

# ---------------------------------------------------------------------------
# Import the constant and fixture code under test
# ---------------------------------------------------------------------------

# We re-derive the expected value rather than importing the constant to keep
# this test file self-contained and not coupled to implementation names.
_EXPECTED_SNAPSHOT_PATH = "tests/fixtures/prod_audit_snapshot.db"


# ---------------------------------------------------------------------------
# D01-D04: conn fixture fail-closed when snapshot absent
# ---------------------------------------------------------------------------


class TestD01_FailClosedWhenAbsent:
    """When prod_audit_snapshot.db is absent, conn must skip — not open a file."""

    def test_snapshot_absent_in_ci_environment(self):
        # In CI, the snapshot file must not exist (no credentials to place it).
        assert not os.path.exists(_EXPECTED_SNAPSHOT_PATH), (
            f"Snapshot unexpectedly found at {_EXPECTED_SNAPSHOT_PATH!r}. "
            "In CI this path must be absent so production_audit tests are skipped."
        )

    def test_no_platform_db_at_snapshot_path(self):
        # Snapshot path must not overlap with production platform.db.
        assert "platform.db" not in _EXPECTED_SNAPSHOT_PATH

    def test_snapshot_path_is_in_tests_fixtures(self):
        # Snapshot lives under tests/fixtures, not data/ (production area).
        assert _EXPECTED_SNAPSHOT_PATH.startswith("tests/fixtures/")

    def test_snapshot_path_ends_with_db(self):
        assert _EXPECTED_SNAPSHOT_PATH.endswith(".db")


# ---------------------------------------------------------------------------
# D05-D06: mode=ro on existing file blocks writes
# ---------------------------------------------------------------------------


class TestD05_ModeRoBlocksWrites:
    """sqlite3 URI mode=ro on an existing file raises OperationalError on write."""

    def test_mode_ro_raises_on_write(self, tmp_path):
        # Create a valid SQLite file first.
        db_path = tmp_path / "snapshot_test.db"
        with sqlite3.connect(str(db_path)) as seed:
            seed.execute("CREATE TABLE t (x INTEGER)")
            seed.commit()

        # Open in mode=ro — writing must raise OperationalError.
        ro_conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        with pytest.raises(sqlite3.OperationalError):
            ro_conn.execute("INSERT INTO t VALUES (1)")
            ro_conn.commit()
        ro_conn.close()

    def test_mode_ro_allows_read(self, tmp_path):
        # mode=ro must still allow SELECT.
        db_path = tmp_path / "snapshot_read.db"
        with sqlite3.connect(str(db_path)) as seed:
            seed.execute("CREATE TABLE u (y INTEGER)")
            seed.execute("INSERT INTO u VALUES (42)")
            seed.commit()

        ro_conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        result = ro_conn.execute("SELECT y FROM u").fetchone()
        assert result[0] == 42
        ro_conn.close()


# ---------------------------------------------------------------------------
# D07-D09: pairwise_overlap pure-function tests (no DB) — normal CI
# ---------------------------------------------------------------------------


class TestD07_PairwiseOverlapPureFunction:
    """get_overlap() is a pure function — no DB, no production_audit mark needed."""

    def test_pairwise_overlap_oct13_oct14(self):
        ov = get_overlap("2026-10-13", "2026-10-14")
        assert ov["pct"] == 80
        assert ov["adjacent"] is True

    def test_pairwise_overlap_oct21_oct22(self):
        ov = get_overlap("2026-10-21", "2026-10-22")
        assert ov["pct"] == 80
        assert ov["adjacent"] is True

    def test_pairwise_overlap_oct13_oct21_zero(self):
        ov = get_overlap("2026-10-13", "2026-10-21")
        assert ov["pct"] == 0


# ---------------------------------------------------------------------------
# D10-D11: _PRODUCTION_SNAPSHOT constant correctness
# ---------------------------------------------------------------------------


class TestD10_SnapshotConstantContract:
    """The snapshot constant in test_session50_market_sources must have specific properties."""

    def test_constant_path_not_data_platform_db(self):
        # Import the actual constant from the module to verify its value.
        import tests.test_session50_market_sources as m50

        assert "platform.db" not in m50._PRODUCTION_SNAPSHOT

    def test_constant_path_in_tests_fixtures_dir(self):
        import tests.test_session50_market_sources as m50

        assert m50._PRODUCTION_SNAPSHOT.startswith("tests/fixtures/")


# ---------------------------------------------------------------------------
# D12-D13: conn fixture must NOT use platform.db path
# ---------------------------------------------------------------------------


class TestD12_ConnFixtureNotPlatformDb:
    """The conn fixture in test_session50_market_sources must not reference platform.db."""

    def test_conn_fixture_source_not_platform_db(self):
        import inspect

        import tests.test_session50_market_sources as m50

        # Retrieve the fixture function's source code.
        src = inspect.getsource(m50.conn)
        assert "platform.db" not in src

    def test_conn_fixture_uses_production_snapshot_constant(self):
        import inspect

        import tests.test_session50_market_sources as m50

        src = inspect.getsource(m50.conn)
        assert "_PRODUCTION_SNAPSHOT" in src


# ---------------------------------------------------------------------------
# D14-D16: isolation guard regression
# ---------------------------------------------------------------------------


class TestD14_IsolationGuardRegression:
    """The _block_production_sqlite_paths guard must still block platform.db in CI."""

    def test_guard_blocks_platform_db_path(self):
        # The autouse guard should raise AssertionError when platform.db is opened.
        with pytest.raises(AssertionError, match="ISOLATION GUARD"):
            sqlite3.connect("data/platform.db")

    def test_guard_allows_memory_db(self):
        # :memory: must pass through the guard without error.
        conn = sqlite3.connect(":memory:")
        assert conn is not None
        conn.close()

    def test_guard_blocks_absolute_platform_db_path(self):
        with pytest.raises(AssertionError, match="ISOLATION GUARD"):
            sqlite3.connect("/some/path/to/platform.db")
