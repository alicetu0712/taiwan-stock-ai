# Session 61 — RC61-01 Error Reporting Acceptance

**Verdict: RC1_ACCEPTANCE_PASS**

## Scope

RC61-01-TPEX-ERROR patches `run_backfill` in `scripts/backfill_daily_prices.py` (lines 500–501). It makes TPEx api_date mismatch errors visible in `summary["errors"]`, symmetric with the existing TWSE handling.

## Behavioral Change

| Scenario | Before patch | After patch |
|----------|-------------|-------------|
| TPEx api_date matches target | No error (correct) | No error (unchanged) |
| TPEx api_date mismatches target | `print()` only; `summary["errors"]` empty | `print()` + `summary["errors"].append(msg)` |
| TPEx api_date is None | No error (correct) | No error (unchanged) |
| TWSE api_date mismatches target | `summary["errors"].append(msg)` (existing behavior) | Unchanged |

## Evidence

TWSE handling (lines 494–498) already appends to `summary["errors"]`:
```python
msg = f"{target_d}: TWSE api_date={twse_api_date} != target — API returned wrong date"
print(f"  [WARN] {msg}")
summary["errors"].append(msg)
```

The TPEx block at lines 500–501 only calls `print()`. The patch makes the two blocks symmetric. The error message format matches the TWSE pattern exactly.

## Acceptance Test Results

| Test | Description | Result |
|------|-------------|--------|
| TC01 | Mismatch NOT in errors before patch | PASS |
| TC02 | Mismatch added to errors after patch | PASS |
| TC03 | No mismatch → no error | PASS |
| TC04 | None api_date → no error | PASS |
| TC05 | Error message contains "API returned wrong date" | PASS |
| TC06 | Exact original diff present in script (1 unique match) | PASS |

All 6 tests pass. No skips.

## Limitations

- RC-1 does not repair any historical NULL volume rows.
- RC-1 does not fix the TradingShares field mismatch.
- RC-1 does not fix security classification.
- RC-1 does not change data inserted into daily_prices.
- Improvement is observability only: callers can now detect when TPEx returned wrong-date data.

## Rollback

Revert lines 500–501 to the original two-line `print()` form. No DB changes required (no data written by this patch). Code rollback is exact and lossless (hash verified).

## Authorization Status

NOT_AUTHORIZED. Requires independent explicit user approval via AUTH-RC61-01.
