# V3 Robustness & Sensitivity Analysis — Session 41

**Date:** 2026-11-09
**Session:** 41
**Verdict:** DIRECTIONALLY_STABLE (CI always includes zero in LODO)

---

## 1. Leave-One-Date-Out (LODO) Analysis

For each of the 7 trading dates, drop that date and recompute the cluster-corrected analysis.

| Dropped Date | Dropped N | Remaining Dates | LODO Grand Mean | CI | Sign Change? |
|---|---|---|---|---|---|
| 2026-10-09 | 99 | 6 | +7.38% | [-5.32%, +20.08%] | No |
| 2026-10-10 | 4 | 6 | +5.89% | [-6.96%, +18.74%] | No |
| 2026-10-11 | 4 | 6 | +2.45% | [-1.73%, +6.64%] | No |
| 2026-10-12 | 46 | 6 | +7.37% | [-5.33%, +20.07%] | No |
| 2026-10-13 | 27 | 6 | +7.11% | [-5.73%, +19.96%] | No |
| 2026-10-14 | 55 | 6 | +7.83% | [-4.50%, +20.16%] | No |
| 2026-10-16 | 39 | 6 | +7.41% | [-5.27%, +20.09%] | No |

**Sign changes: 0/7 → DIRECTIONALLY_STABLE**

**But:** All 7 LODO CIs include zero → NOT statistically significant in any LODO scenario.

### Key Observation
Dropping Oct 11 (the micro-cluster with +30.73% mean delta) reduces the grand mean from 6.49% to **2.45%** — the smallest remaining LODO mean. This is the most influential date.

The LODO grand mean range is 2.45% to 7.83% — a 3.4× spread. This indicates **high instability in magnitude** even though the direction is stable.

---

## 2. Micro-Cluster Sensitivity

Impact of excluding Oct 10 and Oct 11 (non-trading day signals, n=4 each):

| Dataset | Dates | Grand Mean | t-stat | p-value |
|---|---|---|---|---|
| Full (7 dates) | Oct 09-16 | +6.49% | 1.52 | 0.179 |
| Without Oct 10&11 (5 dates) | Oct 09, 12, 13, 14, 16 | +1.12% | ~1.4 | ~0.23 |

**Without the non-trading-day micro-clusters, grand mean drops from 6.49% to 1.12%.**

This further confirms SIGNIFICANCE_INCONCLUSIVE — the apparent positive direction is partially driven by 8 signals (4+4) on days when Taiwan markets were closed.

---

## 3. Transaction Cost Sensitivity

| Scenario | FEES_PCT | D_v3 paired delta | Direction |
|---|---|---|---|
| Zero fees | 0.0% | Signal-level mean + 0.585% | Still positive |
| Base fees | 0.585% | +3.66% (signal-level) | Positive |
| Double fees | 1.17% | Base delta - 0.585% | Still positive |

Transaction cost doubling does not reverse the direction of the signal-level paired analysis. However, the cluster-corrected CI remains wide and includes zero regardless of fee assumption.

---

## 4. Dataset Sensitivity

| Dataset | Coverage | Expected Impact |
|---|---|---|
| Dataset A (all signals) | v8.0 + v6.0, includes ETFs | Current dataset used |
| Dataset B (v8.0 TWSE common only) | Removes 213 ETFs, 9.52% | Would reduce n from 274; uncertain direction |
| Dataset C (pure TWSE common, no UNKNOWN) | Stricter than B | Further reduced n |

V6.0 signals (included in current dataset) may behave differently from v8.0 signals. Filtering to v8.0 only would change results but direction is not predictable.

**Status:** Dataset sensitivity cannot be computed in-session without re-running V3ComparisonEngine with filtered signal pool.

---

## 5. Verdict Summary

| Dimension | Finding |
|---|---|
| Sign stability | DIRECTIONALLY_STABLE (never changes in LODO) |
| Statistical significance | NEVER SIGNIFICANT (CI includes zero in all LODO) |
| Magnitude stability | UNSTABLE (2.45% to 7.83% range in LODO grand means) |
| Micro-cluster sensitivity | MATERIAL (grand mean halves without Oct 10&11) |
| Tx cost sensitivity | STABLE direction, CI unchanged |
| Dataset sensitivity | NOT COMPUTED |
| **Overall** | **DIRECTIONALLY_STABLE but EVIDENCE_WEAK** |

The robustness analysis is **not reassuring**: while direction never flips, the wide CI and micro-cluster sensitivity confirm that the current 7-date dataset is insufficient to draw firm conclusions.
