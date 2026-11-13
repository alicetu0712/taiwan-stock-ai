# Session 71O — Date Boundary Tests

**Session**: 71O  
**File**: `tests/test_session71o_date_boundary.py`  
**Verdict**: `DATE_BOUNDARY_TESTS_PASS` (14/14)

---

## Test Inventory

| ID | Test | Category | Expected | Result |
|---|---|---|---|---|
| O-01 | `test_O01_fixed_nov12_deterministic` | Fixed date | `scheduled_date = 2026-11-12` | ✓ PASS |
| O-02 | `test_O02_fixed_nov13_deterministic` | Fixed date | `scheduled_date = 2026-11-13` | ✓ PASS |
| O-03 | `test_O03_system_date_does_not_affect_fixed_date_result` | System date isolation | Both runs produce `scheduled_date = 2026-11-12` | ✓ PASS |
| O-04 | `test_O04_1559_cst_rejected` | Window boundary | 15:59 → `GUARD_WINDOW_PRE_SCHEDULE` | ✓ PASS |
| O-05 | `test_O05_1600_cst_allowed` | Window boundary | 16:00 → no window guard | ✓ PASS |
| O-06 | `test_O06_1959_cst_allowed` | Window boundary | 19:59 → no window guard | ✓ PASS |
| O-07 | `test_O07_2000_cst_rejected` | Window boundary | 20:00 → `GUARD_WINDOW_EXECUTION_WINDOW_EXPIRED` | ✓ PASS |
| O-07b | `test_O07b_window_unit_check_execution_window` | Window unit | 15:59 reject / 16:00 allow / 20:00 reject | ✓ PASS |
| O-08 | `test_O08_cross_day_state_allows_new_run` | Cross-day state | Yesterday's state → today's run ALLOWED | ✓ PASS |
| O-09 | `test_O09_same_day_success_state_blocks` | Same-day duplicate | SUCCESS state → `ALREADY_RAN_TODAY` | ✓ PASS |
| O-10 | `test_O10_same_day_write_committed_blocks` | Same-day duplicate | `write_committed=True` → `GUARD_STATE_WRITE_COMMITTED_TODAY` | ✓ PASS |
| O-11 | `test_O11_corrupt_state_fail_closed` | Fail closed | Corrupt JSON → `FAIL_CLOSED_CORRUPT` | ✓ PASS |
| O-12 | `test_O12_naive_datetime_fail_closed` | Fail closed | Naive datetime → not allowed | ✓ PASS |
| O-13 | `test_O13_production_state_untouched` | Isolation | Production state file mtime unchanged | ✓ PASS |

---

## O-10 Deploy B Annotation

O-10 (`same_day_write_committed_blocks`) explicitly annotates that `WRITE_COMMITTED_TODAY` protection is **only active under Deploy B** (integrated wrapper). Deploy A (original wrapper) does not write `write_committed=True` to state file. The test passes because it uses `run_cron_pipeline()` from `hybrid_shadow_cron_integrated.py`, which is the Deploy B wrapper.

This is correctly documented in the test docstring:
```python
"""O-10: write_committed=True in same-day state → second run rejected.

Only active under Deploy B (integrated wrapper writes write_committed).
Deploy A (original wrapper) does not write this field.
"""
```

---

## Notes on O-03

O-03 verifies that two sequential runs with the same fixed date (2026-11-12) always produce `scheduled_date='2026-11-12'`. It does **not** assert that the second run is blocked (because it may or may not be blocked depending on whether `date.today()` happens to be 2026-11-12). This test is calendar-safe by design.
