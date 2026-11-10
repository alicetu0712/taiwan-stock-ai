# Warrant Exclusion Patch — Session 60 (PP-01-REVISED)

## Status: NOT_AUTHORIZED

This patch has not been deployed. Explicit authorization is required before any change is made to the production pipeline.

## Bug Anatomy

**File:** `scripts/backfill_daily_prices.py`
**Function:** `_is_excluded(name, stock_id)`
**Line:** 98

**Current (buggy) code:**
```python
if len(sid) > 4 and not sid.isdigit():
    return True
```

**Intended behavior:** Exclude any stock ID longer than 4 characters (warrants, ETFs).

**Actual behavior:** Only excludes IDs longer than 4 characters that contain non-digit characters. Pure-numeric IDs (all Taiwan warrants use `7xxxxx` and ETFs use `00xxx`/`006xxx`) pass the `isdigit()` check and are NOT excluded.

## Exact Diff

```diff
-    if len(sid) > 4 and not sid.isdigit():
+    if len(sid) > 4:
```

One character removal. The `and not sid.isdigit()` clause is deleted entirely.

## Call Sites Affected

The `_is_excluded()` function is called at three locations:

| Line | Context |
|------|---------|
| 125 | TWSE bulk fetch loop |
| 214 | TWSE single-stock fetch loop |
| 273 | TPEx bulk fetch loop |

All three call sites are fixed by this single function-body change.

## Securities Excluded Going Forward (after patch)

- 7xxxxx warrants (len=6, all digits)
- 00xxx ETFs (len=5, all digits: 00858, 00877, 00886, 00887, 00888, 00928, 00955)
- 006xxx ETFs (len=6, all digits: 006201, 009806–009825 range)
- Any future 5-digit or 6-digit alphanumeric IDs (already excluded by old logic, unchanged)

## Securities NOT Affected

- 4-digit TWSE ordinary stocks (len=4 ≤ 4, condition never triggers)
- 4-digit TPEx ordinary stocks (same)
- `EXCLUDE_KEYWORDS` name-based check (first condition in function, unchanged)

## Effect on Historical Rows

**None.** The patch prevents future insertions. Existing warrant/ETF rows in `daily_prices` are not deleted by this patch. If deletion of historical warrant rows is desired, it requires a separate authorized migration step.

## False Positive Risk

LOW. The patch would incorrectly exclude a future ordinary stock that happened to receive a 5-digit or 6-digit ID. No such stock ID format exists in the Taiwan market system today. TWSE and TPEx ordinary stocks uniformly use 4-digit codes.

## False Negative Risk

NONE. All 4-digit ordinary stocks (len=4) do not trigger the `len(sid) > 4` condition. They continue to be inserted correctly.

## Backward Compatibility

BACKWARD_COMPATIBLE. No schema changes. No signal changes. No effect on existing data.

## Authorization Status

NOT_AUTHORIZED. This patch must not be deployed without explicit, independent authorization from the authorized reviewer. The Session 60 research prompt does not constitute authorization.
