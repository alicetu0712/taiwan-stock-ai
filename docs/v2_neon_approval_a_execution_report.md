# Approval A Execution Report — Neon Schema Migration

**Date:** 2026-11-05  
**Git HEAD:** 1c42cb3  
**Executor:** Session 17 (Claude Code)  
**Authorization:** User explicitly authorized Approval A only.  
**Scope:** Add `research_version` / `is_legacy` columns; upgrade unique constraint 2-col → 3-col; create index.  
**NOT executed:** Approval B (data initialization), Approval C (recalculation).

---

## PART B — Pre-Migration Safety Gate (all PASS)

| Check | Result |
|---|---|
| Git HEAD | 1c42cb3 |
| DB host | Neon PostgreSQL (ep-lively-butterfly-…-pooler) |
| Target table | `v2_shadow_signals` |
| Column count (baseline) | 18 (research_version: absent, is_legacy: absent) |
| Row count | 0 ✅ |
| Existing unique constraint | `uq_v2ss_date_stock` ON (trade_date, stock_id) ← 2-col stale ✅ |
| forward_signals count | 1,750 ✅ |
| Abort conditions | None triggered |

---

## PART C — Migration SQL Review

**Atomicity fix:** Original `main()` called `_migrate_columns()` and `_migrate_constraints()` in separate transactions. Refactored to use `_pending_columns()` and `_pending_constraints()` as pure inspection/planning functions, then execute ALL DDL in a single `engine.begin()` context.

**Standalone helpers** (`_migrate_columns()`, `_migrate_constraints()`) preserved for unit test backward compatibility (VM01–VM15).

**Dry-run output (confirmed before execution):**
```
[DRY-RUN] ADD COLUMN v2_shadow_signals.research_version
[DRY-RUN] CREATE INDEX ix_v2_shadow_signals_research_version
[DRY-RUN] ADD COLUMN v2_shadow_signals.is_legacy
[DRY-RUN] DROP CONSTRAINT uq_v2ss_date_stock ON v2_shadow_signals
[DRY-RUN] ALTER TABLE v2_shadow_signals ADD CONSTRAINT uq_v2ss_date_stock_version UNIQUE (trade_date, stock_id, research_version)

Dry-run complete — 3 change(s) would be applied.
```

**Execution order within single transaction:**
1. `ALTER TABLE v2_shadow_signals ADD COLUMN research_version VARCHAR(30) NOT NULL DEFAULT 'v2_research_v1'`
2. `CREATE INDEX IF NOT EXISTS ix_v2_shadow_signals_research_version ON v2_shadow_signals(research_version)`
3. `ALTER TABLE v2_shadow_signals ADD COLUMN is_legacy BOOLEAN NOT NULL DEFAULT FALSE`
4. `ALTER TABLE v2_shadow_signals DROP CONSTRAINT uq_v2ss_date_stock`
5. `ALTER TABLE v2_shadow_signals ADD CONSTRAINT uq_v2ss_date_stock_version UNIQUE (trade_date, stock_id, research_version)`

Steps 4-5 follow 1-3 within the same transaction — `research_version` column exists before it is referenced in the new constraint.

---

## PART D — Execution Output

```
ADD COLUMN v2_shadow_signals.research_version
CREATE INDEX ix_v2_shadow_signals_research_version
ADD COLUMN v2_shadow_signals.is_legacy
DROP CONSTRAINT uq_v2ss_date_stock ON v2_shadow_signals
ALTER TABLE v2_shadow_signals ADD CONSTRAINT uq_v2ss_date_stock_version UNIQUE (trade_date, stock_id, research_version)
✓ Added 2 missing column(s) to v2_shadow_signals
✓ Upgraded 1 constraint(s) on v2_shadow_signals
```

Exit code: 0

---

## PART E — Post-Migration Verification (all PASS)

| Check | Expected | Actual | Status |
|---|---|---|---|
| `research_version` column | VARCHAR(30), NOT NULL | VARCHAR(30), NOT NULL | ✅ PASS |
| `is_legacy` column | BOOLEAN, NOT NULL | BOOLEAN, NOT NULL | ✅ PASS |
| Index `ix_v2_shadow_signals_research_version` | columns=[research_version] | columns=['research_version'] | ✅ PASS |
| Constraint `uq_v2ss_date_stock_version` | (trade_date, stock_id, research_version) | ['trade_date', 'stock_id', 'research_version'] | ✅ PASS |
| Old constraint `uq_v2ss_date_stock` | absent | absent | ✅ PASS |
| `v2_shadow_signals` row count | 0 | 0 | ✅ PASS |
| `forward_signals` row count | 1,750 | 1,750 | ✅ PASS |

---

## PART F — Idempotency Check

```
✓ V2 shadow tables already exist and schema is up to date — nothing to do.
```

Dry-run after migration reports "nothing to do" — no duplicate DDL risk.

---

## PART G — Dashboard Read-Only Verification

`_load_v2_signals()` SQLAlchemy query executed directly against Neon:
- No `ProgrammingError` (schema now valid) ✅
- Returns `[]` (0 rows, correct state before Approval B) ✅
- Dashboard will render "尚無 V2 研究訊號" (no data yet) instead of schema error message ✅

---

## PART H — Regression Tests

| Suite | Count | Status |
|---|---|---|
| Full test suite | **1,706 passed** | ✅ |
| New VM31/VM32 tests | 7 tests | ✅ |
| Ruff lint | 0 errors | ✅ |

Previous count was 1,679. Delta +27 from VM31/VM32 additions (7 tests) plus prior session additions.

---

## Changed Files

| File | Change |
|---|---|
| `scripts/migrate_entry_timing_v2.py` | Atomicity refactor: `_pending_columns()`, `_pending_constraints()`, atomic `main()` |
| `tests/test_v2_shadow_migration.py` | Added VM31a–VM31e, VM32 (7 tests); updated docstring |

---

## Current State

**Neon `v2_shadow_signals` schema:** ✅ Matches `src/research/models.py` V2ShadowSignal exactly.  
**v2_shadow_signals rows:** 0 (Approval B not yet run).  
**Dashboard:** Renders "no data yet" (not schema error) for both v2_research_v1 and v2_research_v2 tabs.

---

## Next Steps (require separate authorization)

**Approval B — Research Initialization** (not yet authorized):
```python
from src.research.entry_timing_research_service import EntryTimingResearchService
for d in ["2026-10-29", "2026-10-30", "2026-11-02", "2026-11-03", "2026-11-04"]:
    service.run_for_date(d)
```
Prerequisites: Approval A complete ✅, ForwardSignals available (1,750 rows) ✅.

**Approval C — Shadow Recalculation** (not yet authorized):  
Requires Approval B complete; generates `v2_research_v2` rows via `ShadowRecalculationService`.
