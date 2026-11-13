# Session 71L — Quality Gate & RC-2 Preservation

**Session**: 71L  
**Verdict**: `QG_AND_RC2_PRESERVED_VERIFIED`

---

## Quality Gate Architecture

```
Layer 0: Scheduler Safety Guards (S71J/K/L)
  └── Window guard (16:00-20:00 CST)
  └── Same-day state guard (ALREADY_RAN / WRITE_COMMITTED / CONCURRENT / UNKNOWN)
  └── BackfillEntryGuard (direct entry detection)

Layer 1: Data Quality Gates (QG-1 ~ QG-7)
  └── Inside backfill_daily_prices.py (UNCHANGED)
  └── Per-date row count, OHLCV completeness, etc.

Layer 2: Post-write Freshness Gate
  └── check_market_freshness() in hybrid_shadow_cron.py (UNCHANGED)
  └── FULL_MARKET_FRESH requires non-benchmark stock count ≥ minimum
```

**Key property**: Layer 0 guards fire BEFORE backfill subprocess is called. They cannot modify or bypass Layer 1/2 logic.

---

## RC-2 Filter Preservation

| Item | Value | Status |
|---|---|---|
| `backfill_daily_prices.py` SHA256 | `4eb6eacf6c65df52aae037731e66e4573a8ae929af807c0fbd7c1adcac4c5afb` | ✓ UNCHANGED |
| RC-2 filter location | lines 93-100 | ✓ UNCHANGED |
| RC-2 logic | `if len(sid) > 4: return True` | ✓ UNCHANGED |

The RC-2 filter is in `backfill_daily_prices.py`, which is **READ ONLY** throughout all S71L work. No code path in the guard module, protected script, or integrated wrapper touches the filter.

---

## Guard Module Isolation Verification

The guard module (`scheduler_safety_guards.py`) contains:
- No imports from `backfill_daily_prices.py`
- No imports from `hybrid_shadow_cron.py`
- No calls to `check_market_freshness()`
- No calls to any QG function (QG-1~QG-7)
- No `sqlite3.connect()` calls
- No `psycopg2`/`asyncpg` calls

Verified by: L-14 (QG isolation), L-15 (no HTTP calls), L-16 (no DB writes).

---

## Test Coverage

| Test | What it checks | Result |
|---|---|---|
| L-13 | RC-2 hash unchanged | ✓ PASS |
| L-14 | Guard module has no QG imports/calls | ✓ PASS |
| L-15 | Guard module has no TWSE/TPEx HTTP calls | ✓ PASS |
| L-16 | Guard module has no DB write calls | ✓ PASS |
| L-17 | Production cron script hash unchanged | ✓ PASS |
| IT-34 (S71K) | RC-2 hash in BackfillEntryGuard sentinel | ✓ PASS |
| IT-35 (S71K) | Wrapper does not modify backfill | ✓ PASS |
