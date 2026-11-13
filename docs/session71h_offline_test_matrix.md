# Session 71H — Offline Test Matrix

**Date**: 2026-11-11  
**Authorization**: STRICT_READ_ONLY / IMPLEMENTATION_PLANNING_ONLY

---

## 1. Test Scope

All tests are **offline** — no live TWSE/TPEx calls. All tests use fixtures and mocked dependencies. All tests verify the SAFETY GUARD behavior proposed in this session. QG-1~QG-7 and freshness gate are tested separately (existing test suite).

Test file location (proposed): `tests/test_cron_safety_guards.py`  
Requires: No code changes to run (designed against PROPOSED code, gates on authorization before implementation).

---

## 2. Test Fixtures

### Fixture F-01: Prior State — SUCCESS (today)
```python
{
  "today": "2026-11-12",
  "status": "SUCCESS",
  "execute": True,
  "taiwan_time": "2026-11-12T16:00:39 CST"
}
```

### Fixture F-02: Prior State — BLOCKED_STALE_DATA (today)
```python
{
  "today": "2026-11-12",
  "status": "BLOCKED_STALE_DATA",
  "execute": True,
  "taiwan_time": "2026-11-12T16:00:39 CST"
}
```

### Fixture F-03: Prior State — SUCCESS (yesterday)
```python
{
  "today": "2026-11-11",
  "status": "SUCCESS",
  "execute": True,
  "taiwan_time": "2026-11-11T16:00:39 CST"
}
```

### Fixture F-04: Prior State — empty / missing / corrupt
```python
{}  # or FileNotFoundError, or invalid JSON
```

### Fixture F-05: Taiwan Time — 15:45 CST (pre-window)
```python
datetime(2026, 11, 12, 7, 45, 0, tzinfo=UTC)  # = 15:45 CST
```

### Fixture F-06: Taiwan Time — 16:00 CST (window start, exact)
```python
datetime(2026, 11, 12, 8, 0, 0, tzinfo=UTC)  # = 16:00 CST
```

### Fixture F-07: Taiwan Time — 16:30 CST (within window)
```python
datetime(2026, 11, 12, 8, 30, 0, tzinfo=UTC)  # = 16:30 CST
```

### Fixture F-08: Taiwan Time — 19:59 CST (window end - 1min)
```python
datetime(2026, 11, 12, 11, 59, 0, tzinfo=UTC)  # = 19:59 CST
```

### Fixture F-09: Taiwan Time — 20:00 CST (window end, expired)
```python
datetime(2026, 11, 12, 12, 0, 0, tzinfo=UTC)  # = 20:00 CST
```

### Fixture F-10: Taiwan Time — 20:01 CST (after window)
```python
datetime(2026, 11, 12, 12, 1, 0, tzinfo=UTC)  # = 20:01 CST
```

### Fixture F-11: Trading day (2026-11-12, Wednesday)
```python
date(2026, 11, 12)  # Wednesday = trading day
```

### Fixture F-12: Non-trading day (2026-11-15, Saturday)
```python
date(2026, 11, 15)  # Saturday = non-trading day
```

---

## 3. Test Cases — Same-day Guard

### T-01: Block on SUCCESS (today)
```python
def test_same_day_guard_blocks_on_success_today(mock_state=F-01, mock_today="2026-11-12"):
    result = run_cron_pipeline(execute=True)
    assert result["status"] == "ALREADY_RAN_TODAY"
    assert result["exit_code"] == 0
    assert backfill_was_not_called()
```
**Expected**: ALREADY_RAN_TODAY, exit 0, no backfill

### T-02: Allow on BLOCKED_STALE_DATA (today)
```python
def test_same_day_guard_allows_on_blocked_stale(mock_state=F-02, mock_today="2026-11-12"):
    result = run_cron_pipeline(execute=True)
    assert result["status"] != "ALREADY_RAN_TODAY"
    assert pipeline_proceeded_to_calendar_check()
```
**Expected**: Pipeline proceeds past guard

### T-03: Allow on SUCCESS (yesterday)
```python
def test_same_day_guard_allows_on_success_yesterday(mock_state=F-03, mock_today="2026-11-12"):
    result = run_cron_pipeline(execute=True)
    assert result["status"] != "ALREADY_RAN_TODAY"
```
**Expected**: Guard does NOT block (yesterday's SUCCESS ≠ today)

### T-04: Allow on Empty State
```python
def test_same_day_guard_allows_on_empty_state(mock_state=F-04, mock_today="2026-11-12"):
    result = run_cron_pipeline(execute=True)
    assert result["status"] != "ALREADY_RAN_TODAY"
```
**Expected**: Guard does NOT block (no prior state = first run)

### T-05: Allow on Corrupted State File
```python
def test_same_day_guard_allows_on_corrupt_state(corrupt_json=True, mock_today="2026-11-12"):
    # State file contains invalid JSON
    result = run_cron_pipeline(execute=True)
    assert result["status"] != "ALREADY_RAN_TODAY"
    # Must not raise exception
```
**Expected**: Guard fails open (treats corrupt = no prior state) → allows run

### T-06: ALREADY_RAN_TODAY exits 0 (clean status)
```python
def test_already_ran_today_exits_zero(mock_state=F-01, mock_today="2026-11-12"):
    result = run_cron_pipeline(execute=True)
    assert result["status"] == "ALREADY_RAN_TODAY"
    assert result["exit_code"] == 0  # Must be clean, not error
```
**Expected**: exit_code = 0

---

## 4. Test Cases — Execution Validity Window

### T-07: Block before window (15:45 CST)
```python
def test_window_blocks_pre_schedule(mock_taiwan_time=F-05, mock_today=F-11):
    result = _is_within_execution_window(now_taipei)
    is_valid, reason = result
    assert is_valid is False
    assert "PRE_SCHEDULE" in reason
```
**Expected**: is_valid=False, reason contains PRE_SCHEDULE

### T-08: Allow at window start (16:00 CST)
```python
def test_window_allows_at_start(mock_taiwan_time=F-06, mock_today=F-11):
    is_valid, reason = _is_within_execution_window(now_taipei)
    assert is_valid is True
    assert reason == "WITHIN_WINDOW"
```
**Expected**: is_valid=True

### T-09: Allow mid-window (16:30 CST)
```python
def test_window_allows_midwindow(mock_taiwan_time=F-07, mock_today=F-11):
    is_valid, reason = _is_within_execution_window(now_taipei)
    assert is_valid is True
```
**Expected**: is_valid=True

### T-10: Allow at window end minus 1 minute (19:59 CST)
```python
def test_window_allows_near_end(mock_taiwan_time=F-08, mock_today=F-11):
    is_valid, reason = _is_within_execution_window(now_taipei)
    assert is_valid is True
```
**Expected**: is_valid=True (window is 16:00–20:00, boundary exclusive at 20:00)

### T-11: Block at window end (20:00 CST)
```python
def test_window_blocks_at_end(mock_taiwan_time=F-09, mock_today=F-11):
    is_valid, reason = _is_within_execution_window(now_taipei)
    assert is_valid is False
    assert "EXECUTION_EXPIRED" in reason
```
**Expected**: is_valid=False

### T-12: Block after window (20:01 CST)
```python
def test_window_blocks_after_end(mock_taiwan_time=F-10, mock_today=F-11):
    is_valid, reason = _is_within_execution_window(now_taipei)
    assert is_valid is False
```
**Expected**: is_valid=False

### T-13: Pipeline exits 0 on EXECUTION_WINDOW_EXPIRED
```python
def test_window_expired_exits_zero(mock_taiwan_time=F-09, mock_today=F-11):
    result = run_cron_pipeline(execute=True)
    assert result["status"] == "EXECUTION_WINDOW_EXPIRED"
    assert result["exit_code"] == 0
    assert backfill_was_not_called()
```
**Expected**: exit_code=0 (clean status), backfill not called

---

## 5. Test Cases — QG Preservation

### T-14: Same-day guard does not bypass QG
```python
def test_guard_does_not_bypass_qg(mock_state=F-02, mock_today="2026-11-12"):
    # State is BLOCKED_STALE_DATA (not SUCCESS), so guard allows pipeline
    # QG should run normally during backfill subprocess
    result = run_cron_pipeline(execute=True)
    # Verify QG was invoked at least once
    assert quality_gate_was_called()
```
**Expected**: Guard allows; QG called in backfill subprocess

### T-15: Validity window guard does not bypass QG
```python
def test_window_guard_does_not_bypass_qg(mock_taiwan_time=F-07):
    # Window is open (16:30 CST) → backfill proceeds
    # QG must still run
    result = run_cron_pipeline(execute=True, mock_backfill=True)
    assert quality_gate_was_called_in_backfill()
```
**Expected**: QG called (not bypassed by window guard)

---

## 6. Test Cases — FileLock Coverage

### T-16: Backfill standalone direct call does not acquire wrapper lock
```python
def test_backfill_standalone_no_wrapper_lock():
    # Run backfill_daily_prices.py directly with mock data
    # Verify it does NOT try to acquire data/.cron.lock
    with mock_sqlite():
        run_backfill(start=today, end=today, execute=False)
    assert not lock_acquire_attempted("data/.cron.lock")
```
**Expected**: No lock attempt (Option A design: backfill has no lock)

### T-17: Wrapper FileLock acquired before backfill subprocess
```python
def test_wrapper_acquires_lock_before_backfill():
    lock_sequence = []
    with mock_filelock(callback=lambda e: lock_sequence.append(e)):
        run_cron_pipeline(execute=False)  # dry-run
    lock_idx = lock_sequence.index("LOCK_ACQUIRED")
    backfill_idx = lock_sequence.index("BACKFILL_CALLED")
    assert lock_idx < backfill_idx
```
**Expected**: Lock acquired before backfill called

---

## 7. Test Cases — Catch-up Scenario

### T-18: Catch-up at 16:45 — guard allows, QG preserved
```python
def test_catchup_1645_allowed():
    # Simulate: machine asleep at 16:00, cron missed
    # Machine wakes at 16:45, launchd fires catch-up at 16:45 CST
    mock_taiwan_time = datetime(2026, 11, 12, 8, 45, 0, tzinfo=UTC)  # 16:45 CST
    mock_state = F-04  # no prior run
    
    result = run_cron_pipeline(execute=True)
    
    assert result["steps"]["execution_window"] == "WITHIN_WINDOW"
    assert result["status"] != "EXECUTION_WINDOW_EXPIRED"
    # QG still runs (via backfill subprocess mock)
    assert quality_gate_called_or_mocked()
```
**Expected**: Catch-up allowed, window guard passes, QG preserved

---

## 8. Test Matrix Summary

| Test | Component | Input | Expected Result | Priority |
|---|---|---|---|---|
| T-01 | Same-day guard | SUCCESS today | ALREADY_RAN_TODAY, exit 0 | P0 |
| T-02 | Same-day guard | BLOCKED_STALE today | Allow, proceed | P0 |
| T-03 | Same-day guard | SUCCESS yesterday | Allow, proceed | P0 |
| T-04 | Same-day guard | Empty state | Allow, proceed | P0 |
| T-05 | Same-day guard | Corrupt state | Allow, proceed (FAIL_OPEN) | P1 |
| T-06 | Same-day guard | SUCCESS today | exit_code == 0 | P0 |
| T-07 | Validity window | 15:45 CST | PRE_SCHEDULE, is_valid=False | P0 |
| T-08 | Validity window | 16:00 CST | WITHIN_WINDOW, is_valid=True | P0 |
| T-09 | Validity window | 16:30 CST | WITHIN_WINDOW, is_valid=True | P0 |
| T-10 | Validity window | 19:59 CST | WITHIN_WINDOW, is_valid=True | P0 |
| T-11 | Validity window | 20:00 CST | EXPIRED, is_valid=False | P0 |
| T-12 | Validity window | 20:01 CST | EXPIRED, is_valid=False | P0 |
| T-13 | Validity window | 20:00, full pipeline | EXECUTION_WINDOW_EXPIRED, exit 0 | P0 |
| T-14 | QG preservation | BLOCKED_STALE state | QG called during backfill | P0 |
| T-15 | QG preservation | 16:30 CST, window open | QG called during backfill | P0 |
| T-16 | FileLock | Backfill direct | No wrapper lock acquired | P1 |
| T-17 | FileLock | Wrapper + backfill | Lock before backfill | P1 |
| T-18 | Catch-up 16:45 | No prior run | WITHIN_WINDOW, QG preserved | P0 |

**Total**: 18 tests  
**P0 count**: 14 (must pass before any deployment)  
**P1 count**: 4 (should pass; non-critical for initial deployment)

---

## 9. Test Infrastructure Notes

All tests require:
- `pytest` (already in test suite)
- `unittest.mock.patch` for `datetime.now`, `_load_state`, `_save_state`
- Mock subprocess for backfill calls (do NOT call real TWSE)
- Mock SQLite for connection-dependent tests
- Existing fixtures from `tests/fixtures/` (if available)

No new test infrastructure needed beyond standard `pytest` and `mock`.

---

## 10. Verdict

| Item | Status |
|---|---|
| **Test count** | 18 tests designed |
| **P0 tests** | 14 — required before deployment |
| **Coverage** | Same-day guard, validity window, QG preservation, FileLock |
| **Live data** | NONE — all offline |
| **Infrastructure** | Standard pytest + mock |
| **Overall** | `OFFLINE_TEST_MATRIX_READY` |
