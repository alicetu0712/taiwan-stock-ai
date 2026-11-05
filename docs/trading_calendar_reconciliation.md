# Trading Calendar Reconciliation — 2026 Q3/Q4

**Date:** 2026-11-05  
**Status:** COMPLETE — 3 calendar errors identified and corrected

---

## Background

`TaiwanTradingCalendar` in `src/core/trading_calendar.py` maintains a hardcoded set of  
TWSE market closure dates. During OHLC continuity gate investigation, comparison against  
the TWSE official FMTQIK monthly trading summary revealed three dates were missing from  
`_TWSE_HOLIDAYS`.

---

## Reconciliation Method

**Source of truth:** TWSE FMTQIK API  
`https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK?response=json&date=YYYYMMDD&type=MS`

This API returns the official monthly market volume summary, listing only actual trading days.  
Dates absent from the FMTQIK response (but that would otherwise be weekday business days)  
are confirmed TWSE market closures.

---

## Errors Found

### Error 1: 2026-09-28 — 中秋節後補假

| Attribute | Value |
|-----------|-------|
| Calendar (before fix) | TRADING_DAY |
| TWSE FMTQIK September 2026 | 09-28 absent |
| Root cause | 中秋節 falls on 09-25; 09-28 (Monday) is bridge holiday |
| Resolution | Added `date(2026, 9, 28)` to `_TWSE_HOLIDAYS` |

### Error 2: 2026-10-23 — 颱風閉市

| Attribute | Value |
|-----------|-------|
| Calendar (before fix) | TRADING_DAY |
| TWSE FMTQIK October 2026 | 10-23 and 10-24 absent |
| Root cause | Typhoon forced TWSE market closure (official government announcement) |
| Resolution | Added `date(2026, 10, 23)` to `_TWSE_HOLIDAYS` |
| Note | 10-24 is Saturday — already a weekend, no entry needed |

### Error 3: 2026-10-26 — 颱風橋接假

| Attribute | Value |
|-----------|-------|
| Calendar (before fix) | TRADING_DAY |
| TWSE FMTQIK October 2026 | 10-26 absent |
| Root cause | Monday bridge holiday following the 10-23/10-24 typhoon closure |
| Resolution | Added `date(2026, 10, 26)` to `_TWSE_HOLIDAYS` |

---

## 2026-10-09 Confirmed Correct

The existing `date(2026, 10, 9)` holiday entry was **correct**.  
- 10-10 (Saturday) = 國慶日; 10-09 (Friday) = compensatory holiday
- FMTQIK October 2026 confirms 10-09 is absent
- DB had 7,586 rows dated 2026-10-09 — these were mislabeled 2026-10-07 data (confirmed by OHLC value cross-check)
- All 7,586 rows were deleted as part of OHLC recovery

---

## Calendar State After Fix

```python
# In _TWSE_HOLIDAYS (2026 section) — entries relevant to this reconciliation:
date(2026, 9, 25),   # 中秋節 (pre-existing)
date(2026, 9, 28),   # 中秋節後補假 ← NEW
date(2026, 10, 9),   # 國慶日補假 (pre-existing, confirmed correct)
date(2026, 10, 23),  # 颱風閉市 ← NEW
date(2026, 10, 26),  # 颱風閉市橋接假 ← NEW
```

---

## Impact on Tests

Two `test_effective_trade_date.py` tests used 2026-10-26 (now a holiday) as a "Monday trading day" example.  
These were updated to use 2026-10-19 (Monday, confirmed trading day).

Five new hybrid cron tests (HC28, HC29) explicitly verify the new holiday entries.

---

## Downstream Effects

| System | Effect |
|--------|--------|
| `TaiwanTradingCalendar.is_trading_day()` | Now returns False for 09-28, 10-23, 10-26 |
| `OHLCContinuityGate` | 09-28, 10-23, 10-26 now classified as MARKET_CLOSED, not EXPECTED_DATA_MISSING |
| `hybrid_shadow_cron.py` | Will correctly skip those days |
| `effective_trade_date()` | Falls back to 10-22 when called on 10-26 morning |
| Test suite | 1594 tests PASS |

---

## Verification

```
_cal = TaiwanTradingCalendar()
_cal.is_trading_day(date(2026, 9, 28))  → False
_cal.is_trading_day(date(2026, 10, 23)) → False
_cal.is_trading_day(date(2026, 10, 26)) → False
_cal.is_trading_day(date(2026, 10, 9))  → False  (pre-existing, confirmed)
_cal.is_trading_day(date(2026, 11, 5))  → True   (trading day, data confirmed)
```
