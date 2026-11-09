# Session 40 Final Verdict — Research Blocker Resolution & Minimum Viable Strategy Comparison

**Date:** 2026-11-09  
**Session:** 40  
**Tests:** 2220 passed, 1 skipped (+50 from S40)

---

## PART L: 20 Final Questions

### Q1: Historical Eligibility 為何 INELIGIBLE（S39 結論）？

三個根本性 INELIGIBLE 原因（EG-02 point-in-time、EG-08 零 outcomes、EG-12 survivorship）。Session 40 更新：EG-08 在 **5D 窗口**已 PARTIAL 解除（V3ComparisonEngine 從 daily_prices 計算 5D outcomes）。EG-02 在 Oct 2026 forward signals 窗口已 PARTIAL 解除（de facto point-in-time）。整體仍 INELIGIBLE for 20D，but **CONDITIONAL for 5D window**。

---

### Q2: 具體有哪些 Blockers？

12 個 blockers：
- **Category A（2）**：EG-02a（point-in-time Oct 2026），EG-10（clustering）
- **Category B（3）**：EG-04（5D coverage），EG-05（benchmark），EG-09（duplicates）
- **Category C（3）**：EG-02b（historical PiT），EG-12（survivorship），EG-07（corp actions）
- **Category D（4）**：EG-08a（20D outcomes），V1V2-DEF（parameter hashes），STAT-POWER（n<100），REGIME（single regime）

---

### Q3: 哪些 Blockers 已解除？

**完全解除（2）**：EG-05（benchmark → RESOLVED），EG-09（duplicates → RESOLVED）

**部分解除（5）**：EG-02a（5D PiT PARTIAL），EG-04（79.7% coverage PARTIAL），EG-08（5D outcomes PARTIAL），EG-10（clustering documented PARTIAL），V1V2-DEF（hashes RECOVERED PARTIAL）

---

### Q4: 哪些 Blockers 仍存在？

**仍 OPEN（6）**：EG-02b（historical PiT）、EG-12（survivorship）、EG-07（corp actions）、EG-08a（20D outcomes）、STAT-POWER（7 dates < 100）、REGIME（single bull regime）

---

### Q5: 是否找到合格歷史窗口？

**是。** `CONDITIONAL_WINDOW_FOUND`：Oct 2026 5D window（7 dates，274 eligible signals）。  
10D 和 20D 仍為 `NO_ELIGIBLE_WINDOW`。

---

### Q6: 合格窗口有多少交易日？

**7 個交易日**（2026-10-12, 10-13, 10-14, 10-16, 10-21, 10-22, 10-28）。有效獨立觀測 N ≈ 7，非 274。

---

### Q7: 有多少 Eligible Signals？

**274 個 5D-eligible 信號**（buy/strong_buy, 7 dates, 有 ≥5D price bars）。  
Dataset B（v8.0 valid TWSE common）：128 筆 buy/strong_buy（5.72% of 2236），但 comparison engine 使用全部 trade_signal='buy/strong_buy' 包含 v6.0。

---

### Q8: 有多少 Paired Samples？

- D_v3 vs A_direct: **267 paired**
- D_v3 vs B_v1v2: **253 paired**
- D_v3 vs C_hybrid: **267 paired**
- V1 vs V2（effectiveness_analysis.json）: **2,953 matured**（但來自 150-stock 模擬，非直接 forward_signals）

---

### Q9: V1 定義是否完整？

**否，RECOVERED（不是 VERIFIED）**。已從現有程式碼計算 parameter hash `13113e2933ec3017`，但沒有 frozen commit → 無法確認 Sessions 23-25 的參數與現在相同。

---

### Q10: V2 定義是否完整？

**否，RECOVERED**。Hash `258513077a5ca6a0` 從 `src/analyzers/entry_timing.py` 現有常數計算。無 frozen commit。EntryTimingAnalyzer 的歷史參數無法驗證。

---

### Q11: V3 定義是否完整？

**是，VERIFIED**。Parameter hash `be43e8ca977d9fdd`，comparison engine hash `1feb7a6b294a063d`，frozen commit `6602c3b`。

---

### Q12: V1 vs V2 是否可比較？

**CONDITIONAL**（從 NOT_COMPARABLE 升級）。效果 analysis.json 有 2,953 個配對樣本，CI95=[-0.05%, +0.16%] 包含零 → NOT statistically significant。V2 相對 V1 有微弱正面跡象，但統計上不顯著。

---

### Q13: V2 vs V3 是否可比較？

**CONDITIONAL**。5D engine 有 253 paired samples，D_v3 vs B_v1v2 delta=+2.99%，CI=[+1.91%, +4.24%]，verdict=SIGNIFICANT_POSITIVE。但：7 dates，single regime，市場下跌期間，CI 未做 cluster 修正。

---

### Q14: V1 vs V3 是否可比較？

**CONDITIONAL**。5D engine 有 267 paired samples，D_v3 vs A_direct delta=+3.66%，CI=[+2.61%, +4.83%]，verdict=SIGNIFICANT_POSITIVE。同上，cluster-adjusted CI 未計算，單一 regime。

---

### Q15: 哪些績效指標可以可靠計算？

**可靠計算（5D CONDITIONAL window）**：mean net return, median net return, win rate, fill rate, mean net alpha（但 CI 不可靠因 effective N=7）

**計算困難但有估計**：transaction cost savings（computable），market avoidance contribution（estimated）

**無法計算**：20D return, Sharpe ratio, MDD, entry timing benefit（unidentifiable）

**統計信心度**：STATISTICAL_CONFIDENCE_UNVERIFIED for all 5D results（7 dates, single regime）

---

### Q16: V3 +3.66ppt 是否仍成立？其適用範圍？

**成立，但僅限 Oct 2026 5D窗口**（CONDITIONAL）：
- 實測數字：D_v3 vs A_direct mean delta = +3.66%，CI=[+2.61%, +4.83%]
- 適用範圍：**7個交易日，bull→declining 市場，single regime，in-sample scoring engine**
- 不可外推至：20D horizon、bear/neutral 市場、非 Oct 2026 市場環境
- 與 Session 27 的 in-sample +3.66% 數字吻合（同樣的 comparison engine 和信號池）

---

### Q17: Market Avoidance 是否能獨立量化？

**可估計，不可精確量化**（ESTIMATED）：
- 曝險減少估計：~1.00ppt（31.4% skipped × 3.20% average avoided loss）≈ 27% of total alpha
- 迴避品質（AVOID_CHASING + NO_ENTRY）：+3.87%/+4.30% alpha，QUANTIFIED
- 無法精確分離：股票選擇 vs. 迴避品質 vs. 出場規則差異

---

### Q18: 是否有任何版本具備可信的績效優勢？

**無法宣稱 V3 勝出（RANKING_CONDITIONAL，非 RANKING_SUPPORTED）**：

V3 在 Oct 2026 5D 窗口相較所有基準均顯示 SIGNIFICANT_POSITIVE，但這是在：
- 市場下行期間（0050 avg -4.65%）
- 7 個交易日（underpowered）
- 單一 regime（bull→decline）
- 市場迴避驅動（非股票選擇）

在足夠大的多 regime 樣本出現前，不能宣稱 V3 是最佳版本。

---

### Q19: 本次是否修改 Production、Cron 或正式資料？

**否，全部維持不變。**
- Crontab hash：`3acaf480cb5dcdd44f40dd9d464955a1`（FROZEN，未變）
- Production SQLite (data/platform.db)：Read-only
- forward_signals：未寫入（fwd_return_20d 仍為 NULL）
- Production MODEL_VERSION：未修改
- foe_v1：未修改
- Hybrid P1–P4：未修改
- V3 Frozen Parameters：未修改

所有新增模組均為 `src/research/` Research-only，所有存取均為 Read-only。

---

### Q20: 下一個最小可行的研究改善是什麼？

**優先順序（按重要性）**：

1. **授權 research-only 20D outcome 計算**（無需修改 cron 或 production）：授權一個 isolated script 從 daily_prices 計算 forward_signals 的 fwd_return_20d，寫入 research cache（非 production DB）。可在 2026-12-02 後立即執行。預期效益：解除 EG-08（20D），讓 V3 比較從 5D 升級到 20D。

2. **授權 cron 繼續執行新信號**：每增加一個 trading date，effective N +1。需要 25+ dates 才能達到 minimally adequate power。

3. **新增 `delisted_date` 欄位（3 筆）**：解除 EG-12，改善歷史 backtest 可信度。

---

## PART M: Final Verdict Enums

```python
# Session 40 Final Verdicts

BLOCKERS             = "BLOCKERS_REDUCED"
# 2 fully RESOLVED (EG-05, EG-09) + 5 PARTIAL.
# 6 still OPEN (EG-02b, EG-12, EG-07, EG-08a 20D, STAT-POWER, REGIME).

HISTORICAL_ELIGIBILITY = "CONDITIONAL_WINDOW_FOUND"
# 5D CONDITIONAL window: Oct 2026, 7 dates, 274 signals.
# 10D and 20D: NO_ELIGIBLE_WINDOW.

VERSION_DEFINITIONS  = "VERSIONS_PARTIAL"
# V1/V2: RECOVERED (hash computed, historical accuracy partial).
# Hybrid V1 / V3: VERIFIED (frozen commit 6602c3b).
# Overall: VERSIONS_PARTIAL (upgraded from PARTIAL — V1/V2 now have hashes).

COMPARISON           = "COMPARISON_CONDITIONAL"
# 5D comparison executed. D_v3 SIGNIFICANT_POSITIVE vs all baselines.
# V1 vs V2: CONDITIONAL (CI includes zero in effectiveness_analysis.json).
# NOT upgraded to COMPARISON_COMPLETED due to: underpowered, single regime.

RANKING              = "RANKING_CONDITIONAL"
# D_v3 shows SIGNIFICANT_POSITIVE on 5D in Oct 2026.
# NOT RANKING_SUPPORTED: 7 dates, single regime, MARKET_AVOIDANCE_DRIVEN only.
# Not RANKING_NOT_SUPPORTED: actual comparison run with positive evidence.

REGRESSION           = "REGRESSION_PASS"
# 2220 tests passed (+50 from S40), 1 skipped.
# Ruff: clean.

ACTIVATION           = "ACTIVATION_BLOCKED"
# Unchanged. Cron frozen. Stage B not authorized.
# V3 not activated. 6 blockers remain.

V3_ATTRIBUTION       = "MARKET_AVOIDANCE_DRIVEN"
# Confirmed by quantitative analysis on Oct 2026 5D window.
# Avoidance quality (AVOID_CHASING + NO_ENTRY): +3.87-4.30% alpha.
# Entry timing: UNIDENTIFIABLE.
# Stock selection within invested (DIRECT_ENTRY): +2.86% (partially confounded).

V1_VS_V2             = "V2_CONDITIONAL_ADVANTAGE"
# effectiveness_analysis.json: N=2953, delta=+0.0572%, CI=[-0.05%, +0.16%].
# CI includes zero → NOT statistically significant at p=0.05.
# V2 shows modest positive trend (2/10 windows significant: W2, W8) but insufficient.
```

---

## Deliverable Summary

| Part | Deliverable | Status |
|---|---|---|
| A | Baseline audit (git, DB, hashes) | DONE |
| B | ResearchBlockerMatrix (12 blockers, 4 categories) | DONE |
| C | EligibleWindowDiscovery (CONDITIONAL 5D window) | DONE |
| D | VersionDefinitionRecovery (V1/V2 RECOVERED) | DONE |
| E | Actual paired comparison (5D run, N=267-274) | DONE |
| F | V3 attribution (MARKET_AVOIDANCE_DRIVEN, quantified) | DONE |
| G | Blocker resolution (2 resolved, 5 partial) | DONE |
| H | Research evidence dashboard (in comparison doc) | DONE |
| I | Statistical safeguards (STAT_CONFIDENCE_UNVERIFIED) | DONE |
| J | 50 tests (BM/WD/VD/PC/AT prefix groups) | DONE |
| K | 7 documents | DONE |
| L | 20 final questions + verdict enums | DONE (this doc) |

---

## Safety Constraint Compliance

- Cron：未修改 ✓
- Stage B：未安裝 ✓
- BTM / FDA / TCC：未修改 ✓
- Production SQLite / Neon：Read-only ✓
- ForwardSignals：未寫入 ✓
- Backfill：未執行 ✓
- Decision Center：未修改 ✓
- MODEL_VERSION：未修改 ✓
- foe_v1：未修改 ✓
- Hybrid P1–P4：未修改 ✓
- V3 Frozen Parameters：未修改 ✓
- ACTUAL / PAPER / V3：未啟用 ✓
