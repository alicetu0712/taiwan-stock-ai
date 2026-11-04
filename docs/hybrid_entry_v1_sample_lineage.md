# Hybrid Entry Strategy V1 — Sample Lineage Report

**Frozen at:** 2026-11-05  
**Reference commit:** 6602c3b (effectiveness analysis)  
**Rule version:** hybrid_v1

---

## 1. What Are These Signals?

All signals referenced in the Hybrid V1 research (both the 457-signal dataset
from earlier sessions and the 2,953-signal dataset from the effectiveness
analysis) are **RECONSTRUCTED RESEARCH COHORT** signals.

They are **NOT**:
- Production ForwardSignals from the live pipeline
- Frozen ForwardSignal records (which are stored in the production Neon DB)
- Actual trade entries or exits from ACTUAL/PAPER Trade Service

They **ARE**:
- Signals generated on-demand by EntryTimingAnalyzer against historical
  DailyPrice OHLC stored in local SQLite (`data/platform.db`)
- Generated at a step interval (every ~5 calendar days per stock) to cover
  the research period
- Filtered and enriched by scripts in `scripts/`

---

## 2. The Two Cohorts Explained

### Cohort A: 457 signals (earlier sessions)

| Attribute | Value |
|---|---|
| Signal period | 2026-04-01 to 2026-08-31 |
| Stock universe | 100 stocks |
| Signal step | Weekly (~5-day) |
| Dedup | 28-calendar-day window |
| Purpose | Proof-of-concept backtest (Sessions 1–2) |
| OOS status | IN-SAMPLE relative to V1 research |
| Data source | EntryTimingAnalyzer on local SQLite |

### Cohort B: 2,953 signals (effectiveness analysis — primary)

| Attribute | Value |
|---|---|
| Signal period | 2024-10-01 to 2026-09-15 |
| Stock universe | 150 stocks |
| Signal step | Weekly (~5-day) |
| Raw signals generated | ~13,023 |
| After 28-day dedup | 3,066 |
| After V1+V2 simulation and maturity filter | 2,953 |
| Purpose | V2 effectiveness analysis + Hybrid rule derivation |
| OOS status | IN-SAMPLE for Hybrid V1 (rules derived from this cohort) |
| Data source | EntryTimingAnalyzer on local SQLite |

---

## 3. Why 457 ≠ 2,953

The 457-signal dataset covered only 5 months (Apr–Aug 2026), 100 stocks.
The 2,953-signal dataset covered 23 months (Oct 2024–Sep 2026), 150 stocks.

The difference is period + universe, not a filtering bug.  Both are independent
reconstructed research cohorts serving different analytical purposes.

Cohort A was used to establish the V1/V2 baseline.  
Cohort B was used for the deeper effectiveness analysis and subgroup findings
that motivated Hybrid V1 rules.

---

## 4. Walk-forward PASS Clarification

The effectiveness analysis reports **"10/10 Walk-forward PASS"** for V2 vs V1.

### What "PASS" actually means:

| Criterion | Result |
|---|---|
| Technical execution (all 10 windows ran) | ✅ YES |
| No look-ahead bias | ✅ YES |
| Minimum sample size (n ≥ 10 per window) | ✅ YES (all windows had 236–294 signals) |
| Paired delta ≥ 0 (V2 outperformed V1) | ❌ NO — 5 of 10 windows had negative delta |
| Statistically significant (CI entirely positive) | ❌ NO — only 2/10 windows (W2, W8) |

**PASS criterion = `paired_delta ≥ −1.0pp`** — a loose technical threshold that
means "V2 did not severely underperform V1," not "V2 significantly outperformed."

### Window-by-window summary:

| Window | Period | Delta | Sign | CI entirely positive? |
|---|---|---|---|---|
| W1 | 2025-01 to 2025-02 | −0.29% | ➖ | No |
| W2 | 2025-03 to 2025-04 | +0.61% | ➕ | Yes (CI [+0.15, +1.13]) |
| W3 | 2025-05 to 2025-06 | +0.30% | ➕ | No |
| W4 | 2025-07 to 2025-08 | +0.24% | ➕ | No |
| W5 | 2025-09 to 2025-10 | −0.12% | ➖ | No |
| W6 | 2025-11 to 2025-12 | −0.05% | ➖ | No |
| W7 | 2026-01 to 2026-02 | −0.22% | ➖ | No |
| W8 | 2026-03 to 2026-04 | +0.44% | ➕ | Yes (CI [+0.08, +0.79]) |
| W9 | 2026-05 to 2026-06 | −0.44% | ➖ | No |
| OOS | 2026-07 to 2026-09 | +0.06% | ➕ | No (CI [−0.23, +0.34]) |

**OOS conclusion:** Point estimate is positive (+0.06%), CI spans zero.
**OOS status = CONDITIONAL, not VALIDATED.**

---

## 5. In-Sample Contamination for Hybrid

### Which data is in-sample?

The Hybrid V1 rules (Bear → wait; Flat MA20 → wait) were derived by examining
the 2024-10 to 2026-09 research cohort (Cohort B).

Therefore:

- Any Hybrid analysis run on Cohort B = **IN-SAMPLE**
- `data/hybrid_backtest.json` = IN-SAMPLE retrospective results
- These results cannot distinguish whether Hybrid genuinely outperforms, or
  whether the rules simply overfit the patterns in Cohort B

### True OOS

Only signals with `signal_date >= 2026-11-05` (rule freeze date) in the
`hybrid_forward_shadow` SQLite table represent true prospective OOS data.

---

## 6. Dedup Methodology

**28-calendar-day dedup:** For each stock, keep only the first signal within
any 28-calendar-day window.  This prevents serial correlation between signals
(a stock generating a signal every 5 days would otherwise count the same trade
multiple times with overlapping hold periods).

28 calendar days ≈ 20 trading days = the standard V1/V2 hold period.

This dedup is applied consistently across V1, V2, and Hybrid analyses.

---

## 7. Simulation Assumptions (SA) Summary

| SA | Assumption | Impact |
|---|---|---|
| SA-1 | WAIT_FOR_PULLBACK trigger at LOW ≤ MA20_est × 1.03 (CONFIRMED_NEXT_OPEN) | Conservative fill assumption |
| SA-2 | WAIT_FOR_BREAKOUT trigger at CLOSE > prior_20d_high (CONFIRMED_NEXT_OPEN) | Conservative fill assumption |
| SA-3 | Same-day stop + target → stop first | Downward bias on returns |
| SA-4 | Gap down through stop → exit at open | Gap slippage modelled |
| SA-5 | 20 trading day hold | Fixed horizon; no early exit on momentum |
| SA-6 | 0.585% round-trip fees | Based on Taiwan brokerage rates |
| SA-7 | V2 no-fill → 0% return in FOS | Downward bias on V2 FOS mean |

---

## 8. Data Quality Flags

Each signal is tagged with three boolean quality flags:

- `is_raw` — before dedup (included in concentration audits only)
- `is_dedup_kept` — passes the 28-day dedup rule
- `is_matured` — had ≥ 22 forward OHLC bars at simulation time

Only signals with `is_dedup_kept = True AND is_matured = True` are used in
all performance analyses (V1/V2/Hybrid comparisons).
