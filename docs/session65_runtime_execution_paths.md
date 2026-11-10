# Session 65 — Runtime Execution Paths & Call Graph

## Status: RUNTIME_PATH_CONFIRMED

---

## 1. Full Call Graph: Cron → DB Write

```
SCH-01: crontab (0 16 * * 1-5)
  └─ /path/to/python3 hybrid_shadow_cron.py --execute
       └─ run_cron_pipeline(execute=True)        [line 281]
            └─ _run_backfill(execute=True)        [line 352]
                 └─ subprocess.run([PYTHON,
                       "backfill_daily_prices.py",
                       "--execute"])              [line 239-244]
                          └─ main() → run_backfill(execute=True)
                               ├─ sqlite3.connect(DB_PATH)   ← opens data/platform.db
                               ├─ _find_missing_dates()      ← read-only
                               └─ for target_d in missing_dates:
                                    ├─ fetch_twse_historical(d)  ← HTTP: TWSE API
                                    │    └─ _parse_twse_openapi_list()
                                    │         └─ _is_excluded(name, sid)   ← RC-2 TARGET
                                    ├─ fetch_tpex_historical(d)  ← HTTP: TPEx API
                                    │    └─ _parse_tpex_response()
                                    │         └─ _is_excluded(name, sid)   ← RC-2 TARGET
                                    ├─ run_quality_gate(twse_df)  ← QG
                                    └─ if QG passes:
                                         └─ _write_df_to_sqlite(conn, df) ← DB WRITE
                                              └─ INSERT OR IGNORE INTO daily_prices
```

---

## 2. `_is_excluded()` Position in Call Graph

`_is_excluded()` is called DURING data parsing, BEFORE quality gate:

```
Step 1: fetch_twse_historical() → HTTP call → returns raw data
Step 2: _parse_twse_openapi_list() → applies _is_excluded() per row  ← RC-2 HERE
Step 3: run_quality_gate(filtered_df)                                 ← QG on filtered data
Step 4: _write_df_to_sqlite(conn, filtered_df)                        ← DB write if QG passes
```

**RC-2 effect position**: Between Step 1 and Step 3 — it changes what data is in `filtered_df` before QG runs.

---

## 3. Path Classification

| Path | Entry | Trigger | `--execute` | DB Write | Provider HTTP | RC-2 Reached | Classification |
|---|---|---|---|---|---|---|---|
| SCH-01 → backfill | Cron (0 16 * * 1-5) | Time-based | YES | YES (if QG passes) | YES (always) | YES | RUNTIME_CONFIRMED |
| EP-01: CLI dry-run | manual CLI (no --execute) | Manual | NO | NO | YES | YES | STATIC_REACHABLE |
| EP-01: CLI execute | manual CLI (--execute) | Manual | YES | YES (if QG passes) | YES | YES | STATIC_REACHABLE |
| GitHub Actions daily | `run_daily.py` | Daily cron | N/A | (not backfill) | NO | NO | NOT_REACHABLE |
| GitHub Actions overnight | `run_overnight.py` | Nightly cron | N/A | (not backfill) | NO | NO | NOT_REACHABLE |
| GitHub Actions hybrid_forward_shadow | manual dispatch | Manual | N/A | (not backfill) | NO | NO | NOT_REACHABLE |
| Import only (test suite) | `pytest` | Test | NO | NO | NO | NO (import only) | STATIC_REACHABLE |

---

## 4. Provider HTTP Calls — What is Called

| Provider | Function | URL Pattern | Evidence |
|---|---|---|---|
| TWSE OpenAPI | `fetch_twse_historical()` | `openapi.twse.com.tw/...` or `www.twse.com.tw/...` | RUNTIME_CONFIRMED (log 2026-11-09) |
| TPEx | `fetch_tpex_historical()` | `www.tpex.org.tw/...` | STATIC_REACHABLE |

**Runtime log confirmation**: `[backfill] Running: .../backfill_daily_prices.py --execute` → then QG result with TWSE api_date — TWSE API was called.

---

## 5. DB Write Path — `data/platform.db`

| DB Path | Source | Write Function | Guard |
|---|---|---|---|
| `/Users/alicetu/Desktop/Antigravity/stock_platform/data/platform.db` | `config.DB_PATH` | `_write_df_to_sqlite()` → `INSERT OR IGNORE INTO daily_prices` | `execute=True` AND QG passes |

Safety check in `_verify_sqlite()` (line 315):
- Verifies file is a SQLite file (not PostgreSQL/Neon)
- Verifies absolute path
- Rejects paths containing "neon" or "postgresql"

**Neon is NOT reachable from this code path.** Only local `data/platform.db` is written.

---

## 6. QG Gate — When Does Write Happen?

The QG must pass for a write to occur. From the log:

| Date | QG Result | DB Write | Reason |
|---|---|---|---|
| 2026-11-09 | FAILED × 3 retries | NO | `api_date=2026-11-06 != target=2026-11-09` |
| 2026-11-10 | FAILED × 3 retries | NO | `api_date=2026-11-09 != target=2026-11-10` |

**Current state**: QG has been failing since 2026-11-05 (last successful insert). DB writes are BLOCKED by QG date mismatch.

**RC-2 and QG interaction**:
- `_is_excluded()` runs BEFORE QG
- Excluding warrants reduces `len(twse_df)` passed to QG
- QG uses `_MIN_COVERED_STOCKS = 5_000` threshold
- If warrants contribute to meeting the 5000-row threshold, excluding them could cause QG coverage failure
- However: current QG failures are date-mismatch based (`api_date != target`), not coverage-based
- **This is an edge-case risk that exists only when TWSE API returns exactly the right date**: if QG-5 date check passes but coverage check now fails due to warrant exclusion

---

## 7. Script Path Confirmation (Critical for RC-2)

The crontab calls:
```
/Users/alicetu/Desktop/Antigravity/stock_platform/scripts/hybrid_shadow_cron.py
```

Inside `hybrid_shadow_cron.py`:
```python
SCRIPTS_DIR = Path(__file__).parent           # = /Users/.../stock_platform/scripts/
PYTHON = sys.executable                        # = /Library/.../python3 (same as crontab)
cmd = [PYTHON, str(SCRIPTS_DIR / "backfill_daily_prices.py")]  # → production script
```

Resolved path:
```
/Users/alicetu/Desktop/Antigravity/stock_platform/scripts/backfill_daily_prices.py
```

This is IDENTICAL to the RC-2 target file (`shasum -a 256` = `4bb88de2...`).

**Conclusion**: RC-2 deployment to `scripts/backfill_daily_prices.py` WILL be picked up by the next cron run.

---

## 8. Key Conclusion

> After RC-2 is deployed, the next scheduled 16:00 cron run WILL:
> 1. Make Provider HTTP calls to TWSE/TPEx (this was ALREADY happening before RC-2)
> 2. Use the new `_is_excluded()` logic (warrants/5-digit ETFs excluded from DataFrame)
> 3. Run QG on the reduced DataFrame (potential edge-case risk if warrants were needed for coverage)
> 4. Write to `data/platform.db` IF AND ONLY IF QG passes (same as before)
>
> RC-2 does NOT create new authorization for cron execution — the cron was already running.
> RC-2 changes WHAT is fetched and inserted, not WHETHER the cron runs.
