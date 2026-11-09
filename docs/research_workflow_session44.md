# Minimal Research Workflow — Session 44

**Date:** 2026-11-09  
**Session:** S44  
**Module:** `src/research/research_workflow_s44.py`  
**Verdict:** WORKFLOW_PARTIAL (no production modifications)

---

## Purpose

Defines the 12-step minimal viable research workflow. All steps are read-only. The workflow stops and reports blockers rather than silently skipping validation.

---

## Workflow Steps

| Step | Name | Expected Status | Description |
|---|---|---|---|
| S01 | Load Read-only Snapshot | PASS | Verify DB accessible; record total forward_signals and daily_prices max |
| S02 | Validate Universe | CONDITIONAL | v8.0 and v6.0 signals both present; v6.0 will be excluded |
| S03 | Validate Strategy Version | PASS | PARAMETER_HASH = be43e8ca977d9fdd |
| S04 | Validate Trading Calendar | PASS | 0 v8.0 signals on Oct 09–11 non-trading days |
| S05 | Validate Execution Provenance | PASS | All fills are NEXT_OPEN (simulated) |
| S06 | Validate Outcome Maturity | CONDITIONAL | 5D: 3 complete clusters; 20D: 0 complete |
| S07 | Validate Comparison Contract | PASS | No v6.0 signals have execution_date in strict pool |
| S08 | Compute Eligible 5D Metrics | PASS | Cluster deltas: [+1.20%, +2.76%, −1.52%]; grand mean +0.81% |
| S09 | Cluster-aware Statistical Inference | PASS | CI=[−1.4%, +3.0%]; SIGNIFICANCE_INCONCLUSIVE |
| S10 | Apply Statistical Guardrails | CONDITIONAL | G01=CONDITIONAL, G03=FAIL, G04=FAIL |
| S11 | Generate Research Manifest | PASS | Deterministic fingerprint generated |
| S12 | Generate Evidence Report | PASS | Quality mean ~5.15/10; ACTIVATION_BLOCKED |

---

## Key Outputs

| Output | Value |
|---|---|
| `production_modified` | `False` |
| `authorization_violations` | None |
| `can_compute_20d` | `False` |
| `guardrail_verdict` | GUARDRAILS_FAIL |
| `n_strict_clusters` | 3 |
| `statistical_verdict_5d` | SIGNIFICANCE_INCONCLUSIVE |

---

## Ordering Contract

Steps S01–S07 are validation gates. S08 (metric computation) is only reached after S01–S07 all pass or are CONDITIONAL. Any BLOCKED step in S01–S05 causes all subsequent steps to be SKIPPED.

---

## Authorization Rule

The workflow explicitly enforces `can_compute_20d = False`. Even if 20D outcomes become available, computation must be explicitly authorized in a future session prompt before the workflow will execute E03–E12.
