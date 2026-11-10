# G04 Dependence Study — Session 50

**Date:** 2026-11-10  
**Session:** S50 — PART G (NEW ANALYSIS)  
**Verdict:** G04 STRUCTURAL FAILURE — weekly spacing does NOT resolve G04

---

## G04 Requirement

Guardrail G04 requires: adjacent cluster windows have < 30% overlap in their 5-day holding periods.

**Purpose:** To ensure that consecutive signal returns are not driven by shared market days, which would create artificial autocorrelation in the return series.

---

## Current G04 Status (All 6 Fills)

### Adjacent Pair Overlap Matrix

| Fill A | Fill B | Days Shared | Overlap % | Adjacent | G04 |
|---|---|---|---|---|---|
| Oct 13 | Oct 14 | 4 | **80%** | Yes | FAIL |
| Oct 14 | Oct 16 | 3 | **60%** | Yes | FAIL |
| Oct 16 | Oct 21 | 2 | **40%** | Yes | FAIL |
| Oct 21 | Oct 22 | 4 | **80%** | Yes | FAIL |
| Oct 22 | Oct 28 | 3 | **60%** | Yes | FAIL |

**All 5 adjacent pairs exceed the 30% threshold. G04 FAIL.**

Maximum adjacent overlap: 80% (Oct 13/14 and Oct 21/22 pairs).

---

## Weekly Spacing Analysis (S50 NEW)

### Scenario 1: ≥5 TD spacing

Applying a minimum 5-TD gap between retained fills:

| Fill | Gap from Previous Retained | Retained? |
|---|---|---|
| Oct 13 | — (baseline) | ✓ |
| Oct 14 | 1 TD from Oct 13 | ✗ skip |
| Oct 16 | 2 TD from Oct 13 | ✗ skip |
| Oct 21 | 6 TD from Oct 13 | ✓ |
| Oct 22 | 1 TD from Oct 21 | ✗ skip |
| Oct 28 | 5 TD from Oct 21 | ✓ |

**Retained: {Oct 13, Oct 21, Oct 28} = N=3**

Adjacent overlaps in retained set:
- Oct 13/Oct 21: 0 shared days → **0% ✓ G04 PASS**
- Oct 21/Oct 28: 2 shared days → **40% ✗ G04 FAIL**

**Conclusion: ≥5 TD spacing STILL FAILS G04 due to Oct 21/Oct 28 pair (40%).**

This is because Oct 28 is exactly 5 TD from Oct 21, which means their 5-day windows still share 2 days. The exit date of Oct 21's window (Oct 28) is the same day as Oct 28 itself.

### Scenario 2: ≥6 TD spacing

Retained: {Oct 13, Oct 21} only (Oct 28 is only 5 TD from Oct 21)

Adjacent pairs:
- Oct 13/Oct 21: 0 shared days → **0% ✓ G04 PASS**

**G04 would PASS but N=2 — G03 is worse than current.**

---

## Critical Finding: G04 Is Structurally Linked to 5-Day Window Size

For a 5-day window, the minimum gap needed for ZERO overlap between adjacent clusters is **6 TD**. This is because:

```
Fill A window: {TD1, TD2, TD3, TD4, TD5}
Fill B window: {TD1', TD2', TD3', TD4', TD5'}
Zero overlap condition: TD5 < TD1' → gap ≥ 6 TD between fills
```

If fills are ≤5 TD apart, they always share at least 1 window day. The Oct 13/Oct 14 pair (1 TD apart) shares 4 of 5 days (80%) — maximum possible.

---

## Effective Sample Size

With pairwise autocorrelation r ≈ 0.8 (from 80% overlap), the effective N formula:

```
N_eff = N / (1 + (N-1) × r)
```

| Scenario | N | r | N_eff |
|---|---|---|---|
| Current (all 6 fills) | 6 | 0.80 | ≈ 1.09 |
| Weekly-5TD subset | 3 | 0.80 | ≈ 1.15 |
| Hypothetical N=10 | 10 | 0.80 | ≈ 1.09 |

**Key insight:** Even with N=10, if all fills are 1–2 TD apart, effective N remains ~1.1.

**Implication:** Standard t-test treating N=3 or N=6 as independent observations overstates statistical power by ~2.6×. The published p=0.58 (from S41, without autocorrelation correction) is already non-significant; the corrected test is even more conclusive in its non-significance.

---

## Bootstrap CI: NOT APPLICABLE

Bootstrap CI with cluster-aware correction requires N≥10 independent clusters (G03 must be met first). With current N=6 and effective N≈1.09:

- Bootstrap would resample 6 highly-correlated returns and treat them as independent draws
- This is methodologically invalid
- Any bootstrap CI computed now would be artificially narrow by ~2.6×

**Bootstrap CI is BLOCKED until G03 is resolved.**

---

## Remediation Options

| Option | G04 After | G03 After | Trade-off |
|---|---|---|---|
| Do nothing | FAIL (5 pairs) | FAIL (6/10) | Not acceptable long-term |
| ≥5 TD spacing | FAIL (1 pair) | FAIL (3/10) | Reduces but doesn't fix G04 |
| ≥6 TD spacing | PASS | FAIL (2/10) | G04 passes but N too small |
| Collect new fills at ≥6 TD | Passes after 4+ weeks | Passes after 10+ fills | Only valid long-term path |
| Accept + document | FAIL | FAIL | Statistical caveat only |

**Recommended path:** Continue data collection at ≥6 TD frequency (weekly+ cadence). After 10 weekly fills with ≥6 TD spacing, both G03 and G04 can pass simultaneously.

---

## Conclusion

G04 failure is **structural**: it stems from the 5-day holding window combined with sub-weekly fill frequency. No data quality improvement can fix this — it requires a design change.

**Statistical verdict: SIGNIFICANCE_INCONCLUSIVE (unchanged)**  
**Activation: ACTIVATION_BLOCKED (unchanged)**

---

## References

- Module: `src/research/calendar_contract_s50.py`
- Function: `build_g04_dependence_study()`
- Tests: `tests/test_session50_market_sources.py` TC33–TC37
- Prior: `docs/guardrails_session49.md`
