# Session 71B — Visual Acceptance Report

**Date**: 2026-11-11  
**Check Time**: 2026-11-11 12:49:53 CST  
**Authorization**: AUTH-S71-BUNDLE-A (read-only acceptance phase)  
**Execution Mode**: CONTROLLED_LOCAL_UI_ACCEPTANCE

---

## 1. Verification Method

**Method used**: Component dry-run rendering via mocked Streamlit + static code analysis.

No live browser environment was available in the automated session. Visual acceptance was performed by:
1. Importing `dashboard/components.py` with mocked `streamlit` module
2. Calling each component function with representative inputs
3. Capturing HTML/markdown output and verifying correctness
4. Performing static code analysis to verify call sites and data provenance

**Limitation**: Actual browser pixel rendering, CSS styling application, and responsive layout cannot be confirmed without a human operator opening the Streamlit dashboard. Items that require browser confirmation are marked `BROWSER_REQUIRED`.

---

## 2. PART C — Streamlit Startup Safety

### Finding: STARTUP_SAFE

**Evidence**:

| Check | Evidence | Status |
|---|---|---|
| Top-level DB writes | AST scan: zero top-level DB writes in app.py | ✓ SAFE |
| Top-level HTTP calls | AST scan: zero HTTP calls at module level | ✓ SAFE |
| Backfill trigger | No backfill call outside cron script | ✓ SAFE |
| Provider calls on startup | Zero `fetch_intraday`, `requests.*` at top level | ✓ SAFE |
| Cron startup | No `hybrid_shadow_cron` import in dashboard | ✓ SAFE |
| Scheduler trigger | No scheduler start in dashboard | ✓ SAFE |
| Neon write on startup | No psycopg write at module level | ✓ SAFE |
| SQLite write on startup | Sidebar does MAX(date) READ only (inside try/except) | ✓ READ_ONLY |
| Session state mutation | components.py verified no `st.session_state` mutations | ✓ SAFE |

**Top-level statements in app.py** (L1–L211, before `main()`):
- L1: Module docstring (Expr — safe)
- L22: `sys.path.insert` (safe)
- L28, L37, L45: Try/import guards (safe)
- L58: `logger = logging.getLogger(...)` (safe)
- L61: `st.set_page_config(...)` (Streamlit config only, no DB)
- L69: `st.markdown(...)` (CSS injection only)
- L213: `def main()` (definition only)
- L398: `if __name__ == "__main__": main()` (guard)

**Conclusion**: Streamlit startup via `streamlit run dashboard/app.py` is safe for local loopback use with no production writes.

---

## 3. PART D — T2 看盤 K-line Freshness Header

### Code Location
`dashboard/_pages/market_watch.py:557–560`

### Call Site Verification

```python
# AFTER st.plotly_chart() (L549), BEFORE MA legend
from dashboard.components import chart_freshness_header
_chart_max_date = price_df["date"].max() if not price_df.empty else None
_analysis_date = analysis.get("date") if analysis else None
chart_freshness_header(_chart_max_date, _analysis_date)
```

### Data Provenance Verification

| Requirement | Evidence | Status |
|---|---|---|
| chart_max_date from actual OHLCV | `price_df["date"].max()` per-stock | ✓ CORRECT |
| NOT from date.today() | AST verified — no date.today() call | ✓ CORRECT |
| NOT from global DB MAX | No global MAX query in market_watch.py | ✓ CORRECT |
| NOT from other stock's data | price_df is per-stock scope | ✓ CORRECT |
| None-safe when price_df empty | `if not price_df.empty else None` | ✓ CORRECT |
| build_chart() unchanged | Line 548 call unchanged | ✓ UNCHANGED |
| st.plotly_chart() unchanged | Line 549–556 unchanged | ✓ UNCHANGED |

### Component Output (dry-run, as_of=2026-11-05)

**Verified HTML output**:
```
"K 線資料截至：2026-11-05 收盤 · ⚠ 落後 6 天 · EOD · 非即時"
```

**Verified None-safe output** (empty price_df):
```
"K 線資料時間未確認 · EOD · 非即時"
```

### Checklist

| Item | Status | Evidence |
|---|---|---|
| K-line freshness label present | ✓ VERIFIED | Dry-run output confirmed |
| Date matches last OHLCV bar | ✓ VERIFIED | price_df["date"].max() provenance |
| EOD clearly labeled | ✓ VERIFIED | "EOD · 非即時" in output |
| Unknown-safe (None → "未確認") | ✓ VERIFIED | Dry-run confirmed |
| date.today() not used as data date | ✓ VERIFIED | Code + AST check |
| Other stock date not used | ✓ VERIFIED | price_df is per-stock |
| Chart not obscured | BROWSER_REQUIRED | CSS analysis only |
| Mobile layout | BROWSER_REQUIRED | CSS analysis only |
| K-line/MA unchanged | ✓ VERIFIED | build_chart() call unchanged |

### UX Finding (not blocking)

**Finding**: "落後 6 天" shows calendar days (6), not trading days (4).  
Calendar days from 2026-11-05 to 2026-11-11 = 6.  
Trading days in same range = 4 (Nov 06, 07, 10, 11).

**Impact**: Overstates staleness by ~50%. For a "data is stale" indicator this is conservative (i.e., the direction of error is acceptable — it never under-claims staleness). No fix authorized this session.

**Mitigation in Phase 2**: Replace `_staleness_days()` with `TaiwanTradingCalendar` counting.

---

## 4. PART E — T0 今日分析 Freshness Anchor

### Code Location
`dashboard/_pages/overview.py:_render_trading_reference:103–119`

### Call Site Verification

```python
# Signal As-of = selected_date (訊號分析日)
# Price As-of  = latest_date (最近成功執行日，作為資料更新狀態的 proxy)
from dashboard.components import data_freshness_banner
_sig_lag = days_old  # calendar days since selected_date
_price_as_of = latest_date  # may differ from selected_date
_price_lag = (today - latest_date).days if latest_date else -1
data_freshness_banner(selected_date, _sig_lag, source_label="AI 訊號", compact=True)
if _price_as_of and _price_as_of != selected_date:
    data_freshness_banner(_price_as_of, _price_lag, source_label="股價資料", compact=True)
```

### Component Output (dry-run, selected_date=2026-11-05, days_old=6)

```
"⚠ AI 訊號截至：2026-11-05（落後 6 天）"
```

### Checklist

| Item | Status | Evidence |
|---|---|---|
| AI signal as-of date shown | ✓ VERIFIED | selected_date provenance |
| Signal and price dates kept separate | ✓ VERIFIED | Two separate banner calls |
| Model version shown | SIDEBAR | Shown in sidebar, not T0 |
| Freshness not shown as live | ✓ VERIFIED | "落後 N 天" framing |
| BUY/WAIT/STRONG_BUY unchanged | ✓ VERIFIED | No computation changes |
| Entry/Stop/Target unchanged | ✓ VERIFIED | No computation changes |
| Existing freshness_html preserved | ✓ VERIFIED | Added BEFORE line 123 |
| Unknown-safe (None latest_date) | ✓ VERIFIED | `if latest_date else -1` guard |

### Known Gap (documented in no_drift_verification.md)

`latest_date` = `MAX(ExecutionLog WHERE success)` = global proxy for price data currency.  
Not a per-stock last-available-date. Label "股價資料" is accurate as a system-level proxy.  
Phase 2 fix: add `load_dailyprice_max_date()` loader.

---

## 5. PART F — T5/T6 Research Banners

### T5 研究回測 (research_backtest.py)

**Code location**: `dashboard/_pages/research_backtest.py:236–242`

```python
def page_research_backtest() -> None:
    from dashboard.components import research_only_banner
    try:
        from src.database import MODEL_VERSION as _MV
    except Exception:
        _MV = "v8.0"
    research_only_banner(protocol_version=_MV, cutoff_date=_CUTOFF_LABEL)
```

**Component output verification**:
```
"🔬 研究用途｜非正式交易推薦 ... 模型版本：v8.0　研究截止：2026-10-09 ... 
此頁面為策略研究記錄，不代表當前 AI 交易建議，不構成買賣指令。
歷史回測結果不代表實際交易績效。Shadow 模式尚未啟用於正式決策。"
```

| Check | Status | Evidence |
|---|---|---|
| 研究截止 present (not 落後) | ✓ VERIFIED | Dry-run: `研究截止 present: True` |
| 落後 NOT present | ✓ VERIFIED | Dry-run: `落後 present: False` |
| 不代表實際交易績效 present | ✓ VERIFIED | Dry-run confirmed |
| Shadow note present | ✓ VERIFIED | Dry-run confirmed |
| _CUTOFF_LABEL = "2026-10-09" preserved | ✓ VERIFIED | Line 15 |
| IS/OOS tabs preserved | ✓ VERIFIED | tab_r, tab_f = st.tabs(...) line 266 |
| Research numbers unchanged | ✓ VERIFIED | No computation changes |
| V3 NOT labeled as activated | ✓ VERIFIED | No V3 activation flag added |

### T6 進場時機 (entry_timing_research.py)

**Code location**: `dashboard/_pages/entry_timing_research.py:204–209`

```python
from dashboard.components import research_only_banner
research_only_banner(compact=False)
st.caption(
    "V2 標籤不影響正式買賣決策、持倉、ForwardSignal 或 MODEL_VERSION v8.0 任何元件。"
    " Shadow Mode — 尚未啟用於正式決策。"
)
```

| Check | Status | Evidence |
|---|---|---|
| Research banner present at top | ✓ VERIFIED | Line 204–206 |
| V2 isolation note preserved | ✓ VERIFIED | st.caption line 208 |
| Shadow mode disclaimer | ✓ VERIFIED | "Shadow Mode — 尚未啟用於正式決策" |
| V2 research numbers unchanged | ✓ VERIFIED | No computation changes |

---

## 6. PART G — Sidebar Verification

### Code Location
`dashboard/app.py:265–293`

### Key Lines Verified

```python
st.metric("股價資料", f"{cnt:,} 筆")
if newest:
    from dashboard.components import data_freshness_banner
    data_freshness_banner(newest, source_label="股價庫", compact=True)
if first_rec:
    st.caption(f"研究起始：{first_rec}")
st.caption(f"正式模型：{_MV}")
st.caption("研究結果不代表正式交易建議")
```

### Checklist

| Item | Status | Evidence |
|---|---|---|
| 正式模型 v8.0 shown | ✓ VERIFIED | `st.caption(f"正式模型：{_MV}")` where _MV from src.database |
| 股價庫 max date with staleness color | ✓ VERIFIED | `data_freshness_banner(newest, source_label="股價庫", compact=True)` |
| NOT claiming per-stock date | ✓ VERIFIED | Label "股價庫" (global max), not per-stock |
| NOT claiming RC-2 H3 passed | ✓ VERIFIED | No H3 reference in code |
| NOT claiming Provider recovered | ✓ VERIFIED | No Provider status in code |
| Research disclaimer present | ✓ VERIFIED | "研究結果不代表正式交易建議" |
| Narrow window layout | BROWSER_REQUIRED | CSS analysis only |

---

## 7. Final Verdict

### Visual Acceptance

`VISUAL_ACCEPTANCE_PARTIAL`

- Component HTML output: **VERIFIED** via dry-run rendering for all 4 items
- Data provenance (chart_max_date from price_df, NOT date.today()): **VERIFIED** by code analysis
- Research framing (研究截止, NOT 落後): **VERIFIED** by dry-run
- None-safe behavior: **VERIFIED** by dry-run
- Browser pixel rendering, CSS application, responsive layout: **BROWSER_REQUIRED**

### Browser Verification Items Required

If user opens Streamlit dashboard locally:

| Page | What to Confirm |
|---|---|
| T2 看盤 | "K 線資料截至：2026-11-05 收盤 · ⚠ 落後 6 天 · EOD · 非即時" appears below K-chart |
| T0 今日 | "⚠ AI 訊號截至：2026-11-05（落後 6 天）" always visible in trading reference section |
| T5 研究回測 | Red/orange research banner prominent at page top |
| T6 進場時機 | Same banner at top + V2 isolation note visible |
| Sidebar | Staleness color + "正式模型：v8.0" + disclaimer |

### UX Finding (not blocking)

| ID | Description | Severity | Authorized Fix |
|---|---|---|---|
| UX-01 | "落後 6 天" shows calendar days (6) not trading days (4) | LOW | Phase 2 (not this session) |

### Startup Safety

`STARTUP_SAFE` — Local Streamlit launch does not trigger any writes, provider calls, or cron modifications.
