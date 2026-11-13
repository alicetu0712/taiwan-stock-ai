# Session 71H — Minimal Implementation Plan

**Date**: 2026-11-11  
**Authorization**: STRICT_READ_ONLY / IMPLEMENTATION_PLANNING_ONLY  
**Status of this document**: DESIGN ONLY — no code has been modified

---

## 1. Implementation Philosophy

**Principle**: Minimum safe change. Every addition must:
1. Be independently testable
2. Exit cleanly (exit 0) on new guard conditions
3. Not change QG-1~QG-7 or freshness gate
4. Not change RC-2 logic or backfill behavior
5. Have a clear rollback path (delete the new code)

**What is NOT in scope**:
- Fixing H3 (requires natural cron execution)
- launchd deployment (requires separate authorization)
- Neon sync changes
- Shadow runner dedup changes
- 111,710 warrant data cleanup

---

## 2. Phase 1 — Safety Guards (hybrid_shadow_cron.py)

**Scope**: `scripts/hybrid_shadow_cron.py` only  
**Goal**: Add validity window guard + same-day SUCCESS guard  
**Requires**: Separate authorization  
**Prerequisite**: H3 acceptance confirmed (or explicit override authorization)

### Change 1.1: Execution Validity Window

**Location**: `hybrid_shadow_cron.py` — add after line 337 (`_is_data_ready()`)

```python
# ADD: 2 constants at module level (near existing constants)
EXECUTION_WINDOW_END_HOUR = 20
EXECUTION_WINDOW_END_MINUTE = 0

# ADD: 1 new function
def _is_within_execution_window(now_taipei):
    """
    Returns (is_valid, reason).
    Valid window: >= 16:00 CST AND < 20:00 CST.
    Caller passes datetime with Asia/Taipei timezone.
    """
    t = now_taipei.time()
    if (t.hour, t.minute) < (16, 0):
        return False, f"PRE_SCHEDULE: {t.strftime('%H:%M')} CST < 16:00 scheduled"
    if (t.hour, t.minute) >= (EXECUTION_WINDOW_END_HOUR, EXECUTION_WINDOW_END_MINUTE):
        return False, (
            f"EXECUTION_EXPIRED: {t.strftime('%H:%M')} CST >= "
            f"{EXECUTION_WINDOW_END_HOUR:02d}:{EXECUTION_WINDOW_END_MINUTE:02d} deadline"
        )
    return True, "WITHIN_WINDOW"
```

**Call point** in `run_cron_pipeline()`, after current Stage 3:
```python
# ADD Stage 3b: Execution window guard
valid, window_reason = _is_within_execution_window(now_taiwan)
result["steps"]["execution_window"] = window_reason
if not valid:
    _log(f"[cron] {window_reason}")
    result["status"] = "EXECUTION_WINDOW_EXPIRED" if "EXPIRED" in window_reason else "PRE_SCHEDULE"
    _save_state(result)
    return result
```

**Add to `clean_statuses`**:
```python
clean_statuses = {
    ...,
    "EXECUTION_WINDOW_EXPIRED",
    "PRE_SCHEDULE",
}
```

**Line count**: ~25 new lines

### Change 1.2: Same-day SUCCESS Guard

**Location**: `hybrid_shadow_cron.py` — add after FileLock acquired (after line 320), before Stage 2 (calendar check)

```python
# ADD Stage 1b: Same-day SUCCESS guard
prior = _load_state()
if (
    prior.get("today") == str(today)
    and prior.get("status") == "SUCCESS"
    and prior.get("execute") is True
):
    _log(f"[cron] ALREADY_RAN_TODAY: {today} — prior run succeeded at "
         f"{prior.get('taiwan_time', 'unknown')}, skipping")
    result["steps"]["same_day_guard"] = "BLOCKED_ALREADY_SUCCESS"
    result["status"] = "ALREADY_RAN_TODAY"
    _save_state(result)
    return result
result["steps"]["same_day_guard"] = "ALLOWED"
```

**Add to `clean_statuses`**:
```python
clean_statuses = {
    ...,
    "ALREADY_RAN_TODAY",
}
```

**Line count**: ~12 new lines

### Change 1.3: Log Append Wrapper (optional)

If launchd migration is authorized, add a shell wrapper to preserve log history:

**New file** `scripts/run_daily_cron.sh`:
```bash
#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"
exec python3 scripts/hybrid_shadow_cron.py --execute >> logs/hybrid_cron.log 2>&1
```

**plist change**: Point `ProgramArguments` to `run_daily_cron.sh` instead of Python directly.

**Line count**: 5 lines (shell script)

---

## 3. Phase 2 — Tests

**Scope**: `tests/test_cron_safety_guards.py` (new file)  
**Goal**: Implement T-01 to T-18 from `session71h_offline_test_matrix.md`  
**Requires**: Phase 1 code changes complete  
**Prerequisite**: Phase 1 implemented and passing existing test suite

**Expected test count**: 18 new tests  
**All offline**: No TWSE/TPEx calls  
**Expected pass rate**: 18/18 (or 14/18 P0 must pass)  
**Integration with existing suite**: `pytest tests/` should still pass all 4273 existing tests

---

## 4. Phase 3 — Scheduler Migration (launchd)

**Scope**: macOS LaunchAgent plist + crontab removal  
**Goal**: Replace cron with launchd `StartCalendarInterval`  
**Requires**: Explicit deployment authorization  
**Prerequisites**:
1. Phase 1 (safety guards) implemented and tested ✓
2. Phase 2 (18 offline tests) all P0 passing ✓
3. H3 acceptance confirmed ✓ (RC-2 natural cron run verified)
4. Non-trading-day deployment window chosen ✓

**Plist content** (designed in `session71g_launchd_architecture_decision.md`):
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.antigravity.stockplatform.dailybackfill</string>
  <key>ProgramArguments</key>
  <array>
    <string>/path/to/stock_platform/scripts/run_daily_cron.sh</string>
  </array>
  <key>WorkingDirectory</key>
  <string>/path/to/stock_platform</string>
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>16</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>16</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>16</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>16</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>16</integer><key>Minute</key><integer>0</integer></dict>
  </array>
  <key>RunAtLoad</key>
  <false/>
  <key>StandardOutPath</key>
  <string>/path/to/stock_platform/logs/hybrid_cron.log</string>
  <key>StandardErrorPath</key>
  <string>/path/to/stock_platform/logs/hybrid_cron.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>HOME</key><string>/Users/alicetu</string>
    <key>PATH</key><string>/usr/local/bin:/usr/bin:/bin</string>
    <key>PYTHONUNBUFFERED</key><string>1</string>
  </dict>
</dict>
</plist>
```

**Deployment steps** (from `session71g_cutover_rollback_plan.md`):
1. Backup crontab: `crontab -l > /tmp/crontab_backup_$(date +%Y%m%d).txt`
2. Remove cron job: `crontab -e` → delete cron line → save
3. Write plist to `~/Library/LaunchAgents/`
4. Bootstrap: `launchctl bootstrap gui/$(id -u) <plist_path>`
5. Verify: `launchctl list | grep dailybackfill`
6. Confirm acceptance window (next trading day 16:00 CST)

**Rollback** (< 2 minutes):
1. `launchctl bootout gui/$(id -u) <plist_path>`
2. `crontab /tmp/crontab_backup_<date>.txt`

---

## 5. Phase Summary

| Phase | Scope | Files Changed | Lines Added | Authorization | Prerequisite |
|---|---|---|---|---|---|
| **Phase 1a** | Validity window guard | `hybrid_shadow_cron.py` | ~25 | Required | — |
| **Phase 1b** | Same-day guard | `hybrid_shadow_cron.py` | ~12 | Required | — |
| **Phase 1c** | Log append wrapper | `scripts/run_daily_cron.sh` (new) | 5 | Required for Phase 3 | Phase 3 only |
| **Phase 2** | 18 offline tests | `tests/test_cron_safety_guards.py` (new) | ~300 | Required | Phase 1 |
| **Phase 3** | LaunchAgent deployment | plist + crontab removal | 0 Python | Deployment auth | Phase 1+2+H3 |

---

## 6. Rollback Plan for Each Phase

| Phase | Rollback | Time | Risk |
|---|---|---|---|
| Phase 1a/b | Revert `hybrid_shadow_cron.py` to previous hash | < 5 min | LOW |
| Phase 2 | Delete `test_cron_safety_guards.py` | < 1 min | NONE (tests only) |
| Phase 3 | `launchctl bootout` + restore crontab | < 2 min | LOW |

---

## 7. What This Plan Does NOT Change

- `backfill_daily_prices.py` (RC-2 patch — hash must remain `4eb6eacf...`)
- `run_hybrid_forward_shadow.py`
- `src/research/dailyprice_quality_gate.py` (QG-1~QG-7)
- `src/research/full_market_freshness_gate.py`
- SQLite schema (`data/platform.db`)
- Neon schema
- RC-2 filter logic (`_is_excluded()`)
- Model weights / signal logic
- `data/.cron_state.json` schema (additive only)

---

## 8. Verdict

| Item | Status |
|---|---|
| **Phase 1 design** | `IMPLEMENTATION_READY` — 37 total lines |
| **Phase 2 design** | `IMPLEMENTATION_READY` — 18 test cases designed |
| **Phase 3 design** | `IMPLEMENTATION_READY` — plist + runbook complete |
| **Authorization received** | `NONE` — all phases require authorization |
| **H3 status** | `PENDING` — required before Phase 3 |
| **Overall** | `IMPLEMENTATION_PLAN_COMPLETE` |
