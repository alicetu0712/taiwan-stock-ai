# Session 71I — RC-2 Runtime Verification

**Document Status**: AWAITING_OBSERVATION  
**Preflight Timestamp**: 2026-11-11 22:06 CST  
**Target Schedule**: 2026-11-12 16:00 CST  
**H3 Status**: H3_PENDING

---

## 1. Static Verification (Completed at Preflight)

### 1.1 On-disk File Hashes

| File | Expected SHA256 | Actual SHA256 | Verdict |
|---|---|---|---|
| `scripts/backfill_daily_prices.py` | `4eb6eacf6c65df52aae037731e66e4573a8ae929af807c0fbd7c1adcac4c5afb` | `4eb6eacf6c65df52aae037731e66e4573a8ae929af807c0fbd7c1adcac4c5afb` | ✓ **MATCH** |
| `scripts/hybrid_shadow_cron.py` | `46209171e00eb46429d0e36d02c106b87cf3684b13803ccdf53369042ba060d4` | `46209171e00eb46429d0e36d02c106b87cf3684b13803ccdf53369042ba060d4` | ✓ **MATCH** |

**Static Verdict**: `HASH_VERIFIED` — On-disk files match expected RC-2 hashes.

**Important limitation**: On-disk hash ≠ runtime-loaded version. Static verification proves the file is correct on disk, but does NOT prove what Python interpreter loaded at execution time. Runtime evidence is required for `RC2_RUNTIME_VERIFIED`.

### 1.2 Python Interpreter in Crontab

| Item | Value |
|---|---|
| Interpreter | `/Library/Frameworks/Python.framework/Versions/3.13/bin/python3` |
| Script path | `/Users/alicetu/Desktop/Antigravity/stock_platform/scripts/hybrid_shadow_cron.py` |
| Working directory | Implicit (script uses absolute paths) |

### 1.3 RC-2 Filter Code (Static)

```python
# backfill_daily_prices.py lines 93-100
def _is_excluded(name: str, stock_id: str) -> bool:
    name_up = str(name).upper()
    if any(kw.upper() in name_up for kw in EXCLUDE_KEYWORDS):
        return True
    sid = str(stock_id).strip()
    if len(sid) > 4:   # ← RC-2 filter: exclude 5+ digit stock_ids
        return True
    return False
```

**Static Verdict**: RC-2 filter confirmed at correct location in correct file.

---

## 2. Runtime Evidence Checklist (PENDING)

### 2.1 Execution Path Confirmation

| Check | Expected | Actual | Verified |
|---|---|---|---|
| Log shows subprocess call to backfill | `Running: ...backfill_daily_prices.py --execute` | PENDING | — |
| Subprocess path matches crontab entry | `/Users/alicetu/Desktop/.../backfill_daily_prices.py` | PENDING | — |
| Python version at runtime | Python 3.13 | PENDING | — |

### 2.2 RC-2 Filter Runtime Evidence

| Check | Expected | Actual | Verified |
|---|---|---|---|
| Any 5+ digit stock codes in `dates_processed` count | ZERO (filtered out) | PENDING | — |
| Filter execution via `_is_excluded()` | Implicit (no explicit log) | PENDING | — |
| Post-run: SQLite has ZERO 5+ digit entries at new dates | YES (if write occurred) | PENDING | — |

### 2.3 Filter Effect Evidence Limitations

The RC-2 filter (`_is_excluded()`) does NOT produce explicit log output when it excludes a stock. Evidence of filter effect comes indirectly from:
1. **New date added with 0 five-digit entries** (strongest evidence)
2. **`total_filtered` or similar counter in log** (if logged by backfill)
3. **Absence of 5+ digit entries in SQLite at new date** (requires write to have occurred)

If the run results in `BLOCKED_STALE_DATA` (no write to SQLite), evidence type 1 and 3 are unavailable. Only type 2 may be available.

---

## 3. Anticipated Scenarios

### Scenario A: QG PASS → Write Occurs

```
Expected log pattern:
[cron] dates_to_backfill: ['2026-11-12', '2026-11-11', '2026-11-10', '2026-11-09', '2026-11-06']
[backfill] dates_processed: 5
[backfill] total_inserted: ~32,000+
[backfill] total_filtered: N (implicit — 5-digit codes excluded)
```

Post-write SQLite check:
```sql
SELECT COUNT(*) FROM daily_prices WHERE LENGTH(stock_id) > 4 AND date = '2026-11-12';
-- Expected: 0 (RC-2 filter applied)
```

### Scenario B: QG FAIL → No Write (BLOCKED_STALE_DATA)

```
Expected log pattern:
[backfill] errors: 3+
  • 2026-11-12: TWSE api_date=2026-11-11 != target — quality gate FAILED
[cron] BLOCKED_STALE_DATA (after 3 retries)
```

SQLite: Unchanged (534,770 rows, max 2026-11-05)

In Scenario B, RC-2 filter runtime evidence is limited to log inspection only.

---

## 4. Post-observation Evidence (CONFIRMED)

**Observation timestamp**: 2026-11-12 20:08 CST

### Cron did not run
No new log entries, no state file update. The pipeline was not invoked on Nov 12.

### On-disk hash re-verification (post-observation)
Both file hashes remain unchanged:
- `backfill_daily_prices.py`: `4eb6eacf...` ✓
- `hybrid_shadow_cron.py`: `46209171...` ✓

### SQLite — no change
No new dates added. 5+ digit check at any date > Nov 05: 0 rows (unchanged).

---

## 5. Verdict

| Item | Value |
|---|---|
| **On-disk Hash** | `HASH_VERIFIED` ✓ |
| **Runtime Version** | `RC2_RUNTIME_NOT_OBSERVED` |
| **Filter Effect** | `RC2_FILTER_NOT_OBSERVED` |
| **Reason** | Cron did not trigger (machine asleep at 16:00 CST) |
| **Overall RC-2 Verdict** | **NOT_OBSERVED** (not FAIL — no execution occurred) |

---

## 6. Post-Observation Update Instructions

After 2026-11-12 16:05 CST, run:

```bash
# Check log for backfill subprocess call and filter evidence
grep -E "(Running:|dates_processed|total_inserted|total_filtered|_is_excluded|len.*sid)" \
  /Users/alicetu/Desktop/Antigravity/stock_platform/logs/hybrid_cron.log | tail -20

# Check SQLite for five-digit entries at new date (if write occurred)
sqlite3 /Users/alicetu/Desktop/Antigravity/stock_platform/data/platform.db \
  "SELECT date, COUNT(*) FROM daily_prices WHERE LENGTH(stock_id) > 4 GROUP BY date ORDER BY date DESC LIMIT 5;"

# Verify file hash unchanged at runtime
shasum -a 256 /Users/alicetu/Desktop/Antigravity/stock_platform/scripts/backfill_daily_prices.py
```
