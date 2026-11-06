# V3 Entry Timing Algorithm — Research Design

**Date:** 2026-11-06  
**Status:** Research Prototype Complete  
**Prototype:** `src/research/v3_entry_strategy.py`  
**Tests:** `tests/test_v3_entry_strategy.py` (31 tests, all pass)  
**Research version:** `v3_research_v1`

---

## 1. Background and Motivation

The existing entry timing system (V1/V2, `src/research/entry_timing.py`) has been in production shadow mode since Session 1. The effectiveness analysis in Session 10 established that V1 and V2 produce identical signal distributions (0 label differences across 2,953 signals), indicating V2 did not introduce meaningful signal differentiation.

The V1/V2 analyzer operates on **three inputs only**: `close`, `high`, `volume`. Its MA20 pullback zone uses a fixed ±range regardless of market regime. It ignores MA60 entirely. It does not compute MA slope.

V3 is a **parallel research track** designed to test whether adding:
1. MA60 as an explicit secondary support level
2. MA slope as an entry qualifier
3. Volume signature classification (3-class)
4. Market regime threshold adaptation

...improves risk-adjusted entry timing compared to the V1/V2 baseline. V3 is **not a replacement** for Hybrid V1 (which is frozen at commit 6602c3b). V3 runs as a research-only prototype until OOS evidence justifies a formal evaluation.

---

## 2. V1/V2 Baseline Inventory

### Inputs

| Input | V1/V2 Use |
|---|---|
| `close[-20:]` | MA20 computation |
| `high[-21:-1]` | prior_20d_high (resistance) |
| `volume[-1] / volume[-20:]` | vol_ratio (breakout qualifier only) |

### Indicators NOT used in V1/V2

- MA60 (level or slope)
- MA20 slope
- Low column (not used in any computation)
- Market regime
- Volume trend classification

### Decision labels (V1/V2)

```
ENTRY_READY             → price in MA20 zone, good R/R, volume OK
WAIT_FOR_PULLBACK       → price above MA20 zone
WAIT_FOR_BREAKOUT       → near prior 20D high, no volume breakout yet
TOO_EXTENDED            → MA20 gap too large
RISK_REWARD_UNFAVORABLE → R/R < 2.0
NO_VALID_SETUP          → none of the above
INSUFFICIENT_DATA       → fewer than 21 bars
```

### Structural limitations

1. **MA60 ignored**: Second support level never checked. Stocks that have pulled back to MA60 (but not MA20) always receive `WAIT_FOR_PULLBACK`, missing a valid setup.
2. **No slope filter**: Can enter MA20 pullback even when MA20 is falling, increasing probability of entering a declining trend.
3. **Binary volume**: Only checks `vol_ratio >= 1.0` for breakout confirmation. No 3-bar vs 10-bar trend — cannot detect contracting-volume pullbacks (healthy setup signal).
4. **Fixed zones**: Same MA20 zone regardless of whether market is bull or bear. In bear markets, the zone should be tighter to reduce false entries.
5. **No confidence score**: Binary decision — no way to rank setups when multiple stocks qualify.

---

## 3. V3 Objective

Design and prototype an entry timing algorithm that addresses the five V1/V2 limitations while remaining:
- **Research-only**: no production writes, no Neon writes, no hybrid_forward_decision updates
- **Comparable**: outputs can be compared to V1/V2 and Hybrid V1 on the same signal universe
- **Deterministic**: same input → same output (no randomness, no state)
- **Annotated**: emits reason codes and confidence score for analysis

V3 targets **formal strategy candidates** — stocks that have passed the V8.0 scoring gate and appear in the candidate pool. It does not replace the scoring gate; it refines the entry timing decision once a candidate is identified.

---

## 4. Six Candidate Setups (S1–S6)

### S1 — MA20 Pullback

**Hypothesis**: Stocks pulling back to MA20 in a rising MA20 trend, with contracting volume, offer favorable R/R entries.

**Conditions**:
- Price within [regime_lower, regime_upper]% of MA20
- MA20 slope: rising (> +0.3%/10 bars)
- MA60 slope: not falling (required V3 differentiator vs V1/V2)
- Volume signature: contracting (3D avg / 10D avg < 0.8)

**Decision**: DIRECT_ENTRY (confidence ≥ 55) or WAIT_MA20_PULLBACK (confidence < 55)

### S2 — MA60 Support

**Hypothesis**: When price has extended well above MA20 and pulls back to MA60, the MA60 acts as a second support level in a bull trend.

**Conditions**:
- Price within ±regime_ma60_zone% of MA60
- MA20 > MA60 (structural integrity: short-term above long-term)
- MA60 slope: not falling

**Decision**: DIRECT_ENTRY (confidence ≥ 50) or WAIT_MA60_SUPPORT

### S3 — Breakout Confirmation

**Hypothesis**: A close above the prior 20D high with volume confirmation (vol_ratio ≥ regime_min_vol) is a valid momentum entry.

**Conditions**:
- `close > prior_20d_high` (prior_20d_high = max(high[-21:-1]))
- Breakout premium ≤ regime_max_premium% (not chasing a stale breakout)
- vol_ratio ≥ regime_breakout_min_vol

**Decision**: DIRECT_ENTRY (with volume) or WAIT_BREAKOUT_CONFIRMATION (without volume)

### S4 — Avoid Chasing

**Hypothesis**: Entries when price is too far from MA20, or when a failed breakout has occurred, have poor R/R and high drawdown risk.

**Conditions triggered**:
- MA20 gap ≥ regime_too_extended_pct (overextension)
- Stale breakout: broken resistance but premium > regime_max_premium
- Failed breakout: recent 3-bar peak above resistance, today well below it

**Decision**: AVOID_CHASING

### S5 — Volume Signature Classification

**Hypothesis**: Volume trend over the last 3 bars relative to the 10-bar average is a leading indicator for setup quality.

**Classification**:
- Contracting (3D/10D < 0.8): healthy pullback, boosts confidence
- Expanding (3D/10D > 1.3): distribution risk, reduces confidence
- Neutral: no adjustment

Applied as a confidence modifier to S1 and S2 decisions.

### S6 — Market Regime Threshold Adaptation

**Hypothesis**: Optimal entry zones are narrower in bear markets and wider in bull markets.

**Parameter table**:

| Parameter | Bear | Neutral | Bull |
|---|---|---|---|
| MA20 zone lower | −1.0% | −2.0% | −3.0% |
| MA20 zone upper | +1.5% | +2.5% | +2.0% |
| MA60 zone | ±2.0% | ±3.0% | ±3.0% |
| Too extended | 12% | 15% | 18% |
| Breakout max premium | 3.0% | 4.0% | 5.0% |
| Breakout min vol | 1.5× | 1.3× | 1.2× |

---

## 5. Decision Framework

### Decision Labels

| Decision | Meaning | Entry order |
|---|---|---|
| `DIRECT_ENTRY` | Setup aligned, confidence ≥ threshold → enter at next open | DIRECT_NEXT_OPEN |
| `WAIT_MA20_PULLBACK` | In setup direction but confidence below threshold → watch | CONFIRMED_NEXT_OPEN |
| `WAIT_MA60_SUPPORT` | At MA60 zone but confidence below threshold → watch | CONFIRMED_NEXT_OPEN |
| `WAIT_BREAKOUT_CONFIRMATION` | Near resistance but no volume yet → watch | CONFIRMED_NEXT_OPEN |
| `AVOID_CHASING` | Overextended, failed breakout, or stale breakout → skip | — |
| `NO_ENTRY` | Below both MAs, MA60 falling with no breakout, or no valid setup | — |
| `INSUFFICIENT_DATA` | Fewer than 21 bars → no decision possible | — |

### Decision Priority (hard-coded order)

1. **Failed breakout** → `AVOID_CHASING`
2. **Below both MAs** → `NO_ENTRY`
3. **MA60 falling** → note (RC_MA60_NOT_RISING added; falls through to breakout check)
4. **Too extended** → `AVOID_CHASING`
5. **Stale breakout** (resistance broken, premium > max) → `AVOID_CHASING`
6. **Fresh breakout with volume** → `DIRECT_ENTRY`
7. **Breakout without volume** → `WAIT_BREAKOUT_CONFIRMATION`
8. **Near resistance** → `WAIT_BREAKOUT_CONFIRMATION`
9. **MA20 pullback zone, MA60 falling** → `NO_ENTRY`
10. **MA20 pullback zone, MA60 OK** → `DIRECT_ENTRY` or `WAIT_MA20_PULLBACK`
11. **MA60 support zone, MA60 falling** → `NO_ENTRY`
12. **MA60 support zone, MA60 OK** → `DIRECT_ENTRY` or `WAIT_MA60_SUPPORT`
13. **Above MA20 zone, below resistance** → `WAIT_MA20_PULLBACK`
14. **Default** → `NO_ENTRY`

### Confidence Score (0–100)

Computed per setup path:

**MA20 pullback path** (base 40):
- MA20 rising: +20; MA20 flat: +10; MA20 falling: −10
- Volume contracting in pullback: +15
- Volume expanding in pullback: −10
- MA60 rising: +10
- Price above MA60: +5
- Bull regime: +5; Bear regime: −10
- R/R ≥ 2.0: +10; R/R < 2.0: −15
- DIRECT_ENTRY if confidence ≥ 55; else WAIT_MA20_PULLBACK

**Breakout path** (base 50):
- Volume confirmed: +25
- MA20 rising: +10
- MA60 rising or flat: +10
- Bull regime: +5
- R/R favorable: +5

---

## 6. Execution Realism

V3 inherits the same execution model as V1/V2 and Hybrid V1.

### Entry timing: NEXT_OPEN

All signals generated on close of day T produce a decision for entry at open of day T+1 (`execution_date = T+1`, `entry_order_type = DIRECT_NEXT_OPEN` or `CONFIRMED_NEXT_OPEN`).

No signal uses same-bar fill. This matches the existing `ForwardSignal.execution_type = "NEXT_OPEN"` convention.

### Fill assumptions

- `DIRECT_NEXT_OPEN`: fill at open of T+1 (no price filtering)
- `CONFIRMED_NEXT_OPEN`: trigger requires price action (MA20/MA60 touch or breakout volume) — entry at triggered-open or next qualifying open
- Gap-down at open: fills at open regardless (worst case for WAIT entries)

### INTRABAR_SEQUENCE_UNKNOWN

For WAIT_* decisions with intraday triggers (e.g., price touching MA20), the intrabar sequence is unknown from daily OHLC. Priority: stop is checked first (SA-3 from execution simulator). If the low hits the stop before the trigger, the trade is considered unfilled.

### Fee structure

Round-trip cost: 0.585% (matching execution_simulator.py SA-6). Unfilled entries: 0% return (SA-7).

---

## 7. Three-Layer Experimental Design

### Layer 1 — Historical Backtest (IS)

**Scope**: Full signal universe in `forward_signals` with `is_legacy=False`, grouped by `research_version`.  
**Method**: For each signal, compute V3 entry decision using history up to signal date. Compare entry at V3-decision price vs entry at NEXT_OPEN.  
**Metric**: Average 20-day return, Sharpe, drawdown, hit rate.  
**Bias risk**: IS overfitting — confidence thresholds tuned on IS data may not generalize.

### Layer 2 — Walk-Forward Validation (OOS)

**Method**: Train on the first 70% of the signal chronology (by date), validate on the last 30%. Repeat with 10 rolling folds.  
**Pass criterion**: OOS Sharpe ≥ 0.5× IS Sharpe, no sign flip on mean return.  
**Comparison baseline**: V1/V2 on the same OOS fold.

### Layer 3 — Prospective Shadow

**Method**: Each day the shadow cron runs, V3 computes a decision for every new candidate and stores it with `research_version = "v3_research_v1"` (not written to `hybrid_forward_decision`). After 20 trading days, the actual outcome is available.  
**Stored in**: `hybrid_research_cache` (existing research isolation table).  
**Classification**: All V3 shadow signals are `PROSPECTIVE`, not RETROSPECTIVE.  
**Gate**: V3 shadow does not run if the OHLC continuity gate is BLOCKED.

---

## 8. Evaluation Metrics

### Primary metrics

| Metric | Definition |
|---|---|
| Mean 20D return | Average return across all DIRECT_ENTRY decisions |
| Hit rate | % of DIRECT_ENTRY with return > 0 |
| Sharpe (annualised) | Mean return / std × √252 |
| Max drawdown | Worst peak-to-trough over holding period |
| Avg R/R achieved | Actual reward / risk ratio at exit |

### Comparison framework

For each metric, compute:
- V3 DIRECT_ENTRY vs V1/V2 ENTRY_READY on same signal universe
- V3 DIRECT_ENTRY vs Hybrid V1 DIRECT on same signal universe
- V3 DIRECT_ENTRY vs Direct Next Open (benchmark: buy at next open unconditionally)

### Decision quality metrics

| Metric | Definition |
|---|---|
| Precision@DIRECT | % of DIRECT_ENTRY that outperform Direct Next Open |
| Recall@DIRECT | % of profitable setups captured by DIRECT_ENTRY |
| WAIT conversion rate | % of WAIT_* that eventually trigger and are profitable |
| AVOID accuracy | % of AVOID_CHASING where abstaining was correct |

### Regime-stratified metrics

Separate analysis by market_regime (bull/bear/neutral) to validate regime-adaptive thresholds.

---

## 9. Baseline Comparison

| Baseline | Method | Expected weakness vs V3 |
|---|---|---|
| **Direct Next Open** | Buy all candidates at next open unconditionally | No entry filter — includes poor setups |
| **V1/V2 ENTRY_READY** | V1/V2 decision for the same candidate | No MA60, no slope filter, no regime adaptation |
| **Hybrid V1** | P1-P4 rules combining v2_entry_label + regime + ma20_trend | FROZEN — cannot be modified; only 2 regime categories |

V3 differentiators expected to improve over each baseline:
- vs Direct Next Open: S4 (avoid chasing) and S6 (regime thresholds) filter poor entry timing
- vs V1/V2: MA60 filter (S2) and slope filter reduce entries in declining trends; regime zones (S6) reduce bear-market false entries
- vs Hybrid V1: Explicit MA60 support setup (S2) adds a setup class Hybrid V1 cannot produce; confidence score enables ranking

---

## 10. Research Prototype Implementation

### Files

| File | Purpose |
|---|---|
| `src/research/v3_entry_strategy.py` | Pure-compute prototype; no DB, no side effects |
| `tests/test_v3_entry_strategy.py` | 31 isolated tests (V3-01 to V3-30 + V3-16b) |

### Key constants

```python
RESEARCH_VERSION = "v3_research_v1"
MIN_BARS_MA20 = 21      # MA20 + prior_20d_high without look-ahead
MIN_BARS_MA60 = 61      # MA60 required
MIN_BARS_SLOPE = 31     # MA20 slope window
MIN_BARS_FULL = 71      # MA60 slope window (60 + 10 + 1)
STOP_BUFFER = 0.03      # mirrors V1/V2 execution_simulator
MIN_RR_RATIO = 2.0      # mirrors V1/V2
MA20_RISING_THRESHOLD = 0.3   # slope %/10 bars
MA20_FALLING_THRESHOLD = -0.3
VOL_CONTRACTING_RATIO = 0.8   # 3D/10D avg < 0.8
VOL_EXPANDING_RATIO = 1.3     # 3D/10D avg > 1.3
```

### Output dataclass: `V3EntryDecision`

Key fields:
- `entry_decision`: one of 7 decision labels
- `confidence`: float 0–100
- `research_version`: always `"v3_research_v1"`
- `setup_type`: sub-label for internal routing
- `market_regime`, `ma20_gap_pct`, `ma60_gap_pct`, `ma20_trend`, `ma60_trend`
- `prior_20d_high`, `resistance_broken`, `near_resistance`, `failed_breakout`
- `vol_ratio`, `volume_signature`, `vol_contraction_in_pullback`
- `entry_price`, `stop_price`, `target_price`, `rr_ratio`
- `proposed_limit_price`, `invalidation_price`
- `reason_codes`: List[str] — always populated
- `data_quality_status`: "OK" or "PARTIAL" (when MA60 unavailable)
- `research_capture_type`: always "RESEARCH_ONLY"

### Test coverage

| Test range | Coverage area |
|---|---|
| V3-01 to V3-06 | All 4 DIRECT_ENTRY and 2 WAIT paths |
| V3-07 to V3-11 | AVOID_CHASING and NO_ENTRY paths |
| V3-12 | Regime threshold adaptation |
| V3-13 | MA60 falling blocks MA20 pullback (key V3 differentiator) |
| V3-14 to V3-15 | Volume signature effect on confidence |
| V3-16 to V3-17 | Insufficient data and PARTIAL quality handling |
| V3-18 | No look-ahead (prior_20d_high uses [-21:-1]) |
| V3-19 | Determinism |
| V3-20 | Research version constant |
| V3-21 | No production imports (source code scan) |
| V3-22 | No Hybrid V1 contamination |
| V3-23 to V3-24 | Confidence bounds, reason codes populated |
| V3-25 to V3-26 | Missing column graceful handling |
| V3-27 | Price gap: prior high uses historical high correctly |
| V3-28 to V3-29 | Conflict scenario and regime threshold inequality |
| V3-30 | R/R unfavorable degrades decision |

---

## 11. Safety Boundaries

The following actions are **forbidden** for V3 at this research stage:

| Forbidden action | Reason |
|---|---|
| Production V3 Deployment | Not validated on OOS data |
| Neon Schema Migration | Research-only; SQLite only |
| Neon Historical Backfill | Research-only |
| Neon Research Recalculation | Research-only |
| Decision Center Integration | V3 not in decision flow |
| Modifying MODEL_VERSION v8.0 | Frozen production scoring |
| Modifying foe_v1 | Frozen scoring engine |
| Modifying BUY/STRONG BUY thresholds | Frozen scoring thresholds |
| Modifying Frozen ForwardSignals | Frozen signal history |
| Modifying ACTUAL/PAPER accounting | Out of research scope |
| Modifying Hybrid V1 (P1–P4) | Frozen at commit 6602c3b |
| Modifying Prospective classification | Shadow integrity |
| Cron schedule modification | Live cron is running |
| GitHub Actions activation | Manual control only |

The source code enforcement is tested by V3-21 (source scan) and V3-22 (no Hybrid V1 contamination).

---

## 12. Final Questions

The following questions remain open and will be answered by running the three experimental layers.

**Q1: Does MA60 as a support level add alpha over V1/V2?**  
Null hypothesis: Mean 20D return for WAIT_MA60_SUPPORT decisions is not statistically different from WAIT_FOR_PULLBACK on the same candidate universe. Test with bootstrap CI on OOS fold.

**Q2: Does MA60 slope filtering (blocking MA20 pullback when MA60 falling) reduce false entries in bear markets?**  
Measure: Hit rate of DIRECT_ENTRY decisions in bear regime with vs without the MA60 slope filter. Expected: filtering removes 15–25% of entries, improves hit rate by >5pp.

**Q3: Does regime-adaptive zone sizing improve signal quality in bear markets?**  
Compare bear-regime DIRECT_ENTRY count and return: V3 (tighter zone) vs V1/V2 (fixed zone). Expected: V3 fires fewer but higher-quality entries in bear.

**Q4: What is the optimal confidence threshold for DIRECT_ENTRY?**  
Current threshold = 55 for MA20 path, 50 for MA60 path. OOS grid search over [45, 50, 55, 60, 65] to find the threshold that maximises OOS Sharpe without overfitting.

**Q5: Does volume contraction during pullback predict better outcomes?**  
Compare 20D return: `vol_contraction_in_pullback=True` vs `False` within DIRECT_ENTRY decisions. Expected: contracting volume improves mean return by >1%.

**Q6: What is the WAIT_* conversion rate in prospective shadow?**  
% of WAIT_MA20_PULLBACK and WAIT_MA60_SUPPORT that trigger within 5 trading days. If <30%, WAIT decisions add little value over NO_ENTRY.

**Q7: Does AVOID_CHASING correctly filter poor outcomes?**  
Measure: Average 20D return if AVOID_CHASING signals had been entered at NEXT_OPEN (counterfactual). If positive, the filter is over-cautious.

**Q8: What is the information coefficient (IC) of the confidence score?**  
Rank-correlation between confidence and 20D return. If IC < 0.05, the confidence score has no predictive value.

**Q9: Does V3 outperform Hybrid V1 on a combined metric (Sharpe × recall)?**  
Single combined metric to avoid cherry-picking. V3 must beat Hybrid V1 on the same OOS fold before any escalation decision.

**Q10: Are regime labels (bull/bear/neutral) derived externally or computed internally?**  
V3 currently accepts `market_regime` as an input from the caller. The quality of the regime label is a dependency. If the regime label is wrong >25% of the time (from `PriceTrendAnalyzer`), regime adaptation is noise.

**Q11: Does the MA60 support setup fire frequently enough to matter?**  
If WAIT_MA60_SUPPORT fires on <5% of candidates, its contribution to overall alpha is negligible. Measure prevalence before tuning.

**Q12: What is the false negative rate for AVOID_CHASING on breakouts?**  
Measure: % of AVOID_CHASING decisions triggered by `breakout_max_premium` where the stock continued to rise another 10%+. If >30%, the stale-breakout threshold may be too tight.

**Q13: Does the 3-class volume signature improve over V1/V2 binary vol_ratio in predicting breakout success?**  
Compare: breakout success rate (20D return > 5%) segmented by `vol_ratio >= 1.0` (V1/V2 method) vs `volume_signature == "expanding"` (V3 method). Expected: V3 volume classification is more discriminative.

**Q14: Is the failed_breakout detection (3-bar peak above resistance, today below) adding value or adding noise?**  
Measure: Average 20D return for failed_breakout=True signals if entered anyway. If average return is positive (>2%), the filter is too aggressive and the 97% threshold should be tightened.
