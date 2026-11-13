# Session 71L — Offline Test Results

**Session**: 71L  
**Verdict**: `OFFLINE_TESTS_PASS` (22/22)

---

## Test Suite: `tests/test_session71l_safety.py`

### TestDirectEntryProtection (L-01 ~ L-04)

| ID | Test | Result |
|---|---|---|
| L-01 | Direct protected backfill `--execute` without wrapper auth → exit 2 | ✓ PASS |
| L-01b | Direct protected backfill dry-run without auth → allowed | ✓ PASS |
| L-02 | Wrapper-authorized child passes QG normally | ✓ PASS |
| L-02b | `CALLED_FROM_WRAPPER=1` → `check_invocation()` returns authorized | ✓ PASS |
| L-03 | Backfill has zero lock calls → no deadlock possible (structural) | ✓ PASS |
| L-04 | Concurrent wrapper+direct: guard blocks direct execute | ✓ PASS |
| L-04b | `BACKFILL_ALLOW_DIRECT=1` override → authorized with warning | ✓ PASS |

### TestCommitOutcomeAndCrashRecovery (L-05 ~ L-12)

| ID | Test | Result |
|---|---|---|
| L-05 | RUNNING + dead PID → `WRITE_OUTCOME_UNKNOWN` (fail-closed) | ✓ PASS |
| L-06 | `WRITE_OUTCOME_UNKNOWN` does not auto-retry (second run blocked) | ✓ PASS |
| L-07 | `write_committed=True` blocks re-write even after shadow failure | ✓ PASS |
| L-08 | Freshness STALE → `write_committed` NOT set | ✓ PASS |
| L-09 | Backfill exit=1 → `write_committed` NOT set | ✓ PASS |
| L-10 | Corrupted state JSON → `FAIL_CLOSED_CORRUPT` | ✓ PASS |
| L-11 | RUNNING + live PID → `CONCURRENT_RUN` (not WRITE_OUTCOME_UNKNOWN) | ✓ PASS |
| L-12 | `_save_state()` uses `os.replace` + `.tmp` (atomic write) | ✓ PASS |

### TestRC2QGIsolation (L-13 ~ L-18)

| ID | Test | Result |
|---|---|---|
| L-13 | RC-2 hash (`4eb6eacf...`) unchanged | ✓ PASS |
| L-14 | Guard module has no QG imports/calls | ✓ PASS |
| L-15 | Guard module has no provider HTTP calls | ✓ PASS |
| L-16 | Guard module has no direct DB write calls | ✓ PASS |
| L-17 | `hybrid_shadow_cron.py` hash (`46209171...`) unchanged | ✓ PASS |
| L-18 | `check_invocation(is_execute=False)` always authorized | ✓ PASS |
| L-18b | Protected script dry-run → not blocked (exit ≠ 2) | ✓ PASS |

**Total**: 22/22 PASS (including 4 sub-tests: L-01b, L-02b, L-04b, L-18b)

---

## Test Isolation Confirmation

All tests use:
- `tmp_path` fixture (pytest managed, isolated per test)
- `:memory:` SQLite (never touches `data/platform.db`)
- Mock runners (`_backfill_ok_runner()`, `_freshness_ok_checker()`, etc.)
- `patch("scripts.hybrid_shadow_cron_integrated.CALENDAR.is_trading_day")`
- No real TWSE/TPEx HTTP calls
- No production state file writes
- No production lock file acquisition

The L-01/L-01b/L-04/L-18b subprocess tests run `backfill_daily_prices_protected.py` as a subprocess with isolated env vars and `:memory:` DB path — no production data touched.
