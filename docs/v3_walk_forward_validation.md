# V3 Walk-forward Validation & Edge Attribution

**Research Only — Not for Production Deployment**  
Run Date: 2026-11-06 | Parameter Hash: `1feb7a6b294a063d`  
Engine: `v3_walk_forward_v1` | IN-SAMPLE DATA ONLY

---

## 1. Executive Summary

V3 entry timing shows a **+1.33% net_return advantage** over direct entry across 274 in-sample signals at the 5D horizon. Attribution is dominated by **Market Avoidance (+1.73%)**, partially offset by **Entry Timing (−0.39%)**: V3 adds value by not trading bad signals, not by improving entry price when it does trade.

Walk-forward validation is **infeasible** with current data — only 10 signal dates within a 20-day window, all from the same declining market phase. All signals are classified as **RESEARCH_EXPOSED_HISTORY**. Statistical power is insufficient (n=10 date-blocks, not 274 iid signals).

**Final Verdicts:**
- Data: `HISTORICAL_ONLY`
- Performance: `INSUFFICIENT_EVIDENCE`
- Attribution: `MARKET_AVOIDANCE_DRIVEN`
- Next Stage: `PROSPECTIVE_SHADOW_CONDITIONAL`

---

## 2. Data Readiness Audit

| Metric | Value |
|---|---|
| Total buy/strong_buy signals | 344 |
| Signals with ≥5 post bars (5D eligible) | 274 (79.7%) |
| Signals with ≥10 post bars (10D eligible) | 1 (0.3%) |
| Signals with 0 post bars | 0 |
| Max post-signal bars | 17 |
| Signal date range | 2026-10-09 → 2026-10-28 |
| Unique signal dates | 10 |
| Unique stocks | 153 |
| **5D Verdict** | **READY (274 ≥ 50 threshold)** |
| **10D Verdict** | **NOT_READY (1 < 50 threshold)** |
| **20D Verdict** | **NOT_READY (max 17 bars)** |

Largest batch: Oct 9 (99 signals, 36% of universe). Temporal clustering is high.

---

## 3. Research Exposure Audit

**Classification: RESEARCH_EXPOSED_HISTORY (all 344 signals)**

V3 was designed 2026-11-06 with full access to:
- All historical OHLCV data (2024-07-01 through 2026-11-05)
- The complete Oct 2026 signal dataset
- MODEL_VERSION v8.0 scores that produced the signal universe

The signal universe (153 stocks) itself reflects v8.0 scoring on Oct 2026 data. No data partition from V3 design exists. HISTORICAL_HOLDOUT would require signals generated without knowledge of Oct 2026 outcomes. PROSPECTIVE_OOS requires signals generated after V3 design via cron pipeline.

| Classification | Signals | Requirement Met? |
|---|---|---|
| HISTORICAL_HOLDOUT | 0 | No — no data partition from design |
| PROSPECTIVE_OOS | 0 | No — cron pipeline starts Nov 6 |
| **RESEARCH_EXPOSED_HISTORY** | **344 (100%)** | **Yes — only valid classification** |

---

## 4. Walk-forward Protocol

**Verdict: INSUFFICIENT_WALK_FORWARD_DATA**
**Feasible windows: 0**

### Why Walk-forward Fails

**Requirement 1 — Minimum signal dates:** 10 total. Any split leaves ≤5 dates per side.

**Requirement 2 — Temporal separation:** Total date span = 19 days (Oct 9–28). Need ≥20 days between train-end and test-start.

**Requirement 3 — Embargo (holding period isolation):** 5D holds from Oct 14 signals extend to ~Oct 21. If test starts Oct 16, it overlaps holding periods. No clean embargo is achievable within the 20-day window.

**Requirement 4 — Multiple market regimes:** All 10 dates fall in the same declining Oct 2026 phase. Walk-forward requires chronologically distinct market conditions.

### Hypothetical Window (illustrative only)

If a split were attempted at date 5 (Oct 14 / Oct 16):
- Train: Oct 9–14 (~215 signals), Test: Oct 16–28 (~59 signals)
- Temporal gap: 2 days (far below 20-day minimum)
- Embargo violation: Oct 9 5D holds expire Oct 16
- Feasible: **NO**

### Path to Feasibility

Walk-forward becomes feasible when: ≥3 non-overlapping signal periods exist, each with ≥20 signals, separated by ≥20 days, covering multiple market regimes. Expected: Q1 2027 at earliest (Nov 6+ cron signals accumulating).

---

## 5. Frozen Strategy Comparison

All results from `v3_comparison_v1` (Session 27), reproduced here for context.

### 5D Performance (274 signals)

| Strategy | Fill Rate | Mean Net Return | Win Rate | Mean Net Alpha |
|---|---|---|---|---|
| A: Direct | 100.0% | −3.20% | 27.0% | −0.80% |
| B: V1/V2 | 90.1% | −2.48% | 27.5% | +0.00% |
| C: Hybrid | 99.3% | −3.19% | 26.8% | −0.82% |
| **D: V3** | **68.6%** | **−1.86%** | **33.0%** | **+2.82%** |

**Note:** All strategies show negative net returns, reflecting the declining Oct–Nov 2026 market. V3's advantage includes benchmark-inflation from the declining 0050 benchmark (see §8 Attribution Reconciliation).

### V3 Fill Breakdown (274 signals)

| Category | Count | % |
|---|---|---|
| Filled (DIRECT / WAIT-triggered) | 188 | 68.6% |
| Skip (AVOID_CHASING / NO_ENTRY) | 54 | 19.7% |
| Wait trigger unfired | 32 | 11.7% |

---

## 6. Edge Attribution — E1 / E2 / E3

**Attribution basis: net_return (algebraically exact). Net_alpha reported separately but not used for attribution (benchmark exposure differs by fill pattern).**

### Overall Result (274 signals, 5D)

**D − A mean net_return = +1.33%**

| Component | Mechanism | n | Mean Δ | Contribution | Label |
|---|---|---|---|---|---|
| E1: Entry Timing | Both filled | 188 | −0.57% | **−0.39%** | HURTS |
| E2a: D-Skip / A-Fill | Systematic skip | 54 | +5.01% | **+0.99%** | HELPS |
| E2b: D-Wait-Unfired / A-Fill | No trigger fired | 32 | +6.30% | **+0.74%** | HELPS |
| **Total** | | **274** | | **+1.34%** | |

Residual: 0.000000% (algebraically exact).

### E1: Entry Timing (Both-Filled)

On the 188 signals where both V3 and direct entry fill, V3 averages −0.57% worse. V3 wins only 42% of these paired comparisons.

**Interpretation:** V3 does NOT improve entry price when it decides to trade. The entry timing feature has negative incremental value on the in-sample data.

**Selection bias caveat:** This subset excludes the SKIP/WAIT signals where V3 had its biggest advantage. The comparison is biased because V3 filtered harder signals out — the remaining both-filled pool is a selected subset.

### E2a: D-Skip / A-Fill (Market Avoidance)

V3 systematically skipped 54 signals (AVOID_CHASING / NO_ENTRY). Of those:
- **44 avoided losses** (avg A.net_return: −4.15%)
- **10 missed gains** (avg A.net_return: +3.21%)

Net: avoided losses outweigh missed gains by ~4:1 in this period.

**Warning:** This advantage is period-specific. In a strong bull market, every skip becomes a missed gain. This is the primary reversal risk.

### E2b: D-Wait-Unfired / A-Fill (Unfired Trigger)

32 signals where V3 waited for a pullback/breakout trigger that never fired. A_direct filled immediately at −3.20% average. By not filling, V3 implicitly avoided a loss. These are declining stocks where the trigger condition (MA20 bounce, breakout confirm) never occurred within 5D.

### E3: Exposure Reduction

V3 fills 68.6% vs A's 100%. Exposure-matched A (random 68.6% fill with SA-7 for the rest):

- Exposure-matched A expected return: −3.20% × 68.6% = **−2.20%**
- D actual mean: **−1.86%**
- Residual after exposure control: **+0.34%**

The +0.34% residual shows V3's selectivity is better than random — it avoids worse-than-average signals, not just random signals.

---

## 7. Attribution Reconciliation

| Component | Contribution |
|---|---|
| E1 (Entry Timing, n=188) | −0.3879% |
| E2a (Skip, n=54) | +0.9890% |
| E2b (Wait-unfired, n=32) | +0.7363% |
| **Total attributed** | **+1.3374%** |
| Overall observed (D − A) | **+1.3374%** |
| Residual | **0.000000%** |

**Reconciliation passes.** Attribution using net_return is algebraically exact because: for skip/wait-unfired signals, D.net_return=0 and contribution = (0 − A.net_return) × (n/N). No benchmark adjustment required.

**Why net_alpha gives a larger (+3.66%) figure:** When D skips, D.net_alpha = 0 − benchmark ≠ 0 (benchmark is negative in this period). Using 0 − A.net_alpha for E2 introduces a benchmark asymmetry. Net_return attribution avoids this.

---

## 8. Statistical Robustness

### 8.1 Date-Block Bootstrap (Correct Method)

| Parameter | Value |
|---|---|
| Sampling unit | signal_date (10 blocks) |
| Effective independent units | **10** |
| Observed mean (date-level) | +1.33% |
| 95% CI (date-block) | **Very wide — unreliable with n=10** |
| Statistical power | **INSUFFICIENT** |

**Why iid bootstrap (n=274) is wrong:** 99 signals on Oct 9 alone (36%). Signals on the same date share market conditions. Treating 274 pairs as independent inflates statistical power by ~27x. The Session 27 CI of [+2.61%, +4.83%] is misleading.

### 8.2 Stock-Cluster Bootstrap

| Parameter | Value |
|---|---|
| Sampling unit | stock_id (153 clusters) |
| Effective independent units | 153 |
| Observed mean (stock-level) | +1.33% |
| Statistical power | MARGINAL (better than date-block, but single regime) |

Stock clustering gives more independent units but doesn't address the single-regime temporal problem.

### 8.3 Signal Concentration

| Metric | Value | Warning |
|---|---|---|
| Oct 9 date concentration | 36.1% (99/274) | HIGH — one date dominates |
| Max stock concentration | <1% (153 unique stocks) | Low |

A single bad day on Oct 9 could swing the overall result significantly.

---

## 9. Market Regime Stability

**Available regimes: bull (170 signals), unknown (97 signals). No bear regime data.**

| Regime | n | D fill rate | D mean net | A mean net | Delta |
|---|---|---|---|---|---|
| bull | 170 | 69.4% | −1.84% | −3.21% | +1.37% |
| unknown | 97 | 67.0% | −1.90% | −3.19% | +1.29% |

Both regimes show similar deltas because they are both sub-periods of the same Oct 2026 declining market. The "bull" label reflects regime at signal_date, not at exit_date.

**Critical gap:** No bear or strong-bull regime data. V3's SKIP advantage may:
- Persist in bear markets (more signals to avoid)
- **Reverse in strong bull markets** (every skip is a missed gain)

Cross-regime stability cannot be assessed until prospective OOS data covers multiple regimes.

---

## 10. Cost & Execution Sensitivity

| Scenario | D−A Delta | Verdict |
|---|---|---|
| Base (0.585% fees) | +1.33% | ROBUST |
| Higher slippage (+0.10%) | ~+1.23% | MARGINAL |
| Higher fees (0.80%) | ~+1.12% | MARGINAL |
| Conservative (1.00% + 0.20% slip) | ~+0.93% | MARGINAL |
| Low fill probability (50% of WAIT) | ~+0.85% | MARGINAL |

The advantage reduces but does not reverse under higher costs. The skip-based advantage (E2a/E2b) is unaffected by fill costs (D.net_return=0 by SA-7). The sensitivity comes from E1 (both-filled) where higher costs reduce D's gross_return.

---

## 11. Historical Walk-forward Results

No walk-forward results are available. INSUFFICIENT_WALK_FORWARD_DATA.

The comparison data shown above (Sessions 27–28) is **in-sample / RESEARCH_EXPOSED_HISTORY** only. No holdout or prospective OOS results exist.

Expected timeline for genuine OOS:
- 5D prospective: Jan 2027 (if cron generates ≥50 buy/strong_buy signals Nov 6+)
- 10D prospective: Feb 2027
- 20D prospective: Apr 2027
- Multi-regime coverage: depends on market conditions

---

## 12. Final Questions — Q1–Q20

**Q1: Is there any true OOS or holdout data?**
No. All 344 signals are RESEARCH_EXPOSED_HISTORY. Prospective OOS begins Nov 6+ via cron pipeline.

**Q2: How many feasible walk-forward windows?**
0 feasible windows. INSUFFICIENT_WALK_FORWARD_DATA.

**Q3: What horizons are ready?**
5D: 274 eligible. 10D: 1. 20D: 0. Max post bars: 17.

**Q4: Is there a leakage risk in any potential split?**
Yes. 5D holds from train dates overlap test dates. No clean embargo possible in the 20-day window.

**Q5: Can purging/embargo be applied?**
No. All signals are within the same 20-day window; embargo is architecturally infeasible.

**Q6: How stable is performance across walk-forward windows?**
Cannot evaluate — no feasible windows exist.

**Q7: Does D beat B (V1/V2)?**
In-sample: D−B net_alpha = +2.99% (Session 27). RESEARCH_EXPOSED_HISTORY only.

**Q8: Does D beat C (Hybrid)?**
In-sample: D−C net_alpha = +3.68% (Session 27). RESEARCH_EXPOSED_HISTORY only.

**Q9: Does performance hold in a true holdout?**
Cannot be tested — no holdout data available.

**Q10: What drives V3's advantage?**
Primarily Market Avoidance, NOT entry timing. E1 (entry timing for fills): −0.39% (NEGATIVE). E2 (avoidance): +1.73% (POSITIVE). Net total: +1.33%.

**Q11: After controlling for exposure rate, is there residual edge?**
+0.34% residual after exposure-matched control. Small positive, driven by selective stock avoidance.

**Q12: Quality of avoided vs missed signals?**
Skipped 44 losers (avg A loss −4.15%) | Missed 10 winners (avg A gain +3.21%). 4:1 ratio in this period.

**Q13: Does attribution reconcile exactly?**
Yes. E1=−0.3879% + E2a=+0.9890% + E2b=+0.7363% = +1.3374% = observed +1.3374%. Residual=0.000000%.

**Q14: Is advantage stable across market regimes?**
Only bull/unknown regime present (both sub-periods of declining Oct 2026). Bear regime data: 0 signals.

**Q15: Is the statistical power adequate?**
No. iid bootstrap (n=274, used in Session 27) overestimates precision. Date-block bootstrap: n=10 effective units = INSUFFICIENT_STATISTICAL_POWER.

**Q16: Is the advantage cost-sensitive?**
Reduces but does not reverse under higher costs (conservative scenario: +0.93%). Not flagged as COST_SENSITIVE_EDGE.

**Q17: What is the overfitting risk?**
HIGH. V3 designed with access to this exact signal dataset. Single market phase (declining Oct 2026). No OOS validation.

**Q18: What is the overall performance verdict?**
INSUFFICIENT_EVIDENCE. Statistically significant on in-sample data, but only n=10 date-blocks with INSUFFICIENT_STATISTICAL_POWER.

**Q19: Were any production systems modified?**
No. ForwardSignals, Hybrid, Cron, Neon, Prospective Shadow all unchanged. Research-only.

**Q20: Recommended next stage?**
PROSPECTIVE_SHADOW_CONDITIONAL: accumulate prospective signals (Nov 6+), re-run at 20D maturity.

---

## 13. Limitations

1. **RESEARCH_EXPOSED_HISTORY.** V3 was designed with knowledge of the signal distribution. These results validate engine correctness, not strategy superiority.

2. **Single declining market phase.** Oct 2026 is one market regime. SKIP advantage may reverse in a strong bull market.

3. **Date-block statistical power.** n=10 effective independent units. Any CI reported from iid bootstrap (n=274) is misleading by ~27x.

4. **Short horizon (5D only).** Too noisy for conclusive alpha estimation. 20D windows required.

5. **No cross-regime validation.** Bull, sideways, bear regimes not covered.

6. **Attribution caveat on E1.** The both-filled subset has selection bias — V3 filtered the harder signals out, leaving an easier pool for A as well.

7. **Stop reconstruction.** 305/344 signals use MA20×0.97 for stop, which may differ from actual decision-time stops.

---

## 14. Safety Verification

**Boundaries respected:**

| Boundary | Status |
|---|---|
| MODEL_VERSION v8.0 | Unchanged |
| foe_v1 logic | Unchanged |
| BUY / STRONG_BUY thresholds | Unchanged |
| Frozen ForwardSignals | Unchanged |
| ACTUAL / PAPER Accounting | Unchanged |
| Hybrid P1–P4 | Unchanged |
| Prospective Classification | Unchanged |
| Production Deployment | NOT executed |
| Neon Schema Migration | NOT executed |
| Neon Historical Backfill | NOT executed |
| Neon Research Recalculation | NOT executed |
| Production Research SQLite writes | NOT executed |
| Cron Schedule Modification | NOT executed |
| GitHub Actions Activation | NOT executed |
| Decision Center Integration | NOT executed |

All database writes in this research use **temporary in-memory SQLite** (test isolation guaranteed).

---

## 15. Tests & Files

| File | Description |
|---|---|
| `src/research/v3_walk_forward.py` | Engine (ENGINE_ID: `v3_walk_forward_v1`) |
| `tests/test_v3_walk_forward.py` | 40 tests (WF-01 to WF-40) |
| `src/research/v3_comparison_engine.py` | Comparison engine (PARAMETER_HASH: `1feb7a6b294a063d`) |
| `tests/test_v3_comparison_engine.py` | 30 tests (CP-01 to CP-30) |
| `docs/v3_vs_baseline_performance_evaluation.md` | Session 27 results |
| `docs/v3_walk_forward_validation.md` | This document |

**Test count:** 40 WF tests + 30 CP tests = 70 research tests. Full suite: 1861 passed (2026-11-06).

### Test Coverage by Category

| Category | Tests | Coverage |
|---|---|---|
| Research Exposure Audit | WF-01 to WF-06 | Classification, counts, date fields |
| Walk-forward Protocol | WF-07 to WF-12 | Insufficient verdict, windows, hash |
| Edge Attribution | WF-13 to WF-20 | E1/E2a/E2b/E3, avoided/missed counts, labels |
| Attribution Reconciliation | WF-21 to WF-25 | Exact sum, N, bias warning |
| Date-Block Bootstrap | WF-26 to WF-29 | Insufficient warning, determinism, mean |
| Cost Sensitivity | WF-30 to WF-33 | All scenarios, base/conservative, verdict |
| Regime Analysis | WF-34 to WF-36 | Grouping, stat power, all regimes reported |
| Safety Invariants | WF-37 to WF-40 | No production writes, verdicts, warning |

---

## 16. Final Verdict

| Dimension | Verdict |
|---|---|
| **Data classification** | HISTORICAL_ONLY (RESEARCH_EXPOSED_HISTORY) |
| **Walk-forward feasibility** | INFEASIBLE (0 windows) |
| **Performance evidence quality** | INSUFFICIENT_EVIDENCE |
| **Attribution** | MARKET_AVOIDANCE_DRIVEN |
| **Statistical power** | INSUFFICIENT (n=10 date-blocks) |
| **Regime coverage** | SINGLE_REGIME (declining Oct 2026) |
| **Cost sensitivity** | MARGINAL (advantage reduces, doesn't reverse) |
| **Next stage** | **PROSPECTIVE_SHADOW_CONDITIONAL** |

**PROSPECTIVE_SHADOW_CONDITIONAL:** V3 shows a plausible attribution story — market avoidance not entry timing — but the evidence base is in-sample and statistically underpowered. Proceed with:
1. Accumulating prospective signals via cron pipeline (Nov 6+ PROSPECTIVE decisions)
2. Re-running comparison at 10D maturity (est. mid-Dec 2026, need ≥50 eligible OOS signals)
3. Re-running at 20D maturity (est. Jan 2027)
4. Validating in a bull-trending OOS period before any production consideration

**Do NOT use in-sample results as evidence for deployment.** The session 27 net_alpha (+3.66%) is inflated by the declining 0050 benchmark. The correct attribution-based estimate is +1.33% net_return, with INSUFFICIENT statistical confidence (n=10 effective independent units).
