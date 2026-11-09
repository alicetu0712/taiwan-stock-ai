# 20D Maturity Verification — Session 45

**Date:** 2026-11-09  
**Session:** S45  
**Module:** `src/research/evidence_policy_s45.py`  
**Verdict:** NOT_READY_FOR_20D

---

## Purpose

Verify per-cluster 20D outcome maturity using actual real-trading-day counts from daily_prices (stock 2330 as proxy). No outcome computation is performed.

---

## Pipeline Status

| Field | Value |
|---|---|
| daily_prices max date | 2026-11-05 |
| Session date | 2026-11-09 (Sunday) |
| Pipeline lag | ≥2 trading days (Nov 06 Thu + Nov 07 Fri missing) |

**Pipeline is behind.** The actual number of real TDs available may be 2 higher than reported below, IF Nov 06 and Nov 07 are Taiwan market trading days. This cannot be confirmed without running the pipeline.

---

## Per-Cluster Maturity

| Fill Date | Signal Date | n | TDs Available (DB) | TDs Required | Maturity Status | ETA (from DB) |
|---|---|---|---|---|---|---|
| Oct 13 | Oct 12 | 46 | 7 | 20 | NOT_YET_MATURE | ~2026-11-24 |
| Oct 14 | Oct 13 | 27 | 6 | 20 | NOT_YET_MATURE | ~2026-11-26 |
| Oct 16 | Oct 14 | 55 | 5 | 20 | NOT_YET_MATURE | ~2026-11-27 |
| Oct 21 | Oct 16 | 39 | 4 | 20 | NOT_YET_MATURE | ~2026-11-29 |
| Oct 22 | Oct 21 | 23 | 3 | 20 | NOT_YET_MATURE | ~2026-11-30 |
| Oct 28 | Oct 22 | 19 | 2 | 20 | NOT_YET_MATURE | ~2026-12-02 |

**0 clusters mature as of S45.**

---

## ETA Comparison (S44 vs S45)

| Fill Date | S44 ETA (Nov 05 DB) | S45 ETA (Nov 05 DB) | Match? |
|---|---|---|---|
| Oct 13 | ~2026-11-24 | ~2026-11-24 | ✓ |
| Oct 14 | ~2026-11-25 | ~2026-11-26 | ≈ (1 day) |
| Oct 16 | ~2026-11-26 | ~2026-11-27 | ≈ |
| Oct 21 | ~2026-11-28 | ~2026-11-29 | ≈ |
| Oct 22 | ~2026-12-02 | ~2026-11-30 | ≈ |
| Oct 28 | ~2026-12-02 | ~2026-12-02 | ✓ |

**S44 estimates confirmed.** Minor ±1 day differences due to calendar rounding vs trading-day counting.

---

## If Pipeline Lag Is Resolved

If Nov 06 and Nov 07 are real trading days (≥50 stocks), actual TD counts would be:
- Fill Oct 13: 9 TDs (not 7) → ETA shifts to ~2026-11-20
- Fill Oct 14: 8 TDs → ~2026-11-21
- Fill Oct 16: 7 TDs → ~2026-11-22

**This would accelerate all ETAs by approximately 4 days.** However, this is UNCONFIRMED without pipeline data.

---

## 20D Date Definitions (Canonical)

| Term | Definition |
|---|---|
| Signal + 20 TDs | 20 real trading days (≥50 stocks) after signal_date |
| Execution + 20 TDs | 20 real TDs after execution_date (fill_date) — the canonical definition |
| 20 Completed Sessions | 20 full market sessions from fill to exit |
| Exit Execution Date | The 20th real TD after fill_date |
| Data Availability Date | Same as exit_execution_date (data published after close) |

**All 20D measurement uses Execution + 20 real TDs.** Calendar-day approximations are NOT used.

---

## 0050 Benchmark Coverage

0050 is available on all currently-available exit dates for all clusters. No benchmark gap identified for the existing 2–7 TDs.

---

## Authorization Status

> This session (S45) does **NOT** authorize 20D outcome computation.  
> Even if clusters become mature, AUTH01 and AUTH02 must be explicitly granted in a future session prompt before computation may proceed.
