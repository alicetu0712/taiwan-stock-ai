# Isolated 5D Recovery Feasibility — Session 46

**Date:** 2026-11-09  
**Session:** S46 — PART D  
**Method:** Calendar-based exit dates (5th real TD per TaiwanTradingCalendar) + local SQLite prices

---

## Recovery Preconditions

A cluster is "isolated computable" if:
1. Calendar-based 5th TD is known
2. Exit date has ≥50 stocks in **local SQLite** (not just Neon)
3. All signal stocks have `execution_price` (NEXT_OPEN) in `forward_signals`
4. All signal stocks have `signal_close` for A_direct comparison

---

## Feasibility Per Cluster

| Fill Date | n Signals | Calendar Exit | Exit in Local SQLite | Feasibility |
|---|---|---|---|---|
| Oct 13 | 46 | Oct 21 | Yes (656 stocks) | ISOLATED_COMPUTABLE |
| Oct 14 | 27 | Oct 28 | Yes (656 stocks) | ISOLATED_COMPUTABLE |
| Oct 16 | 55 | Nov 05 | Yes (6,589 stocks) | ISOLATED_COMPUTABLE |
| Oct 21 | 39 | Oct 30 | No (1 stock) | ISOLATED_PENDING_NEON |
| Oct 22 | 23 | Nov 02 | No (1 stock) | ISOLATED_PENDING_NEON |
| Oct 28 | 19 | Nov 04 | Yes (6,957 stocks) | ISOLATED_COMPUTABLE |

**4 clusters: ISOLATED_COMPUTABLE from local SQLite.**  
**2 clusters: ISOLATED_PENDING_NEON (exit prices only in Neon DB).**

---

## Neon Data Access

Neon DB has 638 stocks for Oct 30 and Nov 02. If Neon read access is authorized in a future session, Oct 21 and Oct 22 fills become computable. Neon data is NOT part of the strict baseline and must be clearly labeled as an isolated research snapshot.

---

## Note on Oct 28 Fill Exit

The Oct 28 fill is ISOLATED_COMPUTABLE because Nov 04 (its calendar 5th TD) was manually backfilled with 6,957 stocks. Even though the proxy counter (`_count_exit_days`) only gives it 2/5 (since Oct 29/30/Nov 02/03 are thin), the actual exit price is available.

This demonstrates the difference between the proxy-based "strict" criterion and the calendar-based "isolated" criterion. The isolated calculation uses calendar truth; the strict baseline uses DB proxy consistency.
