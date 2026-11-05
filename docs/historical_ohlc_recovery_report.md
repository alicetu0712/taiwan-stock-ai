# Historical OHLC Recovery Report — 2026-10-08 to 2026-11-05

**Date:** 2026-11-05  
**Status:** COMPLETE — all 10 recovery targets written; GateResult.PASS confirmed

---

## Scope

0050 (台灣50 ETF) is used as the market proxy by `OHLCContinuityGate`.  
Recovery targeted dates where 0050 data was absent or corrupted in `data/platform.db`,  
blocking the gate for a 30-day window ending 2026-11-05.

---

## Recovery Targets & Outcomes

| Date | Description | Action | Outcome |
|------|-------------|--------|---------|
| 2026-10-08 | Corrupt row (10-06 mislabeled as 10-08) | DELETE old + INSERT correct | WRITTEN close=114.95 |
| 2026-10-09 | Calendar holiday; DB had 7,586 mislabeled rows (10-07 data) | DELETE all 7,586 non-0050 + 0050 row | DELETED (not a trading day) |
| 2026-10-15 | Missing: gap in backfill pipeline | INSERT from TWSE STOCK_DAY | WRITTEN close=116.30 |
| 2026-10-19 | Missing: gap in backfill pipeline | INSERT from TWSE STOCK_DAY | WRITTEN close=116.05 |
| 2026-10-20 | Missing: gap in backfill pipeline | INSERT from TWSE STOCK_DAY | WRITTEN close=115.00 |
| 2026-10-27 | Missing: gap in backfill pipeline | INSERT from TWSE STOCK_DAY | WRITTEN close=114.60 |
| 2026-10-29 | Missing: gap in backfill pipeline | INSERT from TWSE STOCK_DAY | WRITTEN close=115.25 |
| 2026-10-30 | Missing: gap in backfill pipeline | INSERT from TWSE STOCK_DAY | WRITTEN close=112.80 |
| 2026-11-02 | Missing: gap in backfill pipeline | INSERT from TWSE STOCK_DAY | WRITTEN close=112.00 |
| 2026-11-03 | Missing: gap in backfill pipeline | INSERT from TWSE STOCK_DAY | WRITTEN close=107.75 |
| 2026-11-05 | TWSE STOCK_DAY_ALL returned wrong date; recovered individually | INSERT from TWSE STOCK_DAY | WRITTEN close=103.65 |

---

## Data Source

**API:** TWSE individual stock history  
`https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY?stockNo=0050&date=YYYYMMDD&response=json`

- Returns full monthly data for one stock (ROC calendar dates: `YYY/MM/DD`)
- Authoritative source; same data TWSE publishes in its official market stats
- Limitations: individual stock only (not bulk all-stocks); only public API available for historical dates

**Units (stored in DB):**
- `volume`: 千股 (`vol_shares / 1000`)
- `amount`: 百萬元 (`amt_NT$ / 1_000_000`)

---

## Why TWSE STOCK_DAY_ALL Cannot Be Used for Historical Recovery

`STOCK_DAY_ALL` returns LATEST trading day data for all ~1,700 stocks in one call.  
It does NOT support specifying a historical date — the `date` parameter is ignored.  
This makes bulk historical recovery for all stocks impossible via public TWSE APIs.

Only the 0050 market proxy can be efficiently recovered one month at a time.

---

## Safety Constraints Applied

1. **SQLite magic byte check** — refused to write if file is not SQLite format
2. **Dry-run default** — `--execute` flag required for actual writes
3. **Backup before write** — two backups created:
   - `data/platform_recover_backup_20261105_165923.db` (543,481 rows)
   - `data/platform_recover_backup_20261105_170018.db` (528,182 rows — after deletions)
4. **Quality gate** — OHLC consistency check (low ≤ min(open,close), high ≥ max(open,close))
5. **Local SQLite only** — Neon production DB was NOT touched

---

## DB State After Recovery

| Metric | Before (backup) | After (live) |
|--------|----------------|--------------|
| Total rows | 543,481 | 528,182 |
| Corrupt 10-08 rows deleted | — | 7,722 (non-0050 mislabeled data) |
| 10-09 rows deleted | — | 7,586 (confirmed holiday, mislabeled 10-07) |
| 0050 rows inserted | — | 10 |
| integrity_check | OK | OK |
| foreign_key violations | 0 | 0 |

---

## Gate Result

```
check_market(conn, date(2026, 11, 5)):
  gate_result     = GateResult.PASS
  present_sessions = 30
  missing_sessions = 0
  unknown_sessions = 0
```

The gate was previously BLOCKED_MISSING_OHLC (≥10 missing sessions).  
After recovery, it is now PASS — Hybrid signal generation is unblocked for 2026-11-05.

---

## Non-0050 Stocks

The 7,722 non-0050 rows with mislabeled 10-08 data were deleted.  
These stocks no longer have 10-08 OHLC data — their stock-level gates will  
correctly block them on 10-08 rather than passing with wrong MA values.

Bulk recovery for individual stocks is not feasible via public TWSE APIs.  
Stock-level gaps from 10-08 and earlier will naturally age out of the  
30-day gate window by approximately 2026-12-01.

---

## Script

`scripts/recover_ohlc_0050.py` — idempotent, dry-run by default, ruff-clean.
