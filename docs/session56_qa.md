# Session 56 — 20 Final Questions

## Q1: AUTH01 候選資料是否全部具有逐筆可信來源？

**A**: 否。7 筆記錄（S50 verified）有可信的 CLOSE 來源（TWSE single-stock API）。但：
- OPEN/HIGH/LOW 未驗證（估算值）
- VOLUME 完全缺失
- TPEx 資料為 SOURCE_UNVERIFIED
- Corporate actions 未查核
- 1962/1969 筆普通股仍無來源

AUTH01_PARTIAL 是正確判定。

---

## Q2: Oct29/30、Nov02/03 各有多少筆真正通過驗證？

**A**:
- Oct29: 3 筆（2330=2415.0, 2454=4045.0, 2317=248.0）——Close 已驗證
- Oct30: 2 筆（2330=2370.0, 2454=3915.0）
- Nov02: 1 筆（2330=2330.0）
- Nov03: 1 筆（2317=245.0）
- **合計**: 7 筆，全為 TWSE ordinary stock，CLOSE 已驗證，OHLV 未驗證

---

## Q3: 各日期 TWSE/TPEx Coverage Before/After 是多少？

**A**:
- **Before**: 所有 Oct29/30/Nov02/03/Nov06/09 = 0 ordinary stock（僅 0050 benchmark）
- **After 部分回填 (S50)**: Oct29 = 3/1969 = 0.15%；Oct30 = 2/1969 = 0.10%；Nov02/03 = 1/1969 = 0.05%
- **TPEx coverage**: 全部 UNVERIFIED（0%）
- 結論：S50 資料不足以達成有意義的覆蓋率

---

## Q4: AUTH01 Dry-run 後哪些 Quality Gate 會改變？

**A**: **無任何 QG 改變**。3 筆/1969 = 0.15%，遠低於任何 QG 閾值（需要 100+ 筆才能通過最低 QG）。QG 在所有 P1 候選日期仍為 FAIL。

---

## Q5: 哪些 Quality Gate 仍會失敗？

**A**: Oct29/30/Nov02/03/Nov06/09 的所有 QG 仍然 FAIL。Nov04/05 已通過（現有完整資料）。S50 部分回填對 QG 無實質影響。

---

## Q6: AUTH01 是否具備明確 Target DB、Table、Records 與 Rollback Plan？

**A**: 是。
- Target DB: `data/platform.db`
- Target Table: `daily_prices`
- Target Records: 7 筆（Oct29×3, Oct30×2, Nov02×1, Nov03×1）
- Rollback: DELETE 7 筆（trivial）

**但有關鍵限制**：OPEN/HIGH/LOW 為估算值；VOLUME 缺失；不建議以不完整 OHLCV 寫入正式 DB。

---

## Q7: TPEx Patch 的實際 Diff 是否符合 Session 55 描述？

**A**: 是。S56 直接讀取 `scripts/backfill_daily_prices.py` 確認：
- L494-498：TWSE 段已有 `summary["errors"].append(msg)`（已存在）
- L500-501：TPEx 段仍為 `print()` only（未修補）
- 完全符合 S55 描述的 `PRINT_ONLY_CONFIRMED`

---

## Q8: Patch 是否只改變 Error Reporting？

**A**: 是。15 個模擬情境中，所有 price_rows 和 provider_requests 在 before/after 完全相同。唯一差異：TPEx api_date 錯誤時，after 版本會將錯誤加入 `summary["errors"]`。無 trading logic 變更。

---

## Q9: Patch 是否通過所有隔離情境與 Behavioral Equivalence Tests？

**A**: 是。15/15 scenarios PASS。Behavioral equivalence: price_rows ✓, provider_requests ✓, security_universe ✓, QG_thresholds ✓, retry_count ✓, completion_semantics ✓。無 UNEXPECTED_DIFFERENCE。

---

## Q10: Patch 是否有可驗證的 Rollback Plan？

**A**: 是。Rollback：還原 2 行（刪除 msg 變數 + append 行，恢復原始單行 print）。Risk: LOW。

---

## Q11: AUTH01 Only 能解除哪些 Blockers？

**A**:
- B01（AUTH01 not executed）：PARTIAL（7 rows）
- 其他所有 blockers：不變
- G03：不變（0/10）
- Genuine Prospective N：不變（0）
- Nov06/09 TWSE URL：不變

---

## Q12: Patch Only 能解除哪些 Blockers？

**A**:
- B02（TPEx patch not deployed）：RESOLVED
- 其他所有 blockers：不變
- 覆蓋率：不變（patch 不新增 price rows）
- QG：不變

---

## Q13: Combined Scenario 能否真正解除 B01/B02？

**A**: PARTIALLY。
- B01: PARTIAL（7 rows; full universe still needs new provider calls）
- B02: RESOLVED
- 但 B03/B04/B05/B07/B08/B09 全部不變
- G03/Genuine Prospective N：不變（0）

---

## Q14: B01/B02 解除後是否仍缺乏 Genuine Prospective Decision Evidence？

**A**: 是。Genuine Prospective N 永遠維持 0，直到 V3 genuinely produces pre-outcome timestamped decisions。AUTH01 是**歷史資料回填**，永遠不計入 genuine prospective evidence。

---

## Q15: Canonical V2 是否保持完整可重現？

**A**: 是。S56 重新執行 `build_canonical_baseline_v2()` 確認：
- 兩次執行完全相同 fingerprint：`6a133e8cca47bcb25bbc528557e4a00efa2c91e387158c208aef6d2d0dbecf8f`
- Cluster IDs 穩定
- grand_mean = 0.0081 穩定

---

## Q16: Historical Baseline 是否與 Canonical V2 明確分離？

**A**: 是。
- Historical: `2c8b2475c8fdc457`（16-char truncated，UNRECOVERABLE）
- Canonical V2: `6a133e8cca47bcb25bbc528557e4a00efa2c91e387158c208aef6d2d0dbecf8f`（64-char SHA256，VERIFIED）
- 明確不同，不可互換

---

## Q17: Genuine Prospective N 是否仍為 0？

**A**: 是。V3 shadow 未運行，無 pre-outcome timestamped decisions，無 ProspectiveRecorder 在 production 中運行。N=0 無法被任何回填操作改變。

---

## Q18: G03/G04 是否仍然失敗？

**A**: 是。
- G03: 0/10 FAIL（unchanged from S42）
- G04: STRUCTURAL_FAIL（unchanged）
- 無任何情境在 S56 中改變這兩個數字

---

## Q19: Production、Cron、ForwardSignals、Frozen Strategies 是否完全不變？

**A**: 是，全部驗證：
- Crontab hash: 3acaf480cb5dcdd44f40dd9d464955a1（unchanged）
- ForwardSignals: 2605（unchanged）
- daily_prices max: 2026-11-05（unchanged）
- Oct29 non-0050: 0（production DB unmodified）
- V8.0 rules: unchanged
- V3 params: be43e8ca977d9fdd（unchanged）
- Canonical V2 fingerprint: stable

---

## Q20: Session 57 應優先做什麼？需要哪項獨立授權？

**A**: Session 57 最高價值的優先項目：

**選項 A（短期）**: 授權 TPEx Patch 部署
- 低風險（2 lines，rollback trivial）
- 立即改善 error observability
- 解除 B02

**選項 B（中期）**: 解決 AUTH01 的 OHLCV 問題
- 需要取得完整 OHLCV（非僅 close）的資料來源
- 才能安全執行完整回填

**選項 C（長期）**: 規劃 V3 Genuine Prospective Collection
- 需要 Stage B Cron Probe 授權（此項被明確拒絕，S36）
- 或尋找替代激活路徑

**所需獨立授權**:
1. TPEx patch 部署授權
2. AUTH01 完整 OHLCV 來源獲取授權（若要安全回填）
3. 20D outcome 計算授權（AUTH02，Oct13 cluster 約 Nov12 到期）
