# Session 69 — Final Recommendation

**Audit Date**: 2026-11-11  
**Scope**: Read-only architecture audit; no implementation authorized

---

## 1. Architecture Assessment

**Current state**: The platform has grown organically across 60+ sessions. Each session added features, research modules, and pages without systematic IA review. The result is a functional but increasingly crowded platform:

- 10 top-level tabs (industry norm for this size: 5-7)
- 6 Archive items accessed via dropdown within a tab
- 3 separate backtest surfaces with different data models
- 4 trade history access points (2 of which show identical data)
- Version labels inconsistent between CLI and dashboard
- Research pages lack visible isolation markers in the UI
- 60+ `src/research/` modules (mostly session-specific audit artifacts)

**Core strength**: Data model and computation are sound. IS/OOS separation is rigorous. foe_v1 protocol is properly frozen. MODEL_VERSION v8.0 is consistently enforced.

**Severity**: LOW for production reliability. MEDIUM for maintainability and usability.

---

## 2. Current IA vs Recommended IA

| Current (10 tabs) | Recommended Option B (5 tabs) |
|---|---|
| 📊今日 | 🎯決策中心 (今日+個股+歷史) |
| 📡盤中 | 📡市場監控 (盤中+看盤) |
| 📈看盤 | ↑ merged above |
| 💼持倉 | 💼我的交易 (ACTUAL+PAPER+歷史) |
| 🔒證據 | 🔬策略驗證 (證據+研究回測+進場時機+Archive) |
| 🧪研究回測 | ↑ merged above |
| ⏱️進場時機 | ↑ merged above |
| 🔍個股 | ↑ merged into 決策中心 |
| 📋歷史 | ↑ merged into 決策中心 |
| 📦Archive (dropdown) | ⚙️系統 (資料健康+說明+設定) |

---

## 3. Feature Disposition Table

| Feature | Current Status | Disposition | Rationale |
|---|---|---|---|
| 今日分析 (T0) | Production | KEEP | Daily core |
| 盤中監控 (T1) | Production | KEEP | Intraday core |
| 看盤 K線 (T2) | Production | KEEP + data-freshness label | Chart tool |
| 持倉 ACTUAL (T3A) | Production | KEEP | Real trade tracking |
| 持倉 PAPER (T3B) | Production | KEEP | Model simulation |
| 持倉歷史 (T3C) | Production | MERGE_UI → merge with Archive 交易記錄 | Exact duplicate |
| 前向證據 (T4) | Production | KEEP (foe_v1 frozen) | Evidence protocol |
| 研究回測 (T5) | Research | KEEP (IS/OOS boundary) | Research core |
| 進場時機 (T6) | Research | KEEP + RESEARCH banner | V2 research |
| 個股查詢 (T7) | Production | MERGE_UI → into 決策中心 | Combine with 歷史 |
| 歷史推薦 (T8) | Production | MERGE_UI → into 決策中心 | Combine with 個股 |
| Legacy 驗證 | Archive | ARCHIVE (already there) | Reproducibility |
| 成績單 | Archive/Research | ARCHIVE | ForwardSignal audit trail |
| 交易記錄 | Archive | MERGE_UI → merge with T3C | Duplicate |
| 資料健康 | Tool/Archive | KEEP + promote to Sidebar/System | Critical health check |
| 說明 | Tool | KEEP | User education |
| 設定 | Tool | KEEP | Settings |
| main.py CLI | Production | KEEP (DO_NOT_REMOVE) | Pipeline entry point |
| Cron pipeline | Production | KEEP (DO_NOT_REMOVE) | Data ingestion |
| foe_v1 / outcome_service | Production | KEEP FROZEN | Evaluation protocol |
| V3 research modules | Research | KEEP (DO_NOT_REMOVE) | Research reproducibility |
| Session research modules (src/research/session*) | Archive | KEEP (read-only archive) | Audit trail |
| migrate_*.py scripts | Tool | ARCHIVE LABEL | Already executed |

---

## 4. Top 10 Duplication & Fragmentation Problems

Ranked by impact (1 = highest):

| Rank | Problem | Impact | Type |
|---|---|---|---|
| 1 | 10 tabs → cognitive overload for new users | HIGH | UX |
| 2 | No data freshness indicator on 今日/看盤 | HIGH | Data trust |
| 3 | Research pages (T5, T6) lack UI-level isolation marker | HIGH | Research integrity |
| 4 | UserTrade accessible from T3C + Archive (exact duplicate) | MEDIUM | UX confusion |
| 5 | ROUND_TRIP_COST = 0.585 defined in 10+ places | MEDIUM | Maintainability |
| 6 | main.py v6.0 vs dashboard v6.8 version mismatch | MEDIUM | Trust/consistency |
| 7 | raw sqlite3 access in entry_timing_research.py | MEDIUM | Reliability risk |
| 8 | 資料健康 buried in Archive dropdown | MEDIUM | Discoverability |
| 9 | 個股 (T7) and 歷史 (T8) are functionally one page | LOW | Navigation bloat |
| 10 | V2 research labels inconsistent (v2_research_v1 vs "legacy v1") | LOW | Naming clarity |

---

## 5. Top 5 Priority Improvements

### P1: Add Data Freshness Labels (Phase 1)
**What**: Add "資料截至 {max_date}" to Tab 0 (今日) and Tab 2 (看盤).  
**Why**: Currently max_date = 2026-11-05 (5 days behind). Users see recommendations without knowing data is stale.  
**Risk**: NONE — display only.  
**Effort**: XS (1-2 hours).  
**Authorization**: Yes (code change to overview.py + market_watch.py).

### P2: Add RESEARCH ONLY Banner to T5, T6 (Phase 1)
**What**: Visible banner at top of research_backtest.py and entry_timing_research.py.  
**Why**: Users may act on research signals as trading signals.  
**Risk**: NONE — display only.  
**Effort**: XS (30 min).  
**Authorization**: Yes.

### P3: Merge T7 (個股) + T8 (歷史) into Single Tab (Phase 1)
**What**: One tab "🔍個股/歷史" with toggle between search and recent list.  
**Why**: Two tabs for essentially the same data model (Recommendation history).  
**Risk**: LOW — both use load_stock_history and load_recent_recs from loaders.py.  
**Effort**: S (2-3 hours).  
**Authorization**: Yes.

### P4: Extract ROUND_TRIP_COST to config.py (Phase 3)
**What**: `TAIWAN_ROUND_TRIP_FEES_PCT = 0.585` in config.py, import everywhere.  
**Why**: Currently defined in 10+ places — divergence risk on assumption change.  
**Risk**: LOW (pure constant replacement, same value).  
**Effort**: M (need to update all 10+ files + run tests).  
**Authorization**: Yes + regression test confirmation.

### P5: Replace raw sqlite3 in entry_timing_research.py (Phase 3)
**What**: Replace `sqlite3.connect(db_path)` (3 occurrences) with `get_session()` + ORM.  
**Why**: Bypasses ORM session management, schema change safety, connection pooling.  
**Risk**: LOW (read-only page, same data).  
**Effort**: M (must verify query equivalence).  
**Authorization**: Yes + before/after output test.

---

## 6. Next Session Implementation Scope (Proposal)

**Suggested scope for Session 70** (requires user authorization):

**Bundle A — Zero-risk display fixes** (can be done in one session):
1. P1-01: Align main.py version label (XS)
2. P1-02: Data freshness banner on Tab 0 (S)
3. P1-03: Data freshness label on 看盤 (XS)
4. P1-04: RESEARCH banner on research_backtest.py (XS)
5. P1-05: RESEARCH banner on entry_timing_research.py (XS)

**Bundle B — Navigation simplification** (separate session, slightly more risk):
1. P1-06: Merge Tab 7+8
2. P1-07: Remove Tab 3C (keep Archive 交易記錄)
3. P1-08: Promote 資料健康 to Sidebar

**Do NOT combine Bundle A and B in the same session** — test Bundle A first.

---

## 7. What Must Not Change

| Item | Why Frozen |
|---|---|
| foe_v1 evaluation protocol | Pre-registered; changing = data manipulation |
| MODEL_VERSION = "v8.0" | All ForwardSignals tagged with this; changes break history |
| RESEARCH_CUTOFF_DATE = 2026-10-09 | IS/OOS boundary; changes = look-ahead bias |
| IS/OOS separation in research_backtest | Fundamental research methodology |
| RC-2 patch (backfill_daily_prices.py) | H3/H4 not yet complete |
| V3 parameters (be43e8ca...) | Activation blocked |
| Cron schedule (0 16 * * 1-5) | Production schedule |
| AUTH01/AUTH02 | Not authorized |
| Any migration of foe_v1 to foe_v2 | Major research decision, requires separate session |

---

## 8. 15 Final Questions Answers

| Q | Answer |
|---|---|
| Q1. 目前有多少頁面？ | 10 main tabs + 6 Archive items = 16 surfaces (verified from app.py) |
| Q2. 哪些 UI 入口確實重複？ | Tab 3C + Archive 交易記錄（exact duplicate of UserTrade） |
| Q3. 哪些功能名稱相似但用途不同？ | 證據(foe_v1 outcome protocol) vs 成績單(ForwardSignal audit trail)；研究回測 vs Legacy驗證；PAPER vs ACTUAL |
| Q4. 哪些 Service 存在真正重複邏輯？ | ROUND_TRIP_COST = 0.585（SEMANTIC_DUPLICATE，10+處）；Alpha calc（INSUFFICIENT_EVIDENCE，需 Phase 0 確認） |
| Q5. 哪些計算必須因模型版本保留獨立？ | technical.py(V1 scorer) vs price_trend.py(V2 scorer)；RESEARCH_CUTOFF_DATE 兩側資料集；foe_v1 protocol |
| Q6. 哪些資料目前缺少明確 SSOT？ | 交易記錄（UserTrade vs ActualPosition 並存）；price freshness（EOD vs live 未標示） |
| Q7. SQLite 與 Neon 是否有責任重疊？ | YES：PositionMonitor 和 ActualPosition 在 Neon；DailyPrice/ForwardSignal 在 SQLite；no double-write confirmed |
| Q8. Live 與 EOD 資料是否有混用風險？ | YES：看盤(EOD DailyPrice) vs 盤中(live price fetch) 並存但未標示；用戶可能混淆 |
| Q9. 是否有同一檔股票在不同頁面顯示不同訊號的可能？ | YES (INFERRED)：live_monitor 有 lifecycle filter；overview 顯示原始 Recommendation；可能 lifecycle 狀態不同 |
| Q10. 哪些版本標示需要統一？ | main.py v6.0 vs dashboard v6.8；ROUND_TRIP_COST 命名（3 種）；V2 research v1/v2 labels |
| Q11. 哪些功能可以安全隱藏？ | Tab 3C（duplicate）；Archive 設定→移至 Sidebar；Archive 說明→移至 System tab |
| Q12. 哪些功能應保留為 Legacy/Archive？ | Legacy 驗證(backtest.py)；成績單(scorecard.py)；session research modules；migrate_*.py |
| Q13. 是否適合改為五大主要入口？ | YES — Option B Balanced Consolidation 推薦，5 tabs 合適 |
| Q14. 最值得優先處理的五項精簡工作？ | P1:資料新鮮度標示；P2:RESEARCH banner；P3:Tab 7+8合併；P4:ROUND_TRIP_COST集中；P5:sqlite3→ORM |
| Q15. 哪些變更必須另外取得使用者授權？ | 所有程式碼修改（Phase 1-4 全部需要）；Phase 0 文件更新不需要 |

---

## 9. Final Verdict

| Category | Classification |
|---|---|
| Architecture Audit | `ARCHITECTURE_AUDIT_COMPLETE` |
| Feature Inventory | `FEATURE_REGISTRY_COMPLETE` |
| Duplication | `DUPLICATION_CONFIRMED` (DL-02 ROUND_TRIP_COST; DL-05 raw sqlite3; UI T3C+Archive) |
| SSOT | `SSOT_GAPS_IDENTIFIED` (price freshness; UserTrade vs ActualPosition coexistence) |
| UX | `UX_CONSOLIDATION_RECOMMENDED` (5-tab IA, Option B) |
| Refactor | `SAFE_UI_REFACTOR_CANDIDATES_IDENTIFIED` (Phase 1 items are zero-risk) |
| Production | `PRODUCTION_UNCHANGED_VERIFIED` (MODEL_VERSION v8.0, RC-2 hash, cron all VERIFIED) |
| Authorization | `IMPLEMENTATION_NOT_AUTHORIZED` (all proposals require user sign-off) |

---

## 10. White-Paper Summary

**「目前 Taiwan Stock AI 到底有哪些功能太重複？哪些應該合併？哪些應該隱藏？哪些不能刪？如果要讓平台更簡潔、好懂、好維護，應該先做哪五件事？」**

**真正重複的**：
- Tab 3C（持倉歷史）和 Archive 交易記錄 顯示完全相同的 `UserTrade` 資料，二選一。
- `ROUND_TRIP_COST = 0.585` 在 10+ 個檔案裡各自定義，早晚會有人改其中一個而忘了其他。

**應該合併的**：
- Tab 7（個股）+ Tab 8（歷史）→ 一個有切換的查詢頁面，它們本來就是同一個資料集的不同視角。
- 研究頁（Tab 5+6）可以收進「策略驗證」區，讓一般使用者不必看到，進階使用者還是找得到。

**應該隱藏或提升的**：
- 資料健康 目前藏在 Archive 下拉選單第四個選項，但這是你每次看盤前應該先確認的。應該放到 Sidebar 或常駐。
- 設定/說明 可以收到 System 頁，不需要在 Archive 裡。

**絕對不能刪的**：
- foe_v1 證據頁 — 這是正式 pre-registered 研究協議，刪了就是篡改研究記錄。
- Legacy 驗證 — 歷史回測基準，刪了研究就無法重現。
- main.py 完整 pipeline — 整個每日決策流程的核心。
- 所有 V3/V2 研究模組 — 即使 V3 被 blocked，刪除會讓研究記錄無法重現。
- UserTrade 表 — 只能唯讀保留，不能無故刪除使用者資料。

**先做這五件事**：
1. **加「資料截至 YYYY-MM-DD」** 在今日分析和看盤頁面 — 目前資料落後 5 天，使用者卻不知道。（30 分鐘，零風險）
2. **加「研究專區」醒目標示** 在研究回測和進場時機頁 — 避免使用者把研究訊號當成正式交易指令。（30 分鐘，零風險）
3. **合併個股+歷史兩個 Tab** — 兩頁本來就是一件事。（2-3 小時，低風險）
4. **把 ROUND_TRIP_COST = 0.585 集中到 config.py** — 10+ 個地方定義，遲早出錯。（半天，低風險，要跑回歸測試）
5. **把 entry_timing_research.py 的 raw sqlite3 換成 get_session()** — 目前繞過 ORM 保護，Schema 一動就會出問題。（半天，要先寫對照測試）
