# Statistical Guardrails G03/G04 — Session 48

**Date:** 2026-11-09  
**Session:** S48 — PART G (P6)  
**Verdict:** BOTH_FAIL (G03 FAIL + G04 FAIL; unchanged from S47)

---

## G03: Insufficient Cluster Count

**Requirement:** ≥ 10 strict clusters for reliable t-test  
**Current:** 3 strict clusters  
**Status:** FAIL

| Metric | Value |
|---|---|
| Strict clusters | 3 |
| Target | 10 |
| Deficit | 7 |
| Recovery path | Pipeline restoration + ~7–8 weeks consecutive data |

If Oct 21/22/28 fills are promoted (via backfill of Oct 29/30/Nov 02/03):
- Strict count → 6
- G03 still FAIL (need 10)
- Recovery still requires 4+ additional weeks of fill data

---

## G04: Adjacent Window Overlap

**Requirement:** Adjacent cluster windows have < 30% overlap  
**Formula:** `overlap_pct = |window_A ∩ window_B| / window_size × 100`  
**Where:** `window_size = 5` (denominator, not Jaccard union)  
**Status:** FAIL — ALL 5 adjacent pairs exceed 30%

---

## Full Pairwise Overlap Matrix (All 15 Pairs)

| Fill A | Fill B | Shared Days | Overlap % | Adjacent? | Exceeds 30% |
|---|---|---|---|---|---|
| Oct 13 | Oct 14 | 4 | **80%** | Yes | ✗ FAIL |
| Oct 13 | Oct 16 | 2 | 40% | No | — |
| Oct 13 | Oct 21 | 0 | 0% | No | — |
| Oct 13 | Oct 22 | 0 | 0% | No | — |
| Oct 13 | Oct 28 | 0 | 0% | No | — |
| Oct 14 | Oct 16 | 3 | **60%** | Yes | ✗ FAIL |
| Oct 14 | Oct 21 | 0 | 0% | No | — |
| Oct 14 | Oct 22 | 0 | 0% | No | — |
| Oct 14 | Oct 28 | 0 | 0% | No | — |
| Oct 16 | Oct 21 | 2 | **40%** | Yes | ✗ FAIL |
| Oct 16 | Oct 22 | 1 | 20% | No | — |
| Oct 16 | Oct 28 | 0 | 0% | No | — |
| Oct 21 | Oct 22 | 4 | **80%** | Yes | ✗ FAIL |
| Oct 21 | Oct 28 | 2 | 40% | No | — |
| Oct 22 | Oct 28 | 3 | **60%** | Yes | ✗ FAIL |

**Maximum overlap:** 80% (Oct 13/Oct 14 pair and Oct 21/Oct 22 pair)

---

## G03 vs G04: Different Failure Modes

| Guardrail | Failure Type | Root Cause | Remediation |
|---|---|---|---|
| G03 | Insufficient power | Too few clusters | More data (time + pipeline restoration) |
| G04 | Correlation between samples | Daily fills share trading days | Design change required |

Fixing G03 (more clusters) does NOT fix G04. Daily-frequency fills inherently produce adjacent windows that overlap. G04 is a research design issue.

---

## G04 Remediation Options (Design Level — Not Authorized in S48)

| Option | Description | G03 Impact | G04 Impact |
|---|---|---|---|
| Weekly-spaced fills | Only use 1 fill per week (5-TD gap between fills) | Slower to reach 10 clusters | G04 ≈ 0% — windows don't overlap |
| Universe sector rotation | Alternate sectors per fill date | Same cluster count | Partial — different stocks reduce correlation |
| Bootstrap CI | Model correlation structure explicitly | No change | Acceptable if N≥10 (need G03 fix first) |
| Regime conditioning | Cluster by market regime | Same | Reduces spurious correlation |

**Decision required:** Which design path to pursue. No implementation in S48.

---

## Why This Matters for Statistical Inference

With 3 strict clusters at 80% adjacent overlap:

**Effective N calculation:**
- N=3 clusters, pairwise correlation ≈ r due to shared sessions
- If r ≈ 0.8 (from 80% overlap), effective N ≈ N / (1 + (N-1)×r) ≈ 3 / (1 + 2×0.8) ≈ 1.15
- Standard t-test treating N=3 as 3 independent observations overstates statistical power by ~2.6×

The t-test p-value of 0.58 (SIGNIFICANCE_INCONCLUSIVE) already does not support any claim. With the corrected effective N ~1.15, the result is even less informative.

**Bottom line:** G03 and G04 failures mean the current dataset cannot support statistical conclusions about V3 vs A_direct. This is a fundamental constraint, not an engineering fix.
