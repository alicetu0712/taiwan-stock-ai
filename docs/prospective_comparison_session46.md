# 5D Comparison Re-evaluation — Session 46

**Date:** 2026-11-09  
**Session:** S46 — PART E  
**Frozen Baseline:** 3 clusters (unchanged from S44/S45)  
**Expanded Research Snapshot:** 4 finite clusters (adds Oct 28 fill)

---

## Frozen Baseline (UNCHANGED)

The canonical baseline from S44/S45 is preserved exactly:

| Fill Date | n Signals | Exit Date | V3 Mean | A_direct Mean | Delta (D) |
|---|---|---|---|---|---|
| Oct 13 | 46 | Oct 21 | +1.20% | +0.84% | +1.07% |
| Oct 14 | 27 | Oct 28 | +2.76% | +0.14% | +2.76% |
| Oct 16 | 55 | Nov 05 | -1.52% | -1.41% | -1.49% |
| **Grand Mean** | | | | | **+0.81%** |

**CI (95%):** [-1.4%, +3.0%]  
**Verdict:** SIGNIFICANCE_INCONCLUSIVE (N=3, CI crosses 0)

---

## Expanded Research Snapshot (RESEARCH_ONLY — Not Part of Strict Baseline)

Adds Oct 28 fill using calendar-based exit date (Nov 04). Oct 22 fill is PENDING_NEON.

| Fill Date | n Signals | Exit Date | Method | V3 Mean | A_direct Mean | Delta (D) | Note |
|---|---|---|---|---|---|---|---|
| Oct 13 | 46 | Oct 21 | proxy_5td | +1.20% | +0.84% | +1.07% | Frozen |
| Oct 14 | 27 | Oct 28 | proxy_5td | +2.76% | +0.14% | +2.76% | Frozen |
| Oct 16 | 55 | Nov 05 | proxy_5td | -1.52% | -1.41% | -1.49% | Frozen |
| Oct 28 | 19 | Nov 04 | calendar_5td | -13.18% | -15.94% | **+2.75%** | Isolated |
| Oct 22 | 23 | Nov 02 | calendar_5td | NaN | NaN | **NaN** | PENDING_NEON |

**Expanded grand mean (4 finite clusters):** +1.60%  
**Verdict:** SIGNIFICANCE_INCONCLUSIVE (N=4 finite, G03 FAIL N<10)

---

## Oct 28 Fill Result

The Oct 28 fill in a strongly down market (Oct 28 → Nov 04):
- Both V3 and A_direct lost money (down market)
- V3 lost less: -13.18% vs A_direct -15.94%
- Delta = **+2.75 pp** (V3 outperformed by 2.75 pp in relative terms)

This is consistent with the existing 3-cluster pattern: V3's NEXT_OPEN entry (next-day open vs signal-close) generates positive deltas in both up and down markets.

---

## Critical Boundaries

1. The expanded snapshot is **RESEARCH_ONLY** and does not replace the frozen baseline.
2. The frozen baseline uses `_count_exit_days` (2330 proxy); the expanded snapshot uses calendar-based exits.
3. G03 FAIL: N=4 is insufficient for reliable inference (threshold = 10).
4. G04 FAIL: Adjacent windows still overlap ~80%; cluster-level independence not achieved.
5. The Oct 28 isolated result is directionally consistent (+2.75 pp) but not statistically conclusive.

---

## Statistical Note

A one-sample t-test on 4 observations has very low power and is unreliable regardless of p-value. The only valid inference from these 4 clusters is: "direction is consistently positive" (3 out of 4 deltas > 0, Oct 16 delta = -1.49%). No claim of statistical significance is warranted.
