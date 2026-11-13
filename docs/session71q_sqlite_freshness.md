# Session 71Q — SQLite & Post-write Freshness

**Session**: 71Q  
**Verdict**: `SQLITE_UNCHANGED_QG_RETRY_IN_PROGRESS`  
**Updated**: 2026-11-13 16:35 CST

---

## SQLite State at 16:35 CST (Post Retry 1)

| Metric | Value | Change from Baseline |
|---|---|---|
| `daily_prices` row count | **534,770** | UNCHANGED (QG failed — no writes) |
| `daily_prices` MAX(date) | **2026-11-05** | UNCHANGED |

**Consistent with QG failure**: All backfill dates failed QG-1 (api_date mismatch), so no rows were written. The row count unchanged proves guard did not accidentally bypass QG to write bad data.

---

## SQLite Baseline (Verified at 01:43 CST)

| Metric | Value | Source |
|---|---|---|
| DB Path | `data/platform.db` | verified |
| `daily_prices` row count | **534,770** | read-only query |
| `daily_prices` MAX(date) | **2026-11-05** | read-only query |
| `daily_reports` row count | 518 | read-only query |
| `daily_reports` MAX(date) | 2026-10-28 | read-only query |

---

## Post-write Expected State (if cron runs today)

| Metric | Expected After Success | Expected After QG Fail |
|---|---|---|
| Row count | > 534,770 (new rows added) | 534,770 (unchanged) |
| MAX(date) | 2026-11-13 | 2026-11-05 |
| State status | SUCCESS or BLOCKED_STALE_DATA | BLOCKED_STALE_DATA |

Note: QG failure (`quality gate FAILED — not writing to DB`) preserves baseline row count. Row count not changing does NOT imply RC-2 failure.

---

## Post-write Freshness Gate

The wrapper calls `check_market_freshness()` AFTER the backfill writes. It checks whether 0050 (the benchmark stock) has data for today. If TWSE published data after 15:30 CST, freshness should PASS.

Historical result on 2026-11-10: `PROVIDER_NOT_READY` (data not ready by ~16:00 CST even after 3 retries). The same failure could repeat on Nov 13.

---

## SQLite Verification Queries (Post-16:00)

All read-only:

```sql
-- Row count before vs after
SELECT COUNT(*) FROM daily_prices;

-- MAX date advance
SELECT MAX(date) FROM daily_prices;

-- Nov 13 specific rows
SELECT COUNT(*) FROM daily_prices WHERE date = '2026-11-13';

-- RC-2 enforcement check (should be 0 if filter worked)
SELECT COUNT(*) FROM daily_prices WHERE date = '2026-11-13' AND length(sid) > 4;

-- Sample of new rows
SELECT sid, name, date, close FROM daily_prices WHERE date = '2026-11-13' LIMIT 5;
```

---

## Notes on BASELINE_UNAVAILABLE

Since Deploy A was deployed at 01:35 CST and no cron has run since, the baseline (534,770 / 2026-11-05) is the same as the S71P pre-deployment baseline. This is a clean before-snapshot with zero ambiguity.
