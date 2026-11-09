# Research Statistical Guardrails — Session 42

**Date:** 2026-11-09
**Session:** 42
**Verdict:** GUARDRAILS_CONDITIONAL (3 PASS, 2 CONDITIONAL, 5 mixed — 3 FAIL block G01/G03/G04)

---

## 1. Guardrail Results

| ID | Name | Status | Finding |
|---|---|---|---|
| G01 | Trading Calendar Integrity | **FAIL** | 107/274 (39.1%) signals on non-trading days |
| G02 | Metric Label Integrity | **PASS** | All alpha labels corrected in S41/S42 |
| G03 | Cluster Count Adequacy | **FAIL** | 5 clusters; threshold is ≥10 |
| G04 | Holding Period Non-Overlap | **FAIL** | 4/4 adjacent cluster pairs overlap |
| G05 | Signal Independence | **PASS** | Cluster means used (not signal-level) |
| G06 | Outcome Contamination (20D) | **PASS** | 5D and 20D analyses fully separated |
| G07 | Benchmark Consistency | **PASS** | 0050 benchmark recomputed from actual fill dates |
| G08 | Multiple Comparison Correction | **CONDITIONAL** | 3 comparisons without Bonferroni; all INCONCLUSIVE anyway |
| G09 | No Look-Ahead Leakage | **PASS** | NEXT_OPEN architecture verified |
| G10 | Sample Universe Stability | **CONDITIONAL** | ETF-like signals in comparison pool (~0.7%) |

**Summary:** 5 PASS, 2 CONDITIONAL, 3 FAIL

---

## 2. FAIL Guardrails — Detail

### G01: Trading Calendar — FAIL
39.1% of comparison signals have `trade_date` on non-trading days. These signals cannot represent an independent market session's investment decision. They were merged into the Oct 12 fill-date cluster in S42, but their presence means signal generation occurs on non-trading days.

**Fix:** Cron job should check trading calendar before writing signals. Signals on non-trading days should either be suppressed or explicitly marked with `is_trading_day=False`.

### G03: Cluster Count — FAIL
5 fill-date clusters, well below the minimum of 10 for reliable t-test inference. With df=4, the critical t at α=0.05 is 2.78, requiring a grand mean of approximately 2% to reject H0 (given observed σ=1.59%). The current +1.21% cannot clear this bar.

**Fix:** Accumulate more data (target: ≥10 non-overlapping fill-date clusters, ~2 months at current pace).

### G04: Holding Period Overlap — FAIL
5-day return windows for adjacent clusters overlap 2-6 calendar days. This induces cross-cluster correlation that the t-test assumes away. Even N=5 is too generous; effective N≤2.

**Fix:** Use 20D horizon (non-overlapping monthly batching) or HAC-corrected standard errors.

---

## 3. Overall Verdict

```
GUARDRAILS_CONDITIONAL
n_fail = 3 (G01, G03, G04)
n_conditional = 2 (G08, G10)
n_pass = 5 (G02, G05, G06, G07, G09)
Research-grade: NOT CLEARED for RANKING_SUPPORTED
```
