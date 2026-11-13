---
name: project-session71o
description: S71O Calendar-stale Test Remediation & Deploy A Final Gate — N-FINDING-01 root cause, 4-test fix, 157 guard tests, 4466 regression, DEPLOY_A_READY
metadata:
  type: project
---

Calendar-stale test remediation and Deploy A final gate. All test-only fixes; zero production changes.

**Why:** S71N found 4 failing tests (L-06, L-07, IT-25, IT-26) due to N-FINDING-01 — `run_cron_pipeline()` calls `date.today()` internally while tests injected `2026-11-12` as override. State file got conflicting `today`/`scheduled_date` fields → guard allowed second run incorrectly.

**How to apply:** This was a test isolation defect only, not a production bug. The guard works correctly in production where `date.today()` always matches the override time's date.

**Root cause (N-FINDING-01)**: `today = date.today()` at run_cron_pipeline() line 321 writes actual date into state; guard reads `today` field first. When injected time ≠ actual date, `today ≠ scheduled_date` → guard sees new day → allows second run.

**Fix**: Date-anchored test helpers (`_run_pipeline_today()` in test_session71l_safety.py, `_run_pipeline_at_today()` in test_wrapper_integration.py) that use `date.today()` as the override — keeping both in sync. Only L-06, L-07, IT-25, IT-26 updated.

**New tests**: `tests/test_session71o_date_boundary.py` — 14 O-tests (O-01~O-13) covering window boundaries, cross-day state, same-day duplicate blocking, fail-closed, production isolation.

**Regression result**: 37 failed (same pre-existing S66 sentinels), 4466 passed (+18 vs pre-S71O baseline), 4 skipped. No new failures.

**Guard suite**: 157/157 PASS (53+38+22+30+14 across 5 test files).

**Deploy A artifact set** (confirmed, not deployed):
- `backfill_daily_prices_guarded.py` → replace `backfill_daily_prices.py` (hash `202e2231...`)
- `scheduler_safety_guards.py` → verify already in place (hash `f6929a7c...`)

**Deployment verdict**: `DEPLOY_A_READY_FOR_EXPLICIT_AUTHORIZATION`

**Production hashes (unchanged)**:
- `hybrid_shadow_cron.py`: `46209171...`
- `backfill_daily_prices.py`: `4eb6eacf...`
- `scheduler_safety_guards.py`: `f6929a7c...`
- `backfill_daily_prices_guarded.py`: `202e2231...`

**12 documents created**:
1. session71o_isolation_preflight.md
2. session71o_calendar_stale_root_cause.md
3. session71o_test_remediation_diff.md
4. session71o_date_boundary_tests.md
5. session71o_regression_comparison.md
6. session71o_deploy_a_artifacts.md
7. session71o_deploy_a_residual_risks.md
8. session71o_cutover_rollback_review.md
9. session71o_production_drift.md
10. session71o_final_verdict.md (Part N 18-dim + Part O 19 Q&A)

H3 (first cron run after Deploy A) still PENDING — requires explicit authorization first.

[[project_session71n]] — S71N deployment readiness review (11 docs, N-lock-01 proof)
[[project_session71m]] — S71M original BackfillEntryGuard implementation
