# Independent Patch Release Gate — Session 60

## Overview

Three patches to `scripts/backfill_daily_prices.py` are ready for independent authorization. They modify non-overlapping code regions and can be deployed, rolled back, and verified separately.

**All three patches are NOT_AUTHORIZED.** None may be deployed without explicit, independent authorization.

---

## PATCH-1: TPEx Error Reporting

**Type:** Diagnostic only — no data change
**File:** `scripts/backfill_daily_prices.py`
**Line:** ~500

**Exact diff:**
```diff
-  print(f'  TPEx api_date mismatch ...')
+  summary['errors'].append(f'TPEx api_date mismatch ...')
```

**Behavioral change:** API date mismatch errors are captured in the run summary dict instead of printed to stdout. No change to what data is inserted.

**Risk:** VERY LOW

**Rollback:** Revert line ~500 to `print()` statement. No data to undo.

**Post-deployment verification:** Run backfill for one date. Confirm mismatch appears in `summary['errors']`. Confirm row counts and volume values are unchanged.

---

## PATCH-2: Warrant Exclusion

**Type:** Future-insert prevention — no existing data change
**File:** `scripts/backfill_daily_prices.py`
**Line:** 98

**Exact diff:**
```diff
-    if len(sid) > 4 and not sid.isdigit():
+    if len(sid) > 4:
```

**Behavioral change:** Future backfill runs will not insert 7xxxxx warrants, 00xxx ETFs, or 006xxx ETFs. Existing rows in `daily_prices` are not deleted. QG universe denominator becomes smaller (ordinary stocks only) for future runs.

**Risk:** LOW. No existing data removed. Monitored risk: a hypothetical future 5-digit ordinary stock code would be incorrectly excluded.

**Rollback:** Restore `and not sid.isdigit()`. No data needs to be undone.

**Post-deployment verification:** Run backfill for one date. Confirm 6-digit and 5-digit stocks are absent from output. Confirm 4-digit stocks are still inserted.

---

## PATCH-3: TradingShares Volume Field (PP-02 only)

**Type:** Data-touching — fixes NULL volume for future TPEx fetches
**File:** `scripts/backfill_daily_prices.py`
**Line:** 284

**Exact diff:**
```diff
-            vol_raw = _strip_num(str(row.get("TradeVolume", "")))
+            vol_raw = _strip_num(str(row.get("TradingShares", "")))
```

**PP-03 excluded:** Line 285 (`amt_raw`) is NOT changed. PP-03 (TransactionAmount) is an unverified hypothesis and must not be bundled here.

**Behavioral change:** Future TPEx backfill fetches will populate volume (not NULL) for ordinary TPEx stocks. Historical NULL rows remain. Volume unit unchanged (`/1000`).

**Risk:** LOW for PP-02 alone (field confirmed by S58 direct probe). HIGH if PP-03 is bundled.

**Rollback:** Restore `row.get("TradeVolume")` on line 284. Historical rows unaffected.

**Post-deployment verification:** Run backfill for one TPEx date. Confirm volume IS NOT NULL for ordinary TPEx stocks. Confirm TWSE stocks unaffected. Confirm volume scale consistent with TWSE (~千股).

---

## Independence Proof

| Patch | Lines Modified | Overlaps with Other Patches |
|-------|---------------|----------------------------|
| PATCH-1 | ~500 (error handling) | None |
| PATCH-2 | 98 (`_is_excluded` body) | None |
| PATCH-3 | 284 (TPEx volume field read) | None |

Each patch touches a distinct, non-adjacent code region. Applying any subset of the three patches is equivalent to applying each individually.

## Recommended Deployment Order

1. **PATCH-2** (warrant exclusion) — smallest data blast radius, diagnostic effect only. Confirm 4-digit stocks still flowing before proceeding.
2. **PATCH-1** (error reporting) — improves observability with zero data risk.
3. **PATCH-3** (TradingShares) — data-touching; deploy after PATCH-2 output has been observed and confirmed.

**Do not bundle PP-03 with PATCH-3.** PP-03 requires a separate live probe to verify the `TransactionAmount` field name before it can be authorized.
