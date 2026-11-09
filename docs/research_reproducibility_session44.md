# Research Reproducibility Manifest — Session 44

**Date:** 2026-11-09  
**Session:** S44  
**Module:** `src/research/reproducibility_manifest_s44.py`  
**Status:** DETERMINISTIC_WITH_CAVEATS

---

## Purpose

Records the deterministic fingerprint of all inputs needed to reproduce a research run. Any change in input data or strategy parameters will change the fingerprint, surfacing unintended mutations.

---

## Frozen Anchors

| Field | Value |
|---|---|
| `parameter_hash` | `be43e8ca977d9fdd` |
| `forward_signals_count` | 2605 |
| `comparison_contract_version` | v1.0-s44 |
| `fees_pct` | 0.00585 |
| `statistical_method` | cluster_level_one_sample_t_test |

---

## Dataset Fingerprint

Computed as `SHA256(json.dumps(db_meta, sort_keys=True))[:16]` where `db_meta` contains:
- `forward_signals_total`
- `v8_buy_signals`
- `daily_prices_max`
- `strict_fill_dates`

The fingerprint is deterministic and stable across runs given the same DB state.

---

## Caveats (DETERMINISTIC_WITH_CAVEATS)

1. **scipy minor version** — t-test CI values may differ by <0.0001 pp across scipy versions
2. **ORDER BY required** — `GROUP BY trade_date` without `ORDER BY` could produce different ordering on some DB engines; enforced with explicit `ORDER BY trade_date`

Neither caveat affects the statistical verdict (SIGNIFICANCE_INCONCLUSIVE is robust to <0.5 pp CI variation).

---

## How to Reproduce

```python
import sqlite3
from research.reproducibility_manifest_s44 import build_reproducibility_manifest

conn = sqlite3.connect("data/platform.db")
manifest = build_reproducibility_manifest(conn)
print(manifest.dataset_fingerprint)   # 16-char hex
print(manifest.parameter_hash)        # be43e8ca977d9fdd
```

Expected fingerprint: `2c8b2475c8fdc457`

---

## Cluster-Level Aggregation Requirement

All comparisons MUST use cluster-level means (not signal-level). `cluster_level_aggregation = True` is enforced in the manifest. Using raw signal returns would inflate N and produce misleadingly tight CIs.
