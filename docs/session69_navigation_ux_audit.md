# Session 69 — Navigation & UX Audit

**Audit Date**: 2026-11-11  
**Source**: dashboard/app.py (verified), dashboard/_pages/* (verified)

---

## 1. Full Navigation Tree

```
台股 AI 研究平台 v6.8
│
├── [Sidebar]
│     ├── 查看日期 (date picker → session_state["selected_date"])
│     ├── 🔄 重新整理資料 (st.cache_data.clear)
│     ├── Metric: 股價資料 N 筆 / 最新日期 / 研究起始
│     └── 免責聲明
│
└── [10 Tabs]
    │
    ├── Tab 0: 📊今日  (overview.py::page_today)
    │     ├── 市場摘要 (Market Summary card)
    │     ├── 今日推薦 (BUY/STRONG_BUY rec cards with score bars)
    │     ├── 歷史類似情境 (evidence_service: N cases, alpha 20D/60D)
    │     ├── 進場計劃 (entry_low/high, stop, target, R/R)
    │     ├── Watch List / 候選追蹤池
    │     └── 市場狀態 Regime label
    │
    ├── Tab 1: 📡盤中  (live_monitor.py::page_live_monitor)
    │     ├── Signal date auto-resolution (prev_trading_day logic)
    │     ├── Eligible BUY list (live price check)
    │     ├── State: pending_open / active / expired / invalidated
    │     └── Auto-refresh controls
    │
    ├── Tab 2: 📈看盤  (market_watch.py::page_market_watch)
    │     ├── Stock selector (watchable stocks: BUY signals + active positions)
    │     ├── Plotly K-line + Volume chart
    │     ├── MA5/10/20/60 overlays
    │     └── Setup badge (breakout / pullback_buy / trending / etc.)
    │
    ├── Tab 3: 💼持倉  (position.py::page_positions)
    │     ├── Sub-tab A: 💰 真實持倉 ACTUAL
    │     │     ├── ActualPosition (Neon)
    │     │     ├── 未實現損益計算
    │     │     └── 新增/修改持倉 UI
    │     ├── Sub-tab B: 📊 系統模擬 PAPER
    │     │     ├── PositionMonitor (Neon)
    │     │     └── pending_open → active 狀態機
    │     └── Sub-tab C: 📋 歷史交易紀錄
    │           └── UserTrade (SQLite, 舊版)
    │
    ├── Tab 4: 🔒證據  (evidence.py::page_evidence)
    │     ├── foe_v1 ForwardOutcomeEvaluation
    │     ├── PATH_AWARE / PATH_BASELINE 比較
    │     ├── 20D/60D outcome stats
    │     └── Entry status funnel
    │
    ├── Tab 5: 🧪研究回測  (research_backtest.py::page_research_backtest)
    │     ├── In-Sample (analysis_results, date < 2026-10-09)
    │     ├── Out-of-Sample (forward_signals, date >= 2026-10-09)
    │     ├── Bootstrap CI, Cohen's d
    │     └── Setup × Regime breakdown
    │
    ├── Tab 6: ⏱️進場時機  (entry_timing_research.py::page_entry_timing_research)
    │     ├── V2 research (research_version: v2_research_v1/v2)
    │     ├── ENTRY_READY / WAIT_FOR_PULLBACK / etc.
    │     ├── Comparison A/B/C (V1 vs V2 vs Full)
    │     └── [3 raw sqlite3 direct connections]
    │
    ├── Tab 7: 🔍個股  (reports.py::page_search)
    │     ├── Stock ID input
    │     └── History: Recommendation, ForwardSignal, price chart
    │
    ├── Tab 8: 📋歷史  (reports.py::page_history)
    │     └── Recent recommendations list (last N days)
    │
    └── Tab 9: 📦 Archive  (selectbox)
          ├── 🔬 Legacy 驗證 (backtest.py)
          │     ├── Historical backtest (Recommendation table)
          │     ├── Monte Carlo baseline
          │     ├── Signal quality IC/ICIR
          │     └── V1 vs V2 comparison
          ├── 📋 成績單 (scorecard.py)
          │     └── ForwardSignal record per recommendation
          ├── 🗂 交易記錄 (my_trades.py)
          │     ├── UserTrade CRUD
          │     └── Monte Carlo 20D forecast per trade
          ├── 🩺 資料健康 (data_health.py)
          │     ├── Data staleness per source
          │     └── Coverage metrics
          ├── 📖 說明 (guide.py)
          └── ⚙️ 設定 (guide.py::page_settings)
```

---

## 2. Duplicate User Journey Analysis

### Group 1 — Market Monitoring

| Feature | 盤中 (Tab 1) | 看盤 (Tab 2) |
|---|---|---|
| Core question | 「這個 BUY 計劃現在還能執行嗎？」 | 「這檔股票走勢如何？技術型態是什麼？」 |
| Data type | Live price + BUY signal state | Historical OHLC chart + MA |
| Computation | Signal state machine, entry window check | MA5/10/20/60, Plotly chart |
| Write side effects | LiveExecutionEvent state write | None |
| Overlap | 都看股價，但問題不同 | — |

**Verdict**: NOT truly duplicate. 盤中 = execution decision; 看盤 = price analysis. DIFFERENT purpose. Keep separate.

**Issue**: Both show "current price" but from different sources — 盤中 uses live fetch; 看盤 uses DailyPrice (EOD). No explicit freshness label distinguishing them. **UX Risk**: user may confuse EOD data with live data.

---

### Group 2 — Trade Management

| Feature | 持倉 ACTUAL (Tab 3A) | 持倉 PAPER (Tab 3B) | 持倉歷史 (Tab 3C) | 交易記錄 (Archive) |
|---|---|---|---|---|
| Data table | ActualPosition (Neon) | PositionMonitor (Neon) | UserTrade (SQLite) | UserTrade (SQLite) |
| Write access | YES (user manual) | NO (cron-managed) | YES (user manual) | YES (user manual) |
| Purpose | 真實損益 | 模型模擬損益 | 舊版記錄 | 舊版記錄 |
| Overlap | — | PAPER ≠ ACTUAL | Tab 3C = Archive交易記錄 | EXACT DUPLICATE of Tab 3C |

**Verdict**: Tab 3C (持倉歷史) and Archive 交易記錄 show the SAME `UserTrade` table. **EXACT UI DUPLICATE**.

**Recommendation**: Remove Tab 3C from position.py OR remove Archive 交易記錄. Keep one entry. `MERGE_UI`.

---

### Group 3 — Research

| Feature | Legacy驗證 (Archive) | 研究回測 (Tab 5) | 進場時機 (Tab 6) |
|---|---|---|---|
| Data source | Recommendation table | analysis_results + forward_signals | ForwardSignal (V2 research) |
| Cutoff | None (all history) | RESEARCH_CUTOFF_DATE = 2026-10-09 | V2 research periods |
| Purpose | Old-style 5/20/60D return | IS/OOS strict split, Alpha, CI | V2 entry timing label comparison |
| Monte Carlo | Yes | No | No |
| Overlap | Partially overlaps Tab 5 returns | — | Different research question |

**Verdict**: 
- Legacy驗證 vs 研究回測: SIMILAR but DISTINCT data models. Legacy uses pre-cutoff Recommendation; Tab 5 uses IS/OOS split with stricter methodology. **INTENTIONAL_VERSION_ISOLATION** — Legacy must be preserved for historical reproducibility.
- 進場時機 is specifically V2 entry timing research. NOT replaceable by Tab 5. Keep separate.

**Recommendation**: Legacy驗證 stays in Archive with clear "歷史參考" label. No merge needed.

---

### Group 4 — Performance & Evidence

| Feature | 🔒證據 (Tab 4) | 📋成績單 (Archive) |
|---|---|---|
| Data table | ForwardOutcomeEvaluation | ForwardSignal |
| Protocol | foe_v1 (pre-registered) | None (audit trail) |
| Content | PATH_AWARE/BASELINE outcomes, 20D/60D return stats | "On date X, model said Y, actual was Z" |
| Sample basis | Only signals with outcome maturity | All ForwardSignals with decision_label |
| Overlap | Both show "how did we do" | — |

**Verdict**: SIMILAR purpose but different data models and rigor levels. 證據 = formal research evidence (foe_v1); 成績單 = informal audit trail. Keep separate but clarify labeling.

**UX Issue**: Users may not understand difference. Both should clearly state their scope and protocol.

---

### Group 5 — Daily Decision

| Feature | 今日 (Tab 0) | 個股 (Tab 7) |
|---|---|---|
| Scope | Today's BUY signals (all stocks) | Single stock historical lookup |
| Data | Recommendation (filtered) | Recommendation + ForwardSignal (all dates) |
| Primary use case | Daily morning review | Research / follow-up on specific stock |

**Verdict**: NOT duplicate. Different user intents. Tab 0 = "what do I do today?"; Tab 7 = "what happened with 2330?".

---

## 3. UX Issues Summary

### Issue U01: Archive dropdown buries important features
- 資料健康 (critical for understanding data quality) requires 2 clicks via Archive dropdown
- 成績單 (audit trail) is hidden
- **Severity**: MEDIUM — admin/research features are OK hidden, but 資料健康 should be more prominent
- **Recommendation**: Add 資料健康 as persistent status in Sidebar or promote to visible tab

### Issue U02: 10 top-level tabs is too many
- Cognitive load: users must understand all 10 tabs before finding what they need
- Tabs 7+8 (個股 + 歷史) could be combined in one search/history page
- **Severity**: MEDIUM

### Issue U03: Version mismatch
- main.py header says `v6.0`; dashboard says `v6.8`
- Sidebar shows `v6.8`; CLI output shows `v6.0`
- **Severity**: LOW (UI only, no functional impact)
- **Recommendation**: Align to single product version label

### Issue U04: No data freshness label on 看盤
- market_watch.py shows DailyPrice (EOD) charts without indicating "last updated: 2026-11-05"
- User may assume data is current
- **Severity**: MEDIUM (data freshness misrepresentation risk)

### Issue U05: Research pages lack clear "RESEARCH ONLY" banner
- entry_timing_research.py has a docstring disclaimer but it's not visible in UI
- Users might act on research signals as if they were live
- **Severity**: MEDIUM

### Issue U06: Duplicate UserTrade access path
- UserTrade accessible from: position.py Tab 3C AND Archive 交易記錄
- **Severity**: LOW but confusing

---

## 4. Beginner Investor Assessment (10 Questions)

| Q | Question | Current Answer | Gap |
|---|---|---|---|
| 1 | 這檔股票目前是什麼狀態？ | Tab 0 推薦卡 / Tab 2 看盤 | YES — answered |
| 2 | 為什麼系統給出這個判斷？ | Tab 0 Score bars + tags | PARTIAL — scores shown but interpretation unclear |
| 3 | 現在適合買進、等待，還是不適合？ | BUY/WAIT badge on rec card | YES — answered |
| 4 | 理想進場條件是什麼？ | entry_low/high, setup_type | YES — answered (but requires understanding entry window) |
| 5 | 停損應如何設定？ | stop_price on rec card | YES — shown |
| 6 | 可能的風險是什麼？ | risk tags (tag-risk class) | PARTIAL — tags but no plain-language explanation |
| 7 | 歷史類似訊號的績效如何？ | 歷史類似情境 widget in Tab 0 | YES — shown if N≥5 |
| 8 | 樣本數是否足夠？ | N displayed, insufficient warning | YES — _warn_if_small() implemented |
| 9 | 這是正式模型結果，還是研究/模擬？ | PAPER/ACTUAL/RESEARCH labels in position | PARTIAL — Tab 6 research banner missing in UI |
| 10 | 資料更新到什麼時候？ | Sidebar shows newest date | PARTIAL — only shows newest price date, not signal date |

**Key Gap**: No persistent "data as-of" indicator on overview page. User sees recommendations but may not notice data is 5+ days old.

---

## 5. Recommendations Summary

| Item | Current | Recommendation | Risk |
|---|---|---|---|
| Tab 3C vs Archive 交易記錄 | EXACT DUPLICATE | Remove one (keep Archive 交易記錄 for compatibility) | LOW |
| Tab 7 + Tab 8 | Two separate tabs | Merge into single 個股/歷史 tab with toggle | LOW |
| Archive 資料健康 | Hidden in dropdown | Persistent status widget in Sidebar | LOW |
| Data freshness label | Missing from 看盤 + 今日 | Add "資料截至 YYYY-MM-DD" banner | NONE |
| Research pages | No visible RESEARCH ONLY banner | Add prominent banner in Tab 5, 6, Archive | NONE |
| Tab count | 10 | Reduce to 7-8 (merge Tab 7+8, move some to Archive) | LOW |
| Version label | v6.0 (main.py) vs v6.8 (dashboard) | Unify to single product version | NONE |
