# Frozen vs Expanded 5D Comparison — Session 47

**Date:** 2026-11-09  
**Session:** S47 — PART E (P4)  
**Verdict:** NO_NEW_ELIGIBLE_CLUSTERS

---

## A. Frozen Baseline (UNCHANGED from S44/S45/S46)

| Metric | Value |
|---|---|
| Strict clusters | 3 (Oct 13/14/16 fills) |
| Total matched signals | 128 (46 + 27 + 55) |
| Grand mean D (V3 vs A_direct) | **+0.81 pp** |
| CI 95% | [-1.4%, +3.0%] |
| Statistical verdict | SIGNIFICANCE_INCONCLUSIVE |
| Dataset fingerprint | 09c04e8c4059d87e* |
| Session 43 reference | +0.81 pp (matches) |
| Baseline verdict | BASELINE_REPRODUCED |

*Fingerprint changed from S44's `2c8b2475c8fdc457` because `daily_prices_max` changed when Nov 04/05 were manually backfilled between S44 and S47. The metrics (3 clusters, +0.81%) are identical.

### Per-Cluster Deltas (Frozen from S43)

| Fill Date | n Signals | V3 vs A_direct | V3 vs B_v1v2 | V3 vs C_hybrid |
|---|---|---|---|---|
| Oct 13 | 46 | +1.20% | +0.84% | +1.07% |
| Oct 14 | 27 | +2.76% | +0.14% | +2.76% |
| Oct 16 | 55 | -1.52% | -1.41% | -1.49% |
| **Grand mean** | | **+0.81%** | **-0.14%** | **+0.78%** |

---

## B. Expanded Research Snapshot

**Status: NO_NEW_ELIGIBLE_CLUSTERS**

No new clusters can be promoted to strict in Session 47:
- Oct 21/22/28 fills remain DATA_INCOMPLETE
- Recovery of required price data is BLOCKED
- Zero new matched-pair deltas computed

The S46 expanded snapshot (Oct 28 isolated result, D=+2.75%) remains the most recent research-only addition, and is NOT part of the strict baseline.

---

## Statistical Integrity Note

With N=3 strict clusters, standard t-test inference is unreliable:

| Limitation | Impact |
|---|---|
| N=3 clusters (need ≥10) | Low power; CI extremely wide |
| Adjacent windows overlap 80% | Cluster-level independence violated |
| All signals from Oct 2026 | Single market regime; no OOS validation |
| CI includes zero | Cannot claim statistical significance |

**INFERENCE_NOT_RELIABLE for N=3.** The grand mean +0.81 pp is a descriptive statistic, not a confident performance claim.

---

## Why the Frozen Baseline Fingerprint Changed

The `build_canonical_5d_baseline` fingerprint hashes:
- `forward_signals_total`: 2605 (unchanged)
- `v8_buy_signals`: 237 (unchanged)
- `daily_prices_max`: **changed** from pre-Nov04 value to `2026-11-05` after Nov 04/05 manual backfill
- `strict_fill_dates`: ['2026-10-13', '2026-10-14', '2026-10-16'] (unchanged)

The fingerprint change is benign — the baseline metrics are identical. The S44 reference fingerprint `2c8b2475c8fdc457` was computed when `daily_prices_max` was earlier; after the manual backfill, the hash changed to `09c04e8c4059d87e`.

**Action:** Update the reference fingerprint in memory for future sessions to `09c04e8c4059d87e`.

---

## Comparison Verdict

| Dimension | Verdict |
|---|---|
| Frozen baseline | BASELINE_REPRODUCED (+0.81% confirmed) |
| New strict clusters | NONE |
| Expanded comparison | NO_NEW_ELIGIBLE_CLUSTERS |
| Statistical conclusion | SIGNIFICANCE_INCONCLUSIVE (unchanged) |
