# Recovery Feasibility — Session 45

**Date:** 2026-11-09  
**Session:** S45  
**Module:** `src/research/incomplete_cluster_auditor_s45.py`

---

## Recovery Scope

This document assesses whether the two incomplete fill-date clusters can be legally recovered and incorporated into the strict 5D comparison.

---

## Recovery Decision Matrix

| Cluster | Root Cause | Engineering Issue? | Recovery Type | Decision |
|---|---|---|---|---|
| Fill Oct 22 (n=23) | OUTCOME_NOT_MATURE | No | Pipeline-data-dependent | `RECOVERY_REQUIRES_REVIEW` |
| Fill Oct 28 (n=19) | OUTCOME_NOT_MATURE | No | Pipeline-data-dependent | `RECOVERY_REQUIRES_REVIEW` |

**Neither cluster has a recoverable engineering extraction error.** Recovery is not blocked by code bugs or mismatched field mappings — it is blocked purely by data not existing yet.

---

## What Is and Is NOT Allowed

### Allowed
- Waiting for the daily_prices pipeline to advance to Nov 10–13+
- Re-running `build_canonical_5d_baseline()` after pipeline update
- Including newly complete clusters in a **new baseline version** (not overwriting S44)

### Not Allowed
- Generating synthetic exit prices for missing dates
- Using 0050 thin-day prices (Oct 27, 29, 30, Nov 02, 03) as proxy for real TDs
- Lowering the ≥50-stock threshold to include thin days
- Backfilling prices from external sources without authorisation
- Marking either cluster as `PROSPECTIVE` using retrospective price reconstruction
- Modifying V3 parameters or foe_v1 to reclassify signals

---

## Provenance Requirement

All recovered exit prices must be:
- Sourced from the production daily_prices pipeline (not manual entry)
- For dates that are genuine trading days (≥50 stocks in daily_prices)
- Available at the time of recovery analysis (not forward-looking)
- Labelled `RETROSPECTIVE_RECONSTRUCTION` if prices are added after the initial signal capture

Since the signals themselves are `GENUINE_PROSPECTIVE` (locked before execution), the recovery operation is legal as long as:
1. The exit price data comes from the production pipeline's normal daily run
2. No retroactive fill price adjustment is made
3. The resulting baseline version is clearly distinguished from S44 canonical

---

## Recovery Timeline

| Cluster | Required Event | Expected Date |
|---|---|---|
| Oct 22 fill → 5 TDs | Pipeline captures Nov 10 or Nov 11 as real TD | ~2026-11-10 to 11 |
| Oct 28 fill → 5 TDs | Pipeline captures Nov 10, 11, and 12 as real TDs | ~2026-11-12 to 13 |

**Pipeline note:** daily_prices max = 2026-11-05 as of S45. Nov 06–07 data may already be available from the market but not yet in the pipeline. Recovery may be sooner than estimated if the pipeline runs for Nov 06/07.

---

## Impact on Statistical Verdict

Even after both clusters recover:

| State | Strict Clusters | Statistical Verdict |
|---|---|---|
| Now (S45) | 3 | SIGNIFICANCE_INCONCLUSIVE |
| After Oct 22 recovery | 4 | SIGNIFICANCE_INCONCLUSIVE |
| After Oct 22 + Oct 28 recovery | 5 | SIGNIFICANCE_INCONCLUSIVE |

Adding 1–2 clusters to a 3-cluster base still leaves the CI spanning zero. The verdict will not change.

---

## Action Summary

1. **No code changes required** in this session.
2. **Monitor pipeline** until daily_prices.max ≥ 2026-11-11 (Oct-22 fill) and ≥ 2026-11-13 (Oct-28 fill).
3. **Re-run baseline** in a future session after pipeline confirms ≥50-stock counts on those dates.
4. **Create new baseline version** (do not overwrite S44 canonical).
5. **Recheck G03**: still FAIL even at 5 clusters.
