# Data Freshness Root Cause Audit — Session 46

**Date:** 2026-11-09  
**Session:** S46 — PART B  
**Verdict:** ROOT_CAUSE_CONFIRMED

---

## Pipeline Architecture

| Component | Value |
|---|---|
| Scheduler | `scripts/hybrid_shadow_cron.py` |
| Data Script | `scripts/backfill_daily_prices.py` |
| Schedule | `0 16 * * 1-5` (Taiwan 16:00 / UTC 08:00) |
| Cron Hash | `3acaf480cb5dcdd44f40dd9d464955a1` (unchanged) |
| Cron Log | `logs/hybrid_cron.log` |
| First Confirmed Run | `2026-11-09T08:00:17Z` (first line in hybrid_cron.log) |

The daily price collection is handled by `hybrid_shadow_cron.py` which runs `backfill_daily_prices.py` as a subprocess — **not** `run_daily.py` or `main.py`. The 0-byte `run_*.log` files for Nov 02–09 were created by other process activity (manual `main.py` imports) and are not diagnostic of the data pipeline.

---

## Root Cause Chain

| Priority | Cause | Dates Affected |
|---|---|---|
| PRIMARY | `SCHEDULER_NOT_TRIGGERED` | Nov 02–08 (cron not running) |
| SECONDARY | `QUALITY_GATE_FAIL` | Nov 06 (quality gate rejected backfill data) |
| TERTIARY | `PROVIDER_NOT_READY` | Nov 09 (TWSE API returning stale date) |

---

## Per-Date Diagnosis

| Date | Is Trading Day | Root Cause | DB Stocks | Has Full Data |
|---|---|---|---|---|
| 2026-11-02 | Yes | SCHEDULER_NOT_TRIGGERED | 0 | No |
| 2026-11-03 | Yes | SCHEDULER_NOT_TRIGGERED | 0 | No |
| 2026-11-04 | Yes | PARTIAL_MANUAL_RECOVERY | 6,957 | Yes |
| 2026-11-05 | Yes | PARTIAL_MANUAL_RECOVERY | 6,589 | Yes |
| 2026-11-06 | Yes | QUALITY_GATE_FAIL | 0 | No |
| 2026-11-07 | No | MARKET_CLOSED | 0 | No |
| 2026-11-08 | No | MARKET_CLOSED | 0 | No |
| 2026-11-09 | Yes | PROVIDER_NOT_READY | 0 | No |

**Nov 04/05 note:** Data is present via manual `backfill_daily_prices.py` run documented in the DailyPrice Pipeline project (6,957 rows inserted). The cron was not running on these dates.

**Nov 06 note:** The first cron run (Nov 09 08:00 UTC) attempted to backfill Nov 06. The error log shows `quality gate FAILED — not writing to DB`. The specific QG check that failed (QG-5 date consistency or QG-6 coverage) is not definitively identified from the log.

**Nov 09 note:** Cron ran 4 attempts (08:00 + 3 retries at 30-min intervals). TWSE API returned `api_date=2026-11-06` for the Nov 09 request at every attempt. After retry 3 at 09:35 UTC, status = `BLOCKED_STALE_DATA`.

---

## Evidence Sources

1. `logs/hybrid_cron.log` — first entry at `2026-11-09T08:00:17Z` (no prior entries)
2. `crontab -l` — single entry: `hybrid_shadow_cron.py` at 16:00 Taiwan
3. `logs/run_*.log` — all 0 bytes for Nov 02–09 (created by main.py FileHandler, not diagnostic)
4. Direct DB query — `MAX(date) = 2026-11-05` in local SQLite

---

## Neon vs SQLite Divergence

| DB | Max Date | Source |
|---|---|---|
| Local SQLite (`data/platform.db`) | 2026-11-05 | Research canonical DB |
| Neon (PostgreSQL production) | 2026-11-06 | Independent pipeline |

Neon has fuller data (638 stocks for Oct 29/30/Nov 02/03/06) while local SQLite has thin data (1 stock = 0050 only) for those dates. Neon represents a separate production pipeline state. All research baselines (S44/S45/S46) use local SQLite as the authoritative source.

---

## Recovery Path

1. **Nov 06**: Investigate quality gate failure. If QG-5 (date mismatch), retry on next cron run. If QG-6 (coverage), may require manual investigation.
2. **Nov 09**: PROVIDER_NOT_READY is temporal — TWSE typically publishes by 16:30–17:00 Taiwan. Next cron run at 16:00 Nov 10 should succeed.
3. **Nov 02–03**: Not in cron backfill window (cron only looks back limited days). Requires manual `--start 2026-11-02 --end 2026-11-03 --execute`.
