# Hybrid Forward Shadow — First Live Cron Integrity Audit

**Audit Date:** 2026-11-05  
**Auditor Session:** 10  
**Taiwan Time at Audit:** 2026-11-05 19:05 CST  
**Git HEAD:** 1c42cb3  
**Regression:** 1,667 PASS, 0 FAIL (post-fix)

---

## 1. Live Cron Acceptance

### Current Status: `AWAITING_FIRST_SCHEDULED_RUN`

| Check | Evidence | Status |
|---|---|---|
| Cron installed | `crontab -l` → 1 entry, `0 16 * * 1-5` | ✅ PASS |
| Cron entry correct | Python path + `--execute` + log redirect | ✅ PASS |
| `logs/hybrid_cron.log` exists | File NOT found | ⏳ AWAITING |
| First scheduled run | 2026-11-06 (五) 16:00 Taiwan | ⏳ AWAITING |
| FDA granted | `/usr/sbin/cron` in Full Disk Access | ✅ PASS |

**Why `hybrid_cron.log` is the definitive evidence:**  
The cron entry redirects stdout to `logs/hybrid_cron.log`. That file's existence and first-line timestamp are the only reliable proof that macOS cron invoked the process. `trigger_source="cron_scheduled"` in the state file is a tty-detection heuristic — it correctly identifies cron runs (no tty), but also shows `cron_scheduled` when running in Claude Code's Bash tool (also non-tty). It is necessary but not sufficient evidence.

### State File — Session 9 Artifact (not a live cron run)

```json
{
  "run_at": "2026-11-05T10:28:50Z",
  "today": "2026-11-05",
  "trigger_source": "cron_scheduled",
  "status": "BLOCKED_PARTIAL_MARKET",
  "exit_code": 0
}
```

`trigger_source: "cron_scheduled"` is a false positive from Session 9 — the script was invoked from Claude Code's non-tty Bash tool at 18:28 CST Nov 5, before the first scheduled slot. `today: 2026-11-05` confirms this is not the Nov 6 scheduled run.

### Post-scheduled-run Verification Commands

```bash
# 1. Confirm cron triggered (log file must exist and have Nov 6 entries)
ls -la logs/hybrid_cron.log
head -5 logs/hybrid_cron.log

# 2. Confirm trigger_source + timestamp
cat data/.cron_state.json | python3 -m json.tool
# Must show: today=2026-11-06, trigger_source=cron_scheduled, run_at ~16:00 CST

# 3. Confirm freshness outcome
python3 -c "
import json
s=json.load(open('data/.cron_state.json'))
print('status=', s['status'])
print('freshness=', s['steps'].get('data_freshness'))
print('retries=', s['steps'].get('freshness_retry_attempt'))
"
```

---

## 2. Retry Integrity

### Semantics: RETRY_MAX=3 means 1 initial + 3 retries = 4 total attempts

| Attempt | Loop index | Expected Time (from 16:00) | Action |
|---|---|---|---|
| Initial | 0 | 16:00 | Backfill + Freshness check |
| Retry 1 | 1 | ~16:30 | Sleep 30 min → Backfill → Freshness |
| Retry 2 | 2 | ~17:00 | Sleep 30 min → Backfill → Freshness |
| Retry 3 | 3 | ~17:30 | Sleep 30 min → Backfill → Freshness |
| Fail-closed | — | 17:30 | BLOCKED_* if still not fresh |

**Maximum total pipeline duration:** 90 minutes (exits by ~17:30 Taiwan).

### Retryable vs Non-retryable

| FreshnessStatus | Action | Pipeline Status on Exhaustion |
|---|---|---|
| FULL_MARKET_FRESH | Proceed immediately (break) | SUCCESS |
| BENCHMARK_ONLY_UPDATED | Retry up to 3× | BLOCKED_PARTIAL_MARKET |
| PARTIAL_MARKET_UPDATE | Retry up to 3× | BLOCKED_PARTIAL_MARKET |
| PROVIDER_NOT_READY | Retry up to 3× | BLOCKED_STALE_DATA |
| STALE | No retry (immediate fail-close) | BLOCKED_STALE_DATA |
| UNKNOWN | No retry (immediate fail-close) | BLOCKED_STALE_DATA |

### Verdict: PASS

| Item | Result |
|---|---|
| Retry count ≤ RETRY_MAX | ✅ loop range is [0..RETRY_MAX] |
| Retry interval = 30 min | ✅ `_time.sleep(1800)` |
| Re-runs backfill each retry | ✅ `_run_backfill(execute=True)` before continue |
| Re-checks freshness each retry | ✅ `check_market_freshness()` at top of loop |
| Fail-closed on exhaustion | ✅ falls through to status set + return |
| Success exits immediately | ✅ `break` on FULL_MARKET_FRESH |
| Final reason preserved in state | ✅ `data_freshness` + `data_freshness_detail` |
| No duplicate decisions | ✅ shadow only runs once (after final retry loop) |
| `_time` mocked in all retry tests | ✅ HC32 fix applied (Session 10) |

---

## 3. Alert Integrity

### Defect Found & Fixed (Session 10 — P0)

**Root cause:** HC16, HC18, HC26, HC27, HC31 called `run_cron_pipeline()` through failure paths without mocking `_alert()`. Because `_alert()` calls `AlertStateManager()` with the hardcoded production path (`data/.alert_state.json`), 8 full-suite regression runs in Session 9 accumulated:

| Alert Type | Count | Source Tests |
|---|---|---|
| BACKUP_FAILURE | 24 | HC18 (backup=None → alert), HC27, HC31 |
| STALE_DATA | 16 | HC16 (backfill fail → alert), HC26 (STALE → alert) |
| SHADOW_FAILED | 8 | HC18 (shadow exit=1 → alert) |

**Fix:** Added `patch("scripts.hybrid_shadow_cron._alert")` to the `with` block of HC16, HC18, HC26, HC27, HC31.  
**Remediation:** Resolved all 3 test-artifact alerts via `AlertStateManager.resolve()` (history preserved with `resolved=True`).

### Alert Lifecycle Verification

| Lifecycle Step | Mechanism | Status |
|---|---|---|
| First occurrence → new alert | `record()` returns True, creates entry | ✅ AL01 |
| Same-day duplicate → deduplicated | returns False, increments `count` | ✅ AL02-AL03 |
| Resolution | `resolve()` sets `resolved=True` | ✅ AL04 |
| Resolved excluded from active | `active_alerts()` filters `resolved=False` | ✅ AL05 |
| Date filter works | `active_alerts(trade_date=...)` | ✅ AL06 |
| `all_alerts()` includes resolved | returns full history | ✅ AL07 |
| Different types same day = independent | separate keys | ✅ AL08 |
| Corrupt state file → safe load | empty alerts, no crash | ✅ AL09 (new) |
| Re-record after resolve → new entry | resolved → condition False → fresh entry | ✅ AL10 (new) |

### Alert Wiring Points (confirmed in code)

| Trigger | Alert Type | Location |
|---|---|---|
| `backfill_daily_prices.py` exit≠0 | STALE_DATA | Line ~350, after BACKFILL_FAILED |
| Freshness STALE / PROVIDER_NOT_READY after retries | STALE_DATA | Retry loop exhaustion |
| Freshness BENCHMARK_ONLY_UPDATED / PARTIAL after retries | PARTIAL_MARKET | Retry loop exhaustion |
| Freshness unknown (else) | STALE_DATA | Retry loop exhaustion |
| `create_backup()` returns None | BACKUP_FAILURE | Step 5 |
| Shadow runner exit≠0 | SHADOW_FAILED | Step 6 |

**6 trigger locations, 4 alert types used: STALE_DATA (×3), PARTIAL_MARKET (×1), BACKUP_FAILURE (×1), SHADOW_FAILED (×1).**

### Post-fix Alert State

```
active_today=0
all_resolved=True (3 historical test-artifact entries, all resolved)
```

---

## 4. Data Integrity

### Current Market Data (2026-11-05 19:05 CST)

| Data | Last Date | Count | Status |
|---|---|---|---|
| 0050 (benchmark) | 2026-11-05 | 567 rows | ✅ Current |
| Non-0050 stocks | 2026-11-04 | 14,674 distinct | ⚠️ 1 day stale |
| 2026-11-06 non-0050 | — | 0 rows | — (not yet published) |

**2026-11-06 Freshness pre-run:** STALE (expected — backfill not yet run for Nov 6)

### Freshness Gate Verdict

| Gate | Result |
|---|---|
| DailyPrice Quality Gate | BLOCKED (TWSE api_date=2026-11-04 ≠ target 2026-11-06) |
| OHLC Continuity Gate | PASS (present=30, missing=0 as of 2026-11-05) |
| Full-Market Freshness Gate | STALE (pre-run; backfill will run first at 16:00 Nov 6) |
| Fail-closed protection | ✅ Shadow will not run until FULL_MARKET_FRESH |

**Expected Nov 6 scenario:**
1. Cron fires at 16:00
2. Backfill runs → 0050 likely updates immediately
3. Freshness check → `BENCHMARK_ONLY_UPDATED` (non-0050 not yet published)
4. Retry at 16:30 → backfill re-runs → if TWSE published → FULL_MARKET_FRESH → SUCCESS
5. If still partial at 17:30 → BLOCKED_PARTIAL_MARKET, alert recorded

---

## 5. Research Integrity

### Current Decision Inventory

| Classification | Count | Trade Date | Valid OOS? |
|---|---|---|---|
| RETROSPECTIVE_RECONSTRUCTION | 21 | 2026-11-04 | ℹ️ Historical |
| PROSPECTIVE | 0 | — | ⏳ AWAITING |
| LATE_CAPTURE | 0 | — | — |
| INVALID_DATA | 0 | — | — |

**Cutoff:** 2026-11-05 (cron installation date). No PROSPECTIVE decisions until first successful run on 2026-11-06+.

### Fail-closed Protection

The shadow runner can only run when:
1. `FULL_MARKET_FRESH` confirmed (all retries exhausted without this → pipeline returns before shadow)
2. Backfill exit_code=0 (failure → BACKFILL_FAILED before freshness check)

This prevents any partial-data shadow run that could produce INVALID_DATA or misclassified decisions.

### Append-only & Hash

The `hybrid_forward_decision` table enforces uniqueness per `(trade_date, stock_id, model_version)`. Duplicate cron runs (e.g., from a stale lock that shouldn't happen) would not duplicate decisions.

---

## 6. Test Results

### New Tests Added (Session 10)

| Test | Category | Description |
|---|---|---|
| AL09 | Alert | Corrupt state file → safe load, no crash |
| AL10 | Alert | Resolved alert can be re-opened on same day |
| CN01 | Concurrency | Lock released via finally even on pipeline exception |
| CN02 | Concurrency | Second FileLock blocked while first held; released correctly |

### Regression

| Suite | Tests | Result |
|---|---|---|
| test_hybrid_cron.py | 50 | ✅ 50 PASS |
| Full suite | 1,667 | ✅ 1,667 PASS, 0 FAIL |
| Ruff | — | ✅ clean |

### Changed Files (Session 10)

| File | Change |
|---|---|
| `tests/test_hybrid_cron.py` | Added `_alert` mock to HC16, HC18, HC26, HC27, HC31; added AL09, AL10, CN01, CN02 |
| `data/.alert_state.json` | 3 test-artifact alerts resolved (history preserved) |
| `docs/hybrid_first_live_cron_integrity_audit.md` | This file |

---

## 7. Final Verdict

### Scheduler
**`AWAITING`** — Cron installed and verified (1 correct entry, FDA granted). First scheduled trigger at 2026-11-06 16:00 Taiwan has not occurred. `logs/hybrid_cron.log` does not exist.

### Retry
**`PASS`** — RETRY_MAX=3 semantics confirmed (4 total checks, 90 min max). `_time.sleep` mocked in all retry tests. No real sleeps during test suite. Fail-closed verified HC35/HC36/HC38.

### Alerts
**`PASS`** (after fix) — Contamination defect found and fixed: HC16/HC18/HC26/HC27/HC31 lacked `_alert` mock. Historical test-artifact alerts resolved. AL09/AL10 added. Alert lifecycle fully covered.

### Market Data
**`AWAITING`** — Non-0050 data is 1 day stale (2026-11-04). Will be resolved by backfill on 2026-11-06. Fail-closed gate confirmed preventing premature shadow run.

### Research
**`BLOCKED_UPSTREAM`** — L2 not yet PASS. 0 PROSPECTIVE decisions. 21 RETROSPECTIVE_RECONSTRUCTION decisions (pre-cutoff). No misclassification risk.

### Overall
**`CONDITIONAL_READY`**

The system is correctly configured and all logic is verified. One conditional must be met before declaring `READY_FOR_MONITORING`:

> ✅ Required: First scheduled run on 2026-11-06 16:00 Taiwan must produce `logs/hybrid_cron.log` with run_at ~16:00+ and `today=2026-11-06`.

The alert contamination defect (P0) has been fixed. No architectural changes required.

---

## Appendix — Trigger Source Limitation

`trigger_source` is detected via `sys.stdout.isatty()`. This correctly distinguishes:
- Terminal run → `manual`
- Cron run (stdout redirected to log file) → `cron_scheduled`

**Known limitation:** When run via Claude Code's Bash tool (non-interactive subprocess), stdout is also non-tty → shows `cron_scheduled` even for manual invocations. This is why the Session 9 state file shows `trigger_source: "cron_scheduled"` for a manual run.

**Mitigation:** `logs/hybrid_cron.log` existence is the authoritative cron trigger evidence. `trigger_source` is supplementary.
