# Session 71D — Data Source Provenance

**Date**: 2026-11-11  
**Check Time**: 2026-11-11 14:16–14:25 CST  
**Authorization**: AUTH-S71-BUNDLE-A (read-only acceptance phase)

---

## 1. Central Question

> **T2 股票 2465 的 "2026-11-10" K 線日期究竟來自哪裡？**  
> **T0 的 "2026-11-10" 股價日期究竟來自哪裡？**

Both dates come from **Neon PostgreSQL** — the actual production database for the dashboard.

---

## 2. T2 (K-chart Freshness) — End-to-End Provenance

```
Neon PostgreSQL
  └─ table: daily_prices
  └─ stock_id = '2465'
  └─ MAX(date) = '2026-11-10'   ← verified by read-only query
        ↓
  load_price_chart_data("2465", days=90)
    [dashboard/loaders.py:814]
    Uses: get_session() → config.DATABASE_URL → Neon
        ↓
  price_df = DataFrame with date column, max = "2026-11-10"
        ↓
  market_watch.py:558
    _chart_max_date = price_df["date"].max()   → "2026-11-10"
        ↓
  chart_freshness_header(_chart_max_date, _analysis_date)
    [dashboard/components.py]
    staleness_days = (date.today() - date(2026,11,10)).days = 1
    → renders: "K 線資料截至：2026-11-10 收盤·落後 1 天·EOD·非即時"
        ↓
  Screenshot SS-02 (Playwright): visible text confirmed ✓
```

| Node | Value | Evidence | Data Mode |
|---|---|---|---|
| Source DB | Neon PostgreSQL | `DATABASE_URL = postgresql://...` via config.py | PRODUCTION_NEON |
| Table | `daily_prices` | SQLAlchemy ORM `DailyPrice` | READ_ONLY_QUERY |
| Filter | `stock_id = '2465'` | `load_price_chart_data("2465")` | — |
| Max date in Neon | 2026-11-10 | read-only query confirmed | VERIFIED |
| `price_df["date"].max()` | "2026-11-10" | code path analysis | INFERRED |
| Freshness label | "2026-11-10 收盤·落後 1 天" | SS-02 screenshot text | VERIFIED |

**Label**: `PRODUCTION_NEON_DATA`

---

## 3. T0 (Signal & Price Banners) — End-to-End Provenance

### Signal Banner: "⚠ AI 訊號截至：2026-10-28（落後 14 天）"

```
Fixture: SEL_DATE = date(2026, 10, 28)   ← hardcoded in fixture_71c.py
     ↓
page_today(SEL_DATE) → overview.py
     ↓
selected_date = 2026-10-28
days_old = (date.today() - selected_date).days
         = (2026-11-11 - 2026-10-28).days = 14
     ↓
data_freshness_banner(selected_date, 14, source_label="AI 訊號", compact=True)
     → "⚠ AI 訊號截至：2026-10-28（落後 14 天）"
```

| Node | Value | Mode |
|---|---|---|
| Source | Fixture `SEL_DATE` constant | `ISOLATED_FIXTURE_DATA` |
| Date | 2026-10-28 | Fixture-defined |
| Staleness calculation | `date.today() - date(2026, 10, 28)` = 14 days | Computed at render time |

### Price Banner: "⚠ 股價資料截至：2026-11-10（前一交易日）"

```
page_today → overview.py → _render_trading_reference()
     ↓
load_today_data(selected_date)   [loaders.py]
     Uses: get_session() → Neon
     ↓
latest_date = MAX(DailyPrice.date)   [loaders.py:254]
            = 2026-11-10              ← Neon MAX(date) for all stocks
     ↓
_price_lag = (date.today() - latest_date).days = 1
     ↓
data_freshness_banner(latest_date, 1, source_label="股價資料", compact=True)
     staleness=1 → special case: "（前一交易日）"
     → "⚠ 股價資料截至：2026-11-10（前一交易日）"
```

| Node | Value | Mode |
|---|---|---|
| Source DB | Neon PostgreSQL | PRODUCTION_NEON |
| Query | `MAX(DailyPrice.date)` | read-only |
| Result | 2026-11-10 | Neon actual max |
| Staleness | 1 day | computed |
| Label | "（前一交易日）" | staleness=1 special case |

---

## 4. Database Path Decision Tree

```
fixture_71c.py runs:
  import dashboard._pages.overview → page_today → load_today_data()
                                                        ↓
  import dashboard._pages.market_watch → page_market_watch → load_price_chart_data()
                                                                        ↓
  Both call: from src.database import DailyPrice, get_session
                                              ↓
              src/database.py → get_engine() → from config import DATABASE_URL
                                                        ↓
              config.py:50: USE_NEON=true AND NEON_URL present
                        → DATABASE_URL = postgresql://...@neon.tech/...
                                                        ↓
              *** NEON POSTGRESQL IS USED — NOT data/platform.db ***
```

---

## 5. What S71C "Real DB (read-only)" Meant

The fixture header said: "Real DB (read-only)" and "Real database reads (read-only)".

This was **accurate but potentially misleading**:
- "Real DB" = the actual live database the app uses = **Neon**
- NOT = `data/platform.db` (local SQLite)
- The fixture did use real production data, not mocks or seeds
- However, prior sessions described production DB as "534,770 rows / max 2026-11-05" which is local SQLite, creating confusion

**S71C screenshots ARE genuine production data.** Dates shown are correct.

---

## 6. Source Verification Table

| Data Point | Source | Actual Value | Mode | Confident? |
|---|---|---|---|---|
| T2: `price_df` for 2465 | Neon `daily_prices` WHERE `stock_id='2465'` | max=2026-11-10 | PRODUCTION_NEON | YES (query verified) |
| T2: `_chart_max_date` | `price_df["date"].max()` | "2026-11-10" | COMPUTED | YES (from confirmed source) |
| T0: `selected_date` | Fixture constant `SEL_DATE` | 2026-10-28 | ISOLATED_FIXTURE_DATA | YES (fixture code) |
| T0: `latest_date` | Neon `MAX(DailyPrice.date)` | 2026-11-10 | PRODUCTION_NEON | YES (query verified) |
| T0: signal staleness | `date.today() - selected_date` | 14 | COMPUTED | YES |
| T0: price staleness | `date.today() - latest_date` | 1 | COMPUTED | YES |
| Sidebar: `2026-11-05` | Fixture hardcoded constant | 2026-11-05 | ISOLATED_FIXTURE_DATA | YES (fixture code line 79) |
| Sidebar: `date.today()` | System date at render | 2026-11-11 | COMPUTED | YES |

---

## 7. Verdict

| Category | Verdict |
|---|---|
| T2 K-chart date source | `DATA_SOURCE_RECONCILED` — Neon `daily_prices[2465]` max=2026-11-10 |
| T0 signal date source | `DATA_SOURCE_RECONCILED` — Fixture `SEL_DATE=2026-10-28` |
| T0 price date source | `DATA_SOURCE_RECONCILED` — Neon `MAX(DailyPrice.date)=2026-11-10` |
| Sidebar test data | `ISOLATED_FIXTURE_DATA` — hardcoded in fixture (not production query) |
| Prior "534,770 rows" claim | `BASELINE_DATABASE_MISMATCH` — was local SQLite, not dashboard source |
| S71C screenshots | `PRODUCTION_NEON_DATA` — real Neon data, not mocked |
| Overall | `DATA_SOURCE_PARTIALLY_RECONCILED` — data correct, prior baseline documentation wrong |
