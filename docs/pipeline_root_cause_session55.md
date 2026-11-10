# Pipeline Root Cause — Session 55

**Verdict**: ROOT_CAUSE_PARTIAL (unchanged from S54)

## Root Cause Matrix

| ID | Description | Affected Dates | Confidence | Proposed Fix |
|----|-------------|----------------|-----------|--------------|
| RC-01 | CRON_NO_TRIGGER: scheduler did not trigger pipeline on missing dates | Oct29–Nov03, Nov06, Nov09 | DIRECTLY_CONFIRMED | Re-trigger manually (AUTH01) |
| RC-02 | TWSE_LATEST_URL_LAG: TWSE /api/exchangeReport/STOCK_DAY_ALL returns day-lag | Nov06, Nov09 | DIRECTLY_CONFIRMED | Switch to TWSE_HIST_URL per-stock |
| RC-03 | TPEX_HIST_URL: TPEx historical endpoint returns wrong api_date for recent dates | Multiple | STRONGLY_SUPPORTED | Deploy TPEx patch (PART C) |
| RC-04 | DATABASE_WRITE_FAILURE: insert succeeded but no row visible | Speculative | INSUFFICIENT_EVIDENCE | None proposed |

## Evidence Summary (RC-01)

- Cron hash `3acaf480cb5dcdd44f40dd9d464955a1` confirmed unchanged (S55 preflight)
- Oct29–Nov03: DB shows only 1 row (0050 benchmark) for each date — cron never inserted market data
- S46 root cause forensics confirmed cron wasn't triggered by SCHEDULER_NOT_TRIGGERED mechanism
- **Status**: DIRECTLY_CONFIRMED

## Evidence Summary (RC-02)

- TWSE_LATEST_URL endpoint design: returns "latest available" data, not specific date
- Nov06 (confirmed): TWSE url returned Nov05 data for Nov06 request (api_date lag)
- Nov09 (confirmed): same mechanism
- S50 session verified this via manual TWSE single-stock queries
- **Status**: DIRECTLY_CONFIRMED

## Evidence Summary (RC-03)

- `scripts/backfill_daily_prices.py` L500-501: `tpex_api_date != target_d` branch only calls `print()`, NOT `summary["errors"].append()`
- Multiple run summaries show 0 errors despite TPEx date mismatches
- Cannot confirm RC-03 is causally responsible for missing rows (insufficient negative confirmation)
- **Status**: STRONGLY_SUPPORTED (not DIRECTLY_CONFIRMED because error propagation defect could mask evidence)

## Evidence Summary (RC-04)

- No log evidence, no DB constraints violated, no exception trail
- **Status**: INSUFFICIENT_EVIDENCE

## Why ROOT_CAUSE_PARTIAL

ROOT_CAUSE_PARTIAL (not FULLY_RESOLVED) because:
1. RC-03 cannot be confirmed directly (TPEx error propagation defect is itself unpatched)
2. RC-04 not ruled out
3. The interaction between RC-01 (cron no-trigger) and RC-02/RC-03 (URL errors) is not fully characterized

## Relationship to S54

S54 verdict was ROOT_CAUSE_PARTIAL (same). S55 did not change this verdict because:
- No new evidence for RC-03 beyond S54
- RC-04 remains INSUFFICIENT_EVIDENCE
- TPEx patch is PROPOSED but not deployed → RC-03 confirmation still indirect

## Module

`src/research/tpex_patch_verification_s55.py` — PART D
