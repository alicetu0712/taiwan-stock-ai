"""
scripts/run_live_collector.py — 盤中 Live Execution 背景收集器

每 N 分鐘取得「今日 Active BUY Signals」的即時報價，評估進場狀態，
將狀態轉換寫入 DB（live_execution_events）。

Active BUY Signal 定義：
  - signal_date 在最近 SIGNAL_ACTIVE_DAYS 個交易日內
  - execution_date（= next_trading_day(signal_date)）≤ today
  - 例：10/13 收盤 BUY → 10/14 起 Active，非「10/14 有哪些推薦」

執行方式：
  單次：    python3 scripts/run_live_collector.py
  迴圈：    python3 scripts/run_live_collector.py --loop
  強制跑：  python3 scripts/run_live_collector.py --force   （忽略時間窗口，測試用）

crontab 範例（每 2 分鐘，只在交易時段）：
  */2 9-13 * * 1-5 cd /path/to/stock_platform && python3 scripts/run_live_collector.py >> logs/live_collector.log 2>&1

macOS launchd 範例：參考 docs/launchd_live_collector.plist
"""

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

DEFAULT_INTERVAL = 120   # 2 分鐘


def main() -> None:
    parser = argparse.ArgumentParser(description="盤中 Live Execution 背景收集器")
    parser.add_argument(
        "--loop", action="store_true",
        help="持續執行（每 --interval 秒一次）直到手動中止",
    )
    parser.add_argument(
        "--interval", type=int, default=DEFAULT_INTERVAL,
        help=f"loop 模式的間隔秒數（預設 {DEFAULT_INTERVAL}）",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="忽略交易時間窗口限制（測試 / 補跑用）",
    )
    args = parser.parse_args()

    from src.database import init_db
    from src.services.live_background_service import run_once

    init_db()   # create live_execution_events if not exists (idempotent)

    if args.loop:
        logger.info(f"Live collector loop 啟動 (interval={args.interval}s)")
        while True:
            try:
                result = run_once(force=args.force)
                if result.get("skipped"):
                    logger.debug(f"skipped: {result['reason']}")
                else:
                    logger.info(
                        f"candidates={result['candidates']} "
                        f"events_written={result['events_written']} "
                        f"errors={result['errors']}"
                    )
            except Exception as exc:
                logger.error(f"Collection pass failed: {exc}", exc_info=True)
            time.sleep(args.interval)
    else:
        result = run_once(force=args.force)
        if result.get("skipped"):
            logger.info(f"skipped: {result['reason']}")
        else:
            logger.info(
                f"candidates={result['candidates']} "
                f"events_written={result['events_written']} "
                f"errors={result['errors']}"
            )


if __name__ == "__main__":
    main()
