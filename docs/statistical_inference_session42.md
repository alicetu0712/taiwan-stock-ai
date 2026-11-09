# Statistical Inference Report — Session 42

**Date:** 2026-11-09
**Session:** 42
**Verdict:** SIGNIFICANCE_INCONCLUSIVE (all comparisons, all corrections)

---

## 1. The Statistical Problem

The V3 5D comparison uses returns from a 3-week window in October 2026. The fundamental inference challenge:

1. **Small N**: 5 fill-date clusters (not 274 independent signals)
2. **Overlapping windows**: 4/4 adjacent cluster windows overlap → effective N < 5
3. **Non-trading day contamination**: 107/274 signals from non-trading days
4. **Single regime**: One market environment (Taiwan market decline)
5. **Correlated outcomes**: All clusters share exposure to the same macro factor

---

## 2. Cluster-Corrected t-Test Results

For D_v3 vs A_direct (5 fill-date cluster means):
```
Cluster deltas: [+2.62%, +1.20%, +2.76%, -1.52%, +0.99%]
Grand mean: +1.21%
Std dev: 1.59%
SE: 0.71%
t-statistic: 1.57
df: 4
p-value (two-tailed): 0.191
95% CI: [-0.93%, +3.35%]
Verdict: SIGNIFICANCE_INCONCLUSIVE
```

---

## 3. What Would Statistical Power Require?

To detect a true effect of +1.21% with 80% power (α=0.05, two-tailed):
- With σ=1.59% (observed): need N ≈ 23 independent clusters
- At current pace (~19 trading days/month → 5 clusters/month): ~4-5 more months
- Assuming similar volatility and no regime shift

---

## 4. Overlapping Window Correction

The 5 fill-date clusters have overlapping 5D windows (see `docs/observation_cluster_reconstruction_session42.md`). With maximum overlap between adjacent clusters, the effective N for a simple t-test is as low as 2.

**Implication:** The reported p=0.191 is OPTIMISTIC. A HAC-corrected (Newey-West) test with appropriate lag structure would yield a higher p-value.

---

## 5. What SIGNIFICANCE_INCONCLUSIVE Does Not Mean

It does NOT mean:
- V3 is definitely not better than V1/V2 (the direction is consistently positive)
- The strategy should be abandoned
- S41/S42 results contradict each other

It DOES mean:
- With the current data, we cannot distinguish "V3 is +1.21% better" from "V3 is 0% better" with standard confidence
- Activation based on this evidence would be a premature decision
- More data is required

---

## 6. Required Conditions for Upgrading to SIGNIFICANCE_CONDITIONAL

1. ≥10 fill-date clusters (at current pace: ~2 more months)
2. CI lower bound > 0 (effect distinguishable from zero)
3. At least 1 non-overlapping evaluation window pair
4. p < 0.05 for at least 2 of 3 comparators

---

## 7. Verdict Summary

| Comparator | p-value | 95% CI | Verdict |
|---|---|---|---|
| D_v3 vs A_direct | 0.191 | [-0.93%, +3.35%] | SIGNIFICANCE_INCONCLUSIVE |
| D_v3 vs B_v1v2 | 0.773 | [-2.59%, +3.24%] | SIGNIFICANCE_INCONCLUSIVE |
| D_v3 vs C_hybrid | 0.191 | [-0.91%, +3.29%] | SIGNIFICANCE_INCONCLUSIVE |
| Trading-day-only (D vs A) | 0.403 | [-1.96%, +3.68%] | SIGNIFICANCE_INCONCLUSIVE |

```
STATISTICAL_VERDICT = "SIGNIFICANCE_INCONCLUSIVE"
# All CI bounds include zero
# S40 SIGNIFICANT_POSITIVE formally retracted (S41) and confirmed retracted (S42)
# V3 activation must not proceed on these grounds
```
