# Session 22 — OHLC Integrity, Regression Recovery & Data Completeness Audit

**Date:** 2026-11-06  
**Scope:** PF13/PF20 root cause, DailyPrice completeness, OHLC gate decision audit, V3 data readiness  
**Git HEAD:** 1c42cb3

---

## 1. PF13 / PF20 Root Cause Analysis

### Symptom

```
FAIL tests/test_hybrid_shadow_preflight.py::test_PF13_ohlc_gate_pass_on_real_db
FAIL tests/test_hybrid_shadow_preflight.py::test_PF20_run_preflight_overall_conditional
```

PF13 asserted `result.status == STATUS_PASS`; received `STATUS_BLOCK`.  
PF20 asserted `blocked == []`; received `blocked = ["ohlc_continuity_gate"]`.

### Root Cause: Live Data Dependency

`check_ohlc_continuity_gate()` in `scripts/hybrid_shadow_preflight.py` calls:
```python
today = date.today()
report = gate.check_market(conn, today)
```

`OHLCContinuityGate.check_market(conn, trade_date)` builds the last 30 expected trading days ending on `trade_date` (inclusive) and checks whether 0050 had data on each. When run at 01:15 Taiwan time on 2026-11-06:

| Check | Value | Result |
|---|---|---|
| `date.today()` | 2026-11-06 | Trade date passed to gate |
| `is_trading_day(2026-11-06)` | True (Friday) | Proceeds to continuity check |
| `last_0050_date` | 2026-11-05 | Stale check: 1d ≤ 7d tolerance → passes |
| Nov 6 in 30-day expected window | Yes | 0050 has no Nov 6 data → EXPECTED_DATA_MISSING |
| Gate result | BLOCKED_MISSING_OHLC | missing=1 |

**Classification: Test Fixture Defect.** The gate logic is correct — it correctly detects that today's data is absent. The tests were written when today (Nov 5) had data, and failed the following morning before the cron collected today's data at 16:00.

The gate is designed to run after market close (16:00 Taiwan), when today's data is already in DB. Running tests before that time creates a structural day-boundary failure.

### Fix Applied

**PF13** (`tests/test_hybrid_shadow_preflight.py`):  
Added `patch("scripts.hybrid_shadow_preflight.date")` with `mock_date.today.return_value = date(2026, 11, 5)` — the last confirmed data date with gate PASS (present=30, missing=0).

**PF20** (`tests/test_hybrid_shadow_preflight.py`):  
Same pattern, plus `mock_date.fromisoformat = date.fromisoformat` to preserve ISO parsing in `check_dailyprice_freshness()`.

**New test `test_PF13_ohlc_gate_live_health`** (auto-skips before cron):
```python
def test_PF13_ohlc_gate_live_health():
    # Skips automatically if today has no 0050 data yet
    if today_count == 0:
        pytest.skip(f"No 0050 data for {date.today()} — run after cron (16:00 Taiwan)")
    result = check_ohlc_continuity_gate()
    assert result.status == STATUS_PASS
```

### Regression Result

```
1736 passed, 1 skipped (live health auto-skip)
```
Previous baseline: 1734 passed + 2 failures (PF13, PF20).

---

## 2. DailyPrice Completeness Audit

### 0050 (Market Proxy)

| Metric | Value |
|---|---|
| Date range | 2024-07-01 → 2026-11-05 |
| Total rows | 567 |
| Nov 6 data | 0 (not yet collected) |
| OHLC gate result for Nov 5 | PASS (present=30, missing=0) |

0050 provides continuous daily coverage. The OHLC continuity gate uses 0050 as market proxy — gate PASS for all dates ≤ Nov 5.

### Full Market (Individual Stocks)

| Date | Stock Count | Source |
|---|---|---|
| 2026-10-16 | 655 | Earlier backfill |
| 2026-10-21 | 655 | Earlier backfill |
| 2026-10-22 | 655 | Earlier backfill |
| 2026-10-27 | 1 (0050 only) | No full-market backfill |
| 2026-10-28 | 656 | Earlier backfill |
| 2026-10-29 | 1 (0050 only) | No full-market backfill |
| 2026-10-30 | 1 (0050 only) | No full-market backfill |
| 2026-11-02 | 1 (0050 only) | No full-market backfill |
| 2026-11-03 | 1 (0050 only) | No full-market backfill |
| **2026-11-04** | **6,957** | **Historical backfill (Approval D)** |
| 2026-11-05 | 1 (0050 only) | Manual 0050 fetch only |
| 2026-11-06 | 0 | Cron not yet run |

**Key finding:** Full market data is available through 2026-11-04 for 6,957 stocks. The five sessions between the last partial backfill (Oct 28) and the full Nov 4 backfill (Oct 29-30, Nov 2-3) are missing for individual stocks.

### Impact on Shadow Cron (First Run: Nov 6 16:00)

The first scheduled cron run at 16:00 today will compute signals for Nov 6. For EntryTimingAnalyzer with `lookback=90`:
- **Most stocks:** 90-bar history loaded ending Nov 4 (6,957 stocks have data). The missing sessions (Oct 29-30, Nov 2-3, Nov 5) represent gaps within the lookback window.
- **OHLC gate (market-level):** PASS for Nov 6 once today's 0050 data is collected.
- **Stock-level gate:** `check_stock()` checks whether each stock had data on the last 20 market-open dates per 0050. If 0050 had data on Oct 29-30, Nov 2-3 (it does), but individual stocks did not, those stocks will get `BLOCKED_MISSING_OHLC` from the stock-level gate.

**Risk:** Some stocks may have stock-level gate BLOCKED due to Oct 29-Nov 3 gaps. The shadow cron's gate checks handle this — blocked stocks produce no hybrid decision. This is the designed safe behavior (block rather than produce signals with gapped data).

---

## 3. OHLC Gate Decision Audit

### Gate Logic Verified Correct

The gate uses three sequential checks:

1. **Not a trading day:** → `NOT_APPLICABLE` (no block, no signal)
2. **Stale tolerance:** `(trade_date - last_0050_date).days > 7` → `BLOCKED_STALE_DATA`
3. **Continuity window:** Any expected trading day in last 30 without 0050 data → `BLOCKED_MISSING_OHLC`

UNKNOWN_CALENDAR (calendar says holiday, DB has data) → warning only, does NOT block. Calendar was corrected for 3 dates (including 2026-10-09 國慶日補假) in a prior session.

### False PASS / False BLOCK Paths

| Scenario | Gate Behavior | Assessment |
|---|---|---|
| Today not yet in DB (pre-16:00) | BLOCKED_MISSING_OHLC | Correct — data not ready |
| Yesterday's data present, today is holiday | NOT_APPLICABLE | Correct — no signal needed |
| 7-day stale (data interrupted) | BLOCKED_STALE_DATA | Correct |
| 1–6 day calendar gap (long weekend) | Passes stale check; continuity covers it | Correct |
| Today in DB, 30-day window complete | PASS | Correct |

**No false PASS / false BLOCK logic bugs found.** The failures were test isolation issues, not gate logic defects.

---

## 4. Cron Status

| Item | Status |
|---|---|
| Cron installed | Yes (`0 16 * * 1-5`, UTC+8 → Asia/Taipei 16:00) |
| First execution | 2026-11-06 16:00 (not yet run as of 01:15) |
| Last execution date | None (no history yet) |
| State file | No prior execute date recorded |
| PF11 (DailyPrice freshness) | PASS (last=Nov5, gap=1d ≤ STALE_DAYS_WARN=1) |
| PF13 (OHLC gate) | PASS for Nov5 fixture; live check will PASS after 16:00 |

No cron execution bugs to investigate — the cron has not run yet.

---

## 5. V3 Data Readiness Assessment

**Current state:** v2_research_v1 and v2_research_v2 are identical (0 label differences — V1_ALREADY_CONTAINS_V2_FIX). No meaningful V1/V2 strategy difference exists. V3 requires a new algorithm.

**Schema readiness for V3:** `V2ShadowSignal.research_version` is a free-text field; inserting `'v2_research_v3'` requires no schema migration. UniqueConstraint `(trade_date, stock_id, research_version)` handles isolation automatically.

**Data readiness for V3 shadow:**

| Requirement | Status |
|---|---|
| 0050 continuity (gate proxy) | ✅ Through Nov 5; Nov 6 available after cron |
| Full market history (90-bar lookback) | ✅ 6,957 stocks through Nov 4 |
| Nov 5 individual stock data | ⚠️ Missing (only 0050) — gap for Nov 5 close in lookback |
| Oct 29-Nov 3 individual stock data | ⚠️ Missing — gap for 5 sessions in lookback |
| SQLite schema | ✅ `hybrid_forward_decision`, `hybrid_research_cache` tables present |

**Conclusion:** V3 data is **conditionally ready**. 0050 gate will PASS. Individual stock signals may have stock-level gate BLOCKED for stocks where Oct 29-Nov 3 sessions are required for the lookback. This is safe (blocked = no signal, not wrong signal). V3 can proceed once the algorithm is specified; data gaps will naturally fill as cron runs daily.

---

## 6. Files Changed

| File | Change |
|---|---|
| `tests/test_hybrid_shadow_preflight.py` | PF13: add `date.today` mock (Nov 5 fixture); new `test_PF13_ohlc_gate_live_health` (auto-skip); PF20: add `date.today` mock + `fromisoformat` passthrough |

**Lines changed:** ~20  
**Tests:** 1736 passed, 1 skipped (from 1734 passed + 2 failed)
