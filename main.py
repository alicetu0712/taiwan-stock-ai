"""
main.py — 主要入口

AI Taiwan Equity Research Platform v6.0

執行方式：
  # 正常執行（分析今日，產生報告）
  python main.py

  # 指定日期
  python main.py --date 2026-07-01

  # Dry-run（使用範例資料，不打 API）
  python main.py --dry-run

  # 僅重新產生報告
  python main.py --report-only

  # 啟動排程（每日自動執行）
  python main.py --schedule

  # 啟動 Dashboard
  streamlit run dashboard/app.py
"""

import argparse
import logging
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from config import LOGS_DIR, FINMIND_TOKEN, ANTHROPIC_API_KEY

# ── Logging 初始化 ────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            LOGS_DIR / f"run_{date.today().isoformat()}.log",
            mode="a",
            encoding="utf-8",
        ),
    ],
)
logger = logging.getLogger("main")


def run_pipeline(trade_date: date = None, dry_run: bool = False):
    """執行完整每日分析流程。"""
    trade_date = trade_date or date.today()
    start_time = datetime.now()

    logger.info(f"{'='*60}")
    logger.info(f"AI Taiwan Equity Research Platform v6.0")
    logger.info(f"分析日期：{trade_date} | Dry-run：{dry_run}")
    if not FINMIND_TOKEN:
        logger.warning("⚠️  未設定 FINMIND_TOKEN：基本面分析將跳過，僅執行技術面+籌碼分析。")
    if not ANTHROPIC_API_KEY:
        logger.warning("⚠️  未設定 ANTHROPIC_API_KEY：AI 說明將使用規則式備案。")
    logger.info(f"{'='*60}")

    # ── 導入模組 ─────────────────────────────────────────────
    from src.collectors.price_collector import fetch_all_prices, fetch_market_summary
    from src.collectors.chip_collector  import fetch_all_institutional, fetch_margin_trading
    from src.collectors.financial_collector import build_financial_summary
    from src.collectors.news_collector  import fetch_rss_news, fetch_mops_announcements
    from src.validators.data_validator  import DataValidator
    from src.analyzers.fundamental      import FundamentalAnalyzer
    from src.analyzers.technical        import TechnicalAnalyzer
    from src.analyzers.market_behavior  import MarketBehaviorAnalyzer, analyze_market_sentiment
    from src.analyzers.risk             import RiskAnalyzer
    from src.engines.hard_filter        import HardFilter
    from src.engines.decision           import DecisionEngine
    from src.ai.claude_analyst          import ClaudeAnalyst
    from src.reporters.report_generator import ReportGenerator
    from src.database                   import init_db, get_session

    import pandas as pd

    validator   = DataValidator()
    fund_eng    = FundamentalAnalyzer()
    tech_eng    = TechnicalAnalyzer()
    behav_eng   = MarketBehaviorAnalyzer()
    risk_eng    = RiskAnalyzer()
    hf          = HardFilter()
    decision    = DecisionEngine()
    analyst     = ClaudeAnalyst()
    reporter    = ReportGenerator()

    # ── 初始化資料庫 ──────────────────────────────────────────
    engine = init_db()
    session = get_session(engine)

    n_analyzed   = 0
    n_qualified  = 0
    recommendations = []
    fail_reasons    = []

    try:
        # ── Step 1: 抓取股價資料 ─────────────────────────────
        logger.info("[Step 1] Fetching price data...")
        is_backfill = (trade_date < date.today())

        if dry_run:
            price_df, market_summary = _sample_price_data(trade_date)
        elif is_backfill:
            # 回補歷史日期：從 DailyPrice 表讀取當日實際價格
            logger.info(f"[Step 1] 回補模式：從 DB 讀取 {trade_date} 的歷史股價")
            from src.database import DailyPrice
            rows = session.query(DailyPrice).filter(DailyPrice.date == trade_date).all()
            if not rows:
                logger.error(f"DB 中無 {trade_date} 的股價資料，無法回補")
                return None
            price_df = pd.DataFrame([{
                "stock_id": r.stock_id, "date": r.date,
                "close": r.close, "open": r.open,
                "high": r.high, "low": r.low, "volume": r.volume,
                "amount": r.amount, "change_pct": r.change_pct,
            } for r in rows])
            price_df["stock_id"] = price_df["stock_id"].astype(str)
            market_summary = {"index_close": None, "index_change_pct": None,
                              "total_volume": None, "up_count": None, "down_count": None}
            logger.info(f"[Step 1] 回補：讀取 {len(price_df)} 筆歷史股價")
        else:
            price_df     = fetch_all_prices(trade_date)
            market_summary_raw = fetch_market_summary()
            market_summary = {**market_summary_raw}

        price_valid, price_msg = validator.validate_price_data(price_df, trade_date)
        if not price_valid:
            logger.error(f"股價資料驗證失敗：{price_msg}")
            _save_execution_log(session, trade_date, start_time, "failed", 0, 0, 0, price_msg)
            return None

        # ── Step 1b: 把今日股價存入 DailyPrice 表（僅非回補模式）──
        if not dry_run and not is_backfill:
            try:
                from src.database import DailyPrice
                new_rows = 0
                for _, row in price_df.iterrows():
                    exists = session.query(DailyPrice).filter_by(
                        stock_id=row["stock_id"], date=trade_date
                    ).first()
                    if not exists:
                        session.add(DailyPrice(
                            stock_id   = row["stock_id"],
                            date       = trade_date,
                            open       = row.get("open"),
                            high       = row.get("high"),
                            low        = row.get("low"),
                            close      = row.get("close"),
                            volume     = row.get("volume"),
                            amount     = row.get("amount"),
                            change_pct = row.get("change_pct"),
                        ))
                        new_rows += 1
                session.commit()
                logger.info(f"[Step 1b] 今日股價已存入 DB：{new_rows} 筆新增")
            except Exception as e:
                logger.warning(f"今日股價存入 DB 失敗（{e}），繼續執行")
                session.rollback()

        # 只保留本機有歷史資料的股票（加速分析，避免技術指標無意義）
        if not dry_run:
            try:
                from src.database import DailyPrice
                hist_stocks = [r[0] for r in session.query(DailyPrice.stock_id).filter(DailyPrice.date <= trade_date).distinct().all()]
                if hist_stocks:
                    price_df = price_df[price_df["stock_id"].isin(hist_stocks)]
                    logger.info(f"[Step 1] 篩選至有歷史資料的股票：{len(hist_stocks)} 檔")
            except Exception as e:
                logger.warning(f"歷史股票篩選失敗（{e}），使用全部資料")

        n_analyzed = len(price_df["stock_id"].unique())
        logger.info(f"[Step 1] 完成：{n_analyzed} 檔股票")

        # 股票名稱對照表（從 stocks 表載入，供後續分析報告使用）
        from src.database import Stock as StockModel
        _stock_db_rows = session.query(StockModel).all()
        _stock_name_map: dict = {r.stock_id: r.name for r in _stock_db_rows if r.name}
        _stock_industry_map: dict = {r.stock_id: (r.industry or "") for r in _stock_db_rows}

        # Dry-run：注入模擬財務摘要，讓完整流程可以演示
        _dry_run_fin_summaries = _sample_financial_summaries() if dry_run else {}

        # 無財務資料時：從 analysis_results 載入各股票最近有效的 quality_score（基本面每季才變）
        _quality_cache: dict = {}
        if not FINMIND_TOKEN and not dry_run:
            try:
                from src.database import AnalysisResult
                from sqlalchemy import func
                subq = (
                    session.query(
                        AnalysisResult.stock_id,
                        func.max(AnalysisResult.date).label("latest_date")
                    )
                    .filter(AnalysisResult.quality_score > 0)
                    .filter(AnalysisResult.date < trade_date)
                    .group_by(AnalysisResult.stock_id)
                    .subquery()
                )
                rows = (
                    session.query(AnalysisResult)
                    .join(subq, (AnalysisResult.stock_id == subq.c.stock_id) &
                                (AnalysisResult.date == subq.c.latest_date))
                    .all()
                )
                _quality_cache = {r.stock_id: r.quality_score for r in rows}
                logger.info(f"[Step 1] 載入品質分快取：{len(_quality_cache)} 支股票")
            except Exception as e:
                logger.warning(f"品質分快取載入失敗（{e}），將使用預設 0 分")

        # ── Step 2: 抓取法人資料 ─────────────────────────────
        logger.info("[Step 2] Fetching institutional (chip) data...")
        if dry_run:
            inst_df = _sample_institutional(trade_date, price_df["stock_id"].unique())
        elif is_backfill:
            # 回補模式：從 DB 讀取該日法人資料
            from src.database import InstitutionalData
            inst_rows = session.query(InstitutionalData).filter(
                InstitutionalData.date == trade_date
            ).all()
            if inst_rows:
                inst_df = pd.DataFrame([{
                    "stock_id": r.stock_id,
                    "date": r.date,
                    "foreign_net": r.foreign_net or 0,
                    "trust_net": r.trust_net or 0,
                    "dealer_net": r.dealer_net or 0,
                    "total_net": (r.foreign_net or 0) + (r.trust_net or 0) + (r.dealer_net or 0),
                } for r in inst_rows])
                logger.info(f"[Step 2] 回補：讀取 {len(inst_df)} 筆歷史法人資料")
            else:
                logger.warning(f"[Step 2] DB 無 {trade_date} 法人資料，使用空資料")
                inst_df = pd.DataFrame()
        else:
            inst_df = fetch_all_institutional(trade_date)

        inst_valid, inst_msg = validator.validate_institutional_data(inst_df)
        if not inst_valid:
            logger.warning(f"法人資料不完整：{inst_msg}（繼續執行，籌碼分析將使用預設中性分數）")
            inst_df = pd.DataFrame()

        # ── Step 3: 抓取新聞 ────────────────────────────────
        logger.info("[Step 3] Fetching news...")
        if dry_run:
            news_list = []
        else:
            try:
                news_list = fetch_rss_news() + fetch_mops_announcements(trade_date)
            except Exception as e:
                logger.warning(f"新聞資料抓取失敗（{e}），繼續執行。")
                news_list = []

        # ── Step 4: 大盤情緒分析 ────────────────────────────
        market_sentiment = analyze_market_sentiment(price_df, trade_date)
        market_summary   = {**market_summary, **market_sentiment}
        market_ai_text   = analyst.generate_market_summary(market_summary, trade_date)

        # ── Step 5: 技術分析（全市場）───────────────────────
        logger.info("[Step 5] Running technical analysis on all stocks...")
        tech_results = {}

        # 從 DB 拉出完整歷史（最近 120 天），讓技術指標有足夠資料
        hist_map = {}
        if not dry_run:
            try:
                from src.database import DailyPrice
                from sqlalchemy import desc as sqldesc
                cutoff = trade_date - timedelta(days=180)
                rows = (session.query(DailyPrice)
                        .filter(DailyPrice.stock_id.in_(price_df["stock_id"].unique()))
                        .filter(DailyPrice.date >= cutoff)
                        .filter(DailyPrice.date <= trade_date)
                        .order_by(DailyPrice.stock_id, DailyPrice.date)
                        .all())
                for r in rows:
                    hist_map.setdefault(r.stock_id, []).append({
                        "date": r.date, "open": r.open, "high": r.high,
                        "low": r.low, "close": r.close,
                        "volume": r.volume, "amount": r.amount,
                        "change_pct": r.change_pct,
                    })
                logger.info(f"[Step 5] 從 DB 載入歷史資料：{len(hist_map)} 檔")
            except Exception as e:
                logger.warning(f"歷史資料載入失敗（{e}），改用當日資料")

        grouped = price_df.groupby("stock_id")
        for sid, today_row in grouped:
            if sid in hist_map:
                hist = pd.DataFrame(hist_map[sid])
            else:
                hist = today_row
            tech_results[sid] = tech_eng.analyze(sid, hist)

        # ── Step 6: Hard Filter ──────────────────────────────
        # 若無 FinMind，則跳過財務 Hard Filter，改用流動性篩選
        logger.info("[Step 6] Running Hard Filter...")
        qualified_stocks = []

        for sid in price_df["stock_id"].unique():
            sid_data = price_df[price_df["stock_id"] == sid]
            avg_amt  = float(sid_data["amount"].mean()) if "amount" in sid_data.columns else 0

            # 取得最新股價資訊
            latest = sid_data.sort_values("date").iloc[-1] if len(sid_data) > 0 else None
            close  = float(latest["close"]) if latest is not None and "close" in latest else 0

            # 財務資料（優先從本地 DB 讀取，無 DB 資料再嘗試 FinMind）
            fin_sum = _dry_run_fin_summaries.get(sid, {})
            if not dry_run:
                try:
                    fin_sum = build_financial_summary(sid, n_years=5, as_of_date=trade_date)
                except Exception:
                    fin_sum = {}

            # 執行 Hard Filter
            # 若無財務資料，只看流動性（降低門檻）
            if not fin_sum.get("has_data", False):
                # 僅流動性篩選：日均成交金額 >= 1億元
                if avg_amt >= 100:   # 100 百萬 = 1 億
                    qualified_stocks.append((sid, fin_sum, latest))
            else:
                r = hf.filter_stock(
                    stock_id        = sid,
                    name            = _stock_name_map.get(sid, ""),
                    industry        = _stock_industry_map.get(sid, ""),
                    avg_daily_amt_m = avg_amt,
                    eps_ttm         = fin_sum.get("eps_ttm"),
                    roe_avg         = fin_sum.get("roe_avg"),
                    roa_avg         = fin_sum.get("roa_avg"),
                    debt_ratio      = fin_sum.get("debt_ratio"),
                    eps_trend       = fin_sum.get("eps_trend", "unknown"),
                    revenue_trend   = fin_sum.get("revenue_trend", "unknown"),
                )
                if r.passed:
                    qualified_stocks.append((sid, fin_sum, latest))
                else:
                    fail_reasons.append(r.fail_reason)

        n_qualified = len(qualified_stocks)
        logger.info(f"[Step 6] Hard Filter 完成：{n_qualified}/{n_analyzed} 通過")

        # ── Step 7: 深度分析（通過篩選的股票）──────────────
        logger.info(f"[Step 7] Deep analysis on {n_qualified} qualified stocks...")
        candidates = []

        for idx, (sid, fin_sum, latest_row) in enumerate(qualified_stocks):
            if idx % 50 == 0:
                logger.info(f"  深度分析進度：{idx}/{n_qualified}")

            # 取得個股歷史資料
            hist = price_df[price_df["stock_id"] == sid].sort_values("date")

            # 基本面分析
            qual_r = fund_eng.analyze(sid, fin_sum)
            # 無財務資料時，借用最近一次有效的 quality_score（基本面每季才變）
            if qual_r.quality_score == 0.0 and sid in _quality_cache:
                qual_r.quality_score = _quality_cache[sid]
                qual_r.quality_grade = fund_eng._to_grade(qual_r.quality_score)
                qual_r.summary = f"（使用最近財務資料）{qual_r.summary}"

            # 技術面分析
            tech_r = tech_results.get(sid, tech_eng.analyze(sid, hist))

            # 市場行為分析
            chip_hist = inst_df[inst_df["stock_id"] == sid].copy() if not inst_df.empty else pd.DataFrame()
            behav_r   = behav_eng.analyze(sid, chip_hist)

            # 風險分析
            close     = float(latest_row["close"]) if latest_row is not None else None
            volume    = float(latest_row["volume"]) if latest_row is not None and "volume" in latest_row else None
            avg_vol   = float(hist["volume"].tail(20).mean()) if not hist.empty else None
            name      = _stock_name_map.get(sid) or (str(latest_row.get("name", "")) if latest_row is not None else "") or sid
            market    = str(latest_row.get("market", "")) if latest_row is not None else ""

            risk_r = risk_eng.analyze(
                stock_id         = sid,
                technical_result = tech_r,
                behavior_result  = behav_r,
                fin_summary      = fin_sum,
                market_sentiment = market_sentiment,
                close            = close,
                volume           = volume,
                avg_volume       = avg_vol,
            )

            # 決策引擎
            rec = decision.evaluate(
                stock_id         = sid,
                quality_result   = qual_r,
                technical_result = tech_r,
                behavior_result  = behav_r,
                risk_result      = risk_r,
                intelligence_score = 60.0,
                name             = name,
                close            = close,
                volume           = volume,
                market           = market,
                trade_date       = trade_date,
            )
            candidates.append(rec)

        # ── Step 8: 大盤方向判斷 + 選出 Top N ──────────────────
        logger.info("[Step 8] Selecting top recommendations...")

        # 大盤方向：用 0050 ETF 的 60 日均線判斷多空
        bear_mode = False
        try:
            from src.database import DailyPrice as DP60
            rows_0050 = (session.query(DP60)
                         .filter(DP60.stock_id == "0050", DP60.date <= trade_date)
                         .order_by(DP60.date.desc()).limit(60).all())
            if len(rows_0050) >= 30:
                closes_0050 = [float(r.close) for r in rows_0050 if r.close]
                ma60 = sum(closes_0050) / len(closes_0050)
                current_0050 = closes_0050[0]
                bear_mode = current_0050 < ma60
                mode_str = "空頭（限 A/A+）" if bear_mode else "多頭（正常）"
                logger.info(f"[Step 8] 大盤方向：0050={current_0050:.2f} MA60={ma60:.2f} → {mode_str}")
        except Exception as e:
            logger.warning(f"[Step 8] 大盤方向判斷失敗（{e}），預設多頭模式")

        top_recs, no_rec_reason = decision.select_top_n(candidates, bear_mode=bear_mode)

        # ── Step 9: Claude AI 報告生成 ───────────────────────
        logger.info("[Step 9] Generating AI explanations...")
        ai_reports = {}
        for rec in top_recs:
            ai_reports[rec.stock_id] = analyst.generate_research_report(rec)

        if not top_recs:
            no_rec_ai = analyst.generate_no_recommendation_report(
                market_summary  = market_summary,
                n_analyzed      = n_analyzed,
                n_qualified     = n_qualified,
                fail_reasons    = list(set(fail_reasons))[:5],
                trade_date      = trade_date,
            )
            no_rec_reason = no_rec_ai or no_rec_reason

        # ── 持久化推薦與分析結果至資料庫 ─────────────────────────
        _save_recommendations(session, trade_date, top_recs, candidates, ai_reports, market_sentiment)

        # ── Step 9b: 持倉管理 ────────────────────────────────
        logger.info("[Step 9b] Position management...")
        try:
            from src.engines import position_manager
            from src.engines.monte_carlo import simulate

            # 建立新持倉（本日推薦）
            price_map    = {r.stock_id: r.close for r in candidates if r.close}
            timing_map   = {r.stock_id: r.timing_score   for r in candidates}
            behavior_map = {r.stock_id: r.behavior_score for r in candidates}

            for rec in top_recs:
                if not rec.close or rec.close <= 0:
                    continue
                # AI 生成停損/目標價
                hist_returns = []
                try:
                    from src.database import DailyPrice
                    dp_rows = (
                        session.query(DailyPrice)
                        .filter(DailyPrice.stock_id == rec.stock_id)
                        .order_by(DailyPrice.date.desc())
                        .limit(60)
                        .all()
                    )
                    closes = [r.close for r in reversed(dp_rows) if r.close and r.close > 0]
                    if len(closes) >= 2:
                        hist_returns = [(closes[i] - closes[i-1]) / closes[i-1]
                                        for i in range(1, len(closes))]
                except Exception:
                    pass

                targets = analyst.generate_price_targets(rec, hist_returns)
                opened  = position_manager.open_position(
                    session        = session,
                    stock_id       = rec.stock_id,
                    stock_name     = rec.name,
                    entry_date     = trade_date,
                    entry_price    = rec.close,
                    rec_level      = rec.rec_level,
                    rec_score      = rec.total_score,
                    confidence     = rec.confidence,
                    target_price   = targets["target_price"],
                    stop_loss_price= targets["stop_loss_price"],
                    target_pct     = targets["target_pct"],
                    stop_loss_pct  = targets["stop_loss_pct"],
                    ai_rationale   = targets["rationale"],
                )
                if opened:
                    logger.info(
                        f"   建倉 {rec.name}（{rec.stock_id}）"
                        f" 目標 {targets['target_price']}（+{targets['target_pct']}%）"
                        f" 停損 {targets['stop_loss_price']}（{targets['stop_loss_pct']}%）"
                    )

            # 檢查現有持倉出場訊號
            signals = position_manager.check_exit_signals(
                session      = session,
                trade_date   = trade_date,
                price_map    = price_map,
                timing_map   = timing_map,
                behavior_map = behavior_map,
            )
            for sig in signals:
                logger.warning(
                    f"   ⚠️ 出場訊號 {sig.stock_id}：{sig.reason}｜{sig.detail}"
                )
                # 所有出場訊號均自動關倉
                position_manager.close_position(
                    session     = session,
                    stock_id    = sig.stock_id,
                    exit_date   = trade_date,
                    exit_price  = sig.current_price,
                    exit_reason = sig.reason,
                )

            session.commit()
            logger.info(f"[Step 9b] 持倉管理完成（新建倉 {sum(1 for r in top_recs if r.close)} 支，出場訊號 {len(signals)} 個）")
        except Exception as e:
            logger.warning(f"[Step 9b] 持倉管理失敗（不影響主流程）：{e}")

        # ── Step 10: 產生報告 ────────────────────────────────
        logger.info("[Step 10] Generating daily report...")
        result = reporter.generate_daily_report(
            trade_date      = trade_date,
            recommendations = top_recs,
            no_rec_reason   = no_rec_reason,
            market_summary  = market_summary,
            ai_reports      = ai_reports,
            market_ai_text  = market_ai_text,
            n_analyzed      = n_analyzed,
            n_qualified     = n_qualified,
        )

        # ── 完成 ─────────────────────────────────────────────
        end_time = datetime.now()
        elapsed  = (end_time - start_time).total_seconds()
        _save_execution_log(
            session, trade_date, start_time, "success",
            n_analyzed, n_qualified, len(top_recs)
        )

        logger.info(f"{'='*60}")
        logger.info(f"✅ 分析完成！耗時 {elapsed:.1f} 秒")
        logger.info(f"   推薦股票：{len(top_recs)} 檔")
        logger.info(f"   報告位置：{result['md_path']}")
        if top_recs:
            for i, r in enumerate(top_recs, 1):
                logger.info(f"   #{i} {r.name}（{r.stock_id}）"
                           f" 評分={r.total_score:.1f} 信心={r.confidence:.0f}%")
        else:
            logger.info("   今日無推薦標的。")
        logger.info(f"{'='*60}")

        session.close()
        return result

    except Exception as e:
        logger.error(f"分析流程發生嚴重錯誤：{e}", exc_info=True)
        _save_execution_log(session, trade_date, start_time, "failed", n_analyzed, n_qualified, 0, str(e))
        session.close()
        return None


# ── 樣本資料（Dry-run 用）────────────────────────────────────

def _sample_price_data(trade_date: date):
    """Dry-run 時產生範例股價資料。"""
    import numpy as np
    import pandas as pd

    np.random.seed(42)
    samples = [
        ("2330", "台積電", "TWSE"), ("2454", "聯發科", "TWSE"),
        ("2308", "台達電", "TWSE"), ("2317", "鴻海",   "TWSE"),
        ("2382", "廣達",   "TWSE"), ("3008", "大立光", "TWSE"),
        ("2412", "中華電", "TWSE"), ("2609", "陽明",   "TWSE"),
        ("6505", "台塑化", "TWSE"), ("2886", "兆豐金", "TWSE"),
    ]
    dates  = pd.bdate_range(end=trade_date, periods=120)
    records = []
    for sid, name, mkt in samples:
        price = np.random.uniform(50, 1000)
        for d in dates:
            chg = np.random.normal(0, 0.015) * price
            price = max(price + chg, 10)
            records.append({
                "stock_id": sid, "name": name, "market": mkt,
                "date": d.date(), "open": round(price * 0.99, 2),
                "high": round(price * 1.02, 2), "low": round(price * 0.98, 2),
                "close": round(price, 2), "volume": float(np.random.randint(5000, 100000)),
                "amount": float(np.random.randint(500, 50000)),
                "change_pct": round(chg / (price - chg) * 100, 2),
            })

    df = pd.DataFrame(records)
    mkt_summary = {"index_close": 22500.0, "index_change_pct": 0.35}
    return df, mkt_summary


def _sample_financial_summaries() -> dict:
    """Dry-run 模擬財務摘要（讓基本面分析可演示）。"""
    import random
    random.seed(42)
    stocks_data = {
        "2330": {"roe_avg": 27.5, "roa_avg": 14.2, "gross_margin_avg": 53.0,
                 "debt_ratio": 24.0, "eps_ttm": 38.5, "eps_trend": "up",
                 "roe_trend": "up", "revenue_trend": "up", "free_cash_flow": 500000.0,
                 "current_ratio": 2.5, "per": 22.0, "pbr": 5.5, "eps_5y": [22, 24, 28, 32, 38],
                 "roe_5y": [23, 24, 25, 26, 28], "has_data": True},
        "2454": {"roe_avg": 22.1, "roa_avg": 12.5, "gross_margin_avg": 48.0,
                 "debt_ratio": 28.0, "eps_ttm": 28.5, "eps_trend": "up",
                 "roe_trend": "up", "revenue_trend": "up", "free_cash_flow": 80000.0,
                 "current_ratio": 2.8, "per": 18.0, "pbr": 4.2, "eps_5y": [15, 18, 22, 25, 28],
                 "roe_5y": [18, 19, 20, 21, 22], "has_data": True},
        "2308": {"roe_avg": 18.5, "roa_avg": 10.2, "gross_margin_avg": 35.0,
                 "debt_ratio": 35.0, "eps_ttm": 12.5, "eps_trend": "stable",
                 "roe_trend": "stable", "revenue_trend": "up", "free_cash_flow": 30000.0,
                 "current_ratio": 1.8, "per": 16.0, "pbr": 2.8, "eps_5y": [10, 11, 12, 12, 13],
                 "roe_5y": [17, 18, 18, 19, 19], "has_data": True},
        "2317": {"roe_avg": 10.2, "roa_avg": 5.5, "gross_margin_avg": 6.5,
                 "debt_ratio": 55.0, "eps_ttm": 8.2, "eps_trend": "stable",
                 "roe_trend": "down", "revenue_trend": "stable", "free_cash_flow": 15000.0,
                 "current_ratio": 1.2, "per": 10.0, "pbr": 1.0, "eps_5y": [8, 9, 8, 8, 8],
                 "roe_5y": [12, 11, 10, 10, 10], "has_data": True},
        "2382": {"roe_avg": 20.5, "roa_avg": 11.0, "gross_margin_avg": 12.0,
                 "debt_ratio": 42.0, "eps_ttm": 15.2, "eps_trend": "up",
                 "roe_trend": "up", "revenue_trend": "up", "free_cash_flow": 25000.0,
                 "current_ratio": 2.0, "per": 14.0, "pbr": 2.9, "eps_5y": [10, 11, 12, 14, 15],
                 "roe_5y": [17, 18, 19, 20, 21], "has_data": True},
    }
    # 其他股票給普通財務資料
    default = {
        "roe_avg": 12.0, "roa_avg": 6.0, "gross_margin_avg": 25.0,
        "debt_ratio": 45.0, "eps_ttm": 5.0, "eps_trend": "stable",
        "roe_trend": "stable", "revenue_trend": "stable", "has_data": True,
    }
    return stocks_data


def _sample_institutional(trade_date: date, stock_ids):
    """Dry-run 時產生範例法人資料。"""
    import numpy as np
    import pandas as pd

    records = []
    dates = pd.bdate_range(end=trade_date, periods=20)
    for sid in stock_ids:
        for d in dates:
            records.append({
                "stock_id":   sid,
                "date":       d.date(),
                "foreign_net": int(np.random.normal(500, 1000)),
                "trust_net":   int(np.random.normal(100, 300)),
                "dealer_net":  int(np.random.normal(0, 200)),
                "total_net":   0,
            })
    df = pd.DataFrame(records)
    df["total_net"] = df["foreign_net"] + df["trust_net"] + df["dealer_net"]
    return df


def _save_recommendations(session, trade_date, top_recs, all_candidates, ai_reports, market_sentiment):
    """將推薦、分析結果、Decision Journal 持久化至資料庫。"""
    import json
    try:
        from src.database import Recommendation, AnalysisResult, DecisionJournal, ResearchStatus

        # ── 儲存所有股票的分析結果 ─────────────────────────────
        for rec in all_candidates:
            # 更新或新增 AnalysisResult
            existing = session.query(AnalysisResult).filter_by(
                stock_id=rec.stock_id, date=trade_date
            ).first()
            if not existing:
                ar = AnalysisResult(
                    stock_id           = rec.stock_id,
                    date               = trade_date,
                    quality_score      = rec.quality_score,
                    quality_grade      = rec.quality_grade,
                    timing_score       = rec.timing_score,
                    behavior_score     = rec.behavior_score,
                    intelligence_score = rec.intelligence_score,
                    risk_score         = rec.risk_score,
                    total_score        = rec.total_score,
                    confidence         = rec.confidence,
                    rec_level          = rec.rec_level,
                )
                session.add(ar)
            else:
                existing.quality_score      = rec.quality_score
                existing.quality_grade      = rec.quality_grade
                existing.timing_score       = rec.timing_score
                existing.behavior_score     = rec.behavior_score
                existing.intelligence_score = rec.intelligence_score
                existing.risk_score         = rec.risk_score
                existing.total_score        = rec.total_score
                existing.confidence         = rec.confidence
                existing.rec_level          = rec.rec_level

        # ── 儲存推薦紀錄（今日 Top N）────────────────────────
        top_ids = {r.stock_id for r in top_recs}
        for rec in top_recs:
            ai = ai_reports.get(rec.stock_id, {})
            # 避免同一天重複新增
            existing = session.query(Recommendation).filter_by(
                stock_id=rec.stock_id, date=trade_date
            ).first()
            if not existing:
                r = Recommendation(
                    date             = trade_date,
                    stock_id         = rec.stock_id,
                    rec_level        = rec.rec_level,
                    confidence       = rec.confidence,
                    summary          = ai.get("ai_summary", rec.summary),
                    advantages       = json.dumps(rec.advantages, ensure_ascii=False),
                    risks            = json.dumps(rec.risks, ensure_ascii=False),
                    watch_points     = json.dumps(rec.watch_points, ensure_ascii=False),
                    ai_conclusion    = ai.get("conclusion_ai", ""),
                    strategy_version = "v6.0",
                )
                session.add(r)
            else:
                existing.rec_level        = rec.rec_level
                existing.confidence       = rec.confidence
                existing.summary          = ai.get("ai_summary", rec.summary)
                existing.advantages       = json.dumps(rec.advantages, ensure_ascii=False)
                existing.risks            = json.dumps(rec.risks, ensure_ascii=False)
                existing.watch_points     = json.dumps(rec.watch_points, ensure_ascii=False)
                existing.ai_conclusion    = ai.get("conclusion_ai", "")
                existing.strategy_version = "v6.0"

        # ── 更新 Decision Journal ─────────────────────────────
        market_env_desc = f"市場情緒：{market_sentiment.get('sentiment', 'Neutral')}"
        for rec in all_candidates:
            action = "Recommended" if rec.stock_id in top_ids else (
                "WatchList" if rec.total_score >= 55 else "Rejected"
            )
            dj = DecisionJournal(
                date             = trade_date,
                stock_id         = rec.stock_id,
                quality_score    = rec.quality_score,
                timing_score     = rec.timing_score,
                behavior_score   = rec.behavior_score,
                confidence       = rec.confidence,
                rec_level        = rec.rec_level,
                action           = action,
                reason           = rec.summary,
                market_env       = market_env_desc,
                strategy_version = "v6.0",
            )
            session.add(dj)

        # ── 更新 ResearchStatus（研究生命週期）────────────────
        for rec in all_candidates:
            status = "Candidate" if rec.stock_id in top_ids else (
                "WatchList" if rec.total_score >= 55 else "Universe"
            )
            rs = session.query(ResearchStatus).filter_by(stock_id=rec.stock_id).first()
            if rs:
                rs.status       = status
                rs.status_reason = rec.summary
                rs.last_rec_date = trade_date if rec.stock_id in top_ids else rs.last_rec_date
            else:
                rs = ResearchStatus(
                    stock_id      = rec.stock_id,
                    status        = status,
                    status_reason = rec.summary,
                    last_rec_date = trade_date if rec.stock_id in top_ids else None,
                )
                session.add(rs)

        session.commit()
        logger.info(f"✅ 已儲存至資料庫：{len(all_candidates)} 筆分析結果，{len(top_recs)} 筆推薦")

    except Exception as e:
        logger.warning(f"資料庫儲存失敗（不影響報告生成）：{e}")
        session.rollback()


def _save_execution_log(
    session,
    trade_date,
    start_time,
    status,
    n_analyzed,
    n_qualified,
    n_recs,
    errors: str = None,
):
    """儲存執行記錄。"""
    try:
        from src.database import ExecutionLog
        log = ExecutionLog(
            date               = trade_date,
            start_time         = start_time,
            end_time           = datetime.now(),
            status             = status,
            total_stocks       = n_analyzed,
            qualified_stocks   = n_qualified,
            recommended_stocks = n_recs,
            errors             = errors,
        )
        session.add(log)
        session.commit()
    except Exception as e:
        logger.debug(f"ExecutionLog save failed: {e}")


# ── CLI ───────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="AI Taiwan Equity Research Platform v6.0"
    )
    parser.add_argument("--date", type=str, default=None,
                        help="指定交易日 YYYY-MM-DD（預設：今天）")
    parser.add_argument("--dry-run", action="store_true",
                        help="使用範例資料，不打外部 API")
    parser.add_argument("--schedule", action="store_true",
                        help="啟動每日自動排程")
    parser.add_argument("--force", action="store_true",
                        help="即使非交易日也強制執行")
    parser.add_argument("--init-db", action="store_true",
                        help="初始化資料庫")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    if args.init_db:
        from src.database import init_db
        init_db()
        logger.info("資料庫初始化完成。")
        sys.exit(0)

    if args.schedule:
        from src.scheduler import start_scheduler
        start_scheduler()
        sys.exit(0)

    trade_date = date.today()
    if args.date:
        try:
            trade_date = date.fromisoformat(args.date)
        except ValueError:
            logger.error(f"日期格式錯誤：{args.date}，請使用 YYYY-MM-DD 格式。")
            sys.exit(1)

    def is_trading_day(d):
        if d.weekday() >= 5:
            return False
        return True

    if not args.dry_run and not args.force and not is_trading_day(trade_date):
        logger.info(f"{trade_date} 非台股交易日。使用 --force 可強制執行。")
        sys.exit(0)

    run_pipeline(trade_date=trade_date, dry_run=args.dry_run)

    # 分析完成後自動同步至 Neon（讓手機版 Dashboard 即時更新）
    if not args.dry_run:
        neon_url = os.environ.get("NEON_URL", "")
        if not neon_url:
            # 從 .env 讀取
            env_file = Path(__file__).parent / ".env"
            if env_file.exists():
                for line in env_file.read_text().splitlines():
                    if line.startswith("NEON_URL="):
                        neon_url = line.split("=", 1)[1].strip()
                        break
        if neon_url:
            sync_script = Path(__file__).parent / "scripts" / "sync_to_neon.py"
            try:
                import subprocess
                logger.info("[Step 11] 同步至 Neon...")
                r = subprocess.run(
                    [sys.executable, str(sync_script), "--db-url", neon_url, "--days", "1"],
                    capture_output=True, text=True, timeout=600,
                    cwd=str(Path(__file__).parent),
                )
                if r.returncode == 0:
                    logger.info("[Step 11] Neon 同步完成")
                else:
                    logger.warning(f"[Step 11] Neon 同步失敗：{(r.stderr or r.stdout)[-200:]}")
            except Exception as e:
                logger.warning(f"[Step 11] Neon 同步例外：{e}")
