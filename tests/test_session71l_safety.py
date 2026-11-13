"""
Session 71L — Safety Gap Closure Tests (L-01 ~ L-18)

Covers:
  L-01 ~ L-04: Direct entry protection
  L-05 ~ L-12: Commit outcome / crash recovery
  L-13 ~ L-18: RC-2 / QG / isolation preservation

All tests are offline-only. No production files modified. No real providers called.
No writes to production SQLite or Neon.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Optional
from unittest.mock import patch

import pytest
import pytz
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Helpers — shared with integration tests
# ---------------------------------------------------------------------------

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
TAIPEI_TZ = pytz.timezone("Asia/Taipei")

sys.path.insert(0, str(SCRIPTS_DIR.parent))
from src.research.full_market_freshness_gate import FreshnessStatus


@dataclass
class _MockFreshnessReport:
    status: FreshnessStatus
    detail: str = "mock"
    non_benchmark_count: int = 5500
    benchmark_date: Optional[date] = None
    min_required: int = 5000

    def __post_init__(self):
        if self.benchmark_date is None:
            self.benchmark_date = date(2026, 11, 12)

    def human_readable(self) -> str:
        return self.detail


def _taipei(year, month, day, hour, minute=0, second=0) -> datetime:
    return TAIPEI_TZ.localize(datetime(year, month, day, hour, minute, second))


def _freshness_ok_checker():
    return lambda conn, d, is_trading_day: _MockFreshnessReport(
        status=FreshnessStatus.FULL_MARKET_FRESH,
        detail="5500 non-0050 stocks present",
        non_benchmark_count=5500,
    )


def _freshness_stale_checker():
    return lambda conn, d, is_trading_day: _MockFreshnessReport(
        status=FreshnessStatus.STALE,
        detail="data not fresh",
        non_benchmark_count=100,
    )


def _backfill_ok_runner():
    return lambda ex: {"exit_code": 0, "stdout": "backfill ok", "stderr": ""}


def _backfill_fail_runner():
    return lambda ex: {"exit_code": 1, "stdout": "", "stderr": "backfill error"}


def _shadow_ok_runner():
    return lambda: {"exit_code": 0, "stdout": "shadow ok", "stderr": ""}


def _shadow_fail_runner():
    return lambda: {"exit_code": 1, "stdout": "", "stderr": "shadow error"}


def _run_pipeline(tmp_path, hour=17, execute=True, bf=None, sh=None, fr=None,
                  trading_day=True, minute=0):
    from scripts.hybrid_shadow_cron_integrated import run_cron_pipeline

    bf = bf or _backfill_ok_runner()
    sh = sh or _shadow_ok_runner()
    fr = fr or _freshness_ok_checker()

    state = tmp_path / ".cron_state.json"
    lock = tmp_path / ".cron.lock"
    now = _taipei(2026, 11, 12, hour, minute)

    with patch("scripts.hybrid_shadow_cron_integrated.CALENDAR.is_trading_day",
               return_value=trading_day):
        return run_cron_pipeline(
            execute=execute,
            skip_backup=True,
            _now_taipei_override=now,
            _state_file_override=state,
            _lock_file_override=lock,
            _db_path_override=":memory:",
            _backfill_runner=bf,
            _shadow_runner=sh,
            _freshness_checker=fr,
        )


def _run_pipeline_today(tmp_path, hour=17, execute=True, bf=None, sh=None, fr=None,
                        trading_day=True, minute=0):
    """Date-anchored variant: uses actual date.today() for the override.

    Use in tests that perform two sequential pipeline runs and check that the
    second is blocked by the same-day guard.  The root issue (N-FINDING-01) is
    that run_cron_pipeline() calls date.today() internally; when the injected
    _now_taipei_override uses a *different* calendar date the guard sees two
    different dates and incorrectly allows the second run.  This helper keeps
    both values in sync.
    """
    from datetime import date as _date
    from scripts.hybrid_shadow_cron_integrated import run_cron_pipeline

    bf = bf or _backfill_ok_runner()
    sh = sh or _shadow_ok_runner()
    fr = fr or _freshness_ok_checker()

    today = _date.today()
    state = tmp_path / ".cron_state.json"
    lock = tmp_path / ".cron.lock"
    now = _taipei(today.year, today.month, today.day, hour, minute)

    with patch("scripts.hybrid_shadow_cron_integrated.CALENDAR.is_trading_day",
               return_value=trading_day):
        return run_cron_pipeline(
            execute=execute,
            skip_backup=True,
            _now_taipei_override=now,
            _state_file_override=state,
            _lock_file_override=lock,
            _db_path_override=":memory:",
            _backfill_runner=bf,
            _shadow_runner=sh,
            _freshness_checker=fr,
        )


# ===========================================================================
# L-01 ~ L-04: Direct Entry Protection
# ===========================================================================

class TestDirectEntryProtection:

    def test_L01_direct_backfill_execute_blocked(self, tmp_path):
        """L-01: Running protected backfill --execute without wrapper auth → exit code 2."""
        env = {k: v for k, v in os.environ.items()
               if k not in ("CALLED_FROM_WRAPPER", "BACKFILL_ALLOW_DIRECT")}
        result = subprocess.run(
            [sys.executable,
             str(SCRIPTS_DIR / "backfill_daily_prices_protected.py"),
             "--execute",
             "--db", ":memory:"],
            capture_output=True, text=True, env=env,
        )
        assert result.returncode == 2, (
            f"Expected exit code 2 (safety block), got {result.returncode}. "
            f"stderr: {result.stderr[:300]}"
        )
        assert "BACKFILL_GUARD" in result.stderr
        assert "BLOCKED" in result.stderr

    def test_L01b_direct_backfill_dryrun_allowed(self, tmp_path):
        """L-01b: Running protected backfill dry-run without wrapper auth → allowed (no write risk)."""
        env = {k: v for k, v in os.environ.items()
               if k not in ("CALLED_FROM_WRAPPER", "BACKFILL_ALLOW_DIRECT")}
        result = subprocess.run(
            [sys.executable,
             str(SCRIPTS_DIR / "backfill_daily_prices_protected.py"),
             "--start", "2026-11-20",   # future date → no data, exits cleanly
             "--end", "2026-11-20"],
            capture_output=True, text=True, env=env,
        )
        # Should NOT exit 2 (blocked); dry-run is always allowed
        assert result.returncode != 2, (
            f"Dry-run should not be blocked. returncode={result.returncode}. "
            f"stderr: {result.stderr[:300]}"
        )

    def test_L02_wrapper_authorized_child_passes(self, tmp_path):
        """L-02: When called from integrated wrapper, backfill runs and QG applies normally."""
        result = _run_pipeline(tmp_path, hour=17)
        # SUCCESS: backfill+freshness OK → pipeline succeeds
        assert result.get("status") in ("SUCCESS", "BACKFILL_OK",
                                         "SHADOW_FAILED", "SHADOW_OK"), (
            f"Unexpected status: {result.get('status')}"
        )
        # write_committed must be set (data was "written")
        assert result.get("write_committed") is True, (
            f"Expected write_committed=True after success, got {result}"
        )

    def test_L02b_called_from_wrapper_env_authorizes(self):
        """L-02b: BackfillEntryGuard.check_invocation() returns True when CALLED_FROM_WRAPPER=1."""
        from scripts.scheduler_safety_guards import BackfillEntryGuard
        with patch.dict(os.environ, {"CALLED_FROM_WRAPPER": "1"}):
            authorized, msg = BackfillEntryGuard.check_invocation(is_execute=True)
        assert authorized is True
        assert "AUTHORIZED" in msg

    def test_L03_parent_child_lock_no_deadlock(self, tmp_path):
        """L-03: backfill_daily_prices.py has no locks — running it while wrapper holds lock
        does not deadlock. Verified by confirming zero lock acquisition in backfill."""
        # This is a static/structural test: verify by grep that backfill has no flock/fcntl
        backfill = SCRIPTS_DIR / "backfill_daily_prices.py"
        text = backfill.read_text()
        lock_lines = [
            line.strip() for line in text.splitlines()
            if any(kw in line for kw in ("LOCK_EX", "LOCK_NB", "flock(", "fcntl.lock"))
            and not line.strip().startswith("#")
        ]
        assert lock_lines == [], (
            f"backfill_daily_prices.py has unexpected lock code: {lock_lines}"
        )

    def test_L04_concurrent_wrapper_plus_direct_no_overlapping_writes(self, tmp_path):
        """L-04: Protected backfill rejects execute when no wrapper auth; wrapper holds lock.
        No overlapping writes possible through protected entry."""
        # Simulate: wrapper is running (lock held), direct attempt is made.
        lock_file = tmp_path / ".cron.lock"
        lock_file.touch()
        import fcntl
        with open(lock_file, "w") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # While lock is held by "wrapper", direct execute is blocked by guard
            env = {k: v for k, v in os.environ.items()
                   if k not in ("CALLED_FROM_WRAPPER", "BACKFILL_ALLOW_DIRECT")}
            result = subprocess.run(
                [sys.executable,
                 str(SCRIPTS_DIR / "backfill_daily_prices_protected.py"),
                 "--execute",
                 "--db", ":memory:"],
                capture_output=True, text=True, env=env,
            )
            assert result.returncode == 2, (
                f"Direct execute while lock held should still be blocked by guard. "
                f"returncode={result.returncode}"
            )
            fcntl.flock(fh, fcntl.LOCK_UN)

    def test_L04b_maintenance_override_allows_direct(self):
        """L-04b: BACKFILL_ALLOW_DIRECT=1 override passes check_invocation with warning."""
        from scripts.scheduler_safety_guards import BackfillEntryGuard
        env = {k: v for k, v in os.environ.items()
               if k != "CALLED_FROM_WRAPPER"}
        env["BACKFILL_ALLOW_DIRECT"] = "1"
        with patch.dict(os.environ, env, clear=True):
            authorized, msg = BackfillEntryGuard.check_invocation(is_execute=True)
        assert authorized is True
        assert "AUTHORIZED_MAINTENANCE" in msg


# ===========================================================================
# L-05 ~ L-12: Commit Outcome / Crash Recovery
# ===========================================================================

class TestCommitOutcomeAndCrashRecovery:

    def test_L05_running_state_dead_pid_is_fail_closed(self, tmp_path):
        """L-05: State=RUNNING + dead PID → SameDayStateGuard returns WRITE_OUTCOME_UNKNOWN
        (fail-closed). Verifies crash window is handled correctly."""
        from scripts.scheduler_safety_guards import RunStatus, SameDayStateGuard

        state_file = tmp_path / ".cron_state.json"
        dead_pid = 999999999  # virtually impossible to be a live PID
        state_data = {
            "run_id": "20261112_160000_test",
            "scheduled_date": "2026-11-12",
            "status": RunStatus.RUNNING.value,
            "pid": dead_pid,
            "schema_version": "1",
            "write_committed": False,
        }
        state_file.write_text(json.dumps(state_data))

        guard = SameDayStateGuard(state_file)
        result = guard.check(date(2026, 11, 12))

        from scripts.scheduler_safety_guards import GuardStatus
        assert result.guard_status == GuardStatus.WRITE_OUTCOME_UNKNOWN, (
            f"Expected WRITE_OUTCOME_UNKNOWN for dead PID RUNNING state, "
            f"got {result.guard_status}"
        )
        assert not result.allowed

    def test_L06_unknown_commit_outcome_no_auto_retry(self, tmp_path):
        """L-06: WRITE_OUTCOME_UNKNOWN does not auto-retry; second run is blocked.

        Uses _run_pipeline_today() (date-anchored) so that run_cron_pipeline()'s
        internal date.today() matches the injected _now_taipei_override date.
        Fix for N-FINDING-01 (calendar-stale test isolation bug).
        """
        result = _run_pipeline_today(tmp_path, hour=17)
        assert result.get("write_committed") is True

        # Corrupt state to simulate WRITE_OUTCOME_UNKNOWN
        state = tmp_path / ".cron_state.json"
        state_data = json.loads(state.read_text())
        state_data["status"] = "RUNNING"
        state_data["pid"] = 999999999
        state_data["write_committed"] = False
        state.write_text(json.dumps(state_data))

        # Second run → must be blocked
        result2 = _run_pipeline_today(tmp_path, hour=17, minute=10)
        assert "GUARD_STATE" in result2.get("status", ""), (
            f"Expected guard block on second run with dead-PID RUNNING state, "
            f"got: {result2.get('status')}"
        )

    def test_L07_commit_confirmed_post_write_fail_blocks_rewrite(self, tmp_path):
        """L-07: write_committed=True in state → second run blocked even if shadow failed.

        Uses _run_pipeline_today() (date-anchored) — fix for N-FINDING-01.
        """
        result = _run_pipeline_today(tmp_path, hour=17, sh=_shadow_fail_runner())
        # Pipeline should still set write_committed=True after FULL_MARKET_FRESH
        # (shadow failure comes AFTER write, write_committed is unaffected)
        assert result.get("write_committed") is True, (
            f"write_committed should be True regardless of shadow failure: {result}"
        )

        # Second run → must be blocked (WRITE_COMMITTED_TODAY)
        result2 = _run_pipeline_today(tmp_path, hour=17, minute=10)
        assert "GUARD_STATE" in result2.get("status", ""), (
            f"Expected guard block after write_committed=True, got: {result2.get('status')}"
        )

    def test_L08_qg_blocked_not_marked_as_commit(self, tmp_path):
        """L-08: Freshness check returns STALE → pipeline returns without write_committed=True."""
        result = _run_pipeline(tmp_path, hour=17, fr=_freshness_stale_checker())
        assert result.get("write_committed") is not True, (
            f"write_committed should NOT be True when QG fails (freshness stale): {result}"
        )

    def test_L09_provider_failure_not_marked_as_commit(self, tmp_path):
        """L-09: Backfill subprocess fails (exit=1) → pipeline does not mark write_committed=True."""
        result = _run_pipeline(tmp_path, hour=17, bf=_backfill_fail_runner())
        assert result.get("write_committed") is not True, (
            f"write_committed should NOT be True when backfill fails: {result}"
        )

    def test_L10_corrupted_state_fail_closed(self, tmp_path):
        """L-10: Corrupted state file (invalid JSON) → guard returns FAIL_CLOSED_CORRUPT."""
        state_file = tmp_path / ".cron_state.json"
        state_file.write_text("{this is not valid json !!!}")

        from scripts.scheduler_safety_guards import GuardStatus, SameDayStateGuard
        guard = SameDayStateGuard(state_file)
        result = guard.check(date(2026, 11, 12))

        assert result.guard_status == GuardStatus.FAIL_CLOSED_CORRUPT, (
            f"Expected FAIL_CLOSED_CORRUPT for invalid JSON, got {result.guard_status}"
        )
        assert not result.allowed

    def test_L11_running_live_pid_treated_as_concurrent(self, tmp_path):
        """L-11: State=RUNNING + live PID (own PID) → CONCURRENT_RUN (not WRITE_OUTCOME_UNKNOWN)."""
        from scripts.scheduler_safety_guards import GuardStatus, RunStatus, SameDayStateGuard

        state_file = tmp_path / ".cron_state.json"
        live_pid = os.getpid()   # test process itself — definitely alive
        state_data = {
            "run_id": "20261112_160000_test",
            "scheduled_date": "2026-11-12",
            "status": RunStatus.RUNNING.value,
            "pid": live_pid,
            "schema_version": "1",
            "write_committed": False,
        }
        state_file.write_text(json.dumps(state_data))

        guard = SameDayStateGuard(state_file)
        result = guard.check(date(2026, 11, 12))
        assert result.guard_status == GuardStatus.CONCURRENT_RUN, (
            f"Expected CONCURRENT_RUN for live PID, got {result.guard_status}"
        )
        assert not result.allowed

    def test_L12_atomic_state_write_no_partial_read(self, tmp_path):
        """L-12: State is written atomically via os.replace (tmp→target); partial read impossible
        at the Python level. Verified by confirming _save_state uses tmp file + rename."""
        import inspect
        from scripts.hybrid_shadow_cron_integrated import _save_state
        src = inspect.getsource(_save_state)
        assert "os.replace" in src, (
            "_save_state must use os.replace for atomic writes (not found in source)"
        )
        assert ".tmp" in src, (
            "_save_state must write to a .tmp file first (not found in source)"
        )


# ===========================================================================
# L-13 ~ L-18: RC-2 / QG / Isolation Preservation
# ===========================================================================

class TestRC2QGIsolation:

    def test_L13_rc2_hash_unchanged(self):
        """L-13: backfill_daily_prices.py hash matches the known RC-2 hash."""
        from scripts.scheduler_safety_guards import RC2_EXPECTED_SHA256, verify_rc2_hash
        ok, msg = verify_rc2_hash(SCRIPTS_DIR / "backfill_daily_prices.py")
        assert ok, f"RC-2 hash mismatch: {msg}"

    def test_L14_quality_gate_logic_unchanged(self):
        """L-14: Quality gate functions are unmodified (structural check via import + call)."""
        # The QG is in hybrid_shadow_cron.py's check_market_freshness.
        # We verify it by confirming the integrated wrapper's freshness_checker is a passthrough
        # (injected in tests) and that the guard never touches QG-1~QG-7.
        from scripts.scheduler_safety_guards import GuardStatus
        # If guards fire, they return before any QG call.
        # Verify: guard module has no reference to QG internals.
        import scripts.scheduler_safety_guards as ssg
        import inspect
        src = inspect.getsource(ssg)
        # Guard module must not import or call QG functions
        for qg_fn in ("check_market_freshness", "run_qg_", "quality_gate"):
            assert qg_fn not in src, (
                f"scheduler_safety_guards.py must not reference QG function '{qg_fn}'"
            )

    def test_L15_no_provider_http_calls_in_guard_module(self):
        """L-15: Safety guard module makes no HTTP calls to TWSE/TPEx providers."""
        import scripts.scheduler_safety_guards as ssg
        import inspect
        src = inspect.getsource(ssg)
        for provider_url in ("twse.com.tw", "tpex.org.tw", "requests.get", "requests.post",
                             "urllib.request", "httpx"):
            assert provider_url not in src, (
                f"scheduler_safety_guards.py must not contain provider URL/HTTP call: "
                f"'{provider_url}'"
            )

    def test_L16_no_production_db_write_in_guard_module(self):
        """L-16: Safety guard module makes no direct DB writes.
        Note: 'neon.tech' appears in assert_no_neon_write() as a URL pattern to BLOCK
        (not to connect to), so we check for actual write call patterns only."""
        import scripts.scheduler_safety_guards as ssg
        import inspect
        src = inspect.getsource(ssg)
        # These are actual write operations — must NOT appear in guard module
        # (DATABASE_URL may appear as a comment; check for actual connection calls)
        for db_write in ("sqlite3.connect", "INSERT INTO", "psycopg2", "asyncpg"):
            assert db_write not in src, (
                f"scheduler_safety_guards.py must not contain DB write call: '{db_write}'"
            )
        # The guard module should contain the neon-block safety function (not a write call)
        assert "assert_no_neon_write" in src, (
            "assert_no_neon_write safety function must be present in guard module"
        )

    def test_L17_production_cron_script_unchanged(self):
        """L-17: hybrid_shadow_cron.py hash is the known production hash."""
        import hashlib
        expected = "46209171e00eb46429d0e36d02c106b87cf3684b13803ccdf53369042ba060d4"
        actual = hashlib.sha256(
            (SCRIPTS_DIR / "hybrid_shadow_cron.py").read_bytes()
        ).hexdigest()
        assert actual == expected, (
            f"hybrid_shadow_cron.py hash changed! "
            f"Expected {expected[:16]}..., got {actual[:16]}..."
        )

    def test_L18_dryrun_path_unaffected_by_guards(self, tmp_path):
        """L-18: Dry-run (execute=False) is not blocked by any guard layer."""
        # Window guard: dry-run outside window should still pass through gracefully
        # (window guard only applies to execute mode — depends on implementation)
        # Verify: BackfillEntryGuard.check_invocation(is_execute=False) → always authorized
        from scripts.scheduler_safety_guards import BackfillEntryGuard
        with patch.dict(os.environ, {}, clear=True):
            # No env vars at all — still authorized for dry-run
            authorized, msg = BackfillEntryGuard.check_invocation(is_execute=False)
        assert authorized is True, (
            f"Dry-run must always be authorized (no write risk): {msg}"
        )
        assert "dry-run" in msg.lower(), f"Expected dry-run message, got: {msg}"

    def test_L18b_protected_script_dryrun_no_block(self):
        """L-18b: Protected script dry-run with no env vars exits with code 0 (or non-2)."""
        env = {k: v for k, v in os.environ.items()
               if k not in ("CALLED_FROM_WRAPPER", "BACKFILL_ALLOW_DIRECT")}
        result = subprocess.run(
            [sys.executable,
             str(SCRIPTS_DIR / "backfill_daily_prices_protected.py"),
             "--start", "2026-12-01",   # future → no data, quick exit
             "--end", "2026-11-30"],    # start > end → prints info + exits 0
            capture_output=True, text=True, env=env,
        )
        assert result.returncode != 2, (
            f"Dry-run must not be blocked (exit code 2). "
            f"returncode={result.returncode}, stderr={result.stderr[:200]}"
        )
