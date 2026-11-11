# Session 71D — SQLite Identity & Database Architecture Audit

**Date**: 2026-11-11  
**Check Time**: 2026-11-11 14:16–14:25 CST  
**Authorization**: AUTH-S71-BUNDLE-A (read-only acceptance phase)

---

## 1. Discovery Summary

The system uses **two separate data stores** for different purposes. This was not clearly distinguished in Sessions 71B/71C, leading to baseline verification errors.

---

## 2. Local SQLite — Backfill Target

| Property | Value | Evidence |
|---|---|---|
| Absolute Path | `/Users/alicetu/Desktop/Antigravity/stock_platform/data/platform.db` | `find` + read |
| SHA-256 | `6b77472df29c87ab333e1231dd93de41e23ab7f144a61a87c097e59da22d6ee2` | `shasum -a 256` |
| File Size | 86,388,736 bytes (82.4 MB) | `os.path.getsize()` |
| Tables | 28 (actual_positions, analysis_results, candidate_pool, daily_prices, ...) | `sqlite_master` |
| `daily_prices` row count | 534,770 | read-only query |
| `daily_prices` min_date | 2024-07-01 | read-only query |
| `daily_prices` max_date | 2026-11-05 | read-only query |
| `daily_prices[2465]` count | 563 | read-only query |
| `daily_prices[2465]` max | 2026-11-05 | read-only query |
| Distinct stock_id count | 15,046 | read-only query |
| Rows with `len(sid) > 4` | 111,710 (20.9%) | read-only query |
| Rows since 2026-11-06 | 0 | read-only query |

**Writer**: `scripts/backfill_daily_prices.py` (via cron only)  
**Reader (dashboard)**: NEVER — dashboard uses Neon  
**Reader (tests)**: Yes — test suite connects to local SQLite directly

### Other DB Files in `data/`

| File | Size | Contents |
|---|---|---|
| `platform_recover_backup_20261105_165923.db` | (not checked) | Recovery backup |
| `platform_recover_backup_20261105_170018.db` | (not checked) | Recovery backup |
| `research.db` | 0 bytes | Empty |
| `stock_research.db` | 0 bytes | Empty |
| `stock_research.db` (repo root) | 0 bytes | Empty |

**Conclusion**: Only `data/platform.db` is active. All other SQLite files are empty or backups.

---

## 3. Neon PostgreSQL — Dashboard Production Source

| Property | Value | Evidence |
|---|---|---|
| Connection | `postgresql://...@db-host.example.invalid/neondb` | config.py runtime |
| Activation | `.env: USE_NEON=true` | cat .env |
| `daily_prices` row count | 409,039 | read-only query |
| `daily_prices` min_date | 2024-07-01 | read-only query |
| `daily_prices` max_date | **2026-11-10** | read-only query |
| `daily_prices[2465]` count | 558 | read-only query |
| `daily_prices[2465]` max | **2026-11-10** | read-only query |
| `daily_prices[0050]` max | 2026-11-10 | read-only query |
| `daily_prices[2330]` max | 2026-11-10 | read-only query |
| Distinct stock_id count | 9,852 | read-only query |
| Rows with `len(sid) > 4` | Small (ETF series codes only) | read-only query sample |
| Rows since 2026-11-06 | 1,911 | read-only query |

**Writer**: GitHub Actions (separate pipeline — NOT local cron)  
**Reader**: Dashboard / all Streamlit pages via `get_session()`

---

## 4. Divergence Analysis

| Metric | Local SQLite | Neon | Explanation |
|---|---|---|---|
| Row count | 534,770 (MORE) | 409,039 (LESS) | SQLite includes pre-RC2 warrant IDs; Neon was written by GH Actions which may apply different filtering |
| Max date | 2026-11-05 (OLDER) | 2026-11-10 (NEWER) | Neon updated by GH Actions Nov 06–10; local cron blocked by QG since Nov 05 |
| Distinct stocks | 15,046 (MORE) | 9,852 (LESS) | SQLite contains all stocks including warrants/ETFs; Neon appears filtered |
| Warrant IDs | 111,710 rows | Near zero | RC-2 fix addresses future SQLite writes; Neon was filtered by GH Actions separately |

---

## 5. Prior Session Baseline Error

Sessions S71B and S71C repeatedly stated:

> "DB: 534,770 rows, max_date 2026-11-05"

as the production baseline. This was **incorrect** for the dashboard context:

- The query was run against **local SQLite** (`data/platform.db`)
- The dashboard reads from **Neon** (`max_date = 2026-11-10`)
- The "production" baseline for what users see is Neon, not local SQLite

The practical consequences:
- S71C visual screenshots showed 2026-11-10 dates → these were CORRECT (Neon data)
- S71B/C "baseline" showing 2026-11-05 → describes local SQLite only
- No data was fabricated or mocked; the fixture used real Neon data

---

## 6. Verdict

| Category | Verdict |
|---|---|
| Local SQLite Identity | `SQLITE_IDENTITY_VERIFIED` (path, hash, row count all confirmed) |
| Neon Identity | `NEON_IDENTITY_VERIFIED` (connected, queried, stats confirmed) |
| Dashboard DB source | `NEON_IS_PRODUCTION_SOURCE` |
| Cron write target | `LOCAL_SQLITE_IS_CRON_TARGET` |
| Prior baseline (S71B/C) | `BASELINE_DATABASE_MISMATCH` — SQLite stats used as "production" but app uses Neon |
| Overall | `SQLITE_IDENTITY_PARTIAL` — both databases verified, but architecture was misunderstood in prior sessions |
