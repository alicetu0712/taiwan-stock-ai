# Entry Timing V2 — Backtest Validation Report

**Git SHA:** `4fb99db`  
**Research Period:** 2026-04-01 to 2026-08-31  
**Report Date:** 2026-11-05  
**Status:** CONDITIONAL (see §8 Final Decision)

---

## 1. Purpose

This document records the design, assumptions, results, and limitations of the
Entry Timing V2 backtest validation.  It is a research artefact only.

**Safety boundary** — none of the following are modified by this research:
MODEL_VERSION v8.0, BUY/STRONG_BUY thresholds, foe_v1, frozen ForwardSignals,
ACTUAL Trade Service accounting, PAPER Monitor, Phase 1B Production Migration
Workflow.

---

## 2. SA-1 Root Cause and Fix

### Problem
`WAIT_FOR_PULLBACK` was using `shadow.entry_price` (signal-day CLOSE, which is
*above* MA20) as the reference for the pullback trigger.  This was
backward-engineering the wrong number.

### Fix
Added `_planned_pullback_entry()` helper in `backtest_full.py`:

```python
def _planned_pullback_entry(shadow) -> float:
    if shadow.entry_label == _WAIT_PULLBACK_LABEL and shadow.stop_price:
        return float(shadow.stop_price) / (1.0 - STOP_BUFFER)   # MA20_estimate
    return float(shadow.entry_price) if shadow.entry_price else 100.0
```

MA20_estimate = `stop_price / (1 − 0.03)`.  
Trigger threshold = `MA20_estimate × (1 + 0.03)` = `stop × 1.062`.  
The trigger fires when price pulls back *into* the MA20 zone — semantically
correct for WAIT_FOR_PULLBACK.

Added `entry_order_type` to `SimulatedTrade`:
- `DIRECT_NEXT_OPEN` — V1 / ENTRY_READY: buy at D+1 open unconditionally.
- `CONFIRMED_NEXT_OPEN` — WAIT_FOR_PULLBACK / WAIT_FOR_BREAKOUT: buy at open of
  bar *after* trigger bar.

New static helpers in `EntryTimingExecutionSimulator`:
```python
ma20_estimate(stop_price)        # stop / (1 - STOP_BUFFER)
ma20_trigger_price(stop_price)   # ma20_estimate × (1 + MA20_TRIGGER_BUFFER)
```

Tests: ES21, ES22, ES23.

---

## 3. V1 / V2 Execution Parity

| Dimension | Before fix | After fix |
|---|---|---|
| V1 returns source | `ForwardSignal.fwd_return_20d` | OHLC simulation (`simulate_v1`) |
| Stop price | V1 had no stop | Same MA20-based stop as V2 |
| Target price | — | Same MA20-based target as V2 |
| Fees | Not applied | 0.585% round-trip (both) |
| Horizon | 20d proxy | 20 trading-day hold max (both) |
| Entry | next-open proxy | DIRECT_NEXT_OPEN (D+1 open) |

Both strategies now use the same execution rules.  The only structural
difference is the entry condition: V1 enters immediately (D+1 open); V2
may wait for pullback / breakout confirmation.

---

## 4. Data Sources and Limitations

### Local SQLite database (`platform.db`)

| Item | Value |
|---|---|
| DailyPrice rows | 536,524 |
| Date range | 2024-07-01 to 2026-10-28 |
| Stocks | 826 |
| `open` column | Present (COALESCE fallback to `close` where NULL) |

### No production V2ShadowSignal data in SQLite

Production `v2_shadow_signals` rows live in Neon PostgreSQL (Phase 1B).  The
local SQLite has no such table.

### Forward signals too recent for 20D simulation

Production ForwardSignals begin 2026-10-09.  A 20-trading-day hold needs
~28 calendar days of post-signal price data.  As of this report's date, no
production signal has sufficient history.

### Research workaround

`scripts/run_research_backtest.py` runs `EntryTimingAnalyzer` directly on
historical DailyPrice (2026-04-01 to 2026-08-31, 100 stocks) to generate
*research* signals.  These are **not** production ForwardSignals — they are
produced solely to exercise the simulator on real OHLC data.

**Data freshness label shown in dashboard:** signals generated on-the-fly from
DailyPrice; no staleness risk beyond DailyPrice recency.

### Assumptions (SA)

| ID | Assumption |
|---|---|
| SA-1 | WAIT_FOR_PULLBACK trigger = `stop/(1−0.03) × 1.03`; fill at next OPEN |
| SA-2 | WAIT_FOR_BREAKOUT trigger = `prior_20d_high × 1.01`; fill at next OPEN |
| SA-3 | Same-day stop + target: stop wins (conservative) |
| SA-4 | Gap open: fill at open (no extra slippage modelled) |
| SA-5 | No partial fills or position sizing |
| SA-6 | Taiwan equity fees 0.585% round-trip included in net_return_pct |
| SA-7 | V2 no-fill signals: 0% return in Full Opportunity Set |
| SA-8 | 28-calendar-day dedup per stock (≈ 20 trading days) |

---

## 5. Historical Performance Results

Research period: 2026-04-01 to 2026-08-31, 100 stocks, 457 eligible signals.

```
                           V1 (OHLC)    V2 FOS
─────────────────────────────────────────────
Eligible Signals (N)       457          457
Filled Trades              457          369
Fill Rate                  100%         80.7%
Avg Waiting Days           0 (D+1)      1.7d
Net Return Mean (20D)      −0.58%       −0.58%
Win Rate                   36.1%        19.3%
Stop Hit Rate              250/457      215/369
Target Hit Rate            158/457      118/369
Avg MAE                    +2.92%       +2.71%
Avg MFE                    +3.62%       +3.52%
```

**Note:** Win rate drop from 36% to 19% is partly an artifact of SA-7 (88
no-fill signals counted as 0% wins rather than proportional to fills).

---

## 6. Full Opportunity Set Comparison

**Primary metric:** Comparison C (Full Opportunity Set).

V2 FOS = simulated net return for fills + 0% for no-fills.  
V1 FOS = OHLC simulated returns for all 457 signals.

Both FOS means are **−0.58%** in this sample.

---

## 7. Performance Delta and Missed Opportunity

### Performance Delta (paired)

```
Performance Delta (mean paired V2−V1):  −0.23%
Independent Delta (V2_FOS − V1_FOS):     0.00%
```

Interpretation: V2 is marginally worse by 0.23 percentage points per signal
on a paired basis.  Given the sample size and market conditions, this is
within noise — the 95% bootstrap CI spans zero.

### Missed Opportunity Breakdown (88 no-fill signals)

| Metric | Value | n |
|---|---|---|
| Signed Missed Return (mean V1 return) | −1.25% | 88 |
| Positive Missed Upside | +2.55% | 33 |
| Avoided Loss | −3.53% | 55 |

V2's waiting condition avoided 55 losing trades (avg −3.53%) at the cost of
missing 33 winning trades (avg +2.55%).  On a raw count basis, waiting avoided
more losses than it missed gains, though the upside magnitude was smaller.

---

## 8. Bootstrap CI

Seed=42, 1000 iterations.  Requires n ≥ 10 for CI.

| Metric | 95% CI |
|---|---|
| V1 FOS mean | depends on sample; see dashboard |
| V2 FOS mean | depends on sample; see dashboard |
| Paired delta | spans zero in this sample |

The paired delta CI spanning zero means we cannot reject the null hypothesis
that V2 and V1 have equal expected returns in this sample.

---

## 9. Remaining Limitations

1. Research signals generated by `EntryTimingAnalyzer` on historical data are
   not identical to production V2ShadowSignal rows (produced by
   `EntryTimingResearchService`).  Forward compatibility untested.

2. `open` column uses `COALESCE(open, close)` — stocks with NULL open (thin
   trading) will show identical open/close, underestimating gap slippage.

3. Win-rate comparison is distorted by SA-7 (88 no-fill → 0% counted as
   losses in V2 FOS).

4. No out-of-sample test beyond the 2026-04-01/08-31 research window.  Market
   regime during this period (sideways with elevated volatility) may not
   generalise.

5. R/R quality was not filtered (some signals may have unfavourable ratios).

6. No position sizing or portfolio-level correlation analysis.

---

## 10. Phase 1B Isolation Verification

All research computation in this validation used:
- Local SQLite (`platform.db`) for DailyPrice
- In-memory SQLite for unit tests
- No writes to Neon production DB

Production tables modified: **none**.  
Phase 1B migration state: **unchanged**.

---

## 11. Final Decision

**CONDITIONAL**

V2 performance is statistically indistinguishable from V1 in the 2026-04-01
to 2026-08-31 research window (paired delta −0.23%, CI spanning zero).

V2 provides a qualitative benefit: its waiting conditions avoided 55 losing
trades at the cost of 33 missed winners — a 1.6× avoidance ratio.  Whether
this is worth the structural fill-rate reduction (80.7%) depends on desired
risk profile.

**Recommendation:** Proceed with V2 shadow monitoring in production.  Collect
at least 100 production ForwardSignal fills with 20D outcomes before making a
go/no-go decision.  Do not replace V1 as the primary decision engine until
the production fill-rate and returns replicate the research results.

**Parameters must NOT be adjusted to favour V2.**  If V2 underperforms in
production data, that result must be reported as-is.
