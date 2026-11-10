# Session 62 — Authorization Decision Packages

## Scope

Three independently approvable authorization packages for deploying RC patches to
`scripts/backfill_daily_prices.py`. Each package is complete and self-contained. Approving
one does not activate the others.

**Current status: ALL THREE PACKAGES — NOT_AUTHORIZED**

This document does not constitute authorization. The user must grant explicit independent
authorization for each package they wish to approve.

---

## AUTH-RC61-01 — TPEx Error Reporting Patch

**Authorization ID:** AUTH-RC61-01

**Scope:** Code Deployment Only — TPEx api_date mismatch error reporting.
Deploy a 4-line replacement in `run_backfill()` that adds TPEx date mismatches to
`summary["errors"]` (symmetric with existing TWSE handling at lines 494-498).

| Property | Value |
|----------|-------|
| Target file | `scripts/backfill_daily_prices.py` |
| Target line | 500–501 |
| Changed function | `run_backfill()` |
| Risk level | VERY LOW |
| Authorization status | NOT_AUTHORIZED |

**Exact original text (lines 500-501):**
```python
        if tpex_api_date and tpex_api_date != target_d:
            print(f"  [WARN] {target_d}: TPEx api_date={tpex_api_date} != target")
```

**Exact patched text:**
```python
        if tpex_api_date and tpex_api_date != target_d:
            msg = f"{target_d}: TPEx api_date={tpex_api_date} != target — API returned wrong date"
            print(f"  [WARN] {msg}")
            summary["errors"].append(msg)
```

**Expected benefit:** TPEx api_date mismatches will appear in `summary["errors"]` (symmetric
with TWSE). Callers can programmatically detect when TPEx returned wrong-date data.
Improves observability — no data effect.

**Known limitations:** Does not repair historical NULL volume rows. Does not fix TradingShares
field mismatch. Does not fix security classification. Diagnostic improvement only.

**Required tests:** `tests/test_session61_release_candidates.py` — RC1 acceptance group.
All 68 S61 tests + 75 S62 tests must pass post-deployment.

**Deployment steps:**
1. Verify git working tree clean.
2. Apply exact diff (lines 500-501) to `scripts/backfill_daily_prices.py`.
3. Run `python -m pytest tests/test_session61_release_candidates.py -k rc1 -v`.
4. Run full regression.
5. Run one dry-run backfill to confirm no crash.

**Rollback steps:**
1. Revert lines 500-501 to original `print()` only form.
2. Confirm SHA-256 matches `4bb88de209df6b82995f61dcae19eef0d313f18acc0fc77051a12f40f3fce9d9`.
3. No DB changes needed (no data written).

**Monitoring:** Check `summary["errors"]` on next backfill run. Confirm TPEx date mismatches
appear in errors list when present.

**Stop conditions:** Backfill error rate increases unexpectedly. Normal data incorrectly
flagged as errors.

**Explicit exclusions (this authorization does NOT cover):**
- Script execution with `--execute` (requires separate operator decision)
- AUTH01 (TWSE historical backfill — 1,440 calls)
- AUTH02 (20D outcome computation)
- Historical data repair
- Prospective collection
- AUTH-RC61-02 or AUTH-RC61-03

**Authorization wording template:**
> I authorize deployment of AUTH-RC61-01 (TPEx Error Reporting) only: the specified 4-line
> replacement at lines 500-501 of `scripts/backfill_daily_prices.py`. I do not authorize
> script execution with `--execute`, AUTH01, AUTH02, historical data repair, prospective
> collection, or any other RC.

---

## AUTH-RC61-02 — Warrant/ETF Exclusion Patch

**Authorization ID:** AUTH-RC61-02

**Scope:** Code Deployment Only — Security eligibility fix for `_is_excluded()`.
Deploy a single-character removal at line 98 that fixes the warrant/ETF exclusion bug
(len>4 pure-numeric IDs were incorrectly not excluded).

| Property | Value |
|----------|-------|
| Target file | `scripts/backfill_daily_prices.py` |
| Target line | 98 |
| Changed function | `_is_excluded()` (affects 3 call sites: lines 125, 214, 273) |
| Risk level | LOW |
| Authorization status | NOT_AUTHORIZED |

**Exact original text (line 98):**
```python
    if len(sid) > 4 and not sid.isdigit():
```

**Exact patched text:**
```python
    if len(sid) > 4:
```

**Expected benefit:** Future backfill runs insert 0 new warrant/ETF rows (len>4). QG
coverage universe restricted to ordinary stocks only. Coverage metric improvement is
reclassification only — not new data recovery.

**Known limitations:** Does not delete existing 107,765 historical warrant/ETF rows. Does
not fix TradingShares volume mismatch. TWSE historical backfill still requires AUTH01
separately. If a future legitimate 5-digit ordinary stock is listed in Taiwan, it would be
incorrectly excluded (no such stocks exist in current market system).

**Required tests:** `tests/test_session61_release_candidates.py` — RC2 acceptance group.

**Deployment steps:**
1. Verify git working tree clean.
2. Apply exact diff (line 98) to `scripts/backfill_daily_prices.py`.
3. Verify 3 call sites: `grep -n '_is_excluded' scripts/backfill_daily_prices.py` → lines 125, 214, 273.
4. Run `python -m pytest tests/test_session61_release_candidates.py -k rc2 -v`.
5. Run full regression.
6. Run one dry-run backfill — confirm 6-digit/5-digit pure-numeric stocks absent from output.

**Rollback steps:**
1. Revert line 98 to `if len(sid) > 4 and not sid.isdigit():`.
2. Confirm SHA-256 matches original.
3. No DB changes needed. Next backfill may re-insert warrants (INSERT OR IGNORE idempotent).

**Monitoring:** `SELECT COUNT(*) FROM daily_prices WHERE LENGTH(stock_id)>4 AND date > 'DEPLOY_DATE'` — expect 0.

**Stop conditions:** 4-digit TWSE or TPEx ordinary stocks missing from backfill output. 0050 or benchmark stocks missing.

**Explicit exclusions (this authorization does NOT cover):**
- Script execution with `--execute`
- AUTH01, AUTH02, historical data repair
- Deletion of existing 107,765 warrant/ETF rows
- Prospective collection
- AUTH-RC61-01 or AUTH-RC61-03

**Authorization wording template:**
> I authorize deployment of AUTH-RC61-02 (Warrant/ETF Exclusion) only: the specified
> single-line change at line 98 of `scripts/backfill_daily_prices.py`. I do not authorize
> script execution with `--execute`, AUTH01, AUTH02, deletion of historical rows, prospective
> collection, or any other RC.

---

## AUTH-RC61-03 — TradingShares Parser Patch

**Authorization ID:** AUTH-RC61-03

**Scope:** Code Deployment Only — TPEx volume field fix (PP-02 only).
Deploy a 3-line context replacement at lines 284-286 that changes `row.get("TradeVolume")`
to `row.get("TradingShares")` in `fetch_tpex_historical()`. PP-03 (TransactionAmount) is
excluded.

| Property | Value |
|----------|-------|
| Target file | `scripts/backfill_daily_prices.py` |
| Target lines | 284–286 (3-line context) |
| Changed function | `fetch_tpex_historical()` |
| Risk level | LOW (PP-02 only, field confirmed by S58 live probe) |
| Authorization status | NOT_AUTHORIZED |

**Exact original text (lines 284-286):**
```python
            vol_raw = _strip_num(str(row.get("TradeVolume", "")))
            amt_raw = _strip_num(str(row.get("TradeValue", "")))
            o = _strip_num(str(row.get("Open", "")))
```

**Exact patched text:**
```python
            vol_raw = _strip_num(str(row.get("TradingShares", "")))
            amt_raw = _strip_num(str(row.get("TradeValue", "")))
            o = _strip_num(str(row.get("Open", "")))
```

**Expected benefit:** Future TPEx backfill fetches produce non-NULL volume for ordinary TPEx
stocks. Volume unit `/1000` divisor unchanged (千股). TWSE volume path unchanged.

**Known limitations:** Does not repair historical 21,846 NULL rows in `daily_prices`.
Historical repair requires AUTH01 separately. PP-03 (amount field — `TransactionAmount`)
excluded — HYPOTHESIS status. Amount (`TradeValue`) remains as-is. TPEx historical repair
remains BLOCKED (no verified per-stock endpoint).

**Required tests:** `tests/test_session61_release_candidates.py` — RC3 acceptance group.

**Deployment steps:**
1. Verify git working tree clean.
2. Apply exact 3-line context diff (lines 284-286).
3. Verify TWSE line 136 is UNCHANGED: still `row.get("TradeVolume", "")`.
4. Verify line 285 is UNCHANGED: still `row.get("TradeValue", "")`.
5. Run `python -m pytest tests/test_session61_release_candidates.py -k rc3 -v`.
6. Run full regression.
7. Run one dry-run TPEx backfill — confirm volume appears non-NULL in output.

**Rollback steps:**
1. Revert lines 284-286 to original 3-line context.
2. Confirm SHA-256 matches original.
3. If backfill was executed: non-NULL volume rows are correct data. No DB rollback needed.

**Monitoring:** `SELECT AVG(volume) FROM daily_prices WHERE LENGTH(stock_id)=4 AND date='FIRST_POST_DEPLOY_DATE'`. Expected: 100–100,000 千股.

**Stop conditions:** TPEx volume >1,000,000 千股 for typical stock. TWSE volume values changed.

**Explicit exclusions (this authorization does NOT cover):**
- Script execution with `--execute`
- AUTH01, AUTH02, historical data repair
- PP-03 (TransactionAmount) — explicitly HYPOTHESIS, not deployed
- Prospective collection
- AUTH-RC61-01 or AUTH-RC61-02

**Authorization wording template:**
> I authorize deployment of AUTH-RC61-03 (TradingShares Parser, PP-02 only) only: the
> specified 3-line context replacement at lines 284-286 of `scripts/backfill_daily_prices.py`.
> I do not authorize PP-03 (TransactionAmount), script execution with `--execute`, AUTH01,
> AUTH02, historical data repair, prospective collection, or any other RC.

---

## Verdict

**THREE_AUTH_PACKAGES_READY**

All three packages are independently self-contained with exact diffs, test evidence, rollback
steps, and explicit exclusion lists. Each can be approved in isolation without reference to
the others.

---

## Next Action

Present each authorization wording template to the user. Await independent explicit
confirmation for each AUTH-RC61-XX the user wishes to approve. No deployment occurs until
explicit confirmation is received. Session 62 ends with all three packages at NOT_AUTHORIZED.
