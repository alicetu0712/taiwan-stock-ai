# 20D Data Readiness — Session 58

**Verdict**: 20D_DATA_BLOCKED  
**Date**: 2026-11-10

---

## Three Clusters

### Cluster 1: Oct13 (Most Urgent)

| Field | Value |
|-------|-------|
| Execution dates | 2026-10-13, 2026-10-14, 2026-10-16 |
| Signal count | ~1,091 (348+387+356) |
| Exit TD | 20 |
| Exit date estimate | **2026-11-12** |
| Exit prices in DB | NO (daily_prices max = 2026-11-05) |
| Readiness | **20D_DATA_BLOCKED** |

**Double blocker**:
1. AUTH02 not authorized
2. Nov12 exit prices not in `daily_prices` (max = Nov05, 7 trading days short)

Even with AUTH02, the 20D outcomes cannot be computed until `daily_prices` is populated through Nov12. This requires both data pipeline recovery (AUTH01 path extended to Nov12) **and** outcome computation authorization (AUTH02).

**Urgency**: Exit date is Nov12 (2 trading days from Nov10). Window closes imminently.

### Cluster 2: Oct22

| Field | Value |
|-------|-------|
| Execution dates | 2026-10-22, 2026-10-23 |
| Signal count | ~200 (estimate) |
| Exit date estimate | **2026-11-19** |
| Readiness | **20D_NOT_YET_MATURE** |

Not yet mature as of Nov10. Exit prices not in DB (max Nov05, need Nov19). Same double blocker.

### Cluster 3: Oct28–Nov03

| Field | Value |
|-------|-------|
| Execution dates | 2026-10-28 through 2026-11-03 |
| Signal count | ~400 (estimate) |
| Exit date estimate | 2026-11-25 to 2026-12-02 |
| Readiness | **20D_NOT_YET_MATURE** |

Far from maturity. Exit prices not in DB. Pipeline would need to be populated through December.

---

## 20D Blockers Summary

| Blocker | Status | Required Action |
|---------|--------|----------------|
| AUTH02 not authorized | ACTIVE | Explicit user authorization required |
| daily_prices max = Nov05 | ACTIVE | Pipeline recovery + data populate through Nov12 |
| TPEx alternative missing | ACTIVE | TPEx-exclusive stocks have no recovery path yet |
| G03/G04 guardrails not met | ACTIVE | Genuine prospective N=0 unchanged |

---

## What "20D Outcomes" Would Compute

If both blockers were resolved (AUTH02 granted + exit prices in DB):

1. For each signal in Oct13 cluster (N≈1091): compute 20-day return as (exit_price - entry_price) / entry_price
2. Compare vs benchmark (0050) return over same period
3. Compute alpha = signal_return - benchmark_return
4. Aggregate by strategy version (V1/V2/V3) for comparison

This computation is NOT running. This is a design description only.

---

## 20D Data is NOT Genuine Prospective Evidence

The 20D outcomes, when eventually computed, will be:
- **Retrospective** relative to the signal generation date (signals were generated weeks ago)
- **Prospective** relative to the entry date (outcome was not known at time of entry)

The correct classification depends on whether proper decision records were created before the fact. See `docs/genuine_prospective_readiness_session57.md` for the framework.

**G03 status is UNCHANGED by 20D data readiness.**
