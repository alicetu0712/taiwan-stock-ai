# V3 Performance Decomposition Plan — Session 37

**Date:** 2026-11-08  
**Audit Type:** Research design only — read-only  
**Version:** session37_v1

**Scope:** Decompose V3's historical performance (+3.66ppt in-sample, Session 27) into Market Timing, Stock Selection, and Entry Timing components. This is a design plan only — no model changes, no retraining, no production changes.

---

## 1. V3PerformanceDecompositionPlan

### Problem Statement

Session 28 concluded that V3's walk-forward performance was `MARKET_AVOIDANCE_DRIVEN`. The +3.66ppt in-sample advantage cannot be attributed to stock selection ability because the strategy primarily benefits from holding cash during market downturns.

To determine whether any genuine stock selection or entry timing advantage exists, we must cleanly separate the three return components.

**Key principle:** The decomposition is ONLY valid if the three components can be identified on the SAME sample, with MATCHING market exposure periods. If samples cannot be matched, the component is `UNIDENTIFIABLE`.

---

## 2. Component 1: Market Timing

### Definition
Market timing = the strategy's decision to be invested vs. holding cash, independent of which stocks are chosen.

### Measurement approach

```
MarketTimingReturn(t) = IfInvested(t) × MarketReturn(t)
                       − IfCash(t) × CashReturn(t)
```

Where:
- `IfInvested(t)` = 1 if strategy had any open position on date t
- `MarketReturn(t)` = 0050 daily return
- `CashReturn(t)` = 0 (or risk-free rate if applicable)

**Data requirements:**
- V3 position history (open/close dates)
- V2 position history (same dates)
- 0050 price history (available)

**Feasibility:** FEASIBLE with historical backtest position data. Requires that position dates are stored in backtest output.

**Control portfolio:** "Exposure-matched benchmark" — a portfolio that holds 0050 during the same days V3 is invested. This isolates whether V3's market timing (choosing WHEN to invest) adds value beyond simply being in the market.

### Expected finding

V3 likely shows positive market timing because it avoids the market during drawdown periods. This is the `MARKET_AVOIDANCE_DRIVEN` finding from Session 28. If market timing explains most of the +3.66ppt, then stock selection and entry timing contribute little.

---

## 3. Component 2: Stock Selection

### Definition
Stock selection = given that the strategy is invested, does it pick stocks that outperform the market?

### Measurement approach

**Standard approach: Alpha-only return**
```
StockSelectionReturn(t) = PortfolioReturn(t) - BenchmarkReturn(t)
```
where only invested days are counted, and `BenchmarkReturn(t) = 0050 return on same day`.

**Paired approach (better for sparse samples):**
For each signal (stock_id, signal_date), compute:
```
SignalAlpha = Signal_fwd_return_20d - 0050_fwd_return_20d (starting same date)
```

Then compare `mean(SignalAlpha_V3)` vs `mean(SignalAlpha_V2)` using same signals.

**Data requirements:**
- fwd_return_20d for all signals (currently NULL for v8.0)
- 0050 fwd_return_20d starting from same dates (can be computed from daily_prices)

**Feasibility:** PARTIALLY FEASIBLE for historical in-sample analysis. fwd_return_20d for v8.0 Oct 2026 signals is not yet available (20d window). For historical simulation data (from backtest engine), returns are computed internally.

**Identifiability condition:** Stock selection can be isolated ONLY when:
1. Market exposure is held constant between V3 and V2 on the SAME dates
2. OR a matched-exposure sample is constructed

If V3 and V2 are invested on different dates, their stock selection returns are not directly comparable because they reflect different market regimes.

### Current identifiability status

| Requirement | Status |
|---|---|
| Same-date signals available | PARTIAL (backtest has this) |
| fwd_returns computed | NULL for v8.0 ForwardSignals |
| Exposure-matched control | NOT CONSTRUCTED |
| ETF-free signal sample | NOT AVAILABLE (ETFs not filtered) |
| **Identifiable?** | **CONDITIONAL — in-sample only, with caveats** |

---

## 4. Component 3: Entry Timing

### Definition
Entry timing = given the same stock is selected, does the strategy's specific entry price/timing improve returns?

### Measurement approach

**Paired comparison:**
For each (stock_id, date) where both V3 and V2 generate signals:
```
EntryTimingGap = V3_entry_return - V2_entry_return
```
where entry_return = hold_period_return starting from respective entry prices.

**Data requirements:**
- Matched (stock_id, signal_date) pairs in both V3 and V2
- Entry price for each strategy
- Hold-period returns for each entry price

**Identifiability condition:** Entry timing can ONLY be identified when:
1. Both V3 and V2 select the SAME stock on the SAME date
2. They use DIFFERENT entry prices or entry timing rules
3. The post-entry returns can be computed from the entry price

**Current status:**
- V3's entry timing feature: NEXT_OPEN (next-day open price) vs V2 baseline
- V3 uses `execution_price_type = NEXT_OPEN`; V2 may use close price
- Matched (stock_id, date) pairs are needed but require a fresh backtest run

### Current identifiability status

| Requirement | Status |
|---|---|
| Matched (stock_id, date) pairs | NOT COMPUTED (requires backtest re-run) |
| Entry price comparison | NOT AVAILABLE (no stored entry prices for V2) |
| Sample size (matched pairs) | UNKNOWN — could be very small |
| **Identifiable?** | **CURRENTLY UNIDENTIFIABLE without fresh backtest** |

---

## 5. Cross-component Attribution Table

| Component | Identifiable Now? | Required Data | Required Work |
|---|---|---|---|
| Market Timing | YES (qualitative) | Position dates, 0050 prices | Extract position dates from backtest |
| Stock Selection | CONDITIONAL | fwd_return_20d, matched-exposure sample | backtest re-run with exposure control |
| Entry Timing | NO | Matched (stock, date) pairs, V2 entry prices | Fresh backtest comparing V3 vs V2 entries |

---

## 6. Minimum Viable Decomposition — Without New Code

Using ONLY currently available data (read-only):

### Step 1: Market Timing (FEASIBLE)
1. From backtest results, extract: days V3 is invested vs. days V2 is invested
2. Compute: cumulative 0050 return during V3-invested days vs. V2-invested days
3. If V3 is invested on "better" days → market timing advantage identified

### Step 2: Crude Stock Selection (FEASIBLE with caveats)
1. For each signal in backtest results, compare: `signal_return` vs `0050_return_same_period`
2. Pool V3 signals vs V2 signals (but NOT matched by date — different exposure periods)
3. Report: average signal alpha for V3 vs V2, with explicit caveat that date mismatch limits interpretability

### Step 3: Entry Timing (NOT FEASIBLE without backtest re-run)
- Cannot identify without matched (stock, date, entry_price) pairs from both strategies

---

## 7. Required New Research Module: ExposureMatchedComparison

**Module name:** `src/research/exposure_matched_comparison.py` (DESIGN ONLY — not implemented)

**Purpose:** Run V3 and V2 on the SAME subset of signals, restricting to dates where both strategies would be active, to isolate stock selection from market timing.

**Input:**
- Historical forward_signals (is_valid=True, common_stock_only flag)
- Backtest results for both V3 and V2

**Output:**
- `MarketTimingDecomposition`: return attribution to timing decisions
- `StockSelectionDecomposition`: alpha on matched-exposure days
- `EntryTimingDecomposition`: (requires paired entry prices)

**Preconditions:**
- ETF filtering applied
- Source_price_date populated
- Consistent universe across all dates
- Full daily_prices coverage for outcome periods

**Current status:** NOT IMPLEMENTED. This is a research design proposal only.

---

## 8. Research Infrastructure Gaps (PRICE_AVAILABLE ≠ UNIVERSE_COMPLETE)

Before ANY decomposition analysis can be trusted:

| Gap | Impact on Decomposition |
|---|---|
| ETF contamination (192 signals) | Inflates signal pool; ETF timing ≠ stock selection |
| Sparse universe on signal dates | Stock selection results apply to only 48% of universe |
| No source_price_date | Cannot verify no look-ahead in signal computation |
| No corporate action adjustment | 20d return may include dividend distortion |
| No survivorship-bias-free master | Backtest selection pool excludes delisted stocks |

**Conclusion:** Any decomposition of the +3.66ppt advantage is `UNVERIFIED_ESTIMATE` until these infrastructure gaps are addressed.

---

## 9. What CAN Be Stated Now

| Claim | Evidence Level |
|---|---|
| V3 avoids market during drawdown periods | HIGH (walk-forward analysis, Session 28) |
| Market avoidance is the primary performance driver | HIGH (0 feasible walk-forward windows) |
| V3 has genuine stock selection advantage | NOT DEMONSTRATED |
| V3 entry timing (NEXT_OPEN) adds measurable value | NOT DEMONSTRATED |
| +3.66ppt is statistically significant vs V2 | CONDITIONAL (in-sample only, 5-day horizon, Session 27) |

**Decision: V3 Activation must remain BLOCKED until at minimum the market timing vs stock selection decomposition is demonstrated with prospective data.**
