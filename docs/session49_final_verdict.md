# Session 49 Final Verdict — Backfill Authorization Readiness & Pipeline Recovery Validation

**Date:** 2026-11-09  
**Session:** S49 — PARTS A through L  
**Test Count:** 3012 passed, 1 skipped (baseline 2869 + 143 new)

---

## Final Verdict Enums

| Dimension | Verdict |
|---|---|
| Source Verification | SOURCE_PARTIAL (9 dates) + SOURCE_UNVERIFIED (2 dates) |
| Backfill Readiness | 9 INSERT_ONLY_CANDIDATE; 2 UNIVERSE_UNVERIFIED (Nov 06/09 blocked) |
| Authorization Status | PENDING_USER_AUTHORIZATION (AUTH01 not yet granted) |
| Pipeline Recovery Validation | ALL_PASS (10/10 scenarios in Temporary SQLite) |
| Calendar Contract | 6/6 20TD corrected; 3/6 5TD corrected; S46 NOT modified |
| 5D Readiness | STRICT_3_WAITING_3 (unchanged from S48; backfill not executed) |
| 20D Authorization | ACTIVATION_BLOCKED (AUTH01 pending → AUTH02 blocked) |
| Guardrails G03/G04 | BOTH_FAIL (unchanged) |
| Frozen Baseline | BASELINE_REPRODUCED (+0.81%, 3 clusters, UNCHANGED) |
| Activation | ACTIVATION_BLOCKED |
| Regression | REGRESSION_PASS (3012 passed) |

---

## 20 Final Questions

**Q1: 為什麼 TWSE 大量歷史 API (STOCK_DAY_ALL?date=YYYYMMDD) 不能用於回填？**  
A1: TWSE `STOCK_DAY_ALL` bulk endpoint 忽略 `date=` 參數，返回當日資料或空白 body。在 S49 PART B 驗證中，對 2026-10-29 的查詢沒有返回任何歷史資料。這個 endpoint 只支援當日快照，不支援歷史日期查詢。

**Q2: TWSE 單股 API 為何被分類為 SOURCE_PARTIAL 而不是 SOURCE_CONFIRMED？**  
A2: `STOCK_DAY?date=YYYYMMDD&stockNo=XXXX` 確實可以返回歷史月份資料（TSMC 2330 在 Oct 27/29/30 的收盤價已確認），但這需要對每支股票分別查詢。全市場 ~700 支股票需要 ~700 次 API 呼叫，且無法一次性批次取得。SOURCE_PARTIAL 表示「資料存在但取得方式受限」。

**Q3: TPEx OpenAPI 歷史查詢為何無效？**  
A3: TPEx OpenAPI 的 `?d=1151029` 參數被完全忽略，每次查詢都返回當日資料（S49 測試時返回 Nov 09 資料，13674 筆）。TPEx 沒有提供可用的歷史日期參數。

**Q4: TWSE OpenAPI 當前狀態如何解釋 PROVIDER_NOT_READY 根本原因？**  
A4: S49 PART B 查詢 TWSE OpenAPI 時，api_date 返回 `1151106`（Nov 06），而非 `1151109`（Nov 09）。Nov 09 的 cron 執行時，TWSE OpenAPI 只有 Nov 06 的資料。管線在 S03 步驟發現 api_date 不符合預期，觸發 PROVIDER_NOT_READY 失敗。

**Q5: BackfillAuthorizationPackage 的 package_id 是如何生成的？**  
A5: package_id = `AUTH01-` + SHA256(JSON{priority_1_dates, priority_2_dates, blocked_dates, n_insert_only, n_universe_unverified})[:8]。這是一個內容雜湊，確保授權包的結構可被識別和驗證。當前為 `AUTH01-{computed}`，每次生成時計算。

**Q6: 為什麼 Nov 06 和 Nov 09 被分類為 UNIVERSE_UNVERIFIED 而不是 SOURCE_BLOCKED？**  
A6: SOURCE_BLOCKED 意指「已知資料不存在」。UNIVERSE_UNVERIFIED 意指「不清楚資料是否存在或正確」。Nov 06 的 QUALITY_GATE_FAIL 表示 cron 嘗試執行但拒絕了 TWSE 返回的資料，原因不明。Nov 09 的 PROVIDER_NOT_READY 表示 TWSE API 返回過期資料。兩者都需要先解決根本原因才能判斷是否可回填。

**Q7: Temporary SQLite 與 Production SQLite 的隔離如何保證？**  
A7: 所有 10 個恢復場景使用 `sqlite3.connect(":memory:")` 建立純記憶體資料庫，不涉及任何磁碟 I/O。每個場景有獨立的記憶體 DB 實例，場景結束後即消滅。TC35 的驗證測試在場景執行後確認 `data/platform.db` 中 Nov 06/09 仍為 0 筆，直接證明隔離有效。

**Q8: SC10（CLUSTER_PROMOTION_ACHIEVED）場景驗證了什麼？**  
A8: SC10 模擬 Oct 28 叢集的升格過程：先設置只有 Nov 04/05 的 TSMC 資料（proxy_count=2），然後加入 Oct 29/30/Nov 02 的 TSMC 資料（模擬 P1 回填），驗證 proxy_count 從 2 增加到 5，達到 STRICT 門檻。這直接證明了 P1 回填機制在技術上可行。

**Q9: get_corrected_calendar_exit() 的用途是什麼？如何取代 S46 的錯誤值？**  
A9: 這個函數從 `pipeline_recovery_s49.py` 的 `_CORRECT_5TD` / `_CORRECT_20TD` 字典中查找正確的出場日期。它提供一個覆蓋層，讓新的呼叫者不必依賴 `prospective_comparison_s46.py` 的錯誤 `_CALENDAR_5TD`/`_CALENDAR_20TD`。S46 原始模組未修改，兩套值並存，新程式碼應使用 S49 的版本。

**Q10: 20D 最早成熟日 Nov 12 的意義是什麼？**  
A10: Nov 12 是 Oct 13 fill（6 個叢集中進場日最早的）的第 20 個真實交易日。如果管線在 Nov 12 前恢復並有資料，且 AUTH02 已授權，就可以計算 Oct 13 叢集的 20D return。若管線未在 Nov 12 前恢復，Oct 13 叢集的 20D outcome 就永久失去了（除非 Neon DB 有資料）。

**Q11: AUTH01 授權後，立即可以執行哪些步驟？**  
A11: (1) 執行 `backfill_daily_prices.py --start 2026-10-29 --end 2026-11-03 --research-only --execute`；(2) 對每個回填日期執行 QG 驗證（確認 ≥300 stocks）；(3) 重新執行 `build_strict_recovery_readiness()` 確認 proxy counts 更新；(4) 確認 Oct 21/22/28 叢集升格為 STRICT。**不包括**：計算新的 6-cluster baseline（需要另一個授權）。

**Q12: P1 回填為何只包含 Oct 29/30/Nov 02/03，而不包含 Oct 08/15/19/20/27？**  
A12: P1 是「叢集關鍵」日期——這 4 天直接影響 Oct 21/22/28 叢集的 TSMC proxy count，決定它們能否升格為 STRICT。P2 (Oct 08/15/19/20/27) 只是「覆蓋改善」，不影響任何 active 叢集的嚴格性判定，優先級較低。如果時間和 API 配額有限，應優先 P1。

**Q13: CalendarContractIntegration 物件不修改 S46 是否足夠？**  
A13: 目前是足夠的。S49 建立了一個覆蓋層：所有新的分析應使用 `pipeline_recovery_s49.get_corrected_calendar_exit()` 而非 S46 的 `_CALENDAR_5TD`/`_CALENDAR_20TD`。S46 原始模組保留是為了不改變其研究血統記錄。未來正式修正 S46 應在獨立 session 中授權，並更新所有依賴該模組的測試。

**Q14: 5D window 內的 TSMC presence 與 proxy count 的關係是什麼？**  
A14: 兩者是不同的概念。5D window 內的 TSMC presence 是「持有期間內哪些日期有 TSMC 收盤價」（影響 exit price 的可用性）。Proxy count 是「fill_date 之後所有 TSMC-present 日期的總數」（STRICT 資格判定標準）。Oct 13 fill 的 5D window 內只有 2/5 天有 TSMC，但 proxy count = 7，因為 Oct 14/16/21/22/28/Nov04/05 都有 TSMC 資料，可用作替代出場日期。

**Q15: G04 FAIL 的「有效樣本數」計算結論是什麼？**  
A15: 相鄰重疊 80% 意味著相鄰叢集的報酬高度相關（r ≈ 0.8）。有效樣本數 = N / (1 + (N-1)×r)。N=3：有效 N ≈ 1.15；N=6：有效 N ≈ 1.09。標準 t 檢定將 N=3 視為 3 個獨立觀察，高估統計效力約 2.6 倍。已公佈的 p=0.58 已不支持顯著性聲明；修正後更無意義。

**Q16: 為什麼 20D 資料不能解決 G03/G04 問題？**  
A16: 20D 資料是同一批叢集（6 個 fill dates）的更長持有期指標，不增加獨立叢集數量。G03 要求 ≥10 個不相關叢集，20D 不改變叢集數。G04 要求相鄰視窗 < 30% 重疊，這由 fill date 間距決定，20D 視窗反而更長、更容易重疊。

**Q17: S49 的兩個研究模組分別做什麼？**  
A17: `source_verification_s49.py`：(1) 11 日期的歷史資料來源驗證矩陣；(2) BackfillAuthorizationPackage（AUTH01）；(3) 臨時 SQLite 冪等性模擬。`pipeline_recovery_s49.py`：(1) 10 個管線恢復場景（臨時 SQLite）；(2) S46 日曆合約修正覆蓋層；(3) 嚴格叢集恢復就緒狀態；(4) AUTH01+AUTH02 授權包。

**Q18: S49 測試套件新增了哪些覆蓋？**  
A18: 143 個新測試（TC01–TC35），覆蓋：(1) Source matrix 11 筆記錄驗證；(2) Backfill readiness 分類；(3) 衝突風險分類；(4) 生產 DB 現有計數；(5) 叢集升格影響；(6) 授權包結構；(7) 安全限制；(8) 冪等性模擬；(9) 回填後 proxy count 計算；(10) 升格摘要；(11) 10 個恢復場景（SC01–SC10）各自通過；(12) 日曆修正記錄；(13) 20D/5D 日期修正；(14) Strict readiness（有無回填）；(15) AUTH01/AUTH02 狀態；(16) 生產指紋未變。

**Q19: 什麼情況下 ACTIVATION_BLOCKED 可以解除？**  
A19: 解除需要全部達成：(1) G03 通過（≥10 strict clusters，需要 4+ 額外週的資料）；(2) G04 通過（相鄰視窗 < 30% 重疊，需要設計變更）；(3) 統計顯著性達到 p < 0.05；(4) 授權過的 20D outcome 支持長期持有的可行性；(5) Production Neon 有完整的前瞻性資料。目前最快的路徑是 P1 回填 → 管線修復 → 等待 4-6 週 → 重新評估。

**Q20: Session 50 最小可行建議為何？**  
A20: 見「Session 50 最小可行建議」一節。

---

## Key Numbers Summary

| Metric | Value |
|---|---|
| Backfill candidates | 11 |
| INSERT_ONLY candidates | 9 |
| UNIVERSE_UNVERIFIED | 2 (Nov 06/09) |
| Strict clusters (now) | 3 (unchanged) |
| Strict clusters (after P1) | 6 (projected) |
| Grand mean delta | +0.81 pp (unchanged) |
| 20D earliest exit | 2026-11-12 (corrected) |
| 20D latest exit | 2026-11-25 (corrected) |
| Recovery scenarios | 10/10 ALL_PASS |
| Calendar 5D errors (S46) | 3/6 |
| Calendar 20D errors (S46) | 6/6 |
| New tests (S49) | 143 |
| Total tests | 3012 passed, 1 skipped |
| AUTH01 status | PENDING |
| AUTH02 status | BLOCKED_PIPELINE |

---

## Production Fingerprints (All Unchanged)

| Item | Value |
|---|---|
| `forward_signals` total | 2605 |
| `daily_prices` max | 2026-11-05 |
| Baseline fingerprint | `09c04e8c4059d87e` |
| V3 Parameter Hash | `be43e8ca977d9fdd` |
| Crontab Hash | `3acaf480cb5dcdd44f40dd9d464955a1` |
| SESSION | 49 |

---

## Session 50 最小可行建議

### Priority 1: AUTH01 授權 + 執行 P1 回填

**目標：** Oct 29/30/Nov 02/03 回填至 local SQLite  
**方法：** `backfill_daily_prices.py --start 2026-10-29 --end 2026-11-03 --research-only --execute`  
**預期：** Strict count 3→6；Oct 21/22/28 升格為 STRICT  
**條件：** TWSE single-stock API 可用（TSMC Oct 29/30 收盤價已確認）

### Priority 2: 管線修復

**目標：** 修復 Nov 06+ 管線，確保 Nov 12 前有 Oct 13 叢集的 20D 出場資料  
**調查：** (a) Nov 06 QUALITY_GATE_FAIL 根本原因；(b) Nov 09 PROVIDER_NOT_READY 根本原因  
**時間限制：** Nov 12 是 Oct 13 fill 20D 成熟日（3 個交易日後）  
**風險：** 若管線未在 Nov 12 前修復，Oct 13 20D outcome 永久不可計算

### Priority 3: 20D 授權 (AUTH02)

**前提：** Priority 2 完成 + Nov 12–25 資料確認 ≥ 300 stocks  
**目標：** 計算 Oct 13/14/16（+21/22/28 if P1 完成）的 20D return  
**注意：** G03/G04 仍 FAIL；結果仍為 SIGNIFICANCE_INCONCLUSIVE

### Priority 4: G04 設計決策

**選項：** (a) Weekly-spaced fills（G04≈0% 但累積慢）；(b) Bootstrap CI（需 G03 先修復）  
**行動：** 討論並決定設計路徑，不需立即實作

### Do NOT do in S50 without explicit authorization
- Activate V3 / ACTUAL / PAPER trading
- Modify Production Decision Center or v8.0 rules
- Modify `prospective_comparison_s46.py` (需獨立授權)
- Modify V3 parameter hash `be43e8ca977d9fdd`
- Push to Neon production
