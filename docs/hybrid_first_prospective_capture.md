# Hybrid Forward Shadow — First Prospective Capture

**Rule freeze date:** 2026-11-05  
**Classification gating:** `RULE_FREEZE_DATE = date(2026, 11, 5)` in `src/research/hybrid_forward_db.py`  
**Status (2026-11-05 session):** AWAITING — pending 11-05 DailyPrice backfill (~15:30 Taiwan time)

---

## 1. What "PROSPECTIVE" Means

A decision record is classified `PROSPECTIVE` when:

1. `trade_date >= RULE_FREEZE_DATE` (2026-11-05) — signals captured *after* research rules were frozen
2. `trading_days_since_trade <= MAX_PROSPECTIVE_CAPTURE_DAYS` (1) — data was captured within 1 trading day of the signal date

Signals before the freeze date are always `RETROSPECTIVE_RECONSTRUCTION`.

```python
# src/research/hybrid_forward_db.py
RULE_FREEZE_DATE = date(2026, 11, 5)
MAX_PROSPECTIVE_CAPTURE_DAYS = 1

def classify_capture(trade_date, trading_days_since_trade, ...):
    if trade_date < RULE_FREEZE_DATE:
        return CaptureClassification.RETROSPECTIVE_RECONSTRUCTION
    if trading_days_since_trade <= MAX_PROSPECTIVE_CAPTURE_DAYS:
        return CaptureClassification.PROSPECTIVE
    return CaptureClassification.LATE_CAPTURE
```

**Why it matters:** Retrospective signals are optimized *after seeing outcomes*. Prospective signals are recorded *before* outcomes are known. Only PROSPECTIVE signals count as OOS (out-of-sample) evidence.

---

## 2. `trading_days_since_trade` Calculation

The shadow runner computes:
```python
trading_days_since = max(0, cal.count_trading_days(today, last_data_date) - 1)
```

Where:
- `today` = `trade_date` passed to the runner (default: `date.today()`)
- `last_data_date` = `MAX(date)` from `daily_prices WHERE stock_id='0050'`
- `cal.count_trading_days(a, b)` = trading days in `[a, b]` inclusive (data-driven from 0050 prices)

| Scenario | today | last_data_date | count | trading_days_since | Classification |
|----------|-------|----------------|-------|--------------------|----------------|
| Ideal: same day | 11-05 | 11-05 | 1 | 0 | PROSPECTIVE ✓ |
| One day stale (run 11-06 for 11-05) | 11-05 | 11-06 | 2 | 1 | PROSPECTIVE ✓ |
| Data not yet available | 11-05 | 11-04 | 0 | 0 | INVALID_DATA ✗ |
| Two trading days late | 11-05 | 11-07 | 3 | 2 | LATE_CAPTURE ✗ |

**INVALID_DATA guard:** `classify_capture` returns `INVALID_DATA` if `input_data_as_of < trade_date`. This prevents classifying 11-05 signals as PROSPECTIVE when the shadow runner only has 11-04 data — even if `trading_days_since=0`.

---

## 3. HybridTradingCalendar Dependency

The `HybridTradingCalendar` is **data-driven** — it only recognizes dates that have actual 0050 price records in SQLite:

```python
def is_trading_day(self, d: date) -> bool:
    return d in self._set  # only dates with 0050 data in DB
```

**Consequence:** The shadow runner returns `SKIPPED_NON_TRADING_DAY` for any date not yet in the DB, even if it is an actual trading day. DailyPrice must be backfilled first.

---

## 4. Preconditions for First PROSPECTIVE

| Precondition | Status | Action |
|-------------|--------|--------|
| RULE_FREEZE_DATE reached | ✓ 2026-11-05 | No action needed |
| 11-05 DailyPrice available (TWSE market closes 13:30) | ⏳ Waiting | Manual/cron backfill |
| 11-05 data passes QG-5 (api_date == target) | ⏳ Waiting | Automatic via backfill |
| HybridTradingCalendar recognizes 11-05 | ⏳ After backfill | Automatic |
| Shadow runner produces `PROSPECTIVE` classification | ⏳ After calendar | Run shadow runner |

---

## 5. Steps to Generate First PROSPECTIVE

After Taiwan market closes and data is published (~15:30):

```bash
# Step 1: Dry-run to verify 11-05 is now detected as missing
python3 scripts/backfill_daily_prices.py

# Step 2: Execute backfill for 11-05
python3 scripts/backfill_daily_prices.py --execute

# Step 3: Run shadow for today (default: today = 11-05)
python3 scripts/run_hybrid_forward_shadow.py

# Step 4: Verify classification
python3 -c "
import sqlite3
conn = sqlite3.connect('data/platform.db')
rows = conn.execute(
    'SELECT stock_id, trade_date, hybrid_action, capture_classification '
    'FROM hybrid_forward_decision WHERE trade_date >= \"2026-11-05\" LIMIT 5'
).fetchall()
for r in rows:
    print(r)
conn.close()
"
```

Expected output:
```
('1234', '2026-11-05', 'DIRECT_NEXT_OPEN', 'PROSPECTIVE')
...
```

---

## 6. Session Log

| Date | Action | Result |
|------|--------|--------|
| 2026-11-05 AM | Backfilled 2026-11-04 (6,957 rows) | SUCCESS |
| 2026-11-05 AM | Shadow run for 11-04 | 21 decisions, RETROSPECTIVE_RECONSTRUCTION |
| 2026-11-05 AM | Shadow run for 11-05 (before 15:30) | SKIPPED_NON_TRADING_DAY (expected) |
| 2026-11-05 PM | *Pending* Backfill 11-05 + shadow run | AWAITING |

---

## 7. What Happens If Data Is Unavailable

If TWSE/TPEx API does not return 11-05 data (e.g., API delay):
- QG-5 check rejects data: `api_date=11-04 != target=11-05`
- Backfill writes 0 rows
- HybridTradingCalendar still doesn't know 11-05
- Shadow runner returns `SKIPPED_NON_TRADING_DAY`
- **No PROSPECTIVE record is generated** ← correct behavior

The mandate is: **record 0 valid signals rather than fabricate data.**

---

## 8. Idempotency Contract

If shadow is re-run after 11-05 is already captured:
- Same `(stock_id, trade_date, rule_version)` → `inserted=0, skipped=N, conflicts=0`
- If decision_hash changes (different rule evaluation) → `ConflictError` logged (not silently overwritten)
- Run log records every execution even if 0 new decisions

---

## 9. PROSPECTIVE OOS Evidence Accumulation

After 2026-11-05, each trading day adds N new PROSPECTIVE records to `hybrid_forward_decision`. Outcomes (5D/10D/20D returns) are computed by the shadow runner once sufficient price history exists (`--backfill-outcomes-only`).

Query to track accumulation:
```sql
SELECT trade_date, capture_classification, COUNT(*) as n
FROM hybrid_forward_decision
WHERE trade_date >= '2026-11-05'
GROUP BY trade_date, capture_classification
ORDER BY trade_date;
```
