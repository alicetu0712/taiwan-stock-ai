# TWSE Source Contract Matrix — Session 57

**Session ID**: S57  
**Date**: 2026-11-10  
**Status**: TWSE_SOURCE_PARTIAL

---

## Summary

Three distinct TWSE endpoints exist. Only one (TWSE_SINGLE_STOCK) can provide
historical OHLCV. The bulk historical endpoint is broken; the bulk latest endpoint
returns the correct format but always returns today's data.

---

## Source Contract Matrix

| Source | URL Pattern | Date Semantics | OHLCV | Stocks | Historical | Feasibility |
|--------|-------------|----------------|-------|--------|------------|-------------|
| TWSE_BULK_HIST | STOCK_DAY_ALL?date=YYYYMMDD | PARTIAL_HISTORICAL | FULL (if responds) | ~1200 | NOT_AVAILABLE | NOT_FEASIBLE |
| TWSE_BULK_LATEST | openapi.twse.com.tw/v1/STOCK_DAY_ALL | ALWAYS_LATEST | FULL OHLCV+V | 1241 | LATEST_ONLY | FOR_DAILY_CRON |
| TWSE_SINGLE_STOCK | STOCK_DAY?date=YYYYMMDD&stockNo=ID | REQUESTED_DATE_HONORED | FULL OHLCV+V | 1 per call | AVAILABLE | FEASIBLE_WITH_CAUTION |

---

## TWSE_BULK_HIST

**URL**: `https://www.twse.com.tw/exchangeReport/STOCK_DAY_ALL?response=json&date={YYYYMMDD}`

**S57 Probe Result**:
- Requested: Oct29, Nov04 (3 retries each)
- Response: Empty body, `JSONDecodeError: Expecting value: line 1 column 1 (char 0)`
- Verdict: **NOT_AVAILABLE**

**Implication**: This endpoint is completely broken for recent dates. The script currently
tries this URL first and falls back to TWSE_LATEST_URL. The fallback returns WRONG DATE data.

**Remediation**: Remove from active pipeline path. Mark as DEAD.

---

## TWSE_BULK_LATEST

**URL**: `https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL`

**S57 Probe Result**:
- Rows: 1241 stocks
- OHLCV: Full (open/high/low/close/volume all non-null)
- api_date: `2026-11-09` (yesterday, regardless of when queried)
- Date semantics: **ALWAYS_LATEST** — returns latest trading day, no date input

**Root Cause RC-02**: Cron runs next morning → api_date=T-1 → date validation can fail.
Nov06/09 DATE_MISSING may stem from date guard rejecting this off-by-one.

**Use Case**: Valid for daily pipeline if run on target trading day.
Add explicit api_date vs target_date tolerance (+1 trading day acceptable).

---

## TWSE_SINGLE_STOCK

**URL**: `https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date={YYYYMMDD}&stockNo={ID}`

**S50 Verification**:
- Oct29: 2330 (FULL OHLCV V=18403916), 2454 (FULL OHLCV V=6867223), 2317 (FULL OHLCV V=21358260)
- Oct29: 2891/6505/3008 (OHLCV, volume=None)
- Oct30: 2330/2454 FULL OHLCV+V
- Nov02: 2330 FULL OHLCV+V
- Nov03: 2317 FULL OHLCV+V (close=245.5 — corrected from S55/S56 which had 245.0)

**Rate Limit**: HTTP_PAUSE=2.0s per request; TWSE terms NOT VERIFIED.

**Coverage Estimate for Full Recovery**:
- Stocks per date: ~1969 ordinary
- Time per date: 1969 × 2s = ~65 min
- 6 gap dates: ~6.6 hours
- 8 gap dates (incl. Nov06/09): ~8.7 hours

**Verdict**: FEASIBLE_WITH_CAUTION — works for recent historical dates; rate limit and terms unverified.

---

## Nov04/05 Composition Analysis

Nov04 has 6957 rows:
- TWSE_BULK_LATEST returns 1241 stocks
- TPEx_BULK returns 5737 stocks
- Total ~6978, with ~21 de-duplication or exclusion
- 4829 warrant rows (should be excluded from coverage calculation)
- Correct research denominator: **1969** (ordinary 4-digit stocks)

---

## Verdict

| Component | Status |
|-----------|--------|
| TWSE_BULK_HIST | DEAD — returns non-JSON |
| TWSE_BULK_LATEST | ALIVE — daily use only (api_date=T-1 acceptable for T+1 cron) |
| TWSE_SINGLE_STOCK | VERIFIED_PARTIAL — historical works, rate limit unknown |
| **Overall TWSE** | **TWSE_SOURCE_PARTIAL** |
