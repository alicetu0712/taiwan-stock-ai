"""
Scheduler Safety Guards — Phase 1 Implementation
Session 71J, 2026-11-12

Provides two independently testable guards:
  1. ExecutionValidityWindow  — 16:00–20:00 Asia/Taipei
  2. SameDayStateGuard        — prevents duplicate successful writes

NOT yet integrated into hybrid_shadow_cron.py.
Integration is a separate Deployment Prerequisite requiring explicit authorization.

Design constraints:
  - No imports from hybrid_shadow_cron.py or backfill_daily_prices.py
  - Clock injection for testability (no freezegun dependency)
  - Atomic state file writes (os.replace on temp file)
  - Fail-closed on invalid/corrupt state
  - No secrets in state file
  - Compatible with existing .cron_state.json schema (additive)
"""

from __future__ import annotations

import fcntl
import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

import pytz

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TAIPEI_TZ = pytz.timezone("Asia/Taipei")
WINDOW_START = time(16, 0, 0)   # inclusive
WINDOW_END   = time(20, 0, 0)   # exclusive (20:00:00 is NOT allowed)

SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class GuardStatus(str, Enum):
    ALLOWED                = "ALLOWED"
    PRE_SCHEDULE           = "PRE_SCHEDULE"
    EXECUTION_WINDOW_EXPIRED = "EXECUTION_WINDOW_EXPIRED"
    ALREADY_RAN_TODAY      = "ALREADY_RAN_TODAY"
    WRITE_COMMITTED_TODAY  = "WRITE_COMMITTED_TODAY"
    CONCURRENT_RUN         = "CONCURRENT_RUN"
    WRITE_OUTCOME_UNKNOWN  = "WRITE_OUTCOME_UNKNOWN"
    FAIL_CLOSED_CORRUPT    = "FAIL_CLOSED_CORRUPT"
    FAIL_CLOSED_NAIVE_TIME = "FAIL_CLOSED_NAIVE_TIME"


class RunStatus(str, Enum):
    RUNNING                = "RUNNING"
    QG_BLOCKED             = "QG_BLOCKED"
    PROVIDER_FAILED        = "PROVIDER_FAILED"
    WRITE_STARTED          = "WRITE_STARTED"
    WRITE_COMMITTED        = "WRITE_COMMITTED"
    WRITE_OUTCOME_UNKNOWN  = "WRITE_OUTCOME_UNKNOWN"
    POST_WRITE_CHECK_FAILED = "POST_WRITE_CHECK_FAILED"
    SUCCESS                = "SUCCESS"
    FAILED                 = "FAILED"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class WindowCheckResult:
    allowed: bool
    guard_status: GuardStatus
    reason: str
    scheduled_date: date
    actual_time: datetime

    def __post_init__(self):
        if isinstance(self.guard_status, str):
            self.guard_status = GuardStatus(self.guard_status)


@dataclass
class GuardCheckResult:
    allowed: bool
    guard_status: GuardStatus
    reason: str
    scheduled_date: date
    prior_run_id: str | None = None
    prior_status: str | None = None

    def __post_init__(self):
        if isinstance(self.guard_status, str):
            self.guard_status = GuardStatus(self.guard_status)


@dataclass
class RunState:
    schema_version: int = SCHEMA_VERSION
    run_id: str = field(default_factory=lambda: f"cron-{uuid.uuid4().hex[:8]}")
    scheduled_date: str = ""       # ISO date string "YYYY-MM-DD"
    actual_start_utc: str = ""     # ISO datetime string
    pid: int = 0
    status: str = RunStatus.RUNNING.value
    guard_decision: str = GuardStatus.ALLOWED.value
    write_committed: bool = False
    post_write_check: str = ""
    # Intentionally no DATABASE_URL, no API keys, no secrets


# ---------------------------------------------------------------------------
# Execution Validity Window
# ---------------------------------------------------------------------------

def check_execution_window(
    now_taipei: datetime | None = None,
    clock: Callable[[], datetime] | None = None,
) -> WindowCheckResult:
    """
    Check if the current time is within the execution validity window.

    Valid window: 16:00:00 <= now < 20:00:00 Asia/Taipei (same calendar day).
    Does NOT check trading calendar — that is handled upstream.
    Does NOT replace Quality Gate — that runs independently.

    Args:
        now_taipei: Explicit datetime for testing. Must be timezone-aware.
                    If provided, used directly (no clock() call).
        clock:      Callable returning timezone-aware datetime, for injection.
                    Used only if now_taipei is None.

    Returns:
        WindowCheckResult with allowed=True if within window.

    Fail-closed cases:
        - Naive datetime → FAIL_CLOSED_NAIVE_TIME (not allowed)
        - Any exception → FAIL_CLOSED_CORRUPT (not allowed)
    """
    try:
        if now_taipei is None:
            if clock is not None:
                now_taipei = clock()
            else:
                now_taipei = datetime.now(TAIPEI_TZ)

        # Fail closed on naive datetime
        if now_taipei.tzinfo is None:
            return WindowCheckResult(
                allowed=False,
                guard_status=GuardStatus.FAIL_CLOSED_NAIVE_TIME,
                reason="FAIL_CLOSED: naive datetime — cannot determine validity window",
                scheduled_date=date.today(),
                actual_time=now_taipei,
            )

        # Normalize to Taipei timezone
        now_taipei = now_taipei.astimezone(TAIPEI_TZ)
        t = now_taipei.time()
        scheduled_date = now_taipei.date()

        if t < WINDOW_START:
            return WindowCheckResult(
                allowed=False,
                guard_status=GuardStatus.PRE_SCHEDULE,
                reason=(
                    f"PRE_SCHEDULE: {t.strftime('%H:%M:%S')} CST "
                    f"< 16:00:00 (scheduled execution window)"
                ),
                scheduled_date=scheduled_date,
                actual_time=now_taipei,
            )

        if t >= WINDOW_END:
            return WindowCheckResult(
                allowed=False,
                guard_status=GuardStatus.EXECUTION_WINDOW_EXPIRED,
                reason=(
                    f"EXECUTION_WINDOW_EXPIRED: {t.strftime('%H:%M:%S')} CST "
                    f">= 20:00:00 deadline; cross-day catch-up blocked"
                ),
                scheduled_date=scheduled_date,
                actual_time=now_taipei,
            )

        return WindowCheckResult(
            allowed=True,
            guard_status=GuardStatus.ALLOWED,
            reason=(
                f"WITHIN_WINDOW: {t.strftime('%H:%M:%S')} CST "
                f"in [16:00:00, 20:00:00)"
            ),
            scheduled_date=scheduled_date,
            actual_time=now_taipei,
        )

    except Exception as exc:
        return WindowCheckResult(
            allowed=False,
            guard_status=GuardStatus.FAIL_CLOSED_CORRUPT,
            reason=f"FAIL_CLOSED: unexpected error in window check: {exc}",
            scheduled_date=date.today(),
            actual_time=datetime.now(TAIPEI_TZ),
        )


# ---------------------------------------------------------------------------
# Same-day State Guard
# ---------------------------------------------------------------------------

class SameDayStateGuard:
    """
    Prevents duplicate runs on the same scheduled date using an atomic state file.

    Guard logic:
      - SUCCESS for today           → ALREADY_RAN_TODAY (block)
      - WRITE_COMMITTED for today   → WRITE_COMMITTED_TODAY (block; data written,
                                       don't re-write even if post-write failed)
      - RUNNING + PID alive today   → CONCURRENT_RUN (block)
      - RUNNING + PID dead today    → WRITE_OUTCOME_UNKNOWN (block; crash — may
                                       have written, cannot assume not)
      - RUNNING + PID dead yesterday or older → allow retry (stale from prev day)
      - Corrupted state file        → FAIL_CLOSED_CORRUPT (block)
      - Any other state             → ALLOWED (retry permitted)

    The guard does NOT consult SQLite directly — it relies on the state file
    written by the pipeline. This avoids adding a SQLite dependency here and
    is consistent with the existing .cron_state.json pattern.
    """

    def __init__(self, state_path: Path):
        """
        Args:
            state_path: Path to the JSON state file.
                        MUST be a non-production path in tests.
                        Production path: data/.cron_state.json (set by caller).
        """
        self._path = Path(state_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check(
        self,
        scheduled_date: date,
    ) -> GuardCheckResult:
        """
        Check whether a new run for scheduled_date should be allowed.

        Args:
            scheduled_date: The date the cron was supposed to run (not necessarily today).

        Returns:
            GuardCheckResult with allowed=True if the run should proceed.
        """
        state = self._load()
        if state is None:
            # Corrupted → fail closed
            return GuardCheckResult(
                allowed=False,
                guard_status=GuardStatus.FAIL_CLOSED_CORRUPT,
                reason="FAIL_CLOSED: state file corrupt or unreadable",
                scheduled_date=scheduled_date,
            )

        if not state:
            # Missing / empty → first run, allow
            return GuardCheckResult(
                allowed=True,
                guard_status=GuardStatus.ALLOWED,
                reason="ALLOWED: no prior state (first run)",
                scheduled_date=scheduled_date,
            )

        prior_date_str = state.get("today") or state.get("scheduled_date", "")
        prior_status   = state.get("status", "")
        prior_run_id   = state.get("run_id")
        prior_pid      = state.get("pid", 0)

        # Only apply same-day logic when dates match
        if prior_date_str != str(scheduled_date):
            return GuardCheckResult(
                allowed=True,
                guard_status=GuardStatus.ALLOWED,
                reason=(
                    f"ALLOWED: prior state is from {prior_date_str!r}, "
                    f"not today {scheduled_date}"
                ),
                scheduled_date=scheduled_date,
                prior_run_id=prior_run_id,
                prior_status=prior_status,
            )

        # Same day — check status
        if prior_status == RunStatus.SUCCESS.value:
            return GuardCheckResult(
                allowed=False,
                guard_status=GuardStatus.ALREADY_RAN_TODAY,
                reason=(
                    f"ALREADY_RAN_TODAY: {scheduled_date} pipeline completed "
                    f"successfully (run_id={prior_run_id})"
                ),
                scheduled_date=scheduled_date,
                prior_run_id=prior_run_id,
                prior_status=prior_status,
            )

        if prior_status == RunStatus.WRITE_COMMITTED.value or state.get("write_committed"):
            return GuardCheckResult(
                allowed=False,
                guard_status=GuardStatus.WRITE_COMMITTED_TODAY,
                reason=(
                    f"WRITE_COMMITTED_TODAY: data for {scheduled_date} has been "
                    f"committed to SQLite. Post-write check may have failed but "
                    f"re-write is blocked (run_id={prior_run_id})"
                ),
                scheduled_date=scheduled_date,
                prior_run_id=prior_run_id,
                prior_status=prior_status,
            )

        if prior_status == RunStatus.RUNNING.value:
            if prior_pid and _pid_is_alive(prior_pid):
                return GuardCheckResult(
                    allowed=False,
                    guard_status=GuardStatus.CONCURRENT_RUN,
                    reason=(
                        f"CONCURRENT_RUN: pipeline PID {prior_pid} is still running "
                        f"for {scheduled_date}"
                    ),
                    scheduled_date=scheduled_date,
                    prior_run_id=prior_run_id,
                    prior_status=prior_status,
                )
            else:
                # PID dead but status RUNNING → crash
                return GuardCheckResult(
                    allowed=False,
                    guard_status=GuardStatus.WRITE_OUTCOME_UNKNOWN,
                    reason=(
                        f"WRITE_OUTCOME_UNKNOWN: prior run (PID {prior_pid}) for "
                        f"{scheduled_date} crashed. Cannot determine if SQLite was "
                        f"written. Manual intervention required."
                    ),
                    scheduled_date=scheduled_date,
                    prior_run_id=prior_run_id,
                    prior_status=prior_status,
                )

        # All other statuses (QG_BLOCKED, PROVIDER_FAILED, POST_WRITE_CHECK_FAILED,
        # FAILED, etc.) → allow retry
        return GuardCheckResult(
            allowed=True,
            guard_status=GuardStatus.ALLOWED,
            reason=(
                f"ALLOWED: prior status={prior_status!r} for {scheduled_date} "
                f"permits retry"
            ),
            scheduled_date=scheduled_date,
            prior_run_id=prior_run_id,
            prior_status=prior_status,
        )

    def write_state(self, state: RunState) -> bool:
        """
        Atomically write state to the state file.

        Uses write-to-temp + os.replace() for atomicity.
        Does NOT write any secrets.

        Returns:
            True on success, False on failure (non-fatal — caller decides).
        """
        try:
            payload = asdict(state)
            # Safety: strip any accidentally included secrets
            for key in ("database_url", "api_key", "password", "secret"):
                payload.pop(key, None)

            tmp_path = self._path.with_suffix(".tmp")
            tmp_path.write_text(json.dumps(payload, indent=2))
            os.replace(tmp_path, self._path)
            return True
        except Exception:
            return False

    def transition(self, run_id: str, new_status: RunStatus, **extra) -> bool:
        """
        Atomically update only the status field of an existing state.

        Convenience method for status transitions during pipeline execution.
        """
        state = self._load() or {}
        state["status"] = new_status.value
        state["run_id"] = run_id
        for k, v in extra.items():
            state[k] = v

        try:
            tmp_path = self._path.with_suffix(".tmp")
            tmp_path.write_text(json.dumps(state, indent=2))
            os.replace(tmp_path, self._path)
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(self) -> dict | None:
        """
        Load state from file.

        Returns:
            dict if file exists and is valid JSON,
            {}   if file does not exist (first run),
            None if file exists but is corrupt (fail-closed).
        """
        if not self._path.exists():
            return {}
        try:
            text = self._path.read_text()
            if not text.strip():
                return {}
            return json.loads(text)
        except (json.JSONDecodeError, OSError):
            return None  # Corrupt → caller will fail-closed


# ---------------------------------------------------------------------------
# FileLock Option B — Standalone Backfill Entry Check
# ---------------------------------------------------------------------------

class BackfillEntryGuard:
    """
    Option B: Standalone backfill guard — defense-in-depth for direct invocation.

    Two-layer check (check_invocation — legacy/backward-compat):
      Layer 1 (soft): CALLED_FROM_WRAPPER=1 environment variable set by the wrapper.
      Layer 2 (harder): parent process name check via `ps` (macOS/Linux).

    Three-layer check (check_original_entry — S71M strict mode):
      Layer 0 (primary): .cron.lock is currently held by another process.
      Layer 1: CALLED_FROM_WRAPPER=1 (diagnostic/supplementary only when lock is held).
      Layer 2: Parent PID check (diagnostic/supplementary only when lock is held).

    Maintenance override (check_original_entry only):
      BOTH BACKFILL_ALLOW_DIRECT=1 AND BACKFILL_MAINTENANCE_REASON must be set.
      Single env var alone is insufficient — prevents accidental activation.

    Design:
      - check_original_entry() → lock-based primary gate for original backfill entry
      - check_invocation()     → env var gate (backward compat; used by protected.py)
      - check_standalone_bypass() → advisory only
    """

    ENV_KEY = "CALLED_FROM_WRAPPER"
    ALLOW_DIRECT_KEY = "BACKFILL_ALLOW_DIRECT"   # maintenance override (needs companion)
    MAINTENANCE_REASON_KEY = "BACKFILL_MAINTENANCE_REASON"  # companion to ALLOW_DIRECT
    WRAPPER_SCRIPT_NAME = "hybrid_shadow_cron"   # partial match on parent cmdline

    @classmethod
    def is_called_from_wrapper(cls) -> bool:
        return os.environ.get(cls.ENV_KEY) == "1"

    @classmethod
    def _parent_is_wrapper(cls) -> tuple[bool, str]:
        """
        Check parent process command line for wrapper script name.
        Uses `ps -p <ppid> -o command=` (macOS/Linux compatible).
        Returns (is_wrapper, detail_string).
        """
        import subprocess as _sp
        ppid = os.getppid()
        try:
            result = _sp.run(
                ["ps", "-p", str(ppid), "-o", "command="],
                capture_output=True, text=True, timeout=5,
            )
            parent_cmd = result.stdout.strip()
            if cls.WRAPPER_SCRIPT_NAME in parent_cmd:
                return True, f"parent PID {ppid}: {parent_cmd[:80]}"
            return False, f"parent PID {ppid}: {parent_cmd[:80]!r}"
        except Exception as e:
            return False, f"parent PID check failed: {e}"

    @classmethod
    def check_invocation(cls, is_execute: bool = True) -> tuple[bool, str]:
        """
        Defense-in-depth authorization check for backfill execution.

        Returns (is_authorized, message).
        is_authorized=True means the call is from a recognized authorized path.

        Layers:
          1. Maintenance override: BACKFILL_ALLOW_DIRECT=1 (explicit bypass with warning)
          2. Env var: CALLED_FROM_WRAPPER=1 (set by wrapper subprocess call)
          3. Parent PID: parent process name contains 'hybrid_shadow_cron'

        For dry-run (is_execute=False), always returns authorized (no data written).
        """
        if not is_execute:
            return True, "AUTHORIZED: dry-run mode — no write risk"

        # Maintenance override (must be explicit and documented)
        if os.environ.get(cls.ALLOW_DIRECT_KEY) == "1":
            return True, (
                "AUTHORIZED_MAINTENANCE: BACKFILL_ALLOW_DIRECT=1 override active. "
                "Ensure no concurrent wrapper run. Document this in run log."
            )

        # Layer 1: env var from wrapper
        if cls.is_called_from_wrapper():
            return True, "AUTHORIZED: CALLED_FROM_WRAPPER=1"

        # Layer 2: parent process check
        is_wrapper, detail = cls._parent_is_wrapper()
        if is_wrapper:
            return True, f"AUTHORIZED: parent is wrapper ({detail})"

        return False, (
            f"UNAUTHORIZED_DIRECT_ENTRY: backfill --execute called without wrapper "
            f"authorization. {detail}. "
            f"Use hybrid_shadow_cron.py --execute for production runs. "
            f"For maintenance: set BACKFILL_ALLOW_DIRECT=1 and BACKFILL_MAINTENANCE_REASON."
        )

    @classmethod
    def _check_lock_state(cls, lock_path: Path) -> tuple[bool, str]:
        """
        Check if lock_path is currently held by another process.

        Uses try-LOCK_EX-LOCK_NB approach:
          - If we can acquire → lock is NOT held → returns (False, detail)
          - If BlockingIOError → lock IS held by another process → returns (True, detail)

        IMPORTANT: If acquired, immediately releases. No persistent lock is taken.
        IMPORTANT: Uses 'a' (append) mode to avoid truncating the lock file.

        Note on security: same OS user can forge this by holding the lock themselves.
        This is documented as a limitation; the check prevents accidental bypass.
        """
        lock_path = Path(lock_path)
        try:
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            with open(lock_path, "a") as fh:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                # Acquired → no other process holds it
                fcntl.flock(fh, fcntl.LOCK_UN)
                return False, f"lock not held at {lock_path}"
        except BlockingIOError:
            return True, f"lock held by another process at {lock_path}"
        except OSError as e:
            # Treat unexpected OSError as "unknown" → fail-closed (not held)
            return False, f"lock check failed ({e}) at {lock_path}"

    @classmethod
    def check_original_entry(
        cls,
        is_execute: bool = True,
        lock_path: Optional[Path] = None,
    ) -> tuple[bool, str]:
        """
        Lock-based authorization check for the original backfill entry point (S71M).

        This is STRICTER than check_invocation():
          - Lock check is PRIMARY gate (not env var or parent PID)
          - Maintenance requires TWO env vars (ALLOW_DIRECT + MAINTENANCE_REASON)
          - Env var and parent PID are DIAGNOSTIC only when lock is held

        Args:
            is_execute: False = dry-run, always authorized.
            lock_path:  Path to check for active lock. If None, skips lock check
                        and falls back to env-var-only mode (less strict).

        Security limitation: same OS user can forge by acquiring the lock themselves
        before calling backfill. This prevents accidents, not determined misuse.
        """
        if not is_execute:
            return True, "AUTHORIZED: dry-run mode — no write risk"

        # Two-key maintenance override (before lock check)
        allow_direct = os.environ.get(cls.ALLOW_DIRECT_KEY) == "1"
        maintenance_reason = os.environ.get(cls.MAINTENANCE_REASON_KEY, "").strip()
        if allow_direct and maintenance_reason:
            return True, (
                f"AUTHORIZED_MAINTENANCE: BACKFILL_ALLOW_DIRECT=1 + reason='{maintenance_reason[:100]}'. "
                "Ensure no concurrent wrapper run. Document in run log."
            )
        if allow_direct and not maintenance_reason:
            # Single env var alone is insufficient — require companion reason
            return False, (
                "MAINTENANCE_AUTHORIZATION_INCOMPLETE: BACKFILL_ALLOW_DIRECT=1 is set "
                f"but {cls.MAINTENANCE_REASON_KEY} is empty or missing. "
                "Both are required to prevent accidental maintenance mode activation."
            )

        # Primary gate: lock check
        if lock_path is not None:
            lock_held, lock_detail = cls._check_lock_state(lock_path)
            if not lock_held:
                # Lock NOT held → env var and parent PID alone are insufficient
                env_note = ""
                if cls.is_called_from_wrapper():
                    env_note = (
                        f" Note: CALLED_FROM_WRAPPER=1 is set but {lock_path.name} "
                        "is not held — env var alone is not sufficient authorization."
                    )
                return False, (
                    f"UNAUTHORIZED: {lock_detail}.{env_note} "
                    "Use hybrid_shadow_cron.py --execute for production runs. "
                    f"For maintenance: set {cls.ALLOW_DIRECT_KEY}=1 and {cls.MAINTENANCE_REASON_KEY}."
                )
            # Lock IS held — authorized; log diagnostic info
            env_set = cls.is_called_from_wrapper()
            is_wrapper_parent, parent_detail = cls._parent_is_wrapper()
            return True, (
                f"AUTHORIZED: {lock_detail}. "
                f"env_var={'SET' if env_set else 'NOT_SET'}, "
                f"parent={'wrapper' if is_wrapper_parent else f'other({parent_detail[:40]})'}"
            )

        # lock_path=None → fall back to legacy env-var/parent-PID check (backward compat)
        if cls.is_called_from_wrapper():
            return True, "AUTHORIZED: CALLED_FROM_WRAPPER=1 (lock_path not provided)"
        is_wrapper_parent, detail = cls._parent_is_wrapper()
        if is_wrapper_parent:
            return True, f"AUTHORIZED: parent is wrapper ({detail}) (lock_path not provided)"
        return False, (
            "UNAUTHORIZED_DIRECT_ENTRY: no lock_path provided and no env var/parent auth. "
            "Use hybrid_shadow_cron.py --execute for production runs."
        )

    @classmethod
    def check_standalone_bypass(cls) -> tuple[bool, str]:
        """
        Returns (is_bypassing_wrapper, warning_message).
        is_bypassing_wrapper=True means direct invocation detected.
        """
        if cls.is_called_from_wrapper():
            return False, "OK: invoked through wrapper"
        return True, (
            "WARNING: backfill_daily_prices.py invoked directly — "
            "bypasses FileLock in hybrid_shadow_cron.py. "
            "Use hybrid_shadow_cron.py --execute for production runs. "
            "(CALLED_FROM_WRAPPER env var not set)"
        )


# ---------------------------------------------------------------------------
# Neon Write Attempt Blocker
# ---------------------------------------------------------------------------

def assert_no_neon_write(db_url: str | None) -> None:
    """
    Raise if db_url points to Neon/PostgreSQL.

    This is a safety tripwire: backfill must NEVER write to Neon.
    Equivalent to the existing _verify_sqlite() check in backfill_daily_prices.py.

    Raises:
        ValueError if db_url is a Neon/PostgreSQL URL.
    """
    if db_url is None:
        return
    url_lower = str(db_url).lower()
    if any(kw in url_lower for kw in ("postgres", "neon.tech", "supabase", "elephantsql")):
        raise ValueError(
            f"SAFETY_BLOCK: attempted to use non-SQLite database URL "
            f"in backfill write path: {db_url[:40]}..."
        )


# ---------------------------------------------------------------------------
# RC-2 Hash Sentinel
# ---------------------------------------------------------------------------

RC2_EXPECTED_SHA256 = "4eb6eacf6c65df52aae037731e66e4573a8ae929af807c0fbd7c1adcac4c5afb"


def verify_rc2_hash(backfill_path: Path) -> tuple[bool, str]:
    """
    Verify that backfill_daily_prices.py has the expected RC-2 hash.

    Returns:
        (matches: bool, actual_hash: str)
    """
    import hashlib
    try:
        content = Path(backfill_path).read_bytes()
        actual = hashlib.sha256(content).hexdigest()
        return actual == RC2_EXPECTED_SHA256, actual
    except OSError as e:
        return False, f"ERROR: {e}"


# ---------------------------------------------------------------------------
# Internal utility
# ---------------------------------------------------------------------------

def _pid_is_alive(pid: int) -> bool:
    """Check if a process with the given PID is running."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)   # signal 0 = existence check only
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # process exists but we can't send signal
    except OSError:
        return False


def make_run_id(scheduled_date: date) -> str:
    """Generate a unique run ID for a scheduled date."""
    return f"cron-{scheduled_date.isoformat()}-{uuid.uuid4().hex[:8]}"
