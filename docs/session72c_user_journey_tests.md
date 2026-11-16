# Session 72C — User Journey Tests

**Session**: 72C  
**Verdict**: `USER_JOURNEYS_PASS` (code-level; browser not available)  
**Date**: 2026-11-13

---

## Journey 1 — 今日找股票

**Goal**: 開啟 Dashboard → 今日決策 → 找到推薦 → 理解原因 → 查看風險

| Step | Expected | Actual (code trace) | Status |
|---|---|---|---|
| 開啟 Dashboard | 顯示側欄 + 5個主入口 | `main_tabs = st.tabs([...5 items...])` | ✓ PASS |
| 點擊「今日決策」 | 顯示 today推薦子頁 | `main_tabs[0]` → `sub1 = st.tabs([...])` | ✓ PASS |
| 預設顯示「📊今日推薦」 | 推薦股票列表 | `with sub1[0]: _render(page_today, sel_date)` | ✓ PASS |
| 推薦卡片顯示 BUY/WAIT | 訊號清楚標示 | `overview.py:598` signal `in ("strong_buy","buy")` | ✓ PASS |
| 推薦原因顯示 | tags_good / tags_risk | `overview.py:162` `.tag-good`/`.tag-risk` CSS | ✓ PASS |
| 無推薦時顯示說明 | 「目前沒有符合條件的買進訊號。」 | `overview.py` has empty-state branch | ✓ PASS |
| 盤中監控不佔主頁 | 收合至第二子頁 | `sub1[1]` = 盤中監控 | ✓ PASS |

**Usability Issues**: None critical. 盤中監控如無即時資料，`page_live_monitor` 自帶「盤中監控資料尚未啟用」空狀態。

---

## Journey 2 — 分析單一股票

**Goal**: 選擇股票 → K線/均線 → 正式訊號 → 進場/停損/目標價

| Step | Expected | Actual (code trace) | Status |
|---|---|---|---|
| 點擊「個股分析」 | 顯示看盤+個股搜尋 | `main_tabs[1]` → `sub2 = st.tabs([...])` | ✓ PASS |
| 預設「📈看盤K線」 | K線圖 + MA20/MA60 + 成交量 | `page_market_watch` calls chart functions | ✓ PASS |
| 切換「🔍個股搜尋」 | 文字搜尋輸入框 | `page_search` has text_input widget | ✓ PASS |
| 搜尋結果顯示訊號 | BUY/WAIT + 進場條件 | `reports.py` search result with signal | ✓ PASS |
| 顯示推薦歷史 | 歷史推薦紀錄 | `page_history` callable from 進場研究子頁 | ✓ PASS |

**Usability Issues**: Decision Center 在 `reports.py:page_search` 內嵌顯示，使用者需切換子頁才能看 K 線然後看訊號。這是現有功能架構限制，非 UI 迴歸。

---

## Journey 3 — 查看已買股票

**Goal**: 我的持倉 → 成本/損益 → 交易紀錄

| Step | Expected | Actual (code trace) | Status |
|---|---|---|---|
| 點擊「我的持倉」 | 持倉概覽 | `main_tabs[2]` → `sub3[0]` = 持倉狀況 | ✓ PASS |
| 顯示真實/模擬持倉 | 兩種持倉類型清楚分離 | `position.py:page_positions` handles both | ✓ PASS |
| 切換「🗂交易記錄」 | 交易列表 + 輸入表單 | `my_trades.py:page_my_trades` | ✓ PASS |
| 無重複輸入表單 | 只有一個輸入入口 | `page_my_trades` only called once | ✓ PASS |
| 交易寫入邏輯不變 | 原始 Service 未修改 | `my_trades.py` unchanged from production | ✓ PASS |

---

## Journey 4 — 驗證策略

**Goal**: 策略績效 → 樣本數 → 區分歷史/前向 → 理解限制

| Step | Expected | Actual (code trace) | Status |
|---|---|---|---|
| 點擊「策略績效」 | 預設「績效總覽」 | `sub4[0]` → `page_scorecard` | ✓ PASS |
| 顯示樣本數和勝率 | scorecard 統計 | `scorecard.py:page_scorecard` | ✓ PASS |
| 切換「前向驗證」 | Forward Signal 表格 | `evidence.py:page_evidence` | ✓ PASS |
| 切換「歷史回測」 | radio: 研究回測 / Legacy | `st.radio(key="s72c_bt_choice")` | ✓ PASS |
| 選「研究回測」 | V2 research backtest | `page_research_backtest` | ✓ PASS |
| 選「Legacy驗證」 | V1 historical backtest | `page_backtest` | ✓ PASS |
| 切換「進場研究」 | 研究標籤清楚顯示 | `st.info(..."僅供研究"...)` before radio | ✓ PASS |
| 研究結果與正式績效分離 | 有明確標示 | info banner + 版本資訊分離 | ✓ PASS |

---

## Journey 5 — 排查資料問題

**Goal**: 系統管理 → 資料日期 → 資料來源 → 執行紀錄

| Step | Expected | Actual (code trace) | Status |
|---|---|---|---|
| 點擊「系統管理」 | 預設「資料健康」 | `sub5[0]` → `page_data_health` | ✓ PASS |
| 資料最新日期顯示 | 明確日期 + 新鮮度警示 | `data_health.py` has freshness checks | ✓ PASS |
| 切換「版本資訊」 | 版本 Taxonomy 表格 | `_render_version_info()` via `_render()` | ✓ PASS |
| 正式策略顯示 v8.0 | `st.metric("正式模型版本", MODEL_VERSION)` | `_render_version_info` reads from `src.database.MODEL_VERSION` | ✓ PASS |
| V3 顯示 Frozen 狀態 | 明確標示不影響正式建議 | `st.info("V3 目前為 Frozen 狀態...")` | ✓ PASS |

---

## Summary

| Journey | Verdict | Notes |
|---|---|---|
| J1 今日找股票 | PASS | No change needed |
| J2 分析單一股票 | PASS | Minor: K線/訊號在不同子頁，architecture limitation |
| J3 查看已買股票 | PASS | Fully preserved |
| J4 驗證策略 | PASS | Research clearly labeled |
| J5 排查資料問題 | PASS | Version info complete |

**Browser verification**: `VISUAL_ACCEPTANCE_NOT_VERIFIED` — journeys traced via code inspection only.
