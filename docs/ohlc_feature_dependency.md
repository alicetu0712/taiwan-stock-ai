# OHLC Feature Dependency Map

**Last updated:** 2026-11-05

This document maps each signal feature to its OHLC bar requirement, explaining
why the OHLCContinuityGate uses a 30-bar window.

---

## Feature Lookback Requirements

### MA20 (Moving Average, 20 bars)
- **Used by:** `compute_ma20`, breakout detection, stock-level regime filter
- **Bars needed:** 20 consecutive closes
- **Source file:** `src/research/signal_generator.py`
- **Consequence if gap:** MA value computed with fewer bars → wrong level → false
  breakout/near_breakout triggers

### MA20_SLOPE (10-bar slope of MA20)
- **Used by:** `compute_ma_slope`, effectiveness_analyzer regime classification
- **Bars needed:** 30 consecutive closes (MA20 at time T + MA20 at time T-10)
- **Source file:** `src/research/effectiveness_analyzer.py:MA20_SLOPE_BARS = 10`
- **Consequence if gap:** Slope computed over non-consecutive time intervals →
  rate-of-change value meaningless (e.g. 10% over 15 actual days vs 10 trading days)

### REGIME (Market Regime via 0050 MA30)
- **Used by:** `_regime_on_date` in hybrid_forward_db, signal filters
- **Bars needed:** 30 consecutive closes of 0050
- **Source file:** `src/research/hybrid_forward_db.py`
- **Consequence if gap:** Wrong regime classification (bull/bear/neutral) →
  misapplied P1–P4 entry rules

### MA60 (60-bar moving average)
- **Used by:** Longer-term trend filter in signal generation
- **Bars needed:** 60 closes
- **Note:** Gate window (30) does NOT cover the full MA60 window. Gate focuses on
  the most recent 30 bars only. Gaps older than 30 bars would affect MA60 accuracy
  but are outside the gate's scope (they would manifest as stale data).

---

## Why CONTINUITY_WINDOW = 30

```
max(TOTAL_SLOPE_BARS=30, REGIME_BARS=30) = 30
```

Both MA20_SLOPE and REGIME require exactly 30 consecutive trading days.
A single missing expected trading day in the last 30 corrupts at least one of
these features.

---

## Gate Logic Summary

```
Market gate checks: 0050 data for last 30 expected trading days
  Any EXPECTED_DATA_MISSING → BLOCKED_MISSING_OHLC
  UNKNOWN (calendar error, data present) → UNKNOWN_CALENDAR (not blocking)
  All present → PASS

Stock gate checks: does individual stock have data on each of the last 20 market-open dates?
  Any missing → BLOCKED_MISSING_OHLC
  total_bars < 70 → BLOCKED_INSUFFICIENT_HISTORY
  All present, sufficient bars → PASS
```

---

## MIN_HIST_BARS = 70

Signals require at least 70 total closes to have sufficient history for all
lookback windows (MA60=60, plus buffer for slope/regime). Stocks listed for
fewer than 70 trading days are excluded from signal generation.

---

## Implementation

| Component | File | Key Constants |
|-----------|------|---------------|
| OHLCContinuityGate | `src/research/ohlc_continuity_gate.py` | `MA20_BARS=20, TOTAL_SLOPE_BARS=30, REGIME_BARS=30, CONTINUITY_WINDOW=30, MIN_HIST_BARS=70` |
| Integration | `scripts/run_hybrid_forward_shadow.py` | Gate runs before signal generation |
| Dashboard | `dashboard/_pages/entry_timing_research.py` | Panel H3 |
| Tests | `tests/test_ohlc_continuity_gate.py` | CG01–CG25 |
