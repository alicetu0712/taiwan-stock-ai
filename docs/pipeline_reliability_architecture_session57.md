# Pipeline Reliability Architecture — Session 57

**Session ID**: S57  
**Date**: 2026-11-10  
**Status**: DESIGN_COMPLETE — Implementation NOT authorized

---

## Design Principle

Each health check targets a specific failure mode from Sessions 50–57.
No check is currently implemented. All are design recommendations.

---

## Health Check Catalog

### HC-01: Minimum Row Count

**Trigger**: After each daily price fetch completion  
**Threshold**: rows_inserted > 1000 for a known trading day  
**Action on Fail**: Write to error log; alert; mark day as FAILED (not COMPLETE)  
**Currently Implemented**: NO  

**Failure Mode Caught**: Nov06/09 DATE_MISSING (RC-04).
If the cron had a minimum-row guard, the pipeline would have alerted immediately
rather than silently leaving 0 rows.

**Implementation Note**: Requires `TaiwanTradingCalendar_v1` lookup to skip holidays
(HC-05 prerequisite). Do not alert on verified market holidays.

---

### HC-02: API Date Validation

**Trigger**: After each API response (TWSE or TPEx)  
**Threshold**: api_date within ±1 trading day of target_date  
**Action on Fail (strict mismatch >1 day)**: Log ERROR; skip insert for that batch  
**Action on Fail (off-by-one T-1)**: Log WARNING; proceed with insert  
**Currently Implemented**: NO  

**Failure Mode Caught**: RC-02 (TWSE api_date=T-1 when cron runs T+1 morning).
The current code may have a strict guard that rejects T-1 data,
causing Oct29/30/Nov02/03 to only get the benchmark row.

**TPEx Note**: After patch deployment, TPEx api_date mismatch goes into `summary["errors"]`.
HC-02 should read this summary to decide whether to alert.

---

### HC-03: Volume Null Rate

**Trigger**: After each daily price fetch  
**Threshold**: null_volume_pct < 80% for TWSE stocks; TPEx always NULL (expected)  
**Action on Fail**: Log INFO for TPEx structural NULL; Log WARN for TWSE unusual null volume  
**Currently Implemented**: NO  

**Failure Mode Caught**: Nov04 volume_null_rows=5715/6957=82% is expected (TPEx).
Without this check, operators can't distinguish structural TPEx NULL from real data gaps.

**Implementation Note**: Tag each row with exchange source (TWSE vs TPEx) before insert.
Currently `daily_prices` schema has no `exchange` or `source` column —
schema change needed for precise tracking.

---

### HC-04: OHLC Sanity Validation

**Trigger**: Before each row insert  
**Threshold**: high ≥ low, close in [low, high], all OHLC > 0  
**Action on Fail**: Reject row; append to `summary["errors"]`  
**Currently Implemented**: NO  

**Failure Mode Caught**: Data corruption prevention.
Nov04 had 0 OHLC invalid rows — validation was passing by chance.
This should be an explicit hard check.

---

### HC-05: Trading Day Calendar Pre-flight

**Trigger**: Before each fetch attempt for a given date  
**Threshold**: date is in `TaiwanTradingCalendar_v1`  
**Action on Skip**: Log HOLIDAY_SKIP; proceed without error  
**Currently Implemented**: NO  

**Failure Mode Caught**: Unnecessary API calls on holidays.
`TaiwanTradingCalendar_v1` was verified E2E in S56.
Integration with daily pipeline not wired.

---

### HC-06: Deduplication on Insert

**Trigger**: Before each INSERT  
**Threshold**: No existing row for (stock_id, date) combination  
**Action on Fail**: SKIP (INSERT OR IGNORE) or log duplicate if deliberate update  
**Currently Implemented**: NO (not confirmed)  

**Failure Mode Caught**: Duplicate rows from retry runs or manual backfill.
`daily_prices` UNIQUE(stock_id, date) assumed but not verified in schema DDL.

---

## Pipeline Architecture Diagram (Proposed)

```
Daily Cron (T+1 morning)
│
├── HC-05: Is target_date a trading day?
│    ├── NO → HOLIDAY_SKIP; exit cleanly
│    └── YES → continue
│
├── Fetch TWSE_LATEST_URL (1 request)
│    ├── HC-02: api_date within ±1 trading day?
│    │    ├── OK → proceed
│    │    └── FAIL → LOG ERROR; skip TWSE insert
│    └── HC-04: OHLC sanity per row
│
├── Fetch TPEx_BULK (1 request)
│    ├── HC-02: api_date matches? (after patch: check summary["errors"])
│    │    └── FAIL → LOG ERROR; still insert with NULL volume (structural)
│    └── HC-04: OHLC sanity per row
│
├── Insert to daily_prices
│    └── HC-06: INSERT OR IGNORE for deduplication
│
└── Post-insert checks
     ├── HC-01: rows_inserted > 1000?
     │    └── FAIL → ALERT; mark day FAILED
     └── HC-03: TPEx NULL volume rate expected?
```

---

## Implementation Priority

| Check | Priority | Difficulty | Impact |
|-------|----------|------------|--------|
| HC-01 Minimum rows | HIGH | LOW | Catches silent failures immediately |
| HC-02 API date | HIGH | MEDIUM | Fixes RC-02 date mismatch confusion |
| HC-05 Calendar | MEDIUM | LOW | Prevents holiday false alarms |
| HC-04 OHLC sanity | MEDIUM | LOW | Data integrity baseline |
| HC-03 Volume rate | LOW | MEDIUM | Requires exchange tagging |
| HC-06 Dedup | LOW | LOW | Defensive; likely already works |

None of these are authorized in S57. All require pipeline modification authorization.
