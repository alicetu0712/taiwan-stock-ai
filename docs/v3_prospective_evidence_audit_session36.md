# V3 Prospective Evidence Audit — Session 36

**Date:** 2026-11-08  
**Audit Type:** Read-only classification of all hybrid_forward_decision rows  
**Version:** session36_v1

---

## 1. ProspectiveEvidenceEligibilityReport Summary

**Verdict: `NO_GENUINE_PROSPECTIVE_EVIDENCE`**

All 21 hybrid_forward_decision rows are classified as `RETROSPECTIVE_RECONSTRUCTION`. Zero rows qualify as genuine prospective evidence. Zero hybrid_forward_outcome rows exist.

---

## 2. Prospective Eligibility Criteria

A decision is **PROSPECTIVE** if and only if:
1. `capture_classification = PROSPECTIVE_CAPTURE` (not RETROSPECTIVE_RECONSTRUCTION)
2. It was inserted by the scheduled cron job before market close on trade_date
3. `captured_at` is on or before 2026-11-04 16:30 CST (trade_date market close)

A decision is **RETROSPECTIVE_RECONSTRUCTION** if:
1. It was inserted after the trading period of trade_date ended
2. OR it was inserted via a manual/batch run (not the scheduled cron)
3. OR `capture_classification = RETROSPECTIVE_RECONSTRUCTION`

---

## 3. Full Classification of All 21 Decisions

| # | id | trade_date | captured_at | classification | Genuine Prospective? |
|---|---|---|---|---|---|
| 1 | 1 | 2026-11-04 | 2026-11-05T04:42:30 | RETROSPECTIVE_RECONSTRUCTION | **No** |
| 2 | 2 | 2026-11-04 | 2026-11-05T04:42:30 | RETROSPECTIVE_RECONSTRUCTION | **No** |
| 3 | 3 | 2026-11-04 | 2026-11-05T04:42:30 | RETROSPECTIVE_RECONSTRUCTION | **No** |
| 4 | 4 | 2026-11-04 | 2026-11-05T04:42:30 | RETROSPECTIVE_RECONSTRUCTION | **No** |
| 5 | 5 | 2026-11-04 | 2026-11-05T04:42:30 | RETROSPECTIVE_RECONSTRUCTION | **No** |
| 6 | 6 | 2026-11-04 | 2026-11-05T04:42:30 | RETROSPECTIVE_RECONSTRUCTION | **No** |
| 7 | 7 | 2026-11-04 | 2026-11-05T04:42:30 | RETROSPECTIVE_RECONSTRUCTION | **No** |
| 8 | 8 | 2026-11-04 | 2026-11-05T04:42:30 | RETROSPECTIVE_RECONSTRUCTION | **No** |
| 9 | 9 | 2026-11-04 | 2026-11-05T04:42:30 | RETROSPECTIVE_RECONSTRUCTION | **No** |
| 10 | 10 | 2026-11-04 | 2026-11-05T04:42:30 | RETROSPECTIVE_RECONSTRUCTION | **No** |
| 11 | 11 | 2026-11-04 | 2026-11-05T04:42:30 | RETROSPECTIVE_RECONSTRUCTION | **No** |
| 12 | 12 | 2026-11-04 | 2026-11-05T04:42:30 | RETROSPECTIVE_RECONSTRUCTION | **No** |
| 13 | 13 | 2026-11-04 | 2026-11-05T04:42:30 | RETROSPECTIVE_RECONSTRUCTION | **No** |
| 14 | 14 | 2026-11-04 | 2026-11-05T04:42:30 | RETROSPECTIVE_RECONSTRUCTION | **No** |
| 15 | 15 | 2026-11-04 | 2026-11-05T04:42:30 | RETROSPECTIVE_RECONSTRUCTION | **No** |
| 16 | 16 | 2026-11-04 | 2026-11-05T04:42:30 | RETROSPECTIVE_RECONSTRUCTION | **No** |
| 17 | 17 | 2026-11-04 | 2026-11-05T04:42:30 | RETROSPECTIVE_RECONSTRUCTION | **No** |
| 18 | 18 | 2026-11-04 | 2026-11-05T04:42:30 | RETROSPECTIVE_RECONSTRUCTION | **No** |
| 19 | 19 | 2026-11-04 | 2026-11-05T04:42:30 | RETROSPECTIVE_RECONSTRUCTION | **No** |
| 20 | 20 | 2026-11-04 | 2026-11-05T04:42:30 | RETROSPECTIVE_RECONSTRUCTION | **No** |
| 21 | 21 | 2026-11-04 | 2026-11-05T04:42:30 | RETROSPECTIVE_RECONSTRUCTION | **No** |

**All 21: RETROSPECTIVE_RECONSTRUCTION**  
**Genuine Prospective: 0 / 21 (0%)**

---

## 4. Why All 21 Are Retrospective

**Timeline of events:**
- 2026-11-04 (Tuesday): Trading day. The cron job (`0 16 * * 1-5`) was scheduled to run at 16:00. It did not run (confirmed: `hybrid_cron.log` absent, DailyPrice Nov 6 = 0 rows — cron execution failure).
- 2026-11-05 (Wednesday): DailyPrice backfill for Nov 4 performed manually. The hybrid shadow pipeline was run manually against the Nov 4 market data, producing all 21 decisions.
- **captured_at: 2026-11-05T04:42:30** — This is 12 hours and 42 minutes AFTER the Nov 4 market close (16:00). All decisions were inserted in a single batch at this timestamp.

**Result:** These 21 decisions are legitimate reconstructions of what the model *would have* decided on 2026-11-04 given the market data, but they were NOT captured by an independent, pre-specified scheduled process before the outcome was observable. They therefore do not constitute prospective evidence under any standard statistical framework.

---

## 5. Run Log Evidence

| trade_date | event | count |
|---|---|---|
| 2026-11-04 | INSERTED (first run) | 21 |
| 2026-11-04 | SKIPPED_CONFLICT (second run) | 21 |
| 2026-11-04 | SKIPPED_CONFLICT (third run) | 21 |
| 2026-11-05 | SKIPPED_NON_TRADING_DAY | 0 |
| 2026-11-05 | BLOCKED_MISSING_SIGNALS | 0 |

The first run (which created all 21 rows) occurred at 2026-11-05T04:42:30 — the day after the trading date.

---

## 6. Research Version Coverage

| research_version | Decision Count |
|---|---|
| v2_research_v2 | 21 |
| Other | 0 |

All decisions are v2_research_v2. No v3 decisions exist. V3 is not yet activated.

---

## 7. Outcomes Status

| Table | Rows |
|---|---|
| hybrid_forward_decision | 21 |
| hybrid_forward_outcome | **0** |

No outcomes have been evaluated. This is expected: the 21 decisions are for 2026-11-04 trade entries. As of 2026-11-08, the 20-day outcome window would not close until approximately 2026-12-02. However, even when outcomes become available, they will not constitute prospective evidence under the classification above.

---

## 8. Impact on V3 Validation Framework

The prospective validation framework (Phase 3+) requires:
1. `N_prospective ≥ 1` genuine prospective decision
2. At least one hybrid_forward_outcome row with valid return data
3. The decision must have been captured by scheduled cron (not manual batch)

**Current state:**
- Requirement 1: **FAIL** (0 genuine prospective captures)
- Requirement 2: **FAIL** (0 outcome rows)
- Requirement 3: **FAIL** (cron has never successfully executed)

**V3 Prospective Evidence Status: `NO_GENUINE_PROSPECTIVE_EVIDENCE`**

This is a hard blocker for the Evidence Dashboard Phase 4 (live performance) and all prospective-based readiness criteria (R10–R12 in the activation checklist).

---

## 9. What Would Change This Status

The prospective evidence clock starts the **first day** that:
1. `hybrid_shadow_cron.py` executes successfully at 16:00 on a trading day (via scheduled cron, not manual)
2. `hybrid_forward_decision` rows are inserted with `captured_at` within 30 minutes of market close
3. Those rows are classified by the pipeline as `PROSPECTIVE_CAPTURE`

**Minimum time to first prospective evidence:** Next trading day after cron root cause is resolved (Stage B authorized + executed + BTM fix if needed + cron verified running).

**Minimum time to first outcome:** 20 trading days after first prospective decision (earliest: ~mid-December 2026 if cron fixed immediately).

**Minimum decisions for statistical power:** Research suggests N≥50 prospective decisions for meaningful inference. At one trading day per session: ~50 trading days ≈ 2.5 months.
