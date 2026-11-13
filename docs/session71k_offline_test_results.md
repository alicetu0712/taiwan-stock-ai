# Session 71K — Offline Test Results

**Session**: 71K  
**New tests**: `tests/test_wrapper_integration.py`  
**Result**: 38/38 PASS (after 1-line fix to IT-14)

---

## 1. Run Environment

```
python3 -m pytest tests/test_wrapper_integration.py -v
Platform: darwin — Python 3.13.3, pytest-9.1.1
No production files touched. No TWSE/TPEx/Neon calls.
```

---

## 2. Test Results

| ID | Test | Result | Priority |
|---|---|---|---|
| IT-01 | Window: 15:59 CST → GUARD_WINDOW_PRE_SCHEDULE; lock NOT acquired | PASS | P0 |
| IT-02 | Window: 16:00 CST → allowed | PASS | P0 |
| IT-03 | Window: 20:00 CST → EXECUTION_WINDOW_EXPIRED | PASS | P0 |
| IT-04 | Window: 17:30 CST → allowed → SUCCESS | PASS | P0 |
| IT-05 | Non-trading day → SKIPPED_NON_TRADING_DAY | PASS | P1 |
| IT-06 | Window reject → state file NOT written | PASS | P0 |
| IT-07 | First run (no state) → ALLOWED → SUCCESS | PASS | P0 |
| IT-08 | Prior SUCCESS → GUARD_STATE_ALREADY_RAN_TODAY | PASS | P0 |
| IT-09 | WRITE_COMMITTED in state → second run blocked | **P0** PASS | P0 |
| IT-10 | SHADOW_FAILED + write_committed=True → blocked | **P0** PASS | P0 |
| IT-11 | QG_BLOCKED prior → retry allowed → SUCCESS | PASS | P0 |
| IT-12 | Prior day SUCCESS → today allowed | PASS | P1 |
| IT-13 | Corrupt state → GUARD_STATE_FAIL_CLOSED_CORRUPT | PASS | P0 |
| IT-14 | RUNNING written to state before backfill | PASS (after fix) | P0 |
| IT-15 | Lock acquired + released on success | PASS | P0 |
| IT-16 | Concurrent wrapper → BLOCKED_LOCK | PASS | P0 |
| IT-17 | Exception → lock released in finally | PASS | P0 |
| IT-18 | No parent/child deadlock (backfill has no locks) | PASS | P0 |
| IT-19 | QG STALE → write_committed=False | PASS | P0 |
| IT-20 | Freshness PASS → write_committed=True | PASS | P0 |
| IT-21 | Shadow fail after write → write_committed stays True | PASS | P0 |
| IT-22 | Backfill fail → write_committed=False | PASS | P0 |
| IT-23 | Dry-run → DRY_RUN_OK; write_committed not set | PASS | P1 |
| IT-24 | Full SUCCESS → state has run_id + write_committed=True | PASS | P0 |
| IT-25 | Duplicate run after SUCCESS → blocked | **P0** PASS | P0 |
| IT-26 | Cron+launchd dual trigger → second blocked | PASS | P0 |
| IT-27 | RUNNING + dead PID → WRITE_OUTCOME_UNKNOWN | PASS | P0 |
| IT-28 | Production state file not touched | PASS | P0 |
| IT-29 | Production lock file not touched | PASS | P0 |
| IT-30 | Neon URL → SAFETY_BLOCK raised | PASS | P0 |
| IT-31 | Atomic write → no .tmp residue | PASS | P1 |
| IT-32 | State contains run_id for audit | PASS | P1 |
| IT-33 | State contains no secrets | PASS | P0 |
| IT-34 | RC-2 hash unchanged (4eb6eacf...) | PASS | P0 |
| IT-35 | Production wrapper hash unchanged (46209171...) | PASS | P0 |
| IT-36 | No provider HTTP in offline tests | PASS | P0 |
| IT-37 | Production SQLite row count = 534,770 | PASS | P0 |
| IT-38 | Direct entry gap documented | PASS (gap exists) | P1 |

**Total: 38 PASSED, 0 FAILED**

---

## 3. IT-14 Fix Note

**Issue**: `result["status"]` was not updated to `"RUNNING"` before `_save_state()` was called in Step 1c.  
**Fix**: Added `"status": RunStatus.RUNNING.value` to the `result.update()` call.  
**Impact**: 1-line fix in `hybrid_shadow_cron_integrated.py`; zero production files affected.

---

## 4. P0 Test Summary

All P0 tests PASS. The P0 acceptance criteria for Session 71K:

| P0 Criterion | Test | Result |
|---|---|---|
| SQLite written + post-write fail → still blocked | IT-09, IT-10 | PASS |
| Duplicate SUCCESS on same day → blocked | IT-08, IT-25 | PASS |
| Window guard prevents late execution | IT-03, IT-06 | PASS |
| Lock prevents concurrent execution | IT-16 | PASS |
| No production files touched | IT-28, IT-29, IT-37 | PASS |
| RC-2 hash unchanged | IT-34 | PASS |
| Production wrapper unchanged | IT-35 | PASS |

---

## 5. Test Isolation Verification

| Constraint | Compliant? |
|---|---|
| Uses tmp_path for all file I/O | YES |
| Mock backfill (no subprocess) | YES |
| Mock freshness (no DB query) | YES |
| Mock clock (now_taipei_override) | YES |
| No TWSE/TPEx HTTP | YES |
| No production SQLite writes | YES |
| No Neon writes | YES |
| Repeatable offline | YES |
