# Session 70 — Implementation Roadmap

**Audit Date**: 2026-11-11  
**Scope**: Phased implementation plan for data freshness display  
**Authorization**: DESIGN_ONLY — all implementation items require user authorization  
**Target**: Zero-risk display-only changes (no computation, no data model changes)

---

## Immutable Boundaries

Same as Session 69 — do not alter:
- `MODEL_VERSION = "v8.0"`, `RESEARCH_CUTOFF_DATE = 2026-10-09`
- `foe_v1`, RC-2 patch, V3 frozen params, cron schedule
- `_render_dailyprice_freshness_panel()` — reference implementation, do not break
- `overview.py::freshness_html` — existing logic is correct, only extend

---

## Phase 0 — Pre-implementation Checks (No Code)

**Prerequisites**: None. No authorization needed.

| Task | Action | Risk | Effort |
|---|---|---|---|
| P0-01 | Verify `staleness_trading_days` formula using TaiwanTradingCalendar for the 2026-11-05→11-11 gap | None | XS |
| P0-02 | Confirm `load_stock_prices()` returns prices only (no max_date) — need a separate query for freshness | None | XS |
| P0-03 | Confirm `analysis["date"]` is returned by `load_latest_pt_analysis()` and available to `market_watch.py` | None | XS |
| P0-04 | Confirm `dashboard/components.py` does not exist yet (no collision) | None | XS |

**P0-02 finding**: `load_stock_prices()` queries `MAX(DailyPrice.date)` internally (line 254) but does NOT return it. For freshness display, need to add a small helper or separate query.

**P0-03 finding**: `load_latest_pt_analysis()` returns `{"date": row.date, ...}` (line 885). The date IS available but `market_watch.py::_render_setup_banner()` does not display it.

---

## Phase 1A — Zero-Risk Banner Additions (Bundle A)

**Prerequisites**: User authorization for code changes.  
**Safety**: Display-only. No data loading changes. Git-revertible.  
**Estimated effort**: 2–3 hours total.  
**Gate**: All L1 contract tests must pass before merging.

### P1A-01: Create `dashboard/components.py`

**File**: `dashboard/components.py` (new)  
**Changes**: Add CSS injection + 4 component functions  
**Risk**: NONE — new file, nothing imports it yet  
**Effort**: S (45 min)

```python
# dashboard/components.py
"""Shared display components for data freshness labeling."""
# Components: data_freshness_banner, eod_disclaimer_badge,
#             research_only_banner, chart_freshness_header
```

---

### P1A-02: T2 看盤 — chart freshness header

**File**: `dashboard/_pages/market_watch.py`  
**Function**: `page_market_watch()` (line 446)  
**Change**: Add `chart_freshness_header()` call before `st.plotly_chart()`

```python
# BEFORE (line ~525):
analysis = load_latest_pt_analysis(sel_sid)
price_df = load_price_chart_data(sel_sid, days=90)
# ... renders chart directly

# AFTER:
from dashboard.components import chart_freshness_header
analysis = load_latest_pt_analysis(sel_sid)
price_df = load_price_chart_data(sel_sid, days=90)
if not price_df.empty:
    chart_freshness_header(
        chart_max_date=price_df["date"].max(),
        analysis_date=analysis.get("date"),
        staleness_trading_days=_compute_staleness(price_df["date"].max()),
    )
```

**Risk**: NONE — display only, no data change  
**Effort**: XS (20 min)

---

### P1A-03: T0 今日 — persistent freshness anchor

**File**: `dashboard/_pages/overview.py`  
**Function**: `_render_trading_reference()` (line 79)  
**Change**: Add always-visible anchor at top of section (before existing `freshness_html`)

```python
# BEFORE: freshness_html only shown when days_old > 1
# AFTER: always show anchor header

from dashboard.components import data_freshness_banner

# Add at top of _render_trading_reference():
data_freshness_banner(
    as_of_date=selected_date,  # the analysis date
    staleness_trading_days=days_old,
    source_label="AI 訊號",
)
# Keep existing freshness_html logic unchanged — it handles the
# "newer data available" case separately
```

**Risk**: NONE — adds above existing logic  
**Effort**: XS (15 min)

---

### P1A-04: T5 研究回測 — RESEARCH banner

**File**: `dashboard/_pages/research_backtest.py`  
**Function**: `page_research_backtest()` (top of function)  
**Change**: Add `research_only_banner()` before any data display

```python
from dashboard.components import research_only_banner
from src.database import MODEL_VERSION, RESEARCH_CUTOFF_DATE

def page_research_backtest():
    research_only_banner(
        protocol_version=MODEL_VERSION,
        cutoff_date=RESEARCH_CUTOFF_DATE,
    )
    # ... rest of function unchanged
```

**Risk**: NONE — adds display before existing content  
**Effort**: XS (10 min)

---

### P1A-05: T6 進場時機 — RESEARCH banner

**File**: `dashboard/_pages/entry_timing_research.py`  
**Function**: `page_entry_timing_research()` (top)  
**Change**: Replace inline HTML "RESEARCH ONLY" text with shared `research_only_banner()`

```python
# BEFORE (line ~208): inline HTML string
st.markdown('<span>🔬 RESEARCH ONLY — NOT A LIVE BUY SIGNAL</span>', ...)

# AFTER:
from dashboard.components import research_only_banner
research_only_banner(compact=True)  # compact because per-tab
```

**Risk**: LOW — replaces existing HTML string; verify visual equivalence  
**Effort**: XS (15 min)

---

### P1A-06: Sidebar — staleness color for `newest` caption

**File**: `dashboard/app.py`  
**Lines**: 276–278  
**Change**: Add color hint when `newest` is stale

```python
# BEFORE:
st.metric("股價資料", f"{cnt:,} 筆")
if newest:
    st.caption(f"最新：{newest}")

# AFTER:
from dashboard.components import data_freshness_banner
st.metric("股價資料", f"{cnt:,} 筆")
if newest:
    lag = _compute_staleness_trading_days(newest)
    data_freshness_banner(newest, staleness_trading_days=lag, compact=True)
```

**Risk**: LOW — replaces single `st.caption()` call  
**Effort**: XS (15 min)

---

## Phase 1B — Helper Function (Supporting Phase 1A)

**Required by P1A-02 and P1A-06**: a lightweight staleness calculator.

**File**: `dashboard/components.py` (same as P1A-01)

```python
def _compute_staleness_trading_days(as_of_date: "date | str") -> int:
    """
    Compute trading days between as_of_date and today.
    Uses TaiwanTradingCalendar if available; falls back to calendar days.
    
    Returns 0 if as_of_date >= today (current or future).
    """
    from datetime import date as _date
    if isinstance(as_of_date, str):
        as_of_date = _date.fromisoformat(as_of_date)
    today = _date.today()
    if as_of_date >= today:
        return 0
    try:
        from src.core.trading_calendar import TaiwanTradingCalendar
        cal = TaiwanTradingCalendar()
        # count trading days in (as_of_date, today]
        count = sum(
            1 for d in _iter_dates(as_of_date, today)
            if cal.is_trading_day(d) and d > as_of_date
        )
        return count
    except Exception:
        # Fallback: approximate with calendar days (safe underestimate)
        return max(0, (today - as_of_date).days)
```

---

## Phase 2 — Component Extraction (Optional, Phase 1 must pass first)

**Prerequisite**: Phase 1A complete and stable for 1+ sessions.

| Task | File | Description | Effort |
|---|---|---|---|
| P2-01 | `dashboard/components.py` | Extract `sample_size_warning()` from evidence_presenter | XS |
| P2-02 | `dashboard/components.py` | Extract signal card HTML builder from overview.py | M |
| P2-03 | `dashboard/loaders.py` | Add `load_dailyprice_max_date()` function (TTL=300s) | XS |

**P2-03 Detail**: Currently `max(daily_prices.date)` is queried in 3+ places (loaders.py:254, app.py:272, entry_timing_research.py:1118). Extract to single cached function.

```python
@st.cache_data(ttl=300)
def load_dailyprice_max_date() -> "date | None":
    """MAX(daily_prices.date) with 5-min cache."""
    try:
        from src.database import DailyPrice, get_session
        from sqlalchemy import func
        s = get_session()
        result = s.query(func.max(DailyPrice.date)).scalar()
        s.close()
        return result
    except Exception:
        return None
```

---

## Phase 3 — Full Compliance Audit

**Prerequisite**: Phase 2 complete.  
**Action**: Run TC-C01–TC-EC04 acceptance tests. Confirm all 14 pass.  
**Output**: Session N "Data Freshness Compliance Report" document.

---

## File-Level Change Summary

| File | Phase | Change Type | Lines Affected | Risk |
|---|---|---|---|---|
| `dashboard/components.py` | 1A | CREATE NEW | ~150 lines | NONE |
| `dashboard/_pages/market_watch.py` | 1A | ADD 5 lines | ~530 | NONE |
| `dashboard/_pages/overview.py` | 1A | ADD 3 lines | ~84 | NONE |
| `dashboard/_pages/research_backtest.py` | 1A | ADD 3 lines | ~1 | NONE |
| `dashboard/_pages/entry_timing_research.py` | 1A | REPLACE 2 lines | ~208 | LOW |
| `dashboard/app.py` | 1A | REPLACE 2 lines | ~276 | LOW |
| `dashboard/loaders.py` | 2 | ADD function | +15 lines | LOW |
| `tests/test_components.py` | 1A | CREATE NEW | ~100 lines | NONE |

**Total changes**: ~8 files, ~280 net new lines, 0 logic changes.

---

## Rollback Plan

Each phase is independently revertible via `git revert`:
- Phase 1A: `git revert HEAD` (single commit)
- Phase 2: `git revert HEAD~2..HEAD`
- Phase 3: No code, no rollback needed

---

## Verdict

| Item | Status |
|---|---|
| Phase 0 pre-checks | ACTIONABLE_NOW (no authorization needed) |
| Phase 1A bundle | AUTHORIZATION_PENDING |
| Phase 1B helper | AUTHORIZATION_PENDING |
| Phase 2 extraction | AUTHORIZATION_PENDING (after 1A) |
| Risk | ZERO for 1A; LOW for 2 |
| Estimated total effort | Phase 1A: 2–3 hours; Phase 2: 2 hours |
| Impact | HIGH — eliminates GAP_CRITICAL on T2 看盤 |
