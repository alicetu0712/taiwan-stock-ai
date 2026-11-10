# Calendar & 20D Integrity — Session 55

## Calendar Integrity

**Verdict**: CALENDAR_E2E_VERIFIED (unchanged from S42–S54)

| Property | Status |
|----------|--------|
| TaiwanTradingCalendar_v1 | VERIFIED |
| 2026-10-13 is trading day | ✓ |
| 2026-10-14 is trading day | ✓ |
| 2026-10-16 is trading day | ✓ |
| 2026-10-29 is trading day | ✓ |
| 2026-11-04 is trading day | ✓ |
| 2026-11-05 is trading day | ✓ |
| Calendar contract in Canonical V2 | TaiwanTradingCalendar_v1 |

## 20D Return Readiness

**Verdict**: TWENTY_D_NOT_READY

| Fill Date | Entry Date | Expected Exit Date (20TD) | Current Date | Trading Days Elapsed | Status |
|-----------|------------|--------------------------|-------------|---------------------|--------|
| 2026-10-13 | 2026-10-14 | ~2026-11-12 | 2026-11-10 | ~18TD | APPROACHING |
| 2026-10-14 | 2026-10-15 | ~2026-11-13 | 2026-11-10 | ~17TD | APPROACHING |
| 2026-10-16 | 2026-10-17 | ~2026-11-17 | 2026-11-10 | ~15TD | NOT_MATURE |

**Note**: Oct13 20D window may mature ~Nov12. As of 2026-11-10, no cluster has completed 20 trading days since entry.

## CANONICAL_20TD_EXITS

| Fill Date | 20TD Count | Status |
|-----------|------------|--------|
| 2026-10-13 | 0 (exits) | NOT_YET_AVAILABLE |
| 2026-10-14 | 0 (exits) | NOT_YET_AVAILABLE |
| 2026-10-16 | 0 (exits) | NOT_YET_AVAILABLE |

20D data remains LOCKED (no new 20D return or alpha computation authorized — see safety constraints).

## 5D Baseline Status

**Grand Mean (5D, strict fill dates)**: +0.81pp  
**CI**: [−1.4pp, +3.0pp]  
**Verdict**: SIGNIFICANCE_INCONCLUSIVE (N=3, cluster-level t-test)  
**Frozen**: Yes — no recomputation in S55

## G06 / 20D Guardrail

| Guardrail | Requirement | Status |
|-----------|-------------|--------|
| G06 (20D exits) | ≥10 exits per cluster | NOT_MET (0 exits available) |
| Minimum maturity | Oct13 cluster | ~Nov12 (2 days away from today) |

## Why TWENTY_D_NOT_READY

As of 2026-11-10 (today), Oct13 cluster has ~18 trading days elapsed. The 20D window matures approximately Nov12. We cannot compute 20D returns until after that date, and even then only for the first cluster.

## Safety Note

Executing new 20D Return / Alpha / Outcome computation is **explicitly prohibited** per session safety constraints. No 20D computation was performed in S55.
