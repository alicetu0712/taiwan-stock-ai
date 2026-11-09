# Statistical Guardrails G03/G04 — Session 49 Update

**Date:** 2026-11-09  
**Session:** S49 — PART H (P7)  
**Verdict:** BOTH_FAIL (G03 + G04 — unchanged from S48)

---

## Status Summary

| Guardrail | Requirement | Current | After P1 Backfill | Status |
|---|---|---|---|---|
| G03 | ≥ 10 strict clusters | 3 | 6 | **FAIL** |
| G04 | Adjacent overlap < 30% | 80% max | 80% max (unchanged) | **FAIL** |

No change from S48. G03 and G04 failures are confirmed as structural/design issues, not data issues.

---

## G03: Insufficient Cluster Count

**Requirement:** ≥ 10 independent strict clusters  
**Current:** 3 strict clusters  
**After P1 backfill:** 6 strict clusters  
**Still needed:** 4+ additional weeks of fill data after backfill

| Scenario | N | G03 |
|---|---|---|
| Now (no backfill) | 3 | FAIL (need 7 more) |
| After P1 backfill | 6 | FAIL (need 4 more) |
| After 4+ more weeks | 10+ | PASS (possible) |
| With 20D data | Still 6 | FAIL (20D doesn't add clusters) |

**G03 is a time/data problem.** Only accumulating more fill dates (weeks of trading) resolves it.

---

## G04: Adjacent Window Overlap

**Requirement:** Adjacent cluster windows have < 30% overlap  
**Formula:** `overlap_pct = |window_A ∩ window_B| / window_size × 100`  
**Current:** 80% max (Oct 13/14 and Oct 21/22 pairs)

### Pairwise Overlap Matrix (All 15 Pairs, 6 Clusters)

| Fill A | Fill B | Shared Days | Overlap % | Adjacent | > 30%? |
|---|---|---|---|---|---|
| Oct 13 | Oct 14 | 4 | **80%** | Yes | FAIL |
| Oct 13 | Oct 16 | 2 | 40% | No | — |
| Oct 13 | Oct 21 | 0 | 0% | No | — |
| Oct 13 | Oct 22 | 0 | 0% | No | — |
| Oct 13 | Oct 28 | 0 | 0% | No | — |
| Oct 14 | Oct 16 | 3 | **60%** | Yes | FAIL |
| Oct 14 | Oct 21 | 0 | 0% | No | — |
| Oct 14 | Oct 22 | 0 | 0% | No | — |
| Oct 14 | Oct 28 | 0 | 0% | No | — |
| Oct 16 | Oct 21 | 2 | **40%** | Yes | FAIL |
| Oct 16 | Oct 22 | 1 | 20% | No | — |
| Oct 16 | Oct 28 | 0 | 0% | No | — |
| Oct 21 | Oct 22 | 4 | **80%** | Yes | FAIL |
| Oct 21 | Oct 28 | 2 | 40% | No | — |
| Oct 22 | Oct 28 | 3 | **60%** | Yes | FAIL |

**All 5 adjacent pairs exceed 30% threshold.**

---

## G04 Is a Design Problem

Adding Oct 21/22/28 clusters via backfill does NOT improve G04. The adjacent-pair overlap is determined by the spacing between consecutive fill dates, which is daily-frequency (1–2 days apart). This creates 5-day windows that inherently overlap.

### Remediation Options (Requires Design Decision)

| Option | G03 Impact | G04 Impact | Trade-off |
|---|---|---|---|
| Weekly-spaced fills | Slower accumulation | G04 ≈ 0% | Loses data resolution |
| Bootstrap CI | No change | Acceptable if N≥10 | Need G03 fix first |
| Universe sector rotation | No change | Partial reduction | Complex implementation |
| Accept and document | No change | No change | Statistical caveat only |

No design decision authorized in S49.

---

## Effective Sample Size (With G04 Failure)

If adjacent pairwise correlation r ≈ 0.8 (from 80% overlap):

**N=3:** effective N ≈ 3 / (1 + 2×0.8) ≈ 1.15  
**N=6:** effective N ≈ 6 / (1 + 5×0.8) ≈ 1.09 (worse relative efficiency)

Treating N=3 or N=6 as independent observations overstates statistical power. The t-test p-value of 0.58 (from S41) already does not support significance claims; with the corrected effective N, the result is even more inconclusive.

---

## Conclusion

G03 and G04 are unresolved fundamental constraints. Even with 20D data and after P1 backfill:
- Statistical verdict: **SIGNIFICANCE_INCONCLUSIVE (unchanged)**
- Activation: **ACTIVATION_BLOCKED (unchanged)**
