# AI 台股研究平台

> 自動化每日選股研究系統，整合技術面、基本面、籌碼面與 AI 綜合評分，  
> 產出每日研究報告並透過 Streamlit Dashboard 視覺化呈現。

---

## Project Overview

本平台為個人使用的台股研究輔助工具，**不提供買賣建議**，所有輸出均為研究用途。

**核心流程：**

1. 每日自動抓取全市場股價（TWSE + TPEx + Yahoo Finance 備援）
2. 財務資料蒐集（FinMind API / GoodInfo.tw）
3. 多維度評分（技術面 + 基本面 + 籌碼面 + 市場情報）
4. 硬性篩選排除不合格標的
5. Claude AI 生成深度研究報告
6. Dashboard 視覺化 + 持倉追蹤 + 回測驗證

---

## Architecture

```
┌─────────────────────────────────────────┐
│           Streamlit Dashboard           │
│  Today │ Reports │ Backtest │ Positions │
└────────────────┬────────────────────────┘
                 │
     ┌───────────▼───────────┐
     │      src/database     │  PostgreSQL (Neon) / SQLite
     └───────────┬───────────┘
                 │
     ┌───────────▼───────────┐
     │   src/reporters/      │  Claude AI → Markdown 報告
     │   report_generator    │
     └───────────┬───────────┘
                 │
     ┌───────────▼───────────┐
     │   src/engines/        │
     │   decision.py         │  DecisionEngine：整合評分 → 推薦名單
     └───┬───────────────────┘
         │
   ┌─────┴─────┐
   │ Analyzers │
   ├───────────┤
   │ technical │  技術面 0-100（MA/RSI/MACD/KD/型態）
   │ fundament │  基本面 0-100（ROE/ROA/EPS/毛利/估值）
   │ market_bh │  籌碼面 0-100（法人/主力）
   │ risk      │  風險評估 0-100
   └─────┬─────┘
         │
   ┌─────┴──────────────────────┐
   │ Collectors                 │
   ├────────────────────────────┤
   │ price_collector            │  TWSE / TPEx / Yahoo Finance
   │ financial_collector        │  FinMind / GoodInfo.tw
   │ chip_collector             │  法人籌碼
   │ news_collector / mops      │  新聞 / 重訊
   └────────────────────────────┘
```

---

## Scoring Model

綜合分數由五個維度加權計算：

| 維度 | 權重 | 資料來源 |
|---|---|---|
| 基本面（Company Quality） | **40%** | ROE / ROA / EPS / 毛利率 / 估值 |
| 技術面（Technical Timing） | **25%** | MA / RSI / MACD / KD / K 線型態 |
| 籌碼面（Market Behavior）  | **20%** | 三大法人 / 主力進出 |
| 市場情報（Intelligence）   | **10%** | 新聞 / 重訊 / 產業動態 |
| 風險扣分（Risk Penalty）   |  **5%** | 高波動 / 近壓力區 / 財務警示 |

**推薦等級：**

| 等級 | 分數門檻 | 說明 |
|---|---|---|
| A+ ★★★★★ | ≥ 85 | Strong Research Candidate |
| A  ★★★★☆ | ≥ 75 | Research Candidate |
| B  ★★★☆☆ | ≥ 65 | Watch List |
| C  ★★☆☆☆ | ≥ 55 | Observation Only |
| D  ★☆☆☆☆ |  < 55 | Not Recommended |

每日最多推薦 **3 檔**，需通過硬性篩選（流動性、財務健康）才進入評分。

---

## Installation

### 環境需求

- Python 3.11+
- PostgreSQL（生產環境）或 SQLite（本機開發）

### 安裝步驟

```bash
git clone <repo>
cd stock_platform

# 安裝依賴
pip install -r requirements.txt

# 安裝開發工具（測試 + 程式碼風格）
pip install -e ".[dev]"
```

### 環境變數設定

複製 `.env.example` 並填入 API Key：

```bash
cp .env.example .env
```

| 變數 | 必填 | 說明 |
|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ | Claude AI API Key |
| `NEON_URL` | ✅（生產） | PostgreSQL 連線字串 |
| `FINMIND_TOKEN` | 選填 | FinMind API Token（財務資料）|
| `DATABASE_URL` | 選填 | 覆寫資料庫連線 |

---

## How It Works

### 每日分析流程

```bash
# 執行今日分析（需 API Key）
python main.py

# 指定日期
python main.py --date 2026-07-01

# Dry-run（測試用，不打外部 API）
python main.py --dry-run

# 排程模式（每日盤後自動執行）
python main.py --schedule
```

### 啟動 Dashboard

```bash
streamlit run dashboard/app.py
```

Dashboard 頁面：
- **Today** — 當日推薦 + 市場概況
- **Reports** — 歷史報告搜尋 + 閱讀
- **Backtest** — 推薦模型回測驗證
- **Positions** — 個人持倉追蹤（Monte Carlo 模擬）
- **My Trades** — 交易紀錄 + 損益統計

---

## Backtest

Dashboard 的 Backtest 頁面驗證模型預測能力：

- **持有期**：20 日 / 60 日
- **基準**：0050（加權指數 ETF）、0056（高股息 ETF）
- **Alpha**：個股報酬 − 基準報酬
- **指標**：Sharpe Ratio、MDD、IR（Information Ratio）、勝率
- **統計顯著性**：t-test p-value
- **模型信心評等**：★ ~ ★★★★★（樣本數 + p-value + Alpha + IR）

Walk-Forward 設計：推薦日期依序累積，模擬真實未知未來。

---

## Limitations

- 財務資料有延遲（季報約延遲 45 天）
- 所有輸出僅為研究輔助，**不構成投資建議**
- 籌碼資料依賴第三方 API，偶有缺失
- AI 報告為輔助分析，可能存在幻覺或誤判
- 回測基於歷史資料，不代表未來表現

---

## Development

### 執行測試

```bash
pytest                         # 全部測試（97 個）
pytest --cov=src/analyzers     # 含覆蓋率報告
```

### 程式碼風格

```bash
ruff check src/ dashboard/     # Lint
black src/ dashboard/          # Format
isort src/ dashboard/          # Import 排序
```

### 目錄結構

```
stock_platform/
├── main.py                    # 每日分析入口
├── config.py                  # 全域設定
├── pyproject.toml             # 依賴 + 工具設定
├── requirements.txt           # 部署用依賴（Railway）
├── src/
│   ├── database.py            # ORM + 連線管理
│   ├── schedulers.py          # 排程
│   ├── analyzers/             # 四個評分引擎
│   ├── collectors/            # 六個資料蒐集器
│   ├── engines/               # 決策 / 篩選 / Monte Carlo
│   ├── reporters/             # Claude AI 報告產生器
│   └── ai/                    # Claude API 封裝
├── dashboard/
│   ├── app.py                 # Streamlit 主程式（路由）
│   ├── db.py                  # DB 模組初始化
│   ├── loaders.py             # 資料載入層（@cache_data）
│   └── pages/                 # 六個頁面模組
└── tests/                     # 97 個單元測試（coverage 81%）
```

---

## Future Roadmap

- [ ] API 統一介面（Collector.collect / validate / parse / save）
- [ ] Result Pattern（成功 / 警告 / 錯誤統一回傳）
- [ ] Data Health Dashboard（資料品質監控）
- [ ] 效能優化（分析快取 30 分鐘 TTL）
- [ ] 文件完善（docs/*.md 各模組說明）
- [ ] Backend Service 層（API 與 Dashboard 解耦）

---

## License

MIT — 個人研究用途。使用本工具產生的任何投資決策，風險自負。
