# S50 Data Corrections — Session 57

**Session ID**: S57  
**Date**: 2026-11-10  
**Status**: CORRECTIONS_DOCUMENTED

---

## Summary of Corrections

Sessions 55 and 56 both used an incomplete version of the S50 research data.
S57 re-read `src/research/market_source_verification_s50.py:_VERIFIED_RECORDS`
directly and found three significant discrepancies.

---

## Correction 1: Oct29 Record Count (Critical)

| Item | S55/S56 Claim | Actual (S50 source) |
|------|--------------|---------------------|
| Oct29 stock count | 3 stocks | **6 stocks** |
| OHLCV completeness | CLOSE_ONLY | FULL OHLCV for 2330/2454/2317; OHLCV (no volume) for 2891/6505/3008 |

**Impact**: S55/S56 calculated AUTH01 coverage as "3/1969 = 0.15%".
Correct coverage is "6/1969 = 0.30%" for OHLCV-available stocks.
Still far below any QG threshold; QG impact unchanged.

**Root Cause**: S55 `auth01_record_validation_session55.py` defined `_S50_VERIFIED_PRICES`
using only 3 stocks (2330=2415.0, 2454=4045.0, 2317=248.0) as CLOSE-only values.
The actual `_VERIFIED_RECORDS` in `market_source_verification_s50.py` has 6 stocks
with full OHLCV structure.

---

## Correction 2: Nov03 2317 Close Price

| Item | S55/S56 Claim | Actual (S50 source) |
|------|--------------|---------------------|
| Nov03 2317 close | 245.0 | **245.5** |
| OHLCV | Close only? | FULL: O=249.0/H=250.0/L=243.5/C=245.5/V=44139321 |

**Impact**: Any calculation using the Nov03 2317 close price (e.g., 5D/20D return
denominator for 2317 signals entered Nov03) used 245.0 instead of 245.5.
Error magnitude: 0.5/245.0 = 0.2% — small but should be corrected in production data.

---

## Correction 3: Nov09 2330 Close Price

| Item | S55/S56 Claim | Actual (S50 source) |
|------|--------------|---------------------|
| Nov09 2330 close | 2200.0 (S56) | **2235.0** |

**Impact**: S56 auth01_impact_simulation used 2200.0 for Nov09 2330.
Actual value from S50 source is 2235.0.
Error magnitude: 35.0/2235.0 = 1.6% — moderate error in any return calculation using this value.

---

## Full Oct29 Verified Records (Corrected)

| Stock | Open | High | Low | Close | Volume | Quality |
|-------|------|------|-----|-------|--------|---------|
| 2330 | 2420.0 | 2425.0 | 2390.0 | 2415.0 | 18403916 | FULL_OHLCV_V |
| 2454 | 4205.0 | 4225.0 | 4000.0 | 4045.0 | 6867223 | FULL_OHLCV_V |
| 2317 | 250.0 | 253.5 | 247.0 | 248.0 | 21358260 | FULL_OHLCV_V |
| 2891 | 74.5 | 76.2 | 74.1 | 75.3 | None | OHLCV_NO_VOLUME |
| 6505 | 102.5 | 103.0 | 98.5 | 98.6 | None | OHLCV_NO_VOLUME |
| 3008 | 6315.0 | 6315.0 | 5815.0 | 5815.0 | None | OHLCV_NO_VOLUME |

---

## Impact on Prior Verdicts

| Verdict | S55/S56 | Revised |
|---------|---------|---------|
| Oct29 coverage | 3/1969 = 0.15% | 6/1969 = 0.30% |
| Oct29 OHLCV completeness | CLOSE_ONLY | PARTIAL (3/6 have volume, all 6 have OHLCV) |
| AUTH01 quality | CLOSE_ONLY × 3 stocks | OHLCV × 3 stocks + OHLCV_NO_V × 3 stocks |
| QG impact of S50 insert | NO_CHANGE | NO_CHANGE (still far below threshold) |
| Nov03 2317 close | 245.0 | **245.5** |
| Nov09 2330 close | 2200.0 | **2235.0** |

**AUTH01_PARTIAL verdict stands** but is now better characterized:
S50 provides 6 Oct29 records with full OHLCV (not close-only), but volume missing for 3 of 6.
Full recovery still requires T2 (single-stock API for all 1969 ordinary stocks).

---

## Files Affected by Prior Errors

| File | Error | Status |
|------|-------|--------|
| `src/research/auth01_impact_simulation_s56.py` | Used 3-stock CLOSE_ONLY subset | Documents error; not modified |
| `src/research/tpex_patch_verification_s55.py` | Same | Documents error; not modified |
| `docs/auth01_record_validation_session55.md` | "3 Oct29 records verified, CLOSE only" | Superseded by S57 corrections |
| `docs/auth01_impact_simulation_session56.md` | "0.15% coverage, 3 stocks" | Superseded; actual 0.30%, 6 stocks |

Corrections are documented here and encoded in S57 research modules.
No prior files modified — corrections applied forward in S57.
