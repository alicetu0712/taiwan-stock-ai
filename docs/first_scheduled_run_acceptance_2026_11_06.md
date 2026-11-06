# First Scheduled Run Acceptance Audit — 2026-11-06

**Audit Date:** 2026-11-06 01:55 CST  
**Git HEAD:** 381c17b  
**Auditor:** Session 24 SRE Audit  
**Scope:** First cron-scheduled hybrid shadow run; first PROSPECTIVE decision verification

---

## 1. Executive Summary

| Question | Answer |
|---|---|
| Cron installed and correct | ✅ Yes |
| Cron ever triggered | ❌ No — `hybrid_cron.log` does not exist |
| Scheduled 16:00 CST reached | ❌ No — current time 01:55 CST, trigger is 14 hours away |
| Prior runs on Nov 5 | Manual only (not cron-scheduled) |
| Nov 5 trigger_source="cron_scheduled" in state | Misleading — detection bug (stdout not TTY) |
| DailyPrice Nov 6 | 0 rows (cron hasn't run) |
| PROSPECTIVE decisions | 0 (none yet) |
| Existing decisions upgraded | No — all 21 remain RETROSPECTIVE_RECONSTRUCTION |
| Security issues | None |

**Classification: SCHEDULED_RUN_NOT_TRIGGERED** — The 2026-11-06 16:00 cron has not fired. This is expected: the audit runs at 01:55 CST, 14 hours before the first scheduled execution window.

The system is in a valid pre-trigger state. All pre-conditions for a successful 16:00 run are met. One PARTIAL_MARKET alert from Nov 5 remains unresolved (non-blocking for Nov 6).

---

## 2. Trigger Evidence

### hybrid_cron.log existence

```
$ ls -la logs/hybrid_cron.log
ls: logs/hybrid_cron.log: No such file or directory
```

**This is the definitive evidence that cron has never fired.** The cron command is:
```
0 16 * * 1-5  python3 scripts/hybrid_shadow_cron.py --execute >> logs/hybrid_cron.log 2>&1
```

If cron had ever executed, `>>` would have created the file (even if empty). The file's absence proves no scheduled execution has occurred.

### trigger_source Detection Bug

`.cron_state.json` shows `"trigger_source": "cron_scheduled"` from the Nov 5 18:28 CST run. This is **misleading**:

```python
# hybrid_shadow_cron.py line 666
trigger_source = "manual" if sys.stdout.isatty() else "cron_scheduled"
```

When a manual run redirects stdout (non-TTY), `trigger_source` is set to `"cron_scheduled"`. The Nov 5 18:28 run was a manual test after installation (cron was installed at 18:09 CST, cron only fires at 16:00). **This state entry does NOT represent a scheduled trigger.**

### Evidence Table

| Evidence | Expected | Actual | Verdict |
|---|---|---|---|
| Cron Installed | Yes | ✅ 1 entry, correct schedule | PASS |
| Cron Daemon Running | Yes | ✅ `/usr/sbin/cron` PID active | PASS |
| Scheduled Trigger (16:00) | 2026-11-06 16:00 | ❌ Not yet (01:55 CST) | NOT_YET |
| `hybrid_cron.log` Exists | Yes (after first run) | ❌ File absent | NOT_TRIGGERED |
| Nov 6 DailyPrice | After backfill | 0 rows | NOT_YET |
| Lock File | None | ✅ No lock file | PASS |
| Process Running | None expected | ✅ No hybrid processes | PASS |
| DB Integrity | ok | ✅ integrity_check=ok, fk=0 | PASS |
| Retrospective Decisions | 21 (unchanged) | ✅ 21, fp=fc4056bb08b5a6b0 | PASS |

---

## 3. Attempt Timeline

### Scheduled Nov 6 16:00 (NOT YET OCCURRED)

| Slot | Scheduled | Status |
|---|---|---|
| Attempt 1 | 2026-11-06 16:00 CST | PENDING (14 hours away) |
| Attempt 2 | 2026-11-06 16:30 CST | PENDING |
| Attempt 3 | 2026-11-06 17:00 CST | PENDING |
| Attempt 4 | 2026-11-06 17:30 CST | PENDING |

### Nov 5 Manual Run History (NOT scheduled cron)

Cron was installed at 18:09 CST Nov 5 — after the 16:00 slot. All Nov 5 runs were manual.

| Run | Started (UTC) | Started (CST) | Trade Date | Status | Notes |
|---|---|---|---|---|---|
| id=1 | 04:42:02 | 12:42 | 2026-11-05 | SKIPPED_NON_TRADING_DAY | No Nov 5 DailyPrice → DB calendar unaware Nov 5 is trading |
| id=3 | 04:42:30 | 12:42 | 2026-11-04 | SUCCESS (inserted=21) | 21 RETROSPECTIVE decisions for Nov 4 |
| id=5 | 04:42:40 | 12:42 | 2026-11-04 | SUCCESS (inserted=0) | Duplicate prevention (21 already exist) |
| id=7 | 04:42:42 | 12:42 | 2026-11-04 | SUCCESS (inserted=0) | Duplicate prevention |
| id=9 | 09:20:34 | 17:20 | 2026-11-05 | BLOCKED_MISSING_SIGNALS | No full-market Nov 5 data |
| (cron state) | 10:28:50 | 18:28 | 2026-11-05 | BLOCKED_PARTIAL_MARKET | Cron script ran, shadow not invoked; `trigger_source` incorrect |

**Note on SKIPPED_NON_TRADING_DAY for Nov 5:** `run_hybrid_forward_shadow.py` uses `TradingCalendar.from_db(conn)`, a DB-driven calendar built from 0050 DailyPrice dates. At 12:42 CST on Nov 5, no Nov 5 DailyPrice data existed yet → calendar did not include Nov 5 → correctly returned SKIPPED for that date. This is expected behavior when the script is invoked directly without the cron pipeline's backfill step.

**`hybrid_shadow_cron.py` uses `TaiwanTradingCalendar()` (rule-based, not DB-driven) for its own calendar gate** — it will correctly identify Nov 6 as a trading day regardless of backfill state.

---

## 4. Market Data Snapshot (Pre-Trigger State)

As of audit time (01:55 CST Nov 6). **EXECUTION_TIME_DATA_UNVERIFIED** — the 16:00 snapshot cannot be verified until the cron runs.

| Market | Current Max Date | Nov 6 Rows | Coverage | Status |
|---|---|---|---|---|
| 0050 (proxy) | 2026-11-05 | 0 | 567 bars (Jul 2024–Nov 5) | AWAITING_BACKFILL |
| TWSE full market | 2026-11-04 | 0 | 6,957 stocks | AWAITING_BACKFILL |
| TPEx full market | 2026-11-04 | 0 | Included in 6,957 | AWAITING_BACKFILL |

### Critical gaps affecting shadow runner for Nov 6

The shadow runner `_get_signal()` computes signals from DailyPrice using:
```
SELECT close FROM daily_prices WHERE stock_id=? AND date <= ? ORDER BY date DESC LIMIT 100
```

Stocks with gaps Oct 29–Nov 3 (only 1 stock = 0050 on those dates) will have missing bars in the 100-bar lookback. The `MIN_HIST_BARS` check will exclude stocks with insufficient history. This is correct behavior — no decisions for data-deficient stocks.

### OHLC Continuity Gate prediction for Nov 6 at 16:00

After backfill:
- 0050 will have Nov 6 data → gate will check last 30 expected trading days ending Nov 6
- 0050 is continuous Jul 1 2024 – present (through Nov 6 post-backfill)
- **Gate: PASS** (assuming backfill succeeds)
- If backfill fails: gate still checks 0050 → missing Nov 6 → BLOCKED_MISSING_OHLC → shadow runner blocked (correct fail-closed)

---

## 5. Prospective Classification

### RULE_FREEZE_DATE

```python
RULE_FREEZE_DATE = date(2026, 11, 5)  # src/research/hybrid_forward_db.py:33
MAX_PROSPECTIVE_CAPTURE_DAYS = 1       # src/research/hybrid_forward_db.py:38
```

### Classification logic

```python
def classify_capture(trade_date, captured_at, input_data_as_of, trading_days_since_trade):
    if trade_date < RULE_FREEZE_DATE:            → RETROSPECTIVE_RECONSTRUCTION
    if input_data_as_of < trade_date:            → INVALID_DATA
    if trading_days_since_trade <= 1:            → PROSPECTIVE
    else:                                        → LATE_CAPTURE
```

### Current state

| Classification | Count | Trade Date | Comment |
|---|---|---|---|
| RETROSPECTIVE_RECONSTRUCTION | 21 | 2026-11-04 | Nov 4 < RULE_FREEZE_DATE ✓ |
| PROSPECTIVE | 0 | — | Cron not yet triggered |
| LATE_CAPTURE | 0 | — | — |
| INVALID_DATA | 0 | — | — |

### Conditions for Nov 6 PROSPECTIVE

For the Nov 6 16:00 run to produce PROSPECTIVE decisions, all must hold:

| Condition | Verification |
|---|---|
| `trade_date = 2026-11-06 >= RULE_FREEZE_DATE = 2026-11-05` | ✅ True |
| `input_data_as_of >= trade_date` | ✅ True IF backfill inserts Nov 6 data before shadow |
| `trading_days_since_trade = 0 ≤ MAX = 1` | ✅ True (same-day capture) |
| FULL_MARKET_FRESH gate passes | UNKNOWN until cron runs |
| OHLC gate passes | UNKNOWN until backfill |

**Key design guarantee:** The cron pipeline runs backfill BEFORE invoking the shadow runner. So `input_data_as_of` = Nov 6 by the time classification occurs.

### 21 retrospective decisions: classification frozen, cannot be upgraded

The 21 existing RETROSPECTIVE_RECONSTRUCTION decisions for trade_date=2026-11-04 are:
- `trade_date = 2026-11-04 < RULE_FREEZE_DATE = 2026-11-05` → permanently RETROSPECTIVE
- Append-only: no existing record is updated or deleted
- Fingerprint: `fc4056bb08b5a6b0` (verified unchanged)

---

## 6. Data Integrity

### Fingerprints

| Table | Count | Fingerprint | Status |
|---|---|---|---|
| `forward_signals` (SQLite local) | 2,605 | `0927217382eea090` | BASELINE_RECORDED |
| `hybrid_forward_decision` | 21 | `fc4056bb08b5a6b0` | BASELINE_RECORDED |
| `hybrid_forward_run_log` | 9 entries | — | BASELINE_RECORDED |

**PRE_RUN_BASELINE_UNAVAILABLE** — The "before" state for the 16:00 run does not yet exist. The above fingerprints are the current state at 01:55 CST and constitute the baseline for the post-16:00 comparison.

### DB Health

```
integrity_check: ok
fk_violations:   0
journal_mode:    wal
wal_checkpoint:  (0, 0, 0)  # clean
lock_file:       absent
```

### Active processes

No active research writers, no active DB transactions, no lock file. The system is in a clean idle state.

### Shell sessions

~8 `/bin/zsh` sessions visible in `ps aux` are from Claude Code tool calls (spawned by the audit tooling). None are user research writers. No `hybrid_shadow_cron.py` or `run_hybrid_forward_shadow.py` processes are running.

### Alert state

| Alert | Trade Date | Count | Resolved | Impact on Nov 6 |
|---|---|---|---|---|
| STALE_DATA | 2026-11-05 | 16 | ✅ resolved | None — different date |
| SHADOW_FAILED | 2026-11-05 | 8 | ✅ resolved | None — different date |
| PARTIAL_MARKET | 2026-11-05 | 6 | ❌ **unresolved** | None — different trade_date |
| BACKUP_FAILURE | 2026-11-05 | 24 | ✅ resolved | None — different date |

The unresolved PARTIAL_MARKET alert for Nov 5 will NOT block Nov 6 operations. Alert dedup by `(trade_date, alert_type)` — Nov 6 runs will generate new alerts under trade_date=2026-11-06 if needed.

---

## 7. Tests

### V3 research tests (Session 23, completed before this audit)

```
tests/test_v3_entry_strategy.py: 31 passed
Ruff: clean (src/research/v3_entry_strategy.py, tests/test_v3_entry_strategy.py)
```

### Full regression

```
1767 passed, 1 skipped, 962 warnings
```

The 1 skip is `test_PF13_ohlc_gate_live_health` — auto-skips before 16:00 cron (designed behavior).

### Git status

```
M  src/research/v3_entry_strategy.py    # V3 research prototype (uncommitted)
M  tests/test_v3_entry_strategy.py      # V3 tests (uncommitted)
?? docs/v3_entry_timing_research_design.md  # V3 design doc (uncommitted)
```

These uncommitted V3 research files do NOT affect the cron pipeline or hybrid production system.

---

## 8. Issues Found

### Issue 1 — trigger_source detection (LOW, cosmetic)

**Description:** `trigger_source = "manual" if sys.stdout.isatty() else "cron_scheduled"`. Manual runs with redirected stdout (non-TTY) are incorrectly labeled `cron_scheduled` in `.cron_state.json`. The Nov 5 18:28 run created a misleading state.

**Impact:** Dashboard may show "cron_scheduled" for manual runs. No operational impact.

**Remediation:** Replace `sys.stdout.isatty()` with an explicit `--source=manual|cron` flag, or check for the `TERM` environment variable set by cron environments. **Do NOT change until after first scheduled run is verified.**

### Issue 2 — PARTIAL_MARKET alert for Nov 5 unresolved (LOW)

**Description:** `data/.alert_state.json` has `PARTIAL_MARKET` alert with `resolved=false`, count=6, for trade_date=2026-11-05.

**Impact:** None on Nov 6 operations. Alert system will correctly generate a fresh alert for Nov 6 if needed.

**Remediation:** No action required. Alert is informational — Nov 5 never had full market data (only 0050), which was correct behavior.

### Issue 3 — TradingCalendar.from_db() is data-driven (DESIGN NOTE, expected)

**Description:** `run_hybrid_forward_shadow.py` builds its trading calendar from `daily_prices WHERE stock_id='0050'`. Before backfill runs, Nov 6 is not in this calendar.

**Impact:** If shadow runner is invoked directly (without prior backfill), Nov 6 → SKIPPED_NON_TRADING_DAY. This was observed for Nov 5 at 12:42 CST.

**Expected behavior:** The cron pipeline always runs backfill before invoking the shadow runner. After backfill inserts 0050 Nov 6 data, the calendar will correctly include Nov 6. **This is not a bug.**

### Issue 4 — TWSE late-publication risk (MEDIUM, operational)

**Description:** From Session 12 diagnosis: TWSE OpenAPI full-market batch may publish after 17:30 CST. Retry window ends at 17:30. If TWSE is late, the Nov 6 run ends with BLOCKED_PARTIAL_MARKET and 0 PROSPECTIVE decisions.

**Impact:** No PROSPECTIVE decisions for Nov 6; shadow will retry on Nov 7.

**Remediation:** If TWSE publishes after 17:30, run manually:
```bash
python3 scripts/backfill_daily_prices.py --execute
python3 scripts/hybrid_shadow_cron.py --execute
```
But this would generate LATE_CAPTURE (not PROSPECTIVE) decisions for Nov 6.

---

## 9. Final Verdict

### Operational

**UNVERIFIED** — The scheduled 16:00 CST trigger has not occurred (01:55 CST). Pre-conditions are met. First verdict after 17:30 CST.

### Data

**AWAITING_BACKFILL** — Nov 6 DailyPrice: 0 rows. Becomes READY after backfill at 16:00+.

### Prospective

**NONE** — 0 PROSPECTIVE decisions. Expected — no data yet. Becomes VERIFIED_OR_BLOCKED after 17:30 CST depending on TWSE publication timing.

### Overall

**UNVERIFIED** — Pre-trigger state. System configuration correct, no blocking issues found, 1767 tests passing.

---

## 10. Final Questions

| # | Question | Answer |
|---|---|---|
| 1 | 2026/11/06 16:00 Cron 是否真的觸發？ | ❌ 否 — 目前 01:55 CST，觸發在 14 小時後 |
| 2 | 是否有背景執行證據？ | ❌ 否 — `hybrid_cron.log` 不存在（決定性證據） |
| 3 | 是否有四次 Retry？ | ❌ 否 — 尚未觸發 |
| 4 | 每次 Retry 的結果是什麼？ | 未知 — 待 16:00 後驗證 |
| 5 | 0050、TWSE、TPEx 當時是否完整？ | EXECUTION_TIME_DATA_UNVERIFIED |
| 6 | 是否發生 False PASS？ | 未知 — 16:00 前不可驗證 |
| 7 | 是否發生 False BLOCK？ | 未知 — 16:00 前不可驗證 |
| 8 | 是否新增 Hybrid Decisions？ | ❌ 否 — 仍為 21 筆 |
| 9 | 新增多少真正的 PROSPECTIVE Decisions？ | 0 |
| 10 | 21 筆歷史重建資料是否保持原分類？ | ✅ 是 — 全部 RETROSPECTIVE_RECONSTRUCTION，fp 未變 |
| 11 | 是否有重複 Decision？ | ✅ 否 — 無重複（duplicate prevention 在 Nov 4 run_id=fc9dd188/02565324 均 skipped=200）|
| 12 | 是否有 Look-ahead？ | ✅ 否 — `prior_20d_high` 使用 `high[-21:-1]`，`classify_capture` 使用 `input_data_as_of` |
| 13 | ForwardSignals 是否完全不變？ | ✅ 是 — 2605 筆，fp=0927217382eea090 |
| 14 | 是否需要修復 Cron 或 Data Pipeline？ | 不需要（3 個低風險問題，均非阻斷性） |
| 15 | 第一次正式排程能否正式驗收？ | ⏳ PENDING — 需 16:00 後重新驗收 |

---

## 11. Post-16:00 Re-Audit Checklist

執行時間：2026-11-06 17:30–18:00 CST（所有 retry 窗口關閉後）

```bash
# 1. Confirm cron triggered
ls -la logs/hybrid_cron.log
head -50 logs/hybrid_cron.log

# 2. Confirm cron state
cat data/.cron_state.json

# 3. Check DB for new decisions
python3 -c "
import sqlite3
conn = sqlite3.connect('data/platform.db')
rows = conn.execute(\"\"\"
    SELECT trade_date, capture_classification, COUNT(*) 
    FROM hybrid_forward_decision 
    GROUP BY trade_date, capture_classification
\"\"\").fetchall()
for r in rows: print(r)
"

# 4. Check run log for Nov 6
python3 -c "
import sqlite3
conn = sqlite3.connect('data/platform.db')
rows = conn.execute(
    \"SELECT id, trade_date, started_at, inserted_count, status FROM hybrid_forward_run_log ORDER BY id DESC LIMIT 5\"
).fetchall()
for r in rows: print(r)
"

# 5. Check DailyPrice Nov 6
python3 -c "
import sqlite3
conn = sqlite3.connect('data/platform.db')
n = conn.execute(\"SELECT COUNT(DISTINCT stock_id) FROM daily_prices WHERE date='2026-11-06'\").fetchone()
print('Nov 6 stocks:', n[0])
"

# 6. Alert state
cat data/.alert_state.json

# 7. Full regression
python3 -m pytest --tb=no -q
```

---

## 12. Files Changed This Session

| File | Change |
|---|---|
| `src/research/v3_entry_strategy.py` | V3 prototype (Session 23, uncommitted) |
| `tests/test_v3_entry_strategy.py` | V3 tests 31/31 pass (Session 23, uncommitted) |
| `docs/v3_entry_timing_research_design.md` | V3 design doc (Session 23, untracked) |
| `docs/first_scheduled_run_acceptance_2026_11_06.md` | This document (Session 24) |
