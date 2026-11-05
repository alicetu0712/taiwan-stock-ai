# Hybrid First Prospective Capture — Safety Requirements

**Rule Freeze Date:** 2026-11-05  
**Gate Status:** BLOCKED_MISSING_OHLC (as of 2026-11-05)  
**First Valid Capture:** PENDING

---

## Classification System

A Hybrid ForwardDecision is classified by `classify_capture(trade_date, captured_at,
input_data_as_of, trading_days_since_trade)`:

| Class         | Condition                                                        |
|---------------|------------------------------------------------------------------|
| PROSPECTIVE   | trade_date ≥ RULE_FREEZE_DATE AND captured on trading day 0 or 1 AND input_data_as_of ≥ trade_date |
| RETROSPECTIVE | trade_date < RULE_FREEZE_DATE or captured late                   |
| INVALID_DATA  | input_data_as_of < trade_date (data predates the decision date)  |

**RULE_FREEZE_DATE = date(2026, 11, 5)**

---

## INVALID_DATA Guard

The shadow runner checks `input_data_as_of` against `trade_date` before writing
any decision. If the data used to generate a signal is older than the signal date,
the decision is marked INVALID_DATA and excluded from OOS analysis.

This prevents the system from accidentally generating signals using stale data
(e.g., if the cron runs on Nov 5 but the last backfill only reached Nov 3).

---

## OHLC Gate Requirement

Before generating any PROSPECTIVE signal, the OHLCContinuityGate must return
`GateResult.PASS`. If the gate returns BLOCKED_MISSING_OHLC, the shadow runner
returns `RunStatus.BLOCKED_MISSING_OHLC` and writes no decisions.

This ensures:
1. MA20 (20-bar window) uses 20 consecutive, uninterrupted closes
2. MA20_SLOPE (30-bar window) uses 30 consecutive closes for a valid rate-of-change
3. REGIME (30-bar 0050 window) uses 30 consecutive 0050 closes

**A PROSPECTIVE signal generated through a blocked gate would be scientifically invalid.**

---

## First Capture Requirements Checklist

Before the first PROSPECTIVE decision can be recorded:

- [ ] OHLCContinuityGate returns PASS for today's trade_date
- [ ] DailyPrice backfill has run successfully for trade_date
- [ ] Cron script: `hybrid_shadow_cron.py` is running (see `docs/hybrid_cron_final_readiness.md`)
- [ ] `input_data_as_of >= trade_date` (INVALID_DATA guard passes)
- [ ] At least one stock generates a signal (WAIT_FOR_PULLBACK or WAIT_FOR_BREAKOUT)
- [ ] RunStatus = SUCCESS or PARTIAL (not BLOCKED or FAILED)

---

## What Counts as a Valid OOS Test

For a ForwardDecision to contribute to prospective OOS analysis:

1. `capture_classification = PROSPECTIVE`
2. `trade_date >= 2026-11-05`
3. `input_data_as_of >= trade_date`
4. No prior knowledge: rules were frozen (committed) before the signal date
5. Outcome recorded independently: when position resolves, record actual exit price
   without reference to entry rules

---

## Expected Timeline

Assuming cron runs daily starting 2026-11-05 with no new gaps:
- Gate PASS: approximately 2026-12-28 (30 clean trading days from 11-05)
- First PROSPECTIVE capture: same day gate first passes
- First outcome (30-day hold): ~4 weeks after first capture
- Minimum meaningful sample (n=20 signals): several months of daily signals

---

## Safety Boundaries (Cannot Be Changed)

- MODEL_VERSION v8.0 — frozen
- foe_v1 signal generation logic — frozen
- BUY / STRONG BUY thresholds — frozen
- Hybrid P1–P4 entry rules — frozen (commit 6602c3b)
- Existing ForwardDecision records — immutable
- Production Neon DDL/Writes — prohibited
