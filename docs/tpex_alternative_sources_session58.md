# TPEx Alternative Sources — Session 58

**Verdict**: TPEX_ALTERNATIVE_UNVERIFIED  
**Date**: 2026-11-10

---

## Background

S57 confirmed RC-03: TPEx bulk endpoint `tpex_mainboard_daily_close_quotes` ignores the `?d=` date parameter (always returns today's data). S58 reconfirmed this. As a result, historical TPEx data cannot be recovered via the bulk endpoint.

This document records the S58 search for TPEx alternative sources.

---

## Sources Assessed

### Source 1: TPEx OpenAPI Bulk (tpex_mainboard_daily_close_quotes)

| Field | Value |
|-------|-------|
| Endpoint | `tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes` |
| Historical support | NO |
| Full OHLCV | NO (close-focused) |
| Volume | YES (but see field mismatch below) |
| Verdict | **TPEX_ALTERNATIVE_NOT_FOUND** |

**Volume field mismatch**: TPEx API returns `"TradingShares"` but the pipeline script likely reads `"TradeVolume"`. This is the probable cause of `volume=NULL` for all 5737 TPEx records in `daily_prices`. Script fix needed: map `TradingShares` → volume.

This is a separate issue from date recovery — even with correct volume field, historical dates are not recoverable.

### Source 2: TPEx Per-Stock Historical (tpex_mainboard_stock_daily_close_quotes)

| Field | Value |
|-------|-------|
| Endpoint | `tpex.org.tw/openapi/v1/tpex_mainboard_stock_daily_close_quotes?d=1151029&s=2498` |
| Historical support | UNKNOWN (URL redirected) |
| Full OHLCV | UNKNOWN |
| Volume | UNKNOWN |
| Verdict | **TPEX_ALTERNATIVE_UNVERIFIED** |

**Test result**: URL returned a redirect to TPEx homepage. The correct per-stock historical endpoint URL for TPEx remains unknown. The TPEx website mentions "上櫃個股歷史行情" (listed stock history) but the exact API path was not discovered in S58.

### Source 3: TWSE for TPEx Cross-Listed Stocks

| Field | Value |
|-------|-------|
| Endpoint | `twse.com.tw/exchangeReport/STOCK_DAY` |
| Historical support | YES |
| Full OHLCV | YES |
| Volume | YES |
| Verdict | **TPEX_ALTERNATIVE_PARTIAL** |

TWSE single-stock API covers TWSE-listed stocks. Many large-cap stocks (2317, 2882, etc.) are exclusively on TWSE. The v8.0 research universe of ~599 stocks is predominantly TWSE. Pure TPEx-exclusive ordinary stocks require a separate source not found in S58.

---

## Summary

| Gap Type | Source | Status |
|----------|--------|--------|
| TWSE stocks | TWSE single-stock (T2) | FEASIBLE_VERIFIED |
| TPEx-exclusive stocks | No source found | TPEX_ALTERNATIVE_NOT_FOUND |
| TPEx bulk historical | Not available | DATE_PARAM_IGNORED |

**For the v8.0 research universe (~599 TWSE stocks), the lack of TPEx alternative has minimal impact** — the universe is TWSE-focused. The gap in TPEx-exclusive ordinary stocks affects only stocks outside the research universe.

---

## Volume Field Fix (Separate Issue)

Even for current-day TPEx data, the volume field mismatch causes NULL volume in `daily_prices`. Fix: in `scripts/backfill_daily_prices.py`, update TPEx volume field mapping from `"TradeVolume"` to `"TradingShares"`. This does not require new authorization (it's an existing pipeline bug), but should be batched with the already-designed TPEx patch (error propagation fix) for a single deployment.
