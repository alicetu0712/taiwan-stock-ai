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

MODEL_VERSION = "v8.0"


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
    delisted_date = Column(Date)     # None = 仍上市；非 None = 下市日期（供 survivorship bias 修正）
    security_status = Column(String(20), default="listed")  # listed / delisted / suspended / unknown
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
    ma60_gap    = Column(Float)           # (close − MA60) / MA60 × 100%, frozen at signal time
    # Decision Center snapshot
    decision_code          = Column(String(20))   # final code after DC override (e.g. wait_pullback ≠ trade_signal)
    decision_label_version = Column(String(20))   # DECISION_CENTER_VERSION at signal time
    rr_ratio               = Column(Float)        # (target1 − close) / (close − stop_price)
    market_regime          = Column(String(10))   # bull / neutral / bear at signal time
    # Stock-level data quality (JSON: price/ma60/volume/pt_score/institution/financial + confidence)
    data_quality_json = Column(Text)
    # Data Integrity — validity gate
    is_valid          = Column(Boolean, default=True)    # False = 此紀錄不得參與任何績效統計
    invalid_reason    = Column(String(60))               # NON_TRADING_DAY_DATE_MISMATCH / PRICE_DATE_MISMATCH / etc.
    source_price_date = Column(Date)                     # 實際股價資料日期（vs date 欄位）
    # Scoring data completeness — tracks which factor dimensions had real data
    missing_data_factors = Column(String(40))            # comma-separated: e.g. "quality,behavior"; NULL = complete
    # Signal Lifecycle — managed by live_background_service
    lifecycle_status = Column(String(20), default='active')  # active / invalidated / superseded


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
    """持倉追蹤（推薦後建立 pending_open，次日 open 確認後轉 active）

    狀態機：
      pending_open  → active（次日 open 取得）
      pending_open  → cancelled（訊號失效：lifecycle != BUY / is_valid=False）
      active        → closed_profit / closed_loss / closed_manual / closed_signal
    """

    __tablename__ = "position_monitor"

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_id = Column(String(10), nullable=False)
    stock_name = Column(String(50))
    # signal_date = 推薦當日（= ForwardSignal.trade_date）
    signal_date = Column(Date)
    # expected_execution_date = 次日交易日（signal_date + 1 trading day）
    expected_execution_date = Column(Date)
    # date_entered / entry_price 在 pending_open 時為 NULL；active 時必填
    date_entered = Column(Date)
    entry_price = Column(Float)
    # entry_source 追溯進場語意：
    #   NEXT_OPEN            = Shadow Trading（次日開盤進場，foe_v1 對齊）
    #   SIGNAL_CLOSE_LEGACY  = Pre-fix 持倉（以訊號日收盤進場，不計入 Shadow Trading 績效）
    #   CONFIRMED            = 手動/直接建倉
    entry_source = Column(String(30))

    # shadow_trading_type 區分執行時點語意：
    #   NEXT_OPEN_HISTORICAL   = 收盤後 pipeline 執行，open 為已知資訊（回測等同）
    #   LIVE_PREOPEN_OBSERVED  = 盤前 pipeline 執行，open 尚未揭示（須另建盤前流程才可用）
    #   NULL                   = SIGNAL_CLOSE_LEGACY 舊資料（不計入 Shadow Trading 績效）
    shadow_trading_type = Column(String(30))

    # execution_recorded_at：activate_pending_positions 激活此持倉的時間戳記
    # 對照 expected_execution_date 可計算激活延遲，供績效分類稽核使用
    execution_recorded_at = Column(DateTime)

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
    status = Column(String(20), default="pending_open")
    # pending_open / active / cancelled
    # closed_profit / closed_loss / closed_manual / closed_signal

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


class LiveExecutionEvent(Base):
    """
    盤中 Live Decision 狀態轉換記錄（Forward 研究資料集）

    寫入時機：State Transition（prev_status → live_status 發生改變時）。
    不記錄持續不變的狀態，避免每 10 秒產生一筆無研究價值的重複資料。

    用途：
      - 回答「RAPID_DROP 攔截的 BUY，20D 後表現如何？」
      - 不同門檻（-2.5%/-4% × +1%/+3%/+5%）× 20D Alpha 矩陣
      - live_rule_version 用於比較不同版本門檻的效果
    """

    __tablename__ = "live_execution_events"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Signal context
    stock_id     = Column(String(10), nullable=False, index=True)
    signal_date  = Column(Date, nullable=False, index=True)   # BUY 訊號日期
    signal_price = Column(Float)                              # 訊號日收盤價

    # Observation context
    observed_at   = Column(DateTime, nullable=False, default=datetime.utcnow)
    current_price = Column(Float)   # 觀察當下即時成交
    intraday_low  = Column(Float)   # 今日截至觀察時最低點

    # State transition
    prev_status = Column(String(30))    # 前一狀態（None = 首次觀察）
    live_status = Column(String(30), nullable=False)

    # Metrics at observation time
    drop_pct          = Column(Float)   # 低點 vs 訊號價跌幅（%）
    bounce_pct        = Column(Float)   # 現價 vs 低點反彈幅度（%）
    rr_at_observation = Column(Float)   # 以現價計算的 R/R

    # Signal plan frozen at signal_date (from Recommendation)
    entry_low   = Column(Float)
    entry_high  = Column(Float)
    stop_price  = Column(Float)
    target1     = Column(Float)

    # Data quality at observation time
    quote_trade_date = Column(String(8))    # YYYYMMDD（報價來源日期）
    quote_quality    = Column(String(10))   # valid / stale / unknown

    # Version tracking — enables comparing rule versions in future research
    strategy_version  = Column(String(20))
    live_rule_version = Column(String(20))


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
    close_at_signal         = Column(Float)        # signal_date 收盤價（legacy 相容欄，非進場價）
    candidate_rank          = Column(Integer)      # 當日 candidates 中的排名（1=最高分）

    # ── 執行時機修正（Execution Timing Bias fix）─────────────────
    signal_close            = Column(Float)        # signal_date 收盤價（明確語意，同 close_at_signal）
    execution_date          = Column(Date)         # 實際執行日（signal_date 後首個交易日）
    execution_price         = Column(Float)        # 執行日開盤進場價（NEXT_OPEN）
    execution_price_type    = Column(String(20))   # "NEXT_OPEN" | "SIGNAL_CLOSE_LEGACY"

    # ── 決策快照（Recommendation ATR plan 凍結，表示當時網站說什麼）──
    entry_low      = Column(Float)        # 建議進場區間下緣
    entry_high     = Column(Float)        # 建議進場區間上緣
    stop_price     = Column(Float)        # 停損價（凍結值）
    target1        = Column(Float)        # 目標價 T1
    target2        = Column(Float)        # 目標價 T2
    decision_label = Column(String(30))   # stable code: strong_buy/buy/wait_pullback/wait/reduce/sell

    locked_at = Column(DateTime, default=datetime.utcnow)

    # ── 事後填入的績效結果（signal 成熟後逐步回填）─────────────────
    fwd_return_20d       = Column(Float)    # 20 交易日後報酬率（%）
    alpha_20d            = Column(Float)    # 超額報酬 vs 0050（%），20 交易日
    fwd_return_60d       = Column(Float)    # 60 交易日後報酬率（%）
    alpha_60d            = Column(Float)    # 超額報酬 vs 0050（%），60 交易日
    stop_triggered_day   = Column(Integer)  # 第幾個交易日收盤跌破停損（NULL = 未觸發）
    t1_hit_day           = Column(Integer)  # 第幾個交易日收盤首次達到 T1
    outcome_note          = Column(String(20))  # T1_HIT / STOP_TRIGGERED / EXPIRED / null
    outcome_price_quality = Column(String(10))  # OHLC / CLOSE_ONLY — whether stop/T1 scan used intraday H/L or close fallback
    outcomes_computed_at  = Column(DateTime)
    # Data Integrity — validity gate
    is_valid          = Column(Boolean, default=True)    # False = 此紀錄不得參與任何績效統計
    invalid_reason    = Column(String(60))               # NON_TRADING_DAY_DATE_MISMATCH / PRICE_DATE_MISMATCH
    source_price_date = Column(Date)                     # 實際股價資料日期（vs trade_date 欄位）


class OvernightMarketContext(Base):
    """
    隔夜市場風險快照 — 每個 execution_date × overnight_rule_version 唯一一筆。

    建立時機：TW 盤前（live_background_service.run_once 開頭）。
    Live Monitor 只讀 DB，不直接呼叫外部 API。

    時間層說明：
      us_market_date   = 最近完成的美股 regular session 日期
      available_at     = us_market_date 16:00 ET（UTC-aware），代表資料的最早可取得時間
      source_timestamp = Yahoo API 回傳的原始 timestamp（不得修改語意）
      fetched_at       = 系統實際 fetch 時間（UTC）

    data_quality:
      COMPLETE = 全部指標齊全且 exact-session match
      PARTIAL  = 部分指標缺失
      STALE    = 取得的 session date ≠ 預期 us_market_date
      UNKNOWN  = 完全無法取得

    重要：UNKNOWN / STALE 不得產生 GREEN risk_level。
    """

    __tablename__ = "overnight_market_contexts"
    __table_args__ = (
        UniqueConstraint(
            "execution_date", "overnight_rule_version",
            name="uq_omc_exec_date_version",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Date mapping
    execution_date = Column(Date, nullable=False, index=True)
    us_market_date = Column(Date)                           # prev US trading day

    # US market returns (1-day return vs prior session close, %)
    sp500_return_pct    = Column(Float)    # ^GSPC
    nasdaq_return_pct   = Column(Float)    # ^IXIC
    sox_return_pct      = Column(Float)    # ^SOX

    # VIX
    vix_close           = Column(Float)    # absolute level
    vix_change_pct      = Column(Float)    # % change from prior session

    # Taiwan futures overnight (NULL in v1 — no reliable free source)
    taiex_futures_overnight_return_pct = Column(Float)

    # Risk assessment
    risk_level          = Column(String(10), nullable=False)  # GREEN/YELLOW/RED/UNKNOWN
    risk_score          = Column(Float)                       # nullable in v1
    risk_reasons_json   = Column(Text)                        # JSON list of reason dicts

    # Data quality
    data_quality        = Column(String(10), nullable=False)  # COMPLETE/PARTIAL/STALE/UNKNOWN

    # Source provenance — Yahoo timestamp and our availability calculation are separate
    source_name         = Column(String(50))
    source_timestamp    = Column(DateTime)    # raw timestamp from Yahoo (UTC-naive stored as UTC)
    available_at        = Column(DateTime)    # us_market_date 16:00 ET as UTC (DST-correct)
    fetched_at          = Column(DateTime, default=datetime.utcnow)

    # Version — bump only when threshold semantics or classification logic changes
    overnight_rule_version = Column(String(20), nullable=False)

    # Retry tracking for transient UNKNOWN contexts (fetch_error before freeze time)
    retry_count = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)


class ForwardOutcomeEvaluation(Base):
    """
    foe_v1 pre-registered outcome evaluation — one row per (signal × path × protocol).

    Unique key: (forward_signal_id, path_type, outcome_protocol_version).
    Two rows per eligible signal: BASELINE_NEXT_OPEN + OVERNIGHT_AWARE_RECONFIRMED.

    Mutability rules:
      - Row is mutable while horizons are accumulating.
      - Once horizon_20d_matured_at is set, the entire 20D bundle is IMMUTABLE.
      - Once horizon_60d_matured_at is set, the entire 60D bundle is IMMUTABLE.
      - Evaluation semantics changes require foe_v2, never retroactive overwrite.

    Invariants (when both horizons complete for the same row):
      mae_60d <= mae_20d  (60D window ⊇ 20D window)
      mfe_60d >= mfe_20d
    """

    __tablename__ = "forward_outcome_evaluations"
    __table_args__ = (
        UniqueConstraint(
            "forward_signal_id", "path_type", "outcome_protocol_version",
            name="uq_foe_signal_path_version",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Identity
    forward_signal_id    = Column(Integer, nullable=False, index=True)   # FK → forward_signals.id
    signal_evaluation_id = Column(String(60))   # "{stock_id}_{signal_date}" — human-readable
    stock_id             = Column(String(10), nullable=False, index=True)
    signal_date          = Column(Date, nullable=False, index=True)

    # Path and protocol versions
    path_type                  = Column(String(40), nullable=False)   # BASELINE_NEXT_OPEN / OVERNIGHT_AWARE_RECONFIRMED
    outcome_protocol_version   = Column(String(20), nullable=False)   # foe_v1
    overnight_rule_version     = Column(String(20))   # overnight_v1 or NULL (legacy)
    overnight_risk_level       = Column(String(10))   # GREEN/YELLOW/RED/UNKNOWN or NULL
    overnight_context_id       = Column(Integer)       # FK → overnight_market_contexts.id
    live_rule_version          = Column(String(20))

    # Execution status and entry
    entry_status               = Column(String(30))   # EXECUTED / EXPIRED_BEFORE_ENTRY / INVALIDATED_BEFORE_ENTRY / PENDING / DATA_INSUFFICIENT / NOT_APPLICABLE
    entry_date                 = Column(Date)
    entry_timestamp            = Column(DateTime)     # Aware path: ENTRY_RECONFIRMED observed_at
    entry_price                = Column(Float)
    entry_price_type           = Column(String(40))   # BASELINE_NEXT_OPEN / LIVE_ENTRY_RECONFIRMED_QUOTE
    entry_quote_quality        = Column(String(10))   # Aware path only

    # MAE/MFE scan window metadata
    mae_mfe_start_date         = Column(Date)         # entry_date (Baseline) or next_td (Aware)
    entry_day_excursion_excluded = Column(Boolean)    # False (Baseline) / True (Aware)

    # Benchmark
    benchmark_entry_date         = Column(Date)
    benchmark_entry_price        = Column(Float)
    benchmark_entry_price_type   = Column(String(20))   # "0050_DAILY_OPEN"
    benchmark_timing_approximation = Column(Boolean)   # False (Baseline) / True (Aware)

    # Transaction cost assumption (snapshot at computation time)
    transaction_cost_assumption  = Column(Float)       # e.g. 0.585

    # ── 20D FINALIZATION BUNDLE (immutable after horizon_20d_matured_at is set) ──
    return_20d               = Column(Float)
    alpha_20d                = Column(Float)
    mae_20d                  = Column(Float)
    mfe_20d                  = Column(Float)
    target_stop_outcome_20d  = Column(String(25))   # T1_FIRST / STOP_FIRST / SAME_DAY_AMBIGUOUS / NEITHER
    target_hit_date_20d      = Column(Date)
    stop_hit_date_20d        = Column(Date)
    outcome_data_quality_20d = Column(String(25))
    horizon_20d_matured_at   = Column(DateTime)     # set once; guards 20D bundle immutability

    # ── 60D FINALIZATION BUNDLE (immutable after horizon_60d_matured_at is set) ──
    return_60d               = Column(Float)
    alpha_60d                = Column(Float)
    mae_60d                  = Column(Float)
    mfe_60d                  = Column(Float)
    target_stop_outcome_60d  = Column(String(25))
    target_hit_date_60d      = Column(Date)
    stop_hit_date_60d        = Column(Date)
    outcome_data_quality_60d = Column(String(25))
    horizon_60d_matured_at   = Column(DateTime)

    # Exclusion (formal overnight cohort eligibility)
    exclusion_reason         = Column(String(50))   # NO_OVERNIGHT_DATA / MISSING_VALID_NEXT_OPEN_ENTRY / …

    # Audit
    created_at  = Column(DateTime, default=datetime.utcnow)
    updated_at  = Column(DateTime, default=datetime.utcnow)


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


def _safe_add_cols(engine, table: str, new_cols: list) -> None:
    """ALTER TABLE helper: each column runs in its own transaction.
    Converts DATETIME → TIMESTAMP on PostgreSQL so the same migration list
    works on both SQLite (local dev) and PostgreSQL (Railway / Neon).
    """
    from sqlalchemy import inspect, text

    is_pg = engine.dialect.name == "postgresql"
    try:
        existing = {c["name"] for c in inspect(engine).get_columns(table)}
    except Exception:
        return
    for col_name, col_type in new_cols:
        if col_name in existing:
            continue
        if is_pg:
            pg_type = (col_type
                       .replace("DATETIME", "TIMESTAMP")
                       .replace("DEFAULT 1", "DEFAULT TRUE")
                       .replace("DEFAULT 0", "DEFAULT FALSE"))
        else:
            pg_type = col_type
        with engine.begin() as conn:
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {pg_type}"))
                logger.info(f"{table}: added column {col_name}")
            except Exception as exc:
                logger.warning(f"{table} migration {col_name}: {exc}")


def _migrate_stocks(engine) -> None:
    """stocks テーブルに新カラムを追加（自動マイグレーション）。"""
    from sqlalchemy import inspect, text

    new_cols = [
        ("delisted_date",   "DATE"),
        ("security_status", "VARCHAR(20) DEFAULT 'listed'"),
    ]
    try:
        existing = {c["name"] for c in inspect(engine).get_columns("stocks")}
    except Exception:
        return
    with engine.begin() as conn:
        for col_name, col_type in new_cols:
            if col_name not in existing:
                try:
                    conn.execute(text(
                        f"ALTER TABLE stocks ADD COLUMN {col_name} {col_type}"
                    ))
                    logger.info(f"stocks: added column {col_name}")
                except Exception as exc:
                    logger.warning(f"stocks migration {col_name}: {exc}")


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
        ("outcome_price_quality",   "VARCHAR(10)"),
        ("outcomes_computed_at",    "DATETIME"),
        # Data Integrity validity gate
        ("is_valid",                "BOOLEAN DEFAULT 1"),
        ("invalid_reason",          "VARCHAR(60)"),
        ("source_price_date",       "DATE"),
        # Execution Timing Bias fix
        ("signal_close",            "FLOAT"),
        ("execution_date",          "DATE"),
        ("execution_price",         "FLOAT"),
        ("execution_price_type",    "VARCHAR(20)"),
    ]
    _safe_add_cols(engine, "forward_signals", new_cols)


def _migrate_recommendations(engine) -> None:
    """recommendations に新カラムを追加（自動マイグレーション）。"""
    from sqlalchemy import inspect, text

    new_cols = [
        ("entry_low",         "FLOAT"),
        ("entry_high",        "FLOAT"),
        ("stop_price",        "FLOAT"),
        ("target1",           "FLOAT"),
        ("target2",           "FLOAT"),
        ("atr",               "FLOAT"),
        ("vol_ratio",         "FLOAT"),
        ("ma60_gap",          "FLOAT"),
        # Decision Center snapshot
        ("decision_code",          "VARCHAR(20)"),
        ("decision_label_version", "VARCHAR(20)"),
        ("rr_ratio",               "FLOAT"),
        ("market_regime",          "VARCHAR(10)"),
        # Stock-level data quality
        ("data_quality_json", "TEXT"),
        # Data Integrity validity gate
        ("is_valid",          "BOOLEAN DEFAULT 1"),
        ("invalid_reason",    "VARCHAR(60)"),
        ("source_price_date", "DATE"),
        # Scoring data completeness
        ("missing_data_factors", "VARCHAR(40)"),
        # Signal Lifecycle
        ("lifecycle_status", "VARCHAR(20) DEFAULT 'active'"),
        # Scoring fields added in v7+
        ("tier",             "VARCHAR(20)"),
        ("stock_name",       "VARCHAR(60)"),
        ("behavior_score",   "FLOAT"),
        ("timing_score",     "FLOAT"),
        ("total_score",      "FLOAT"),
        ("score_change_5d",  "FLOAT"),
        ("score_change_10d", "FLOAT"),
        ("timing_change_5d", "FLOAT"),
        ("behavior_change_5d", "FLOAT"),
    ]
    _safe_add_cols(engine, "recommendations", new_cols)


def _migrate_analysis_results(engine) -> None:
    """analysis_results に新カラムを追加（自動マイグレーション）。"""
    from sqlalchemy import inspect, text

    new_cols = [
        ("score_change_5d",    "FLOAT"),
        ("score_change_10d",   "FLOAT"),
        ("timing_change_5d",   "FLOAT"),
        ("behavior_change_5d", "FLOAT"),
    ]
    _safe_add_cols(engine, "analysis_results", new_cols)


def _migrate_forward_outcome_evaluations(engine) -> None:
    """forward_outcome_evaluations に新カラムを追加（自動マイグレーション）。"""
    from sqlalchemy import inspect, text

    new_cols = [
        ("forward_signal_id",           "INTEGER NOT NULL DEFAULT 0"),
        ("signal_evaluation_id",         "VARCHAR(60)"),
        ("stock_id",                     "VARCHAR(10) NOT NULL DEFAULT ''"),
        ("signal_date",                  "DATE NOT NULL DEFAULT '1970-01-01'"),
        ("path_type",                    "VARCHAR(40) NOT NULL DEFAULT ''"),
        ("outcome_protocol_version",     "VARCHAR(20) NOT NULL DEFAULT 'foe_v1'"),
        ("overnight_rule_version",       "VARCHAR(20)"),
        ("overnight_risk_level",         "VARCHAR(10)"),
        ("overnight_context_id",         "INTEGER"),
        ("live_rule_version",            "VARCHAR(20)"),
        ("entry_status",                 "VARCHAR(30)"),
        ("entry_date",                   "DATE"),
        ("entry_timestamp",              "DATETIME"),
        ("entry_price",                  "FLOAT"),
        ("entry_price_type",             "VARCHAR(40)"),
        ("entry_quote_quality",          "VARCHAR(10)"),
        ("mae_mfe_start_date",           "DATE"),
        ("entry_day_excursion_excluded", "BOOLEAN"),
        ("benchmark_entry_date",         "DATE"),
        ("benchmark_entry_price",        "FLOAT"),
        ("benchmark_entry_price_type",   "VARCHAR(20)"),
        ("benchmark_timing_approximation", "BOOLEAN"),
        ("transaction_cost_assumption",  "FLOAT"),
        ("return_20d",                   "FLOAT"),
        ("alpha_20d",                    "FLOAT"),
        ("mae_20d",                      "FLOAT"),
        ("mfe_20d",                      "FLOAT"),
        ("target_stop_outcome_20d",      "VARCHAR(25)"),
        ("target_hit_date_20d",          "DATE"),
        ("stop_hit_date_20d",            "DATE"),
        ("outcome_data_quality_20d",     "VARCHAR(25)"),
        ("horizon_20d_matured_at",       "DATETIME"),
        ("return_60d",                   "FLOAT"),
        ("alpha_60d",                    "FLOAT"),
        ("mae_60d",                      "FLOAT"),
        ("mfe_60d",                      "FLOAT"),
        ("target_stop_outcome_60d",      "VARCHAR(25)"),
        ("target_hit_date_60d",          "DATE"),
        ("stop_hit_date_60d",            "DATE"),
        ("outcome_data_quality_60d",     "VARCHAR(25)"),
        ("horizon_60d_matured_at",       "DATETIME"),
        ("exclusion_reason",             "VARCHAR(50)"),
        ("created_at",                   "DATETIME"),
        ("updated_at",                   "DATETIME"),
    ]
    _safe_add_cols(engine, "forward_outcome_evaluations", new_cols)


def _migrate_overnight_market_contexts(engine) -> None:
    """overnight_market_contexts に新カラムを追加（自動マイグレーション）。"""
    from sqlalchemy import inspect, text

    new_cols = [
        ("retry_count", "INTEGER NOT NULL DEFAULT 0"),
    ]
    try:
        existing = {c["name"] for c in inspect(engine).get_columns("overnight_market_contexts")}
    except Exception:
        return   # table doesn't exist yet; create_all will handle it
    with engine.begin() as conn:
        for col_name, col_type in new_cols:
            if col_name not in existing:
                try:
                    conn.execute(text(
                        f"ALTER TABLE overnight_market_contexts ADD COLUMN {col_name} {col_type}"
                    ))
                    logger.info(f"overnight_market_contexts: added column {col_name}")
                except Exception as exc:
                    logger.warning(f"overnight_market_contexts migration {col_name}: {exc}")


def _migrate_decision_label_to_codes(engine) -> None:
    """One-time data migration: forward_signals.decision_label display strings → stable codes."""
    from sqlalchemy import text
    from src.core.decision_codes import _LEGACY_DISPLAY_TO_CODE

    with engine.begin() as conn:
        for display, code in _LEGACY_DISPLAY_TO_CODE.items():
            try:
                result = conn.execute(
                    text("UPDATE forward_signals SET decision_label = :code WHERE decision_label = :display"),
                    {"code": code, "display": display},
                )
                if result.rowcount:
                    logger.info(f"Migrated decision_label: {repr(display)} → {repr(code)} ({result.rowcount} rows)")
            except Exception as exc:
                logger.warning(f"decision_label migration {display!r}: {exc}")


def _migrate_position_monitor(engine) -> None:
    """position_monitor に pending execution カラムを追加（後方互換）。
    既存 active 持倉は SIGNAL_CLOSE_LEGACY としてマークする。
    """
    from sqlalchemy import inspect, text

    new_cols = [
        ("signal_date",              "DATE"),
        ("expected_execution_date",  "DATE"),
        ("entry_source",             "VARCHAR(30)"),
        ("shadow_trading_type",      "VARCHAR(30)"),
        ("execution_recorded_at",    "DATETIME"),  # _safe_add_cols converts to TIMESTAMP on PG
    ]
    _safe_add_cols(engine, "position_monitor", new_cols)
    # 將所有 entry_source IS NULL 的 active/closed 記錄標記為 SIGNAL_CLOSE_LEGACY
    from sqlalchemy import inspect, text
    try:
        existing = {c["name"] for c in inspect(engine).get_columns("position_monitor")}
        if "entry_source" in existing:
            with engine.begin() as conn:
                result = conn.execute(text(
                    "UPDATE position_monitor "
                    "SET entry_source = 'SIGNAL_CLOSE_LEGACY' "
                    "WHERE entry_source IS NULL AND status IN "
                    "('active','closed_profit','closed_loss','closed_manual','closed_signal')"
                ))
                if result.rowcount:
                    logger.info(
                        f"position_monitor: marked {result.rowcount} pre-fix records "
                        "as SIGNAL_CLOSE_LEGACY"
                    )
    except Exception as exc:
        logger.warning(f"position_monitor SIGNAL_CLOSE_LEGACY migration: {exc}")


def init_db(engine: Optional[Engine] = None) -> Engine:
    if engine is None:
        engine = get_engine()
    Base.metadata.create_all(engine)
    _migrate_stocks(engine)
    _migrate_analysis_results(engine)
    _migrate_forward_signals(engine)
    _migrate_recommendations(engine)
    _migrate_decision_label_to_codes(engine)
    _migrate_overnight_market_contexts(engine)
    _migrate_forward_outcome_evaluations(engine)
    _migrate_position_monitor(engine)
    from config import DATABASE_URL

    logger.info(f"Database initialized: {DATABASE_URL[:40]}...")
    return engine


def get_session(engine=None) -> Session:
    if engine is None:
        engine = get_engine()
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    return SessionLocal()
