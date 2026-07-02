"""
scripts/backfill_history.py — 批次回補歷史分析結果

使用方式（在 stock_platform/ 目錄下）：
  python3 scripts/backfill_history.py           # 全部補齊
  python3 scripts/backfill_history.py --limit 30 # 只補最近 30 天
"""
import sys
import subprocess
import logging
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import init_db, get_session, DailyPrice, AnalysisResult

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("backfill")


def main():
    parser = argparse.ArgumentParser(description="歷史分析回補")
    parser.add_argument("--limit", type=int, default=0, help="最多回補幾天（0=全部，從最舊開始）")
    args = parser.parse_args()

    engine = init_db()
    s = get_session(engine)
    from sqlalchemy import func as sqlfunc
    # 只取有足夠股票資料的日期（>= 200 支）
    valid_dates = {
        r[0] for r in
        s.query(DailyPrice.date, sqlfunc.count(DailyPrice.stock_id).label("n"))
         .group_by(DailyPrice.date)
         .having(sqlfunc.count(DailyPrice.stock_id) >= 200)
         .all()
    }
    price_dates = sorted(valid_dates)
    done_dates  = set(r[0] for r in s.query(AnalysisResult.date).distinct().all())
    s.close()

    need = [d for d in price_dates if d not in done_dates]
    if args.limit > 0:
        need = need[-args.limit:]   # 取最近 N 天
    total = len(need)

    logger.info("=" * 60)
    logger.info(f"歷史分析回補 — 待補 {total} 天（已完成 {len(done_dates)} 天）")
    logger.info("=" * 60)

    main_py = str(Path(__file__).parent.parent / "main.py")
    ok, fail = 0, []

    for i, d in enumerate(need, 1):
        date_str = str(d)
        pct = i / total * 100
        logger.info(f"[{pct:5.1f}%] [{i}/{total}] {date_str}")
        try:
            r = subprocess.run(
                [sys.executable, main_py, "--date", date_str],
                capture_output=True, text=True, timeout=180,
                cwd=str(Path(__file__).parent.parent),
            )
            if r.returncode == 0:
                ok += 1
                # 從 stdout 找推薦數
                for line in r.stdout.splitlines():
                    if "推薦股票" in line or "分析完成" in line:
                        logger.info(f"         → {line.strip()}")
                        break
            else:
                fail.append(date_str)
                err = (r.stderr or r.stdout or "")[-200:]
                logger.warning(f"         → 失敗：{err}")
        except subprocess.TimeoutExpired:
            fail.append(date_str)
            logger.warning(f"         → 逾時（>180s）")
        except Exception as e:
            fail.append(date_str)
            logger.warning(f"         → 例外：{e}")

    logger.info("=" * 60)
    logger.info(f"回補完成！成功 {ok} 天，失敗 {len(fail)} 天")
    if fail:
        logger.warning(f"失敗日期（前20筆）：{fail[:20]}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
