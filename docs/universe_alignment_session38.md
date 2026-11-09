# Universe Alignment Audit — Session 38

**Date:** 2026-11-08  
**Session:** 38  
**Verdict:** `SIGNIFICANT_MISMATCH`

---

## 1. Three-Phase Universe Summary

| Phase | Date Range | Stocks/Day | TWSE Common | TPEx | ETFs | Note |
|---|---|---|---|---|---|---|
| Training / Backtest | Jul 2024 – May 2026 | ~720 | 720 | 0 | 0 | Clean TWSE-only era |
| Walk-forward | (design only, no windows) | — | — | — | — | 0 feasible windows (Session 28) |
| Forward Signals (v8.0) | Oct 12–28, 2026 | 394–410 | 368 unique | 0 | 42 unique | Mismatched |

---

## 2. Alignment Gap Analysis

### Gap 1: Stock Count (HIGH severity)

| Metric | Training | Forward |
|---|---|---|
| Stocks per day | ~720 | 394–410 |
| Coverage ratio | — | 55–57% |
| Threshold (≥70%) | — | FAIL |

**Root cause**: Oct 2026 DailyPrice loading pipeline only provided prices for ~394 of 826 master stocks on each signal date. The remaining 432 master stocks had no prices and could not receive signals.

**Impact**: Signal universe in forward phase is structurally different from training. The 48% of master stocks absent on signal dates create systematic selection bias — only stocks with active price feeds on a specific day receive signals.

---

### Gap 2: ETF Contamination Rate (HIGH severity)

| Metric | Training | Forward |
|---|---|---|
| ETF signals | 0 (0%) | 213 (9.52%) |
| ETF unique stocks | 0 | 42 |
| Threshold (Δ < 5%) | — | FAIL |

**Root cause**: The signal generation engine does not filter by security type. During the forward era, ETFs (0050, 00646, etc.) had DailyPrice records and were processed alongside common stocks.

**Impact**: Performance comparisons between training (0% ETF) and forward (9.52% ETF) phases are biased because the return distribution differs between common stocks and ETFs.

---

### Gap 3: TPEx Inclusion (MEDIUM severity → structural)

| Metric | Training | Forward |
|---|---|---|
| TPEx common stocks | 0 | 0 |
| TPEx in prices | 0 (this era) | 895 (orphans) |
| Coverage of TPEx | 0% | 0% of signals |

**Note**: TPEx absence is consistent between training and forward (both 0%), so this gap does NOT create an alignment mismatch between the two phases. However, it represents a universe incompleteness that affects absolute performance comparisons against the full Taiwan stock market.

---

### Gap 4: Orphan TWSE Stocks (MEDIUM severity)

| Metric | Training | Forward |
|---|---|---|
| Orphan TWSE in signals | 0 (all used master) | 787 signals from non-master TWSE stocks |
| Non-master in signal pool | 0% | ~39% of TWSE-common signals |

**Root cause**: The forward signal era's DailyPrice load included 377 TWSE common stocks that are NOT in the platform's stocks master. These generated 787 signals (35.2% of v8.0 total).

**Impact**: Model was trained only on the 826-stock master subset. Forward signals include stocks the model has never "seen" in training — a universe expansion mid-deployment.

---

## 3. Full Alignment Matrix

| Dimension | Training Era | Forward Era | Status |
|---|---|---|---|
| Universe denominator | 826 master only | 826 master + 377 TWSE orphans + ETFs | MISMATCH |
| Stock count per day | ~720 | 394–395 (master) | MISMATCH |
| ETF contamination | 0% | 9.52% | MISMATCH |
| TPEx inclusion | 0% | 0% | ALIGNED |
| Delisted stocks | Possible (3 mid-era) | 0 | PARTIAL |
| Source price date | Not verified | Not verified | UNVERIFIED |

---

## 4. Conclusion

**UNIVERSE_ALIGNMENT_VERDICT: `SIGNIFICANT_MISMATCH`**

Three of four measured dimensions show alignment failures of HIGH or MEDIUM severity.

The implication for research:

| Assessment | Validity |
|---|---|
| Training era backtest validity (internal) | CONDITIONAL (see Session 37) |
| Forward era signals as prospective test of model | COMPROMISED — universe mismatch |
| Cross-phase performance comparison (V3 vs V2) | CONDITIONAL — in-sample only |
| Activation decision based on forward signals | BLOCKED — universe contaminated |

---

## 5. Remediation Requirements

Before any forward era signals can serve as a valid out-of-sample test:

1. **ETF filtering**: Exclude 42 ETF stock_ids from signal generation (SecurityClassificationService)
2. **DailyPrice pipeline fix**: Investigate why only 394/826 master stocks have prices on Oct 12–28
3. **Orphan TWSE decision**: Either add 377 orphan TWSE stocks to master, or explicitly exclude them from signal generation
4. **TPEx decision**: Make explicit design decision — either add TPEx to training or document exclusion
5. **Point-in-time universe**: Implement listing_date filtering to prevent future look-ahead bias
