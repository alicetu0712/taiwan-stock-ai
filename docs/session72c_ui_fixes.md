# Session 72C — UI Fixes Log

**Session**: 72C  
**Applied to**: `/Users/alicetu/Desktop/Antigravity/stock_platform_72ab/dashboard/app.py`  
**Production**: UNCHANGED  
**Date**: 2026-11-13

---

## Fix F1 — Exception Safety for `_render_version_info()`

| Field | Value |
|---|---|
| Issue | `_render_version_info()` called directly at line 370, bypassing `_render()` wrapper |
| Root Cause | 72AB implementation oversight — `_render()` wraps page functions in try/except; module-level helper was not wrapped |
| Files | `dashboard/app.py` |
| Change | Line 370: `_render_version_info()` → `_render(_render_version_info)` |
| Regression Impact | None — `_render()` accepts any callable; tested with existing test suite |
| Test | All 19 72AB tests PASS after change |

**Before**:
```python
with sub5[1]:
    _render_version_info()
```

**After**:
```python
with sub5[1]:
    _render(_render_version_info)
```

---

## Fix F2 — Flatten Triple Tab Nesting in 策略績效

| Field | Value |
|---|---|
| Issue | `sub4[2]` (歷史回測) and `sub4[3]` (進場研究) each contained a third-level `st.tabs()` — creating 3 levels: `main_tabs → sub4 → bt_tabs/rs_tabs` |
| Root Cause | 72AB implementation used `st.tabs()` for sub-page selection within already-nested sub-tabs |
| Files | `dashboard/app.py` |
| Change | Replaced inner `st.tabs()` with `st.radio(horizontal=True)` in both affected sections |
| Widget Keys Added | `s72c_bt_choice` and `s72c_rs_choice` (prefixed to avoid conflicts) |
| Regression Impact | None — same page functions called, same data |
| Test | All 19 72AB tests PASS; `test_five_main_tabs_in_ast` still counts exactly 5 top-level tabs |

**Before (歷史回測)**:
```python
with sub4[2]:
    bt_tabs = st.tabs(["🔬 研究回測", "📦 Legacy 驗證"])
    with bt_tabs[0]:
        _render(page_research_backtest)
    with bt_tabs[1]:
        _render(page_backtest)
```

**After**:
```python
with sub4[2]:
    bt_choice = st.radio("回測類型",
        ["🔬 研究回測（V2 Research）", "📦 Legacy 驗證（V1 Historical）"],
        horizontal=True, key="s72c_bt_choice", label_visibility="collapsed")
    st.markdown("---")
    if bt_choice and "研究回測" in bt_choice:
        _render(page_research_backtest)
    else:
        _render(page_backtest)
```

---

## No Other Fixes Applied

No other UI issues were found in the isolated codebase. All page functions were left unchanged.

Items not fixed (require backend authorization):
- `v2_shadow_signals` automated write path (`BACKEND_CHANGE_REQUIRES_SEPARATE_AUTHORIZATION`)
- Widget keys inside individual page files (not needed — no duplicates found)
- Neon connection in `entry_timing_research.py` (requires production Streamlit restart to fix env vars)

---

## Prototype Badge Note

The sidebar contains `<span class="s72ab-badge">72AB 隔離版</span>` to clearly identify the prototype. This **must be removed** before production deployment. It is a presentation-only change with no logic impact.
