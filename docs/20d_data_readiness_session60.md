# 20D Data Readiness — Session 60

## Summary

All three October 2026 signal clusters are blocked from 20-day return computation. No `fwd_return_20d` has been calculated for any of the 1,977 signals. AUTH02 has not been authorized.

## Cluster Status

| Cluster | Execution Dates | Signal Count | Exit TD Estimate | Exit in DB? | Readiness |
|---------|----------------|--------------|-----------------|-------------|-----------|
| Oct13-16 | Oct13, Oct14, Oct16 | 1,091 | ~Nov12–Nov16 | No (> Nov05) | DATA_BLOCKED |
| Oct21-22 | Oct21, Oct22 | 563 | ~Nov19–Nov21 | No | NOT_YET_MATURE |
| Oct28 | Oct28 | 323 | ~Nov26–Dec01 | No | NOT_YET_MATURE |
| **Total** | | **1,977** | | | **ALL BLOCKED** |

## Blockers

**DB Max Date:** `daily_prices` maximum date = 2026-11-05 (last confirmed full trading day).

**Oct13-16 cluster:** The 20th trading day after Oct13 falls around Nov12–Nov16. This range is entirely beyond the DB max of Nov05. Even if AUTH02 were granted, the exit price data does not exist in the database.

**Oct21-22 and Oct28 clusters:** Exit dates are even further out (Nov19–Dec01). These are NOT_YET_MATURE regardless of DB state — there is no source data for these exit dates yet.

**AUTH02:** Computation of `fwd_return_20d` for any cluster requires AUTH02. This authorization was explicitly declined in Session 36 and has not been re-authorized since.

## fwd_return_20d Status

```sql
SELECT COUNT(*) FROM forward_signals
WHERE execution_date IN ('2026-10-13','2026-10-14','2026-10-16',
                         '2026-10-21','2026-10-22','2026-10-28')
  AND fwd_return_20d IS NOT NULL
-- Returns: 0
```

Zero signals have a computed 20D return. This is the correct state given the blockers above.

## What Would Unlock Oct13-16

To compute 20D returns for the Oct13-16 cluster:
1. Daily prices must extend to at least Nov16 (20 trading days after Oct13)
2. AUTH01 must be granted to fill the Oct29–Nov09 gap
3. AUTH02 must be granted to authorize 20D return computation
4. The pipeline must be run after the above conditions are met

Steps 1–3 are all currently blocked or unauthorized.

## Genuine Prospective Evidence

No genuine prospective 20D evidence exists. The Oct signals were placed during forward collection windows but their outcomes are not yet computable. Computing them retroactively once data arrives would constitute genuine prospective evidence only if the signals and parameters were frozen before the outcome date — which they were (MODEL_VERSION v8.0, frozen V3 params, frozen Hybrid P1–P4).

However, AUTH02 must be obtained before any computation occurs.
