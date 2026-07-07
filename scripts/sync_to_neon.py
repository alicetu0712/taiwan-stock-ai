"""
scripts/sync_to_neon.py — 將本機分析結果同步至 Neon PostgreSQL

用途：
  本機跑完 python3 main.py 後，執行此腳本把結果推到雲端，
  手機版 dashboard 就能看到最新資料。

使用方式：
  python3 scripts/sync_to_neon.py --db-url "postgresql://..."

  或先在環境變數設好 NEON_URL：
  export NEON_URL="postgresql://..."
  python3 scripts/sync_to_neon.py

同步的資料表：
  - analysis_results   （每日分析評分）
  - recommendations    （推薦股票）
  - daily_reports      （AI 報告全文）
  - execution_logs     （執行紀錄）

不同步（資料量太大，手機版不需要）：
  - daily_prices
  - institutional_data
"""

import sys
import os
import argparse
import logging
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("sync_to_neon")


def get_local_engine():
    from config import DB_PATH
    from sqlalchemy import create_engine
    engine = create_engine(f"sqlite:///{DB_PATH}")
    return engine


def get_neon_engine(neon_url: str):
    from sqlalchemy import create_engine
    url = neon_url.replace("postgres://", "postgresql://", 1)
    engine = create_engine(url, pool_pre_ping=True, connect_args={"sslmode": "require"})
    return engine


def sync_table(local_session, neon_session, Model, key_fields: list, days: int = 90):
    """把本機 Model 的近 N 天資料同步到 Neon（upsert by key fields）。"""
    from sqlalchemy import inspect

    since = date.today() - timedelta(days=days)
    rows = local_session.query(Model).filter(Model.date >= since).all()
    if not rows:
        logger.info(f"  {Model.__tablename__}: 本機無近 {days} 天資料，略過")
        return 0

    mapper  = inspect(Model)
    all_cols = [col.key for col in mapper.columns]

    inserted = updated = 0
    for row in rows:
        key = {f: getattr(row, f) for f in key_fields}
        existing = neon_session.query(Model).filter_by(**key).first()
        if existing:
            for col in all_cols:
                if col not in key_fields and col != "id":
                    setattr(existing, col, getattr(row, col))
            updated += 1
        else:
            # 帶入本機 id，避免 Neon sequence 與已有記錄衝突
            kwargs = {col: getattr(row, col) for col in all_cols}
            neon_session.add(Model(**kwargs))
            inserted += 1

    neon_session.commit()
    logger.info(f"  {Model.__tablename__}: 新增 {inserted}，更新 {updated}")
    return inserted + updated


def main():
    parser = argparse.ArgumentParser(description="同步本機分析結果到 Neon")
    parser.add_argument("--db-url", type=str, default=None,
                        help="Neon 連線字串（預設讀 NEON_URL 環境變數）")
    parser.add_argument("--days", type=int, default=90,
                        help="同步幾天內的資料（預設 90 天）")
    parser.add_argument("--skip-prices", action="store_true",
                        help="跳過 daily_prices 同步（每日自動同步用，加快速度）")
    args = parser.parse_args()

    neon_url = args.db_url or os.environ.get("NEON_URL", "")
    if not neon_url:
        logger.error(
            "請提供 Neon 連線字串：\n"
            "  python3 scripts/sync_to_neon.py --db-url \"postgresql://...\"\n"
            "  或設定環境變數 NEON_URL"
        )
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("本機 SQLite → Neon PostgreSQL 同步")
    logger.info(f"同步範圍：近 {args.days} 天")
    logger.info("=" * 60)

    # 建立連線
    try:
        local_engine = get_local_engine()
        logger.info("✓ 本機 SQLite 連線成功")
    except Exception as e:
        logger.error(f"本機 DB 連線失敗：{e}")
        sys.exit(1)

    try:
        neon_engine = get_neon_engine(neon_url)
        with neon_engine.connect() as conn:
            conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        logger.info("✓ Neon 連線成功")
    except Exception as e:
        logger.error(f"Neon 連線失敗：{e}")
        logger.error("請確認連線字串正確，且 Neon 專案仍在運作")
        sys.exit(1)

    # 在 Neon 建立所有資料表（若尚未建立）
    from src.database import Base, init_db, get_session
    Base.metadata.create_all(neon_engine)
    logger.info("✓ Neon 資料表確認完成")

    from sqlalchemy.orm import sessionmaker
    LocalSession = sessionmaker(bind=local_engine)
    NeonSession  = sessionmaker(bind=neon_engine)
    local_s = LocalSession()
    neon_s  = NeonSession()

    from src.database import (
        AnalysisResult, Recommendation, DailyReport, ExecutionLog,
        DecisionJournal, ResearchStatus, Stock, PositionMonitor, DailyPrice, UserTrade,
    )

    total = 0
    logger.info("\n同步中...")

    try:
        # stocks 表（不限日期）
        stocks = local_s.query(Stock).all()
        s_ins = 0
        for row in stocks:
            if not neon_s.query(Stock).filter_by(stock_id=row.stock_id).first():
                neon_s.add(Stock(
                    stock_id=row.stock_id, name=row.name,
                    market=row.market, industry=row.industry,
                ))
                s_ins += 1
        neon_s.commit()
        logger.info(f"  stocks: 新增 {s_ins}")

        # 有日期的資料表
        total += sync_table(local_s, neon_s, AnalysisResult,
                            key_fields=["stock_id", "date"], days=args.days)
        total += sync_table(local_s, neon_s, Recommendation,
                            key_fields=["stock_id", "date"], days=args.days)
        total += sync_table(local_s, neon_s, DailyReport,
                            key_fields=["date"], days=args.days)
        total += sync_table(local_s, neon_s, ExecutionLog,
                            key_fields=["date"], days=args.days)

        # position_monitor（全量同步：持倉狀態隨時更新，不限日期）
        pm_rows = local_s.query(PositionMonitor).all()
        pm_ins = pm_upd = 0
        from sqlalchemy import inspect as _inspect
        pm_cols = [c.key for c in _inspect(PositionMonitor).columns]
        for row in pm_rows:
            existing = neon_s.query(PositionMonitor).filter_by(id=row.id).first()
            if existing:
                for col in pm_cols:
                    if col != "id":
                        setattr(existing, col, getattr(row, col))
                pm_upd += 1
            else:
                kwargs = {col: getattr(row, col) for col in pm_cols}
                neon_s.add(PositionMonitor(**kwargs))
                pm_ins += 1
        neon_s.commit()
        logger.info(f"  position_monitor: 新增 {pm_ins}，更新 {pm_upd}")
        total += pm_ins + pm_upd

        # DailyPrice（僅同步曾被推薦過的股票，供回測頁使用；--skip-prices 時略過）
        if args.skip_prices:
            logger.info("  daily_prices: 已跳過（--skip-prices）")
        rec_stock_ids = {} if args.skip_prices else {r.stock_id for r in local_s.query(Recommendation).all()}
        if rec_stock_ids:
            from sqlalchemy import inspect as _inspect2
            dp_cols = [c.key for c in _inspect2(DailyPrice).columns]
            dp_rows = (local_s.query(DailyPrice)
                       .filter(DailyPrice.stock_id.in_(rec_stock_ids))
                       .all())
            dp_ins = dp_upd = 0
            for row in dp_rows:
                existing = neon_s.query(DailyPrice).filter_by(
                    stock_id=row.stock_id, date=row.date).first()
                if existing:
                    for col in dp_cols:
                        if col != "id":
                            setattr(existing, col, getattr(row, col))
                    dp_upd += 1
                else:
                    kwargs = {col: getattr(row, col) for col in dp_cols}
                    neon_s.add(DailyPrice(**kwargs))
                    dp_ins += 1
            neon_s.commit()
            logger.info(f"  daily_prices (推薦股票): 新增 {dp_ins}，更新 {dp_upd}")
            total += dp_ins + dp_upd

        # UserTrade（全量同步，確保本機與雲端一致）
        from sqlalchemy import inspect as _insp_ut
        ut_cols = [c.key for c in _insp_ut(UserTrade).columns]
        ut_rows = local_s.query(UserTrade).all()
        ut_ins = ut_upd = 0
        for row in ut_rows:
            existing = neon_s.query(UserTrade).filter_by(id=row.id).first()
            if existing:
                for col in ut_cols:
                    if col != "id": setattr(existing, col, getattr(row, col))
                ut_upd += 1
            else:
                neon_s.add(UserTrade(**{col: getattr(row, col) for col in ut_cols}))
                ut_ins += 1
        neon_s.commit()
        logger.info(f"  user_trades: 新增 {ut_ins}，更新 {ut_upd}")
        total += ut_ins + ut_upd

        # ResearchStatus（無日期欄位，全量同步）
        rs_rows = local_s.query(ResearchStatus).all()
        rs_upd = 0
        for row in rs_rows:
            existing = neon_s.query(ResearchStatus).filter_by(stock_id=row.stock_id).first()
            if existing:
                existing.status = row.status
                existing.status_reason = row.status_reason
                existing.last_rec_date = row.last_rec_date
            else:
                neon_s.add(ResearchStatus(
                    stock_id=row.stock_id, status=row.status,
                    status_reason=row.status_reason, last_rec_date=row.last_rec_date,
                ))
            rs_upd += 1
        neon_s.commit()
        logger.info(f"  research_status: 同步 {rs_upd} 筆")

    except Exception as e:
        logger.error(f"同步失敗：{e}")
        neon_s.rollback()
        sys.exit(1)
    finally:
        local_s.close()
        neon_s.close()

    logger.info("=" * 60)
    logger.info(f"✅ 同步完成！共 {total} 筆資料推到 Neon")
    logger.info("重新整理手機版 dashboard 即可看到最新資料")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
