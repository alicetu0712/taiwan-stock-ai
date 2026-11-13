# Session 71J — FileLock Safety Analysis

**Session**: 71J  
**Decision**: Option A+B (soft enforcement); Option C NOT_RECOMMENDED  
**Status**: DOCUMENTED / NOT_YET_INTEGRATED

---

## 1. FileLock Architecture (Existing)

The existing `hybrid_shadow_cron.py` already holds an exclusive lock via:

```python
# hybrid_shadow_cron.py:315 (approx)
lock_fd = open(LOCK_FILE, "w")
fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
```

Lock file: `data/.cron.lock`  
Scope: Wraps the entire backfill pipeline including subprocess call.

**Existing protection**: Two concurrent wrapper invocations → second fails to acquire
lock → exits immediately without data write.

---

## 2. Option A — Wrapper-Enforced Lock (Current Behavior)

The wrapper acquires the lock *before* calling the backfill subprocess.
No change required. All production runs go through the wrapper.

| Property | Value |
|---|---|
| Lock holder | `hybrid_shadow_cron.py` (wrapper PID A) |
| Protected region | Entire pipeline including backfill subprocess |
| Deadlock risk | None (only one process holds the lock) |
| Direct bypass | Possible if `backfill_daily_prices.py` is called directly |

**Status**: Already implemented. No changes needed.

---

## 3. Option B — Backfill Direct-Invocation Warning

`BackfillEntryGuard.check_standalone_bypass()` warns when `backfill_daily_prices.py`
is called without the `CALLED_FROM_WRAPPER=1` environment variable.

This is a **soft warning**, not a hard block, because:
1. Adding a hard `LOCK_NB` to `backfill_daily_prices.py` itself would require
   modifying a production file (not authorized in S71J).
2. Even with a warning, `INSERT OR IGNORE` protects against duplicate rows.
3. The main risk is duplicate pipeline execution, not data corruption.

**Integration point** (Phase 2): Add to `backfill_daily_prices.py` entrypoint:
```python
from scripts.scheduler_safety_guards import BackfillEntryGuard
is_bypass, msg = BackfillEntryGuard.check_standalone_bypass()
if is_bypass:
    logging.warning(msg)
```

---

## 4. Option C — Lock on Backfill Process (NOT RECOMMENDED)

**Scenario**: Backfill acquires the same `.cron.lock` file independently.

**Deadlock analysis**:

```
Wrapper PID A:
  1. open(".cron.lock", "w")
  2. fcntl.flock(LOCK_EX | LOCK_NB)  ← acquires lock
  3. subprocess.run(["python3", "backfill_daily_prices.py"])
     → spawns PID B

Backfill PID B:
  1. open(".cron.lock", "w")
  2. fcntl.flock(LOCK_EX | LOCK_NB)  ← BLOCKED (wrapper holds lock!)
     → Raises BlockingIOError → pipeline exits with code 1 → 0 rows written
```

**Outcome**: Pipeline fails silently. Data is never written. QG never runs.

**Additional risk**: If Option C uses a *different* lock file (e.g., `.backfill.lock`),
it provides no protection against the dual-invocation scenario (wrapper + direct).

**Verdict**: Option C NOT_RECOMMENDED.

---

## 5. Lock File State Matrix

| Scenario | Wrapper Lock | Backfill Lock | Outcome |
|---|---|---|---|
| Normal run via wrapper | HELD by wrapper | (none) | ✓ NORMAL |
| Dual wrapper invocation | HELD by #1 | BLOCKED #2 | ✓ PROTECTED (Option A) |
| Direct backfill + wrapper | HELD by wrapper | — | ⚠ WARNING issued (Option B) |
| Direct backfill + direct backfill | (none) | (none) | ⚠ Both run; INSERT OR IGNORE protects data |
| Option C: backfill tries same lock | HELD by wrapper | BLOCKED | ✗ DATA LOSS |

---

## 6. Post-Implementation Lock File Check

```bash
# Verify lock file is not currently held
flock -n data/.cron.lock echo "Lock is free" || echo "Lock is held"

# Verify stale lock (PID check)
cat data/.cron.lock   # contains PID if populated
```

Drift check result: Lock file exists. Stale PID (prior session, not currently alive).
Production lock is NOT held.

---

## 7. Summary

| Option | Implemented | Authorized | Risk |
|---|---|---|---|
| A: Wrapper FileLock | YES (existing) | YES | None |
| B: Direct invocation warning | YES (new module) | YES | Soft warning only |
| C: Backfill acquires same lock | NOT implemented | NOT RECOMMENDED | Deadlock / data loss |

**Recommendation**: Deploy Option B warning as part of Phase 2 integration.
Hard lock on backfill subprocess requires separate design review.
