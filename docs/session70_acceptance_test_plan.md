# Session 70 — Acceptance Test Plan

**Audit Date**: 2026-11-11  
**Scope**: Verifiable acceptance criteria for data freshness display  
**Test Type**: UI behavioral tests + contract unit tests  
**Authorization**: Design-only. Tests must be written before implementation (Phase 2).

---

## 1. Test Strategy

Three layers of testing:

| Layer | Type | When | Tool |
|---|---|---|---|
| L1: Contract unit tests | Pure Python | Before UI changes | pytest |
| L2: UI integration tests | Render verification | After component implementation | Manual or pytest-html |
| L3: Regression tests | Existing page functionality | After every change | pytest (existing suite) |

---

## 2. L1 — Contract Unit Tests

### TC-C01: DataFreshnessContract staleness classification

```python
def test_freshness_status_current():
    """staleness_trading_days=0 → CURRENT"""
    contract = DataFreshnessContract(
        source_name="daily_prices",
        source_type="sqlite_eod",
        as_of_date=date(2026, 11, 11),
        staleness_trading_days=0,
        freshness_status="CURRENT",
        display_label="資料截至：2026-11-11 ✓",
        ...
    )
    assert contract.freshness_status == "CURRENT"

def test_freshness_status_stale_multi():
    """staleness_trading_days=5 → STALE_MULTI"""
    contract = build_freshness_contract("daily_prices", as_of=date(2026,11,5))
    assert contract.freshness_status == "STALE_MULTI"
    assert "落後 5 個交易日" in contract.display_label

def test_freshness_status_unknown():
    """as_of_date=None → UNKNOWN"""
    contract = build_freshness_contract("analysis_results", as_of=None)
    assert contract.freshness_status == "UNKNOWN"
    assert "未知" in contract.display_label
```

### TC-C02: build_freshness_label() correctness

```python
@pytest.mark.parametrize("lag,expected_fragment", [
    (0, "✓"),
    (1, "前一交易日"),
    (5, "落後 5 個交易日"),
])
def test_build_freshness_label(lag, expected_fragment):
    label = build_freshness_label(date(2026, 11, 5), lag)
    assert expected_fragment in label
```

### TC-C03: is_display_compliant() validation

```python
def test_t2_compliant_with_all_required():
    assert is_display_compliant("T2", [
        "freshness_anchor", "data_type_label", "eod_disclaimer"
    ]) is True

def test_t2_non_compliant_missing_anchor():
    assert is_display_compliant("T2", [
        "data_type_label", "eod_disclaimer"
    ]) is False

def test_t5_compliant():
    assert is_display_compliant("T5", [
        "research_banner", "cutoff_date"
    ]) is True
```

### TC-C04: Signal provenance assertion

```python
def test_eod_price_ssot():
    """EOD price freshness must derive from daily_prices, not analysis_results"""
    contract = get_eod_freshness()
    assert contract.source_name == "daily_prices"
    assert contract.source_type == "sqlite_eod"

def test_live_quote_different_from_eod():
    """Live quote contract must have source_type='api_live'"""
    contract = get_intraday_freshness()
    assert contract.source_type == "api_live"
    assert contract.freshness_status in ("LIVE", "STALE_LIVE")
```

---

## 3. L2 — UI Integration Tests (Manual)

### TC-UI01: T2 看盤 — chart freshness header

**Setup**: Open T2 看盤 at any time  
**Expected**:
- [ ] "K 線資料截至：YYYY-MM-DD" visible above or below chart
- [ ] "技術分析日期：YYYY-MM-DD" visible  
- [ ] "EOD · 非即時" badge visible  
- [ ] If `staleness_trading_days > 1`: orange ⚠️ warning visible

**Anti-pattern**: Chart renders with no date indicator at all. ← CURRENT state (must fix)

---

### TC-UI02: T2 看盤 — EOD badge during market hours

**Setup**: Open T2 看盤 between 09:00–13:30 CST  
**Expected**:
- [ ] "📊 EOD 收盤資料 · 非即時 · 每日 16:00 後更新" badge visible  
- [ ] No live price displayed (chart still shows last EOD)

---

### TC-UI03: T0 今日 — persistent freshness anchor

**Setup**: Open T0 今日, select a date that is the latest available  
**Expected**:
- [ ] Freshness anchor visible even when `days_old == 0` relative to latest_data_date
- [ ] Shows "AI 分析訊號日期：{selected_date}"
- [ ] Shows "價格資料截至：{max_daily_price_date}"

**Current state**: Only shows `freshness_html` warning when `days_old > 1`. When viewing the latest date, no freshness indicator appears. ← MUST FIX

---

### TC-UI04: T5/T6 — RESEARCH banner

**Setup**: Open T5 研究回測 or T6 進場時機  
**Expected**:
- [ ] Banner "🔬 研究專區" visible at top (not just in docstring)
- [ ] "不代表當前交易建議" text visible
- [ ] Model version and cutoff date shown

**Current state**: T5 has no banner. T6 has text "RESEARCH ONLY" in HTML but not prominently at page top.

---

### TC-UI05: Sidebar — staleness color

**Setup**: Current state (staleness = 5 trading days)  
**Expected**:
- [ ] `st.caption("最新：2026-11-05")` shown with orange color or ⚠️ prefix
- [ ] Not just plain grey text

**Current state**: Plain `st.caption()` with no color differentiation.

---

### TC-UI06: T1 盤中 — existing behavior preserved

**Setup**: Open T1 盤中  
**Expected** (must NOT regress):
- [ ] Session label "盤中" / "收盤後" still shown
- [ ] Valid/stale per quote still shown
- [ ] Refresh interval countdown still shown

---

## 4. L3 — Regression Tests

All existing tests must pass after any freshness display change.  
Reference: 4313 total tests (as of S64).

| Test Suite | File | Scope |
|---|---|---|
| Core pipeline | `tests/test_*.py` | MODEL_VERSION, signal computation |
| DB/ORM | `tests/test_database*.py` | Schema, NOT NULL, models |
| Loaders | (if exists) | Cache TTL, return types |
| Component | `tests/test_components.py` | NEW — must be written |

**Golden rule**: Adding a freshness banner must not change any return value from loaders.py functions. Components are display-only.

---

## 5. Edge Case Tests

### TC-EC01: Empty daily_prices (fresh install)
```python
def test_freshness_banner_no_data():
    """as_of_date=None when no prices exist → shows 'unknown' gracefully"""
    banner_html = render_data_freshness_banner(as_of_date=None, ...)
    assert "未知" in banner_html
    # Must not raise exception
```

### TC-EC02: Non-trading day selected
```python
def test_freshness_on_weekend():
    """selected_date = Saturday, latest_data_date = previous Friday"""
    # freshness_anchor should show Friday's date, not Saturday
    assert freshness_anchor_date == friday_date
```

### TC-EC03: staleness_trading_days calculation
```python
def test_staleness_counts_trading_days_not_calendar_days():
    """2026-11-05 to 2026-11-11 = 5 calendar days but 4 trading days (Nov 7/8 weekend + Nov 10 holiday? )"""
    # Need TradingCalendarService for accurate count
    lag = compute_staleness_trading_days(date(2026, 11, 5), date(2026, 11, 11))
    assert lag == 4  # or 5 if Nov 10 is trading — verify with calendar
```

### TC-EC04: Research page frozen state
```python
def test_research_cutoff_never_shown_as_stale():
    """RESEARCH_CUTOFF_DATE = 2026-10-09 is a research boundary, not a data staleness date"""
    # research_only_banner should NOT show "落後 N 個交易日"
    banner_html = render_research_only_banner(cutoff_date=RESEARCH_CUTOFF_DATE)
    assert "落後" not in banner_html
    assert "研究截止" in banner_html  # correct framing
```

---

## 6. Acceptance Criteria Summary

| ID | Description | Required for Phase 1 |
|---|---|---|
| TC-C01 | DataFreshnessContract staleness classification | Yes |
| TC-C02 | build_freshness_label() | Yes |
| TC-C03 | is_display_compliant() | Yes |
| TC-C04 | Signal provenance assertion | Yes |
| TC-UI01 | T2 chart freshness header | Yes |
| TC-UI02 | T2 EOD badge | Yes |
| TC-UI03 | T0 persistent anchor | Yes |
| TC-UI04 | T5/T6 RESEARCH banner | Yes |
| TC-UI05 | Sidebar staleness color | Yes |
| TC-UI06 | T1 no regression | Yes (gating) |
| TC-EC01 | Empty data | Yes |
| TC-EC02 | Weekend date | Yes |
| TC-EC03 | Trading day staleness calculation | Yes |
| TC-EC04 | Research cutoff not shown as stale | Yes |

**Gate**: All 14 tests must pass before Phase 1 implementation is considered complete.

---

## 7. Verdict

| Item | Status |
|---|---|
| L1 test specs | COMPLETE |
| L2 test specs | COMPLETE |
| L3 regression requirement | DEFINED |
| Edge cases | 4 identified |
| Test file target | `tests/test_components.py` (new) |
| Authorization | NOT_AUTHORIZED (design-only session) |
