# Session 71M — Regression Comparison

**Session**: 71M  
**Verdict**: `ZERO_NEW_REGRESSIONS_VERIFIED`

---

## Test Suite Delta

| Metric | S71L Baseline | S71M Result | Delta |
|---|---|---|---|
| Passed | 4,422 | **4,452** | +30 |
| Failed | 37 | **37** | 0 |
| Skipped | 4 | 4 | 0 |
| New tests added | — | 30 | +30 |

**4422 + 30 = 4452 ✓**

---

## Pre-existing Failures (Unchanged)

The 37 failing tests are all in RC-2 era session tests (since S66). Root cause: tests check `backfill_daily_prices.py` hash against pre-RC-2 value. The hash didn't change in S71M (production file untouched), so these failures remain exactly as before.

---

## Production Hash Verification

| File | Pre-S71M Hash | Post-S71M Hash | Match? |
|---|---|---|---|
| `scripts/hybrid_shadow_cron.py` | `46209171...` | `46209171...` | ✓ IDENTICAL |
| `scripts/backfill_daily_prices.py` | `4eb6eacf...` | `4eb6eacf...` | ✓ IDENTICAL |

---

## Modified Files Summary

| File | Change | Old → New |
|---|---|---|
| `scripts/scheduler_safety_guards.py` | Additive (new methods) | `00304d34...` → new hash |
| `scripts/hybrid_shadow_cron_integrated.py` | Additive (guarded preference) | `6ae4476c...` → new hash |
| `scripts/backfill_daily_prices_guarded.py` | NEW file | — → `202e2231...` |
| `tests/test_session71m_entry_guard.py` | NEW test file | — → 30/30 PASS |

**SQLite**: 534,770 rows, max=2026-11-05 ✓ UNCHANGED
