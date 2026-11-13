# Session 71M — Lock Protocol

**Session**: 71M  
**Verdict**: `LOCK_SAFETY_VERIFIED`

---

## Lock Architecture (Complete Picture)

```
Wrapper (hybrid_shadow_cron_integrated.py)
  └── Step 1: fcntl.LOCK_EX on data/.cron.lock (BlockingIOError → BLOCKED_LOCK)
  └── Step 4: subprocess → backfill_daily_prices_guarded.py --execute
                └── _get_cron_lock_path() → data/.cron.lock (same file)
                └── check_original_entry(lock_path=data/.cron.lock)
                    └── _check_lock_state():
                        └── open(data/.cron.lock, 'a')
                        └── flock(LOCK_EX | LOCK_NB) → BlockingIOError
                        └── → lock IS held → AUTHORIZED
  └── finally: fcntl.LOCK_UN
```

---

## Deadlock Analysis

**Q: Does `_check_lock_state()` cause deadlock when wrapper holds the lock?**

No. The key: `LOCK_NB` (non-blocking).

```
Wrapper: flock(lock_fd, LOCK_EX)      ← holds lock
Backfill: flock(test_fd, LOCK_EX | LOCK_NB) → BlockingIOError (immediately)
```

`LOCK_NB` means "fail immediately if can't acquire" — it does NOT block. `BlockingIOError` is caught and interpreted as "lock is held" → AUTHORIZED. No spin-wait, no deadlock.

**Q: What if backfill accidentally acquires the lock?**

If `_check_lock_state()` succeeds in acquiring LOCK_EX (meaning the wrapper is NOT running):
1. Backfill immediately releases: `flock(LOCK_UN)`
2. Returns `(False, "lock not held")` → UNAUTHORIZED
3. Backfill exits with code 2

The lock is released in < 1ms. No persistent lock is taken by the backfill guard.

---

## Lock File Integrity

**File**: `data/.cron.lock`

- Never truncated (opened with `'a'` mode, not `'w'`)
- Never deleted by backfill guard
- Never used for data storage (zero-byte lock file is valid)
- Release in `finally` block of wrapper (exception-safe)

---

## Concurrent Invocation Scenarios

| Scenario | Outcome |
|---|---|
| Wrapper running → backfill subprocess | Authorized (lock held) ✓ |
| No wrapper → backfill direct | Unauthorized (lock not held) ✓ |
| Wrapper running → second wrapper | BLOCKED_LOCK (wrapper FileLock) ✓ |
| Wrapper running → direct protected.py | Authorized (env var check) ✓ |
| No wrapper → direct guarded.py | Unauthorized (lock not held) ✓ |

---

## Test Coverage

- M-09: Concurrent wrapper blocked by lock ✓
- M-10: Wrapper lock held → guarded backfill authorized ✓
- M-11: LOCK_NB prevents deadlock (structural) ✓
- M-12: Lock IS held → check_original_entry returns AUTHORIZED ✓
- IT-15 (S71K): Lock file → wrapper blocked ✓
- IT-16 (S71K): External lock → wrapper BLOCKED_LOCK ✓
- IT-17 (S71K): Lock released in finally block ✓
- L-03 (S71L): Backfill has zero file locks ✓
