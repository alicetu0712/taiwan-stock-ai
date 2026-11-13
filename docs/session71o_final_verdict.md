# Session 71O — Final Verdict

**Session**: 71O  
**Execution Mode**: `ISOLATED_TEST_REMEDIATION / OFFLINE_VERIFICATION / NO_PRODUCTION_DEPLOYMENT`  
**Maximum Outcome**: `DEPLOY_A_READY_FOR_EXPLICIT_AUTHORIZATION`

---

## Part N — 18-Dimension Verdict

### Dimension 1 — Calendar-Stale Root Cause

**Verdict**: `ROOT_CAUSE_VERIFIED`

N-FINDING-01 (discovered in S71N): `run_cron_pipeline()` calls `date.today()` for the `today` field while tests inject `_taipei(2026, 11, 12, ...)` as `_now_taipei_override`. State file gets `today='2026-11-13'` (actual) but `scheduled_date='2026-11-12'` (from override). `SameDayStateGuard.check()` reads `today` first → mismatch → incorrectly ALLOWS second run.

Confirmed as **test isolation defect only** — not a production bug.

---

### Dimension 2 — Production Bug Assessment

**Verdict**: `NOT_A_PRODUCTION_BUG`

In production, `date.today()` and `_now_taipei_override.date()` are always identical (cron runs at current wall-clock time). The mismatch only occurs in tests that inject a past date. Guard behavior is correct for production use case.

---

### Dimension 3 — Fix Correctness

**Verdict**: `FIX_CORRECT`

New date-anchored helpers (`_run_pipeline_today()`, `_run_pipeline_at_today()`) use `date.today()` for the override — keeping both values in sync. Only 4 tests use them (L-06, L-07, IT-25, IT-26). All other tests unchanged.

No xfail or skip markers introduced. Assertions unchanged — tests still assert the same guard conditions.

---

### Dimension 4 — IT-27 Non-Interference

**Verdict**: `IT_27_UNAFFECTED`

IT-27 pre-writes a hardcoded `scheduled_date="2026-11-12"` state file, then checks that the second run detects it as stale (old state ≠ today). IT-27 continues to use the original `_run_pipeline_at` correctly, because it relies on date mismatch by design.

---

### Dimension 5 — Guard Suite Totals

**Verdict**: `GUARD_SUITE_157_157_PASS`

| File | Tests | PASS |
|---|---|---|
| test_scheduler_safety_guards.py | 53 | 53 |
| test_wrapper_integration.py | 38 | 38 |
| test_session71l_safety.py | 22 | 22 |
| test_session71m_original_guard.py | 30 | 30 |
| test_session71o_date_boundary.py | 14 | 14 |
| **Total** | **157** | **157** |

---

### Dimension 6 — Full Regression

**Verdict**: `REGRESSION_PASS_NO_NEW_FAILURES`

| Metric | Pre-S71O | Post-S71O | Delta |
|---|---|---|---|
| Passing | 4448 | 4466 | +18 |
| Failing | 41 | 37 | -4 |
| Total | 4493 | 4507 | +14 |

37 remaining failures are pre-existing since S66 (sentinel tests, fail by design). No new failures.

---

### Dimension 7 — O-Tests (Date Boundary)

**Verdict**: `DATE_BOUNDARY_TESTS_14_14_PASS`

14 tests (O-01~O-13) covering: fixed date determinism, execution validity window boundaries, same-day state guard (date-anchored), fail-closed behavior, production isolation. All 14/14 PASS.

---

### Dimension 8 — Deploy A Artifact Set

**Verdict**: `DEPLOY_A_TWO_FILES_VERIFIED`

Deploy A = 2 files:
1. `backfill_daily_prices_guarded.py` (replace production backfill) — hash `202e2231...`
2. `scheduler_safety_guards.py` (verify already in place) — hash `f6929a7c...`

File 2 is already deployed; Deploy A verifies its hash has not drifted before activating File 1.

---

### Dimension 9 — Entry Guard Mechanism

**Verdict**: `ENTRY_GUARD_VERIFIED`

Lock-based authorization: `_check_lock_state()` attempts `fcntl.flock(LOCK_EX | LOCK_NB)`. When cron wrapper holds the lock, subprocess gets `BlockingIOError` → AUTHORIZED. Cross-process proof: N-lock-01 test (S71N). Two-key maintenance override verified.

---

### Dimension 10 — Production Code Unchanged

**Verdict**: `ZERO_PRODUCTION_DRIFT`

All 4 production hashes identical to S71N baseline. Only test files modified. No `scripts/` files touched.

---

### Dimension 11 — RC-2 Filter Preservation

**Verdict**: `RC2_FILTER_UNCHANGED`

`_is_excluded()` and `EXCLUDE_KEYWORDS` in `backfill_daily_prices.py` unchanged since S66. AST-verified in S71N. Not touched in S71N or S71O.

---

### Dimension 12 — Quality Gate Preservation

**Verdict**: `QG_PRESERVED`

Quality Gate logic in `backfill_daily_prices.py` unchanged. No guard modifications affect QG evaluation. Verified in S71N; confirmed not touched in S71O.

---

### Dimension 13 — Atomic Cutover Design

**Verdict**: `ATOMIC_CUTOVER_DESIGN_VERIFIED`

`cp → /tmp/backfill_daily_prices.py.new` then `mv` on APFS = kernel-level `rename(2)` syscall. Atomic single-file replacement. No partial-state window. Detailed in S71N (session71n_atomic_cutover_plan.md). No changes required from S71N.

---

### Dimension 14 — Rollback Plan

**Verdict**: `ROLLBACK_VERIFIED`

Restore `backfill_daily_prices.py` to hash `4eb6eacf...`. Guard module (`scheduler_safety_guards.py`) does not need rollback — backward-compatible. Detailed in S71N (session71n_rollback_runbook.md). No changes in S71O.

---

### Dimension 15 — Scheduler Migration Separation

**Verdict**: `SCHEDULER_MIGRATION_INDEPENDENT`

Deploy A does not involve launchd migration. launchd migration (S71G–S71H design) is a separate Deploy C sequence that requires independent authorization. No launchd changes in S71N or S71O.

---

### Dimension 16 — Isolation Compliance

**Verdict**: `ISOLATION_FULLY_COMPLIANT`

All test runs use `tmp_path`. No production SQLite/Neon writes. No TWSE/TPEx HTTP calls. No `.env` loaded. Production state file mtime unchanged (O-13 PASS). No launchd changes.

---

### Dimension 17 — Deploy B Separation

**Verdict**: `DEPLOY_B_CORRECTLY_SEPARATED`

`hybrid_shadow_cron_integrated.py` is NOT deployed in Deploy A. It was implemented and tested in S71K–S71L but requires separate authorization (Deploy B). `write_committed=True` protection is Deploy B only — correctly annotated in O-10 test docstring.

---

### Dimension 18 — Overall Deployment Readiness

**Verdict**: `DEPLOY_A_READY_FOR_EXPLICIT_AUTHORIZATION`

All 18 dimensions PASS or VERIFIED. No production bugs found. No regressions introduced. Artifact set confirmed. Cutover and rollback plans verified. The only remaining gate is explicit user authorization.

---

## Part O — Executive Summary (19 Q&A)

**Q1: What was the goal of Session 71O?**  
Fix 4 calendar-stale test failures (N-FINDING-01) discovered in S71N, verify no production bugs were masked, run full guard suite + regression, and confirm Deploy A readiness for explicit authorization.

**Q2: What is N-FINDING-01?**  
`run_cron_pipeline()` calls `date.today()` for the internal `today` field. Tests that inject `_taipei(2026, 11, 12, ...)` as the override time write `today='2026-11-13'` (actual date) but `scheduled_date='2026-11-12'` (from override). `SameDayStateGuard.check()` reads `today` first → sees mismatch → incorrectly allows second run.

**Q3: Is N-FINDING-01 a production bug?**  
No. In production, `date.today()` and `_now_taipei_override.date()` are always the same (cron runs at current wall-clock time). The mismatch only occurs in tests that inject a fixed past date as the override.

**Q4: What was the fix?**  
Two new date-anchored test helpers (`_run_pipeline_today()` in `test_session71l_safety.py` and `_run_pipeline_at_today()` in `test_wrapper_integration.py`) that use `date.today()` as the override date — keeping both values in sync. Only 4 tests (L-06, L-07, IT-25, IT-26) were updated to use these helpers.

**Q5: Were any production scripts modified?**  
No. Zero changes to any file in `scripts/`. Only test files were modified.

**Q6: What is the guard suite total?**  
157/157 PASS across 5 test files (53+38+22+30+14).

**Q7: What is the full regression result?**  
37 failed (pre-existing since S66, sentinel tests by design), 4466 passed, 4 skipped. 4 previously failing tests (L-06, L-07, IT-25, IT-26) are now PASSING. 14 new O-tests added.

**Q8: Are there any new test failures?**  
No. The 37 remaining failures are identical to the pre-existing S66 baseline. No regression introduced.

**Q9: What are the O-tests?**  
14 new date boundary tests (O-01~O-13) covering: fixed date determinism, execution validity window boundaries (15:59/16:00/19:59/20:00), same-day state guard using date-anchored helpers, fail-closed behavior (corrupt state, naive datetime), and production isolation verification.

**Q10: What is Deploy A exactly?**  
Replace `scripts/backfill_daily_prices.py` (hash `4eb6eacf...`) with `scripts/backfill_daily_prices_guarded.py` (hash `202e2231...`) using an atomic `cp/mv` procedure. Also verify `scheduler_safety_guards.py` (hash `f6929a7c...`) is already in place. 2 files total.

**Q11: Why does Deploy A require 2 files?**  
`backfill_daily_prices_guarded.py` imports `BackfillEntryGuard` from `scheduler_safety_guards`. The guard module must be verified as present and at the correct hash before the guarded backfill is activated.

**Q12: How does the entry guard authorize cron-initiated backfill runs?**  
`_check_lock_state()` attempts `fcntl.flock(LOCK_EX | LOCK_NB)`. When the cron wrapper holds the lock, the subprocess gets `BlockingIOError` → guard returns AUTHORIZED. Direct operator invocations (without the wrapper's lock) are BLOCKED. Cross-process behavior proven by N-lock-01 test.

**Q13: How is maintenance override handled?**  
Two-key requirement: both `BACKFILL_ALLOW_DIRECT=1` AND `BACKFILL_MAINTENANCE_REASON=<non-empty>` must be set. Single-key returns `MAINTENANCE_AUTHORIZATION_INCOMPLETE`.

**Q14: Is the RC-2 filter preserved?**  
Yes. `_is_excluded()` and `EXCLUDE_KEYWORDS` in `backfill_daily_prices.py` unchanged since S66. AST-verified in S71N. Not touched in S71N or S71O.

**Q15: What is the rollback plan?**  
Restore `backfill_daily_prices.py` to hash `4eb6eacf...`. `scheduler_safety_guards.py` does not need rollback — it is backward-compatible with the original backfill.

**Q16: What are the residual risks?**  
R-01: Lock-based authorization covers execute path only (dry-run bypasses guard by design). R-02: `write_committed=True` protection absent under Deploy A. R-03: Single-node lock (not distributed). R-04: Hash drift window between verification and cutover (seconds). R-05: OSError → fail-closed (conservative). R-06: Two-key maintenance requirement may surprise operators.

**Q17: Does H3 acceptance change with S71O?**  
No. H3 (first cron run after Deploy A: guard fires correctly, backfill completes, SQLite advances) remains the acceptance criterion. H3 is PENDING. It was last awaited at the 2026-11-12 16:00 CST window; scheduler sleep was confirmed as the reason it was missed.

**Q18: What is NOT included in Deploy A?**  
launchd migration (Deploy C), `hybrid_shadow_cron_integrated.py` deployment (Deploy B), `write_committed=True` protection, scheduler migration.

**Q19: What is the final deployment verdict?**  
`DEPLOY_A_READY_FOR_EXPLICIT_AUTHORIZATION` — all 18 audit dimensions PASS, 157/157 guard tests PASS, full regression shows no new failures. Explicit user authorization required before any production file changes.
