# Statistical Significance Audit — Session 41

**Date:** 2026-11-09
**Session:** 41
**Critical Verdict:** ALL S40 SIGNIFICANT_POSITIVE VERDICTS DOWNGRADED TO SIGNIFICANCE_INCONCLUSIVE

---

## 1. The Core Problem

Session 40's V3ComparisonEngine bootstrap CI treated all 274 signals as independent observations. This is **incorrect**: the 274 signals span only **7 trading dates**. Signals from the same date share:
- Same market conditions during hold period
- Same 0050 benchmark move
- Strong cross-sectional correlation in returns

Effective N ≈ 7 (not 274).

---

## 2. Cluster-Corrected Analysis

### Method
1. Group signals by signal_date → 7 clusters
2. Compute cluster-level mean delta (D_v3 - baseline) per date
3. Run one-sample t-test on the 7 cluster means (df=6)
4. Compute 95% CI using t-distribution with df=6

### Per-Date Results (D_v3 vs A_direct)

| Date | N Signals | Cluster Mean Delta | Warning |
|---|---|---|---|
| 2026-10-09 | 99 | +1.18% | — |
| 2026-10-10 | 4 | +10.09% | MICRO_CLUSTER |
| 2026-10-11 | 4 | +30.73% | MICRO_CLUSTER |
| 2026-10-12 | 46 | +1.20% | — |
| 2026-10-13 | 27 | +2.76% | — |
| 2026-10-14 | 55 | -1.52% | — |
| 2026-10-16 | 39 | +0.99% | — |

**Grand mean (cluster-level): +6.49%**
*(Inflated by Oct 10 and Oct 11 micro-clusters with extreme positive outliers)*

### Cluster-Corrected Results

| Comparison | Uncorrected CI (N=274) | Cluster CI (N=7) | p-value | S40 Verdict | S41 Revised |
|---|---|---|---|---|---|
| D_v3 vs A_direct | [+2.61%, +4.83%] | **[-3.95%, +16.93%]** | 0.179 | SIGNIFICANT_POSITIVE | **SIGNIFICANCE_INCONCLUSIVE** |
| D_v3 vs B_v1v2 | [+1.91%, +4.24%] | **[-4.93%, +16.57%]** | 0.233 | SIGNIFICANT_POSITIVE | **SIGNIFICANCE_INCONCLUSIVE** |
| D_v3 vs C_hybrid | [+2.65%, +4.85%] | **[-3.97%, +16.92%]** | 0.180 | SIGNIFICANT_POSITIVE | **SIGNIFICANCE_INCONCLUSIVE** |

**All three cluster CIs include zero → NOT statistically significant at p=0.05.**

---

## 3. Micro-Cluster Warning

Oct 10 and Oct 11 2026 are **non-standard trading days**:
- Oct 10 is Taiwan National Day (國慶日) — markets CLOSED
- Oct 11 is Sunday — markets CLOSED

4 signals each on these dates are likely cron runs on non-trading days. Their fills happen on the next available trading day, creating atypical hold periods with extreme variance.

**Impact:** These 2 dates contribute 10.09% and 30.73% mean deltas (both extreme positive outliers), inflating the cluster-level grand mean from ~1.5% to 6.49%.

**Without Oct 10 and Oct 11 (5 dates):**
- Cluster means: 1.18%, 1.20%, 2.76%, -1.52%, 0.99%
- Grand mean: **+1.12%** (dramatically lower)
- CI: approximately [-1.1%, +3.3%] (smaller but still likely includes zero)

---

## 4. Sign Test

| Comparison | Positive Dates / Total | Binomial p |
|---|---|---|
| D_v3 vs A_direct | 6/7 | 0.125 |
| D_v3 vs B_v1v2 | 5/7 | 0.453 |
| D_v3 vs C_hybrid | 6/7 | 0.125 |

No comparison reaches p < 0.05 by sign test. 5/7 for D_v3 vs B_v1v2 is not meaningful evidence.

---

## 5. Leave-One-Date-Out Analysis

| Dropped Date | n | Remaining Mean | CI Includes Zero? | Sign Change? |
|---|---|---|---|---|
| 2026-10-09 | 99 | +7.38% | Yes | No |
| 2026-10-10 | 4 | +5.89% | Yes | No |
| 2026-10-11 | 4 | +2.45% | Yes | No |
| 2026-10-12 | 46 | +7.37% | Yes | No |
| 2026-10-13 | 27 | +7.11% | Yes | No |
| 2026-10-14 | 55 | +7.83% | Yes | No |
| 2026-10-16 | 39 | +7.41% | Yes | No |

**Verdict: DIRECTIONALLY_STABLE** — sign never changes, but CI always includes zero.

---

## 6. Formal Retraction of S40 Verdict

The Session 40 label **SIGNIFICANT_POSITIVE** must be formally retracted for all three comparisons.

**Replacement verdict: SIGNIFICANCE_INCONCLUSIVE**

Rationale:
- Cluster-corrected CI includes zero for all comparisons
- p-values are 0.18-0.23 (not significant at conventional 5% threshold)
- 7 trading dates provide minimal statistical power
- Micro-cluster contamination from non-trading-day signals inflates grand mean

---

## 7. What Would Change This

Minimum requirements for a valid SIGNIFICANT_POSITIVE claim:
- **≥25 independent trading dates** (minimum adequate power)
- **Multi-regime coverage** (bull AND bear/neutral regimes)
- **Cluster-corrected CI that excludes zero**
- **Removal of non-trading-day signals** from comparison universe

Current status: 7 dates available. At current cron cadence (~5 dates/month), reaching 25 dates requires ~4-5 additional months of data.

---

## 8. Impact on Other S40 Claims

| S40 Claim | S41 Status |
|---|---|
| "SIGNIFICANT_POSITIVE" for D_v3 vs A_direct | RETRACTED → SIGNIFICANCE_INCONCLUSIVE |
| "SIGNIFICANT_POSITIVE" for D_v3 vs B_v1v2 | RETRACTED → SIGNIFICANCE_INCONCLUSIVE |
| "SIGNIFICANT_POSITIVE" for D_v3 vs C_hybrid | RETRACTED → SIGNIFICANCE_INCONCLUSIVE |
| "RANKING_CONDITIONAL" overall | UNCHANGED (still not RANKING_NOT_SUPPORTED) |
| "MARKET_AVOIDANCE_DRIVEN" attribution | UNCHANGED (confirmed) |
| "0050 avg -4.65%" during hold | CORRECTED: actual avg -2.16% (Oct 09-16 dates) |
