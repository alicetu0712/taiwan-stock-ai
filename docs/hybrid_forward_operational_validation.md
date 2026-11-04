# Hybrid Forward Shadow — Operational Validation Report

**Rule version:** hybrid_v1  
**Rule freeze date:** 2026-11-05  
**Freeze commit:** 6602c3b  
**Report date:** 2026-11-05  
**Status:** DEPLOYMENT READY (local runner) | CONDITIONAL ENGINEERING | INSUFFICIENT DATA (strategy verdict)

---

## Executive Summary

The Hybrid Forward Shadow system satisfies all operational correctness requirements needed to accumulate
trustworthy out-of-sample (OOS) forward evidence. The core principle:

> 今天產生的 Hybrid 決策，必須在今天被可靠地保存；未來只能驗證它，不能偷偷改寫它。

This report documents the validation of each sub-system against that principle.

---

## A. Rule Freeze Verification

| Check | Result |
|-------|--------|
| `MODEL_VERSION` v8.0 unchanged | PASS — not touched |
| `foe_v1` thresholds unchanged | PASS — not touched |
| `BUY / STRONG BUY` score gates unchanged | PASS — not touched |
| `RULE_FREEZE_DATE` = 2026-11-05 | PASS — hardcoded in `hybrid_forward_db.py` |
| Freeze commit reference | 6602c3b (hybrid_entry_strategy.py + tests) |
| `RULE_VERSION` = "hybrid_v1" | PASS — constant in `hybrid_entry_strategy.py` |

---

## B. Data Source Integrity & Capture Classification

Every `hybrid_forward_decision` row is tagged with one of four classifications:

| Class | Meaning | Valid for OOS? |
|-------|---------|---------------|
| `PROSPECTIVE` | trade_date ≥ 2026-11-05 AND captured ≤ 1 trading day late | **YES** |
| `LATE_CAPTURE` | trade_date ≥ freeze date BUT captured > 1 trading day late | No — timing bias |
| `RETROSPECTIVE_RECONSTRUCTION` | trade_date < 2026-11-05 (pre-freeze) | No — in-sample |
| `INVALID_DATA` | input_data_as_of < trade_date (future data used as inputs) | No — look-ahead |

Rule: `classify_capture()` in `hybrid_forward_db.py` applies these labels at insert time, before any
data is written. The label is immutable after insertion.

Stale data guard: if `DailyPrice.last_date` is more than 7 calendar days before `trade_date`, the run
returns `BLOCKED_STALE_DATA` and writes no decisions.

---

## C. Append-Only Decision Integrity

### Schema guarantees

```sql
UNIQUE(stock_id, trade_date, rule_version)  -- on hybrid_forward_decision
UNIQUE(decision_id, horizon, calculation_version)  -- on hybrid_forward_outcome
```

### Decision hash

Each inserted decision includes:
- `decision_hash = sha256(hybrid_action | rule_reason | rule_priority | rule_version)[:16]`
- `input_data_hash = sha256(stock_id | trade_date | market_regime | ma20_slope | ma20_trend | ma20_gap_pct | v2_entry_label | input_data_as_of)[:16]`

On re-run with the same PK:
- Same decision_hash → `INSERT OR IGNORE` skips silently (idempotent)
- Different decision_hash → raises `ConflictError` and sets run status to `CONFLICT`

**The original record is NEVER modified.** `UPDATE` on `hybrid_forward_decision` is explicitly forbidden
by the access layer. Only `hybrid_forward_outcome` rows track evolving calculation results.

### Decision/Outcome separation

`hybrid_forward_decision` stores the signal that was generated today.  
`hybrid_forward_outcome` is a separate table linked by `decision_id`, filled in once the holding period
matures. Recalculating an outcome never touches the original decision row.

---

## D. Daily Runner Reliability

Runner: `scripts/run_hybrid_forward_shadow.py`

### Run status enum

| Status | Meaning |
|--------|---------|
| `SUCCESS` | All decisions inserted, no errors |
| `PARTIAL` | Some insertions failed, see `error_summary` |
| `SKIPPED_NON_TRADING_DAY` | trade_date is not a Taiwan trading day |
| `BLOCKED_STALE_DATA` | DailyPrice data is > 7 calendar days stale |
| `BLOCKED_MISSING_SIGNALS` | No ForwardSignal entries for the requested date |
| `FAILED` | Unhandled exception |
| `CONFLICT` | Same PK produced a different decision on re-run |

### Non-trading day check

Built from 0050 DailyPrice dates (Taiwan trading calendar proxy). Runs on a non-trading day return
`SKIPPED_NON_TRADING_DAY` and write no data.

### Retry / recovery

The `--backfill-outcomes-only` flag recalculates outcomes for already-matured decisions without inserting
new decision rows. The `--force-stale` flag bypasses the stale data check for testing or catch-up runs
(any resulting records are tagged `LATE_CAPTURE` or `RETROSPECTIVE_RECONSTRUCTION` as appropriate).

Every run is recorded in `hybrid_forward_run_log` regardless of outcome.

---

## E. GitHub Actions Scheduling

**STATUS: DEPLOYMENT BLOCKED — pending persistence decision.**

Workflow file: `.github/workflows/hybrid_forward_shadow.yml`

Schedule cron (commented out): `30 7 * * 1-5` (UTC 07:30 = Taiwan 15:30, Mon–Fri)

The workflow is blocked because GitHub Actions runners are ephemeral — `data/platform.db` would be lost
after each run. A persistence backend must be chosen before enabling the schedule:

| Option | Trade-offs |
|--------|------------|
| A. GitHub artifact cache | Simple, free; SQLite binary in cache is fragile for large DBs |
| B. S3/GCS persistent SQLite | Reliable; requires cloud secrets + I/O overhead |
| C. Dedicated research PostgreSQL | Most robust; requires schema port to psycopg2 |
| D. Local cron (current) | No external dependency; requires persistent machine uptime |

**Current recommendation:** Option D (local cron) for the first 3 months of PROSPECTIVE accumulation,
then revisit if uptime becomes unreliable.

---

## F. Trading-Day Maturity

Maturity dates are computed using `TradingCalendar` (class in `hybrid_trading_calendar.py`), built from
0050 DailyPrice proxy dates. Natural (calendar) days are **not** used.

| Horizon | Method |
|---------|--------|
| 5D | `add_trading_days(entry_date, 5)` |
| 10D | `add_trading_days(entry_date, 10)` |
| 20D | `add_trading_days(entry_date, 20)` |

Where `entry_date = next_trading_day(trade_date)` (the first trading day on or after trade_date).

A decision is `MATURED` once `today >= maturity_date` and both entry and exit prices are available.

---

## G. Dashboard Operational Health

The "🔀 Hybrid 策略" tab in `entry_timing_research.py` now shows four panels:

| Panel | Content |
|-------|---------|
| G1. 系統健康 | Latest run date, status, consecutive failures, conflict count, data freshness |
| G2. 前瞻記錄池 | PROSPECTIVE / LATE_CAPTURE / RETROSPECTIVE / INVALID counts; matured 5D/10D/20D; pending; unique stocks and dates |
| G3. 前瞻績效 | Only shown when matured_20d > 0; shows "尚無足夠前瞻樣本" otherwise (never shows 0% as a performance claim) |
| G4. 名詞白話解釋 | Plain-language definitions of PROSPECTIVE, Matured, Paired Delta, Conflict, LATE_CAPTURE, RETROSPECTIVE |

---

## H. Test Coverage

56 tests (FS01–FS55 + FS56 operational summary) in `tests/test_hybrid_forward_shadow.py`.

| Category | Tests | Coverage |
|----------|-------|----------|
| TradingCalendar | FS01–FS05 | is_trading_day, next_trading_day, add_trading_days, count_trading_days |
| Capture classification | FS06–FS10 | PROSPECTIVE/LATE_CAPTURE/RETROSPECTIVE/INVALID_DATA/edge cases |
| Decision hashing | FS11–FS14 | Same inputs → same hash; different inputs → different hash |
| Append-only insert | FS15–FS20 | Idempotent skip, ConflictError on hash mismatch, insert returns row_id |
| Decision/outcome separation | FS21–FS25 | Outcome not in decision table; delete outcome doesn't touch decision |
| Run log | FS26–FS30 | SUCCESS/PARTIAL/CONFLICT/BLOCKED_STALE logged correctly |
| Stale data guard | FS31–FS35 | > 7 days → BLOCKED; ≤ 7 days → allowed |
| Outcome maturity | FS36–FS42 | 5D/10D/20D maturity dates using TradingCalendar |
| Non-trading day skip | FS43–FS45 | Weekend and holiday → SKIPPED |
| Idempotency | FS46–FS48 | Double-run same date → 0 conflicts |
| Full shadow run | FS49–FS52 | Pre-freeze retrospective; idempotent; no-data blocked |
| Operational summary | FS53–FS55 | get_operational_summary returns correct counts |

Total tests (project): 1448 passing.

---

## Verdict

| Dimension | Verdict |
|-----------|---------|
| Engineering correctness | CONDITIONAL PASS — all integrity constraints satisfied; persistence for GH Actions TBD |
| Operational readiness | DEPLOYMENT READY for local runner |
| Strategy evidence | INSUFFICIENT DATA — 0 PROSPECTIVE records as of 2026-11-05 (rule freeze day) |

The system is correctly built. Strategy verdict requires accumulation of ≥ 50 matured PROSPECTIVE records
(earliest possible: approximately 2027-01 for 20D horizon).
