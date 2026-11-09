# 20D Authorization Readiness (AUTH01/AUTH02) — Session 49

**Date:** 2026-11-09  
**Session:** S49 — PART G (P6)  
**Verdict:** ACTIVATION_BLOCKED (AUTH01 and AUTH02 both pending)

---

## Overview

Two authorization items are required before 20D outcomes can be computed:

- **AUTH01**: Backfill Oct 29/30/Nov 02/03 into local SQLite
- **AUTH02**: Compute 20D return outcomes for Oct 13/14/16 fills

Neither is currently authorized.

---

## AUTH01: Data Backfill Authorization

| Field | Value |
|---|---|
| Status | AUTH01_PENDING |
| Earliest execution | 2026-11-09 (today) |
| Target dates | Oct 29/30/Nov 02/03 (Priority 1) |
| Method | `backfill_daily_prices.py --research-only --execute` |
| Expected outcome | Strict count 3→6; Oct 21/22/28 promoted to STRICT |

### Prerequisites for AUTH01
1. INSERT OR IGNORE idempotency verified ✓ (SC04 confirmed)
2. Local SQLite only (not Neon) ✓ (SAFETY-02)
3. TWSE single-stock API source verified ✓ (TSMC prices confirmed for Oct 29/30)
4. QG validation must pass for each backfilled date
5. **User authorization required**

---

## AUTH02: 20D Outcome Computation Authorization

| Field | Value |
|---|---|
| Status | BLOCKED_PIPELINE |
| Earliest maturity | 2026-11-12 (Oct 13 fill → 20TD) |
| Days until maturity | 3 calendar days |
| Latest maturity | 2026-11-25 (Oct 28 fill → 20TD) |

### Prerequisites for AUTH02
1. AUTH01 completed (pipeline has full data for Oct 29–Nov 03)
2. Pipeline restored: Nov 06+ pipeline must run successfully
3. Nov 12/13/17/20/23/25 must have ≥300 stocks in local SQLite
4. Holding-period convention specified (calendar 20TD vs price-available 20TD)
5. G03/G04 guardrails acknowledged (outcome SIGNIFICANCE_INCONCLUSIVE expected)
6. **User authorization required**

### Critical Path

1. **AUTH01 granted** → execute backfill Oct 29/30/Nov 02/03
2. **Pipeline restoration** (fix QUALITY_GATE_FAIL + PROVIDER_NOT_READY)
3. Wait for **Nov 12** (Oct 13 fill 20D maturity)
4. Confirm Nov 12–25 data present (≥300 stocks each day)
5. **AUTH02 granted** → compute 20D outcomes
6. Note: G03/G04 still FAIL → SIGNIFICANCE_INCONCLUSIVE persists

---

## 20D Exit Date Schedule (Corrected)

| Fill Date | Signals | Corrected 20D Exit | S46 (Wrong) | Δ |
|---|---|---|---|---|
| 2026-10-13 | 46 | 2026-11-12 | 2026-11-14 | -2d |
| 2026-10-14 | 27 | 2026-11-13 | 2026-11-17 | -4d |
| 2026-10-16 | 55 | 2026-11-17 | 2026-11-19 | -2d |
| 2026-10-21 | 39 | 2026-11-20 | 2026-11-24 | -4d |
| 2026-10-22 | 23 | 2026-11-23 | 2026-11-25 | -2d |
| 2026-10-28 | 19 | 2026-11-25 | 2026-12-02 | -7d |

---

## What 20D Computation Does NOT Change

Even after AUTH02:
- **G03 FAIL**: 6 clusters < 10 required
- **G04 FAIL**: adjacent window overlap unchanged
- **SIGNIFICANCE_INCONCLUSIVE**: statistical verdict unchanged
- **Frozen +0.81% 5D baseline**: unchanged (20D is a separate metric)

The 20D data would provide a longer-horizon perspective but does not resolve the statistical power or independence problems.

---

## Timeline Risk

If pipeline is NOT restored by Nov 12:
- Oct 13 fill's 20D exit date passes without data
- Oct 13 becomes permanently NOT_COMPUTABLE for 20D
- Nov 13/17/20/23/25 similarly expire without backfill if pipeline remains broken

**Nov 12 is a hard deadline.** The pipeline must be restored and data confirmed by then for AUTH02 to have any operational value.
