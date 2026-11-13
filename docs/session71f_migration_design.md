# Session 71F — Scheduler Migration Design

**Date**: 2026-11-11  
**Authorization**: STRICT_READ_ONLY / DESIGN_ONLY  
**Note**: This document describes the migration plan. ZERO implementation actions are taken here.

---

## 1. Migration Goal

Replace macOS traditional cron with launchd `StartCalendarInterval` to eliminate the sleep-miss failure (`MISSED_DUE_TO_SLEEP`) observed on 2026-11-11.

---

## 2. Pre-Migration Prerequisites

| Prerequisite | Status | Action Required |
|---|---|---|
| H3 acceptance complete | PENDING | Complete H3 with natural execution (option A or B) first |
| User authorization for launchd | NOT OBTAINED | Must receive explicit "execute Option B" instruction |
| Plist design reviewed | COMPLETE (this doc) | — |
| Rollback plan documented | COMPLETE (Section 6) | — |
| Test plan written | COMPLETE (Section 5) | — |

**Recommended sequencing**: Complete H3 acceptance under current cron first (Option A, Nov 12), then migrate to launchd for future reliability.

---

## 3. Migration Steps (DESIGN ONLY — NOT AUTHORIZED)

### Phase 1: Prepare Plist

```bash
# Create plist (requires authorization)
cat > ~/Library/LaunchAgents/com.antigravity.stockplatform.dailybackfill.plist << 'EOF'
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
        <key>Hour</key><integer>8</integer>
        <key>Minute</key><integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/Users/alicetu/Desktop/Antigravity/stock_platform/logs/hybrid_cron.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/alicetu/Desktop/Antigravity/stock_platform/logs/hybrid_cron.log</string>
    <key>WorkingDirectory</key>
    <string>/Users/alicetu/Desktop/Antigravity/stock_platform</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>HOME</key><string>/Users/alicetu</string>
        <key>PATH</key><string>/Library/Frameworks/Python.framework/Versions/3.13/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
    <key>RunAtLoad</key><false/>
</dict>
</plist>
EOF

# Validate (read-only — safe anytime)
plutil -lint ~/Library/LaunchAgents/com.antigravity.stockplatform.dailybackfill.plist
```

### Phase 2: Load LaunchD Agent

```bash
# Load agent (requires authorization)
launchctl bootstrap gui/$UID \
  ~/Library/LaunchAgents/com.antigravity.stockplatform.dailybackfill.plist

# Verify loaded
launchctl list com.antigravity.stockplatform.dailybackfill
# Expected: "0" exit code, PID "-" (not currently running)
```

### Phase 3: Remove Crontab Entry

```bash
# Save backup (always do first)
crontab -l > ~/Desktop/crontab_before_migration_$(date +%Y%m%d).txt

# Remove hybrid_shadow_cron entry
crontab -l | grep -v "hybrid_shadow_cron" | crontab -

# Verify removal
crontab -l | grep hybrid_shadow_cron
# Expected: (no output)
```

### Phase 4: Verify Migration

```bash
# 1. launchd agent listed
launchctl list com.antigravity.stockplatform.dailybackfill

# 2. crontab entry gone
crontab -l | grep hybrid

# 3. Log baseline for new run
tail -n 5 logs/hybrid_cron.log
```

---

## 4. Acceptance Criteria for Migration

| Criterion | Test | Expected |
|---|---|---|
| Agent loaded | `launchctl list <label>` | Returns entry without error |
| Crontab cleared | `crontab -l \| grep hybrid` | Empty |
| First natural fire | Log shows new entry with launchd timestamp | New entry dated next trading day |
| Catch-up behavior | Machine asleep at 16:00, then wake | Job fires within 60 s of wake |
| No double-fire | Log entries per day | Exactly 1 run per trading day |
| SQLite writes | New rows after catch-up fire | Rows with correct date added |
| Filter compliance | No `len(stock_id) > 4` in new rows | Zero contamination |

---

## 5. Transition Period

During the transition window (Option A → Option B):

| Phase | Scheduler | Action |
|---|---|---|
| Now → H3 complete | Traditional cron | Keep cron; ensure machine awake at 16:00 |
| H3 complete → migration authorized | Traditional cron | Await authorization |
| Migration authorized | LaunchD | Execute Phases 1–4 above |
| Post-migration H3' | LaunchD | Verify new scheduler fires naturally; run acceptance checks |

---

## 6. Rollback Plan

If launchd migration causes issues (unexpected behavior, double-fire, environment errors):

```bash
# Step 1: Unload agent
launchctl bootout gui/$UID \
  ~/Library/LaunchAgents/com.antigravity.stockplatform.dailybackfill.plist

# Step 2: Remove plist
rm ~/Library/LaunchAgents/com.antigravity.stockplatform.dailybackfill.plist

# Step 3: Restore crontab from backup
crontab ~/Desktop/crontab_before_migration_<date>.txt

# Step 4: Verify cron restored
crontab -l | grep hybrid_shadow_cron
```

Rollback time estimate: **< 2 minutes**.

---

## 7. Design Verdict

| Item | Status |
|---|---|
| Migration design | COMPLETE |
| Plist structure | DESIGNED (not created) |
| Rollback plan | DOCUMENTED |
| Test plan | DOCUMENTED |
| Authorization obtained | NOT YET |
| Implementation | **NOT AUTHORIZED — awaiting explicit instruction** |
