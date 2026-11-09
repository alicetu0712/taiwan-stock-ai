# Data Coverage Quality Gate — Session 48

**Date:** 2026-11-09  
**Session:** S48 — PART C (P2)  
**Verdict:** COVERAGE_PARTIAL — 9 complete, 9 benchmark-only, 2 missing

---

## DailyCoverageMatrix Summary (Oct 08 – Nov 09)

| Metric | Value |
|---|---|
| Total trading days analyzed | 20 |
| DATA_COMPLETE days | 9 |
| BENCHMARK_ONLY days (1 stock) | 9 |
| DATA_MISSING days (0 rows) | 2 |
| Root cause confirmed | 18 |
| Root cause partial | 2 |

---

## 15 Coverage Dimensions

Each record in the DailyCoverageMatrix captures 15 dimensions:

| Dim | Field | Description |
|---|---|---|
| 1 | `is_trading_day` | Calendar confirmation (all 20 = True) |
| 2 | `stock_count` | Distinct stocks in daily_prices |
| 3 | `has_data` | True if stock_count > 0 |
| 4 | `coverage_tier` | TIER_1_PROXY / TIER_655_FILL / TIER_6957_BACKFILL / TIER_ZERO_MISSING |
| 5 | `benchmark_present` | 0050 present (yes for all TIER_1+ dates) |
| 6 | `tsmc_present` | 2330 present (only on fill dates and backfill) |
| 7 | `fill_date_flag` | execution_date in forward_signals |
| 8 | `proxy_date_flag` | Only 0050 present |
| 9 | `pipeline_root_cause` | Root cause enum |
| 10 | `coverage_status` | DATA_COMPLETE / BENCHMARK_ONLY / DATA_MISSING |
| 11 | `source_type` | FILL_DATE_PIPELINE / MANUAL_BACKFILL / PROXY_ONLY / NONE |
| 12 | `pipeline_stage_reached` | Last pipeline stage executed |
| 13 | `recovery_feasibility` | BLOCKED / NOT_NEEDED |
| 14 | `affects_active_cluster` | Inside any cluster's 5D holding window |
| 15 | `root_cause_confidence` | ROOT_CAUSE_CONFIRMED / PARTIAL |

---

## Full Coverage Matrix

| Date | Stocks | TSMC | Fill | Root Cause | Coverage |
|---|---|---|---|---|---|
| 2026-10-08 | 1 | ✗ | ✗ | PIPELINE_SELECTIVE | BENCHMARK_ONLY |
| 2026-10-12 | 655 | ✓ | ✓ | NO_GAP | DATA_COMPLETE |
| 2026-10-13 | 656 | ✓ | ✓ | NO_GAP | DATA_COMPLETE |
| 2026-10-14 | 656 | ✓ | ✓ | NO_GAP | DATA_COMPLETE |
| 2026-10-15 | 1 | ✗ | ✗ | PIPELINE_SELECTIVE | BENCHMARK_ONLY |
| 2026-10-16 | 655 | ✓ | ✓ | NO_GAP | DATA_COMPLETE |
| 2026-10-19 | 1 | ✗ | ✗ | PIPELINE_SELECTIVE | BENCHMARK_ONLY |
| 2026-10-20 | 1 | ✗ | ✗ | PIPELINE_SELECTIVE | BENCHMARK_ONLY |
| 2026-10-21 | 655 | ✓ | ✓ | NO_GAP | DATA_COMPLETE |
| 2026-10-22 | 655 | ✓ | ✓ | NO_GAP | DATA_COMPLETE |
| 2026-10-27 | 1 | ✗ | ✗ | PIPELINE_SELECTIVE | BENCHMARK_ONLY |
| 2026-10-28 | 656 | ✓ | ✓ | NO_GAP | DATA_COMPLETE |
| 2026-10-29 | 1 | ✗ | ✗ | PIPELINE_SELECTIVE | BENCHMARK_ONLY |
| 2026-10-30 | 1 | ✗ | ✗ | SCHEDULER_NOT_TRIGGERED | BENCHMARK_ONLY |
| 2026-11-02 | 1 | ✗ | ✗ | SCHEDULER_NOT_TRIGGERED | BENCHMARK_ONLY |
| 2026-11-03 | 1 | ✗ | ✗ | SCHEDULER_NOT_TRIGGERED | BENCHMARK_ONLY |
| 2026-11-04 | 6957 | ✓ | ✗ | MANUAL_BACKFILL | DATA_COMPLETE |
| 2026-11-05 | 6589 | ✓ | ✗ | MANUAL_BACKFILL | DATA_COMPLETE |
| 2026-11-06 | 0 | ✗ | ✗ | QUALITY_GATE_FAIL | DATA_MISSING |
| 2026-11-09 | 0 | ✗ | ✗ | PROVIDER_NOT_READY | DATA_MISSING |

---

## Quality Gate: Row-Count Alone is Insufficient

A naive QG that checks only `COUNT(*) >= threshold` would:
- **Pass** Nov 04/05 (6957/6589 rows) but flag them as outliers
- **Pass** fill dates (655 rows) which is the reference
- **Fail** proxy dates (1 row) but miss the difference between PROXY_ONLY and legitimate data

The 15-dimension DailyCoverageMatrix adds nuance:
- **TSMC presence** distinguishes full-coverage dates from proxy-only dates
- **Source type** distinguishes fill-date pipeline from manual backfill
- **Root cause** enables targeted remediation rather than generic "rerun"

---

## Notes on TSMC as Benchmark Proxy

TSMC (2330) is used as a coverage proxy because:
1. It is in the v8.0 tracked universe
2. The pipeline fetches it on every full-coverage date
3. Its presence/absence is a reliable signal for full-universe coverage

0050 (ETF) is always fetched as a market status check, even on days with no full data pull.

---

## Affects Active Cluster Flag

Dates within any cluster's 5D holding window are flagged `affects_active_cluster=True`. Missing data on these dates directly impacts the ability to compute 5D returns:

| Active Window Date | Stock Count | Affects |
|---|---|---|
| Oct 15/19/20 (Oct 13 window) | 1 | Oct 13 cluster exit |
| Oct 15/19/20 (Oct 14 window) | 1 | Oct 14 cluster exit |
| Oct 19/20/27 (Oct 16 window) | 1 | Oct 16 cluster exit |
| Oct 27/29/30 (Oct 21 window) | 1 | Oct 21 cluster exit |
| Oct 27/29/30/Nov02 (Oct 22 window) | 1 | Oct 22 cluster exit |
| Oct 29/30/Nov02/03 (Oct 28 window) | 1 | Oct 28 cluster exit |
