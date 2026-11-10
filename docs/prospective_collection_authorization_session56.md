# Prospective Collection Authorization Roadmap — Session 56

**Verdict**: COLLECTION_BLOCKED (unchanged from S55)

## Readiness Matrix (12 items)

| # | Requirement | Status | Blocking Item |
|---|-------------|--------|--------------|
| 1 | Frozen Strategy (v8.0) | ✓ FROZEN | — |
| 2 | Frozen Parameters (be43e8ca977d9fdd) | ✓ FROZEN | — |
| 3 | Code Commit (8580874) | ✓ FROZEN | — |
| 4 | Input Snapshot (Canonical V2) | ✓ VERIFIED | — |
| 5 | Decision Cutoff | ✗ NOT MET | V3 shadow not running |
| 6 | V3 Decision Generation | ✗ BLOCKED | V3 not activated |
| 7 | Recorder Registration | ✗ NOT MET | prospective_recorder_s51 not in production |
| 8 | Immutable Storage | ✗ NOT MET | No production immutable record |
| 9 | Future Execution Observation | ✗ NOT MET | No live market feed |
| 10 | Price Coverage (Oct29–Nov03) | ✗ INSUFFICIENT | 0.15% (3/1969) |
| 11 | Cluster Eligibility | ✗ PENDING | Requires items 5–9 |
| 12 | Statistical Guardrails (G03/G04) | ✗ FAIL | 0/10 windows |

## Minimal Authorization Sequence

**Stage A — Research Evidence Storage** (No auth required):
- Canonical Baseline V2 ✓ DONE
- Research module documentation ✓ DONE

**Stage B — Market Data Recovery** (AUTH01 required):
- Authorize AUTH01 for Oct29/30/Nov02/03
- Deploy TPEx patch (AUTH02-patch)
- These stages are independent of genuine prospective collection

**Stage C — Historical Outcome Completion** (AUTH02-20D required):
- 20D maturity reached for Oct13 cluster (~Nov12)
- Authorize 20D return computation

**Stage D — Genuine Prospective Decision Collection** (AUTH03 required):
- Activate V3 prospective shadow
- Register ProspectiveRecorder in production
- Collect V3 decisions with timestamps BEFORE outcomes

**Stage E — Independent Cluster Accumulation** (time + calendar):
- Accumulate ≥10 independent clusters with weekly spacing
- Each cluster must have genuine V3 decision before outcome
- Minimum time: ~10 weeks from V3 activation

**Stage F — Statistical Evaluation** (AUTH04 required):
- Run cluster-level t-test on genuine N≥10 clusters
- Compare against baseline

## Explicit Boundaries

MUST NOT:
- Modify production cron
- Activate V3 shadow/paper/actual without authorization
- Count historical backfill toward G03
- Count reconstructed outcomes as genuine prospective
- Lower G03/G04 thresholds

## S56 vs S55

| Item | S55 | S56 | Change |
|------|-----|-----|--------|
| Blockers cleared | 0 | 0 | No change |
| Coverage insight | "~700 universe" | "1969 ordinary stocks" | More precise |
| OHLCV limitation | Known (estimated) | Explicitly documented | Clearer |
| AUTH01 value | Understated | Explicitly: 0.15% | More accurate |

## Module

`src/research/auth01_impact_simulation_s56.py` — PART B5
