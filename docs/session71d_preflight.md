# Session 71D — Preflight Verification

**Date**: 2026-11-11  
**Check Time**: 2026-11-11 14:16–14:20 CST  
**Authorization**: AUTH-S71-BUNDLE-A (read-only acceptance phase)  
**Execution Mode**: READ_ONLY_RUNTIME_AUDIT / DATA_PROVENANCE_VERIFICATION

---

## 1. Environment

| Item | Value | Status |
|---|---|---|
| System Time | 2026-11-11 14:16 CST (06:16 UTC) | CONFIRMED |
| Host / User | alicetu @ macOS (Darwin 25.3.0) | CONFIRMED |
| Repository Root | `/Users/alicetu/Desktop/Antigravity/stock_platform` | CONFIRMED |
| Git Branch | main | CONFIRMED |
| Git HEAD | d9a8a72 (commit message redacted) | CONFIRMED |
| Git Working Tree | 5 modified, 36 untracked (Bundle A unchanged, docs only) | CONFIRMED |
| Python | `/Library/Frameworks/Python.framework/Versions/3.13/bin/python3` | CONFIRMED |

---

## 2. RC-2 File Hash

| File | Expected SHA-256 | Actual SHA-256 | Status |
|---|---|---|---|
| `scripts/backfill_daily_prices.py` | `4eb6eacf6c65df52aae037731e66e4573a8ae929af807c0fbd7c1adcac4c5afb` | `4eb6eacf6c65df52aae037731e66e4573a8ae929af807c0fbd7c1adcac4c5afb` | ✓ RC2_HASH_VERIFIED |

---

## 3. Cron Configuration

| Item | Value | Status |
|---|---|---|
| Crontab Entry | `0 16 * * 1-5  /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 /Users/alicetu/Desktop/Antigravity/stock_platform/scripts/hybrid_shadow_cron.py --execute >> /Users/alicetu/Desktop/Antigravity/stock_platform/logs/hybrid_cron.log 2>&1` | VERIFIED (live crontab, not documentation) |
| Schedule | `0 16 * * 1-5` | 16:00 Asia/Taipei weekdays |
| Last Run | 2026-11-10T09:37:32Z (Nov 10 17:37 CST) | Pre-RC2 deployment |
| Nov 11 Entries | 0 | H3_PENDING |
| Time Until Next | ~1h 40min (at time of check) | CRON_NOT_YET_DUE |

---

## 4. Database Identity — CRITICAL FINDING

**Two distinct databases exist. They serve different roles.**

| Property | Local SQLite | Neon PostgreSQL |
|---|---|---|
| Path / URL | `data/platform.db` | `postgresql://...@db-host.example.invalid/neondb` |
| Role | Backfill write target (cron only) | Dashboard read source (app always) |
| Activation | `USE_NEON=false` / no .env | `USE_NEON=true` (current .env) |
| `daily_prices` rows | 534,770 | 409,039 |
| `daily_prices` min_date | 2024-07-01 | 2024-07-01 |
| `daily_prices` max_date | **2026-11-05** | **2026-11-10** |
| `daily_prices[2465]` max | **2026-11-05** | **2026-11-10** |
| Distinct stock_id count | 15,046 | 9,852 |
| Rows with `len(sid) > 4` | 111,710 (20.9%) | Small number (ETF codes) |
| Local SHA-256 | `6b77472df29c87ab...` | N/A (remote) |
| Local file size | 86,388,736 bytes (82.4 MB) | N/A |

**Key implication**: S71B/C baseline "534,770 rows / max_date 2026-11-05" described LOCAL SQLite, NOT the actual dashboard data source. This is an error in prior session documentation.

---

## 5. Database Connection Routing

```
USE_NEON=true (in .env)
     ↓
config.py:50-54: DATABASE_URL = postgresql://...@neon.tech/...
     ↓
get_session() / get_engine() → Neon PostgreSQL
     ↓
Dashboard (all pages) reads from Neon
```

```
backfill_daily_prices.py
     ↓
from config import DB_PATH → data/platform.db
     ↓
sqlite3.connect(DB_PATH) → Local SQLite ONLY
(script header: "NEVER touches production Neon")
```

---

## 6. Session 71C Artifact Verification

| Item | Status | Note |
|---|---|---|
| `scratchpad/fixture_71c.py` | EXISTS (in session scratchpad) | `/private/tmp/claude-501/...scratchpad/fixture_71c.py` |
| Screenshots (5 files) | EXISTS | In `scratchpad/screenshots/` |
| `docs/session71c_*.md` (5 files) | EXISTS | All 5 deliverables present |
| Fixture DB connection | Neon (via `get_session()` → USE_NEON=true) | NOT local SQLite |

---

## 7. Preflight Gate Summary

| Check | Status |
|---|---|
| RC-2 hash | ✓ PASS |
| Cron installed | ✓ PASS |
| H3 Nov 11 cron | PENDING (14:20 CST, cron at 16:00) |
| Production code unchanged | ✓ PASS |
| DB identity clarified | ✓ TWO_DATABASES_IDENTIFIED |
| Data provenance clarified | NEON_IS_DASHBOARD_SOURCE |
| Authorization boundary | ✓ READ_ONLY_VERIFIED |
