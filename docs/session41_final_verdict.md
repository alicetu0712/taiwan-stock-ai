# Session 41 Final Verdict — Statistical Significance Audit & Performance Attribution

**Date:** 2026-11-09
**Session:** 41
**Tests:** 2273 passed, 1 skipped (+53 from S41)

---

## PART L: 20 Final Questions

### Q1: Session 40 的 SIGNIFICANT_POSITIVE 結論是否通過 Session 41 的驗證？

**否。**所有三個 SIGNIFICANT_POSITIVE 結論均已被降級為 SIGNIFICANCE_INCONCLUSIVE。

Cluster-adjusted analysis（以 trading date 為獨立單位）：
- D_v3 vs A_direct: CI=[-3.95%, +16.93%], p=0.179
- D_v3 vs B_v1v2: CI=[-4.93%, +16.57%], p=0.233
- D_v3 vs C_hybrid: CI=[-3.97%, +16.92%], p=0.180

三者的 CI 均包含零，p 值均遠高於 0.05。**S40 的「顯著性」是統計謬誤的產物，原因是將 274 個相關信號誤當作 274 個獨立觀測。**

---

### Q2: 有效獨立觀測數是多少？

**7（非 274）。**274 個信號來自 7 個 trading date。同一天的信號在相同市場環境下持倉，彼此高度相關。有效 N = 7。

---

### Q3: Cluster 修正的技術方式是什麼？

每個 trading date 的信號合併為一個 cluster。計算每個 cluster 的平均 delta（D_v3 - A_direct），得到 7 個值，對這 7 個 cluster 均值進行 one-sample t-test（df=6），計算 95% CI。此方法對比 S40 bootstrap CI（n=274 independent）。

---

### Q4: S40 文件中的 Signal Dates 是否正確？

**否。** S40 文件聲稱 signal dates 為 Oct 12-28（7 dates）。實際 V3ComparisonEngine 使用的是 Oct 09-16（7 dates: 09, 10, 11, 12, 13, 14, 16）。274 = 99+4+4+46+27+55+39 ✓。

此差異源於 EligibleWindowDiscovery 模組與 V3ComparisonEngine 的過濾邏輯不同。

---

### Q5: 0050 平均報酬的 S40 聲稱（-4.65%）是否正確？

**否，已修正。** 實際 Oct 09-16 dates 的 0050 5D returns：-1.60%, -2.09%, +0.53%, -2.71%, -3.81%, -3.31%, -2.14%。Equal-weighted 平均 = **-2.16%**，非 -4.65%。

S40 的 -4.65% 對應 EligibleWindowDiscovery 識別的 Oct 12-28 dates，非 V3ComparisonEngine 實際使用的 dates。

---

### Q6: Micro-cluster 問題的影響是什麼？

Oct 10 和 Oct 11 是**非交易日**（國慶日、週日）但各有 4 個信號，各自 mean delta 為 +10.09% 和 +30.73%，對 cluster-level 分析影響巨大。若排除這兩天，grand mean 從 6.49% 降至 **1.12%**。這表明「正向方向」部分由非交易日異常信號驅動。

---

### Q7: DIRECT_ENTRY 的 Alpha 是正是負？

**負，-0.56%（vs A_direct）。** S40 文件聲稱 +2.86%，但那是 vs 0050 benchmark，不是 vs A_direct paired。正確的 paired alpha for DIRECT_ENTRY = -0.56%：V3 direct fills 比 A_direct 差 0.56ppt，原因可能是 exit rule 差異在下跌市場中不利。

---

### Q8: AVOID_CHASING 的 Alpha 有多大（配對比較）？

**+6.38%（vs A_direct paired）。** S40 doc 聲稱 +3.87%（這是 vs 0050 benchmark）。正確的 paired alpha 更大：V3 避開的 41 支股票在 A_direct 中平均下跌 6.38%，V3 以 0% 迴避。

---

### Q9: NO_ENTRY 的配對 Alpha 是多少？

**+0.67%（vs A_direct paired）。** NO_ENTRY 被迴避的 13 支股票在 A_direct 只下跌 0.67%，說明 NO_ENTRY 的迴避品質不佳——這些股票的表現遠比 AVOID_CHASING 的好（-6.38%）。NO_ENTRY 的正面貢獻幾乎可以忽略。

---

### Q10: Stock Selection 是否可識別？

**否，STOCK_SELECTION_UNIDENTIFIABLE。** V3 和 A_direct 使用相同的 foe_v1 scoring engine，接收完全相同的信號。股票選擇能力在兩者之間無法區分。DIRECT_ENTRY paired alpha = -0.56%（負）進一步否認了股票選擇優勢。

---

### Q11: Entry Timing 是否可識別？

**否，ENTRY_TIMING_UNIDENTIFIABLE。** V3ComparisonEngine 將所有 WAIT decisions 計為 0% return（因為沒有追蹤延遲進場的實際填單）。無法區分「V3 等待後以更好價格進場」與「V3 等待後根本沒進場」。

---

### Q12: Leave-One-Date-Out 結果如何？

**DIRECTIONALLY_STABLE（但 CI 仍包含零）。** 7 次 LODO 均沒有符號改變（所有 grand means 為正）。但所有 7 個 LODO CI 都包含零，grand mean 範圍為 2.45% 到 7.83%（高不穩定性）。

---

### Q13: Transaction Cost 敏感性如何？

費率翻倍（0.585% → 1.17%）不會改變方向。但這是 signal-level 分析——cluster-corrected CI 仍然包含零，不受費率影響。

---

### Q14: 20D Outcomes 是否可用？

**否，全部為 NULL。** 344 個 Oct 2026 信號的 `fwd_return_20d` 均為 NULL。最早 Oct 09 信號預計約在 2026-11-10 成熟，最晚 Oct 28 信號約在 2026-12-02 成熟。在全部成熟並獲得授權前，不計算 20D returns。

---

### Q15: 目前的整體排名結論是什麼？

**RANKING_CONDITIONAL（維持，不升級，不降級）。**

- 有方向性正面證據（DIRECTIONALLY_STABLE）
- 但統計上不顯著（SIGNIFICANCE_INCONCLUSIVE）
- 歸因於市場迴避（MARKET_AVOIDANCE_DRIVEN），非選股或進場能力
- 7 dates，single regime，不足以支持 RANKING_SUPPORTED

---

### Q16: 整體 V3 績效改善的正確歸因是什麼？

**MARKET_AVOIDANCE_DRIVEN（確認）：**
1. 主要驅動：AVOID_CHASING（41 支股票，A_direct -6.38% → V3 避免）
2. 次要驅動：WAIT_BREAKOUT_CONF（部分避免 + 部分延遲進場）
3. 微小：交易成本節省（~0.18ppt）
4. 負向：DIRECT_ENTRY（V3 direct fills 比 A_direct 差 -0.56%）

**V3 在下跌市場中的優勢完全來自「不進場」，不是「更好地進場」。**

---

### Q17: 若非要用數字描述 V3 優勢，應使用哪個？

**應使用 cluster-adjusted grand mean = +6.49%，但必須同時報告 CI=[-3.95%, +16.93%]。** 不得單獨引用 +3.66%（signal-level paired mean）而不附帶「CI 在 cluster 修正後包含零」的警語。

---

### Q18: 要達到 RANKING_SUPPORTED，最小需求是什麼？

1. ≥25 個獨立 trading dates
2. 多 regime 覆蓋（bull + bear/neutral）
3. Cluster-corrected CI 不包含零
4. 至少一個完整的 OOS 20D 比較窗口
5. 排除非交易日信號

---

### Q19: 本次是否修改 Production、Cron 或正式資料？

**否，全部維持不變。**
- Crontab hash：`3acaf480cb5dcdd44f40dd9d464955a1`（FROZEN，未變）
- Production SQLite (data/platform.db)：Read-only
- `forward_signals.fwd_return_20d`：仍為 NULL（未寫入）
- MODEL_VERSION v8.0：未修改
- foe_v1：未修改
- Hybrid P1–P4：未修改
- V3 Frozen Parameters：未修改
- 所有 S41 模組均為 `src/research/`，均 Research-only

---

### Q20: 下一個最重要的研究行動是什麼？

**優先順序：**

1. **授權 research-only 20D outcomes 計算**（2026-12-02 後）：在 isolated research cache 中從 `daily_prices` 計算 20D returns，不修改正式資料。解除 EG-08a。

2. **排除非交易日信號**：Oct 10、Oct 11 的 8 個信號應被識別並標記，避免污染 cluster 分析。

3. **等待累積更多 trading dates**：每個月增加約 5 個 trading dates。達到 25 個有效 dates 需要約 3-4 個月。

4. **授權回填 `listing_date`（3 筆）**：解除 EG-12，改善歷史 backtest 可信度。

---

## PART M: Final Verdict Enums

```python
# Session 41 Final Verdicts

REPRODUCTION            = "ALL_REPRODUCED"
# S40 numerical results (10/10) reproduced exactly.
# Documentation discrepancy found: S40 dates Oct 12-28 were wrong; actual Oct 09-16.
# S40 0050 returns (-4.65%) were wrong; actual -2.16%.
# S40 subgroup alpha labeling wrong ("vs A_direct" was actually "vs 0050").

STATISTICAL_SIGNIFICANCE = "ALL_S40_SIGNIFICANT_POSITIVE_DOWNGRADED_TO_SIGNIFICANCE_INCONCLUSIVE"
# Cluster-corrected CI includes zero for all 3 comparisons (N=7, not 274).
# p-values: 0.179, 0.233, 0.180 (all > 0.05).
# S40 SIGNIFICANT_POSITIVE formally retracted.

ATTRIBUTION             = "MARKET_AVOIDANCE_DRIVEN_CONFIRMED"
# AVOID_CHASING: +6.38% paired alpha (n=41, A_direct -6.38% for these stocks).
# DIRECT_ENTRY: -0.56% paired alpha (V3 direct fills UNDERPERFORM A_direct).
# Stock selection: UNIDENTIFIABLE (same foe_v1 engine).
# Entry timing: UNIDENTIFIABLE (WAIT fills not tracked).

ROBUSTNESS              = "DIRECTIONALLY_STABLE"
# Sign never changes in LODO (0/7 dates cause sign flip).
# But CI always includes zero in all LODO scenarios.
# Grand mean range: 2.45% to 7.83% (highly variable).

TWENTY_D_OUTCOME        = "NOT_YET_MATURE"
# 344 Oct 2026 signals, all fwd_return_20d=NULL.
# Earliest maturity: ~2026-11-10 (Oct 09 signals).
# Latest maturity: ~2026-12-02 (Oct 28 signals).
# DO NOT compute returns before full maturity and authorization.

RANKING                 = "RANKING_CONDITIONAL"
# Maintained from S40. Directionally positive evidence exists.
# Not upgraded to RANKING_SUPPORTED: insufficient power, single regime.
# Not downgraded to RANKING_NOT_SUPPORTED: actual comparison run with positive direction.

REGRESSION              = "REGRESSION_PASS"
# 2273 tests passed (+53 from S41), 1 skipped.
# Ruff: clean on all 6 new S41 modules.

ACTIVATION              = "ACTIVATION_BLOCKED"
# Unchanged. Cron frozen. Stage B not authorized.
# V3 not activated. 6 blockers remain open.
# No new blockers added this session.
```

---

## Deliverable Summary

| Part | Deliverable | Status |
|---|---|---|
| A | Baseline audit (git, DB, hashes, crontab) | DONE |
| B | Session40ReproductionReport (10/10 REPRODUCED) | DONE |
| C | Statistical Significance Audit (all 3 downgraded) | DONE |
| D | Market Avoidance Attribution Audit (corrected S40 errors) | DONE |
| E | AVOID_CHASING / NO_ENTRY analysis (DESCRIPTIVE_ASSOCIATION_ONLY) | DONE |
| F | Stock Selection & Entry Timing (both UNIDENTIFIABLE) | DONE |
| G | Robustness & Sensitivity (DIRECTIONALLY_STABLE, 0 sign changes) | DONE |
| H | 20D Outcome Readiness (NO_SIGNALS_MATURE) | DONE |
| I | V3 Evidence Strength Report (RANKING_CONDITIONAL) | DONE |
| J | 53 tests (SA/RP/AC/RB/OR/ES prefix groups) | DONE |
| K | 8 documents | DONE |
| L | 20 final questions | DONE (this doc) |
| M | Final verdict enums | DONE (this doc) |

---

## Safety Constraint Compliance

- Cron：未修改 ✓
- Stage B：未安裝 ✓
- BTM / FDA / TCC：未修改 ✓
- Production SQLite / Neon：Read-only ✓
- ForwardSignals：未寫入 ✓
- Backfill：未執行 ✓
- Decision Center：未修改 ✓
- MODEL_VERSION v8.0：未修改 ✓
- foe_v1：未修改 ✓
- Hybrid P1–P4：未修改 ✓
- V3 Frozen Parameters：未修改 ✓
- ACTUAL / PAPER / V3：未啟用 ✓
