# Session 70 — Display Contract Design

**Audit Date**: 2026-11-11  
**Scope**: DataFreshnessContract + SignalDisplayContract specifications  
**Authorization**: Design only — no implementation authorized in this session

---

## 1. Design Principles

1. **Never show price or signal data without a freshness anchor.** Every surface showing historical data must include "資料截至 {date}" or equivalent.
2. **Distinguish EOD from Live.** Any page that might be viewed during market hours must state whether data is real-time or end-of-day.
3. **Don't fabricate currency.** When data is stale, show it clearly. Do not hide the gap.
4. **Reuse, don't reinvent.** `_render_dailyprice_freshness_panel()` (entry_timing_research.py:1110) and the intraday `quote_date_status()` pattern are reference implementations.
5. **Frozen research is exempt from daily freshness.** IS/OOS research pages (T5, T6) already show the cutoff date — this is their "freshness anchor" and is correct.

---

## 2. DataFreshnessContract

### 2.1 Data Structure (Python)

```python
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

@dataclass
class DataFreshnessContract:
    # Identity
    source_name: str            # "daily_prices" | "analysis_results" | "intraday" | "overnight"
    source_type: str            # "sqlite_eod" | "sqlite_research" | "api_live" | "sqlite_analysis"
    
    # Temporal
    as_of_date: Optional[date]  # most recent date in source (None = unknown)
    fetched_at: Optional[datetime]  # when source was last fetched (UTC); None for SQLite sources
    cache_ttl_seconds: int      # loaders.py TTL for this source
    
    # Staleness computation
    staleness_trading_days: int   # 0 = current; >0 = days behind
    
    # Status
    freshness_status: str       # "CURRENT" | "STALE_1D" | "STALE_MULTI" | "LIVE" | "UNKNOWN"
    
    # Display
    display_label: str          # "資料截至：2026-11-05 ⚠️ 落後 5 個交易日"
    source_timezone: str = "Asia/Taipei"
```

### 2.2 Freshness Status Rules

| Condition | Status | Display Color |
|---|---|---|
| `staleness_trading_days == 0` | `CURRENT` | Green `#4caf50` |
| `staleness_trading_days == 1` | `STALE_1D` | Amber `#ff9800` |
| `staleness_trading_days > 1` | `STALE_MULTI` | Orange `#ff7043` |
| Live API data, `trade_date == today` | `LIVE` | Teal `#00bcd4` |
| Live API data, `trade_date != today` | `STALE_LIVE` | Red `#f44336` |
| Unable to determine | `UNKNOWN` | Grey `#9e9e9e` |

### 2.3 Standard Labels

```python
def build_freshness_label(contract: DataFreshnessContract) -> str:
    """Standard label string for any freshness contract."""
    if contract.freshness_status == "LIVE":
        t = contract.fetched_at.strftime("%H:%M") if contract.fetched_at else "—"
        return f"即時資料 · 更新時間 {t}"
    if contract.as_of_date is None:
        return "資料日期：未知"
    lag = contract.staleness_trading_days
    date_str = contract.as_of_date.strftime("%Y-%m-%d")
    if lag == 0:
        return f"資料截至：{date_str} ✓"
    elif lag == 1:
        return f"資料截至：{date_str}（落後 1 個交易日）"
    else:
        return f"資料截至：{date_str} ⚠️ 落後 {lag} 個交易日"
```

---

## 3. SignalDisplayContract

### 3.1 Mandatory Elements per Page

Every page showing price, score, or signal data MUST include:

| Element | Type | Placement | Format |
|---|---|---|---|
| `freshness_anchor` | Required | Header or first visible element | "資料截至：{date}" |
| `data_type_label` | Required | Near data or header | "EOD 收盤價" / "即時報價" / "AI 分析訊號" |
| `staleness_warning` | Conditional (if stale) | Prominent, inline | ⚠️ banner or metric color |
| `model_version` | Required for signals | Footer or info expander | "模型版本：v8.0" |

### 3.2 Per-Page Contract

#### T0 — 今日 (overview.py)

**Current**: Partial — `freshness_html` only triggers when `days_old > 1`  
**Required addition**: Add persistent "資料截至：{max_daily_price_date}" to trading reference header

```python
# PROPOSED: Add to _render_trading_reference(), always visible
st.markdown(
    f'<div class="freshness-anchor">'
    f'AI 分析訊號日期：{selected_date} | '
    f'價格資料截至：{latest_price_date}</div>',
    unsafe_allow_html=True
)
```

**Contract fields**:
- `source_name`: "recommendations"
- `freshness_anchor`: `selected_date` (always shown)
- `price_freshness`: `MAX(daily_prices.date)` for the specific stocks shown
- `data_type_label`: "AI 分析訊號（收盤後產生）"
- `model_version`: `MODEL_VERSION` from `src.database`

---

#### T2 — 看盤 (market_watch.py)

**Current**: None  
**Required**: Most critical gap — chart shows stale data with no indicator

```python
# PROPOSED: Add to page_market_watch(), before chart render
def _render_chart_freshness_header(price_df: pd.DataFrame, analysis: dict) -> None:
    if price_df.empty:
        return
    chart_max_date = price_df["date"].max()  # already str in current code
    analysis_date = analysis.get("date")     # available but unused
    
    st.markdown(
        f'<div class="chart-freshness">'
        f'K 線資料截至：<b>{chart_max_date}</b> · '
        f'技術分析日期：<b>{analysis_date or "—"}</b> · '
        f'<span style="color:#9e9e9e;font-size:0.75rem">收盤後更新 | 非即時</span>'
        f'</div>',
        unsafe_allow_html=True
    )
```

**Contract fields**:
- `source_name`: "daily_prices"
- `freshness_anchor`: `df["date"].max()` (always shown, even if chart is "current")
- `data_type_label`: "EOD 收盤價 | 非即時"
- `staleness_warning`: if `staleness_trading_days > 1`, show banner

---

#### T1 — 盤中 (live_monitor.py)

**Current**: GOOD — session label + valid/stale distinction already implemented  
**Minor addition**: Expose overnight context `fetched_at` in risk badge tooltip

**Contract fields**:
- `source_name`: "intraday" (live) + "overnight_market_contexts"
- `freshness_anchor`: `fetched_at.strftime("%H:%M:%S")` (live)
- `data_type_label`: "即時報價" (盤中) / "EOD 收盤後" (非盤中)
- Overnight: add `available_at` or `fetched_at` as tooltip on risk badge

---

#### T4 — 證據 (evidence.py)

**Current**: Protocol version shown; no data freshness  
**Required**: Add "最後評估日期" and "訊號覆蓋期間" to page header

**Contract fields**:
- `source_name`: "forward_outcome_evaluations"
- `freshness_anchor`: `MAX(forward_signals.trade_date)` for covered signals
- `data_type_label`: "前向執行評估（foe_v1 協議）"
- Note: outcome freshness = when was the last outcome evaluated (not when foe_v1 was registered)

---

#### T5/T6 — Research (research_backtest.py, entry_timing_research.py)

**Current**: RESEARCH_CUTOFF_DATE shown (IS/OOS split); T6 has `_render_dailyprice_freshness_panel()`  
**Required**: Add prominent RESEARCH banner (not just docstring)

**Contract fields** (T5):
- `freshness_anchor`: IS = `RESEARCH_CUTOFF_DATE` (frozen), OOS = `MAX(forward_signals.trade_date)`
- `data_type_label`: "🔬 研究專區 — 非即時交易訊號"
- `research_note`: "此頁面為策略研究記錄，不代表當前交易建議"

---

### 3.3 Shared CSS Class

All freshness labels should use a shared CSS class for consistency:

```css
.freshness-anchor {
    font-size: 0.72rem;
    color: #78909c;
    padding: 4px 8px;
    background: rgba(0,0,0,0.04);
    border-radius: 4px;
    display: inline-flex;
    gap: 8px;
    align-items: center;
}

.freshness-stale {
    color: #ff7043;
    font-weight: 600;
}

.freshness-warning-banner {
    background: rgba(255,112,67,0.08);
    border-left: 3px solid #ff7043;
    border-radius: 0 6px 6px 0;
    padding: 6px 12px;
    font-size: 0.8rem;
    margin: 6px 0;
}

.data-type-label {
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #9e9e9e;
}
```

---

## 4. Contract Validation Rules

A display is **compliant** if:

```python
def is_display_compliant(page: str, elements_shown: list[str]) -> bool:
    required = {
        "T0": ["freshness_anchor", "data_type_label"],
        "T1": ["freshness_anchor", "data_type_label", "live_vs_eod"],
        "T2": ["freshness_anchor", "data_type_label", "eod_disclaimer"],
        "T4": ["freshness_anchor", "protocol_version"],
        "T5": ["research_banner", "cutoff_date"],
        "T6": ["research_banner", "dailyprice_freshness_panel"],
    }
    return all(e in elements_shown for e in required.get(page, []))
```

---

## 5. What Must NOT Change

| Item | Reason |
|---|---|
| `_render_dailyprice_freshness_panel()` logic | Reference implementation — keep as-is |
| `overview.py` `freshness_html` logic | Existing logic is correct — extend, not replace |
| `quote_date_status()` in intraday_collector | Correct stale detection — keep |
| IS/OOS cutoff display in research_backtest.py | Correct research freshness boundary |
| `load_latest_completed_date()` semantics | Returns ExecutionLog success date correctly |

---

## 6. Verdict

| Requirement | Status |
|---|---|
| DataFreshnessContract defined | COMPLETE |
| SignalDisplayContract per page | COMPLETE |
| CSS class spec | COMPLETE |
| Reference implementations identified | COMPLETE |
| Authorization to implement | NOT AUTHORIZED (this session is design-only) |
