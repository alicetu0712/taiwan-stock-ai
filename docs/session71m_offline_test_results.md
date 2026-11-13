# Session 71M — Offline Test Results

**Session**: 71M  
**Verdict**: `OFFLINE_TESTS_PASS` (30/30)

---

## Test Suite: `tests/test_session71m_entry_guard.py`

### TestEntryAuthorization (M-01 ~ M-07)

| ID | Test | Result |
|---|---|---|
| M-01 | Direct guarded --execute without lock → exit 2 | ✓ PASS |
| M-01b | Direct guarded dry-run without lock → allowed | ✓ PASS |
| M-02 | Integrated wrapper (lock held) → authorized | ✓ PASS |
| M-03 | Protected adapter with CALLED_FROM_WRAPPER=1 → authorized | ✓ PASS |
| M-04 | CALLED_FROM_WRAPPER=1 alone, no lock → rejected | ✓ PASS |
| M-04b | check_original_entry() lock NOT held + env set → UNAUTHORIZED | ✓ PASS |
| M-05 | No env, no lock → rejected | ✓ PASS |
| M-06 | BACKFILL_ALLOW_DIRECT=1 alone → rejected (incomplete maintenance) | ✓ PASS |
| M-07 | Two-key maintenance override → authorized | ✓ PASS |
| M-07b | check_original_entry() two-key unit test → AUTHORIZED_MAINTENANCE | ✓ PASS |

### TestWritePathAndConcurrency (M-08 ~ M-10)

| ID | Test | Result |
|---|---|---|
| M-08 | run_backfill(execute=True) without auth → guard_blocked=True | ✓ PASS |
| M-08b | run_backfill(execute=True) with lock+env → guard passes | ✓ PASS |
| M-09 | Concurrent wrapper → BLOCKED_LOCK (single writer) | ✓ PASS |
| M-10 | Wrapper holds lock → guarded backfill authorized | ✓ PASS |

### TestLockAndStateSafety (M-11 ~ M-15)

| ID | Test | Result |
|---|---|---|
| M-11 | _check_lock_state uses LOCK_NB (no deadlock) | ✓ PASS |
| M-12 | Lock IS held → check_original_entry AUTHORIZED | ✓ PASS |
| M-13 | RUNNING + dead PID → WRITE_OUTCOME_UNKNOWN (no auto-retry) | ✓ PASS |
| M-14 | write_committed=True → second run blocked | ✓ PASS |
| M-15 | Corrupted state → FAIL_CLOSED_CORRUPT | ✓ PASS |

### TestPreservationAndIsolation (M-16 ~ M-24)

| ID | Test | Result |
|---|---|---|
| M-16 | Dry-run preserved (not blocked by guard) | ✓ PASS |
| M-16b | check_original_entry(is_execute=False) always authorized | ✓ PASS |
| M-17 | --help works without authorization | ✓ PASS |
| M-18 | RC-2 filter semantically identical (line comparison) | ✓ PASS |
| M-18b | Original backfill RC-2 hash unchanged | ✓ PASS |
| M-19 | QG preserved; guard before QG in call order | ✓ PASS |
| M-20 | Guard module has no TWSE/TPEx HTTP calls | ✓ PASS |
| M-21 | Guard module has no sqlite3.connect | ✓ PASS |
| M-22 | Guard module has no Neon/psycopg2 writes | ✓ PASS |
| M-23 | hybrid_shadow_cron.py hash unchanged | ✓ PASS |
| M-24 | No LaunchAgent plist installed | ✓ PASS |

**Total**: 30/30 PASS (including sub-tests: M-01b, M-04b, M-07b, M-08b, M-16b, M-18b)

---

## Combined Guard Suite

| File | Tests | Result |
|---|---|---|
| `test_scheduler_safety_guards.py` | 53 | 53/53 ✓ |
| `test_wrapper_integration.py` | 38 | 38/38 ✓ |
| `test_session71l_safety.py` | 22 | 22/22 ✓ |
| `test_session71m_entry_guard.py` | 30 | 30/30 ✓ |
| **Guard suite total** | **143** | **143/143 ✓** |
