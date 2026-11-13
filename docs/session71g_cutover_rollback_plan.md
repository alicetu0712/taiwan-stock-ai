# Session 71G — Cutover & Rollback Plan

**Date**: 2026-11-11  
**Authorization**: STRICT_READ_ONLY / MIGRATION_DESIGN_ONLY  
**Note**: This document is DESIGN ONLY. No steps executed here.

---

## 1. G1 — Pre-deployment Gate

All must pass before migration proceeds.

| Check | Verification Command | Accept Criterion |
|---|---|---|
| Explicit user authorization | (verbal/written) | "AUTHORIZED" received |
| H3 acceptance complete | `grep "\[2026-11-1" logs/hybrid_cron.log \| tail -5` | At least one natural cron run observed post-RC2 |
| RC-2 hash | `shasum -a 256 scripts/backfill_daily_prices.py` | `4eb6eacf...` |
| Cron baseline captured | `crontab -l > ~/Desktop/crontab_backup_$(date +%Y%m%d).txt` | File created |
| Lock state clean | `cat data/.cron.lock && kill -0 $(cat data/.cron.lock) 2>/dev/null` | PID dead or file missing |
| No running backfill | `pgrep -f hybrid_shadow_cron \| pgrep -f backfill_daily_prices` | No output |
| DB baseline captured | `python3 -c "import sqlite3; c=sqlite3.connect('file:data/platform.db?mode=ro',uri=True).cursor(); c.execute('SELECT COUNT(*),MAX(date) FROM daily_prices'); print(c.fetchone())"` | Recorded for rollback comparison |
| Plist syntax valid | `plutil -lint ~/Library/LaunchAgents/com.antigravity.stockplatform.dailybackfill.plist` | "OK" |
| Rollback plan reviewed | (this document) | Confirmed |

---

## 2. G2 — Offline Validation

Before loading, validate the plist without triggering execution.

```bash
# 2a. Plist syntax check (read-only)
plutil -lint ~/Library/LaunchAgents/com.antigravity.stockplatform.dailybackfill.plist
# Expected: com.antigravity...plist: OK

# 2b. Verify Python path exists
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 --version
# Expected: Python 3.13.x

# 2c. Verify script exists and has correct hash
shasum -a 256 /Users/alicetu/Desktop/Antigravity/stock_platform/scripts/hybrid_shadow_cron.py
# Expected: 46209171...

# 2d. Verify working directory accessible
ls /Users/alicetu/Desktop/Antigravity/stock_platform/data/platform.db
# Expected: file exists

# 2e. Confirm no existing launchd agent with same label
launchctl list com.antigravity.stockplatform.dailybackfill 2>&1
# Expected: "Could not find service..." (not yet loaded)

# 2f. Dry-run script test (no DB writes, no provider calls)
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 \
  /Users/alicetu/Desktop/Antigravity/stock_platform/scripts/hybrid_shadow_cron.py
# Expected: "DRY-RUN complete" or "SKIPPED_NON_TRADING_DAY"
# (dry-run = no --execute; makes no writes or provider calls)
```

---

## 3. G3 — Controlled Cutover

**Critical design**: Eliminate the dual-scheduler window to prevent double-fire.

### 3A. Atomic Cutover Sequence (DESIGN ONLY)

```
Step 1: Verify no job is currently running
         pgrep -f hybrid_shadow_cron  → empty
         pgrep -f backfill_daily_prices → empty

Step 2: REMOVE crontab entry (single atomic edit)
         crontab -l | grep -v "hybrid_shadow_cron" > /tmp/newcron_$(date +%Y%m%d%H%M%S)
         crontab /tmp/newcron_<timestamp>
         crontab -l | grep hybrid   → empty (verify removal)

         ← DUAL SCHEDULER WINDOW BEGINS HERE (launchd not yet loaded)
         ← Duration should be < 60 seconds

Step 3: CREATE plist file
         [write plist to ~/Library/LaunchAgents/com.antigravity.stockplatform.dailybackfill.plist]

Step 4: LOAD launchd agent
         launchctl bootstrap gui/$UID \
           ~/Library/LaunchAgents/com.antigravity.stockplatform.dailybackfill.plist

         ← DUAL SCHEDULER WINDOW ENDS HERE

Step 5: VERIFY loaded
         launchctl list com.antigravity.stockplatform.dailybackfill
         # Expected: entry with PID="-" (waiting, not running)

Step 6: VERIFY cron removed
         crontab -l | grep hybrid_shadow_cron  → empty
```

### 3B. Timing Safety

| Event | Time | Risk |
|---|---|---|
| Crontab entry removed | T+0 | No scheduler active |
| Plist written | T+1s | Still no scheduler active |
| launchd bootstrap | T+5s | launchd active |
| Total window without scheduler | ~5 seconds | Acceptable if not during 15:59–16:01 window |

**Safety rule**: Do NOT execute cutover between 15:55 and 16:05 CST. Execute during off-schedule hours (e.g., 10:00–15:00 CST or after 17:00 CST).

### 3C. Catch-up Safety During Cutover

After launchd loads, it may immediately fire a catch-up if the last scheduled time was missed:
- If migration happens after 16:00 on a trading day → launchd detects the missed 16:00 fire → may fire immediately
- **Mitigation**: This is acceptable behavior — the catch-up is on the correct day

**How to suppress unexpected immediate catch-up** (if undesirable):
- Perform migration outside of trading day (weekend)
- Or: include `RunAtLoad=false` (already in design) — this prevents immediate fire on load; catch-up still fires when machine is next awake at scheduled interval

---

## 4. G4 — Post-deployment Acceptance

After cutover, verify correct state before waiting for first natural fire.

```bash
# 4a. launchd agent loaded
launchctl list com.antigravity.stockplatform.dailybackfill
# Expected: entry exists, PID="-"

# 4b. User context correct
launchctl list com.antigravity.stockplatform.dailybackfill | head -5
# Expected: runs as alicetu (GUI/$UID context)

# 4c. No crontab entry remaining
crontab -l | grep hybrid_shadow_cron
# Expected: empty

# 4d. No duplicate job
crontab -l | grep -c hybrid  # → 0
launchctl list | grep antigravity  # → 1 entry

# 4e. Script hash unchanged
shasum -a 256 scripts/backfill_daily_prices.py
# Expected: 4eb6eacf...

# 4f. Lock file clean
ls -la data/.cron.lock 2>/dev/null; echo "lock: $?"
# PID in lock should be dead or file absent

# 4g. State file unchanged
cat data/.cron_state.json | python3 -m json.tool
# Should still show last run (not a new run)
```

---

## 5. G5 — Rollback Design

**When to trigger rollback**:
- launchd fires unexpected catch-up at wrong time
- Shadow runner runs twice on same day
- launchd environment error (missing module, path not found)
- Any unexpected SQLite write observed
- User decision to revert

**Rollback steps** (DESIGN ONLY):

```bash
# Step 1: Unload launchd agent
launchctl bootout gui/$UID \
  ~/Library/LaunchAgents/com.antigravity.stockplatform.dailybackfill.plist

# Step 2: Verify unloaded
launchctl list com.antigravity.stockplatform.dailybackfill 2>&1
# Expected: "Could not find service..."

# Step 3: Remove plist (optional — keep as reference)
# mv ~/Library/LaunchAgents/com.antigravity.stockplatform.dailybackfill.plist \
#    ~/Desktop/launchd_plist_backup_$(date +%Y%m%d).plist

# Step 4: Restore crontab from backup
crontab ~/Desktop/crontab_backup_<date>.txt

# Step 5: Verify cron restored
crontab -l | grep hybrid_shadow_cron
# Expected: "0 16 * * 1-5  .../hybrid_shadow_cron.py --execute ..."

# Step 6: Verify no duplicate scheduler
crontab -l | grep hybrid | wc -l  # → 1
launchctl list | grep antigravity  # → empty

# Step 7: Verify SQLite unchanged (if rollback due to unexpected write)
python3 -c "
import sqlite3
c=sqlite3.connect('file:data/platform.db?mode=ro',uri=True).cursor()
c.execute('SELECT COUNT(*),MAX(date) FROM daily_prices')
print(c.fetchone())
"
# Compare to pre-migration baseline

# Step 8: Verify RC-2 hash
shasum -a 256 scripts/backfill_daily_prices.py
# Expected: 4eb6eacf...

# Step 9: Preserve logs
cp logs/hybrid_cron.log logs/hybrid_cron_pre_rollback_$(date +%Y%m%d%H%M%S).log
```

**Data rollback policy**: This plan does NOT authorize SQLite data rollback. If unexpected data was written, that requires separate authorization with explicit review of what was written.

---

## 6. Mid-cutover Failure Handling

| Failure point | State | Recovery |
|---|---|---|
| Crash after crontab removal, before plist write | No scheduler active | Write plist and load; or restore crontab from backup |
| Crash after plist write, before bootstrap | No scheduler active | Run `launchctl bootstrap gui/$UID <plist>` |
| Crash after bootstrap | launchd active | Verify state; run acceptance checks |
| launchd bootstrap error | No scheduler active | Check error message; restore crontab if unable to fix quickly |

---

## 7. Authorization Checklist

| Authorization Required | Status |
|---|---|
| H3 complete | PENDING |
| Explicit user "execute migration" instruction | NOT RECEIVED |
| Code changes (validity window guard) | SEPARATE AUTHORIZATION NEEDED |
| launchd installation | NOT AUTHORIZED (this session) |
| Crontab modification | NOT AUTHORIZED (this session) |

**This document is DESIGN ONLY. Zero steps executed.**
