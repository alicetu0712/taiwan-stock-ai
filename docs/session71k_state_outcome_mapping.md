# Session 71K — State & Outcome Mapping

**Session**: 71K  
**Component**: Write outcome tracking in `hybrid_shadow_cron_integrated.py`

---

## 1. Outcome Mapping Table

| Actual Event | `result["status"]` | `write_committed` | State Guard Retry? | Evidence |
|---|---|---|---|---|
| Window guard reject (pre-schedule) | `GUARD_WINDOW_PRE_SCHEDULE` | not set | N/A — no state | No lock, no state save |
| Window guard reject (expired) | `GUARD_WINDOW_EXECUTION_WINDOW_EXPIRED` | not set | N/A — no state | No lock, no state save |
| Window guard reject (naive datetime) | `GUARD_WINDOW_FAIL_CLOSED_NAIVE_TIME` | not set | N/A | Fail-closed |
| State guard reject (already success) | `GUARD_STATE_ALREADY_RAN_TODAY` | not set | NO | Same day SUCCESS |
| State guard reject (write committed) | `GUARD_STATE_WRITE_COMMITTED_TODAY` | True (prior) | NO | SQLite already written |
| State guard reject (concurrent run) | `GUARD_STATE_CONCURRENT_RUN` | not set | NO (wait for release) | PID alive |
| State guard reject (unknown crash) | `GUARD_STATE_WRITE_OUTCOME_UNKNOWN` | unknown | NO (manual review) | PID dead; crash |
| State guard reject (corrupt state) | `GUARD_STATE_FAIL_CLOSED_CORRUPT` | unknown | NO (manual review) | JSON corrupt |
| Lock reject | `BLOCKED_LOCK` | not set | YES (after release) | Another process holds lock |
| Non-trading day | `SKIPPED_NON_TRADING_DAY` | not set | N/A | Calendar check |
| Data not ready (dry-run only) | `DATA_NOT_READY` | not set | N/A | <15:30 CST |
| Backfill subprocess failed (exit!=0) | `BACKFILL_FAILED` | False | YES | exit_code != 0 |
| Dry-run complete | `DRY_RUN_OK` | not set | N/A | execute=False |
| Freshness STALE (after retries) | `BLOCKED_STALE_DATA` | False | YES (next window) | TWSE not ready |
| Freshness PARTIAL (after retries) | `BLOCKED_PARTIAL_MARKET` | False | YES (next window) | Partial market |
| Freshness FULL_MARKET_FRESH | (proceeds to Step 5) | **True** | NO (data written) | WRITE_COMMITTED set |
| Shadow failed (after write) | `SHADOW_FAILED` | **True** | NO (don't re-write) | Shadow exit!=0 |
| Full success | `SUCCESS` | **True** | NO | Pipeline complete |
| Unknown crash (PID dead, RUNNING) | `RUNNING` (stale state) | False or unknown | WRITE_OUTCOME_UNKNOWN | Manual recovery |

---

## 2. Write-committed Semantics

`write_committed=True` is set **at the moment `check_market_freshness()` returns `FULL_MARKET_FRESH`**, which is the best available proxy for "SQLite INSERT has been committed."

### Why this is the correct proxy:

The pipeline flow after backfill subprocess exits 0:
1. Backfill runs → SQLite INSERT OR IGNORE for each passing QG date
2. Wrapper calls `check_market_freshness()` → queries SQLite for `0050` and 5000+ stocks on today
3. If FULL_MARKET_FRESH: data IS in SQLite (the check reads it directly)
4. Set `write_committed=True`

If backfill exits 0 but QG blocked all dates:
- `check_market_freshness()` returns PROVIDER_NOT_READY or STALE (not FULL_MARKET_FRESH)
- `write_committed` is NOT set to True
- Retry is allowed

### Cannot determine write from exit code alone:

`backfill_daily_prices.py` exits 0 for BOTH:
- Scenario A: data written (QG passed, INSERT succeeded)
- Scenario B: data NOT written (QG-5 blocked all dates)

This is why `write_committed` is based on `FULL_MARKET_FRESH`, not `exit_code == 0`.

---

## 3. P0 Verification: "SQLite Written But Post-write Check Failed"

**Scenario**: Freshness PASS → `write_committed=True` → Shadow runner FAILS → `SHADOW_FAILED`.

Expected: Second invocation sees `write_committed=True` → blocked.

**Test IT-21** verifies this:
```python
def test_IT21_shadow_fail_after_write_committed(tmp_path):
    result = _run_pipeline_at(tmp_path, hour=16, shadow=_shadow_fail())
    assert result["status"] == "SHADOW_FAILED"
    assert result.get("write_committed") is True

# Second invocation:
def test_IT10_post_write_check_failed_with_write_committed_still_blocks(tmp_path):
    # State has status=SHADOW_FAILED + write_committed=True
    result2 = _run_pipeline_at(tmp_path, hour=17)
    assert "WRITE_COMMITTED_TODAY" in result2["status"]
```

**Both tests PASS. P0 condition VERIFIED.**

---

## 4. State Transition Sequence (Successful Run)

```
t=0  window guard check         → result.status = (not set yet)
t=1  lock acquired               → result.steps.lock = "acquired"
t=2  same-day guard check        → result.steps.same_day_guard = "ALLOWED"
t=3  RUNNING written to state    → state.status = "RUNNING" (VERIFIED by IT-14)
t=4  calendar check              → result.steps.calendar = "trading_day"
t=5  data readiness check        → result.steps.data_ready = True
t=6  backfill subprocess         → result.steps.backfill = {exit_code: 0}
t=7  freshness check → PASS      → result.write_committed = True
t=8  WRITE_COMMITTED written     → state.write_committed = True
t=9  backup                      → result.steps.backup = "..."
t=10 shadow runner               → result.steps.shadow = {exit_code: 0}
t=11 SUCCESS written             → state.status = "SUCCESS"
t=12 lock released               → result.steps.lock = "released"
```

---

## 5. Write Outcome Determination Gap

### WRITE_OUTCOME_UNVERIFIED scenarios (cannot determine):

| Scenario | Cannot determine because |
|---|---|
| Crash after INSERT but before `check_market_freshness()` completes | Freshness check didn't return FULL_MARKET_FRESH |
| OOM kill between INSERT and commit | Atomicity depends on SQLite WAL mode |
| Partial write (some dates written, others not) | Freshness only checks FULL_MARKET_FRESH vs not |

**For production purposes**: If `write_committed=False` and `status=RUNNING` with dead PID, treat as `WRITE_OUTCOME_UNKNOWN`. Manual check required:
```bash
sqlite3 data/platform.db "SELECT date, COUNT(*) FROM daily_prices WHERE date = '2026-11-12'"
```

### Not a blocker for deployment:
The `WRITE_OUTCOME_UNKNOWN` state correctly prevents automated retry (fail-closed). Manual recovery is by design — these are rare crash scenarios.
