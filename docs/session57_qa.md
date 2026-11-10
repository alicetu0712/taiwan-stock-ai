# Session 57 — 20 Final Questions

## Q1: TWSE_HIST_URL 是否能提供歷史 OHLCV？

**A**: 否。S57 live probe 確認：針對 Oct29 和 Nov04 各進行 3 次重試，全部回傳非 JSON（空 body，`JSONDecodeError: Expecting value: line 1 column 1`）。此 endpoint 對近期日期完全無法使用（RC-01 DIRECTLY_CONFIRMED）。

---

## Q2: TWSE_LATEST_URL 是否能提供歷史 OHLCV？

**A**: 否。S57 probe 確認：無論何時查詢，api_date 永遠是最新交易日（2026-11-09，即昨日）。可提供當日完整 OHLCV（1241 stocks），但無法查詢歷史日期（RC-02 DIRECTLY_CONFIRMED）。

---

## Q3: TWSE_SINGLE_STOCK 是否能提供歷史 OHLCV？

**A**: 是。S50 Session 50 已驗證：Oct29 的 2330/2454/2317 均有完整 OHLCV+volume；Oct30/Nov02/Nov03 也各有確認記錄。歷史日期功能已驗證（FEASIBLE_VERIFIED）。但費率限制（2s/request）與 TWSE 使用條款尚未正式確認。

---

## Q4: TPEx_HIST_URL 是否能提供歷史 OHLCV？

**A**: 否。S57 live probe 鐵證確認（RC-03 DIRECTLY_CONFIRMED）：
- 請求 d=1151029（Oct29）→ api_date=2026-11-10（今日）
- 請求 d=1151104（Nov04）→ api_date=2026-11-10（今日）
- 兩次請求完全相同的 api_date，與 d= 參數無關
- 此 endpoint 設計上只返回最新市場資料，`?d=` 參數被完全忽略

---

## Q5: TPEx volume 為什麼全部是 NULL？

**A**: 這是 TPEx `tpex_mainboard_daily_close_quotes` endpoint 的設計限制。5737 筆記錄中，volume=NULL 為 ALL，與請求日期無關。此 endpoint 名稱本身（"close_quotes"）即暗示只返回收盤資料。Nov04 的 5715 null volume rows 就是 TPEx records 的結構性特徵，非資料錯誤。

---

## Q6: 完整市場恢復需要多少時間？

**A**: 使用 TWSE_SINGLE_STOCK（T2 tier）：
- 每日 ~1969 requests × 2s = ~65.6 分鐘
- 6 個 gap dates（Oct29/30/Nov02/03/Nov06/09）= 393.6 分鐘 = **~6.6 小時**
- 包含 Oct08/15/19/20/27（5個歷史補充日）：再加 ~5.5 小時 = ~12 小時總計
- 風險：IP throttle 可能，TWSE rate limit 政策未確認

---

## Q7: AUTH01 授權後能達到多少覆蓋率（僅 S50 資料）？

**A**: 若只插入 S50 研究快照：
- Oct29: 6/1969 = 0.30%
- Oct30: 2/1969 = 0.10%
- Nov02: 1/1969 = 0.05%
- Nov03: 1/1969 = 0.05%
- **Quality Gate 無任何改變**（遠低於任何 QG 閾值）

若執行完整 T2 恢復：~1969/1969 = ~100% TWSE ordinary coverage（TPEx 普通股另計）。

---

## Q8: S55/S56 有哪些 S50 資料錯誤需要更正？

**A**: 三個錯誤：
1. **Oct29 筆數**：S55/S56 聲稱 3 筆 CLOSE_ONLY；實際 `_VERIFIED_RECORDS` 有 6 筆，其中 3 筆 (2330/2454/2317) 有完整 OHLCV+volume
2. **Nov03 2317 close**：S55/S56 用 245.0；實際 245.5（+0.2% 誤差）
3. **Nov09 2330 close**：S56 用 2200.0；實際 2235.0（+1.6% 誤差）
這些誤差不影響 AUTH01_PARTIAL 判定，但影響任何以此為基準的報酬率計算。

---

## Q9: Nov04 為什麼有 6957 筆但 881 筆 ordinary stock volume 為 NULL？

**A**: 兩個獨立原因：
1. **5715 筆 TPEx records**：全部 volume=NULL（endpoint 設計限制）
2. **881 筆 ordinary 4-digit stocks**：部分 TWSE 普通股可能在 Nov04 無成交（停牌/低流動性）；volume=NULL/0 反映真實市場狀態，非資料錯誤
3. **正確** denominator: 1969 ordinary stocks；不應包含 4829 warrants

---

## Q10: Nov06/09 DATE_MISSING 的根本原因是什麼？

**A**: RC-04（SCHEDULER_NOT_TRIGGERED）STRONGLY_SUPPORTED：
- Nov06/09 在 `daily_prices` 中完全無資料（連 0050 都沒有）
- S50 研究快照確認這兩天是有效交易日（2330/2454 有收盤價）
- Nov04/05 相鄰日期有 6957/6589 筆資料，排除普遍停機
- 結論：cron job 在 Nov06/09 未執行，或執行時遇到未捕捉的例外而靜默失敗

---

## Q11: Oct29/30/Nov02/03 只有 benchmark 的根本原因是什麼？

**A**: RC-05（SUFFICIENT_EVIDENCE）：pipeline 在這些日期有執行（1 筆 0050 存在），但普通股 fetch 失敗。最可能的子原因（RC-02）：date validation guard 拒絕了 TWSE_LATEST_URL 的資料，因為 api_date=T-1 ≠ target_date=T，而 0050 可能來自不受此 guard 管制的獨立路徑。

---

## Q12: TPEx Patch 授權後能解除哪些問題？

**A**: TPEx patch（B02）解除後：
- TPEx api_date mismatch 錯誤進入 `summary["errors"]`（可監控）
- 不改變任何 price_rows 或 provider_requests
- 不恢復歷史 TPEx 資料（RC-03 是 endpoint 設計問題）
- 不解除 B01/B03/B04/B05/B07/B08
- 不影響 G03/G04/Canonical V2/Coverage Gate

---

## Q13: 完整恢復後 Quality Gate 狀態是什麼？

**A**:
- G01 Data Coverage：PASS expected（6 gap dates recovered）
- G02 Signal Coverage：CONDITIONAL（取決於信號日期的 coverage）
- G03 Genuine Prospective：**FAIL（0/10）——完全不受影響**
- G04 Weekly Spacing：**STRUCTURAL_FAIL——完全不受影響**
G03 和 G04 只能通過 V3 啟用和演算法修改解決，與資料恢復無關。

---

## Q14: 為什麼 historical backfill 無法貢獻 genuine prospective evidence？

**A**: Genuine prospective 的定義要求：在 outcome 日期**之前**做出的決策，並有 pre-outcome timestamp 記錄。AUTH01 是歷史回填（現在插入過去的價格資料）。任何以這些歷史資料產生的 V3 "決策" 都是 retrospective reconstruction，永遠不計入 genuine prospective N。這是定義上的約束，非工程問題。

---

## Q15: 研究覆蓋率計算的正確 denominator 是什麼？

**A**: **1969**（Nov04 actual ordinary 4-digit stock count）
- 錯誤：6957（包含 4829 warrants + 159 ETFs）
- 錯誤：6978（TWSE 1241 + TPEx 5737，包含重複和非普通股）
- 正確：1969（1000-9999 prefix, Nov04 reference）
- 官方：1996（S38 official ordinary stock universe；1969 比官方少 27，正常市場流轉）

---

## Q16: Nov04 的 Warrant 污染比例是多少？

**A**: (4816 + 13) / 6957 = **69.4%**。七成資料是認購/認售權證（7xx prefix）和優先股（02x prefix）。研究分析必須過濾 warrants，否則覆蓋率計算和 universe 統計都會嚴重失真。

---

## Q17: 20D 計算截止日是什麼？有多緊迫？

**A**: Oct13 cluster execution_date=2026-10-14，20 trading days → maturity ~2026-11-12。今天是 2026-11-10，還剩 **2 個交易日**。AUTH02 是最緊迫的授權請求。如果 Nov12 前未授權，結果仍可在 Nov12 後計算（使用 Nov12 收盤價），但 window 已是當下活躍狀態。

---

## Q18: S57 研究模組是否改變任何正式生產系統？

**A**: 否。S57 新增了兩個 research module（`market_ohlcv_source_verification_s57.py`、`market_coverage_recovery_s57.py`）和一個 test 檔案，全部為 research-only。

Production system 狀態驗證：
- daily_prices max: 2026-11-05（不變）
- Oct29 non-0050 rows: 0（不變）
- Crontab hash: 3acaf480cb5dcdd44f40dd9d464955a1（不變）
- V3 params: be43e8ca977d9fdd（不變）
- Canonical V2 FP: 6a133e8cca47bcb25bbc528557e4a00efa2c91e387158c208aef6d2d0dbecf8f（不變）

---

## Q19: 有哪些需要獨立授權的次要決策？

**A**: 四項獨立授權，優先級由高到低：

1. **AUTH02（最緊迫）**：20D outcome 計算，Oct13 cluster ~Nov12 到期
2. **TPEx Patch**：2 行修改，低風險，永久性 TPEx 錯誤觀測能力
3. **AUTH01**：歷史回填，需先確認 TWSE rate limit 政策和完整 OHLCV 來源
4. **Stage B Cron Probe**：V3 genuine prospective 啟動（S36 明確拒絕；需新決策）

---

## Q20: Session 58 應優先做什麼？

**A**: 建議的 Session 58 議程（依優先級）：

**立即可執行（無需新授權）**：
- 無（所有進一步工作都需要至少一項授權）

**授權後立即可執行**：
1. AUTH02 → 執行 Oct13 20D outcome 計算（2 trading days window）
2. TPEx patch 授權 → 部署 L500-503 修改
3. AUTH01 完整版 → 先確認 TWSE rate limit policy，再規劃分階段 T2 恢復

**需要新決策**：
4. Stage B Cron Probe 重新評估（S36 拒絕；是否改變決策？）
5. Pipeline reliability 修改授權（HC-01 to HC-06 實作）
