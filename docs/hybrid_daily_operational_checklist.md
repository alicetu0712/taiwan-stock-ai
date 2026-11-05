# Hybrid Forward Shadow — Daily Operational Checklist

**Operating mode:** Local SQLite (Option D) — manual or cron  
**Research only** — no production writes, no Neon access

---

## A. Pre-flight (run any time)

```bash
# 1. Check DailyPrice freshness + last run state
python3 scripts/hybrid_shadow_cron.py --status
```

Look for:
- `last_data_date` ≤ 1 day old → OK
- `last_data_date` 2–7 days old → warning, backfill needed
- `last_data_date` > 7 days old → `BLOCKED_STALE_DATA` on next shadow run

```bash
# 2. Check decision summary
python3 -c "
import sqlite3, json
conn = sqlite3.connect('data/platform.db')
from src.research.hybrid_forward_db import get_operational_summary
print(json.dumps(get_operational_summary(conn), indent=2, default=str))
conn.close()
"
```

---

## B. Daily Operations (after 15:30 Taiwan time, Mon–Fri)

### Option B1: Automated (cron configured)

Nothing to do — cron handles backfill + backup + shadow at 16:00 Taiwan.

Verify after ~16:05:
```bash
python3 scripts/hybrid_shadow_cron.py --status
# Expected: status=SUCCESS, last_data_date=today
```

### Option B2: Manual (cron not yet configured)

```bash
# Step 1: Backfill any missing DailyPrice data
python3 scripts/backfill_daily_prices.py --execute

# Step 2: Run hybrid forward shadow for today
python3 scripts/run_hybrid_forward_shadow.py

# Step 3: Create manual backup (optional but recommended)
python3 -c "
import sys; sys.path.insert(0,'.')
from scripts.hybrid_shadow_cron import create_backup
from datetime import date
result = create_backup('data/platform.db', date.today())
print('Backup:', result)
"
```

---

## C. Verify Today's Run

```bash
python3 -c "
import sqlite3
from datetime import date
conn = sqlite3.connect('data/platform.db')
today = str(date.today())

# Today's decisions
n = conn.execute(
    'SELECT COUNT(*) FROM hybrid_forward_decision WHERE trade_date=?', (today,)
).fetchone()[0]

# Classification breakdown
cls = conn.execute(
    'SELECT capture_classification, COUNT(*) FROM hybrid_forward_decision '
    'WHERE trade_date=? GROUP BY 1', (today,)
).fetchall()

# Last run log
log = conn.execute(
    'SELECT run_id, status, inserted_count, error_count FROM hybrid_forward_run_log '
    'ORDER BY started_at DESC LIMIT 1'
).fetchone()

print(f'Decisions for {today}: {n}')
print('Classifications:', dict(cls))
print('Last run:', log)
conn.close()
"
```

**Expected on a valid trading day (trade_date >= 2026-11-05):**
```
Decisions for 2026-11-05: N (N > 0 on active market day)
Classifications: {'PROSPECTIVE': N}
Last run: ('run_id', 'SUCCESS', N, 0)
```

**Expected on holiday / weekend:**
```
Last run: ('run_id', 'SKIPPED_NON_TRADING_DAY', 0, 0)
```

---

## D. Weekly Maintenance (every Monday)

```bash
# 1. Check backup inventory
python3 scripts/hybrid_shadow_cron.py --status

# 2. Verify DailyPrice coverage for the past week
python3 -c "
import sqlite3
from datetime import date, timedelta
conn = sqlite3.connect('data/platform.db')
today = date.today()
for i in range(7, 0, -1):
    d = today - timedelta(days=i)
    n = conn.execute(
        'SELECT COUNT(DISTINCT stock_id) FROM daily_prices WHERE date=?', (str(d),)
    ).fetchone()[0]
    print(f'{d}: {n} stocks')
conn.close()
"

# 3. Check PROSPECTIVE accumulation
python3 -c "
import sqlite3
conn = sqlite3.connect('data/platform.db')
rows = conn.execute(
    'SELECT trade_date, capture_classification, COUNT(*) '
    'FROM hybrid_forward_decision '
    'WHERE trade_date >= \"2026-11-05\" '
    'GROUP BY 1, 2 ORDER BY 1 DESC LIMIT 14'
).fetchall()
for r in rows:
    print(r)
conn.close()
"
```

---

## E. Incident Response

### BLOCKED_STALE_DATA

```bash
# Check how stale
python3 -c "
import sqlite3; from datetime import date
conn = sqlite3.connect('data/platform.db')
last = conn.execute('SELECT MAX(date) FROM daily_prices WHERE stock_id=\"0050\"').fetchone()[0]
print(f'last={last}, gap={(date.today() - date.fromisoformat(last)).days}d')
"

# Backfill
python3 scripts/backfill_daily_prices.py --execute
```

### QG-5 Failure (wrong-date data)

API returned data for a different date than requested (data not yet published):
```
[WARN] 2026-11-05: TWSE api_date=2026-11-04 != target — API returned wrong date
```
Solution: Wait until after 15:30 Taiwan time and retry.

### Decision Hash Conflict

```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('data/platform.db')
rows = conn.execute(
    'SELECT run_id, error_summary FROM hybrid_forward_run_log '
    'WHERE error_summary LIKE \"%conflict%\" ORDER BY started_at DESC LIMIT 5'
).fetchall()
for r in rows: print(r)
"
```

If you see conflicts: **do NOT delete and re-insert decisions**. Conflicts mean the same (stock, date, rule_version) produced different signals across runs — this indicates a non-determinism bug. File an issue.

### No PROSPECTIVE records after RULE_FREEZE_DATE

Verify:
1. `trade_date >= 2026-11-05` ← correct
2. `last_data_date` is fresh (≤ 1 trading day stale)
3. `HybridTradingCalendar.is_trading_day(today) = True` ← needs DailyPrice for today

```bash
python3 -c "
import sqlite3, sys; sys.path.insert(0,'.')
from src.research.hybrid_trading_calendar import TradingCalendar
from datetime import date
conn = sqlite3.connect('data/platform.db')
cal = TradingCalendar.from_db(conn)
today = date.today()
print(f'is_trading_day({today}):', cal.is_trading_day(today))
conn.close()
"
```

If `False`: DailyPrice for today not yet backfilled. Run backfill first.

---

## F. Safety Reminders

| ❌ Never | ✅ Always |
|----------|----------|
| Modify `RULE_FREEZE_DATE` or `MODEL_VERSION` | Dry-run before `--execute` |
| Delete or update `hybrid_forward_decision` rows | Use `--status` to diagnose |
| Write to Neon PostgreSQL from this script | Let QG-5 block wrong-date data |
| Run `--force-stale` to generate fake PROSPECTIVE records | Record 0 signals on bad data days |
| Install crontab without user approval | Confirm backfill QG PASS before shadow |

---

## G. Quick Reference

| Command | Purpose |
|---------|---------|
| `python3 scripts/hybrid_shadow_cron.py --status` | Last run summary + backups |
| `python3 scripts/backfill_daily_prices.py` | Dry-run: show missing dates |
| `python3 scripts/backfill_daily_prices.py --execute` | Write missing DailyPrice |
| `python3 scripts/run_hybrid_forward_shadow.py` | Generate today's decisions |
| `python3 scripts/hybrid_shadow_cron.py --execute` | Full pipeline (backfill + backup + shadow) |
| `python3 scripts/hybrid_shadow_cron.py` | Dry-run full pipeline |
| `crontab -l` | Show installed cron jobs |
