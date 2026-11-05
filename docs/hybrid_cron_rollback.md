# Hybrid Cron Rollback Procedure

**Date:** 2026-11-05  
**Scope:** Local macOS crontab for `hybrid_shadow_cron.py`

---

## Disable Cron (Emergency Stop)

```bash
# Option A: Edit and remove the cron line
crontab -e   # delete the hybrid_shadow_cron.py line, save

# Option B: Remove entire crontab (only if no other cron jobs exist)
crontab -r

# Option C: Comment out without editing interactively
crontab -l | grep -v hybrid_shadow_cron > /tmp/cron_disabled.txt
crontab /tmp/cron_disabled.txt
```

Verify disabled:
```bash
crontab -l | grep hybrid_shadow_cron || echo "Cron entry removed ✓"
```

---

## Restore Original Crontab

Before installing the cron, you should have backed up the existing crontab:

```bash
# Restore from backup
crontab /tmp/crontab_backup_YYYYMMDD.txt
```

If no backup exists and crontab was empty before:
```bash
crontab -r   # removes all entries
```

---

## Preserve Already-Captured Forward Decisions

Do NOT delete `data/platform.db` to roll back — this would destroy all research history.

Forward decisions are append-only: they are never deleted or modified by the cron.  
Disabling the cron only stops NEW captures; existing decisions are preserved.

If you want to view existing PROSPECTIVE decisions before rollback:
```bash
python3 -c "
import sqlite3; conn = sqlite3.connect('data/platform.db')
rows = conn.execute('''
    SELECT trade_date, capture_classification, COUNT(*) 
    FROM hybrid_forward_decision 
    GROUP BY trade_date, capture_classification 
    ORDER BY trade_date DESC LIMIT 20
''').fetchall()
for r in rows: print(r)
conn.close()
"
```

---

## Avoid Duplicate Execution

The file lock at `data/.cron.lock` prevents simultaneous runs.  
If the cron is re-enabled after a gap, the first run will:
1. Check the lock (not held → proceed)
2. Detect the data gap via Step 4b (BLOCKED_STALE_DATA if data not fetched)
3. Exit cleanly — no duplicate decisions generated

For decisions, `INSERT OR IGNORE` on `(stock_id, trade_date, rule_version)` ensures idempotency.

---

## Failure Recovery Procedures

### Provider (TWSE) API Failure

**Symptoms:** Cron status = `BACKFILL_FAILED`, backfill stderr mentions HTTP error.

**Recovery:**
```bash
# Check TWSE manually
curl -s "https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK?response=json&date=20261105&type=MS" | python3 -m json.tool | head -30

# Manual backfill for missed dates
python3 scripts/backfill_daily_prices.py --start YYYY-MM-DD --end YYYY-MM-DD --execute

# Re-run shadow manually for the missed date
python3 scripts/run_hybrid_forward_shadow.py --date YYYY-MM-DD
```

**Note:** If more than 1 trading day has passed since the original trade_date, decisions captured will be `LATE_CAPTURE`, not `PROSPECTIVE`. This is acceptable and transparent in the DB.

### Missing OHLC / Gate Blocked

**Symptoms:** Shadow runner returns `BLOCKED_MISSING_OHLC`.

**Recovery:**
1. Run `python3 scripts/hybrid_shadow_preflight.py` to identify missing dates.
2. Use `python3 scripts/recover_ohlc_0050.py --execute` for 0050 (see `docs/historical_ohlc_recovery_report.md`).
3. Wait for the coverage gap to age out of the 30-day window (if individual stocks affected).

### Calendar Conflict

**Symptoms:** Cron runs on a holiday, or skips a valid trading day.

**Recovery:**
1. Check `src/core/trading_calendar.py` → `_TWSE_HOLIDAYS`.
2. Cross-check against TWSE FMTQIK official calendar.
3. Update `_TWSE_HOLIDAYS` and add test for the new holiday.
4. Re-run the cron for the affected date if needed.

### Database Lock (`BLOCKED_LOCK`)

**Symptoms:** Cron status = `BLOCKED_LOCK`.

**Check:**
```bash
cat data/.cron.lock   # shows PID of process holding lock
ps aux | grep hybrid_shadow_cron   # check if that PID is running
```

**Recovery:**
```bash
# If the PID is dead but lock file remains:
rm data/.cron.lock
# Next cron run will acquire the lock normally
```

### Backup Failure

**Symptoms:** Cron log shows `[backup] ERROR`.

**Recovery:**
1. Check disk space: `df -h data/`
2. Check backup dir permissions: `ls -la data/backups/`
3. Manual backup: `cp data/platform.db data/backups/platform_$(date +%Y%m%d_manual).db.bak`

**Note:** Backup failure does NOT stop the shadow run (the cron continues).  
If you want to stop on backup failure, you must modify `hybrid_shadow_cron.py`.

### Mac Sleep / Shutdown (Missed Runs)

macOS cron does NOT run missed jobs after wakeup. If the Mac was asleep during the 16:00 slot:

```bash
# Check last cron state
python3 scripts/hybrid_shadow_cron.py --status

# Manually run for the missed date
python3 scripts/run_hybrid_forward_shadow.py --date YYYY-MM-DD
```

**Important:** Decisions captured the following day for a missed date will be:
- `PROSPECTIVE` if `trading_days_since_trade <= 1` (missed by 1 day)
- `LATE_CAPTURE` if `trading_days_since_trade > 1` (missed by 2+ days)

This is NOT reported as cron success — the absence of a run log entry for that date indicates missed execution.

### No Formal Signals

**Symptoms:** Shadow runner returns `BLOCKED_MISSING_SIGNALS`.

**Recovery:**
```bash
# Check if stocks have data for the target date
python3 -c "
import sqlite3; conn = sqlite3.connect('data/platform.db')
cnt = conn.execute(\"SELECT COUNT(DISTINCT stock_id) FROM daily_prices WHERE date='YYYY-MM-DD' AND stock_id!='0050'\").fetchone()[0]
print(f'Stocks with data: {cnt}')
conn.close()
"
```

If 0 stocks: backfill did not run successfully. See Provider Failure above.  
If `> 0` stocks but `< 100`: data quality issue — check backfill QG gate output.

---

## Backup Restore

```bash
# List available backups
ls -lh data/backups/ data/platform_recover_backup_*.db 2>/dev/null

# Restore from a cron-created backup
cp data/backups/platform_YYYYMMDD_TTTTTTTTTTZ.db.bak /tmp/restored_platform.db
sqlite3 /tmp/restored_platform.db "PRAGMA integrity_check;"  # verify before use

# Replace live DB with restored (only after confirming integrity)
cp data/platform.db data/platform_pre_restore_backup.db  # keep current
cp /tmp/restored_platform.db data/platform.db
```

**SINGLE_DEVICE_FAILURE_RISK:** All backups are on the same Mac.  
Off-device backup options (choose one):
- `cp data/platform.db ~/Library/Mobile\ Documents/com~apple~CloudDocs/backups/` (iCloud)
- `rsync -a data/platform.db user@remote:/backup/`
- Dropbox: `cp data/platform.db ~/Dropbox/backups/`

---

## State After Rollback

| Item | Preserved | Reason |
|------|-----------|--------|
| Forward decisions | ✅ Yes | Append-only table — cron disable doesn't delete |
| DB integrity | ✅ Yes | No rollback needed; just stop future runs |
| Crontab | Removed | As requested |
| Log files | ✅ Yes | `logs/hybrid_cron.log` persists |
| Cron state JSON | ✅ Yes | `data/.cron_state.json` persists |

Rollback is non-destructive by design.
