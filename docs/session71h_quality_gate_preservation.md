# Session 71H — Quality Gate Preservation Design

**Date**: 2026-11-11  
**Authorization**: STRICT_READ_ONLY / IMPLEMENTATION_PLANNING_ONLY

---

## 1. Existing Quality Gates (Inventory)

The pipeline has two independent QG layers:

### Layer 1: Data Quality Gate (QG-1~QG-7)
**Location**: `src/research/dailyprice_quality_gate.py`  
**Called from**: `backfill_daily_prices.py:504-505`  
**Runs**: Per-date, before every write (once for TWSE, once for TPEx)  
**Character**: HARD BLOCK — data not written if any QG fails

| Check | Rule | Purpose |
|---|---|---|
| QG-1 | OHLC: open/close ≤ high, open/close ≥ low | Structural integrity |
| QG-2 | Price bounds: 0.1 ≤ price ≤ 20000 | Outlier rejection |
| QG-3 | Volume ≥ 0 | Non-negative volume |
| QG-4 | No intra-batch duplicate stock_id+date pairs | No self-collision |
| QG-5 | api_date == target_d | **Anti-stale guard** (most critical) |
| QG-6 | Stock coverage: TWSE≥300, TPEx≥50 | Anti-partial-fetch |
| QG-7 | Benchmark 0050 present (TWSE only) | Benchmark anchor |

### Layer 2: Post-Write Freshness Gate
**Location**: `src/research/full_market_freshness_gate.py`  
**Called from**: `hybrid_shadow_cron.py:376`  
**Runs**: After all dates written; retries up to 3×30min  
**Character**: SOFT BLOCK — data already written, pipeline stage blocked

| Status | Meaning |
|---|---|
| `FULL_MARKET_FRESH` | ≥5000 stocks with today's date in SQLite |
| `PARTIAL_MARKET_UPDATE` | >0 stocks updated but <5000 |
| `BENCHMARK_ONLY_UPDATED` | Only 0050 updated |
| `PROVIDER_NOT_READY` | 0050 last_date < today |
| `STALE` | last_date significantly behind today |
| `MARKET_CLOSED` | Non-trading day |
| `UNKNOWN` | Error |

**Retryable**: PROVIDER_NOT_READY, PARTIAL_MARKET_UPDATE, BENCHMARK_ONLY_UPDATED  
**Constant**: `MIN_COVERED_STOCKS = 5000`

---

## 2. Three-Layer Safety Architecture

The proposed design adds a third layer (Scheduler Safety Guard) BEFORE the existing two:

```
┌─────────────────────────────────────────────────────────────────────┐
│  Layer 0: Scheduler Safety Guards (NEW)                              │
│  hybrid_shadow_cron.py                                               │
│                                                                     │
│  FileLock → Calendar Check → Data Readiness → Validity Window →      │
│  Same-day Guard                                                      │
│                                                                     │
│  BLOCK: BLOCKED_LOCK / SKIPPED_NON_TRADING_DAY / DATA_NOT_READY /   │
│         EXECUTION_WINDOW_EXPIRED / ALREADY_RAN_TODAY                 │
│  Exit: 0 (clean)                                                    │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ PASS (all guards cleared)
┌──────────────────────────────▼──────────────────────────────────────┐
│  Layer 1: Data Quality Gate (EXISTING, UNCHANGED)                    │
│  backfill_daily_prices.py → dailyprice_quality_gate.py               │
│                                                                     │
│  QG-1 through QG-7, per-date, before each write                     │
│  BLOCK: skip date, append to errors[]                               │
│  Idempotent: INSERT OR IGNORE                                       │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ PASS (data written to SQLite)
┌──────────────────────────────▼──────────────────────────────────────┐
│  Layer 2: Post-Write Freshness Gate (EXISTING, UNCHANGED)            │
│  hybrid_shadow_cron.py → full_market_freshness_gate.py               │
│                                                                     │
│  MIN_COVERED_STOCKS=5000; retries 3×30min                           │
│  BLOCK: BLOCKED_STALE_DATA / BLOCKED_PARTIAL_MARKET                  │
│  Exit: 0 (clean, allows retry)                                      │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ FULL_MARKET_FRESH
                              ↓
                      Shadow runner + Backup
```

---

## 3. Preservation Rules

### Rule P-1: Layer 0 Guards MUST NOT Bypass Layer 1 or Layer 2

The scheduler safety guard (Layer 0) is BEFORE data processing. It does not replace or weaken any data quality check.

| Guard | May bypass QG? | May bypass Freshness? |
|---|---|---|
| FileLock → BLOCKED_LOCK | N/A (no data fetch) | N/A |
| Calendar → SKIPPED | N/A (no data fetch) | N/A |
| Data readiness → DATA_NOT_READY | N/A (no data fetch) | N/A |
| Validity window → EXPIRED | N/A (no data fetch) | N/A |
| Same-day guard → ALREADY_RAN_TODAY | N/A (no data fetch) | N/A |

None of the Layer 0 guards reach the data layer. They all exit before Stage 4 (backfill subprocess). **QG bypass risk: NONE.**

### Rule P-2: QG-5 (api_date == target_d) is the Ultimate Stale-Data Guard

Even if the scheduler fires 4 hours late (catch-up at 20:00 CST), QG-5 will reject any TWSE response where `api_date != target_date`. This is the definitive protection against stale data being written.

The validity window guard (Layer 0) is a belt+suspenders protection: it prevents execution after 20:00 CST, but even without it, QG-5 would reject wrong-date data.

### Rule P-3: Freshness Gate Thresholds Must Not Be Changed

`MIN_COVERED_STOCKS = 5000` in both `backfill_daily_prices.py` and `full_market_freshness_gate.py`. These must remain consistent. Any migration work must not change these constants.

### Rule P-4: Per-Date Atomicity is Preserved

Each date is committed independently (`conn.commit()` per date at `backfill_daily_prices.py:546`). A crash after committing 3 dates leaves those 3 dates written. The next run's `_find_missing_dates()` will skip them. This idempotency is a core property and must not be changed.

### Rule P-5: QG Failure on a Date Does Not Block Other Dates

If Nov 06 passes QG and Nov 07 fails QG-5 (stale data), Nov 06 is still written. Nov 07 is added to `errors[]` and skipped. This partial-write behavior is correct and idempotent.

---

## 4. New Guards Must Not Interfere with Existing QG

| Proposed change | QG-1~7 preserved? | Freshness gate preserved? |
|---|---|---|
| Validity window guard | YES — exits before Stage 4 | YES — not reached |
| Same-day SUCCESS guard | YES — exits before Stage 4 | YES — not reached |
| FileLock warning on backfill standalone | YES — QG still runs | YES — not reached |
| launchd migration (scheduler change only) | YES — no code change | YES — no code change |

---

## 5. Interaction with BLOCKED_STALE_DATA State

When the pipeline returns `BLOCKED_STALE_DATA`:
- Backfill HAD run (exit 0)
- QG may have blocked some dates (api_date mismatch)
- Freshness gate exhausted retries
- Data for today NOT in SQLite (or incomplete)

Same-day guard ALLOWS retry in this state (see `session71h_same_day_guard_design.md`).

On retry:
1. `_find_missing_dates()` returns today's date (not covered or partial coverage)
2. QG-5 runs again on fresh fetch
3. If TWSE now has today's data: QG-5 passes → data written → freshness gate passes → SUCCESS
4. QG behavior: **IDENTICAL** to first run

---

## 6. What Would Break QG Preservation

The following actions would break QG preservation and are PROHIBITED:

| Action | Why Prohibited |
|---|---|
| Add `--skip-qg` flag to backfill | Removes data integrity check |
| Lower `MIN_COVERED_STOCKS` | Accepts partial market data |
| Remove QG-5 date check | Allows stale data in SQLite |
| Run backfill in `execute=False` mode from wrapper | No writes, QG still runs but no-op |
| Remove freshness gate | No post-write verification |
| Add same-day guard INSIDE backfill subprocess | Could prevent legitimate retry writes |

None of these are proposed. All are explicitly excluded from the implementation plan.

---

## 7. Verdict

| Item | Status |
|---|---|
| **QG-1~QG-7 preservation** | `PRESERVED` — no proposed change touches backfill internals |
| **Freshness gate preservation** | `PRESERVED` — no proposed change touches freshness gate |
| **New guards bypass risk** | `NONE` — all new guards exit before data fetch |
| **Per-date atomicity** | `PRESERVED` |
| **QG-5 stale data guard** | `PRESERVED` — ultimate anti-stale check regardless of scheduler timing |
| **Overall** | `QUALITY_GATE_PRESERVATION_VERIFIED` |
