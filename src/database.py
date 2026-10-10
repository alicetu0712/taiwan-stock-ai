"""
database.py — SQLite 資料庫與 SQLAlchemy 設定

所有資料持久化透過此模組進行。
支援 Research Lifecycle、Decision Journal、歷史分析紀錄。
"""

import logging
from datetime import date as _date
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

logger = logging.getLogger(__name__)

# ── Research / Forward 邊界（固定，永不隨今日日期移動）─────────
# In-Sample  : analysis_results.date < RESEARCH_CUTOFF_DATE
# Out-of-Sample: forward_signals.trade_date >= RESEARCH_CUTOFF_DATE
RESEARCH_CUTOFF_DATE: _date = _date(2026, 10, 9)

MODEL_VERSION = "v6.0"


class Base(DeclarativeBase):
    pass


# ── 資料表定義 ─────────────────────────────────────────────────


class Stock(Base):
    """股票基本資料"""

    __tablename__ = "stocks"

    stock_id = Column(String(10), primary_key=True)
    name = Column(String(50), nullable=False)
    market = Column(String(10))  # TWSE / TPEx
    industry = Column(String(50))
    listing_date = Column(Date)
    capital = Column(Float)  # 資本額（億）
    outstanding_shares = Column(Float)  # 流通股數（千股）
    is_excluded = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=datetime.utcnow)


class DailyPrice(Base):
    """每日股價資料"""

    __tablename__ = "daily_prices"
    __table_args__ = (UniqueConstraint("stock_id", "date"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_id = Column(String(10), nullable=False)
    date = Column(Date, nullable=False)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Float)  # 成交量（千股）
    amount = Column(Float)  # 成交金額（百萬）
    change_pct = Column(Float)


class FinancialQuarter(Base):
    """季度財務數據"""

    __tablename__ = "financial_quarters"
    __table_args__ = (UniqueConstraint("stock_id", "year", "quarter"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_id = Column(String(10), nullable=False)
    year = Column(Integer, nullable=False)
    quarter = Column(Integer, nullable=False)
    eps = Column(Float)  # EPS（元）
    roe = Column(Float)  # 股東權益報酬率（%）
    roa = Column(Float)  # 資產報酬率（%）
    gross_margin = Column(Float)  # 毛利率（%）
    op_margin = Column(Float)  # 營業利益率（%）
    net_margin = Column(Float)  # 淨利率（%）
    debt_ratio = Column(Float)  # 負債比率（%）
    current_ratio = Column(Float)  # 流動比率
    quick_ratio = Column(Float)  # 速動比率
    free_cash_flow = Column(Float)  # 自由現金流（百萬）
    per = Column(Float)  # 本益比
    pbr = Column(Float)  # 股價淨值比
    dividend_yield = Column(Float)  # 殖利率（%）


class MonthlyRevenue(Base):
    """月營收資料"""

    __tablename__ = "monthly_revenue"
    __table_args__ = (UniqueConstraint("stock_id", "year", "month"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_id = Column(String(10), nullable=False)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    revenue = Column(Float)  # 營收（百萬）
    yoy_growth = Column(Float)  # YoY 成長率（%）


class InstitutionalData(Base):
    """三大法人每日買賣超"""

    __tablename__ = "institutional_data"
    __table_args__ = (UniqueConstraint("stock_id", "date"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_id = Column(String(10), nullable=False)
    date = Column(Date, nullable=False)
    foreign_net = Column(Float)  # 外資買賣超（張）
    trust_net = Column(Float)  # 投信買賣超（張）
    dealer_net = Column(Float)  # 自營商買賣超（張）
    total_net = Column(Float)  # 三大法人合計（張）


class MarginTrading(Base):
    """融資融券資料"""

    __tablename__ = "margin_trading"
    __table_args__ = (UniqueConstraint("stock_id", "date"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_id = Column(String(10), nullable=False)
    date = Column(Date, nullable=False)
    margin_balance = Column(Float)  # 融資餘額（張）
    margin_buy = Column(Float)  # 融資買進（張）
    margin_sell = Column(Float)  # 融資賣出（張）
    short_balance = Column(Float)  # 融券餘額（張）
    short_sell = Column(Float)  # 融券賣出（張）
    short_buy = Column(Float)  # 融券買進（張）


class AnalysisResult(Base):
    """每日分析結果"""

    __tablename__ = "analysis_results"
    __table_args__ = (UniqueConstraint("stock_id", "date"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_id = Column(String(10), nullable=False)
    date = Column(Date, nullable=False)
    quality_score = Column(Float)  # 基本面評分（0-100）
    quality_grade = Column(String(5))  # A+/A/B/C/D
    timing_score = Column(Float)  # Momentum（RSI/MACD）0-100（V2: 15%）
    behavior_score = Column(Float)  # 市場行為評分（0-100）
    intelligence_score = Column(Float)  # 情報評分（舊欄位，V2 不計分）
    risk_score = Column(Float)  # 風險評分（0-100，越高越安全）
    total_score = Column(Float)  # 綜合評分（0-100）
    confidence = Column(Float)  # 信心分數（%）
    rec_level = Column(String(5))  # A+/A/B/C/D
    # 分數動能（每日填入，供回測 / IC 診斷使用）
    score_change_5d = Column(Float)
    score_change_10d = Column(Float)
    timing_change_5d = Column(Float)    # timing_score 今日 − 5D 前
    behavior_change_5d = Column(Float)  # behavior_score 今日 − 5D 前
    # V2 新增欄位
    price_trend_score = Column(Float)   # PriceTrend 0-100（V2: 45%）
    setup_type = Column(String(20))     # breakout/pullback_buy/pullback_hold/trending/breakdown/none
    ma20_gap = Column(Float)            # (close−MA20)/MA20 × 100%
    volume_ratio = Column(Float)        # 當日量 / 20日均量
    trade_signal = Column(String(20))   # strong_buy/buy/wait/reduce/sell


class Recommendation(Base):
    """每日推薦紀錄"""

    __tablename__ = "recommendations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False)
    stock_id = Column(String(10), nullable=False)
    rec_level = Column(String(5))
    confidence = Column(Float)
    summary = Column(Text)  # 一句話摘要
    advantages = Column(Text)  # 主要優勢（JSON）
    risks = Column(Text)  # 主要風險（JSON）
    watch_points = Column(Text)  # 觀察重點（JSON）
    ai_conclusion = Column(Text)  # AI 結論
    # 評分快照（供 cooldown breakout exception 比較）
    total_score = Column(Float)
    timing_score = Column(Float)
    behavior_score = Column(Float)
    # 分數動能快照（填入時的 5D 變化，Rising Opportunities 顯示用）
    score_change_5d = Column(Float)
    score_change_10d = Column(Float)
    timing_change_5d = Column(Float)
    behavior_change_5d = Column(Float)
    # 層級標記：'recommend'（Core Picks）/ 'opportunity'（Rising）/ 'watch'
    tier = Column(String(20), default="recommend")
    stock_name = Column(String(60))
    strategy_version = Column(String(20), default="v7.0")
    # V2 新增欄位
    price_trend_score = Column(Float)
    setup_type = Column(String(20))
    ma20_gap = Column(Float)
    trade_signal = Column(String(20))   # strong_buy/buy/wait/reduce/sell
    created_at = Column(DateTime, default=datetime.utcnow)
    # Decision Center 欄位（ATR-based entry/exit，由 DecisionEngine 計算）
    entry_low   = Column(Float)
    entry_high  = Column(Float)
    stop_price  = Column(Float)
    target1     = Column(Float)
    target2     = Column(Float)
    atr         = Column(Float)
    vol_ratio   = Column(Float)


class DecisionJournal(Base):
    """研究決策日誌（Research Lifecycle）"""

    __tablename__ = "decision_journal"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False)
    stock_id = Column(String(10), nullable=False)
    quality_score = Column(Float)
    timing_score = Column(Float)
    behavior_score = Column(Float)
    intelligence_score = Column(Float)
    risk_score = Column(Float)
    confidence = Column(Float)
    rec_level = Column(String(5))
    action = Column(String(50))  # Recommended / WatchList / Rejected / Archived
    reason = Column(Text)
    market_env = Column(Text)  # 當日市場環境描述
    strategy_version = Column(String(20), default="v6.0")
    created_at = Column(DateTime, default=datetime.utcnow)


class ResearchStatus(Base):
    """股票研究狀態（Stage 1~6）"""

    __tablename__ = "research_status"

    stock_id = Column(String(10), primary_key=True)
    status = Column(
        String(20)
    )  # Universe/Qualified/Researching/WatchList/Candidate/Archived
    status_reason = Column(Text)
    last_rec_date = Column(Date)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PositionMonitor(Base):
    """持倉追蹤（推薦後自動建立，手動或訊號觸發關倉）"""

    __tablename__ = "position_monitor"

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_id = Column(String(10), nullable=False)
    stock_name = Column(String(50))
    date_entered = Column(Date, nullable=False)
    entry_price = Column(Float, nullable=False)

    # AI 設定的價格目標
    target_price = Column(Float)  # 目標價
    stop_loss_price = Column(Float)  # 停損價
    target_pct = Column(Float)  # 目標漲幅%
    stop_loss_pct = Column(Float)  # 停損跌幅%
    position_pct = Column(Float)  # 建議持倉比例%（依等級）
    ai_price_rationale = Column(Text)  # Claude 說明停損/目標依據

    # 推薦資訊
    rec_level = Column(String(5))
    rec_score = Column(Float)
    confidence = Column(Float)

    # 狀態
    status = Column(String(20), default="active")
    # active / closed_profit / closed_loss / closed_manual / closed_signal

    exit_date = Column(Date)
    exit_price = Column(Float)
    exit_reason = Column(String(50))
    # TARGET_HIT / STOP_LOSS / WEAK_TECHNICAL / INSTITUTIONAL_EXIT / MANUAL
    pnl_pct = Column(Float)
    mc_result = Column(Text)  # 預算蒙地卡羅結果（JSON）

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class UserTrade(Base):
    """使用者真實下單紀錄"""

    __tablename__ = "user_trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_id = Column(String(10), nullable=False)
    stock_name = Column(String(50))
    buy_date = Column(Date, nullable=False)
    buy_price = Column(Float, nullable=False)
    shares = Column(Integer, nullable=False, default=1)  # 張數
    target_price = Column(Float)  # 自設目標價
    stop_price = Column(Float)  # 自設停損價
    status = Column(String(10), default="holding")  # holding / closed
    sell_date = Column(Date)
    sell_price = Column(Float)
    realized_pnl = Column(Float)  # 實現損益（元）
    realized_pct = Column(Float)  # 實現損益（%）
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class ExecutionLog(Base):
    """每日執行記錄"""

    __tablename__ = "execution_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False)
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    status = Column(String(20))  # success / partial / failed
    total_stocks = Column(Integer)
    qualified_stocks = Column(Integer)
    recommended_stocks = Column(Integer)
    errors = Column(Text)
    strategy_version = Column(String(20), default="v6.0")


class DailyReport(Base):
    """每日報告（Markdown 內文，供雲端環境使用）"""

    __tablename__ = "daily_reports"
    __table_args__ = (UniqueConstraint("date"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False)
    content_md = Column(Text)
    strategy_version = Column(String(20), default="v6.0")
    created_at = Column(DateTime, default=datetime.utcnow)


class ForwardSignal(Base):
    """
    Forward validation signals — append-only，features 在建立當下凍結。

    Rules:
      - (trade_date, stock_id) UNIQUE — 重複資料只 skip，永不 UPDATE
      - locked_at 記錄凍結時間戳
      - 即使演算法改版，也禁止回頭覆寫歷史記錄
    """

    __tablename__ = "forward_signals"
    __table_args__ = (
        UniqueConstraint("trade_date", "stock_id", name="uq_fs_date_stock"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_date = Column(Date, nullable=False, index=True)
    stock_id = Column(String(10), nullable=False, index=True)
    stock_name = Column(String(50))

    # ── 凍結的 feature snapshot ─────────────────────────────
    pt_score = Column(Float)           # price_trend_score
    setup_type = Column(String(20))
    trade_signal = Column(String(20))
    ma20_gap = Column(Float)
    ma60_gap = Column(Float)           # (close − MA60) / MA60 × 100
    ma60_slope = Column(String(10))    # "up" / "down" / "flat"
    vol_ratio = Column(Float)
    total_score = Column(Float)
    timing_score = Column(Float)
    behavior_score = Column(Float)
    rec_level = Column(String(5))
    model_version = Column(String(20), default=MODEL_VERSION)

    # ── v2 追加欄位（signal 當下凍結，事後不可補）────────────────
    confidence              = Column(Float)        # 信心分數（%）
    industry                = Column(String(50))   # 產業分類
    market_regime_at_signal = Column(String(10))   # bull / neutral / bear
    close_at_signal         = Column(Float)        # 進場收盤價（免事後猜 entry）
    candidate_rank          = Column(Integer)      # 當日 candidates 中的排名（1=最高分）

    # ── 決策快照（Recommendation ATR plan 凍結，表示當時網站說什麼）──
    entry_low      = Column(Float)        # 建議進場區間下緣
    entry_high     = Column(Float)        # 建議進場區間上緣
    stop_price     = Column(Float)        # 停損價（凍結值）
    target1        = Column(Float)        # 目標價 T1
    target2        = Column(Float)        # 目標價 T2
    decision_label = Column(String(30))   # "BUY★" / "BUY" / "WAIT FOR PULLBACK" / "WAIT" / "REDUCE" / "SELL/AVOID"

    locked_at = Column(DateTime, default=datetime.utcnow)

    # ── 事後填入的績效結果（signal 成熟後逐步回填）─────────────────
    fwd_return_20d       = Column(Float)    # 20 交易日後報酬率（%）
    alpha_20d            = Column(Float)    # 超額報酬 vs 0050（%），20 交易日
    fwd_return_60d       = Column(Float)    # 60 交易日後報酬率（%）
    alpha_60d            = Column(Float)    # 超額報酬 vs 0050（%），60 交易日
    stop_triggered_day   = Column(Integer)  # 第幾個交易日收盤跌破停損（NULL = 未觸發）
    t1_hit_day           = Column(Integer)  # 第幾個交易日收盤首次達到 T1
    outcome_note         = Column(String(20))  # T1_HIT / STOP_TRIGGERED / EXPIRED / null
    outcomes_computed_at = Column(DateTime)


class PipelineFunnel(Base):
    """每日 pipeline 漏斗統計——追蹤各階段股票留存數"""

    __tablename__ = "pipeline_funnels"
    __table_args__ = (UniqueConstraint("date"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False)

    # 各 stage 的股票數（由上到下遞減）
    universe = Column(Integer, default=0)          # 全市場取得股價的股票數
    with_price = Column(Integer, default=0)        # 篩選至有歷史資料後
    hard_filter_pass = Column(Integer, default=0)  # 通過 Hard Filter
    deep_analyzed = Column(Integer, default=0)     # 完成深度分析（=hard_filter_pass）
    scored_55plus = Column(Integer, default=0)     # total_score ≥ 55
    scored_65plus = Column(Integer, default=0)     # total_score ≥ 65
    recommended = Column(Integer, default=0)       # 實際推薦

    # Hard Filter 失敗原因 Top 3（次數最多）
    fail_top1_reason = Column(String(120), default="")
    fail_top1_count = Column(Integer, default=0)
    fail_top2_reason = Column(String(120), default="")
    fail_top2_count = Column(Integer, default=0)
    fail_top3_reason = Column(String(120), default="")
    fail_top3_count = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)


# ── 引擎與 Session ───────────────────────────────────────────


def get_engine() -> Engine:
    from config import DATABASE_URL

    is_sqlite = DATABASE_URL.startswith("sqlite")
    engine = create_engine(
        DATABASE_URL,
        echo=False,
        future=True,
        **({"pool_pre_ping": True} if not is_sqlite else {}),
    )
    if is_sqlite:
        with engine.connect() as conn:
            conn.execute(text("PRAGMA journal_mode=WAL"))
            conn.execute(text("PRAGMA foreign_keys=ON"))
    return engine


def _migrate_forward_signals(engine) -> None:
    """forward_signals に新カラムを追加（既存 DB の自動マイグレーション）。"""
    from sqlalchemy import inspect, text

    new_cols = [
        ("confidence",              "FLOAT"),
        ("industry",                "VARCHAR(50)"),
        ("market_regime_at_signal", "VARCHAR(10)"),
        ("close_at_signal",         "FLOAT"),
        ("candidate_rank",          "INTEGER"),
        # 決策快照（Audit Trail — 凍結）
        ("entry_low",               "FLOAT"),
        ("entry_high",              "FLOAT"),
        ("stop_price",              "FLOAT"),
        ("target1",                 "FLOAT"),
        ("target2",                 "FLOAT"),
        ("decision_label",          "VARCHAR(30)"),
        # 績效結果（事後回填）
        ("fwd_return_20d",          "FLOAT"),
        ("alpha_20d",               "FLOAT"),
        ("fwd_return_60d",          "FLOAT"),
        ("alpha_60d",               "FLOAT"),
        ("stop_triggered_day",      "INTEGER"),
        ("t1_hit_day",              "INTEGER"),
        ("outcome_note",            "VARCHAR(20)"),
        ("outcomes_computed_at",    "DATETIME"),
    ]
    try:
        existing = {c["name"] for c in inspect(engine).get_columns("forward_signals")}
    except Exception:
        return  # table might not exist yet; create_all handles it
    with engine.begin() as conn:
        for col_name, col_type in new_cols:
            if col_name not in existing:
                try:
                    conn.execute(text(
                        f"ALTER TABLE forward_signals ADD COLUMN {col_name} {col_type}"
                    ))
                    logger.info(f"forward_signals: added column {col_name}")
                except Exception as exc:
                    logger.warning(f"forward_signals migration {col_name}: {exc}")


def _migrate_recommendations(engine) -> None:
    """recommendations に新カラムを追加（自動マイグレーション）。"""
    from sqlalchemy import inspect, text

    new_cols = [
        ("entry_low",   "FLOAT"),
        ("entry_high",  "FLOAT"),
        ("stop_price",  "FLOAT"),
        ("target1",     "FLOAT"),
        ("target2",     "FLOAT"),
        ("atr",         "FLOAT"),
        ("vol_ratio",   "FLOAT"),
    ]
    try:
        existing = {c["name"] for c in inspect(engine).get_columns("recommendations")}
    except Exception:
        return
    with engine.begin() as conn:
        for col_name, col_type in new_cols:
            if col_name not in existing:
                try:
                    conn.execute(text(
                        f"ALTER TABLE recommendations ADD COLUMN {col_name} {col_type}"
                    ))
                    logger.info(f"recommendations: added column {col_name}")
                except Exception as exc:
                    logger.warning(f"recommendations migration {col_name}: {exc}")


def init_db(engine: Optional[Engine] = None) -> Engine:
    if engine is None:
        engine = get_engine()
    Base.metadata.create_all(engine)
    _migrate_forward_signals(engine)
    _migrate_recommendations(engine)
    from config import DATABASE_URL

    logger.info(f"Database initialized: {DATABASE_URL[:40]}...")
    return engine


def get_session(engine=None) -> Session:
    if engine is None:
        engine = get_engine()
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    return SessionLocal()
