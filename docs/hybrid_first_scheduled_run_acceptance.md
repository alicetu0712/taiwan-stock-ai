# Hybrid Forward Shadow — First Scheduled Run Acceptance

**Date:** 2026-11-05 (updated after installation + initial operational verification)  
**Cron installed:** ✅ 2026-11-05 18:09 Taiwan  
**Manual pipeline run:** ✅ BLOCKED_PARTIAL_MARKET (correct fail-closed, 18:28 Taiwan)  
**Status:** `AWAITING_FIRST_SCHEDULED_RUN` — next scheduled trigger: **2026-11-06 (五) 16:00 Taiwan**

---

## Three-Level Acceptance Summary

### L1 — Scheduler Acceptance

| Check | Status | Evidence |
|---|---|---|
| Cron entry correct | ✅ PASS | `crontab -l` → 1 entry, `0 16 * * 1-5` |
| Timezone correct | ✅ PASS | System CST (UTC+8), cron hour 16 = 16:00 Taiwan |
| Actual cron trigger | ⏳ AWAITING | No `logs/hybrid_cron.log` yet; installed at 18:09 (after 16:00 slot) |
| Python process starts | ✅ SIMULATED_PASS | env -i + tty detection confirmed |
| No Permission Denied | ✅ USER_CONFIRMED | FDA granted to /usr/sbin/cron; env -i PASS |
| No duplicate execution | ✅ PASS | FileLock tested (HC20), entry count=1 |
| File lock normal | ✅ PASS | .cron.lock exists and releases correctly |
| State saved | ✅ PASS | .cron_state.json with exit_code + trigger_source |
| Trigger source recorded | ✅ PASS | `trigger_source: manual / cron_scheduled` (tty detection) |

**L1 Verdict: `AWAITING`** — scheduler installed and all pre-conditions pass; waiting for first actual trigger at 2026-11-06 16:00.

---

### L2 — Market Data Pipeline Acceptance

**Last checked:** 2026-11-05 18:28 Taiwan

| Market | Expected Date | Actual Date | Coverage | Gate |
|---|---|---|---|---|
| 0050 | 2026-11-05 | 2026-11-05 ✓ | 567 rows (manual backfill) | — |
| TWSE (stocks table) | 2026-11-05 | **2026-11-04** ❌ | 719 stocks on 11-04 | STALE |
| All non-0050 (daily_prices) | 2026-11-05 | **2026-11-04** ❌ | 6,956 on 11-04 | STALE |
| Full Market (11-05) | 2026-11-05 | **0 stocks** | — | **BENCHMARK_ONLY_UPDATED** |

| Gate | Result |
|---|---|
| DailyPrice Quality Gate | BLOCKED (TWSE api_date=11-04 ≠ target 11-05) |
| OHLC Continuity Gate | ✅ PASS (present=30, missing=0) |
| Full-Market Freshness Gate | BENCHMARK_ONLY_UPDATED → **BLOCKED_PARTIAL_MARKET** |
| ForwardSignals (11-05+) | 0 (no data yet) |

**Note on TPEx:** At 18:20 Taiwan, TPEx data for 11-05 passed quality gate (5,353 rows), but TWSE failed — entire date blocked (both required). TWSE API still returning 11-04 data at 18:20 Taiwan, which is unusual.

**Fail-closed verified:** Cron pipeline correctly returns `BLOCKED_PARTIAL_MARKET` (exit=0), shadow runner NOT invoked.

**L2 Verdict: `BLOCKED_PARTIAL_MARKET`** — data gates correctly blocking. This is expected/correct behavior; not a system failure.

---

### L3 — Prospective Research Acceptance

L2 is BLOCKED → L3 blocked upstream.

**Current decision inventory:**

| Classification | Count | Trade Date Range |
|---|---|---|
| RETROSPECTIVE_RECONSTRUCTION | 21 | 2026-11-04 |
| PROSPECTIVE | 0 | — |
| LATE_CAPTURE | 0 | — |
| INVALID_DATA | 0 | — |

**L3 Verdict: `BLOCKED_UPSTREAM`** — L2 not yet PASS; zero prospective decisions.

---

## State File Evidence (2026-11-05 18:28)

```json
{
  "run_at": "2026-11-05T10:28:50.814302+00:00",
  "taiwan_time": "2026-11-05T18:28:50 CST",
  "status": "BLOCKED_PARTIAL_MARKET",
  "exit_code": 0,
  "trigger_source": "manual",
  "steps": {
    "calendar": "trading_day",
    "data_freshness": "BENCHMARK_ONLY_UPDATED",
    "data_freshness_detail": "0050 updated to 2026-11-05, but non-0050 count=0; full market data not yet published"
  }
}
```

Key design: `exit_code=0` for BLOCKED_PARTIAL_MARKET (expected/safe condition). Business status is `BLOCKED_PARTIAL_MARKET`. Dashboard displays both separately.

---

## Backup Status

| Property | Value |
|---|---|
| File | `platform_20261105_20261105T101252Z.db.bak` |
| Size | 82.4 MB |
| integrity_check | ok |
| Rows (hybrid_forward_decision) | 21 |
| Restore test | ✅ rows=21, hashes_match=True |
| Risk | SINGLE_DEVICE_FAILURE_RISK (all on same Mac) |

---

## First Scheduled Run Verification (after 2026-11-06 16:00 Taiwan)

```bash
# 1. Confirm cron triggered (log file must exist)
ls -la logs/hybrid_cron.log
tail -30 logs/hybrid_cron.log

# 2. Check status and trigger source
python3 scripts/hybrid_shadow_cron.py --status
cat data/.cron_state.json | python3 -m json.tool

# 3. Confirm trigger_source = "cron_scheduled"
python3 -c "import json; s=json.load(open('data/.cron_state.json')); print(s.get('trigger_source'))"

# 4. Confirm market data freshness
python3 -c "
import sqlite3
from datetime import date
from src.research.full_market_freshness_gate import check_market_freshness
conn = sqlite3.connect('data/platform.db')
r = check_market_freshness(conn, date(2026,11,6), is_trading_day=True)
print(r.status.value, r.non_benchmark_count, 'stocks')
conn.close()
"

# 5. Check missed runs
python3 scripts/hybrid_shadow_cron.py --check-missed

# 6. Check for PROSPECTIVE decisions
python3 -c "
import sqlite3
conn = sqlite3.connect('data/platform.db')
rows = conn.execute(\"SELECT trade_date, capture_classification, COUNT(*) FROM hybrid_forward_decision WHERE trade_date >= '2026-11-06' GROUP BY trade_date, capture_classification\").fetchall()
print(rows or 'No decisions >= 2026-11-06 yet')
conn.close()
"
```

---

## Decision Classification Reference

| Classification | Valid OOS? | Required Condition |
|---|---|---|
| `PROSPECTIVE` | ✅ Full OOS value | trade_date >= 2026-11-05, L2 PASS, captured same/next trading day |
| `LATE_CAPTURE` | ⚠️ Acceptable | trade_date >= 2026-11-05, captured 2+ days later (e.g. Mac sleep) |
| `RETROSPECTIVE_RECONSTRUCTION` | ℹ️ Historical only | trade_date < 2026-11-05 |
| `INVALID_DATA` | 🛑 BUG | input_data_as_of < trade_date |

---

## Expected Timeline

| Date | Event | Status |
|---|---|---|
| 2026-11-05 18:09 | Cron installed | ✅ DONE |
| 2026-11-05 18:28 | Manual pipeline run | ✅ BLOCKED_PARTIAL_MARKET (correct) |
| 2026-11-06 16:00 | **First scheduled trigger** | ⏳ AWAITING |
| 2026-11-06+ | First PROSPECTIVE decisions (if signals exist) | ⏳ AWAITING |
| ~2026-11-13 | First 5D outcomes available | ⏳ AWAITING |
| ~2026-11-26 | First 20D outcomes available | ⏳ AWAITING |
| 100+ PROSPECTIVE decisions | Statistical evidence | ⏳ AWAITING |
