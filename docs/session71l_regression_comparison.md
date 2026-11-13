# Session 71L — Regression Comparison

**Session**: 71L  
**Verdict**: `ZERO_NEW_REGRESSIONS_VERIFIED`

---

## Test Suite Delta

| Metric | S71K Baseline | S71L Result | Delta |
|---|---|---|---|
| Passed | 4,400 | **4,422** | +22 |
| Failed | 37 | **37** | 0 |
| Skipped | 4 | 4 | 0 |
| New tests added | — | 22 | +22 |

**4400 + 22 = 4422 ✓** (exact match)

---

## Pre-existing Failures (Unchanged)

The 37 failing tests are all in the RC-2 era session tests (since S66). These were failing BEFORE S71L and remain failing AFTER. None are related to S71L changes.

**Root cause**: These tests check the hash/content of `backfill_daily_prices.py` against a pre-RC-2 expected value. After RC-2 was deployed in S66, the hash changed. They are NOT defects — they document pre/post-RC-2 state.

**S71L impact**: ZERO. Neither `backfill_daily_prices.py` nor `hybrid_shadow_cron.py` was modified. The 37 failures are structurally immutable from S71L's perspective.

---

## Production Drift Verification

| File | Pre-S71L Hash | Post-S71L Hash | Match? |
|---|---|---|---|
| `scripts/hybrid_shadow_cron.py` | `46209171...` | `46209171...` | ✓ IDENTICAL |
| `scripts/backfill_daily_prices.py` | `4eb6eacf...` | `4eb6eacf...` | ✓ IDENTICAL |

---

## Modified Files (Non-production, Additive Only)

| File | Change | Tests |
|---|---|---|
| `scripts/scheduler_safety_guards.py` | Added `check_invocation()` to `BackfillEntryGuard` | 53 existing + 22 new = all pass |
| `scripts/hybrid_shadow_cron_integrated.py` | `_run_backfill()` prefers protected script | 38 existing pass |
| `scripts/backfill_daily_prices_protected.py` | NEW file | Covered by L-01/L-01b/L-04/L-18b |
| `tests/test_session71l_safety.py` | NEW test file | 22/22 PASS |

---

## Full Guard Test Suite Summary

| Test File | Tests | Result |
|---|---|---|
| `test_scheduler_safety_guards.py` | 53 | 53/53 PASS |
| `test_wrapper_integration.py` | 38 | 38/38 PASS |
| `test_session71l_safety.py` | 22 | 22/22 PASS |
| **Guard suite total** | **113** | **113/113 PASS** |
