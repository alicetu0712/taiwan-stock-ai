# V3 Historical Backtest Framework

**Status:** RESEARCH ONLY — not production-ready  
**Date:** 2026-11-06  
**Engine version:** v3_backtest_v1  
**Research version:** v3_research_v1  
**Parameter hash:** be43e8ca977d9fdd  

---

## 1. Purpose

This document describes the historical backtest framework for V3 Entry Timing strategy
(`src/research/v3_entry_strategy.py`). The framework replays V3 decisions on historical
OHLCV data to answer the 14 research questions from `docs/v3_entry_timing_research_design.md`.

V3 is a parallel research track — it does NOT replace Hybrid V1 (frozen) or modify
any production system. See §12 (Safety Boundaries) for the complete restriction list.

---

## 2. Repository Audit Summary (P0)

### Existing infrastructure reused

| Module | Role | Reuse |
|--------|------|-------|
| `execution_simulator.py` | SA-1 to SA-7 intrabar rules, hold lifecycle, P&L | Full (_run_hold, _compute_pnl, _wait_for_breakout) |
| `hybrid_trading_calendar.py` | TradingCalendar.from_db() | Available for walk-forward |
| `effectiveness_analyzer.py` | EnrichedSignal, bootstrap CI | Available for future phases |
| `hybrid_backtest.py` | Three-strategy comparison framework | Reference for phase 2 |
| `v3_entry_strategy.py` | V3EntryTimingAnalyzer, V3EntryDecision | Core decision layer |

### Data state at framework creation (2026-11-06)

| Dataset | Coverage |
|---------|----------|
| daily_prices | 2024-07-01 to 2026-11-05, 14,675 stocks, 528,182 rows |
| forward_signals (buy/strong_buy) | 2026-10-09 to 2026-10-28, 344 signals |
| 0050 benchmark | 2024-07-01 to 2026-11-05, 567 bars |

---

## 3. Data Contract (P1)

### Time-causality guarantees

For each signal with `signal_date = D`:

```
History  = daily_prices WHERE stock_id = X AND date <= D    (no future bars)
Forward  = daily_prices WHERE stock_id = X AND date >  D    (strictly after)
Benchmark= daily_prices WHERE stock_id = '0050'             (same window)
```

The V3 analyzer receives only the `History` DataFrame. It computes all indicators
(MA20, MA60, slopes, prior_20d_high) from bars ending on D inclusive.

`prior_20d_high` uses `high[-21:-1]` — excludes today (high[-1]), same convention
as V1/V2. No single-bar look-ahead.

### Data quality gates

- **MIN_BARS_FULL = 71**: signals with fewer history bars are skipped (`n_skipped_no_history`)
- **PARTIAL maturation**: trades where forward bars < HOLD_DAYS=20 are labeled PARTIAL,
  not excluded. Performance stats are computed but marked as preliminary.
- **Missing stop/target**: if V3 cannot compute stop_price (no MA anchor), trade is
  skipped with `NO_FILL_NO_HIST`. Target = 999999 sentinel when not computable
  (never fires as target, only hold expiry applies).

---

## 4. Historical Signal Universe (P2)

### Initial dry run universe

The initial dry run uses buy/strong_buy signals from `forward_signals` (the production
scoring system's output), loaded via `load_buy_signals_for_backtest(conn)`.

**Universe characteristics (Oct 9–Oct 28, 2026):**

| Attribute | Value |
|-----------|-------|
| Total buy/strong_buy signals | 344 |
| Signals with sufficient history (≥71 bars) | 341 |
| Market regime | 'bull' (245), 'unknown' (99) |
| Stocks | 152 unique |
| Date range | 2026-10-09 to 2026-10-28 (20 signal dates) |

### Selection bias considerations

1. **Survival bias**: forward_signals only contains stocks the production system scored.
   Low-quality or illiquid stocks are excluded upstream.
2. **Regime concentration**: all signals in a single bull-regime window (Oct 2026).
   No bear/neutral regime exposure in this universe.
3. **Window too short for 20D windows**: signals from Oct 9–Oct 28 have at most 18
   trading days of post-signal data (through Nov 5). All 220 filled trades are PARTIAL.
4. **Implication**: dry-run performance stats are preliminary only. Walk-forward
   requires a longer historical universe.

### Path to larger universe

Future expansion options (not yet implemented):
- Apply a minimal candidate screen (pt_score ≥ 50, vol_ratio > 0.5) to daily_prices
  going back to 2024-07-01, to generate IS signals with complete 20D windows.
- Requires defining the candidate screen criteria independently (outside scope of P2).

---

## 5. V3 Decision Replay (P3)

### Decision → Execution mapping

| V3 Decision | Execution model | Trigger | Fill |
|-------------|-----------------|---------|------|
| DIRECT_ENTRY | DIRECT_NEXT_OPEN | — | D+1 OPEN |
| WAIT_MA20_PULLBACK | CONFIRMED_NEXT_OPEN | LOW ≤ proposed_limit_price (MA20) | OPEN of bar after trigger |
| WAIT_MA60_SUPPORT | CONFIRMED_NEXT_OPEN | LOW ≤ proposed_limit_price (MA60) | OPEN of bar after trigger |
| WAIT_BREAKOUT_CONFIRMATION | CONFIRMED_NEXT_OPEN | CLOSE > prior_20d_high | OPEN of bar after trigger |
| AVOID_CHASING | SKIP | — | No fill |
| NO_ENTRY | SKIP | — | No fill |
| INSUFFICIENT_DATA | SKIP | — | No fill |

### Key V3 vs V1/V2 trigger differences

V1/V2 `WAIT_FOR_PULLBACK` derives the trigger from stop_price:
```
trigger = stop_price / (1 - STOP_BUFFER) × (1 + STOP_BUFFER)  ≈ MA20 × 1.062
```

V3 uses the actual MA level stored in `proposed_limit_price`:
- WAIT_MA20_PULLBACK: trigger = MA20 (or MA20 × (1 + zone_upper%) for above-zone case)
- WAIT_MA60_SUPPORT: trigger = MA60

This eliminates the stop-price approximation and is more precise.

### Parameter versioning

All parameters are frozen at analysis time and captured in `PARAMETER_HASH`:
```
PARAMETER_HASH = be43e8ca977d9fdd
```

Recomputed deterministically from: RESEARCH_VERSION, ENGINE_VERSION, _REGIME_PARAMS,
MIN_BARS_FULL, STOP_BUFFER, MIN_RR_RATIO, FEES_PCT, HOLD_DAYS, EXPIRY_DAYS.

---

## 6. Order Simulation Engine (P4)

The `V3BacktestEngine._simulate_v3_entry()` method dispatches to:

1. **DIRECT_ENTRY**: calls `EntryTimingExecutionSimulator._fill_next_open()`
2. **WAIT_MA20_PULLBACK / WAIT_MA60_SUPPORT**: calls `V3BacktestEngine._simulate_wait_level()`
   — custom trigger using V3's proposed_limit_price directly
3. **WAIT_BREAKOUT_CONFIRMATION**: calls `EntryTimingExecutionSimulator._wait_for_breakout()`
4. **Skip decisions**: no simulation, SimulatedTrade.no_fill_reason = NO_FILL_SKIP_LABEL

---

## 7. Execution Assumptions (P5)

All assumptions are labelled SA-N to match `execution_simulator.py`:

| Label | Assumption | Value |
|-------|------------|-------|
| SA-1 | WAIT pullback trigger: LOW ≤ level, fill next OPEN | MA level (not stop approximation) |
| SA-2 | WAIT breakout trigger: CLOSE > prior_20d_high, fill next OPEN | Same as V1/V2 |
| SA-3 | Same-day stop + target ambiguity | Stop first (conservative) |
| SA-4 | Gap down through stop at open | Exit at open (gap slippage) |
| SA-5 | Standard hold period | 20 trading days from fill |
| SA-6 | Taiwan round-trip fees | 0.585% (buy 0.1425% + sell 0.4425%) |
| SA-7 | No-fill in Full Opportunity Set | 0% return over same window |
| SA-8 | WAIT expiry window | 10 bars (EXPIRY_DAYS) |

---

## 8. Trade Lifecycle (P6)

```
SIGNAL_CREATED
    │
    ├── SKIP (AVOID_CHASING / NO_ENTRY / INSUFFICIENT_DATA)
    │       SimulatedTrade.no_fill_reason = NO_FILL_SKIP_LABEL
    │
    ├── NO_HISTORY → no_fill_reason = NO_FILL_NO_HIST
    │
    └── ELIGIBLE
            │
            ├── DIRECT_ENTRY → fill at D+1 OPEN
            │
            ├── WAIT_* → scan expiry window
            │       ├── trigger fires → fill at next OPEN (CONFIRMED_NEXT_OPEN)
            │       └── no trigger → no_fill_reason = NO_FILL_EXPIRED
            │
            └── FILLED
                    │
                    └── HOLD (up to HOLD_DAYS bars)
                            ├── gap-down stop (SA-4) → EXIT_GAP_STOP
                            ├── stop hit (SA-3 / SA-5) → EXIT_STOP / EXIT_AMBIGUOUS_STOP
                            ├── target hit → EXIT_TARGET
                            └── hold expiry → EXIT_HOLD_EXPIRY
```

MAE (max adverse excursion) and MFE (max favorable excursion) are computed as
percentage drawdown/runup from fill price over the hold period.

R-multiple = (exit - fill) / (fill - stop).

---

## 9. Conservative Intrabar Rules (P7)

The `INTRABAR_SEQUENCE_UNKNOWN` flag (`ambiguous_day = True` in `SimulatedTrade`) is
set whenever both stop and target are hit within the same daily bar (SA-3).

In that case:
- Outcome = stop first (conservative)
- `exit_reason = EXIT_AMBIGUOUS_STOP`
- `stop_hit = True`, `target_hit = False`
- `simulation_note` records the ambiguity

This is the most conservative assumption: we cannot know intraday sequence from
daily bars, so we always assume the worst-case outcome when both extremes are hit.

---

## 10. Outcome & Benchmark (P8)

### Returns

Net return = gross return − 0.585% fees:
```
gross_return_pct = (exit_price - fill_price) / fill_price × 100
net_return_pct   = gross_return_pct - 0.585
```

Holding period uses calendar days from OHLCV bars (trading days, not calendar days).
`days_held` = number of OHLCV bars from fill to exit.

### Benchmark (0050)

Alpha is computed per trade, not per portfolio:
```
benchmark_return = (0050_close_at_exit - 0050_open_at_fill) / 0050_open_at_fill × 100
alpha_20d        = trade.net_return_pct - benchmark_return
```

Benchmark is gross (no fees), since 0050 is a passive ETF held without active trading.
Alpha is therefore conservative: V3 net minus 0050 gross.

### 5D / 10D windows

The initial framework uses 20D as the primary window (matching V1/V2 for comparability).
5D and 10D windows are planned for Phase 2 (requires extending SimulatedTrade).

---

## 11. Initial Dry Run Results (P11)

**Run date:** 2026-11-06  
**Engine:** v3_backtest_v1 | **Hash:** be43e8ca977d9fdd  

```
Input signals:         344
Analyzed (≥71 bars):   341  (3 skipped: insufficient history)
Skipped (skip decision): 59 (AVOID_CHASING=46, NO_ENTRY=13)

Trade fills:           220 filled, 62 no-fill-expired
Maturation:            FULL=0, PARTIAL=220, NO_DATA=59
```

**V3 Decision Distribution:**
```
WAIT_MA20_PULLBACK       105  (30.8%)
DIRECT_ENTRY              95  (27.9%)
WAIT_BREAKOUT_CONF        82  (24.0%)
AVOID_CHASING             46  (13.5%)
NO_ENTRY                  13   (3.8%)
```

**Setup Distribution:**
```
wait_pullback_above_zone  103  (price above MA20 zone, waiting for pullback)
near_breakout              82  (near resistance, waiting for vol breakout)
ma20_pullback              48  (in MA20 zone, direct entry)
breakout                   46  (resistance broken with volume)
failed_breakout            35  (failed breakout → AVOID_CHASING)
...
```

**Preliminary Performance (220 PARTIAL trades):**
```
mean_net_return:    -5.30%
median_net_return:  -5.09%
win_rate:           19.1%
mean_alpha_20d:     +2.33%
```

### ⚠️ Dry run interpretation caveats

1. **All trades are PARTIAL** (< 20D forward data). Oct 9–28 signals have at most
   ~18 bars through Nov 5. Performance numbers reflect a truncated, partially-open
   exit (at last available close), not the full 20D outcome.
2. **Market context**: Oct–Nov 2026 was a declining bull market. The low win rate
   (19%) is consistent with a broad market drawdown, not necessarily V3-specific.
3. **Positive alpha (+2.33%)** means V3 filled trades underperformed the market by
   less than 0050 declined. This is an artifact of the truncated window.
4. **No bear or neutral regime coverage.** All signals are from a 'bull' or
   'unknown' (→ neutral params) regime window.
5. **In-sample**: V3 parameters were designed on intuition, not optimized on this
   data. However, the input universe (forward_signals) overlaps the design period.
   True OOS requires either time-out-of-sample or cross-validation.

---

## 12. Testing (P10)

**Test file:** `tests/test_v3_backtest_engine.py` (25 tests, BT-01 to BT-25)

| ID | Category | Description |
|----|----------|-------------|
| BT-01 | Execution | DIRECT_ENTRY fills at D+1 OPEN |
| BT-02 | Execution | WAIT_MA20_PULLBACK: no trigger → EXPIRED |
| BT-03 | Execution | WAIT_MA20_PULLBACK: trigger fires |
| BT-04 | Execution | WAIT_MA60_SUPPORT: trigger fires |
| BT-05 | Execution | WAIT_BREAKOUT_CONFIRMATION: fires on CLOSE > prior_high |
| BT-06 | Execution | AVOID_CHASING → no fill (SKIP) |
| BT-07 | Execution | NO_ENTRY → no fill (SKIP) |
| BT-08 | Lifecycle | Stop hit during hold |
| BT-09 | Lifecycle | SA-3 same-day ambiguity → stop first |
| BT-10 | Lifecycle | 20D hold expiry → exit at close |
| BT-11 | Lifecycle | MAE/MFE computed after hold |
| BT-12 | Maturation | FULL: ≥ HOLD_DAYS forward bars |
| BT-13 | Maturation | PARTIAL: 1 to HOLD_DAYS-1 bars |
| BT-14 | Maturation | NO_DATA: 0 forward bars |
| BT-15 | Safety | Parameter hash is deterministic |
| BT-16 | Safety | No look-ahead: history cutoff at signal_date |
| BT-17 | Safety | Result is JSON-serializable |
| BT-18 | Aggregate | n_filled count correct |
| BT-19 | Aggregate | decision_distribution populated |
| BT-20 | Aggregate | mean_net_return uses filled trades only |
| BT-21 | Data | Insufficient history → n_skipped_no_history |
| BT-22 | Benchmark | 0050 gross return computed correctly |
| BT-23 | Benchmark | Missing 0050 data → None |
| BT-24 | Loader | load_buy_signals_for_backtest loads buy/strong_buy only |
| BT-25 | Metadata | Result carries correct engine/research version |

All 25 tests pass. No DB writes in any test (all use in-memory SQLite).

---

## 13. Architecture Diagram

```
V3SignalInput(signal_date, stock_id, market_regime)
    │
    │ _load_history(stock_id, signal_date)
    │ → daily_prices WHERE date <= signal_date  [NO LOOK-AHEAD]
    ▼
V3EntryTimingAnalyzer.analyze(stock_id, history, market_regime)
    │
    ▼
V3EntryDecision(entry_decision, proposed_limit_price, prior_20d_high,
                stop_price, target_price, confidence, ...)
    │
    ├── SKIP decision? → SimulatedTrade(no_fill=SKIP_LABEL)
    │
    └── _simulate_v3_entry(signal, v3, post_ohlcv)
            │
            ├── DIRECT_ENTRY          → sim._fill_next_open()
            ├── WAIT_MA20_PULLBACK    → engine._simulate_wait_level(MA20)
            ├── WAIT_MA60_SUPPORT     → engine._simulate_wait_level(MA60)
            └── WAIT_BREAKOUT_CONF   → sim._wait_for_breakout(prior_20d_high)
                    │
                    ▼
            SimulatedTrade (SA-3 / SA-4 / SA-5 from execution_simulator._run_hold)
                    │
                    ▼
            benchmark_return: 0050 open[fill] → close[exit]
            alpha_20d:        trade.net_return_pct - benchmark_return
```

---

## 14. Safety Boundaries

The following actions are forbidden in this research track:

**Do not modify:**
- MODEL_VERSION v8.0
- foe_v1
- BUY / STRONG BUY thresholds
- Frozen ForwardSignals (Neon or SQLite)
- ACTUAL / PAPER position accounting
- Hybrid V1 rules (P1–P4, frozen 2026-11-05)
- Prospective Classification logic

**Do not execute:**
- Production deployment of V3
- Neon schema migration
- Neon historical backfill
- Neon research recalculation
- Production research SQLite writes
- Formal ForwardSignals modification
- Cron schedule modification
- GitHub Actions activation
- Decision Center integration

---

## 15. Next Steps

### Phase 2: Extended Historical Universe

- Define candidate screen criteria (pt_score, setup_type, vol_ratio) for 2024–2026 IS universe
- Generate synthetic historical signal universe covering full daily_prices range
- Run V3 backtest on IS signals with complete 20D windows
- Compare V3 decision distribution and performance vs V1/V2

### Phase 3: Walk-Forward Validation

- 10-fold time-ordered walk-forward (matching V2 methodology in effectiveness_analyzer.py)
- Embargo period between train/test to prevent leakage
- Compare V3 Sharpe × recall vs Hybrid V1 baseline

### Phase 4: 14 Research Questions

Answer Q1–Q14 from `docs/v3_entry_timing_research_design.md`:
- Q1: Does MA60 support setup have alpha vs V1/V2?
- Q6: WAIT_* conversion rate (what % trigger within 5D)?
- Q8: Confidence score IC (rank-correlation with 20D return)?
- Q9: Does V3 exceed Hybrid V1 on Sharpe × recall?
- etc.

---

*Research only. All decisions in this document are exploratory and do not represent
investment advice or validated strategies.*
