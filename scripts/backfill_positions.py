"""
scripts/backfill_positions.py — 從歷史推薦記錄回填 position_monitor

邏輯：
  1. 讀取 recommendations 表全部推薦
  2. 對每筆推薦取進場日收盤價 → 建立 position_monitor 記錄
  3. 逐日掃描 daily_prices high/low 判斷是否觸及目標價或停損價
  4. 計算最終損益（active 用最新收盤；已出場用出場價）
  5. 統計整體勝率與報酬率

執行：
  python3 scripts/backfill_positions.py
"""
import sys
import logging
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import init_db, get_session, Recommendation, PositionMonitor, DailyPrice, Stock  # noqa: F401
from sqlalchemy import func

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                    handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger("backfill_positions")

# 各等級目標 / 停損 / 倉位
LEVEL_PARAMS = {
    "A+": {"target_pct": 20.0, "stop_loss_pct": 8.0, "position_pct": 30.0},
    "A":  {"target_pct": 15.0, "stop_loss_pct": 8.0, "position_pct": 20.0},
    "B":  {"target_pct": 10.0, "stop_loss_pct": 7.0, "position_pct": 10.0},
    "C":  {"target_pct":  7.0, "stop_loss_pct": 7.0, "position_pct":  5.0},
    "D":  {"target_pct":  5.0, "stop_loss_pct": 5.0, "position_pct":  5.0},
}


def main():
    engine = init_db()
    s = get_session(engine)

    # 已有持倉的 key（stock_id + date_entered）避免重複
    existing_keys = {
        (p.stock_id, str(p.date_entered))
        for p in s.query(PositionMonitor.stock_id, PositionMonitor.date_entered).all()
    }

    # 股票名稱對照
    name_map = {r.stock_id: r.name for r in s.query(Stock).all() if r.name}

    # 全部推薦紀錄（按日期排序）
    recs = s.query(Recommendation).order_by(Recommendation.date.asc()).all()
    logger.info(f"推薦記錄：{len(recs)} 筆，已有持倉 key：{len(existing_keys)} 筆")

    # 預載所有需要的 daily_prices（避免逐筆查詢）
    logger.info("預載 daily_prices...")
    all_prices = s.query(DailyPrice).order_by(DailyPrice.stock_id, DailyPrice.date).all()
    # 按 stock_id 分組，每天的資料
    from collections import defaultdict
    price_map = defaultdict(dict)  # price_map[stock_id][date_str] = row
    for p in all_prices:
        price_map[p.stock_id][str(p.date)] = p
    logger.info(f"價格資料載入完成（{len(all_prices):,} 筆）")

    added = 0
    skipped = 0
    skipped_budget = 0

    # 資金追蹤：模擬 100% 總資金，active 持倉依序佔用
    # budget_map[stock_id] = position_pct（持有中）
    budget_used: dict = {}   # {stock_id: position_pct}

    def _current_used():
        return sum(budget_used.values())

    for rec in recs:
        date_str = str(rec.date)
        key = (rec.stock_id, date_str)

        if key in existing_keys:
            skipped += 1
            continue

        # 取進場日收盤價
        entry_row = price_map[rec.stock_id].get(date_str)
        if not entry_row or not entry_row.close:
            continue

        entry_price = float(entry_row.close)
        params = LEVEL_PARAMS.get(rec.rec_level or "B", LEVEL_PARAMS["B"])

        target_pct    = params["target_pct"]
        stop_loss_pct = params["stop_loss_pct"]
        base_pct      = params["position_pct"]
        # 動態倉位：依信心度調整（與 position_manager.py 一致）
        confidence_val = float(rec.confidence or 80.0)
        conf_adj  = round((confidence_val - 80.0) / 10.0 * 5.0)
        position_pct = max(base_pct - 10, min(base_pct + 10, base_pct + conf_adj))
        position_pct = min(position_pct, 35.0)
        position_pct = round(position_pct, 0)
        target_price    = round(entry_price * (1 + target_pct / 100), 2)
        stop_loss_price = round(entry_price * (1 - stop_loss_pct / 100), 2)

        # ── 資金控管：超過 100% 不開倉 ──────────────────────────
        if rec.stock_id in budget_used:
            skipped_budget += 1
            continue   # 同股票已有持倉
        if _current_used() + position_pct > 100.0:
            skipped_budget += 1
            logger.debug(f"[Budget] {rec.stock_id} 跳過：已用 {_current_used():.0f}%＋{position_pct:.0f}% > 100%")
            continue

        # 取進場日之後的所有日期（排序）
        future_dates = sorted(
            d for d in price_map[rec.stock_id].keys() if d > date_str
        )

        status      = "active"
        exit_date   = None
        exit_price  = None
        exit_reason = None
        pnl_pct     = None

        # 動態停損（追蹤停損）起始值
        dynamic_stop = stop_loss_price
        entry_dt     = date.fromisoformat(date_str)

        for fd in future_dates:
            fd_row = price_map[rec.stock_id][fd]
            high  = float(fd_row.high)  if fd_row.high  else None
            low   = float(fd_row.low)   if fd_row.low   else None
            close = float(fd_row.close) if fd_row.close else None
            fd_dt = date.fromisoformat(fd)

            # ── 追蹤停損更新 ─────────────────────────────────
            if high:
                pnl_high = (high - entry_price) / entry_price * 100
                if pnl_high >= 12.0:
                    locked = round(entry_price * 1.06, 2)
                    if locked > dynamic_stop:
                        dynamic_stop = locked
                elif pnl_high >= 8.0:
                    if entry_price > dynamic_stop:
                        dynamic_stop = entry_price

            # ── 目標價達成 ───────────────────────────────────
            if high and high >= target_price:
                status      = "closed_profit"
                exit_date   = fd_dt
                exit_price  = target_price
                exit_reason = "TARGET_HIT"
                pnl_pct     = round((exit_price - entry_price) / entry_price * 100, 2)
                break

            # ── 停損觸發（含追蹤停損）───────────────────────
            if low and low <= dynamic_stop:
                pnl_at_stop = (dynamic_stop - entry_price) / entry_price * 100
                status      = "closed_profit" if pnl_at_stop > 0 else "closed_loss"
                exit_date   = fd_dt
                exit_price  = round(dynamic_stop, 2)
                exit_reason = "TRAILING_STOP" if dynamic_stop > stop_loss_price else "STOP_LOSS"
                pnl_pct     = round(pnl_at_stop, 2)
                break

            # ── 時間強制出場（與 position_manager.py v6.4 一致）─
            held_days = (fd_dt - entry_dt).days
            if close:
                pnl_now = (close - entry_price) / entry_price * 100
                # 45 天且虧損（pnl < 0）→ 強制出場
                if held_days >= 45 and pnl_now < 0 and abs(pnl_now) < 8.0:
                    status      = "closed_signal"
                    exit_date   = fd_dt
                    exit_price  = close
                    exit_reason = "TIME_LIMIT"
                    pnl_pct     = round(pnl_now, 2)
                    break
                # 90 天（不管盈虧）且無明顯方向 → 強制出場
                if held_days >= 90 and abs(pnl_now) < 8.0:
                    status      = "closed_signal"
                    exit_date   = fd_dt
                    exit_price  = close
                    exit_reason = "TIME_LIMIT"
                    pnl_pct     = round(pnl_now, 2)
                    break

        # active 持倉用最新收盤計算浮動損益
        if status == "active":
            last_date = future_dates[-1] if future_dates else date_str
            last_row  = price_map[rec.stock_id].get(last_date)
            if last_row and last_row.close:
                pnl_pct = round((float(last_row.close) - entry_price) / entry_price * 100, 2)

        pos = PositionMonitor(
            stock_id         = rec.stock_id,
            stock_name       = name_map.get(rec.stock_id, rec.stock_id),
            date_entered     = rec.date,
            entry_price      = entry_price,
            target_price     = target_price,
            stop_loss_price  = stop_loss_price,
            target_pct       = target_pct,
            stop_loss_pct    = stop_loss_pct,
            position_pct     = position_pct,
            rec_level        = rec.rec_level,
            rec_score        = None,
            confidence       = rec.confidence,
            status           = status,
            exit_date        = exit_date,
            exit_price       = exit_price,
            exit_reason      = exit_reason,
            pnl_pct          = pnl_pct,
        )
        s.add(pos)
        existing_keys.add(key)
        added += 1

        # 更新資金追蹤
        if status == "active":
            budget_used[rec.stock_id] = position_pct
        # 若已出場則不佔用資金（歷史上已釋放）
        # 但因為回填是順序處理，active 代表截至今日尚未出場

    s.commit()
    logger.info(f"新增持倉：{added} 筆，跳過（已存在）：{skipped} 筆，資金不足跳過：{skipped_budget} 筆")

    # ── 統計整體報酬 ─────────────────────────────────────────
    all_pos = s.query(PositionMonitor).all()
    closed  = [p for p in all_pos if p.status in ("closed_profit","closed_loss","closed_signal") and p.pnl_pct is not None]
    active  = [p for p in all_pos if p.status == "active" and p.pnl_pct is not None]

    if closed:
        import math, sqlite3
        avg_pnl     = sum(p.pnl_pct for p in closed) / len(closed)
        wins        = [p for p in closed if p.pnl_pct > 0]
        losses      = [p for p in closed if p.pnl_pct <= 0]
        win_rate    = len(wins) / len(closed) * 100
        avg_win     = sum(p.pnl_pct for p in wins)  / len(wins)  if wins   else 0
        avg_loss    = sum(p.pnl_pct for p in losses) / len(losses) if losses else 0
        weighted_pnl = sum(p.pnl_pct * (p.position_pct or 10) for p in closed) / sum(p.position_pct or 10 for p in closed)

        # ── Sharpe Ratio（假設無風險利率 1.5% / 年 ≈ 0.006% / 日）──
        pnl_list = [p.pnl_pct for p in closed]
        rf_per_trade = 1.5 / 252 * 20     # 以平均 20 交易日持倉為基準
        excess = [r - rf_per_trade for r in pnl_list]
        std_pnl = (sum((x - avg_pnl) ** 2 for x in pnl_list) / len(pnl_list)) ** 0.5
        sharpe = (avg_pnl - rf_per_trade) / std_pnl if std_pnl > 0 else 0

        # ── 最大回撤（模擬：用損益序列計算峰谷）────────────────
        cumulative = 0.0
        peak = 0.0
        max_drawdown = 0.0
        for r in pnl_list:
            cumulative += r
            if cumulative > peak:
                peak = cumulative
            dd = peak - cumulative
            if dd > max_drawdown:
                max_drawdown = dd

        # ── 0050 ETF 同期報酬（benchmark）────────────────────
        bench_ret = None
        try:
            all_dates = sorted(set(p.date_entered for p in all_pos if p.date_entered))
            if all_dates:
                start_d, end_d = all_dates[0], date.today()
                bench_rows = s.query(DailyPrice).filter(
                    DailyPrice.stock_id == "0050",
                    DailyPrice.date >= start_d,
                    DailyPrice.date <= end_d,
                ).order_by(DailyPrice.date).all()
                if len(bench_rows) >= 2:
                    bench_ret = (bench_rows[-1].close - bench_rows[0].close) / bench_rows[0].close * 100
        except Exception:
            pass

        logger.info("=" * 60)
        logger.info("📊 整體持倉績效報告")
        logger.info("=" * 60)
        logger.info(f"  已平倉：{len(closed)} 筆  |  持倉中：{len(active)} 筆")
        logger.info(f"  勝率：{win_rate:.1f}%  （{len(wins)} 勝 / {len(losses)} 負）")
        logger.info(f"  平均損益：{avg_pnl:+.2f}%（加權：{weighted_pnl:+.2f}%）")
        logger.info(f"  平均獲利：+{avg_win:.2f}%  |  平均虧損：{avg_loss:.2f}%")
        logger.info(f"  盈虧比：{abs(avg_win/avg_loss):.2f}" if avg_loss != 0 else "  盈虧比：∞")
        logger.info(f"  Sharpe Ratio：{sharpe:.2f}（每筆交易，rf≈1.5%/年）")
        logger.info(f"  最大累積回撤：{max_drawdown:.2f}%")
        if bench_ret is not None:
            logger.info(f"  同期 0050 報酬：{bench_ret:+.2f}%  |  Alpha：{avg_pnl - bench_ret/len(closed)*20:+.2f}%（每筆）")
        if active:
            active_pnl = sum(p.pnl_pct for p in active) / len(active)
            logger.info(f"  持倉中浮動均損益：{active_pnl:+.2f}%")
        logger.info("=" * 60)
        logger.info("各狀態明細：")
        for st in ["closed_profit", "closed_loss", "closed_signal", "active"]:
            grp = [p for p in all_pos if p.status == st]
            if grp:
                pnls = [p.pnl_pct for p in grp if p.pnl_pct is not None]
                avg  = sum(pnls)/len(pnls) if pnls else 0
                logger.info(f"  {st:20s}: {len(grp):3d} 筆  均損益 {avg:+.2f}%")
        logger.info("=" * 60)

    s.close()


if __name__ == "__main__":
    main()
