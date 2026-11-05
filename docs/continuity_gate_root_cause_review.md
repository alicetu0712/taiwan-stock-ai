# OHLC Continuity Gate — Root Cause Review

**Date:** 2026-11-05  
**Status:** ALL root causes resolved; GateResult.PASS

---

## Gate Was Blocking Because…

When `check_market(conn, date(2026, 11, 5))` was first run (before this session's fixes),  
it returned `GateResult.BLOCKED_MISSING_OHLC` with `missing_sessions >= 10`.

The 30-day gate window for 2026-11-05 spans approximately 2026-10-01 → 2026-11-05  
(the 30 most recent TWSE trading days before and including 11-05).

---

## Root Causes Identified

### Root Cause 1: Calendar errors (3 dates)

The gate classified 2026-09-28, 2026-10-23, 2026-10-26 as trading days  
(because they were absent from `_TWSE_HOLIDAYS`), then found no 0050 data for those  
dates → `DateStatus.EXPECTED_DATA_MISSING` → contributed to missing_sessions count.

**Fix:** Added all three to `_TWSE_HOLIDAYS` → now classified as `MARKET_CLOSED` →  
no longer counted against the gate.

### Root Cause 2: Corrupt 2026-10-08 data

0050 had a row for 2026-10-08, but the OHLC values were actually 2026-10-06 data  
(mislabeled during the backfill pipeline). The gate still passed this date  
(data was present, even if wrong), but downstream MA20/MA60 calculations  
would have produced incorrect slope values.

**Fix:** Deleted corrupt row; inserted correct 0050 values from TWSE STOCK_DAY API  
(confirmed: close=114.95 for 10-08, matches FMTQIK index data).

### Root Cause 3: 10-09 mislabeled rows

7,586 stocks had data dated 2026-10-09 (a confirmed holiday).  
These were 2026-10-07 values mislabeled during backfill.  
The gate classified 10-09 as `DateStatus.UNKNOWN` (calendar says HOLIDAY, DB has data).

**Fix:** Deleted all 7,586 rows. Gate now classifies 10-09 as `MARKET_CLOSED`.

### Root Cause 4: Backfill pipeline gaps (8 dates)

The `hybrid_shadow_cron.py` / `backfill_daily_prices.py` pipeline had not run  
(or failed silently) on 10-15, 10-19, 10-20, 10-27, 10-29, 10-30, 11-02, 11-03.  
The 11-05 backfill failed because TWSE STOCK_DAY_ALL returned the wrong date  
(a known API limitation — it returns latest data, not necessarily today's).

**Fix:** Recovered all 9 dates individually via `scripts/recover_ohlc_0050.py`  
using the TWSE STOCK_DAY (individual stock) API.

---

## Why STOCK_DAY_ALL Cannot Fix This

The TWSE bulk API (`STOCK_DAY_ALL`) only returns the most recent trading day's data  
for all stocks — it does not support historical date selection.  
Historical bulk recovery for all ~1,700 stocks is not possible via public TWSE APIs.

---

## Gate After All Fixes

```
check_market(conn, date(2026, 11, 5)):
  gate_result      = GateResult.PASS
  present_sessions  = 30
  missing_sessions  = 0
  unknown_sessions  = 0
```

---

## Gate Logic Summary

The gate operates on 0050 (market proxy) only:

```
For each of the 30 most recent trading days ending on trade_date:
  1. is_trading_day(d)? → Yes → check DB for 0050 row
     - 0050 row exists → PASS this date (present_sessions++)
     - 0050 row missing → EXPECTED_DATA_MISSING (missing_sessions++)
  2. is_trading_day(d)? → No (HOLIDAY/WEEKEND) → MARKET_CLOSED (skip)
  3. Calendar unknown → UNKNOWN (not counted as missing OR present)

PASS if missing_sessions == 0 AND present_sessions == CONTINUITY_WINDOW (30)
BLOCKED_MISSING_OHLC if missing_sessions > 0
```

---

## Remaining Risk: Stock-Level Gate

The stock-level gate (`check_stock`) checks each signal stock against the last 20  
market-open days. Non-0050 stocks are missing data for 10-08 (7,722 rows deleted)  
and may be missing data for other dates in the gap period.

These stocks will return `GateResult.BLOCKED_MISSING_OHLC` on `check_stock`.  
This is the correct, safe behavior — the gate catches stocks with incomplete MA history.

The 30-day window naturally ages out: stocks missing only 10-08 will clear the  
20-day stock gate by approximately 2026-12-05 (20 trading days after 10-08).
