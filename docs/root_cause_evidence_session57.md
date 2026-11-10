# Root Cause Evidence Ledger — Session 57

**Session ID**: S57  
**Date**: 2026-11-10

---

## Summary

Five root causes identified. Three directly confirmed by S57 live probes.

| Code | Hypothesis | Confidence | Evidence Type |
|------|-----------|------------|---------------|
| RC-01 | TWSE_HIST_URL returns non-JSON | DIRECTLY_CONFIRMED | S57 live probe |
| RC-02 | TWSE_LATEST_URL always returns yesterday | DIRECTLY_CONFIRMED | S57 live probe |
| RC-03 | TPEx_HIST_URL ignores date param | DIRECTLY_CONFIRMED | S57 live probe |
| RC-04 | SCHEDULER_NOT_TRIGGERED for Nov06/09 | STRONGLY_SUPPORTED | Absence of rows |
| RC-05 | Oct29/30/Nov02/03 benchmark-only | SUFFICIENT_EVIDENCE | 1-row pattern |

---

## RC-01: TWSE_HIST_URL Returns Non-JSON

**Hypothesis**: The classic TWSE bulk historical URL returns empty/non-JSON for recent dates,
causing the pipeline to fail silently on the primary fetch path.

**Evidence**: S57 live probe, 2026-11-10:
```
GET https://www.twse.com.tw/exchangeReport/STOCK_DAY_ALL?response=json&date=20261029
Attempts: 3
Error: JSONDecodeError: Expecting value: line 1 column 1 (char 0)
Result: Empty body / HTML error page
Repeated for date=20261104: same result
```

**Root Cause**: TWSE changed the endpoint behavior; this URL no longer returns JSON
for recent or current dates. The endpoint may work for older historical dates (unverified).

**Pipeline Impact**: The script falls through to TWSE_LATEST_URL, which returns WRONG DATE data.

**Remediation**:
1. Remove TWSE_HIST_URL from active fetch path
2. Document as DEAD for dates ≥ some threshold (exact boundary unknown)
3. Replace with TWSE_SINGLE_STOCK pattern for historical recovery

---

## RC-02: TWSE_LATEST_URL Always Returns T-1 Data

**Hypothesis**: The OpenAPI fallback returns the latest trading day (T-1 when cron runs T+1 morning),
causing api_date mismatch and potentially triggering date validation guards.

**Evidence**: S57 live probe, 2026-11-10:
```
GET https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL
Result: 1241 stocks, api_date=2026-11-09 (yesterday)
Probe date: 2026-11-10
Off-by-one: api_date = probe_date - 1 trading day
```

**Pipeline Impact**: If cron runs on day T for target date T, api_date=T-1 creates
a mismatch. If the script has a strict date validation guard, it may reject the data
and write 0 rows — explaining Nov06/09 DATE_MISSING.

**When This Works**: For daily cron running early morning on T, requesting data for T-1:
api_date=T-1 matches → data accepted. This is likely the intended behavior.

**Remediation**:
1. Add tolerance: accept api_date within ±1 trading day of target_date
2. Log WARNING not ERROR for off-by-one
3. Add minimum-row health check to detect silent failures

---

## RC-03: TPEx_HIST_URL Ignores Date Parameter

**Hypothesis**: The TPEx `tpex_mainboard_daily_close_quotes` endpoint ignores the `?d=`
date parameter and always returns today's data.

**Evidence**: S57 live probe, 2026-11-10:
```
GET ...tpex_mainboard_daily_close_quotes?d=1151029  (Oct29)
Result: 5737 stocks, api_date=2026-11-10 (TODAY)

GET ...tpex_mainboard_daily_close_quotes?d=1151104  (Nov04)
Result: 5737 stocks, api_date=2026-11-10 (TODAY)
```

Both different dates → identical api_date = today. The endpoint is designed
to return only current market data. The endpoint name confirms this:
`daily_close_quotes` (not `historical_quotes`).

**Additional Finding**: Volume=NULL for ALL 5737 records regardless of date.

**Pipeline Impact**: Any TPEx data inserted via this endpoint has:
1. Wrong date (always today's date)
2. Missing volume (NULL for all records)

The S55 TPEx patch (L500-503) correctly captures this in `summary["errors"]`
after deployment, enabling monitoring. It does not fix the data problem.

**Remediation**:
1. Deploy TPEx patch (DEPLOYMENT_READY)
2. For historical recovery: investigate TPEx per-stock historical API (unverified)
3. Accept NULL volume as structural for TPEx records

---

## RC-04: SCHEDULER_NOT_TRIGGERED for Nov06/09

**Hypothesis**: The GitHub Actions cron job did not run on Nov06/09, or ran but raised
an unhandled exception before writing any rows.

**Evidence**:
- Nov06: 0 rows in daily_prices (not even 0050 benchmark)
- Nov09: 0 rows in daily_prices (not even 0050 benchmark)
- S50 research snapshots confirm Nov06/09 were valid trading days (2330/2454 have price data)
- Nov04/05 (adjacent) had 6957/6589 rows — not a universal outage

**Confidence**: STRONGLY_SUPPORTED (absence of rows including benchmark suggests no run at all)

**Direct Verification Needed**: GitHub Actions workflow run history for Nov06/09.
Cannot confirm without audit of CI logs (outside research scope).

**Remediation**:
1. Add GitHub Actions run-status monitoring alert
2. Minimum-row health check: alert if rows < 1000 for a known trading day
3. Add retry logic for cron failures (idempotent daily run)

---

## RC-05: Oct29/30/Nov02/03 Benchmark-Only

**Hypothesis**: The pipeline ran on Oct29/30/Nov02/03 but only processed the benchmark ETF (0050),
failing to fetch ordinary stock data. 

**Evidence**:
- Exactly 1 row per date (the 0050 benchmark ETF)
- If the pipeline had completely failed, 0 rows would be expected
- S50 confirmed TWSE_SINGLE_STOCK works for these dates → data existed

**Most Likely Sub-Cause**: Date validation guard rejected TWSE_LATEST_URL data
because api_date (T-1) ≠ target_date (T). The 0050 benchmark may come from a
separate simpler fetch that bypasses date validation.

**Confidence**: SUFFICIENT_EVIDENCE (consistent pattern across 4 dates)

**Remediation**: Same as RC-02 — add api_date tolerance to date validation.

---

## Cross-Reference

| RC | Affects | Patch/Fix Required | Authorization |
|----|---------|-------------------|---------------|
| RC-01 | All historical fetches | Remove TWSE_HIST_URL from pipeline | Pipeline change |
| RC-02 | Daily cron date validation | Add ±1 trading day tolerance | Pipeline change |
| RC-03 | TPEx data quality | Deploy S55 TPEx patch | TPEx patch auth |
| RC-04 | Nov06/09 missing | GH Actions audit + HC-01 health check | Research scope |
| RC-05 | Oct29–Nov03 benchmark-only | Same as RC-02 + HC-01 | Pipeline change |

None of these remediations are authorized in S57. All require pipeline modification authorization.
