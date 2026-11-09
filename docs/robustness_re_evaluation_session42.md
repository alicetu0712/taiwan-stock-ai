# Robustness Re-Evaluation — Session 42

**Date:** 2026-11-09
**Session:** 42
**Verdict:** DIRECTIONALLY_STABLE but EVIDENCE_WEAK (re-confirmed, corrected magnitude)

---

## 1. Leave-One-Cluster-Out (LOCO) Analysis — S42

Using 5 fill-date clusters (not 7 signal-date clusters as in S41 LODO):

| Dropped Cluster | Dropped n | Remaining N | LOCO Grand Mean | 95% CI | Sign Change? |
|---|---|---|---|---|---|
| fill Oct 12 (non-TD) | 107 | 4 | +1.19% | [-0.64%, +3.02%] | No |
| fill Oct 13 | 46 | 4 | +1.22% | [-2.37%, +4.82%] | No |
| fill Oct 14 | 27 | 4 | +0.74% | [-1.14%, +2.62%] | No |
| fill Oct 16 | 55 | 4 | +1.68% | [-0.03%, +3.39%] | No |
| fill Oct 21 | 39 | 4 | +1.26% | [-1.19%, +3.72%] | No |

**Sign changes: 0/5 → DIRECTIONALLY_STABLE**  
All CIs include zero (or barely touch 0) → never statistically significant.

---

## 2. Comparison: S41 LODO vs S42 LOCO

| Analysis | Clusters | LODO/LOCO Grand Mean Range | Sign Changes |
|---|---|---|---|
| S41 LODO (7 signal-date) | 7 | 2.45% to 7.83% (3.4× spread) | 0/7 |
| **S42 LOCO (5 fill-date)** | 5 | 0.74% to 1.68% (2.3× spread) | 0/5 |

**S42 shows narrower magnitude range** (better stability) compared to S41, because the micro-cluster inflation is removed. The grand mean is now consistently in the 0.7-1.7% range.

---

## 3. Transaction Cost Sensitivity

| Scenario | FEES_PCT | Direction Change? |
|---|---|---|
| Zero fees | 0.0% | No (grand mean ~1.80%) |
| Base fees | 0.585% | Reference (+1.21%) |
| Double fees | 1.17% | No (grand mean ~0.62%) |

Direction remains positive under double fees. However CI includes zero at all fee assumptions.

---

## 4. Non-Trading Signal Sensitivity

| Dataset | n | Grand Mean D_v3 vs A | Verdict |
|---|---|---|---|
| All signals (5 fill clusters) | 274 | +1.21% | INCONCLUSIVE |
| Trading-day signals only (4 clusters) | 167 | +0.86% | INCONCLUSIVE |
| Trading-day only, cluster 3 dropped | 3 | +0.75% | INSUFFICIENT_DATA |

Excluding non-trading signals reduces the grand mean to +0.86% and cluster count to 4. Direction remains positive but further weakens evidence.

---

## 5. Verdict

```
ROBUSTNESS = "DIRECTIONALLY_STABLE"
# Sign never changes in LOCO (0/5)
# Magnitude stable (0.74% to 1.68%, narrower than S41)
# Statistical significance: never significant (all CIs include zero)
# Key improvement over S41: micro-cluster inflation removed
```
