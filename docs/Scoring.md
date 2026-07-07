# Scoring Model

AI 台股研究平台的評分邏輯。所有參數皆定義於 `config.py`，無需修改程式碼即可調整。

## 綜合評分（Total Score）

```
Total = quality × 0.40
      + timing  × 0.25
      + behavior × 0.20
      + intelligence × 0.10
      - risk    × 0.05
```

| 維度 | 權重 | 模組 | 說明 |
|---|---|---|---|
| Company Quality | 40% | `fundamental.py` | ROE / ROA / EPS / 毛利率 / 估值 |
| Technical Timing | 25% | `technical.py` | RSI / KD / MA 趨勢 / 支撐壓力 |
| Market Behavior | 20% | `market_behavior.py` | 三大法人籌碼 |
| Market Intelligence | 10% | `decision.py` | 新聞情緒 / 產業訊號 |
| Risk Penalty | 5% | `risk.py` | 波動率 / 回撤 / Beta |

## 推薦等級

| 等級 | 最低分 | 星級 | 標籤 |
|---|---|---|---|
| A+ | 85 | ★★★★★ | Strong Research Candidate |
| A | 75 | ★★★★☆ | Research Candidate |
| B | 65 | ★★★☆☆ | Watch List |
| C | 55 | ★★☆☆☆ | Observation Only |
| D | 0 | ★☆☆☆☆ | Not Recommended |

每日最多推薦 3 檔（`RECOMMENDATION_RULES.max_daily_recs`），最低信心分數 70%。

## 第一層硬性篩選（Hard Filter）

通不過者直接排除，不進入評分。

| 條件 | 門檻 | config key |
|---|---|---|
| 上市年數 | ≥ 3 年 | `min_listing_years` |
| 市值 | ≥ 100 億 | `min_market_cap_b` |
| 資本額 | ≥ 20 億 | `min_capital_b` |
| 日均成交額 | ≥ 1 億 | `min_avg_daily_amt_m` |
| TTM EPS | > 0 | `min_ttm_eps` |
| ROE | ≥ 15% | `min_roe` |
| ROA | ≥ 8% | `min_roa` |
| 負債比率 | ≤ 60% | `max_debt_ratio` |

## Company Quality 子評分

### ROE 評分
| ROE | 分數 |
|---|---|
| ≥ 20% | 100 |
| ≥ 15% | 80 |
| ≥ 10% | 60 |
| ≥ 8% | 40 |
| < 8% | 0 |

### 毛利率評分
| 毛利率 | 分數 |
|---|---|
| ≥ 40% | 100 |
| ≥ 30% | 80 |
| ≥ 20% | 60 |
| ≥ 10% | 40 |
| < 10% | 20 |

### 負債比率評分
| 負債比率 | 說明 |
|---|---|
| ≤ 30% | 很安全 |
| ≤ 50% | 普通 |
| ≤ 60% | 偏高 |
| > 60% | 扣分 |

## Technical Timing 子評分

| 指標 | 說明 |
|---|---|
| RSI | 30–70 中性；< 30 超賣加分；> 70 超買扣分 |
| KD | 黃金交叉加分；死亡交叉扣分 |
| MA 趨勢 | 5/20/60 均線多頭排列加分 |
| 支撐壓力 | 距支撐位近加分；距壓力位近扣分 |

## 調整評分參數

1. 開啟 `config.py`
2. 修改對應的 dict（`SCORE_WEIGHTS` / `HARD_FILTER` / `QUALITY_CONFIG`）
3. 不需重啟；下次執行分析即生效
