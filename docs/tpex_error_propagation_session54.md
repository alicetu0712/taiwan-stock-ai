# TPEx Error Propagation — Session 54

**Verdict**: ERROR_PROPAGATION_PARTIAL (research adapter verified; production patch pending authorization)

## Observability Defect

In `scripts/backfill_daily_prices.py`:

```python
# TWSE mismatch → enters summary["errors"] → appears in cron log ✓
summary["errors"].append(f"{target_d}: TWSE api_date={twse_api_date} != target")

# TPEx mismatch → print() only → NOT in cron log ✗
print(f"  [WARN] {target_d}: TPEx api_date={tpex_api_date} != target")
```

**Impact**: When TPEx is the sole failure (e.g., Nov06 attempted on Nov09), cron log shows only "quality gate FAILED" without identifying the provider.

## Structured Error Contract (PipelineErrorEvent)

Fields: `event_id`, `timestamp`, `provider`, `stage`, `requested_date`, `returned_date`, `error_code`, `severity`, `retryable`, `message`, `source_evidence`, `correlation_id`, `attempt_number`

Error codes: `PROVIDER_DATE_MISMATCH`, `PROVIDER_STALE_DATA`, `PROVIDER_TIMEOUT`, `PROVIDER_RATE_LIMIT`, `PROVIDER_RESPONSE_INVALID`, `UNIVERSE_COVERAGE_LOW`, `BENCHMARK_ONLY`, `PERSISTENCE_FAILURE`, `COMPLETION_MARKER_INVALID`

## Nov09 Run Summary (with full propagation)

12 errors across 4 attempts:
- **TPEx Nov06→Nov09** (TPEx returned Nov09 for Nov06 target): 4 errors (1/attempt)
- **TWSE Nov09→Nov06** (TWSE returned Nov06 for Nov09 target): 4 errors (1/attempt) — DIRECTLY_CONFIRMED in cron log
- **TPEx Nov09→Nov09** (TPEx returned current date, still wrong): 4 errors (1/attempt)

Both `tpex_errors_propagated=True` and `all_errors_propagated=True` via research adapter.

## Production Patch Proposal

| Field | Value |
|-------|-------|
| File | `scripts/backfill_daily_prices.py` |
| Change | `print(...)` → `summary["errors"].append(...)` |
| Safety | Verified — 1-line observability fix, no logic change |
| Authorization | **REQUIRED** (production code) |
| Status | PRODUCTION_PATCH_PROPOSAL ONLY — NOT deployed in S54 |

## Module

`src/research/pipeline_error_propagation_s54.py` — PART C
