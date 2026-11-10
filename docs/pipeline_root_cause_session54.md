# Pipeline Root Cause Isolation — Session 54

**Verdict**: ROOT_CAUSE_PARTIAL (symptom-level confirmed; scheduler trigger root cause unknown)

## Root Cause Matrix

| ID | Description | Affected Dates | Confidence |
|----|-------------|----------------|------------|
| RC-01 | CRON_NO_TRIGGER: scheduler did not invoke pipeline on Nov06 | Nov06 | DIRECTLY_CONFIRMED |
| RC-02 | TWSE_LATEST_URL_LAG: TWSE returns previous trading day data | Nov09, Nov10 | DIRECTLY_CONFIRMED |
| RC-03 | TPEX_HIST_URL_CURRENT_DATE: TPEx ignores d= parameter | Nov06, Nov09, Nov10 | STRONGLY_SUPPORTED |
| RC-04 | SCHEDULER_ROOT_CAUSE: why was Nov06 trigger absent? | Nov06 | INSUFFICIENT_EVIDENCE |

## Evidence Summary

**RC-01**: `logs/hybrid_cron.log` absent at 23:03 Taiwan on Nov06. Shell `>>` redirect creates log even on Python error; absence = no invocation. DIRECTLY_CONFIRMED.

**RC-02**: `logs/hybrid_cron.log` explicit entries:
- `2026-11-09: TWSE api_date=2026-11-06 != target` (all 4 retries on Nov09)
- `2026-11-06: TWSE api_date=2026-11-09 != target` (Nov10 cron)
- `2026-11-10: TWSE api_date=2026-11-09 != target` (Nov10 cron)
Root cause: `TWSE_HIST_URL` returns CSV for historical dates → `json()` fails → fallback to `TWSE_LATEST_URL` which has 1-trading-day systematic lag.

**RC-03**: Code analysis of `scripts/backfill_daily_prices.py` confirms TPEx api_date mismatch goes to `print()` only. `market_source_verification_s50.py` confirmed `SOURCE_UNAVAILABLE` for TPEx bulk historical. STRONGLY_SUPPORTED.

**RC-04**: System cron logs not available for analysis in S54. Manual inspection needed.

## Comparison to S53 Verdict

No change. ROOT_CAUSE_PARTIAL was the S53 verdict; S54 adds:
1. Structured `PipelineErrorEvent` contract for all RC symptoms
2. Per-attempt error trace for Nov09 (4 attempts × 3 errors = 12 events)
3. Production patch proposal for TPEx observability gap

## Proposed Fix Roadmap

1. **RC-01/RC-04**: Inspect system cron logs; verify crontab integrity (read-only, no auth needed)
2. **RC-02**: Replace `TWSE_LATEST_URL` fallback with single-stock API (AUTH_TWSE_SINGLE_STOCK, new auth)
3. **RC-03**: Apply production patch proposal (`print` → `summary["errors"]`); then verify TPEx appears in cron log

## Module

`src/research/pipeline_error_propagation_s54.py` — PART D
