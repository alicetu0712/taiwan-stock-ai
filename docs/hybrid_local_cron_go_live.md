# Hybrid Forward Shadow — Local Cron Go-Live

**Script:** `scripts/hybrid_shadow_cron.py`  
**Status:** READY FOR APPROVAL — not installed  
**Approval required:** User must explicitly authorize crontab installation

---

## 1. Architecture

```
Crontab (macOS cron)
  └── hybrid_shadow_cron.py --execute
        ├── File lock (fcntl.flock) — prevents concurrent runs
        ├── Calendar check — exits on non-trading days
        ├── Data readiness check — Taiwan time >= 15:30
        ├── backfill_daily_prices.py --execute (subprocess)
        │     └── QG-5 blocks wrong-date writes automatically
        ├── DB backup → data/backups/platform_YYYYMMDD_*.db.bak
        ├── run_hybrid_forward_shadow.py (subprocess)
        └── State written to data/.cron_state.json
```

**Safety constraints enforced at every run:**
- File lock prevents duplicate concurrent execution
- SQLite verification guard (`_verify_sqlite`) in backfill
- QG-5 blocks stale/wrong-date API data
- Backup created before every shadow run
- Dry-run default (`--execute` required for all writes)

---

## 2. Script Capabilities

```bash
# Check current status (no changes)
python3 scripts/hybrid_shadow_cron.py --status

# Dry-run (all checks, no writes)
python3 scripts/hybrid_shadow_cron.py

# Full execute (backfill + backup + shadow)
python3 scripts/hybrid_shadow_cron.py --execute

# Full execute without backup (testing only)
python3 scripts/hybrid_shadow_cron.py --execute --no-backup
```

---

## 3. Crontab Configuration (AWAITING APPROVAL)

**Step 1:** Get your exact paths:
```bash
pwd        # e.g., /Users/alice/stock_platform
which python3
```

**Step 2:** Configure log directory:
```bash
mkdir -p /Users/alice/stock_platform/logs
```

**Step 3:** Copy-paste crontab entry (do NOT install without approval):

```cron
# Hybrid Forward Shadow — daily DailyPrice backfill + signal capture
# Taiwan 16:00 = UTC 08:00 (replace paths before installing)
0 8 * * 1-5  /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 /Users/alicetu/Desktop/Antigravity/stock_platform/scripts/hybrid_shadow_cron.py --execute >> /Users/alicetu/Desktop/Antigravity/stock_platform/logs/cron.log 2>&1
```

**Step 4 (HUMAN ACTION — after approval):**
```bash
crontab -e
# Paste the line above, save, verify:
crontab -l
```

---

## 4. Timezone Notes

| Event | Taiwan (CST, UTC+8) | UTC |
|-------|---------------------|-----|
| Market open | 09:00 | 01:00 |
| Market close | 13:30 | 05:30 |
| Data ready | ~15:30 | ~07:30 |
| Recommended cron | 16:00 | 08:00 |

The script checks `_is_data_ready()` (Taiwan time >= 15:30) at every run:
- If run before 15:30 in dry-run mode → exits with `DATA_NOT_READY`
- If run before 15:30 with `--execute` → warns but continues; backfill QG-5 blocks wrong-date writes anyway

---

## 5. Backup Policy

| Setting | Value |
|---------|-------|
| Backup directory | `data/backups/` |
| Backup filename | `platform_YYYYMMDD_THHMMSSZ.db.bak` |
| Retention | 7 most recent (older auto-deleted) |
| Min size check | 100 KB (refuses to backup if DB seems empty) |

Backup is created *before* shadow runner writes — so DB state before each run is preserved.

---

## 6. State File

After each run, `data/.cron_state.json` stores:
```json
{
  "run_at": "2026-11-05T08:00:03Z",
  "today": "2026-11-05",
  "taiwan_time": "2026-11-05T16:00:03 CST",
  "execute": true,
  "status": "SUCCESS",
  "steps": {
    "lock": "released",
    "calendar": "trading_day",
    "data_ready": true,
    "backfill": {"exit_code": 0, "executed": true},
    "backup": "platform_20261105_T080003Z.db.bak",
    "shadow": {"exit_code": 0}
  },
  "last_data_date": "2026-11-05"
}
```

View with: `python3 scripts/hybrid_shadow_cron.py --status`

---

## 7. Troubleshooting

### Cron runs but nothing happens
1. Check log: `tail -50 logs/cron.log`
2. Check state: `python3 scripts/hybrid_shadow_cron.py --status`
3. Ensure log directory exists: `ls logs/`
4. Test Python path: `crontab -l` — verify the exact Python path matches `which python3`

### SKIPPED_NON_TRADING_DAY every day
- Holiday or weekend: expected
- Confirm Taiwan holidays in `src/core/trading_calendar.py`

### DATA_NOT_READY on trading days
- Cron fires before 15:30 Taiwan time — check UTC offset
- Taiwan is UTC+8; adjust cron if machine timezone differs

### BACKFILL_FAILED
- API may be down: run manually `python3 scripts/backfill_daily_prices.py`
- Check for QG-5 error (wrong-date data): try again after 15:30

### BLOCKED_LOCK
- Another cron instance is running: `ps aux | grep hybrid_shadow_cron`
- Stale lock after crash: `rm data/.cron.lock` (then verify no run is active)

### Backup NOT VERIFIED
- Directory: `ls data/backups/`
- Run once manually: `python3 scripts/hybrid_shadow_cron.py --execute`
- Check size: `du -sh data/backups/*.db.bak`

---

## 8. Acceptance Checklist (Human)

Before declaring cron go-live:

- [ ] `python3 scripts/hybrid_shadow_cron.py` (dry-run) exits cleanly
- [ ] `logs/` directory exists and is writable
- [ ] `data/backups/` directory exists (or will be auto-created)
- [ ] State file written correctly: `data/.cron_state.json`
- [ ] Crontab line reviewed with correct paths
- [ ] Run once manually with `--execute` to verify full pipeline
- [ ] First PROSPECTIVE record captured (see `docs/hybrid_first_prospective_capture.md`)
- [ ] User approves crontab installation

---

## 9. What This Script Does NOT Do

- Does **not** touch production Neon PostgreSQL
- Does **not** modify `MODEL_VERSION`, `RULE_VERSION`, or any frozen config
- Does **not** install itself — requires explicit `crontab -e` from user
- Does **not** push to GitHub or trigger any remote pipeline
- Does **not** overwrite existing decisions (UNIQUE constraint + ConflictError)
