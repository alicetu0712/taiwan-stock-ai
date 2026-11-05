# DailyPrice Recovery Plan

**Date:** 2026-11-05  
**Status:** PARTIAL RECOVERY COMPLETE  
**Root cause:** See `docs/dailyprice_pipeline_root_cause.md`

---

## 1. Recovery Summary

| Step | Action | Result |
|------|--------|--------|
| Identify gap | `SELECT MAX(date) FROM daily_prices WHERE stock_id='0050'` | 2026-10-28 |
| Identify missing days | `backfill_daily_prices.py` dry-run | 6 trading days missing |
| Recover 2026-11-04 | `backfill_daily_prices.py --start 2026-11-04 --end 2026-11-04 --execute` | 6,957 rows inserted (1,242 TWSE + 5,715 TPEx) |
| Shadow runner test | `run_hybrid_forward_shadow.py --date 2026-11-04` | SUCCESS, 21 decisions |
| Stale data check | gap = 1 day < 7-day tolerance | Unblocked ✓ |

**Unrecoverable (public API limitation):**
- 2026-10-29, 10-30, 11-02, 11-03: No historical all-stocks API available
- These days would need FinMind (paid) or TEJ data

---

## 2. Recovery Script Usage

### Standard usage (dry-run first)

```bash
# 1. See what dates are missing (dry-run, no DB changes)
python3 scripts/backfill_daily_prices.py

# 2. Target a specific date range (dry-run)
python3 scripts/backfill_daily_prices.py --start 2026-11-04 --end 2026-11-05

# 3. Execute after reviewing dry-run output
python3 scripts/backfill_daily_prices.py --start 2026-11-04 --end 2026-11-04 --execute
```

### Daily operation (run after market close ~15:30 Taiwan)

```bash
# Backfill any missing date(s) since last run
python3 scripts/backfill_daily_prices.py --execute
```

The script automatically detects the last stored date and uses it as the start date. It is **idempotent** — running it twice for the same date inserts 0 rows on the second run.

### Cron setup (Option D — local cron)

```cron
# Taiwan 16:00 = UTC 08:00; run after TWSE closes and data is published
0 8 * * 1-5  cd /path/to/stock_platform && python3 scripts/backfill_daily_prices.py --execute >> logs/backfill_daily.log 2>&1
```

---

## 3. Data Quality Gate Results (2026-11-04)

| Market | Rows | QG result | Notes |
|--------|------|-----------|-------|
| TWSE | 1,242 | PASS | All QG-1 through QG-7 passed |
| TPEx | 5,715 | PASS | Used TPEX_PRICE_MIN=0.01 (penny stocks) |
| Total | 6,957 | PASS | Committed to `daily_prices` |

**QG-7 benchmark (0050):** Present in TWSE batch ✓  
**QG-5 date consistency:** api_date=2026-11-04 == target ✓  
**QG-6 coverage:** TWSE 1,242 ≥ 300; TPEx 5,715 ≥ 50 ✓

---

## 4. Limitations

| Limitation | Impact | Workaround |
|------------|--------|------------|
| No TWSE historical API for past dates | Cannot backfill 10-29 to 11-03 | Paid data source (FinMind) |
| TPEx date param ignored (returns latest) | Cannot target specific historical dates | Same |
| TWSE old URL returns HTML not JSON | Same | Same |
| Local SQLite was always sparse | Pre-existing gap in Oct 2026 | Not a blocker for shadow runner |

---

## 5. If 11-04 Data Becomes Stale Again

If more than 7 calendar days pass without an update:

```bash
# Check current status
python3 -c "
import sqlite3; c=sqlite3.connect('data/platform.db')
print(c.execute(\"SELECT MAX(date) FROM daily_prices WHERE stock_id='0050'\").fetchone())
"

# Backfill
python3 scripts/backfill_daily_prices.py --execute
```

If the TWSE OpenAPI returns a date different from the target (data not yet published), the script will report "both TWSE and TPEx returned wrong-date data" and not write. Try again after 15:30 Taiwan time.

---

## 6. What Requires Human Action

| Action | Why human | Done? |
|--------|-----------|-------|
| Configure crontab for daily backfill | Machine-specific path | ⏳ Pending |
| Decide on paid data source for gap days | Cost decision | ⏳ Pending |
| When today's (11-05) data is available, run shadow | Manual trigger until cron is set | ⏳ Pending |
