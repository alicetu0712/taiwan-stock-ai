"""
Offline tests for scheduler_safety_guards.py
Session 71J, 2026-11-12

Test matrix (T-01 ~ T-25):
  T-01..T-08  Execution Validity Window
  T-09..T-18  Same-day State Guard
  T-19..T-21  FileLock / BackfillEntryGuard
  T-22..T-23  Neon write blocker
  T-24..T-25  Utility (transition, RC-2 hash sentinel)

Design constraints:
  - No freezegun → manual clock injection (now_taipei parameter)
  - All file I/O uses tempfile (no production files touched)
  - No production provider calls (TWSE/TPEx/Neon/SQLite)
  - No imports from hybrid_shadow_cron or backfill_daily_prices
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import date, datetime, time, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
import pytz

from scripts.scheduler_safety_guards import (
    BackfillEntryGuard,
    GuardCheckResult,
    GuardStatus,
    RunState,
    RunStatus,
    SameDayStateGuard,
    WindowCheckResult,
    assert_no_neon_write,
    check_execution_window,
    make_run_id,
    verify_rc2_hash,
    _pid_is_alive,
)

TAIPEI_TZ = pytz.timezone("Asia/Taipei")

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_state(tmp_path):
    """Temporary state file path (does not yet exist)."""
    return tmp_path / ".cron_state.json"


@pytest.fixture()
def guard(tmp_state):
    return SameDayStateGuard(tmp_state)


def _taipei(year, month, day, hour=0, minute=0, second=0):
    """Build a timezone-aware datetime in Asia/Taipei."""
    return TAIPEI_TZ.localize(datetime(year, month, day, hour, minute, second))


def _write_state(tmp_state, payload: dict):
    tmp_state.write_text(json.dumps(payload))


# ---------------------------------------------------------------------------
# T-01 ~ T-08: Execution Validity Window
# ---------------------------------------------------------------------------

class TestExecutionValidityWindow:

    def test_T01_exactly_1600_allowed(self):
        """T-01: 16:00:00 CST is the first valid second."""
        now = _taipei(2026, 11, 12, 16, 0, 0)
        result = check_execution_window(now_taipei=now)
        assert result.allowed is True
        assert result.guard_status == GuardStatus.ALLOWED

    def test_T02_before_1600_blocked(self):
        """T-02: 15:59:59 CST is PRE_SCHEDULE."""
        now = _taipei(2026, 11, 12, 15, 59, 59)
        result = check_execution_window(now_taipei=now)
        assert result.allowed is False
        assert result.guard_status == GuardStatus.PRE_SCHEDULE
        assert "16:00" in result.reason

    def test_T03_exactly_2000_blocked(self):
        """T-03: 20:00:00 CST is the first expired second (exclusive upper bound)."""
        now = _taipei(2026, 11, 12, 20, 0, 0)
        result = check_execution_window(now_taipei=now)
        assert result.allowed is False
        assert result.guard_status == GuardStatus.EXECUTION_WINDOW_EXPIRED
        assert "20:00" in result.reason

    def test_T04_after_2000_blocked(self):
        """T-04: 20:00:01 CST is EXECUTION_WINDOW_EXPIRED."""
        now = _taipei(2026, 11, 12, 20, 0, 1)
        result = check_execution_window(now_taipei=now)
        assert result.allowed is False
        assert result.guard_status == GuardStatus.EXECUTION_WINDOW_EXPIRED

    def test_T05_last_valid_second(self):
        """T-05: 19:59:59 CST is the last valid second."""
        now = _taipei(2026, 11, 12, 19, 59, 59)
        result = check_execution_window(now_taipei=now)
        assert result.allowed is True
        assert result.guard_status == GuardStatus.ALLOWED

    def test_T06_naive_datetime_fail_closed(self):
        """T-06: Naive datetime (no tzinfo) → FAIL_CLOSED_NAIVE_TIME."""
        now = datetime(2026, 11, 12, 16, 30, 0)   # No timezone
        assert now.tzinfo is None
        result = check_execution_window(now_taipei=now)
        assert result.allowed is False
        assert result.guard_status == GuardStatus.FAIL_CLOSED_NAIVE_TIME

    def test_T07_non_taipei_timezone_normalized(self):
        """T-07: UTC 08:00 == Taipei 16:00 → ALLOWED."""
        # 08:00 UTC = 16:00 CST (+8)
        now_utc = datetime(2026, 11, 12, 8, 0, 0, tzinfo=timezone.utc)
        result = check_execution_window(now_taipei=now_utc)
        assert result.allowed is True
        assert result.guard_status == GuardStatus.ALLOWED

    def test_T08_midnight_blocked(self):
        """T-08: 00:00 CST is PRE_SCHEDULE."""
        now = _taipei(2026, 11, 12, 0, 0, 0)
        result = check_execution_window(now_taipei=now)
        assert result.allowed is False
        assert result.guard_status == GuardStatus.PRE_SCHEDULE

    def test_window_check_via_clock_callable(self):
        """clock= injection works (alternative to now_taipei=)."""
        now = _taipei(2026, 11, 12, 17, 0, 0)
        result = check_execution_window(clock=lambda: now)
        assert result.allowed is True

    def test_window_returns_correct_scheduled_date(self):
        """scheduled_date in result matches the date portion of now_taipei."""
        now = _taipei(2026, 11, 12, 17, 30, 0)
        result = check_execution_window(now_taipei=now)
        assert result.scheduled_date == date(2026, 11, 12)


# ---------------------------------------------------------------------------
# T-09 ~ T-18: Same-day State Guard
# ---------------------------------------------------------------------------

class TestSameDayStateGuard:

    # --- file absent / empty ---

    def test_T09_no_state_file_allowed(self, guard):
        """T-09: No state file → first run → ALLOWED."""
        result = guard.check(date(2026, 11, 12))
        assert result.allowed is True
        assert result.guard_status == GuardStatus.ALLOWED

    def test_T10_prior_day_success_allowed(self, guard, tmp_state):
        """T-10: Prior day SUCCESS → today is different → ALLOWED."""
        _write_state(tmp_state, {
            "scheduled_date": "2026-11-11",
            "status": "SUCCESS",
            "run_id": "cron-20261111-abc12345",
        })
        result = guard.check(date(2026, 11, 12))
        assert result.allowed is True
        assert result.guard_status == GuardStatus.ALLOWED

    # --- same-day blocks ---

    def test_T11_same_day_success_blocked(self, guard, tmp_state):
        """T-11: Same day SUCCESS → ALREADY_RAN_TODAY (blocked)."""
        _write_state(tmp_state, {
            "scheduled_date": "2026-11-12",
            "status": "SUCCESS",
            "run_id": "cron-20261112-abc12345",
        })
        result = guard.check(date(2026, 11, 12))
        assert result.allowed is False
        assert result.guard_status == GuardStatus.ALREADY_RAN_TODAY

    def test_T12_same_day_running_alive_blocked(self, guard, tmp_state):
        """T-12: Same day RUNNING + PID alive → CONCURRENT_RUN (blocked)."""
        my_pid = os.getpid()   # guaranteed alive
        _write_state(tmp_state, {
            "scheduled_date": "2026-11-12",
            "status": "RUNNING",
            "pid": my_pid,
            "run_id": "cron-20261112-alive",
        })
        result = guard.check(date(2026, 11, 12))
        assert result.allowed is False
        assert result.guard_status == GuardStatus.CONCURRENT_RUN

    def test_T13_same_day_running_dead_pid_blocked(self, guard, tmp_state):
        """T-13: Same day RUNNING + dead PID → WRITE_OUTCOME_UNKNOWN (blocked)."""
        _write_state(tmp_state, {
            "scheduled_date": "2026-11-12",
            "status": "RUNNING",
            "pid": 999999999,  # effectively impossible PID
            "run_id": "cron-20261112-crashed",
        })
        result = guard.check(date(2026, 11, 12))
        assert result.allowed is False
        assert result.guard_status == GuardStatus.WRITE_OUTCOME_UNKNOWN

    def test_T14_same_day_qg_blocked_allowed(self, guard, tmp_state):
        """T-14: Same day QG_BLOCKED → retry permitted → ALLOWED."""
        _write_state(tmp_state, {
            "scheduled_date": "2026-11-12",
            "status": "QG_BLOCKED",
            "run_id": "cron-20261112-qg",
        })
        result = guard.check(date(2026, 11, 12))
        assert result.allowed is True
        assert result.guard_status == GuardStatus.ALLOWED

    def test_T15_same_day_provider_failed_allowed(self, guard, tmp_state):
        """T-15: Same day PROVIDER_FAILED → retry permitted → ALLOWED."""
        _write_state(tmp_state, {
            "scheduled_date": "2026-11-12",
            "status": "PROVIDER_FAILED",
            "run_id": "cron-20261112-pf",
        })
        result = guard.check(date(2026, 11, 12))
        assert result.allowed is True

    def test_T16_same_day_failed_allowed(self, guard, tmp_state):
        """T-16: Same day FAILED → retry permitted → ALLOWED."""
        _write_state(tmp_state, {
            "scheduled_date": "2026-11-12",
            "status": "FAILED",
            "run_id": "cron-20261112-fail",
        })
        result = guard.check(date(2026, 11, 12))
        assert result.allowed is True

    # --- corrupt state ---

    def test_T17_corrupt_state_fail_closed(self, guard, tmp_state):
        """T-17: Corrupt state file → FAIL_CLOSED_CORRUPT (blocked)."""
        tmp_state.write_text("{ invalid json !!!!")
        result = guard.check(date(2026, 11, 12))
        assert result.allowed is False
        assert result.guard_status == GuardStatus.FAIL_CLOSED_CORRUPT

    # --- atomic write ---

    def test_T18_atomic_write_creates_file(self, guard, tmp_state):
        """T-18: write_state() creates the state file atomically."""
        state = RunState(
            scheduled_date="2026-11-12",
            pid=os.getpid(),
            status=RunStatus.RUNNING.value,
        )
        success = guard.write_state(state)
        assert success is True
        assert tmp_state.exists()
        payload = json.loads(tmp_state.read_text())
        assert payload["scheduled_date"] == "2026-11-12"
        assert payload["status"] == "RUNNING"
        assert payload["schema_version"] == 1

    # --- S71J extra: write_committed ---

    def test_T19_write_committed_today_blocked(self, guard, tmp_state):
        """T-19 (S71J): Same day WRITE_COMMITTED → WRITE_COMMITTED_TODAY (blocked)."""
        _write_state(tmp_state, {
            "scheduled_date": "2026-11-12",
            "status": "WRITE_COMMITTED",
            "run_id": "cron-20261112-wc",
            "write_committed": True,
        })
        result = guard.check(date(2026, 11, 12))
        assert result.allowed is False
        assert result.guard_status == GuardStatus.WRITE_COMMITTED_TODAY

    def test_write_committed_flag_alone_blocks(self, guard, tmp_state):
        """write_committed=True with any status blocks (data already written)."""
        _write_state(tmp_state, {
            "scheduled_date": "2026-11-12",
            "status": "POST_WRITE_CHECK_FAILED",  # failed but write happened
            "run_id": "cron-20261112-pwcf",
            "write_committed": True,
        })
        result = guard.check(date(2026, 11, 12))
        assert result.allowed is False
        assert result.guard_status == GuardStatus.WRITE_COMMITTED_TODAY

    def test_post_write_check_failed_no_write_flag_allowed(self, guard, tmp_state):
        """POST_WRITE_CHECK_FAILED without write_committed=True → allows retry."""
        _write_state(tmp_state, {
            "scheduled_date": "2026-11-12",
            "status": "POST_WRITE_CHECK_FAILED",
            "run_id": "cron-20261112-pwcf",
            "write_committed": False,
        })
        result = guard.check(date(2026, 11, 12))
        # No write confirmed → retry is safe
        assert result.allowed is True

    def test_state_guard_uses_today_field_as_fallback(self, guard, tmp_state):
        """Guard reads 'today' field as fallback for 'scheduled_date' (legacy compat)."""
        _write_state(tmp_state, {
            "today": "2026-11-12",        # legacy key
            "status": "SUCCESS",
            "run_id": "cron-20261112-legacy",
        })
        result = guard.check(date(2026, 11, 12))
        assert result.allowed is False
        assert result.guard_status == GuardStatus.ALREADY_RAN_TODAY

    def test_no_secrets_in_written_state(self, guard, tmp_state):
        """write_state() must not persist secrets."""
        state = RunState(scheduled_date="2026-11-12", status=RunStatus.RUNNING.value)
        # Inject a fake secret via dataclass __dict__
        state.__dict__["database_url"] = "postgresql://user:pass@neon.tech/db"
        guard.write_state(state)
        payload = json.loads(tmp_state.read_text())
        assert "database_url" not in payload
        assert "password" not in payload

    def test_transition_updates_status(self, guard, tmp_state):
        """T-24: transition() updates status field atomically."""
        _write_state(tmp_state, {
            "scheduled_date": "2026-11-12",
            "status": "RUNNING",
            "run_id": "cron-20261112-trans",
            "pid": os.getpid(),
        })
        ok = guard.transition("cron-20261112-trans", RunStatus.SUCCESS)
        assert ok is True
        payload = json.loads(tmp_state.read_text())
        assert payload["status"] == "SUCCESS"

    def test_running_zero_pid_treated_as_dead(self, guard, tmp_state):
        """RUNNING with pid=0 → PID effectively dead → WRITE_OUTCOME_UNKNOWN."""
        _write_state(tmp_state, {
            "scheduled_date": "2026-11-12",
            "status": "RUNNING",
            "pid": 0,
            "run_id": "cron-20261112-pid0",
        })
        result = guard.check(date(2026, 11, 12))
        assert result.allowed is False
        assert result.guard_status == GuardStatus.WRITE_OUTCOME_UNKNOWN

    def test_empty_state_file_treated_as_first_run(self, guard, tmp_state):
        """Empty state file (blank JSON) → no prior state → ALLOWED."""
        tmp_state.write_text("")
        result = guard.check(date(2026, 11, 12))
        assert result.allowed is True
        assert result.guard_status == GuardStatus.ALLOWED


# ---------------------------------------------------------------------------
# T-20 ~ T-21: BackfillEntryGuard
# ---------------------------------------------------------------------------

class TestBackfillEntryGuard:

    def test_T20_no_wrapper_env_warns(self):
        """T-20: Without CALLED_FROM_WRAPPER=1 → bypass detected."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("CALLED_FROM_WRAPPER", None)
            is_bypass, msg = BackfillEntryGuard.check_standalone_bypass()
        assert is_bypass is True
        assert "WARNING" in msg
        assert "wrapper" in msg.lower()

    def test_T21_with_wrapper_env_ok(self):
        """T-21: CALLED_FROM_WRAPPER=1 → no bypass."""
        with patch.dict(os.environ, {"CALLED_FROM_WRAPPER": "1"}):
            is_bypass, msg = BackfillEntryGuard.check_standalone_bypass()
        assert is_bypass is False
        assert "OK" in msg

    def test_is_called_from_wrapper_false_by_default(self):
        """is_called_from_wrapper() returns False when env var absent."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("CALLED_FROM_WRAPPER", None)
            assert BackfillEntryGuard.is_called_from_wrapper() is False


# ---------------------------------------------------------------------------
# T-22 ~ T-23: Neon write blocker
# ---------------------------------------------------------------------------

class TestNeonWriteBlocker:

    def test_T22_neon_url_raises(self):
        """T-22: Neon URL triggers ValueError."""
        with pytest.raises(ValueError, match="SAFETY_BLOCK"):
            assert_no_neon_write(
                "postgresql://user:pass@ep-abc-123.us-east-1.aws.neon.tech/neondb"
            )

    def test_T23_sqlite_path_no_error(self):
        """T-23: SQLite file path passes silently."""
        assert_no_neon_write("sqlite:///data/platform.db")  # no exception

    def test_none_url_no_error(self):
        """None URL is a no-op."""
        assert_no_neon_write(None)  # no exception

    def test_postgres_keyword_raises(self):
        """'postgres' in URL triggers block."""
        with pytest.raises(ValueError):
            assert_no_neon_write("postgres://localhost:5432/testdb")

    def test_supabase_raises(self):
        """Supabase-style URL also blocked."""
        with pytest.raises(ValueError):
            assert_no_neon_write("postgresql://user:pw@db.supabase.co/db")


# ---------------------------------------------------------------------------
# T-25: RC-2 hash sentinel
# ---------------------------------------------------------------------------

class TestRC2HashSentinel:

    def test_T25_hash_mismatch_detected(self, tmp_path):
        """T-25: Tampered file produces different hash → (False, actual_hash)."""
        f = tmp_path / "backfill_daily_prices.py"
        f.write_text("# tampered content")
        matches, actual = verify_rc2_hash(f)
        assert matches is False
        assert len(actual) == 64   # SHA-256 hex digest length

    def test_hash_match_on_exact_content(self, tmp_path):
        """verify_rc2_hash returns True when content matches expected SHA-256."""
        import hashlib
        from scripts.scheduler_safety_guards import RC2_EXPECTED_SHA256
        # Build a file whose content produces the expected hash
        # (conceptual test — the real file would match)
        f = tmp_path / "backfill_daily_prices.py"
        # We cannot reproduce the exact file; verify the helper reads & hashes correctly
        f.write_text("synthetic content")
        expected_for_synthetic = hashlib.sha256(b"synthetic content").hexdigest()

        # Temporarily patch the constant to match our synthetic file
        with patch("scripts.scheduler_safety_guards.RC2_EXPECTED_SHA256",
                   expected_for_synthetic):
            matches, actual = verify_rc2_hash(f)
        assert matches is True
        assert actual == expected_for_synthetic

    def test_missing_file_returns_error(self, tmp_path):
        """Missing file → (False, 'ERROR: ...')."""
        matches, msg = verify_rc2_hash(tmp_path / "nonexistent.py")
        assert matches is False
        assert "ERROR" in msg


# ---------------------------------------------------------------------------
# _pid_is_alive utility
# ---------------------------------------------------------------------------

class TestPidIsAlive:

    def test_own_pid_alive(self):
        assert _pid_is_alive(os.getpid()) is True

    def test_zero_pid_not_alive(self):
        assert _pid_is_alive(0) is False

    def test_negative_pid_not_alive(self):
        assert _pid_is_alive(-1) is False

    def test_impossible_pid_not_alive(self):
        assert _pid_is_alive(999999999) is False


# ---------------------------------------------------------------------------
# make_run_id utility
# ---------------------------------------------------------------------------

class TestMakeRunId:

    def test_format(self):
        run_id = make_run_id(date(2026, 11, 12))
        assert run_id.startswith("cron-2026-11-12-")
        parts = run_id.split("-")
        assert len(parts) == 5   # cron, 2026, 11, 12, <hex8>

    def test_unique(self):
        ids = {make_run_id(date(2026, 11, 12)) for _ in range(50)}
        assert len(ids) == 50   # all unique


# ---------------------------------------------------------------------------
# Integration: window + guard chained (simulates wrapper guard chain)
# ---------------------------------------------------------------------------

class TestGuardChain:

    def test_expired_window_before_state_check(self, guard, tmp_state):
        """
        Window expiry fires before same-day check.
        (State check is never reached if window expired.)
        """
        now = _taipei(2026, 11, 12, 20, 30, 0)
        window = check_execution_window(now_taipei=now)
        assert window.allowed is False
        assert window.guard_status == GuardStatus.EXECUTION_WINDOW_EXPIRED
        # State guard is not consulted — no interaction needed

    def test_allowed_window_then_allowed_state(self, guard):
        """Both guards allow → pipeline proceeds."""
        now = _taipei(2026, 11, 12, 16, 15, 0)
        window = check_execution_window(now_taipei=now)
        assert window.allowed is True

        state_result = guard.check(date(2026, 11, 12))
        assert state_result.allowed is True

    def test_allowed_window_then_blocked_state(self, guard, tmp_state):
        """Window allows but state blocks → pipeline is stopped."""
        _write_state(tmp_state, {
            "scheduled_date": "2026-11-12",
            "status": "SUCCESS",
            "run_id": "cron-20261112-prior",
        })
        now = _taipei(2026, 11, 12, 17, 0, 0)
        window = check_execution_window(now_taipei=now)
        assert window.allowed is True

        state_result = guard.check(date(2026, 11, 12))
        assert state_result.allowed is False
        assert state_result.guard_status == GuardStatus.ALREADY_RAN_TODAY

    def test_cron_launchd_dual_trigger_same_day(self, guard, tmp_state):
        """
        S71J: Simulate cron + launchd firing on same day (dual-trigger scenario).
        First execution writes SUCCESS; second invocation is blocked by guard.
        """
        # Simulate first run completing successfully
        state = RunState(
            scheduled_date="2026-11-12",
            pid=os.getpid(),
            status=RunStatus.SUCCESS.value,
            run_id="cron-20261112-first",
        )
        guard.write_state(state)

        # Second trigger (simulate launchd catch-up after sleep)
        result = guard.check(date(2026, 11, 12))
        assert result.allowed is False
        assert result.guard_status == GuardStatus.ALREADY_RAN_TODAY
        assert result.prior_run_id == "cron-20261112-first"

    def test_rc2_hash_drift_in_state_scenario(self, tmp_path):
        """
        S71J: RC-2 hash drift detection: tampered backfill script is detected.
        Guard module is NOT responsible for blocking, but verify_rc2_hash()
        correctly signals the drift.
        """
        f = tmp_path / "backfill_daily_prices.py"
        f.write_text("# modified by attacker")
        matches, _ = verify_rc2_hash(f)
        assert matches is False   # drift detected

    def test_direct_backfill_bypass_check(self):
        """
        S71J: Running backfill without wrapper env → bypass warning raised.
        """
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("CALLED_FROM_WRAPPER", None)
            is_bypass, msg = BackfillEntryGuard.check_standalone_bypass()
        assert is_bypass is True
        # Caller is responsible for acting on this — guard does not hard-block

    def test_neon_write_attempt_blocked_in_guard_layer(self):
        """
        S71J: Any code path that attempts a Neon write is blocked at guard layer.
        """
        neon_url = "postgresql://user:pass@ep-abc.us-east-1.aws.neon.tech/neondb"
        with pytest.raises(ValueError, match="SAFETY_BLOCK"):
            assert_no_neon_write(neon_url)

    def test_lock_state_written_atomically(self, guard, tmp_state):
        """
        S71J: State file written via os.replace — no partial read possible.
        Verify the .tmp file is cleaned up after a successful write.
        """
        state = RunState(
            scheduled_date="2026-11-12",
            pid=os.getpid(),
            status=RunStatus.RUNNING.value,
        )
        guard.write_state(state)
        tmp_file = tmp_state.with_suffix(".tmp")
        assert not tmp_file.exists(), "Temp file must be cleaned up after atomic replace"
        assert tmp_state.exists()
