# Hybrid Forward Shadow — Go-Live Readiness & Runbook

**Date:** 2026-11-05  
**Status:** CONDITIONAL — preflight passes with 4 warnings; awaiting manual approval

---

## Preflight Summary

```
python3 scripts/hybrid_shadow_preflight.py
```

| Section | Result |
|---------|--------|
| Environment (8 checks) | 7 PASS, 1 WARNING (USE_NEON=true) |
| DB Isolation (4 checks) | 4 PASS |
| Data Integrity (5 checks) | 3 PASS, 2 WARNING (orphan WAL, backup) |
| Cron Safety (5 checks) | 3 PASS, 2 WARNING (backup, macOS FDA) |
| **Overall** | **CONDITIONAL** |

No BLOCKED checks. Cron installation is safe to proceed once warnings acknowledged.

---

## Go/No-Go Checklist

| # | Criterion | Status | Notes |
|---|-----------|--------|-------|
| 1 | OHLCContinuityGate market gate PASS | ✅ PASS | present=30, missing=0 |
| 2 | 0050 data complete for 30-day window | ✅ COMPLETE | 10 dates recovered |
| 3 | Calendar errors corrected | ✅ FIXED | 09-28, 10-23, 10-26 added as holidays |
| 4 | DB integrity check | ✅ OK | 528,182 rows, 0 FK violations |
| 5 | Cron fail-closed (Step 4b ABORT) | ✅ VERIFIED | HC26 confirms BLOCKED_STALE_DATA |
| 6 | Backfill coverage-aware | ✅ FIXED | _find_missing_dates uses stock universe coverage |
| 7 | Backfill idempotent when current | ✅ FIXED | start > end exits 0, not 1 |
| 8 | Full test suite | ✅ 1619 PASS | 0 failures |
| 9 | Ruff clean | ✅ CLEAN | 0 errors in all modified files |
| 10 | Neon production untouched | ✅ CONFIRMED | Only local SQLite written |
| 11 | Preflight script available | ✅ CREATED | `scripts/hybrid_shadow_preflight.py` |
| 12 | Local crontab installed | ⏳ PENDING | Requires explicit user approval |
| 13 | Off-device backup | ⚠️ NOT CONFIGURED | SINGLE_DEVICE_FAILURE_RISK |
| 14 | macOS Full Disk Access for cron | ⚠️ UNVERIFIED | May need FDA in System Settings |

---

## Corrected Cron Entry

**Previous entry in this doc was INCORRECT** — missing `--execute` flag and used `python3` without full path.

### Correct entry (use this):

```cron
0 8 * * 1-5  /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 /Users/alicetu/Desktop/Antigravity/stock_platform/scripts/hybrid_shadow_cron.py --execute >> /Users/alicetu/Desktop/Antigravity/stock_platform/logs/hybrid_cron.log 2>&1
```

**Time:** 08:00 UTC = 16:00 Asia/Taipei (Taiwan is UTC+8, no DST)  
**Days:** Mon–Fri (cron schedule + `is_trading_day()` double-check)  
**Flag:** `--execute` is required; without it the cron only dry-runs and writes nothing

---

## Installation Procedure

### Step 1: Run preflight
```bash
cd /Users/alicetu/Desktop/Antigravity/stock_platform
python3 scripts/hybrid_shadow_preflight.py
```
Confirm: overall = PASS or CONDITIONAL (no BLOCKED)

### Step 2: Backup existing crontab
```bash
crontab -l > /tmp/crontab_backup_$(date +%Y%m%d).txt
echo "Backup saved to /tmp/crontab_backup_$(date +%Y%m%d).txt"
```

### Step 3: Verify macOS Full Disk Access
On macOS Sequoia (25.3), `cron` may need Full Disk Access to read/write files in `~/Desktop`:  
**System Settings → Privacy & Security → Full Disk Access → enable `cron`**

If `cron` is not in the list, add it:  
`/usr/sbin/cron` or via `Finder → Go → Go to Folder → /usr/sbin/cron`

### Step 4: Install cron entry
```bash
crontab -e
```
Add this line:
```
0 8 * * 1-5  /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 /Users/alicetu/Desktop/Antigravity/stock_platform/scripts/hybrid_shadow_cron.py --execute >> /Users/alicetu/Desktop/Antigravity/stock_platform/logs/hybrid_cron.log 2>&1
```

### Step 5: Verify installation
```bash
crontab -l | grep hybrid_shadow_cron
```
Expected output: the full cron line above.

### Step 6: First manual verification run
On the next trading day (Taiwan 16:00–17:00):
```bash
python3 scripts/hybrid_shadow_cron.py --status
```
Check for `status: SUCCESS` and `last_data_date: <today>`.

---

## Monitoring

### Check cron log
```bash
tail -50 logs/hybrid_cron.log
```

### Check last run status
```bash
python3 scripts/hybrid_shadow_cron.py --status
```

### Check data freshness
```bash
python3 -c "
import sqlite3; conn = sqlite3.connect('data/platform.db')
print('Last 0050 date:', conn.execute(\"SELECT MAX(date) FROM daily_prices WHERE stock_id='0050'\").fetchone()[0])
conn.close()
"
```

### Check forward decisions
```bash
python3 -c "
import sqlite3; conn = sqlite3.connect('data/platform.db')
rows = conn.execute('''
    SELECT trade_date, capture_classification, COUNT(*)
    FROM hybrid_forward_decision
    GROUP BY trade_date, capture_classification
    ORDER BY trade_date DESC LIMIT 10
''').fetchall()
for r in rows: print(r)
conn.close()
"
```

### Check backups
```bash
ls -lh data/backups/ 2>/dev/null || echo "No scheduled backups yet"
ls -lh data/platform_recover_backup_*.db 2>/dev/null
```

---

## Rollback

See `docs/hybrid_cron_rollback.md` for detailed rollback procedures.

**Quick stop:**
```bash
# Remove cron entry
crontab -l | grep -v hybrid_shadow_cron > /tmp/cron_no_hybrid.txt
crontab /tmp/cron_no_hybrid.txt
# Verify
crontab -l | grep hybrid_shadow_cron || echo "Stopped ✓"
```

---

## First Run Success Criteria

After the first successful `--execute` run, verify:

1. `python3 scripts/hybrid_shadow_cron.py --status` → `status: SUCCESS`
2. `last_data_date` = today's date
3. At least 1 `PROSPECTIVE` or `LATE_CAPTURE` decision in `hybrid_forward_decision`
4. No `INVALID_DATA` classifications
5. Backup created in `data/backups/`

See `docs/hybrid_first_live_run_acceptance.md` for full acceptance test procedure.

---

## Failure Recovery Summary

| Failure | Cron Status | Action |
|---------|-------------|--------|
| TWSE API unavailable | BACKFILL_FAILED (exit=1) | Wait and retry manually |
| Data not yet published | BLOCKED_STALE_DATA (exit=0) | Normal — data arrives ~15:30-16:00 |
| Holiday / weekend | SKIPPED_NON_TRADING_DAY (exit=0) | Normal |
| Another cron running | BLOCKED_LOCK (exit=0) | Wait or remove stale lock |
| OHLC gate blocked | BLOCKED_MISSING_OHLC (exit=1) | Recover OHLC data |
| Mac was asleep at 16:00 | No log entry | Run manually after wakeup |
| No stocks data | BLOCKED_MISSING_SIGNALS (exit=1) | Check backfill coverage |

---

## Remaining Risks

### SINGLE_DEVICE_FAILURE_RISK
All data (`data/platform.db`) and backups are on the same Mac.  
Off-device backup options (free):
- **iCloud:** `cp data/platform.db ~/Library/Mobile\ Documents/com~apple~CloudDocs/backups/`
- **Dropbox:** `cp data/platform.db ~/Dropbox/backups/`
- **External drive:** Mount and `cp data/platform.db /Volumes/MyDrive/backups/`

Recommend: add weekly backup to crontab after main cron is stable.

### macOS Full Disk Access
If cron cannot write to `~/Desktop/...`, it will fail silently or with permission errors.  
Verify FDA setting before first scheduled run.

### TWSE API Data Delay
TWSE publishes data at ~15:30 Taiwan time. If delayed, cron gets BLOCKED_STALE_DATA.  
This is correct behavior — not an error. Data will be available on next manual or automatic run.

---

## Approval Request

**This document does NOT activate the cron.**

To install, explicitly reply: **"approve crontab install"**

After approval, run the installation procedure above (Steps 1–6).  
Do not auto-install from any script — crontab requires manual `crontab -e`.
