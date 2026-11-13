# Session 71H — Execution Contract

**Date**: 2026-11-11 21:51 CST  
**Authorization**: STRICT_READ_ONLY / IMPLEMENTATION_PLANNING_ONLY  
**Source**: Re-confirmed from actual code (not inherited from S71G)

---

## 1. Script Identity (Re-verified)

| Script | SHA-256 | Status |
|---|---|---|
| `hybrid_shadow_cron.py` | `46209171e00eb46429d0e36d02c106b87cf3684b13803ccdf53369042ba060d4` | UNCHANGED |
| `backfill_daily_prices.py` | `4eb6eacf6c65df52aae037731e66e4573a8ae929af807c0fbd7c1adcac4c5afb` | UNCHANGED (RC-2) |
| `backfill_daily_prices.py.bak-PRE-RC2-20261111` | (backup) | Pre-RC2 preserved |

---

## 2. Full Execution Call Graph

```
Trigger Source
    │
    ├─── [A] cron (0 16 * * 1-5)
    │         stdout/stderr >> logs/hybrid_cron.log 2>&1
    │
    ├─── [B] launchd StartCalendarInterval (designed, not deployed)
    │         StandardOutPath → logs/hybrid_cron.log (TRUNCATES)
    │
    └─── [C] Manual: python3 scripts/hybrid_shadow_cron.py --execute
              stdout to terminal (isatty=True → trigger_source="manual")

    ↓
hybrid_shadow_cron.py _cli()   [line 628]
    │
    ├─ --status → print_status(), sys.exit(0)
    ├─ --check-missed → _print_missed_runs(), sys.exit(0)
    └─ default → run_cron_pipeline(execute=True)   [line 668]

run_cron_pipeline()   [line 281]
    │
    ├─ Stage 1: FileLock   [line 315–320]
    │   └─ FileLock(data/.cron.lock).acquire()
    │       ├─ fcntl.flock(LOCK_EX|LOCK_NB)
    │       ├─ Writes PID to lock file
    │       └─ FAIL → result["status"]="BLOCKED_LOCK", return (exit 0)
    │
    ├─ Stage 2: Calendar Check   [line 326]
    │   └─ CALENDAR.is_trading_day(date.today())
    │       └─ FAIL → "SKIPPED_NON_TRADING_DAY", save_state, return (exit 0)
    │
    ├─ Stage 3: Data Readiness   [line 337]
    │   └─ _is_data_ready() → Taiwan time >= 15:30 CST
    │       ├─ FAIL + dry-run → "DATA_NOT_READY", save_state, return
    │       └─ FAIL + execute → logs WARNING, continues (QG-5 blocks wrong-date writes)
    │
    ├─ Stage 4: Backfill Subprocess   [line 352]
    │   └─ subprocess.run(backfill_daily_prices.py --execute)   [line 239–244]
    │       │   WorkingDirectory: stock_platform root
    │       │   PYTHON: sys.executable (same interpreter as wrapper)
    │       │
    │       └─ run_backfill(start, end, execute=True)   [backfill:422]
    │           ├─ _verify_sqlite(DB_PATH)   [line 315]  ← SQLite magic bytes check, not Neon
    │           ├─ _find_missing_dates(conn, start, end)   [line 332]  ← 0050 coverage, threshold=5000
    │           └─ for each missing_date:
    │               ├─ fetch_twse_historical(d)   [line 162]  ← HTTP call to TWSE API
    │               ├─ fetch_tpex_historical(d)   [line 251]  ← HTTP call to TPEx API
    │               ├─ run_quality_gate(twse_df, d, "TWSE")   [line 504]
    │               │   └─ QG-1: OHLC consistency
    │               │   └─ QG-2: Price bounds (0.1–20000)
    │               │   └─ QG-3: Volume non-negative
    │               │   └─ QG-4: No intra-batch duplicates
    │               │   └─ QG-5: Date consistency (api_date == target_d) ← KEY GUARD
    │               │   └─ QG-6: Coverage threshold (TWSE≥300, TPEx≥50)
    │               │   └─ QG-7: Benchmark 0050 presence (TWSE only)
    │               ├─ run_quality_gate(tpex_df, d, "TPEx")   [line 505]
    │               ├─ if NOT qg_ok → skip date, append to errors[]
    │               ├─ if execute AND qg_ok:
    │               │   ├─ _write_df_to_sqlite(conn, twse_df)   [line 387]
    │               │   │   └─ INSERT OR IGNORE INTO daily_prices (stock_id, date, ...)
    │               │   ├─ _write_df_to_sqlite(conn, tpex_df)
    │               │   └─ conn.commit()   [line 546]  ← per-date commit
    │               └─ [NO FileLock in backfill — only wrapper has lock]
    │
    │   FAIL (exit_code != 0) → "BACKFILL_FAILED", alert, save_state, return (exit 1)
    │   dry-run complete → "DRY_RUN_OK", return (exit 0)
    │
    ├─ Stage 4b: Freshness Gate Loop   [line 376]
    │   └─ for _retry in range(RETRY_MAX+1):  [RETRY_MAX=3, interval=30min]
    │       └─ check_market_freshness(sqlite_conn, today)
    │           ├─ FULL_MARKET_FRESH → break, proceed to Stage 5
    │           ├─ PROVIDER_NOT_READY / PARTIAL / BENCHMARK_ONLY:
    │           │   └─ if retries < MAX: sleep(1800s), re-run backfill, retry
    │           └─ exhausted OR STALE/UNKNOWN:
    │               └─ "BLOCKED_STALE_DATA" or "BLOCKED_PARTIAL_MARKET", save_state, return (exit 0)
    │
    ├─ Stage 5: Backup   [line 446]
    │   └─ create_backup(DB_PATH, today) → data/backups/platform_<date>_<ts>.db.bak
    │       └─ FAIL → warning, continues (non-fatal)
    │
    ├─ Stage 6: Shadow Runner Subprocess   [line 455]
    │   └─ subprocess.run(run_hybrid_forward_shadow.py)
    │       └─ run_shadow_pipeline(trade_date=today)
    │           ├─ new_run_id() → generates unique run_id (UUID-like)
    │           ├─ _is_data_fresh(last_data_date, today, tolerance=7 days)
    │           ├─ for each signal: generate decision
    │           │   └─ INSERT INTO hybrid_forward_decision
    │           │       ON CONFLICT(stock_id, trade_date, rule_version) → CONFLICT recorded
    │           │       [NO FileLock; NO same-day block; CONFLICT ≠ FAIL]
    │           └─ upsert_run_log(conn, log)
    │               └─ INSERT INTO hybrid_forward_run_log ON CONFLICT(run_id) DO UPDATE
    │               [NO unique constraint on trade_date → multiple rows per day possible]
    │
    └─ Stage 7: State Save + Lock Release   [line 473–476, finally:]
        ├─ lock.release()  ← ALWAYS executes (finally block)
        └─ _save_state(result) → data/.cron_state.json
```

---

## 3. Stage Contract Table

| Stage | File:Line | Precondition | Side Effect | Failure Behavior |
|---|---|---|---|---|
| FileLock acquire | `hybrid_shadow_cron.py:315` | Lock file accessible | Writes PID to lock file | BLOCKED_LOCK → exit 0 |
| Calendar check | `hybrid_shadow_cron.py:326` | — | None | SKIPPED_NON_TRADING_DAY → exit 0 |
| Data readiness | `hybrid_shadow_cron.py:337` | — | None | DATA_NOT_READY → exit 0 (dry-run only) |
| Backfill subprocess | `hybrid_shadow_cron.py:352` | Lock held | TWSE/TPEx HTTP call; SQLite write (if QG pass) | BACKFILL_FAILED → exit 1 |
| Quality Gate (per date) | `backfill_daily_prices.py:504` | Fetch succeeded | None (read-only) | Skip date; error appended |
| SQLite write | `backfill_daily_prices.py:534–546` | QG pass | `INSERT OR IGNORE` + `commit()` | Per-date; partial commit preserved |
| Freshness gate | `hybrid_shadow_cron.py:376` | Backfill succeeded | SQLite read (0050 count) | BLOCKED_STALE_DATA → exit 0 (retries) |
| Backup | `hybrid_shadow_cron.py:446` | Freshness gate pass | File copy to backups/ | Non-fatal warning |
| Shadow runner | `hybrid_shadow_cron.py:455` | Backup done | SQLite write (decisions) | SHADOW_FAILED → exit 1 |
| Lock release | `hybrid_shadow_cron.py:473` | always (finally) | Lock file released | Cannot fail silently |
| State save | `hybrid_shadow_cron.py:476` | always (finally) | Writes .cron_state.json | File write error non-fatal |

---

## 4. `--execute` Bypass Analysis

| Entry Point | Has FileLock? | Has QG? | Can bypass wrapper? |
|---|---|---|---|
| `hybrid_shadow_cron.py --execute` (normal) | YES | YES (via subprocess) | No |
| `backfill_daily_prices.py --execute` (direct) | **NO** | YES (internal) | **YES — bypasses wrapper lock** |
| `run_hybrid_forward_shadow.py` (direct) | NO | YES (stale data check) | YES — no wrapper involvement |
| `sync_to_neon.py` | NO | NO | YES — writes Neon `daily_prices` (manual only) |

**Critical finding**: `backfill_daily_prices.py --execute` can be run directly, bypassing the FileLock in the wrapper. The backfill has its own internal QG (QG-1~QG-7) but no process lock.

---

## 5. Additional Entry Points Found

| Script | Purpose | Writes SQLite? | Writes Neon? | In Cron? |
|---|---|---|---|---|
| `sync_to_neon.py` | Sync local → Neon | NO | YES (daily_prices) | NO — manual only |
| `run_daily.py` | (not read this session) | UNKNOWN | UNKNOWN | UNKNOWN |
| `run_overnight.py` | (not read this session) | UNKNOWN | UNKNOWN | UNKNOWN |
| `import_history.py` | (not read this session) | UNKNOWN | UNKNOWN | UNKNOWN |

`sync_to_neon.py` is a separate manual script that writes `daily_prices` to Neon. It is **not** part of the cron pipeline and does not use the FileLock. This is a known legitimate use case (manual sync after backfill).

---

## 6. Shadow Runner Same-Day Analysis

`hybrid_forward_run_log` schema:
```sql
run_id TEXT NOT NULL UNIQUE     ← per-invocation UUID
trade_date TEXT NOT NULL         ← NO UNIQUE constraint
```

Consequence: If shadow runner runs twice on the same `trade_date`:
1. First run: inserts decisions with `UNIQUE(stock_id, trade_date, rule_version)` — succeeds
2. Second run: same decisions conflict → `CONFLICT` status recorded; still writes new `run_id` to run_log
3. No hard BLOCK at the shadow runner level for same-day re-run

---

## 7. Contract Findings vs S71G

| Finding | S71G | S71H Re-verification | Status |
|---|---|---|---|
| Backfill has no FileLock | Identified | CONFIRMED: no lock in backfill | `CONTRACT_VERIFIED` |
| Two-stage QG | Identified | CONFIRMED: QG-1~7 + freshness gate | `CONTRACT_VERIFIED` |
| Shadow runner has own run log | Noted | CONFIRMED: upsert_run_log, run_id UNIQUE | `CONTRACT_VERIFIED` |
| Same-day run guard missing | Identified | CONFIRMED: no same-day check at any stage | `CONTRACT_VERIFIED` |
| `data_ready` = time ≥ 15:30 | Clarified | CONFIRMED: `_is_data_ready()` line 337 | `CONTRACT_VERIFIED` |
| `sync_to_neon.py` as Neon write path | Not identified in S71G | NEW FINDING: writes Neon daily_prices | `CONTRACT_CLARIFIED` |
| Shadow decision dedup | Partial note | CONFIRMED: UNIQUE(stock, date, rule_version); CONFLICT recorded but not blocking | `CONTRACT_VERIFIED` |
| launchd log truncation | Noted | `PLATFORM_BEHAVIOR_UNVERIFIED` for launchd; cron appends | `CONTRACT_PARTIAL` |

**Overall**: `CONTRACT_VERIFIED` with one new finding (`sync_to_neon.py`).

---

## 8. Verdict

| Item | Status |
|---|---|
| **Execution contract** | `CONTRACT_VERIFIED` |
| Backfill lock coverage | `MISSING` |
| Same-day guard | `MISSING` |
| Validity window | `MISSING` |
| Shadow runner dedup | `PARTIAL` (CONFLICT ≠ BLOCK) |
| SQLite write isolation | `VERIFIED` (uses DB_PATH, not DATABASE_URL) |
| New Neon write path | `sync_to_neon.py` — MANUAL ONLY, not in cron pipeline |
