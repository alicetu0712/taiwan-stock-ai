# Clean Research Universe — Session 39

**Date:** 2026-11-08  
**Session:** 39  
**Version:** session39_v1

---

## 1. Dataset Definitions Applied to v8.0 ForwardSignals

Using `CleanResearchUniverseBuilder` with official TWSE/TPEx classification from Session 38.

### Dataset A — Original

| Metric | Value |
|---|---|
| Total signals | 2,236 |
| Unique stocks | 410 |
| TWSE common signals | 2,023 |
| ETF signals | 213 (9.52%) |
| TPEx common signals | 0 |
| Unknown signals | 0 |
| Probable delisted | 0 |
| Trading dates | 7 (Oct 12–28, 2026) |
| ETF filtering | None — original state |

### Dataset B — Verified Common Stock (Recommended)

| Metric | Value |
|---|---|
| Total signals | **2,023** |
| Unique stocks | **368** |
| TWSE common signals | 2,023 (all) |
| ETF signals removed | 213 (−9.52%) |
| TPEx common signals | 0 |
| Trading dates | 7 |
| Classification method | Official TWSE/TPEx OpenAPI (Session 38) |
| **Status** | **RECOMMENDED for all future research** |

### Dataset C — Sensitivity (B = C for Session 38/39)

| Metric | Value |
|---|---|
| Total signals | **2,023** |
| Retained UNKNOWN | 0 (none in v8.0 FS) |
| ETF signals removed | 213 |
| **Note** | Identical to Dataset B — no UNKNOWN signals in v8.0 |

---

## 2. Why B = C in Session 38/39

All 42 non-common stock_ids in FS v8.0 are confirmed ETFs (0-prefix, official-verified). There are zero UNKNOWN (non-classifiable) securities in v8.0 signals. Therefore the sensitivity boundary (C = common + unknown) produces the same result as the clean set (B = common only).

---

## 3. Dataset B Properties

### Coverage

| Dimension | Value |
|---|---|
| Trading dates | Oct 12, 14, 15, 17, 21, 22, 28 (2026) |
| Stocks per date | ~45–102 (varies by date) |
| TWSE coverage | 368/715 master stocks (51.5%) |
| Full TWSE market | 368/1099 official (33.5%) |
| TPEx coverage | 0/897 (explicitly absent) |

### Decision Label Distribution (v8.0 valid, Dataset B)

The decision_label column (from foe_v1 scoring) is the same across all three datasets — filtering only affects stock_id classification, not label distribution. All 2023 B-dataset signals carry the original decision_label from foe_v1.

---

## 4. Data Fingerprints (Reproducibility)

| Dataset | Fingerprint |
|---|---|
| A_original | Computed from all 2236 (stock_id, trade_date) pairs |
| B_verified_common | Computed from 2023 TWSE-common (stock_id, trade_date) pairs |
| C_sensitivity | = B fingerprint (identical content) |

Fingerprints are SHA-256 (first 16 hex chars) of sorted (stock_id:trade_date) pairs. Recomputing from the same DB will produce the same fingerprint.

---

## 5. Limitations

| Limitation | Severity |
|---|---|
| TPEx entirely absent (0 of 897 official) | HIGH — 44.9% of common stocks excluded by design |
| 314 pre-existing TWSE stocks missing from master | HIGH — 28.6% of TWSE not in signal pool |
| fwd_return_20d = NULL for all 2236 signals | CRITICAL — no performance analysis possible yet |
| Point-in-time universe unverified | MEDIUM — listing dates not stored |
| 7 trading dates only | MEDIUM — small prospective sample |

---

## 6. Verdict

**`CLEAN_UNIVERSE_PARTIAL`** — Dataset B established (2023 signals, 368 TWSE stocks), but significant structural gaps remain (TPEx absent, 35% market coverage, 0 outcomes).
