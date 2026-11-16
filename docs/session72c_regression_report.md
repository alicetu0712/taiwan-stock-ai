# Session 72C — Regression Report

**Session**: 72C  
**Verdict**: `REGRESSION_PASS` (0 new failures)  
**Date**: 2026-11-13

---

## Test Run Summary

| Run | Tests Collected | Passed | Failed | Skipped | Duration |
|---|---|---|---|---|---|
| Baseline (72AB) | 4526 | 4453 | 50 | 4 | ~155s |
| After 72C fixes | 4526 | **4453** | **50** | 4 | ~155s |
| Delta | 0 | **0** | **0** | 0 | — |

**Result: ZERO new failures introduced by Session 72C changes.**

---

## 72AB New Tests (19 tests)

| Test | Status |
|---|---|
| `test_exactly_5_top_level_tabs` | ✓ PASS |
| `test_no_duplicate_main_navigation` | ✓ PASS |
| `test_all_core_pages_reachable` | ✓ PASS |
| `test_legacy_reachable_via_system_management` | ✓ PASS |
| `test_archive_still_importable` | ✓ PASS |
| `test_v3_not_activated` | ✓ PASS |
| `test_production_model_version_preserved` | ✓ PASS |
| `test_empty_state_kinds` | ✓ PASS |
| `test_five_main_tabs_in_ast` | ✓ PASS |
| `test_ui_version_not_conflated_with_model_version` | ✓ PASS |
| `test_production_app_py_unchanged` | ✓ PASS |
| `test_isolated_app_py_different` | ✓ PASS |
| `test_no_production_path_writes` | ✓ PASS |
| `test_deploy_a_hash_unchanged` | ✓ PASS |
| `test_production_cron_wrapper_unchanged` | ✓ PASS |
| `test_isolated_root_distinct_from_production` | ✓ PASS |
| `test_production_scripts_untouched` | ✓ PASS |
| `test_isolated_components_has_empty_state` | ✓ PASS |
| `test_production_components_unchanged` | ✓ PASS |

---

## Pre-existing Failures (50 — all present before Session 72)

All 50 failures are in RC-2 hash verification tests from sessions 63–71. They compare the backfill script hash against a pre-Deploy-A expected value, but the isolated repo (and production) now contain the Deploy-A guarded version (`202e2231...`). These are **known test drift** from Deploy A deployment — not regressions introduced by any UI change.

Representative failures:
- `test_session63_rc2_authorization.py::test_tc36_production_integrity_script_hash`
- `test_session63_rc2_authorization.py::test_tc37_no_deployment_executed`
- `test_session63_rc2_authorization.py::test_tc40_rc2_go_for_authorization`
- `test_session71_bundle_a.py::TestNoDrift::test_rc2_hash_unchanged`
- `test_session71l_safety.py::TestRC2QGIsolation::test_L13_rc2_hash_unchanged`
- `test_session71m_entry_guard.py::TestPreservationAndIsolation::test_M18b_rc2_hash_verification`
- `test_wrapper_integration.py::TestEdgeCases::test_IT34_rc2_hash_production_unchanged`
- (43 more of same pattern)

**Root cause of pre-existing failures**: These tests were written when Deploy A had not yet been applied. They hard-code the pre-Deploy-A backfill script hash. After Deploy A, the hash legitimately changed. These tests need updating in a separate session (`BACKEND_CHANGE_REQUIRES_SEPARATE_AUTHORIZATION`).

---

## 72C Fix Regression Impact

| Fix | Tests Affected | Before | After |
|---|---|---|---|
| F1: `_render()` wrapper for version info | None directly | 19/19 | 19/19 |
| F2: st.radio replacing inner st.tabs | `test_five_main_tabs_in_ast` | PASS | PASS (radio not counted as tab) |
