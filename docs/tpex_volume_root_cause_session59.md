# TPEx NULL Volume Root Cause — Session 59

**Date**: 2026-11-10  
**Previous Session**: S58  
**Status**: ROOT_CAUSE_CONFIRMED

---

## Executive Summary

Session 59 forensics confirmed two distinct bugs causing 129,636 NULL volume rows in `daily_prices`. This corrects S58's erroneous reference of "5,737 NULL volume rows."

| Bug | ID | Rows | Confidence |
|-----|----|------|------------|
| Warrant ID not excluded by `_is_excluded` | RC-59-01 | 107,765 | HIGH |
| TPEx field name mismatch (`TradeVolume` vs `TradingShares`) | RC-59-02 | 21,846 | HIGH |
| Other / TWSE in-table minor | RC-59-03 | 25 | LOW |
| **Total** | | **129,636** | |

No production changes were made. All fixes require explicit authorization.

---

## S58 Reference Correction

S58 cited "5,737 NULL volume rows" and "RC-03: volume=NULL ALL 5737 records." This was incorrect.

**Origin of 5,737**: S57 ran a live probe of the TPEx bulk endpoint on a specific date and received 5,737 rows in the response. That count represented a single bulk API response, not production NULL volume.

**Actual production NULL volume**: 129,636 rows, confirmed by direct DB query in S59:
```sql
SELECT COUNT(*) FROM daily_prices WHERE volume IS NULL;
-- Result: 129,636
```

---

## Root Cause 1: Warrant ID Exclusion Bug (RC-59-01)

**Affected rows**: 107,765  
**Stock IDs**: 6-digit pure numeric (e.g., 700022, 710045, 720011)  
**File**: `scripts/backfill_daily_prices.py`  
**Line**: 98

### Bug

```python
# Original (BROKEN):
if len(sid) > 4 and not sid.isdigit():
    return True
```

For ID `"700022"`:
- `len("700022") > 4` → `True`
- `not "700022".isdigit()` → `not True` → `False`
- `True and False` → `False` → **not excluded**

Warrant IDs enter the pipeline, their volume field is populated as NULL (TPEx returns no meaningful volume for warrants), and they are stored with `volume=NULL`.

### Fix (NOT AUTHORIZED)

```python
# Patched (PP-01):
if len(sid) > 4:
    return True
```

This excludes any stock ID longer than 4 characters. Side effect: must verify 5-digit ETF IDs (00xxx) are handled correctly elsewhere.

### Evidence

- DB query: `SELECT COUNT(*) FROM daily_prices WHERE volume IS NULL AND LENGTH(stock_id)=6 AND stock_id GLOB '[0-9]*'` → 107,765
- Sample IDs confirmed: 700022, 710045, 720011 (pure 6-digit numeric = warrant format)
- Stocks table: these IDs do not appear (warrants excluded from research universe)

---

## Root Cause 2: TPEx Field Name Mismatch (RC-59-02)

**Affected rows**: 21,846  
**Stock IDs**: 4-digit numeric TPEx ordinary stocks (e.g., 1240, 1259, 1264)  
**File**: `scripts/backfill_daily_prices.py`  
**Line**: 284

### Bug

```python
# Original (BROKEN):
vol_raw = _strip_num(str(row.get("TradeVolume", "")))
```

TPEx API (`https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes`) returns field name `TradingShares`, not `TradeVolume`. `row.get("TradeVolume", "")` returns `""` → `_strip_num("")` returns `None` → stored as `NULL`.

### Fix (NOT AUTHORIZED)

```python
# Patched (PP-02):
vol_raw = _strip_num(str(row.get("TradingShares", "")))
```

### Evidence

- S58 WebFetch of live TPEx bulk response: field `"TradingShares"` explicitly present in payload (DIRECTLY_CONFIRMED)
- Cross-check: 21,846 4-digit NULL stocks have `volume=NULL AND amount=NULL` but `open/high/low/close` all present (0 NULL) — confirms field mismatch affects only volume/amount columns
- `change_pct` present for 21,621/21,846 rows — confirms OHLC parsing works, only volume field name is wrong

---

## Distribution Analysis

| Property | Value |
|----------|-------|
| Total NULL volume rows | 129,636 |
| Distinct dates with NULL | 25 |
| Date range | Jun 2026 – Nov 2026 |
| 2024 NULL rows | 0 |
| 2025 NULL rows | 0 |
| Nov04/05 included | Yes |

**Why only 2026**: The backfill script's TPEx path was not executed for 2024–2025 historical dates. TPEx data collection began in mid-2026. All NULL rows are confined to dates where TPEx fetching occurred.

**Why only 25 dates**: Backfill was run selectively, not continuously.

---

## Volume Unit Semantics

Both TWSE and TPEx store volume in 千股 (thousands of shares):

| Exchange | Raw Field | Divisor | DB Unit |
|----------|-----------|---------|---------|
| TWSE | `TradeVolume` | ÷ 1,000 | 千股 |
| TPEx (post-fix) | `TradingShares` | ÷ 1,000 | 千股 |

No unit mismatch exists between exchanges. The only issue is the field name. Post-fix volume values will be consistent with TWSE storage standard.

---

## Authorization Status

| Action | Status |
|--------|--------|
| Deploy PP-01 (warrant exclusion) | NOT_AUTHORIZED |
| Deploy PP-02 (TradingShares volume) | NOT_AUTHORIZED |
| Deploy PP-03 (amount field — HYPOTHESIS) | NOT_AUTHORIZED |
| Repair historical NULL rows in production | NOT_AUTHORIZED |
| Repair historical NULL rows in Neon | NOT_AUTHORIZED |

No production SQLite or Neon DB was modified in S59. All forensics used read-only queries.
