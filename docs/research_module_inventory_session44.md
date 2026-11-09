# Research Module Inventory — Session 44

**Date:** 2026-11-09  
**Session:** S44 — Research Consolidation & 20D Outcome Execution Readiness  
**Module:** `src/research/research_module_inventory_s44.py`

---

## Purpose

Enumerates all research modules created across Sessions 26–44, categorises each by function, identifies duplicates, and records recommended actions for consolidation.

---

## Module Summary

| Category | Count |
|---|---|
| Total modules | ≥55 |
| STRATEGY | 4 |
| BACKTEST | 6 |
| COMPARISON | 8 |
| EXECUTION | 5 |
| GUARDRAILS | 4 |
| EVIDENCE | 5 |
| CALENDAR | 4 |
| SIGNAL | 3 |
| UNIVERSE | 3 |
| WORKFLOW | 2 |
| STATISTICS | 3 |
| INFRASTRUCTURE | 4 |

---

## Recommended Actions

| Action | Count | Meaning |
|---|---|---|
| KEEP_AS_IS | ~20 | Canonical, no overlap |
| SUPERSEDED_KEEP | ~12 | Older version; newer exists; keep for history |
| SUPERSEDED_RETIRE | ~5 | Duplicated; can be retired |
| CONSOLIDATE | ~8 | Merge with related module |
| EXTEND | ~6 | Needs new data or logic |
| DOCUMENT | ~4 | Needs better docs |

---

## Duplicate Pairs Identified (≥5 pairs)

1. `corrected_5d_comparison_s43.py` vs `canonical_5d_baseline_s44.py` — S44 supersedes S43 baseline
2. `research_readiness_20d.py` vs `maturity_reconciliation_20d_s44.py` — S44 supersedes
3. `guardrail_remediation_s43.py` vs `guardrail_consolidation_s44.py` — S44 consolidates
4. `comparison_contract_s40.py` vs `fill_date_contract.py` — functionally overlapping comparison scoping
5. `evidence_quality_report_s43.py` vs future S44 quality report — S44 extends

---

## Safety Constraints Enforced

- No modules in inventory have `research_boundary = WRITES_PRODUCTION`
- All DB-touching modules use `READ_ONLY_DB` or `IN_MEMORY_ONLY`
- Production platform.db is never written by research modules

---

## Session Coverage

Sessions covered: S26 (V3 prototype), S27–S29 (comparison + WF), S35 (Hybrid), S38 (security classification), S39–S43 (comparison + execution integrity), S44 (consolidation).
