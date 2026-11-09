# Canonical Research Data Contract — Session 44

**Date:** 2026-11-09  
**Session:** S44  
**Module:** `src/research/canonical_data_contract_s44.py`  
**Version:** v1.0-s44

---

## Purpose

Defines the 20 canonical fields and their semantics for all V3 vs A/B/C comparison research. Prevents mixing incompatible fields (e.g., signal_date with execution_date, gross with net return).

---

## Field Categories

### Date Fields (5)

| Field | Definition |
|---|---|
| `signal_date` | Date the strategy engine generated the signal (trade_date in forward_signals) |
| `execution_date` | Date the simulated fill was computed by NEXT_OPEN (always a real trading day) |
| `fill_date` | Alias for execution_date in cluster context |
| `outcome_end_date` | Date 5 (or 20) stock-specific trading days after fill_date |
| `analysis_date` | Date this research computation was run |

### Version Fields (4)

| Field | Definition |
|---|---|
| `model_version` | Version of the scoring model (v6.0 excluded from v8.0 comparisons) |
| `parameter_hash` | Frozen hash of V3 strategy parameters: `be43e8ca977d9fdd` |
| `comparison_contract_version` | Version of this contract used for the comparison (v1.0-s44) |
| `research_session` | Session number (S44) |

### Sample Fields (2)

| Field | Definition |
|---|---|
| `cluster_count` | Number of fill-date clusters in the strict pool (not raw signal count) |
| `raw_n` | Total signal count in the strict pool |

### Performance Fields (5)

| Field | Definition |
|---|---|
| `gross_return` | (exit_price - fill_price) / fill_price (before fees) |
| `net_return` | gross_return - FEES_PCT (FEES_PCT=0.00585 research assumption) |
| `paired_delta_vs_baseline` | V3 cluster mean − comparator cluster mean (per fill-date cluster) |
| `alpha_vs_0050` | V3 cluster mean − 0050 return for same period |
| `cluster_mean_return` | Mean net_return across all signals in a fill-date cluster |

### Statistical Fields (4)

| Field | Definition |
|---|---|
| `ci_lower` | 95% CI lower bound (cluster-level t-test) |
| `ci_upper` | 95% CI upper bound |
| `p_value` | Two-tailed p-value from cluster-level one-sample t-test |
| `statistical_verdict` | SIGNIFICANT_POSITIVE / SIGNIFICANCE_INCONCLUSIVE / SIGNIFICANT_NEGATIVE |

---

## Forbidden Mixings

| Field A | Field B | Reason |
|---|---|---|
| `signal_date` | `execution_date` | They refer to different events (day before execution) |
| `alpha_vs_0050` | `paired_delta_vs_baseline` | Alpha = raw vs benchmark; Delta = paired vs strategy |
| `gross_return` | `net_return` | Fee treatment must be consistent in a single comparison |
| `cluster_count` | `raw_n` | Statistical inference uses cluster means, not signal counts |
| `RETROSPECTIVE` | `PROSPECTIVE` | Retrospective signals NOT valid for unbiased comparison |
| `dataset_namespace` | `strategy_namespace` | Different scoping namespaces; must not be conflated |

---

## Key Invariants

- All comparisons use cluster-level aggregation (not signal-level)
- v6.0 signals are always excluded from v8.0 comparisons
- FEES_PCT=0.00585 is a research assumption (not verified against live broker data)
- parameter_hash `be43e8ca977d9fdd` is frozen; comparisons are invalid if hash changes
