# Corrected 5D Comparison — Session 43

## 1. What Changed from S42

Session 42 used 5 fill-date clusters (fill Oct 12-21). Session 43 applies the v8.0-strict filter:

| Change | S42 | S43 |
|--------|-----|-----|
| Clusters used | 5 (fill Oct 12, 13, 14, 16, 21) | 3 strict (fill Oct 13, 14, 16) |
| v6.0 exclusion | No (fill Oct 12 cluster = 107 v6.0 signals) | Yes (fill Oct 12 excluded) |
| Incomplete cluster | fill Oct 21 included | fill Oct 21 flagged INCOMPLETE |
| Grand mean vs A_direct | +1.21% | +0.81% |
| Verdict | SIGNIFICANCE_INCONCLUSIVE | SIGNIFICANCE_INCONCLUSIVE |

## 2. Cluster-Level Results

### Strict Clusters (v8.0 only, complete 5D exit data)

| Fill Date | Signal Date | n Signals | Δ vs A_direct | Δ vs B_v1v2 | Δ vs C_hybrid |
|-----------|------------|-----------|---------------|-------------|---------------|
| Oct 13 | Oct 12 | 46 | +1.20% | +0.84% | +1.07% |
| Oct 14 | Oct 13 | 27 | +2.76% | +0.14% | +2.76% |
| Oct 16 | Oct 14 | 55 | -1.52% | -1.41% | -1.49% |

### Excluded Clusters

| Fill Date | Signal Dates | n Signals | Reason |
|-----------|------------|-----------|--------|
| Oct 12 | Oct 09-11 | 107 | v6.0 model (EXCLUDED_V60) |
| Oct 21 | Oct 16 | 39 | fill Oct 21 incomplete exit data (INCOMPLETE_EXIT) |

## 3. Statistical Results — Strict (N=3)

**D_v3 vs A_direct:**
- Cluster deltas: [+1.20%, +2.76%, −1.52%]
- Grand mean: **+0.81%**
- 95% CI: approximately [−1.4%, +3.0%]
- p-value: ≈ 0.37
- Verdict: **SIGNIFICANCE_INCONCLUSIVE**

**D_v3 vs B_v1v2:**
- Cluster deltas: [+0.84%, +0.14%, −1.41%]
- Grand mean: **−0.14%**
- Verdict: **SIGNIFICANCE_INCONCLUSIVE**

**D_v3 vs C_hybrid:**
- Cluster deltas: [+1.07%, +2.76%, −1.49%]
- Grand mean: **+1.11%**
- Verdict: **SIGNIFICANCE_INCONCLUSIVE**

## 4. Cross-Session Comparison

| Session | Clusters | Grand Mean (vs A) | Verdict |
|---------|----------|-------------------|---------|
| S40 | Signal-level (all) | +3.66% | SIGNIFICANT_POSITIVE (now retracted) |
| S41 | 7 signal-date clusters | +6.49% | SIGNIFICANT_POSITIVE (now retracted) |
| S42 | 5 fill-date clusters (mixed v6.0+v8.0) | +1.21% | SIGNIFICANCE_INCONCLUSIVE |
| S43 strict | 3 fill-date clusters (v8.0 only) | +0.81% | SIGNIFICANCE_INCONCLUSIVE |

**Trend**: Each correction reduces the apparent advantage. The residual +0.81% with CI [-1.4%, +3.0%] is not distinguishable from zero.

## 5. Why fill Oct 12 Inflated S42 Results

The fill Oct 12 cluster (v6.0 signals, Oct 09-11) had a delta of +2.62% vs A_direct. Including this cluster in S42's grand mean pulled the mean from +0.81% (strict) to +1.21% (mixed). The v6.0 signals represent a different model and different market conditions — their inclusion in a v8.0 performance analysis is a category error.

## 6. Interpretation

The strict v8.0 analysis shows D_v3 performing slightly better than A_direct (+0.81%) on average across 3 clusters, but:
- The 95% confidence interval crosses zero
- N=3 clusters is insufficient for statistical inference
- Adjacent clusters overlap 80% (G04 FAIL), violating independence
- No historical data exists to validate out-of-sample

**Current conclusion: insufficient evidence to claim V3 outperforms A_direct.**
