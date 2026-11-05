# Hybrid Forward Shadow — First Live Run Acceptance Criteria

**Date:** 2026-11-05  
**Status:** AWAITING FIRST VALID PROSPECTIVE CAPTURE

---

## PROSPECTIVE Capture Requirements

A decision is classified `PROSPECTIVE` if and only if ALL conditions are met:

| # | Condition | How Verified |
|---|-----------|-------------|
| 1 | `trade_date >= RULE_FREEZE_DATE` (2026-11-05) | `classify_capture()` check |
| 2 | `input_data_as_of >= trade_date` | QG-5 + Step 4b in cron |
| 3 | `trading_days_since_trade <= MAX_PROSPECTIVE_CAPTURE_DAYS` (1) | Computed from TradingCalendar |
| 4 | OHLC continuity gate: PASS | `check_market()` gate = PASS |
| 5 | 0050 DailyPrice present for trade_date | Coverage check in backfill |
| 6 | >= 1,000 non-0050 stocks present for trade_date | New coverage check in `_find_missing_dates` |
| 7 | Hybrid P1–P4 rules frozen (RULE_VERSION unchanged) | `RULE_VERSION` constant in `hybrid_entry_strategy.py` |
| 8 | `captured_at` = actual save timestamp (UTC) | `datetime.now(timezone.utc)` at run time |
| 9 | No look-ahead: feature cutoff = trade_date | `feature_cutoff_date = today` in shadow runner |

A decision CANNOT be PROSPECTIVE if:
- `trade_date < 2026-11-05` → RETROSPECTIVE_RECONSTRUCTION (21 such decisions already exist)
- `input_data_as_of < trade_date` → INVALID_DATA
- `trading_days_since_trade > 1` → LATE_CAPTURE

---

## Current DB State (2026-11-05)

```
hybrid_forward_decision:
  RETROSPECTIVE_RECONSTRUCTION: 21  (trade_date=2026-11-04, captured 2026-11-05)
  PROSPECTIVE:                    0  (not yet captured)

hybrid_forward_run_log (last runs):
  2026-11-04  SUCCESS  inserted=21  (RETROSPECTIVE_RECONSTRUCTION)
  2026-11-05  SKIPPED_NON_TRADING_DAY  (run before 11-05 OHLC was in DB; TradingCalendar said non-trading)
```

---

## Why 2026-11-05 Decisions Have Not Been Captured Yet

1. The shadow runner was attempted on 2026-11-05 before OHLC data was recovered for that date.
2. `TradingCalendar.from_db(conn)` builds its date list from 0050's DailyPrice records.
3. At the time of the run (UTC 01:14 = Taiwan 09:14), 0050 had no 11-05 data → calendar said non-trading.
4. Result: `SKIPPED_NON_TRADING_DAY`.

5. Since then, 0050 was manually recovered for 11-05 — but non-0050 stocks are still missing 11-05 data (TWSE STOCK_DAY_ALL API returns 11-04 data as of Taiwan 17:19).
6. The shadow runner needs `_get_stocks_on_date(conn, 2026-11-05)` to return >= 1 stock.

---

## First PROSPECTIVE Capture Acceptance Test (Manual)

After cron runs with `--execute` and succeeds for the first time on a date >= 2026-11-05:

### Step 1: Verify run log
```sql
SELECT trade_date, status, inserted_count, started_at
FROM hybrid_forward_run_log
ORDER BY started_at DESC
LIMIT 1;
```
Expected: `status='SUCCESS'`, `inserted_count > 0`

### Step 2: Verify classifications
```sql
SELECT capture_classification, COUNT(*) 
FROM hybrid_forward_decision 
WHERE trade_date >= '2026-11-05'
GROUP BY capture_classification;
```
Expected: `PROSPECTIVE > 0` (or `LATE_CAPTURE` if captured next day)

**NOT acceptable:** `INVALID_DATA` decisions (indicates data or classification bug)

### Step 3: Verify no look-ahead
```sql
SELECT MIN(trade_date - input_data_as_of) AS min_gap
FROM hybrid_forward_decision
WHERE capture_classification = 'PROSPECTIVE';
```
Expected: `min_gap >= 0` (input_data_as_of always <= trade_date)

### Step 4: Verify decision hash stability
Run the shadow runner twice with `--date <same_date>` and confirm:
- Second run: `inserted=0` (idempotent — duplicates skipped)
- No `CONFLICT` errors

### Step 5: Verify append-only
```sql
-- Look for any update or delete events on hybrid_forward_decision
-- (This table must be INSERT-only after initial capture)
SELECT COUNT(*) FROM hybrid_forward_decision 
WHERE captured_at < '2026-11-05';  -- should be 21 (RETROSPECTIVE only)
```

---

## Capture Classification Summary

| Classification | Condition | Research Value |
|----------------|-----------|----------------|
| PROSPECTIVE | trade_date on day of capture, fresh data | ✅ Full value — genuine out-of-sample |
| LATE_CAPTURE | trade_date captured next day, fresh data | ⚠️ Acceptable — minor timing delay |
| RETROSPECTIVE_RECONSTRUCTION | trade_date < 2026-11-05 | ℹ️ Backfill only — not OOS evidence |
| INVALID_DATA | Input data not available at capture time | 🛑 Must not exist — indicates bug |

---

## Go/No-Go for First PROSPECTIVE Run

| Condition | Current Status |
|-----------|---------------|
| OHLC gate PASS | ✅ PASS |
| 0050 data for trade_date | ✅ 2026-11-05 |
| Non-0050 stocks for trade_date | ⏳ TWSE not yet published as of 17:19 Taiwan |
| Cron installed | ⏳ Awaiting approval |
| Rules frozen (RULE_VERSION) | ✅ Frozen at v1_hybrid |

---

## Expected First PROSPECTIVE Run Timeline

If cron is approved and installed:
1. **Earliest valid capture for 2026-11-05**: After TWSE publishes all stocks' data for 11-05 (usually 15:30-16:00 Taiwan). Cron scheduled at 16:00 Taiwan.
2. **If 11-05 is missed**: 11-06 becomes the first PROSPECTIVE date (cron captures next trading day).
3. **LATE_CAPTURE window**: If captured on 11-06 for 11-05 trade_date, `trading_days_since_trade=1 <= MAX_PROSPECTIVE_CAPTURE_DAYS=1` → still PROSPECTIVE.

---

## What Makes a Valid Evidence Set

For the Hybrid V1 effectiveness measurement to be meaningful:
- **Minimum PROSPECTIVE decisions**: 100+ across multiple trade_dates
- **Minimum maturity**: 20 trading days per decision for 20D outcomes
- **Estimated availability of first 20D outcomes**: ~2026-12-10 (20 trading days after 11-05)

Until then: "尚無足夠前瞻樣本，等待後續交易日資料成熟。"
