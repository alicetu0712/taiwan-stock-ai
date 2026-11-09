# Backfill Authorization Package — Session 49

**Date:** 2026-11-09  
**Session:** S49 — PART C (P2)  
**Package ID:** AUTH01-{computed hash}  
**Status:** PENDING_USER_AUTHORIZATION

---

## Overview

This document defines the authorization package for backfilling missing stock price data into the local research SQLite (`data/platform.db`). This is NOT a production Neon write authorization.

**Scope:** 9 out of 11 backfill candidates are INSERT_ONLY_CANDIDATE (source verified). 2 dates (Nov 06/09) remain UNIVERSE_UNVERIFIED and are blocked.

---

## Priority Classification

### Priority 1 (Cluster-Critical): Oct 29/30/Nov 02/03

These dates directly promote the 3 incomplete fill clusters from INCOMPLETE to STRICT:

| Date | TSMC Price | Clusters Promoted |
|---|---|---|
| 2026-10-29 | 2415 (confirmed) | Oct 21 (proxy 4→5) |
| 2026-10-30 | 2370 (confirmed) | Oct 21/22 (proxy +1 each) |
| 2026-11-02 | unconfirmed | Oct 21/22/28 (proxy +1 each) |
| 2026-11-03 | unconfirmed | Partial (Oct 28 safety margin) |

**Expected outcome:** Strict count 3 → 6; Oct 21/22/28 all become STRICT.

### Priority 2 (Coverage-Improvement): Oct 08/15/19/20/27

These 5 dates have 0050 proxy only. Full backfill adds ~655 stocks per date but does NOT affect any active fill cluster (no incomplete cluster exits on these dates).

| Date | Current | After Backfill |
|---|---|---|
| Oct 08 | 1 stock | ~655 stocks |
| Oct 15 | 1 stock | ~655 stocks |
| Oct 19 | 1 stock | ~655 stocks |
| Oct 20 | 1 stock | ~655 stocks |
| Oct 27 | 1 stock (TSMC 2330 price=2400 confirmed) | ~655 stocks |

### Blocked: Nov 06/09

Both remain UNIVERSE_UNVERIFIED. See source_verification_s49.md for details.

---

## Safety Constraints (Must Be Honored)

| ID | Rule |
|---|---|
| SAFETY-01 | Use `INSERT OR IGNORE` — existing 0050 proxy rows are preserved |
| SAFETY-02 | Local SQLite (`data/platform.db`) ONLY — Neon is NOT touched |
| SAFETY-03 | Nov 06/09 blocked until QUALITY_GATE_FAIL + PROVIDER_NOT_READY resolved |
| SAFETY-04 | Do NOT modify `forward_signals`, Cron, v8.0 rules, V3 parameters |
| SAFETY-05 | Use `scripts/backfill_daily_prices.py --research-only --execute` |

---

## Expected Cluster Promotion After P1 Backfill

| Fill Date | Before P1 | After P1 | Status |
|---|---|---|---|
| Oct 13 | STRICT (proxy=7) | STRICT (proxy=11) | Unchanged |
| Oct 14 | STRICT (proxy=6) | STRICT (proxy=10) | Unchanged |
| Oct 16 | STRICT (proxy=5) | STRICT (proxy=9) | Unchanged |
| Oct 21 | INCOMPLETE (proxy=4) | **STRICT (proxy=8)** | **Promoted** |
| Oct 22 | INCOMPLETE (proxy=3) | **STRICT (proxy=7)** | **Promoted** |
| Oct 28 | INCOMPLETE (proxy=2) | **STRICT (proxy=5)** | **Promoted** |

---

## Authorization Requirements

1. **User authorization required** to execute `backfill_daily_prices.py --execute`
2. After each date: QG validation must confirm ≥ 300 stocks present
3. After P1 backfill complete: re-run `build_strict_readiness_matrix_5d()` to confirm proxy counts updated
4. **Extended baseline computation (N=6) requires SEPARATE session authorization** — not covered by AUTH01

---

## Idempotency Verification

Simulated in Temporary SQLite (in-memory, not production):
- INSERT OR IGNORE confirmed idempotent: second insert batch adds 0 rows
- Conflict risk = LOW for all 9 INSERT_ONLY candidates
- 0050 proxy row preserved by INSERT OR IGNORE

---

## What AUTH01 Does NOT Authorize

- Computing new 5D baseline with N=6 clusters (requires AUTH02-equivalent)
- Computing 20D outcomes (requires AUTH02 + pipeline restoration)
- Modifying Neon, forward_signals, v8.0 rules, V3
- Backfilling Nov 06/09 (UNIVERSE_UNVERIFIED)
