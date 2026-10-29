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
from datetime import date, datetime
from zoneinfo import ZoneInfo

_TAIPEI = ZoneInfo("Asia/Taipei")

def main():
    parser = argparse.ArgumentParser(description="手動執行每日分析")
    parser.add_argument("--date",    type=str, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force",   action="store_true")
    args = parser.parse_args()

    if args.date:
        trade_date = date.fromisoformat(args.date)
    else:
        # Use Asia/Taipei to avoid UTC/Taiwan date mismatch on night runs.
        trade_date = datetime.now(_TAIPEI).date()

    from src.core.trading_calendar import _calendar, MarketStatus
    if not args.force and not args.dry_run and not _calendar.is_trading_day(trade_date):
        status = _calendar.market_status(trade_date)
        if status == MarketStatus.CALENDAR_UNKNOWN:
            print(
                f"ERROR: {trade_date} → CALENDAR_UNKNOWN — "
                f"trading_calendar.py _COVERED_YEARS does not include {trade_date.year}. "
                "Update _TWSE_HOLIDAYS before this date or use --force to bypass.",
                file=sys.stderr,
            )
            sys.exit(2)
        print(f"{trade_date} 非台股交易日（{status.value}）。使用 --force 可強制執行。")
        sys.exit(0)

    from main import run_pipeline
    result = run_pipeline(trade_date=trade_date, dry_run=args.dry_run)
    if result is None:
        sys.exit(1)


if __name__ == "__main__":
    main()
