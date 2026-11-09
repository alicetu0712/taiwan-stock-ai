# Corrected 5D Comparison — Session 42

**Date:** 2026-11-09
**Session:** 42
**Verdict:** ALL_COMPARISONS_SIGNIFICANCE_INCONCLUSIVE

---

## 1. Corrections Applied

| Correction | Description | Effect |
|---|---|---|
| Non-trading signals | Oct 09+10+11 merged into fill Oct 12 | 7 → 5 clusters |
| Fill-date clustering | execution_date as observation unit | Removes micro-cluster inflation |
| Benchmark alignment | 0050 from actual fill dates | -4.65% → -2.16% |

---

## 2. Fill-Date Cluster Deltas (D_v3 vs A_direct)

| Fill Date | Signal Dates | n | D_v3 delta |
|---|---|---|---|
| 2026-10-12 | Oct 09, 10, 11 (non-trading) | 107 | **+2.62%** |
| 2026-10-13 | Oct 12 | 46 | +1.20% |
| 2026-10-14 | Oct 13 | 27 | +2.76% |
| 2026-10-16 | Oct 14 | 55 | **-1.52%** |
| 2026-10-21 | Oct 16 | 39 | +0.99% |
| **Grand mean (N=5)** | | **274** | **+1.21%** |

**CI (95%):** [-0.93%, +3.35%] — includes zero  
**t-statistic:** 1.57, **p-value:** 0.191  
**Verdict:** SIGNIFICANCE_INCONCLUSIVE

---

## 3. All Three Comparisons

| Comparator | N | Grand Mean | CI 95% | p-value | Verdict |
|---|---|---|---|---|---|
| A_direct (V1 sim) | 5 | **+1.21%** | [-0.93%, +3.35%] | 0.191 | SIGNIFICANCE_INCONCLUSIVE |
| B_v1v2 | 5 | **+0.32%** | [-2.59%, +3.24%] | 0.773 | SIGNIFICANCE_INCONCLUSIVE |
| C_hybrid (Hybrid V1) | 5 | **+1.19%** | [-0.91%, +3.29%] | 0.191 | SIGNIFICANCE_INCONCLUSIVE |

**D vs B_v1v2 is nearly zero (+0.32%, p=0.77)** — V3 barely outperforms V1/V2 hybrid when measured at the fill-date cluster level.

---

## 4. Trading-Day-Only Sensitivity (N=4)

Excluding the Oct 12 cluster (which absorbs non-trading signals):

| Comparator | N | Grand Mean | CI 95% | p-value | Verdict |
|---|---|---|---|---|---|
| A_direct | 4 | +0.86% | [-1.96%, +3.68%] | 0.40 | SIGNIFICANCE_INCONCLUSIVE |

Removing the non-trading cluster further weakens the evidence.

---

## 5. Comparison Across Sessions

| Session | Method | D_v3 vs A_direct Grand Mean | CI | Includes Zero? |
|---|---|---|---|---|
| S40 | Signal-level paired mean | +3.66% | Bootstrap [-0.3%, +7.5%] (uncorrected) | No → SIGNIFICANT_POSITIVE ❌ |
| S41 | 7 signal-date clusters, t-test df=6 | +6.49% | [-3.95%, +16.93%] | Yes → INCONCLUSIVE ✓ |
| **S42** | **5 fill-date clusters, t-test df=4** | **+1.21%** | **[-0.93%, +3.35%]** | **Yes → INCONCLUSIVE ✓** |

**Key insight:** The S41 correction over-corrected because micro-clusters (Oct 10, Oct 11, n=4 each) with extreme returns (+10%, +30%) inflated the cluster grand mean to +6.49%. The S42 fill-date correction removes this by merging them into the Oct 12 cluster, reducing the grand mean to its true value of +1.21%.

---

## 6. Verdict

```
ALL_COMPARISONS_SIGNIFICANCE_INCONCLUSIVE
D_v3 grand mean vs A_direct: +1.21% (↓ from +6.49% in S41)
D_v3 grand mean vs B_v1v2:  +0.32% (essentially zero evidence)
D_v3 grand mean vs C_hybrid: +1.19%
All CIs include zero; all p-values > 0.19
S40 SIGNIFICANT_POSITIVE formally retracted (confirmed from S41 + strengthened in S42)
```
