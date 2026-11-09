# Canonical 5D Baseline — Session 44

**Date:** 2026-11-09  
**Session:** S44  
**Module:** `src/research/canonical_5d_baseline_s44.py`  
**Baseline ID:** S44-5D-STRICT-V1

---

## Purpose

Establishes the canonical 5-day performance baseline for V3 vs A/B/C comparisons. Extends S43 scope (Oct 09–16 signals) to the full v8.0 signal range (Oct 09–28 signals).

---

## Full v8.0 Fill-Date Cluster Inventory

| Fill Date | Signal Date(s) | Model Ver | n Signals | 5D Exit Days | Status |
|---|---|---|---|---|---|
| Oct 12 | Oct 09–11 | v6.0 | 107 | — | EXCLUDED_V60 |
| Oct 13 | Oct 12 | v8.0 | 46 | 5/5 | **COMPLETE** |
| Oct 14 | Oct 13 | v8.0 | 27 | 5/5 | **COMPLETE** |
| Oct 16 | Oct 14 | v8.0 | 55 | 5/5 | **COMPLETE** |
| Oct 21 | Oct 16 | v8.0 | 39 | 4/5 | INCOMPLETE_EXIT |
| Oct 22 | Oct 21 | v8.0 | 23 | 3/5 | INCOMPLETE_EXIT *(new in S44)* |
| Oct 28 | Oct 22 | v8.0 | 19 | 2/5 | INCOMPLETE_EXIT *(new in S44)* |
| NULL | Oct 28 | v8.0 | 28 | — | EXCLUDED_NULL_EXEC |

**Strict cluster count: 3** (unchanged from S43)  
**New S44 finding:** 2 additional incomplete clusters discovered (fill Oct 22, Oct 28); do not change guardrail verdicts.

---

## Canonical Cluster Deltas (D_v3 vs comparators)

From S43 Bash analysis — hardcoded as regression reference:

| Fill Date | vs A_direct | vs B_v1v2 | vs C_hybrid |
|---|---|---|---|
| Oct 13 | +1.20% | +0.84% | +1.07% |
| Oct 14 | +2.76% | +0.14% | +2.76% |
| Oct 16 | −1.52% | −1.41% | −1.49% |
| **Grand mean** | **+0.81%** | **−0.14%** | **+0.78%** |

---

## Statistical Inference (3 strict clusters)

| Metric | vs A_direct |
|---|---|
| Grand mean | +0.81 pp |
| 95% CI | [−1.4, +3.0] pp |
| Verdict | **SIGNIFICANCE_INCONCLUSIVE** |

CI spans zero → cannot claim V3 is significantly better than direct entry.

---

## Regression Tolerance

S44 recomputed delta must be within ±0.5 pp of S43 reference (+0.81%). Any deviation beyond this indicates dataset or computation change.

---

## Limitations

1. Only 3 strict clusters — far below the ≥10 needed for reliable inference (G03 FAIL)
2. Adjacent 5D windows overlap ~80% — independence assumption violated (G04 FAIL)
3. All signals from Oct 2026 — single month, no OOS validation
4. FEES_PCT=0.00585 is a research assumption only
