# Market Data Integrity Audit — Session 36

**Date:** 2026-11-08  
**Audit Type:** Read-only market data inspection  
**Version:** session36_v1

---

## 1. MarketDataIntegrityReport Summary

**Verdict: `DATA_INTEGRITY_PARTIAL`**

Full-market coverage (≥5000 stocks) exists for only 25 of 567 trading dates in the DailyPrice table. The vast majority of dates have SPARSE (TWSE-only ~655 stocks) or PROXY_ONLY (0050 only) coverage. Nov 6, 2026 has 0 rows.

---

## 2. Database Totals

| Item | Value |
|---|---|
| Total DailyPrice rows | 534,770 |
| Date range | 2024-07-01 to 2026-11-05 |
| Duplicate (stock_id, date) pairs | **0** |
| Stocks table count | 826 (TWSE only) |
| TPEx stocks in stocks table | **0** |

---

## 3. 0050 Coverage

| Field | Value | Verdict |
|---|---|---|
| Trade dates | 567 | — |
| Date range | 2024-07-01 to 2026-11-05 | — |
| Latest date | 2026-11-05 | — |
| Missing Nov 6 | Yes (cron failure) | BLOCKER |
| Data Quality | Continuous proxy | **PASS** |

0050 is the most complete series. Used as trading calendar proxy throughout the system.

---

## 4. TWSE Coverage

| Field | Value |
|---|---|
| Stocks in `stocks` table | 826 (all marked TWSE) |
| Typical non-0050 stocks per SPARSE date | ~655 |
| Dates with SPARSE (100–999 stocks) | ~40 known dates |
| Explanation | ~826 stocks total, some excluded; TWSE batch not always downloaded |

**TWSE coverage is PARTIAL.** Most dates from Oct 2026 have ~655 TWSE stocks (not all 826), because excluded or delisted stocks reduce the count.

---

## 5. TPEx Coverage

| Field | Value |
|---|---|
| TPEx stocks in `stocks` table | **0** |
| TPEx stocks in `daily_prices` (via batch) | Estimated ~4,000+ on full-market dates |
| Tracking granularity | Unknown — TPEx not separately identified |
| Latest TPEx date | Unknown (mixed with TWSE in daily_prices) |

**TPEx is NOT tracked as a distinct data source.** TPEx stocks appear in `daily_prices` on full-market backfill dates (Nov 4–5: ~6957 stocks = TWSE 826 + TPEx ~6131) but cannot be independently verified because the `stocks` table does not include TPEx entries.

**Observed fact:** On Nov 4, 6957 total stocks. stocks table has 826 TWSE. Implies ~6131 TPEx stocks present on Nov 4 only via backfill.

---

## 6. DailyPrice Coverage by Type

| Coverage Category | Criteria | Count (dates) | Example Dates |
|---|---|---|---|
| **FULL** (≥5000 stocks) | Full market batch | **25** | Jun 2026, Jul 2026, Nov 4–5 |
| **SPARSE** (100–999) | TWSE-only subset | ~40 | Oct 12–28, 2026 |
| **PROXY_ONLY** (1 stock = 0050) | Only 0050 downloaded | Multiple | Oct 15, 19, 20, 27, 29, 30 |
| **MISSING** (0 stocks) | No data | **1** (Nov 6) | 2026-11-06 |

---

## 7. Oct–Nov 2026 Detail

| Date | Non-0050 | 0050 | Coverage | Note |
|---|---|---|---|---|
| 2026-10-01 | 498 | 1 | SPARSE | — |
| 2026-10-08 | 0 | 1 | PROXY_ONLY | — |
| 2026-10-12 | 654 | 1 | SPARSE | ForwardSignals date |
| 2026-10-13 | 655 | 1 | SPARSE | ForwardSignals date |
| 2026-10-14 | 655 | 1 | SPARSE | ForwardSignals date |
| 2026-10-15 | 0 | 1 | PROXY_ONLY | — |
| 2026-10-16 | 654 | 1 | SPARSE | ForwardSignals date |
| 2026-10-19 | 0 | 1 | PROXY_ONLY | — |
| 2026-10-20 | 0 | 1 | PROXY_ONLY | — |
| 2026-10-21 | 654 | 1 | SPARSE | ForwardSignals date |
| 2026-10-22 | 654 | 1 | SPARSE | ForwardSignals date |
| 2026-10-27 | 0 | 1 | PROXY_ONLY | — |
| 2026-10-28 | 655 | 1 | SPARSE | ForwardSignals date (last) |
| 2026-10-29 | 0 | 1 | PROXY_ONLY | — |
| 2026-10-30 | 0 | 1 | PROXY_ONLY | — |
| 2026-11-02 | 0 | 1 | PROXY_ONLY | — |
| 2026-11-03 | 0 | 1 | PROXY_ONLY | — |
| 2026-11-04 | 6956 | 1 | **FULL** | Manual backfill |
| 2026-11-05 | 6588 | 1 | **FULL** | Cron partial (later) |
| 2026-11-06 | 0 | 0 | **MISSING** | Cron failure |

---

## 8. Missing Trading Dates

| Date | Day | Expected | Actual | Cause |
|---|---|---|---|---|
| 2026-11-06 | Friday | Full market | 0 rows | Cron execution failure |

Nov 6 is the only confirmed missing trading day. Nov 7–8 are weekend (non-trading). No recovery authorized.

---

## 9. Duplicate Check

| Check | Result |
|---|---|
| (stock_id, date) pairs with count > 1 | **0** |
| Verdict | No duplicates detected |

---

## 10. Research Impact: ForwardSignals Window

**Critical finding:** All 7 ForwardSignals dates (Oct 12–28, 2236 v8.0 signals) were computed on SPARSE data:

| Date | DailyPrice Stocks | Type | Signal Count |
|---|---|---|---|
| 2026-10-12 | 655 | SPARSE | 348 |
| 2026-10-13 | 656 | SPARSE | 387 |
| 2026-10-14 | 656 | SPARSE | 356 |
| 2026-10-16 | 655 | SPARSE | 261 |
| 2026-10-21 | 655 | SPARSE | 302 |
| 2026-10-22 | 655 | SPARSE | 323 |
| 2026-10-28 | 656 | SPARSE | 259 |

**Inference (not direct observation):** Signals were generated from ~655 TWSE-subset stocks, potentially excluding ~6000+ TPEx stocks and remaining TWSE stocks. This introduces selection bias in both V3 and baseline comparisons — both strategies were compared on the same restricted universe, but that universe (~10% of market) may not be representative.

This is a data quality concern for V3 research, not a correctness error. Both strategies were evaluated on the same data, but the universe is narrower than the full Taiwan market.

---

## 11. Data Quality Verdict

| Dimension | Verdict | Notes |
|---|---|---|
| 0050 completeness | **PASS** | Full history, latest Nov 5 |
| TWSE completeness | **PARTIAL** | Most dates SPARSE (~655 not 826) |
| TPEx completeness | **FAIL** | Not tracked separately; absent most dates |
| Nov 6 data | **MISSING** | Cron failure, not backfilled |
| Duplicates | **PASS** | Zero duplicates |
| ForwardSignals universe | **PARTIAL** | SPARSE coverage on all signal dates |
| **Overall** | **DATA_INTEGRITY_PARTIAL** | — |
