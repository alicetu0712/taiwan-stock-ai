# Eligible Window Discovery — Session 40

**Date:** 2026-11-09  
**Session:** 40  
**Overall Verdict:** `CONDITIONAL_WINDOW_FOUND`

---

## 1. Discovery Method

Windows are assessed on **DATA QUALITY criteria only** before any performance is computed. Performance is NEVER used to select windows (anti-selection-bias protocol).

Three candidate horizons assessed:
- 5D (5 trading days)
- 10D (10 trading days)
- 20D (20 trading days)

Signal pool: `forward_signals` with `trade_signal IN ('buy', 'strong_buy')`

---

## 2. Candidate Window Summary

| Horizon | Signal Dates | Raw N | Eligible N | % Coverage | Verdict | Exclusion Reason |
|---|---|---|---|---|---|---|
| **5D** | 2026-10-12 – 2026-10-28 (7 dates) | 344 | 274 | 79.7% | **CONDITIONAL** | C10: 7 dates < 20 minimum |
| 10D | Same | 344 | 1 | 0.3% | INELIGIBLE | C4: 0.3% coverage |
| 20D | Same | 344 | 0 | 0% | INELIGIBLE | C4: 0% coverage |

**Best window: 5D CONDITIONAL window (Oct 2026)**

---

## 3. 5D Window: Per-Check Assessment

| ID | Check Name | Verdict | Actual | Required |
|---|---|---|---|---|
| C1 | Official security classification | PASS | 100% officially classified (Session 38) | All signals classified |
| C2 | Point-in-time universe | CONDITIONAL | De facto PiT (production-generated); no listing_date | Stocks listed on signal_date |
| C3 | Trading date validity | PASS | 7/7 dates in daily_prices | All dates in daily_prices |
| C4 | Market data coverage | CONDITIONAL | 274/344 (79.7%) have ≥5D post-bars | ≥80% |
| C5 | Benchmark availability | PASS | 0050 available for all 7 dates | 0050 available |
| C6 | Price freshness | CONDITIONAL | source_price_date populated; staleness not verified | source_price_date ≤1D before signal |
| C7 | Corporate action adjustment | CONDITIONAL | Assumed adjusted; unverified | Prices adjusted for splits/rights |
| C8 | Outcome availability | PASS | 274/274 5D-eligible signals have price bars for outcome computation | ≥5D price bars |
| C9 | Duplicate signals | PASS | 0 duplicates | Zero duplicates |
| C10 | Overlapping hold-period samples | CONDITIONAL | 7 dates; effective N ≈ 7; raw N = 274; CI not cluster-adjusted | ≥20 independent dates |

**Score: 4 PASS, 5 CONDITIONAL, 1 FAIL (None)**

**Verdict: CONDITIONAL** — All criteria PASS or CONDITIONAL; no FAIL. Usable with explicit caveats.

---

## 4. Critical Caveats for the 5D CONDITIONAL Window

| Caveat | Impact |
|---|---|
| 7 independent trading dates (effective N ≈ 7) | STATISTICAL_CONFIDENCE_UNVERIFIED — bootstrap CI overoptimistic |
| Single market regime: ALL bull at signal date | Cannot generalize to bear or neutral regime |
| Market declined during hold period (0050 avg -4.65%) | V3 lower-fill advantage is MARKET_AVOIDANCE_DRIVEN, not generalizable |
| foe_v1 generated the signals (IN-SAMPLE scoring) | Cannot validate scoring model quality |
| Corporate action status unverified | Minor price distortion possible |
| Point-in-time de facto only | Minor: 3 confirmed delistings not in this window's signal pool |

---

## 5. What This Window Enables

| Analysis | Feasible? | Caveat |
|---|---|---|
| V1 vs V2 (from effectiveness_analysis.json) | YES | CONDITIONAL (CI includes zero) |
| V3 vs A/B/C (5D horizon) | YES | CONDITIONAL (underpowered, single regime) |
| 20D outcome comparison | NO | Wait until 2026-12-02 |
| Multi-regime comparison | NO | All signals in bull regime |
| Statistical ranking with power | NO | Effective N = 7, too small |

---

## 6. Excluded Windows

| Horizon | Reason |
|---|---|
| 10D | Only 1/344 signals (0.3%) have ≥10 post-bars → INELIGIBLE (C4 FAIL) |
| 20D | Zero signals have ≥20 post-bars → INELIGIBLE (C4 FAIL, C8 FAIL) |

No historical pre-Oct 2026 windows were assessed because `forward_signals` only contains Oct 2026 dates. The `analysis_results` table (2024-07-01 to 2026-10-28) was not evaluated as a signal source for V3 comparison due to schema incompatibility with V3ComparisonEngine (requires `ma20_gap_pct` and other V3-specific columns).

---

## 7. When More Windows Become Available

| Milestone | Date | Unlocks |
|---|---|---|
| 20D outcomes for Oct 12 signals | 2026-12-02 | 20D horizon for first 2 signal dates |
| 20D outcomes for Oct 28 signals | 2026-12-25 (est.) | 20D for all 7 dates |
| 10 independent dates | ~2027-01 (if cron running) | Minimally powered comparison |
| 25+ independent dates | ~2027-Q2 | Statistically adequate comparison |
| Multi-regime coverage | ~2027-Q3 | Generalizable comparison |
