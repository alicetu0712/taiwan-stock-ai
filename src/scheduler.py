"""
scheduler.py — 每日自動排程（PRD Chapter 2.2）

每個交易日收盤後自動執行分析流程：
  15:35 確認收盤資料完整
  15:40 更新股價資料
  15:45 更新法人資料
  15:50 更新新聞
  15:55 AI 分析
  16:00 產生每日研究報告
  16:05 更新 Dashboard
"""

import logging
import sys
from datetime import date

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from config import LOGS_DIR, SCHEDULE

logger = logging.getLogger(__name__)


def is_trading_day(d: date = None) -> bool:
    """判斷是否為台股交易日（週一~週五，不含國定假日）。"""
    d = d or date.today()
    if d.weekday() >= 5:
        return False
    try:
        import pandas_market_calendars as mcal

        cal = mcal.get_calendar("XTAI")
        sched = cal.schedule(
            start_date=d.strftime("%Y-%m-%d"),
            end_date=d.strftime("%Y-%m-%d"),
        )
        return not sched.empty
    except Exception:
        logger.debug("pandas_market_calendars unavailable; weekday-only check.")
        return True


def run_daily_pipeline(trade_date: date = None, force: bool = False):
    """執行每日完整分析流程。"""
    trade_date = trade_date or date.today()

    if not force and not is_trading_day(trade_date):
        logger.info(f"{trade_date} 非台股交易日，跳過分析。")
        return

    logger.info(f"{'='*60}")
    logger.info("AI Taiwan Equity Research Platform — 每日分析啟動")
    logger.info(f"分析日期：{trade_date}")
    logger.info(f"{'='*60}")

    from main import run_pipeline

    try:
        run_pipeline(trade_date=trade_date)
    except Exception as e:
        logger.error(f"每日分析流程發生錯誤：{e}", exc_info=True)


def _parse_time(time_str: str):
    """解析 'HH:MM' 字串。"""
    h, m = map(int, time_str.split(":"))
    return h, m


def start_scheduler():
    """啟動 APScheduler 排程。"""
    scheduler = BlockingScheduler(timezone="Asia/Taipei")

    h, m = _parse_time(SCHEDULE["run_analysis"])
    scheduler.add_job(
        func=run_daily_pipeline,
        trigger=CronTrigger(hour=h, minute=m, timezone="Asia/Taipei"),
        id="daily_analysis",
        name="Daily Stock Analysis",
        replace_existing=True,
    )

    logger.info(f"排程已啟動：每個交易日 {SCHEDULE['run_analysis']} 自動執行分析。")
    logger.info("按 Ctrl+C 停止排程。")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("排程已停止。")
        scheduler.shutdown()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(
                LOGS_DIR / f"scheduler_{date.today().isoformat()}.log", encoding="utf-8"
            ),
        ],
    )
    start_scheduler()
