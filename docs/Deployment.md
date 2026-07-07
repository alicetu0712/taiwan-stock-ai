# Deployment

本機開發與雲端部署指南。

## 系統需求

- Python 3.11 或 3.13
- pip
- （雲端）PostgreSQL / Neon 資料庫

## 本機快速啟動

```bash
# 1. 安裝依賴
pip install -r requirements.txt

# 2. 建立 .env（複製範本後填入金鑰）
cp .env.example .env

# 3. 啟動 Dashboard
streamlit run dashboard/app.py
```

## 環境變數（`.env`）

| 變數 | 必填 | 說明 |
|---|---|---|
| `ANTHROPIC_API_KEY` | 選填 | Claude AI 摘要功能。留空則跳過 AI 分析。|
| `FINMIND_TOKEN` | 選填 | FinMind 財務 API。留空則財務資料功能受限。|
| `DATABASE_URL` | 選填 | PostgreSQL 連線字串。留空則使用本機 SQLite。|
| `NEON_DATABASE_URL` | 選填 | Neon 專用格式（優先於 `DATABASE_URL`）。|

**本機預設**：不設定 `DATABASE_URL` 時自動使用 `data/platform.db`（SQLite）。

## 資料庫切換邏輯（`config.py`）

```
若設定 NEON_DATABASE_URL → 使用 Neon（postgresql://）
否則若設定 DATABASE_URL  → 使用 postgresql:// 或 sqlite://
否則                       → SQLite（data/platform.db）
```

程式碼無需修改，改環境變數即可切換。

## 每日批次執行

```bash
# 手動執行（收盤後）
python main.py

# 排程（config.py SCHEDULE 設定時間點）
# 預設：
#   15:35 確認收盤
#   15:40 抓取股價（price_collector）
#   15:45 抓取法人（chip_collector）
#   15:50 抓取新聞（news_collector）
#   15:55 執行分析（analyzers → decision）
#   16:00 產生報告（report_generator）
#   16:05 更新 Dashboard 快取
```

## 雲端部署（Streamlit Community Cloud）

1. Push 到 GitHub repo
2. 在 Streamlit Community Cloud 連結 repo
3. 設定 Secrets（對應 `.env` 的環境變數）：
   ```toml
   ANTHROPIC_API_KEY = "sk-ant-..."
   FINMIND_TOKEN = "..."
   NEON_DATABASE_URL = "postgresql://..."
   ```
4. Main file path: `dashboard/app.py`

批次執行在 Streamlit Cloud 需要外部排程（如 GitHub Actions cron）呼叫 `main.py`，或使用 `src/scheduler.py`。

## 開發工具

```bash
# 執行測試
pytest tests/ -v --cov=src/analyzers --cov=src/collectors --cov-report=term-missing

# 格式化 + lint
black src/ dashboard/ tests/ config.py
isort src/ dashboard/ tests/ config.py
ruff check src/ dashboard/ tests/ config.py
flake8 src/ dashboard/ tests/ config.py --max-line-length=88

# CI（GitHub Actions）
# .github/workflows/test.yml 定義 test + lint 兩個 job
# Python 3.11 / 3.13 矩陣測試
```

## 目錄結構（關鍵路徑）

```
data/
  platform.db          # 本機 SQLite DB
  *.csv                # 歷史資料快取

reports/
  daily/               # YYYY-MM-DD_report.md
  backtests/

logs/
  platform.log

.env                   # 金鑰（不 commit）
```
