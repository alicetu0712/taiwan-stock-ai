# Session 39 Final Verdict — Clean Research Universe & V1/V2/V3 Comparison Foundation

**Date:** 2026-11-08  
**Session:** 39  
**Tests:** 2170 passed, 1 skipped (regression from 2119 + 51 new)

---

## PART K: 20 Final Questions

### Q1: V1/V2/V3 是三種不同的選股模型嗎？

**不是。** V1/V2/V3（及 Hybrid V1）全部使用相同的底層評分引擎 `foe_v1` / MODEL_VERSION v8.0。它們只在進場時機過濾邏輯上有差異，不涉及選股能力。正確的問題框架是：「更精緻的進場時機過濾是否能改善交易績效？」

---

### Q2: Dataset B 有多少筆信號？哪些被排除？

Dataset B = **2,023 筆**（v8.0 valid）。排除 213 筆 ETF 信號（9.52%）。所有 42 個 ETF stock_id 均為 0-prefix，官方 TWSE/TPEx OpenAPI 驗證。Dataset C 在 v8.0 中與 Dataset B 相同（無 UNKNOWN 證券）。

---

### Q3: fwd_return_20d 目前有多少筆有值？何時可取得？

**0 筆**（全部 NULL）。最早有資料的 FS 信號日期為 2026-10-12，最早的 fwd_return_20d 在 2026-12-02 才能產生。在此之前，所有報酬率分析均 INSUFFICIENT_DATA。

---

### Q4: V3 in-sample +3.66ppt 優勢的來源是什麼？

**MARKET_AVOIDANCE_DRIVEN**（與 Session 28 一致）。V3 在市場下行時持有較少部位（更多 WAIT/NO_ENTRY 決策），避免損失。股票選擇能力和進場價格改善目前均為 UNIDENTIFIABLE（無匹配樣本、無 outcome 資料）。

---

### Q5: 歷史研究資格閘門的整體判定是什麼？三個 INELIGIBLE 的原因是？

整體：**INELIGIBLE**。三個 INELIGIBLE 檢查：
- **EG-02**（時間點宇宙）：股票主表無 listing_date，無法驗證歷史日期的有效宇宙
- **EG-08**（缺少 outcome）：fwd_return_20d = 0/2236
- **EG-12**（生存偏誤）：0 筆 delisted_date，99 筆疑似下市，3 筆確認的期中下市未處理

---

### Q6: Hybrid V1 和 V3 的 parameter hash 分別是什麼？

- **Hybrid V1**：MA 閾值 `ma20_rising=0.3, ma20_falling=-0.3`，frozen commit `6602c3b`
- **V3**：BT parameter hash `be43e8ca977d9fdd`，frozen commit `6602c3b`

---

### Q7: 六對策略配對中，哪一對可以被比較？

只有 **Hybrid V1 ↔ V3** 為 CONDITIONAL（兩者均 VERIFIED，只被 outcome 資料封鎖）。其他五對（含 V1 或 V2 的組合）均 NOT_COMPARABLE，因為 V1/V2 為 PARTIAL 狀態（無 parameter hash）。

---

### Q8: Cron 狀態是否有改變？

**否。** Cron hash 仍為 `3acaf480cb5dcdd44f40dd9d464955a1`，CRON_FROZEN_UNCHANGED（S36 以來未變動）。本 session 明確不得修改 Cron。

---

### Q9: ETF 污染率的精確數字及驗證方法是什麼？

**9.52%**（213/2236 FS v8.0 valid 信號）。驗證方式：官方 TWSE 公開資訊觀測站 ETF 清單 + TPEx ETF 清單，透過 Session 38 SecurityClassificationService 分類。全部 42 個 ETF stock_id 均以 `0` 開頭（如 00878, 00631L 等）。

---

### Q10: TPEx 完全缺席的影響是什麼？

**嚴重**。官方台股普通股宇宙 = TWSE 1,099 + TPEx 897 = 1,996 檔。FS v8.0 完全沒有 TPEx 信號（0/897），代表 foe_v1 當前只涵蓋台灣市場 44.9% 的普通股標的。任何基於 FS v8.0 的結論均不能推廣至 TPEx 掛牌股票。

---

### Q11: 10 個比較準備度維度中，有幾個 BLOCKED？

**5 個 BLOCKED**（Outcome Availability、Matched Samples、Statistical Power、Out-of-Sample Evidence、Prospective Evidence）。另有 4 個 CONDITIONAL、1 個 READY（Transaction Costs）。

---

### Q12: Session 39 新增了哪三個模組？各有什麼功能？

1. **`src/research/clean_research_universe.py`** — `CleanResearchUniverseBuilder`：建構 Dataset A/B/C，含官方分類、fingerprint、來源追蹤
2. **`src/research/strategy_version_registry.py`** — `StrategyVersionRegistry`：正式記錄 V1/V2/Hybrid_V1/V3 四個版本定義及 pairwise 可比性
3. **`src/research/comparison_readiness_report.py`** — `HistoricalResearchEligibilityGate`（12 checks）+ `StrategyComparisonFramework` + `V1V2V3ComparisonReadinessReport`（10 dimensions）

---

### Q13: 交易成本假設（FEES_PCT）的來源為何？

**0.585%**（買賣合計），來源：`src/execution_simulator.py` 及 `src/research/v3_comparison_engine.py`。此數字代表一次完整買進+賣出的總摩擦成本，包含交易稅與手續費估算。

---

### Q14: v8.0 有效信號中 BUY/STRONG_BUY 佔多少？

**128 筆**（71 BUY + 57 STRONG_BUY），佔 2,236 筆 v8.0 valid 信號的 **5.72%**。V1/V2/V3 比較只適用於這 128 筆可操作信號，其餘 2,108 筆（wait/sell/reduce/wait_pullback）不觸發任何版本的進場。

---

### Q15: 最早可以執行有統計意義的 Hybrid V1 ↔ V3 比較是什麼時候？

- **最早可行（underpowered）：2026-12-15**（第一批 outcome 產生後）
- **統計充分：2027-Q1 at earliest**（需要 25+ 個交易日、非重疊觀測 ≥ 100 筆）
- 目前 7 個信號日期 = 最多 7 個獨立叢集，遠低於充分統計功率所需

---

### Q16: 生存偏誤的具體確認案例是哪些？

三筆確認的期中下市記錄：
- **2867**：2026-07-24 下市
- **6806**：2026-06-22 下市  
- **6288**：2025-08-04 下市

這三檔在下市前均曾出現在 FS 信號中。若回測引擎未正確處理下市後的價格，報酬計算可能失真。

---

### Q17: Dataset B 的 data fingerprint 是如何產生的？

對所有 2,023 個 `(stock_id, trade_date)` 配對排序後，計算 SHA-256 的前 16 個 hex 字元。從同一個 DB 重新計算會產生相同的 fingerprint，確保實驗可重現性。

---

### Q18: Session 39 的測試結構是什麼？有幾個測試組？

51 個新測試，分為 5 個前綴群組：
- **CU** (1–12)：CleanResearchUniverseBuilder
- **VR** (1–12)：StrategyVersionRegistry
- **EG** (1–09)：HistoricalEligibilityGate
- **CF** (1–08)：StrategyComparisonFramework
- **RR** (1–10)：V1V2V3ComparisonReadinessReport

全部使用 in-memory fixture，不存取 production DB。

---

### Q19: 要將 HISTORICAL_ELIGIBILITY 從 INELIGIBLE 升級到 CONDITIONAL，最少需要哪些改動？

三項最低要求：
1. 等待 2026-12-02（fwd_return_20d 開始有值，解除 EG-08）
2. 新增 `delisted_date` 欄位，標記 2867/6806/6288（解除 EG-12）
3. 從 TWSE 匯入上市日期至 stocks 主表（解除 EG-02 → CONDITIONAL）

---

### Q20: Session 39 最關鍵的一個發現是什麼？

**V1/V2/V3 都是同一個評分引擎（foe_v1）的進場時機過濾變體，不是獨立的選股模型。** 這意味著三個版本選出的股票完全相同（BUY/STRONG_BUY 128 筆固定），差異只在「何時進場」。因此，所謂的「版本比較」只能回答「哪種進場時機過濾更好？」而無法回答「哪個版本的選股能力更強？」

---

## PART L: Final Verdict Enums

```python
# Session 39 Final Verdicts

CLEAN_UNIVERSE       = "CLEAN_UNIVERSE_PARTIAL"
# Dataset B = 2,023 signals (368 TWSE stocks). TPEx absent, 35% market coverage,
# 0 outcomes available. Framework defined and reproducible.

HISTORICAL_ELIGIBILITY = "HISTORICAL_ELIGIBILITY_INELIGIBLE"
# 12-check gate: 2 ELIGIBLE, 4 CONDITIONAL, 3 INELIGIBLE, 2 UNVERIFIED.
# Blockers: EG-02 (point-in-time), EG-08 (0 outcomes), EG-12 (survivorship).

VERSION_REGISTRY     = "VERSIONS_PARTIAL"
# 4 versions registered. V1/V2: PARTIAL (no parameter hash).
# Hybrid V1 / V3: VERIFIED (frozen commit 6602c3b).

COMPARISON           = "COMPARISON_BLOCKED"
# Framework designed. Contract defined. Cannot execute — 0 comparable outcomes.
# Only Hybrid V1 ↔ V3 eligible once outcomes arrive (2026-12-02 earliest).

RANKING              = "RANKING_NOT_SUPPORTED"
# 5 of 10 readiness dimensions BLOCKED.
# V1/V2 not rankable (PARTIAL definitions).
# Earliest statistically adequate comparison: 2027-Q1.

REGRESSION           = "REGRESSION_PASS"
# 2170 tests passed (+51 from S39), 1 skipped.
# All new tests in-memory, no production DB access.
# Ruff lint: clean.

ACTIVATION           = "ACTIVATION_BLOCKED"
# Unchanged from S38. 6 blockers remain.
# Quality gate FAIL (7/12). ETF contamination 9.52%.
# Cron frozen. Stage B not authorized.

V3_ATTRIBUTION       = "MARKET_AVOIDANCE_DRIVEN"
# In-sample +3.66ppt confirmed as market timing / exposure reduction.
# Stock selection: UNIDENTIFIABLE. Entry timing: UNIDENTIFIABLE.
# Consistent with Session 28 walk-forward conclusion.

PROSPECTIVE          = "NO_PROSPECTIVE_EVIDENCE"
# Cron frozen. Stage B blocked. 0 live forward signals post-S39.
# V3 shadow framework READY but CRON_ACCEPTANCE_PENDING.
```

---

## Deliverable Summary

| Part | Deliverable | Status |
|---|---|---|
| B | CleanResearchUniverseBuilder (Dataset A/B/C) | DONE |
| C | HistoricalResearchEligibilityGate (12 checks) | DONE |
| D | StrategyVersionRegistry (4 versions) | DONE |
| E | StrategyComparisonFramework | DONE |
| F | Performance metrics design | DONE (in comparison contract) |
| G | V3 performance attribution doc | DONE |
| H | V1V2V3ComparisonReadinessReport | DONE |
| I | 51 tests (all in-memory) | DONE — 2170 total passed |
| J | 7 documents | DONE (all 7) |
| K | 20 final questions | DONE (this doc) |
| L | Final verdict enums | DONE (this doc) |

---

## 7 Documents Written This Session

1. `docs/strategy_version_registry_session39.md`
2. `docs/clean_research_universe_session39.md`
3. `docs/historical_eligibility_session39.md`
4. `docs/v1_v2_v3_comparison_contract_session39.md`
5. `docs/v3_performance_attribution_session39.md`
6. `docs/comparison_readiness_session39.md`
7. `docs/session39_final_verdict.md` ← this file

---

## Safety Constraint Compliance

本 session 未違反任何安全限制：
- Cron：未修改 ✓
- Stage B Probe：未安裝 ✓
- BTM / FDA / TCC：未修改 ✓
- Production SQLite / Neon：未寫入 ✓
- ForwardSignals：未修改 ✓
- Backfill：未執行 ✓
- Decision Center：未修改 ✓
- MODEL_VERSION：未修改 ✓
- foe_v1：未修改 ✓
- Hybrid P1–P4：未修改 ✓
- V3 Frozen Parameters：未修改 ✓
- V3 / ACTUAL / PAPER：未啟用 ✓
- 所有正式資料存取：Read-only ✓
