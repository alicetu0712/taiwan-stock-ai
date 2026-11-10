# 20D Data Readiness & AUTH02 Gate — Session 59

**Date**: 2026-11-10  
**Overall Verdict**: 20D_DATA_BLOCKED  
**AUTH02 Status**: NOT_AUTHORIZED

---

## Cluster Summary

| Cluster | Exec Dates | Signals | Exit Dates (est.) | DB Max | Readiness |
|---------|-----------|---------|-------------------|--------|-----------|
| Oct13-16 | Oct13/14/16 | 1,091 | Nov12–16 | 2026-11-05 | DATA_BLOCKED |
| Oct21-22 | Oct21/22 | 563 | Nov19–21 | 2026-11-05 | NOT_YET_MATURE |
| Oct28 | Oct28 | 323 | Nov26–Dec01 | 2026-11-05 | NOT_YET_MATURE |
| **Total** | | **1,977** | | | |

`fwd_return_20d` = NULL for all 1,977 signals. No 20D outcomes computed (AUTH02 not authorized).

---

## Oct13-16 Cluster Details

**Signals**: 1,091  
**Execution dates**: 2026-10-13 (348), 2026-10-14 (387), 2026-10-16 (356)  
**Entry prices**: ALL present (`execution_price` populated for all 1,091)  
**Exit dates** (20 trading days from each exec date):
- Oct13 + 20TD → ~2026-11-12
- Oct14 + 20TD → ~2026-11-13
- Oct16 + 20TD → ~2026-11-16

**Problem**: DB max date = 2026-11-05. Exit dates (Nov12+) are **not yet in `daily_prices`**. Even if AUTH02 were authorized today, exit prices do not exist in the DB.

**Readiness**: DATA_BLOCKED (double blocker — see below)

---

## Oct21-22 Cluster Details

**Signals**: 563  
**Execution dates**: 2026-10-21 (261), 2026-10-22 (302)  
**Exit dates**: ~2026-11-19 to 2026-11-21  
**Readiness**: NOT_YET_MATURE — exit date ~2 weeks beyond DB max

---

## Oct28 Cluster Details

**Signals**: 323  
**Execution dates**: 2026-10-28 (323)  
**Exit dates**: ~2026-11-26 to 2026-12-01  
**Readiness**: NOT_YET_MATURE — exit date ~3–4 weeks beyond DB max

---

## Double Blocker Analysis (Oct13-16 Cluster)

Both blockers must be resolved before the Oct13-16 20D outcomes can be computed:

| Blocker | Description | Resolution |
|---------|-------------|------------|
| **Blocker 1** | AUTH02 NOT AUTHORIZED | Explicit user authorization required |
| **Blocker 2** | `daily_prices` max = Nov05; exit prices for Nov12+ not in DB | Pipeline recovery must extend to Nov12 (requires AUTH01) |

Resolving one blocker without the other is insufficient. Both must be resolved in sequence:
1. AUTH01 (pipeline recovery through Nov12)
2. AUTH02 (20D computation authorization)

---

## Nov12 Is Not a Hard Deadline

Nov12 is the **20TD exit date**, not an expiry for the analysis.

- If `daily_prices` is eventually backfilled through Nov12 and AUTH02 is authorized, the 20D return computation remains valid.
- The entry used NEXT_OPEN execution (prices known at trade time), so the outcome is a genuine forward-looking measurement even if computed after the exit date.
- Minor consideration: corporate actions or delistings occurring between Oct13 and Nov12 would require adjustment, but this is a data quality concern, not a validity issue.

**Binding constraint**: AUTH02 authorization (not the calendar date).

---

## AUTH02 Scope Definition

If authorized, the 20D computation for Oct13-16 cluster would:

1. **Query**: For each of 1,091 signals, fetch `execution_price` from `forward_signals` and `close` from `daily_prices` at the 20TD exit date for that stock.
2. **Calculate**:
   - `signal_return = (exit_close - execution_price) / execution_price`
   - `benchmark_return = (0050_exit_close - 0050_exec_close) / 0050_exec_close`
   - `fwd_return_20d = signal_return`
   - `alpha_20d = signal_return - benchmark_return`
3. **Write**: Update `fwd_return_20d` and `alpha_20d` in `forward_signals` for affected rows.
4. **Scope**: Oct13-16 signals only (1,091 rows). Does not affect v8.0 historical signals.

**NOT AUTHORIZED** — this description is for planning purposes only.

---

## Authorization Requirements

| Item | Required | Status |
|------|----------|--------|
| AUTH02 explicit authorization | Yes | NOT_AUTHORIZED |
| `daily_prices` populated through Nov12 | Yes | BLOCKED (AUTH01 needed) |
| AUTH01 (pipeline recovery) | Yes (prerequisite) | NOT_AUTHORIZED |
| TWSE compliance confirmation | Yes (AUTH01 prerequisite) | NOT_STARTED |
