# Session 71M — RC-2 / QG Preservation

**Session**: 71M  
**Verdict**: `RC2_SEMANTICS_PRESERVED` / `QG_PRESERVED_VERIFIED`

---

## RC-2 Filter

| Item | Original | Guarded | Match |
|---|---|---|---|
| Hash (`backfill_daily_prices.py`) | `4eb6eacf...` | UNCHANGED (production) | ✓ UNCHANGED |
| Hash (`backfill_daily_prices_guarded.py`) | — | `202e2231...` (new) | — |
| RC-2 filter code | `if len(sid) > 4: return True` | IDENTICAL | ✓ IDENTICAL |
| RC-2 location | lines 93-100 | guarded lines ~110-120 (offset by guard imports) | ✓ PRESERVED |

**Important**: The whole-file hash of `backfill_daily_prices_guarded.py` DIFFERS from the original — this is EXPECTED and explicitly documented in the spec. The RC-2 filter semantics are UNCHANGED.

---

## Quality Gate Preservation

The guard check in `run_backfill()` runs at step 1, BEFORE any QG call:

```
Guard check (new) → _verify_sqlite() → connect() → _find_missing_dates() 
  → fetch providers → run_quality_gate() ← QG unchanged
```

QG-1~QG-7 logic in `run_quality_gate()` is imported from `src.research.dailyprice_quality_gate` and is **not modified in any S71M file**.

**Guard module isolation**: `scheduler_safety_guards.py` does not import or reference any QG functions (verified by M-19 and L-14 tests).

---

## Semantic Diff: Guard Additions Only

Changes to `run_backfill()` in guarded version:
```
+ _lock_path parameter (optional, default None)
+ _get_cron_lock_path() call to derive lock path
+ BackfillEntryGuard.check_original_entry() check
+ Early return if guard blocks (guard_blocked=True)
```

No changes to:
- EXCLUDE_KEYWORDS
- `_is_excluded()` function (RC-2 filter)
- `_verify_sqlite()`
- `run_quality_gate()` calls
- `_write_df_to_sqlite()` calls
- `conn.commit()` semantics
- `fetch_twse_historical()` / `fetch_tpex_historical()`

---

## Test Coverage

- M-18: RC-2 filter semantically identical (line-level comparison) ✓
- M-18b: Original backfill RC-2 hash `4eb6eacf...` unchanged ✓
- M-19: QG preserved; guard before QG in call order ✓
- L-13 (S71L): RC-2 hash sentinel ✓
- L-14 (S71L): Guard module has no QG imports ✓
