# 20D Maturity Reconciliation — Session 47

**Date:** 2026-11-09  
**Session:** S47 — PART F (P5)  
**Verdict:** 20D_NOT_READY (all 6 clusters NOT_YET_MATURE)  
**Key correction:** S46 20D dates were WRONG for 5 of 6 clusters

---

## S46 Date Error Explanation

S46 `prospective_comparison_s46.py` contained `_CALENDAR_20TD` values that do not match TaiwanTradingCalendar's `nth_td_after(fill_date, 20)` output. The errors were 2–7 days LATER than the correct dates.

Likely cause: S46 may have derived 20D dates from TSMC-proxy logic (counting 20 dates where TSMC has data in SQLite after fill_date) rather than the actual trading calendar. This is the same mismatch that caused errors in S46's `_CALENDAR_5TD` for Oct 13/14/16 fills.

---

## Corrected 20D Maturity Matrix

| Fill Date | Signal Date | Exec Date | Correct 20th TD | S46 Said | S46 Error | Stock Count | Status |
|---|---|---|---|---|---|---|---|
| Oct 13 | Oct 12 | Oct 13 | **2026-11-12** | 2026-11-14 | +2 days | 0 (future) | NOT_YET_MATURE |
| Oct 14 | Oct 13 | Oct 14 | **2026-11-13** | 2026-11-17 | +4 days | 0 (future) | NOT_YET_MATURE |
| Oct 16 | Oct 14 | Oct 16 | **2026-11-17** | 2026-11-19 | +2 days | 0 (future) | NOT_YET_MATURE |
| Oct 21 | Oct 16 | Oct 21 | **2026-11-20** | 2026-11-24 | +4 days | 0 (future) | NOT_YET_MATURE |
| Oct 22 | Oct 21 | Oct 22 | **2026-11-23** | 2026-11-25 | +2 days | 0 (future) | NOT_YET_MATURE |
| Oct 28 | Oct 22 | Oct 28 | **2026-11-25** | 2026-12-02 | +7 days | 0 (future) | NOT_YET_MATURE |

**All 6 clusters NOT_YET_MATURE as of Nov 09.**  
**Earliest maturity: Nov 12** (3 trading days from analysis date, Oct 13 fill).

---

## Manual Count Verification (Oct 13 Fill)

20 trading days after Oct 13:
1. Oct 14 (Wed)
2. Oct 15 (Thu)
3. Oct 16 (Fri)
4. Oct 19 (Mon)
5. Oct 20 (Tue)
6. Oct 21 (Wed)
7. Oct 22 (Thu)
8. Oct 27 (Tue) ← after Oct 23–26 holiday cluster
9. Oct 28 (Wed)
10. Oct 29 (Thu)
11. Oct 30 (Fri)
12. Nov 02 (Mon)
13. Nov 03 (Tue)
14. Nov 04 (Wed)
15. Nov 05 (Thu)
16. Nov 06 (Fri)
17. Nov 09 (Mon)
18. Nov 10 (Tue)
19. Nov 11 (Wed)
20. **Nov 12 (Thu)** ← 20th TD

TaiwanTradingCalendar `nth_td_after(2026-10-13, 20)` = `2026-11-12` ✓

---

## 5D Date Corrections (Also From Part D)

The same TSMC-proxy vs calendar-TD mismatch affects 5th TD dates for Oct 13/14/16 fills:

| Fill Date | Correct 5th Calendar TD | S46 Said | Available Data on Correct TD |
|---|---|---|---|
| Oct 13 | **Oct 20** | Oct 21 | 1 stock (PARTIAL) |
| Oct 14 | **Oct 21** | Oct 28 | 655 stocks (COMPLETE) |
| Oct 16 | **Oct 27** | Nov 05 | 1 stock (PARTIAL) |
| Oct 21 | Oct 30 | Oct 30 ✓ | 1 stock (PARTIAL) |
| Oct 22 | Nov 02 | Nov 02 ✓ | 1 stock (PARTIAL) |
| Oct 28 | Nov 04 | Nov 04 ✓ | 6,957 stocks (COMPLETE) |

The frozen baseline deltas (+0.81% from S43) were computed using the actual prices available at the time — the specific exit date used in the S42 bash analysis is not documented here. The corrections above represent the **calendar-based** 5th TD, which may differ from what S42 used.

---

## 20D Data Requirements

For 20D outcome computation (when authorized):
- Exit prices needed: Nov 12–25 for different clusters
- DB currently has data through Nov 05; Nov 06–25 not yet captured
- Full pipeline restoration required for Nov 06+
- Minimum data needed: at least Nov 06, Nov 09, Nov 10, Nov 11, Nov 12 for first cluster

---

## Authorization Status

20D outcome computation was NOT authorized in S44/S45/S46/S47.

Future authorization (AUTH01 + AUTH02) must specify:
- Which fill clusters to compute
- Which holding-period convention to use (calendar TD vs proxy-based)
- How to handle partial coverage dates within the 20D window
- Transaction cost assumptions

**20D_NOT_READY until all 6 clusters reach their exit dates AND pipeline is restored.**
