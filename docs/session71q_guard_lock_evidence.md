# Session 71Q — Guard & FileLock Evidence

**Session**: 71Q  
**Verdict**: `GUARD_AUTHORIZED_CONFIRMED`  
**Updated**: 2026-11-13 16:35 CST

---

## Guard Runtime Evidence (2026-11-13 16:00 CST)

**GUARD AUTHORIZED — CONFIRMED**

| Evidence Item | Value | Source |
|---|---|---|
| Backfill script called by wrapper | ✓ | Log: `[backfill] Running: .../backfill_daily_prices.py --execute` |
| `[BACKFILL_GUARD] BLOCKED` in log | **ABSENT** | Grep result: `NO_GUARD_BLOCK_MESSAGE_FOUND` |
| Backfill exit code | 0 | Log: `Done (exit=0) ✓` |
| FileLock state in state file | `"lock": "acquired"` | `data/.cron_state.json` |
| Backfill ran (not short-circuited) | ✓ | QG evaluation occurred (dates evaluated) |

**Authorization Proof**: The wrapper holds `fcntl.flock(LOCK_EX)` during the entire run. When the guarded backfill subprocess calls `fcntl.flock(LOCK_EX | LOCK_NB)` on the same lock, it gets `BlockingIOError` → `AUTHORIZED`. The absence of `[BACKFILL_GUARD] BLOCKED` and the presence of QG evaluation logs confirm the guard authorized execution.

**Deploy A Runtime Status**: `DEPLOY_A_GUARD_AUTHORIZED` ✓

---

## Guard Readiness Verification (Pre-trigger)

| Check | Result |
|---|---|
| `backfill_daily_prices.py` is guarded version | ✓ Hash `202e2231...` |
| `BackfillEntryGuard.check_original_entry()` importable | ✓ IMPORT_OK |
| `_check_lock_state()` available | ✓ |
| Lock path verified | `/Users/alicetu/.../data/.cron.lock` |
| Lock not currently held | ✓ LOCK_NOT_HELD (verified at 01:35 CST) |
| Cross-process lock proof | N-lock-01 test (S71N) ✓ |
| Monitor processes hold lock? | NO — read-only tail only |

---

## Expected Guard Behavior When Cron Fires

When `0 16 * * 1-5` triggers `hybrid_shadow_cron.py --execute`:

1. Wrapper acquires `fcntl.flock(LOCK_EX)` on `data/.cron.lock`
2. Wrapper calls `subprocess.run(backfill_daily_prices.py --execute)`
3. Guarded backfill calls `BackfillEntryGuard.check_original_entry(is_execute=True, lock_path=...)`
4. Guard attempts `fcntl.flock(LOCK_EX | LOCK_NB)` on same lock
5. Lock is held by wrapper → `BlockingIOError` → Guard returns `AUTHORIZED`
6. Backfill proceeds to QG evaluation

No `CALLED_FROM_WRAPPER=1` env var is needed — lock-based detection is sufficient.

---

## Unexpected Guard Behaviors to Watch For

| Scenario | Indicator | Action |
|---|---|---|
| Guard unexpectedly BLOCKS cron | Exit code 2 in log / "BACKFILL_GUARD BLOCKED" in log | Record as `GUARD_RUNTIME_FAILURE` |
| Lock contention | "LOCK_CONFLICT" or timeout in log | Record with timestamps |
| Parent/child deadlock | Wrapper hangs > 10 min | Record, do not force-kill |
| Unexpected maintenance override | "MAINTENANCE" in log without user action | Record as anomaly |

---

## S71P Guard Rejection Test (reference)

For comparison — from S71P post-deployment test without lock held:

```
[BACKFILL_GUARD] BLOCKED: UNAUTHORIZED: lock not held at .../data/.cron.lock.
Use hybrid_shadow_cron.py --execute for production runs.
For maintenance: set BACKFILL_ALLOW_DIRECT=1 and BACKFILL_MAINTENANCE_REASON.
[BACKFILL_GUARD] No data was read or written.
Exit code: 2
```

This confirms the guard fires correctly. When cron wrapper holds the lock, the guard should produce NO such blocking message.
