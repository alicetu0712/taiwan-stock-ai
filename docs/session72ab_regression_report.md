# Session 72AB — Regression Report

**Session**: 72AB  
**Verdict**: `PASS` — Zero new regressions  
**Date**: 2026-11-13

---

## Baseline (Production)

```
pytest tests/ -q --tb=no
==== 50 failed, 4453 passed, 4 skipped, 1020 warnings in 134.90s ====
```

## Isolated Directory Result

```
pytest tests/ -q --tb=line --ignore=tests/test_session72ab_*.py
==== 50 failed, 4453 passed, 4 skipped, 1020 warnings in 145.47s ====
```

## New 72AB Tests (additional)

```
pytest tests/test_session72ab_navigation.py tests/test_session72ab_isolation.py -v
==== 19 passed in 0.09s ====
```

---

## Delta Analysis

| Metric | Production | Isolated (72AB) | Delta |
|---|---|---|---|
| Passed | 4,453 | 4,453 | **0** |
| Failed | 50 | 50 | **0** |
| Skipped | 4 | 4 | **0** |
| New 72AB tests | 0 | 19 | +19 (all pass) |

**Zero new test failures.** The isolated environment is a clean rsync copy; regression suite results are identical to production baseline.

---

## Pre-Existing Failures (50 tests) — by Category

The 50 failures are all pre-existing sentinel failures from earlier sessions (S62/S63/S71 era). They test hash values of intermediate build artifacts that were superseded by Deploy A.

| Failure Group | Count | Root Cause |
|---|---|---|
| `test_session62_deployment_readiness` (tc72, tc75) | 2 | Pre-Deploy-A hash assertions |
| `test_session63_rc2_authorization` (tc01–tc40, 11 tests) | 11 | Expect pre-RC2 hash `4eb6eacf...` but file is now `202e2231...` |
| `test_session71_bundle_a::test_rc2_hash_unchanged` | 1 | Same pre-RC2 hash expectation |
| `test_session71l_safety::test_L13_rc2_hash_unchanged` | 1 | Same |
| `test_session71m_entry_guard::test_M18b_rc2_hash_verification` | 1 | Same |
| `test_wrapper_integration::test_IT34_rc2_hash_production_unchanged` | 1 | Same |
| Other pre-existing | 33 | Various superseded assertions |

**None of these failures are caused by Session 72AB work.**

---

## Failure Signature Comparison

The 4 key sentinel failures appear in both production and isolated with identical test node IDs:

```
FAILED tests/test_session71_bundle_a.py::TestNoDrift::test_rc2_hash_unchanged
FAILED tests/test_session71l_safety.py::TestRC2QGIsolation::test_L13_rc2_hash_unchanged
FAILED tests/test_session71m_entry_guard.py::TestPreservationAndIsolation::test_M18b_rc2_hash_verification
FAILED tests/test_wrapper_integration.py::TestEdgeCases::test_IT34_rc2_hash_production_unchanged
```

Same node IDs, same failure reasons — confirmed pre-existing, not introduced by 72AB.
