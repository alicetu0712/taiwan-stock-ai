# Hybrid Entry Strategy V1 — Pre-registration

**Rule Version:** hybrid_v1  
**Frozen At:** 2026-11-05T00:00:00  
**Frozen Commit:** 6602c3b  
**Author:** Research pipeline (Taiwan Stock AI)  
**Status:** FROZEN — do not modify rules after this timestamp

---

## 1. Purpose

This document records the Hybrid Entry Strategy V1 rules **before** collecting
any prospective data.  Pre-registration prevents post-hoc hypothesis adjustment
and makes the distinction between in-sample and out-of-sample results explicit
and auditable.

---

## 2. Research Background

The rules are derived from Entry Timing V2 Effectiveness Analysis
(`docs/entry_timing_v2_effectiveness_analysis.md`, commit 6602c3b).

Two subgroup findings emerged from the 2024-10 to 2026-09 research cohort:

| Subgroup | N | Paired Delta | 95% CI (pre-Bonferroni) |
|---|---|---|---|
| Bear regime + WAIT_FOR_PULLBACK | ~88 | +0.36% | [+0.02%, +0.69%] |
| Flat MA20 + WAIT_FOR_PULLBACK | ~68 | +0.41% | [+0.09%, +0.70%] |

**Multiple testing caveat:** With ~20 group comparisons, Bonferroni-corrected
alpha = 0.0025.  Neither finding survives Bonferroni correction at 95% CI.
Both are **hypothesis-generating findings only**.

**Key observation:** When MA20 is flat (trend ambiguous) or market regime is
bear, waiting for a pullback trigger appears to improve relative to immediate
entry — but this needs prospective confirmation on new data.

---

## 3. Hypothesis Under Test

> *Applying WAIT_FOR_PULLBACK when market regime is Bear or stock MA20 trend
> is Flat — and switching all other WAIT_FOR_PULLBACK signals to immediate
> entry — will produce a superior risk-adjusted return compared to V1 (all
> immediate) and V2 (all wait) across a future independent sample.*

Null hypothesis: Hybrid V1 produces the same mean paired delta vs V1 as V2
FOS (+0.06%, CI spans zero).

---

## 4. Feature Definitions

### 4.1 Market Regime (from 0050 MA20)

Computed on signal_date using 0050 DailyPrice (Taiwan 50 ETF as proxy).

| Regime | Condition |
|---|---|
| `bull` | 0050 close > MA20_0050 AND 10-bar MA20 slope > +0.3% |
| `bear` | 0050 close < MA20_0050 AND 10-bar MA20 slope < −0.3% |
| `neutral` | All other cases |
| `unknown` | Insufficient 0050 history (< 20 bars) |

MA20 is a simple 20-bar moving average of daily closes.  
Slope = (MA20_now − MA20_10_bars_ago) / MA20_10_bars_ago × 100.

### 4.2 Stock MA20 Trend

Computed on signal_date using the stock's own daily close history.

| Trend | Condition |
|---|---|
| `rising` | 10-bar MA20 slope > +0.3% |
| `flat` | 10-bar MA20 slope between −0.3% and +0.3% (inclusive) |
| `falling` | 10-bar MA20 slope < −0.3% |

Same slope definition as 4.1, but applied per-stock.

### 4.3 V2 Entry Label

The EntryTimingAnalyzer output for a signal.  Possible values:
- `ENTRY_READY` — price is in an immediately tradeable zone
- `WAIT_FOR_PULLBACK` — price is extended above MA20; wait for pullback
- `WAIT_FOR_BREAKOUT` — price near prior 20D high; wait for breakout confirmation
- `TOO_EXTENDED`, `NO_VALID_SETUP`, `RISK_REWARD_UNFAVORABLE` — skip labels

---

## 5. Decision Rules (Priority Order)

```
Input:  v2_entry_label, market_regime, ma20_trend

P1 (highest):  market_regime == "bear" AND v2_entry_label == "WAIT_FOR_PULLBACK"
               → WAIT_PULLBACK
               Reason: Waiting reduces buying into continued bear-market weakness.

P2:            ma20_trend == "flat" AND v2_entry_label == "WAIT_FOR_PULLBACK"
               → WAIT_PULLBACK
               Reason: Ambiguous trend; pullback trigger adds confirmation.

P3:            market_regime == "bull" AND ma20_trend == "rising"
               → DIRECT_NEXT_OPEN
               Reason: Clear momentum; immediate entry captures upside.

P4 (default):  All other conditions
               → DIRECT_NEXT_OPEN
               Reason: No strong evidence for waiting; default to V1 behaviour.
```

**Critical constraint:**
- P1 and P2 only fire for `WAIT_FOR_PULLBACK` signals.
- `WAIT_FOR_BREAKOUT` and `ENTRY_READY` signals always go to P4 → DIRECT_NEXT_OPEN.
- Skip labels are not changed; they never enter simulation.

### 5.1 Simulation mapping

| HybridAction | Simulation method |
|---|---|
| WAIT_PULLBACK | simulate_v2(label="WAIT_FOR_PULLBACK") — same as V2 |
| DIRECT_NEXT_OPEN | simulate_v1() — enter at D+1 OPEN |

---

## 6. No-Lookahead Guarantee

All features used in the decision are computable from data available on or
before `signal_date`:

| Feature | Data source | Look-ahead risk |
|---|---|---|
| market_regime | 0050 close history up to signal_date | None — uses historical closes |
| ma20_trend | Stock close history up to signal_date | None — uses historical closes |
| v2_entry_label | EntryTimingAnalyzer output on signal_date | None — uses signal_date close |

`HybridDecision.feature_cutoff_date` is always set to `signal_date`.
Tests HY37 and HY38 verify this invariant.

---

## 7. What "PASS" Means in Validation

For the forward shadow to claim PASS for Hybrid V1:

| Criterion | Threshold |
|---|---|
| Paired delta (Hybrid vs V1) | ≥ 0 (positive direction) |
| 95% CI | lo > 0 (entirely positive) |
| Sample size | n ≥ 200 matured OOS signals |
| Walk-forward consistency | No single window < −1.5pp |

A result of "delta > 0 but CI spans zero" = **CONDITIONAL** (not PASS).  
A result of "delta > 0 and CI entirely positive" = **PROVISIONAL PASS**  
(requires replication or longer OOS before full VALIDATED status).

---

## 8. In-Sample / OOS Boundary

| Data period | Status for Hybrid V1 |
|---|---|
| 2024-10-01 to 2026-09-15 | IN-SAMPLE (rules derived here) — cannot validate |
| 2026-09-16 to 2026-11-04 | GREY ZONE — adjacent to derivation period |
| 2026-11-05 onwards | TRUE OOS — prospective forward shadow only |

---

## 9. Files

| File | Role |
|---|---|
| `src/research/hybrid_entry_strategy.py` | Rule engine (HybridDecisionService) |
| `src/research/hybrid_backtest.py` | Three-strategy comparison module |
| `scripts/run_hybrid_backtest.py` | In-sample retrospective analysis |
| `scripts/run_hybrid_forward_shadow.py` | Prospective OOS runner (daily) |
| `tests/test_hybrid_entry_strategy.py` | 46 tests HY01–HY44 |
| `docs/hybrid_entry_v1_sample_lineage.md` | Sample cohort lineage |
| `docs/hybrid_entry_v1_backtest.md` | Retrospective results (IN-SAMPLE) |
| `docs/hybrid_entry_v1_forward_shadow_plan.md` | OOS validation plan |

---

## 10. Safety Boundaries

The following are **FORBIDDEN** for this research:

- Modifying MODEL_VERSION v8.0
- Modifying BUY / STRONG_BUY score thresholds
- Modifying foe_v1 calculation logic
- Writing to production Neon ForwardSignal table
- Modifying ACTUAL Trade Service accounting
- Modifying PAPER Position Monitor
- Production Migration (Phase 1B workflow)
- Backfilling production ForwardSignals based on Hybrid research
