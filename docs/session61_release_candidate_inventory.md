# Session 61 — Release Candidate Inventory

Three independent Release Candidates targeting `scripts/backfill_daily_prices.py`. All are NOT_AUTHORIZED pending explicit user approval. None have been deployed.

## RC Summary Table

| RC ID | Name | Target Line | Risk | Authorization |
|-------|------|-------------|------|---------------|
| RC61-01-TPEX-ERROR | TPEx Error Reporting Patch | 500–501 | VERY LOW | NOT_AUTHORIZED |
| RC61-02-SECURITY-ELIGIBILITY | Warrant/ETF Exclusion Patch | 98 | LOW | NOT_AUTHORIZED |
| RC61-03-TPEX-VOLUME | TradingShares Parser Patch (PP-02 only) | 284–286 | LOW | NOT_AUTHORIZED |

## RC61-01-TPEX-ERROR

**Function:** `run_backfill`

**Exact diff:**
```python
# BEFORE (line 500-501)
        if tpex_api_date and tpex_api_date != target_d:
            print(f"  [WARN] {target_d}: TPEx api_date={tpex_api_date} != target")

# AFTER
        if tpex_api_date and tpex_api_date != target_d:
            msg = f"{target_d}: TPEx api_date={tpex_api_date} != target — API returned wrong date"
            print(f"  [WARN] {msg}")
            summary["errors"].append(msg)
```

**What it fixes:** TWSE api_date mismatches are appended to `summary["errors"]` (lines 494–498). The TPEx branch is not. After the patch, both are symmetric. No data is inserted or changed.

## RC61-02-SECURITY-ELIGIBILITY

**Function:** `_is_excluded` (3 call sites: lines 125, 214, 273)

**Exact diff:**
```python
# BEFORE (line 98)
    if len(sid) > 4 and not sid.isdigit():

# AFTER
    if len(sid) > 4:
```

**What it fixes:** Pure-numeric codes longer than 4 digits (warrants `7xxxxx`, ETFs `00xxx`, `006xxx`) pass through the old condition because `isdigit()` is `True`. After the patch, all codes longer than 4 characters are excluded, regardless of content.

**Universe contract:** Taiwan TWSE and TPEx ordinary stocks always use 4-digit numeric codes. TWSE Innovation Board stocks (e.g. 6423) also use 4-digit codes. Zero false exclusions of ordinary stocks.

## RC61-03-TPEX-VOLUME

**Function:** `fetch_tpex_historical`

**Exact diff (3-line context required for uniqueness — TWSE line 136 uses identical single-line pattern):**
```python
# BEFORE (lines 284–286)
            vol_raw = _strip_num(str(row.get("TradeVolume", "")))
            amt_raw = _strip_num(str(row.get("TradeValue", "")))
            o = _strip_num(str(row.get("Open", "")))

# AFTER
            vol_raw = _strip_num(str(row.get("TradingShares", "")))
            amt_raw = _strip_num(str(row.get("TradeValue", "")))
            o = _strip_num(str(row.get("Open", "")))
```

**What it fixes:** TPEx bulk API returns `TradingShares` for volume; the script was reading `TradeVolume` (absent in TPEx responses) → `None` → stored as NULL. Only the volume field changes. Amount (`TradeValue`) and all OHLC fields are unchanged. TWSE line 136 is not modified.

**PP-03 excluded:** The amount field (`TradeValue` → hypothetical `TransactionAmount`) is HYPOTHESIS status and is not part of RC-3.

## Frozen References

- Production script SHA-256: `4bb88de209df6b82995f61dcae19eef0d313f18acc0fc77051a12f40f3fce9d9`
- daily_prices max date: 2026-11-05 (unchanged)
- NULL volume rows: 129,636 (unchanged)
- V3 parameter hash: `be43e8ca977d9fdd` (frozen)
- Regression: 4198 passed / 4 skipped
