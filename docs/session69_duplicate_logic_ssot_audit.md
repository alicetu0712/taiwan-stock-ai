# Session 69 — Duplicate Logic & SSOT Audit

**Audit Date**: 2026-11-11  
**Execution Mode**: READ_ONLY_ARCHITECTURE_AUDIT

---

## 1. Duplicate Logic Candidates

### DL-01: MA Calculation — technical.py vs price_trend.py

| Item | Implementation A | Implementation B |
|---|---|---|
| File | `src/analyzers/technical.py` | `src/analyzers/price_trend.py` |
| Computed | MA5/10/20/60, setup_type (breakout/pullback_buy/trending/breakdown) | MA5/10/20/60, setup_type, MA slope, MA deviation (MA20_gap, MA60_gap) |
| Input | OHLCV DataFrame | OHLCV DataFrame |
| Output | `TechnicalResult` dataclass | `PriceTrendResult` dataclass |
| Called by | `main.py` pipeline → `TechnicalAnalyzer.analyze()` | `main.py` pipeline → `PriceTrendAnalyzer.analyze()`, `research_backtest_service.py` |
| Score contribution | `timing_score` (100-pt scale, V1 scorer) | `price_trend_score` (0-100, V2 architecture, 45% core) |
| MA formula | Pandas rolling mean (identical basis) | Same rolling mean |
| Setup taxonomy | breakout/pullback_buy/pullback_hold/trending/breakdown/none (6 types) | breakout/near_breakout/failed_breakout/pullback_buy/pullback_hold/ma60_support/trending/overextended/breakdown (9 types v8.0) |
| Evidence | VERIFIED (both files read) | VERIFIED |

**Classification**: `INTENTIONAL_VERSION_ISOLATION`

**Semantic difference**: price_trend.py is the V2 architecture replacement with richer setup taxonomy (9 vs 6 types) and additional MA slope/deviation analysis. technical.py's `timing_score` is part of V1 scorer. Both are called in the same pipeline because the scoring system uses both V1 and V2 components under MODEL_VERSION v8.0.

**Consolidation risk**: HIGH — merging would change MODEL_VERSION v8.0 signal outputs. NOT SAFE without full re-research.

**Recommendation**: DO_NOT_MERGE. Document the boundary clearly.

---

### DL-02: ROUND_TRIP_COST = 0.585

| Location | File | Context |
|---|---|---|
| A | `src/services/backtest_service.py:16` | Legacy backtest (Recommendation table) |
| B | `src/services/research_backtest_service.py:37` | IS/OOS research backtest |
| C | `src/research/v3_walk_forward.py:75` | V3 walk-forward (fees_pct=0.585) |
| D | `src/research/v3_comparison_engine.py:16` | V3 comparison engine |
| E | `src/research/comparison_readiness_report.py:21` | FEES_PCT = 0.585 |
| F | `src/research/execution_simulator.py:30` | SA-6 annotation |
| G+ | 10+ research modules | Scattered inline constants |

**Classification**: `SEMANTIC_DUPLICATE`

**Semantic differences**: All represent the same Taiwan round-trip transaction cost (buy 0.1425% + sell 0.4425%). Derivation comment is repeated verbatim in A and B. Some research modules use `fees_pct` as a local variable; others as module-level constant.

**Risk of divergence**: If the assumption changes (e.g., brokerage discount), it must be updated in 10+ places. Already a silent inconsistency risk.

**Recommendation**: Extract to `config.py` as `TAIWAN_ROUND_TRIP_FEES_PCT = 0.585`. Then import everywhere. LOW consolidation risk (pure constant, no logic change). **Phase 3 task**.

---

### DL-03: ETF/Warrant Exclusion Logic

| Item | Implementation A | Implementation B |
|---|---|---|
| File | `scripts/backfill_daily_prices.py::_is_excluded()` (lines 93-100, RC-2 patched) | `dashboard/loaders.py::_is_etf_or_excluded()` (lines 169-186) |
| Logic | `len(sid) > 4` → exclude ALL (post RC-2); EXCLUDE_KEYWORDS in name | `sid.startswith('0')` → ETF; alpha chars → warrant/DR; EXCLUDE_KEYWORDS; EXCLUDE_PATTERNS |
| Purpose | Controls what enters `daily_prices` table (DB ingestion filter) | Controls what appears in UI stock list (display filter) |
| Input | stock_id (string), name (string) | sid (string), name (string) |
| Called by | Backfill pipeline (cron) | `load_stock_names()`, `load_stock_list()` |
| 0050 behavior | NOT excluded (len=4) | Excluded (startswith('0')) |
| 00858 behavior | Excluded (len=5, post RC-2) | Excluded (startswith('0')) |
| 700022 behavior | Excluded (len=6) | Excluded (len>4, via EXCLUDE_PATTERNS inferred) |

**Classification**: `SIMILAR_BUT_DISTINCT`

**Key difference**: Implementation A is the production DB ingestion gate (RC-2 patch controls this). Implementation B is the UI display filter. They serve different masters:
- A decides what PRICE DATA is stored → affects data quality, all downstream
- B decides what STOCKS appear in UI dropdowns → affects UX only

**Critical gap**: 0050 behavior DIVERGES:
- A: 0050 IS in `daily_prices` (len=4, not excluded) ✓ correct — 0050 is the benchmark
- B: 0050 IS excluded from UI stock list (startswith('0')) ✓ correct — benchmark not shown as tradable

This divergence is CORRECT. 0050 must be in daily_prices (benchmark) but NOT in the trading stock UI. Do not merge.

**Recommendation**: Document the intentional divergence clearly. Add comments to both files. `SIMILAR_BUT_DISTINCT` — keep separate.

---

### DL-04: Trading Calendar

| Item | Implementation A | Implementation B |
|---|---|---|
| File | `src/core/trading_calendar.py` (233 lines) | `src/research/hybrid_trading_calendar.py` (111 lines) |
| Purpose | Production calendar (SSOT) | Research-specific wrapper |
| API | `is_trading_day()`, `next_trading_day()`, `prev_trading_day()`, `effective_trade_date()` | Research-only functions |
| Used by | main.py, live_monitor, loaders, cron | Research modules only |

**Classification**: `SIMILAR_BUT_DISTINCT` (INFERRED — file not fully read)

**Recommendation**: Confirm whether hybrid_trading_calendar wraps core/trading_calendar or reimplements. If wrapping: document clearly. If reimplementing: consolidation candidate for Phase 3.

---

### DL-05: Raw SQLite Access in entry_timing_research.py

**Finding**: `dashboard/_pages/entry_timing_research.py` contains 3 separate `sqlite3.connect()` calls at lines 1113, 1122, 1242, 1252, 1325, 1338, 1354.

**Risk**: 
- Bypasses SQLAlchemy ORM session management → no connection pooling, no migration safety
- Schema changes may silently break these queries
- Inconsistent with all other pages using `get_session()`
- Thread safety concerns under Streamlit's execution model

**Classification**: `REFACTOR_CANDIDATE`

**Recommendation**: Replace with `get_session()` + ORM queries. This is a Phase 1/2 fix with LOW business logic risk (read-only research page).

---

### DL-06: Alpha Calculation

| Item | Implementation A | Implementation B |
|---|---|---|
| File | `src/services/backtest_service.py::_alpha()` (line 43) | `src/services/research_backtest_service.py` (inline) |
| Formula | `ret - benchmark_ret` | Same (inferred) |

**Classification**: `INSUFFICIENT_EVIDENCE` — need to read both implementations fully to confirm.

**Recommendation**: Verify in Phase 0 documentation. If identical formula, extract to `src/utils/`.

---

## 2. SSOT Analysis

### SSOT-01: Stock Price Data

| Layer | Source | Purpose | Freshness |
|---|---|---|---|
| Authoritative | `daily_prices` (SQLite) | Historical EOD price | As of last successful cron write |
| Secondary | TWSE/TPEx Provider (HTTP) | Backfill source | Real-time (pre-QG) |
| Intraday | External collector (intraday_collector.py) |盤中 live monitor | Real-time |
| Neon sync | Via sync_to_neon.py | Cloud backup | Lag vs SQLite |

**SSOT**: `daily_prices` SQLite for historical. Provider for live backfill. Intraday collector for 盤中.

**Risk**: 看盤 and 盤中 may show different prices (EOD vs live). No freshness label currently.

**Gap**: Currently max_date = 2026-11-05 (5 trading days behind). Pages showing price data don't flag staleness to user. **SSOT_GAPS_IDENTIFIED**.

---

### SSOT-02: Trade Signals

| Table | Producer | Consumer | Type |
|---|---|---|---|
| `recommendations` | main.py pipeline | overview, search, history, backtest | Daily signal record |
| `forward_signals` | hybrid_shadow_cron | research_backtest, scorecard, evidence | Forward signal (OOS) |
| `analysis_results` | main.py pipeline | research_backtest (IS) | Research features |

**SSOT**: `recommendations` for trading decisions; `forward_signals` for research/forward tracking. These are parallel records of the same event at different lifecycle stages.

**Risk**: A signal appears in BOTH `recommendations` and `forward_signals` for the same date/stock. If they diverge (e.g., due to lifecycle updates), different pages could show different data for the same day. **SSOT_GAPS_IDENTIFIED**.

---

### SSOT-03: Position Data (Three Tables)

| Table | Storage | Write Path | Purpose | Status |
|---|---|---|---|---|
| `position_monitor` | Neon | hybrid_shadow_cron (auto) | PAPER/model simulation | Active |
| `actual_positions` | Neon | Dashboard UI (manual) | Real user trades | Active |
| `user_trades` | SQLite | Dashboard UI (manual, old) | Legacy trade record | Legacy |

**Gap**: `user_trades` (SQLite, legacy) and `actual_positions` (Neon, new) coexist. Users with legacy records see them in Tab 3C + Archive, but cannot migrate to `actual_positions`. Two sources for "my trades".

**Recommendation**: Phase 2 — provide migration tool or clearly label `user_trades` as "read-only legacy". Do NOT delete.

---

### SSOT-04: Research Results vs Forward Evidence

| Table | Cutoff | Protocol | Consumer |
|---|---|---|---|
| `analysis_results` (IS) | Before 2026-10-09 | In-Sample (look-ahead possible) | research_backtest |
| `forward_signals` (OOS) | After 2026-10-09 | Out-of-Sample (strict) | research_backtest, scorecard |
| `forward_outcome_evaluations` | After 2026-10-09 | foe_v1 (pre-registered) | evidence.py |

**SSOT**: Each table has clear ownership. The boundary is `RESEARCH_CUTOFF_DATE = 2026-10-09`. **SSOT_CONSISTENT** for this domain.

**Risk**: Any code that queries `forward_signals` without filtering by `model_version` could mix V1 and V2 research results. The `research_version` and `is_legacy` columns in `ForwardSignal` are the guard.

---

## 3. Summary Classification Table

| ID | Duplicate | Classification | Priority | Action |
|---|---|---|---|---|
| DL-01 | technical.py vs price_trend.py MA calc | INTENTIONAL_VERSION_ISOLATION | — | Document boundary |
| DL-02 | ROUND_TRIP_COST = 0.585 × 10+ | SEMANTIC_DUPLICATE | Phase 3 | Extract to config.py |
| DL-03 | ETF exclusion (backfill vs UI) | SIMILAR_BUT_DISTINCT | — | Document intentional divergence |
| DL-04 | trading_calendar vs hybrid_trading_calendar | SIMILAR_BUT_DISTINCT | Phase 0 | Verify relationship |
| DL-05 | Raw sqlite3 in entry_timing_research.py | REFACTOR_CANDIDATE | Phase 1 | Replace with get_session() |
| DL-06 | Alpha calculation | INSUFFICIENT_EVIDENCE | Phase 0 | Verify formulas |

---

## 4. SSOT Gap Register

| Gap | Tables | Risk | Recommendation |
|---|---|---|---|
| Price staleness not shown | daily_prices | MEDIUM (data freshness misrepresentation) | Add "as-of" label to all price displays |
| UserTrade vs ActualPosition coexist | user_trades, actual_positions | LOW | Label legacy clearly |
| Recommendations vs ForwardSignals parallel | recommendations, forward_signals | MEDIUM | Document lifecycle, add version guard |
| 0050 divergence (backfill vs UI) | daily_prices, stocks | INFORMATIONAL | Document as intentional |
