# Session 37 Final Verdict

**Date:** 2026-11-08  
**Session:** 37 — Market Data Coverage & Universe Integrity Redesign  
**Mode:** Research-only / Read-only Production Data / No Cron Changes  
**Version:** session37_v1

---

## 1. Executive Summary

Session 37 established the first systematic audit of the Taiwan stock universe, market data coverage, and signal generation integrity. Five major previously unknown issues were identified:

1. **ForwardSignals include ETFs** — 8.6% of v8.0 signals are for ETFs, not common stocks
2. **Train-test universe mismatch** — Backtest used ~720 stocks/day; ForwardSignals dates had only 394 of those same stocks (48%), plus ETFs and non-master stocks
3. **TPEx entirely absent** — stocks master has 826 TWSE stocks only; zero TPEx stocks tracked
4. **Survivorship bias probable** — 826 stocks ALL listed, 0 delisted in 28 months; delistings were likely never loaded
5. **ForwardSignals count reconciled** — 2605 (all) vs 2236 (v8.0 only) explained by model_version filter; no data loss

---

## 2. Verdict Table

| Domain | Verdict | Key Finding |
|---|---|---|
| Universe | `UNIVERSE_PARTIAL` | 826 TWSE only; 0 TPEx; ETFs present in signals |
| Stock Master | `STOCK_MASTER_PARTIAL` | No TPEx, no delisted, no FK constraint |
| DailyPrice Coverage | `COVERAGE_PARTIAL` | 25/572 dates full-market; Oct 2026 sparse (48% master) |
| ForwardSignals Count | `COUNT_RECONCILED` | 2605=all; 2236=v8.0 only; 369=v6.0 invalid |
| Historical Backtest | `BACKTEST_CONDITIONAL` | Internally consistent; multiple biases vs absolute performance |
| V3 Research | `V3_RESEARCH_BLOCKED` | Same blockers as Session 36 + new universe issues |
| Regression | `REGRESSION_PASS` | No code changes; 2042 passed |
| V3 Activation | `ACTIVATION_BLOCKED` | Unchanged |

---

## 3. PART A — Baseline

| Item | Value |
|---|---|
| Git HEAD | ad6fbb8 |
| Branch | main |
| Working tree | 2 modified files, ~25 untracked docs/scripts |
| Crontab hash | e8f7fd5ca4ddeb551afcba88c0e1c7a2 (UNCHANGED) |
| Audit timestamp | 2026-11-08T04:28:34 CST |
| BT_HASH | be43e8ca977d9fdd (UNCHANGED) |
| CP_HASH | 1feb7a6b294a063d (UNCHANGED) |
| ForwardSignals (all) | 2605 |
| ForwardSignals (v8.0 valid) | 2236 |
| Hybrid decisions | 21 |
| DailyPrice rows | 534,770 |
| stocks count | 826 (all TWSE) |

**2236 vs 2605 reconciliation:** `COUNT_RECONCILED` — model_version filter difference only. See `forward_signals_reconciliation_session37.md`.

---

## 4. New Findings (Not Known in Prior Sessions)

| Finding | Severity | Impact |
|---|---|---|
| ForwardSignals includes ETFs (192/2236 = 8.6%) | HIGH | Signal universe contamination |
| ForwardSignals uses non-master 4-digit stocks (787/2236 = 35.2%) | HIGH | Unknown security type |
| Only 394 of 826 master stocks present on ForwardSignals dates | HIGH | 52% of master excluded from signal generation |
| 1,275 four-digit orphan stocks in daily_prices not in stocks master | HIGH | TPEx common stocks likely excluded from entire platform |
| 14,319 total stock_ids in daily_prices without master records | MEDIUM | No metadata for most securities |
| ETF contamination exists in both v6.0 AND v8.0 signals | HIGH | Methodology issue predates current research |
| Historical backtest era (Jul 2024–May 2026): clean TWSE-only | POSITIVE | Good internal consistency for relative comparisons |
| Survivorship bias: 0 delisted stocks in 28-month master | HIGH | Inflates historical performance estimates |

---

## 5. What The +3.66ppt In-Sample Advantage Means Now

The V3 vs V2 comparison (+3.66ppt, Session 27) was computed on the same in-sample signal universe. Given the new findings:

| Assessment dimension | Status |
|---|---|
| Relative comparison validity (V3 vs V2 on same data) | CONDITIONAL (internally consistent) |
| Absolute return estimate validity | LOW (survivorship + ETF contamination) |
| Market timing attribution | HIGH (market avoidance confirmed as primary driver) |
| Stock selection attribution | UNIDENTIFIABLE without decomposition analysis |
| Entry timing attribution | UNIDENTIFIABLE without matched-pair analysis |

**Conclusion:** The +3.66ppt advantage exists in-sample on this dataset, but cannot be attributed to genuine stock selection ability. The decomposition plan in `v3_performance_decomposition_plan_session37.md` outlines how to isolate the components.

---

## 6. Architecture Proposal Summary (Design Only)

Proposed new modules (not implemented):

| Module | Purpose | Blockers |
|---|---|---|
| `UniverseRegistry` | TWSE+TPEx common stock master with security_type | Schema migration + ETL |
| `SecurityTypeClassifier` | Auto-classify stock_ids as common/ETF/etc. | Design ready, no code yet |
| `StockMasterValidator` | Validate no ETF in signals | Requires security_type column |
| `MarketCoverageAuditor` | Daily coverage with authoritative denominator | Requires UniverseRegistry |
| `ForwardSignalReconciler` | Log source_price_date, universe at computation | Requires production code change |
| `BacktestEligibilityGate` | Gate: reject sparse dates / ETF-contaminated signals | Research code change |
| `ExposureMatchedComparison` | V3 vs V2 stock selection decomposition | Requires clean data first |

---

## 7. What Changed in Session 37

| Item | Before | After |
|---|---|---|
| Code changes | — | None |
| New docs | 0 | 7 (this session) |
| ForwardSignals understanding | "2236 valid" | 2236 v8.0 (1257 master + 787 orphan 4-digit + 192 ETF) |
| Universe understanding | "826 TWSE stocks" | 826 TWSE master + 0 TPEx + ETFs contaminating signals |
| Backtest validity | "SPARSE coverage concern" | CONDITIONAL — consistent in backtest era, mismatched in signal era |
| ETF contamination | Unknown | CONFIRMED — 8.6% of v8.0 signals |
| Count reconciliation | Unresolved | RESOLVED: 2605 total = 2236 v8.0 + 369 v6.0 |

---

## 8. Unresolved Questions (Requiring Future Work)

| Question | Priority | Work Required |
|---|---|---|
| Why are only 394 of 826 master stocks present on Oct 12–28? | HIGH | Investigate data loading pipeline for Oct 2026 |
| Are the 1275 orphan 4-digit stocks actually TPEx? | HIGH | Load TPEx master and cross-reference |
| Does the signal engine filter by stocks master? | HIGH | Code audit of signal generation pipeline |
| Which stocks were delisted 2024–2026? | HIGH | TWSE/TPEx historical data |
| Does corporate action distortion affect fwd_return calculations? | MEDIUM | Obtain adjusted price data |
| What data source was used for Oct 12–28 daily_prices? | MEDIUM | Investigate ETL logs |

---

## 9. Document Index (Session 37)

| File | Purpose |
|---|---|
| `docs/universe_definition_session37.md` | TRADEABLE_COMMON_STOCK_UNIVERSE definition |
| `docs/stock_master_integrity_session37.md` | stocks/daily_prices FK, orphan analysis, ETF contamination |
| `docs/dailyprice_coverage_matrix_session37.md` | Coverage matrix by date, type, verdict |
| `docs/forward_signals_reconciliation_session37.md` | 2605 vs 2236 — COUNT_RECONCILED |
| `docs/historical_backtest_bias_audit_session37.md` | 10 biases analyzed, severity, remediation |
| `docs/v3_performance_decomposition_plan_session37.md` | Market timing / stock selection / entry timing design |
| `docs/session37_final_verdict.md` | This document |
