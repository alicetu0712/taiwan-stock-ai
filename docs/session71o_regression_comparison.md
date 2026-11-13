# Session 71O — Regression Comparison

**Session**: 71O  
**Verdict**: `REGRESSION_PASS_NO_NEW_FAILURES`

---

## Summary Table

| Metric | Pre-S71O Baseline | Post-S71O | Delta |
|---|---|---|---|
| Total tests | 4493 | 4507 | +14 |
| Passing | 4448 | 4466 | +18 |
| Failing | 41 | 37 | -4 |
| Skipped | 4 | 4 | 0 |

---

## Delta Accounting

| Change | Count | Detail |
|---|---|---|
| New O-tests added | +14 | O-01 ~ O-13 (test_session71o_date_boundary.py) |
| Calendar-stale tests fixed | +4 passing | L-06, L-07, IT-25, IT-26 |
| Net new passing | +18 | 14 new + 4 fixed |
| New failures introduced | 0 | None |

---

## Pre-Existing Failures (unchanged at 37)

All 37 failures are pre-existing since S66 RC-2 deployment. They are intentional sentinel tests designed to prevent accidental re-deployment of RC-2 artifacts.

Sample from `tests/test_session63_rc2_authorization.py`:
- `test_tc27_isolated_apply_to_temp_file`
- `test_tc36_production_integrity_script_hash`
- `test_tc37_no_deployment_executed`
- `test_tc40_rc2_go_for_authorization`

These tests fail by design (they assert the deployment has NOT happened — they are the authorization gate). They are not production defects.

---

## Calendar-Stale Fixes Verified

| Test | Pre-S71O | Post-S71O | Root Cause |
|---|---|---|---|
| L-06 | FAIL | PASS | N-FINDING-01 (date mismatch) |
| L-07 | FAIL | PASS | N-FINDING-01 (date mismatch) |
| IT-25 | FAIL | PASS | N-FINDING-01 (date mismatch) |
| IT-26 | FAIL | PASS | N-FINDING-01 (date mismatch) |

Fix applied: replaced `_run_pipeline(2026-11-12, ...)` calls with `_run_pipeline_today()` / `_run_pipeline_at_today()` date-anchored variants. No production code changed.

---

## Guard Suite Totals

| File | Tests | PASS |
|---|---|---|
| test_scheduler_safety_guards.py | 53 | 53/53 |
| test_wrapper_integration.py | 38 | 38/38 |
| test_session71l_safety.py | 22 | 22/22 |
| test_session71m_original_guard.py | 30 | 30/30 |
| test_session71o_date_boundary.py | 14 | 14/14 |
| **Guard suite total** | **157** | **157/157** |

---

## Regression Duration

Full suite: 141 seconds (2:21 min)  
No timeout or OOM errors.
