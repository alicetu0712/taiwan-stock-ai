# Baseline Fingerprint Reconciliation — Session 54

**Verdict**: BASELINE_UNRESOLVED

## Fingerprint History

| Fingerprint | Sessions | Source Module | Reproducible |
|-------------|----------|---------------|--------------|
| `2c8b2475c8fdc457` | S44–S47 | `reproducibility_manifest_s44.py` (documented) | **No** |
| `09c04e8c4059d87e` | S47–S54 | `canonical_5d_baseline_s44.py` | **Yes** |

## Three-module Serialization Analysis

Three research modules compute SHA256[:16] fingerprints with **different JSON key names**:

| Module | JSON Keys | Current FP |
|--------|-----------|------------|
| `reproducibility_manifest_s44.py` | `{total, v8_buy, dp_max, strict_fds}` | `f48aa7f3ea673d7c` |
| `canonical_5d_baseline_s44.py` | `{forward_signals_total, v8_buy_signals, daily_prices_max, strict_fill_dates}` | `09c04e8c4059d87e` |
| `incomplete_cluster_auditor_s45.py` | `{forward_signals_total, v8_buy, daily_prices_max, strict_fill_dates}` | `91f522535a372e75` |

**Root cause**: `json.dumps(sort_keys=True)` serializes key names, so `{"total": 2605, ...}` and `{"forward_signals_total": 2605, ...}` produce different digests even with identical values.

## Brute-force Search (S54)

Attempted to reproduce `2c8b2475c8fdc457` from:
- 3 payload structures × 15+ dp_max values × v8_buy range 200–280 × 6 strict_fd subsets
- **Result**: NOT reproducible from any known combination

## Difference Classification

| Cause | Present |
|-------|---------|
| HASH_FORMAT_DIFFERENCE | No — all use SHA256[:16] |
| SERIALIZATION_DIFFERENCE | **Yes** — JSON key names differ across 3 modules |
| INPUT_DATA_DIFFERENCE | No — metrics are identical |
| METHODOLOGY_DIFFERENCE | No — same algorithm |
| UNEXPLAINED_DIFFERENCE | **Yes** — `2c8b2475c8fdc457` source is unresolvable |

## Baseline Metrics (Frozen — IDENTICAL across all sessions)

```
n_strict_clusters: 3
strict_fill_dates: [2026-10-13, 2026-10-14, 2026-10-16]
grand_mean_delta:  +0.81pp (Oct13: +1.20pp, Oct14: +2.76pp, Oct16: −1.52pp)
CI:                [−1.4pp, +3.0pp]
statistical_verdict: SIGNIFICANCE_INCONCLUSIVE
current_fingerprint: 09c04e8c4059d87e
```

## Conclusion

Cannot use BASELINE_IDENTICAL_VERIFIED without traceable source for `2c8b2475c8fdc457`.
Current canonical fingerprint `09c04e8c4059d87e` from `canonical_5d_baseline_s44.py` is confirmed reproducible.
Verdict: **BASELINE_UNRESOLVED** (fingerprint unresolvable; metrics identical).
