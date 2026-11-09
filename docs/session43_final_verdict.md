# Session 43 Final Verdict — Execution-Date Integrity & Comparable Evidence Expansion

## Core Question

**V3 是否真的比 V1/V2 更好？**  
Session 43 verdict: **INSUFFICIENT_EVIDENCE**

---

## 20 Final Questions & Answers

### Q1. 為什麼 Oct 14 信號的 execution_date 是 Oct 16？這是資料錯誤還是正確行為？

**A**: 正確行為。Oct 15 是「thin day」——`daily_prices` 中只有 0050 一檔股票有資料。NEXT_OPEN pipeline 掃描各股股票的 `daily_prices`，找不到 Oct 15 的收盤價，因此跳到 Oct 16。這不是錯誤，而是系統正確地跳過只有 ETF 資料的日子。

---

### Q2. 為什麼 Oct 16 信號的 execution_date 是 Oct 21？跳過了哪些日期？

**A**: 跳過了 Oct 17（無一般股票資料）、Oct 18（週六）、Oct 19（thin day, 只有 0050）、Oct 20（thin day, 只有 0050）。Oct 21 是第一個有一般股票開盤價的交易日，因此 execution_date = Oct 21。

---

### Q3. 所有非交易日信號（Oct 09-11）的根本原因是什麼？

**A**: 所有 107 筆信號都是 model version v6.0，原因分三個：
- Oct 09（99 筆）：v6.0 cron 在 Oct 08 晚間執行，預判 Oct 09 為下一交易日，但 Oct 09 是補假日（國慶日前一天補假）
- Oct 10（4 筆）：v6.0 cron 在國慶日當天（Oct 10，週六）執行
- Oct 11（4 筆）：v6.0 cron 生成了 Oct 11（週日）的信號

v8.0 有 calendar guard，不會在非交易日生成信號。

---

### Q4. v6.0 信號排除後，剩餘的 v8.0 信號有多少？分佈如何？

**A**: v8.0 信號共 237 筆（所有訊號日期），其中：
- 嚴格可比（strict）：128 筆（Oct 12/13/14 信號日期，對應 fill Oct 13/14/16）
- 條件可比（conditional）：39 筆（Oct 16 信號日期，fill Oct 21，出場資料不完整）
- 合計：167 筆

---

### Q5. FillDateComparisonContract 的嚴格配對條件是什麼？Oct 16 為什麼是 conditional 而不是 strict？

**A**: 嚴格條件：(1) v8.0 模型、(2) execution_date 為真實交易日（≥50 股）、(3) 每檔股票在 fill_date 後有 5 個完整出場日。Oct 16 信號 fill Oct 21，而 Oct 21 之後只有 4 個交易日（Oct 22, Oct 28, Nov 04, Nov 05），第 5 個出場日（Nov 06+）超出 `daily_prices` 範圍，故為 conditional。

---

### Q6. S43 嚴格版 5D 比較的結果是什麼？與 S42 有何不同？

**A**:
- S43 strict（3 clusters，fill Oct 13/14/16）：D_v3 vs A_direct 大均值 **+0.81%**，CI ≈ [−1.4%, +3.0%]，p ≈ 0.37，**SIGNIFICANCE_INCONCLUSIVE**
- S42（5 clusters，混合 v6.0+v8.0）：+1.21%，SIGNIFICANCE_INCONCLUSIVE
- 差異：fill Oct 12 的 v6.0 cluster delta 為 +2.62%，拉高了 S42 的均值。移除後，真實 v8.0 表現為 +0.81%。兩者同樣不顯著。

---

### Q7. 為什麼 fill Oct 12 cluster 的 delta 高達 +2.62%？是真實的 V3 優勢嗎？

**A**: 不是。fill Oct 12 cluster 的信號全是 v6.0（Oct 09-11 非交易日信號）。這些信號在不同市場狀況（國慶日前後）、不同模型下生成，與 v8.0 的比較基礎不同。+2.62% 反映的是 v6.0 信號的歷史特性，不能歸因於 V3 策略的優勢。

---

### Q8. 什麼是 comparable evidence expansion？是否找到新的可用窗口？

**A**: Comparable evidence expansion 是系統性地搜尋除 Oct 2026 以外的額外比較窗口。Session 43 檢查了 3 個候選窗口：(1) Oct 2026（已分析，CONDITIONAL）、(2) Oct 2026 以前假設性窗口（INELIGIBLE，無前瞻性信號）、(3) Nov-Dec 2026 未來（INELIGIBLE，出場資料不足）。結論：**NO_NEW_ELIGIBLE_WINDOW**，新增獨立觀測數 = 0。

---

### Q9. 為什麼不能從 backtest 資料重建歷史信號？

**A**: 因為 V3 參數（閾值、權重）是在歷史資料上優化的。用這些參數對歷史重建信號，等同於 in-sample 測試，不是 out-of-sample。這會引入 look-ahead bias，膨脹表現。唯一有效的比較基礎是 Oct 2026 開始的前瞻性信號。

---

### Q10. G01 guardrail 修復了多少？為什麼還是 CONDITIONAL 而非 PASS？

**A**: G01 從 FAIL 升至 CONDITIONAL。修復：排除 v6.0 信號後，v8.0 strict pool 中非交易日信號比例 = 0%。尚未 PASS 的原因：交易日曆的來源（`SELECT DISTINCT date FROM daily_prices`）仍包含 thin days（只有 0050 的日子）。要達到 PASS，需要將曆法定義改為「當天 ≥50 股有資料」的門檻。

---

### Q11. G03 和 G04 為什麼無法修復？

**A**:
- **G03（cluster 數 ≥5）**：strict 分析只有 3 個完整 cluster，遠低於門檻。唯一解法是等 cron 累積更多月份的信號——無法從現有資料中憑空製造 cluster。
- **G04（window overlap <50%）**：相鄰 fill 日期的 5D 窗口重疊 ~80%。這是每日生成信號 + 5D 持有期的結構性限制，無法事後修正。

---

### Q12. 20D 窗口何時才能使用？目前進度如何？

**A**: 截至 Nov 09 2026，`daily_prices` 最新日期為 Nov 05（TSMC）。fill Oct 13 需要 20 個交易日出場，目前約有 15 個可用，預計 Nov 25 左右才能完整。fill Oct 21 預計 Dec 04。**目前 NOT_READY_FOR_20D**，4 個 fill clusters 均未成熟（0/4）。

---

### Q13. 目前的執行架構（NEXT_OPEN SIMULATED）與實際交易的差距是什麼？

**A**: 差距有三層：(1) **價格**：用的是開盤價，真實交易受到市場衝擊、流動性影響；(2) **填單時間**：NEXT_OPEN 假設以當日開盤即能成交，實際下單需排隊；(3) **滑價**：未計入。這些差距在台灣流動性強的大型股較小（如 2330 TSMC），但對中小型股影響顯著。V3 建議的性能聲明應標注「SIMULATED_FILL，非實際成交」。

---

### Q14. D_v3 vs B_v1v2 的 strict 結果是什麼？能說 V3 比 V1/V2 更好嗎？

**A**: D_v3 vs B_v1v2 strict 3-cluster 大均值 ≈ **−0.14%**，CI 包含 0，p >> 0.1，**SIGNIFICANCE_INCONCLUSIVE**。V3 甚至略遜於 V1/V2（但差異統計上不顯著）。目前無法聲稱 V3 比 V1/V2 更好。

---

### Q15. 要得出 V3 優於 A_direct 的初步結論，最低需要什麼條件？

**A**: 至少需要：(1) 7+ 個嚴格可比 fill clusters；(2) window overlap < 50%（需要週期 ≥ 2 週以上的信號間距）；(3) 95% CI 不包含 0；(4) 至少一個 out-of-sample 時間段（非 Oct 2026）。在此之前，所有結論均為「不足以判斷」（INSUFFICIENT_EVIDENCE）。

---

### Q16. thin day 的定義是什麼？有哪些 thin days？

**A**: 「Thin day」= `daily_prices` 中某日只有 ≤49 個不同股票有資料（通常只有 ETF 如 0050）的日子。Oct-Nov 2026 的 thin days：Oct 15, 19, 20, 27, 29, 30, Nov 02, 03（均為 0050-only）。這些日子在技術上市場有開盤，但一般股票沒有價格資料。

---

### Q17. locked_at 欄位在訊號日期異常中扮演什麼角色？

**A**: `locked_at` 是 signal 寫入 DB 的 UTC 時間戳。對於 Oct 09 信號，`locked_at ≈ 2026-10-08`（前一天晚間），顯示 cron 在 Oct 08 執行，預判 Oct 09 為下一交易日。這是 v6.0 cron 的 day-ahead labeling 機制——不看行事曆，直接假設 trade_date = run_date + 1。v8.0 修正了這個問題。

---

### Q18. evidence quality 的整體評分是多少？主要瓶頸是哪兩個維度？

**A**: S43 mean score = **5.15/10**（S42 為 3.55/10，提升 +1.60）。主要瓶頸：
- **STATISTICAL_POWER** (2.5/10)：N=3 clusters 嚴重不足
- **WINDOW_INDEPENDENCE** (2.0/10)：80% 重疊違反獨立性假設

這兩個維度無法透過分析技巧改善，只能靠資料累積和設計變更解決。

---

### Q19. Session 43 完成後，V3 啟用的阻礙清單有哪些更新？

**A**: Session 43 修復的項目：移除 v6.0 污染（evidence quality 提升）、正式化 execution date 語意定義。**仍未解除的阻礙**：
1. CRON_FROZEN（Stage B 未授權）→ 仍 BLOCKED
2. G03 cluster 數不足（3 < 5）→ 仍 FAIL
3. G04 window overlap（80%）→ 仍 FAIL
4. SIGNIFICANCE_INCONCLUSIVE（N=3, p>0.3）→ 仍不顯著
5. 20D 窗口未成熟（NOT_READY）→ 仍 BLOCKED
6. NO_NEW_ELIGIBLE_WINDOW → 無新證據

V3 啟用狀態：**ACTIVATION_BLOCKED**，所有阻礙均與 Session 42 相同，S43 無新解除項目。

---

### Q20. 綜合 S42-S43 的所有修正後，V3 究竟比 A_direct 好多少？

**A**: 在最嚴格的 v8.0-only、3-cluster 分析下，D_v3 vs A_direct 的估計大均值為 **+0.81%**（95% CI: [−1.4%, +3.0%]）。這個數字：
- 比 S40 的 +3.66% 低 78%
- 比 S41 的 +6.49% 低 88%
- 比 S42 的 +1.21% 低 33%
- CI 包含 0，統計不顯著

**答案是：我們不知道**。現有資料不足以判斷 V3 是否真的優於 A_direct。最誠實的陳述是：「在 2026 年 10 月這一個月的 3 個可比 fill-date cluster 中，V3 的平均超額報酬估計為 +0.81%，但置信區間包含 0，結論不確定。」

---

## Final Verdict Enums

```python
class ExecutionIntegrityVerdict(str, Enum):
    EXECUTION_VERIFIED = "EXECUTION_VERIFIED"
    EXECUTION_PARTIAL = "EXECUTION_PARTIAL"      # ← S43: NULL exec for v6.0 signals
    EXECUTION_FAILED = "EXECUTION_FAILED"
    # S43 session verdict: EXECUTION_PARTIAL

class NonTradingDayAuditVerdict(str, Enum):
    DATE_CAUSES_IDENTIFIED = "DATE_CAUSES_IDENTIFIED"   # ← S43
    DATE_CAUSES_PARTIAL = "DATE_CAUSES_PARTIAL"
    DATE_CAUSES_UNKNOWN = "DATE_CAUSES_UNKNOWN"
    # S43 session verdict: DATE_CAUSES_IDENTIFIED

class ComparisonVerdict(str, Enum):
    SIGNIFICANT_POSITIVE = "SIGNIFICANT_POSITIVE"
    SIGNIFICANT_NEGATIVE = "SIGNIFICANT_NEGATIVE"
    SIGNIFICANCE_INCONCLUSIVE = "SIGNIFICANCE_INCONCLUSIVE"   # ← S43
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    # S43 session verdict: SIGNIFICANCE_INCONCLUSIVE (all comparators)

class EvidenceExpansionVerdict(str, Enum):
    NEW_WINDOW_ELIGIBLE = "NEW_WINDOW_ELIGIBLE"
    NEW_WINDOW_CONDITIONAL = "NEW_WINDOW_CONDITIONAL"
    NO_NEW_ELIGIBLE_WINDOW = "NO_NEW_ELIGIBLE_WINDOW"   # ← S43
    # S43 session verdict: NO_NEW_ELIGIBLE_WINDOW

class GuardrailVerdict(str, Enum):
    GUARDRAILS_PASS = "GUARDRAILS_PASS"
    GUARDRAILS_CONDITIONAL = "GUARDRAILS_CONDITIONAL"
    GUARDRAILS_FAIL = "GUARDRAILS_FAIL"   # ← S43 (G03, G04 still FAIL)
    # S43 session verdict: GUARDRAILS_FAIL

class StrategyRankingVerdict(str, Enum):
    V3_CLEARLY_SUPERIOR = "V3_CLEARLY_SUPERIOR"
    V3_MARGINALLY_SUPERIOR = "V3_MARGINALLY_SUPERIOR"
    RANKING_INCONCLUSIVE = "RANKING_INCONCLUSIVE"   # ← S43
    V1V2_MARGINALLY_SUPERIOR = "V1V2_MARGINALLY_SUPERIOR"
    # S43 session verdict: RANKING_INCONCLUSIVE

class RegressionVerdict(str, Enum):
    NO_REGRESSION = "NO_REGRESSION"   # ← S43 (2422 passed, 0 failed)
    REGRESSION_DETECTED = "REGRESSION_DETECTED"
    # S43 session verdict: NO_REGRESSION

class ActivationVerdict(str, Enum):
    ACTIVATION_ELIGIBLE = "ACTIVATION_ELIGIBLE"
    ACTIVATION_CONDITIONAL = "ACTIVATION_CONDITIONAL"
    ACTIVATION_BLOCKED = "ACTIVATION_BLOCKED"   # ← S43
    # S43 session verdict: ACTIVATION_BLOCKED
```

---

## Session 43 Summary

| Deliverable | Status |
|-------------|--------|
| PART B: ExecutionDateIntegrityAuditor | ✓ Complete |
| PART C: NonTradingDayAuditor | ✓ Complete |
| PART D: FillDateComparisonContract | ✓ Complete |
| PART E: CorrectedFiveDayComparisonS43 | ✓ Complete |
| PART F: EvidenceExpansionAuditor | ✓ Complete |
| PART G: GuardrailRemediationReport | ✓ Complete |
| PART H: TwentyDayReadinessReport | ✓ Complete |
| PART I: EvidenceQualityReport | ✓ Complete |
| PART J: Tests (87 tests) | ✓ 87/87 pass |
| PART K: 9 documents | ✓ Complete |
| PART L: 20 Q&A | ✓ Complete |
| PART M: Final Verdict Enums | ✓ Complete |
| Ruff | ✓ All clean |
| Full Regression | ✓ 2422 passed, 0 failed |
| Safety Constraints | ✓ No production modifications |

**Tests**: 2422 (S43 adds 87 new; +87 from S42's 2335)
