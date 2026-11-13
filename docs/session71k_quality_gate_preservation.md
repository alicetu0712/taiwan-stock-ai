# Session 71K — Quality Gate Preservation

**Session**: 71K  
**Verdict**: `QG_PRESERVED_VERIFIED`

---

## 1. Quality Gate Architecture (Confirmed from Code)

The QG runs INSIDE `backfill_daily_prices.py` as a subprocess. The integrated wrapper does NOT touch QG logic.

### Guard vs QG Layering:

```
Layer 0: Scheduler Safety Guards (new, in wrapper)
  └── Execution Window Guard
  └── Same-day State Guard
  └── FileLock

  [PASS] ↓

Layer 1: Data Quality Gates (backfill subprocess — UNCHANGED)
  ├── QG-1: OHLC bounds
  ├── QG-2: Price bounds
  ├── QG-3: Volume ≥ 0
  ├── QG-4: No intra-batch duplicates
  ├── QG-5: api_date == target_date
  ├── QG-6: TWSE ≥ 300 stocks, TPEx ≥ 50
  └── QG-7: 0050 present in TWSE

  [PASS] ↓

Layer 2: Post-write Freshness Gate (wrapper — UNCHANGED)
  └── check_market_freshness() ≥ 5000 non-0050 stocks today
  └── Retry policy: 3 × 30 min for recoverable statuses
```

**Guards (Layer 0) exit BEFORE Layer 1.** QG can never be bypassed by the guard path.

---

## 2. Guard → QG Relationship

| Guard Status | Does QG Run? | Explanation |
|---|---|---|
| Window rejected | NO | Pipeline returns before lock acquired |
| State guard rejected | NO | Pipeline returns after lock acquired but before backfill |
| Lock rejected | NO | Pipeline returns before backfill |
| Guard ALLOWED | YES (backfill subprocess runs) | Normal path |

**If guard rejects, QG never runs.** This is CORRECT behavior — QG only makes sense if data can be written, which requires passing the guards.

**If guard PASSES, QG runs normally.** Guards add no bypass path to QG.

---

## 3. QG Result Mapping

| QG Outcome | `write_committed` | Wrapper Status | Retry? |
|---|---|---|---|
| QG-5 fail (api_date mismatch) | False | `BLOCKED_STALE_DATA` | YES |
| QG-6 fail (insufficient stocks) | False | `BLOCKED_STALE_DATA` | YES |
| QG pass, freshness PARTIAL | False | `BLOCKED_PARTIAL_MARKET` | YES |
| QG pass, freshness FULL | **True** | `SUCCESS` | NO |
| QG blocked, 3 retries exhausted | False | `BLOCKED_STALE_DATA` | YES (next window) |

---

## 4. Zero-change Verification

| Component | Location | Modified? |
|---|---|---|
| QG-1 ~ QG-7 logic | `src/research/dailyprice_quality_gate.py` | NO |
| QG thresholds | `dailyprice_quality_gate.py` | NO |
| Provider API date check (QG-5) | `backfill_daily_prices.py` | NO |
| `check_market_freshness()` | `src/research/full_market_freshness_gate.py` | NO |
| Freshness thresholds (≥5000) | `full_market_freshness_gate.py` | NO |
| Retry policy (3 × 30 min) | `hybrid_shadow_cron_integrated.py` | NO |
| RC-2 filter (`len(sid) > 4`) | `backfill_daily_prices.py` | NO |
| Trading calendar | `src/core/trading_calendar.py` | NO |

---

## 5. Post-write Gate Semantics (Unchanged)

The integrated wrapper treats `FULL_MARKET_FRESH` as the trigger for `write_committed=True`. This is a NEW semantic added on top of the existing behavior. The underlying `check_market_freshness()` logic and thresholds are unchanged.

**QG FAIL ≠ No data written (always true)**:
- QG-5 fail (api_date mismatch): No data written ✓
- QG-6 fail (insufficient stocks): No data written ✓

**QG PASS + Freshness PASS = Data written (always true)**:
- `FULL_MARKET_FRESH` requires ≥5000 non-0050 stocks with today's date in SQLite
- This can ONLY be true if backfill wrote those rows
- Therefore `write_committed=True` is a sound proxy ✓

---

## 6. QG Preservation Test Evidence

| Test | What it verifies |
|---|---|
| IT-19 | QG blocked (STALE) → `write_committed=False` |
| IT-20 | Freshness PASS → `write_committed=True` |
| IT-21 | Shadow fails after write → `write_committed` stays True |
| IT-22 | Backfill fails → `write_committed=False` |
| IT-09 | WRITE_COMMITTED blocks re-write (P0) |
| IT-10 | SHADOW_FAILED + write_committed → still blocks re-write (P0) |

**All 6 tests PASS. `QG_PRESERVED_VERIFIED`.**
