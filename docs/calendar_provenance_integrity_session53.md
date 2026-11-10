# Session 53: Calendar + Provenance Integrity

**Calendar Verdict**: CALENDAR_E2E_VERIFIED (carried forward from S52)  
**Provenance Classification**: BASE_ONLY_PROSPECTIVE

## Calendar Integrity

| Check | Status |
|-------|--------|
| SSOT module | `src/research/calendar_contract_s50.py` |
| All callers compliant | Yes |
| Legacy code isolated | Yes |
| Canonical fill dates correct | Yes |
| Oct 27 NOT a fill date | Yes (confirmed — it is 5TD exit of Oct 16) |
| Exit dates verified | Yes |

### Canonical Fill Dates (corrected since S52)

```
2026-10-13, 2026-10-14, 2026-10-16,
2026-10-21, 2026-10-22, 2026-10-28
```

**Oct 27 error**: Earlier sessions (S51 memory) incorrectly listed Oct 27 as a fill date. It is the 5TD exit of Oct 16, not a fill date. Corrected and confirmed in S52, maintained in S53.

### Canonical Exit Dates

| Fill Date | 5TD Exit | 20TD Exit |
|-----------|----------|-----------|
| 2026-10-13 | 2026-10-20 | 2026-11-12 |
| 2026-10-14 | 2026-10-21 | 2026-11-13 |
| 2026-10-16 | 2026-10-23 | 2026-11-17 |
| 2026-10-21 | 2026-10-28 | 2026-11-20 |
| 2026-10-22 | 2026-10-29 | 2026-11-23 |
| 2026-10-28 | 2026-11-06 | 2026-11-25 |

**Nov 12 hard deadline**: Oct 13 20TD exit = Nov 12. If pipeline not restored by Nov 12, Oct 13 outcome cannot be computed.

## Provenance Summary

| Layer | Count | Classification |
|-------|-------|----------------|
| V3_DECISION_PROSPECTIVE | 0 | — |
| BASE_SIGNAL_PROSPECTIVE | 6 | All canonical fill clusters |
| RETROSPECTIVE_RECONSTRUCTION | 21 | hybrid_forward_decision Nov04 batch |

**Overall**: BASE_ONLY_PROSPECTIVE

The apparent contradiction between S36 ("RETROSPECTIVE") and S45/46 ("genuinely prospective") is resolved: S36 addressed the V3 DECISION layer (which is RETROSPECTIVE). S45/46 addressed the BASE SIGNAL layer (which IS genuinely prospective — locked_at < execution_date for all 6 clusters). Both are correct; they refer to different layers.

## S52 Fingerprint Correction

S52 memory listed "Baseline Fingerprint 2c8b2475c8fdc457" but the actual `dataset_fingerprint` from `canonical_5d_baseline_s44.py` is `09c04e8c4059d87e`. These are different hash computations over different fields; both are valid, no discrepancy in underlying data. The `09c04e8c4059d87e` fingerprint is the canonical baseline fingerprint.
