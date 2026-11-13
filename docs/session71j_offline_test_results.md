# Session 71J — Offline Test Results

**Session**: 71J  
**Test file**: `tests/test_scheduler_safety_guards.py`  
**Execution timestamp**: 2026-11-12 (Session 71J)  
**Result**: 53 PASSED / 0 FAILED

---

## 1. Run Command & Environment

```bash
python3 -m pytest tests/test_scheduler_safety_guards.py -v

# Platform: darwin — Python 3.13.3, pytest-9.1.1, pluggy-1.6.0
# No freezegun (manual clock injection used throughout)
# All tests use tmp_path fixture — no production files accessed
```

---

## 2. Full Results

| ID | Test Name | Result |
|---|---|---|
| T-01 | test_T01_exactly_1600_allowed | PASS |
| T-02 | test_T02_before_1600_blocked | PASS |
| T-03 | test_T03_exactly_2000_blocked | PASS |
| T-04 | test_T04_after_2000_blocked | PASS |
| T-05 | test_T05_last_valid_second | PASS |
| T-06 | test_T06_naive_datetime_fail_closed | PASS |
| T-07 | test_T07_non_taipei_timezone_normalized | PASS |
| T-08 | test_T08_midnight_blocked | PASS |
| — | test_window_check_via_clock_callable | PASS |
| — | test_window_returns_correct_scheduled_date | PASS |
| T-09 | test_T09_no_state_file_allowed | PASS |
| T-10 | test_T10_prior_day_success_allowed | PASS |
| T-11 | test_T11_same_day_success_blocked | PASS |
| T-12 | test_T12_same_day_running_alive_blocked | PASS |
| T-13 | test_T13_same_day_running_dead_pid_blocked | PASS |
| T-14 | test_T14_same_day_qg_blocked_allowed | PASS |
| T-15 | test_T15_same_day_provider_failed_allowed | PASS |
| T-16 | test_T16_same_day_failed_allowed | PASS |
| T-17 | test_T17_corrupt_state_fail_closed | PASS |
| T-18 | test_T18_atomic_write_creates_file | PASS |
| T-19 | test_T19_write_committed_today_blocked | PASS |
| — | test_write_committed_flag_alone_blocks | PASS |
| — | test_post_write_check_failed_no_write_flag_allowed | PASS |
| — | test_state_guard_uses_today_field_as_fallback | PASS |
| — | test_no_secrets_in_written_state | PASS |
| T-24 | test_transition_updates_status | PASS |
| — | test_running_zero_pid_treated_as_dead | PASS |
| — | test_empty_state_file_treated_as_first_run | PASS |
| T-20 | test_T20_no_wrapper_env_warns | PASS |
| T-21 | test_T21_with_wrapper_env_ok | PASS |
| — | test_is_called_from_wrapper_false_by_default | PASS |
| T-22 | test_T22_neon_url_raises | PASS |
| T-23 | test_T23_sqlite_path_no_error | PASS |
| — | test_none_url_no_error | PASS |
| — | test_postgres_keyword_raises | PASS |
| — | test_supabase_raises | PASS |
| T-25 | test_T25_hash_mismatch_detected | PASS |
| — | test_hash_match_on_exact_content | PASS |
| — | test_missing_file_returns_error | PASS |
| — | test_own_pid_alive | PASS |
| — | test_zero_pid_not_alive | PASS |
| — | test_negative_pid_not_alive | PASS |
| — | test_impossible_pid_not_alive | PASS |
| — | test_format | PASS |
| — | test_unique | PASS |
| — | test_expired_window_before_state_check | PASS |
| — | test_allowed_window_then_allowed_state | PASS |
| — | test_allowed_window_then_blocked_state | PASS |
| — | test_cron_launchd_dual_trigger_same_day | PASS |
| — | test_rc2_hash_drift_in_state_scenario | PASS |
| — | test_direct_backfill_bypass_check | PASS |
| — | test_neon_write_attempt_blocked_in_guard_layer | PASS |
| — | test_lock_state_written_atomically | PASS |

**Total: 53 PASSED, 0 FAILED**

---

## 3. Coverage by Risk Category

| Risk | Tests | Status |
|---|---|---|
| Pre-schedule false trigger | T-01, T-02, T-08 | COVERED |
| Post-deadline catch-up | T-03, T-04, T-05 | COVERED |
| Naive clock (DST safety) | T-06 | COVERED |
| Timezone normalization | T-07 | COVERED |
| First run (no state) | T-09 | COVERED |
| Prior day stale state | T-10 | COVERED |
| Duplicate SUCCESS block | T-11 | COVERED |
| Concurrent run (PID alive) | T-12 | COVERED |
| Crashed run (PID dead) | T-13 | COVERED |
| QG-blocked retry | T-14 | COVERED |
| Provider-failed retry | T-15 | COVERED |
| Generic failed retry | T-16 | COVERED |
| Corrupt state fail-closed | T-17 | COVERED |
| Atomic write correctness | T-18 | COVERED |
| Write-committed block | T-19 | COVERED |
| FileLock direct bypass | T-20, T-21 | COVERED |
| Neon write block | T-22, T-23 | COVERED |
| RC-2 hash drift | T-25 | COVERED |
| Dual-trigger (cron+launchd) | chain test | COVERED |
| State transition (RUNNING→SUCCESS) | T-24 | COVERED |
| Secret exclusion from state | — | COVERED |

---

## 4. Test Isolation Verification

Each test uses `tmp_path` pytest fixture for file I/O:
- State files: `tmp_path / ".cron_state.json"`
- Lock files: `tmp_path / ".cron.lock"` (not used in these tests — guard doesn't hold lock itself)
- No imports from `hybrid_shadow_cron` or `backfill_daily_prices`
- No TWSE/TPEx/Neon calls
- No production SQLite reads or writes

---

## 5. Offline Constraint Compliance

| Constraint | Compliant? |
|---|---|
| No production cron execution | YES |
| No TWSE/TPEx API calls | YES |
| No production SQLite writes | YES |
| No Neon writes | YES |
| No LaunchAgent installation | YES |
| No `--execute` flag invoked | YES |
| freezegun not required | YES (manual injection) |
| All tests repeatable offline | YES |
