# Session 69 — Target Information Architecture

**Audit Date**: 2026-11-11

---

## 1. Current State IA

```
台股 AI 研究平台 v6.8
├── Sidebar (global: date picker, cache refresh, DB stats)
└── 10 Main Tabs
    ├── T0: 📊今日          — daily recommendations + market summary
    ├── T1: 📡盤中          — intraday signal validity
    ├── T2: 📈看盤          — K-line + MA chart
    ├── T3: 💼持倉          — 3 sub-tabs: ACTUAL / PAPER / 歷史
    ├── T4: 🔒證據          — foe_v1 forward outcome evaluation
    ├── T5: 🧪研究回測      — IS/OOS research, Alpha stats
    ├── T6: ⏱️進場時機      — V2 entry timing research
    ├── T7: 🔍個股          — single stock search
    ├── T8: 📋歷史          — recent recommendations list
    └── T9: 📦 Archive (selectbox)
            ├── 🔬 Legacy 驗證
            ├── 📋 成績單
            ├── 🗂 交易記錄
            ├── 🩺 資料健康
            ├── 📖 說明
            └── ⚙️ 設定
```

**Problems**:
- 10 top-level tabs → cognitive overload
- T7 + T8 are closely related (both show Recommendation history), split unnecessarily
- T3 sub-tab C (歷史) = Archive 交易記錄 exact duplicate
- 資料健康 buried in Archive (critical admin tool)
- Research pages (T5, T6) lack clear RESEARCH ONLY boundary marker in UI
- Setting (設定) hidden deep in Archive

---

## 2. Option A — Minimal Change

**Philosophy**: Fix labeling and duplication without restructuring tabs.

```
台股 AI 研究平台 v6.8
├── Sidebar (+ persistent data-freshness indicator + 資料健康 quick link)
└── 8 Main Tabs  (-2 from current)
    ├── T0: 📊今日          — (unchanged)
    ├── T1: 📡盤中          — (unchanged)
    ├── T2: 📈看盤          — + data-freshness label
    ├── T3: 💼持倉          — remove 歷史 sub-tab (merge into Archive 交易記錄)
    ├── T4: 🔒證據          — (unchanged)
    ├── T5: 🔬 研究區       — merge T5+T6 into tabbed research area
    │       ├── Tab: 研究回測 (current T5)
    │       └── Tab: 進場時機 (current T6)
    ├── T6: 🔍個股/歷史     — merge current T7+T8
    └── T7: 📦 Archive (selectbox, promoted 資料健康 to Sidebar)
```

| Metric | Current | Option A |
|---|---|---|
| Top-level tabs | 10 | 8 |
| Click depth to 資料健康 | 2 (Archive dropdown) | 1 (Sidebar link) |
| UserTrade duplicates | 2 | 1 |
| Research banner | None | Added to merged Research tab |
| Data freshness label | None | Added to Sidebar + 看盤 |
| Migration risk | — | LOW |
| Development effort | — | S (< 1 day) |

---

## 3. Option B — Balanced Consolidation (Recommended)

**Philosophy**: 5 primary sections matching user mental models.

```
台股 AI 研究平台 v6.8
├── Sidebar (global: date, refresh, freshness indicator, quick links)
└── 5 Main Tabs
    │
    ├── T0: 🎯 決策中心  Decision Hub
    │       ├── 今日推薦 (current T0 content)
    │       ├── 個股查詢 (current T7)
    │       └── 近期歷史 (current T8, simplified)
    │
    ├── T1: 📡 市場監控  Market Monitor
    │       ├── 盤中監控 (current T1)
    │       └── 看盤 K線 (current T2)
    │       Note: clear freshness label: "EOD data" vs "Live"
    │
    ├── T2: 💼 我的交易  My Trades
    │       ├── 實際持倉 ACTUAL (current T3A)
    │       ├── 模型模擬 PAPER (current T3B)
    │       └── 交易記錄 (current T3C + Archive 交易記錄, merged)
    │
    ├── T3: 🔬 策略驗證  Strategy Validation  [RESEARCH ONLY banner]
    │       ├── 前向證據 foe_v1 (current T4)
    │       ├── 研究回測 IS/OOS (current T5)
    │       ├── 進場時機 V2 (current T6)
    │       └── [Archive] 成績單, Legacy驗證
    │
    └── T4: ⚙️ 系統  System
            ├── 資料健康 (promoted from Archive)
            ├── 說明
            └── 設定
```

| Metric | Current | Option B |
|---|---|---|
| Top-level tabs | 10 | 5 |
| Click depth to any feature | 1 | 2 max |
| Research isolation | None | Explicit banner on T3 |
| Data freshness label | None | T1 header + Sidebar |
| UserTrade duplicates | 2 | 1 |
| Beginner discoverability | Poor (10 tabs) | Good (5 clear sections) |
| Power user access | Good (all visible) | Good (sub-tabs accessible) |
| Migration risk | — | MEDIUM (restructuring) |
| Development effort | — | M (1-2 days, UI only) |

**Key invariants preserved**:
- foe_v1 protocol NOT changed
- IS/OOS separation NOT changed
- MODEL_VERSION v8.0 NOT changed
- All data computation unchanged
- All routes preserved (via sub-tabs)

---

## 4. Option C — Aggressive Simplification

**Philosophy**: 3 sections for maximum simplicity.

```
├── T0: 📊 今日決策      — 今日推薦 + 盤中 + 個股
├── T1: 💼 持倉&交易     — ACTUAL + PAPER + history
└── T2: 🔬 研究&系統     — All research + data health + settings
```

| Metric | Current | Option C |
|---|---|---|
| Top-level tabs | 10 | 3 |
| Click depth | 1 | 3+ |
| Beginner friendly | Poor | POOR (too compressed) |
| Power user access | Good | Poor (buried) |
| Migration risk | — | HIGH |

**Verdict**: Over-simplified. Research pages need breathing room. NOT recommended.

---

## 5. Recommended Option: B (Balanced Consolidation)

**Rationale**:
1. 5 tabs matches user mental models: "What do I do today?", "What's happening in the market?", "What are my positions?", "What does the research say?", "How is the system doing?"
2. Research isolation becomes explicit with dedicated 策略驗證 section
3. 決策中心 combines the 3 daily-use pages (今日/個股/歷史) into one flow
4. 市場監控 clearly labels EOD vs live data
5. No production computation changes required

**What MUST stay separate (non-negotiable)**:
- foe_v1 evidence: cannot be merged into plain "results" — needs protocol label
- IS/OOS research: cannot be shown together — RESEARCH_CUTOFF_DATE boundary is fundamental
- ACTUAL vs PAPER positions: must stay labeled separately
- V3: must remain blocked/isolated

**What CAN be merged (UI only)**:
- Tab 7 (個股) + Tab 8 (歷史) → one search+history page
- Tab 3C + Archive 交易記錄 → one UserTrade view
- Tab 5 + Tab 6 → sub-tabs under 策略驗證
- Tab 4 (證據) can optionally be a sub-tab in 策略驗證

---

## 6. Tab Mapping: Current → Option B

| Current | Goes to | Notes |
|---|---|---|
| T0 今日 | T0 決策中心 / 今日推薦 | Primary position |
| T1 盤中 | T1 市場監控 / 盤中監控 | Add EOD/Live label |
| T2 看盤 | T1 市場監控 / 看盤 | Add data-freshness |
| T3A ACTUAL | T2 我的交易 / 實際持倉 | Unchanged |
| T3B PAPER | T2 我的交易 / 模型模擬 | Unchanged |
| T3C 歷史 | T2 我的交易 / 交易記錄 | Merge with Archive 交易記錄 |
| T4 證據 | T3 策略驗證 / 前向證據 | Add RESEARCH banner |
| T5 研究回測 | T3 策略驗證 / 研究回測 | Add RESEARCH banner |
| T6 進場時機 | T3 策略驗證 / 進場時機 | Add RESEARCH banner |
| T7 個股 | T0 決策中心 / 個股查詢 | Merge with 歷史 |
| T8 歷史 | T0 決策中心 / 近期歷史 | Merge with 個股 |
| Archive Legacy驗證 | T3 策略驗證 / Legacy Archive | Preserved |
| Archive 成績單 | T3 策略驗證 / 成績單 | Preserved |
| Archive 交易記錄 | T2 我的交易 / 交易記錄 | Merge with T3C |
| Archive 資料健康 | T4 系統 / 資料健康 | Promoted |
| Archive 說明 | T4 系統 / 說明 | Promoted |
| Archive 設定 | T4 系統 / 設定 | Promoted |

---

## 7. Progressive Disclosure

**Beginner view** (default): 決策中心 / 市場監控 / 我的交易  
**Advanced view** (expandable): 策略驗證 / 系統  
**Expert**: All research sub-tabs visible

---

## 8. Terminology Standardization

| Current (inconsistent) | Proposed Standard |
|---|---|
| `BUY`, `STRONG_BUY`, `WAIT` (mixed Chinese/English) | Keep English codes + Chinese tooltip |
| `PAPER` / `模型模擬` (mixed) | 模型模擬 (PAPER) |
| `ACTUAL` / `真實持倉` (mixed) | 實際持倉 (ACTUAL) |
| `Legacy 驗證` / `舊版回測` | 歷史回測 (Legacy) |
| `foe_v1` (code-level) | 前向執行評估協議 v1 (UI) |
| `研究回測` / `Research Backtest` | 策略研究 (顯示名稱) |
