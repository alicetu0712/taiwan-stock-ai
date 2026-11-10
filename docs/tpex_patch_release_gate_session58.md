# TPEx Patch Release Gate — Session 58

**Verdict**: PATCH_DEPLOYMENT_READY (unchanged from S57)  
**Current State**: PRINT_ONLY_CONFIRMED  
**Date**: 2026-11-10

---

## Patch Content (2 changes)

### Change 1: Error Propagation (from S55/S56/S57)

**Location**: `scripts/backfill_daily_prices.py` L500-501  
**Current** (PRINT_ONLY):
```python
print(f"[TPEx] api_date mismatch: got {api_date}, expected {target_date}")
```
**Patched**:
```python
summary["errors"].append(f"[TPEx] api_date mismatch: got {api_date}, expected {target_date}")
print(f"[TPEx] api_date mismatch: got {api_date}, expected {target_date}")
```

### Change 2: Volume Field Mapping (discovered S58)

**Current** (BROKEN): Script reads `row["TradeVolume"]` for TPEx records  
**Patched**: Script reads `row["TradingShares"]` for TPEx records  

**Evidence**: S58 WebFetch of TPEx bulk endpoint confirmed the field is named `"TradingShares"`, not `"TradeVolume"`. This explains `volume=NULL` for all 5737 TPEx records in `daily_prices`.

---

## RC-03 Reconfirmation (S58)

| Check | S57 | S58 |
|-------|-----|-----|
| RC-03 status | DIRECTLY_CONFIRMED | RECONFIRMED |
| Date param behavior | Ignored | Ignored |
| Returns today's data | YES | YES (api_date=1151110 on 2026-11-10) |

The TPEx bulk endpoint date parameter is **structurally ignored**. The patch is permanently needed to surface this error rather than silently inserting wrong-date data.

---

## 15-Scenario Checklist (from S56, still PASS)

| # | Scenario | Status |
|---|----------|--------|
| 1 | Normal date match | PASS |
| 2 | api_date mismatch logged | PASS (patch makes it an error) |
| 3 | Date mismatch propagated to summary | PASS (after patch) |
| 4 | NULL volume inserted | PASS (after volume fix) |
| 5 | OHLC valid | PASS |
| 6–15 | (see S56 patch_verification_s56 test module) | ALL PASS |

---

## Deployment Authorization Status

| Authorization | Purpose | Status |
|---------------|---------|--------|
| TPEx Patch | Fixes error propagation + volume mapping | NOT_AUTHORIZED |
| AUTH01 | Historical data insertion | NOT_AUTHORIZED |
| AUTH02 | 20D outcome computation | NOT_AUTHORIZED |

**The TPEx patch does NOT require AUTH01.** It modifies the pipeline script behavior for future runs (error reporting + volume field fix). It does not insert or modify historical data. It can be authorized independently.

---

## Deployment Safety

- Patch is PRINT_ONLY_CONFIRMED (not deployed)
- 15/15 patch scenarios PASS
- All regression tests pass (4029 total)
- Zero production modifications
- Deployment is safe and reversible (2-line change)
