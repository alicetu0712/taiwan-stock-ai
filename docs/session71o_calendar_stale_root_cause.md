# Session 71O — Calendar-stale Root Cause Verification

**Session**: 71O  
**Verdict**: `CALENDAR_STALE_ROOT_CAUSE_VERIFIED`

---

## Affected Tests

| ID | Node ID | Failure |
|---|---|---|
| L-06 | `test_session71l_safety.py::TestCommitOutcomeAndCrashRecovery::test_L06_unknown_commit_outcome_no_auto_retry` | Expected GUARD_STATE, got SUCCESS |
| L-07 | `test_session71l_safety.py::TestCommitOutcomeAndCrashRecovery::test_L07_commit_confirmed_post_write_fail_blocks_rewrite` | Expected GUARD_STATE, got SUCCESS |
| IT-25 | `test_wrapper_integration.py::TestWriteOutcomeMapping::test_IT25_duplicate_run_after_success_blocked` | Expected ALREADY_RAN_TODAY, got SUCCESS |
| IT-26 | `test_wrapper_integration.py::TestEdgeCases::test_IT26_cron_launchd_dual_trigger_blocked` | Expected ALREADY_RAN_TODAY, got SUCCESS |

---

## Root Cause Analysis

### Source of the conflict

**`run_cron_pipeline()` line 321** (`scripts/hybrid_shadow_cron_integrated.py`):
```python
today = date.today()       # ← ACTUAL current date (e.g. 2026-11-13)
...
result["today"] = str(today)  # written to state file
```

**Test helpers** (`_run_pipeline` and `_run_pipeline_at`):
```python
now = _taipei(2026, 11, 12, hour, minute)  # ← fixed date 2026-11-12
```

**Guard derivation**:
```python
window = check_execution_window(now_taipei=now_taiwan)
# scheduled_date = now_taiwan.date() = 2026-11-12  ← from override
```

**State file after first run**:
```json
{
  "today": "2026-11-13",          ← from date.today() (actual date)
  "scheduled_date": "2026-11-12"  ← from guard using injected time
}
```

### Guard comparison on second run

`SameDayStateGuard.check()` line 283:
```python
prior_date_str = state.get("today") or state.get("scheduled_date", "")
# → reads "today" first → "2026-11-13"
```

Second run `window.scheduled_date = date(2026, 11, 12)`.

Comparison: `"2026-11-13" != "2026-11-12"` → `ALLOWED` (guard thinks it's a new day).

**Expected behavior**: Second run should be BLOCKED (same-day protection).

---

## Production Bug Assessment

**Production Bug?** `NO`

In production, `date.today()` and `now_taiwan.date()` are always the same (cron runs at current wall-clock time). The divergence only occurs in tests that inject a past date as `_now_taipei_override` while `date.today()` returns the actual current date.

The guard behavior is **correct** for the production use case. The test isolation was **insufficient**.

---

## Common Root Cause Confirmed

All 4 failures share the same root cause: `_now_taipei_override` date ≠ `date.today()`.

| Test | Fixed Date Injected | Actual Date | Mismatch |
|---|---|---|---|
| L-06 | 2026-11-12 | 2026-11-13 | ✓ same root |
| L-07 | 2026-11-12 | 2026-11-13 | ✓ same root |
| IT-25 | 2026-11-12 | 2026-11-13 | ✓ same root |
| IT-26 | 2026-11-12 | 2026-11-13 | ✓ same root |

The 4 tests were always correct on 2026-11-12 (system date == injected date). They failed when the system date advanced to 2026-11-13 and beyond.

---

## Why Other Tests Were Not Affected

Tests that use `_run_pipeline` / `_run_pipeline_at` for a **single** pipeline run (L-01~L-05, L-08~L-18, IT-01~IT-24, IT-27~IT-38) do not check same-day blocking. They either:
- Check exit codes from CLI subprocesses (L-01~L-04, M-01~M-24)
- Check the guard result after a pre-written state (IT-27, L-05, L-10~L-12)
- Do not read the pipeline state file for date comparison

Only tests that run the pipeline TWICE and expect the second to be blocked are affected by N-FINDING-01.
