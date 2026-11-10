# Six-cluster V3 Provenance Audit — Session 52

**Analysis date**: 2026-11-10  
**Session**: S52  
**Module**: `src/research/provenance_audit_s52.py` → `build_six_cluster_provenance()`  
**Overall Verdict**: BASE_ONLY_PROSPECTIVE

---

## Critical Correction: Canonical Fill Dates

**S51 memory error**: October 27 was listed as a fill date.  
**Corrected (S52)**: Oct 27 is the **5TD exit date of Oct 16**, not a fill date.

| Canonical Fill Date | Signal count (v8.0) | First locked | Last locked | locked < exec? |
|--------------------|---------------------|--------------|-------------|----------------|
| 2026-10-13 | 348 | 2026-10-12 | 2026-10-12 | ✓ |
| 2026-10-14 | 387 | 2026-10-12 | 2026-10-13 | ✓ |
| 2026-10-16 | 356 | 2026-10-14 | 2026-10-14 | ✓ |
| 2026-10-21 | 261 | 2026-10-16 | 2026-10-16 | ✓ |
| 2026-10-22 | 302 | 2026-10-21 | 2026-10-21 | ✓ |
| 2026-10-28 | 323 | 2026-10-21 | 2026-10-21 | ✓ |

---

## Per-cluster Classification

All six clusters: **BASE_SIGNAL_PROSPECTIVE**

**Rationale**: v8.0 base signal was locked before execution_date (confirmed by DB locked_at timestamps). V3 decision layer was never generated for any of these dates.

---

## Provenance Layer Separation

The critical rule (C3): `locked_at < execution_date` is **necessary but not sufficient** for V3_DECISION_PROSPECTIVE.

| Layer | Clusters with prospective evidence |
|-------|-----------------------------------|
| BASE_SIGNAL | 6/6 (all locked before execution) |
| V3_DECISION | 0/6 (V3 never activated; no decisions generated) |
| FILL_SIMULATION | N/A (not tracked separately) |
| OUTCOME | N/A (AUTH02 not authorized) |

---

## hybrid_forward_decision (21 rows)

- trade_date: 2026-11-04
- rule_version: hybrid_v1
- research_version: v2_research_v2
- Classification: **RETROSPECTIVE_RECONSTRUCTION**
- These were generated manually on Nov 04, before RULE_FREEZE_DATE (2026-11-05). They are NOT V3 decisions.

---

## Contradiction Ledger

| Session | Classification | Basis |
|---------|---------------|-------|
| S36 | 21 decisions = RETROSPECTIVE_RECONSTRUCTION | hybrid_forward_decision on Nov 04 |
| S45/46 | "ALL_GENUINE_PROSPECTIVE" for 6 fill clusters | Based on BASE SIGNAL timestamps |
| S51 | BASE_SIGNAL_PROSPECTIVE; RULE_FREEZE_DATE introduced | Formal provenance framework |
| S52 | BASE_SIGNAL_PROSPECTIVE confirmed; fill dates corrected | DB verification + layer separation |

**Resolution**: S45/46 "Genuine Prospective" label was correct at the BASE SIGNAL layer. The error was not explicitly distinguishing between Base Signal Provenance and V3 Decision Provenance. S52 formally separates these layers. The base signal timestamps are genuine prospective evidence; the V3 decision layer was never generated prospectively.

---

## V3_DECISION_PROSPECTIVE Count: 0

No V3 decisions exist for any fill date. V3 is ACTIVATION_BLOCKED. Classification V3_DECISION_PROSPECTIVE is currently unachievable.
