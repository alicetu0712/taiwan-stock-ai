# TWSE T2 Bounded Pilot — Session 58

**Verdict**: T2_PILOT_PASS  
**Requests used**: 5 (within 12 cap)  
**Date**: 2026-11-10

---

## Pilot Design

| Parameter | Value |
|-----------|-------|
| Max requests allowed | 12 |
| Actual requests (WebFetch) | 5 |
| Python requests (SSL failed) | 9 (never reached server) |
| Total server-side budget used | 5 |
| Concurrency | Sequential |
| Delay | WebFetch (manual) |

**SSL note**: 9 Python-based requests were attempted before switching to WebFetch. All failed with `CERTIFICATE_VERIFY_FAILED` (Python 3.13.3 environment lacks TWSE SSL certs). These requests never reached TWSE servers, so server-side budget is unaffected.

---

## Pilot Results

| ID | Stock | Month | Dates Retrieved | OHLCV | Status |
|----|-------|-------|----------------|-------|--------|
| P01 | 2330 TSMC | Oct 2026 | Oct29, Oct30 | FULL+V | PASS |
| P02 | 2317 Foxconn | Nov 2026 | Nov02, Nov03, Nov06, Nov09 | FULL+V | PASS |
| P03 | 2454 MediaTek | Oct 2026 | Oct29, Oct30 | FULL+V | PASS |
| P04 | 1301 Formosa Plastics | Oct 2026 | Oct29, Oct30 | FULL+V | PASS |
| P05 | 2882 Cathay FHC | Nov 2026 | Nov02, Nov03, Nov06, Nov09 | FULL+V | PASS |

**5/5 PASS. All FULL_OHLCV_WITH_VOLUME.**

---

## Monthly Response Semantics (S57 Correction)

The TWSE single-stock endpoint (`STOCK_DAY?date=YYYYMMDD&stockNo=ID`) returns **all trading days in the requested calendar month**, not a single date.

| S57 Assumption | S58 Correction |
|----------------|---------------|
| 1 request per date per stock | 1 request per month per stock |
| 6 dates × 1969 stocks = 11,814 calls | 2 months × 599 stocks = 1,198 calls |
| ~6.6 hours total runtime | ~40 minutes total runtime |
| Denominator: 1969 (all ordinary) | Denominator: 599 (v8.0 research universe) |

**Oct29 and Oct30 are covered by one October request per stock.**  
**Nov02, Nov03, Nov06, and Nov09 are covered by one November request per stock.**

---

## Key Findings

1. **P01 response confirmed**: October request returned 19 trading days (full month)
2. **Nov03 close controversy resolved**: P02 independently confirmed 2317 close = 245.5 (not 245.0)
3. **Nov06/09 upgraded**: 2317 and 2882 both FULL OHLCV+volume (not close-only)
4. **Industry diversity**: 4 industries covered (semiconductor, tech hardware, chemicals, financial)
5. **New stocks**: 1301 and 2882 not in S50 probes — pilot extends coverage evidence

---

## Important Distinction

**T2_PILOT_PASS ≠ FULL_MARKET_RECOVERY_AUTHORIZED**

- Pilot passed → endpoint works for verified stocks and months
- Compliance not verified → rate limit unknown
- Authorization not granted → AUTH01 required for full recovery
- Production not modified → all systems unchanged
