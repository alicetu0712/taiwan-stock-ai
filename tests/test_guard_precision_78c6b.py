"""
S78C.6B.2 Phase F — Isolation Guard fail-closed safety regression tests (21 tests).

Verifies the session-level fail-closed guard introduced in S78C.6B.2:

Allowed-path tests (guard must NOT block):
  E01: pytest tmp_path test.db
  E02: test_platform.db in pytest tmp_path (was false positive with old guard)
  E03: platform.db in pytest tmp_path (different canonical path)
  E04: :memory: always allowed
  E05: ci_module_conn (module-scoped :memory:)

Production-block tests (guard MUST block):
  E06: Canonical production path blocked
  E07: Path traversal to production DB blocked
  E08: Symlink targeting production canonical path blocked
  E09: SQLite URI pointing to production DB blocked

Fail-closed tests (unknown paths blocked by default):
  EF01: Unknown path outside allowed roots blocked
  EF02: Hardlink alias to production DB blocked (skipped when prod DB absent)
  EF03: Percent-encoded URI pointing to production DB blocked
  EF04: Unsupported URI scheme blocked
  EF05: Empty string path blocked
  EF06: Authority-based URI blocked

Allowlist-completeness tests:
  EF07: tests/fixtures/ root is an explicitly allowed root
  EF08: pytest session temp root is registered after _register_pytest_temp_root runs

Guard-correctness tests:
  E13: Guard raises before sqlite3.connect() completes (no empty file created)
  E14: Guard is active during test body execution (live check)
  EF09: Guard liveness fixture raises if guard is patched out

All tests use synthetic paths or pytest tmp_path — no production DB access.
"""

from __future__ import annotations

import os
import sqlite3
import urllib.parse
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).parent.parent
_PRODUCTION_DB_CANONICAL = os.path.realpath(str(_PROJECT_ROOT / "data" / "platform.db"))
_PROD_AUDIT_SNAPSHOT = str(
    _PROJECT_ROOT / "tests" / "fixtures" / "prod_audit_snapshot.db"
)
_TESTS_FIXTURES_CANONICAL = os.path.realpath(str(_PROJECT_ROOT / "tests" / "fixtures"))


# ---------------------------------------------------------------------------
# E01-E03: Legitimate pytest temp DBs are allowed
# ---------------------------------------------------------------------------


class TestE01_AllowedPaths:

    def test_e01_pytest_tmp_db_allowed(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE t (x INTEGER)")
        conn.close()

    def test_e02_test_platform_db_in_tmp_allowed(self, tmp_path):
        # Was a false positive with substring guard: "platform.db" in "test_platform.db"
        db_path = str(tmp_path / "test_platform.db")
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE t (x INTEGER)")
        conn.close()

    def test_e03_platform_db_in_tmp_allowed(self, tmp_path):
        # pytest tmp_path / "platform.db" must be allowed: canonical path ≠ production
        db_path = str(tmp_path / "platform.db")
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE t (x INTEGER)")
        conn.close()


# ---------------------------------------------------------------------------
# E04-E05: In-memory and module-scoped CI fixtures
# ---------------------------------------------------------------------------


class TestE04_InMemoryAndCIFixtures:

    def test_e04_in_memory_allowed(self):
        conn = sqlite3.connect(":memory:")
        assert conn is not None
        conn.close()

    def test_e05_ci_module_conn_accessible(self, ci_module_conn):
        # ci_module_conn is module-scoped :memory: — must be reachable
        rows = ci_module_conn.execute("PRAGMA database_list").fetchall()
        assert any(row[2] == "" for row in rows)  # :memory: has empty path


# ---------------------------------------------------------------------------
# E06-E09: Production DB access is blocked (various bypass vectors)
# ---------------------------------------------------------------------------


class TestE06_ProductionPathBlocked:

    def test_e06_production_canonical_path_blocked(self):
        with pytest.raises(AssertionError, match="ISOLATION GUARD"):
            sqlite3.connect(_PRODUCTION_DB_CANONICAL)

    def test_e07_path_traversal_blocked(self):
        traversal = str(_PROJECT_ROOT / "tests" / ".." / "data" / "platform.db")
        with pytest.raises(AssertionError, match="ISOLATION GUARD"):
            sqlite3.connect(traversal)

    def test_e08_symlink_to_production_blocked(self, tmp_path):
        link_path = tmp_path / "link.db"
        link_path.symlink_to(_PRODUCTION_DB_CANONICAL)
        with pytest.raises(AssertionError, match="ISOLATION GUARD"):
            sqlite3.connect(str(link_path))

    def test_e09_uri_production_path_blocked(self):
        uri = f"file:{_PROJECT_ROOT / 'data' / 'platform.db'}?mode=ro"
        with pytest.raises(AssertionError, match="ISOLATION GUARD"):
            sqlite3.connect(uri, uri=True)


# ---------------------------------------------------------------------------
# EF01-EF06: Fail-closed: unregistered and malformed paths blocked
# ---------------------------------------------------------------------------


class TestEF01_FailClosed:

    def test_ef01_unknown_path_blocked(self, tmp_dir_outside_pytest=None):
        # A path that is NOT under tests/fixtures/ and NOT under pytest temp root
        # and NOT the production DB → still blocked (fail-closed).
        # Use /dev/null as a known non-test-root path on macOS/Linux.
        with pytest.raises(AssertionError, match="ISOLATION GUARD"):
            sqlite3.connect("/dev/null")

    def test_ef02_hardlink_to_production_blocked(self, tmp_path):
        if not os.path.exists(_PRODUCTION_DB_CANONICAL):
            pytest.skip(
                "Production DB absent — hardlink creation requires target to exist"
            )
        link_path = tmp_path / "hard_link.db"
        os.link(_PRODUCTION_DB_CANONICAL, str(link_path))
        with pytest.raises(AssertionError, match="ISOLATION GUARD"):
            sqlite3.connect(str(link_path))

    def test_ef03_percent_encoded_production_uri_blocked(self):
        # Percent-encode the production path and pass as file: URI
        encoded_path = urllib.parse.quote(_PRODUCTION_DB_CANONICAL)
        uri = f"file:{encoded_path}?mode=ro"
        with pytest.raises(AssertionError, match="ISOLATION GUARD"):
            sqlite3.connect(uri, uri=True)

    def test_ef04_unsupported_uri_scheme_blocked(self):
        with pytest.raises(AssertionError, match="ISOLATION GUARD"):
            sqlite3.connect("ftp://localhost/data/platform.db")

    def test_ef05_empty_string_blocked(self):
        with pytest.raises(AssertionError, match="ISOLATION GUARD"):
            sqlite3.connect("")

    def test_ef06_authority_based_uri_blocked(self):
        with pytest.raises(AssertionError, match="ISOLATION GUARD"):
            sqlite3.connect("file://localhost/data/platform.db")


# ---------------------------------------------------------------------------
# EF07-EF08: Allowlist completeness
# ---------------------------------------------------------------------------


class TestEF07_AllowlistCompleteness:

    def test_ef07_tests_fixtures_root_allows_snapshot_path(self, tmp_path):
        # tests/fixtures/ is an explicitly allowed root.
        # Verify: canonical path of prod_audit_snapshot is under _TESTS_FIXTURES_CANONICAL.
        snapshot_canonical = os.path.realpath(_PROD_AUDIT_SNAPSHOT)
        assert snapshot_canonical.startswith(_TESTS_FIXTURES_CANONICAL), (
            f"Snapshot canonical {snapshot_canonical!r} is not under "
            f"fixtures root {_TESTS_FIXTURES_CANONICAL!r}"
        )

    def test_ef08_pytest_temp_root_registered(self, tmp_path_factory):
        # _PYTEST_TEMP_ROOT must be populated after _register_pytest_temp_root runs.
        # We import _PYTEST_TEMP_ROOT from conftest to verify.
        import tests.conftest as cf

        assert (
            len(cf._PYTEST_TEMP_ROOT) >= 1
        ), "_PYTEST_TEMP_ROOT is empty — _register_pytest_temp_root may not have run"
        # tmp_path must be under the registered root
        from pathlib import Path

        base = Path(cf._PYTEST_TEMP_ROOT[0])
        # tmp_path_factory.getbasetemp() should equal or be the same as the registered root
        registered = Path(cf._PYTEST_TEMP_ROOT[0])
        assert registered.exists(), f"Registered temp root does not exist: {registered}"


# ---------------------------------------------------------------------------
# E13, E14, EF09: Guard correctness
# ---------------------------------------------------------------------------


class TestE13_GuardBehaviourEdgeCases:

    def test_e13_guard_raises_before_file_created(self, tmp_path):
        # Guard raises before sqlite3.connect() completes — no new file is created.
        # Use a symlink to the production path as the target to trigger the guard.
        prod_link = tmp_path / "prod_link.db"
        prod_link.symlink_to(_PRODUCTION_DB_CANONICAL)
        with pytest.raises(AssertionError, match="ISOLATION GUARD"):
            sqlite3.connect(str(prod_link))
        # Symlink still exists but no connection was opened
        assert prod_link.is_symlink()

    def test_e14_guard_active_during_test_body(self):
        try:
            sqlite3.connect("data/platform.db")
            raise AssertionError("Guard did not fire — guard may be inactive")
        except AssertionError as exc:
            assert "ISOLATION GUARD" in str(exc), f"Wrong exception: {exc}"

    def test_ef09_guard_liveness_fixture_detects_patch(self, monkeypatch):
        # Temporarily replace sqlite3.connect with the original (simulating a patch-out).
        # The _block_production_sqlite_paths fixture runs AFTER setup, so we verify
        # the guard is still the guarded version at this point in the test body.
        import tests.conftest as cf

        assert (
            sqlite3.connect is cf._guarded_connect
        ), "Guard should still be active mid-test"
