# Session 71C — Screenshot Evidence

**Date**: 2026-11-11  
**Check Time**: 2026-11-11 13:51–14:05 CST  
**Method**: Playwright (chromium-1248, headless) + Isolated Streamlit Fixture (port 8502)

---

## 1. Environment

| Property | Value |
|---|---|
| Browser | Chromium 156.0.8078.4 (Playwright chromium v1248) |
| Viewport | 1280×900 (default), 1280×2500 (full page) |
| Streamlit App | Isolated fixture `scratchpad/fixture_71c.py` on port 8502 |
| Data | Real SQLite (read-only), SEL_DATE=2026-10-28, Stock=2465 麗臺 |
| Label | ISOLATED_TEST_HARNESS — NOT PRODUCTION DASHBOARD |

---

## 2. Screenshot Index

| ID | File | Tab | Description |
|---|---|---|---|
| SS-01 | `01_t0_today_v2.png` | T0 今日 | Full page, freshness banners visible |
| SS-02 | `02_t2_full_page.png` | T2 看盤 | Full page with K-chart + freshness header |
| SS-03 | `03_t5_research_v2.png` | T5 研究回測 | Research banner + backtest content |
| SS-04 | `04_t6_entry_v2.png` | T6 進場時機 | Research banner + V2 isolation note |
| SS-05 | `05_sidebar_full_v2.png` | Sidebar 元件 | All 4 components, full page |

**Screenshot storage path**: `scratchpad/screenshots/`

---

## 3. SS-01: T0 今日

**File**: `01_t0_today_v2.png`  
**Page**: T0 今日分析  
**SEL_DATE**: 2026-10-28

**Observed UI** (confirmed from screenshot):
```
⚠ AI 訊號截至：2026-10-28（落後 14 天）         ← NEW: data_freshness_banner
⚠ 股價資料截至：2026-11-10（前一交易日）         ← NEW: data_freshness_banner
[加權指數 48353.49 | 市場情緒 偏空]              ← EXISTING (unchanged)
今日交易參考
  訊號分析日: 2026/10/28
  適用交易日: 2026/10/29
  今日無推薦標的
```

**Expected UI** (from spec):
- AI signal as-of date, persistent anchor: ✓
- Signal and price dates separate: ✓ (Oct 28 vs Nov 10)
- Not claiming real-time: ✓

**Verdict**: PASS  
**Data source**: `selected_date = 2026-10-28`; `latest_date = 2026-11-10` (actual rendering — from DailyPrice loader, not ExecutionLog)

---

## 4. SS-02: T2 看盤

**File**: `02_t2_full_page.png`  
**Page**: T2 看盤  
**Stock**: 2465 麗臺

**Observed UI** (confirmed from screenshot):
```
麗臺（2465） [進度牛勢] [等待]
現價: 136.0 | MA5: 123.5 | MA10: 116.2 | MA20: 101.8 | MA60: 95.6
[K-chart: dark background, candlesticks, MA lines, volume bars]        ← EXISTING (unchanged)
K 線資料截至：2026-11-10 收盤·技術分析：2026-11-10·落後 1 天·EOD·非即時   ← NEW
— MA5 — MA10 — MA20（基準線）— MA60 — MA20+10% 趨勢線               ← EXISTING (unchanged)
```

**Expected UI** (from spec):
- Date from actual price_df max: ✓ (2026-11-10 is 2465's per-stock last date)
- NOT using global DB MAX (2026-11-05): ✓ (shows 2026-11-10, not 2026-11-05)
- NOT using date.today() (2026-11-11): ✓ (shows 2026-11-10)
- EOD/非即時: ✓
- Chart not obscured: ✓ (label below chart)
- MA lines unchanged: ✓

**Verdict**: PASS  
**Key observation**: Per-stock date (2026-11-10) ≠ global MAX (2026-11-05). The design correctly uses `price_df["date"].max()`.

---

## 5. SS-03: T5 研究回測

**File**: `03_t5_research_v2.png`  
**Page**: T5 研究回測

**Observed UI** (confirmed from screenshot):
```
🔬 研究用途｜非正式交易推薦  模型版本：v8.0  研究截止：2026-10-09   ← NEW banner
此頁面為策略研究記錄，不代表當前 AI 交易建議，不構成買賣指令。
歷史回測結果不代表實際交易績效。Shadow 模式尚未啟用於正式決策。
研究回測 & 前瞻驗證（Research Backtest & Forward Validation）       ← EXISTING
[page description, 歷史研究 / 未來驗證 tabs]                         ← EXISTING
A. 研究目前進度與可信度                                                ← EXISTING
  分析日期：2024-07-01 ~ 2026-09-11
  有效樣本 20D 去重：1,258 筆
  樣本足夠，但 20D Alpha 尚不顯著（p ≥ 0.05）
```

**Expected UI** (from spec):
- Research banner at top: ✓
- "研究截止" (not "落後"): ✓
- "歷史回測結果不代表實際交易績效": ✓
- Shadow note: ✓
- Research data unchanged: ✓

**Verdict**: PASS

---

## 6. SS-04: T6 進場時機

**File**: `04_t6_entry_v2.png`  
**Page**: T6 進場時機研究

**Observed UI** (confirmed from screenshot):
```
V2 進場時機研究（Shadow Mode）                                          ← EXISTING title
🔬 研究用途｜非正式交易推薦                                              ← NEW banner
此頁面為策略研究記錄，不代表當前 AI 交易建議，不構成買賣指令。歷史回測結果不代表實際交易績效。Shadow 模式尚未啟用於正式決策。
V2 標籤不影響正式買賣決策、持倉、ForwardSignal 或 MODEL_VERSION v8.0 任何元件。 Shadow Mode — 尚未啟用於正式決策。  ← PRESERVED
研究版本: [v2_research_v2 ▾]                                            ← EXISTING
[研究數據: 218 NO_VALID_SETUP | 31 ENTRY_READY | 23 RISK_REWARD_UNFAVORABLE | 14 WAIT_FOR_BREAKOUT]
```

**Expected UI** (from spec):
- Research banner at top: ✓
- V2 isolation note preserved: ✓
- V3 not labeled as activated: ✓ (Shadow Mode only)
- Research data unchanged: ✓

**Verdict**: PASS

---

## 7. SS-05: Sidebar / Components

**File**: `05_sidebar_full_v2.png`  
**Page**: Dedicated "Sidebar 元件" test tab

**Observed UI** (confirmed from full-page screenshot):
```
Sidebar 元件獨立測試

data_freshness_banner (compact=True, AI 訊號, staleness=6)
⚠ AI 訊號截至：2026-11-05（落後 6 天）

data_freshness_banner (compact=True, 股價庫, staleness=6)
⚠ 股價庫截至：2026-11-05（落後 6 天）

data_freshness_banner (staleness=0)
✓ 即時資料截至：2026-11-11

data_freshness_banner (None — unknown-safe)
未知來源日期：未確認

eod_disclaimer_badge()
📊 EOD 收盤資料·非即時·每日 16:00 後更新

chart_freshness_header('2026-11-05')
K 線資料截至：2026-11-05 收盤·落後 6 天·EOD·非即時

chart_freshness_header(None)
K 線資料時間未確認·EOD·非即時

research_only_banner(v8.0, 2026-10-09)
🔬 研究用途｜非正式交易推薦  模型版本：v8.0  研究截止：2026-10-09
此頁面為策略研究記錄，不代表當前 AI 交易建議，不構成買賣指令。歷史回測結果不代表實際交易績效。Shadow 模式尚未啟用於正式決策。

正式模型：v8.0
研究結果不代表正式交易建議
```

**All 10 component outputs confirmed correct.**

**Verdict**: PASS

---

## 8. Screenshot Disclaimer

| Property | Value |
|---|---|
| Data source | ISOLATED_TEST_HARNESS with real read-only SQLite data |
| Mock data | NONE — all data from actual production SQLite |
| Label | Fixture header clearly shows "ISOLATED TEST HARNESS · Real DB (read-only)" |
| Limitation | Isolated fixture excludes `page_live_monitor` to avoid Provider HTTP |

**These screenshots are from a REAL Streamlit app rendering REAL production data.** The only isolation is excluding `page_live_monitor` to prevent Provider HTTP calls. All other page functions (page_today, page_market_watch, page_research_backtest, page_entry_timing_research) use the actual production codebase and SQLite data.
