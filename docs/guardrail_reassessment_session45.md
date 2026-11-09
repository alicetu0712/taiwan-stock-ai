# Guardrail Reassessment — Session 45

**Date:** 2026-11-09  
**Session:** S45  
**Module:** `src/research/evidence_policy_s45.py`  
**Overall Verdict:** GUARDRAILS_FAIL

---

## Reassessment Scope

Focused on G01, G03, G04. These are the guardrails with active FAIL or CONDITIONAL status from S44. G02, G05–G10 are verified in S44 consolidation and unchanged.

---

## G01: Trading Calendar Integrity

| Field | Value |
|---|---|
| Horizon | 5D |
| S44 Verdict | CONDITIONAL |
| S45 Evidence | Oct 22/28 incomplete clusters confirmed as OUTCOME_NOT_MATURE, not calendar errors. v8.0 strict pool has 0 non-TD signals. Thin-day skipping (Oct 15/19/20) correctly handled. |
| **S45 Verdict** | **CONDITIONAL** (unchanged) |
| Remaining Blocker | TradingCalendarIntegrityAuditor uses DISTINCT date query; must switch to ≥50-stock threshold |

---

## G03: Independent Cluster Count (≥10)

| Field | Value |
|---|---|
| Horizon | 5D |
| S44 Verdict | FAIL |
| S45 Evidence | Still 3 strict clusters. Oct 22/28 fill confirmed OUTCOME_NOT_MATURE — even if both recover → 5 clusters. Minimum needed: 10. |
| **S45 Verdict** | **FAIL** (unchanged) |
| Remaining Blocker | Need 7 more strict clusters. Accumulation rate ~12–15/month. ETA ~Jan 2027. |
| Path to PASS | Accumulate Nov–Dec 2026 cron signals |

**Key rule preserved:** The threshold of 10 is NOT lowered. Using 3 clusters is insufficient for reliable t-test inference regardless of statistical significance. Even at 5 clusters after recovery, G03 remains FAIL.

---

## G04: Holding Period Non-Overlap

### 5D Assessment

| Field | Value |
|---|---|
| Horizon | 5D |
| S44 Verdict | FAIL |
| S45 Evidence | Oct 13 (exit ~Oct 21) and Oct 14 (exit ~Oct 22) share Oct 14-21 (~80% overlap). Design constraint — cannot be resolved for daily fills with 5D windows. |
| **S45 Verdict** | **FAIL** (unchanged) |
| Remaining Blocker | Inherent design constraint |

### 20D Assessment

| Field | Value |
|---|---|
| Horizon | 20D |
| S44 Verdict | FAIL |
| S45 Evidence | Oct 13 (20D exit ~Nov 24) and Oct 14 (20D exit ~Nov 25) have 5TD gap → 20D windows overlap ~15 TDs (~75%). Still a constraint even at 20D for consecutive fills. |
| **S45 Verdict** | **FAIL** (unchanged) |
| Path to PASS | Use only one fill per 20-TD period. First eligible: single fill per month. |

**5D and 20D assessed independently** per PART H requirements. Neither is affected by the other's status.

---

## Guardrail Summary

| ID | Horizon | Before | After | Type |
|---|---|---|---|---|
| G01 | 5D | CONDITIONAL | CONDITIONAL | ENGINEERING_FIXABLE |
| G03 | 5D | FAIL | FAIL | DATA_LIMITED |
| G04 | 5D | FAIL | FAIL | DESIGN_CONSTRAINT |
| G04 | 20D | FAIL | FAIL | DESIGN_CONSTRAINT |

**Overall: GUARDRAILS_FAIL** — G03 and G04 both FAIL, unchanged from S44.

---

## Critical Boundaries

1. **G03 threshold is not negotiable.** Using 3 or 5 clusters cannot be retroactively promoted to "sufficient" because performance looks good.
2. **G04 applies to both horizons independently.** Achieving 20D maturity does not resolve G04 for 5D, nor vice versa.
3. **Neither guardrail can be fixed by research code changes.** Both require external conditions (more data or different signal cadence).
