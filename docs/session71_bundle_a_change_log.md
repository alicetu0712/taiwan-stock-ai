# Session 71 — Bundle A Change Log

**Date**: 2026-11-11  
**Authorization**: AUTH-S71-BUNDLE-A  
**Mode**: CONTROLLED_UI_ONLY_IMPLEMENTATION

---

## Files Created

### `dashboard/components.py` (NEW)

**Purpose**: Shared display-only UI components for data freshness labeling.

**Hash**: `5b03e0b3d7a8f253c6c6c17e4f1709cd0abbe8d0849ea4e2646a3167a3539bbb`

**Components implemented**:
1. `_inject_css()` — CSS injection (once per session)
2. `_staleness_days(as_of)` — calendar-day staleness helper (not trading days; display only)
3. `data_freshness_banner(as_of_date, staleness_days, source_label, *, compact)` — freshness anchor
4. `eod_disclaimer_badge()` — "EOD 收盤資料 · 非即時" badge
5. `research_only_banner(protocol_version, cutoff_date, *, compact)` — research isolation banner
6. `chart_freshness_header(chart_max_date, analysis_date)` — K-line chart freshness header

**Design constraints enforced**:
- No DB queries, no HTTP calls, no session state mutations
- `date.today()` used ONLY for staleness gap, never as data currency claim
- All functions Unknown-safe (None → "未確認")

---

### `tests/test_session71_bundle_a.py` (NEW)

**Purpose**: 33 acceptance tests for Bundle A.

**Hash**: `a64dd38030939dac78e30fc75a18b1bfc0959babe1f6098d28278af34ed95657`

**Test result**: 33/33 PASS

---

## Files Modified

### `dashboard/_pages/market_watch.py` (P1A-02)

**Hash Before**: `c4ab071f0cab72ecd86d8772f70d6cd2c02a555b381850049240a703c7ef4dc1`  
**Hash After**: `da36c10ec3ffdf9cdb8fc4e259324fc29a0ecab3ca11ca9767b97fcfd985f6d9`

**Change**: Added 7 lines after `st.plotly_chart()` (line 553), before MA legend.

```python
# ── 資料新鮮度標示（K 線截至日期）─────────────────────────────
# chart_max_date 來自該股票實際 price_df，不使用全域 MAX 或系統日期
from dashboard.components import chart_freshness_header
_chart_max_date = price_df["date"].max() if not price_df.empty else None
_analysis_date = analysis.get("date") if analysis else None
chart_freshness_header(_chart_max_date, _analysis_date)
```

**Unchanged**: `build_chart()` call, `st.plotly_chart()` call, all OHLCV data, MA lines, `_render_ma_row()`, MA legend

**What user sees**: Below the K-line chart and before the MA legend, a small freshness line appears:
- `K 線資料截至：2026-11-05 收盤 · 技術分析：2026-11-05 · ⚠ 落後 6 天 · EOD · 非即時`

---

### `dashboard/_pages/overview.py` (P1A-03)

**Hash Before**: `d6a77b34829cdb5c4ffc96229f47b56dd915ac9faef0e7c4b35da9b11bb6cc74`  
**Hash After**: `211caefb6933d84809b1ad3d5eff8778f7fb7a65463277b1df489c770dea5ccf`

**Change**: Added 23 lines inside `_render_trading_reference()`, after the `days_old` computation and before the existing `freshness_html` logic.

```python
# ── 持久性資料時間標示（永遠顯示）─────────────────────────────
from dashboard.components import data_freshness_banner
data_freshness_banner(selected_date, _sig_lag, source_label="AI 訊號", compact=True)
if _price_as_of and _price_as_of != selected_date:
    data_freshness_banner(_price_as_of, _price_lag, source_label="股價資料", compact=True)
```

**Unchanged**: All existing `freshness_html` logic, all recommendation cards, prices, entry/stop/target values, candidate pool

**Known gap (documented)**: `latest_date` is `MAX(ExecutionLog.date WHERE status='success')` = best proxy for price-data-as-of; not an individual stock date. This is PART F documented gap — cannot add per-stock queries without new DB calls.

---

### `dashboard/_pages/research_backtest.py` (P1A-04)

**Hash Before**: `18a8b5b68102068ba2b9426babf405d35c0f7c35e4057f735d2084bd9c9f3d90`  
**Hash After**: `ef3464a24c39b4bf12811291d056ffd796ed5fee7cd72a09c5b9d62b50772d20`

**Change**: Added 9 lines at the START of `page_research_backtest()`, before the existing page title HTML.

```python
# ── 研究用途標示（頁面最頂端，永遠顯示）────────────────────
from dashboard.components import research_only_banner
research_only_banner(protocol_version=_MV, cutoff_date=_CUTOFF_LABEL)
```

**Unchanged**: All IS/OOS tab structure, all research calculations, `_CUTOFF_LABEL = "2026-10-09"`, all statistics

---

### `dashboard/_pages/entry_timing_research.py` (P1A-05)

**Hash Before**: `594bdc77a8c65c2d5425dc9454b90ebc39623f6aaafe4aff28851c1276adc445`  
**Hash After**: `2ed22c58a08337574a804f93af83775676c2d3ac4982271704fdadd82946407a`

**Change**: Replaced inline banner HTML (13 lines) with shared component call (5 lines). Net: -8 lines.

```python
# Before: inline st.markdown with HTML
# After:
from dashboard.components import research_only_banner
research_only_banner(compact=False)
st.caption("V2 標籤不影響正式買賣決策、持倉、ForwardSignal 或 MODEL_VERSION v8.0 任何元件。 Shadow Mode — 尚未啟用於正式決策。")
```

**Preserved**: V2-specific isolation note text. All V2 research computation logic. All tabs.

**Risk**: LOW — visual equivalence. The shared component shows the same semantic content in the same visual style.

---

### `dashboard/app.py` (P1A-06)

**Hash Before**: `0b936fe028c795def15dc2977fd23637e92cce632896eb03b246ee4aa81bb7a5`  
**Hash After**: `709e161c427c24240c1e1978d0eed701989554b1e2bcd5da45563853ea3ac002`

**Change**: In sidebar try block, added `MODEL_VERSION` import, replaced `st.caption("最新：{newest}")` with `data_freshness_banner(newest, source_label="股價庫", compact=True)`, added two caption lines.

**Before**:
```python
st.metric("股價資料", f"{cnt:,} 筆")
if newest:
    st.caption(f"最新：{newest}")
```

**After**:
```python
st.metric("股價資料", f"{cnt:,} 筆")
if newest:
    from dashboard.components import data_freshness_banner
    data_freshness_banner(newest, source_label="股價庫", compact=True)
...
st.caption(f"正式模型：{_MV}")
st.caption("研究結果不代表正式交易建議")
```

**PART H compliance**:
- ✓ Shows Production Model Version (`v8.0`)
- ✓ Shows data status with staleness color
- ✓ Shows Research Disclaimer
- ✓ Does NOT claim RC-2 H3 passed
- ✓ Does NOT claim provider is recovered
- ✓ Framed as "股價庫最新日期" (not individual stock date)

---

## Unchanged Files (Verified)

| File | Reason |
|---|---|
| `scripts/backfill_daily_prices.py` | RC-2 — not in scope |
| `scripts/hybrid_shadow_cron.py` | Cron — not in scope |
| `dashboard/_pages/live_monitor.py` | T1 already has good freshness |
| `dashboard/loaders.py` | No loader changes needed |
| `src/database.py` | Model — not in scope |
| All `src/` modules | Model — not in scope |
| All `tests/` (except new file) | Tests pass unchanged |

---

## Net Change Summary

| Metric | Value |
|---|---|
| New files | 2 (`components.py`, `test_session71_bundle_a.py`) |
| Modified files | 5 |
| Lines added | ~110 |
| Lines removed | ~13 |
| Computation changes | ZERO |
| DB changes | ZERO |
| Cron changes | ZERO |
| RC-2 changes | ZERO |
