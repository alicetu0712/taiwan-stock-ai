# Session 71N — RC-2 / QG Semantic Diff

**Session**: 71N  
**Verdict**: `RC2_SEMANTICS_PRESERVED` / `QG_PRESERVED`

---

## RC-2 Filter: Verification

### Production File Status

| File | SHA256 | Status |
|---|---|---|
| `backfill_daily_prices.py` | `4eb6eacf6c65df52aae037731e66e4573a8ae929af807c0fbd7c1adcac4c5afb` | UNCHANGED ✓ |

### Guarded File — AST-level Comparison

**EXCLUDE_KEYWORDS** (AST comparison — exact values, not string diff):
```
Original:  ['ETF', 'ETN', 'REIT', 'REITs', '特別股', '受益憑證', 'DR', 'DEPOSITARY', 'WARRANT', 'WARRANTS']
Guarded:   ['ETF', 'ETN', 'REIT', 'REITs', '特別股', '受益憑證', 'DR', 'DEPOSITARY', 'WARRANT', 'WARRANTS']
RESULT: IDENTICAL ✓
```

**`_is_excluded()` function** (string comparison):
```
RESULT: IDENTICAL ✓
```

**RC-2 filter call sites** (line numbers differ due to added imports/constants):
```
Original:  lines 125, 214, 273
Guarded:   lines 146, 235, 294
Offset:    +21 lines (guard imports, _DEFAULT_LOCK_FILE, _get_cron_lock_path)
Semantics: IDENTICAL ✓
```

---

## Changes Between Original and Guarded (Full Diff Summary)

**Added at top of guarded file** (before all original content):
1. Import: `from scripts.scheduler_safety_guards import BackfillEntryGuard`
2. Constant: `_DEFAULT_LOCK_FILE = Path(DB_PATH).parent / ".cron.lock"`
3. Function: `_get_cron_lock_path(db_path=None, _override=None)`

**Added in `run_backfill()` signature**:
- New parameter `_lock_path=None` (test isolation only)

**Added in `run_backfill()` body** (before any other logic):
```python
if execute:
    lock_path = _get_cron_lock_path(db_path, _lock_path)
    authorized, reason = BackfillEntryGuard.check_original_entry(
        is_execute=True, lock_path=lock_path
    )
    if not authorized:
        return {"guard_blocked": True, ...}
```

**Added in `main()` body** (before `run_backfill()` call):
```python
if args.execute:
    lock_path = _get_cron_lock_path(args.db)
    authorized, reason = BackfillEntryGuard.check_original_entry(...)
    if not authorized:
        sys.exit(2)
```

**NOT changed** (verified by inspection):
- `EXCLUDE_KEYWORDS` values
- `_is_excluded()` function body
- `_verify_sqlite()` function
- `run_quality_gate()` calls
- `_write_df_to_sqlite()` calls
- `conn.commit()` semantics
- `fetch_twse_historical()` and `fetch_tpex_historical()` calls
- Trading calendar logic
- SQLite write target path
- Post-write freshness logic
- Model or signal logic

---

## Hash Change After Deploy A

After `cp backfill_daily_prices_guarded.py backfill_daily_prices.py`:

| File | Pre-Deploy Hash | Post-Deploy Hash | Reason |
|---|---|---|---|
| `backfill_daily_prices.py` | `4eb6eacf...` | `202e2231...` | Guard additions |

**This hash change is EXPECTED and NOT a sign of RC-2 drift.**

The RC-2 filter semantics are preserved. The new hash is the new canonical baseline for this file.

**New rollback baseline must be recorded before deployment:**
- `4eb6eacf...` = rollback target (original)
- `202e2231...` = deployment candidate

---

## QG Preservation Verification

The guard check runs BEFORE any QG call:

```
Guard check → _verify_sqlite() → connect() → fetch providers → run_quality_gate() ← QG unchanged
```

`scheduler_safety_guards.py` does NOT import any QG modules:
```bash
$ grep 'quality_gate' scripts/scheduler_safety_guards.py
# (no output)
```

QG-1 through QG-7 logic in `src/research/dailyprice_quality_gate.py` is NOT modified in any S71N artifact.
