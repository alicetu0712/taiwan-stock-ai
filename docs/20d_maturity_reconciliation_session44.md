# 20D Outcome Maturity Reconciliation — Session 44

**Date:** 2026-11-09  
**Session:** S44  
**Module:** `src/research/maturity_reconciliation_20d_s44.py`  
**Verdict:** NOT_READY_FOR_20D

---

## Purpose

Reconciles the ETA discrepancy between prior sessions and establishes the canonical maturity timeline for 20D outcome analysis.

---

## Maturity Status by Fill Cluster

| Fill Date | Signal Dates | v8.0 n | TD Available (as of Nov 05) | Need | ETA | Confidence |
|---|---|---|---|---|---|---|
| Oct 13 | Oct 12 | 46 | 7 | 13 more | ~2026-11-24 | MEDIUM |
| Oct 14 | Oct 13 | 27 | 6 | 14 more | ~2026-11-25 | MEDIUM |
| Oct 16 | Oct 14 | 55 | 5 | 15 more | ~2026-11-26 | LOW |
| Oct 21 | Oct 16 | 39 | 4 | 16 more | ~2026-11-28 | LOW |
| Oct 22 | Oct 21 | 23 | 3 | 17 more | ~2026-12-02 | LOW |

**Current status as of 2026-11-09:** All clusters NOT_YET_MATURE.

---

## ETA Discrepancy Reconciliation

**Question:** Why did S43 estimate Nov 25 while earlier sessions estimated Dec 02?

**Root cause:** Two different counting methods were used:

| Method | Approach | Fill Oct 13 ETA |
|---|---|---|
| S43 (TSMC-specific) | Count TSMC (2330) trading days after Oct 13; needed 20; had 7 → ~Nov 24–26 | ~Nov 25 |
| Earlier sessions | Calendar-day approximation: execution_date + 28 calendar days | ~Dec 02 |

**Canonical answer:** ~Nov 24–26 for fill Oct 13, based on stock-specific trading day count. The calendar-day method overestimates by ~1 week (20 trading days < 28 calendar days in Taiwan market).

---

## Authorization Constraint

> This session (S44) is NOT authorized to compute or write 20D outcomes.  
> Even if clusters become mature, computation must be explicitly authorized in a future session.

---

## Daily Price Coverage

As of 2026-11-05, `daily_prices.max(date)` = 2026-11-05 (6,589 stocks). Data pipeline must continue running daily to reach the Nov 24 threshold.
