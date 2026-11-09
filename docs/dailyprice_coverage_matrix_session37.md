# DailyPrice Coverage Matrix — Session 37

**Date:** 2026-11-08  
**Audit Type:** Read-only coverage analysis  
**Version:** session37_v1

---

## 1. MarketCoverageSummary

**Verdict: `COVERAGE_PARTIAL`**

Of 572 total dates in daily_prices (Jul 2024 – Nov 2026), only 25 have full-market data. 538 dates have TWSE-only-like data (400–900 stocks), 9 dates have proxy-only (0050), and 1 date (Nov 6) has 0 rows.

**Critical:** "Full-market" and "TWSE-only" cannot be precisely verified without an authoritative TWSE/TPEx reference master by date. All coverage verdicts below are based on observed data patterns, not on a certified stock count denominator.

---

## 2. Coverage Categories

| Category | Criteria (Observed) | Date Count | Confidence |
|---|---|---|---|
| `FULL_MARKET_LOADED` | ≥5000 distinct stock_ids | 25 | MEDIUM (not VERIFIED — no authoritative denominator) |
| `TWSE_ONLY` | 400–900 stock_ids, all in master | 404 | MEDIUM |
| `TWSE_SPARSE` | 400–900 stock_ids, mix of master + orphan | ~134 | MEDIUM |
| `PROXY_ONLY` | 1 stock (0050 only) | 9 | HIGH |
| `MISSING` | 0 stock_ids | 1 (Nov 6) | HIGH |

**Note:** `FULL_MARKET_LOADED` ≠ `FULL_MARKET_VERIFIED`. Without an authoritative count of listed securities per date, we cannot compute a true coverage ratio.

---

## 3. Full Historical Coverage Summary (Monthly)

| Month | Dates | Min stocks | Max stocks | Min in-master | Max in-master | Type |
|---|---|---|---|---|---|---|
| 2024-07 | ~22 | 713 | 716 | 713 | 716 | TWSE_ONLY |
| 2024-08 | ~22 | 709 | 714 | 709 | 714 | TWSE_ONLY |
| 2024-09 | ~21 | 713 | 718 | 713 | 718 | TWSE_ONLY |
| 2024-10 | ~23 | 715 | 720 | 715 | 720 | TWSE_ONLY |
| 2024-11 | ~20 | 713 | 719 | 713 | 719 | TWSE_ONLY |
| 2024-12 | ~21 | 715 | 721 | 715 | 721 | TWSE_ONLY |
| 2025-01 | ~22 | 717 | 721 | 717 | 721 | TWSE_ONLY |
| 2025-02 | ~20 | 715 | 720 | 715 | 720 | TWSE_ONLY |
| 2025-03 | ~21 | 718 | 722 | 718 | 722 | TWSE_ONLY |
| 2025-04 | ~21 | 715 | 722 | 715 | 722 | TWSE_ONLY |
| 2025-05 | ~21 | 715 | 721 | 715 | 721 | TWSE_ONLY |
| 2025-06 | ~20 | 713 | 722 | 713 | 722 | TWSE_ONLY |
| 2025-07 | ~23 | 714 | 721 | 714 | 721 | TWSE_ONLY |
| 2025-08 | ~21 | 716 | 722 | 716 | 722 | TWSE_ONLY |
| 2025-09 | ~21 | 713 | 722 | 713 | 722 | TWSE_ONLY |
| 2025-10 | ~22 | 715 | 722 | 715 | 722 | TWSE_ONLY |
| 2025-11 | ~21 | 717 | 721 | 717 | 721 | TWSE_ONLY |
| 2025-12 | ~21 | 718 | 722 | 718 | 722 | TWSE_ONLY |
| 2026-01 | ~21 | 717 | 721 | 717 | 721 | TWSE_ONLY |
| 2026-02 | ~20 | 719 | 723 | 719 | 723 | TWSE_ONLY |
| 2026-03 | ~21 | 719 | 724 | 719 | 724 | TWSE_ONLY |
| 2026-04 | ~21 | 719 | 724 | 719 | 724 | TWSE_ONLY |
| 2026-05 | ~20 | 718 | 722 | 718 | 722 | TWSE_ONLY |
| 2026-06 | ~20 | 719 | 6393 | 719 | 725 | MIXED (first full-market backfill) |
| 2026-07 | ~23 | 496 | 7272 | 496 | 720 | MIXED |
| 2026-08 | ~21 | 496 | 7119 | 496 | 719 | MIXED |
| 2026-09 | ~21 | 494 | 6324 | 494 | 719 | MIXED |
| 2026-10 | ~19 | 1 | 656 | 1 | 500 | MIXED (PROXY_ONLY + SPARSE) |
| 2026-11 | ~5 | 1 | 6957 | 1 | 720 | MIXED (PROXY_ONLY + FULL + MISSING) |

---

## 4. DailyPriceCoverageMatrix — Oct–Nov 2026 Detail

| Date | Total | In-master | Orphan 4-digit | 5-digit | 6-digit | 4-dig 0-prefix | Verdict |
|---|---|---|---|---|---|---|---|
| 2026-10-01 | 499 | 499 | 0 | 0 | 0 | 8 | TWSE_ONLY |
| 2026-10-02 | 499 | 499 | 0 | 0 | 0 | 8 | TWSE_ONLY |
| 2026-10-05 | 500 | 500 | 0 | 0 | 0 | 8 | TWSE_ONLY |
| 2026-10-06 | 500 | 500 | 0 | 0 | 0 | 8 | TWSE_ONLY |
| 2026-10-07 | 497 | 497 | 0 | 0 | 0 | 8 | TWSE_ONLY |
| 2026-10-08 | 1 | 1 | 0 | 0 | 0 | 1 | PROXY_ONLY |
| 2026-10-09 | — | — | — | — | — | — | MISSING (no daily_prices; V6 signals use Oct 7 price) |
| 2026-10-10 | 0 | 0 | 0 | 0 | 0 | 0 | MISSING |
| 2026-10-11 | 0 | 0 | 0 | 0 | 0 | 0 | MISSING |
| 2026-10-12 | 655 | 394 | 204 | 44 | 13 | 4 | TWSE_SPARSE (+ETF) |
| 2026-10-13 | 656 | 395 | 204 | 44 | 13 | 4 | TWSE_SPARSE (+ETF) |
| 2026-10-14 | 656 | 395 | 204 | 44 | 13 | 4 | TWSE_SPARSE (+ETF) |
| 2026-10-15 | 1 | 1 | 0 | 0 | 0 | 1 | PROXY_ONLY |
| 2026-10-16 | 655 | 395 | 203 | 44 | 13 | 4 | TWSE_SPARSE (+ETF) |
| 2026-10-19 | 1 | 1 | 0 | 0 | 0 | 1 | PROXY_ONLY |
| 2026-10-20 | 1 | 1 | 0 | 0 | 0 | 1 | PROXY_ONLY |
| 2026-10-21 | 655 | 395 | 203 | 44 | 13 | 4 | TWSE_SPARSE (+ETF) |
| 2026-10-22 | 655 | 395 | 203 | 44 | 13 | 4 | TWSE_SPARSE (+ETF) |
| 2026-10-27 | 1 | 1 | 0 | 0 | 0 | 1 | PROXY_ONLY |
| 2026-10-28 | 656 | 395 | 204 | 44 | 13 | 4 | TWSE_SPARSE (+ETF) |
| 2026-10-29 | 1 | 1 | 0 | 0 | 0 | 1 | PROXY_ONLY |
| 2026-10-30 | 1 | 1 | 0 | 0 | 0 | 1 | PROXY_ONLY |
| 2026-11-02 | 1 | 1 | 0 | 0 | 0 | 1 | PROXY_ONLY |
| 2026-11-03 | 1 | 1 | 0 | 0 | 0 | 1 | PROXY_ONLY |
| 2026-11-04 | 6957 | 720 | 1249 | 112 | 4868 | 8 | FULL_MARKET_LOADED |
| 2026-11-05 | 6589 | 718 | 1249 | 112 | 4502 | 8 | FULL_MARKET_LOADED |
| 2026-11-06 | 0 | 0 | 0 | 0 | 0 | 0 | **MISSING** (cron failure) |

---

## 5. Coverage Ratio Note

Coverage ratio **cannot be computed precisely** without an authoritative universe denominator. Prior sessions used `non_0050 >= 5000` as a proxy for "full market" — this is a *data loading completeness indicator*, not a stock universe coverage metric.

For the TWSE-only period (Jul 2024 – May 2026):
- Observed: 713–724 stocks/day
- Master: 826 total
- Implicit coverage: ~87–88% of master stocks have prices each day
- **Missing coverage denominator:** We don't know how many TWSE stocks were listed on each historical date (varies due to listings/delistings)

For ForwardSignals dates (Oct 12–28):
- Observed: 394–395 master stocks (of 826 total master)
- Implicit coverage of master: ~48%
- **Why only 48%?** On Oct 12–28, only a subset of TWSE stocks was downloaded. The data loading on these dates was neither a full TWSE batch nor a proxy-only batch. This may be due to a partial data source change.

---

## 6. Missing Trading Day Analysis

| Date | Expected | Actual | Cause | Recovery Status |
|---|---|---|---|---|
| 2026-11-06 | Full market | 0 rows | Cron execution failure | NOT BACKFILLED (not authorized) |
| 2026-10-09 | Full/sparse (not in DB) | 0 rows | Unknown — no daily_prices loaded | V6.0 signals used Oct 7 prices |
| 2026-10-10 | National Holiday | 0 rows | National Day holiday | Expected missing |
| 2026-10-11 | Unclear | 0 rows | Unknown | V6.0 signals generated for this date with 10 signals |

---

## 7. Duplicate Check

| Dimension | Result |
|---|---|
| (stock_id, date) duplicates in daily_prices | **0** |

---

## 8. Data Freshness

| Metric | Value |
|---|---|
| Latest date in daily_prices | 2026-11-05 |
| Latest 0050 date | 2026-11-05 |
| Today | 2026-11-08 (weekend) |
| Trading days since latest data | Nov 6 (1 day, cron failure) |
| Nov 7–8 | Weekend (non-trading) |

---

## 9. Verdict

| Dimension | Verdict |
|---|---|
| Coverage accuracy | UNVERIFIED (no authoritative denominator) |
| Consistency (backtest era) | HIGH (713–724/day, all in master, clean) |
| Consistency (ForwardSignals era) | LOW (394–395 master stocks — only 48%) |
| ETF contamination | PRESENT on ForwardSignals dates |
| Nov 6 recovery | NOT AUTHORIZED |
| Duplicate-free | PASS |
| **Overall** | **`COVERAGE_PARTIAL`** |
