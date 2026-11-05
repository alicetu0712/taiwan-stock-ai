# V2 Research Difference Audit & Forward Performance Readiness

**Date:** 2026-11-06  
**Git HEAD:** 1c42cb3 (no code changes in Session 21; new tests + dashboard text fix only)  
**Session:** 21  
**Scope:** Read-only audit of V1/V2 research pipeline + forward maturity readiness.  
**New Files:** `tests/test_v2_research_audit.py` (30 tests), `dashboard/_pages/entry_timing_research.py` (description fix)

---

## 1. Executive Summary

### Why are there 0 Label Changes and 0 Entry Price Changes?

**Root cause: `V1_ALREADY_CONTAINS_V2_FIX`**

The `_load_history` DESC+LIMIT fix (commit `fadafdb`) was merged into `entry_timing_research_service.py` BEFORE Approval B ran (commit `1c42cb3`). This means:

- `v2_research_v1` was computed with the **corrected** algorithm (DESC+LIMIT+reverse).
- `v2_research_v2` was recomputed by `ShadowRecalculationService` using the **same** corrected algorithm.
- Both versions call the **same** `EntryTimingAnalyzer.analyze()` with the **same** DailyPrice data at the **same** as-of date.

Same code + same data = identical output. Zero label changes, zero entry price changes — this is the **expected and correct** result.

### Is there a Version Routing Bug?

**NO.** The routing is correct:
- `entry_timing_research_service.py` correctly creates `research_version='v2_research_v1'` rows.
- `shadow_recalculation_service.py` correctly reads `research_version='v2_research_v1'` and writes `research_version='v2_research_v2'` rows.
- The V2 row `entry_label` comes from `result.entry_label` (fresh analyzer output), not `v1.entry_label`.

### Is there Look-ahead Bias?

**NO.** `prior_20d_high = float(np.max(high[-21:-1]))` explicitly excludes today's bar (index -1), and `entry_price = close[-1]` is today's close (signal-day price, not next-day price). The `_load_history` uses `date <= as_of` (not `< as_of + 1`), which correctly includes the signal date and excludes future data.

### is_legacy Documentation Inconsistency

The `V2ShadowSignal` model docstring states `'v2_research_v1' — pre-DESC fix (may have stale lookback data, is_legacy=True)`. **This is incorrect for the actual data.** Both v2_research_v1 and v2_research_v2 have `is_legacy=False` because the fix was already applied before Approval B. This is a **stale docstring**, not a data error. Dashboard description updated to reflect actual state.

---

## 2. Pipeline Mapping (PART B)

| Component | File / Function | Input | Output | Research Version |
|---|---|---|---|---|
| Formal Signal | `src/database.py::ForwardSignal` | PriceTrendAnalyzer v8.0 | `decision_label`, `pt_score`, `setup_type` | N/A (production) |
| V1 Research | `src/research/entry_timing_research_service.py::EntryTimingResearchService.run_for_date()` | ForwardSignal + DailyPrice (90 bars, DESC+LIMIT fix) | `V2ShadowSignal` row | `v2_research_v1` |
| V2 Recalculation | `src/research/shadow_recalculation_service.py::ShadowRecalculationService.recalculate()` | V1 rows + DailyPrice (90 bars, same DESC+LIMIT fix) | `V2ShadowSignal` row | `v2_research_v2` |
| Persistence | `src/research/models.py::V2ShadowSignal` | ORM model | Neon `v2_shadow_signals` table | Both v1 and v2 |
| Comparison | `ShadowRecalculationService.recalculate()` label_changes | V1.entry_label vs result.entry_label | `LabelChange` list in `RecalcReport` | V1→V2 diff |
| Dashboard | `dashboard/_pages/entry_timing_research.py::_render_signal_list()` | `v2_shadow_signals` filtered by `research_version` | Streamlit table, stats, backtest | v2_research_v2 (default) |

**Key findings:**
- V1 and V2 call the **same** `EntryTimingAnalyzer.analyze()` (confirmed by source inspection, test RA-01).
- Both use the **same** `_load_history` semantics: DESC+LIMIT(90)+reversed (confirmed by source inspection, test RA-02).
- ShadowRecalculationService does NOT copy V1 fields — all fields come from `result.*` (confirmed test RA-05).

---

## 3. Field-level Difference Matrix (PART C)

**Pair key:** `(trade_date, stock_id)` | **Tolerance:** 0.01 absolute | **Pairs:** 1,021

| Field | Compared Pairs | Different | Same | Verdict |
|---|---:|---:|---:|---|
| entry_label | 1,021 | **0** | 1,021 | ✅ IDENTICAL |
| entry_price | 1,021 | **0** | 1,021 | ✅ IDENTICAL |
| stop_price | 1,021 | **0** | 1,021 | ✅ IDENTICAL |
| target_price | 1,021 | **0** | 1,021 | ✅ IDENTICAL |
| rr_ratio | 1,021 | **0** | 1,021 | ✅ IDENTICAL |
| ma20_gap_pct | 1,021 | **0** | 1,021 | ✅ IDENTICAL |
| dist_to_resistance_pct | 1,021 | **0** | 1,021 | ✅ IDENTICAL |
| vol_ratio | 1,021 | **0** | 1,021 | ✅ IDENTICAL |
| prior_20d_high | 1,021 | **0** | 1,021 | ✅ IDENTICAL |
| data_bars | 1,021 | **0** | 1,021 | ✅ IDENTICAL (all 90) |
| is_legacy | 1,021 | **0** | 1,021 | ✅ IDENTICAL (all False) |
| v1_decision_label (copied) | 1,021 | 0 | 1,021 | ✅ IDENTICAL (denormalized copy) |

**Classification of differences:**

1. Decision Difference: 0 cases
2. Entry Timing Difference: 0 cases
3. Entry Price Difference: 0 cases
4. Risk Management Difference: 0 cases
5. Metadata-only Difference: `research_version` differs (by design: v1 vs v2), `created_at` differs (by design: different execution timestamps)

---

## 4. V2 Logic Execution Proof (PART D)

### Call Graph

```
ShadowRecalculationService.recalculate()
  ├─ Read: research_session.query(V2ShadowSignal, research_version='v2_research_v1')
  ├─ For each v1 row:
  │   ├─ Check: existing v2_research_v2 row? → skip if yes
  │   ├─ CALL: self._load_history(prod_session, v1.stock_id, v1.trade_date)
  │   │         └─ DailyPrice DESC LIMIT 90 reversed → pd.DataFrame (90 bars)
  │   ├─ CALL: analyzer.analyze(v1.stock_id, history) → EntryTimingResult
  │   └─ Write: V2ShadowSignal(entry_label=result.entry_label, entry_price=result.entry_price, ...)
  └─ Return: RecalcReport(label_changes=[LabelChange] where result.entry_label != v1.entry_label)
```

### Core Condition Analysis

| Question | Answer |
|---|---|
| Does V2 call `analyzer.analyze()`? | YES (confirmed test RA-01, RA-05) |
| Does V2 copy V1 field values directly? | NO — V2 `entry_label = result.entry_label`, not `v1.entry_label` |
| Does V2 use the latest as-of-date data? | YES — `DailyPrice.date <= v1.trade_date` |
| Is there look-ahead in prior_20d_high? | NO — `high[-21:-1]` excludes today (test RA-06) |
| Is there a silent fallback to V1? | NO — if `len(history) < 21`, it goes to `errors`, not to V1 copy |
| Are there ignored V2 parameters? | NO — both use same `MIN_BARS=21`, same `MA20_PULLBACK_*`, same `STOP_BUFFER=0.03` |
| Does V2 logic execution produce expected output? | YES — when different data provided, different labels produced (test RA-09b) |

### Why V2 == V1 numerically

The service comment in `entry_timing_research_service._load_history`:
> "The previous ASC+LIMIT implementation returned the OLDEST lookback rows (e.g. data from years ago instead of recent 90 bars) — now fixed."

This fix was committed in `fadafdb`, which predates Approval B's commit `1c42cb3`. Therefore:
- V1 was computed with the fix already in place
- V2 recalculation uses the same fix
- Both read the same 90-bar window from the same DailyPrice table
- `EntryTimingAnalyzer` is deterministic (test RA-03)

**Result: identical outputs.**

---

## 5. Research Identity Verdict (PART E)

### VERDICT: `V1_ALREADY_CONTAINS_V2_FIX`

**Evidence:**
1. Source inspection: both `_load_history` implementations use DESC+LIMIT(90)+reversed (test RA-02 ✅)
2. Same `EntryTimingAnalyzer.analyze()` imported from same module (test RA-01 ✅)
3. Neon field comparison: 0 differences across all 1,021 pairs, all fields (live query ✅)
4. `is_legacy=False` for all v2_research_v1 rows (confirms fix was applied at V1 creation time) (test RA-11 ✅)
5. RecalcReport confirms: `processed=1021, skipped=0, errors=0, label_changes=0`

**Implications:**
- **DO NOT** claim V2 improves entry timing over V1.
- **DO NOT** compare V1 vs V2 performance — the return series are identical.
- V2 serves as a formally version-controlled research baseline for future algorithm iterations.
- Future `v2_research_v3` would require a new entry timing algorithm to produce different results.

---

## 6. Forward Performance Readiness (PART F)

**Data source:** Neon DailyPrice (0050 proxy, Taiwan trading calendar)  
**Last available 0050 date:** 2026-11-05  
**Today:** 2026-11-06

### Maturity Table

| Signal Date | Signals (V2) | 5D Mature | 10D Mature | 20D Mature | 5D Date | 10D Date (est.) | 20D Date (est.) |
|---|---:|---|---|---|---|---|---|
| 2026-10-29 | 191 | ✅ YES (Nov 5) | ❌ NO | ❌ NO | 2026-11-05 | ~2026-11-12 | ~2026-11-26 |
| 2026-10-30 | 210 | ❌ NO | ❌ NO | ❌ NO | ~2026-11-06 | ~2026-11-13 | ~2026-11-27 |
| 2026-11-02 | 187 | ❌ NO | ❌ NO | ❌ NO | ~2026-11-09 | ~2026-11-16 | ~2026-12-02 |
| 2026-11-03 | 213 | ❌ NO | ❌ NO | ❌ NO | ~2026-11-10 | ~2026-11-17 | ~2026-12-03 |
| 2026-11-04 | 220 | ❌ NO | ❌ NO | ❌ NO | ~2026-11-11 | ~2026-11-18 | ~2026-12-04 |

**Notes:**
- 5D dates computed exactly from Neon 0050 trading calendar. 10D/20D estimated assuming standard Mon-Fri Taiwan trading (no known November holidays). Actual dates require Neon DailyPrice to accumulate beyond Nov 5.
- "5D MATURE" means the 5th trading day after the signal date has arrived. 2026-10-29's 5D = 2026-11-05 ≤ today (2026-11-06) → MATURE.
- Entry Price definition: signal-day close price (`entry_price = close[-1]`). No separate open column in DailyPrice; next-day open would require `execution_price` from ForwardSignal table (NEXT_OPEN architecture).
- Exit Price definition (for future validation): 5D/10D/20D close after signal date, using DailyPrice.
- 0050 Benchmark: use 0050 DailyPrice return over same window. Adjusted prices not separately tracked; Corporate Action / Split data not independently managed in current schema.
- Survivorship bias: possible — stocks with INSUFFICIENT_HISTORY (729 excluded signals) are all ETF stocks; non-survivorship stocks not specifically tracked.

### Forward Performance Status

**PERFORMANCE_NOT_YET_VALIDATED**

Currently available mature data:
- 5D only for Oct 29 signals (191 V2 rows)
- 191 paired rows, all `NO_VALID_SETUP`/`ENTRY_READY`/etc.

**Minimum recommended sample for analysis:** 20D matured signals from at least 3 signal dates = ~600 pairs. Earliest: ~2026-11-26.

---

## 7. As-of-date & Prospective Classification (PART G)

### Classification of Approval B/C Research Data

| Row Set | Signal Dates | Research Created | Classification | Reason |
|---|---|---|---|---|
| v2_research_v1 | 2026-10-29 ~ 2026-11-04 | 2026-11-05 (Approval B) | **RETROSPECTIVE_RESEARCH** | Created 1–7 days after signal dates |
| v2_research_v2 | 2026-10-29 ~ 2026-11-04 | 2026-11-05 (Approval C) | **RETROSPECTIVE_RESEARCH** | Created 1–7 days after signal dates |

**Key rule:** PROSPECTIVE = signal captured on the same day it is generated and stored before the signal date closes. Approval B/C computed historical research on 2026-11-05 for signals from 2026-10-29 to 2026-11-04 — these are RETROSPECTIVE by definition.

**DO NOT** reclassify these rows as PROSPECTIVE even after forward returns become available. RETROSPECTIVE_RESEARCH with mature returns = historical backtest data, not prospective OOS validation.

### Decision Capture Timeline (Approval B/C)

```
Signal dates:  Oct 29  Oct 30  Nov 2  Nov 3  Nov 4
                                                    ↓
Approval B/C computed on:                     2026-11-05
                                              (1–7 trading days later)
                                              = RETROSPECTIVE_RESEARCH
```

---

## 8. Statistical Validation Plan (PART H)

### Core Metrics (for future use when data matures)

| Metric | Applies To | Notes |
|---|---|---|
| N (sample) | V1 / V2 (paired) | Minimum n=20 for preliminary; n=50 for publication |
| Mean Return | V1 / V2 | Use OHLC simulated net return (after 0.585% round-trip fee) |
| Median Return | V1 / V2 | Robust to outliers |
| Standard Deviation | V1 / V2 | For CI computation |
| Win Rate | V1 / V2 | Wins = net return > 0 |
| Mean Alpha vs 0050 | V1 / V2 | 0050 same-window return as benchmark |
| Paired Mean Difference | V2 − V1 | 0.0 expected until algorithm differs |
| 95% Bootstrap CI | Paired delta | 1,000 bootstrap samples, seed=42 |
| p-value | Paired t-test | One-tailed vs 0 |
| MAE / MFE | V1 / V2 | Only if intraday OHLC available |

### V1/V2 Comparison Rules

1. Only use 20D-mature signals (use trading calendar, not calendar days).
2. Never assign 0% return to immature signals.
3. V1 and V2 must be paired on the same `(trade_date, stock_id)`.
4. Missing OHLCV: exclude and document count.
5. 28-day dedup per stock to prevent correlated samples.
6. Cluster standard errors by date if same-day signals dominate.
7. n < 20: report as INSUFFICIENT_SAMPLE, no statistical claim.
8. Alpha = signal return − benchmark (0050) return over same window.
9. Clearly distinguish Research Evidence from Trading Recommendation.

### CRITICAL CONSTRAINT

**`NO_MEANINGFUL_STRATEGY_DIFFERENCE`** (test RA-12 ✅)

V1 and V2 are computed with identical logic from identical data. Their return series are identical. Paired delta = 0.0 for all pairs. Standard deviation = 0.0. No statistical test can produce a meaningful p-value or confidence interval from a zero-variance distribution.

**The only meaningful V1/V2 comparison will occur when a new algorithm version (v2_research_v3+) is introduced.** Until then, all V1/V2 comparisons produce trivially equal results.

---

## 9. Validation Runner Readiness (PART I)

### Existing Infrastructure (use, do not rebuild)

| Component | File | Status |
|---|---|---|
| Backtest engine (FOS) | `src/research/backtest_full.py::run_full_backtest()` | ✅ EXISTS |
| OHLC simulation | `src/research/execution_simulator.py` | ✅ EXISTS |
| Trading calendar | `src/research/hybrid_trading_calendar.py::TradingCalendar` | ✅ EXISTS |
| Dedup logic | `src/research/backtest_full.py::_dedup_signals()` | ✅ EXISTS |
| Bootstrap CI | `src/research/backtest_full.py::_bootstrap_ci()` | ✅ EXISTS |
| Dashboard runner | `dashboard/_pages/entry_timing_research.py::_render_full_backtest()` | ✅ EXISTS |
| Maturity gate | `TradingCalendar.add_trading_days()` | ✅ EXISTS |

### Forward Performance Runner: NOT REQUIRED (yet)

`run_full_backtest()` already supports:
- Date range filtering
- 5D/10D/20D via `expiry_days` parameter
- 0050 benchmark via `v1_fwd_stats` (Comparison A)
- V1/V2 pairing via shared `v1_decision_label` field
- Missing data reporting via `missing_ohlcv_count`
- Maturity gate via `ohlcv_cutoff`
- CSV/Markdown: not natively, but results dict is serializable
- Read-only by default (no Neon writes)

**Gap: 20D window requires** `ohlcv_cutoff = to_date + timedelta(days=35)` already in code, but Nov 5 DailyPrice is the last row. When DailyPrice extends to ~Nov 26, the runner will naturally begin computing 20D returns for Oct 29 signals.

**No new runner component required for Session 21.**

---

## 10. Dashboard Status (PART J)

### Changes Made

| Item | Before | After |
|---|---|---|
| v2_research_v1 info text | "pre-DESC fix，is_legacy=True" | "初始研究基準，is_legacy=False，DESC+LIMIT fix 已包含" |
| v2_research_v2 info text | "post-DESC fix，is_legacy=False" | "重算版本，與 v2_research_v1 使用相同邏輯" |
| Equivalence warning | ❌ MISSING | ✅ ADDED: "V1/V2 CURRENTLY EQUIVALENT — NO PERFORMANCE ADVANTAGE ESTABLISHED" |

### V1/V2 Research Version Panel After Fix

The dashboard now shows:
- For v2_research_v1: correct description (not claiming pre-DESC-fix status)
- For v2_research_v2: acknowledges same logic as v2_research_v1
- Prominent `st.warning()` block: "V1/V2 CURRENTLY EQUIVALENT — NO PERFORMANCE ADVANTAGE ESTABLISHED" with 0 label changes, 0 price changes, forward return maturity date

### Remaining Dashboard Items

| Item | Status |
|---|---|
| V2 signal list (1,021 rows) | ✅ Displays correctly |
| Label distribution | ✅ Correct |
| Backtest (FOS) | ✅ Run button available; will show results when data matures |
| Effectiveness analysis | ✅ Available (pre-computed JSON) |
| Hybrid forward shadow | ✅ Shows PROSPECTIVE tracking |
| Known limitations | ✅ 8 items listed |
| Maturity status per signal date | ❌ NOT SHOWN (enhancement for future session) |

---

## 11. Integrity Verification (PART K / PART L)

| Item | Value |
|---|---|
| Git HEAD | 1c42cb3 (unchanged) |
| New files | `tests/test_v2_research_audit.py`, `docs/v2_research_difference_forward_performance_readiness.md` |
| Modified files | `dashboard/_pages/entry_timing_research.py` (description text fix only) |
| New tests | 30 (RA-01 to RA-12 × class methods) |
| Tests passed | **30/30** |
| Full regression | 1,734 passed + 2 pre-existing failures (PF13, PF20: OHLC gate BLOCKED on Nov 6 due to DailyPrice not yet updated for today) |
| Ruff | ✅ All checks passed |
| Neon writes | **0** (read-only session, no Neon writes in Session 21) |
| ForwardSignals fingerprint | `d38102c842b30f54` (unchanged, 2,102 rows) |
| ForwardSignals Oct29-Nov4 | 1,750 rows (unchanged) |
| V1 research count | 1,021 rows (unchanged) |
| V2 research count | 1,021 rows (unchanged) |
| Hybrid Decisions fingerprint | `88313e607d66adf7` (unchanged) |

---

## Final Answers to Session 21 Questions

| # | Question | Answer |
|---|---|---|
| 1 | V1 與 V2 是否真正使用不同演算法？ | **NO** — 相同 `EntryTimingAnalyzer.analyze()` + 相同 `_load_history` |
| 2 | 為什麼 1,021 筆結果完全一致？ | `V1_ALREADY_CONTAINS_V2_FIX` — fadafdb fix 在 Approval B 之前已包含 |
| 3 | V2 是否真正執行了預期的計算？ | YES — 呼叫 `analyzer.analyze()`，非 V1 複製（test RA-05 ✅） |
| 4 | 是否存在 Version Routing Bug？ | **NO** — routing 正確；V1→V2 分開寫入，`entry_label=result.entry_label` |
| 5 | V2 是否有任何可驗證的進場優勢？ | **NO** — `NO_MEANINGFUL_STRATEGY_DIFFERENCE`；0 label/price 差異 |
| 6 | 目前 5D、10D、20D 哪些已成熟？ | 只有 Oct 29 的 5D（Nov 5）已成熟；其餘均未成熟 |
| 7 | 各日期 20D Maturity Date 是哪一天？ | Oct29≈Nov26, Oct30≈Nov27, Nov2≈Dec2, Nov3≈Dec3, Nov4≈Dec4 |
| 8 | 目前資料屬於 Historical 還是 Prospective？ | **RETROSPECTIVE_RESEARCH** — Approval B/C 在訊號日後 1–7 天計算 |
| 9 | 是否已具備 Forward Performance Runner？ | YES — `backtest_full.py::run_full_backtest()` 已存在且功能完整 |
| 10 | 是否可以進行有意義的 V1/V2 績效比較？ | **NO** — 相同策略、相同返回序列；只有 v2_research_v3+ 引入新邏輯後才有意義 |
| 11 | Dashboard 是否正確揭露研究限制？ | NOW YES — 新增 equivalence warning + 修正 is_legacy 描述 |
| 12 | 下一個研究里程碑是什麼？ | 2026-11-26：Oct 29 訊號 20D 成熟，可開始 `run_full_backtest()` 歷史績效驗證 |
