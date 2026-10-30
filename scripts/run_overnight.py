"""
scripts/run_overnight.py — 盤前隔夜市場資料收集

執行時機：台灣 09:00 (UTC 01:00)，每個交易日盤前。
  - 此時美股已收盤 5 小時，隔夜資料完整可取。
  - 在台股開盤前執行，確保無 look-ahead bias。

流程：
  1. 確認 execution_date（今日台灣時區日期）為台股交易日
  2. 呼叫 ensure_overnight_context(execution_date) 取得/建立隔夜市場快照
  3. 呼叫 link_overnight_to_forward_signals() 將快照 ID 寫回 forward_signals
  4. 輸出摘要供 GitHub Actions verification 使用

執行：
  python scripts/run_overnight.py                     # 今日（TW timezone）
  python scripts/run_overnight.py --date 2026-10-31   # 指定 execution_date
  python scripts/run_overnight.py --force             # 非交易日也執行（測試用）
"""

import logging
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent.parent))

TW = ZoneInfo("Asia/Taipei")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="盤前 Overnight Context 收集")
    parser.add_argument("--date",  type=str, default=None, help="execution_date YYYY-MM-DD")
    parser.add_argument("--force", action="store_true",    help="非交易日也執行（測試用）")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger = logging.getLogger("run_overnight")

    # ── Determine execution_date ─────────────────────────────────
    if args.date:
        try:
            execution_date = date.fromisoformat(args.date)
        except ValueError:
            print(f"ERROR: invalid --date '{args.date}', expected YYYY-MM-DD", file=sys.stderr)
            sys.exit(2)
    else:
        execution_date = datetime.now(TW).date()

    logger.info(f"[overnight] execution_date={execution_date}  force={args.force}")

    # ── Trading day guard ─────────────────────────────────────────
    if not args.force:
        from src.core.trading_calendar import _calendar, MarketStatus

        if not _calendar.is_trading_day(execution_date):
            status = _calendar.market_status(execution_date)
            if status == MarketStatus.CALENDAR_UNKNOWN:
                print(
                    f"ERROR: {execution_date} → CALENDAR_UNKNOWN — "
                    "trading_calendar.py _COVERED_YEARS does not include this year. "
                    "Update _TWSE_HOLIDAYS or use --force to bypass.",
                    file=sys.stderr,
                )
                sys.exit(2)
            print(f"{execution_date} 非台股交易日（{status.value}）。使用 --force 可強制執行。")
            sys.exit(0)

    # ── Collect overnight context ─────────────────────────────────
    from src.services.overnight_service import (
        ensure_overnight_context,
        link_overnight_to_forward_signals,
    )

    ctx = ensure_overnight_context(execution_date)
    if ctx is None:
        logger.error(f"[overnight] ensure_overnight_context returned None for {execution_date}")
        sys.exit(1)

    logger.info(
        f"[overnight] context id={ctx.id}  risk={ctx.risk_level}  "
        f"dq={ctx.data_quality}  us_market_date={ctx.us_market_date}  "
        f"retry={ctx.retry_count}"
    )

    # ── Link to forward_signals ───────────────────────────────────
    linked = link_overnight_to_forward_signals(execution_date, ctx)
    logger.info(f"[overnight] {linked} forward_signal(s) linked to ctx id={ctx.id}")

    # Summary line for GitHub Actions post-run verification
    print(
        f"overnight pipeline OK  "
        f"execution_date={execution_date}  "
        f"risk={ctx.risk_level}  "
        f"dq={ctx.data_quality}  "
        f"us_market_date={ctx.us_market_date}  "
        f"linked_signals={linked}"
    )


if __name__ == "__main__":
    main()
