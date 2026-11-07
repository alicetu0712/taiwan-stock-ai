# Hybrid Scheduler Recovery Plan — Session 32

**Date:** 2026-11-07  
**Status:** PLAN_ONLY — awaiting user authorization  
**Version:** session32_v1  

---

## Executive Summary

The 2026-11-06 Hybrid Shadow Cron failure is caused by **BTM (Background Task Management) authorization missing**. The recovery plan has four phases:

1. **Phase 1 (BTM fix)**: Grant BTM authorization for the cron entry in System Settings
2. **Phase 2 (Verification)**: Confirm cron execution via minute-level test
3. **Phase 3 (Market Data)**: Backfill 2026-11-06 DailyPrice (separate authorization)
4. **Phase 4 (Scheduled Acceptance)**: Wait for first successful scheduled run

---

## Phase 1 — BTM Fix (MANUAL, requires System Settings access)

### Option A: Re-authorize existing crontab (Recommended)

```
1. Open System Settings → General → Login Items & Extensions
2. Scroll to the bottom section (varies by macOS version):
   - Look for "Allow in Background" or "Background Allow"
   - Or check "Login Items" section for unrecognized entries
3. Find any entry related to:
   - cron / /usr/sbin/cron
   - Python / com.antigravity
   - Or any entry with "enable" toggle set to OFF
4. Toggle to ENABLED / ALLOW
```

If no entry appears in System Settings, it means BTM registration never completed.

### Option B: Re-register crontab to trigger BTM notification

```bash
# REQUIRES USER AUTHORIZATION
# Step 1: Remove current crontab
crontab -r

# Step 2: Wait 10 seconds for BTM to process removal
sleep 10

# Step 3: Re-install crontab
crontab -e
# (Add back the entry)

# Step 4: Wait for system notification:
# "Background Items Added - cron has added login items"
# Click "Review..." in notification

# Step 5: In System Settings, find the cron entry and Allow it

# Step 6: Verify BTM entry exists
sfltool dumpbtm | grep -i "cron"
```

**Expected result after fix:**
```
$ sfltool dumpbtm | grep -A5 "Identifier.*cron"
                 Type: legacy agent (0x10008)
                Flags: [ legacy ] (0x1)
          Disposition: [enabled, allowed, notified] (0xb)
```

### Option C: Migrate to launchd (alternative, see below)

---

## Phase 2 — Scheduler Verification (PENDING_APPROVAL)

### 2a — Minute-level cron test

```bash
# SCHEDULER_TEST_PENDING_APPROVAL
# Requires explicit authorization to modify crontab

# Generate test entry (for review only — NOT executing):
echo "* * * * * /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 \
  /private/tmp/cron_test/minimal_cron_test.py >> /tmp/cron_btm_test.log 2>&1"

# After authorization:
# 1. Install test entry: crontab -e (add above line)
# 2. Wait 60 seconds
# 3. Check: ls -la /tmp/cron_btm_test.log
# 4. If log exists → BTM authorized, cron working
# 5. Remove test entry: crontab -e (remove test line)
# 6. Verify only production entry remains
```

### 2b — launchd forks counter

After granting BTM and waiting for 16:00:
```bash
launchctl print system/com.vix.cron | grep "forks ="
# Expected: forks = N (N > 0)
```

### 2c — Log file verification

```bash
ls -la logs/hybrid_cron.log  # Must exist after first successful run
```

---

## Phase 3 — Market Data Backfill (SEPARATE AUTHORIZATION REQUIRED)

### Backfill Readiness Assessment

| Criterion | Status |
|---|---|
| Nov 6 source data available | PROBABLE (TWSE/TPEx historical APIs) |
| Backfill script supports historical dates | YES (`--start YYYY-MM-DD`) |
| Duplicate protection | YES (quality gate QG-5 blocks wrong-date writes) |
| Rollback plan | SQLite backup created before each run |
| DRY_RUN mode | YES (default, `--execute` required for writes) |
| Nov 6 is a valid trading day | YES (Friday, regular TWSE session) |

### Backfill Readiness: `BACKFILL_READY_FOR_APPROVAL`

### Pre-backfill checklist (if approved)

```bash
# 1. Verify current DB state
sqlite3 data/platform.db "SELECT date, COUNT(*) FROM daily_prices WHERE date >= '2026-11-04' GROUP BY date;"

# 2. Dry run first (safe — no writes)
python3 scripts/backfill_daily_prices.py --start 2026-11-06 --end 2026-11-06

# 3. Verify dry run shows expected stock counts
# Expected: ~6,500-7,000 stocks for Nov 6

# 4. ONLY AFTER AUTHORIZATION: Execute
python3 scripts/backfill_daily_prices.py --start 2026-11-06 --end 2026-11-06 --execute

# 5. Verify post-backfill
sqlite3 data/platform.db "SELECT COUNT(*) FROM daily_prices WHERE date='2026-11-06';"
```

### Important classification note

Even after backfill of Nov 6 market data:
- Any Nov 6 Hybrid decisions captured AFTER the backfill = **`LATE_CAPTURE`** (not `PROSPECTIVE`)
- `LATE_CAPTURE` has reduced but acceptable OOS validity weight
- Full `PROSPECTIVE` requires same-day capture (not possible retroactively)

---

## Phase 4 — Scheduled Acceptance

After Phase 1 (BTM fix) and Phase 2 (verification pass):

```
Next trading day after BTM fix → 16:00 Taiwan
  ↓
Expected: hybrid_cron.log created
Expected: cron_state.json updated
Expected: hybrid_forward_run_log has new entry
Expected: launchd forks > 0
Expected: PROSPECTIVE decisions captured (if market data fresh)
```

Verification checklist (from `hybrid_first_scheduled_run_acceptance.md`):
1. `ls -la logs/hybrid_cron.log` — must exist
2. `python3 scripts/hybrid_shadow_cron.py --status`
3. `cat data/.cron_state.json` — confirm trigger_source="cron_scheduled"
4. `sqlite3 data/platform.db "SELECT COUNT(*) FROM hybrid_forward_run_log WHERE trade_date >= '2026-11-10'"`
5. `sfltool dumpbtm | grep -c cron` — confirm BTM entry persists

---

## Cron vs launchd Comparison

| Item | Traditional cron | launchd LaunchAgent |
|---|---|---|
| Scheduler reliability (macOS 26.x) | **LOW** — BTM check blocks jobs | **HIGH** — better macOS integration |
| macOS 13+ compatibility | Requires explicit BTM authorization | Native; no BTM check for user agents |
| Configuration | `crontab -e` (5-field syntax) | XML plist file |
| Timezone | Inherits system timezone | Inherits system timezone |
| Working directory | None (must `cd` or use abs paths) | `WorkingDirectory` key available |
| Environment | Minimal (`PATH=/usr/bin:/bin:/usr/sbin:/sbin`) | `EnvironmentVariables` key |
| Logging | `>> logfile 2>&1` redirect | `StandardOutPath` / `StandardErrorPath` |
| Retry logic | External (via hybrid_shadow_cron.py) | External (same) |
| Sleep/wake | Missed if system asleep | Same — fires when system wakes (best-effort) |
| Maintenance | Simple text format | XML plist (more verbose) |
| FDA | Required for file access | Inherits user FDA |
| BTM restriction | **YES — cronBTMCheck blocks jobs** | **NO — user agents exempt** |

**Recommendation: launchd is safer for macOS 13+/26.x.** However, migration requires user authorization (launchctl bootstrap user/$UID).

### Proposed LaunchAgent plist (design only, NOT installing)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.antigravity.hybrid-shadow-cron</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Library/Frameworks/Python.framework/Versions/3.13/bin/python3</string>
        <string>/Users/alicetu/Desktop/Antigravity/stock_platform/scripts/hybrid_shadow_cron.py</string>
        <string>--execute</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key><integer>16</integer>
        <key>Minute</key><integer>0</integer>
    </dict>
    <key>WorkingDirectory</key>
    <string>/Users/alicetu/Desktop/Antigravity/stock_platform</string>
    <key>StandardOutPath</key>
    <string>/Users/alicetu/Desktop/Antigravity/stock_platform/logs/hybrid_launchd.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/alicetu/Desktop/Antigravity/stock_platform/logs/hybrid_launchd.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/Library/Frameworks/Python.framework/Versions/3.13/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
        <key>HOME</key>
        <string>/Users/alicetu</string>
    </dict>
</dict>
</plist>
```

**Installation (requires explicit authorization):**
```bash
# 1. Save plist to ~/Library/LaunchAgents/com.antigravity.hybrid-shadow-cron.plist
# 2. Load: launchctl bootstrap gui/501 ~/Library/LaunchAgents/com.antigravity.hybrid-shadow-cron.plist
# 3. Verify: launchctl print gui/501/com.antigravity.hybrid-shadow-cron
# 4. If migrating from cron: crontab -r  (after launchd is verified working)
```

**Caveats:**
- LaunchAgent only fires while user is logged in (GUI session active)
- `StartCalendarInterval` does NOT backfill missed runs (similar to cron on macOS)
- The existing retry logic in `hybrid_shadow_cron.py` remains unchanged
- The `trigger_source` detection (`sys.stdout.isatty()`) will show `"cron_scheduled"` for launchd runs (no TTY) — same as existing design

---

## V3 Shadow Activation Blockers (Updated)

| R | Status | Change from Session 31 |
|---|---|---|
| R3 0050 Nov 6 | FAIL | Unchanged (0 rows) |
| R4 TWSE proxy | FAIL | Unchanged |
| R5 TPEx proxy | FAIL | Unchanged |
| R8 live captures | FAIL_NO_EVIDENCE | Unchanged |
| R13 Cron Acceptance | CRON_EXECUTION_FAILURE | Root cause now CONFIRMED: BTM_AUTHORIZATION_MISSING |
| R16 Explicit Approval | PENDING | Unchanged |

**All 6 blockers remain. Activation verdict: `ACTIVATION_BLOCKED`**

Earliest possible V3 activation:
1. Phase 1 complete (BTM fix) — requires System Settings action
2. Phase 2 complete (scheduler verification) — requires test crontab authorization
3. Phase 3 complete (Nov 6 backfill) — requires explicit data write authorization
4. Phase 4 complete (first successful scheduled run with PROSPECTIVE decisions) — requires waiting for next trading day 16:00
5. Phase 5 (R16 explicit approval) — requires human authorization decision

---

## Required Approvals Checklist

| Action | Type | Phase |
|---|---|---|
| System Settings BTM authorization | Manual GUI — no code | 1 |
| Test crontab install + remove | Crontab modification | 2 |
| `backfill_daily_prices.py --execute` | Production data write | 3 |
| launchctl bootstrap (if migrating) | System service install | 4 (optional) |
| crontab -r (if migrating to launchd) | Crontab removal | 4 (optional) |
| V3 Shadow Activation | Explicit research authorization | 5 |
