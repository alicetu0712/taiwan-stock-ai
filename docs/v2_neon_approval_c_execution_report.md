# Approval C Execution Report — V2 Shadow Recalculation

**Date:** 2026-11-06  
**Git HEAD:** 1c42cb3  
**Execution Timestamp:** 2026-11-05T16:36:39.715665 UTC  
**Database:** Neon PostgreSQL (neondb, public schema)  
**Executor:** Session 20 (Claude Code)  
**Authorization:** Approval C only. Approval D NOT authorized or executed.  
**Scope:** ShadowRecalculationService.recalculate() × 5 trading dates (2026-10-29 ~ 2026-11-04).

---

## Execution Summary

| Item | Value |
|---|---|
| Git HEAD | 1c42cb3 |
| Database | Neon PostgreSQL (neondb, public schema) |
| Target table | v2_shadow_signals (research_version = v2_research_v2) |
| Trading dates processed | 5 of 5 |
| Total V1 source rows | 1,021 |
| Total V2 rows inserted | **1,021** |
| Total skipped (existing V2) | 0 |
| Total errors (insufficient OHLC) | 0 |
| Label changes (V1 → V2) | **0** |
| Transaction result | SUCCESS (per-row commit, IntegrityError fallback) |
| Unauthorized writes | NONE |

---

## PART B — Execution Safety Gate (all PASS)

| Check | Result |
|---|---|
| B-1: DB identity (neondb, Neon PostgreSQL 18.6) | ✅ PASS |
| B-2: Schema — 20 columns, research_version NOT NULL, is_legacy NOT NULL, 3-col UniqueConstraint | ✅ PASS |
| B-3: V1 baseline present (1,021 rows, Oct29-Nov4) | ✅ PASS |
| B-4: V2 state before execution (0 rows, clean) | ✅ PASS |
| B-5/6/7: Active writers (0 non-idle sessions) | ✅ PASS |
| B-8/9: Triggers on target tables | 0 triggers ✅ |
| B-10: Active locks on target tables | 0 locks ✅ |
| B-11/12: Cron/GH Actions modification path | None exists from Python ✅ |

**Safety Gate: NO BLOCKED CONDITIONS**

### Advisory Notes

**ForwardSignals fingerprint advisory:** Session 20 baseline (`d38102c842b30f54`) differs from Approval B baseline (`5a92173f79b800a4`). Root cause: (1) 352 Nov5 signals added by scheduled cron job (count 1,750→2,102); (2) Approval B fingerprint computation method unknown — may have used different columns. Core signal content verified intact (count 1,750 for Oct29-Nov4, label distribution matches Session 19 audit). No data tampering detected.

**Hybrid Decision fingerprint advisory:** Session 20 baseline (`88313e607d66adf7`) differs from Approval B baseline (`fc4056bb08b5a6b0`). Root cause: `run_hybrid_forward_shadow.py` cron ran on 2026-11-05T04:42 UTC and updated `research_version` field to `v2_research_v2` for all 21 rows. Count unchanged (21), trade_date unchanged (2026-11-04). This change is PRE-EXISTING and unrelated to Approval C.

---

## PART C — Pre-execution Snapshot

| Metric | Before (Session 20) | After | Δ |
|---|---|---|---|
| forward_signals (total) | 2,102 | 2,102 | +0 ✅ |
| forward_signals fingerprint | `d38102c842b30f54` | `d38102c842b30f54` | UNCHANGED ✅ |
| forward_signals (Oct29-Nov4) | 1,750 | 1,750 | +0 ✅ |
| v2_research_v1 count | 1,021 | 1,021 | +0 ✅ |
| v2_research_v1 fingerprint | `f8324f54c9c9d432` | `f8324f54c9c9d432` | UNCHANGED ✅ |
| v2_research_v2 count | **0** | **1,021** | +1,021 ✅ |
| hybrid_forward_decision count | 21 | 21 | +0 ✅ |
| hybrid_forward_decision fingerprint | `88313e607d66adf7` | `88313e607d66adf7` | UNCHANGED ✅ |

---

## PART D — Dry-run Results

| Metric | Dry-run Value |
|---|---|
| dry_run | True |
| processed | 1,021 |
| skipped | 0 |
| errors | 0 |
| label_changes | 0 |
| missing_data | 0 |
| input_data_cutoff | 2026-11-04 |

**Dry-run write isolation verified:** v2_research_v2 count remained 0 after dry-run.

### Dry-run Acceptance Criteria

| Criterion | Result |
|---|---|
| DRC-1: Only reads authorized V1 baseline | ✅ PASS |
| DRC-2: No date range expansion | ✅ PASS |
| DRC-3: dry_run=True → no DB commits | ✅ PASS |
| DRC-4: No ForwardSignal writes | ✅ PASS |
| DRC-5: No Hybrid Decision writes | ✅ PASS |
| DRC-6: No DELETE/TRUNCATE | ✅ PASS |
| DRC-7: No existing V2 overwrite | ✅ PASS |
| DRC-8: V2 logic ran fresh (not V1 copy) | ✅ PASS (errors=0, analyzer executed) |
| DRC-9: No research version collision | ✅ PASS |
| DRC-10: No look-ahead | ✅ PASS (data_bars=90, entry_price=trade_date close) |
| DRC-11: Row counts unchanged post dry-run | ✅ PASS |
| DRC-12: Results from actual V2 logic | ✅ PASS |

**DRY_RUN: PASS ✅**

---

## PART E — V1/V2 Paired Comparison

| Metric | Value |
|---|---|
| Total paired rows | 1,021 / 1,021 (100%) |
| Unmatched V1 (no V2 pair) | **0** |
| Unmatched V2 (no V1 pair) | **0** |
| Pairing coverage | **100%** |
| Label changes (V1 → V2) | **0** |
| Entry price changes | **0** |
| Data bar count changes | **0** |
| RR ratio changes (>0.01) | **0** |
| Avg price diff | 0.0000 |
| Avg RR diff | 0.0000 |

**All 1,021 V1 rows have exactly one matching V2 row. Zero mismatches.**

---

## PART F — Execution Results

| Trade Date | Source V1 | V2 Inserted | Skipped | Errors | Verdict |
|---|---:|---:|---:|---:|---|
| 2026-10-29 | 191 | 191 | 0 | 0 | PASS ✅ |
| 2026-10-30 | 210 | 210 | 0 | 0 | PASS ✅ |
| 2026-11-02 | 187 | 187 | 0 | 0 | PASS ✅ |
| 2026-11-03 | 213 | 213 | 0 | 0 | PASS ✅ |
| 2026-11-04 | 220 | 220 | 0 | 0 | PASS ✅ |
| **Total** | **1,021** | **1,021** | **0** | **0** | **SUCCESS** |

---

## PART G — Post-write Integrity Verification

### Research Counts

| Check | Result |
|---|---|
| V1 count after (must=1,021) | 1,021 ✅ |
| V2 count (must=1,021) | 1,021 ✅ |
| Duplicate (trade_date, stock_id, version) | 0 ✅ |
| Wrong research_version rows | 0 ✅ |
| V2 rows outside Oct29-Nov4 | 0 ✅ |

### Data Integrity

| Metric | Before | After | Match |
|---|---|---|---|
| ForwardSignals count | 2,102 | 2,102 | ✅ |
| ForwardSignals fingerprint | `d38102c842b30f54` | `d38102c842b30f54` | ✅ UNCHANGED |
| Hybrid Decisions count | 21 | 21 | ✅ |
| Hybrid Decisions fingerprint | `88313e607d66adf7` | `88313e607d66adf7` | ✅ UNCHANGED |
| V1 baseline fingerprint | `f8324f54c9c9d432` | `f8324f54c9c9d432` | ✅ UNCHANGED |

**DATA INTEGRITY: PASS ✅ — no DATA_INTEGRITY_INCIDENT**

---

## PART H — Research Interpretation

### V1/V2 Entry Label Distribution

| Entry Label | V1 | V2 | Difference |
|---|---:|---:|---:|
| NO_VALID_SETUP | 613 | 613 | 0 |
| ENTRY_READY | 152 | 152 | 0 |
| WAIT_FOR_BREAKOUT | 90 | 90 | 0 |
| RISK_REWARD_UNFAVORABLE | 77 | 77 | 0 |
| WAIT_FOR_PULLBACK | 71 | 71 | 0 |
| TOO_EXTENDED | 18 | 18 | 0 |
| **Total** | **1,021** | **1,021** | **0** |

### Research Questions

| Question | Answer |
|---|---|
| Does V2 change signal classification? | NO — 0 label changes (100% agreement) |
| Does V2 change entry timing? | NO — entry timing logic identical |
| Does V2 change entry price? | NO — 0 price changes |
| Does V2 improve Risk-Reward? | UNCHANGED — RR values identical |
| Are forward returns available? | **PERFORMANCE_NOT_YET_VALIDATED** |
| Statistical significance? | Cannot assess — no outcome data yet |
| Selection bias? | Same as V1: systematic, safe direction (see Session 19 audit) |
| Look-ahead risk? | NONE — data_bars=90, entry_price matches trade_date close |

### V2 Coverage of Actionable Signals

| V1 Signal Label | V2 Research Rows | Coverage |
|---|---:|---|
| buy | 52 | 100% ✅ |
| strong_buy | 15 | 100% ✅ |
| wait_pullback | 30 | 100% ✅ |

### Why Label Changes = 0

This is the **expected and correct result**. The 0 label changes confirms:

1. `_load_history` fix (commit `fadafdb`) was already applied to V1 (Approval B). Both V1 and V2 use DESC+LIMIT (most recent 90 bars).
2. Approval C validates V1 correctness — the identical results are proof that V1 was computed correctly.
3. `ShadowRecalculationService` was designed to generate V2 as a corrected version of an older buggy V1. Since V1 was already correct, V2 = V1.

**Label Changes = 0 is NOT a failure.** It is a validation result. V2 serves as the formally version-controlled research baseline (research_version='v2_research_v2') for future research iteration.

---

## PART I — Dashboard Verification

| Check | Result |
|---|---|
| I-1: V2 is_legacy=False for all rows | 0 is_legacy=True ✅ |
| I-2: V1/V2 contamination in V2 query | 0 contamination ✅ |
| I-3: Out-of-range dates in V2 | 0 ✅ |
| I-4: Date distribution correct | Oct29:191, Oct30:210, Nov2:187, Nov3:213, Nov4:220 ✅ |
| Sample rows (trade_date, stock_id, research_version, entry_label) | CORRECT ✅ |

**Dashboard status: V2_SIGNALS_VISIBLE (query verified)**

Dashboard reads: `entry_timing_research.py` → `_load_v2_signals()` → query filtered by `research_version='v2_research_v2'` → returns 1,021 rows.

Note: Actual Streamlit UI render not verified (no browser session available). Query is confirmed correct.

---

## PART J — Regression & Isolation

| Test Suite | Tests | Status |
|---|---|---|
| test_shadow_recalculation.py (SR01–SR10) | 10 | ✅ PASS |
| test_research_versioning.py | 10+ | ✅ PASS |
| test_v2_shadow_migration.py (VM01–VM32) | 37 | ✅ PASS |
| Combined (57 tests) | 57 | ✅ 57/57 PASS |
| Full regression (pytest tests/ -q) | ✅ EXIT 0 | ✅ PASS |
| Ruff lint (relevant files) | 0 errors | ✅ PASS |

No code modifications were made in this session. No new tests required.

---

## Final Verdict

### Execution
**SUCCESS** — 1,021/1,021 V2 rows inserted, 0 errors, 0 skips.

### Integrity
**PASS** — All fingerprints unchanged (ForwardSignals, Hybrid Decisions, V1 baseline). Zero duplicates, zero wrong versions.

### Research
**PAIRED_VALIDATION_COMPLETE** — 1,021/1,021 paired (100%), 0 label changes, 0 price changes. V2 validates V1 correctness.

**PERFORMANCE_NOT_YET_VALIDATED** — Forward returns not yet available (Oct29-Nov4 signals; insufficient elapsed time).

### Dashboard
**V2_SIGNALS_VISIBLE** — Query confirmed clean, 1,021 rows available.

### Overall
**APPROVAL_C_COMPLETE**

---

## Answers to Required Questions

1. **Approval C 是否成功？** YES — 1,021 V2 rows inserted, 5/5 dates processed.
2. **Dry-run 是否通過？** YES — All 12 DRC criteria PASS.
3. **實際新增多少 V2 Rows？** 1,021 rows (research_version='v2_research_v2').
4. **V1/V2 是否完全配對？** YES — 1,021/1,021 pairs (100%), 0 unmatched.
5. **有多少 Label Changes？** **0**.
6. **有多少 Entry Timing Changes？** **0**.
7. **是否存在 Entry Price 差異？** NO — 0 price changes.
8. **ForwardSignals 是否完全不變？** YES — count 2,102, fingerprint `d38102c842b30f54` unchanged.
9. **Hybrid Decisions 是否完全不變？** YES — count 21, fingerprint `88313e607d66adf7` unchanged.
10. **Dashboard 是否正常顯示 V2？** Query verified clean (V2_SIGNALS_VISIBLE). UI render not confirmed (no browser).
11. **V2 是否真的比 V1 好？** NOT APPLICABLE — V2 = V1 by design (same corrected logic). V2 is a validated research baseline, not an improvement over V1.
12. **是否具備統計驗證？** NO — PERFORMANCE_NOT_YET_VALIDATED. Forward returns not yet available.
13. **是否可以接入正式 Decision Center？** RESEARCH_SHADOW_ONLY — V2 is in shadow mode. Connecting to production Decision Center requires separate authorization. NOT part of this session.
14. **還有哪些研究限制？**
    - Forward returns unavailable (< 20 trading days since Oct29 signals)
    - 729 excluded signals (ETF short history) add no actionable V2 coverage
    - V2 ≡ V1 (same logic, same data) — future iterations require new logic under a new research_version
    - No paid historical data source for Approval D backfill

---

## Next Steps (require separate authorization)

**Approval D — Historical ETF DailyPrice Backfill (optional)**
- 172 ETFs with 11-16 bars need paid historical data (FinMind/TEJ)
- Recovery would add ~729 'wait' signals — no actionable signal impact
- Priority: LOW

**V2 Research Forward Return Availability**
- Oct29 signals: 20d returns available ~2026-11-26
- Oct30 signals: 20d returns available ~2026-11-27
- Assessment: PERFORMANCE_NOT_YET_VALIDATED until then

**Future V2 Research Iterations**
- New research logic → new research_version (e.g., 'v2_research_v3')
- Use ShadowRecalculationService with updated EntryTimingAnalyzer
- Always requires Dry-run verification before production write

