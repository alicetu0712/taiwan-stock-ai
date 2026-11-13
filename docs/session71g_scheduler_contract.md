# Session 71G — Scheduler Contract

**Date**: 2026-11-11  
**Authorization**: STRICT_READ_ONLY / MIGRATION_DESIGN_ONLY  
**Source**: Code-confirmed from actual files (not prior documentation)

---

## 1. Script Chain Identity

| Script | SHA-256 | Role |
|---|---|---|
| `hybrid_shadow_cron.py` | `46209171e00eb46429d0e36d02c106b87cf3684b13803ccdf53369042ba060d4` | Orchestrator wrapper |
| `backfill_daily_prices.py` | `4eb6eacf6c65df52aae037731e66e4573a8ae929af807c0fbd7c1adcac4c5afb` | Data fetcher + writer (RC-2 patched) |

---

## 2. Actual Execution Chain (Code-Confirmed)

Confirmed from `hybrid_shadow_cron.py:281–478` (`run_cron_pipeline()`).

```
cron / launchd
    ↓
hybrid_shadow_cron.py --execute
    ↓
Step 1: FileLock acquire (data/.cron.lock, fcntl.flock LOCK_EX|LOCK_NB)
    ↓ BLOCKED_LOCK if fails
Step 2: TaiwanTradingCalendar.is_trading_day(today)
    ↓ SKIPPED_NON_TRADING_DAY if False
Step 3: _is_data_ready() → Taiwan time >= 15:30?
    ↓ DATA_NOT_READY if False (dry-run only; execute mode continues with warning)
Step 4: subprocess.run(backfill_daily_prices.py --execute)
    ├─ _verify_sqlite(DB_PATH)  [safety: confirms SQLite magic bytes, not Neon URL]
    ├─ _find_missing_dates(conn, start, end)  [0050-based coverage check, threshold=5000]
    ├─ For each missing_date:
    │   ├─ fetch_twse_historical(d) → (DataFrame, api_date)  [calls TWSE API]
    │   ├─ fetch_tpex_historical(d) → (DataFrame, api_date)  [calls TPEx API]
    │   ├─ run_quality_gate(twse_df, d, "TWSE")  [QG-1 to QG-7]
    │   ├─ run_quality_gate(tpex_df, d, "TPEx")  [QG-1 to QG-6]
    │   ├─ If QG PASS: _write_df_to_sqlite() → INSERT OR IGNORE → conn.commit()
    │   └─ If QG FAIL: skip date (not written), append to errors[]
    └─ exit 0 (always, unless crash)
    ↓ BACKFILL_FAILED if exit_code != 0
Step 4b: Freshness verification loop (RETRY_MAX=3, RETRY_INTERVAL=30 min)
    ├─ check_market_freshness(sqlite_conn, today)  [reads SQLite: 0050 date + non-0050 count]
    ├─ FULL_MARKET_FRESH → break, proceed to Step 5
    ├─ PROVIDER_NOT_READY / PARTIAL / BENCHMARK_ONLY → sleep(30m), re-run backfill, retry
    └─ STALE / UNKNOWN or retries exhausted → BLOCKED_STALE_DATA / BLOCKED_PARTIAL_MARKET
Step 5: create_backup(DB_PATH, today)  [copies SQLite to data/backups/]
Step 6: subprocess.run(run_hybrid_forward_shadow.py)  [shadow decisions]
    ↓ SHADOW_FAILED if exit_code != 0
Step 7: lock.release() + _save_state(result) → data/.cron_state.json
    ↓ SUCCESS
```

---

## 3. Stage-by-Stage Contract

### Stage 1: FileLock
| Item | Value |
|---|---|
| Entry point | `FileLock(LOCK_FILE).acquire()` at line 316 |
| File | `data/.cron.lock` |
| Mechanism | `fcntl.flock(LOCK_EX | LOCK_NB)` |
| Input | Lock file path |
| Output | True (acquired) or False (blocked) |
| Side effects | Writes PID to lock file on success |
| Failure | Returns False → `BLOCKED_LOCK` → exit 0 |
| Auth boundary | No external calls |

### Stage 2: Calendar Check
| Item | Value |
|---|---|
| Entry point | `TaiwanTradingCalendar().is_trading_day(today)` at line 326 |
| Input | `date.today()` |
| Output | bool |
| Side effects | None |
| Failure | Exception → unhandled (crashes to Step 7) |
| Auth boundary | No external calls; uses local holiday calendar |

### Stage 3: Data Readiness
| Item | Value |
|---|---|
| Entry point | `_is_data_ready()` at line 337 |
| Input | Current Taiwan time |
| Output | True if >= 15:30 CST |
| Side effects | None |
| Failure behavior | Returns False → DATA_NOT_READY (dry-run) or warning (execute) |
| Auth boundary | No external calls |

### Stage 4: Backfill Subprocess
| Item | Value |
|---|---|
| Entry point | `_run_backfill(execute=True)` at line 352 |
| Input | `--execute` flag |
| Output | `{exit_code, stdout, stderr}` |
| Calls TWSE API | YES — `TWSE_LATEST_URL` + `TWSE_HIST_URL` |
| Calls TPEx API | YES — `TPEX_HIST_URL` |
| Writes SQLite | YES (if QG passes per date) |
| Writes Neon | **NO** (uses `config.DB_PATH`, not `DATABASE_URL`) |
| Has own FileLock | **NO** — only wrapper has lock |
| Idempotency | `INSERT OR IGNORE` (per `stock_id, date` unique constraint) |
| QG | Per-date: QG-1 to QG-7 (date consistency = QG-5 is key) |
| Failure behavior | exit_code=0 even if all dates blocked (graceful); crash → exit!=0 |
| Auth boundary | Calls public TWSE/TPEx APIs (no credentials required) |

### Stage 4b: Freshness Gate
| Item | Value |
|---|---|
| Entry point | `check_market_freshness(db_conn, today)` at line ~377 |
| Input | SQLite connection, today's date |
| Output | `FreshnessReport` with `FreshnessStatus` |
| Mechanism | Reads `MAX(date)` for 0050; counts non-0050 stocks on today |
| Threshold | `MIN_COVERED_STOCKS = 5000` |
| Retryable | PROVIDER_NOT_READY, PARTIAL_MARKET_UPDATE, BENCHMARK_ONLY_UPDATED |
| Non-retryable | STALE, UNKNOWN |
| Max wait | 3 retries × 30 min = 90 min |
| Side effects | Calls `_run_backfill()` again on each retry |
| Auth boundary | No external calls (reads local SQLite only) |

### Stage 5: Backup
| Item | Value |
|---|---|
| Entry point | `create_backup(DB_PATH, today)` at line 446 |
| Input | DB_PATH, today |
| Output | Backup path or None |
| Side effects | Copies SQLite to `data/backups/platform_<date>_<ts>.db.bak` |
| Failure behavior | Logs warning, continues to Step 6 (non-fatal) |
| Auth boundary | Local file system only |

### Stage 6: Shadow Runner
| Item | Value |
|---|---|
| Entry point | `_run_shadow()` at line 455 |
| Script | `run_hybrid_forward_shadow.py` |
| Writes SQLite | YES (forward shadow decisions) |
| Writes Neon | Unknown (not inspected this session) |
| Failure behavior | `SHADOW_FAILED` if exit_code != 0 |
| Auth boundary | Depends on shadow runner (not fully audited in S71G) |

### Stage 7: State Save
| Item | Value |
|---|---|
| Entry point | `_save_state(result)` in `finally:` at line 476 |
| Output file | `data/.cron_state.json` |
| Always executes | YES (finally block) |
| Auth boundary | Local file system only |

---

## 4. State File Explanation (Nov 10 State)

```json
{
  "steps": {
    "lock": "released",          ← Step 7 finally
    "calendar": "trading_day",   ← Step 2 passed
    "data_ready": true,          ← Step 3: time >= 15:30 CST (NOT data quality)
    "backfill": {
      "exit_code": 0,            ← Step 4: subprocess ran without crash
      "executed": true           ← execute=True was passed
    },
    "data_freshness": "PROVIDER_NOT_READY",  ← Step 4b: 0050 not at today's date
    "freshness_retry_attempt": 3             ← All 3 retries exhausted
  },
  "status": "BLOCKED_STALE_DATA"
}
```

**Interpretation**: Backfill ran and called the TWSE/TPEx API (exit_code=0 means no crash), but internal QG-5 blocked writing Nov 10 data (api_date=Nov 09 ≠ target=Nov 10). Post-backfill freshness check found 0050 still at Nov 05 → PROVIDER_NOT_READY. After 3 retries (90 min), still blocked.

---

## 5. Prior Documentation vs Actual Code

| Assumption | Prior Docs | Actual Code | Status |
|---|---|---|---|
| QG runs before backfill fetch | Implied | QG runs INSIDE backfill subprocess | `CONTRACT_VERIFIED` |
| Freshness gate runs after backfill | Implied | Confirmed at Step 4b | `CONTRACT_VERIFIED` |
| `data_ready` = data freshness | Assumed | Actually = time >= 15:30 CST | `CONTRACT_CLARIFIED` |
| Backfill has process lock | Assumed | **NO** — only wrapper has lock | `CONTRACT_MISMATCH` |
| State file date = last successful write | Implied | State reflects last run, any outcome | `CONTRACT_CLARIFIED` |
| Shadow runner always runs after backfill | Assumed | Only if freshness gate passes | `CONTRACT_VERIFIED` |

---

## 6. Configuration Contract

| Config Item | Source | Value | Used By |
|---|---|---|---|
| `DB_PATH` | `config.py:20` | `BASE_DIR/data/platform.db` | backfill, cron, shadow |
| `DATABASE_URL` | `config.py:50` | SQLite (local) or Neon (if USE_NEON=true) | Dashboard only |
| `LOCK_FILE` | `hybrid_shadow_cron.py:63` | `data/.cron.lock` | Cron wrapper |
| `STATE_FILE` | `hybrid_shadow_cron.py:66` | `data/.cron_state.json` | Cron wrapper |
| `RETRY_MAX` | `hybrid_shadow_cron.py:81` | 3 | Freshness retry |
| `RETRY_INTERVAL_MINUTES` | `hybrid_shadow_cron.py:82` | 30 | Freshness retry |
| `MIN_COVERED_STOCKS` | `full_market_freshness_gate.py:26` | 5000 | Freshness gate |
| `DATA_READY_HOUR` | `hybrid_shadow_cron.py:57` | 15 | Time readiness |
| `DATA_READY_MINUTE` | `hybrid_shadow_cron.py:58` | 30 | Time readiness |

---

## 7. Verdict

| Item | Status |
|---|---|
| Call chain confirmed from code | VERIFIED |
| Prior documentation accuracy | MOSTLY CORRECT — 2 contract clarifications |
| Critical finding | `CONTRACT_MISMATCH`: backfill has NO FileLock |
| RC-2 filter location | `backfill_daily_prices.py:93–100` (`_is_excluded()`) |
| SQLite isolation | CONFIRMED — backfill uses `DB_PATH` not `DATABASE_URL` |
