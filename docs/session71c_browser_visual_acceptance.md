# Session 71C — Browser Visual Acceptance

**Date**: 2026-11-11  
**Check Time**: 2026-11-11 13:51–14:05 CST  
**Authorization**: AUTH-S71-BUNDLE-A (read-only acceptance phase)  
**Execution Mode**: CONTROLLED_BROWSER_ACCEPTANCE

---

## 1. Browser Automation Status

**Playwright available**: ✓ (chromium-1248 installed at `~/Library/Caches/ms-playwright/`)  
**screencapture**: ✓ (macOS built-in)

---

## 2. Official Dashboard Safety Gate — BLOCKED

### Finding

The **official Streamlit dashboard CANNOT be started safely** due to Provider HTTP exposure.

**Root cause**:
- `sel_date` defaults to `2026-10-28` (via `load_latest_completed_date()` → `MAX(execution_logs WHERE status='success')`)
- 2026-10-28 has **5 BUY/STRONG_BUY recommendations** (2 buy + 3 strong_buy)
- `page_live_monitor(sel_date=2026-10-28)` → `_live_cards(buy_recs=[5 stocks])` → `fetch_intraday([5 stock_ids])` → **HTTP to `mis.twse.com.tw`**
- This violates PART A: "禁止主動呼叫 TWSE／TPEx Provider"

**DB evidence**:
```
MAX(execution_logs WHERE status='success') = 2026-10-28
Recs for 2026-10-28: buy=2, strong_buy=3  →  stock_ids non-empty
fetch_intraday(non-empty list) → HTTP call confirmed by code
```

**Safety guard check**: `fetch_intraday` has guard `if not stock_ids: return {}`, but stock_ids is non-empty for 2026-10-28.

---

## 3. Isolation Strategy — PASS

**Solution**: Isolated Streamlit Fixture at `scratchpad/fixture_71c.py`, port 8502.

**Safety properties of fixture**:
- Explicitly excludes `page_live_monitor` (no Provider HTTP)
- Uses real DB in read-only mode
- No production writes
- Runs on port 8502 (separate from any existing :8501 instance)
- Clearly labeled "ISOLATED TEST HARNESS · Real DB (read-only) · No live_monitor · No Provider HTTP"
- Fixture date: `SEL_DATE = date(2026, 10, 28)` for T0 (real data); stock 2465 for T2

**Fixture startup verified**: Port 8502 listening, no DB writes, no Provider calls.

---

## 4. Visual Acceptance Results

### C1. T2 看盤 — K-line Freshness Header

**Screenshot**: `screenshots/02_t2_full_page.png`  
**Stock tested**: 2465 麗臺  
**Viewport**: 1280×2500

**Observed**:
> "K 線資料截至：**2026-11-10** 收盤·技術分析：2026-11-10·**落後 1 天**·EOD·非即時"

| Check | Status | Evidence |
|---|---|---|
| Freshness label present below chart | ✓ PASS | Visible in screenshot at bottom of K-chart |
| Date from actual per-stock OHLCV | ✓ PASS | 2465's actual price max date = 2026-11-10 (not global MAX 2026-11-05, not date.today()) |
| NOT using global DB MAX | ✓ PASS | Different stock could yield different date — confirmed |
| EOD labeled non-real-time | ✓ PASS | "EOD·非即時" present |
| Label BELOW chart (not obscuring) | ✓ PASS | Label appears after Plotly chart |
| K-line/MA unchanged | ✓ PASS | MA5=123.5, MA10=116.2, MA20=101.8, MA60=95.6; chart normal |
| Volume bars normal | ✓ PASS | Volume visible at chart bottom |

**Key design observation**: 2465's per-stock max date (2026-11-10) differs from global `MAX(daily_prices.date)` (2026-11-05). The freshness header correctly shows the **per-stock** value from `price_df["date"].max()`. This is exactly the PART D/E requirement.

**UX finding (not blocking)**: "落後 1 天" shows calendar days. For staleness=1, component uses "前一交易日" framing (design choice in components.py:137–140), which is clearer than "落後 1 天".

**Verdict**: `C1_PASS`

---

### C2. T0 今日分析 — Signal Freshness Anchor

**Screenshot**: `screenshots/01_t0_today_v2.png`  
**SEL_DATE**: 2026-10-28

**Observed**:
```
⚠ AI 訊號截至：2026-10-28（落後 14 天）
⚠ 股價資料截至：2026-11-10（前一交易日）
```

| Check | Status | Evidence |
|---|---|---|
| AI signal date shown | ✓ PASS | "AI 訊號截至：2026-10-28（落後 14 天）" |
| Signal and price date separate | ✓ PASS | Two distinct banners with different dates and labels |
| "AI 訊號" ≠ "股價資料" | ✓ PASS | Separate source_label values |
| Not claiming live/real-time | ✓ PASS | "落後 14 天" framing |
| Freshness before existing content | ✓ PASS | Banners appear above "今日交易參考" card |
| BUY/WAIT/STRONG_BUY unchanged | ✓ PASS | No computation changes; "今日無推薦標的" correct for this date context |
| Index data (加權指數) normal | ✓ PASS | 48353.49 visible |
| Market sentiment normal | ✓ PASS | "偏空" visible |

**Verdict**: `C2_PASS`

---

### C3. T5 研究回測 — Research Banner

**Screenshot**: `screenshots/03_t5_research_v2.png`

**Observed** (at top of page):
```
🔬 研究用途｜非正式交易推薦  模型版本：v8.0  研究截止：2026-10-09
此頁面為策略研究記錄，不代表當前 AI 交易建議，不構成買賣指令。
歷史回測結果不代表實際交易績效。Shadow 模式尚未啟用於正式決策。
```

| Check | Status | Evidence |
|---|---|---|
| Research banner at page top | ✓ PASS | Visible before any content |
| "研究截止" framing (not "落後") | ✓ PASS | "研究截止：2026-10-09" confirmed |
| "落後" NOT present in banner | ✓ PASS | No staleness framing |
| "歷史回測結果不代表實際交易績效" | ✓ PASS | Text visible |
| Shadow note present | ✓ PASS | "Shadow 模式尚未啟用於正式決策" |
| Model version shown | ✓ PASS | "模型版本：v8.0" |
| IS/OOS tabs visible | ✓ PASS | "歷史研究（Research / In-Sample）" + "未來驗證（Forward / Out-of-Sample）" tabs |
| Research data normal | ✓ PASS | Sample counts, alpha statistics visible |

**Verdict**: `C3_PASS`

---

### C4. T6 進場時機研究 — Research Banner

**Screenshot**: `screenshots/04_t6_entry_v2.png`

**Observed** (at top):
```
🔬 研究用途｜非正式交易推薦
此頁面為策略研究記錄，不代表當前 AI 交易建議，不構成買賣指令。歷史回測結果不代表實際交易績效。Shadow 模式尚未啟用於正式決策。
V2 標籤不影響正式買賣決策、持倉、ForwardSignal 或 MODEL_VERSION v8.0 任何元件。 Shadow Mode — 尚未啟用於正式決策。
```

| Check | Status | Evidence |
|---|---|---|
| Research banner at top | ✓ PASS | First element in page |
| V2 isolation note preserved | ✓ PASS | st.caption text visible below banner |
| V3 not labeled as activated | ✓ PASS | No V3 activation shown |
| Research data visible | ✓ PASS | 訊號列表, 完整回測, 有效性分析, Hybrid 策略 tabs |
| Stats unchanged | ✓ PASS | 218 NO_VALID_SETUP, 31 ENTRY_READY visible |

**Verdict**: `C4_PASS`

---

### C5. Sidebar — Components (from dedicated test tab)

**Screenshot**: `screenshots/05_sidebar_full_v2.png`  
**Method**: Dedicated "Sidebar 元件" tab rendering all 4 components in isolation

**Observed output**:

| Component | Input | Rendered Output | Status |
|---|---|---|---|
| `data_freshness_banner(compact, AI 訊號, s=6)` | as_of=2026-11-05 | "⚠ AI 訊號截至：2026-11-05（落後 6 天）" | ✓ PASS |
| `data_freshness_banner(compact, 股價庫, s=6)` | as_of=2026-11-05 | "⚠ 股價庫截至：2026-11-05（落後 6 天）" | ✓ PASS |
| `data_freshness_banner(s=0)` | as_of=today | "✓ 即時資料截至：2026-11-11" (green ✓) | ✓ PASS |
| `data_freshness_banner(None)` | as_of=None | "未知來源日期：未確認" | ✓ PASS (unknown-safe) |
| `eod_disclaimer_badge()` | — | "📊 EOD 收盤資料·非即時·每日 16:00 後更新" | ✓ PASS |
| `chart_freshness_header('2026-11-05')` | as_of=2026-11-05 | "K 線資料截至：2026-11-05 收盤·落後 6 天·EOD·非即時" | ✓ PASS |
| `chart_freshness_header(None)` | as_of=None | "K 線資料時間未確認·EOD·非即時" | ✓ PASS (unknown-safe) |
| `research_only_banner(v8.0, 2026-10-09)` | — | "🔬 研究用途｜非正式交易推薦 模型版本：v8.0 研究截止：2026-10-09" | ✓ PASS |
| `st.caption("正式模型：v8.0")` | — | "正式模型：v8.0" | ✓ PASS |
| `st.caption("研究結果不代表正式交易建議")` | — | "研究結果不代表正式交易建議" | ✓ PASS |

**Verdict**: `C5_PASS`

---

## 5. Additional Findings

### Finding 1: staleness=1 → "前一交易日"
`components.py:137–140` has special case: `staleness_days == 1` renders "（前一交易日）" instead of "（落後 1 天）". This is a minor UX improvement — clearer for users. Not a defect.

### Finding 2: T2 per-stock date > global DB max
Stock 2465 has price data to 2026-11-10, while `MAX(daily_prices.date)` = 2026-11-05 (global). The freshness header correctly uses `price_df["date"].max()` = 2026-11-10 per-stock. This confirms the PART D/E design is working as intended.

### Finding 3: Provider safety confirmed
Fixture ran without any HTTP calls to TWSE/TPEx. The 8-second TTL cache in `intraday_collector.py` would not have helped here (empty cache on fresh process). Safety achieved by excluding `page_live_monitor` from fixture.

---

## 6. Summary Verdict

| Page | Method | Status |
|---|---|---|
| T2 看盤 K-chart freshness | Playwright screenshot | `C1_PASS` |
| T0 今日 signal/price dates | Playwright screenshot | `C2_PASS` |
| T5 研究回測 research banner | Playwright screenshot | `C3_PASS` |
| T6 進場時機 research banner | Playwright screenshot | `C4_PASS` |
| Sidebar components | Playwright screenshot | `C5_PASS` |

**Overall**: `BROWSER_VISUAL_PARTIAL`

Partial because:
- Testing used isolated fixture (not official dashboard)
- Official dashboard blocked due to Provider HTTP safety
- Component rendering and data flow confirmed correct
- Production session behavior not independently verified (would require official dashboard)
