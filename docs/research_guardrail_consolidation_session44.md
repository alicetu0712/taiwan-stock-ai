# Research Guardrail Consolidation — Session 44

**Date:** 2026-11-09  
**Session:** S44  
**Module:** `src/research/guardrail_consolidation_s44.py`  
**Verdict:** GUARDRAILS_FAIL

---

## Purpose

Consolidates all S42–S43 guardrail findings into a unified view. Key addition: explicitly categorises each guardrail as ENGINEERING_FIXABLE, DATA_LIMITED, or DESIGN_CONSTRAINT.

---

## Consolidated Verdicts

| ID | Name | Type | S42 | S43 | S44 |
|---|---|---|---|---|---|
| G01 | Trading Calendar Integrity | ENG_FIXABLE | FAIL | CONDITIONAL | CONDITIONAL |
| G02 | Metric Label Integrity | ENG_FIXABLE | PASS | PASS | PASS |
| G03 | Cluster Count Adequacy (≥10) | DATA_LIMITED | FAIL | FAIL | **FAIL** |
| G04 | Holding Period Non-Overlap | DESIGN_CONSTRAINT | FAIL | FAIL | **FAIL** |
| G05 | Signal Independence | ENG_FIXABLE | PASS | PASS | PASS |
| G06 | Outcome Contamination (20D vs 5D) | ENG_FIXABLE | PASS | PASS | PASS |
| G07 | Benchmark Consistency | ENG_FIXABLE | PASS | PASS | PASS |
| G08 | Multiple Comparison Correction | ENG_FIXABLE | CONDITIONAL | CONDITIONAL | CONDITIONAL |
| G09 | No Look-Ahead Leakage | ENG_FIXABLE | PASS | PASS | PASS |
| G10 | Sample Universe Stability (ETF) | ENG_FIXABLE | CONDITIONAL | CONDITIONAL | CONDITIONAL |

**Summary: 6 PASS, 2 CONDITIONAL, 2 FAIL**

---

## Why G03/G04 Cannot Be Engineered Away

**G03 (DATA_LIMITED):** We have 3 strict fill clusters (need ≥10). There is no engineering fix — we must wait for Nov–Dec 2026 cron signals. Each month adds ~12–15 fill clusters. ETA: ~Jan 2027 for 10+ strict clusters.

**G04 (DESIGN_CONSTRAINT):** Adjacent 5D windows overlap ~80%. This is structurally inherent to daily signals + 5-day holding periods. Cannot be fixed without either:
- Switching to weekly/monthly signal cadence, OR
- Using HAC-corrected standard errors, OR
- Using 20D windows (non-overlapping if clusters ≥4 weeks apart — achievable ~Jan 2027)

---

## S44 New Finding

Extending scope to full v8.0 range (Oct 09–28) adds 2 more incomplete clusters (fill Oct 22, Oct 28). **This does NOT change G03 or G04 verdicts.** Strict count remains 3.

---

## Path to PASS for Each Failing Guardrail

| ID | Path to PASS | ETA |
|---|---|---|
| G01 | Update TradingCalendarIntegrityAuditor to use ≥50-stock threshold | Next session |
| G03 | Accumulate Nov–Dec 2026 cron signals (~12–15/month) | ~Jan 2027 |
| G04 | Use 20D windows when ≥4-week cluster spacing available | ~Jan 2027 |
