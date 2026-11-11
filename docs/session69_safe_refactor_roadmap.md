# Session 69 — Safe Refactor Roadmap

**Audit Date**: 2026-11-11  
**All items are PROPOSALS. Implementation requires user authorization.**

---

## Immutable Boundaries (Must Not Change)

The following are frozen regardless of any simplification:
- `MODEL_VERSION = "v8.0"` and all signal computations
- `foe_v1` outcome evaluation protocol and rules
- `RESEARCH_CUTOFF_DATE = 2026-10-09` and IS/OOS separation
- RC-2 patch (`4eb6eacf...`) — pending H3/H4 acceptance
- V3 frozen parameters (`be43e8ca977d9fdd`) — activation blocked
- Hybrid Entry P1–P4
- Cron schedule (`0 16 * * 1-5`)
- AUTH01/AUTH02 not authorized

---

## Phase 0 — No-Code Alignment (Documentation only)

**Prerequisite**: None. No authorization needed for doc changes.

| Task | Action | Files | Risk | Effort |
|---|---|---|---|---|
| P0-01 | Write Feature Registry (this doc set) | docs/ | NONE | DONE |
| P0-02 | Document trading_calendar.py vs hybrid_trading_calendar.py relationship | docs/ | NONE | XS |
| P0-03 | Document UserTrade (legacy) vs ActualPosition (new) migration path | docs/ | NONE | XS |
| P0-04 | Document 0050 intentional divergence (backfill keeps; UI excludes) | docs/ | NONE | XS |
| P0-05 | Confirm alpha calculation formula equivalence (backtest_service vs research_backtest_service) | Read-only | NONE | XS |
| P0-06 | Document session migration scripts (migrate_*.py) as "already executed" | docs/ | NONE | XS |

**Acceptance criteria**: All "UNKNOWN" items in duplicate audit resolved to VERIFIED.

---

## Phase 1 — UI-Only Simplification

**Prerequisite**: P0 complete. User authorization for code changes.

**Safety**: All changes are display/routing only. No computation changes. No data model changes. All existing routes preserved.

| Task | Action | Files Changed | Risk | Effort |
|---|---|---|---|---|
| P1-01 | Align main.py version label from v6.0 to v6.8 | main.py:68 | NONE | XS |
| P1-02 | Add "資料截至 {max_date}" banner to Tab 0 overview | overview.py + loaders.py | NONE | S |
| P1-03 | Add data freshness label to market_watch.py (EOD data) | market_watch.py | NONE | XS |
| P1-04 | Add prominent RESEARCH ONLY banner to research_backtest.py | research_backtest.py | NONE | XS |
| P1-05 | Add prominent RESEARCH ONLY banner to entry_timing_research.py | entry_timing_research.py | NONE | XS |
| P1-06 | Merge Tab 7 (個股) + Tab 8 (歷史) into single tab with toggle | app.py, reports.py | LOW | S |
| P1-07 | Remove Tab 3C (歷史) from position.py — keep Archive 交易記錄 as SSOT | position.py | LOW | S |
| P1-08 | Promote 資料健康 to Sidebar persistent link (not hidden in Archive) | app.py | NONE | XS |
| P1-09 | Add version/model label to research pages (MODEL_VERSION import, not hardcode) | research_backtest.py, scorecard.py | NONE | XS |
| P1-10 | Add "模型版本 v8.0 | 研究截止 2026-10-09" header to research tabs | research_backtest.py | NONE | XS |

**Regression test coverage needed**:
- Verify Tab 7+8 merge preserves all load_stock_history and load_recent_recs functionality
- Verify Tab 3C removal does not break position.py loading

**Rollback**: Git revert. All changes are UI-only.

---

## Phase 2 — Shared Presentation Components

**Prerequisite**: Phase 1 complete. User authorization.

**Safety**: Extract repeated UI HTML/Python patterns into shared functions. No new computation. No new data model.

| Task | Action | Files | Risk | Effort |
|---|---|---|---|---|
| P2-01 | Extract `data_freshness_banner(max_date)` shared component | dashboard/loaders.py or new dashboard/components.py | LOW | S |
| P2-02 | Extract `research_only_banner(protocol_version)` shared component | dashboard/components.py | NONE | XS |
| P2-03 | Extract `sample_size_warning(n)` shared component (currently in evidence_presenter only) | dashboard/components.py | NONE | S |
| P2-04 | Shared Signal Card HTML builder (currently repeated in overview.py) | dashboard/components.py | LOW | M |
| P2-05 | IA restructure: implement Option B (5-tab layout) if P1 validated | app.py | MEDIUM | M |

**P2-05 note**: Only attempt after P1 is stable and tested for 1+ sessions.

**Acceptance criteria for each component**:
- Identical visual output to existing implementation
- Passes all existing page-level tests
- No change to data loading logic

---

## Phase 3 — Service Consolidation

**Prerequisite**: Phase 2 complete. Contract tests written first. User authorization.

**Safety**: Each item requires before/after output comparison.

| Task | Contract Test Required | Files | Risk | Effort |
|---|---|---|---|---|
| P3-01: Extract `TAIWAN_ROUND_TRIP_FEES_PCT` to config.py | YES — verify 0.585 propagates to all callers | config.py + 10+ files | LOW (pure constant) | M |
| P3-02: Replace raw sqlite3 in entry_timing_research.py with get_session() | YES — same query results | entry_timing_research.py | LOW (read-only page) | M |
| P3-03: Verify/document trading_calendar vs hybrid_trading_calendar boundary | YES — same date classifications | — | LOW | S |
| P3-04: Centralize alpha calculation if P0-05 confirms duplication | YES — identical outputs for all test dates | backtest_service.py + research_backtest_service.py + src/utils/ | MEDIUM | M |

**P3-01 Contract Tests**:
```python
# Golden fixture: for dates with known signals, net_return should be unchanged
assert BacktestService.compute_backtest_data()["ret_20d"][0] == BEFORE_VALUE
# Same for research_backtest_service
```

**P3-02 ORM Migration Test**:
```python
# Same rows returned for all V2 research queries via ORM vs sqlite3
assert orm_result == sqlite3_result for N test cases
```

**Rollback**: Git revert per file. Each item is independent.

---

## Phase 4 — Controlled Deprecation

**Prerequisite**: Phase 3 complete. All dependency checks passed. User authorization.

**Before any deprecation**: must verify ALL of:
- Not imported anywhere (grep)
- Not called by UI, CLI, cron, GitHub Actions
- Not referenced in tests (or tests updated)
- Research reproducibility not affected
- No external user/script dependencies

| Candidate | Safe to Hide? | Safe to Archive? | Safe to Remove? | Prerequisite |
|---|---|---|---|---|
| Archive Legacy驗證 (backtest.py) | YES (already in Archive) | SAFE_TO_ARCHIVE_UI | DO_NOT_REMOVE (reproducibility) | None |
| `user_trades` table + my_trades.py | NO (active write path) | NO | DO_NOT_REMOVE | Migration tool to actual_positions first |
| `migrate_*.py` (3 scripts) | YES (already not in nav) | SAFE_TO_ARCHIVE_UI | REFACTOR_CANDIDATE after confirming migrations complete | Verify all migrations ran |
| `run_live_collector.py` | UNKNOWN | UNKNOWN | DO_NOT_REMOVE until dependency verified | P0-02 investigation |
| `goodinfo_collector.py` | UNKNOWN | UNKNOWN | DO_NOT_REMOVE until import trace done | Grep for imports |
| Session research modules (src/research/session*) | YES | SAFE_TO_ARCHIVE_UI | DO_NOT_REMOVE (reproducibility) | None |
| `stock_research.db` (empty file at root) | YES | SAFE | SAFE_TO_REMOVE | Verify not imported |

---

## Blocked Items

The following refactors are BLOCKED pending other decisions:

| Item | Blocker |
|---|---|
| Any change to backfill_daily_prices.py | RC-2 H3/H4 acceptance pending |
| Any change to outcome_evaluation.py | foe_v1 frozen protocol |
| Any change to hybrid_shadow_cron.py | Active cron, authorized only |
| Any change to MODEL_VERSION | v8.0 frozen |
| V3 activation | ACTIVATION_BLOCKED |
| AUTH01/AUTH02 | NOT AUTHORIZED |
| Historical repair | NOT AUTHORIZED |
