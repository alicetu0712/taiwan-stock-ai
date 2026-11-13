# Session 71L — Crash Window Analysis

**Session**: 71L  
**Verdict**: `CRASH_WINDOW_HANDLED_CORRECTLY`

---

## The Crash Window

```
Timeline:
  backfill subprocess running...
    └── conn.commit() [backfill line 546]   ← WINDOW OPENS (data written)
    └── backfill exits (exit code 0)
    └── wrapper receives exit code
    └── wrapper calls check_market_freshness()
    └── FULL_MARKET_FRESH confirmed
    └── result["write_committed"] = True
    └── _save_state(result)                 ← WINDOW CLOSES (state confirmed)
  
  SIGKILL anywhere in WINDOW → crash with unknown outcome
```

---

## Recovery Logic (Already Implemented)

`SameDayStateGuard.check()` handles this via the RUNNING + dead PID branch:

```python
if prior_status == RunStatus.RUNNING.value:
    if prior_pid and _pid_is_alive(prior_pid):
        return GuardCheckResult(
            allowed=False,
            guard_status=GuardStatus.CONCURRENT_RUN, ...
        )
    else:
        return GuardCheckResult(
            allowed=False,
            guard_status=GuardStatus.WRITE_OUTCOME_UNKNOWN,
            reason=(
                f"WRITE_OUTCOME_UNKNOWN: prior run (PID {prior_pid}) for "
                f"{scheduled_date} crashed. Cannot determine if SQLite was "
                f"written. Manual intervention required."
            ), ...
        )
```

**Behavior**: RUNNING + dead PID → `WRITE_OUTCOME_UNKNOWN` → `allowed=False`

This is **fail-closed**: the guard blocks any retry until a human investigates and manually clears/resets the state file. This is the correct tradeoff — a blocked retry is recoverable; a double-write is not.

---

## Why No Auto-Recovery

Auto-recovery options considered and rejected:

| Option | Problem |
|---|---|
| Auto-retry if `write_committed=False` | Cannot distinguish "wrote and crashed" from "crashed before writing" |
| Read SQLite to check row count | Adds SQLite dependency to guard; guard may run before connection available |
| Use separate crash-flag file | Complexity; another file to atomically update; same race condition at smaller scale |

**Decision**: Fail-closed with `WRITE_OUTCOME_UNKNOWN` + manual intervention is the correct policy for financial data integrity.

---

## Manual Recovery Procedure

```bash
# 1. Check if data was actually written
sqlite3 data/platform.db "SELECT date, COUNT(*) FROM daily_prices 
  WHERE date = '$(jq -r .scheduled_date data/.cron_state.json)'"

# 2a. If rows present (commit succeeded before crash):
#     Reset state to reflect actual outcome
python3 -c "
import json; p='data/.cron_state.json'
s=json.loads(open(p).read())
s['status']='WRITE_COMMITTED'; s['write_committed']=True
open(p,'w').write(json.dumps(s,indent=2))"

# 2b. If no rows (commit did not complete):
#     Reset state to allow retry
python3 -c "
import json; p='data/.cron_state.json'
s=json.loads(open(p).read())
s['status']='FAILED'; s['write_committed']=False
open(p,'w').write(json.dumps(s,indent=2))"
```

---

## Test Coverage

- **L-05**: RUNNING + dead PID → `WRITE_OUTCOME_UNKNOWN` ✓ PASS
- **L-06**: `WRITE_OUTCOME_UNKNOWN` does not auto-retry ✓ PASS
- **L-07**: `write_committed=True` blocks re-write even after shadow failure ✓ PASS
- **L-11**: RUNNING + live PID → `CONCURRENT_RUN` (not WRITE_OUTCOME_UNKNOWN) ✓ PASS
- **L-12**: Atomic state write via `os.replace` ✓ PASS
