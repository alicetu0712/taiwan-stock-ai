# Session 71L — Lock Protocol & Deadlock Safety

**Session**: 71L  
**Verdict**: `DEADLOCK_FREE_CONFIRMED`

---

## Lock Architecture

```
hybrid_shadow_cron_integrated.py
  └── Step 1: Acquire FileLock on data/.cron.lock (LOCK_EX | LOCK_NB)
        └── If LOCK_NB fails → BLOCKED_LOCK (return immediately)
        └── If acquired → proceed
              └── Step 4: subprocess _run_backfill()
                    └── backfill_daily_prices.py runs
                          └── sqlite3.connect(db_path) — zero lock acquisition
              └── Step 5: check_market_freshness()
              └── finally: FileLock.__exit__() → fcntl.LOCK_UN
```

**Key fact**: `backfill_daily_prices.py` has **zero file locks**.

```bash
# Verified by grep:
grep -n "LOCK_EX\|LOCK_NB\|flock(\|fcntl.lock" backfill_daily_prices.py
# Line 168: comment only ("# No flock needed here")
```

---

## Why No Deadlock

A deadlock requires a cycle in the lock acquisition order. Since:
1. Wrapper holds `data/.cron.lock` via `fcntl.LOCK_EX`
2. Backfill subprocess has **no lock acquisition** at all
3. Backfill subprocess has no `fcntl` calls

There is no possible lock cycle. Parent-child lock protocol is safe by design.

---

## Option C (Rejected)

Option C would have backfill acquire the same lock file. This was rejected:
- If backfill acquires `data/.cron.lock` while wrapper holds it → `BlockingIOError`
- Backfill exits with error code, zero data written
- This is a liveness failure (not a safety failure), but unacceptable

Decision: **Option B** (env var + parent PID check) for entry detection; no second lock in backfill.

---

## Test Coverage

| Test | Scenario | Result |
|---|---|---|
| L-03 | Static grep: backfill has no LOCK_EX/LOCK_NB | ✓ PASS |
| L-04 | Wrapper holds lock; direct protected execute blocked by guard (not by lock) | ✓ PASS |
| IT-15 (S71K) | Wrapper acquires lock; second wrapper blocked | ✓ PASS |
| IT-16 (S71K) | External lock holder → wrapper returns BLOCKED_LOCK | ✓ PASS |
| IT-17 (S71K) | Lock released in finally block even on exception | ✓ PASS |
