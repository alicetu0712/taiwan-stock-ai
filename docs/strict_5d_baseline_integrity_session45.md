# Strict 5D Baseline Integrity — Session 45

**Date:** 2026-11-09  
**Session:** S45  
**Module:** `src/research/incomplete_cluster_auditor_s45.py`

---

## Purpose

Verify that the Session 44 canonical 5D baseline remains intact and reproducible in S45. Establish the Before / After comparison framework for future recovery events.

---

## Before (S44 Canonical)

| Field | Value |
|---|---|
| Version ID | S44-canonical |
| Strict Fill Clusters | 3 (Oct 13, Oct 14, Oct 16) |
| Strict Signals | 128 (46 + 27 + 55) |
| Cluster Deltas vs A_direct | [+1.20%, +2.76%, −1.52%] |
| Grand Mean vs A_direct | **+0.81 pp** |
| 95% CI | [−1.4, +3.0] pp |
| Statistical Verdict | **SIGNIFICANCE_INCONCLUSIVE** |
| Dataset Fingerprint | `2c8b2475c8fdc457` |
| Comparison Contract | v1.0-s44 |

---

## After S45 (No New Strict Clusters)

| Field | Value |
|---|---|
| Version ID | S45-after-recovery |
| Strict Fill Clusters | 3 (unchanged) |
| Grand Mean vs A_direct | +0.81 pp (unchanged) |
| Statistical Verdict | SIGNIFICANCE_INCONCLUSIVE (unchanged) |
| Dataset Fingerprint | `2c8b2475c8fdc457` (unchanged) |
| New Strict Clusters Added | **0** |
| Baseline Integrity Verdict | **BASELINE_REPRODUCED** |

---

## Why Baseline Is Unchanged

Both incomplete clusters (Oct 22, Oct 28) remain at 3/5 and 2/5 exit days respectively. Neither qualifies for the strict pool until 5 real TDs are available. Pipeline max = 2026-11-05 → no new strict clusters possible today.

---

## Future Baseline Versioning Rules

When a new strict cluster is added:

1. **Create new version** — do NOT overwrite S44-canonical or S45-after-recovery.
2. **Record** the new fill date, signal date, cluster delta vs A/B/C, and updated grand mean.
3. **Recompute CI** using all strict cluster deltas (cluster-level t-test).
4. **Document** the evidence provenance (GENUINE_PROSPECTIVE required).
5. **Recheck guardrails** G03 (still FAIL until ≥10 clusters) and G04 (always FAIL for daily fills).

### Version naming convention

```
S{session}-{n_strict}clusters-v{increment}
```

Example: `S46-4clusters-v1` (if Oct 22 fill recovers in S46)

---

## Statistical Constraints

| Sample | Should NOT be treated as |
|---|---|
| 3 clusters | 3 independent observations for strong inference |
| 5 clusters (after recovery) | 5 independent observations |
| 128 signals | 128 independent stock returns |
| 274 signals (5 clusters) | 274 independent returns |

**All inference must use cluster-level means, not signal-level counts.** G04 (overlapping windows) further undermines the independence assumption — this cannot be engineered away for daily signals with 5D holding periods.

---

## Regression Tolerance

S45 recomputed delta = +0.81 pp = within ±0.5 pp of S44 reference. **REGRESSION CHECK PASS.**
