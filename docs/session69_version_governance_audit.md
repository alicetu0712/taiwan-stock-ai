# Session 69 — Version & Naming Governance Audit

**Audit Date**: 2026-11-11

---

## 1. Version Registry

| Version Label | Value | Where Defined | What It Controls | Status |
|---|---|---|---|---|
| Product UI Version (dashboard) | `v6.8` | `dashboard/app.py:65` page_title | UI display only | Active |
| Product UI Version (CLI) | `v6.0` | `main.py:68` log output | CLI display only | **Stale — mismatch with v6.8** |
| MODEL_VERSION | `v8.0` | `src/database.py:39` | ForwardSignal.model_version, Recommendation filtering, signal computation | FROZEN — production |
| V1_MODEL_VERSION | `v8.0` | `src/database.py:38` | Historical v8.0 signal identification | FROZEN |
| foe_v1 | `foe_v1` | `src/engines/outcome_evaluation.py`, `src/database.py:676` | Forward outcome evaluation protocol | FROZEN |
| RESEARCH_CUTOFF_DATE | `2026-10-09` | `src/database.py:33` | IS/OOS research boundary | FROZEN |
| V2 Research Version | `v2_research_v1`, `v2_research_v2` | `entry_timing_research.py:27` | V2 entry timing research labels | Research |
| V3 Parameter Hash | `be43e8ca977d9fdd` | `src/research/v3_backtest_engine.py` etc. | V3 frozen parameters | FROZEN (activation blocked) |
| Canonical V2 SHA-256 | `6a133e8cca47bcb25bbc528557e4a00efa2c91e387158c208aef6d2d0dbecf8f` | Research docs | V2 baseline integrity | FROZEN |
| RC-2 Patched Hash | `4eb6eacf...` | Deployed working tree | backfill_daily_prices.py integrity | DEPLOYED (H3 pending) |
| Hybrid Entry | P1–P4 | Research docs | Hybrid entry strategy phases | FROZEN |
| _CUTOFF_LABEL | `"2026-10-09"` | `research_backtest.py:15` | UI display of cutoff | Matches RESEARCH_CUTOFF_DATE |
| SD_VERSION | `v2` | Cron diagnostics | Scheduler diagnostics version | Tool |
| CANDIDATE_POOL_VERSION | (in candidate_pool_service.py) | `src/services/candidate_pool_service.py` | Pool versioning | Active |

---

## 2. Naming Inconsistencies

| Concept | Name A | Name B | Name C | Files |
|---|---|---|---|---|
| Product version | `v6.0` (CLI) | `v6.8` (Dashboard) | — | main.py, app.py |
| In-sample research | `analysis_results` (table) | `AnalysisResult` (ORM) | `In-Sample` (UI label) | database.py, research_backtest.py |
| Out-of-sample | `forward_signals` (table) | `ForwardSignal` (ORM) | `Out-of-Sample` (UI label) | database.py |
| Legacy backtest | `Legacy 驗證` (UI) | `backtest.py` (file) | `BacktestService` (class) | app.py, backtest.py |
| Trade fee | `ROUND_TRIP_COST` (const) | `fees_pct` (V3 var) | `FEES_PCT` (research) | backtest_service.py, v3_walk_forward.py, comparison_readiness_report.py |
| Research evidence | `🔒證據` (UI) | `EvidencePresenter` (class) | `foe_v1` (protocol) | app.py, evidence_presenter.py |
| Model signal | `BUY` (UI) | `trade_signal` (DB col) | `decision_label` (ForwardSignal) | database.py |
| Portfolio simulation | `PAPER` (UI position tab) | `position_monitor` (table) | `PositionMonitor` (ORM) | database.py, position.py |
| Actual trade | `ACTUAL` (UI position tab) | `actual_positions` (table) | `ActualPosition` (ORM) | database.py, position.py |
| Setup pattern | `breakout` (v8.0) | `breakout_buy` (old v7) | `Breakout` (UI card) | technical.py, price_trend.py, market_watch.py |

---

## 3. Missing Version Labels in UI

| Page | Missing Label | Risk |
|---|---|---|
| Tab 0 今日 | "資料截至 YYYY-MM-DD" on market summary | User assumes data is current |
| Tab 2 看盤 | No EOD vs live price distinction | MEDIUM — data freshness misrepresentation |
| Tab 5 研究回測 | No "模型版本 v8.0 / 研究截止 2026-10-09" header | User may not know which model they're viewing |
| Tab 6 進場時機 | "RESEARCH ONLY" is in docstring only, not UI | User may treat research as live signal |
| Archive 成績單 | No "ForwardSignal v8.0 only" note | — |
| Archive Legacy驗證 | "Legacy" label present ✓ | — |

---

## 4. Deprecation Status Register

| Feature | Explicitly Deprecated? | Evidence | Recommendation |
|---|---|---|---|
| Legacy 驗證 (backtest.py) | YES — moved to Archive, labeled "Legacy" | app.py:366 | ARCHIVE — maintain read access |
| UserTrade (user_trades table) | Partial — still in position.py Tab 3C | database.py:365 | Mark as "legacy records" |
| V1 research (is_legacy=True ForwardSignals) | YES — is_legacy flag | database.py ForwardSignal | KEEP for research reproducibility |
| V2 research v1 (v2_research_v1) | Partial — badge shows "legacy v1" | entry_timing_research.py:50 | ARCHIVE label in UI |
| V3 (blocked) | YES — ACTIVATION_BLOCKED | docs, research modules | DO_NOT_REMOVE (research preserved) |
| migration scripts (3 files) | No — but likely already run | scripts/migrate_*.py | ARCHIVE with note "already executed" |
| run_live_collector.py | No explicit deprecation | scripts/ | UNKNOWN — needs investigation |
| goodinfo_collector.py | No explicit deprecation | src/collectors/ | UNKNOWN — investigate if still called |

---

## 5. Recommended Naming Convention

### A. Product Version Policy
- Dashboard title: `v{MAJOR}.{MINOR}` (e.g., `v6.8`)
- CLI header: sync with dashboard version
- **Action**: Update `main.py:68` from `v6.0` to `v6.8` (UI only, no model impact)

### B. Model Version Policy
- Production model: always `MODEL_VERSION` from `src/database.py` (currently `v8.0`)
- Never hardcode `"v8.0"` in page UI — always import from `src.database.MODEL_VERSION`
- Research versions: `{strategy}_{researcher_version}` (e.g., `v2_research_v2`)

### C. Feature Status Labels
| Status | Label | Meaning |
|---|---|---|
| Production | (no badge) | Active, model-driven, affects real decisions |
| Research | 🔬 研究專區 | Shadow/research only, NOT for trading decisions |
| Legacy | 📦 歷史參考 | Historical, frozen, read-only |
| Experimental | 🧪 實驗性 | V3 / blocked features |

### D. Data Freshness Policy
Every page showing price or signal data should display:
`資料截至：{max_date}` where max_date comes from `SELECT MAX(date) FROM daily_prices`.

### E. Transaction Cost Constant
Centralize in `config.py`:
```python
TAIWAN_ROUND_TRIP_FEES_PCT = 0.585  # buy 0.1425% + sell 0.4425%
```
Import in all backtest/research modules.

---

## 6. Impact Assessment

| Change | Affects Production Calculations? | Affects UI Only? | Authorization Required? |
|---|---|---|---|
| Align main.py version label to v6.8 | NO | YES | No (cosmetic) |
| Add data freshness label to pages | NO | YES | No |
| Add RESEARCH ONLY banner to Tab 5/6 | NO | YES | No |
| Extract ROUND_TRIP_COST to config.py | NO (same value) | NO | Yes (code change) |
| Merge Tab 7+8 into one page | NO | YES | Yes (code change) |
| Replace raw sqlite3 in Tab 6 | NO (read-only) | NO | Yes (code change) |
| Merge UserTrade access points | NO | YES | Yes (code change) |
| Mark migration scripts as archived | NO | NO | No (documentation only) |
