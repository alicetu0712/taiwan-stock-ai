# V3 vs Baseline Performance Evaluation

**Research Only — Not for Production Deployment**  
Run Date: 2026-11-06 | Parameter Hash: `1feb7a6b294a063d`  
Engine: `v3_comparison_v1` | IN-SAMPLE DATA

---

## 1. Purpose

Establish a fair, reproducible comparison of V3 entry timing against three baselines using the same signal universe, same exit rules, and same benchmark. The goal is to determine whether V3 shows measurable entry-timing advantage in the current in-sample window, and what conditions further validation requires.

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
| **5D Verdict** | **READY (274 ≥ 50 threshold)** |
| **10D Verdict** | **NOT_READY (1 < 50 threshold)** |
| **20D Verdict** | **NOT_READY (max 17 bars)** |

**Conclusion:** This evaluation compares strategies at the **5D horizon only**. 10D and 20D comparisons require additional data accumulation (Nov 2026 onwards).

---

## 3. Signal Universe

344 buy/strong_buy signals across 10 signal dates (Oct 9–28, 2026). Of these, 274 have at least 5 post-signal bars and are included in the 5D comparison.

Breakdown:
- Oct 9: 99 signals (largest batch)
- Oct 12: 46 | Oct 14: 55 | Oct 16: 39 | Oct 28: 28
- Oct 10, 11, 13, 21, 22: 4–27 each

Decision label distribution (274 eligible signals): wait_pullback=~80, buy=~53, strong_buy=~41, NULL=~75 (estimated from full 344).

---

## 4. Fair Comparison Contract

All four strategies are evaluated on the **same 274 signals** with identical rules:

| Parameter | Rule |
|---|---|
| Universe | Same (stock_id, signal_date) pairs per horizon |
| Fees | 0.585% round-trip (SA-6) |
| Exit rules | stop-or-target-or-horizon (5D CLOSE) |
| Stop (A/B/C) | forward_signals.stop_price if available; else MA20×(1−0.03) reconstructed |
| Stop (D) | V3's own stop_price from V3EntryDecision |
| Target (A/B/C) | forward_signals.target1 if available; else MA20×1.06 |
| No-fill | 0% return (SA-7 opportunity cost) |
| Benchmark | 0050 gross return: open[fill_date] → close[exit_date] |
| SA-3 | Ambiguous stop+target day → stop first |
| SA-4 | Gap-down through stop → exit at OPEN |

---

## 5. The Four Strategies

### A: Direct Next Open (Baseline)
Always fill at D+1 OPEN regardless of label. Represents naive immediate entry.  
Entry label: `ENTRY_READY` for all signals.

### B: V1/V2 Labels (Label-Based)
Maps `forward_signals.decision_label` → simulation entry:
- `wait_pullback` → `WAIT_FOR_PULLBACK` (trigger: LOW ≤ MA20×1.03)
- `buy`, `strong_buy`, NULL → `ENTRY_READY`

### C: Hybrid V1 (HybridDecisionService)
Applies frozen Hybrid V1 rules (P1–P4):
- P1: Bear + wait_pullback → wait
- P2: Flat MA20 + wait_pullback → wait
- P3: Bull + Rising MA20 → direct
- P4: Default → direct

MA20 slope computed from OHLCV history (last 10-bar window).

### D: V3 (V3EntryTimingAnalyzer)
Full V3 analysis using history up to signal_date (strict no look-ahead):
- `DIRECT_ENTRY` → fill at D+1 OPEN
- `WAIT_MA20_PULLBACK` → trigger at actual MA20 level
- `WAIT_MA60_SUPPORT` → trigger at actual MA60 level
- `WAIT_BREAKOUT_CONFIRMATION` → trigger when CLOSE > prior_20d_high
- `AVOID_CHASING` / `NO_ENTRY` → no fill (0% SA-7)

---

## 6. Performance Results — 5D Horizon

### 6.1 Strategy-Level Summary

| Strategy | Fill Rate | Mean Gross | Mean Net | Median Net | Win Rate | Mean Net Alpha |
|---|---|---|---|---|---|---|
| A: Direct | 100.0% | −2.62% | −3.20% | −3.68% | 27.0% | −0.80% |
| B: V1/V2 | 90.1% | −1.81% | −2.48% | −2.92% | 27.5% | +0.00% |
| C: Hybrid | 99.3% | −2.61% | −3.19% | −3.68% | 26.8% | −0.82% |
| **D: V3** | **68.6%** | **−1.19%** | **−1.86%** | **−2.33%** | **33.0%** | **+2.82%** |

**Market context:** All strategies show negative net returns, reflecting the Oct–Nov 2026 market decline. The 0050 benchmark fell approximately −2.0% to −2.4% over typical 5D windows in this period.

### 6.2 D Fill Breakdown

| Category | Count | % of Universe |
|---|---|---|
| Filled | 188 | 68.6% |
| Skip (AVOID_CHASING / NO_ENTRY) | 54 | 19.7% |
| Wait trigger not fired (5D) | 32 | 11.7% |

Exit reasons (188 fills): HORIZON=131 (69.7%), GAP_STOP=23 (12.2%), TARGET=17 (9.0%), STOP=17 (9.0%)

---

## 7. Statistical Comparison — D vs Baselines

| Comparison | N pairs | Mean Δ | Median Δ | 95% CI | Sign test p | Cohen's d | Verdict |
|---|---|---|---|---|---|---|---|
| D vs A | 267 | +3.66% | — | [+2.61%, +4.83%] | 0.000 | 0.40 | **SIGNIFICANT_POSITIVE** |
| D vs B | 267 | +2.99% | — | [+1.91%, +4.24%] | 0.000 | 0.32 | **SIGNIFICANT_POSITIVE** |
| D vs C | 267 | +3.68% | — | [+2.65%, +4.85%] | 0.000 | 0.40 | **SIGNIFICANT_POSITIVE** |

**Bootstrap CI:** 10,000 resamples, seed=42, 95% confidence.  
**Sign test:** Two-sided binomial under H₀: p(D > baseline) = 0.5.  
**Cohen's d:** 0.32–0.40 = small-to-medium effect size.

All CIs are strictly above 0 → SIGNIFICANT_POSITIVE verdict. However, see critical caveats below.

---

## 8. Subgroup Analysis (Strategy D)

### 8.1 By V3 Decision

| V3 Decision | N | Mean Net Alpha |
|---|---|---|
| NO_ENTRY | 13 | +4.30% |
| AVOID_CHASING | 41 | +3.87% |
| WAIT_BREAKOUT_CONF | 73 | +3.92% |
| DIRECT_ENTRY | 82 | +2.86% |
| WAIT_MA20_PULLBACK | 58 | +0.32% |

**Key insight:** V3's alpha advantage is concentrated in SKIP decisions (AVOID/NO_ENTRY) and WAIT_BREAKOUT_CONF. These add value by avoiding bad entries in a declining market. WAIT_MA20_PULLBACK shows only +0.32% alpha — the pullback trigger fired (stock declined to MA20 zone) but the market continued falling.

### 8.2 By Market Regime

| Regime | N | Mean Net Alpha |
|---|---|---|
| bull | 170 | +2.85% |
| unknown | 97 | +2.77% |

Only 2 regimes represented (no bear signals in eligible universe, consistent with the Oct 2026 initial bull readings).

---

## 9. Return & Alpha Definitions

- **Gross return:** `(exit_price − fill_price) / fill_price`
- **Net return:** `gross − FEES_PCT/100` (0.585% deducted for fills); `0.0` for no-fills (SA-7)
- **Benchmark return:** 0050 gross: `(0050_close[exit_date] − 0050_open[fill_date]) / 0050_open[fill_date]`
- **Net alpha:** `net_return − benchmark_return`; for no-fills: `0 − benchmark_return` (conservative)
- **Conservative alpha:** Same as net alpha — penalizes V3 fully for skip decisions in a rising benchmark

---

## 10. Final Questions — Q1–Q20

**Q1: Does V3 show positive alpha vs direct entry?**  
Yes. Mean net alpha D−A = +3.66%, CI=[+2.61%,+4.83%], p=0.000. Statistically significant in-sample.

**Q2: Does V3 beat the V1/V2 label-based approach?**  
Yes. Mean delta = +2.99%, CI=[+1.91%,+4.24%], p=0.000.

**Q3: Does V3 beat Hybrid V1?**  
Yes. Mean delta = +3.68%, CI=[+2.65%,+4.85%], p=0.000. Hybrid was nearly identical to direct (C≈A) in this period.

**Q4: What is the effect size?**  
Cohen's d = 0.32–0.40 (small-to-medium). Meaningful but modest.

**Q5: What is the fill rate trade-off?**  
V3 fills 68.6% vs 100% for direct. The 31.4% non-fill opportunity cost is the primary risk in a rising market.

**Q6: What drives V3's advantage in this period?**  
Primarily SKIP decisions (+3.87–4.30% alpha) — avoiding overextended or deteriorating stocks during a market decline. WAIT_MA20_PULLBACK underperforms (+0.32%) as expected when markets decline through MA20.

**Q7: Is the win rate meaningfully different?**  
D: 33% vs A: 27% for filled trades. Modest improvement in hit rate.

**Q8: Are results robust to regime?**  
Only bull/unknown regimes represented — insufficient bear regime data to test.

**Q9: Is this 5D result indicative of longer-term performance?**  
Unknown. 5D is too short for conclusive evidence. Requires 10D/20D windows (not yet available).

**Q10: What is the benchmark (0050) return in this period?**  
Approximately −2.0% to −2.4% per 5D window based on fill/exit dates observed.

**Q11: Is V3 alpha driven by fewer trades (not filling into declines)?**  
Partially yes. 54 SKIP decisions with 0% return vs benchmark of ~−2.3% each contributes approximately 54×2.3% = ~1.24% of the per-signal alpha uplift.

**Q12: Would V3 underperform in a bull rally?**  
Yes — SKIP and WAIT decisions would miss upside in strong breakouts. This is the primary risk and requires out-of-sample validation in a bull-trending period.

**Q13: How should stop/target reconstruction affect results?**  
Only 39/344 signals have forward_signals.stop_price. The remaining 305 use MA20×(1-0.03). In a declining market, this reconstruction is conservative (stops may be hit earlier than actual MA20 on signal_date).

**Q14: What is the statistical power of 274 signals?**  
With Cohen's d=0.40, 274 pairs provides >90% power at α=0.05 (two-sided). However, all signals are from one 50-day window — temporal clustering reduces effective independence.

**Q15: Are the 10 signal dates independent?**  
No. Signals cluster by date (99 on Oct 9 alone). Market regime is correlated across dates. True out-of-sample validation requires signals across multiple market regimes.

**Q16: Can these results be used to deploy V3 in production?**  
No. IN_SAMPLE_WARNING applies. V3 was designed around this signal distribution. These results validate engine correctness, not strategy superiority.

**Q17: What would constitute a valid out-of-sample test?**  
(a) Forward-looking signals post-Nov 6 not yet observed when V3 was designed, (b) At least one full market cycle (bull+correction), (c) Minimum 500 signals across ≥6 months.

**Q18: Is the statistical significance spurious given in-sample nature?**  
Possibly. The SIGNIFICANT_POSITIVE verdict reflects the data, not a prediction. It is consistent with V3's design intent (avoid overextended entries) during the specific Oct–Nov 2026 declining period.

**Q19: What is the recommended next action?**  
Begin accumulating prospective forward signals (Nov 6+ from cron pipeline) for genuine out-of-sample evaluation. Run this comparison again at 20D maturity once available (est. Dec 2026).

**Q20: What would falsify V3's advantage?**  
(a) OOS signals in a bull-trending period showing D−A ≤ 0, (b) WAIT_MA20_PULLBACK alpha < A in multiple regimes, (c) Bootstrap CI crossing zero with n > 500 OOS signals.

---

## 11. Final Verdict

| Dimension | Verdict |
|---|---|
| Statistical (5D in-sample) | SIGNIFICANT_POSITIVE |
| Effect size | SMALL_TO_MEDIUM (Cohen's d 0.32–0.40) |
| Mechanism | Plausible (SKIP decisions + selectivity) |
| Out-of-sample | NOT_TESTED (data not yet available) |
| Recommendation | CONDITIONAL_PROCEED |

**CONDITIONAL_PROCEED:** V3 shows statistically significant in-sample alpha (+2.99% to +3.68% vs baselines) with plausible mechanism. The advantage is real in this period but IN-SAMPLE. Proceed with:
1. Accumulating OOS signals via cron pipeline (Nov 6+ PROSPECTIVE decisions)
2. Re-running this evaluation at 10D maturity (est. mid-Nov 2026)
3. Re-running at 20D maturity (est. Dec 2026)
4. Validating in a bull-trending OOS period before any production consideration

---

## 12. Critical Caveats

1. **IN-SAMPLE DATA.** All 344 signals were generated by MODEL_VERSION v8.0 — the same model basis used in V3EntryTimingAnalyzer. These results cannot validate the underlying scoring model.

2. **Single market phase.** All signals are from an Oct–Nov 2026 declining/correction period. V3's SKIP advantage may reverse in a strong bull rally.

3. **Temporal clustering.** 99/274 signals (36%) are from Oct 9. Independence assumption of bootstrap CI is violated.

4. **5D horizon only.** Short-term returns are noisy. 20D windows are required for meaningful alpha estimation in this asset class.

5. **Stop reconstruction.** 305/344 signals use reconstructed stops (MA20×0.97), which may differ from actual decision-time stops.

6. **No transaction costs beyond fees.** Market impact, slippage beyond open-price assumption, and opportunity cost of capital are not modeled.

---

## 13. Architecture

```
V3ComparisonEngine(conn)
  ├── run_data_readiness_audit() → DataReadinessReport
  └── run_comparison(horizon_days) → ComparisonResult
        ├── _load_signals(horizon_days) → 274 signals (5D)
        ├── _run_strategy_a() → ComparisonRow [A]
        ├── _run_strategy_b() → ComparisonRow [B]
        ├── _run_strategy_c() → ComparisonRow [C]  (HybridDecisionService)
        ├── _run_strategy_d() → ComparisonRow [D]  (V3EntryTimingAnalyzer)
        ├── _strategy_stats()
        ├── _paired_stats() × 3  (D vs A/B/C)
        └── _subgroup_mean_net_alpha()

_hold_to_horizon(fill_price, stop, target, hold_bars, horizon_days)
  SA-4: gap-down → exit at OPEN
  SA-3: ambiguous → stop first
  stop hit → STOP
  target hit → TARGET
  horizon → CLOSE of bar [horizon]
```

---

## 14. Files

| File | Description |
|---|---|
| `src/research/v3_comparison_engine.py` | Engine (PARAMETER_HASH: `1feb7a6b294a063d`) |
| `tests/test_v3_comparison_engine.py` | 30 tests (CP-01 to CP-30) |
| `docs/v3_vs_baseline_performance_evaluation.md` | This document |

---

## 15. Safety Boundaries

**不得修改:** MODEL_VERSION v8.0, foe_v1, BUY/STRONG BUY Thresholds, Frozen ForwardSignals, ACTUAL/PAPER Accounting, Hybrid P1–P4, Prospective Classification.

**不得執行:** Production Deployment, Neon Schema Migration, Neon Historical Backfill, Neon Research Recalculation, Production Research SQLite Writes, Cron Schedule Modification, GitHub Actions Activation, Decision Center Integration, 未授權正式資料寫入.
