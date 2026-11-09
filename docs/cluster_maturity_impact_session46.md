# Cluster Maturity Impact — Session 46

**Date:** 2026-11-09  
**Session:** S46 — PART C  
**Local SQLite Max:** 2026-11-05 (unchanged from S45)

---

## Key Distinction: MATURE_BUT_DATA_INCOMPLETE vs NOT_YET_MATURE

The pipeline's proxy exit-day counter (`_count_exit_days` using TSMC/2330 as proxy) gives a different signal from the actual market reality:

- **NOT_YET_MATURE**: The 5th real trading day has NOT yet occurred. Waiting for time to pass.
- **MATURE_BUT_DATA_INCOMPLETE**: The 5th real trading day HAS occurred (by calendar), but the local SQLite pipeline has not captured those intermediate dates fully (thin data = only 0050 proxy).

---

## Cluster Status by Fill Date

| Fill Date | n Signals | Calendar 5th TD | Exit in DB? | Proxy Days | Required | Category |
|---|---|---|---|---|---|---|
| Oct 13 | 46 | Oct 21 | Yes (656 stocks) | 7 | 5 | MATURE_AND_COMPLETE |
| Oct 14 | 27 | Oct 28 | Yes (656 stocks) | 7 | 5 | MATURE_AND_COMPLETE |
| Oct 16 | 55 | Nov 05 | Yes (6,589 stocks) | 7 | 5 | MATURE_AND_COMPLETE |
| Oct 21 | 39 | Oct 30 | No (1 stock) | 4 | 5 | MATURE_BUT_DATA_INCOMPLETE |
| Oct 22 | 23 | Nov 02 | No (1 stock) | 3 | 5 | MATURE_BUT_DATA_INCOMPLETE |
| Oct 28 | 19 | Nov 04 | Yes (6,957 stocks) | 2 | 5 | MATURE_BUT_DATA_INCOMPLETE |

**Calendar 5th TD derived from `TaiwanTradingCalendar` (not from DB proxy).**

---

## Impact on Strict Baseline

The proxy exit-day count (using 2330 presence in local SQLite) is what determines if a cluster is "strict" in `canonical_5d_baseline_s44.py`:
- Oct 22 fill: proxy = 3/5 → still INCOMPLETE_EXIT → not strict
- Oct 28 fill: proxy = 2/5 → still INCOMPLETE_EXIT → not strict

**The strict baseline (3 clusters) is UNCHANGED from S45.**

However, the actual 5D outcomes CAN be computed for Oct 28 fill (exit Nov 04 is in DB) and Oct 21 fill (exit Oct 30 is in Neon, not SQLite). See `prospective_comparison_session46.md`.

---

## Why Oct 28 Fill Is "MATURE_BUT_DATA_INCOMPLETE"

The true 5th real TD after Oct 28:
- Oct 29 (1st TD), Oct 30 (2nd), Nov 02 (3rd), Nov 03 (4th), **Nov 04 (5th)**

Nov 04 IS in the DB (6,957 stocks). But Oct 29/30/Nov 02/03 have only 0050 in local SQLite. So:
- Proxy counter sees: Nov 04 (1st), Nov 05 (2nd) → only 2 days
- Calendar truth: Oct 29/30/Nov 02/03/04 = 5th TD on Nov 04

The exit price (Nov 04 close for each signal stock) is available in the DB despite the low proxy count.

---

## Counts

| Category | Count |
|---|---|
| MATURE_AND_COMPLETE | 3 |
| MATURE_BUT_DATA_INCOMPLETE | 3 |
| NOT_YET_MATURE | 0 |

All 6 fill clusters have passed their 5D window as of Nov 09. Zero clusters remain in the future (NOT_YET_MATURE).
