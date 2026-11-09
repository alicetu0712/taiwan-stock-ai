# G04 Overlap Analysis — Session 47

**Date:** 2026-11-09  
**Session:** S47 — PART G (P6)  
**G04 Status:** FAIL (unchanged)

---

## G04 Official Definition

G04 requires that adjacent 5D holding windows have < 30% overlap.

**Formula:**
```
overlap_pct(A, B) = |window_A ∩ window_B| / window_size × 100
```

Where:
- `window_A`, `window_B` = sets of 5 actual trading days in each cluster's hold period
- `window_size` = 5 (holding sessions per cluster)
- `∩` = intersection (shared trading days)

This formula divides by `window_size` (not by union size, which would be Jaccard similarity). The 30% threshold = ≤1.5 shared days out of 5.

---

## Full Overlap Matrix (All Pairs)

| Fill A | Fill B | A Window | B Window | Shared Days | Overlap % | Adjacent? |
|---|---|---|---|---|---|---|
| Oct 13 | Oct 14 | Oct 14–20 | Oct 15–21 | Oct 15/16/19/20 | **80%** | Yes |
| Oct 13 | Oct 16 | Oct 14–20 | Oct 19–27 | Oct 19/20 | 40% | No |
| Oct 13 | Oct 21 | Oct 14–20 | Oct 22–30 | — | 0% | No |
| Oct 13 | Oct 22 | Oct 14–20 | Oct 27–Nov02 | — | 0% | No |
| Oct 13 | Oct 28 | Oct 14–20 | Oct 29–Nov04 | — | 0% | No |
| Oct 14 | Oct 16 | Oct 15–21 | Oct 19–27 | Oct 19/20/21 | **60%** | Yes |
| Oct 14 | Oct 21 | Oct 15–21 | Oct 22–30 | — | 0% | No |
| Oct 14 | Oct 22 | Oct 15–21 | Oct 27–Nov02 | — | 0% | No |
| Oct 14 | Oct 28 | Oct 15–21 | Oct 29–Nov04 | — | 0% | No |
| Oct 16 | Oct 21 | Oct 19–27 | Oct 22–30 | Oct 22/27 | **40%** | Yes |
| Oct 16 | Oct 22 | Oct 19–27 | Oct 27–Nov02 | Oct 27 | 20% | No |
| Oct 16 | Oct 28 | Oct 19–27 | Oct 29–Nov04 | — | 0% | No |
| Oct 21 | Oct 22 | Oct 22–30 | Oct 27–Nov02 | Oct 27/28/29/30 | **80%** | Yes |
| Oct 21 | Oct 28 | Oct 22–30 | Oct 29–Nov04 | Oct 29/30 | 40% | No |
| Oct 22 | Oct 28 | Oct 27–Nov02 | Oct 29–Nov04 | Oct 29/30/Nov02 | **60%** | Yes |

**Window notation:** "Oct 14–20" = {Oct 14, Oct 15, Oct 16, Oct 19, Oct 20} (5 real TDs)

---

## Adjacent Pair Summary

| Adjacent Pair | Overlap % | Exceeds 30% Threshold |
|---|---|---|
| Oct 13 / Oct 14 | 80% | ✗ FAIL |
| Oct 14 / Oct 16 | 60% | ✗ FAIL |
| Oct 16 / Oct 21 | 40% | ✗ FAIL |
| Oct 21 / Oct 22 | 80% | ✗ FAIL |
| Oct 22 / Oct 28 | 60% | ✗ FAIL |

**ALL adjacent pairs exceed the 30% threshold.** G04 FAIL confirmed.

---

## Why This Matters for Statistical Inference

G04 failure means the t-test assumption of independence is violated:

1. **Shared sessions = shared risk:** If a macro event (e.g., Fed announcement, Taiwan Strait news) occurs during Oct 15/16/19/20 (shared by Oct 13 and Oct 14 fills), both cluster returns move in the same direction. They are NOT independent observations.

2. **Effective sample size:** 3 clusters with 80% adjacent overlap have an effective N closer to 1.5–2, not 3. Standard t-test treating them as N=3 overstates statistical power.

3. **Delta correlation:** V3 − A_direct delta for adjacent clusters will be positively correlated. Any regime-level alpha captured by V3 would appear in both Oct 13 and Oct 14 results simultaneously.

---

## G04 and G03 Are Distinct Blockers

| Guardrail | Requirement | Current | Status |
|---|---|---|---|
| G03 | ≥10 strict clusters | 3 | FAIL — insufficient power |
| G04 | <30% adjacent overlap | 40–80% | FAIL — independence violated |

They measure different risks:
- G03: insufficient absolute sample size
- G04: correlation between existing samples reduces effective sample size further

Fixing G03 (more clusters) does NOT fix G04 (the overlap pattern persists with daily fills).

---

## G04 Remediation Options (Design Level)

| Option | Description | Tradeoff |
|---|---|---|
| Weekly-spaced fills | Only use one fill per week (5 TD separation) | Loses data efficiency; 20 weeks to reach 20 clusters |
| Non-overlapping universe rotation | Split universe by sector; alternate sectors per fill | Requires redesign; reduces per-cluster N |
| Bootstrap CI on cluster means | Model correlation explicitly in inference | Acceptable for N≥10; still need G03 first |
| Regime-conditioned clustering | Group by market regime; test within regime | Research design decision required |

**No design change authorized in S47. G04 FAIL unchanged.**
