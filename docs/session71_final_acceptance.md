# Session 71 — Final Acceptance

**Date**: 2026-11-11  
**Authorization**: AUTH-S71-BUNDLE-A

---

## 1. Final Acceptance Gate Checklist

| Criterion | Evidence | Status |
|---|---|---|
| All changes within authorized scope | 6 Bundle A items only; no scope creep | ✓ |
| Four shared components satisfy Display-only Contract | No DB/HTTP/session in components.py; tests confirm | ✓ |
| T2 K-line data date is correct (from actual chart data) | `price_df["date"].max()` per stock, not global max | ✓ |
| T0 freshness anchor shown (always visible) | `data_freshness_banner()` added before `freshness_html` | ✓ |
| T5 research banner added | `research_only_banner()` at top of `page_research_backtest()` | ✓ |
| T6 research banner present | Replaced inline HTML with shared component | ✓ |
| Sidebar model version + data status shown | `MODEL_VERSION` + staleness banner added | ✓ |
| Unknown-safe behavior correct | TC-EC01, TC-EC03 pass; None → "未確認" | ✓ |
| No signal/score drift | No computation changes; test suite baseline unchanged | ✓ |
| No K-line data changes | `build_chart` and plotly calls unchanged | ✓ |
| No Provider HTTP added | test_no_provider_http_in_components PASS | ✓ |
| No DB writes | test_no_db_write_in_components PASS; row count unchanged | ✓ |
| Cron not modified | git diff + hash verified | ✓ |
| RC-2 hash unchanged | `4eb6eacf...` confirmed | ✓ |
| Relevant tests pass | 33/33 Bundle A tests PASS | ✓ |
| Full regression unchanged | 4276/4276 baseline tests PASS | ✓ |
| Rollback executable | `git checkout -- <files>` sequence documented | ✓ |
| Git diff has no unauthorized changes | Only 5 dashboard files modified + 2 new created | ✓ |

---

## 2. Partial Verification Required (Browser)

The following items require user browser verification before full acceptance:

| Item | Why |
|---|---|
| T2 看盤 K-line chart freshness header visual | Tests mock `st.markdown`; actual rendering not confirmed |
| T0 today page freshness anchor visual | Need to confirm compact=True looks appropriate |
| T5/T6 research banner visual | Need to confirm banner color/size is prominent enough |
| Sidebar staleness color visual | Need to confirm `fr-warning-banner` class renders correctly in sidebar |

---

## 3. Known Gaps (Not Blocking)

| Gap | Description | Future Fix |
|---|---|---|
| Calendar vs trading days | `_staleness_days()` uses calendar days. Shows "落後 6 天" not "4 個交易日" | Phase 2: use TaiwanTradingCalendar |
| T0 Price As-of is a proxy | `latest_date` from ExecutionLog, not per-stock price date | Phase 2: add `load_dailyprice_max_date()` loader |
| H3 still pending | RC-2 H3 not yet accepted (pre-existing, unrelated to Bundle A) | Await next natural cron run |
| Browser render not verified | Streamlit UI mocked in tests | User to confirm in browser |

---

## 4. Part N — Final Verdict

### Implementation
`BUNDLE_A_IMPLEMENTED`  
All 6 authorized items (P1A-01 through P1A-06) implemented successfully.

### UI Validation
`UI_ACCEPTANCE_INCONCLUSIVE`  
Contract tests pass (33/33). Browser rendering NOT yet confirmed by user.

### Model Integrity
`NO_MODEL_DRIFT_VERIFIED`  
MODEL_VERSION v8.0 unchanged. All signal/score/entry-stop-target computations unchanged. 4276 baseline tests pass.

### Data Integrity
`NO_DB_WRITE_VERIFIED`  
534,770 rows unchanged. components.py has zero DB calls. No new queries added to any page.

### Cron Integrity
`CRON_UNCHANGED_VERIFIED`  
Cron schedule `0 16 * * 1-5` unchanged. `hybrid_shadow_cron.py` unchanged. RC-2 hash unchanged.

### RC-2 Integrity
`RC2_HASH_UNCHANGED`  
`4eb6eacf6c65df52aae037731e66e4573a8ae929af807c0fbd7c1adcac4c5afb` confirmed.

### Release
`LOCAL_IMPLEMENTATION_ACCEPTED`  
(pending user browser verification per Section 2 above)

### Deployment
`DEPLOYMENT_NOT_AUTHORIZED`  
No production deployment executed or authorized in this session.

---

## 5. Part O — Executive Summary

### 1. 這次實際修改了哪些頁面？
5 個頁面 + 2 個新檔案：
- T2 看盤 (`market_watch.py`) — K 線圖下方加資料截至標示
- T0 今日 (`overview.py`) — 訊號參考區最上方加持久性新鮮度標示
- T5 研究回測 (`research_backtest.py`) — 頁面最頂端加 🔬 研究用途 banner
- T6 進場時機 (`entry_timing_research.py`) — 替換原有 inline HTML 為 shared component
- Sidebar (`app.py`) — 資料庫最新日期加顏色標示 + 模型版本 + 研究免責

### 2. 使用者現在能看到哪些新的資料時間標示？
- **T2 看盤**：「K 線資料截至：2026-11-05 收盤 · 技術分析：2026-11-05 · ⚠ 落後 6 天 · EOD · 非即時」
- **T0 今日**：「⚠ AI 訊號截至：2026-11-05（落後 6 天）」（無論看哪一天都顯示）
- **T5/T6**：「🔬 研究用途｜非正式交易推薦 ... 歷史回測結果不代表實際交易績效。」
- **Sidebar**：「⚠ 股價庫截至：2026-11-05（落後 6 天）」+ 「正式模型：v8.0」

### 3. 哪些資料時間仍無法確認？
- T0 的「Price As-of」使用 ExecutionLog 成功日期作為 proxy，非個股精確日期
- T4 證據頁的「最後評估日期」未修改（Out of Scope）
- T1 盤中 overnight context 的 `fetched_at` 未修改（Out of Scope）

### 4. 研究結果是否已清楚區分正式推薦？
是。T5/T6 均有醒目的 🔬 banner，明確說明「非正式交易推薦」、「歷史回測結果不代表實際交易績效」、「Shadow Mode 尚未啟用於正式決策」。

### 5. 有沒有改變任何股票推薦結果？
**沒有**。所有 BUY/WAIT/STRONG_BUY 訊號、分數、信心度、進場區間、停損、目標價完全未改變。

### 6. 有沒有改變 K 線或技術指標？
**沒有**。`build_chart()` 呼叫完全未修改，`price_df` 的 OHLCV 未動，均線計算未動，Plotly trace 未動。

### 7. 有沒有碰到正式資料庫？
**沒有**。`daily_prices` 仍 534,770 筆，max_date 仍 2026-11-05，零寫入。`components.py` 完全不查詢資料庫。

### 8. 有沒有影響 RC-2 或 Cron？
**沒有**。RC-2 hash `4eb6eacf...` 完全一致。Cron `0 16 * * 1-5` 完全未改。

### 9. 測試通過多少項？哪些未通過？
- **Bundle A 驗收測試**：33 / 33 PASS
- **全套回歸測試**：4,276 PASS（與基線完全相同）
- **37 個預期失敗**：皆為 S66 RC-2 部署後的已知預期失敗，與本次無關

### 10. 是否能安全回滾？
是。5 個修改過的檔案可用 `git checkout -- <file>` 完整還原。2 個新建檔案可直接刪除。操作說明詳見 `session71_rollback_plan.md`。

### 11. 是否建議接受 Bundle A？
**建議接受**，但需使用者在瀏覽器中確認 4 個頁面的視覺效果（T0、T2、T5、Sidebar）後再最終定案。

### 12. 下一階段應優先處理什麼？
- **立即**：使用者開啟 Streamlit 確認視覺效果
- **H3 等待**：下一次 16:00 CST 自然 Cron 執行後，確認 H3 Runtime Acceptance
- **Phase 2 候選**：（需新授權）`load_dailyprice_max_date()` 函數、T4 證據頁最後評估日期、`_staleness_days` 升級為交易日計算
