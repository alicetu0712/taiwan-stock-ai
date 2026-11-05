# OHLC Continuity Audit — 2026-11 Session

**Date:** 2026-11-05  
**Gate Status for 2026-11-05:** BLOCKED_MISSING_OHLC

---

## Purpose

Before the first prospective Hybrid signal can be generated, the system must
confirm that the last 30 expected trading days all have 0050 data in the local
SQLite DB. This document records the audit result.

---

## Full 30-Day Window: 2026-10-07 → 2026-11-05

Expected trading days per TaiwanTradingCalendar. Status per 0050 presence in
`data/platform.db`.

| Date       | Calendar Status | DB Data | Classification            |
|------------|-----------------|---------|---------------------------|
| 2026-10-07 | Trading Day     | ✅      | DATA_AVAILABLE            |
| 2026-10-08 | Trading Day     | ✅      | DATA_AVAILABLE            |
| 2026-10-09 | Holiday (補假)  | ✅      | UNKNOWN (calendar error)  |
| 2026-10-12 | Trading Day     | ✅      | DATA_AVAILABLE            |
| 2026-10-13 | Trading Day     | ✅      | DATA_AVAILABLE            |
| 2026-10-14 | Trading Day     | ✅      | DATA_AVAILABLE            |
| 2026-10-15 | Trading Day     | ❌      | EXPECTED_DATA_MISSING     |
| 2026-10-16 | Trading Day     | ✅      | DATA_AVAILABLE            |
| 2026-10-19 | Trading Day     | ❌      | EXPECTED_DATA_MISSING     |
| 2026-10-20 | Trading Day     | ❌      | EXPECTED_DATA_MISSING     |
| 2026-10-21 | Trading Day     | ✅      | DATA_AVAILABLE            |
| 2026-10-22 | Trading Day     | ✅      | DATA_AVAILABLE            |
| 2026-10-23 | Trading Day     | ❌      | EXPECTED_DATA_MISSING     |
| 2026-10-26 | Trading Day     | ❌      | EXPECTED_DATA_MISSING     |
| 2026-10-27 | Trading Day     | ❌      | EXPECTED_DATA_MISSING     |
| 2026-10-28 | Trading Day     | ✅      | DATA_AVAILABLE            |
| 2026-10-29 | Trading Day     | ❌      | EXPECTED_DATA_MISSING     |
| 2026-10-30 | Trading Day     | ❌      | EXPECTED_DATA_MISSING     |
| 2026-10-31 | Weekend         | —       | MARKET_CLOSED             |
| 2026-11-01 | Weekend         | —       | MARKET_CLOSED             |
| 2026-11-02 | Trading Day     | ❌      | EXPECTED_DATA_MISSING     |
| 2026-11-03 | Trading Day     | ❌      | EXPECTED_DATA_MISSING     |
| 2026-11-04 | Trading Day     | ✅      | DATA_AVAILABLE            |
| 2026-11-05 | Trading Day     | ❌      | EXPECTED_DATA_MISSING     |

**Missing sessions: ≥10 (gate: BLOCKED_MISSING_OHLC)**  
**Unknown sessions: 1 (2026-10-09 — does not block)**

---

## Calendar Discrepancy: 2026-10-09

TaiwanTradingCalendar lists `date(2026, 10, 9)` as `國慶日補假`.  
However 0050 (and 7,586 other stocks) have data for that date in the DB.  
Empirical data confirms the market was open. The calendar entry is an error.  
Classification: UNKNOWN — does **not** block gate.

Action: `src/core/trading_calendar.py` should be updated to remove 2026-10-09
from `_TWSE_HOLIDAYS` and add it to covered trading days. Tracked separately.

---

## Why Gate Blocks Until ~30 Clean Consecutive Days

MA20_SLOPE requires 30 consecutive closes (MA20 at current + MA20 10 bars ago).
REGIME window also requires 30 bars of 0050. If any bar in those 30 is missing,
the computed slope or regime would silently use non-consecutive days, producing
incorrect values.

Gate will pass approximately **6 weeks** after daily cron begins running cleanly,
assuming no further backfill gaps.

---

## Feature Audit

| Feature      | Required Bars | Available (2026-11-05) | Missing | Gate Result          |
|--------------|---------------|------------------------|---------|----------------------|
| MA20         | 20            | ~10                    | ≥10     | BLOCKED_MISSING_OHLC |
| MA20_SLOPE   | 30            | ~10                    | ≥10     | BLOCKED_MISSING_OHLC |
| REGIME_MA30  | 30            | ~10                    | ≥10     | BLOCKED_MISSING_OHLC |

---

## Recovery Path

Option A — Historical backfill (if TWSE data available):
```
python3 scripts/backfill_daily_prices.py --start-date 2026-10-15 --execute
python3 scripts/run_hybrid_forward_shadow.py
```

Option B — Wait for cron accumulation (~6 weeks from first clean day):
- Each day cron runs successfully adds one clean bar.
- Gate will PASS once 30 consecutive expected trading days all have 0050 data.
