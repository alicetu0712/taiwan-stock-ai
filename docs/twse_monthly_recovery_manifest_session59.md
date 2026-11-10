# TWSE Monthly Recovery Manifest — Session 59

**Date**: 2026-11-10  
**Verdict**: MANIFEST_BUILT_PENDING_AUTHORIZATION  
**Auth Required**: AUTH01 (compliance prerequisite unmet)

---

## S58 vs S59 Corrections

| Item | S58 Estimate | S59 Calculation | Source |
|------|-------------|-----------------|--------|
| Eligible stocks | 599 | **712** | Live DB query: active 4-digit non-ETF TWSE in 2026 |
| Total requests | 1,198 | **1,424** | 712 × 2 months |
| Runtime estimate | ~40 min | **~47 min** | 1,424 × 2s / 60 |
| Coverage denominator | 599 | **712** | Same correction |

**Root cause of S58 estimate**: S58 used 599 from S50's heuristic count of 4-digit numeric stocks in the v8.0 research universe. S59 queried `daily_prices` directly for stocks active in 2026 (Aug–Nov), yielding a more accurate 712.

**Full TWSE stocks table**: 826 entries. 712 reflects the active-in-2026 subset.

---

## PIT Universe Definition

| Property | Value |
|----------|-------|
| Stocks in `stocks` table (market=TWSE) | 826 |
| Active 4-digit non-ETF TWSE stocks (2026) | 712 |
| ETF stocks (excluded from recovery) | ~114 |
| TPEx ordinary stocks | Not in `stocks` table (market=None) |
| Recovery months | October 2026 + November 2026 |

---

## Request Budget

| Parameter | Value |
|-----------|-------|
| Eligible stocks | 712 |
| Months | 2 (Oct 2026, Nov 2026) |
| Total stock-month requests | 1,424 |
| Delay per request | 2 seconds |
| Concurrency | 1 (sequential) |
| Estimated runtime | ~47 minutes |
| Retry budget | 3 retries per failure |
| Stop condition | HTTP 429 or 5+ consecutive failures |
| Existing cached responses | 0 (no full month caches exist) |

---

## 5 Pilot-Verified Stock-Month Entries

From S58 pilot (5/5 PASS). All are INSERT_CANDIDATE, AUTH01_PENDING.

| Stock | Month | OHLCV Status | Key Data Points |
|-------|-------|-------------|-----------------|
| 2330 (TSMC) | Oct 2026 | FULL_OHLCV | Oct29: O=2420/C=2415/V=18.4M; Oct30: O=2380/C=2370/V=36.6M |
| 2454 (MediaTek) | Oct 2026 | FULL_OHLCV | Oct29: O=4205/C=4045/V=6.9M; Oct30: O=3820/C=3915/V=13M |
| 1301 (Formosa) | Oct 2026 | FULL_OHLCV | Oct29: O=75.3/C=73.9/V=19.1M; Oct30: O=72.2/C=72.5/V=25.2M |
| 2317 (Hon Hai) | Nov 2026 | FULL_OHLCV | Nov03: close=**245.5** CONFIRMED; Nov06/09: full OHLCV |
| 2882 (Cathay FHC) | Nov 2026 | FULL_OHLCV | Nov02: O=117/C=116; Nov03: C=113; Nov06/09: full OHLCV |

**Note**: Nov03 2317 close = 245.5 was CONFIRMED by S58 P02 direct probe, resolving the S55/S56 controversy (245.0 vs 245.5). The correct value is **245.5**.

---

## Coverage Estimates for 6 Gap Dates

| Gap Date | Existing Rows | QG Before Recovery | Full T2 After Recovery |
|----------|--------------|-------------------|----------------------|
| 2026-10-29 | ~7 | FAIL | PASS_LIKELY |
| 2026-10-30 | ~3 | FAIL | PASS_LIKELY |
| 2026-11-02 | ~3 | FAIL | PASS_LIKELY |
| 2026-11-03 | ~2 | FAIL | PASS_LIKELY |
| 2026-11-06 | ~4 | FAIL | PASS_LIKELY |
| 2026-11-09 | ~4 | FAIL | PASS_LIKELY |

Coverage denominator: 712 active TWSE stocks.  
QG threshold: 95%.  
Current coverage for all gap dates: < 2% → all FAIL.  
Full T2 recovery (1,424 calls): all gap dates would reach ~100% → PASS_LIKELY.

---

## Authorization Status

| Authorization | Status | Prerequisite |
|---------------|--------|--------------|
| AUTH01 (full T2 recovery) | NOT_AUTHORIZED | TWSE compliance confirmation |
| AUTH01 (pilot 23 records only) | NOT_AUTHORIZED | Explicit user authorization |
| TWSE compliance confirmation | NOT_STARTED | Contact TWSE market data team |

The 23-record manifest (5 pilot stocks × 6 gap dates) represents a small but verified subset. Even if authorized, 23 records would bring max coverage to 1.2% (Oct29) — far below the 95% QG threshold.

Full T2 recovery (1,424 calls) is required to pass the coverage quality gate. It remains blocked pending compliance confirmation.
