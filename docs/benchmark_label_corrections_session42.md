# Benchmark & Alpha Label Corrections — Session 42

**Date:** 2026-11-09
**Session:** 42
**Corrections:** 6 (5 from S41, 1 new from S42)

---

## 1. Correction Ledger

| ID | Metric | S40 Label (Wrong) | S40 Value | Correct Label | Correct Value | Impact |
|---|---|---|---|---|---|---|
| CR-B01 | AVOID_CHASING alpha | "vs A_direct" | +3.87% | "vs 0050 benchmark" | +6.38% (vs A_direct) | Understated by 2.51ppt |
| CR-B02 | DIRECT_ENTRY alpha | "vs A_direct" | +2.86% | "vs 0050 benchmark" | -0.56% (vs A_direct) | **Sign flipped: negative** |
| CR-B03 | NO_ENTRY alpha | "vs A_direct" | +4.30% | "vs 0050 benchmark" | +0.67% (vs A_direct) | Overstated by 3.63ppt |
| CR-B04 | 0050 avg return | Oct 12-28 avg | -4.65% | Oct 09-16 (actual engine dates) | -2.16% | Benchmark appeared 2.49ppt worse |
| CR-B05 | Signal date range | "Oct 12-28, 7 dates" | (EligibleWindowDiscovery) | "Oct 09-16, 7 signal dates" | V3ComparisonEngine actual | Source of CR-B04 error |
| CR-B06 | Cluster definition | "7 signal-date clusters" | S41 method | "5 fill-date clusters" | S42 corrected | Grand mean: +6.49% → +1.21% |

---

## 2. Root Cause Analysis

**CR-B01/02/03 (Alpha Labels):** The `avoid_chasing_analysis.py` subgroup calculation computed "D_v3 mean - 0050 mean" but labeled the result as "vs A_direct paired." This was fixed in S41 by adding both metrics separately. The sign flip in DIRECT_ENTRY (-0.56%) is the most consequential finding.

**CR-B04/05 (Benchmark Dates):** S40 documentation described EligibleWindowDiscovery output dates (Oct 12-28), but V3ComparisonEngine used different dates (Oct 09-16). The 0050 benchmark was computed for the documented dates, not the actual engine dates. The corrected benchmark is **-2.16%** (not -4.65%).

**CR-B06 (Clustering):** S41 used signal-date clusters (7), which treated Oct 09/10/11 non-trading signals as independent. S42 uses fill-date clusters (5), merging them into one Oct 12 cluster. This cuts the grand mean by 5.28ppt.

---

## 3. Corrected Key Metrics

| Metric | S40 (Wrong) | S41 (Partial Fix) | S42 (Fully Corrected) |
|---|---|---|---|
| D_v3 grand mean vs A_direct | +3.66% (signal-level) | +6.49% (7 signal-date clusters) | **+1.21% (5 fill-date clusters)** |
| D_v3 grand mean vs B_v1v2 | +2.99% | — | **+0.32%** |
| D_v3 grand mean vs C_hybrid | +3.68% | — | **+1.19%** |
| 0050 benchmark avg | -4.65% | -2.16% (corrected) | -2.16% |
| DIRECT_ENTRY alpha vs A_direct | +2.86% | -0.56% (corrected) | -0.56% |

---

## 4. Verdict

```
BENCHMARK_CORRECTED
All 6 corrections documented in CorrectionEntry records
Most critical: CR-B02 (DIRECT_ENTRY alpha sign flip) and CR-B06 (clustering correction)
Benchmark integrity: PASS as of S42 (all metrics carry correct labels)
```
