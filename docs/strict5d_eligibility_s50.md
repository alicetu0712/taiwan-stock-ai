# Strict 5D Eligibility Matrix — Session 50

**Date:** 2026-11-10  
**Session:** S50 — PART F  
**Status:** STRICT_3_WAITING_3 (unchanged from S48/S49 since backfill not executed)

---

## Eligibility Rule

A cluster is STRICT_ELIGIBLE if its fill date has ≥ 5 TSMC-present trading days after fill date in `daily_prices`. This measures whether the market was sufficiently data-complete to trust the 5TD return calculation.

| Status | Meaning |
|---|---|
| `STRICT_ELIGIBLE` | proxy_count ≥ 5 now |
| `READY_AFTER_VERIFIED_BACKFILL` | proxy_count ≥ 5 only after P1 backfill executes |
| `WAITING_FOR_PIPELINE` | future date, pipeline hasn't run yet |
| `INSUFFICIENT_PROXY` | even after P1, proxy_count < 5 |

---

## Current Eligibility (Pre-Backfill)

| Fill Date | Exit 5TD | Proxy Count (now) | Strict Now? | Status |
|---|---|---|---|---|
| 2026-10-13 | 2026-10-20 | 7 | ✓ YES | STRICT_ELIGIBLE |
| 2026-10-14 | 2026-10-21 | 6 | ✓ YES | STRICT_ELIGIBLE |
| 2026-10-16 | 2026-10-27 | 5 | ✓ YES | STRICT_ELIGIBLE |
| 2026-10-21 | 2026-10-30 | 4 | ✗ NO | READY_AFTER_VERIFIED_BACKFILL |
| 2026-10-22 | 2026-11-02 | 3 | ✗ NO | READY_AFTER_VERIFIED_BACKFILL |
| 2026-10-28 | 2026-11-04 | 2 | ✗ NO | READY_AFTER_VERIFIED_BACKFILL |

**Strict now: 3/6 — G03 FAIL (requires 10)**

---

## Post-P1 Backfill Projections

P1 backfill = Oct 29/30/Nov 02/03 (pending AUTH01 authorization)

| Fill Date | Proxy Count (after P1) | Strict After P1? | Backfill Dates Needed |
|---|---|---|---|
| 2026-10-13 | 7 (unchanged) | ✓ YES | — |
| 2026-10-14 | 6 (unchanged) | ✓ YES | — |
| 2026-10-16 | 5 (unchanged) | ✓ YES | — |
| 2026-10-21 | 8 (+4 from Oct 29/30/Nov 02/03) | ✓ YES | Oct 29 |
| 2026-10-22 | 7 (+4) | ✓ YES | Oct 29/30 |
| 2026-10-28 | 5 (+3) | ✓ YES | Oct 29/30/Nov 02 |

**Strict after P1: 6/6 — G03 still FAIL (need 10)**

---

## Proxy Count Logic

Proxy count = number of distinct dates in `daily_prices` where:
- `date > fill_date`  
- `stock_id = '2330'` (TSMC is the proxy indicator)

This counts how many trading days have usable data AFTER the signal was generated. The minimum of 5 ensures the 5TD exit window is fully covered.

---

## G03 Status After P1 Backfill

Even with all 6 clusters becoming STRICT after P1 backfill:
- G03 requires ≥ 10 independent strict clusters
- Current: 6 clusters (after P1) → G03 FAIL
- Need 4+ more weeks of trading with daily fill dates to reach 10

**G03 is a time/data problem, not a data quality problem.**

---

## Frozen Baseline

The frozen 5D baseline (+0.81 pp) was computed on the 3 strict clusters (Oct 13/14/16) only. This baseline does NOT change with backfill or P1 completion.

Adding Oct 21/22/28 to the strict pool will produce a NEW comparison (not an update to the frozen baseline). That new comparison requires explicit authorization.

---

## References

- Module: `src/research/calendar_contract_s50.py`
- Function: `build_strict5d_eligibility_matrix()`
- Tests: `tests/test_session50_market_sources.py` TC29–TC32
- Prior: `docs/strict_5d_recovery_readiness_s49.md`
