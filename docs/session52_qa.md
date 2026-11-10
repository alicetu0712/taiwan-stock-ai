# Session 52 Q&A — 20 Questions

**Session**: S52  
**Analysis date**: 2026-11-10

---

**Q01: Nov 06 QG_FAIL 的直接證據是什麼？**  
A: 兩層證據。(1) `hybrid_cron_postwindow_acceptance_2026_11_06.md` 確認 `hybrid_cron.log` 在 23:03 CST 後不存在——cron `>>` 重定向在腳本無輸出時仍會建立檔案，故缺失即確認未執行（DIRECTLY_CONFIRMED）。(2) Nov 09 backfill 重試時，Nov 06 以 `quality gate FAILED — not writing to DB` 失敗，含義是 TWSE bulk 返回的 Nov 06 資料 coverage 不足（<5000 stocks）。第一層是 CRON_NO_TRIGGER 的直接證據；第二層是 backfill 後續嘗試的直接證據。

**Q02: Nov 09 STALE_DATA 的直接證據是什麼？**  
A: `hybrid_cron.log` 中 4 次重試都記錄：`2026-11-09: TWSE api_date=2026-11-06 != target — API returned wrong date`。每次 backfill 在 1–2 分鐘內完成後，cron 以 PROVIDER_NOT_READY 狀態等 30 分鐘。3 次重試後以 BLOCKED_STALE_DATA 結束，時間 09:35:14Z。`.cron_state.json` 確認最終狀態。全部 DIRECTLY_CONFIRMED。

**Q03: Scheduler 未觸發是否已被直接證明？**  
A: 是，對 Nov 06。`hybrid_cron.log` 在 Nov 06 23:03 CST 後仍不存在，而該檔案在 Nov 09 cron 執行時立即建立——確認 `>>` 重定向機制正常運作。Nov 06 cron 未執行是 DIRECTLY_CONFIRMED。macOS scheduler 為何不執行（電源管理？Full Disk Access 問題？）仍 ROOT_CAUSE_INCONCLUSIVE（Stage B Probe NOT AUTHORIZED）。

**Q04: Pipeline Root Cause 哪些已確認、哪些仍是推測？**  
A: **DIRECTLY_CONFIRMED**：Nov 06 cron 未觸發；Nov 09/10 TWSE bulk api_date 偏移一個交易日；Nov 06 backfill coverage QG 失敗（Nov 09 重試時）；Nov 09/10 backfill QG-5 失敗（api_date 不符）。**HYPOTHESIS_ONLY**：Nov 06 coverage QG 的具體子項目（S38 reclassification？API 部分回應？）；macOS cron 未執行的根本原因；TWSE bulk API 為何總是返回前一日資料。

**Q05: 六個歷史 Fill Clusters 的 V3 Provenance 各是什麼？**  
A: 六個均為 BASE_SIGNAL_PROSPECTIVE。v8.0 訊號在 execution_date 前 locked（所有 `first_locked_at < execution_date`）。V3 決策層從未為這些日期生成。Fill dates 已更正為 Oct 13/14/16/21/22/28（S51 記憶體錯誤記為 Oct 27）。

**Q06: 哪些只有 Base Signal 事前存在？**  
A: 全部六個。Oct 13 訊號在 Oct 12 06:42 鎖定；Oct 14 在 Oct 12–13 鎖定；Oct 16 在 Oct 14 鎖定；Oct 21 在 Oct 16 鎖定；Oct 22 在 Oct 21 鎖定；Oct 28 在 Oct 21 鎖定。全部在 execution_date 前。

**Q07: 是否有任何完整 V3 Decision 在結果前固定？**  
A: 否。V3 從未啟用。`hybrid_forward_decision` 的 21 筆記錄使用 `rule_version='hybrid_v1'`，於 Nov 04 手動生成，分類為 RETROSPECTIVE_RECONSTRUCTION（pre RULE_FREEZE_DATE）。V3_DECISION_PROSPECTIVE count = 0。

**Q08: S36 與 S45／46 的 Prospective 矛盾如何解釋？**  
A: S36 正確識別 `hybrid_forward_decision` 21 筆為 RETROSPECTIVE_RECONSTRUCTION（Nov 04 手動生成）。S45/46 的 "ALL_GENUINE_PROSPECTIVE" 標籤針對的是 BASE SIGNAL 層（v8.0 訊號時間戳），而非 V3 DECISION 層。兩者都正確——它們描述不同的分析層。S52 形式化了這個分離：BASE_SIGNAL_PROSPECTIVE 確認；V3_DECISION_PROSPECTIVE 仍為 0。

**Q09: Recorder 是否真正具備 Append-only 行為？**  
A: 技術上是透過 convention + fingerprint 而非 DDL 強制。`INSERT OR IGNORE` 防止重複插入。但 SQLite 本身沒有阻止 `UPDATE` 或 `DELETE` 的機制——任何有檔案存取權限的程序都可以修改資料庫。防護機制是：每筆記錄都有指紋，`verify_all()` 可偵測事後修改。RIT-11 測試確認：`UPDATE` 後 `verify()` 失敗。

**Q10: `register()` 連續呼叫是否都正確？**  
A: 是。已於 S51 修正 `cursor.rowcount == 1`（舊版使用 `total_changes` 累積值）。RIT-02 和 RIT-03 確認：同一 payload 連續 3 次呼叫分別返回 `True, False, False`。TC18 有獨立的重複插入測試。

**Q11: Recorder 是否能偵測 Payload／Timestamp／Hash 竄改？**  
A: 是，對包含在 fingerprint 中的欄位。RIT-04（payload mutation）、RIT-05（locked_at tampering）、RIT-06（code_commit_hash）、RIT-07（parameter_hash）均 PASS。注意：`registered_at` 也在 fingerprint 中（測試 TC21 修正了此認識）。`input_snapshot_fingerprint` 不在 decision fingerprint 中——需獨立驗證。

**Q12: Recorder 的不可變性限制是什麼？**  
A: 五個主要限制：(1) Local SQLite 不具外部不可變性；(2) hash 不等於可信時間戳記；(3) Git commit hash 不能獨立證明執行版本；(4) Mock recorder 不等於正式前瞻性樣本；(5) 無 RFC 3161 TSA = 無強不可否認性。

**Q13: Calendar SSOT 是否覆蓋所有實際 Research Call Sites？**  
A: 是。9 個 call site 全部審計完畢。4 個 LEGACY_FROZEN（S46–S49，不修改）；2 個 SSOT_COMPLIANT（S50 本身和 S52 新模組）；3 個 NO_TRADING_DAY_OFFSET（S51 和 S52 新模組無曆法計算）。無 LEGACY_ACTIVE_BUG。

**Q14: S46 錯誤 5D／20D 日期是否已完全隔離？**  
A: 是。S46 erroneous dates 只存在於凍結的 `prospective_comparison_s46.py` 中。該模組不被任何活動研究路徑呼叫。S50 SSOT 有修正值（Δ從 -2d 到 -7d）。TC26、TC27、TC28 確認正確值。

**Q15: Prospective Collection Protocol 是否已事前固定？**  
A: 是，所有必要欄位均在 S52 session start（2026-11-10）固定於 `CollectionPreRegistration`。Collection 本身因管線未恢復和 V3 未啟用而 BLOCKED。Protocol 預先登記完成；Collection 等待解除阻塞。

**Q16: G03／G04 是否仍 FAIL？**  
A: 是。G03 FAIL：V3_DECISION_PROSPECTIVE = 0，需要 10。G04 FAIL（結構性）：5D window + ≤5TD 間距 = 重疊保證。現有 Oct 13–28 歷史資料無法修復 G04；需要新叢集以 ≥6TD 間距蒐集。

**Q17: Oct 29–Nov 09 的價格資料距離可安全回填還缺什麼？**  
A: (1) AUTH01 授權（所有 6 個 PENDING 日期）；(2) Nov 06 coverage QG 問題的根因——需了解為何 TWSE bulk Nov 06 資料 <5000 stocks，或改用 single-stock API 回填；(3) Nov 09 需等待 TWSE bulk API 更新或改用 single-stock API；(4) Corporate actions 核實；(5) Quality gate 驗證通過。

**Q18: AUTH01／AUTH02 是否仍未授權？**  
A: AUTH01 = PENDING（6 日期待授權）；AUTH02 = NOT_AUTHORIZED（20D 結算計算）。兩者均需顯式用戶授權。

**Q19: Production、Cron、ForwardSignals、Frozen Strategies 是否完全未變？**  
A: 是，全部確認。ForwardSignals = 2605 total（v8.0 valid = 2236，與 S51 一致）；daily_prices max = 2026-11-05；v8.0 buy+strong_buy = 237；Nov 06/09 non-0050 rows = 0。Cron 仍為 `0 16 * * 1-5`，S52 未修改。Production MODEL_VERSION v8.0、foe_v1、Hybrid P1–P4、V3 frozen parameters——均未觸碰。

**Q20: Session 53 最小可行且最值得優先執行的工作是什麼？**  
A: **S53 最高優先（唯一需要用戶決策的）**：(1) **AUTH01 授權**：決定是否授權 Oct 29/30, Nov 02/03, Nov 06, Nov 09 回填。這是唯一能解開後續所有工作的前提。(2) **Pipeline 修復授權**：決定是否授權改用 single-stock API（~600 calls/day）以繞過 TWSE bulk api_date 偏移問題。**S53 research-only 工作（無需新授權）**：(3) Nov 06 coverage QG 子項目診斷——讀取 backfill 腳本 QG 邏輯，確認哪個子檢查失敗；(4) 更新記憶體中的 fill dates（Oct 27 → Oct 16）。
