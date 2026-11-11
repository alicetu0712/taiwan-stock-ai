# Session 71D — Bundle A Freshness Contract Verification

**Date**: 2026-11-11  
**Check Time**: 2026-11-11 14:16–14:25 CST  
**Authorization**: AUTH-S71-BUNDLE-A (read-only acceptance phase)

---

## 1. Contract Definition (from Session 70)

The DataFreshnessContract requires:
1. Use actual stock DataFrame (per-stock date, not global MAX)
2. Use correct date column (`price_df["date"]`)
3. Handle empty data (`price_df.empty` → `None`)
4. Handle `None` / unknown dates safely
5. Handle non-trading days (calendar-day staleness for display)
6. Correctly label EOD vs Live
7. Clearly separate Signal Date from Price Date
8. Work correctly with Fixture (Neon-connected)
9. Never use global `MAX(date)` as K-chart freshness
10. No misleading text

---

## 2. Per-Item Contract Verification

### G1: Uses actual stock DataFrame

```python
# dashboard/_pages/market_watch.py:558
_chart_max_date = price_df["date"].max() if not price_df.empty else None
```

- `price_df` is loaded via `load_price_chart_data(sel_sid)` → queries Neon WHERE `stock_id = sel_sid`
- Returns rows for that specific stock only
- `price_df["date"].max()` = max of THAT STOCK's dates

**Verdict**: `VERIFIED` — per-stock date used correctly

---

### G2: Correct date column

```python
df["date"] = df["date"].astype(str)   # loaders.py:851
```

- Column name is `"date"`, type str
- `price_df["date"].max()` returns the lexicographically greatest date string
- For ISO date strings (YYYY-MM-DD), lexicographic max = chronological max

**Verdict**: `VERIFIED` — correct column, correct behavior

---

### G3: Empty data handling

```python
_chart_max_date = price_df["date"].max() if not price_df.empty else None
chart_freshness_header(_chart_max_date, _analysis_date)
```

```python
# components.py: chart_freshness_header with None input
# → renders: "K 線資料時間未確認·EOD·非即時"
```

- Empty DataFrame → `_chart_max_date = None`
- `chart_freshness_header(None)` → safe fallback text
- Confirmed in SS-05 (Sidebar tab): "K 線資料時間未確認·EOD·非即時"

**Verdict**: `VERIFIED`

---

### G4: None / unknown date handling

```python
# components.py:_staleness_days
def _staleness_days(d) -> int:
    if d is None:
        return -1
    ...
# chart_freshness_header(None) → staleness=-1 → "K 線資料時間未確認"
# data_freshness_banner(None, -1) → "未知來源日期：未確認"
```

- Confirmed in SS-05 sidebar tests

**Verdict**: `VERIFIED`

---

### G5: Non-trading day handling

```python
# components.py:_staleness_days
staleness_days = (date.today() - d_as_date).days
```

- Uses calendar-day difference, not trading-day difference
- 2026-11-11 (today) − 2026-11-10 (Neon max) = 1 calendar day → shows "落後 1 天"
- Known limitation: "落後 1 天" on a Monday after a weekend would correctly show 1 calendar day
- Not using TaiwanTradingCalendar for staleness (Phase 2 enhancement, not Phase 1A requirement)

**Verdict**: `VERIFIED` — calendar days intended for display; trading-day precision is Phase 2

---

### G6: EOD vs Live label

```python
# components.py:chart_freshness_header
"EOD·非即時"   # always appended to K-chart freshness
```

```python
# components.py:eod_disclaimer_badge
"📊 EOD 收盤資料·非即時·每日 16:00 後更新"
```

- All freshness labels explicitly include "EOD·非即時"
- No data source claims real-time

**Verdict**: `VERIFIED`

---

### G7: Signal Date vs Price Date separation

T0 (overview.py) renders TWO separate banners:
1. `data_freshness_banner(selected_date, _sig_lag, source_label="AI 訊號")` → "AI 訊號截至：2026-10-28（落後 14 天）"
2. `data_freshness_banner(_price_as_of, _price_lag, source_label="股價資料")` → "股價資料截至：2026-11-10（前一交易日）"

The second banner only renders when `_price_as_of != selected_date` (guard in overview.py).

**Verdict**: `VERIFIED` — signal and price dates clearly separated

---

### G8: Works correctly with Fixture

- Fixture uses `get_session()` → Neon → real production data
- `price_df` for stock 2465 returns real Neon rows with max=2026-11-10
- Freshness calculations use real data, not mocked values
- Sidebar tab uses hardcoded test dates ("2026-11-05") for component isolation, clearly labeled

**Verdict**: `VERIFIED` — fixture correctly exercises real data path

---

### G9: Does NOT use global MAX(date) for K-chart

```python
# CORRECT (implemented):
_chart_max_date = price_df["date"].max()   # per-stock from DailyPrice query

# FORBIDDEN (not in code):
# _chart_max_date = load_max_daily_price_date()  # global MAX
# _chart_max_date = date.today()
```

- Neon `MAX(daily_prices.date)` = 2026-11-10 (same for all stocks in this case)
- Neon `daily_prices[2465].max()` = 2026-11-10 (same in this case)
- BUT: different stocks can have different max dates if data is uneven
- Code uses per-stock path, not global MAX

**Verdict**: `VERIFIED`

---

### G10: No misleading text

| Component | Text | Assessment |
|---|---|---|
| K-chart header (staleness=1) | "落後 1 天" | Accurate (calendar day) |
| T0 signal banner | "落後 14 天" | Accurate (Oct 28 → Nov 11 = 14 days) |
| T0 price banner | "（前一交易日）" | Accurate (staleness=1 special case) |
| T5 research banner | "研究截止：2026-10-09" | Accurate (IS/OOS cutoff, not data staleness) |
| T6 research banner | "🔬 研究用途｜非正式交易推薦" | Accurate |
| Sidebar staleness=0 | "✓ 即時資料截至：2026-11-11" | Accurate |

**Verdict**: `VERIFIED` — no misleading text found

---

## 3. staleness=1 Special Case

```python
# components.py:137-140
elif staleness_days == 1:
    inner = (
        f'<span class="fr-stale">'
        f"⚠ {source_label}截至：{d_str}（前一交易日）"
        f"</span>"
    )
    wrapper_class = "fr-anchor"
```

This special-cases staleness of exactly 1 calendar day to show "（前一交易日）" instead of "（落後 1 天）". This is a deliberate UX choice — on the trading day immediately after the last data, "前一交易日" is more natural than "落後 1 天".

**Assessment**: Intentional, documented, correct behavior. Not a defect.

---

## 4. `_staleness_days()` Scope

`_staleness_days()` is called with `date.today()` as the reference:

```python
def _staleness_days(d) -> int:
    today = date.today()
    ...
    staleness_days = (today - d_as_date).days
```

- This is DISPLAY-ONLY computation
- `date.today()` here = system clock when dashboard renders
- This is NOT used as "market data time" or "trading signal date"
- The contract explicitly allows calendar-day staleness for display

**Verdict**: `FRESHNESS_CONTRACT_VERIFIED` — scope is correct

---

## 5. Final Verdict

| Item | Verdict |
|---|---|
| G1: Per-stock DataFrame | ✓ VERIFIED |
| G2: Correct date column | ✓ VERIFIED |
| G3: Empty data handling | ✓ VERIFIED |
| G4: None/unknown handling | ✓ VERIFIED |
| G5: Non-trading day display | ✓ VERIFIED (calendar-day, by design) |
| G6: EOD/Live label | ✓ VERIFIED |
| G7: Signal/Price separation | ✓ VERIFIED |
| G8: Fixture correctness | ✓ VERIFIED (Neon real data) |
| G9: No global MAX misuse | ✓ VERIFIED |
| G10: No misleading text | ✓ VERIFIED |
| **Overall** | **`FRESHNESS_CONTRACT_VERIFIED`** |
