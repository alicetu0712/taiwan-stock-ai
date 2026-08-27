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
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
REPORTS_DIR = BASE_DIR / "reports"
LOGS_DIR = BASE_DIR / "logs"
DB_PATH = DATA_DIR / "platform.db"

for _d in [DATA_DIR, REPORTS_DIR / "daily", REPORTS_DIR / "backtests", LOGS_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

# ── API 金鑰 ──────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
FINMIND_TOKEN = os.getenv("FINMIND_TOKEN", "")

# ── 資料庫連線 ────────────────────────────────────────────────
# 本機 DB 檔存在 → SQLite（本機執行）
# 本機 DB 檔不存在 + NEON_URL 設定 → 直接用 Neon（Streamlit Cloud）
# 防止 shell 殘留的舊 DATABASE_URL 污染連線
_raw_db_url = os.getenv("DATABASE_URL", "")
_neon_url = os.getenv("NEON_URL", "")
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
HTTP_RETRY = 3
HTTP_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TaiwanStockResearch/6.0)"}

# ── TWSE / TPEx OpenAPI ───────────────────────────────────────
TWSE_API = {
    "daily_all": "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL",
    "listed_stocks": "https://openapi.twse.com.tw/v1/opendata/t187ap03_L",
    "market_index": "https://openapi.twse.com.tw/v1/exchangeReport/FMTQIK",
    "market_summary": "https://openapi.twse.com.tw/v1/exchangeReport/MI_INDEX",
    "foreign_net": "https://openapi.twse.com.tw/v1/exchangeReport/MI_QFIIS",
    "trust_net": "https://openapi.twse.com.tw/v1/exchangeReport/MI_SITC",
    "dealer_net": "https://openapi.twse.com.tw/v1/exchangeReport/MI_PROP",
    "margin": "https://openapi.twse.com.tw/v1/exchangeReport/MI_MARGN",
}

TPEX_API = {
    "daily_all": "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes",
    "listed_stocks": "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_stocks_information",
    "institutional": "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_institution_trading_summary",
    "margin": "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_margin_transactions",
}

# ── 新聞 RSS ──────────────────────────────────────────────────
NEWS_RSS_FEEDS = [
    "https://tw.stock.yahoo.com/rss",
    # MoneyDJ RSS 已失效（主機 SSL/連線失敗），暫時移除
    # "https://www.moneydj.com/rss/news.aspx",
]

# ── 技術分析參數 ──────────────────────────────────────────────
TA_CONFIG = {
    "ma_periods": [5, 10, 20, 60, 120, 240],
    "rsi_period": 14,
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
    "kd_period": 9,
    "bb_period": 20,
    "bb_std": 2,
    "atr_period": 14,
    "vol_ma": 20,
    "min_history": 60,
}

# ── AI 評分模型 ───────────────────────────────────────────────
# 各模組權重（合計 = 1.0）
SCORE_WEIGHTS = {
    "quality": 0.40,  # Company Quality（基本面）
    "timing": 0.25,  # Technical Timing（技術面）
    "behavior": 0.20,  # Market Behavior（籌碼）
    "intelligence": 0.10,  # Market Intelligence（情報）
    "risk": 0.05,  # Risk Penalty（風險扣分）
}

# ── 硬性篩選條件（Hard Filter）────────────────────────────────
# 只保留「基礎資格」與「明顯不適合」的底線；品質高低（ROE/ROA/負債/成長）
# 一律改由評分引擎（QUALITY_CONFIG + FundamentalAnalyzer）漸層計分。
HARD_FILTER = {
    "min_listing_years": 3,  # 上市年數 >= 3
    "min_market_cap_b": 10.0,  # 市值 >= 10億（單位：億）
    "min_capital_b": 2.0,  # 資本額 >= 2億（單位：億）
    "min_avg_daily_amt_m": 100.0,  # 平均日成交金額 >= 1億（單位：百萬，流動性底線）
    "min_ttm_eps": 0.0,  # TTM EPS > 0（必須獲利，唯一保留的財務底線）
    # ↓↓ 以下已停用於 hard filter，改由評分引擎漸層處理，避免懸崖式淘汰 ↓↓
    # "min_roe": 15.0,          # ROE：改由 QUALITY_CONFIG 計分
    # "min_roa": 8.0,           # ROA：改由 QUALITY_CONFIG 計分
    # "max_debt_ratio": 60.0,   # 負債比：改由 QUALITY_CONFIG 計分
    # "revenue_trend_years": 3, # 營收趨勢：改由評分引擎處理（不再直接淘汰）
    # "eps_trend_years": 3,     # EPS 趨勢：改由評分引擎處理（不再直接淘汰）
}

# ── Company Quality 評分參數 ──────────────────────────────────
QUALITY_CONFIG = {
    "roe": {
        "excellent": 20.0,  # ≥20% → 非常優秀
        "great": 15.0,  # ≥15% → 優秀
        "good": 10.0,  # ≥10% → 良好
        "pass": 8.0,  # ≥8%  → 普通
    },
    "roa": {
        "excellent": 12.0,
        "great": 8.0,
        "good": 5.0,
        "pass": 3.0,
    },
    "gross_margin": {
        "excellent": 40.0,
        "great": 30.0,
        "good": 20.0,
        "pass": 10.0,
    },
    "debt_ratio": {
        "safe": 30.0,  # ≤30% → 很安全
        "moderate": 50.0,  # ≤50% → 普通
        "risky": 60.0,  # ≤60% → 偏高
    },
}

# ── 推薦等級定義 ──────────────────────────────────────────────
RECOMMENDATION_LEVELS = {
    "A+": {"min_score": 85, "stars": "★★★★★", "label": "Strong Research Candidate"},
    "A": {"min_score": 75, "stars": "★★★★☆", "label": "Research Candidate"},
    "B": {"min_score": 65, "stars": "★★★☆☆", "label": "Watch List"},
    "C": {"min_score": 55, "stars": "★★☆☆☆", "label": "Observation Only"},
    "D": {"min_score": 0, "stars": "★☆☆☆☆", "label": "Not Recommended"},
}

# ── 推薦規則 ──────────────────────────────────────────────────
RECOMMENDATION_RULES = {
    "max_daily_recs": 3,  # 每日最多推薦 3 檔
    "min_confidence": 70.0,  # 最低信心分數（%）
    "min_quality_grade": "B",  # 最低品質等級（品質關卡的單一真相來源）
    # 註：min_total_score 已停用。品質門檻改由 rec_level（RECOMMENDATION_LEVELS）
    #     單一把關，避免與等級判斷重複。B 級 = 總分 ≥ 65（見 RECOMMENDATION_LEVELS）。
    # "min_total_score": 65.0,
}

# ── 觀察名單規則（未達正式推薦，但為當日相對最強的一群）──────────
# 目的：即使沒有正式推薦，也能顯示「今日最接近條件」的標的，
#       而非只顯示「今日無推薦」。採「絕對品質底線 + 相對排名」雙軌。
WATCH_LIST_RULES = {
    "min_score": 50.0,  # 絕對底線：總分至少 50 才可能入觀察名單
    "top_percentile": 90.0,  # 相對排名：當日 percentile ≥ 90（前 10%）
    "min_confidence": 60.0,  # 觀察名單的信心要求（低於正式推薦的 70%）
    "max_watch": 5,  # 觀察名單最多顯示檔數
}

# ── 可負擔性榜（預算榜）規則 ──────────────────────────────────
# 原則：股票「評分」完全不看股價（不因股價高低加減分）；
#       此處只在「評分之後」，額外篩出資金可負擔的最佳標的另立一榜。
#       高價績優股不會被扣分，只是不出現在你的「可負擔榜」。
AFFORDABILITY = {
    "max_price": 300.0,  # 單股股價上限（元）；None = 不限
    "max_lot_cost": None,  # 單張成本上限（元 = 股價 × 每張股數）；None = 不限
    "shares_per_lot": 1000,  # 台股每張 = 1000 股
    "min_score": 50.0,  # 可負擔榜的品質底線（避免列出便宜但爛的股票）
    "max_list": 5,  # 可負擔榜最多顯示檔數
}

# ── 排程時間 ──────────────────────────────────────────────────
SCHEDULE = {
    "check_close": "15:35",
    "fetch_price": "15:40",
    "fetch_chip": "15:45",
    "fetch_news": "15:50",
    "run_analysis": "15:55",
    "generate_report": "16:00",
    "update_dashboard": "16:05",
}

# ── AI 模型設定 ───────────────────────────────────────────────
AI_CONFIG = {
    "model": "claude-sonnet-4-6",
    "max_tokens": 2048,
    "temperature": 0.3,
}

# ── 排除條件 ──────────────────────────────────────────────────
EXCLUDE_KEYWORDS = [
    "ETF",
    "ETN",
    "權證",
    "牛熊",
    "認購",
    "認售",
    "期貨",
    "選擇權",
    "特別股",
    "存託憑證",
    "DR",
]

EXCLUDE_PATTERNS = [
    r"^\d{4}[A-Z]",  # 權證代號
    r"^7[89]\d{2}",  # 興櫃
]
