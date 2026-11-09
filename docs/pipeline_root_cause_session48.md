# Pipeline Reliability Root Cause — Session 48

**Date:** 2026-11-09  
**Session:** S48 — PART B (P1)  
**Verdict:** ROOT_CAUSE_CONFIRMED (18/20 dates), ROOT_CAUSE_PARTIAL (2/20 dates)

---

## Three-Tier Stock Count Pattern

The research SQLite DB shows three distinct stock-count tiers for trading days after Oct 08:

| Tier | Stock Count | Dates | Root Cause |
|---|---|---|---|
| TIER_1_PROXY | 1 (0050 only) | Oct 08/15/19/20/27/29/30, Nov 02/03 (9 dates) | PIPELINE_SELECTIVE or SCHEDULER_NOT_TRIGGERED |
| TIER_655_FILL | ~655–656 stocks | Oct 12/13/14/16/21/22/28 (7 dates) | NO_GAP (fill dates) |
| TIER_6957_BACKFILL | ~6957 stocks | Nov 04/05 (2 dates) | MANUAL_BACKFILL |
| TIER_ZERO_MISSING | 0 rows | Nov 06/09 (2 dates) | QUALITY_GATE_FAIL / PROVIDER_NOT_READY |

---

## 10-Stage Pipeline Analysis

### Stage Flow

| Stage | Description |
|---|---|
| S01_CALENDAR_CHECK | TradingCalendarService: is today a trading day? |
| S02_SCHEDULER_VERIFY | Cron / scheduler active? |
| S03_DATA_PROVIDER_FETCH | TWSE / TPEx API call |
| S04_QUALITY_GATE | QG-1..QG-7 validation |
| S05_TRANSFORM | Convert raw → internal format |
| S06_DEDUP_CHECK | Check for existing rows |
| S07_SQLITE_WRITE | INSERT to daily_prices |
| S08_SIGNAL_TRIGGER | Does today have forward signals? |
| S09_SIGNAL_EXECUTION | Record execution_date / execution_price |
| S10_RESEARCH_CACHE | Update research cache |

### Stage Reached by Root Cause

| Root Cause | Last Stage | Explanation |
|---|---|---|
| NO_GAP (fill date) | S10_RESEARCH_CACHE | Full pipeline ran; signal execution |
| MANUAL_BACKFILL | S07_SQLITE_WRITE | Backfill script: S06+S07 only |
| PIPELINE_SELECTIVE | S07_SQLITE_WRITE | Reached S07 but only wrote 0050 proxy |
| SCHEDULER_NOT_TRIGGERED | S01_CALENDAR_CHECK | Scheduler never ran |
| QUALITY_GATE_FAIL | S04_QUALITY_GATE | QG rejected batch; nothing written |
| PROVIDER_NOT_READY | S03_DATA_PROVIDER_FETCH | TWSE api_date stale; fetch returned empty |

---

## Root Cause Details Per Date

### PIPELINE_SELECTIVE (Oct 08/15/19/20/27/29)

The pipeline ran on these dates (cron was active from at least Oct 08). However, the pipeline only wrote the benchmark stock (0050) to `daily_prices` on days when no forward signals were executing.

**Evidence**: `pipeline_funnels` table shows Oct 08 had 7723 stocks in universe and 2 recommended. Despite a full signal evaluation run, `daily_prices` only received 0050. This indicates the full price write was conditional on signal execution.

**Design principle**: ForwardSignalService needed price data to compute `execution_price`; on non-fill days, full price data was not stored because there were no signals to execute.

### SCHEDULER_NOT_TRIGGERED (Oct 30, Nov 02/03)

The cron job had not been activated. First log entry in `hybrid_forward_run_log`: `2026-11-05T04:42:02Z` (run on Nov 04 data). The cron likely started around Nov 09T08:00:17Z (first independent cron execution).

**Evidence**: Oct 30 and Nov 02/03 each have 1 row (0050 only) — but unlike the PIPELINE_SELECTIVE dates where the pipeline actively ran, these dates may reflect a residual 0050 write from an earlier session that pre-populated these dates.

### QUALITY_GATE_FAIL (Nov 06)

The cron ran on Nov 06 (Saturday or following the first cron activation) but the daily QG (QG-1..QG-7) rejected the data batch. No rows were written to `daily_prices`.

**Confidence**: ROOT_CAUSE_PARTIAL — QG rejection confirmed by 0 rows in `daily_prices`, but the specific QG check that failed is not logged in the available tables.

### PROVIDER_NOT_READY (Nov 09)

The cron ran on Nov 09 but the TWSE `api_date` field was stale (not matching Nov 09). The data provider fetch (S03) returned no fresh data.

**Confidence**: ROOT_CAUSE_PARTIAL — 0 rows in `daily_prices`, first cron log at `2026-11-09T08:00:17Z` confirms scheduler was running.

---

## Why Oct 1–7 Has ~499 Stocks (Legacy Tier)

Before Oct 08, `daily_prices` has ~499 stocks per day. This is the pre-v8.0 era:
- Pipeline used an earlier universe filter (not v8.0's 655-stock filtered universe)
- The ~499 figure represents a subset of the TWSE universe under a prior version

After Oct 12 (when v8.0 fill dates begin), the pipeline switched to writing only the v8.0-filtered universe (~655 stocks) on fill dates, plus 0050 as a proxy on non-fill dates.

---

## Impact on Research

| Dimension | Impact |
|---|---|
| Strict clusters (Oct 13/14/16) | NOT AFFECTED — full data on these fill dates |
| Incomplete clusters (Oct 21/22/28) | AFFECTED — exit prices missing for window days |
| 20D outcomes | BLOCKED — Nov 06-25 have no data (future trading days) |
| Statistical guardrails | UNCHANGED — G03/G04 FAIL unchanged |
