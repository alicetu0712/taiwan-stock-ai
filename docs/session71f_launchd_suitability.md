# Session 71F — LaunchD Suitability Evaluation

**Date**: 2026-11-11  
**Authorization**: STRICT_READ_ONLY / DESIGN_ONLY  
**Note**: This document is DESIGN ONLY. No launchd installation, modification, or loading is authorized.

---

## 1. Problem Statement

Traditional cron on macOS silently skips jobs when the machine is asleep at fire time. The backfill job (`hybrid_shadow_cron.py`) runs at 16:00 CST daily. If the machine is sleeping, the job is missed with no retry.

Requirement: reliable daily execution of backfill job, tolerant of machine sleep, without increasing production risk.

---

## 2. macOS Scheduler Comparison

| Feature | Traditional Cron | launchd (StartCalendarInterval) |
|---|---|---|
| Runs user jobs | YES | YES |
| Wakes machine from sleep | NO | NO (unless `WakeForHead` or `pmset schedule`) |
| Catches up missed job after wake | **NO** (vixie-cron drops it) | **YES** — fires within 60 s of wake if missed |
| Idempotency guard | NONE (script-level only) | NONE (script-level only) |
| Logging | stdout/stderr redirect | stdout/stderr to files or `StandardOutPath` |
| Environment variables | Minimal cron env | Same user env as login shell (`EnvironmentVariables`) |
| Holiday / trading day logic | Script-level | Script-level |
| Configuration | `crontab -e` | `.plist` file in `~/Library/LaunchAgents/` |
| Load method | Automatic via crond | `launchctl bootstrap gui/$UID <plist>` |
| System integration | Mature, stable | Native macOS, preferred since 10.4 |
| Multiple-fire protection | Cron minute-tick | launchd ensures single instance per interval |

**Critical difference**: launchd `StartCalendarInterval` has **catch-up behavior** — if the machine was asleep during the scheduled time, launchd fires the job the next time the machine is awake (within a grace window). This directly addresses the Nov 11 failure.

---

## 3. Safety Analysis for Our Script

### 3A. Idempotency Assessment

`hybrid_shadow_cron.py` is designed to be run once per day:

| Safety feature | Present | Detail |
|---|---|---|
| FileLock (`fcntl.flock`) | YES | Prevents concurrent runs |
| `is_trading_day()` check | YES | Skips weekends / holidays |
| State file check (`data/.cron_state.json`) | YES | Records last run date |
| Quality Gate | YES | Validates data freshness before writing |
| Read-only Neon | YES | Script never writes to production |

**Key question**: Is it safe if launchd fires at e.g. 18:00 CST (after waking from 16:00 sleep)?

| Scenario | Behavior | Safe? |
|---|---|---|
| Fires at 16:05 (slight delay) | Writes new data for today | YES |
| Fires at 18:00 (2h delay) | Writes new data for today | YES — TWSE data still available |
| Fires twice in same day (e.g. 16:00 + 18:00) | Second run: FileLock or state file prevents duplicate write | YES (if idempotency verified) |
| Fires on non-trading day | `is_trading_day()` check skips | YES |

**Idempotency verdict**: CONDITIONAL SAFE — the script has layered guards. launchd single-instance guarantee prevents true concurrent runs. The state file `run_at` check provides same-day deduplication at application level.

### 3B. Environment Compatibility

| Variable | Cron provides | LaunchD requires |
|---|---|---|
| `PATH` | Minimal (needs full path in crontab) | Must set via `EnvironmentVariables` or use full paths |
| `HOME` | Not guaranteed | Set by launchd from user context |
| `PYTHONPATH` | Not set | Must set explicitly |
| `.env` file | Not loaded | Script loads it via `dotenv` — OK |

Current crontab already uses full Python path (`/Library/Frameworks/Python.framework/Versions/3.13/bin/python3`). LaunchD plist would use same approach.

---

## 4. Option A: Retain Traditional Cron + Wake Guard

**Description**: Keep existing crontab. User must ensure machine is awake between 15:50–16:10 CST on trading days.

| Attribute | Value |
|---|---|
| Implementation effort | Zero (crontab unchanged) |
| Authorization required | None |
| Reliability | LOW — depends on user discipline |
| Risk | LOW — no system changes |
| Catch-up behavior | NONE |
| Nov 12 success probability | HIGH only if machine is awake |

**Operational requirement**: User must be active on the machine or manually prevent sleep during the 16:00 CST window on every trading day.

---

## 5. Option B: Migrate to LaunchD Agent

**Description**: Replace crontab entry with a `~/Library/LaunchAgents/` plist using `StartCalendarInterval`. LaunchD catch-up behavior ensures job runs even after sleep.

| Attribute | Value |
|---|---|
| Implementation effort | Low (single .plist file) |
| Authorization required | YES — explicit user authorization needed |
| Reliability | HIGH — catch-up after sleep |
| Risk | LOW-MEDIUM — standard macOS mechanism |
| Catch-up behavior | YES — fires within ~60 s of wake |
| Nov 12 success probability | HIGH regardless of sleep state |

### 5A. Designed Plist Structure (NOT authorized — design only)

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
        <string>/Library/Frameworks/Python.framework/Versions/3.13/bin/python3</string>
        <string>/Users/alicetu/Desktop/Antigravity/stock_platform/scripts/hybrid_shadow_cron.py</string>
        <string>--execute</string>
    </array>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>8</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>/Users/alicetu/Desktop/Antigravity/stock_platform/logs/hybrid_cron.log</string>

    <key>StandardErrorPath</key>
    <string>/Users/alicetu/Desktop/Antigravity/stock_platform/logs/hybrid_cron.log</string>

    <key>WorkingDirectory</key>
    <string>/Users/alicetu/Desktop/Antigravity/stock_platform</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>HOME</key>
        <string>/Users/alicetu</string>
        <key>PATH</key>
        <string>/Library/Frameworks/Python.framework/Versions/3.13/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>

    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
```

**Plist file path** (design): `~/Library/LaunchAgents/com.antigravity.stockplatform.dailybackfill.plist`

### 5B. Option B Deployment Steps (NOT authorized — design only)

```bash
# Step 1: Write plist to LaunchAgents
cp /path/to/com.antigravity.stockplatform.dailybackfill.plist ~/Library/LaunchAgents/

# Step 2: Validate plist syntax
plutil -lint ~/Library/LaunchAgents/com.antigravity.stockplatform.dailybackfill.plist

# Step 3: Load agent (requires explicit authorization)
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.antigravity.stockplatform.dailybackfill.plist

# Step 4: Disable / remove crontab entry
crontab -l | grep -v hybrid_shadow_cron > /tmp/newcron && crontab /tmp/newcron

# Step 5: Verify loaded
launchctl list com.antigravity.stockplatform.dailybackfill
```

### 5C. Option B Risk Register

| Risk | Likelihood | Mitigation |
|---|---|---|
| LaunchD fires multiple times (catch-up + scheduled) | LOW | launchd guarantees one instance per interval; FileLock protects against concurrent |
| Wrong environment (missing .env vars) | MEDIUM | Script uses `python-dotenv` to load `.env`; WorkingDirectory set |
| Late catch-up runs TWSE after close | LOW | Script has QG; TWSE data is published post-close and available throughout day |
| Log append vs truncate conflict | LOW | Both stdout/stderr → same file; same as crontab behavior |
| Rollback complexity | LOW | `launchctl bootout gui/$UID <label>` + restore crontab |

---

## 6. Recommendation

**Recommended: Option B (launchd migration)**

The sleep-miss failure is **structural** — it will recur on any day the machine is on battery and not in active use around 16:00 CST. Option A (keep cron) cannot solve this without user discipline on every trading day.

Option B provides native macOS catch-up behavior with low implementation risk. The script already has idempotency guards (FileLock, state file, trading-day check, QG) that make delayed execution safe.

**Blocking conditions for Option B**:
1. User explicit authorization for launchd deployment
2. Removal of corresponding crontab entry (to avoid double-fire)
3. Test run verification (H3 must still complete under launchd)

---

## 7. Suitability Verdict

| Option | Verdict | Condition |
|---|---|---|
| **Option A (cron)** | `SUITABLE_WITH_CAVEAT` | Requires user to ensure machine awake at 16:00 CST |
| **Option B (launchd)** | `SUITABLE_RECOMMENDED` | Requires explicit user authorization; removes sleep-miss risk |
