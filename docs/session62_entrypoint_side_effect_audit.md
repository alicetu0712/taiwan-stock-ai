# Session 62 — Entry-point & Side-effect Audit

## Scope

Audit all execution entry points for `scripts/backfill_daily_prices.py` and verify that
no import-time side effects (DB opens, network calls, scheduler starts) exist in the base
script or in the patched text of RC61-01, RC61-02, RC61-03.

Execution mode: READ_ONLY / STATIC_ANALYSIS. No live network requests issued. No production
file modified.

---

## Entry-point Inventory

| ID | Caller | Trigger | Target Function | Write Effects | Network Effects | Scheduler | Auth Required |
|----|--------|---------|-----------------|---------------|-----------------|-----------|---------------|
| EP-01 | Direct CLI — human operator | `python scripts/backfill_daily_prices.py` | `main() → run_backfill(execute=False)` | NONE (dry-run default). LOCAL SQLite only if `--execute` present. | ACTIVE on invocation (TWSE+TPEx fetch). | NONE | `--execute` flag required for DB writes. |
| EP-02 | `scripts/hybrid_shadow_cron.py _run_backfill()` | `subprocess.run(cmd)` — line 244 | `main() → run_backfill(execute=bool)` | LOCAL SQLite if `execute=True` + QG pass. NONE if `execute=False`. | ACTIVE when called (fetches TWSE+TPEx). | CRON_FROZEN — schedule `0 16 * * 1-5` NOT INSTALLED (declined S36). | `--execute` flag + explicit crontab install (not done). |
| EP-03 | Python import — test suite | `from scripts.backfill_daily_prices import ...` | Module-level init only. `_CALENDAR` created. `main()` NOT called. | NONE | NONE | NONE | None — import is read-only. |
| EP-04 | GitHub Actions `daily-pipeline.yml` | `cron: '55 7 * * 1-5'`; `workflow_dispatch` | `run_daily.py` — NOT `backfill_daily_prices.py` | Writes to Neon via `run_daily.py` only. backfill script NOT called. | `run_daily.py` provider calls only. | NONE for backfill script. | GitHub Actions secrets (NEON_URL etc.). NOT related to backfill RCs. |
| EP-05 | GitHub Actions `overnight-pipeline.yml` | `cron: '0 1 * * 1-5'`; `workflow_dispatch` | `run_overnight.py` — NOT `backfill_daily_prices.py` | Writes to Neon via `run_overnight.py` only. backfill script NOT called. | `run_overnight.py` provider calls only. | NONE for backfill script. | NOT related to backfill RCs. |
| EP-06 | GitHub Actions `hybrid_forward_shadow.yml` | `workflow_dispatch` (manual only) | `run_hybrid_forward_shadow.py` — NOT `backfill_daily_prices.py` | backfill script NOT called. | NONE for backfill script. | NONE for backfill script. | NOT related to backfill RCs. |

**Key finding — EP-02:** `hybrid_shadow_cron.py` calls `backfill_daily_prices.py` as a
subprocess (not an import). Cron is NOT installed. Deployment of an RC patch does not
activate or modify this caller.

---

## Import-time Side-effect Audit

| ID | Module-level Code | DB Opened | SQL Executed | Network Called | Scheduler Started | File Written | main() Called | Verdict |
|----|-------------------|-----------|--------------|----------------|-------------------|--------------|---------------|---------|
| IS-01 | `_CALENDAR = TaiwanTradingCalendar()` (line 65) | No | No | No | No | No | No | SAFE |
| IS-02 | `_MIN_COVERED_STOCKS = 5_000` (line 568) | No | No | No | No | No | No | SAFE |
| IS-03 | URL constants `TWSE_HIST_URL` etc. (lines 51-54) | No | No | No | No | No | No | SAFE |
| IS-04 | `if __name__ == "__main__": main()` (line 635) | No | No | No | No | No | No | SAFE |
| IS-05 | `_default_start()` — only inside `main()` | No | No | No | No | No | No | SAFE |
| IS-06 | RC-1 patch: `summary["errors"].append(msg)` | No | No | No | No | No | No | SAFE |
| IS-07 | RC-2 patch: `if len(sid) > 4:` boolean change | No | No | No | No | No | No | SAFE |
| IS-08 | RC-3 patch: `row.get("TradingShares", "")` | No | No | No | No | No | No | SAFE |

**Notes on IS-01:** `TaiwanTradingCalendar` has no `__init__`, uses only `frozenset` of
holiday dates and pure Python logic. Imports only `zoneinfo`, `logging`, `datetime`, `enum`.
No DB, no HTTP.

**Notes on IS-05:** `_default_start()` does open `sqlite3.connect(DB_PATH)` for a SELECT
query, but it is a function definition at line 573, not module-level execution. It is called
only at line 601 inside `main()`, which requires `__main__` context.

---

## Test Evidence

| Test ID | Description | Result |
|---------|-------------|--------|
| TC01 | Exactly 6 entry points catalogued | PASS |
| TC02 | EP-01 CLI correctly described (main, run_backfill, --execute) | PASS |
| TC03 | EP-02 subprocess from hybrid_shadow_cron, NOT INSTALLED | PASS |
| TC04 | EP-03 import: no write, no network, no scheduler | PASS |
| TC05 | EP-04/EP-05 GH Actions call run_daily/overnight (not backfill) | PASS |
| TC06 | EP-06 hybrid_forward_shadow uses different script | PASS |
| TC07 | All 8 import-time checks return SAFE | PASS |
| TC08–TC14 | Individual IS-01..IS-08 checks (no DB, no network, no scheduler) | PASS (8) |

All 14 TC01–TC14 tests pass.

---

## Limitations

- **NOT_RUN_SAFETY_BOUNDARY:** Live network requests (EP-01 and EP-02 network effects) were
  not tested in a live environment. Static analysis confirms no network calls on import and
  that calls are gated behind `run_backfill()`. A live isolated dry-run was not performed
  because it would require a network connection and risk exceeding authorized API quota.
- EP-02 cron installation status verified by docstring statement ("NOT installed
  automatically") and S36 decline record — not by live `crontab -l` execution.
- GitHub Actions workflows verified by static YAML inspection (no `backfill_daily_prices`
  reference in any step command).

---

## Verdict

**ENTRYPOINT_AUDIT_PASS**

---

## Next Action

No action required before authorization. When user grants AUTH-RC61-01/02/03, the deployment
procedure (see `session62_deployment_isolation.md`) begins at EP-01 (Direct CLI dry-run).
