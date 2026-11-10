# Prospective Cluster Collection Plan — Session 51

**Analysis date**: 2026-11-10  
**Session**: S51  
**Module**: `src/research/prospective_recorder_s51.py` → `ProspectiveClusterCollectionPlan`

---

## Target Parameters (pre-registered)

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `target_n` | 10 | G03 requires ≥10 independent clusters |
| `min_td_gap` | 6 | G04 requires ≥6 TD between clusters to avoid window overlap |
| `min_stocks_per_date` | 300 | Signal quality floor |
| `coverage_threshold` | 5,000 | Pipeline quality gate (`_MIN_COVERED_STOCKS`) |
| `rule_freeze_date` | 2026-11-05 | V3 decisions before this date = RETROSPECTIVE_RECONSTRUCTION |
| `v3_parameter_hash` | `be43e8ca977d9fdd` | Frozen; must match for V3_DECISION_PROSPECTIVE |
| `model_version` | `v8.0` | Frozen |

---

## Current State (as of S51)

| Classification | Count |
|----------------|-------|
| V3_DECISION_PROSPECTIVE | 0 |
| BASE_SIGNAL_PROSPECTIVE | 6 (Oct 13–28) |
| RETROSPECTIVE_RECONSTRUCTION | ≥1 (Nov 04) |
| PROVENANCE_UNVERIFIED | 0 |

**G03 status**: FAIL (need ≥10 V3_DECISION_PROSPECTIVE; have 0)  
**G04 status**: FAIL (structural: 5D window + ≤5 TD fill spacing = overlap)  
**Collection verdict**: FRAMEWORK_READY_COLLECTION_PENDING

---

## Clusters Needed

- V3_DECISION_PROSPECTIVE needed: **10** (from 0)
- Estimated calendar weeks at 1 cluster/week: **~10.8 weeks** (from 2026-11-10)
- Estimated completion: **~2027-01-26** (contingent on pipeline restoration + V3 activation)

---

## Pre-Registration Rules

These rules are fixed before any prospective collection begins. They **cannot** be modified retroactively:

1. Each cluster must be on a trading day with pipeline FULL_MARKET_FRESH status
2. Each cluster must have ≥6 TD gap from the previous V3_DECISION_PROSPECTIVE cluster
3. V3 parameter hash must equal `be43e8ca977d9fdd` at decision time
4. Decision must be locked (ImmutableDecisionPayload fingerprinted) before `execution_date`
5. Clusters may not be reclassified post-hoc

---

## Blockers

1. **Pipeline not operational** — Nov 06 (QG FAIL) and Nov 09 (STALE_DATA) both blocked
2. **V3 not activated** — ACTIVATION_BLOCKED (see `docs/session51_final_verdict.md`)
3. **AUTH01 pending** — backfill for Oct 29/30, Nov 02/03, Nov 06, Nov 09 all PENDING

---

## Planned Cluster Specs (tentative)

No clusters can be formally scheduled until pipeline is restored. First eligible date will be the first post-restoration trading day with ≥5,000 stock coverage and V3 active.
