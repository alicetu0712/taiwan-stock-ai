# DailyPrice Quality Gate

**Component:** `src/research/dailyprice_quality_gate.py`  
**Used by:** `scripts/backfill_daily_prices.py` (before every DB write)  
**Tests:** `tests/test_dailyprice_quality_gate.py` (DP01–DP20, 21 tests)

---

## 1. Purpose

The quality gate validates DailyPrice data fetched from TWSE/TPEx APIs before writing to local SQLite. It prevents:
- Writing wrong-date data (API returned data for a different date)
- Writing corrupted OHLC data (open > high, etc.)
- Writing data from incomplete API responses (too few stocks → API may have failed)
- Silently corrupting MA20 calculations used by the shadow runner

---

## 2. Checks

| Check ID | Category | Severity | Description |
|----------|----------|----------|-------------|
| QG-0 | Schema | Error | Required columns (stock_id, date, open, high, low, close, volume) all present |
| QG-1 | OHLC integrity | Error | `low ≤ min(open, close)` and `high ≥ max(open, close)` and all values > 0 |
| QG-2 | Price bounds | Error | `price_min ≤ close ≤ 20,000` (TWSE: min=0.10; TPEx: min=0.01 for penny stocks) |
| QG-3 | Volume | Error | `volume ≥ 0` (0 is allowed for trading halts) |
| QG-4 | Duplicates | Error | No stock_id appears more than once in a single batch |
| QG-5 | Date consistency | Error | Every row's date == the target date requested |
| QG-6 | Coverage | Error | Batch size ≥ min_expected_stocks (TWSE: 300; TPEx: 50) |
| QG-7 | Benchmark | Error | `0050` present in TWSE batch (required for MA20 regime calculation) |

**Result:** `QualityGateResult.passed = False` if any error-severity check fails. Warnings do not block.

---

## 3. Market-Specific Thresholds

| Setting | TWSE | TPEx | Rationale |
|---------|------|------|-----------|
| `price_min` | 0.10 | 0.01 | TPEx has legitimate penny stocks trading ≥ NT$0.01 |
| `min_stocks` | 300 | 50 | TWSE lists ~1,200 stocks; TPEx lists ~5,700; thresholds are conservative lower bounds |
| `require_benchmark` | True (0050) | False | 0050 is TWSE-listed, not on TPEx |

---

## 4. QG-5 Date Consistency — Critical Guard

**Why it exists:** Both TWSE and TPEx OpenAPI endpoints return "most recent available" data. If the API hasn't updated for today yet (market hasn't closed, or there's a delay), requesting today's data returns yesterday's.

Without QG-5, the backfill script would silently write 11-04 data under an 11-05 key, corrupting the trading calendar.

**Behavior:**
- Backfilling 2026-11-04 when TWSE returns 2026-11-04 → ✓ passes QG-5, writes
- Backfilling 2026-11-05 when TWSE returns 2026-11-04 → ✗ fails QG-5, does not write
- Backfilling 2026-10-29 when TWSE returns 2026-11-04 → ✗ fails QG-5, does not write

This prevents writing any wrong-date data into the DB.

---

## 5. Usage

```python
from src.research.dailyprice_quality_gate import run_quality_gate
import pandas as pd
from datetime import date

df = pd.DataFrame([...])  # columns: stock_id, date, open, high, low, close, volume
result = run_quality_gate(df, target_date=date(2026, 11, 4), market="TWSE")

if result.passed:
    # Safe to write
    write_to_db(df)
else:
    for issue in result.issues:
        print(f"  [{issue.severity.upper()}] {issue.check}: {issue.detail}")
```

### Auditing existing data

```python
import sqlite3
from src.research.dailyprice_quality_gate import audit_existing_data

conn = sqlite3.connect("data/platform.db")
result = audit_existing_data(conn, date(2026, 11, 4), market="TWSE")
print(result.summary_str())
# → [QualityGate PASS] 2026-11-04 TWSE: 1242/1242 rows OK, 0 errors, 0 warnings
```

---

## 6. Test Coverage

| Test ID | What it verifies |
|---------|-----------------|
| DP01–DP05 | Valid batches pass (TWSE, TPEx, exact threshold, zero volume, None change_pct) |
| DP06–DP10 | QG-1 OHLC failures (low > close, high < open, zero close, negative low) |
| DP11–DP13 | QG-2 price bound failures (too low, too high, exact boundary) |
| DP14–DP15 | QG-3 volume (negative fails, zero passes) |
| DP16–DP17 | QG-4 duplicate detection |
| DP18 | QG-5 wrong date fails |
| DP19 | QG-6 below threshold fails |
| DP20 | QG-7 missing 0050 fails |
| audit test | `audit_existing_data()` on empty DB |

---

## 7. 2026-11-04 Live Results

```
[QualityGate PASS] 2026-11-04 TWSE: 1242/1242 rows OK, 0 errors, 0 warnings
[QualityGate PASS] 2026-11-04 TPEx: 5715/5715 rows OK, 0 errors, 0 warnings
```

TWSE 1,242 stocks (OpenAPI fallback, api_date=2026-11-04 ✓)  
TPEx 5,715 stocks (ROC date param, api_date=2026-11-04 ✓)
