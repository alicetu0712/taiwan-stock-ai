# Observation Cluster Reconstruction — Session 42

**Date:** 2026-11-09
**Session:** 42
**Verdict:** OBSERVATION_UNIT_CORRECTED (5 fill-date clusters, N=5, effective N≤2)

---

## 1. The Problem: Signal-Date vs Fill-Date Clustering

Session 41 clustered by `trade_date` (signal date), yielding 7 clusters:
- Treated Oct 09, Oct 10, Oct 11 as separate independent clusters
- Two clusters had n=4 each (Oct 10, Oct 11) — micro-clusters from non-trading days
- These micro-clusters had extreme returns (+10%, +30%), inflating the grand mean

The correct observation unit for financial research is the **fill date** (when the trade is executed). Signals on different dates that all fill on the same day are NOT independent.

---

## 2. Fill-Date Cluster Construction

Using `forward_signals.execution_date` as the fill date (NULL for non-trading-day signals → computed as next trading day from `daily_prices`):

| Fill Date | Signal Date(s) | n Signals | Contains Non-TD? | 5D Window | Overlaps Next? |
|---|---|---|---|---|---|
| 2026-10-12 | Oct 09, 10, 11 | **107** | **Yes** | Oct 12 → Oct 16 | Yes (+4 days) |
| 2026-10-13 | Oct 12 | 46 | No | Oct 13 → Oct 19 | Yes (+6 days) |
| 2026-10-14 | Oct 13 | 27 | No | Oct 14 → Oct 20 | Yes (+5 days) |
| 2026-10-16 | Oct 14 | 55 | No | Oct 16 → Oct 22 | Yes (+2 days) |
| 2026-10-21 | Oct 16 | 39 | No | Oct 21 → Oct 29 | No |

**Total: 5 clusters, 274 signals.**

---

## 3. Cluster Count Reduction

| Method | Clusters | Micro-Clusters | Grand Mean D_v3 vs A |
|---|---|---|---|
| S40 (signal-level, no clustering) | — | — | +3.66% |
| S41 (signal-date clustering) | **7** | 2 (Oct 10, Oct 11) | +6.49% |
| **S42 (fill-date clustering)** | **5** | 0 | **+1.21%** |

---

## 4. Overlapping Windows Problem

All 4 adjacent cluster pairs have overlapping 5D holding windows:

| Pair | Overlap (calendar days) |
|---|---|
| Oct 12–16 ∩ Oct 13–19 | 4 days (Oct 13–16) |
| Oct 13–19 ∩ Oct 14–20 | 6 days (Oct 14–19) |
| Oct 14–20 ∩ Oct 16–22 | 5 days (Oct 16–20) |
| Oct 16–22 ∩ Oct 21–29 | 2 days (Oct 21–22) |

**4 out of 4 adjacent pairs overlap.** The 5 "clusters" are not independent. Effective independent N is pessimistically estimated at 1–2.

This means the t-test with df=4 (n=5 clusters) **overstates** statistical power. The true p-value from independent data would be even higher than the reported p=0.191.

---

## 5. Recommendation

For future comparisons, use **non-overlapping evaluation windows** (e.g., 20D horizon with monthly batching). With 5D horizon and near-daily signals, overlapping windows are unavoidable unless signals are sampled ≥5 trading days apart.

---

## 6. Verdict

```
OBSERVATION_UNIT_CORRECTED
N_clusters_signal_date = 7 (S41)
N_clusters_fill_date   = 5 (S42)
N_overlapping_pairs    = 4/4
Effective_independent_N = 1-2 (pessimistic)
```
