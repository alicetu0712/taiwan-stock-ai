# Session 42 Final Verdict — Trading Calendar Integrity & Statistical Evidence Repair

**Date:** 2026-11-09
**Session:** 42
**Tests:** 2335 passed, 1 skipped (+62 from S42)

---

## PART M: 20 Final Questions

### Q1: What was the core question Session 42 set out to answer?

"V3 的歷史績效改善，在修正交易日期、統計分群、比較基準與樣本重疊問題後，究竟還剩下多少可信證據？"

**Answer:** After all corrections, D_v3 vs A_direct grand mean = **+1.21%** (CI: [-0.93%, +3.35%], p=0.191, SIGNIFICANCE_INCONCLUSIVE). The corrected number is substantially lower than both S40 (+3.66% signal-level) and S41 (+6.49% signal-date cluster). The direction is positive but statistically indistinguishable from zero.

---

### Q2: What percentage of comparison signals were on non-trading days?

**39.1% (107/274).** Oct 09, 10, 11 are confirmed non-trading days via `daily_prices` ground truth:
- Oct 09: Pre-National Day holiday (補假)
- Oct 10: National Day (國慶日) + Saturday
- Oct 11: Sunday

---

### Q3: How does fill-date clustering change the grand mean?

| Session | Method | Grand Mean |
|---|---|---|
| S40 | Signal-level | +3.66% |
| S41 | 7 signal-date clusters | +6.49% |
| **S42** | **5 fill-date clusters** | **+1.21%** |

The S41 method treated Oct 09/10/11 as separate clusters. Oct 10 (n=4) and Oct 11 (n=4) had extreme micro-cluster means (+10%, +30%), inflating the S41 grand mean to +6.49%. S42 merges them into the Oct 12 fill-date cluster, yielding +1.21%.

---

### Q4: Why is Oct 14 → fill Oct 16 (not Oct 15)?

The `forward_signals.execution_date` for Oct 14 signals is Oct 16. This was set when the NEXT_OPEN pipeline computed execution. It may reflect that Oct 15 was excluded from the execution schedule (possibly an additional market closure or Neon data availability lag at time of computation). The key insight: `execution_date` in the DB, not simply "next calendar/trading day," is the authoritative fill date.

---

### Q5: How do the 5 fill-date cluster windows overlap?

| Pair | Overlap (calendar days) |
|---|---|
| Oct 12–16 ∩ Oct 13–19 | 4 days |
| Oct 13–19 ∩ Oct 14–20 | 6 days |
| Oct 14–20 ∩ Oct 16–22 | 5 days |
| Oct 16–22 ∩ Oct 21–29 | 2 days |

**4/4 adjacent pairs overlap.** This means effective independent N < 5, and the t-test p=0.191 is OPTIMISTIC. True p-value under HAC correction would be even higher.

---

### Q6: What does D_v3 vs B_v1v2 = +0.32% mean?

V3 barely outperforms V1/V2 when measured at the fill-date cluster level. p=0.773 — this is essentially null evidence. If V3's value comes purely from V3-specific decisions (vs the V1/V2 baseline that already includes combined scoring), there is no detectable advantage in the Oct 2026 window.

---

### Q7: Which guardrails FAIL?

| Guardrail | Status | Issue |
|---|---|---|
| G01: Calendar | FAIL | 39.1% non-trading day signals |
| G03: Cluster Count | FAIL | 5 clusters, need ≥10 |
| G04: Overlap | FAIL | 4/4 adjacent pairs overlap |

Three failures make this GUARDRAILS_CONDITIONAL (not PASS). No result derived from this dataset should be treated as production-grade evidence.

---

### Q8: What is the corrected attribution of V3's performance advantage?

MARKET_AVOIDANCE_DRIVEN (confirmed from S41, unchanged):
- AVOID_CHASING: +6.38% paired alpha (n=41, dominant driver — V3 avoided stocks that fell)
- DIRECT_ENTRY: -0.56% (V3 direct fills slightly underperform A_direct)
- NO_ENTRY: +0.67% (marginal)

October 2026 market was declining (0050 at -2.16% over comparison window). V3's advantage is "not being in losing trades," not "being in winning trades."

---

### Q9: Is the corrected 0050 benchmark recomputed?

Yes. S40 used -4.65% (computed from wrong dates Oct 12-28). S42 computes from actual fill dates (Oct 12/13/14/16/21) → **-2.16%**. The benchmark is less negative than previously documented, meaning S40 overstated how bad the market environment was.

---

### Q10: What is the statistical power situation?

To detect +1.21% effect with 80% power (α=0.05, σ=1.59%):
- Need: N ≈ 23 independent clusters
- Have: 5 clusters (effective 1-2 due to overlap)
- Gap: ~18+ more independent clusters needed

At ~5 non-overlapping fill-date clusters per month: **~3-4 months** to reach adequate power. This is the minimum timeline before statistical evidence can support RANKING_CONDITIONAL → RANKING_SUPPORTED.

---

### Q11: Does S42 change the RANKING_CONDITIONAL verdict?

**No change.** RANKING_CONDITIONAL is maintained. The corrections strengthen the case that the data is insufficient to upgrade, but the direction remains positive. No downgrade to RANKING_NOT_SUPPORTED because the direction is consistently positive across all 5 clusters and 3 comparators.

---

### Q12: Does LOCO (Leave-One-Cluster-Out) show sign changes?

**No.** 0/5 sign changes. Grand means in LOCO range: +0.74% to +1.68% (narrower than S41's 2.45%-7.83% from LODO). The magnitude is now more stable because micro-cluster inflation is removed.

---

### Q13: What is the key difference between S41 and S42 significance findings?

| Aspect | S41 | S42 |
|---|---|---|
| Grand mean | +6.49% | +1.21% |
| Cluster count | 7 | 5 |
| Micro-cluster inflation | Yes (Oct 10+11 n=4 each) | Removed (merged into Oct 12) |
| CI | [-3.95%, +16.93%] | [-0.93%, +3.35%] |
| Verdict | SIGNIFICANCE_INCONCLUSIVE | SIGNIFICANCE_INCONCLUSIVE |

Both sessions reach the same verdict (INCONCLUSIVE) but for cleaner reasons in S42. S41's CI was wide due to micro-cluster variance. S42's CI is narrower and more reliable.

---

### Q14: Are there any signals with mature 20D outcomes yet?

**Not yet.** All 344 October 2026 signals have `fwd_return_20d = NULL`. Oct 09-11 signals (fill Oct 12) will mature ~Nov 10, which is 1 day from the evaluation date. Full maturity for all Oct 2026 signals: ~Dec 02.

---

### Q15: What is the significance of D_v3 vs B_v1v2 being near zero?

V3 vs B_v1v2 is the most rigorous comparison (V3 vs the existing hybrid V1/V2 that already has combined scoring). +0.32%, p=0.773 means: given the current evidence, V3 offers no measurable improvement over V1/V2 combined. This is the strictest comparator and the most pessimistic result.

---

### Q16: Why does the Oct 12 cluster (non-trading signals) have +2.62% delta?

The 107 signals generated Oct 09-11 (national holiday period) filled on Oct 12. The Oct 12-16 holding window happened to perform +2.62% better for V3 than A_direct. This is one data point. Without knowing whether V3's AVOID_CHASING or WAIT decisions during that specific period drove the outperformance, no causal attribution can be made.

---

### Q17: How should researchers cite V3 performance going forward?

**Required citation format:**
> "V3 5D corrected grand mean vs A_direct: +1.21% (95% CI [-0.93%, +3.35%], p=0.191, N=5 fill-date clusters, Oct 2026, SIGNIFICANCE_INCONCLUSIVE). S40 SIGNIFICANT_POSITIVE formally retracted (S41, confirmed S42). Calendar contamination: 39.1% signals on non-trading days (corrected by fill-date clustering). Three statistical guardrails FAIL (G01, G03, G04)."

---

### Q18: Is there any path to V3 activation from these results?

**No, ACTIVATION_BLOCKED unchanged.** Required conditions:
1. ≥10 independent fill-date clusters → ~2-3 months
2. CI lower bound > 0 → requires more data
3. G01 (calendar) fixed → production signal filter needed
4. G03 (cluster count) → time
5. G04 (overlap) → switch to 20D horizon with monthly batching
6. 20D outcome comparison → requires Nov/Dec data + authorization

---

### Q19: Were any production systems modified?

**No, all production systems unchanged:**
- Crontab hash: `3acaf480cb5dcdd44f40dd9d464955a1` (FROZEN)
- Production SQLite (data/platform.db): Read-only
- `forward_signals`: No writes
- `fwd_return_20d`: Still NULL (not filled)
- MODEL_VERSION v8.0: Unchanged
- foe_v1: Unchanged
- Hybrid P1–P4: Unchanged
- V3 Frozen Parameters: Unchanged (PARAMETER_HASH be43e8ca)
- Decision Center: Unchanged
- ACTUAL / PAPER / V3: Not activated

---

### Q20: What is the single most important next research action?

**Authorize research-only 20D outcome computation after 2026-11-14.**

After Oct 09-16 signals mature (~Nov 10-14):
1. Run research script: compute 20D returns from `daily_prices` into research cache
2. This unblocks EG-08a and enables a 20D horizon comparison
3. 20D horizon avoids the 5D window overlap problem (non-overlapping monthly batches)
4. Combined with 5D results: provides two independent horizons on the same October 2026 signals

This does NOT require Neon access, cron changes, or any production modification.

---

## PART N: Final Verdict Enums

```python
# Session 42 Final Verdicts

CALENDAR_INTEGRITY = "CALENDAR_FAILED"
# 107/274 (39.1%) signals on non-trading days (Oct 09, 10, 11)
# Root cause: cron runs on holidays; execution_date = NULL for these signals
# Fix applied: merged into fill-date cluster (Oct 12); future fix: production filter

OBSERVATION_UNIT = "OBSERVATION_UNIT_CORRECTED"
# 7 signal-date clusters (S41) → 5 fill-date clusters (S42)
# execution_date is authoritative fill date; daily_prices next-TD as fallback
# Overlapping windows: 4/4 adjacent pairs overlap; effective N ≤ 2

BENCHMARK_LABELS = "BENCHMARK_CORRECTED"
# 6 corrections documented (CR-B01 through CR-B06)
# Most critical: DIRECT_ENTRY alpha sign flip (-0.56% not +2.86%)
# 0050 benchmark: -2.16% (corrected from -4.65%)

CORRECTED_5D_COMPARISON = "ALL_COMPARISONS_SIGNIFICANCE_INCONCLUSIVE"
# D_v3 vs A_direct: +1.21%, CI [-0.93%, +3.35%], p=0.191
# D_v3 vs B_v1v2: +0.32%, CI [-2.59%, +3.24%], p=0.773
# D_v3 vs C_hybrid: +1.19%, CI [-0.91%, +3.29%], p=0.191
# All CIs include zero; S40 SIGNIFICANT_POSITIVE formally retracted

STATISTICAL_GUARDRAILS = "GUARDRAILS_CONDITIONAL"
# G01: FAIL (calendar), G03: FAIL (cluster count), G04: FAIL (window overlap)
# G08: CONDITIONAL (multiple comparison), G10: CONDITIONAL (ETF contamination)
# G02, G05, G06, G07, G09: PASS

ATTRIBUTION = "MARKET_AVOIDANCE_DRIVEN_CONFIRMED"
# Unchanged from S41. Corrections improved label accuracy, not conclusion.

ROBUSTNESS = "DIRECTIONALLY_STABLE"
# 0/5 sign changes in LOCO. Magnitude range: 0.74% to 1.68%.
# Narrower than S41 (micro-cluster inflation removed).

TWENTY_D_OUTCOME = "PARTIAL_MATURITY"
# Oct 09-16 signals: ~mature Nov 10-14; fwd_return_20d still NULL
# Oct 21-28 signals: not mature until Nov-Dec
# Research authorization needed to compute from daily_prices

RANKING = "RANKING_CONDITIONAL"
# Maintained from S40/S41. No upgrade (insufficient power).
# No downgrade (direction consistently positive).
# S40 SIGNIFICANT_POSITIVE formally retracted.

REGRESSION = "REGRESSION_PASS"
# 2335 tests passed (+62 from S42), 1 skipped.
# Ruff: clean on all 5 new S42 modules.

ACTIVATION = "ACTIVATION_BLOCKED"
# Unchanged. 3 guardrail failures, insufficient cluster count.
# No production modifications in this session.
```

---

## Deliverable Summary

| Part | Deliverable | Status |
|---|---|---|
| A | Baseline audit (trading calendar, signal classification) | DONE (via Bash in prior session) |
| B | TradingCalendarIntegrityAuditor + report | DONE |
| C | ObservationUnitAuditor (5 fill-date clusters) | DONE |
| D | BenchmarkIntegrityAuditor (6 corrections) | DONE |
| E | CorrectedFiveDayComparison (all 3 INCONCLUSIVE) | DONE |
| F | Statistical inference narrative | DONE (doc) |
| G | Performance attribution repair | DONE (doc) |
| H | Robustness re-evaluation (LOCO, DIRECTIONALLY_STABLE) | DONE (doc) |
| I | Statistical guardrails (10 guardrails, CONDITIONAL) | DONE |
| J | 20D readiness update | DONE (doc) |
| K | 62 tests (TC/UA/BI/C5/GR/VD) | DONE (2335 total) |
| L | 10 documents | DONE |
| M | 20 Q&A and final verdicts | DONE (this doc) |

---

## Safety Constraint Compliance

- Cron: 未修改 ✓ (hash 3acaf480cb5dcdd44f40dd9d464955a1 unchanged)
- Stage B: 未安裝 ✓
- BTM / FDA / TCC: 未修改 ✓
- Production Neon: Read-only ✓
- Production SQLite (data/platform.db): Read-only ✓
- ForwardSignals: 未寫入 ✓
- Backfill: 未執行 ✓
- Decision Center: 未修改 ✓
- MODEL_VERSION v8.0: 未修改 ✓
- foe_v1: 未修改 ✓
- Hybrid P1–P4: 未修改 ✓
- V3 Frozen Parameters (be43e8ca): 未修改 ✓
- ACTUAL / PAPER / V3: 未啟用 ✓
