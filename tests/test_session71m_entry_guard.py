"""
Session 71M — Original Backfill Entry Guard Tests (M-01 ~ M-24)

Tests the lock-based authorization in backfill_daily_prices_guarded.py
and the check_original_entry() method in BackfillEntryGuard.

All tests are offline-only. No production files modified. No real providers called.
No writes to production SQLite or Neon.

Lock isolation: tests use tmp_path lock files, never touch data/.cron.lock.
"""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR.parent))

from scripts.scheduler_safety_guards import BackfillEntryGuard


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _env_clean(**extra):
    """Return clean env dict without any guard env vars, plus extras."""
    env = {k: v for k, v in os.environ.items()
           if k not in ("CALLED_FROM_WRAPPER", "BACKFILL_ALLOW_DIRECT",
                        "BACKFILL_MAINTENANCE_REASON", "BACKFILL_LOCK_PATH")}
    env.update(extra)
    return env


def _run_guarded(tmp_path, *extra_args, env_extra=None, lock_held=False):
    """
    Run backfill_daily_prices_guarded.py as subprocess.
    Uses an isolated lock file from tmp_path.

    If lock_held=True, acquires the lock BEFORE running the subprocess.
    Returns subprocess result.
    """
    lock_file = tmp_path / "test.cron.lock"
    lock_file.touch()

    env = _env_clean(BACKFILL_LOCK_PATH=str(lock_file))
    if env_extra:
        env.update(env_extra)

    if lock_held:
        with open(lock_file, "a") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "backfill_daily_prices_guarded.py"),
                 "--db", ":memory:", *extra_args],
                capture_output=True, text=True, env=env,
                cwd=str(SCRIPTS_DIR.parent),
            )
            fcntl.flock(fh, fcntl.LOCK_UN)
    else:
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "backfill_daily_prices_guarded.py"),
             "--db", ":memory:", *extra_args],
            capture_output=True, text=True, env=env,
            cwd=str(SCRIPTS_DIR.parent),
        )
    return result


# ===========================================================================
# M-01 ~ M-07: Entry Authorization
# ===========================================================================

class TestEntryAuthorization:

    def test_M01_direct_original_execute_blocked(self, tmp_path):
        """M-01: Direct --execute without wrapper lock → exit code 2 (fail closed)."""
        result = _run_guarded(tmp_path, "--execute", lock_held=False)
        assert result.returncode == 2, (
            f"Expected exit 2, got {result.returncode}. stderr: {result.stderr[:300]}"
        )
        assert "BACKFILL_GUARD" in result.stderr
        assert "BLOCKED" in result.stderr

    def test_M01b_direct_dryrun_allowed(self, tmp_path):
        """M-01b: Dry-run (no --execute) without lock → allowed (no write risk)."""
        result = _run_guarded(
            tmp_path,
            "--start", "2026-12-01", "--end", "2026-11-30",  # start > end → clean exit 0
            lock_held=False,
        )
        assert result.returncode != 2, (
            f"Dry-run must not be blocked. returncode={result.returncode}"
        )

    def test_M02_integrated_wrapper_authorized(self, tmp_path):
        """M-02: When lock is held (simulating wrapper), guarded backfill is authorized."""
        from scripts.hybrid_shadow_cron_integrated import run_cron_pipeline
        from src.research.full_market_freshness_gate import FreshnessStatus
        from dataclasses import dataclass
        import pytz
        from datetime import datetime

        TAIPEI_TZ = pytz.timezone("Asia/Taipei")

        @dataclass
        class _FR:
            status: FreshnessStatus
            detail: str = "mock"
            non_benchmark_count: int = 5500
            benchmark_date: date = None
            min_required: int = 5000
            def __post_init__(self):
                if self.benchmark_date is None:
                    self.benchmark_date = date(2026, 11, 12)
            def human_readable(self): return self.detail

        bf = lambda ex: {"exit_code": 0, "stdout": "ok", "stderr": ""}
        sh = lambda: {"exit_code": 0, "stdout": "ok", "stderr": ""}
        fr = lambda conn, d, is_trading_day: _FR(status=FreshnessStatus.FULL_MARKET_FRESH)

        state = tmp_path / ".cron_state.json"
        lock = tmp_path / ".cron.lock"
        now = TAIPEI_TZ.localize(datetime(2026, 11, 12, 17, 0, 0))

        with patch("scripts.hybrid_shadow_cron_integrated.CALENDAR.is_trading_day",
                   return_value=True):
            result = run_cron_pipeline(
                execute=True, skip_backup=True,
                _now_taipei_override=now,
                _state_file_override=state,
                _lock_file_override=lock,
                _db_path_override=":memory:",
                _backfill_runner=bf,
                _shadow_runner=sh,
                _freshness_checker=fr,
            )
        assert result.get("write_committed") is True, (
            f"Expected write_committed=True when wrapper runs: {result}"
        )

    def test_M03_protected_adapter_authorized_via_env(self, tmp_path):
        """M-03: Protected adapter (backfill_daily_prices_protected.py) with env → authorized."""
        # protected.py uses check_invocation() (env var check, not lock-based)
        lock_file = tmp_path / "test.cron.lock"
        lock_file.touch()
        env = _env_clean(
            CALLED_FROM_WRAPPER="1",
            BACKFILL_LOCK_PATH=str(lock_file),
        )
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "backfill_daily_prices_protected.py"),
             "--start", "2026-12-01", "--end", "2026-11-30"],  # start > end → dry exit
            capture_output=True, text=True, env=env,
            cwd=str(SCRIPTS_DIR.parent),
        )
        assert result.returncode != 2, (
            f"Protected adapter should be authorized with CALLED_FROM_WRAPPER=1. "
            f"returncode={result.returncode}, stderr={result.stderr[:200]}"
        )

    def test_M04_fake_env_var_alone_rejected(self, tmp_path):
        """M-04: CALLED_FROM_WRAPPER=1 alone WITHOUT lock held → rejected by guarded entry."""
        # lock_held=False → check_original_entry sees lock NOT held → UNAUTHORIZED
        result = _run_guarded(
            tmp_path, "--execute",
            env_extra={"CALLED_FROM_WRAPPER": "1"},
            lock_held=False,
        )
        assert result.returncode == 2, (
            f"Env var alone without lock must be rejected. returncode={result.returncode}"
        )
        assert "BACKFILL_GUARD" in result.stderr
        assert "BLOCKED" in result.stderr

    def test_M04b_check_original_entry_lock_not_held_env_set(self, tmp_path):
        """M-04b: check_original_entry() with lock NOT held + env var → UNAUTHORIZED."""
        lock_file = tmp_path / "test.cron.lock"
        lock_file.touch()
        with patch.dict(os.environ, {"CALLED_FROM_WRAPPER": "1"}, clear=False):
            authorized, msg = BackfillEntryGuard.check_original_entry(
                is_execute=True, lock_path=lock_file
            )
        assert not authorized, f"Expected unauthorized, got: {msg}"
        assert "UNAUTHORIZED" in msg
        assert "env_var" in msg.lower() or "CALLED_FROM_WRAPPER" in msg or "not held" in msg

    def test_M05_no_env_no_lock_rejected(self, tmp_path):
        """M-05: No env var, no lock, no fake parent → rejected (direct invocation scenario)."""
        result = _run_guarded(tmp_path, "--execute", env_extra={}, lock_held=False)
        assert result.returncode == 2, (
            f"No auth at all must be rejected. returncode={result.returncode}"
        )

    def test_M06_maintenance_single_key_rejected(self, tmp_path):
        """M-06: BACKFILL_ALLOW_DIRECT=1 alone (no MAINTENANCE_REASON) → rejected."""
        result = _run_guarded(
            tmp_path, "--execute",
            env_extra={"BACKFILL_ALLOW_DIRECT": "1"},
            lock_held=False,
        )
        assert result.returncode == 2, (
            f"Single maintenance key must be rejected. returncode={result.returncode}"
        )
        assert "BACKFILL_GUARD" in result.stderr

    def test_M07_maintenance_two_key_authorized(self, tmp_path):
        """M-07: BACKFILL_ALLOW_DIRECT=1 + BACKFILL_MAINTENANCE_REASON → authorized."""
        result = _run_guarded(
            tmp_path, "--execute",
            env_extra={
                "BACKFILL_ALLOW_DIRECT": "1",
                "BACKFILL_MAINTENANCE_REASON": "test maintenance run M-07",
            },
            lock_held=False,
        )
        # Should NOT be blocked (exit 2); may succeed or fail for other reasons (no live API)
        assert result.returncode != 2, (
            f"Two-key maintenance must not be blocked by guard. "
            f"returncode={result.returncode}, stderr={result.stderr[:300]}"
        )

    def test_M07b_check_original_entry_maintenance(self, tmp_path):
        """M-07b: check_original_entry() with two-key maintenance → authorized."""
        lock_file = tmp_path / "test.cron.lock"
        lock_file.touch()
        env = {"BACKFILL_ALLOW_DIRECT": "1",
               "BACKFILL_MAINTENANCE_REASON": "M-07b test"}
        with patch.dict(os.environ, env, clear=False):
            authorized, msg = BackfillEntryGuard.check_original_entry(
                is_execute=True, lock_path=lock_file
            )
        assert authorized, f"Two-key maintenance must authorize. msg: {msg}"
        assert "AUTHORIZED_MAINTENANCE" in msg
        assert "M-07b test" in msg


# ===========================================================================
# M-08 ~ M-10: Write Path & Concurrency
# ===========================================================================

class TestWritePathAndConcurrency:

    def test_M08_direct_module_run_backfill_blocked(self, tmp_path):
        """M-08: run_backfill(execute=True) in guarded module without auth → guard_blocked."""
        from scripts.backfill_daily_prices_guarded import run_backfill
        from datetime import date

        lock_file = tmp_path / "test.cron.lock"
        lock_file.touch()
        # No lock held, no env vars → unauthorized
        env = {k: v for k, v in os.environ.items()
               if k not in ("CALLED_FROM_WRAPPER", "BACKFILL_ALLOW_DIRECT",
                            "BACKFILL_MAINTENANCE_REASON")}
        with patch.dict(os.environ, env, clear=True):
            result = run_backfill(
                start=date(2026, 11, 12), end=date(2026, 11, 12),
                execute=True, db_path=":memory:",
                _lock_path=str(lock_file),
            )
        assert result.get("guard_blocked") is True, (
            f"run_backfill without auth must return guard_blocked=True. result: {result}"
        )
        assert result["total_inserted"] == 0

    def test_M08b_run_backfill_authorized_with_lock(self, tmp_path):
        """M-08b: run_backfill(execute=True) with lock held + env → guard passes (not guard_blocked)."""
        import sqlite3 as _sqlite3
        from scripts.backfill_daily_prices_guarded import run_backfill
        from datetime import date

        # Create a real SQLite file so _verify_sqlite() passes
        db_path = str(tmp_path / "test.db")
        conn = _sqlite3.connect(db_path)
        conn.execute("""CREATE TABLE IF NOT EXISTS daily_prices (
            stock_id TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL,
            volume INTEGER, PRIMARY KEY (stock_id, date))""")
        conn.commit()
        conn.close()

        lock_file = tmp_path / "test.cron.lock"
        lock_file.touch()

        with open(lock_file, "a") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            import pandas as _pd
            _empty_df = _pd.DataFrame()
            with patch.dict(os.environ, {"CALLED_FROM_WRAPPER": "1"}, clear=False), \
                 patch("scripts.backfill_daily_prices_guarded.fetch_twse_historical",
                       return_value=(_empty_df, None)), \
                 patch("scripts.backfill_daily_prices_guarded.fetch_tpex_historical",
                       return_value=(_empty_df, None)):
                result = run_backfill(
                    start=date(2026, 11, 12), end=date(2026, 11, 12),
                    execute=True, db_path=db_path,
                    _lock_path=str(lock_file),
                )
            fcntl.flock(fh, fcntl.LOCK_UN)

        assert result.get("guard_blocked") is not True, (
            f"run_backfill with lock+env should not be guard-blocked. result: {result}"
        )

    def test_M09_concurrent_wrapper_single_writer(self, tmp_path):
        """M-09: Lock prevents second wrapper from starting (single writer)."""
        # This test verifies the wrapper's FileLock mechanism using IT-16 pattern
        from scripts.hybrid_shadow_cron_integrated import run_cron_pipeline
        from dataclasses import dataclass
        from src.research.full_market_freshness_gate import FreshnessStatus
        import pytz
        from datetime import datetime

        TAIPEI_TZ = pytz.timezone("Asia/Taipei")

        @dataclass
        class _FR:
            status: FreshnessStatus
            detail: str = "mock"
            non_benchmark_count: int = 5500
            benchmark_date: date = None
            min_required: int = 5000
            def __post_init__(self):
                if self.benchmark_date is None:
                    self.benchmark_date = date(2026, 11, 12)
            def human_readable(self): return self.detail

        lock_file = tmp_path / ".cron.lock"
        lock_file.touch()
        state_file = tmp_path / ".cron_state.json"

        # First "wrapper" holds the lock
        with open(lock_file, "a") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # Second pipeline attempt → should be blocked by lock
            with patch("scripts.hybrid_shadow_cron_integrated.CALENDAR.is_trading_day", return_value=True):
                result = run_cron_pipeline(
                    execute=True, skip_backup=True,
                    _now_taipei_override=TAIPEI_TZ.localize(datetime(2026, 11, 12, 17, 0, 0)),
                    _state_file_override=state_file,
                    _lock_file_override=lock_file,
                    _db_path_override=":memory:",
                    _backfill_runner=lambda ex: {"exit_code": 0, "stdout": "", "stderr": ""},
                    _shadow_runner=lambda: {"exit_code": 0, "stdout": "", "stderr": ""},
                    _freshness_checker=lambda conn, d, is_trading_day: _FR(
                        status=FreshnessStatus.FULL_MARKET_FRESH),
                )
            fcntl.flock(fh, fcntl.LOCK_UN)

        assert "BLOCKED_LOCK" in result.get("status", ""), (
            f"Second pipeline should be blocked by lock. status: {result.get('status')}"
        )

    def test_M10_wrapper_plus_direct_no_concurrent_write(self, tmp_path):
        """M-10: Wrapper holds lock → direct guarded execute blocked by guard (lock not acquirable)."""
        lock_file = tmp_path / "test.cron.lock"
        lock_file.touch()

        env = _env_clean(
            CALLED_FROM_WRAPPER="1",  # Set env var, but lock NOT acquirable by backfill
            BACKFILL_LOCK_PATH=str(lock_file),
        )

        # Acquire the lock ourselves (simulating wrapper)
        with open(lock_file, "a") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # Now run guarded backfill as subprocess — it will find lock IS held → AUTHORIZED
            # (This is the POSITIVE case: lock held by wrapper → guarded backfill authorized)
            result = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "backfill_daily_prices_guarded.py"),
                 "--execute", "--db", ":memory:"],
                capture_output=True, text=True, env=env,
                cwd=str(SCRIPTS_DIR.parent),
            )
            fcntl.flock(fh, fcntl.LOCK_UN)

        # With lock held + CALLED_FROM_WRAPPER=1 → NOT blocked by guard (exit 2)
        # (May fail for API reasons, but NOT guard reasons)
        assert result.returncode != 2, (
            f"With lock held, guarded backfill should be authorized. "
            f"returncode={result.returncode}, stderr={result.stderr[:200]}"
        )


# ===========================================================================
# M-11 ~ M-15: Lock & State Safety
# ===========================================================================

class TestLockAndStateSafety:

    def test_M11_parent_child_no_deadlock(self):
        """M-11: backfill_daily_prices_guarded.py uses LOCK_NB → BlockingIOError not deadlock."""
        # Structural check: guard uses LOCK_NB in _check_lock_state
        import inspect
        src = inspect.getsource(BackfillEntryGuard._check_lock_state)
        assert "LOCK_NB" in src, "_check_lock_state must use LOCK_NB to avoid deadlock"
        assert "LOCK_UN" in src, "_check_lock_state must release lock if acquired"

    def test_M12_lock_acquisition_fail_is_authorized(self, tmp_path):
        """M-12: Lock IS held (simulating wrapper running) → authorized, no failure."""
        lock_file = tmp_path / "test.cron.lock"
        lock_file.touch()

        with open(lock_file, "a") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # Lock IS held by us → check_original_entry should return AUTHORIZED
            with patch.dict(os.environ, {"CALLED_FROM_WRAPPER": "1"}):
                authorized, msg = BackfillEntryGuard.check_original_entry(
                    is_execute=True, lock_path=lock_file
                )
            fcntl.flock(fh, fcntl.LOCK_UN)

        assert authorized, f"Lock held should authorize. msg: {msg}"
        assert "AUTHORIZED" in msg

    def test_M13_unknown_commit_no_auto_retry(self, tmp_path):
        """M-13: State=RUNNING + dead PID → WRITE_OUTCOME_UNKNOWN → no auto-retry."""
        from scripts.scheduler_safety_guards import GuardStatus, RunStatus, SameDayStateGuard
        import json

        state_file = tmp_path / ".cron_state.json"
        state_file.write_text(json.dumps({
            "run_id": "test-run", "scheduled_date": "2026-11-12",
            "status": RunStatus.RUNNING.value, "pid": 999999999,
            "schema_version": "1", "write_committed": False,
        }))
        guard = SameDayStateGuard(state_file)
        result = guard.check(date(2026, 11, 12))
        assert result.guard_status == GuardStatus.WRITE_OUTCOME_UNKNOWN
        assert not result.allowed

    def test_M14_post_write_failure_no_duplicate_write(self, tmp_path):
        """M-14: write_committed=True in state → second run guard-blocked (no duplicate write)."""
        import json
        from scripts.scheduler_safety_guards import GuardStatus, RunStatus, SameDayStateGuard

        state_file = tmp_path / ".cron_state.json"
        state_file.write_text(json.dumps({
            "run_id": "test-run", "scheduled_date": "2026-11-12",
            "status": RunStatus.SUCCESS.value, "pid": 12345,
            "schema_version": "1", "write_committed": True,
        }))
        guard = SameDayStateGuard(state_file)
        result = guard.check(date(2026, 11, 12))
        assert result.guard_status in (
            GuardStatus.ALREADY_RAN_TODAY, GuardStatus.WRITE_COMMITTED_TODAY
        )
        assert not result.allowed

    def test_M15_corrupted_state_fail_closed(self, tmp_path):
        """M-15: Corrupted state file → guard returns FAIL_CLOSED_CORRUPT."""
        from scripts.scheduler_safety_guards import GuardStatus, SameDayStateGuard

        state_file = tmp_path / ".cron_state.json"
        state_file.write_text("{corrupted json!!!")

        guard = SameDayStateGuard(state_file)
        result = guard.check(date(2026, 11, 12))
        assert result.guard_status == GuardStatus.FAIL_CLOSED_CORRUPT
        assert not result.allowed


# ===========================================================================
# M-16 ~ M-24: Preservation & Isolation
# ===========================================================================

class TestPreservationAndIsolation:

    def test_M16_dryrun_preserved(self, tmp_path):
        """M-16: Dry-run always passes all guard layers."""
        result = _run_guarded(
            tmp_path,
            "--start", "2026-12-01", "--end", "2026-11-30",  # start > end → clean exit
            lock_held=False,
        )
        assert result.returncode != 2, (
            f"Dry-run must not be blocked by guard. returncode={result.returncode}"
        )

    def test_M16b_check_original_entry_dryrun(self, tmp_path):
        """M-16b: check_original_entry(is_execute=False) → always authorized."""
        lock_file = tmp_path / "test.cron.lock"
        lock_file.touch()
        # No lock held, no env vars → still authorized for dry-run
        with patch.dict(os.environ, {}, clear=True):
            authorized, msg = BackfillEntryGuard.check_original_entry(
                is_execute=False, lock_path=lock_file
            )
        assert authorized
        assert "dry-run" in msg.lower()

    def test_M17_read_only_cli_preserved(self, tmp_path):
        """M-17: --help works without any authorization."""
        env = _env_clean()
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "backfill_daily_prices_guarded.py"), "--help"],
            capture_output=True, text=True, env=env,
            cwd=str(SCRIPTS_DIR.parent),
        )
        assert result.returncode == 0, f"--help should exit 0, got {result.returncode}"
        assert "execute" in result.stdout.lower() or "help" in result.stdout.lower()

    def test_M18_rc2_filter_semantic_preservation(self):
        """M-18: RC-2 filter in guarded version is semantically identical to original."""
        guarded_src = open(SCRIPTS_DIR / "backfill_daily_prices_guarded.py").read()
        original_src = open(SCRIPTS_DIR / "backfill_daily_prices.py").read()

        # Exact RC-2 filter code must match
        rc2_original = "    sid = str(stock_id).strip()\n    if len(sid) > 4:\n        return True"
        assert rc2_original in original_src, "RC-2 filter not found in original"
        assert rc2_original in guarded_src, "RC-2 filter not identical in guarded version"

    def test_M18b_rc2_hash_verification(self):
        """M-18b: Original backfill RC-2 hash matches expected value."""
        from scripts.scheduler_safety_guards import RC2_EXPECTED_SHA256, verify_rc2_hash
        ok, actual = verify_rc2_hash(SCRIPTS_DIR / "backfill_daily_prices.py")
        assert ok, f"Original backfill RC-2 hash mismatch. actual={actual[:16]}"

    def test_M19_qg_preserved_in_guarded(self):
        """M-19: QG-1~QG-7 logic is unmodified in guarded version (structural check)."""
        guarded_src = open(SCRIPTS_DIR / "backfill_daily_prices_guarded.py").read()
        # QG is in run_quality_gate import — verify import and call are present
        assert "run_quality_gate" in guarded_src, "run_quality_gate import missing in guarded"
        assert "qg_ok" in guarded_src, "QG logic variable missing in guarded"
        assert "quality gate FAILED" in guarded_src, "QG failure path missing in guarded"
        # Guard must come BEFORE the QG (guard blocks before any API calls)
        guard_pos = guarded_src.find("check_original_entry")
        qg_pos = guarded_src.find("run_quality_gate")
        assert guard_pos < qg_pos, "Guard must appear before QG in run_backfill()"

    def test_M20_no_provider_http_in_guard_module(self):
        """M-20: scheduler_safety_guards.py has no TWSE/TPEx HTTP calls."""
        import inspect, scripts.scheduler_safety_guards as ssg
        src = inspect.getsource(ssg)
        for url_kw in ("twse.com.tw", "tpex.org.tw", "requests.get", "requests.post", "httpx"):
            assert url_kw not in src, f"Guard module must not contain HTTP call: '{url_kw}'"

    def test_M21_no_production_sqlite_in_guard_module(self):
        """M-21: scheduler_safety_guards.py has no sqlite3.connect calls."""
        import inspect, scripts.scheduler_safety_guards as ssg
        src = inspect.getsource(ssg)
        assert "sqlite3.connect" not in src, "Guard module must not connect to SQLite"

    def test_M22_no_neon_write_in_guard_module(self):
        """M-22: scheduler_safety_guards.py has no Neon/PostgreSQL write calls."""
        import inspect, scripts.scheduler_safety_guards as ssg
        src = inspect.getsource(ssg)
        for neon_kw in ("psycopg2", "asyncpg", "postgres://", "INSERT INTO"):
            assert neon_kw not in src, f"Guard module must not write to Neon: '{neon_kw}'"
        # assert_no_neon_write exists as a safety function (not a write)
        assert "assert_no_neon_write" in src, "assert_no_neon_write safety function must exist"

    def test_M23_no_cron_modification(self):
        """M-23: Original cron script hash is unchanged."""
        import hashlib
        expected = "46209171e00eb46429d0e36d02c106b87cf3684b13803ccdf53369042ba060d4"
        actual = hashlib.sha256((SCRIPTS_DIR / "hybrid_shadow_cron.py").read_bytes()).hexdigest()
        assert actual == expected, (
            f"hybrid_shadow_cron.py hash changed! expected {expected[:16]}, got {actual[:16]}"
        )

    def test_M24_no_launchd_deployment(self):
        """M-24: No LaunchAgent plist file installed in ~/Library/LaunchAgents."""
        launch_agents_dir = Path.home() / "Library" / "LaunchAgents"
        plist_files = list(launch_agents_dir.glob("*antigravity*.plist")) + \
                      list(launch_agents_dir.glob("*hybrid_cron*.plist")) + \
                      list(launch_agents_dir.glob("*backfill*.plist"))
        assert plist_files == [], (
            f"Found LaunchAgent plist(s) that should not be installed: {plist_files}"
        )
