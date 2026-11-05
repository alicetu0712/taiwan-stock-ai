# Hybrid Forward Shadow — First Scheduled Run Verification

**Audit Date:** 2026-11-05  
**Taiwan Time at Audit:** 2026-11-05 19:16 CST  
**Git HEAD:** 1c42cb3  
**Session:** 11  
**Overall Verdict:** `AWAITING_FIRST_SCHEDULED_RUN`

---

## Final Acceptance Table

| Area | Status | Evidence |
|---|---|---|
| Cron Installation | ✅ VERIFIED | 1 correct entry, Python + script paths confirmed |
| Actual Scheduled Trigger | ⏳ AWAITING | `logs/hybrid_cron.log` absent; 2026-11-06 16:00 not yet reached |
| Retry Execution | ⏳ AWAITING | No run yet; policy logic verified in HC34-HC38 |
| Full-market Freshness | ⚠️ STALE (pre-run) | 0050=Nov5, non-0050=Nov4; TWSE API not publishing Nov5 at 19:16 |
| Fail-closed | ✅ VERIFIED | Quality gate blocks write; shadow not invoked without FULL_MARKET_FRESH |
| Hybrid Shadow | ⏳ AWAITING | 0 PROSPECTIVE decisions; shadow not invoked |
| Prospective Classification | ⏳ AWAITING | No PROSPECTIVE decisions yet |
| Alert State | ✅ CLEAN | 0 active alerts; 3 resolved test artifacts (Session 10 fix) |
| Backup Restore | ✅ VERIFIED | 82MB, integrity=ok, hash=0b17ec6315d12be4, matches live DB |
| Dashboard G0 | ✅ WIRED | Retry counter, alert banner, Chinese status descriptions in place |
| Regression | ✅ 1,667 PASS | 0 failures, Ruff clean (Session 10 baseline) |

---

## PART A — Baseline Confirmation

| Item | Confirmed Value |
|---|---|
| Git HEAD | `1c42cb3` (unchanged) |
| Cron schedule | `0 16 * * 1-5` |
| Timezone | Asia/Taipei (CST, UTC+8) |
| Cron entries | 1 (no duplicates) |
| RETRY_MAX | 3 retries + 1 initial = 4 total checks |
| Retry interval | 30 minutes |
| Max retry window | 90 minutes (exits ≤17:30 Taiwan) |
| Alert state | `data/.alert_state.json` (0 active) |
| Research SQLite | `data/platform.db` (82MB, 28 tables) |
| Decisions (pre-run) | 21 RETROSPECTIVE_RECONSTRUCTION, 0 PROSPECTIVE |
| Session 10 baseline | 1,667 PASS |

---

## PART B — Scheduler Verdict: `AWAITING`

**Taiwan time at audit: 2026-11-05 19:16 CST**  
First scheduled run: **2026-11-06 (五) 16:00 Taiwan** — not yet reached.

### Preflight Results

| Check | Result | Detail |
|---|---|---|
| Cron entry count | ✅ PASS | 1 entry |
| Cron entry content | ✅ PASS | `0 16 * * 1-5 python3 hybrid_shadow_cron.py --execute >> logs/hybrid_cron.log 2>&1` |
| Python executable | ✅ PASS | `/Library/Frameworks/Python.framework/Versions/3.13/bin/python3` → python3.13 symlink |
| Script file | ✅ PASS | `scripts/hybrid_shadow_cron.py` exists, 29,362 bytes |
| Log directory | ✅ WRITABLE | `logs/` writable; write test passed |
| `logs/hybrid_cron.log` | ✅ ABSENT | Correctly absent — no cron run yet |
| SQLite readable | ✅ PASS | 82MB, 28 tables, `hybrid_forward_decision` present |
| File lock | ✅ ACQUIRABLE | `.cron.lock` exists (from last session, PID stale); new acquire succeeds → released OK |
| Alert state | ✅ CLEAN | 0 active; 3 resolved test-artifact entries |
| Backup path | ✅ PASS | 1 official backup (82MB, integrity=ok) |
| FDA (Full Disk Access) | ✅ USER CONFIRMED | `/usr/sbin/cron` added in System Settings (Session 7) |

### Definitive First Scheduled Run Evidence (after 2026-11-06 16:00)

```bash
# Step 1 — Log file must exist (non-negotiable)
ls -la logs/hybrid_cron.log
head -5 logs/hybrid_cron.log   # first line timestamp must be ~16:00 CST Nov 6

# Step 2 — State file must show today=2026-11-06
cat data/.cron_state.json | python3 -m json.tool

# Step 3 — Cross-validate timestamp (Taiwan time ~16:00 on 2026-11-06)
python3 -c "
import json
s = json.load(open('data/.cron_state.json'))
print('today=', s['today'])           # must be 2026-11-06
print('trigger_source=', s['trigger_source'])  # cron_scheduled
print('run_at=', s['run_at'])         # must be ~08:00 UTC = 16:00 Taiwan
"
```

**Note on `trigger_source`:** The session 9 state file incorrectly shows `trigger_source: "cron_scheduled"` from a manual run via Claude Code's Bash tool (non-tty stdout). `trigger_source` is necessary but not sufficient evidence — `logs/hybrid_cron.log` existence with correct timestamp is authoritative.

---

## PART C — Retry Verdict: `AWAITING`

Policy confirmed correct from code inspection:

| Attempt | Loop index | Expected start | Sleep before |
|---|---|---|---|
| Initial check | 0 | 16:00 | — |
| Retry 1 | 1 | ~16:30 | 30 min after attempt 0 |
| Retry 2 | 2 | ~17:00 | 30 min after attempt 1 |
| Retry 3 | 3 | ~17:30 | 30 min after attempt 2 |
| Fail-closed | — | 17:30+ | — (no sleep; returns) |

**RETRY_MAX=3 semantics:** `range(RETRY_MAX+1)` = [0,1,2,3] → 4 total freshness checks. Sleep condition: `_retry_attempt < RETRY_MAX` → sleeps after attempts 0, 1, 2 only.

| Status | Retryable? | Exhaustion outcome |
|---|---|---|
| FULL_MARKET_FRESH | — (break immediately) | SUCCESS |
| BENCHMARK_ONLY_UPDATED | ✅ | BLOCKED_PARTIAL_MARKET |
| PARTIAL_MARKET_UPDATE | ✅ | BLOCKED_PARTIAL_MARKET |
| PROVIDER_NOT_READY | ✅ | BLOCKED_STALE_DATA |
| STALE | ❌ immediate | BLOCKED_STALE_DATA |
| UNKNOWN | ❌ immediate | BLOCKED_STALE_DATA |

**Expected Nov 6 scenario:**  
TWSE currently slow (19:16 CST Nov 5, TWSE API still showing Nov 4 data for today). On Nov 6:
1. Backfill runs → 0050 likely updates immediately
2. If non-0050 not yet published → `BENCHMARK_ONLY_UPDATED` → retry at 16:30
3. If TWSE publishes by 16:30 → retry succeeds → `FULL_MARKET_FRESH` → shadow runs → SUCCESS
4. If still partial at 17:30 → `EXHAUSTED_SAFE` / BLOCKED_PARTIAL_MARKET

---

## PART D — Market Data Verdict: `PROVIDER_NOT_READY` (pre-run)

### Detailed Market Status (2026-11-05 19:16 CST)

| Market | Expected Date | API Date | DB Date | DB Count | Quality Gate |
|---|---|---|---|---|---|
| 0050 | 2026-11-05 | 2026-11-05 | ✅ 2026-11-05 | 567 rows | PASS |
| TWSE (non-0050) | 2026-11-05 | ❌ 2026-11-04 | 2026-11-04 | 727 stocks | **FAIL** (api_date mismatch) |
| TPEx | 2026-11-05 | ✅ 2026-11-05 | ❌ not written | 5,353 (API) | PASS (blocked by TWSE) |
| Full Market | 2026-11-05 | — | 0 stocks on Nov5 | — | **BLOCKED** |

**Explanation:** TPEx quality gate passes (5,353 rows) but the DailyPrice pipeline blocks the entire date when TWSE fails. TWSE API was still returning 2026-11-04 data at 19:16 CST Nov 5 — unusually late. This may resolve before the Nov 6 16:00 cron run.

**2026-11-06 Freshness pre-run:** `PROVIDER_NOT_READY` (benchmark=2026-11-05; 0050 for Nov 6 not yet published — correct at 19:16 CST Nov 5).

### Additional Gates

| Gate | Result |
|---|---|
| OHLC Continuity Gate (Nov 5) | ✅ PASS — present=30, missing=0 |
| DailyPrice Quality Gate (Nov 5, dry-run) | ❌ BLOCKED — TWSE api_date=2026-11-04 ≠ 2026-11-05 |
| Full-market Freshness Gate (Nov 5) | BENCHMARK_ONLY_UPDATED |
| Full-market Freshness Gate (Nov 6, pre-run) | PROVIDER_NOT_READY |

**Fail-closed protection:** Shadow runner can only proceed when `FULL_MARKET_FRESH`. All blocked states (BENCHMARK_ONLY_UPDATED, PROVIDER_NOT_READY, STALE) correctly abort before shadow invocation.

---

## PART E — Research Integrity Verdict: `BLOCKED_UPSTREAM`

### Decision Inventory

| Metric | Before Run | After Run | New |
|---|---|---|---|
| Total Decisions | 21 | — | — |
| PROSPECTIVE | 0 | — | — |
| LATE_CAPTURE | 0 | — | — |
| RETROSPECTIVE | 21 | — | — |
| INVALID_DATA | 0 | — | — |

**Unique constraint confirmed:** `UNIQUE(stock_id, trade_date, rule_version)` — prevents duplicate decisions for same stock/date/rule combination. Idempotency guaranteed at DB level.

**No duplicates:** `duplicate_trade_date_stock=0`

**Append-only protection:**
- Primary key: `id INTEGER PRIMARY KEY AUTOINCREMENT`
- Business unique: `UNIQUE(stock_id, trade_date, rule_version)`
- Existing decisions cannot be overwritten; second insert with same key → SQLite constraint error

**Prospective classification rule (unchanged):**
- `PROSPECTIVE`: trade_date ≥ 2026-11-05 AND L2 PASS AND captured same/next trading day
- `LATE_CAPTURE`: trade_date ≥ 2026-11-05 AND captured 2+ days later
- `RETROSPECTIVE_RECONSTRUCTION`: trade_date < 2026-11-05
- `INVALID_DATA`: input_data_as_of < trade_date (bug marker)

---

## PART F — Alert State Verdict: `CLEAN`

| Metric | Value |
|---|---|
| Active alerts (today) | 0 |
| Total alerts in file | 3 (all resolved) |
| Resolved alerts | STALE_DATA count=16, BACKUP_FAILURE count=24, SHADOW_FAILED count=8 |
| Test contamination | Remediated in Session 10 (HC16/18/26/27/31 fixed) |

The 3 resolved entries are test-artifact history from Session 9 (8 regression runs without `_alert` mock). They are marked `resolved=True` and correctly excluded from `active_alerts()`. The dashboard shows 0 active alerts for today.

---

## PART G — Backup Verdict: `PASS` (SINGLE_DEVICE_FAILURE_RISK)

| Property | Value |
|---|---|
| Official backup | `platform_20261105_20261105T101252Z.db.bak` |
| Size | 82 MB |
| Created | 2026-11-05 10:12 UTC |
| Integrity check | `ok` |
| Decision rows | 21 |
| Decision hash | `0b17ec6315d12be4` |
| Live DB hash | `0b17ec6315d12be4` ✅ MATCHES |
| Hashes match | ✅ True |
| Retention | 7 backups (BACKUP_KEEP_N=7) |

**Additional files in data/ (not official backups):**
- `platform_recover_backup_20261105_165923.db` (82MB) — recovery backup from Nov 5 operations
- `platform_recover_backup_20261105_170018.db` (82MB) — recovery backup from Nov 5 operations
- `platform 2.db-wal` (101KB, Jul 1) — orphaned WAL file from old database copy, no corresponding .db file

**Risk:** `SINGLE_DEVICE_FAILURE_RISK` — all backups on same Mac. Off-device backup options documented in `docs/hybrid_off_device_backup_plan.md`. Not remediated without user approval.

---

## PART H — Dashboard G0

G0 panel displays (verified in code):

| Field | Display | Source |
|---|---|---|
| Cron installed | ✅ 是 / ⏳ 未安裝 | crontab -l check |
| Last run time | 2026-11-05T10:28 | state.run_at |
| Business status | BLOCKED_PARTIAL_MARKET | state.status |
| Exit code | exit=0 | state.exit_code |
| Trigger source | 排程觸發 / 手動 | state.trigger_source |
| Retry attempts | 0/3 | state.steps.freshness_retry_attempt |
| Active alerts today | 0 | .alert_state.json |
| Freshness caption | 🕐 0050 已更新，等待全市場資料 | BENCHMARK_ONLY_UPDATED |

**Chinese status descriptions** (G0 panel):

| Status | Description displayed |
|---|---|
| `BLOCKED_PARTIAL_MARKET` | 部分股票行情尚未更新完成，系統已暫停產生新研究決策（非異常，正常保護） |
| `BLOCKED_STALE_DATA` | 0050 基準股資料過期，無法確認交易日完整性 |
| `SKIPPED_NON_TRADING_DAY` | 非交易日，跳過（正常） |
| `SUCCESS` | 全流程完成 — 資料已補齊、備份已存、Shadow 研究已寫入 |
| `SHADOW_FAILED` | Shadow 研究執行失敗 — 請查看 logs/hybrid_cron.log |

---

## PART I — Five-Trading-Day Monitoring Plan

**After first successful cron run**, fill in this table daily:

| Date | Trading Day? | Cron Triggered? | Freshness Gate | Retry Count | Business Status | New Decisions | PROSPECTIVE | Alerts | Backup |
|---|---|---|---|---|---|---|---|---|---|
| 2026-11-06 (五) | ✅ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
| 2026-11-09 (一) | ✅ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
| 2026-11-10 (二) | ✅ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
| 2026-11-11 (三) | ✅ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |
| 2026-11-12 (四) | ✅ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ |

**Daily check commands:**

```bash
# After 16:00 each trading day
python3 -c "
import json
s = json.load(open('data/.cron_state.json'))
print('today:', s['today'])
print('status:', s['status'])
print('retries:', s['steps'].get('freshness_retry_attempt'))
print('exit:', s['exit_code'])
"

# Count new PROSPECTIVE decisions
python3 -c "
import sqlite3
conn = sqlite3.connect('data/platform.db')
rows = conn.execute('''
  SELECT trade_date, capture_classification, COUNT(*)
  FROM hybrid_forward_decision
  WHERE trade_date >= '2026-11-06'
  GROUP BY trade_date, capture_classification ORDER BY trade_date
''').fetchall()
print(rows or 'No decisions >= 2026-11-06 yet')
conn.close()
"

# Check active alerts
python3 -c "
import sys; sys.path.insert(0,'.')
from src.research.alert_state import AlertStateManager
from datetime import date
mgr = AlertStateManager()
active = mgr.active_alerts(date.today())
print(f'active_alerts={len(active)}')
for a in active: print(f'  {a.alert_type}: {a.message}')
"

# Latest backup
ls -lah data/backups/ | tail -3
```

---

## Pre-existing Conditions (not defects, not action items)

| Item | File | Date | Action Required |
|---|---|---|---|
| Orphaned WAL | `data/platform 2.db-wal` (101KB) | Jul 1 2026 | None — old artifact, no corresponding .db file. Can be removed with user approval. |
| Recover backups | `data/platform_recover_backup_20261105_*.db` × 2 | Nov 5 2026 | None — recovery backups from operations. Can be archived with user approval. |
| SINGLE_DEVICE_FAILURE_RISK | All backups on same Mac | Ongoing | Documented in `hybrid_off_device_backup_plan.md`. Action requires user approval. |
| TPEx in stocks table | 0 TPEx entries in `stocks` table | Ongoing | TPEx prices ARE in `daily_prices` via API; `stocks` table only tracks TWSE. Acceptable gap. |

---

## Final Verdict

### Scheduler
**`AWAITING`** — 2026-11-05 19:16 CST. First scheduled run is 2026-11-06 16:00 Taiwan. `logs/hybrid_cron.log` does not exist. All preflight checks PASS.

### Market Data
**`AWAITING`** — Non-0050 data stale (last: 2026-11-04). TWSE API still returning Nov 4 data at 19:16 CST Nov 5. TPEx API ready (5,353 rows) but not written due to TWSE gate failure. Expect data to be available when cron fires Nov 6 ~16:00.

### Research
**`BLOCKED_UPSTREAM`** — L2 not yet PASS. 0 PROSPECTIVE decisions. 21 RETROSPECTIVE_RECONSTRUCTION pre-cutoff decisions in DB (not OOS-valid). Unique constraint `UNIQUE(stock_id, trade_date, rule_version)` enforces append-only idempotency.

### Overall
**`AWAITING_FIRST_SCHEDULED_RUN`**

---

## Items Verified (No Code Changes Required)

1. ✅ Cron installation correct (1 entry, right Python, right script, right redirect)
2. ✅ File lock acquirable and releasable
3. ✅ Alert state clean (0 active, test contamination remediated Session 10)
4. ✅ Backup integrity (hash matches live DB)
5. ✅ Unique constraint on hybrid_forward_decision (`UNIQUE(stock_id, trade_date, rule_version)`)
6. ✅ Retry logic verified in HC34-HC38 tests
7. ✅ Alert lifecycle verified in AL01-AL10 tests
8. ✅ Fail-closed: shadow not invoked unless FULL_MARKET_FRESH

## Items Not Yet Verifiable (time-bound)

1. ⏳ First real cron trigger (requires Nov 6 16:00 to pass)
2. ⏳ Retry execution timeline (requires live run with partial market data)
3. ⏳ First PROSPECTIVE decision
4. ⏳ Shadow runner success on live market data

## Actual Defects Found

**None** (Session 11 is read-only audit)

The only defect in this audit cycle was the alert state contamination found and fixed in Session 10.

## Code Changes

**None** — read-only audit session.

## Next Human Verification Time

**2026-11-06 (五) after 16:00 Taiwan** — check `logs/hybrid_cron.log` for first entry, then run verification commands in PART B.

If log exists and `today=2026-11-06`: update this document and mark Scheduler → `VERIFIED`.
