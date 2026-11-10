# TWSE PIT Universe — Session 60

## S59 → S60 Correction

Session 59 hardcoded 712 as the number of eligible TWSE stocks for recovery. Session 60 runs a live query and returns a higher, more accurate figure.

| Measure | Value | Source |
|---------|-------|--------|
| S59 hardcoded | 712 | Manual estimate, prior session |
| S60 Aug2026+ query | 720 | Live DB query (see below) |
| S60 Nov05 actual | 717 | Live DB query (most recent full trading day) |
| S60 all-time | 727 | Live DB query (all dates) |
| Recommended denominator | 720 | Aug2026+ (covers recovery scope) |

## Query Methodology

**Aug2026+ eligible stocks:**
```sql
SELECT COUNT(DISTINCT dp.stock_id)
FROM daily_prices dp
INNER JOIN stocks s ON s.stock_id = dp.stock_id
WHERE s.market = 'TWSE'
  AND dp.date >= '2026-08-01'
  AND LENGTH(dp.stock_id) = 4
  AND dp.stock_id GLOB '[0-9][0-9][0-9][0-9]'
```

This query identifies stocks that have appeared in TWSE daily prices since August 2026 and are present in the official `stocks` table. It is the most appropriate denominator for the Oct/Nov 2026 recovery window.

**Nov05 actual:**
```sql
SELECT COUNT(DISTINCT dp.stock_id)
FROM daily_prices dp
INNER JOIN stocks s ON s.stock_id = dp.stock_id
WHERE s.market = 'TWSE'
  AND dp.date = '2026-11-05'
  AND LENGTH(dp.stock_id) = 4
  AND dp.stock_id != '0050'
```

Nov05 is the last confirmed full data day (db_max = 2026-11-05). The 717 figure is a lower-bound on the PIT universe (some stocks may be listed but had no trading on that specific date).

## Request Budget

| Metric | S59 | S60 |
|--------|-----|-----|
| Eligible stocks | 712 | 720 |
| Months | 2 | 2 |
| Total API requests | 1,424 | 1,440 |
| Runtime estimate (2s delay) | ~47 min | ~48 min |
| Additional vs S59 | — | +16 requests, ~32 seconds |

## Discrepancy Explanation

The 8-stock difference (712 → 720) likely results from S59 applying a more restrictive filter or using a snapshot that excluded stocks with sporadic trading in the Aug–Nov window. The impact is negligible: 16 additional API calls, less than 1 minute of additional runtime.

## PIT Per Gap Date

The six gap dates (Oct29, Oct30, Nov02, Nov03, Nov06, Nov09) have zero rows in `daily_prices` for TWSE stocks. This confirms they are genuine data gaps requiring AUTH01 backfill, not partial-fetch anomalies.

## Authorization Status

AUTH01 is required to execute the 1,440 API calls. This authorization has not been granted. The PIT universe query is read-only and safe to run at any time.
