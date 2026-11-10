# Session 53: Single-stock API Fallback Feasibility

**Classification**: FALLBACK_PARTIAL  
**Safety**: Research-only analysis. No live API calls in module. No production writes.

## Summary

| Source | Status | Historical | Stocks | Evidence |
|--------|--------|-----------|--------|---------|
| TWSE_SINGLE_STOCK | SOURCE_VERIFIED_PARTIAL | Yes | 599 (v8.0 universe) | S50 real calls |
| TPEX_SINGLE_STOCK | SOURCE_UNVERIFIED | Unknown | 0 | Not tested |
| TWSE_BULK_HIST | SOURCE_UNAVAILABLE | No | 0 | S50: CSV response |
| TPEX_BULK_HIST | SOURCE_UNAVAILABLE | No | 0 | S50: current-date only |

**Overall Verdict**: FALLBACK_PARTIAL

TWSE single-stock (`STOCK_DAY?date=YYYYMMDD&stockNo=XXXX`) returns historically accurate monthly data. All 599 four-digit stocks in the v8.0 research universe are accessible. TPEx single-stock endpoint unknown → 0 TPEx stocks verified.

## TWSE Single-stock Specification

- **URL**: `www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date=YYYYMMDD&stockNo=XXXX`
- **Calls per date**: 599 (one per 4-digit stock in v8.0 universe)
- **Estimated runtime**: ~20 minutes at 2s/call
- **Rate limit risk**: LOW (2s pause; designed for retail use)
- **Verified stocks (S50)**: TSMC (2330), MediaTek (2454), Foxconn (2317), CTBC (2891), FPC (6505), Largan (3008)
- **Verified dates**: Oct 29/30, Nov 02/03, Nov 06/09

## Fallback Gap

TWSE single-stock covers only TWSE-listed stocks (~30% of market by stock count). TPEx-listed stocks (~800 common stocks) are NOT covered. Full market backfill (≥5000 stocks required by `_MIN_COVERED_STOCKS`) requires TPEx coverage.

For research purposes (v8.0 universe = 599 TWSE stocks), TWSE single-stock is sufficient.

## 12 Failure Scenarios

| ID | Mode | Result |
|----|------|--------|
| FS-01 | HTTP_FAILURE | HANDLED_CORRECTLY |
| FS-02 | TIMEOUT | HANDLED_CORRECTLY |
| FS-03 | RATE_LIMIT | PARTIAL_RECOVERY (no 429-specific delay) |
| FS-04 | STALE_DATE | HANDLED_CORRECTLY (QG-5 blocks) |
| FS-05 | WRONG_STOCK_ID | PARTIAL_RECOVERY (no explicit stock-id check) |
| FS-06 | MISSING_OHLC | HANDLED_CORRECTLY (parser skips None rows) |
| FS-07 | DUPLICATE_RESPONSE | HANDLED_CORRECTLY (QG-4 blocks) |
| FS-08 | PARTIAL_UNIVERSE | HANDLED_CORRECTLY (QG-6 blocks) |
| FS-09 | TPEX_UNAVAILABLE | PARTIAL_RECOVERY (TWSE-only write proceeds) |
| FS-10 | BENCHMARK_ONLY | HANDLED_CORRECTLY (QG-6 blocks) |
| FS-11 | RETRY_EXHAUSTION | HANDLED_CORRECTLY (stock skipped) |
| FS-12 | SUCCESSFUL_RECOVERY | HANDLED_CORRECTLY |

## Critical Caveat

This analysis is **research/prototype** — the fallback adapter has not been deployed. AUTH01 authorization is required before any production backfill using single-stock APIs.
