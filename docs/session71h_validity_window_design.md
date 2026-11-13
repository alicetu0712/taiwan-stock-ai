# Session 71H — Execution Validity Window Design

**Date**: 2026-11-11  
**Authorization**: STRICT_READ_ONLY / IMPLEMENTATION_PLANNING_ONLY

---

## 1. The Problem

The script uses `date.today()` to determine which data to fetch. If launchd fires a catch-up after the machine wakes from sleep, the execution date must still match the originally scheduled date. A catch-up that fires after midnight CST will target the wrong date permanently.

Additionally, the existing `_is_data_ready()` check only verifies time >= 15:30 CST. It does NOT enforce a maximum execution time, leaving catch-up runs unlimited.

---

## 2. Requirements

The validity window must satisfy all of the following:

| Requirement | Rationale |
|---|---|
| Do not allow execution before 16:00 CST | Pre-schedule execution is unexpected; scheduled time is 16:00 |
| Do not allow cross-day catch-up | `date.today()` changes at midnight → targets wrong date |
| Do not skip QG for in-window executions | QG applies regardless of timing |
| Do not assume Provider data is available because window is open | `_is_data_ready()` and QG-5 handle data currency |
| Do not change trading day calendar logic | Calendar check remains at Stage 2 |
| Handle timezone errors gracefully | Use `pytz.timezone("Asia/Taipei")` already in use |

**Note on 15:30 lower bound**: The existing `_is_data_ready()` check already enforces >= 15:30. The question is whether to raise the lower bound to 16:00 (the scheduled time). The spec lists 15:30 as the candidate lower bound. However:
- Cron fires at 16:00; the script should not be expected to execute correctly at 15:45 via catch-up
- 15:30 allows the script to run BEFORE the scheduled time — which is unexpected
- **Recommendation**: lower bound = 16:00 (scheduled time), not 15:30

---

## 3. Policy Comparison

### Policy A — Strict Window (16:00–16:30)

```
Valid: 16:00:00 CST ≤ now ≤ 16:30:00 CST
```

| Attribute | Value |
|---|---|
| Catch-up window | 30 minutes |
| Covers: sleep 15:59, wake 16:28 | YES ✓ |
| Covers: sleep 16:00, wake 16:45 | NO ✗ |
| Cross-day risk | NONE |
| Data quality | FULL (QG preserved) |
| Implementation | Add deadline check in `_is_data_ready()` replacement |
| Risk | May miss legitimate catch-ups (e.g., 16:35 wake) |

### Policy B — Controlled Catch-up Window (16:00–20:00)

```
Valid: 16:00:00 CST ≤ now ≤ 20:00:00 CST
```

| Attribute | Value |
|---|---|
| Catch-up window | 4 hours |
| Covers: sleep 16:00, wake 19:30 | YES ✓ |
| Covers: sleep 16:00, wake 22:00 | NO ✗ |
| Cross-day risk | NONE (window ends before midnight) |
| Data quality | FULL (QG preserved, TWSE data stable from 15:30) |
| Implementation | Add deadline check |
| Risk | Very late catch-up (e.g., 19:55) runs with day's data — acceptable |

### Policy C — No Catch-up (Exact Schedule Only)

```
Valid: 16:00:00 CST ≤ now ≤ 16:01:00 CST (1-minute window)
```

| Attribute | Value |
|---|---|
| Catch-up window | 1 minute (cron natural fire only) |
| Covers: sleep 16:00, wake 16:30 | NO ✗ |
| Cross-day risk | NONE |
| Data quality | FULL |
| Implementation | Requires exact timing from scheduler |
| Risk | Defeats the purpose of launchd migration |

---

## 4. Scenario Verification

| Scenario | Policy A | Policy B | Policy C |
|---|---|---|---|
| 15:55 awake, 16:00 fire | ✓ | ✓ | ✓ |
| Sleep 16:00, wake 16:28 | ✓ Catch-up at 16:28 | ✓ | ✗ EXPIRED |
| Sleep 16:00, wake 16:45 | ✗ EXPIRED | ✓ Catch-up | ✗ EXPIRED |
| Sleep 16:00, wake 19:00 | ✗ EXPIRED | ✓ Catch-up | ✗ EXPIRED |
| Sleep 16:00, wake 22:00 | ✗ EXPIRED | ✗ EXPIRED | ✗ EXPIRED |
| Sleep 16:00, wake next day 09:00 | ✗ EXPIRED | ✗ EXPIRED | ✗ EXPIRED |
| Provider api_date stale | QG-5 blocks write | QG-5 blocks write | QG-5 blocks write |
| Non-trading day | Calendar check skips | Calendar check skips | Calendar check skips |

---

## 5. Proposed Implementation (Design Only)

```python
# PROPOSED — not authorized, not implemented
# Location: hybrid_shadow_cron.py, replace/augment _is_data_ready()

EXECUTION_WINDOW_START_HOUR = 16   # Must be >= scheduled cron time
EXECUTION_WINDOW_START_MINUTE = 0
EXECUTION_WINDOW_END_HOUR = 20     # Policy B: 20:00 CST (4-hour window)
EXECUTION_WINDOW_END_MINUTE = 0

def _is_within_execution_window(now_taipei: datetime) -> tuple[bool, str]:
    """
    Returns (is_valid, reason).
    Valid window: 16:00–20:00 CST, same day as today.
    
    Separate from _is_data_ready() (which checks TWSE data availability >= 15:30).
    This guard enforces the SCHEDULER-level validity window.
    """
    t = now_taipei.time()
    start = (EXECUTION_WINDOW_START_HOUR, EXECUTION_WINDOW_START_MINUTE)
    end = (EXECUTION_WINDOW_END_HOUR, EXECUTION_WINDOW_END_MINUTE)
    
    if (t.hour, t.minute) < start:
        return False, (
            f"PRE_SCHEDULE: {t.strftime('%H:%M')} CST < {start[0]:02d}:{start[1]:02d} CST "
            f"(scheduled 16:00). Catch-up not permitted before scheduled time."
        )
    if (t.hour, t.minute) >= end:
        return False, (
            f"EXECUTION_EXPIRED: {t.strftime('%H:%M')} CST ≥ {end[0]:02d}:{end[1]:02d} CST "
            f"deadline. Today's execution window has closed. "
            f"date.today()={date.today()} will differ from missed schedule date after midnight."
        )
    return True, "WITHIN_WINDOW"
```

**Call point**: After Stage 3 (`_is_data_ready()`), as new Stage 3b:

```python
# PROPOSED Stage 3b (not authorized):
valid, reason = _is_within_execution_window(now_taiwan)
result["steps"]["execution_window"] = reason
if not valid:
    _log(f"[cron] {reason} — skipping execution")
    result["status"] = "EXECUTION_WINDOW_EXPIRED" if "EXPIRED" in reason else "PRE_SCHEDULE"
    _save_state(result)
    return result
```

---

## 6. Interaction with Existing Guards

| Existing Guard | Function | Interaction with Window |
|---|---|---|
| `_is_data_ready()` (>= 15:30) | TWSE data publication check | Window raises lower bound to 16:00; `_is_data_ready()` still runs at 15:30 check |
| `CALENDAR.is_trading_day()` | Calendar check | Window guard only applies on trading days (runs after calendar check) |
| QG-5 (api_date == target) | Data date validation | Fully preserved; window guard does NOT bypass QG |
| Freshness gate | Post-write check | Fully preserved; runs only after backfill |
| FileLock | Concurrency | Fully preserved; runs before window check |

---

## 7. Exit Status for Expired Window

```python
clean_statuses = {
    "SUCCESS", "DRY_RUN_OK", "SKIPPED_NON_TRADING_DAY", "DATA_NOT_READY",
    "BLOCKED_STALE_DATA", "BLOCKED_LOCK", "BLOCKED_PARTIAL_MARKET",
    "EXECUTION_WINDOW_EXPIRED",   # NEW — add to clean_statuses (exit 0)
    "PRE_SCHEDULE",               # NEW — add to clean_statuses (exit 0)
}
```

Both new statuses use exit code 0 (expected behavior, not a crash).

---

## 8. Recommendation

**`CONTROLLED_CATCHUP_RECOMMENDED` — Policy B (16:00–20:00 CST)**

Rationale:
- Covers most practical sleep recovery scenarios
- Prevents cross-day targeting (window well before midnight)
- Preserves all existing QG behavior
- Requires minimal code change (1 new function + 1 call point)
- Low risk: expired window exits cleanly with exit 0

**Implementation scope**: 2 functions + 2 constants in `hybrid_shadow_cron.py` (requires separate authorization).
