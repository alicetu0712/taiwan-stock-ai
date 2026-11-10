# Session 61 — Authorization Packages

**Verdict: THREE_INDEPENDENT_PACKAGES_READY**

## Overview

Three independent authorization packages are prepared. Each can be approved, deferred, or declined independently without affecting the others.

No package contains the others. Approving AUTH-RC61-02 does NOT authorize AUTH-RC61-01 or AUTH-RC61-03.

---

## AUTH-RC61-01 — TPEx Error Reporting

| Field | Value |
|-------|-------|
| Package ID | AUTH-RC61-01 |
| RC | RC61-01-TPEX-ERROR |
| File | `scripts/backfill_daily_prices.py` |
| Lines | 500–501 |
| Type | Observability — no data written |
| Risk level | LOW |
| Reversible | Yes — exact hash round-trip verified |

**What this authorizes:**
- Modify lines 500–501 of `backfill_daily_prices.py` to append TPEx api_date mismatch into `summary["errors"]`.
- No data is written to `data/platform.db` or Neon by this patch itself.

**Exact diff:**
```diff
-        if tpex_api_date and tpex_api_date != target_d:
-            print(f"  [WARN] {target_d}: TPEx api_date={tpex_api_date} != target")
+        if tpex_api_date and tpex_api_date != target_d:
+            msg = f"{target_d}: TPEx api_date={tpex_api_date} != target — API returned wrong date"
+            print(f"  [WARN] {msg}")
+            summary["errors"].append(msg)
```

**What this does NOT authorize:**
- AUTH-RC61-02, AUTH-RC61-03
- Any production backfill
- Any DB writes
- Any schema changes

**DQ acceptance metric:**
- Metric: `summary["errors"]` populated on mismatch
- Baseline: 0 errors (not populated)
- Threshold: Populated within 1 run on mismatch
- Observation window: Next scheduled backfill run after deployment
- Rollback trigger: If errors are incorrectly emitted for valid dates

---

## AUTH-RC61-02 — Security Eligibility Fix

| Field | Value |
|-------|-------|
| Package ID | AUTH-RC61-02 |
| RC | RC61-02-SECURITY-ELIGIBILITY |
| File | `scripts/backfill_daily_prices.py` |
| Lines | 98 |
| Type | Exclusion logic — affects future inserts, NOT existing rows |
| Risk level | LOW |
| Reversible | Yes — exact hash round-trip verified |

**What this authorizes:**
- Modify line 98 of `backfill_daily_prices.py` to change `if len(sid) > 4 and not sid.isdigit():` → `if len(sid) > 4:`.
- Future backfill runs will exclude warrants (6-digit, 7xxxxx) and ETFs (5-digit 00xxx) from insertion.
- Existing 107,765 warrant/ETF rows in `daily_prices` are NOT deleted.

**Exact diff:**
```diff
-    if len(sid) > 4 and not sid.isdigit():
+    if len(sid) > 4:
```

**What this does NOT authorize:**
- AUTH-RC61-01, AUTH-RC61-03
- Deletion of existing warrant/ETF rows in daily_prices
- Any schema changes
- Any backfill execution

**DQ acceptance metric:**
- Metric: QG coverage % denominator contains only ordinary stocks
- Baseline: Denominator includes warrants/ETFs (inflated)
- Threshold: 0 new warrant/ETF rows after first post-deployment backfill
- Observation window: 5 trading days post-deployment
- Rollback trigger: Any 4-digit ordinary stock is excluded

---

## AUTH-RC61-03 — TPEx TradingShares Volume Fix

| Field | Value |
|-------|-------|
| Package ID | AUTH-RC61-03 |
| RC | RC61-03-TPEX-VOLUME |
| File | `scripts/backfill_daily_prices.py` |
| Lines | 284 |
| Type | Data quality — corrects field name for future inserts |
| Risk level | LOW–MEDIUM |
| Reversible | Yes — exact hash round-trip verified; existing NULL rows are NOT modified |

**What this authorizes:**
- Modify line 284 of `backfill_daily_prices.py` within 3-line context to change `row.get("TradeVolume", "")` → `row.get("TradingShares", "")` for the TPEx parser.
- Future backfill runs will correctly read volume from `TradingShares` field.
- Existing 21,846 NULL volume rows in daily_prices are NOT modified.

**3-line context diff:**
```diff
-            vol_raw = _strip_num(str(row.get("TradeVolume", "")))
             amt_raw = _strip_num(str(row.get("TradeValue", "")))
             o = _strip_num(str(row.get("Open", "")))
+            vol_raw = _strip_num(str(row.get("TradingShares", "")))
             amt_raw = _strip_num(str(row.get("TradeValue", "")))
             o = _strip_num(str(row.get("Open", "")))
```

**PP-03 (TransactionAmount for amount) is NOT included in this authorization.**

**What this does NOT authorize:**
- AUTH-RC61-01, AUTH-RC61-02
- Historical repair of existing NULL volume rows (requires separate AUTH01)
- PP-03 (amount field fix — HYPOTHESIS, MEDIUM confidence)
- Any schema changes

**DQ acceptance metric:**
- Metric: TPEx stocks have non-NULL volume in daily_prices after backfill
- Baseline: TPEx volume = NULL (21,846 historical rows)
- Threshold: NULL rate for TPEx stocks < 5% after 5 trading days
- Observation window: 5 trading days post-deployment
- Rollback trigger: TWSE volume becomes NULL (line 136 contaminated)

---

## Package Independence Matrix

| | AUTH-RC61-01 | AUTH-RC61-02 | AUTH-RC61-03 |
|--|---|---|---|
| AUTH-RC61-01 requires | — | No | No |
| AUTH-RC61-02 requires | No | — | No |
| AUTH-RC61-03 requires | No | No | — |
| Approving one authorizes | — | Nothing else | Nothing else |

**All three can be deployed in any order. None blocks any other.**
