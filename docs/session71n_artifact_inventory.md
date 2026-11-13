# Session 71N — Deployment Artifact Inventory

**Session**: 71N  
**Verdict**: `ARTIFACT_SET_COMPLETE` (Deployment A — Safety Guard Runtime)

---

## Full Artifact Table

| File | Type | SHA256 | Required for Deploy A? | Dependency |
|---|---|---|---|---|
| `scripts/hybrid_shadow_cron.py` | PRODUCTION (read-only) | `46209171...` | NO (unchanged) | Calls `backfill_daily_prices.py` by name |
| `scripts/backfill_daily_prices.py` | PRODUCTION → REPLACED | `4eb6eacf...` → `202e2231...` | YES (target file) | Called by wrapper by name |
| `scripts/scheduler_safety_guards.py` | NEW → MUST DEPLOY | `f6929a7c...` | YES (guard module) | Imported by guarded backfill |
| `scripts/backfill_daily_prices_guarded.py` | CANDIDATE (source) | `202e2231...` | YES (source of cp) | Imports safety_guards |
| `scripts/backfill_daily_prices_protected.py` | CANDIDATE (unused in Deploy A) | `7aa3a602...` | NO for Deploy A | - |
| `scripts/hybrid_shadow_cron_integrated.py` | CANDIDATE (unused in Deploy A) | `dc474aa2...` | NO for Deploy A | - |

---

## Critical Finding: Deploy A does NOT require replacing the wrapper

The original `hybrid_shadow_cron.py` hardcodes:
```python
cmd = [PYTHON, str(SCRIPTS_DIR / "backfill_daily_prices.py")]
```

After `cp backfill_daily_prices_guarded.py backfill_daily_prices.py`, the original wrapper automatically calls the guarded version — **no wrapper modification required**.

---

## Is it really just one `cp`?

**No.** Two files are needed:

### File 1 — `scheduler_safety_guards.py` (MUST deploy first or simultaneously)

The guarded backfill imports it:
```python
from scripts.scheduler_safety_guards import BackfillEntryGuard
```

If `scheduler_safety_guards.py` does not contain `check_original_entry()` and `_check_lock_state()`, the import will fail or raise `AttributeError`, breaking backfill entirely.

**Verification**: The current `scripts/scheduler_safety_guards.py` (hash `f6929a7c...`) already contains all required methods. It is an **additive change** to the existing production file — no production functionality is removed.

### File 2 — `backfill_daily_prices.py` (replace with guarded version)

The actual `cp`:
```bash
cp scripts/backfill_daily_prices_guarded.py scripts/backfill_daily_prices.py
```

---

## Minimum Deploy A Artifact Set

```
DEPLOY  scripts/scheduler_safety_guards.py      (replace: f6929a7c... already in place)
REPLACE scripts/backfill_daily_prices.py        (cp from guarded: 202e2231...)
KEEP    scripts/hybrid_shadow_cron.py           (UNCHANGED: 46209171...)
IGNORE  scripts/backfill_daily_prices_protected.py  (not needed for Deploy A)
IGNORE  scripts/hybrid_shadow_cron_integrated.py    (Deploy B only)
```

---

## Artifact Status

`scheduler_safety_guards.py` is ALREADY deployed to the working directory (hash `f6929a7c...`). The only missing step for Deploy A is replacing `backfill_daily_prices.py` with the guarded version.

**Deploy A artifact set**: `COMPLETE` (both required files present and verified)
