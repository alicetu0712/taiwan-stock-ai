# TPEx Parser Patch — Verification Session 59

**Date**: 2026-11-10  
**Status**: PARSER_PATCH_PARTIAL — PP-01/PP-02 HIGH confidence, PP-03 HYPOTHESIS  
**Deployment**: NOT_AUTHORIZED (PRINT_ONLY_CONFIRMED)

---

## Patch Bundle Overview

Three patches identified. None deployed to production.

| ID | Description | File | Line | Confidence | Status |
|----|-------------|------|------|------------|--------|
| PP-01 | Warrant ID exclusion fix | `scripts/backfill_daily_prices.py` | 98 | HIGH | NOT_AUTHORIZED |
| PP-02 | TPEx volume field: `TradeVolume` → `TradingShares` | `scripts/backfill_daily_prices.py` | 284 | HIGH | NOT_AUTHORIZED |
| PP-03 | TPEx amount field: `TradeValue` → `TransactionAmount` | `scripts/backfill_daily_prices.py` | 285 | MEDIUM (HYPOTHESIS) | NOT_AUTHORIZED |

---

## PP-01: Warrant ID Exclusion

**Function**: `_is_excluded()`  
**Line**: 98

```python
# Original:
if len(sid) > 4 and not sid.isdigit():
    return True

# Patched:
if len(sid) > 4:
    return True
```

**Why**: 6-digit pure-numeric warrant IDs (e.g., `700022`) satisfy `len > 4` but fail `not sid.isdigit()` → not excluded → enter pipeline with NULL volume. The fix removes the `isdigit` guard.

**Confidence**: HIGH — logic error is unambiguous.

**Side effects**:  
- Any ID longer than 4 characters is excluded, regardless of content.  
- 5-digit ETF codes (e.g., `00631L`) are already 6 characters and have letters → still excluded correctly.  
- Must verify: no legitimate 5-digit numeric ordinary stocks exist. Current research universe uses 4-digit IDs only.

---

## PP-02: TradingShares Volume Field

**Function**: `fetch_tpex_historical()`  
**Line**: 284

```python
# Original:
vol_raw = _strip_num(str(row.get("TradeVolume", "")))

# Patched:
vol_raw = _strip_num(str(row.get("TradingShares", "")))
```

**Evidence chain**:
1. S58 WebFetch of live TPEx bulk endpoint (Nov04 probe) returned field `"TradingShares"` explicitly in JSON payload — DIRECTLY_CONFIRMED.
2. Cross-check: `open/high/low/close` are non-NULL for the same rows, confirming the OHLC field names are correct; only `volume` is NULL → isolated field name bug.
3. TWSE uses `TradeVolume` (correct for TWSE); TPEx uses different field names throughout its API.

**Confidence**: HIGH — DIRECTLY_CONFIRMED from live payload.

**Side effects**: Affects only `fetch_tpex_historical()`. TWSE parsers use `TradeVolume` (correct). Volume unit unchanged: ÷ 1,000.

---

## PP-03: Amount Field (HYPOTHESIS)

**Function**: `fetch_tpex_historical()`  
**Line**: 285

```python
# Original:
amt_raw = _strip_num(str(row.get("TradeValue", "")))

# Patched (HYPOTHESIS):
amt_raw = _strip_num(str(row.get("TransactionAmount", "")))
```

**Evidence**: HYPOTHESIS only. S58 WebFetch confirmed `TradingShares` for volume but did not verify the amount field name. `TransactionAmount` is the assumed TPEx equivalent of TWSE's `TradeValue`.

**Confidence**: MEDIUM — needs live probe to confirm field name.

**Risk**: If the field name is different (e.g., `TradeValue` or another variant), the patch would not fix the amount NULL issue, or could introduce a regression if `TransactionAmount` doesn't exist.

**Recommended**: Run one targeted WebFetch of TPEx API response to confirm amount field name before including PP-03 in deployment.

---

## Isolated Schema Compatibility Tests

10 test scenarios executed on a patched parser in isolated environment. No production writes.

| # | Scenario | Expected | Result |
|---|----------|----------|--------|
| 1 | `TradingShares` valid | volume = raw/1000 | PASS |
| 2 | `TradeVolume` present (TWSE field) | volume = NULL (TPEx ignores it) | PASS |
| 3 | Both fields present | uses `TradingShares` | PASS |
| 4 | No volume fields | volume = NULL | PASS |
| 5 | Null volume placeholder | volume = NULL | PASS |
| 6 | Zero volume | volume = 0.0 | PASS |
| 7 | Negative volume (invalid) | volume = -1.0 (rejected upstream) | PASS |
| 8 | Comma-separated numeric | volume = parsed correctly | PASS |
| 9 | Dash placeholder (non-trading) | volume = NULL | PASS |
| 10 | `TransactionAmount` valid | amount = raw/1,000,000 | PASS |

All 10 PASS.

---

## Repair Simulation Results

4 scenarios on isolated temporary SQLite (not production DB):

| ID | Scenario | Result |
|----|----------|--------|
| RS-01 | UPDATE NULL volume to verified value | PASS — volume updated correctly |
| RS-02 | Idempotency — `WHERE volume IS NULL` guard | PASS — second UPDATE does nothing |
| RS-03 | TWSE stock untouched by TPEx repair | PASS — 2330 volume unchanged |
| RS-04 | Transaction ROLLBACK restores original | PASS — rollback verified |

All 4 PASS. Production DB not modified.

---

## Deployment Authorization Status

**Current state**: PRINT_ONLY_CONFIRMED  
The existing L500-501 TPEx api_date mismatch handler uses `print()` only — error is not propagated to `summary["errors"]`. This is a confirmed pre-existing issue, not introduced by S59.

**To deploy the patch bundle**:
1. Explicit user authorization required
2. PP-03 amount field should be verified via live probe first
3. After deployment, run one backfill dry-run to confirm warrant rows are excluded
4. Re-run full regression to confirm no regressions

No deployment occurred in S59.

---

## Risk Assessment

| Risk | Patches Affected | Severity | Mitigation |
|------|-----------------|----------|------------|
| ETF exclusion broken | PP-01 | LOW | 5-digit ETF IDs contain letters (e.g., `00631L`) → still excluded by `len > 4` |
| Amount field wrong | PP-03 | MEDIUM | Verify `TransactionAmount` name via one live probe before deploying |
| TWSE parser regression | PP-02 | NONE | PP-02 only modifies `fetch_tpex_historical()`, not TWSE paths |
| Historical rows not repaired | All | INFO | Patch fixes future fetches; historical repair requires separate authorized backfill |
