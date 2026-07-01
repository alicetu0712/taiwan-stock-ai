"""
scripts/run_daily.py — 手動觸發每日分析

執行：
  python scripts/run_daily.py                  # 今天
  python scripts/run_daily.py --date 2026-07-01  # 指定日期
  python scripts/run_daily.py --dry-run          # 測試模式
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
from datetime import date

def main():
    parser = argparse.ArgumentParser(description="手動執行每日分析")
    parser.add_argument("--date",    type=str, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force",   action="store_true")
    args = parser.parse_args()

    trade_date = date.today()
    if args.date:
        trade_date = date.fromisoformat(args.date)

    from src.scheduler import is_trading_day
    if not args.force and not args.dry_run and not is_trading_day(trade_date):
        print(f"{trade_date} 非台股交易日。使用 --force 可強制執行。")
        sys.exit(0)

    from main import run_pipeline
    run_pipeline(trade_date=trade_date, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
