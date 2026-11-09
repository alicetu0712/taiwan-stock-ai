# Session 47 Final Verdict — Historical Data Gap Closure & Strict Cluster Eligibility

**Date:** 2026-11-09  
**Session:** S47 — PARTS A through M  
**Test Count:** 2762 passed, 1 skipped (baseline 2661 + 101 new)

---

## Final Verdict Enums

| Dimension | Verdict |
|---|---|
| Data Gap | DATA_GAP_CONFIRMED |
| Research Recovery | RECOVERY_BLOCKED |
| Strict Eligibility | STRICT_ELIGIBILITY_UNCHANGED |
| Frozen Baseline | BASELINE_REPRODUCED |
| 20D Readiness | 20D_NOT_READY |
| Guardrails | GUARDRAILS_FAIL (G03/G04 unchanged) |
| Ranking | RANKING_NOT_SUPPORTED |
| Regression | REGRESSION_PASS |
| Activation | ACTIVATION_BLOCKED |

---

## 20 Final Questions

**Q1: 11/02 是否為正式交易日？**  
A1: 是。TaiwanTradingCalendar 確認 2026-11-02 (Mon) 為正式交易日。

**Q2: 11/03 是否為正式交易日？**  
A2: 是。2026-11-03 (Tue) 為正式交易日。

**Q3: 這兩天實際缺少哪些股票或價格？**  
A3: Nov 02/03 在 SQLite 各只有 1 股（0050 proxy）。全市場 ~655 檔股票的價格完全缺失。TSMC (2330) 在這兩天均不在 DB 中，因此 `_count_exit_days` 代理計數無法累積。

**Q4: 缺口是否只影響這兩天？**  
A4: **否**。S47 新發現：缺口遠超 Nov 02/03。完整清單：Oct 08、Oct 15、Oct 19、Oct 20、Oct 27、Oct 29、Oct 30、Nov 02、Nov 03（皆為 PARTIAL_COVERAGE，1 stock），Nov 06、Nov 09（DATE_MISSING，0 stocks）。共 11 個有問題的交易日。

**Q5: 資料缺失的真正原因是什麼？**  
A5: 兩種根本原因：
- **PIPELINE_SELECTIVE**（Oct 15/19/20/27/29）：管線只在 Forward Signal 生成日（Fill Dates）執行，中間交易日從未抓取。這是既有結構性缺口。
- **SCHEDULER_NOT_TRIGGERED**（Oct 30/Nov 02/03）：Cron 自 Nov 02 前即未運作；第一筆 cron log 為 Nov 09T08:00:17Z。

**Q6: 哪些歷史價格可在隔離環境安全恢復？**  
A6: **目前均無法恢復（RECOVERY_BLOCKED）**。本地 SQLite 無對應日期的歷史快照，TWSE 歷史 API 和正式 backfill 均未在隔離研究環境中授權。

**Q7: Oct 21 的 Signal / Fill / Outcome 對照為何？**  
A7: Signal Date = Oct 16，Execution (Fill) Date = Oct 21，5th Calendar TD = Oct 30（實際 TaiwanTradingCalendar），TSMC proxy count = 4/5（Oct 30 只有 0050）→ DATA_INCOMPLETE。

**Q8: Oct 22 的 Signal / Fill / Outcome 對照為何？**  
A8: Signal Date = Oct 21，Execution Date = Oct 22，5th Calendar TD = Nov 02，TSMC proxy count = 3/5（Oct 29/30/Nov 02 只有 0050）→ DATA_INCOMPLETE。

**Q9: Oct 28 的 Signal / Fill / Outcome 對照為何？**  
A9: Signal Date = Oct 22，Execution Date = Oct 28，5th Calendar TD = Nov 04（Nov 04 有 6,957 stocks），但 Oct 29/30/Nov 02/03 只有 0050，TSMC proxy count = 2/5 → DATA_INCOMPLETE。

**Q10: 哪些叢集符合 Strict Eligibility？**  
A10: 只有 3 個：Oct 13/14/16 fills（TSMC proxy ≥5）。Oct 21/22/28 fills 仍為 DATA_INCOMPLETE。

**Q11: Frozen Baseline 是否仍為 3 clusters、+0.81 pp？**  
A11: **是**。重現確認：3 strict clusters，grand mean D = +0.81 pp，CI [-1.4%, +3.0%]，SIGNIFICANCE_INCONCLUSIVE。Dataset fingerprint 已從 `2c8b2475c8fdc457` 變為 `09c04e8c4059d87e`（因 Nov 04/05 manual backfill 改變了 `daily_prices_max`），但基線數據完全不變。

**Q12: Expanded Research Snapshot 有多少完整 Clusters？**  
A12: **0 個新增**。S46 的 Oct 28 isolated 研究快照（D=+2.75%，RESEARCH_ONLY）仍是最新的研究補充，S47 未新增任何 strict-eligible cluster。

**Q13: Expanded V3 vs A_direct 的描述性績效為何？**  
A13: 無新增。維持 S46 擴展快照：4 個有限叢集均值 +1.60%（Oct 13 +1.07%, Oct 14 +2.76%, Oct 16 -1.49%, Oct 28 +2.75%，Oct 22 仍 NaN/PENDING）。

**Q14: 新增叢集後，統計推論是否仍不可靠？**  
A14: **是**。N=3 strict clusters，CI 極寬（[-1.4%, +3.0%] pp），且 G04 FAIL（相鄰視窗 80% 重疊，獨立性假設違反）。即使 Oct 21/22/28 fills 升格，N=6 在 G04 FAIL 情況下有效樣本數仍≈3，推論仍不可靠。

**Q15: 20D 最早成熟日究竟是 11/14 還是其他日期？**  
A15: **S46 有誤。正確答案：2026-11-12**（Oct 13 fill 的第 20 個真實交易日）。S46 的 `_CALENDAR_20TD` 值對 5 個叢集均有錯誤，係使用 TSMC proxy 邏輯或錯誤慣例所致。

**Q16: 20D 全部候選叢集最晚成熟日為何？**  
A16: **2026-11-25**（Oct 28 fill 的第 20 個真實交易日）。S46 錯誤標為 Dec 02（差 7 天）。

**Q17: G04 80% overlap 的正式計算方式為何？**  
A17: `overlap_pct = |window_A ∩ window_B| / window_size × 100`。分母 = 5（每個叢集持有的交易日數）。分子 = 兩個 5 天窗口的交集天數。最大重疊對：Oct 13/14 和 Oct 21/22 各有 4 個共享交易日 = 80%。G04 門檻 < 30%（≤1.5 天），全部相鄰對均超過門檻。

**Q18: G03 / G04 最新狀態為何？**  
A18: G03 FAIL（3/10，恢復路徑在 pipeline 修復後 + 7-8 週連續資料）；G04 FAIL（設計性問題，需 weekly-spaced fills 或 bootstrap CI）。兩者均未改變。

**Q19: Production、Cron、ForwardSignals、Frozen Strategies 是否完全未變？**  
A19: 是，全部未變。
- `forward_signals` 總數：2605 ✓
- `daily_prices` max (SQLite)：2026-11-05 ✓
- V3 Parameter Hash：`be43e8ca977d9fdd` ✓
- Crontab Hash：`3acaf480cb5dcdd44f40dd9d464955a1` ✓
- Production NOT modified ✓

**Q20: Session 48 應優先執行什麼？**  
A20: 見「Session 48 建議」一節。

---

## Key Numbers Summary

| Metric | Value |
|---|---|
| Total trading days analyzed (Oct 08–Nov 09) | 20 |
| COMPLETE trading days | 9 |
| PARTIAL_COVERAGE days (1 stock) | 9 |
| DATE_MISSING days | 2 |
| Strict clusters | 3 (unchanged) |
| Incomplete clusters | 3 (unchanged) |
| Grand mean D | +0.81% |
| CI 95% | [-1.4%, +3.0%] |
| Statistical verdict | SIGNIFICANCE_INCONCLUSIVE |
| Correct 20D earliest exit | 2026-11-12 (S46 said Nov 14: WRONG) |
| Correct 20D latest exit | 2026-11-25 (S46 said Dec 02: WRONG) |
| G04 max overlap % | 80% (Oct 13/14 and Oct 21/22 pairs) |
| New S47 tests | 101 |
| Total tests | 2762 passed, 1 skipped |

---

## Production Fingerprints (All Unchanged)

| Item | Value |
|---|---|
| `forward_signals` total | 2605 |
| `daily_prices` max (SQLite) | 2026-11-05 |
| Baseline fingerprint | `09c04e8c4059d87e` (changed from S44 due to daily_prices_max change) |
| V3 Parameter Hash | `be43e8ca977d9fdd` |
| Crontab Hash | `3acaf480cb5dcdd44f40dd9d464955a1` |
| SESSION | 47 |

---

## Session 48 最小可行研究建議

### Priority 1: Pipeline Restoration (AI-1 from S46)

**Goal:** Backfill Oct 30, Nov 02, Nov 03 to promote Oct 21/22 fills to strict.  
**Method:** Manual `backfill_daily_prices.py --start 2026-10-30 --end 2026-11-03 --execute`  
**Expected outcome:** Oct 21 proxy 4→8, Oct 22 proxy 3→7 → both STRICT.  
**Requires:** Separate backfill authorization. Same scope as Nov 04/05 manual backfill.

### Priority 2: S46 Date Error Fix

**Goal:** Correct `_CALENDAR_5TD` and `_CALENDAR_20TD` in `prospective_comparison_s46.py`.  
**Method:** Replace hardcoded values with TaiwanTradingCalendar-computed values.  
**Impact:** Fixes documentation accuracy; does NOT change frozen baseline deltas.

### Priority 3: 20D Authorization Preparation

**Goal:** Prepare for 20D outcome computation (Oct 13 fill exits Nov 12).  
**Timeline:** Nov 12 is 3 trading days away. Data needed: Nov 06–12 (pipeline must run).  
**Requires:** AUTH01 + AUTH02 explicit authorization in S48.

### Priority 4: G04 Design Decision

**Goal:** Decide on G04 remediation strategy (weekly spacing or bootstrap CI).  
**This is a research design decision, not a data problem.**  
**No implementation in S48; requires design specification first.**

### Do NOT do in S48 without explicit authorization

- 20D Outcome calculation
- Production DB modification
- V3 activation
- Cron modification
- S46 `_CALENDAR_5TD`/`_CALENDAR_20TD` values in production comparison modules (wait until confirmed correct + tests pass)
