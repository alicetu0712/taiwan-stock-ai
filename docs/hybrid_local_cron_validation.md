# Hybrid Forward Shadow — Local Cron Validation

**Date:** 2026-11-05  
**Current cron status:** NOT CONFIGURED (crontab empty)  
**Manual collection status:** 2026-11-04 DailyPrice added manually ✓

---

## 1. Current State

### Crontab audit result

```bash
$ crontab -l
# → (empty — no cron jobs configured)
```

**Finding:** Option D (local cron) is the intended operating mode, but no cron jobs exist. The researcher has been running the pipeline manually.

### Impact

| Component | Status without cron |
|-----------|---------------------|
| DailyPrice in local SQLite | Only updated when manually run |
| Hybrid Forward Shadow decisions | Only generated when manually run |
| PROSPECTIVE records | Cannot accumulate automatically |
| BLOCKED_STALE_DATA risk | High — 7-day tolerance means 1 missed week blocks the runner |

---

## 2. Required Daily Operations (until cron is configured)

Run these commands after each trading day's close (~15:30 Taiwan time):

```bash
# Step 1: Backfill any missing DailyPrice data
python3 scripts/backfill_daily_prices.py --execute

# Step 2: Run hybrid forward shadow for today's decisions
python3 scripts/run_hybrid_forward_shadow.py

# Step 3: Check the result
python3 -c "
import sqlite3, json
conn = sqlite3.connect('data/platform.db')
from src.research.hybrid_forward_db import get_operational_summary
summary = get_operational_summary(conn)
conn.close()
print(json.dumps(summary, indent=2, default=str))
"
```

---

## 3. Recommended Cron Configuration

### Prerequisites

1. Confirm the absolute path to your project:
   ```bash
   pwd  # e.g., /Users/alice/stock_platform
   ```

2. Confirm Python path:
   ```bash
   which python3  # e.g., /Library/Frameworks/Python.framework/.../bin/python3
   ```

### Cron entries

```cron
# Taiwan time 16:00 (UTC 08:00), Mon-Fri
# Step A: Backfill DailyPrice from TWSE/TPEx APIs
0 8 * * 1-5  cd /path/to/stock_platform && python3 scripts/backfill_daily_prices.py --execute >> logs/backfill_daily.log 2>&1

# Step B: Run hybrid forward shadow (5 min after backfill)
5 8 * * 1-5  cd /path/to/stock_platform && python3 scripts/run_hybrid_forward_shadow.py >> logs/hybrid_shadow.log 2>&1
```

Replace `/path/to/stock_platform` with your actual project path.

### Install cron

```bash
# Edit crontab
crontab -e

# Paste the two lines above (with correct path substituted)
# Verify:
crontab -l
```

---

## 4. Validation Steps (after cron is installed)

### Verify DailyPrice collection (after first cron run)

```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('data/platform.db')
last = conn.execute(\"SELECT MAX(date) FROM daily_prices WHERE stock_id='0050'\").fetchone()[0]
print(f'DailyPrice last date: {last}')
"
```

Expected: today's date (or yesterday if running before 15:30 Taiwan time).

### Verify shadow run (after second cron run)

```bash
python3 -c "
import sqlite3, json
conn = sqlite3.connect('data/platform.db')
from src.research.hybrid_forward_db import get_operational_summary
s = get_operational_summary(conn)
conn.close()
print('Last run status:', s['latest_run']['status'])
print('Total decisions:', s['total_decisions'])
print('PROSPECTIVE:', s['prospective_decisions'])
"
```

Expected: `status=SUCCESS`, `prospective_decisions > 0` (after RULE_FREEZE_DATE 2026-11-05).

---

## 5. Troubleshooting

### Scenario: Cron runs but no data written

**Check 1:** Log file
```bash
tail -20 logs/backfill_daily.log
```
**Check 2:** Time zone — cron UTC 08:00 = Taiwan 16:00. Adjust if machine is in a different timezone.

**Check 3:** Python path
```bash
# Verify Python version in cron environment
0 8 * * 1-5  /Library/Frameworks/Python.framework/.../bin/python3 --version >> /tmp/cron_test.log 2>&1
```

### Scenario: backfill_daily_prices shows "No missing trading days"

This is correct — either today's data is already in the DB, or today is a non-trading day.

### Scenario: shadow shows BLOCKED_STALE_DATA

The DailyPrice data is more than 7 days old. Run backfill manually:
```bash
python3 scripts/backfill_daily_prices.py --execute
```

---

## 6. Alternative: GitHub Actions Option A (pending approval)

The workflow `.github/workflows/hybrid_forward_shadow.yml` is configured for Option A (artifact cache). To enable automated GH Actions execution:

1. Run manual `workflow_dispatch` with `confirm_persistence=YES` (seeds cache)
2. Run a second manual dispatch (verifies cache restore)
3. Uncomment `schedule:` block in the workflow YAML

See `docs/hybrid_storage_deployment_readiness.md` for the full checklist.

---

## 7. Current Operational Status (2026-11-05)

| Check | Result |
|-------|--------|
| Crontab configured | ❌ Not yet |
| DailyPrice 2026-11-04 | ✅ Written (6,957 rows) |
| Shadow runner for 2026-11-04 | ✅ SUCCESS (21 decisions, RETROSPECTIVE_RECONSTRUCTION) |
| Stale data gap | ✅ 1 day (< 7-day tolerance) |
| PROSPECTIVE records | ⏳ Pending — start from 2026-11-05 after today's data is available |
