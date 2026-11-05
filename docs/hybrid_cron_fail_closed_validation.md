# Hybrid Cron Fail-Closed Validation

**Date:** 2026-11-05  
**Status:** Step 4b ABORT confirmed; HC26-HC30 all PASS

---

## Change Summary

`scripts/hybrid_shadow_cron.py` Step 4b was changed from WARN-and-continue  
to ABORT when the DB's last_data_date does not equal today.

---

## Before (WARN)

```python
if last_date_post_backfill != today:
    _log(f"[cron] WARN: DB stale (last={last_date_post_backfill}), continuing anyway")
    # pipeline continued to shadow run with stale data
```

## After (ABORT — fail-closed)

```python
if last_date_post_backfill != today:
    _log(f"[cron] BLOCKED_STALE_DATA — last={last_date_post_backfill}, today={today}")
    result["status"] = "BLOCKED_STALE_DATA"
    result["steps"]["data_freshness"] = f"STALE: last={last_date_post_backfill}"
    _save_state(result)
    return result
result["steps"]["data_freshness"] = "OK"
```

---

## Why This Matters

If the backfill step writes the wrong date's data (e.g. TWSE STOCK_DAY_ALL  
returning yesterday's prices as today's), the shadow run would compute signals  
based on stale OHLC. With the fail-closed guard:

- The pipeline aborts before signal generation
- Status is recorded as `BLOCKED_STALE_DATA` (exit_code=0, not an alert)
- Ops can investigate the data freshness failure before any signals are produced
- The OHLCContinuityGate provides a second independent layer of defence

---

## Exit Code Classification

```python
clean_statuses = {
    "SUCCESS",
    "DRY_RUN_OK",
    "SKIPPED_NON_TRADING_DAY",
    "DATA_NOT_READY",
    "BLOCKED_STALE_DATA",   # ← added; not an infrastructure error
    "BLOCKED_LOCK",
}
exit_code = 0 if result["status"] in clean_statuses else 1
```

`BLOCKED_STALE_DATA` exits cleanly (code 0) because it is an expected condition  
(e.g., TWSE API not yet updated, holiday data lag). It does NOT page on-call.

---

## Tests Added (HC26-HC30)

| Test | Scenario | Expected |
|------|----------|---------|
| HC26 | DB stale (last_date = yesterday) | status=BLOCKED_STALE_DATA; shadow NOT called |
| HC27 | DB fresh (last_date = today) | proceeds past Step 4b to shadow |
| HC28 | Calendar check: 09-28 | is_trading_day=False |
| HC29 | Calendar check: 10-23, 10-26 | is_trading_day=False for both |
| HC30 | Live DB integration: gate for 11-05 | GateResult.PASS |

All 30 HC tests pass.

---

## OHLCContinuityGate as Second Layer

Even if Step 4b ABORT were bypassed, the gate would catch it:

```
run_hybrid_forward_shadow.py step order:
  1. Backfill daily prices
  2. Step 4b: data freshness check → ABORT if stale
  3. OHLCContinuityGate.check_market() → ABORT if gate fails
  4. Signal generation (only reached if both checks pass)
```

Both guards must pass for signals to be generated.

---

## Validation Command

```bash
python3 -m pytest tests/test_hybrid_cron.py -v -k "HC26 or HC27 or HC28 or HC29 or HC30"
```

Expected output: 5 PASSED.
