# DailyPrice Pipeline — Root Cause Analysis

**Date:** 2026-11-05  
**Symptom:** Local SQLite `data/platform.db` DailyPrice frozen at 2026-10-28  
**Shadow runner status:** `BLOCKED_STALE_DATA` (gap = 8 calendar days > 7-day tolerance)

---

## 1. Architecture Clarification

There are TWO separate database paths:

| Database | Location | Updated by | Used by |
|----------|----------|------------|---------|
| Production Neon PostgreSQL | Cloud (Neon.tech) | GitHub Actions `daily-pipeline.yml` (Mon–Fri 15:55 Taiwan) | Streamlit Cloud dashboard, production recommendations |
| Local Research SQLite | `data/platform.db` | Manual local run only | Hybrid Forward Shadow runner |

**Key invariant:** GitHub Actions writes to Neon via `DATABASE_URL = NEON_URL`. It does NOT write to local SQLite. These are separate databases.

---

## 2. Root Cause

**Primary cause:** No automated local DailyPrice collection exists.

| Check | Verdict |
|-------|---------|
| GitHub Actions `daily-pipeline.yml` writes to local SQLite | ❌ No — writes to Neon only |
| Local crontab configured | ❌ No — `crontab -l` returned empty |
| `run_daily.py` scheduled locally | ❌ No automation |
| Last manual local run | 2026-10-28 (8 calendar days ago) |

**Contributing factors:**

1. **Sparse existing data:** The local SQLite never had complete daily coverage. Even before the current gap, dates like 2026-10-15, 10-19, 10-20, 10-23, 10-26, 10-27 were missing because the pipeline was only run manually on some days.

2. **STALE_DATA_TOLERANCE_DAYS = 7:** The shadow runner blocks after 7 calendar days without a data update. With a gap of 8 days (10-28 → 11-05), it was `BLOCKED_STALE_DATA`.

3. **HybridTradingCalendar is data-driven:** The shadow runner's trading calendar is built from actual 0050 price dates in SQLite (`TradingCalendar.from_db(conn)`). A date is only recognized as a trading day if that date's prices exist in the DB. Without 2026-11-05 data, the shadow cannot classify 11-05 as a trading day.

---

## 3. Missing Trading Days (2026-10-28 → 2026-11-05)

| Date | Day | Expected trading day? | Status |
|------|-----|----------------------|--------|
| 2026-10-29 | Thu | ✓ | Missing — no public API for historical all-stocks data |
| 2026-10-30 | Fri | ✓ | Missing — same |
| 2026-10-31 | Sat | Weekend | N/A |
| 2026-11-01 | Sun | Weekend | N/A |
| 2026-11-02 | Mon | ✓ | Missing — same |
| 2026-11-03 | Tue | ✓ | Missing — same |
| 2026-11-04 | Wed | ✓ | **Recovered** (via `backfill_daily_prices.py --execute`) |
| 2026-11-05 | Thu | ✓ | Pending (today's data not yet published) |

---

## 4. API Investigation Results

| API | URL | Historical support | Result |
|-----|-----|--------------------|--------|
| TWSE old API | `www.twse.com.tw/exchangeReport/STOCK_DAY_ALL?date=YYYYMMDD` | Claimed | Returns HTML (not JSON) — does not work |
| TWSE OpenAPI v1 | `openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL` | No date param | Returns most recent day only (2026-11-04 as of this date) |
| TPEx OpenAPI v1 | `tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes?d=RRRMMDD` | Claimed | Ignores date param — returns most recent day only |

**Conclusion:** Neither TWSE nor TPEx public APIs support historical all-stocks queries. The gap days 2026-10-29 through 2026-11-03 cannot be recovered without a paid historical data source (FinMind, TEJ, etc.).

---

## 5. Impact on Hybrid Forward Shadow

| Aspect | Impact |
|--------|--------|
| Shadow run for 2026-10-29 to 2026-11-03 | Cannot generate PROSPECTIVE records — data unavailable |
| Shadow run for 2026-11-04 | ✅ Runs — 21 decisions inserted (`RETROSPECTIVE_RECONSTRUCTION`) |
| Shadow run for 2026-11-05 | Available after today's market close (~15:00 Taiwan) + backfill |
| PROSPECTIVE records | Will begin from 2026-11-05 (RULE_FREEZE_DATE) once data is available |

The 5 missing days (10-29 to 11-03) are tagged `RETROSPECTIVE_RECONSTRUCTION` if recovered later via a paid source. This does not affect the validity of PROSPECTIVE records from 11-05 onward.

---

## 6. Resolution

1. **Immediate fix:** `backfill_daily_prices.py --execute` → added 6,957 rows for 2026-11-04 ✓
2. **Shadow runner unblocked:** last_data_date=2026-11-04, gap=1 day < 7-day tolerance ✓
3. **Long-term fix:** Configure local cron (see `docs/hybrid_local_cron_validation.md`)
