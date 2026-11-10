# B01/B02 Dependency Audit — Session 56

**Verdict**: B01_B02_PARTIALLY_SUPPORTED

## B01/B02 Original Definitions (Session 55)

| Blocker | Definition |
|---------|-----------|
| B01 | AUTH01 backfill not executed |
| B02 | TPEx patch not deployed |

## Dependency Graph

| Component | B01 (AUTH01) | B02 (TPEx Patch) | Both |
|-----------|-------------|-----------------|------|
| Data in DB for Oct29/30/Nov02/03 | ✓ Directly resolves | ✗ No effect | ✓ |
| TPEx error observability | ✗ No effect | ✓ Directly resolves | ✓ |
| Nov06/09 URL type fix (RC-02) | ✗ | ✗ (separate fix) | ✗ |
| Coverage >100 stocks/date | ✗ (3/1969 = 0.15%) | ✗ | ✗ |
| QG PASS for Oct29/30/Nov02/03 | ✗ (0.15% << threshold) | ✗ | ✗ |
| Genuine Prospective Evidence | ✗ (historical, not prospective) | ✗ | ✗ |
| G03 clusters | ✗ (backfill ≠ prospective) | ✗ | ✗ |

## Counterfactual Scenarios

| Scenario | B01 | B02 | G03 | Collection | Prospective N |
|----------|-----|-----|-----|-----------|--------------|
| Neither | BLOCKED | BLOCKED | 0/10 | BLOCKED | 0 |
| AUTH01 only | RESOLVED (partial) | BLOCKED | 0/10 | BLOCKED | 0 |
| Patch only | BLOCKED | RESOLVED | 0/10 | BLOCKED | 0 |
| AUTH01 + Patch | PARTIAL (7 rows) | RESOLVED | 0/10 | BLOCKED | 0 |
| AUTH01 + Patch + Full Collection | PARTIAL | RESOLVED | Requires new windows | CONDITIONAL | 0 → accumulates |

## Why PARTIALLY_SUPPORTED (not VERIFIED)

The S55 claim: "授權 AUTH01 與 TPEx Patch 可以直接解除 B01+B02，開始 G03 累積路徑" is **partially supported** because:

1. **B01 resolution is partial**: AUTH01 with S50 data only achieves 0.15% coverage per date, not full universe. QG still fails. The claim that AUTH01 "opens" G03 is MISLEADING — G03 requires genuine prospective decisions, which historical backfill never provides.

2. **B02 resolution is verified**: TPEx patch directly fixes error propagation. PATCH_DEPLOYMENT_READY confirmed.

3. **G03 accumulation path requires more than B01+B02**: G03 needs: (a) V3 decisions before outcome, (b) frozen parameters, (c) immutable timestamps, (d) ≥10 independent clusters with weekly spacing. AUTH01 backfill provides NONE of these.

## Genuine Prospective Collection Requirements

For genuine V3 prospective evidence (Genuine N to increment from 0):

| Requirement | Current State |
|-------------|--------------|
| V3 Decision Before Outcome | NOT MET (V3 shadow not running) |
| Frozen Parameters | MET (be43e8ca977d9fdd frozen) |
| Frozen Code/Input | MET |
| Immutable Timestamp | NOT MET (no prospective recorder running) |
| Cutoff Compliance | NOT MET |
| Genuine Execution Observation | NOT MET |
| Eligible Market Data | PARTIAL (only Nov04/05 backfilled) |
| Independent Cluster Definition | NOT MET |
| Pre-registered Protocol | MET (baseline_v2 registered) |

**Genuine N = 0. AUTH01 does not change this.**

## Post-B01+B02 Remaining Blockers

After AUTH01 + TPEx Patch authorized and deployed:

- B01: RESOLVED (partial — 7 rows; full universe still needs new provider calls)
- B02: RESOLVED
- B03: Cron recovery still required (AUTH01 was manual; cron still not re-triggered)
- B04/B05: Nov06/09 TWSE_HIST_URL fix still needed
- B06: TPEx coverage still unverified
- B07: G03 0/10 — requires genuine prospective windows (time + cron + V3 decisions)
- B08: G04 STRUCTURAL_FAIL — algorithm change needed
- B09: Stage B Cron Probe still NOT AUTHORIZED

## Module

`src/research/auth01_impact_simulation_s56.py` — PART B5  
`src/research/tpex_patch_deployment_s56.py` — PART C–D
