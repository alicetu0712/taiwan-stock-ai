# Session 68 — Runtime Evidence Report

## Status: NATURAL_CRON_EXECUTION_PENDING

Session 68 Timestamp: 2026-11-11 01:07 CST
Execution Mode: READ_ONLY_PRODUCTION_AUDIT

---

## 1. Production Identity Verification (C1/C2)

| Item | Expected | Actual | Match | Source |
|---|---|---|---|---|
| File path | `scripts/backfill_daily_prices.py` | Same | ✓ | File system |
| SHA-256 | `4eb6eacf6c65df52aae037731e66e4573a8ae929af807c0fbd7c1adcac4c5afb` | `4eb6eacf6c65df52aae037731e66e4573a8ae929af807c0fbd7c1adcac4c5afb` | ✓ MATCH | `shasum -a 256` |
| Line 98 | `    if len(sid) > 4:` | `    if len(sid) > 4:` | ✓ MATCH | `sed -n '95,102p'` |
| Cron expression | `0 16 * * 1-5` | `0 16 * * 1-5` | ✓ MATCH | `crontab -l` |
| Cron Python | `/Library/Frameworks/Python.framework/Versions/3.13/bin/python3` | Same | ✓ | `crontab -l` |
| Cron script | `.../stock_platform/scripts/hybrid_shadow_cron.py --execute` | Same | ✓ | `crontab -l` |
| Cron log | `.../stock_platform/logs/hybrid_cron.log` | Same | ✓ | `crontab -l` |
| Git HEAD | `816ca2eaf40216838555f36a1b1c9f6aff5d6b47` | `M scripts/backfill_daily_prices.py` | ✓ EXPECTED | `git status` |
| Backup present | `scripts/backfill_daily_prices.py.bak-PRE-RC2-20261111` | Exists | ✓ | `stat` |

**Deployment Identity**: `RC2_DEPLOYMENT_IDENTITY_VERIFIED`

Working tree `M scripts/backfill_daily_prices.py` is expected — RC-2 was deployed as a working-tree modification. HEAD still has original code; the patched file is tracked in working tree.

---

## 2. Execution Chain Verification (E1/E2)

The chain:
```
Cron (0 16 * * 1-5)
  → hybrid_shadow_cron.py --execute
  → _run_backfill(execute=True)         [line 352]
  → backfill_daily_prices.py --execute  [line 239]
  → run_backfill(execute=True)
  → _is_excluded()                      [lines 125/214/273]
  → QG
  → _write_df_to_sqlite()               [line 387]
```

| Level | Evidence Available | Status |
|---|---|---|
| `CRON_TRIGGER_CONFIRMED` | Log entries `2026-11-10T08:00:39Z` show `Hybrid Shadow Cron — EXECUTE` | CONFIRMED (pre-RC2) |
| `BACKFILL_PROCESS_CONFIRMED` | Log: `[backfill] Running: .../backfill_daily_prices.py --execute` | CONFIRMED (pre-RC2) |
| `RC2_VERSION_AT_EXECUTION_CONFIRMED` | No post-RC2 run yet | PENDING |
| `RC2_BRANCH_EXECUTION_CONFIRMED` | No post-RC2 run yet | PENDING |
| `RC2_FILTER_EFFECT_CONFIRMED` | No post-RC2 run yet | PENDING |

**Note**: The chain structure is confirmed from pre-RC2 runs. Post-RC2 version adoption (`RC2_VERSION_AT_EXECUTION_CONFIRMED`) requires an actual post-RC2 execution.

---

## 3. Log Evidence — Existing Records

### Last Pre-RC2 Run (2026-11-10)

```
[2026-11-10T08:00:39Z] ============================================================
[2026-11-10T08:00:39Z] Hybrid Shadow Cron — EXECUTE
[2026-11-10T08:00:39Z] Taiwan time: 2026-11-10 16:00:39 CST
[2026-11-10T08:00:39Z] [cron] 2026-11-10 is a trading day ✓
[2026-11-10T08:00:39Z] [backfill] Running: .../backfill_daily_prices.py --execute
[2026-11-10T08:02:46Z] [backfill]   errors: 5
[2026-11-10T08:02:46Z]     • 2026-11-10: TWSE api_date=2026-11-09 != target — API returned wrong date
[2026-11-10T08:02:46Z]     • 2026-11-10: quality gate FAILED — not writing to DB
...
[2026-11-10T09:37:32Z] [cron] BLOCKED_STALE_DATA (after 3 retries)
```

This run used the **pre-RC2** version (original hash `4bb88de2...`).

### Nov 11 Log Status
- Zero entries after `2026-11-10T09:37:32Z`
- `hybrid_cron.log` last modified: `Nov 10 17:37:32 CST` (= `2026-11-10T09:37:32Z`)
- **No post-RC2 natural cron run has occurred**

---

## 4. Version-at-Execution Assessment (E3)

| Evidence Type | Available | Verdict |
|---|---|---|
| Runtime recorded hash in log | No — log does not record script hash | N/A |
| Deployment mtime + execution timestamp | Deployment: 00:46:10 CST Nov 11; Next execution: 16:00 CST Nov 11 | Deployment precedes execution window |
| Versioned runtime artifact | None | N/A |
| Process command/script path | From crontab: same absolute path as deployed file | INFERRED — path matches |
| Audit record | H1/H2 PASS from S66 | STATIC only |

**Classification**: `RC2_RUNTIME_CODE_ADOPTION_UNVERIFIED`

Rationale: Deployment timestamp (00:46 CST) is before first eligible cron (16:00 CST). Once cron fires, the cron subprocess calls `SCRIPTS_DIR / "backfill_daily_prices.py"` which resolves to the patched file. However, actual runtime adoption can only be `CONFIRMED` after the first post-RC2 cron execution is logged.

---

## 5. RC-2 Filter Effect (F1/F2/F3)

### Expected Behavior
RC-2 change: `if len(sid) > 4 and not sid.isdigit():` → `if len(sid) > 4:`

| Stock Type | Stock ID Example | len | Numeric | Pre-RC2 | Post-RC2 |
|---|---|---|---|---|---|
| Ordinary TWSE | 2330 | 4 | Yes | INCLUDED | INCLUDED |
| Ordinary TWSE | 6423 | 4 | Yes | INCLUDED | INCLUDED |
| Benchmark | 0050 | 4 | Yes | INCLUDED | INCLUDED |
| 5-digit ETF | 00858 | 5 | Yes | INCLUDED (bug) | EXCLUDED (fixed) |
| 6-digit Warrant | 700022 | 6 | Yes | INCLUDED (bug) | EXCLUDED (fixed) |
| Alpha-numeric len>4 | TESTX | 5 | No | EXCLUDED | EXCLUDED |

### Runtime Filter Evidence
No runtime filter log data available. No post-RC2 provider fetch has occurred.

**Classification**: `RC2_FILTER_EFFECT_UNVERIFIED`

**Note**: RC-2 behavior is verified offline (H2 PASS from S66). Runtime verification requires a post-RC2 run.

**Regression assessment**: `REGRESSION_NOT_ASSESSED` — no runtime evidence. Offline H2 showed no regression for 4-digit stocks.

---

## 6. Rollback Status

| Item | Status |
|---|---|
| Backup | `scripts/backfill_daily_prices.py.bak-PRE-RC2-20261111` — PRESENT |
| Backup mtime | 2026-11-11 00:46:01 CST |
| Any regression evidence | NONE |
| Any unauthorized side effect | NONE |
| Rollback required | NO |

**Classification**: `ROLLBACK_NOT_INDICATED`
