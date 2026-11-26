"""
S78C.6B.4 Coverage compatibility tests (CV01-CV12).

Verifies that the fail-closed isolation guard is compatible with
pytest-cov / coverage 7.x SQLite lifecycle after the Option A repair:

  - pyproject.toml: data_file = ".ci_cov_data/.coverage"
  - conftest.py:    _COVERAGE_DATA_DIR pre-registered at import time

Allowed-path tests (guard must NOT block):
  CV01: _COVERAGE_DATA_DIR safety properties verified
  CV02: coverage per-process file (.coverage.hostname.pid.xxx) allowed
  CV03: coverage hash-renamed file (.coverage.xxx.Hhashhash) allowed
  CV04: coverage combine file (.coverage.xxx.combine) allowed
  CV05: import-time registration persists through fixture lifecycle
  CV08: .coverage-named file in tmp_path allowed (path-based, not filename-based)
  CV11: hardlink to synthetic coverage file from tmp_path allowed (not production)

Production-block tests (guard MUST block):
  CV06: symlink inside _COVERAGE_DATA_DIR escaping to production path blocked
  CV07: fake .coverage file at repo root (outside _COVERAGE_DATA_DIR) blocked
  CV09: production DB canonical path still blocked
  CV10: unknown path (/dev/null) still blocked

Lifecycle and safety tests:
  CV12: guard liveness + _COVERAGE_DATA_DIR isolation invariants

All tests use synthetic paths or pytest tmp_path only.
No production database access.  OPEN_ISOLATION_GAP: test_comparison_framework_session39
RR-10 manual sqlite3.connect reassignment; not executed in this test file.
"""

from __future__ import annotations

import os
import sqlite3
import urllib.parse
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Module-level constants derived from conftest internals
# ---------------------------------------------------------------------------

import tests.conftest as _cf

_COV_DIR = _cf._COVERAGE_DATA_DIR
_REPO_ROOT = _cf._REPO_ROOT
_PROD_CANONICAL = _cf._PRODUCTION_DB_CANONICAL
_FIXTURES_CANONICAL = _cf._TESTS_FIXTURES_CANONICAL


# ---------------------------------------------------------------------------
# CV01-CV05, CV08: Allowed-path and registration tests
# ---------------------------------------------------------------------------


class TestCoverageDirectoryRegistration:

    def test_cv01_coverage_dir_safety_properties(self):
        """_COVERAGE_DATA_DIR is a real, unambiguous, pre-registered directory."""
        # Must exist as a real directory, not a symlink
        assert os.path.isdir(_COV_DIR), f"Not a directory: {_COV_DIR!r}"
        assert not os.path.islink(_COV_DIR), f"Must not be a symlink: {_COV_DIR!r}"
        # Must be exactly {repo_root}/.ci_cov_data
        assert os.path.dirname(_COV_DIR) == _REPO_ROOT
        assert os.path.basename(_COV_DIR) == ".ci_cov_data"
        # Must be pre-registered in _PYTEST_TEMP_ROOT at import time
        assert _COV_DIR in _cf._PYTEST_TEMP_ROOT, (
            f"_COVERAGE_DATA_DIR not in _PYTEST_TEMP_ROOT: {_cf._PYTEST_TEMP_ROOT!r}"
        )
        # Must not collide with protected paths
        assert _COV_DIR != _REPO_ROOT
        assert _COV_DIR != _FIXTURES_CANONICAL
        assert _COV_DIR != os.path.dirname(_PROD_CANONICAL)
        assert not _COV_DIR == _PROD_CANONICAL

    def test_cv02_coverage_per_process_file_allowed(self, tmp_path):
        """Per-process coverage file (.coverage.hostname.pid.xxx) is allowed."""
        artifact = Path(_COV_DIR) / ".coverage.linux-x86_64-cpython-313.host.12345.cv02"
        try:
            conn = sqlite3.connect(str(artifact))
            conn.close()
        finally:
            # Remove so coverage combine does not find this synthetic file.
            artifact.unlink(missing_ok=True)

    def test_cv03_coverage_hash_renamed_file_allowed(self, tmp_path):
        """Hash-renamed coverage file (.coverage.xxx.Habc123h) is allowed."""
        artifact = Path(_COV_DIR) / ".coverage.linux.12345.cv03.Habc123def456h"
        try:
            conn = sqlite3.connect(str(artifact))
            conn.close()
        finally:
            artifact.unlink(missing_ok=True)

    def test_cv04_coverage_combine_file_allowed(self, tmp_path):
        """Coverage combine file (.coverage.xxx.combine) is allowed."""
        artifact = Path(_COV_DIR) / ".coverage.linux.12345.cv04.combine"
        try:
            conn = sqlite3.connect(str(artifact))
            conn.close()
        finally:
            artifact.unlink(missing_ok=True)

    def test_cv05_import_time_registration_persists(self):
        """_COVERAGE_DATA_DIR stays in _PYTEST_TEMP_ROOT during test body.

        Import-time entries are not removed by session-scoped fixture teardown
        (which only removes pytest's temp root entry).  This confirms coverage's
        Central.finish() can still reach the dir after fixture teardown.
        """
        # Entry was present at module import (CV01 verified); must still be present now.
        assert _COV_DIR in _cf._PYTEST_TEMP_ROOT, (
            "_COVERAGE_DATA_DIR was removed from _PYTEST_TEMP_ROOT prematurely — "
            "coverage teardown would be blocked."
        )
        # Also confirm entry count: at minimum 1 (cov dir) + 1 (pytest temp root) = 2
        # (pytest temp root is registered by _register_pytest_temp_root autouse fixture)
        assert len(_cf._PYTEST_TEMP_ROOT) >= 2, (
            f"Expected ≥2 entries in _PYTEST_TEMP_ROOT, got {_cf._PYTEST_TEMP_ROOT!r}"
        )

    def test_cv08_coverage_filename_in_tmp_path_allowed(self, tmp_path):
        """A .coverage-named file in tmp_path is allowed (guard is path-based, not filename-based)."""
        # Guard must NOT use .coverage* filename as a global exemption.
        # A file named .coverage.fake in pytest's tmp_path must still be allowed
        # because tmp_path is under _PYTEST_TEMP_ROOT — not because of the filename.
        fake_cov = tmp_path / ".coverage.fake_cv08"
        conn = sqlite3.connect(str(fake_cov))
        conn.execute("CREATE TABLE IF NOT EXISTS t (x INTEGER)")
        conn.close()


# ---------------------------------------------------------------------------
# CV06-CV07, CV09-CV10: Block tests
# ---------------------------------------------------------------------------


class TestCoverageDirectoryBlockers:

    def test_cv06_symlink_escape_from_cov_dir_blocked(self):
        """Symlink inside _COVERAGE_DATA_DIR targeting production path is blocked."""
        link_path = Path(_COV_DIR) / "escape_test_cv06.db"
        try:
            link_path.symlink_to(_PROD_CANONICAL)
            # realpath follows the symlink → resolves to _PROD_CANONICAL → BLOCKED
            with pytest.raises(AssertionError, match="ISOLATION GUARD"):
                sqlite3.connect(str(link_path))
        finally:
            if link_path.is_symlink():
                link_path.unlink()

    def test_cv07_fake_coverage_at_repo_root_blocked(self):
        """A .coverage* file at the repo root (outside _COVERAGE_DATA_DIR) is blocked."""
        # This is the OLD default coverage location that the guard now blocks.
        # Path resolves to {repo_root}/.coverage.fake_cv07 — NOT under .ci_cov_data/.
        fake_root_cov = str(Path(_REPO_ROOT) / ".coverage.fake_cv07")
        with pytest.raises(AssertionError, match="ISOLATION GUARD"):
            sqlite3.connect(fake_root_cov)

    def test_cv09_production_db_still_blocked(self):
        """Production DB canonical path is still blocked after Option A change."""
        with pytest.raises(AssertionError, match="ISOLATION GUARD"):
            sqlite3.connect(_PROD_CANONICAL)

    def test_cv10_unknown_path_still_blocked(self):
        """Unknown path outside all allowed roots is still blocked (fail-closed)."""
        with pytest.raises(AssertionError, match="ISOLATION GUARD"):
            sqlite3.connect("/dev/null")


# ---------------------------------------------------------------------------
# CV11: Hardlink with synthetic file
# ---------------------------------------------------------------------------


class TestHardlinkSynthetic:

    def test_cv11_hardlink_to_synthetic_cov_file_allowed(self, tmp_path):
        """Hardlink to synthetic coverage file is correctly allowed.

        The hardlink check compares inodes against _PRODUCTION_DB_CANONICAL only.
        A hardlink to a synthetic file in tmp_path (not an alias to production DB)
        must not be false-positively blocked.
        """
        # Create synthetic source file in _COVERAGE_DATA_DIR (allowed)
        synthetic = Path(_COV_DIR) / "synthetic_cv11.db"
        src_conn = sqlite3.connect(str(synthetic))
        src_conn.execute("CREATE TABLE IF NOT EXISTS t (x INTEGER)")
        src_conn.close()

        # Create hardlink from tmp_path to the synthetic file
        hardlink = tmp_path / "hardlink_cv11.db"
        try:
            os.link(str(synthetic), str(hardlink))
        except OSError as exc:
            pytest.skip(f"Hardlink creation failed (cross-filesystem?): {exc}")

        # Hardlink is in tmp_path → under _PYTEST_TEMP_ROOT → allowed
        # Hardlink check only compares against _PRODUCTION_DB_CANONICAL inode,
        # which either doesn't exist or has a different inode → no false positive
        conn = sqlite3.connect(str(hardlink))
        conn.close()


# ---------------------------------------------------------------------------
# CV12: Guard lifecycle and isolation invariants
# ---------------------------------------------------------------------------


class TestGuardLifecycle:

    def test_cv12_guard_liveness_and_cov_dir_isolation(self):
        """Guard is active; _COVERAGE_DATA_DIR is properly isolated from protected paths."""
        # Guard liveness
        assert sqlite3.connect is _cf._guarded_connect, (
            "sqlite3.connect no longer points to _guarded_connect — guard may be inactive."
        )
        # _COVERAGE_DATA_DIR is not a prefix of any protected path
        assert not _cf._is_under(_PROD_CANONICAL, _COV_DIR), (
            "Production DB is under _COVERAGE_DATA_DIR — isolation broken."
        )
        assert not _cf._is_under(_FIXTURES_CANONICAL, _COV_DIR), (
            "tests/fixtures is under _COVERAGE_DATA_DIR — isolation broken."
        )
        # _COVERAGE_DATA_DIR is not under production DB parent directory
        assert not _cf._is_under(_COV_DIR, os.path.dirname(_PROD_CANONICAL)), (
            "_COVERAGE_DATA_DIR is under data/ — would allow production DB parent."
        )
        # _COVERAGE_DATA_DIR is a direct child of _REPO_ROOT (one level only)
        assert Path(_COV_DIR).parent == Path(_REPO_ROOT)


# ---------------------------------------------------------------------------
# CU01-CU12: SQLite URI compatibility (file:/// support for coverage combine)
# ---------------------------------------------------------------------------


class TestCoverageURICompatibility:
    """S78C.6B.5 — file:/// URI support for coverage's combine step.

    Coverage's sqlitedb.py calls sqlite3.connect(filename, check_same_thread=False, uri=True)
    where filename is file:///.../.ci_cov_data/.coverage.<suffix>?mode=ro&immutable=1.
    These tests verify the guard correctly handles this case.
    """

    def test_cu01_github_actions_exact_uri_format_allowed(self):
        """GitHub Actions exact URI format (file:///path?mode=ro&immutable=1) to .ci_cov_data is allowed."""
        artifact = Path(_COV_DIR) / ".coverage.linux.12345.cu01"
        try:
            conn_create = sqlite3.connect(str(artifact))
            conn_create.close()
            uri = f"file://{artifact}?mode=ro&immutable=1"
            conn = sqlite3.connect(uri, check_same_thread=False, uri=True)
            conn.close()
        finally:
            artifact.unlink(missing_ok=True)

    def test_cu02_uri_mode_ro_alone_allowed(self):
        """file:/// URI with mode=ro only (no immutable) is allowed.

        Matches the actual GitHub CI URI format used by coverage 7.17+ check_hot_journal():
            file:///.../.ci_cov_data/.coverage?mode=ro
        immutable is optional; mode=ro alone is sufficient.
        """
        artifact = Path(_COV_DIR) / ".coverage.cu02"
        try:
            conn_create = sqlite3.connect(str(artifact))
            conn_create.close()
            uri = f"file://{artifact}?mode=ro"
            conn = sqlite3.connect(uri, uri=True)
            conn.close()
        finally:
            artifact.unlink(missing_ok=True)

    def test_cu03_uri_to_production_db_blocked(self):
        """file:/// URI pointing to production DB is blocked (production deny priority preserved)."""
        uri = f"file://{_PROD_CANONICAL}?mode=ro&immutable=1"
        with pytest.raises(AssertionError, match="ISOLATION GUARD"):
            sqlite3.connect(uri, uri=True)

    def test_cu04_non_empty_authority_blocked(self):
        """file://host/path with non-empty authority is blocked even with uri=True."""
        with pytest.raises(AssertionError, match="authority-based URI not supported"):
            sqlite3.connect("file://somehost/tmp/test.db", uri=True)

    def test_cu05_uri_outside_allowed_roots_blocked(self):
        """file:/// URI to path outside all allowed roots is blocked (fail-closed)."""
        with pytest.raises(AssertionError, match="ISOLATION GUARD"):
            sqlite3.connect("file:///tmp/unauthorized_cu05.db?mode=ro&immutable=1", uri=True)

    def test_cu06_file_uri_without_uri_true_blocked(self):
        """file:// URI string passed without uri=True kwarg is blocked."""
        artifact = Path(_COV_DIR) / ".coverage.cu06"
        uri = f"file://{artifact}"
        with pytest.raises(AssertionError, match="ISOLATION GUARD"):
            sqlite3.connect(uri)  # uri=True not set → guard blocks

    def test_cu07_uri_unknown_query_param_blocked(self):
        """file:/// URI with unknown query parameter (cache=shared) is blocked."""
        artifact = Path(_COV_DIR) / ".coverage.cu07"
        uri = f"file://{artifact}?cache=shared"
        with pytest.raises(AssertionError, match="unauthorized URI query parameters"):
            sqlite3.connect(uri, uri=True)

    def test_cu08_uri_duplicate_query_param_blocked(self):
        """file:/// URI with duplicate query parameter (mode=ro&mode=rw) is blocked."""
        artifact = Path(_COV_DIR) / ".coverage.cu08"
        uri = f"file://{artifact}?mode=ro&mode=rw"
        with pytest.raises(AssertionError, match="duplicate URI query parameter"):
            sqlite3.connect(uri, uri=True)

    def test_cu09_uri_symlink_escape_blocked(self):
        """Symlink inside .ci_cov_data via file:/// URI pointing to production path is blocked."""
        link = Path(_COV_DIR) / "escape_cu09.db"
        try:
            link.symlink_to(_PROD_CANONICAL)
            uri = f"file://{link}?mode=ro&immutable=1"
            with pytest.raises(AssertionError, match="ISOLATION GUARD"):
                sqlite3.connect(uri, uri=True)
        finally:
            if link.is_symlink():
                link.unlink()

    def test_cu10_uri_path_traversal_blocked(self):
        """Path traversal in file:/// URI is resolved and blocked."""
        traversal = f"file://{_COV_DIR}/../../../etc/passwd?mode=ro&immutable=1"
        with pytest.raises(AssertionError, match="ISOLATION GUARD"):
            sqlite3.connect(traversal, uri=True)

    def test_cu11_uri_percent_encoded_prod_path_blocked(self):
        """Percent-encoded production DB path in file:/// URI is decoded and blocked.

        Encodes the filename (platform%2Edb) to verify the guard decodes before checking.
        """
        prod_dir, prod_file = _PROD_CANONICAL.rsplit("/", 1)
        encoded_file = urllib.parse.quote(prod_file, safe="")  # platform.db → platform%2Edb
        uri = f"file://{prod_dir}/{encoded_file}?mode=ro"
        with pytest.raises(AssertionError, match="ISOLATION GUARD"):
            sqlite3.connect(uri, uri=True)

    def test_cu12_uri_no_query_params_blocked(self):
        """file:/// URI without query params is blocked (empty query is unverified format)."""
        artifact = Path(_COV_DIR) / ".coverage.cu12"
        uri = f"file://{artifact}"
        with pytest.raises(AssertionError, match="ISOLATION GUARD"):
            sqlite3.connect(uri, uri=True)

    def test_cu13_uri_mode_rw_blocked(self):
        """mode=rw is not a CI-verified value and is blocked."""
        artifact = Path(_COV_DIR) / ".coverage.cu13"
        uri = f"file://{artifact}?mode=rw&immutable=1"
        with pytest.raises(AssertionError, match="unauthorized URI mode"):
            sqlite3.connect(uri, uri=True)

    def test_cu14_uri_mode_rwc_blocked(self):
        """mode=rwc is not a CI-verified value and is blocked."""
        artifact = Path(_COV_DIR) / ".coverage.cu14"
        uri = f"file://{artifact}?mode=rwc&immutable=1"
        with pytest.raises(AssertionError, match="unauthorized URI mode"):
            sqlite3.connect(uri, uri=True)

    def test_cu15_uri_immutable_zero_blocked(self):
        """immutable=0 is not a CI-verified value and is blocked."""
        artifact = Path(_COV_DIR) / ".coverage.cu15"
        uri = f"file://{artifact}?mode=ro&immutable=0"
        with pytest.raises(AssertionError, match="unauthorized URI immutable"):
            sqlite3.connect(uri, uri=True)

    def test_cu16_uri_fragment_blocked(self):
        """URI fragment (#) is not supported and is blocked."""
        artifact = Path(_COV_DIR) / ".coverage.cu16"
        uri = f"file://{artifact}?mode=ro&immutable=1#section"
        with pytest.raises(AssertionError, match="ISOLATION GUARD"):
            sqlite3.connect(uri, uri=True)

    def test_cu17_uri_outside_cov_dir_blocked(self):
        """file:/// URI to path outside .ci_cov_data is blocked (B1 scope restriction).

        Even a path that would otherwise be in _PYTEST_TEMP_ROOT is blocked
        when accessed via URI, since URIs are exclusively for .ci_cov_data.
        """
        repo_root_db = f"{_REPO_ROOT}/test_cu17_check.db"
        uri = f"file://{repo_root_db}?mode=ro&immutable=1"
        with pytest.raises(AssertionError, match="ISOLATION GUARD"):
            sqlite3.connect(uri, uri=True)

    def test_cu18_uri_immutable_only_blocked(self):
        """file:/// URI with immutable=1 only (missing mode=ro) is blocked (strict contract)."""
        artifact = Path(_COV_DIR) / ".coverage.cu18"
        try:
            conn_create = sqlite3.connect(str(artifact))
            conn_create.close()
            uri = f"file://{artifact}?immutable=1"
            with pytest.raises(AssertionError, match="missing required URI query parameter 'mode'"):
                sqlite3.connect(uri, uri=True)
        finally:
            artifact.unlink(missing_ok=True)

    def test_cu19_uri_reversed_param_order_allowed(self):
        """file:/// URI with parameters in reversed order (immutable=1&mode=ro) is allowed."""
        artifact = Path(_COV_DIR) / ".coverage.linux.12345.cu19"
        try:
            conn_create = sqlite3.connect(str(artifact))
            conn_create.close()
            uri = f"file://{artifact}?immutable=1&mode=ro"
            conn = sqlite3.connect(uri, check_same_thread=False, uri=True)
            conn.close()
        finally:
            artifact.unlink(missing_ok=True)

    def test_cu20_real_coverage_artifact_uri_compatibility(self):
        """Real Coverage artifact (CoverageData API); guard allows check_hot_journal URI pattern.

        Uses coverage.data.CoverageData to create a genuine SQLite artifact, then
        verifies the guard allows file://...?mode=ro (coverage 7.17+ check_hot_journal format)
        and file://...?mode=ro&immutable=1 (older combine format).

        CI_PARITY_NOTE: check_hot_journal() exists in coverage >=7.17 (CI version ~7.17.5).
        Local coverage 7.15.0 does not have this function; the URI pattern is reproduced
        synthetically here, since the actual function call cannot be executed locally.
        CHECK_HOT_JOURNAL_CI_PARITY_UNVERIFIED.
        """
        import shutil

        import coverage as cov_pkg  # noqa: F401
        from coverage.data import CoverageData

        test_subdir = Path(_COV_DIR) / "test_cu20"
        test_subdir.mkdir(exist_ok=True)
        cov_file = str(test_subdir / ".coverage")

        try:
            # Step 1: Create a real Coverage SQLite artifact via public API.
            data = CoverageData(basename=cov_file)
            data.add_lines({"cu20_placeholder.py": {1: None, 2: None}})
            data.write()
            assert os.path.isfile(cov_file), "CoverageData.write() did not create artifact"

            # Step 2: Simulate coverage 7.17+ check_hot_journal() URI call.
            # check_hot_journal opens main .coverage read-only to detect stale journals.
            uri_ro = f"file://{cov_file}?mode=ro"
            conn = sqlite3.connect(uri_ro, check_same_thread=False, uri=True)
            conn.close()

            # Step 3: Verify mode=ro&immutable=1 (older combine step) still allowed.
            uri_both = f"file://{cov_file}?mode=ro&immutable=1"
            conn2 = sqlite3.connect(uri_both, check_same_thread=False, uri=True)
            conn2.close()

            # Step 4: Guard still active after real coverage artifact operations.
            assert sqlite3.connect is _cf._guarded_connect, "Guard deactivated during CU20"
        finally:
            shutil.rmtree(test_subdir, ignore_errors=True)

    def test_cu21_coverage_combine_guard_compatibility(self):
        """Coverage.combine() runs without guard interference.

        Creates per-process coverage files via CoverageData API, then calls
        Coverage.combine() to verify the guard allows all combine-step SQLite access.
        Guard must remain active throughout.
        """
        import shutil

        import coverage as cov_pkg
        from coverage.data import CoverageData

        test_subdir = Path(_COV_DIR) / "test_cu21"
        test_subdir.mkdir(exist_ok=True)
        main_cov_file = str(test_subdir / ".coverage")

        try:
            # Create two per-process coverage data files via real Coverage API.
            for i in range(2):
                proc_file = str(test_subdir / f".coverage.host.{10000 + i}.cu21")
                data = CoverageData(basename=proc_file)
                data.add_lines({f"cu21_module{i}.py": {j + 1: None for j in range(3)}})
                data.write()

            # Run Coverage.combine() — guard must not block combine-step SQLite access.
            cov = cov_pkg.Coverage(data_file=main_cov_file, config_file=False)
            cov.combine(data_paths=[str(test_subdir)], strict=False)

            assert os.path.isfile(main_cov_file), "Coverage.combine() did not produce output"
            assert sqlite3.connect is _cf._guarded_connect, "Guard deactivated during CU21"
        finally:
            shutil.rmtree(test_subdir, ignore_errors=True)
