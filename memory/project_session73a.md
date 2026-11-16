---
name: project-session73a
description: S73A 短線反彈策略可行性：INSUFFICIENT_EVIDENCE；群聚修正後全部不顯著；交易成本吃掉邊際；需補充資料
metadata:
  type: project
---

短線搶反彈（1-5D）策略可行性研究。資料唯讀，不修改任何正式環境。

**Why:** 使用者希望在市場下跌時做短線反彈交易，評估現有資料與架構是否支持。

**How to apply:** 目前統計證據不足，不建議進入生產。若補充5年歷史資料 + 已下市股票後可重新評估。

**關鍵發現**：
- 群聚修正是關鍵：同一天多支股票同時觸發訊號，原始 N=6,642（BEAR）→ 有效 N=108 交易日（61倍膨脹）
- BEAR 5D 毛報酬：原始 +1.07%（看起來有邊際）→ 群聚修正後 -0.23%（無邊際）
- 淨報酬（扣 0.585% 成本）：BEAR 5D = -0.82%，BULL 5D = -0.44%
- 全部 9 組（3 Regime × 3 Horizon）**NOT_SIGNIFICANT**
- 交易成本 0.585% > 所有毛報酬均值

**資料現況**：
- 724 支股票，568 個交易日（Jul 2024–Nov 2026）
- 無下市股票（存活偏差存在但未量化）
- 無盤中資料（僅日線收盤）
- 歷史僅24個月（不足5年）
- Jun–Sep 2026 資料異常（9,765 筆/天 vs 正常 722）

**統計判定**：`INSUFFICIENT_EVIDENCE`
**最終狀態**：`FEASIBLE_DATA_ONLY_NO_EVIDENCE`
**Production Ready**：NOT_READY

**進入 73B 前需要**：
- B2：5年+ 歷史資料（或至少一個完整牛熊循環）
- B3：已下市股票資料（消除存活偏差）
- B4：每日開盤價（目前資料是否含 open 需確認）

**工作區**：`/Users/alicetu/Desktop/Antigravity/stock_platform_73a/`
- 19 份研究文件（docs/session73a_*.md）
- research/bounce_research.py（唯讀研究模組）
- 8/8 tests PASS

**正式環境完全未修改**：
- backfill_daily_prices.py：202e2231... ✅
- dashboard/app.py：709e161c... ✅
- SQLite：536,739 rows / 2026-11-13 ✅
