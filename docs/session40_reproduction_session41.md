# Session 40 Reproduction Report — Session 41

**Date:** 2026-11-09
**Session:** 41
**Status:** ALL_REPRODUCED (10/10 metrics)

---

## Reproduction Summary

All 10 numerical metrics from Session 40 were reproduced within tolerance (|diff| ≤ 0.0001):

| Metric | Expected (S40) | Actual (S41) | Status |
|---|---|---|---|
| A_direct mean net | -3.1959% | -3.1959% | REPRODUCED |
| B_v1v2 mean net | -2.4770% | -2.4770% | REPRODUCED |
| C_hybrid mean net | -3.1866% | -3.1866% | REPRODUCED |
| D_v3 mean net | -1.8632% | -1.8632% | REPRODUCED |
| D_v3 fill rate | 68.61% | 68.61% | REPRODUCED |
| D_v3 vs A_direct delta | +3.6565% | +3.6565% | REPRODUCED |
| D_v3 vs B_v1v2 delta | +2.9862% | +2.9862% | REPRODUCED |
| D_v3 vs C_hybrid delta | +3.6833% | +3.6833% | REPRODUCED |
| D_v3 vs A_direct CI lower | +2.6136% | +2.6136% | REPRODUCED |
| D_v3 vs A_direct CI upper | +4.8344% | +4.8344% | REPRODUCED |

---

## Documentation Discrepancy (S40 Error)

**S40 docs claimed:** Signal dates 2026-10-12 to 2026-10-28 (7 dates)

**Actual V3ComparisonEngine used:** 2026-10-09, 10-10, 10-11, 10-12, 10-13, 10-14, 10-16

Signal count verification:
- 2026-10-09: n=99 → fill Oct 12
- 2026-10-10: n=4 → fill Oct 13 (or Oct 12?)
- 2026-10-11: n=4 → fill Oct 12?
- 2026-10-12: n=46
- 2026-10-13: n=27
- 2026-10-14: n=55
- 2026-10-16: n=39
- **Total: 274** ✓ (matches n_5d_eligible=274)

The EligibleWindowDiscovery module in S40 assessed dates starting from Oct 12, while V3ComparisonEngine counted all forward signals with ≥5D post-price-bars available.

**Consequence:** 0050 benchmark returns claimed in S40 doc (-6.09% to -10.58% per date) were INCORRECT. Actual per-date 0050 returns for Oct 09-16 are -1.60%, -2.09%, +0.53%, -2.71%, -3.81%, -3.31%, -2.14%. The S40 claim of "avg -4.65%" was not verified against actual engine output.

---

## Key Numbers Confirmed

- **V3ComparisonEngine parameter hash:** `1feb7a6b294a063d` (unchanged)
- **D_v3 fill rate:** 68.61% (188/274 signals filled)
- **7 trading dates** used: all within Oct 09-16 window
- **run_at timestamp:** consistent with previous execution

---

## Implications for Cluster Analysis

Having confirmed the signal composition (274 = 7 dates × various n), the cluster-corrected analysis in PART C uses the correct date groupings. The 274 paired signals are NOT independent — there are only 7 independent trading dates.

---

## Safety Compliance

No production data was modified. All reads were from `data/platform.db` (Read-only). `forward_signals.fwd_return_20d` remains NULL.
