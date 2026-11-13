# Session 71J — Implementation Diff

**Session**: 71J  
**New Files Created**: 2  
**Existing Files Modified**: 0  
**Production State**: UNCHANGED

---

## 1. New File: `scripts/scheduler_safety_guards.py`

### Summary

Standalone safety guard module. NOT imported by production cron. Provides:

| Component | Lines (approx) | Purpose |
|---|---|---|
| Enums (`GuardStatus`, `RunStatus`) | ~25 | Typed status values |
| Dataclasses (`WindowCheckResult`, `GuardCheckResult`, `RunState`) | ~30 | Structured return types |
| `check_execution_window()` | ~50 | 16:00–20:00 CST validity window |
| `SameDayStateGuard` | ~100 | Atomic state file–based duplicate guard |
| `BackfillEntryGuard` | ~25 | Soft warning for direct invocation bypass |
| `assert_no_neon_write()` | ~12 | Safety tripwire for Neon URL |
| `verify_rc2_hash()` | ~12 | RC-2 hash sentinel |
| `_pid_is_alive()`, `make_run_id()` | ~20 | Utility functions |

**Total**: ~274 lines (including docstrings and blank lines)

### Key design decisions

1. **Clock injection via `now_taipei` parameter** — no `freezegun` dependency.
   Caller passes a timezone-aware `datetime`; production caller passes `datetime.now(TAIPEI_TZ)`.

2. **Fail-closed on naive datetime** — `GuardStatus.FAIL_CLOSED_NAIVE_TIME` blocks execution
   rather than inferring timezone, preventing silent DST errors.

3. **Atomic state writes via `os.replace(tmp, target)`** — the temp file is written first
   and then renamed atomically. No partial read is possible.

4. **`WRITE_COMMITTED` blocks regardless of `status` field** — once `write_committed=True`
   is in the state, any re-run attempt for the same day is blocked. This prevents
   double-write even if `POST_WRITE_CHECK_FAILED` after the write.

5. **`WRITE_OUTCOME_UNKNOWN` blocks crashed runs** — if PID is dead but status=RUNNING,
   we cannot determine if SQLite was written. Guard blocks and requires manual intervention.

6. **Legacy `today` key supported** — the existing `.cron_state.json` uses `"today"` as key;
   the guard falls back to that field for compatibility.

7. **No secrets in state file** — `write_state()` strips `database_url`, `api_key`,
   `password`, `secret` before writing.

---

## 2. New File: `tests/test_scheduler_safety_guards.py`

### Summary

53 offline tests in 8 test classes. All use `tmp_path` fixture for file I/O.
No production files touched. No TWSE/TPEx/Neon/SQLite calls.

| Class | Tests | Coverage |
|---|---|---|
| `TestExecutionValidityWindow` | 10 | T-01~T-08 + 2 extras |
| `TestSameDayStateGuard` | 18 | T-09~T-19 + 7 extras |
| `TestBackfillEntryGuard` | 3 | T-20~T-21 + 1 |
| `TestNeonWriteBlocker` | 5 | T-22~T-23 + 3 |
| `TestRC2HashSentinel` | 3 | T-25 + 2 |
| `TestPidIsAlive` | 4 | utility |
| `TestMakeRunId` | 2 | utility |
| `TestGuardChain` | 8 | integration (dual-trigger, drift, bypass) |

**Total**: 53 tests

---

## 3. Zero-Change Confirmation

### Production file hashes (unchanged)

```
Pre-implementation:
  4eb6eacf...  scripts/backfill_daily_prices.py
  46209171...  scripts/hybrid_shadow_cron.py

Post-implementation:
  4eb6eacf...  scripts/backfill_daily_prices.py  ← IDENTICAL
  46209171...  scripts/hybrid_shadow_cron.py      ← IDENTICAL
```

### SQLite (unchanged)

```
Pre-implementation:  COUNT=534,770  MAX=2026-11-05
Post-implementation: COUNT=534,770  MAX=2026-11-05  ← IDENTICAL
```

### State file (unchanged)

```
today: 2026-11-10  status: BLOCKED_STALE_DATA  ← UNCHANGED
```

---

## 4. Deployment Prerequisite

The guards in `scheduler_safety_guards.py` are **not wired into production** yet.
Integration requires the following changes to `hybrid_shadow_cron.py` (Phase 2):

```python
# At the top of run_cron_job() or equivalent entrypoint:
from scripts.scheduler_safety_guards import (
    check_execution_window, SameDayStateGuard
)

window = check_execution_window()
if not window.allowed:
    log(f"[GUARD] Execution blocked: {window.reason}")
    return {"status": window.guard_status.value}

guard = SameDayStateGuard(state_path=STATE_FILE_PATH)
state_check = guard.check(scheduled_date=window.scheduled_date)
if not state_check.allowed:
    log(f"[GUARD] Same-day guard: {state_check.reason}")
    return {"status": state_check.guard_status.value}

guard.write_state(RunState(
    scheduled_date=str(window.scheduled_date),
    pid=os.getpid(),
    status=RunStatus.RUNNING.value,
))
```

This integration is a **Deployment Prerequisite** requiring explicit Phase 2 authorization.
