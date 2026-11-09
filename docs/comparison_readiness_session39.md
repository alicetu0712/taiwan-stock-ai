# V1/V2/V3 Comparison Readiness Report — Session 39

**Date:** 2026-11-08  
**Session:** 39  
**Overall Verdict:** `RANKING_NOT_SUPPORTED`

---

## 1. Readiness Dimensions (10)

| # | Dimension | Status | Key Finding |
|---|---|---|---|
| 1 | Version Definition | CONDITIONAL | Hybrid V1 + V3 VERIFIED; V1/V2 PARTIAL (no parameter hash) |
| 2 | Clean Universe | CONDITIONAL | Dataset B established (2023 TWSE signals); TPEx absent; 35% market coverage |
| 3 | Historical Coverage | CONDITIONAL | v8.0 dates valid; market coverage 48% forward / 87% backtest |
| 4 | Outcome Availability | **BLOCKED** | 0/2236 fwd_return_20d; none before 2026-12-02 |
| 5 | Matched Samples | **BLOCKED** | Cannot match without outcomes; different signal subsets per version |
| 6 | Risk Assumptions | CONDITIONAL | FEES_PCT=0.585% documented; exit rule not version-specific |
| 7 | Transaction Costs | READY | FEES_PCT=0.585% from execution_simulator.py; computable from signal counts |
| 8 | Statistical Power | **BLOCKED** | 0 outcomes; dedup ~290–360 estimate; MDD unknown |
| 9 | Out-of-Sample Evidence | **BLOCKED** | Walk-forward: 1 window, MARKET_AVOIDANCE_DRIVEN, INSUFFICIENT_EVIDENCE |
| 10 | Prospective Evidence | **BLOCKED** | Cron frozen; Stage B not authorized; NO_PROSPECTIVE_EVIDENCE |

**BLOCKED: 5 / 10 dimensions**  
**CONDITIONAL: 4 / 10 dimensions**  
**READY: 1 / 10 dimensions**

---

## 2. Blocking Analysis

### BLOCKED-04: Outcome Availability

- fwd_return_20d = NULL for all 2236 v8.0 valid signals
- Earliest signal date: 2026-10-12 → earliest outcome date: 2026-12-02 (20 trading days)
- Until this date, **no return-based comparison can be computed**
- Affects: ALL versions (V1, V2, Hybrid V1, V3)

### BLOCKED-05: Matched Samples

- For a paired comparison (same stock, same date), all versions must have an outcome
- V2/Hybrid/V3 each apply additional filters → their signal subsets may differ
- Currently: 0 outcomes → 0 matched pairs → 0 pair-wise alpha estimates
- Even after Dec 2026: requires careful dedup by 20D overlapping windows

### BLOCKED-08: Statistical Power

- Expected post-Dec dedup N: ~290–360 (7 dates, estimated ~50 unique stocks/date)
- For 80% power to detect 1% effect at p<0.05: N ≥ ~100 non-overlapping observations
- 7 trading dates = max 7 independent clusters → severely underpowered for inference
- Requires months of additional forward-collection before power thresholds are met

### BLOCKED-09: Out-of-Sample Evidence

- Session 28 walk-forward: 1 feasible window, net_return +1.33%, verdict MARKET_AVOIDANCE_DRIVEN
- Walk-forward conclusion: INSUFFICIENT_EVIDENCE (single window, possible survivorship)
- Requires minimum 10 windows for SUFFICIENT_EVIDENCE

### BLOCKED-10: Prospective Evidence

- Cron status: FROZEN (hash 3acaf480cb5dcdd44f40dd9d464955a1, unchanged)
- Stage B probe: NOT authorized (explicitly blocked in S36)
- Real-time signal comparison: IMPOSSIBLE without live execution
- Prospective V3 shadow: FRAMEWORK_READY but CRON_ACCEPTANCE_PENDING (Session 29)

---

## 3. Conditional Dimension Details

### CONDITIONAL-01: Version Definition

| Version | Status | Blocker |
|---|---|---|
| V1 (v1_signal_only) | PARTIAL | No parameter hash for BUY/STRONG_BUY thresholds |
| V2 (v2_entry_timing) | PARTIAL | EntryTimingAnalyzer MA20 thresholds unversioned |
| Hybrid V1 (hybrid_v1) | VERIFIED | Frozen commit 6602c3b, hash documented |
| V3 (v3_entry_timing) | VERIFIED | Parameter hash be43e8ca977d9fdd, frozen |

Upgrade path: document V1/V2 thresholds and assign hashes.

### CONDITIONAL-02: Clean Universe

- Dataset B = 2023 signals (368 TWSE stocks) — defined and reproducible
- TPEx entirely absent (0/897 official TPEx stocks)
- 35% of TWSE market covered (368/1099)
- `CLEAN_UNIVERSE_PARTIAL` — usable but not representative of full Taiwan market

### CONDITIONAL-03: Historical Coverage

- v8.0 trading dates valid (Oct 12–28, 2026) — 7 dates confirmed
- market data coverage: 48% forward (below 80% threshold) / 87% backtest era
- Some stocks missing ohlc data for some dates — will cause missed fill prices in comparison

### CONDITIONAL-06: Risk Assumptions

- FEES_PCT=0.585% documented
- Exit rule: 20D horizon used consistently, but actual stop_price / target1 handling not verified per-version
- Capital assumption: 1 unit equal weight — no leverage — documented

---

## 4. The One Comparable Pair

**Only Hybrid V1 ↔ V3 is eligible for future comparison.**

| Pair | Comparable? | Reason |
|---|---|---|
| V1 ↔ V2 | NOT_COMPARABLE | Both PARTIAL |
| V1 ↔ Hybrid V1 | NOT_COMPARABLE | V1 PARTIAL |
| V1 ↔ V3 | NOT_COMPARABLE | V1 PARTIAL |
| V2 ↔ Hybrid V1 | NOT_COMPARABLE | V2 PARTIAL |
| V2 ↔ V3 | NOT_COMPARABLE | V2 PARTIAL |
| **Hybrid V1 ↔ V3** | **CONDITIONAL** | Both VERIFIED; blocked by outcomes only |

The Hybrid V1 ↔ V3 comparison becomes unblocked when:
1. fwd_return_20d populated (after 2026-12-02)
2. At minimum 2–3 months of additional forward signals collected

---

## 5. Minimum Path to Comparison

| Step | Required | Unlocks |
|---|---|---|
| 1 | Wait for 2026-12-02 (first outcomes) | BLOCKED-04 |
| 2 | Compute fwd_return_20d for all v8.0 signals | BLOCKED-04, BLOCKED-05 |
| 3 | Build matched pairs (Hybrid V1, V3) for identical (stock, date) | BLOCKED-05 |
| 4 | Run cluster-adjusted analysis (7-date clusters) | Partial BLOCKED-08 |
| 5 | Collect 2–3 more months of forward signals (target: 25+ dates) | BLOCKED-08 fully |
| 6 | Authorize prospective V3 shadow + cron re-enable | BLOCKED-10 |

**Earliest viable comparison: 2026-12-15 (Hybrid V1 ↔ V3 only, underpowered)**  
**Statistically adequate comparison: 2027-Q1 at earliest**

---

## 6. What Session 39 Established

1. **CleanResearchUniverseBuilder** — Dataset A/B/C defined, reproducible, fingerprinted
2. **StrategyVersionRegistry** — 4 versions formally documented with comparability table
3. **HistoricalResearchEligibilityGate** — 12 checks run, INELIGIBLE overall
4. **StrategyComparisonFramework** — shared contract defined (fees, benchmark, calendar, dedup policy)
5. **V1V2V3ComparisonReadinessReport** — 10 dimensions, 5 BLOCKED, RANKING_NOT_SUPPORTED
6. **51 tests** (CU/VR/EG/CF/RR prefix groups), all passing

---

## 7. Final Verdict

**`RANKING_NOT_SUPPORTED`**

The framework is designed, the datasets are defined, and the contracts are documented. The comparison cannot be executed today because outcome data does not yet exist (BLOCKED-04). When outcomes arrive, only Hybrid V1 vs V3 is structurally eligible for comparison. V1 and V2 require parameter documentation before they can participate.
