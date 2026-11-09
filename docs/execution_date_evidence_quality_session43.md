# Execution-Date Evidence Quality Report — Session 43

## 1. Overview

Session 43 rates the overall quality of the V3 comparison evidence across 10 dimensions. Each dimension is scored 0-10.

| Score Range | Grade | Meaning |
|-------------|-------|---------|
| 8.5-10 | STRONG | Adequate for strong claims |
| 6.5-8.4 | ADEQUATE | Acceptable for conditional claims |
| 4.0-6.4 | CONDITIONAL | Use with caveats; flag in reports |
| 2.0-3.9 | WEAK | Insufficient for meaningful claims |
| 0-1.9 | CRITICAL | Do not use for any claim |

## 2. Dimension Scores

| Dimension | S42 Score | S43 Score | Δ | Grade | Key Limiting Factor |
|-----------|-----------|-----------|---|-------|---------------------|
| EXECUTION_INTEGRITY | 5.0 | 7.5 | +2.5 | ADEQUATE | 107 v6.0 signals have NULL exec |
| SIGNAL_PROVENANCE | 4.0 | 7.0 | +3.0 | ADEQUATE | trade_date unreliable without calendar |
| CALENDAR_ACCURACY | 3.0 | 6.0 | +3.0 | CONDITIONAL | DISTINCT date includes thin days |
| SAMPLE_COMPLETENESS | 4.0 | 4.5 | +0.5 | CONDITIONAL | Only 3 complete clusters |
| STATISTICAL_POWER | 2.0 | 2.5 | +0.5 | WEAK | N=3; independence violated |
| WINDOW_INDEPENDENCE | 2.0 | 2.0 | 0.0 | WEAK | 80% overlap between adjacent clusters |
| BENCHMARK_ALIGNMENT | 4.5 | 7.5 | +3.0 | ADEQUATE | 0050 dates corrected in S42 |
| MODEL_VERSION_PURITY | 5.0 | 8.0 | +3.0 | STRONG | v6.0 exclusion complete |
| OUTCOME_MATURITY | 3.0 | 3.5 | +0.5 | WEAK | 0 of 4 clusters have 20D exits |
| EVIDENCE_EXPANDABILITY | 3.0 | 3.0 | 0.0 | WEAK | NO_NEW_ELIGIBLE_WINDOW |

**S42 mean**: 3.55 / 10  
**S43 mean**: 5.15 / 10 (+1.60 improvement)

## 3. Strongest and Weakest Dimensions

**Strongest**: MODEL_VERSION_PURITY (8.0/10)
- S43 strict filter fully eliminates v6.0 contamination
- 100% of non-TD signals confirmed as v6.0 by NonTradingDayAuditor
- Only residual issue: ETF contamination ~0.7% (minor)

**Weakest**: WINDOW_INDEPENDENCE (2.0/10)
- Adjacent 5D windows share 80% of trading days
- Statistical t-test assumes independence; this assumption is materially violated
- No structural fix available without changing signal cadence

## 4. Activation Blockers

The following dimensions prevent V3 activation based on evidence quality:

1. **STATISTICAL_POWER** (2.5/10): Only 3 independent clusters; N < 5 minimum for t-inference
2. **WINDOW_INDEPENDENCE** (2.0/10): 80% overlap violates independence
3. **OUTCOME_MATURITY** (3.5/10): 0 complete 20D windows; 5D windows alone insufficient
4. **EVIDENCE_EXPANDABILITY** (3.0/10): No historical archives; no near-term expansion possible

**Verdict: ACTIVATION_BLOCKED_INSUFFICIENT**

## 5. Improvement Since S41

| Session | Mean Score | Key Improvement |
|---------|-----------|-----------------|
| S41 | ~2.5 | Baseline (pre-correction) |
| S42 | 3.55 | Calendar + benchmark correction |
| S43 | 5.15 | v6.0 exclusion + execution semantics |

The consistent upward trend reflects genuine methodological improvements, not data selection. Each session corrects a specific error; the improvements are real.

## 6. What Would Make This Evidence Adequate?

Minimum requirements for a CONDITIONAL activation recommendation:

| Requirement | Current | Needed | ETA |
|-------------|---------|--------|-----|
| Strict fill clusters | 3 | 7+ | Jan 2027 |
| Window overlap | 80% | <50% | Structural change |
| 20D complete windows | 0 | 3+ | Dec 2026 |
| New eligible windows | 0 | 1+ | Nov 2026 |

Even meeting these requirements would yield only CONDITIONAL evidence. STRONG evidence would require multiple calendar-year OOS validation periods.

## 7. Summary Verdict

The evidence base for V3 performance claims has improved substantially in S42-S43 through methodological corrections. However, the residual evidence quality (mean 5.15/10) remains insufficient for any activation decision. The principal blockers are **data scarcity** (inherent to Oct 2026 cron launch) and **structural overlap** (inherent to daily signal + 5D window design). These cannot be resolved by further analysis — only by time (data accumulation) or design changes.
