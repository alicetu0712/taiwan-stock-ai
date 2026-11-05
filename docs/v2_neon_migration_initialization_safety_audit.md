# V2 Neon Migration & Initialization Safety Audit

**Session:** 16  
**Git HEAD:** 1c42cb3 (uncommitted Session 14/16 changes)  
**Status:** All safety checks PASS. Three independent approvals required before any production writes.

---

## PART B — Database Connection Map

| Component | Database | Table | Read/Write |
|---|---|---|---|
| Dashboard `_load_v2_signals()` | Neon (USE_NEON=true → DATABASE_URL) | `v2_shadow_signals` | Read |
| `EntryTimingResearchService.run_for_date()` | Neon (hardcoded `get_session()`) | `v2_shadow_signals` | Write |
| `EntryTimingResearchService._load_history()` | Neon (same session) | `daily_prices` | Read |
| `ShadowRecalculationService.recalculate()` | Caller-injected sessions (both → Neon) | `v2_shadow_signals` (W), `daily_prices` (R) | R+W |
| Hybrid Forward Shadow (`hybrid_shadow_cron.py`) | SQLite `data/platform.db` | `hybrid_forward_decision` | Write |
| ForwardSignals (source data) | Neon | `forward_signals` | Read-only by research |

**SQLite / Neon mixing:** None for V2 shadow. Hybrid Forward Shadow uses SQLite exclusively. No cross-DB coupling.

**DB isolation confirmed:** `v2_shadow_signals` and `v2_shadow_outcomes` live under `ResearchBase` (separate `DeclarativeBase`). Neither appears in production `Base.metadata.tables`. Neither is passed to `init_db()`.

---

## PART C — Neon Schema Read-only Audit

**Table:** `v2_shadow_signals`  
**Row count:** 0  
**Audit date:** 2026-11-05

### Current Columns (18 — STALE)

| Column | Type | Nullable | Default |
|---|---|---|---|
| id | INTEGER | NOT NULL | nextval(...) |
| trade_date | DATE | NOT NULL | — |
| stock_id | VARCHAR(10) | NOT NULL | — |
| v1_decision_label | VARCHAR(30) | nullable | — |
| v1_pt_score | DOUBLE PRECISION | nullable | — |
| v1_setup_type | VARCHAR(20) | nullable | — |
| entry_label | VARCHAR(30) | nullable | — |
| dist_to_resistance_pct | DOUBLE PRECISION | nullable | — |
| ma20_gap_pct | DOUBLE PRECISION | nullable | — |
| rr_ratio | DOUBLE PRECISION | nullable | — |
| vol_ratio | DOUBLE PRECISION | nullable | — |
| prior_20d_high | DOUBLE PRECISION | nullable | — |
| stop_price | DOUBLE PRECISION | nullable | — |
| target_price | DOUBLE PRECISION | nullable | — |
| entry_price | DOUBLE PRECISION | nullable | — |
| created_at | TIMESTAMP | NOT NULL | — |
| data_bars | INTEGER | nullable | — |
| reasons_json | VARCHAR(500) | nullable | — |

**Missing columns (required by model):**
- `research_version VARCHAR(30) NOT NULL DEFAULT 'v2_research_v1'`
- `is_legacy BOOLEAN NOT NULL DEFAULT FALSE`

### Current Indexes

| Name | Unique | Columns |
|---|---|---|
| ix_v2_shadow_signals_stock_id | No | stock_id |
| ix_v2_shadow_signals_trade_date | No | trade_date |
| uq_v2ss_date_stock | Yes | (trade_date, stock_id) ← **STALE: missing research_version** |

### Model-Expected Constraint

```
uq_v2ss_date_stock_version  UNIQUE (trade_date, stock_id, research_version)
```

**Critical:** Old 2-column constraint will block `ShadowRecalculationService` from writing `v2_research_v2` rows alongside `v2_research_v1` rows for the same stock/date.

---

## PART D — Migration Dry-run Results

Command: `python scripts/migrate_entry_timing_v2.py --dry-run`

Output (confirmed no Neon writes):
```
[DRY-RUN] ADD COLUMN v2_shadow_signals.research_version
[DRY-RUN] CREATE INDEX ix_v2_shadow_signals_research_version
[DRY-RUN] ADD COLUMN v2_shadow_signals.is_legacy
[DRY-RUN] DROP CONSTRAINT uq_v2ss_date_stock ON v2_shadow_signals
[DRY-RUN] ALTER TABLE v2_shadow_signals ADD CONSTRAINT uq_v2ss_date_stock_version UNIQUE (trade_date, stock_id, research_version)

Dry-run complete — 3 change(s) would be applied.
```

### Dry-run Safety Verification

| Check | Result |
|---|---|
| Zero DDL executed against Neon | ✅ CONFIRMED (dry_run branch exits before engine.begin()) |
| No commit to Neon | ✅ CONFIRMED |
| No create_all() side effects | ✅ CONFIRMED (create_all only in `main()` for missing tables, not reached) |
| Correct columns listed | ✅ research_version + is_legacy |
| Correct constraint listed | ✅ DROP uq_v2ss_date_stock, ADD uq_v2ss_date_stock_version |
| Idempotent: second dry-run = same output | ✅ (by design: each step checks for existence) |
| Partial migration handled | ✅ Each column is its own transaction |
| Existing rows unaffected by ADD COLUMN | ✅ DEFAULT fills existing rows |

### Full Migration Plan

**Before schema:**
- 18 columns, missing research_version + is_legacy
- UNIQUE(trade_date, stock_id) — 2-column

**Planned DDL (execution order matters):**

```sql
-- Step 1a: Add research_version (transaction 1)
ALTER TABLE v2_shadow_signals
  ADD COLUMN research_version VARCHAR(30) NOT NULL DEFAULT 'v2_research_v1';

-- Step 1b: Index on research_version
CREATE INDEX IF NOT EXISTS ix_v2_shadow_signals_research_version
  ON v2_shadow_signals(research_version);

-- Step 1c: Add is_legacy (transaction 2)
ALTER TABLE v2_shadow_signals
  ADD COLUMN is_legacy BOOLEAN NOT NULL DEFAULT FALSE;

-- Step 2: Upgrade constraint (transaction 3 — atomic DROP + ADD)
-- research_version must exist before this step
ALTER TABLE v2_shadow_signals DROP CONSTRAINT uq_v2ss_date_stock;
ALTER TABLE v2_shadow_signals
  ADD CONSTRAINT uq_v2ss_date_stock_version
  UNIQUE (trade_date, stock_id, research_version);
```

**After schema:**
- 20 columns (all present)
- UNIQUE(trade_date, stock_id, research_version) — 3-column

**Estimated affected rows:** 0 (table is empty — zero data risk)

**Lock risk:** `ALTER TABLE ADD COLUMN DEFAULT` on PostgreSQL 11+ uses a fast path that avoids table rewrite. 0 rows = negligible lock duration.

**Rollback strategy:**
```sql
-- Rollback Step 2:
ALTER TABLE v2_shadow_signals DROP CONSTRAINT uq_v2ss_date_stock_version;
ALTER TABLE v2_shadow_signals ADD CONSTRAINT uq_v2ss_date_stock UNIQUE (trade_date, stock_id);
-- Rollback Step 1:
ALTER TABLE v2_shadow_signals DROP COLUMN is_legacy;
ALTER TABLE v2_shadow_signals DROP COLUMN research_version;
DROP INDEX ix_v2_shadow_signals_research_version;
```

**Verification SQL (post-migration):**
```sql
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'v2_shadow_signals'
  AND column_name IN ('research_version', 'is_legacy');
-- Expected: 2 rows

SELECT constraint_name, constraint_type
FROM information_schema.table_constraints
WHERE table_name = 'v2_shadow_signals' AND constraint_type = 'UNIQUE';
-- Expected: uq_v2ss_date_stock_version (NOT uq_v2ss_date_stock)
```

---

## PART E — Research Initialization Safety Audit

**Service:** `EntryTimingResearchService.run_for_date()`  
**Eligible trading dates:** 2026-10-29, 2026-10-30, 2026-11-02, 2026-11-03, 2026-11-04 (5 days)

| Item | Detail |
|---|---|
| Input table | `forward_signals` (Neon, read-only) |
| Output table | `v2_shadow_signals` (Neon, write) |
| Research version written | `v2_research_v1` (SQLAlchemy default) |
| Write method | `session.add()` + `session.commit()` per row |
| Unique key (post-migration) | `(trade_date, stock_id, research_version)` |
| Transaction boundary | 1 commit per signal row |
| Idempotency | Skip-check filters by `research_version == 'v2_research_v1'` (Session 16 fix) |
| Covers ForwardSignals? | ❌ Never modifies `forward_signals` |
| Covers Decision Center? | ❌ No `V2ShadowSignal` in `Base.metadata.tables` |
| Covers Hybrid Forward Shadow? | ❌ Writes to Neon only; Hybrid uses SQLite |

**Source data:**

| Date | ForwardSignals | Expected V1 inserts |
|---|---|---|
| 2026-10-29 | 323 | ≤ 323 (minus stocks with insufficient OHLC history) |
| 2026-10-30 | 361 | ≤ 361 |
| 2026-11-02 | 316 | ≤ 316 |
| 2026-11-03 | 369 | ≤ 369 |
| 2026-11-04 | 381 | ≤ 381 |
| **Total** | **1,750** | **≤ 1,750** (exact count requires dry-run) |

**Current existing rows:** 0 — no duplicates possible.

**Bug fixed (Session 16):** Skip-check now filters by `research_version == 'v2_research_v1'`. Previously, any existing row (including future `v2_research_v2`) would have blocked v1 generation.

**Run command (after Approval A):**
```python
from src.research.entry_timing_research_service import EntryTimingResearchService
from src.database import get_session
from datetime import date

svc = EntryTimingResearchService()
for td in [date(2026,10,29), date(2026,10,30), date(2026,11,2), date(2026,11,3), date(2026,11,4)]:
    processed, skipped, errors = svc.run_for_date(td)
    print(f"{td}: processed={processed} skipped={skipped} errors={errors}")
```

---

## PART F — Shadow Recalculation Safety Audit

**Service:** `ShadowRecalculationService.recalculate()`

| Operation | Target Table | INSERT | UPDATE | DELETE | Risk |
|---|---|---|---|---|---|
| Schema Migration | v2_shadow_signals | — | — | — | LOW |
| Historical Init (run_for_date) | v2_shadow_signals | ✅ per row | ❌ never | ❌ never | LOW |
| Recalculation | v2_shadow_signals | ✅ v2 rows | ❌ never | ❌ never | LOW |

| Check | Result |
|---|---|
| Reads `v2_research_v1` rows from [from_date, to_date] | ✅ |
| Skips if `v2_research_v2` already exists (idempotent) | ✅ |
| Writes only `research_version='v2_research_v2'` | ✅ |
| Does NOT delete, truncate, or update existing rows | ✅ APPEND-ONLY |
| Does NOT modify `v2_research_v1` rows | ✅ |
| Does NOT touch ForwardSignal | ✅ |
| Does NOT affect Hybrid Forward decisions | ✅ (SQLite-only) |
| Does NOT change created_at timestamps | ✅ |
| Does NOT change Prospective Classification | ✅ |

**Verdict:** `NOT HIGH_RISK_RECALCULATION` — pure append-only write.

---

## PART G — Isolation Scenario Results

All 8 scenarios tested via VM21–VM30. SQLite in-memory used for Scenarios A–H.

| Scenario | Test | Result |
|---|---|---|
| A: Empty Schema | VM21, VM22 | ✅ PASS |
| B: Existing Legacy Data | VM23 | ✅ PASS |
| C: Partial Migration | VM24 | ✅ PASS |
| D: Repeated Initialization | VM25 | ✅ PASS |
| E: Repeated Recalculation | VM26 | ✅ PASS |
| F: Failure / Rollback | VM27 | ✅ PASS |
| G: DB Mismatch (sentinel distinction) | VM28 | ✅ PASS |
| H: Research Isolation | VM29, VM30 | ✅ PASS |

**PostgreSQL constraint DDL** (DROP CONSTRAINT) not testable in SQLite. Verified via:
- VM13: `_CONSTRAINT_UPGRADES` spec matches `V2ShadowSignal.__table_args__`
- VM20: SQLite 2-col constraint correctly blocks v1+v2 coexistence (proves constraint matters)
- VM19: 3-col constraint correctly allows v1+v2 coexistence

---

## PART H — Dashboard Error Classification

| Error Type | Before Session 16 | After Session 16 |
|---|---|---|
| PostgreSQL `ProgrammingError` (missing column) | → schema sentinel ✅ | → schema sentinel ✅ |
| SQLite `OperationalError` "no such column" | → schema sentinel ✅ | → schema sentinel ✅ |
| PostgreSQL `OperationalError` "connection refused" | → schema sentinel ❌ (wrong) | → connection sentinel ✅ |
| General `Exception` (env/import error) | → connection sentinel ✅ | → connection sentinel ✅ |
| Empty result (schema OK, 0 rows) | → [] ✅ | → [] ✅ |

**Fix:** `OperationalError` now inspects error message — `"no such column"` / `"no such table"` → schema error; all others → connection error.

---

## PART I — Risk Assessment

### Phase 1 — Schema Migration

| Check | Result |
|---|---|
| Safe | ✅ — 0 existing rows, DEFAULT fills |
| Reversible | ✅ — full rollback DDL documented above |
| Data loss risk | ✅ NONE — ADD COLUMN with DEFAULT preserves all rows |
| Affects production trading | ✅ NONE — ResearchBase isolated from production Base |

**Risk: LOW**

### Phase 2 — Historical Research Initialization

| Check | Result |
|---|---|
| New data only | ✅ — no existing rows to overwrite |
| Look-ahead risk | ✅ NONE — analyzer uses `DailyPrice.date <= as_of` |
| Repeatable | ✅ — skip-check is idempotent |
| Modifies ForwardSignals | ✅ NONE |

**Risk: LOW**

### Phase 3 — V2 Shadow Recalculation

| Check | Result |
|---|---|
| Overwrites existing results | ✅ NONE — append-only, skip if v2 exists |
| Version conflicts | ✅ NONE — unique constraint prevents duplicates |
| Affects Forward Research | ✅ NONE — purely research schema |
| Independently verifiable | ✅ — compare entry_label v1 vs v2 in report |

**Risk: LOW**

---

## PART J — Approval Plan

### Approval A — Neon Schema Migration

**Command:** `python scripts/migrate_entry_timing_v2.py`

**Exact DDL to be executed:**
```sql
-- Transaction 1
ALTER TABLE v2_shadow_signals
  ADD COLUMN research_version VARCHAR(30) NOT NULL DEFAULT 'v2_research_v1';
CREATE INDEX IF NOT EXISTS ix_v2_shadow_signals_research_version
  ON v2_shadow_signals(research_version);

-- Transaction 2
ALTER TABLE v2_shadow_signals
  ADD COLUMN is_legacy BOOLEAN NOT NULL DEFAULT FALSE;

-- Transaction 3 (atomic)
ALTER TABLE v2_shadow_signals DROP CONSTRAINT uq_v2ss_date_stock;
ALTER TABLE v2_shadow_signals
  ADD CONSTRAINT uq_v2ss_date_stock_version
  UNIQUE (trade_date, stock_id, research_version);
```

**Prerequisite:** None  
**Estimated rows affected by DDL:** 0 data rows changed, 2 columns added  
**Lock risk:** Negligible (empty table)  
**Rollback:** Documented in PART D above  
**Verification:** Column + constraint check SQL in PART D above  

---

### Approval B — Historical Research Initialization

**Prerequisite:** Approval A must be complete first.

**Run:** `EntryTimingResearchService.run_for_date()` for each of:
- 2026-10-29, 2026-10-30, 2026-11-02, 2026-11-03, 2026-11-04

**Source:** `forward_signals` (1,750 rows in Neon, read-only)  
**Target:** `v2_shadow_signals` with `research_version = 'v2_research_v1'`  
**Expected inserts:** ≤ 1,750 (exact count TBD — stocks with < 21 bars are skipped)  
**Idempotent:** ✅ safe to re-run  
**Modifies ForwardSignals:** ❌ never  
**Modifies Decision Center / Hybrid:** ❌ never  
**Rollback:**
```sql
DELETE FROM v2_shadow_signals WHERE research_version = 'v2_research_v1';
```

---

### Approval C — V2 Shadow Recalculation

**Prerequisite:** Approval B must be complete first (v1 rows must exist as source).

**Run:** `ShadowRecalculationService.recalculate(research_session, prod_session, from_date, to_date)`  
**Recalculation scope:** rows where `research_version = 'v2_research_v1'` in [2026-10-29, 2026-11-04]  
**Writes:** New rows with `research_version = 'v2_research_v2'`, `is_legacy = False`  
**Write mode:** Append-only — never updates or deletes existing rows  
**Existing data protection:** Skip-check prevents duplicates  
**Verification:** Compare `entry_label` distribution between v1 and v2 versions  
**Rollback:**
```sql
DELETE FROM v2_shadow_signals WHERE research_version = 'v2_research_v2';
```

**Three approvals are independent and sequential. Approval A ≠ auto-authorization for B or C.**

---

## PART K — Summary Verdict

| Area | Verdict | Evidence |
|---|---|---|
| Neon Read-only Schema Audit | COMPLETE | Neon queried; 18 cols, 0 rows, stale constraint confirmed |
| Migration Dry-run | PASS — READY | Dry-run output verified, 0 Neon writes |
| Initialization Safety | SAFE | Append-only, skip-check fixed, no production impact |
| Recalculation Safety | SAFE | Pure append, no DELETE/UPDATE, isolated |
| SQLite Isolation Tests | PASS 31/31 | VM01–VM30 all green |
| PostgreSQL Constraint DDL | SPEC VERIFIED | VM13, VM19, VM20 — live PostgreSQL needs Approval A |
| Dashboard Error Classification | FIXED | `OperationalError` correctly split |
| Forward Research Isolation | CONFIRMED | ResearchBase ≠ Base; no production table overlap |

### Answers to Key Questions

1. **V2 Shadow 頁面空白的根本原因是否已完全確認？** ✅ YES — 3 layers: missing columns, 0 rows, silent exception
2. **Neon Migration 是否安全？** ✅ YES — empty table, DEFAULT fills, full rollback documented
3. **是否真的需要新增欄位？** ✅ YES — `research_version` and `is_legacy` confirmed absent in Neon
4. **歷史研究初始化是否安全？** ✅ YES — append-only, skip-check fixed, no production side effects
5. **Recalculation 是否可能覆寫資料？** ✅ NO — append-only, skip-check prevents duplicates
6. **是否需要分階段授權？** ✅ YES — 3 sequential approvals (A → B → C)
7. **哪些項目已通過驗證？** Migration dry-run, 31 isolation tests, Ruff clean, 1,700 total tests
8. **哪些項目仍有風險？** PostgreSQL constraint DDL not live-tested (needs Approval A execution)
9. **是否有正式資料被修改？** ✅ NO — 0 Neon writes in this session
10. **下一步建議授權哪一項？** **Approval A** (schema migration) — lowest risk, prerequisite for B and C

### Overall Verdict

**READY_FOR_APPROVAL_A**

Approval A (schema migration) is safe, reversible, and confirmed via dry-run. Grant Approval A independently. Do not execute B or C until A is confirmed complete.

---

## Changed Files (Session 16)

| File | Change |
|---|---|
| `scripts/migrate_entry_timing_v2.py` | Added `_migrate_constraints()` + `_CONSTRAINT_UPGRADES`; fixed column transaction isolation |
| `src/research/entry_timing_research_service.py` | Fixed skip-check: added `research_version == 'v2_research_v1'` filter |
| `dashboard/_pages/entry_timing_research.py` | Split `OperationalError` by message; improved schema error UI text |
| `tests/test_v2_shadow_migration.py` | VM01–VM30 (31 tests); Scenarios A–H; constraint + skip-check tests |

**Test count:** 1,669 → 1,700 (+31)  
**Neon writes:** 0  
**ForwardSignals row count:** 1,750 (unchanged)  
**Hybrid Decision count:** No change (SQLite, not touched)

---

*Generated: Session 16, 2026-11-05*
