# Session 53: Coverage Quality Gate Forensics

**Audit Date**: 2026-11-10  
**Classification**: QG_ROOT_CAUSE_PARTIAL  
**Safety**: Read-only. No production writes.

## Summary

Nov 06 coverage data was never collected due to two independent failures:

1. **Primary (Nov 06 on Nov 06)**: `CRON_NO_TRIGGER` — DIRECTLY_CONFIRMED (log absent at 23:03 Taiwan)
2. **Secondary (Nov 06 on Nov 09+)**: `TPEx_QG5_FAIL` — STRONGLY_SUPPORTED (TPEx bulk always returns current-date data)

## QG Sub-condition Breakdown

| Check | TWSE | TPEx | Confidence | Blocking |
|-------|------|------|-----------|---------|
| QG-5 (date) | PASS (Nov06→Nov06 on Nov09) | FAIL (Nov09→Nov06 target) | STRONGLY_SUPPORTED | Yes |
| QG-6 (coverage) | PASS | N/A | STRONGLY_SUPPORTED | No |
| QG-7 (benchmark) | PASS | N/A | STRONGLY_SUPPORTED | No |

## Five-matrix Root Cause Table

| Target | Attempt | TWSE api_date | TWSE QG-5 | TPEx QG-5 | Confidence |
|--------|---------|--------------|-----------|-----------|------------|
| Nov06 | Nov09 | Nov06 (matches) | PASS | FAIL | STRONGLY_SUPPORTED |
| Nov09 | Nov09 | Nov06 (wrong) | FAIL | FAIL | DIRECTLY_CONFIRMED |
| Nov09 | Nov10 | Nov09 (matches) | PASS | FAIL | STRONGLY_SUPPORTED |
| Nov10 | Nov10 | Nov09 (wrong) | FAIL | — | DIRECTLY_CONFIRMED |
| Nov06 | Nov10 | Nov09 (wrong) | FAIL | — | DIRECTLY_CONFIRMED |

## Root Cause: TWSE

`TWSE_HIST_URL` (`www.twse.com.tw/exchangeReport/STOCK_DAY_ALL?date=YYYYMMDD`) returns a CSV response for historical dates. `resp.json()` raises `JSONDecodeError` → code falls back to `TWSE_LATEST_URL` (`openapi.twse.com.tw`), which always returns the most recently published day — a **systematic 1-trading-day lag**.

Evidence: cron log shows `"TWSE api_date=2026-11-06 != target"` for Nov 09 target on Nov 09 cron. DIRECTLY_CONFIRMED.

## Root Cause: TPEx

`TPEX_HIST_URL` (`?d=RRRMMDD`) ignores the date parameter and returns current-date data regardless. Every row's `Date` field equals the cron execution date, not the requested target → QG-5 fires per row.

**Critical asymmetry**: TPEx api_date mismatch uses only `print()` to stdout, NOT `summary["errors"].append()`. This means TPEx QG-5 failures **do not appear in the cron log**. This is why Nov06/Nov09 attempt shows only `"quality gate FAILED"` without an explicit TPEx error.

Evidence: `scripts/backfill_daily_prices.py` code path confirmed. STRONGLY_SUPPORTED.

## Pipeline Trace: Nov 06

| Stage | Expected | Observed | Evidence |
|-------|----------|----------|---------|
| SCHEDULER_TRIGGER | Cron fires 08:00 UTC | **NO TRIGGER** | Log absent at 23:03 Taiwan |
| PROCESS_START | Pipeline starts | NOT STARTED | .cron_state.json frozen |
| PROVIDER_* | All stages | NOT EXECUTED | — |
| COMPLETION_MARKER | SUCCESS | NOT CREATED | — |

**Primary failure**: `CRON_NO_TRIGGER` DIRECTLY_CONFIRMED.

## Pipeline Trace: Nov 09

| Stage | Expected | Observed | Evidence |
|-------|----------|----------|---------|
| SCHEDULER_TRIGGER | Cron fires 08:00:17Z | TRIGGERED | Log first line |
| PROVIDER_TWSE_RESPONSE | api_date=Nov09 | api_date=Nov06 | Log: explicit TWSE api_date error |
| QUALITY_GATE | PASS | QG-5 FAIL | Log: "quality gate FAILED" |
| COMPLETION_MARKER | SUCCESS | BLOCKED_STALE_DATA | Log: 09:35:14Z after 3 retries |

## Overall Verdict: QG_ROOT_CAUSE_PARTIAL

- TWSE failure: DIRECTLY_CONFIRMED (cron log)
- TPEx failure: STRONGLY_SUPPORTED (code analysis + S50 SOURCE_UNAVAILABLE)
- Per-row sub-check detail (QG-1/2/3): INSUFFICIENT_EVIDENCE (not in cron log output)
