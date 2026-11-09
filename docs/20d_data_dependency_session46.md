# 20D Data Dependency Analysis — Session 46

**Date:** 2026-11-09  
**Session:** S46 — PART G  
**Authorization Status:** 20D OUTCOME CALCULATION NOT AUTHORIZED (S44/S45/S46)

---

## Calendar 20th Trading Day Per Fill Cluster

| Fill Date | Calendar 20th TD | Days Until (from Nov 09) | Status |
|---|---|---|---|
| Oct 13 | Nov 14 | 5 days | NOT_YET_MATURE |
| Oct 14 | Nov 17 | 8 days | NOT_YET_MATURE |
| Oct 16 | Nov 19 | 10 days | NOT_YET_MATURE |
| Oct 21 | Nov 24 | 15 days | NOT_YET_MATURE |
| Oct 22 | Nov 25 | 16 days | NOT_YET_MATURE |
| Oct 28 | Dec 02 | 23 days | NOT_YET_MATURE |

**All 6 fill clusters are NOT_YET_MATURE for 20D as of 2026-11-09.**

---

## DB Coverage Requirement

A complete 20D computation requires exit-day prices (closing prices 20 real TDs after each fill date). The earliest exit date is Nov 14 — still 5 trading days in the future from the analysis date.

| Requirement | Status |
|---|---|
| Local SQLite Max | 2026-11-05 (9 days before earliest 20D exit) |
| Neon Max | 2026-11-06 (8 days before earliest 20D exit) |
| Data needed through | 2026-12-02 (for Oct 28 fill) |
| Pipeline working? | PROVIDER_NOT_READY as of Nov 09 |

Even if the pipeline were fully operational today, 20D computations for the first cluster (Oct 13 fill) would not be possible until **at least Nov 14**, and all 6 clusters are not complete until after **Dec 02**.

---

## Proxy TD Counts (Local SQLite, as of Nov 09)

The `_count_exit_days` proxy (using stock_id='2330' in daily_prices after fill date) gives:

| Fill Date | Proxy TD Count | Required for 20D | Shortfall |
|---|---|---|---|
| Oct 13 | 7 | 20 | 13 |
| Oct 14 | 7 | 20 | 13 |
| Oct 16 | 7 | 20 | 13 |
| Oct 21 | 4 | 20 | 16 |
| Oct 22 | 3 | 20 | 17 |
| Oct 28 | 2 | 20 | 18 |

No cluster is close to being computable for 20D in local SQLite.

---

## Why This Matters for Guardrails

G04 (20D coverage guardrail) requires ≥10 strict clusters with verified 20D outcomes. Current status:
- Strict 20D clusters: **0** (none have reached 20th TD)
- Required: 10
- G04 Status: **FAIL** (structural, not temporal — first possible non-fail is mid-December at earliest)

---

## Authorization Block

20D outcome calculation was explicitly not authorized in S44, S45, and S46. Even when calendar dates mature, computation requires:
1. Full pipeline restoration (Nov 06, Nov 09 dates backfilled)
2. Explicit authorization in a future session
3. Revised G04 guardrail assessment

**No 20D computation was performed in this session.**
