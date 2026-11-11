# Session 70 — Shared UI Components

**Audit Date**: 2026-11-11  
**Scope**: Component API specifications for data freshness display  
**Status**: DESIGN ONLY — not authorized for implementation in this session  
**Target file**: `dashboard/components.py` (new file; does not exist yet)

---

## 1. Component Inventory

| Component | Priority | Used By | Replaces |
|---|---|---|---|
| `data_freshness_banner()` | HIGH | T0, T2, T4, T5, Sidebar | Ad-hoc inline HTML |
| `eod_disclaimer_badge()` | HIGH | T2 | None (new) |
| `research_only_banner()` | HIGH | T5, T6 | Docstring-only text |
| `chart_freshness_header()` | HIGH | T2 看盤 | None (new) |
| `overnight_risk_badge()` | LOW | T1 | Partial — extend existing |

---

## 2. Component Specifications

### 2.1 `data_freshness_banner()`

**Purpose**: Show "資料截至 {date}" with staleness color. Used as a persistent header element on any page with historical data.

**API**:
```python
def data_freshness_banner(
    as_of_date: "date | str | None",
    staleness_trading_days: int = 0,
    source_label: str = "資料",
    *,
    show_live_badge: bool = False,
    compact: bool = False,
) -> None:
    """
    Render an inline freshness indicator using st.markdown.
    
    Args:
        as_of_date: Latest date for which data is available. 
                    Pass None to show "資料日期：未知".
        staleness_trading_days: Number of trading days behind today.
                    0 = current, 1+ = stale.
        source_label: Label prefix, e.g., "K 線資料" or "AI 訊號".
        show_live_badge: If True, show "即時" badge instead of date.
        compact: If True, render as inline span (no border/padding).
    
    Returns:
        None (renders via st.markdown with unsafe_allow_html=True)
    """
```

**Behavior**:
- `staleness_trading_days == 0` → green: `✓ {source_label}截至：{date}`
- `staleness_trading_days == 1` → amber: `⚠ {source_label}截至：{date}（前一交易日）`
- `staleness_trading_days > 1` → orange: `⚠ {source_label}截至：{date}（落後 {n} 個交易日）`
- `as_of_date is None` → grey: `{source_label}日期：未知`
- `show_live_badge=True` → teal: `● 即時 {fetched_at}`

**Reference**: Extends existing `freshness_html` logic from `overview.py:99–115`.

**Usage examples**:
```python
# T2 看盤 — chart header
from dashboard.components import data_freshness_banner
data_freshness_banner(price_df["date"].max(), staleness_trading_days=5, source_label="K 線")

# Sidebar — compact inline
data_freshness_banner(newest, staleness_trading_days=5, compact=True)

# T1 盤中 — live mode
data_freshness_banner(None, show_live_badge=True, source_label="報價")
```

---

### 2.2 `eod_disclaimer_badge()`

**Purpose**: Persistent "EOD 收盤價 | 非即時" label for pages showing historical price charts.

**API**:
```python
def eod_disclaimer_badge(
    *,
    show_during_market_hours_only: bool = False,
) -> None:
    """
    Render a small "EOD data — not real-time" disclaimer badge.
    
    Args:
        show_during_market_hours_only: If True, only render between 09:00–13:30 CST.
                    If False (default), always render.
    """
```

**Rendered output** (HTML):
```html
<span class="data-type-label eod-badge">
  📊 EOD 收盤資料 · 非即時 · 每日 16:00 後更新
</span>
```

**Usage**: T2 看盤 `page_market_watch()`, T7 個股 chart

---

### 2.3 `research_only_banner()`

**Purpose**: Prominent "RESEARCH ONLY" banner for T5/T6 pages. Prevents users from treating research signals as live trading signals.

**API**:
```python
def research_only_banner(
    protocol_version: str = "",
    cutoff_date: "date | str | None" = None,
    *,
    compact: bool = False,
) -> None:
    """
    Render a prominent research-only banner.
    
    Args:
        protocol_version: e.g., "v8.0" to show model version.
        cutoff_date: IS/OOS split date, e.g., RESEARCH_CUTOFF_DATE.
        compact: If True, render as small strip. If False, render as full banner.
    """
```

**Rendered output** (full mode):
```html
<div class="research-only-banner">
  🔬 <strong>研究專區</strong> — 此頁面為策略研究記錄，
  不代表當前交易建議，不構成買賣指令。
  模型版本：v8.0 · 研究截止：2026-10-09
</div>
```

**Usage**: 
- `research_backtest.py`: top of `page_research_backtest()`
- `entry_timing_research.py`: top of `page_entry_timing_research()`
- Both in full mode (compact=False)

**Reference**: Extends existing `entry_timing_research.py:208` RESEARCH ONLY text.

---

### 2.4 `chart_freshness_header()`

**Purpose**: Combined header for K-line charts showing both chart data-as-of and analysis date.

**API**:
```python
def chart_freshness_header(
    chart_max_date: "date | str",
    analysis_date: "date | str | None" = None,
    staleness_trading_days: int = 0,
) -> None:
    """
    Render a two-part freshness header for K-line charts.
    
    Shows:
    - "K 線資料截至：{chart_max_date}"
    - "技術分析日期：{analysis_date}" (if provided)
    - Staleness warning if staleness_trading_days > 1
    - EOD disclaimer badge
    """
```

**Rendered output**:
```html
<div class="chart-freshness-header">
  <span>K 線資料截至：<strong>2026-11-05</strong></span>
  <span class="separator">·</span>
  <span>技術分析：<strong>2026-11-05</strong></span>
  <span class="eod-badge">EOD · 非即時</span>
  <!-- if stale: -->
  <span class="freshness-stale">⚠ 落後 5 個交易日</span>
</div>
```

**Usage**: `market_watch.py::page_market_watch()` before `st.plotly_chart()`

---

### 2.5 `overnight_risk_badge()` (extend existing)

**Purpose**: Extend T1's existing risk display to include `fetched_at` timestamp.

**API** (extension, not replacement):
```python
def overnight_risk_tooltip(
    risk_level: str,
    fetched_at: "datetime | None",
    data_quality: str,
) -> str:
    """
    Return HTML string for risk badge with tooltip showing fetched_at.
    
    Returns inline HTML — caller uses unsafe_allow_html=True.
    """
```

**Usage**: `live_monitor.py` — extend existing risk badge render.

---

## 3. Component File Structure

Target file: `dashboard/components.py`

```python
"""
dashboard/components.py — Shared UI components for freshness display.

DESIGN NOTE: All components render via st.markdown(unsafe_allow_html=True).
They do NOT query the database — callers pass pre-computed values.
This keeps components pure: input → HTML output.
"""

from datetime import date, datetime
from typing import Optional

import streamlit as st

# ── CSS (injected once per session) ───────────────────────────────────

_CSS_INJECTED = False

def _inject_freshness_css() -> None:
    global _CSS_INJECTED
    if _CSS_INJECTED:
        return
    st.markdown("""<style>
    .freshness-anchor { ... }
    .freshness-stale { ... }
    .research-only-banner { ... }
    .eod-badge { ... }
    </style>""", unsafe_allow_html=True)
    _CSS_INJECTED = True


# ── Components ─────────────────────────────────────────────────────────

def data_freshness_banner(...) -> None: ...
def eod_disclaimer_badge(...) -> None: ...
def research_only_banner(...) -> None: ...
def chart_freshness_header(...) -> None: ...
def overnight_risk_tooltip(...) -> str: ...
```

---

## 4. Data Flow (Components Are Display-Only)

```
loaders.py functions          components.py
    ↓                              ↓
load_price_chart_data()   →  chart_freshness_header(df["date"].max(), ...)
load_latest_pt_analysis() →  chart_freshness_header(..., analysis["date"])
load_db_stats()           →  data_freshness_banner(stats["newest"], ...)
[inline in page]          →  research_only_banner(MODEL_VERSION, CUTOFF)
```

Components receive computed values — they never query DB themselves.

---

## 5. Implementation Checklist (Phase 2)

```
[ ] Create dashboard/components.py (new file)
[ ] Move _freshness_css from inline to components.py
[ ] Implement data_freshness_banner()
[ ] Implement eod_disclaimer_badge()
[ ] Implement research_only_banner()
[ ] Implement chart_freshness_header()
[ ] Add components import to market_watch.py
[ ] Add components import to overview.py
[ ] Add components import to research_backtest.py
[ ] Add components import to entry_timing_research.py
[ ] Verify: existing _render_dailyprice_freshness_panel() unchanged
[ ] Verify: existing freshness_html in overview.py unchanged
```

---

## 6. What NOT to Change

| Item | Reason |
|---|---|
| `entry_timing_research.py:_render_dailyprice_freshness_panel()` | Reference implementation; keep as-is |
| `overview.py:_render_trading_reference()` freshness_html | Working logic — only add, never replace |
| `live_monitor.py` session label + valid/stale | Already correct |
| `loaders.py` TTL values | Separate concern; don't change without cache analysis |
| Any computation logic | Components are display-only |

---

## 7. Verdict

| Component | Spec Status |
|---|---|
| `data_freshness_banner()` | FULLY_SPECIFIED |
| `eod_disclaimer_badge()` | FULLY_SPECIFIED |
| `research_only_banner()` | FULLY_SPECIFIED |
| `chart_freshness_header()` | FULLY_SPECIFIED |
| `overnight_risk_badge()` | PARTIALLY_SPECIFIED (extension only) |
| Target file path | `dashboard/components.py` |
| Authorization | NOT_AUTHORIZED (design-only session) |
