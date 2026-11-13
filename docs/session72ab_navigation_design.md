# Session 72AB — Navigation Design

**Session**: 72AB  
**Verdict**: `FIVE_ENTRIES_COMPLETE`

---

## Before: 10-Tab Navigation

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ 📊今日 │ 📡盤中 │ 📈看盤 │ 💼持倉 │ 🔒證據 │ 🧪研究回測 │ ⏱️進場 │ 🔍個股 │ 📋歷史 │ 📦Archive │
└──────────────────────────────────────────────────────────────────────────────┘

Archive dropdown:
  🔬 Legacy 驗證 / 📋 成績單 / 🗂 交易記錄 / 🩺 資料健康 / 📖 說明 / ⚙️ 設定
```

**Problems**:
- 今日 and 盤中 are separate top-level entries for the same daily check
- 看盤 and 個股 are separate entries for per-stock analysis
- 研究回測 and Legacy驗證 are both backtests separated into different levels
- 成績單、交易記錄、資料健康、說明、設定 buried in Archive dropdown
- 進場時機 occupies a top-level slot but has no auto-populated data
- 10 tabs = too many for a new user to navigate

---

## After: 5-Tab Navigation (72AB Isolated)

```
┌────────────────────────────────────────────────────────┐
│ 🎯 今日決策 │ 📈 個股分析 │ 💼 我的持倉 │ 📊 策略績效 │ ⚙️ 系統管理 │
└────────────────────────────────────────────────────────┘
```

### Tab 1: 🎯 今日決策
```
  [📊 今日推薦]  [📡 盤中監控]
  ├── page_today(date)        ← 推薦股票、買賣訊號、評分
  └── page_live_monitor(date) ← 盤中價格追蹤
```
User question answered: **今天有哪些股票值得關注？為什麼？**

### Tab 2: 📈 個股分析
```
  [📈 看盤 K 線]  [🔍 個股搜尋]
  ├── page_market_watch(date) ← K線、MA20/60、成交量、趨勢
  └── page_search()           ← 個股搜尋 + Decision Center
```
User question answered: **現在適不適合進場？理想價格、停損、目標價？**

### Tab 3: 💼 我的持倉
```
  [💼 持倉狀況]  [🗂 交易記錄]
  ├── page_positions()   ← 持倉損益、模型 vs 真實
  └── page_my_trades()   ← 交易輸入、歷史記錄
```
User question answered: **已買股票應該續抱、減碼或停損嗎？**

### Tab 4: 📊 策略績效
```
  [📋 績效總覽]  [🔒 前向驗證]  [🧪 歷史回測]  [⏱️ 進場研究]
  ├── page_scorecard()          ← ForwardSignal 成績單
  ├── page_evidence()           ← EvidencePresenter 前向驗證
  ├── [🔬 研究回測] + [📦 Legacy] ← research_backtest + backtest
  └── [⏱️ 進場時機] + [📋 歷史]   ← entry_timing_research + page_history
```
User question answered: **這套策略的歷史表現是否可信？**

### Tab 5: ⚙️ 系統管理
```
  [🩺 資料健康]  [🏷️ 版本資訊]  [📖 說明]  [⚙️ 設定]
  ├── page_data_health()       ← 資料完整性、覆蓋率
  ├── _render_version_info()   ← 完整版本 Taxonomy
  ├── page_guide()             ← 評分說明
  └── page_settings(date)      ← 日期選擇、設定
```
User question answered: **目前資料是否最新、完整？**

---

## Information Architecture Mapping

| User Question | Old Location | New Location |
|---|---|---|
| 今天有哪些股票值得關注？ | 📊今日 (tab 0) | 🎯今日決策 → 今日推薦 |
| 為什麼被推薦？ | 📊今日 detail | 🎯今日決策 → 今日推薦 (同頁) |
| 現在適不適合進場？ | 🔍個股 / 📈看盤 | 📈個股分析 → 看盤K線 |
| 理想買進價格？停損？目標價？ | 🔍個股 Decision Center | 📈個股分析 → 個股搜尋 |
| 風險報酬比？ | 🔍個股 | 📈個股分析 → 個股搜尋 |
| 已買股票應如何處理？ | 💼持倉 | 💼我的持倉 → 持倉狀況 |
| 策略歷史表現？ | 🧪研究回測 + 🔒證據 | 📊策略績效 (sub-tabs) |
| 資料是否最新？ | 🩺資料健康 (Archive) | ⚙️系統管理 → 資料健康 |
