"""
config.py — 全域設定中心

AI Taiwan Equity Research Platform v6.0
所有策略參數皆可由此調整，無需修改程式碼。
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(override=True)

# ── 路徑 ──────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent
DATA_DIR    = BASE_DIR / "data"
REPORTS_DIR = BASE_DIR / "reports"
LOGS_DIR    = BASE_DIR / "logs"
DB_PATH     = DATA_DIR / "platform.db"

for _d in [DATA_DIR, REPORTS_DIR / "daily", REPORTS_DIR / "backtests", LOGS_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

# ── API 金鑰 ──────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
FINMIND_TOKEN     = os.getenv("FINMIND_TOKEN", "")

# ── 資料庫連線 ────────────────────────────────────────────────
# 本機 DB 檔存在 → SQLite（本機執行）
# 本機 DB 檔不存在 + NEON_URL 設定 → 直接用 Neon（Streamlit Cloud）
# 防止 shell 殘留的舊 DATABASE_URL 污染連線
_raw_db_url = os.getenv("DATABASE_URL", "")
_neon_url   = os.getenv("NEON_URL", "")
if DB_PATH.exists():
    DATABASE_URL = f"sqlite:///{DB_PATH}"
elif _neon_url:
    DATABASE_URL = _neon_url.replace("postgres://", "postgresql://", 1)
elif _raw_db_url.startswith("postgres://"):
    DATABASE_URL = _raw_db_url.replace("postgres://", "postgresql://", 1)
elif _raw_db_url.startswith("postgresql://"):
    DATABASE_URL = _raw_db_url
else:
    DATABASE_URL = f"sqlite:///{DB_PATH}"

# ── HTTP 設定 ─────────────────────────────────────────────────
HTTP_TIMEOUT = 30
HTTP_RETRY   = 3
HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TaiwanStockResearch/6.0)"
}

# ── TWSE / TPEx OpenAPI ───────────────────────────────────────
TWSE_API = {
    "daily_all":       "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL",
    "listed_stocks":   "https://openapi.twse.com.tw/v1/opendata/t187ap03_L",
    "market_index":    "https://openapi.twse.com.tw/v1/exchangeReport/FMTQIK",
    "market_summary":  "https://openapi.twse.com.tw/v1/exchangeReport/MI_INDEX",
    "foreign_net":     "https://openapi.twse.com.tw/v1/exchangeReport/MI_QFIIS",
    "trust_net":       "https://openapi.twse.com.tw/v1/exchangeReport/MI_SITC",
    "dealer_net":      "https://openapi.twse.com.tw/v1/exchangeReport/MI_PROP",
    "margin":          "https://openapi.twse.com.tw/v1/exchangeReport/MI_MARGN",
}

TPEX_API = {
    "daily_all":       "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes",
    "listed_stocks":   "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_stocks_information",
    "institutional":   "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_institution_trading_summary",
    "margin":          "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_margin_transactions",
}

# ── 新聞 RSS ──────────────────────────────────────────────────
NEWS_RSS_FEEDS = [
    "https://tw.stock.yahoo.com/rss",
    "https://www.moneydj.com/rss/news.aspx",
]

# ── 技術分析參數 ──────────────────────────────────────────────
TA_CONFIG = {
    "ma_periods":   [5, 10, 20, 60, 120, 240],
    "rsi_period":   14,
    "macd_fast":    12,
    "macd_slow":    26,
    "macd_signal":  9,
    "kd_period":    9,
    "bb_period":    20,
    "bb_std":       2,
    "atr_period":   14,
    "vol_ma":       20,
    "min_history":  60,
}

# ── AI 評分模型 ───────────────────────────────────────────────
# 各模組權重（合計 = 1.0）
SCORE_WEIGHTS = {
    "quality":    0.40,   # Company Quality（基本面）
    "timing":     0.25,   # Technical Timing（技術面）
    "behavior":   0.20,   # Market Behavior（籌碼）
    "intelligence": 0.10, # Market Intelligence（情報）
    "risk":       0.05,   # Risk Penalty（風險扣分）
}

# ── 硬性篩選條件（Hard Filter）────────────────────────────────
HARD_FILTER = {
    "min_listing_years":      3,       # 上市年數 >= 3
    "min_market_cap_b":       10.0,    # 市值 >= 100億（單位：億）
    "min_capital_b":          2.0,     # 資本額 >= 20億（單位：億）
    "min_avg_daily_amt_m":    100.0,   # 平均日成交金額 >= 1億（單位：百萬）
    "min_ttm_eps":            0.0,     # TTM EPS > 0
    "min_roe":                15.0,    # ROE >= 15%
    "min_roa":                8.0,     # ROA >= 8%
    "max_debt_ratio":         60.0,    # 負債比率 <= 60%
    "revenue_trend_years":    3,       # 至少 3 年營收趨勢
    "eps_trend_years":        3,       # 至少 3 年 EPS 趨勢
}

# ── Company Quality 評分參數 ──────────────────────────────────
QUALITY_CONFIG = {
    "roe": {
        "excellent": 20.0,   # ≥20% → 非常優秀
        "great":     15.0,   # ≥15% → 優秀
        "good":      10.0,   # ≥10% → 良好
        "pass":       8.0,   # ≥8%  → 普通
    },
    "roa": {
        "excellent": 12.0,
        "great":      8.0,
        "good":       5.0,
        "pass":       3.0,
    },
    "gross_margin": {
        "excellent": 40.0,
        "great":     30.0,
        "good":      20.0,
        "pass":      10.0,
    },
    "debt_ratio": {
        "safe":       30.0,   # ≤30% → 很安全
        "moderate":   50.0,   # ≤50% → 普通
        "risky":      60.0,   # ≤60% → 偏高
    },
}

# ── 推薦等級定義 ──────────────────────────────────────────────
RECOMMENDATION_LEVELS = {
    "A+": {"min_score": 85, "stars": "★★★★★", "label": "Strong Research Candidate"},
    "A":  {"min_score": 75, "stars": "★★★★☆", "label": "Research Candidate"},
    "B":  {"min_score": 65, "stars": "★★★☆☆", "label": "Watch List"},
    "C":  {"min_score": 55, "stars": "★★☆☆☆", "label": "Observation Only"},
    "D":  {"min_score": 0,  "stars": "★☆☆☆☆", "label": "Not Recommended"},
}

# ── 推薦規則 ──────────────────────────────────────────────────
RECOMMENDATION_RULES = {
    "max_daily_recs":         3,       # 每日最多推薦 3 檔
    "min_confidence":         70.0,    # 最低信心分數（%）
    "min_quality_grade":      "B",     # 最低品質等級
    "min_total_score":        65.0,    # 最低綜合評分
}

# ── 排程時間 ──────────────────────────────────────────────────
SCHEDULE = {
    "check_close":     "15:35",
    "fetch_price":     "15:40",
    "fetch_chip":      "15:45",
    "fetch_news":      "15:50",
    "run_analysis":    "15:55",
    "generate_report": "16:00",
    "update_dashboard":"16:05",
}

# ── AI 模型設定 ───────────────────────────────────────────────
AI_CONFIG = {
    "model":       "claude-sonnet-4-6",
    "max_tokens":  2048,
    "temperature": 0.3,
}

# ── 排除條件 ──────────────────────────────────────────────────
EXCLUDE_KEYWORDS = [
    "ETF", "ETN", "權證", "牛熊", "認購", "認售",
    "期貨", "選擇權", "特別股", "存託憑證", "DR"
]

EXCLUDE_PATTERNS = [
    r"^\d{4}[A-Z]",  # 權證代號
    r"^7[89]\d{2}",  # 興櫃
]
