# Session 71O — Test Remediation Diff

**Session**: 71O  
**Verdict**: `FOUR_TEST_FIXES_PASS`  
**Production Code Modified**: NO

---

## File 1: `tests/test_session71l_safety.py`

### Added: `_run_pipeline_today()` helper (after `_run_pipeline`)

```python
def _run_pipeline_today(tmp_path, hour=17, execute=True, bf=None, sh=None, fr=None,
                        trading_day=True, minute=0):
    """Date-anchored variant: uses actual date.today() for the override.

    Use in tests that perform two sequential pipeline runs and check that the
    second is blocked by the same-day guard.  The root issue (N-FINDING-01) is
    that run_cron_pipeline() calls date.today() internally; when the injected
    _now_taipei_override uses a *different* calendar date the guard sees two
    different dates and incorrectly allows the second run.  This helper keeps
    both values in sync.
    """
    from datetime import date as _date
    from scripts.hybrid_shadow_cron_integrated import run_cron_pipeline

    bf = bf or _backfill_ok_runner()
    sh = sh or _shadow_ok_runner()
    fr = fr or _freshness_ok_checker()

    today = _date.today()
    state = tmp_path / ".cron_state.json"
    lock = tmp_path / ".cron.lock"
    now = _taipei(today.year, today.month, today.day, hour, minute)

    with patch("scripts.hybrid_shadow_cron_integrated.CALENDAR.is_trading_day",
               return_value=trading_day):
        return run_cron_pipeline(
            execute=execute,
            skip_backup=True,
            _now_taipei_override=now,
            _state_file_override=state,
            _lock_file_override=lock,
            _db_path_override=":memory:",
            _backfill_runner=bf,
            _shadow_runner=sh,
            _freshness_checker=fr,
        )
```

### Modified: `test_L06` — replace `_run_pipeline` with `_run_pipeline_today`

```diff
-        result = _run_pipeline(tmp_path, hour=17)
+        """L-06: ... Uses _run_pipeline_today() (date-anchored) ..."""
+        result = _run_pipeline_today(tmp_path, hour=17)
         ...
-        result2 = _run_pipeline(tmp_path, hour=17, minute=10)
+        result2 = _run_pipeline_today(tmp_path, hour=17, minute=10)
```

### Modified: `test_L07` — replace `_run_pipeline` with `_run_pipeline_today`

```diff
-        result = _run_pipeline(tmp_path, hour=17, sh=_shadow_fail_runner())
+        """L-07: ... Uses _run_pipeline_today() (date-anchored) ..."""
+        result = _run_pipeline_today(tmp_path, hour=17, sh=_shadow_fail_runner())
         ...
-        result2 = _run_pipeline(tmp_path, hour=17, minute=10)
+        result2 = _run_pipeline_today(tmp_path, hour=17, minute=10)
```

---

## File 2: `tests/test_wrapper_integration.py`

### Added: `_run_pipeline_at_today()` helper (after `_run_pipeline_at`)

```python
def _run_pipeline_at_today(tmp_path, hour, minute=0, execute=True,
                           backfill=None, shadow=None, freshness=None,
                           trading_day=True):
    """Date-anchored variant of _run_pipeline_at.

    Uses date.today() as the override date so that run_cron_pipeline()'s
    internal date.today() matches the injected _now_taipei_override.date().
    Use in tests that make two sequential pipeline runs and check the second
    is blocked by the same-day guard (fix for N-FINDING-01).
    """
    from datetime import date as _date
    today = _date.today()
    state = tmp_path / ".cron_state.json"
    lock  = tmp_path / ".cron.lock"
    db    = ":memory:"
    now   = _taipei(today.year, today.month, today.day, hour, minute)

    with patch(
        "scripts.hybrid_shadow_cron_integrated.CALENDAR.is_trading_day",
        return_value=trading_day,
    ):
        return run_cron_pipeline(
            execute=execute,
            skip_backup=True,
            _now_taipei_override=now,
            _state_file_override=state,
            _lock_file_override=lock,
            _db_path_override=db,
            _backfill_runner=backfill or _backfill_ok(),
            _shadow_runner=shadow or _shadow_ok(),
            _freshness_checker=freshness or _freshness_ok(),
        )
```

### Modified: `test_IT25` — replace `_run_pipeline_at` with `_run_pipeline_at_today`

```diff
-        result1 = _run_pipeline_at(tmp_path, hour=16)
+        """IT-25: ... Uses _run_pipeline_at_today() ..."""
+        result1 = _run_pipeline_at_today(tmp_path, hour=16)
-        result2 = _run_pipeline_at(tmp_path, hour=17)
+        result2 = _run_pipeline_at_today(tmp_path, hour=17)
```

### Modified: `test_IT26` — replace `_run_pipeline_at` with `_run_pipeline_at_today`

```diff
-        result1 = _run_pipeline_at(tmp_path, hour=16)
+        """IT-26: ... Uses _run_pipeline_at_today() ..."""
+        result1 = _run_pipeline_at_today(tmp_path, hour=16)
-        result2 = _run_pipeline_at(tmp_path, hour=16, minute=30)
+        result2 = _run_pipeline_at_today(tmp_path, hour=16, minute=30)
```

---

## Invariants Preserved

| Invariant | Status |
|---|---|
| Original `_run_pipeline` unchanged | ✓ — no other test affected |
| Original `_run_pipeline_at` unchanged | ✓ — IT-27 (uses hardcoded state) still passes |
| Assertion conditions unchanged | ✓ — still assert GUARD_STATE / ALREADY_RAN_TODAY |
| No xfail / skip introduced | ✓ |
| No production guard modified | ✓ |
| No production files modified | ✓ |
| All 4 tests PASS after fix | ✓ |

---

## File 3: `tests/test_session71o_date_boundary.py` (NEW)

14 date boundary tests added (O-01 ~ O-13). See `session71o_date_boundary_tests.md`.
