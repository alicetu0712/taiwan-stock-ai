# Session 71K — FileLock Acceptance

**Session**: 71K  
**Verdict**: `DIRECT_ENTRY_GAP_REMAINS` / Lock safety otherwise VERIFIED

---

## 1. Lock Architecture (Existing, Unchanged)

The production wrapper uses `fcntl.flock(LOCK_EX | LOCK_NB)` on `data/.cron.lock`.

```
FileLock (data/.cron.lock)
  │
  ├── Wrapper (PID A) acquires LOCK_EX | LOCK_NB
  │     └── holds lock for entire pipeline duration
  │
  ├── Backfill subprocess (PID B) spawned by wrapper
  │     └── does NOT acquire any lock (confirmed: grep finds only comment at line 168)
  │
  └── Wrapper releases lock in finally block
```

---

## 2. Lock Verification Results (IT-15 ~ IT-18)

| Test | Scenario | Result |
|---|---|---|
| IT-15 | Normal run: lock acquired + released | PASS |
| IT-16 | Concurrent wrapper: second blocked by BLOCKED_LOCK | PASS |
| IT-17 | Exception in backfill: lock released in finally | PASS |
| IT-18 | Parent/child deadlock: not possible (backfill has no locks) | PASS (by design) |

---

## 3. Lock Properties

| Property | Value | Verified? |
|---|---|---|
| Lock file path | `data/.cron.lock` | YES |
| Lock type | `fcntl.LOCK_EX | LOCK_NB` (exclusive, non-blocking) | YES |
| Lock holder | Wrapper PID (parent) only | YES |
| Lock scope | Entire pipeline (Steps 1–6) | YES |
| Lock release | In `finally` block (always releases) | YES (IT-17) |
| Crash recovery | File-level lock released by OS when process dies | YES (POSIX guarantee) |
| PID written to lock file | YES (`os.write(fd, f"{pid}\n")`) | YES |

---

## 4. Backfill Lock Analysis (No Deadlock)

Code inspection of `backfill_daily_prices.py`:
```bash
grep -n "flock|lock|fcntl|Lock" scripts/backfill_daily_prices.py
# Line 168: comment only ("If the api_date in the response != d, the QG-5 check will block...")
```

**Result**: `backfill_daily_prices.py` acquires NO file locks. 

**Deadlock analysis (Option C, NOT implemented):**
If backfill acquired the SAME lock file:
1. Wrapper PID A: `flock(LOCK_EX)` → succeeds
2. Backfill PID B (child): `flock(LOCK_EX | LOCK_NB)` → BLOCKED (BlockingIOError)
3. Backfill exits with error → 0 data written
4. Pipeline returns BACKFILL_FAILED

This is why Option C is NOT recommended (see `session71j_filelock_safety.md`).

---

## 5. `CALLED_FROM_WRAPPER` Integration

The integrated wrapper now sets `CALLED_FROM_WRAPPER=1` in the subprocess env when calling backfill:

```python
env = {**os.environ, "CALLED_FROM_WRAPPER": "1"}
subprocess.run(cmd, ..., env=env)
```

This enables `BackfillEntryGuard.check_standalone_bypass()` to distinguish legitimate (via wrapper) from direct invocations.

---

## 6. Direct Backfill Entry Gap

**`DIRECT_ENTRY_GAP_REMAINS`**: `backfill_daily_prices.py` can still be invoked directly without going through the wrapper. This bypasses:
- Execution window guard
- Same-day state guard
- FileLock

### Why this gap cannot be closed in S71K:

Closing this gap requires modifying `backfill_daily_prices.py` to:
1. Check `CALLED_FROM_WRAPPER=1` and reject if absent, OR
2. Acquire its own lock (but this risks Option C deadlock)

Both options modify a production file. This is NOT authorized in S71K.

### Mitigation in place:

| Mitigation | Status |
|---|---|
| `BackfillEntryGuard` soft warning | IMPLEMENTED (S71J) |
| `INSERT OR IGNORE` prevents duplicate rows | EXISTING |
| SQLite WAL mode serializes concurrent writes | EXISTING |
| `CALLED_FROM_WRAPPER=1` env set by integrated wrapper | NEW (S71K) |

### Precondition to block deployment:

If this gap must be closed before deployment, the deployment gate requires:
- Authorization to modify `backfill_daily_prices.py`
- Design review for the chosen enforcement method (warning vs hard-block)
- Tests for the enforcement path

---

## 7. Lock Safety Summary

| Check | Verdict |
|---|---|
| Lock acquisition | VERIFIED |
| Lock ownership (parent only) | VERIFIED |
| Lock scope covers pipeline | VERIFIED |
| Lock release in finally | VERIFIED |
| No parent/child deadlock | VERIFIED (backfill has no locks) |
| Crash recovery (OS releases) | VERIFIED (POSIX) |
| Duplicate scheduler blocked | VERIFIED (IT-16) |
| Direct backfill bypass | **DIRECT_ENTRY_GAP_REMAINS** |
| Hard-block on direct entry | NOT AUTHORIZED (requires backfill modification) |

**Deployment gate**: This gap must be explicitly acknowledged (or closed) before production deployment.
