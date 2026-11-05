# V2 Shadow Signal Missing Data — Root Cause Analysis

**Session:** 14  
**Status:** Diagnosed. Code fixes applied. Neon schema migration + data init PENDING AUTHORIZATION.

---

## Summary

The "V2 進場時機研究 → 📋 訊號列表" page shows no data for `v2_research_v2` due to three layered causes. All have been diagnosed. Two require authorization to execute against Neon.

---

## Root Cause Layers

### Layer 1 — PRIMARY: Missing columns in Neon `v2_shadow_signals` (SCHEMA MISMATCH)

**What:** Neon `v2_shadow_signals` table exists (18 columns) but is missing `research_version` (VARCHAR 30) and `is_legacy` (BOOLEAN). The SQLAlchemy model defines both columns; the production table does not have them.

**Why:** `migrate_entry_timing_v2.py` uses `ResearchBase.metadata.create_all(engine, checkfirst=True)`. When the table already exists, `checkfirst=True` skips it entirely — it does **not** diff and add new columns. The model was updated to add these columns after the table was first created.

**Effect:** Every query that filters by `research_version` raises `psycopg2.errors.UndefinedColumn`. Before the fix, this was silently swallowed by a bare `except Exception` → `return []`.

**Fix applied (code):** `scripts/migrate_entry_timing_v2.py` now has a `_migrate_columns()` step that:
1. Inspects the existing table for missing columns.
2. Executes `ALTER TABLE v2_shadow_signals ADD COLUMN research_version ...` and `ADD COLUMN is_legacy ...` if absent.
3. Creates `ix_v2_shadow_signals_research_version` index.
4. Respects `--dry-run`.

**Pending authorization (Neon DDL):** Run the migration against Neon:
```bash
python scripts/migrate_entry_timing_v2.py          # production Neon
python scripts/migrate_entry_timing_v2.py --dry-run  # preview only
```

---

### Layer 2 — SECONDARY: `v2_shadow_signals` has 0 rows (SERVICES NEVER RUN)

**What:** Even after the schema is fixed, the table will be empty. `EntryTimingResearchService.run_for_date()` has never been run against Neon.

**Source data available:** 1,750 ForwardSignals in Neon for 2026-10-29 to 2026-11-04 (confirmed via direct query).

**Pipeline to populate data (requires authorization for Neon writes):**

Step 1 — Produce `v2_research_v1` rows:
```python
from src.research.entry_timing_research_service import EntryTimingResearchService
svc = EntryTimingResearchService(research_session=sess, prod_session=sess)
for trade_date in [date(2026, 10, 29), ..., date(2026, 11, 4)]:
    svc.run_for_date(trade_date)
```

Step 2 — Produce `v2_research_v2` rows (corrected `_load_history`):
```python
from src.research.shadow_recalculation_service import ShadowRecalculationService
ShadowRecalculationService(research_session=sess, prod_session=sess).recalculate()
```

---

### Layer 3 — TERTIARY: Silent exception masking (DASHBOARD BUG — FIXED)

**What:** `_load_v2_signals()` caught all exceptions with `except Exception: return []`. A schema error (column missing) looked identical to empty data — both returned `[]`. The error message told users to run internal service class names, which is not useful for general operation.

**Fix applied (code):** `dashboard/_pages/entry_timing_research.py`:
- `_load_v2_signals()` now catches `ProgrammingError`/`OperationalError` specifically and returns `[_V2_SIGNALS_SCHEMA_ERROR]` sentinel; non-schema exceptions return `[_V2_SIGNALS_CONNECTION_ERROR]`; empty query returns `[]`.
- `_render_signal_list()` now shows distinct messages per error type:
  - Schema error → actionable migration instructions.
  - Connection error → environment check guidance.
  - Empty result → clear two-step initialization instructions (no internal function names).

---

## Verification Evidence

| Check | Result |
|---|---|
| Neon `v2_shadow_signals` columns | 18 columns: NO `research_version`, NO `is_legacy` |
| Neon `v2_shadow_signals` row count | 0 rows |
| ForwardSignals in Neon | 1,750 rows (2026-10-29 to 2026-11-04) |
| SQL error type | `psycopg2.errors.UndefinedColumn` on `research_version` filter |
| Migration script defect | `create_all(checkfirst=True)` skips existing tables — documented SQLAlchemy behavior |
| Dashboard silent catch | `except Exception: return []` at line 101–103 (pre-fix) |

---

## Files Changed

| File | Change |
|---|---|
| `scripts/migrate_entry_timing_v2.py` | Added `_migrate_columns()` + `_REQUIRED_COLUMNS` for column-level migration |
| `dashboard/_pages/entry_timing_research.py` | Split silent exception; added sentinels; improved empty state messaging |
| `tests/test_v2_shadow_migration.py` | VM01–VM10: 10 new tests covering both fixes |

---

## Authorization Required Before Production Fix Is Complete

| Action | Authorization needed |
|---|---|
| `python scripts/migrate_entry_timing_v2.py` | Neon DDL (ALTER TABLE) |
| `EntryTimingResearchService.run_for_date()` × 5 dates | Neon research data write |
| `ShadowRecalculationService.recalculate()` | Neon research data write |

**Do not execute these against Neon without explicit authorization per Session 14 safety boundaries.**

---

## V2 / Hybrid Independence Confirmation

V2 Shadow Signal data (`v2_shadow_signals`) is **fully isolated** from production:
- Uses `ResearchBase` (separate `DeclarativeBase` from production `Base`)
- Never imported into `src/database.py`; never passed to `init_db()`
- Does NOT affect `MODEL_VERSION v8.0`, `foe_v1`, BUY/STRONG BUY thresholds, ForwardSignals, ACTUAL/PAPER accounting, Hybrid P1–P4 rules, or `hybrid_forward_decision` table

---

*Generated: Session 14, 2026-11-05*
