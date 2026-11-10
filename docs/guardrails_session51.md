# Statistical Guardrails — Session 51

**Analysis date**: 2026-11-10  
**Session**: S51  
**Baseline**: +0.81 pp (fingerprint `09c04e8c4059d87e`)

---

## G03: Independent Cluster Count

**Status**: FAIL (maintained from S50)

| Requirement | Current | Verdict |
|-------------|---------|---------|
| ≥10 independent clusters | 3 strict-eligible (Oct 13, 21, 28) | FAIL |
| Clusters must be V3_DECISION_PROSPECTIVE | 0 V3_DECISION_PROSPECTIVE | FAIL |
| All clusters must have ≥6 TD gap | Oct 21/Oct 28 = 5 TD gap | FAIL |

**Why G03 cannot pass currently**:
- V3 is not activated → no V3_DECISION_PROSPECTIVE records possible
- With ≤5 TD spacing between Oct 21 and Oct 28, only N=2 clusters qualify at ≥6 TD threshold
- Need 10 qualifying clusters; currently 0

**Path to G03 PASS**: Restore pipeline → Activate V3 → Collect 10 V3_DECISION_PROSPECTIVE clusters with ≥6 TD spacing (~10.8 weeks from 2026-11-10)

---

## G04: Weekly Dependence (Cluster Spacing)

**Status**: FAIL (structural — cannot be fixed without changing window size or collection frequency)

| Scenario | Min TD gap | Clusters retained | G04 verdict |
|----------|-----------|-------------------|-------------|
| ≥5 TD spacing | 5 | N=3 (Oct 13, 21, 28) | G04_FAIL (Oct 21/28 = 40% overlap) |
| ≥6 TD spacing | 6 | N=2 (Oct 13, 21) | G04_PASS but G03 worse |
| Current 5D window | — | — | STRUCTURAL: 5D window + ≤5 TD spacing = guaranteed overlap |

**Root cause**: The 5-trading-day return window means any two fill clusters within 5 TD will have overlapping measurement periods. With ≤5 TD between Oct 21 and Oct 28 fills, independence cannot be established.

**Effective N** (N=6, r=0.8): ≈ 1.09 → bootstrap CI completely invalid at current cluster count.

**Path to G04 PASS**: Collect clusters with ≥6 TD spacing AND N ≥ 10. This is the same requirement as G03 — both guardrails pass simultaneously or not at all.

---

## Baseline Frozen

The strict 5D baseline of **+0.81 pp** (fingerprint `09c04e8c4059d87e`) is frozen and must not be overwritten. Any new calculation is a separate analysis and must be labelled with its own fingerprint. No new 20D return/alpha/outcome calculations were executed in S51.

---

## Guardrail Independence from Pipeline State

G03 and G04 failures are **not** caused by the pipeline failures (Nov 06, Nov 09 blocks). They are caused by:
1. V3 not activated (no V3_DECISION_PROSPECTIVE evidence)
2. Structural overlap in existing fill cluster spacing

Restoring the pipeline is necessary but not sufficient for guardrail passage.
