# 20D Calendar Contract Correction — Session 48

**Date:** 2026-11-09  
**Session:** S48 — PART E (P4)  
**Verdict:** ALL_6_CLUSTERS_CORRECTED; NOT_YET_MATURE as of Nov 09

---

## Summary of Corrections

S46 `prospective_comparison_s46.py` contained `_CALENDAR_20TD` values that do not match TaiwanTradingCalendar. All 6 clusters had errors (ranging 2–7 days too late).

| Fill Date | S46 Said | Correct | Error | Explanation |
|---|---|---|---|---|
| Oct 13 | 2026-11-14 | **2026-11-12** | +2 days | TSMC-proxy instead of real TD |
| Oct 14 | 2026-11-17 | **2026-11-13** | +4 days | TSMC-proxy drift |
| Oct 16 | 2026-11-19 | **2026-11-17** | +2 days | TSMC-proxy drift |
| Oct 21 | 2026-11-24 | **2026-11-20** | +4 days | TSMC-proxy drift |
| Oct 22 | 2026-11-25 | **2026-11-23** | +2 days | TSMC-proxy drift |
| Oct 28 | 2026-12-02 | **2026-11-25** | **+7 days** | TSMC-proxy drift (largest error) |

**Earliest maturity:** 2026-11-12 (Oct 13 fill, 3 calendar days from analysis date)  
**Latest maturity:** 2026-11-25 (Oct 28 fill)

---

## 5D Date Corrections Also Required

The same TSMC-proxy mismatch affected `_CALENDAR_5TD` for Oct 13/14/16 fills:

| Fill Date | S46 Said | Correct | Error |
|---|---|---|---|
| Oct 13 | 2026-10-21 | **2026-10-20** | +1 day |
| Oct 14 | 2026-10-28 | **2026-10-21** | **+7 days** |
| Oct 16 | 2026-11-05 | **2026-10-27** | **+9 days** |
| Oct 21 | 2026-10-30 | 2026-10-30 | ✓ correct |
| Oct 22 | 2026-11-02 | 2026-11-02 | ✓ correct |
| Oct 28 | 2026-11-04 | 2026-11-04 | ✓ correct |

**Note**: The frozen baseline deltas (+0.81%) were computed from actual S43 price analysis and are not affected by these calendar date corrections. The corrections affect documentation accuracy, not the baseline numbers.

---

## Root Cause: TSMC-Proxy Date Counting

S46 likely used the `_count_exit_days()` logic (counting TSMC-present dates after fill_date) as a proxy for "which trading day is the Nth". Because TSMC was absent on many intermediate dates (Oct 15/19/20/27/29/30/Nov 02/03 — the PARTIAL_COVERAGE dates), counting "TSMC-present days" produces dates that are 1–9 days later than counting actual trading calendar days.

**Correct approach**: Use `TaiwanTradingCalendar.next_trading_day() × N` to find the Nth real trading day. This is what S47 and S48 use.

---

## 20D Maturity Matrix (as of 2026-11-09)

| Fill Date | 20TD Exit Date | Stock Count | TSMC | Maturity Status | Days Until |
|---|---|---|---|---|---|
| Oct 13 | 2026-11-12 | 0 (future) | — | NOT_YET_MATURE | 3 days |
| Oct 14 | 2026-11-13 | 0 (future) | — | NOT_YET_MATURE | 4 days |
| Oct 16 | 2026-11-17 | 0 (future) | — | NOT_YET_MATURE | 8 days |
| Oct 21 | 2026-11-20 | 0 (future) | — | NOT_YET_MATURE | 11 days |
| Oct 22 | 2026-11-23 | 0 (future) | — | NOT_YET_MATURE | 14 days |
| Oct 28 | 2026-11-25 | 0 (future) | — | NOT_YET_MATURE | 16 days |

**All 6 clusters NOT_YET_MATURE** as of analysis date (Nov 09).

---

## Manual Verification: Oct 13 Fill → 20th TD = Nov 12

Counting 20 real trading days after Oct 13 (National Day compensatory holiday Oct 09 excluded):

1. Oct 14  2. Oct 15  3. Oct 16  4. Oct 19  5. Oct 20  
6. Oct 21  7. Oct 22  8. Oct 27  ← Oct 23–26 holiday cluster  
9. Oct 28  10. Oct 29  11. Oct 30  12. Nov 02  13. Nov 03  
14. Nov 04  15. Nov 05  16. Nov 06  17. Nov 09  18. Nov 10  
19. Nov 11  **20. Nov 12** ✓

TaiwanTradingCalendar confirms: `next_trading_day(2026-10-13, 20) = 2026-11-12`.

---

## Authorization Status

**20D outcome computation is NOT AUTHORIZED in S48.**

Future authorization must specify:
- Which fill clusters to compute (all 6, or strict-only)
- Which holding-period convention (calendar TD vs price-available TD)
- How to handle partial coverage within the 20D window
- Transaction cost assumptions (current research assumption: FEES_PCT = 0.00585)

**Data requirements** when authorized:
- Nov 10, 11, 12 needed for Oct 13 fill (earliest exit)
- Nov 06, 09, 10, 11, 12 needed (some already 0 rows — pipeline restoration required)
