# Isolated Cron Test Approval Plan — Session 33

**Date:** 2026-11-07  
**Status:** SCHEDULER_TEST_PENDING_APPROVAL  
**Version:** session33_v1  

---

## 1. Purpose

This plan describes an isolated, reversible cron test to verify whether the macOS scheduler can fire jobs under current system conditions. It is NOT a test of the production Hybrid Shadow script.

The test has three stages:
- **Stage A** (Preparation) — COMPLETE, no authorization needed
- **Stage B** (Scheduler Installation) — PENDING_APPROVAL
- **Stage C** (Scheduled Observation) — Requires Stage B authorization

---

## 2. Stage A — Preparation (COMPLETE)

### Probe Script

```
Path:    scripts/diagnostics/cron_probe.py
Version: v1
Tests:   30 tests (CP01–CP30), all PASS
```

**Manual execution verified:**
```bash
$ python3 scripts/diagnostics/cron_probe.py --dry-run
{
  "probe_version": "v1",
  "test_id": "483de843-d994-4e87-b673-5da1b7f8e25f",
  "utc_timestamp": "2026-11-07T04:58:59.622949+00:00",
  "taiwan_timestamp": "2026-11-07T12:58:59.622949+08:00",
  "pid": 52925,
  "uid": 501,
  ...
}
```

### Probe Safety Properties
- No imports from src.research or trading modules
- No SQLite or Neon connections
- No network calls
- No crontab modification
- Output to dedicated directory only
- AST-verified (CP28/CP29/CP30)

---

## 3. Stage B — Scheduler Installation (PENDING_APPROVAL)

### Required Authorization

**The user must explicitly authorize crontab modification before Stage B begins.**

No crontab modification will occur without explicit authorization.

### Proposed Crontab Entry

```
* * * * *  /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 /Users/alicetu/Desktop/Antigravity/stock_platform/scripts/diagnostics/cron_probe.py --execute --output-dir /tmp/cron_probe_output >> /tmp/cron_probe_redirect.log 2>&1
```

| Field | Value | Meaning |
|---|---|---|
| Minute | `*` | Every minute |
| Hour | `*` | Every hour |
| Day | `*` | Every day |
| Month | `*` | Every month |
| DOW | `*` | Every weekday |
| Script | `cron_probe.py` | Isolated probe only |
| Output dir | `/tmp/cron_probe_output` | Temp — not in project |
| Redirect log | `/tmp/cron_probe_redirect.log` | Stderr capture |

### Production Crontab Protection

**Before installing the test entry:**
1. Backup current crontab: `crontab -l > /tmp/crontab_backup_$(date +%Y%m%d_%H%M%S).txt`
2. Verify backup exists and contains production entry
3. Only then: `crontab -e` to add test entry

The production entry must remain intact:
```
0 16 * * 1-5  /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 /Users/alicetu/Desktop/Antigravity/stock_platform/scripts/hybrid_shadow_cron.py --execute >> /Users/alicetu/Desktop/Antigravity/stock_platform/logs/hybrid_cron.log 2>&1
```

### Pre-installation Checklist

- [ ] User has explicitly authorized test crontab installation
- [ ] Production crontab backed up to `/tmp/crontab_backup_YYYYMMDD_HHMMSS.txt`
- [ ] Test script dry-run PASS confirmed
- [ ] `/tmp/cron_probe_output` directory writable
- [ ] Enough time to observe (at least 2 minutes before removal)

---

## 4. Stage C — Scheduled Observation (Requires Stage B)

### Expected Trigger Time

After installation: within 60 seconds (fires on next full minute).

### Success Conditions

1. `/tmp/cron_probe_output/cron_probe_*.json` created
2. File contains valid JSON with `pid > 0`
3. `/tmp/cron_probe_redirect.log` created (even if empty = OK)
4. `launchctl print system/com.vix.cron | grep "forks ="` shows forks > previous count
5. Record UID=501 (alicetu)

### Failure Conditions

1. No output file after 120 seconds → **Cron still NOT triggering**
2. Output file exists but `uid != 501` → Execution context wrong
3. `/tmp/cron_probe_redirect.log` contains Python error → Environment problem
4. `launchctl forks` unchanged after 120 seconds → BTM still blocking

### Interpretation

| Scenario | forks | Output file | Meaning |
|---|---|---|---|
| BTM now authorized | +N | EXISTS | BTM was the cause; cron now works |
| BTM still blocking | 0 | ABSENT | BTM authorization not yet granted |
| Other blocker | +N | ABSENT | Fork happened but script failed |
| Environment issue | +N | EXISTS but malformed | Python env problem |

**A test failure here does NOT mean cron is permanently broken — it means BTM authorization is still needed.**

---

## 5. Test Duration and Removal

### Duration
- Minimum: 2 minutes (to observe 2 trigger attempts)
- Maximum: 10 minutes (before removal)
- Do NOT leave test entry installed overnight

### Removal Procedure

**After observation (requires user authorization to remove):**

```bash
# Step 1: Show current crontab
crontab -l

# Step 2: Remove test entry, keep production entry
# (crontab -e, delete the * * * * * line)

# Step 3: Verify only production entry remains
crontab -l
# Expected: only the 0 16 * * 1-5 line

# Step 4: Verify no stale probe output older than test session
ls -la /tmp/cron_probe_output/
```

### Rollback Procedure

If anything goes wrong during Stage B/C:

```bash
# Full crontab restore
crontab /tmp/crontab_backup_YYYYMMDD_HHMMSS.txt

# Verify
crontab -l
```

---

## 6. What This Test Does NOT Prove

- **A test PASS does not mean Hybrid Shadow cron is now working.** The probe uses a different script path and fires every minute (not at 16:00).
- **A test PASS does not advance V3 Activation.** The activation requires the FORMAL Hybrid cron to execute successfully on a trading day 16:00.
- **A test FAIL does not mean the production entry is broken.** It only confirms BTM authorization is still needed.

---

## 7. After Test: BTM Verification

Whether test passes or fails, check BTM state:

```bash
# If test PASS: should see cron entry in BTM
sfltool dumpbtm | grep -A10 "cron\|hybrid"

# If test FAIL: still no cron entry
sfltool dumpbtm | grep -c "cron"

# Check forks counter
launchctl print system/com.vix.cron | grep "forks ="
```

---

## 8. Authorization Request

To proceed with Stage B, the user must authorize:

> **"I authorize installation of the test crontab entry described in Stage B. I understand this is a temporary entry to be removed within 10 minutes, and does not modify the production Hybrid Shadow entry."**

Current status: `SCHEDULER_TEST_PENDING_APPROVAL`
