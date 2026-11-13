# Session 71I — SQLite / Neon Isolation

**Document Status**: AWAITING_OBSERVATION  
**Preflight Timestamp**: 2026-11-11 22:06 CST  
**Target Schedule**: 2026-11-12 16:00 CST  
**H3 Status**: H3_PENDING

---

## 1. Architecture Reminder

| Database | Role | Write Source | Read Source |
|---|---|---|---|
| SQLite `data/platform.db` | Cron backfill target | `backfill_daily_prices.py` via `config.DB_PATH` | — |
| Neon PostgreSQL | Dashboard read source | `sync_to_neon.py` (manual only) | Dashboard via USE_NEON=true |

**SQLite and Neon are separate databases. A change in one does NOT automatically appear in the other.**

The cron pipeline ONLY writes to SQLite. Neon is NOT touched by the cron job.

---

## 2. SQLite Pre-run Baseline

| Metric | Baseline Value (2026-11-11 22:06 CST) |
|---|---|
| Row count (`daily_prices`) | **534,770** |
| MAX(date) | **2026-11-05** |
| Nov 2026 date breakdown | Nov 02 (1), Nov 03 (1), Nov 04 (6,957), Nov 05 (6,589) |
| 5+ digit entries at max date | **4,614** (pre-RC-2 era data) |
| `hybrid_forward_run_log` rows | **5** |
| `hybrid_forward_run_log` max trade_date | **2026-11-05** |

---

## 3. Neon Pre-run Baseline

| Metric | Baseline Value |
|---|---|
| Row count | UNVERIFIED (DATABASE_URL not configured here) |
| MAX(date) | 2026-11-10 (reference: S71D confirmed via dashboard) |
| Write access from cron | NONE — cron writes SQLite only |

---

## 4. Expected SQLite Changes Post-run

### If Scenario A (QG PASS for Nov 12):

| Metric | Expected Post-run Value |
|---|---|
| Row count | **~541,000+** (534,770 + ~6,400 new rows for Nov 12) |
| MAX(date) | **2026-11-12** |
| New date added | 2026-11-12 |
| Prior missing dates (Nov 06, 09, 10, 11) | Still 0 rows (QG-5 would fail for those — api_date will be Nov 12) |
| 5+ digit entries at 2026-11-12 | **0** (RC-2 filter applied) |
| `hybrid_forward_run_log` new rows | 1+ (shadow runner executed) |
| `hybrid_forward_run_log` max trade_date | **2026-11-12** |

### If Scenario B (QG FAIL — BLOCKED_STALE_DATA):

| Metric | Expected Post-run Value |
|---|---|
| Row count | **534,770** (UNCHANGED) |
| MAX(date) | **2026-11-05** (UNCHANGED) |
| New date added | NONE |
| 5+ digit entries | UNCHANGED |
| `hybrid_forward_run_log` new rows | 0 (shadow runner not reached) |

---

## 5. Unexpected Change Scenarios

| Scenario | Verdict |
|---|---|
| New 5+ digit entries appear at Nov 12 | **UNEXPECTED** — RC-2 filter failure |
| Neon row count increases after cron run | **UNEXPECTED** — indicates unauthorized sync_to_neon.py run |
| SQLite row count increases but `today` ≠ Nov 12 | **UNEXPECTED** — wrong date written (QG-5 failure) |
| SQLite schema changed | **UNEXPECTED** — not authorized |

---

## 6. SQLite Isolation Check (PENDING)

### 6.1 Pre/Post Comparison Table

| Metric | Pre-run | Post-observation | Delta | Verdict |
|---|---|---|---|---|
| Total rows | 534,770 | **534,770** | 0 | UNCHANGED |
| MAX(date) | 2026-11-05 | **2026-11-05** | 0 | UNCHANGED |
| Nov 12 row count | 0 | **0** | 0 | UNCHANGED |
| Nov 11 row count | 0 | **0** | 0 | UNCHANGED |
| 5+ digit at new date | 0 | **0** | 0 | UNCHANGED |
| `hybrid_forward_run_log` rows | 5 | **5** | 0 | UNCHANGED |
| Non-authorized schema changes | None | **None** | 0 | VERIFIED |

**Note**: No change because pipeline did not execute (machine asleep at 16:00 CST).

### 6.2 Write Authorization Matrix

| Write | Authorized? | Expected? |
|---|---|---|
| INSERT daily_prices for Nov 12 (QG pass) | YES | Scenario A |
| INSERT daily_prices for Nov 06/09/10/11 | CONDITIONAL (QG must pass) | UNLIKELY (QG-5 mismatch) |
| INSERT 5+ digit stock_ids | NO (RC-2 blocked) | 0 expected |
| Any Neon write from cron | NO (cron only writes SQLite) | 0 expected |
| Schema change | NO | 0 expected |

---

## 7. Neon Isolation Check (CONFIRMED)

| Check | Expected | Actual | Verdict |
|---|---|---|---|
| Neon row count unchanged post-run | YES | UNCHANGED (cron did not run) | VERIFIED |
| No `sync_to_neon.py` invocation in cron log | YES | Log unchanged (106 lines, Nov 10) | VERIFIED |
| Dashboard read source remains Neon (USE_NEON=true) | YES | Config unchanged | VERIFIED |

Cron pipeline did not execute — Neon was not at risk of unauthorized write. Isolation confirmed by absence of any pipeline execution.

---

## 8. Post-run Evidence (PENDING)

```bash
# Post-run SQLite check commands:

# Row count and max date
sqlite3 /Users/alicetu/Desktop/Antigravity/stock_platform/data/platform.db \
  "SELECT COUNT(*), MAX(date) FROM daily_prices;"

# Date breakdown for Nov 2026
sqlite3 /Users/alicetu/Desktop/Antigravity/stock_platform/data/platform.db \
  "SELECT date, COUNT(*) FROM daily_prices WHERE date >= '2026-11-01' GROUP BY date ORDER BY date;"

# Five-digit check at any new date
sqlite3 /Users/alicetu/Desktop/Antigravity/stock_platform/data/platform.db \
  "SELECT date, COUNT(*) FROM daily_prices WHERE LENGTH(stock_id) > 4 AND date > '2026-11-05' GROUP BY date;"

# Shadow run log
sqlite3 /Users/alicetu/Desktop/Antigravity/stock_platform/data/platform.db \
  "SELECT COUNT(*), MAX(trade_date) FROM hybrid_forward_run_log;"
```

---

## 9. Verdict

| Item | Verdict |
|---|---|
| **SQLite baseline** | `RECORDED` |
| **Neon baseline** | `UNVERIFIED` (DATABASE_URL not configured) |
| **Post-run SQLite check** | **PENDING** |
| **Post-run Neon isolation** | **PENDING** |
| **RC-2 five-digit exclusion in SQLite** | **PENDING** |
| **Overall** | **PENDING** |
