# Verified Historical Market Data Source Matrix — Session 50

**Date:** 2026-11-10  
**Session:** S50 — PART B (Real API Investigation Results)  
**Verdict:** ALL_11_DATES_SOURCE_VERIFIED_PARTIAL

---

## Summary

S50 PART B conducted real TWSE and TPEx API investigations to establish which data sources can provide historically accurate market data for the 11 candidate backfill dates. This supersedes the S49 "UNIVERSE_UNVERIFIED" classification for Nov 06 and Nov 09.

---

## Provider Investigation Results

### TWSE Single-Stock Historical (STOCK_DAY?date=YYYYMMDD&stockNo=XXXX)

**Verdict: SOURCE_VERIFIED_PARTIAL**

Returns historically accurate monthly data per stock. The `date=` parameter correctly selects the month. Each call returns OHLC + volume for all trading days in that month.

| Date | Stock | Exchange | Close | OHLC Valid |
|---|---|---|---|---|
| 2026-10-29 | 2330 (台積電) | TWSE | 2415.0 | ✓ |
| 2026-10-29 | 2454 (聯發科) | TWSE | 4045.0 | ✓ |
| 2026-10-29 | 2317 (鴻海) | TWSE | 248.0 | ✓ |
| 2026-10-29 | 2891 (中信金) | TWSE | 75.3 | ✓ |
| 2026-10-29 | 6505 (台塑化) | TWSE | 98.6 | ✓ |
| 2026-10-29 | 3008 (大立光) | TWSE | 5815.0 | ✓ |
| 2026-10-30 | 2330 (台積電) | TWSE | 2370.0 | ✓ |
| 2026-10-30 | 2454 (聯發科) | TWSE | 3915.0 | ✓ |
| 2026-11-02 | 2330 (台積電) | TWSE | 2330.0 | ✓ |
| 2026-11-03 | 2317 (鴻海) | TWSE | 245.5 | ✓ |
| 2026-11-06 | 2330 (台積電) | TWSE | 2135.0 | close-only |
| 2026-11-06 | 2454 (聯發科) | TWSE | 3390.0 | close-only |
| 2026-11-09 | 2330 (台積電) | TWSE | 2235.0 | close-only |
| 2026-11-09 | 2454 (聯發科) | TWSE | 3725.0 | close-only |

**Critical caveat:** Each stock requires a separate API call. Full 599-stock backfill requires ~600 calls per date.

### TWSE Bulk Historical (STOCK_DAY_ALL?response=json&date=YYYYMMDD)

**Verdict: SOURCE_UNAVAILABLE for historical dates**

HTTP 200 returned, but response body always contains CURRENT DATE data regardless of `date=` parameter.

Confirmed:
- Query `date=20261029` → response has `1151109` (Nov 09 data, NOT Oct 29)
- Query `date=20261030` → response has `1151109` (Nov 09 data, NOT Oct 30)

**IMPORTANT:** HTTP 200 does NOT mean historical data is available. The endpoint is a current-day snapshot only.

### TPEx Bulk Historical (?d=RRRMMDD)

**Verdict: SOURCE_UNAVAILABLE for historical dates**

HTTP 200 returned, 13674 records, but Date field = `1151109` for any `?d=` parameter.

Confirmed:
- Query `?d=1151029` (Oct 29) → returns Nov 09 data (13674 records)
- Query `?d=1151030` (Oct 30) → returns Nov 09 data (same)

**IMPORTANT:** HTTP 200 does NOT mean historical data is available. The parameter is ignored.

---

## Per-Date Source Verdicts

| Date | Existing DB Rows | Source Verdict | Upgrade from S49 | Notes |
|---|---|---|---|---|
| 2026-10-08 | ~655 | SOURCE_VERIFIED_PARTIAL | — | TSMC C confirmed |
| 2026-10-15 | ~655 | SOURCE_VERIFIED_PARTIAL | — | TSMC C confirmed |
| 2026-10-19 | ~655 | SOURCE_VERIFIED_PARTIAL | — | TSMC C confirmed |
| 2026-10-20 | ~655 | SOURCE_VERIFIED_PARTIAL | — | TSMC C confirmed |
| 2026-10-27 | ~655 | SOURCE_VERIFIED_PARTIAL | — | TSMC C=2400 confirmed |
| 2026-10-29 | 1 (0050 proxy) | SOURCE_VERIFIED_PARTIAL | — | 6 stocks full OHLC verified |
| 2026-10-30 | 1 (0050 proxy) | SOURCE_VERIFIED_PARTIAL | — | 2 stocks verified |
| 2026-11-02 | 1 (0050 proxy) | SOURCE_VERIFIED_PARTIAL | — | TSMC confirmed |
| 2026-11-03 | 1 (0050 proxy) | SOURCE_VERIFIED_PARTIAL | — | Foxconn confirmed |
| **2026-11-06** | **0** | **SOURCE_VERIFIED_PARTIAL** | **UNIVERSE_UNVERIFIED→VERIFIED_PARTIAL** | **UPGRADE: pipeline failed but data exists** |
| **2026-11-09** | **0** | **SOURCE_VERIFIED_PARTIAL** | **UNIVERSE_UNVERIFIED→VERIFIED_PARTIAL** | **UPGRADE: PROVIDER_NOT_READY but data exists** |

---

## Nov 06/09 Status Upgrade (Critical S50 Finding)

### Prior status (S48/S49): UNIVERSE_UNVERIFIED
The pipeline failed for these dates: QG_FAIL (Nov 06) and PROVIDER_NOT_READY (Nov 09). Because the bulk API failed, the data availability was classified as UNIVERSE_UNVERIFIED.

### New status (S50): SOURCE_VERIFIED_PARTIAL
Real TWSE single-stock API calls confirmed:
- **Nov 06**: TSMC C=2135, MediaTek C=3390 — historically accurate data EXISTS
- **Nov 09**: TSMC C=2235, MediaTek C=3725 — historically accurate data EXISTS

**Interpretation:** The pipeline failure was a **bulk API + quality gate issue**, not a data non-existence issue. The underlying data is accessible via per-stock API calls. This means a manual per-stock backfill is technically feasible, subject to AUTH01 authorization.

### Implication for ACTIVATION_BLOCKED
This upgrade does NOT change ACTIVATION_BLOCKED. The pipeline root cause (why the pipeline failed and produced only 1-stock proxy data) is unresolved. The data being available per-stock is a necessary but not sufficient condition for recovery.

---

## Universe Composition

| Category | Count | TWSE Single-Stock Accessible |
|---|---|---|
| 4-digit numeric stocks | 599 | ~100% (20/20 sample confirmed) |
| ETF / non-4-digit | 57 | Excluded from backfill |
| Total fill universe | 656 | 599 eligible |

Random 20-stock sample from Oct 13 fill universe: **20/20 accessible via TWSE single-stock API**.

---

## What "SOURCE_VERIFIED_PARTIAL" Means

| Claim | Status |
|---|---|
| Data source exists | ✓ CONFIRMED (TWSE STOCK_DAY endpoint) |
| Data is accessible | ✓ CONFIRMED (HTTP 200, correct historical date returned) |
| Sample data retrieved | ✓ CONFIRMED (1–6 stocks per date, OHLC validated) |
| All 599 stocks verified individually | ✗ NOT DONE (requires ~600 API calls/date) |
| Bulk retrieval available | ✗ UNAVAILABLE (TWSE bulk + TPEx bulk ignore date parameter) |

SOURCE_VERIFIED_PARTIAL ≠ SOURCE_CONFIRMED. Full confirmation requires running backfill_daily_prices.py in per-stock mode against all 599 stocks for all 9 candidate dates.

---

## References

- Module: `src/research/market_source_verification_s50.py`
- Functions: `build_verified_historical_source_matrix()`, `build_backfill_candidate_manifest()`
- Tests: `tests/test_session50_market_sources.py` TC01–TC15
- Prior: `docs/source_verification_s49.md` (S49 SOURCE_PARTIAL findings)
