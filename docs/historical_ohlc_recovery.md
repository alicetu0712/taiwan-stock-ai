# Historical OHLC Recovery Investigation

**Date:** 2026-11-05  
**Status:** RECOVERY NOT YET EXECUTED (pending decision)

---

## Summary

The 30-day window ending on 2026-11-05 has ≥10 missing expected trading days,
causing the OHLCContinuityGate to return BLOCKED_MISSING_OHLC. This document
records what recovery would require and what risks exist.

---

## Missing Dates Requiring Recovery

| Date       | Day | Gap Before (days) |
|------------|-----|-------------------|
| 2026-10-15 | Thu | –                 |
| 2026-10-19 | Mon | 1 weekend         |
| 2026-10-20 | Tue | –                 |
| 2026-10-23 | Fri | 2 days            |
| 2026-10-26 | Mon | 1 weekend         |
| 2026-10-27 | Tue | –                 |
| 2026-10-29 | Thu | 1 day (10/28 OK)  |
| 2026-10-30 | Fri | –                 |
| 2026-11-02 | Mon | 1 weekend         |
| 2026-11-03 | Tue | –                 |
| 2026-11-05 | Thu | 1 day (11/04 OK)  |

---

## Recovery Option A: Historical Backfill

```bash
# Check what's available
python3 scripts/backfill_daily_prices.py --dry-run

# Execute backfill for specific date range
python3 scripts/backfill_daily_prices.py \
    --start-date 2026-10-15 \
    --end-date 2026-11-05 \
    --execute
```

**Prerequisites:**
- Data source must be accessible (TWSE/external API)
- Quality gate (QG-5) must pass for each date
- DailyPrice backfill script must support date-range arguments

**After recovery:**
```bash
python3 scripts/run_hybrid_forward_shadow.py
# Gate should PASS if all missing dates recovered
```

**Security boundary:** This is a local SQLite write operation on `data/platform.db`
(research environment). NOT a Neon DDL write. NOT a production migration.
Local backfill is authorized under the safety rules.

---

## Recovery Option B: Wait for Cron Accumulation

Without historical backfill, each day the cron runs successfully adds one clean
bar to the DB. The gate will PASS once 30 consecutive expected trading days all
have 0050 data.

**Estimated timeline:**
- 11 missing days + 30 required = gate passes after ~6-8 weeks from 2026-11-05
  (accounting for weekends and additional gaps from cron failures)
- Conservative estimate: gate PASS by **2026-12-28** (6 weeks, no new gaps)

---

## Verification After Recovery

```python
import sqlite3
from datetime import date
from src.research.ohlc_continuity_gate import GateResult, OHLCContinuityGate

conn = sqlite3.connect("data/platform.db")
gate = OHLCContinuityGate()
report = gate.check_market(conn, date.today())
print(report.gate_result)
print(f"Missing: {report.missing_sessions}")
print(f"Missing dates: {report.missing_dates}")
conn.close()
```

Expected output after full recovery: `GateResult.PASS`, `missing_sessions = 0`

---

## Safety Constraints

- Do NOT backfill using synthetic/interpolated prices. Only real TWSE market data.
- Each recovered date must pass the DailyPrice quality gate (QG-5: price range check,
  volume > 0, all OHLC fields present).
- Do NOT modify any existing ForwardDecision records based on recovered data.
  Recovered data only allows FUTURE decisions for dates after recovery.
