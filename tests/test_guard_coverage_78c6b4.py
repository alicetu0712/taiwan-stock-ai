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
