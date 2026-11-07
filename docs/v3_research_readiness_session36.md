# V3 Research Readiness Assessment — Session 36

**Date:** 2026-11-08  
**Audit Type:** Read-only readiness evaluation  
**Version:** session36_v1

---

## 1. V3ResearchReadinessReport Summary

**Verdict: `RESEARCH_BLOCKED`**

V3 cannot advance to production activation. Six categories of blockers exist: no prospective evidence, cron execution unresolved, sparse training universe, no walk-forward windows, no outcomes, and data integrity gaps. No technical code changes were made in this session.

---

## 2. Component Hash Verification

| Component | Hash | Status |
|---|---|---|
| BT_HASH (backtest engine) | `be43e8ca977d9fdd` | UNCHANGED |
| CP_HASH (comparison) | `1feb7a6b294a063d` | UNCHANGED |
| hybrid_shadow_cron.py | `46209171…` | UNCHANGED |
| SD_VERSION | v2 | UNCHANGED |
| Git HEAD | ad6fbb8 | UNCHANGED |
| Test count | 2042 PASS, 1 skip | UNCHANGED |

---

## 3. V3 Research Findings (Historical)

| Session | Phase | Metric | Value | Verdict |
|---|---|---|---|---|
| Session 26 | Prototype + BT Engine | — | Completed | — |
| Session 27 | In-sample comparison | V3 vs V2 net_return | +3.66ppt | SIGNIFICANT_POSITIVE (5D) |
| Session 28 | Walk-forward | Feasible windows | **0** | MARKET_AVOIDANCE_DRIVEN |
| Session 28 | Walk-forward | Net return (adj) | +1.33% | INSUFFICIENT_EVIDENCE |
| Session 29 | Prospective shadow | Genuine captures | **0** | FRAMEWORK_READY, NO_EVIDENCE |

---

## 4. Blockers

### B1 — No Walk-Forward Windows (Session 28)

**Status: BLOCKER**

Walk-forward validation requires at least 1 feasible window (non-trivial in-sample, non-trivial OOS period with market diversity). V3 showed 0 feasible windows because the market avoidance signal dominated all periods.

A model that primarily avoids the market produces positive nominal returns but cannot be distinguished from a cash-holding strategy. Insufficient evidence to attribute the +3.66ppt in-sample gain to genuine stock selection ability.

**Resolution path:** V3 requires redesign (Session 29 conclusion). The prospective shadow was intended to gather live evidence of stock selection quality independent of avoidance bias.

---

### B2 — No Prospective Evidence

**Status: BLOCKER**

As documented in `v3_prospective_evidence_audit_session36.md`:
- Genuine prospective captures: 0
- hybrid_forward_outcome rows: 0
- Root cause: cron has never executed; all 21 decisions are RETROSPECTIVE_RECONSTRUCTION

**Resolution path:** Requires cron to execute successfully on a trading day at 16:00, which requires Stage B authorization (see `isolated_cron_stage_b_approval_request.md`).

---

### B3 — Cron Root Cause Inconclusive (Sessions 34–35)

**Status: BLOCKER**

Root cause for the Nov 6 cron failure is `ROOT_CAUSE_INCONCLUSIVE`. BTM entry exists as `[enabled, allowed, not notified] (0x3)`. Whether `not notified` blocks execution is undocumented by Apple.

Stage B isolation test is designed to resolve this but has not been authorized.

**Resolution path:** User authorizes Stage B (see `isolated_cron_stage_b_approval_request.md`).

---

### B4 — Sparse Training Universe

**Status: RESEARCH_CONCERN**

All 7 ForwardSignals dates (Oct 12–28, 2026) have SPARSE DailyPrice coverage (~655 TWSE-subset stocks). The full Taiwan market has ~6957 stocks (826 TWSE + ~6131 TPEx).

**Implications:**
1. The in-sample comparison (+3.66ppt) was conducted on ~10% of the market universe
2. TWSE-only universe introduces sector concentration bias (financial, manufacturing)
3. When full-market data becomes available, signal scores may change significantly
4. Backtest results on sparse data may not generalize to production (where full-market data would be expected)

**Severity:** This affects both V3 and V2 equally (same data for both), so the relative comparison (+3.66ppt) may still be internally consistent. However, absolute performance claims and production readiness require full-market data.

**Resolution path:** Full-market DailyPrice coverage on all future trading days. Requires cron to execute successfully (triggers DailyPrice pipeline). Oct 12–28 historical dates cannot be retroactively filled without explicit authorization.

---

### B5 — 0 Outcome Rows

**Status: BLOCKER**

No hybrid_forward_outcome rows exist. Even if the 21 retrospective decisions were counted as evidence, there are no outcome observations.

**Timeline constraint:** The 20-day outcome window for Nov 4 trade decisions closes approximately 2026-12-02. No outcomes will be available before that date regardless of other actions.

**Resolution path:** Prospective decisions must exist first (B2 blocker). After that, 20 trading days of market data must elapse.

---

### B6 — TPEx Data Gap

**Status: RESEARCH_CONCERN**

TPEx stocks (estimated ~6131) are absent from the `stocks` table and therefore absent from ForwardSignals generation. The signal universe is effectively TWSE-only on most dates.

**Resolution path:** Requires a separate ETL pipeline to load TPEx stocks into the `stocks` table with proper classification. Not part of the current roadmap.

---

## 5. Activation Readiness Checklist

| ID | Criterion | Status | Blocker |
|---|---|---|---|
| R1 | Crontab installed | PASS | — |
| R2 | Cron daemon running | PASS | — |
| R3 | Python path absolute | PASS | — |
| R4 | Log redirect configured | PASS | — |
| R5 | hybrid_cron.log exists | **FAIL** | B3 |
| R6 | At least 1 cron execution confirmed | **FAIL** | B3 |
| R7 | At least 1 ForwardSignal (v8.0) | PASS | — |
| R8 | DailyPrice backfill current | **FAIL** | Nov 6 missing |
| R9 | Full-market DailyPrice on signal dates | **FAIL** | B4 |
| R10 | ≥1 genuine prospective decision | **FAIL** | B2 |
| R11 | ≥1 hybrid_forward_outcome | **FAIL** | B5 |
| R12 | V3 shadow activated | **FAIL** | B1, B2, B3 |
| R13 | BTM root cause resolved | **FAIL** | B3 |
| R14 | Walk-forward validation PASS | **FAIL** | B1 |

**6 blockers remain. ACTIVATION_BLOCKED.**

---

## 6. Research Timeline Projection

| Milestone | Prerequisite | Earliest Date |
|---|---|---|
| Stage B authorized | User decision | — |
| Stage B test run | Stage B authorized | Day of authorization |
| Cron root cause resolved | Stage B PASS | Same day |
| First prospective decision | Cron resolved + trading day | Next trading day 16:00 |
| First 20d outcome | Prospective decision | ~20 trading days later (≈Dec 2026) |
| Minimum power (N=50) | 50 trading days of cron | ≈Feb 2027 |
| Walk-forward redesign | Model redesign (B1) | Separate roadmap item |

---

## 7. What Is NOT Blocked

The following work can proceed in parallel, independent of cron resolution:

| Work Item | Status |
|---|---|
| TPEx stock table ETL design | Unblocked (read-only design) |
| V3 model redesign (address market avoidance bias) | Unblocked (research work) |
| ForwardSignals quality audit | Unblocked (read-only) |
| DailyPrice pipeline improvement | Unblocked (read-only audit) |
| Stage B controlled test | Blocked only on user authorization |

---

## 8. Research Readiness Verdict

| Dimension | Verdict |
|---|---|
| Walk-forward validation | `INSUFFICIENT_EVIDENCE` |
| Prospective shadow | `NO_GENUINE_PROSPECTIVE_EVIDENCE` |
| Cron execution | `SCHEDULED_EXECUTION_NOT_OBSERVED` |
| Data quality | `DATA_INTEGRITY_PARTIAL` |
| **Overall V3 Readiness** | **`RESEARCH_BLOCKED`** |
| **V3 Activation** | **`ACTIVATION_BLOCKED`** |
