# Session 48 Final Verdict — Pipeline Reliability & 20D Calendar Contract Correction

**Date:** 2026-11-09  
**Session:** S48 — PARTS A through L  
**Test Count:** 2869 passed, 1 skipped (baseline 2762 + 107 new)

---

## Final Verdict Enums

| Dimension | Verdict |
|---|---|
| Pipeline Root Cause | ROOT_CAUSE_CONFIRMED (18/20), ROOT_CAUSE_PARTIAL (2/20) |
| Coverage Matrix | COVERAGE_PARTIAL (9 complete, 9 benchmark-only, 2 missing) |
| Backfill Dry-run | INSERT_ONLY_CANDIDATES_IDENTIFIED |
| 20D Calendar Correction | ALL_6_CLUSTERS_CORRECTED (S46 had 6/6 20TD errors) |
| 5D Calendar Correction | 3_CLUSTERS_CORRECTED (Oct 13/14/16 5TD errors fixed) |
| 20D Maturity | 20D_NOT_READY (all 6 NOT_YET_MATURE) |
| 5D Readiness | STRICT_3_WAITING_3 (unchanged from S47) |
| Guardrails | BOTH_FAIL (G03 3/10, G04 max 80%) |
| Frozen Baseline | BASELINE_REPRODUCED (+0.81%, 3 clusters) |
| Activation | ACTIVATION_BLOCKED |
| Regression | REGRESSION_PASS (2869 passed) |

---

## 20 Final Questions

**Q1: 管線的三個 stock-count 層級分別是什麼？**  
A1: TIER_1_PROXY (1 stock, 0050): 非 fill date 的交易日，管線只寫入基準股；TIER_655_FILL (~655 stocks): fill date，管線為 ForwardSignalService 寫入完整過濾後宇宙；TIER_6957_BACKFILL (~6957 stocks): Nov 04/05 手動補齊，涵蓋全市場。

**Q2: PIPELINE_SELECTIVE 的技術定義是什麼？**  
A2: 管線在 ForwardSignalService 有 signal 執行的日期（fill dates）才執行完整資料拉取；非 fill date 只寫入 0050 proxy 以確認市場開市狀態。設計上是有意為之，但沒有回填中間日期的機制。

**Q3: SCHEDULER_NOT_TRIGGERED 的直接證據為何？**  
A3: `hybrid_forward_run_log` 顯示最早的正式 cron 執行為 `2026-11-05T04:42:02Z`（處理 Nov 04 資料）。Oct 30/Nov 02/03 各只有 0050，與 cron 未運作的預測一致。

**Q4: Nov 06 和 Nov 09 為何完全沒有資料（0 rows）？**  
A4: Nov 06 = QUALITY_GATE_FAIL（cron 嘗試執行但 QG 拒絕批次）；Nov 09 = PROVIDER_NOT_READY（cron 執行時 TWSE api_date 過期，S03 fetch 失敗）。兩者都在 cron 啟動後發生，但各自有不同的 failure mode。

**Q5: 15 個覆蓋維度中哪些最關鍵？**  
A5: 最關鍵的 5 個：(5) benchmark_present（0050 proxy 確認）；(6) tsmc_present（TSMC = 完整覆蓋 proxy）；(10) coverage_status（三段分類：DATA_COMPLETE/BENCHMARK_ONLY/DATA_MISSING）；(9) pipeline_root_cause（針對性修復路徑）；(14) affects_active_cluster（直接影響 5D return 計算）。

**Q6: Backfill Dry-run 的 INSERT_ONLY_CANDIDATE 和 CONFLICT_REQUIRES_REVIEW 有何區別？**  
A6: INSERT_ONLY = 現有 0050 row 不需 UPDATE（INSERT 其他股票即可，0050 row 用 INSERT OR IGNORE 跳過）；CONFLICT_REQUIRES_REVIEW = 有 row 需要比對是否為正確資料（本 session 無此類別，全部為 LOW risk）。Nov 06/09 是 UNIVERSE_UNVERIFIED（0 rows，整批 INSERT，但不確定 API 能否提供該日資料）。

**Q7: S48 的 20D 日期修正是否改變了 Frozen Baseline (+0.81%)?**  
A7: 否。日期修正只改變「哪一天是第 N 個交易日」的文件記錄，不改變 S43 Bash 分析時使用的實際價格數據。Frozen baseline 的 delta 是從真實歷史價格計算出的結果，不依賴 `_CALENDAR_5TD`/`_CALENDAR_20TD` 的命名。

**Q8: S46 的 20D 日期錯誤對研究結論有什麼影響？**  
A8: 只影響「何時可以計算 20D outcome」的時間表，不影響任何已公佈的 5D baseline 數字。S46 文件中的 Nov 14（應為 Nov 12）和 Dec 02（應為 Nov 25）是時間表誤差，非研究結論誤差。

**Q9: 修正後，20D 最早成熟日是哪一天？**  
A9: 2026-11-12（Oct 13 fill 的第 20 個真實交易日）。距分析日 Nov 09 只剩 3 個交易日。

**Q10: 為什麼 Oct 13 fill 的 5D window 內 TSMC 只有 2/5，但 proxy count = 7？**  
A10: proxy count 計算方式是「fill_date 之後所有 TSMC-present 日期的總數」，不限於 5D window。Oct 13 後的 TSMC 存在日：Oct 14/16/21/22/28/Nov04/05 = 7 個，遠超 5D window 內的 2 個（Oct 14 和 Oct 16）。

**Q11: Strict eligibility 的 proxy_count ≥ 5 是否代表「exit 一定成功」？**  
A11: 否。proxy_count ≥ 5 是充分條件（確保有足夠的價格數據點計算 5D return），但不代表所有 5D window dates 都有 TSMC 覆蓋。Oct 13 fill 的 5D window 內有 3 個 partial coverage 日，exit price 可能使用了 window 外的後續日期。

**Q12: G04 的正式公式是什麼？**  
A12: `overlap_pct = |window_A ∩ window_B| / window_size × 100`，分母固定為 5（window_size），非 Jaccard union。Oct 13/Oct 14 pair：4/5 = 80%，Oct 21/Oct 22 pair：4/5 = 80%，均為最大值。

**Q13: G04 FAIL 是否可以在不改變研究設計的情況下修復？**  
A13: 否。G04 失敗是 daily-frequency fill 的結構性問題，只要 fill dates 連續，相鄰的 5D window 就必然重疊。修復方案需要設計變更：weekly-spaced fills 或 bootstrap CI 明確建模相關性。

**Q14: Backfill Oct 29/30/Nov 02/03 後，strict count 能提升到多少？**  
A14: 從 3 提升到 6（Oct 21/22/28 全部升格為 STRICT）。但 G04 仍 FAIL（相鄰視窗重疊 40-80% 的結構不變），G03 仍 FAIL（6 < 10）。

**Q15: 什麼情況下可以考慮計算 20D outcome？**  
A15: 四個先決條件全部達成後：(1) pipeline 修復，Nov 06+ 有完整資料；(2) 至少 Nov 10/11/12 有 ≥ 300 stocks（Oct 13 fill 的 20D exit 日）；(3) 明確授權 (AUTH01 + AUTH02)；(4) 指定持有期間慣例（calendar TD 或 price-available TD）。

**Q16: `prospective_comparison_s46.py` 中的錯誤是否已被修正？**  
A16: 否。S48 只在新模組（`calendar_contract_s48.py`）中記錄正確值。S46 原始模組未被修改（這需要另行授權，且修改會改變模組的 version/fingerprint）。

**Q17: 為什麼 Oct 1–7 的 `daily_prices` 有 ~499 stocks 而非 655？**  
A17: 這是 v8.0 之前的 legacy tier。Oct 08 以前管線使用舊的宇宙過濾邏輯，約 499 stocks。Oct 12 起切換至 v8.0 filtered universe (~655 stocks)，只在 fill dates 完整寫入。

**Q18: S48 是否觸及任何 Production 系統？**  
A18: 否。S48 嚴格為 READ-ONLY 研究。所有 `build_*()` 函數只讀取 `data/platform.db`，無任何 INSERT/UPDATE/DELETE。Production Neon、Cron、ForwardSignals、daily_prices、v8.0 規則、V3 參數均未變動。

**Q19: 下一步研究優先順序為何？**  
A19: (1) 授權並執行 Oct 29/30/Nov 02/03 backfill → 3 個 incomplete clusters 升格；(2) 修復 Nov 06+ pipeline → 20D outcome 資料準備；(3) 授權 20D outcome 計算（AUTH01+AUTH02）；(4) G04 設計決策（weekly spacing vs bootstrap CI）。

**Q20: Session 49 最小可行建議為何？**  
A20: 見「Session 49 建議」一節。

---

## Key Numbers Summary

| Metric | Value |
|---|---|
| Trading days analyzed (Oct 08–Nov 09) | 20 |
| DATA_COMPLETE days | 9 |
| BENCHMARK_ONLY days | 9 |
| DATA_MISSING days | 2 |
| Backfill candidates | 11 |
| INSERT_ONLY candidates | 9 |
| Strict clusters | 3 (unchanged) |
| Incomplete clusters | 3 (unchanged) |
| Grand mean delta | +0.81 pp (unchanged) |
| 20D earliest exit | 2026-11-12 (corrected; S46 said Nov 14) |
| 20D latest exit | 2026-11-25 (corrected; S46 said Dec 02) |
| G04 max overlap % | 80% |
| S48 new tests | 107 |
| Total tests | 2869 passed, 1 skipped |

---

## Production Fingerprints (All Unchanged)

| Item | Value |
|---|---|
| `forward_signals` total | 2605 |
| `daily_prices` max | 2026-11-05 |
| Baseline fingerprint | `09c04e8c4059d87e` |
| V3 Parameter Hash | `be43e8ca977d9fdd` |
| Crontab Hash | `3acaf480cb5dcdd44f40dd9d464955a1` |
| SESSION | 48 |

---

## Session 49 最小可行建議

### Priority 1: Backfill Oct 29/30/Nov 02/03

**Goal:** Promote Oct 21/22/28 fills from INCOMPLETE to STRICT.  
**Method:** `backfill_daily_prices.py --start 2026-10-29 --end 2026-11-03 --research-only`  
**Expected outcome:** Strict count 3 → 6; proxy counts: Oct 21 (4→8), Oct 22 (3→7), Oct 28 (2→5).  
**Prerequisite:** TWSE historical API availability confirmation for these dates.  
**Research impact:** Still SIGNIFICANCE_INCONCLUSIVE (G03/G04 still FAIL), but expanded to 6 clusters.

### Priority 2: Pipeline Restoration (Nov 06+)

**Goal:** Restore daily pipeline so Nov 06–25 are captured for 20D outcomes.  
**Method:** Investigate and fix QUALITY_GATE_FAIL (Nov 06) and PROVIDER_NOT_READY (Nov 09) root causes.  
**Timeline:** Nov 12 is the earliest 20D exit date — only 3 trading days away.  
**Risk:** If pipeline is not restored by Nov 12, Oct 13 fill's 20D outcome may be uncomputable.

### Priority 3: 20D Authorization (AUTH01 + AUTH02)

**Goal:** Authorize 20D outcome computation for Oct 13/14/16 fills.  
**Prerequisites:** Pipeline restoration complete; Nov 12–25 data confirmed available.  
**Output:** 6 clusters with both 5D and 20D return metrics.  
**Research design**: Specify holding-period convention before computing.

### Priority 4: S46 `_CALENDAR_5TD`/`_CALENDAR_20TD` Correction

**Goal:** Fix incorrect dates in `src/research/prospective_comparison_s46.py`.  
**Method:** Replace hardcoded values with correct TaiwanTradingCalendar-verified dates.  
**Risk:** Module modification changes its content hash; test suite must be updated accordingly.  
**Note:** Pure documentation correction; no baseline metrics change.

### Do NOT do in S49 without explicit authorization

- Activate V3
- Activate ACTUAL / PAPER trading
- Modify Production Decision Center
- Modify v8.0 signal generation rules
- Modify Hybrid P1–P4
- Change `be43e8ca977d9fdd` V3 parameter hash
- Modify GitHub Actions
- Push to Neon production
