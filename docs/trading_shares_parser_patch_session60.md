# TradingShares Parser Patch — Session 60 (PP-02 / PATCH-3)

## Status: NOT_AUTHORIZED

PP-02 is ready for authorization. PP-03 (TransactionAmount) is excluded from this patch — it remains a hypothesis and must not be deployed.

## PP-02: Volume Field Fix

**File:** `scripts/backfill_daily_prices.py`
**Line:** 284
**Parser path:** `fetch_tpex_historical()` (TPEx bulk API only)

**Exact diff:**
```diff
-            vol_raw = _strip_num(str(row.get("TradeVolume", "")))
+            vol_raw = _strip_num(str(row.get("TradingShares", "")))
```

**Root cause:** The TPEx bulk API returns a field named `TradingShares` for trading volume. The script reads `TradeVolume`, which does not exist in the TPEx response, so `row.get("TradeVolume", "")` returns `""`, which `_strip_num` converts to `None`, stored as `NULL`.

## Evidence Chain (PP-02)

1. **S58 P02 live WebFetch:** Direct HTTP probe of the TPEx bulk endpoint on 2026-11-06. The raw JSON payload explicitly contained the key `TradingShares`. Field `TradeVolume` was absent.
2. **S59 forensics:** Confirmed 21,846 NULL volume rows in SET-C (TPEx ordinary stocks, 4-digit, not in stocks table). All have OHLC present but volume = NULL — consistent with a field name read from a key that doesn't exist.
3. **Confidence:** HIGH — DIRECTLY_CONFIRMED from live API observation.

## PP-03: TransactionAmount (HYPOTHESIS — NOT INCLUDED)

**Line:** 285
**Original:** `amt_raw = _strip_num(str(row.get("TradeValue", "")))`
**Proposed:** `amt_raw = _strip_num(str(row.get("TransactionAmount", "")))`

PP-03 is **excluded** from PATCH-3. The field name `TransactionAmount` was not observed in any live probe. It is an inference by naming convention analogy. Evidence level: MEDIUM (hypothesis). The risk of deploying a wrong amount field name is non-zero (data corruption in the amount column). PP-03 must not be bundled with PP-01/PP-02 until verified by a fresh live probe.

## Volume Unit Contract

Both TWSE and TPEx store volume in thousands of shares (千股). The `/1000` divisor applies to both paths.

| Source | API Field | Divisor | DB Unit |
|--------|-----------|---------|---------|
| TWSE | TradeVolume | 1,000 | 千股 |
| TPEx (original) | TradeVolume (WRONG — returns None) | — | NULL |
| TPEx (patched) | TradingShares | 1,000 | 千股 |

**Evidence for unit consistency:** S58 P02 probe of 2317 on 2026-11-06 returned `TradingShares = 89,094,382` raw shares. After `/1000`: 89,094 千股. This scale is consistent with TWSE volume for an actively traded stock.

## Scope

- Affects: `fetch_tpex_historical()` volume field read only
- Does NOT affect: TWSE parser (`fetch_twse_openapi` reads `TradeVolume`, which is correct for TWSE)
- Does NOT affect: amount field (line 285 unchanged — PP-03 excluded)
- Does NOT affect: existing NULL rows in `daily_prices` (historical rows remain NULL; only future backfill runs benefit)
- Volume divisor (`/1000`) unchanged

## Authorization Status

NOT_AUTHORIZED. Requires explicit deployment authorization. The Session 60 research prompt does not constitute authorization.
