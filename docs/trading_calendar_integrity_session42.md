# Trading Calendar Integrity Report — Session 42

**Date:** 2026-11-09
**Session:** 42
**Verdict:** CALENDAR_FAILED (39.1% of comparison signals on non-trading days)

---

## 1. Purpose

Verify that forward signal `trade_date` values correspond to actual Taiwan market trading days, using `daily_prices` as ground truth.

---

## 2. Ground Truth Source

Calendar source: `daily_prices` table (TWSE price feed ingested by daily cron pipeline).  
Data as of: 2026-11-09.

**October 2026 trading days (19 total):**  
Oct 01, 02, 05, 06, 07, 08, 12, 13, 14, 15, 16, 19, 20, 21, 22, 27, 28, 29, 30

---

## 3. Signal Date Audit

| Signal Date | Market Status | Reason | n Buy/SB | Fill Date |
|---|---|---|---|---|
| 2026-10-09 | NON_TRADING_DAY | Pre-National Day holiday (補假); Friday but market closed | 99 | 2026-10-12 |
| 2026-10-10 | NON_TRADING_DAY | National Day (國慶日) + Saturday | 4 | 2026-10-12 |
| 2026-10-11 | NON_TRADING_DAY | Sunday | 4 | 2026-10-12 |
| 2026-10-12 | TRADING_DAY | — | 46 | 2026-10-13 |
| 2026-10-13 | TRADING_DAY | — | 27 | 2026-10-14 |
| 2026-10-14 | TRADING_DAY | — | 55 | 2026-10-16 |
| 2026-10-16 | TRADING_DAY | — | 39 | 2026-10-21 |

**Fill date source:** `forward_signals.execution_date` (NEXT_OPEN architecture). For non-trading-day signals where `execution_date` is NULL, the next trading day from `daily_prices` is used (all three map to Oct 12).

---

## 4. Impact Summary

| Metric | Value |
|---|---|
| Total buy/strong_buy signals in comparison window | 274 |
| Non-trading-day signals (Oct 09+10+11) | 107 |
| Non-trading-day percentage | **39.1%** |
| Fill date for all 3 non-trading dates | 2026-10-12 |
| Trading-day signals | 167 |

**CALENDAR_FAILED**: 39.1% exceeds the 5% threshold for CALENDAR_PARTIAL.

---

## 5. Root Cause

The cron job runs on calendar days, including holidays and weekends. When the market is closed, the job generates signals with the current date as `trade_date`, but sets `execution_date = NULL` (no NEXT_OPEN execution entry). The V3ComparisonEngine reads `trade_date` for clustering, not `execution_date`.

**Result in S41 analysis:** Oct 09, 10, 11 were treated as 3 separate signal-date clusters. Because each had only n=4-99 signals and unusual returns (micro-clusters with +10%/+30%), they inflated the cluster-corrected grand mean from +1.21% to +6.49%.

---

## 6. Correction Applied in S42

Non-trading-day signals are merged into their fill-date cluster (Oct 12). This:
- Reduces 7 signal-date clusters → 5 fill-date clusters
- Reduces grand mean D_v3 vs A_direct from **+6.49% → +1.21%**
- Maintains SIGNIFICANCE_INCONCLUSIVE (CI still includes zero)

---

## 7. Verdict

```
CALENDAR_FAILED: 107/274 (39.1%) signals on non-trading days
CORRECTION: merged into fill Oct 12 cluster
IMPACT: grand mean correction -5.28ppt (from +6.49% to +1.21%)
```
