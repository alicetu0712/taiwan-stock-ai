# Session 50 Final Verdict — Verified Market Data Sources & Calendar Contract Consolidation

**Date:** 2026-11-10  
**Session:** S50 — PARTS A through M  
**Test Count:** 3203 passed, 1 skipped (baseline 3012 + 191 new)

---

## Final Verdict Enums

| Dimension | Verdict |
|---|---|
| Source Verification | SOURCE_VERIFIED_PARTIAL (all 11 dates) |
| Nov 06/09 Status | **UPGRADED**: UNIVERSE_UNVERIFIED → SOURCE_VERIFIED_PARTIAL |
| Calendar Contract | SSOT_CONSOLIDATED (S50 is single source of truth) |
| S46 Module | ERRONEOUS_PRESERVED (unchanged — overlay approach) |
| Pipeline Status | BLOCKED (Nov 05 last DATA_COMPLETE; Nov 06/09 = 0 rows) |
| Backfill Manifest | SAMPLE_VERIFIED; full 599-stock manifest requires dry-run |
| Authorization AUTH01 | PENDING USER AUTHORIZATION |
| Authorization AUTH02 | BLOCKED_PIPELINE |
| Strict Clusters Now | 3/6 (Oct 13/14/16 strict) |
| Strict Clusters After P1 | 6/6 (after backfill) |
| G03 Guardrail | FAIL (3/10 now; 6/10 after P1; need 10) |
| G04 Guardrail | FAIL (structural; weekly spacing does NOT fix) |
| 20D Readiness | BLOCKED_PIPELINE (all 6 clusters) |
| Nov 12 Deadline | URGENT (10 days to Oct 13 maturity from analysis date) |
| Frozen Baseline | BASELINE_REPRODUCED (+0.81%, 3 clusters, UNCHANGED) |
| Statistical Verdict | SIGNIFICANCE_INCONCLUSIVE (unchanged) |
| Activation | ACTIVATION_BLOCKED (unchanged) |
| Regression | REGRESSION_PASS (3203 passed) |

---

## 20 Final Questions

**Q1: 為什麼所有 11 個候選日期都被升格為 SOURCE_VERIFIED_PARTIAL？**  
A1: S50 PART B 的真實 API 調查確認，TWSE 單股 API (STOCK_DAY?date=YYYYMMDD&stockNo=XXXX) 對全部 11 個日期都能返回正確的歷史月份資料。S49 的 9 個「INSERT_ONLY_CANDIDATE」日期本來就有 SOURCE_PARTIAL 狀態；S50 新增的關鍵發現是 Nov 06 和 Nov 09 也能透過單股 API 取得資料，將它們從 UNIVERSE_UNVERIFIED 升格為 SOURCE_VERIFIED_PARTIAL。

**Q2: Nov 06/09 被升格後，它們的回填路徑是什麼？**  
A2: 升格表示「資料存在」，但不代表回填路徑已清楚。Nov 06 的 QUALITY_GATE_FAIL 和 Nov 09 的 PROVIDER_NOT_READY 都是管線問題（bulk API 或 scheduler 問題），不是資料問題。正確路徑：(1) 修復管線 bulk fetch 問題；(2) 重新跑 cron（已是當前日期以前，需要特殊處理）；或 (3) 使用 per-stock 回填模式（需要 ~600 API 呼叫，授權後才能執行）。不能在未解決根本原因前就嘗試回填。

**Q3: TWSE Bulk Historical 返回 HTTP 200 但是錯誤資料，這對研究的影響是什麼？**  
A3: 核心影響是：「HTTP 200 ≠ 資料存在」。S50 PART B 明確記錄了這個陷阱。任何依賴 HTTP 200 來判斷資料可用性的系統邏輯都是錯誤的。正確的驗證方式：(1) 解析 response body 中的日期欄位；(2) 確認回傳的 `date` 欄位等於查詢日期；(3) 確認 stock_count 在合理範圍。scripts/backfill_daily_prices.py 目前的 fallback 邏輯可能就是這個問題的來源。

**Q4: BackfillCandidateManifest 的 PARTIALLY_READY 和 READY_FOR_USER_AUTHORIZATION 有什麼差別？**  
A4: `READY_FOR_USER_AUTHORIZATION` 表示「樣本記錄無衝突，冪等性驗證通過，可以請求授權」。`PARTIALLY_READY` 表示「樣本驗證通過，但全部 599 股尚未逐一確認；有未解決的風險需要告知使用者」。S50 的 Manifest 因為 RISK-01（只驗證了樣本）而被標為 PARTIALLY_READY，不是因為有衝突。實際授權前需先執行 dry-run。

**Q5: ResearchTradingCalendarContract 的 fingerprint 是如何設計的？**  
A5: fingerprint = `CCFP-` + SHA256(JSON{`_CORRECT_5TD`, `_CORRECT_20TD`, `version`="s50"})[:8]。這是內容雜湊，確保只要 authoritative dates 不變，fingerprint 就不變。如果未來有人修改 _CORRECT_5TD 或 _CORRECT_20TD，fingerprint 會立即改變，可以在 TC24 測試中被偵測到（`fingerprint_deterministic` 測試）。

**Q6: 為什麼 S50 的 SSOT 不直接修改 calendar_contract_s48 或 pipeline_recovery_s49 中的重複 dict？**  
A6: 因為 S48 和 S49 的模組已經是凍結的研究記錄。修改它們會改變那些 session 的研究血統，可能使那些 session 的測試行為改變，並造成未來的可重現性問題。S50 採取「疊加 SSOT」方式：不修改過去的模組，只在 S50 中宣告「以後新呼叫者應使用我」。這和 S49 對 S46 採取的覆蓋層方式一致。

**Q7: G04 weekly spacing 分析的核心新發現是什麼？**  
A7: **≥5 TD spacing 無法解決 G04。** 採用 ≥5 TD 間距過濾後，保留 {Oct 13, Oct 21, Oct 28}（N=3），但 Oct 21/Oct 28 相鄰對的重疊率仍為 40% > 30%，G04 仍然失敗。根本原因：5 日持有窗口 + 兩個 fill dates 恰好相距 5 TD，導致窗口共享 2 天。要讓 G04 在 weekly spacing 下通過，需要 ≥6 TD 間距——但這樣只剩 N=2，使 G03 更差。

**Q8: G04 effective N 計算的實際意義是什麼？**  
A8: 以 r=0.8（來自 80% 重疊）計算，N=6 的有效樣本數 ≈ 1.09。這意味著用 N=6 做 t-test 時，實際上等同於只有 1 個有效觀察。S41 公佈的 p=0.58 已經不顯著（即使假設 N=6 獨立）；修正後的有效 N≈1.09 使統計推斷完全無意義。這也解釋了為什麼 bootstrap CI 在 G03 解決前是無效的——bootstrap 只是在 1 個有效點上做重抽樣。

**Q9: PipelineCompletionContract 的 10 個階段如何幫助診斷 Nov 06/09 失敗？**  
A9: 透過 10 個階段，可以精確定位失敗點：Nov 09 在 S02（PROVIDER_READY_CHECK）失敗，api_date 返回 1151106 而非 1151109；Nov 06 在 S05（QUALITY_GATE）失敗，資料被 bulk fetch 回來了但無法通過品質檢查。這種分類防止了「模糊說管線壞了」，讓修復工作可以針對具體問題（S02 要調查 scheduler timing；S05 要調查 quality gate threshold 或資料異常）。

**Q10: BENCHMARK_ONLY 判斷規則對研究的重要性是什麼？**  
A10: 2026-10-29/30/Nov 02/03 的 daily_prices 中只有 1 筆記錄（0050 proxy），這些日期不能提供 portfolio 的 exit price。如果沒有這個規則，分析師可能誤以為「DB 有這一天的資料」而嘗試計算 exit return，結果只得到 0050 的報酬率而非持倉組合的真實報酬。BENCHMARK_ONLY_REJECTED 是明確的預防機制。

**Q11: 20D Readiness Matrix 為什麼所有叢集都是 BLOCKED_PIPELINE？**  
A11: 判斷邏輯中，`pipeline_restored=False` 的優先級高於所有其他條件。即使某個叢集已成熟（exit date 已過）、也有 AUTH01 授權，只要管線沒有恢復並寫入 exit date 的資料，就無法計算 20D return。管線不通 = exit price 不在 DB 中 = 無法計算 = BLOCKED_PIPELINE。這比 BLOCKED_AUTH01 更根本。

**Q12: Nov 12 是什麼截止日期，為什麼如此緊迫？**  
A12: Nov 12 是 Oct 13 fill date 的第 20 個真實交易日（corrected 20TD）。如果管線在 Nov 12 前沒有恢復並寫入當天的全市場資料，Oct 13 叢集的 20D exit price 就永遠無法從本地 platform.db 計算（除非透過 Neon DB，但需要另外授權）。從分析日 Nov 02 算起，只有 10 個日曆日。如果管線今天起動，Nov 06–Nov 12 的資料需要補回（需要回填），否則 Oct 13 的 20D outcome 永久消失。

**Q13: S46 的錯誤日期如果用於實際研究，最嚴重的後果是什麼？**  
A13: 20TD 的後果最嚴重。S46 的 Oct 28 20TD exit 是 2026-12-02，比正確值 2026-11-25 晚 7 天。如果研究者等到 Dec 02 才去查 Oct 28 的 20D 報酬，他們可能會：(1) 錯過 Nov 25 是正確的出場日，把 Nov 26–Dec 02 的額外市場波動計入報酬；(2) 在統計上誤判信號效果的持久性。對 20D 分析來說，7 天的誤差在臺灣市場可以造成 ±3–5% 的報酬率偏差。

**Q14: S50 的兩個研究模組如何分工？**  
A14: `market_source_verification_s50.py`（PARTS B/C）專注於「資料來源驗證」：回答「我們能從哪裡拿到歷史資料？哪些記錄可以插入 DB？」`calendar_contract_s50.py`（PARTS D–H）專注於「研究框架合約」：回答「正確的日曆日期是什麼？管線完成的定義是什麼？G04 能被修復嗎？20D 什麼時候可以計算？」兩個模組互補，前者是資料層，後者是分析合約層。

**Q15: 為什麼 S50 不執行正式回填？**  
A15: S50 規範明確說明：「本次不是正式 Backfill 授權」。S50 的角色是「驗證來源可用性、建立正式 Manifest、為授權準備文件」。實際的正式回填需要使用者明確授權（AUTH01），這是在 S50 完成後、根據本文件中的 Manifest 和風險說明來做的決定。強制分離「研究準備」和「生產寫入」是本平台的核心安全原則。

**Q16: 在 S50 建立 SSOT 之前，同樣的日期出現在哪些地方？**  
A16: `_CORRECT_5TD` 和 `_CORRECT_20TD` 在兩個凍結模組中重複出現：(1) `calendar_contract_s48.py`（S48 建立，原始版本）；(2) `pipeline_recovery_s49.py`（S49 建立，作為覆蓋層複製）。S50 的 `calendar_contract_s50.py` 是第三個出現點，但被宣告為 SSOT。S48/S49 的版本不刪除（維持研究血統），但新呼叫者應只使用 S50。這是「不修改凍結模組」原則下的最優解。

**Q17: S50 的 191 個新測試涵蓋了哪些主要面向？**  
A17: 191 個測試（40 個類別）涵蓋：(1) SourceMatrix 11 日期結構與 SOURCE_VERIFIED_PARTIAL 分類；(2) Nov 06/09 升格驗證；(3) Oct 29 六股 OHLC 完整驗證；(4) TWSE/TPEx provider 判斷；(5) validate_ohlc 函數正確性；(6) BackfillManifest 冪等性、動作分類、風險清單；(7) CalendarContract 5TD/20TD 修正值與 S46 錯誤值；(8) 10 個管線階段與 DATA_COMPLETE/BENCHMARK_ONLY 規則；(9) Strict 5D 升格條件；(10) G04 weekly spacing 新發現；(11) 20D 就緒性判斷；(12) 生產指紋確認。

**Q18: G04 最終的解法是什麼？什麼時候可以看到結果？**  
A18: G04 唯一的完全解法是「收集 ≥6 TD 間距的 fill date，且累積到 N≥10 個叢集」。以台股正常交易週期（每週 5 個交易日），≥6 TD ≈ 每 1.5 週一個 fill date，要累積到 10 個至少需要 15 週（約 4 個月）。同時，G03 要求也從第 10 個叢集起才能通過。這意味著：**最快的 G03+G04 雙通過需要約 4 個月的持續資料收集**。在此期間，可以提前記錄每週 fill date 的原始信號和 proxy count，不需等 20TD 成熟。

**Q19: 20D 資料即使計算出來，對激活決策有什麼幫助？**  
A19: 20D 資料在兩個方面有研究價值：(1) **持有期比較**：5D 基線為 +0.81pp，20D 是否維持、加強或反轉？持久性是信號有效性的指標；(2) **新決策證據**：如果 20D 顯示 alpha 明顯衰減（e.g., +0.1pp），說明信號主要是短期的，策略設計應考慮動態出場而非固定 20TD。但因為 G03/G04 未通過，任何 20D 結果都不具備足夠的統計效力來單獨支持激活。20D 是「更多證據」而非「足夠證據」。

**Q20: Session 51 的最優先行動是什麼？**  
A20: 三個優先行動依重要性排序：(1) **管線緊急修復**（Nov 12 前）：解決 Nov 06 QUALITY_GATE_FAIL 根本原因；確保 Nov 12 有 Oct 13 叢集的 20D exit price 資料。如果管線無法在 Nov 12 前修復，唯一替代方案是透過 Neon DB 授權存取。(2) **AUTH01 授權 + P1 回填**：授權後執行 Oct 29/30/Nov 02/03 回填，使 Strict count 從 3 升至 6；這是 20D 計算的前提之一。(3) **G04 設計決策**：決定是否切換到 weekly-spaced fill frequency（每 ≥6 TD 一個 fill date），即使短期犧牲資料密度，也能建立統計上可辯護的基礎。

---

## Key Numbers Summary

| Metric | Value |
|---|---|
| Backfill candidates | 11 |
| SOURCE_VERIFIED_PARTIAL | 11 (all upgraded) |
| Dates upgraded (S50 new) | 2 (Nov 06/09) |
| Strict clusters (now) | 3 (Oct 13/14/16) |
| Strict clusters (after P1) | 6 (projected) |
| Grand mean delta | +0.81 pp (unchanged, frozen) |
| 20D earliest exit (corrected) | 2026-11-12 |
| 20D latest exit (corrected) | 2026-11-25 |
| Nov 12 deadline urgency | HIGH (10 days from analysis date) |
| G03 | FAIL (6/10 after P1) |
| G04 | FAIL (structural) |
| Weekly spacing 5TD | G04 still FAIL (Oct 21/Oct 28 = 40%) |
| Weekly spacing 6TD | G04 PASS but N=2 |
| Effective N (N=6, r=0.8) | ≈1.09 |
| New tests (S50) | 191 |
| Total tests | 3203 passed, 1 skipped |
| AUTH01 status | PENDING |
| AUTH02 status | BLOCKED_PIPELINE |

---

## Production Fingerprints (All Unchanged)

| Item | Value |
|---|---|
| `forward_signals` total | 2605 |
| `daily_prices` max | 2026-11-05 |
| Frozen baseline fingerprint | `09c04e8c4059d87e` |
| V3 Parameter Hash | `be43e8ca977d9fdd` |
| SESSION | 50 |

---

## Session 51 Minimum Viable Actions

### Priority 1: 管線緊急修復 (URGENT — Nov 12 deadline)
**目標：** 修復 Nov 06+ 管線，確保 Nov 12 有 Oct 13 叢集的 20D exit price  
**時間限制：** 2026-11-12（今起 10 日曆日）  
**方法：** 調查 Nov 06 QUALITY_GATE_FAIL + Nov 09 PROVIDER_NOT_READY 根本原因  
**風險：** 若管線未在 Nov 12 前修復，Oct 13 20D outcome 永久不可從 local DB 計算

### Priority 2: AUTH01 授權 + P1 回填
**目標：** Oct 29/30/Nov 02/03 回填至 local SQLite  
**效果：** Strict count 3→6；Oct 21/22/28 升格為 STRICT  
**條件：** TWSE single-stock API 可用（TSMC prices confirmed）

### Priority 3: G04 設計決策
**決策：** 是否切換到 ≥6 TD fill frequency（約每週一次）  
**權衡：** G04 解決 vs 資料累積速度降低  
**時程：** 討論即可；不需要立即實作

### Do NOT do in S51 without explicit authorization
- Activate V3 / ACTUAL / PAPER trading
- Modify Production Decision Center or v8.0 rules
- Modify `prospective_comparison_s46.py`
- Push to Neon production
- Modify V3 parameter hash `be43e8ca977d9fdd`
- Execute 20D outcome calculations (AUTH02 not granted)
