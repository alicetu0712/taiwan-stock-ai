# V2 Historical OHLC Coverage Audit

**Date:** 2026-11-06  
**Git HEAD:** 1c42cb3  
**Auditor:** Session 19 (Claude Code, read-only)  
**Scope:** 1,750 ForwardSignals × 5 dates (2026-10-29 ~ 2026-11-04) + Approval C readiness assessment  
**Authorization:** Read-only audit. No production writes.

---

## Executive Summary

Approval B initialized 1,021 / 1,750 (58.3%) signals. The remaining 729 (41.7%) were skipped with error code INSUFFICIENT_HISTORY (< 21 DailyPrice bars). This audit classifies every signal, validates the 21-bar rule, identifies the root cause, assesses selection bias, and determines whether Approval C (ShadowRecalculationService.recalculate()) is safe to execute.

**Key findings:**

| Finding | Result |
|---|---|
| Signal classification ambiguity | ZERO — all 1,750 cleanly classified |
| 21-bar rule correctness | VALIDATED (mathematically correct, no off-by-one) |
| Root cause of 729 errors | Insufficient DailyPrice depth for 172 established ETFs |
| Selection bias against actionable signals | ZERO — all 729 excluded signals are decision_label='wait' |
| Approval C safety | SAFE (read: verified safe to execute) |
| Approval C expected outcome | ~1,021 new v2_research_v2 rows, ~0 label changes |
| Backfill (Approval D) urgency | LOW — excluded signals are non-actionable |

**Verdict: READY_FOR_APPROVAL_C**

---

## PART B — Session State Verification

Confirmed at audit start:

| Check | Result |
|---|---|
| Active Neon transactions | 0 ✅ |
| Active run_for_date() processes | 0 ✅ |
| Session 18 background processes | All dead shell snapshots ✅ |
| forward_signals count | 2,102 (1,750 Oct29-Nov4 + 352 Nov5 from cron) ✅ |
| v2_shadow_signals count | 1,021 (unchanged from Approval B) ✅ |
| unauthorized writes | NONE ✅ |

The +352 Nov5 signals are from the first scheduled cron job run (2026-11-06 16:00). These are outside Approval B scope and are not in v2_shadow_signals. No active writer was present at audit start.

---

## PART C — Signal Coverage Mapping

**Source:** 1,750 ForwardSignals with trade_date between 2026-10-29 and 2026-11-04 (inclusive), `decision_label IS NOT NULL`.

### Per-date classification

| Trade Date | RESEARCH_CREATED | INSUFFICIENT_HISTORY | Other | Total |
|---|---:|---:|---:|---:|
| 2026-10-29 | 191 | 132 | 0 | 323 |
| 2026-10-30 | 210 | 151 | 0 | 361 |
| 2026-11-02 | 187 | 129 | 0 | 316 |
| 2026-11-03 | 213 | 156 | 0 | 369 |
| 2026-11-04 | 220 | 161 | 0 | 381 |
| **Total** | **1,021** | **729** | **0** | **1,750** |

### Classification definitions

| Category | Count | Definition |
|---|---:|---|
| RESEARCH_CREATED | 1,021 | V2ShadowSignal row exists for (trade_date, stock_id, v2_research_v1) |
| INSUFFICIENT_HISTORY | 729 | Stock has DailyPrice rows but fewer than 21 bars ≤ trade_date |
| MISSING_DAILYPRICE | 0 | Stock has zero DailyPrice rows |
| QUERY_FILTER_EXCLUSION | 0 | Filtered before OHLC load |
| INVALID_OHLC | 0 | OHLC values NULL or zero |
| DATE_ALIGNMENT_ERROR | 0 | DailyPrice dates misaligned with trade_date |
| UNKNOWN | 0 | Classification impossible |

**All 1,750 signals cleanly classified. No UNKNOWN or multi-category ambiguity.**

---

## PART D — 21-Bar Rule Analysis

### Code reference

`src/analyzers/entry_timing.py:102`
```python
MIN_BARS = 21  # need prior_20d_high without look-ahead
```

`src/analyzers/entry_timing.py:129`
```python
prior_20d_high = float(np.max(high[-21:-1]))  # [-21:-1] excludes today — no look-ahead
```

`src/research/entry_timing_research_service.py:68`
```python
if history is None or len(history) < 21:
    errors += 1
    continue
```

### Rule validation

| Question | Analysis | Verdict |
|---|---|---|
| Why 21? | `high[-21:-1]` requires 21 elements to give 20 prior bars (today excluded). With 21 bars: `high[0:20]` = 20 prior days; today = `high[20]`. | CORRECT |
| Trading days or calendar days? | `DailyPrice.date` only contains actual trading days (no weekends/holidays). Comparison is trading-day based. | CORRECT |
| Is as-of inclusive? | `DailyPrice.date <= as_of` — includes the signal date itself as bar 21. | CORRECT |
| Off-by-one risk? | With exactly 21 bars: today = `close[-1]` / `high[-1]`; prior 20 = `high[-21:-1]` = indices 0-19. MA20 = `mean(close[-20:])` = indices 1-20 (includes today as most recent). All consistent. | NO BUGS |
| `_load_history` order correctness | DESC+LIMIT(90) gives the most recent 90 bars, then `reversed()` restores chronological order. | CORRECT |

**Verdict: LOOKBACK_RULE_VALIDATED** — no code defects, no off-by-one errors.

### _load_history fix confirmation

Commit `fadafdb` ("fix(research): _load_history DESC+reverse + backtest methodology hardening") predates Approval B (HEAD `1c42cb3`). Approval B therefore used the **fixed** DESC+LIMIT version.

Verification via v2_shadow_signals data:
- All 1,021 rows have `data_bars=90` (most recent 90 bars loaded, as expected with fixed query)
- 5/5 sampled ENTRY_READY rows show `entry_price == DailyPrice.close` for the signal's `trade_date` (confirms data is 2026-era, not 2024)

---

## PART E — DailyPrice Coverage Audit

### Overall statistics

| Metric | Value |
|---|---|
| Total stocks in DailyPrice | 9,852 |
| Total rows | 407,128 |
| Date range | 2024-07-01 ~ 2026-11-05 |
| NULL/zero close | 0 ✅ |
| NULL high | 0 ✅ |
| NULL low | 0 ✅ |
| NULL volume | 17,364 (4.3%) |

### ForwardSignal universe coverage

| Metric | Value |
|---|---|
| Distinct stocks in ForwardSignals (Oct29-Nov4) | 410 |
| Stocks with zero DailyPrice records | **0** ✅ |
| Stocks with 1-20 bars on Oct 29 | **172** |
| Stocks with ≥21 bars on Oct 29 | **238** |

### Two-cohort structure

#### Cohort 1: Short-history stocks (172 stocks)

| Property | Value |
|---|---|
| Bars on Oct 29 | 11 (all identical) |
| Bars on Nov 4 | 15 |
| Total bars in DailyPrice | 16 |
| Earliest date | 2026-09-11 (all identical) |
| Data quality | 0 NULL close/high, 0 NULL volume |
| Stock type | Established ETFs (00X codes) |
| Sample IDs | 006208, 00646, 00662, 00692, 00712, 00713, 00735, 00757, 00830, 00878, 00881, 00882, … |

**Actual date pattern for 00713:**
```
2026-09-11  (seed point, isolated)
-- 27-day gap --
2026-10-08  (regular collection resumes)
2026-10-09, 10-12, 10-13, 10-14, 10-16, 10-21, 10-22, 10-28, 10-29, 10-30
2026-11-02, 11-03, 11-04, 11-05
```

**Root cause:** The DailyPrice pipeline added these 172 ETFs to its collection on 2026-09-11 (mass seed of ~4,982 stocks). Regular daily collection for these ETFs resumed on 2026-10-08 (after a ~27-day gap, likely a pipeline configuration gap). No historical backfill was performed. These are **established ETFs with years of market history**, not newly listed stocks.

**Gap classification:** `DATABASE_HISTORY_MISSING` (data exists in market but was not fetched). This is distinct from genuine short history.

#### Cohort 2: Adequate-history stocks (238 stocks)

| Property | Value |
|---|---|
| Bars on Oct 29 | 238–564 |
| Total bars in DailyPrice | 243–569 |
| Earliest date range | 2024-07-01 ~ 2025-08-06 |
| NULL volume in research window (Jul–Nov 2026) | **0** ✅ |

### NULL volume analysis

| Date | Stocks with NULL volume | Cause |
|---|---:|---|
| 2026-10-08 | 6,488 | Mass backfill (price only, no volume) |
| 2026-10-09 | 5,872 | Same |
| 2026-09-11 | 4,982 | Same (original seed date) |
| Other dates | 1 each (25 dates) | Isolated individual rows |

The NULL volume rows are from the initial mass backfill operations and do NOT affect the 238 research stocks (zero NULL volume in the research window).

---

## PART F — Recoverable Signal Estimation

| Root Cause | Signal Count | Stocks Affected | Recoverable? | Recovery Method | Priority |
|---|---:|---:|---|---|---|
| DATABASE_HISTORY_MISSING (ETF pipeline gap) | 729 | 172 | YES — market data exists | Paid source (FinMind/TEJ) for pre-Sep-11 history; ≥21 bars per ETF | LOW |
| MISSING_DAILYPRICE | 0 | 0 | N/A | N/A | N/A |
| GENUINE_SHORT_HISTORY | 0 | 0 | N/A | N/A | N/A |

**Recovery scope:** All 172 ETFs need data back to at least 2026-09-28 (21 trading days before Oct 29) to become eligible. For full lookback coverage (90 bars), data back to ~2026-06-18 is needed.

**Recovery impact:** Only `decision_label='wait'` signals would be recovered (see PART G). No actionable signal coverage would change.

---

## PART G — Selection Bias Assessment

### Decision label distribution by classification

| decision_label | RESEARCH_CREATED | INSUFFICIENT_HISTORY | Coverage |
|---|---:|---:|---|
| wait | 389 | **729** | 34.8% (many excluded) |
| sell | 454 | 0 | **100%** ✅ |
| reduce | 81 | 0 | **100%** ✅ |
| buy | 52 | 0 | **100%** ✅ |
| wait_pullback | 30 | 0 | **100%** ✅ |
| strong_buy | 15 | 0 | **100%** ✅ |
| **Total** | **1,021** | **729** | 58.3% overall |

### Bias verdict

**ZERO selection bias against actionable signals.**

All 729 excluded signals have `decision_label='wait'`. Every `buy` (52), `strong_buy` (15), and `wait_pullback` (30) signal in the ForwardSignal universe is included in V2 research. The exclusion is systematic (affects only one label) and operates in the **safe direction**: 'wait' signals indicate no immediate action, so their absence from V2 research does not create a research gap for trading decisions.

The 172 excluded ETFs are part of the screener universe but their V2 entry timing is irrelevant for the current V2 research question (which focuses on actionable BUY/STRONG BUY setups).

---

## PART H — Backfill Proposal

### Backfill Approval D assessment (read-only proposal)

| Item | Detail |
|---|---|
| Existing pipeline | `scripts/backfill_daily_prices.py` (dry-run default, `--execute` flag) |
| Free API limitation | TWSE/TPEx public APIs return only current-day data; historical dates require paid source |
| Required coverage | 172 ETFs × ≥21 bars before Oct 29, 2026 (data back to ~2026-08-27 minimum) |
| Full lookback coverage | 90 bars before Oct 29 → data back to ~2026-06-18 |
| Paid sources known | FinMind, TEJ (referenced in `scripts/backfill_daily_prices.py` comments) |

### Recommendation

**Approval D: NOT URGENT — optional enhancement.**

Rationale:
1. All 729 excluded signals have `decision_label='wait'` — zero actionable signals affected
2. V2 research already covers 100% of `buy`, `strong_buy`, and `wait_pullback` signals
3. Recovery would add 'wait'-only signals with no impact on the entry timing research question
4. Paid data source procurement is out of scope for the current V2 research track

If pursued in a future session: execute with dry-run verification, QG PASS required before writing.

---

## PART I — Approval C Readiness

**Service:** `ShadowRecalculationService.recalculate()` in `src/research/shadow_recalculation_service.py`

### Technical readiness

| Check | Result |
|---|---|
| T-1: _load_history logic identical to fixed version (DESC+LIMIT+reverse) | ✅ PASS |
| T-2: Writes only to v2_shadow_signals (research_version='v2_research_v2') | ✅ PASS |
| T-3: Reads from v2_research_v1 rows + DailyPrice (read-only production intent) | ✅ PASS |
| T-4: Per-row commit with IntegrityError rollback (idempotent) | ✅ PASS |
| T-5: Separate research_session and prod_session architecture | ✅ PASS |
| T-6: dry_run=False for execution; dry_run=True available for safety preview | ✅ PASS |
| T-7: 3-col UniqueConstraint (trade_date, stock_id, research_version) prevents duplicates | ✅ PASS |
| T-8: label_changes tracking in RecalcReport for research comparison | ✅ PASS |

### Data readiness

| Check | Result |
|---|---|
| D-1: 1,021 v2_research_v1 rows available as source | ✅ PASS |
| D-2: All 1,021 rows have data_bars=90 (fixed history query confirmed) | ✅ PASS |
| D-3: entry_price matches DailyPrice.close for trade_date (5/5 spot check) | ✅ PASS |
| D-4: Zero existing v2_research_v2 rows (clean state) | ✅ PASS |
| D-5: NULL volume in DailyPrice (17,364 rows) — coerced to 0 by analyzer | ⚠️ ADVISORY — 0 NULL volume in research window, no impact on Approval C |

### Research readiness

| Check | Result |
|---|---|
| R-1: v2_research_v1 created with FIXED _load_history (commit fadafdb predates Approval B) | ✅ CONFIRMED |
| R-2: v2_research_v1 entry_labels based on 2026 market data (entry_price verified) | ✅ CONFIRMED |
| R-3: v2_research_v2 expected to produce identical labels to v2_research_v1 | ⚠️ ADVISORY |

**R-3 advisory:** Because both v2_research_v1 (created by Approval B) and v2_research_v2 (to be created by Approval C) use the same corrected `_load_history` logic (DESC+LIMIT+reverse) and the same DailyPrice data, the expected outcome is ~1,021 v2_research_v2 rows with ~0 label changes. Approval C would serve as a **validation step** (confirms v1 correctness) rather than a label correction step. This is not a blocker — it is the correct research outcome.

### Production safety

| Check | Result |
|---|---|
| P-1: No production table writes (ForwardSignal, ActualPosition, HybridForwardDecision) | ✅ PASS |
| P-2: ForwardSignals fingerprint unchanged | ✅ GUARANTEED |
| P-3: Hybrid Forward Shadow unchanged | ✅ GUARANTEED |
| P-4: DailyPrice read-only via prod_session | ✅ PASS |

### Approval C expected execution parameters

```python
svc = ShadowRecalculationService()
report = svc.recalculate(
    research_session=<neon_research_session>,
    prod_session=<neon_prod_session>,
    from_date=date(2026, 10, 29),
    to_date=date(2026, 11, 4),
    dry_run=True,  # preview first
)
# Expected: processed=1021, skipped=0, errors=0, label_changes≈0
```

---

## PART J — Test Coverage

| Suite | Tests | Status |
|---|---|---|
| test_shadow_recalculation.py (SR01–SR10) | 10 | ✅ 10/10 PASS |
| test_v2_shadow_migration.py (VM01–VM32) | 37 | ✅ All PASS (from prior sessions) |

**SR01:** writes v2_research_v2 rows correctly  
**SR02:** idempotent (re-run skips existing rows)  
**SR03:** label changes recorded in RecalcReport  
**SR04:** insufficient history counted as error, not crash  
**SR05:** dry_run produces no DB writes  
**SR06:** date range filter respected  
**SR07:** summary() contains all key fields  
**SR08:** existing v2 rows are skipped  
**SR09:** no label_change recorded when labels match  
**SR10:** missing_data list populated for OHLC gaps  

No code changes were made in this session. No new tests required.

---

## Approval C Verdict

### **READY_FOR_APPROVAL_C**

| Criterion | Status |
|---|---|
| Technical safety | ✅ ALL PASS |
| Data integrity | ✅ 1,021 v2_research_v1 rows ready, clean |
| Selection bias | ✅ ZERO against actionable signals |
| 21-bar rule | ✅ VALIDATED |
| Production isolation | ✅ No production writes possible |
| Test coverage | ✅ 10/10 SR tests PASS |

**Advisory notes (not blockers):**
1. Expected ~0 label changes — Approval C validates v1 correctness, not corrects it
2. 729 excluded signals (all 'wait') may be recovered via paid backfill (Approval D) in a future session, but this is not required for Approval C
3. Recommend dry_run=True first to generate label_changes report before final execution

**Approval C is authorized to proceed in a future session upon explicit user authorization.**

---

## Appendix: Data Quality Flag Log

| Flag | Date | Stocks | Type | Impact on Research |
|---|---|---|---|---|
| NULL volume in backfill seed rows | 2026-09-11, 10-08, 10-09 | ~6,500 | Backfill pipeline gap | NONE — not in research window |
| Oct 12–13 duplicate close (00713) | 2026-10-12, 10-13 | 00713 | Possible duplicate fetch | NONE — 00713 in INSUFFICIENT_HISTORY |
| 172 ETF history gap (Sep 12 – Oct 7) | 2026-09-12 ~ 2026-10-07 | 172 | Pipeline gap | 729 INSUFFICIENT_HISTORY signals (all 'wait') |

