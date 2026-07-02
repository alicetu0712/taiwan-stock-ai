"""
position_manager.py — 持倉管理與出場訊號引擎

功能：
  1. 推薦時建立持倉追蹤記錄（open_position）
  2. 每日掃描活躍持倉，偵測出場訊號（check_exit_signals）
  3. 手動關倉（close_position）
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

logger = logging.getLogger(__name__)

# 依等級建議持倉比例
POSITION_SIZE_MAP = {
    "A+": 30.0,
    "A":  20.0,
    "B":  10.0,
    "C":   5.0,
    "D":   0.0,
}

# 技術面轉弱閾值（低於此分數發出警示）
WEAK_TIMING_THRESHOLD   = 45.0
WEAK_BEHAVIOR_THRESHOLD = 40.0

# 追蹤停損觸發條件
TRAILING_BREAKEVEN_PCT  = 8.0    # 浮盈 >= 8%：停損移至進場價（保本）
TRAILING_LOCK_PCT       = 12.0   # 浮盈 >= 12%：停損移至 +6%（鎖利）
TRAILING_LOCK_FLOOR     = 6.0    # 鎖利後停損保留的最低獲利 %

# 時間停損：持倉超過此日曆天數且無明顯方向，強制出場
TIME_LIMIT_DAYS         = 45     # ≈ 30 個交易日


@dataclass
class ExitSignal:
    stock_id:    str
    reason:      str    # TARGET_HIT / STOP_LOSS / WEAK_TECHNICAL / INSTITUTIONAL_EXIT
    current_price: float
    pnl_pct:     float
    detail:      str


def open_position(
    session,
    stock_id:       str,
    stock_name:     str,
    entry_date:     date,
    entry_price:    float,
    rec_level:      str,
    rec_score:      float,
    confidence:     float,
    target_price:   float,
    stop_loss_price: float,
    target_pct:     float,
    stop_loss_pct:  float,
    ai_rationale:   str = "",
) -> bool:
    """建立新持倉。若同一股票已有 active 持倉則跳過。"""
    from src.database import PositionMonitor

    existing = (
        session.query(PositionMonitor)
        .filter(
            PositionMonitor.stock_id == stock_id,
            PositionMonitor.status   == "active",
        )
        .first()
    )
    if existing:
        logger.info(f"[Position] {stock_id} 已有活躍持倉，跳過建立")
        return False

    # 動態倉位：依信心度在基礎倉位上下調整（±5%，以 80% 信心為基準）
    # confidence 70% → -5%  | 80% → 基準  | 90% → +5%  | 最大單支 35%
    base_pct = POSITION_SIZE_MAP.get(rec_level, 10.0)
    conf_adj = round((confidence - 80.0) / 10.0 * 5.0)   # 每 10% 信心差異 = ±5%
    new_pct  = max(base_pct - 10, min(base_pct + 10, base_pct + conf_adj))
    new_pct  = min(new_pct, 35.0)  # 單支上限 35%
    new_pct  = round(new_pct, 0)
    logger.info(f"[Position] {stock_id} 倉位：{base_pct:.0f}%（基準）× 信心 {confidence:.0f}% → {new_pct:.0f}%")

    # 資金控管：確認剩餘資金足夠
    used_pct = (
        session.query(PositionMonitor)
        .filter(PositionMonitor.status == "active")
        .with_entities(PositionMonitor.position_pct)
        .all()
    )
    total_used = sum((r[0] or 0) for r in used_pct)
    if total_used + new_pct > 100.0:
        logger.info(
            f"[Position] {stock_id} 跳過：已用 {total_used:.0f}%＋新倉 {new_pct:.0f}% > 100%，資金不足"
        )
        return False

    pos = PositionMonitor(
        stock_id          = stock_id,
        stock_name        = stock_name,
        date_entered      = entry_date,
        entry_price       = entry_price,
        target_price      = target_price,
        stop_loss_price   = stop_loss_price,
        target_pct        = target_pct,
        stop_loss_pct     = stop_loss_pct,
        position_pct      = new_pct,
        ai_price_rationale= ai_rationale,
        rec_level         = rec_level,
        rec_score         = rec_score,
        confidence        = confidence,
        status            = "active",
    )
    session.add(pos)
    session.flush()
    logger.info(
        f"[Position] 建倉 {stock_id}（{stock_name}）"
        f" 進場 {entry_price:.2f}｜目標 {target_price:.2f}（+{target_pct:.1f}%）"
        f"｜停損 {stop_loss_price:.2f}（{stop_loss_pct:.1f}%）"
        f"｜持倉 {pos.position_pct:.0f}%"
    )
    return True


def check_exit_signals(
    session,
    trade_date: date,
    price_map:  dict,           # {stock_id: current_close_price}
    timing_map: dict = None,    # {stock_id: timing_score}  （可選）
    behavior_map: dict = None,  # {stock_id: behavior_score}（可選）
) -> list:
    """
    掃描所有 active 持倉，回傳出場訊號列表。
    不自動關倉，由呼叫者決定是否執行 close_position。
    """
    from src.database import PositionMonitor

    timing_map   = timing_map   or {}
    behavior_map = behavior_map or {}

    positions = (
        session.query(PositionMonitor)
        .filter(PositionMonitor.status == "active")
        .all()
    )

    signals = []
    for pos in positions:
        sid = pos.stock_id
        current_price = price_map.get(sid)
        if current_price is None:
            continue

        pnl = (current_price - pos.entry_price) / pos.entry_price * 100

        # ── 追蹤停損更新（動態調整 stop_loss_price）────────────
        if pos.entry_price and pos.entry_price > 0:
            if pnl >= TRAILING_LOCK_PCT:
                locked = round(pos.entry_price * (1 + TRAILING_LOCK_FLOOR / 100), 2)
                if locked > (pos.stop_loss_price or 0):
                    pos.stop_loss_price = locked
                    logger.info(f"[Trailing] {sid} 浮盈 {pnl:.1f}%，停損上移至 +{TRAILING_LOCK_FLOOR}%（{locked:.2f}）")
            elif pnl >= TRAILING_BREAKEVEN_PCT:
                if pos.entry_price > (pos.stop_loss_price or 0):
                    pos.stop_loss_price = pos.entry_price
                    logger.info(f"[Trailing] {sid} 浮盈 {pnl:.1f}%，停損移至保本（{pos.entry_price:.2f}）")

        # 1. 目標價達成
        if pos.target_price and current_price >= pos.target_price:
            signals.append(ExitSignal(
                stock_id=sid, reason="TARGET_HIT",
                current_price=current_price, pnl_pct=round(pnl, 2),
                detail=f"現價 {current_price:.2f} 達目標 {pos.target_price:.2f}（+{pnl:.1f}%）",
            ))
            continue

        # 2. 停損觸發
        if pos.stop_loss_price and current_price <= pos.stop_loss_price:
            signals.append(ExitSignal(
                stock_id=sid, reason="STOP_LOSS",
                current_price=current_price, pnl_pct=round(pnl, 2),
                detail=f"現價 {current_price:.2f} 跌破停損 {pos.stop_loss_price:.2f}（{pnl:.1f}%）",
            ))
            continue

        # 3. 技術面轉弱
        t_score = timing_map.get(sid)
        b_score = behavior_map.get(sid)
        if t_score is not None and b_score is not None:
            if t_score < WEAK_TIMING_THRESHOLD and b_score < WEAK_BEHAVIOR_THRESHOLD:
                signals.append(ExitSignal(
                    stock_id=sid, reason="WEAK_TECHNICAL",
                    current_price=current_price, pnl_pct=round(pnl, 2),
                    detail=f"技術分 {t_score:.0f}、籌碼分 {b_score:.0f} 雙雙偏弱",
                ))
                continue

        # 4. 法人持續賣超
        if b_score is not None and b_score < WEAK_BEHAVIOR_THRESHOLD:
            signals.append(ExitSignal(
                stock_id=sid, reason="INSTITUTIONAL_EXIT",
                current_price=current_price, pnl_pct=round(pnl, 2),
                detail=f"法人籌碼大幅轉向，市場行為分 {b_score:.0f}",
            ))
            continue

        # 5. 30 交易日（≈45 日曆天）強制出場：持倉虧損且無方向，釋放資本
        # 邏輯：pnl < 0（虧損），且無停損觸發（沒有跌到停損），持倉時間太長
        # 小浮盈（0~8%）給更多時間，只要不在虧損就繼續持有
        if pos.date_entered:
            held_days = (trade_date - pos.date_entered).days
            if held_days >= TIME_LIMIT_DAYS and pnl < 0 and abs(pnl) < TRAILING_BREAKEVEN_PCT:
                signals.append(ExitSignal(
                    stock_id=sid, reason="TIME_LIMIT",
                    current_price=current_price, pnl_pct=round(pnl, 2),
                    detail=f"持倉 {held_days} 天小幅虧損（{pnl:+.1f}%）且無明顯復甦，釋放資本",
                ))
            elif held_days >= TIME_LIMIT_DAYS * 2 and abs(pnl) < TRAILING_BREAKEVEN_PCT:
                # 超過 90 天（≈60 交易日）不管盈虧都強制出場
                signals.append(ExitSignal(
                    stock_id=sid, reason="TIME_LIMIT",
                    current_price=current_price, pnl_pct=round(pnl, 2),
                    detail=f"持倉 {held_days} 天超過雙倍時限（{pnl:+.1f}%），強制釋放資本",
                ))

    return signals


def close_position(
    session,
    stock_id:      str,
    exit_date:     date,
    exit_price:    float,
    exit_reason:   str,
) -> Optional[object]:
    """關閉指定股票的活躍持倉。"""
    from src.database import PositionMonitor

    pos = (
        session.query(PositionMonitor)
        .filter(
            PositionMonitor.stock_id == stock_id,
            PositionMonitor.status   == "active",
        )
        .first()
    )
    if not pos:
        return None

    pnl = (exit_price - pos.entry_price) / pos.entry_price * 100
    pos.status      = _exit_status(exit_reason, pnl)
    pos.exit_date   = exit_date
    pos.exit_price  = exit_price
    pos.exit_reason = exit_reason
    pos.pnl_pct     = round(pnl, 2)

    from datetime import datetime
    pos.updated_at = datetime.utcnow()

    logger.info(
        f"[Position] 關倉 {stock_id}  原因:{exit_reason}"
        f"  進場:{pos.entry_price:.2f} → 出場:{exit_price:.2f}  損益:{pnl:+.1f}%"
    )
    return pos


def _exit_status(reason: str, pnl: float) -> str:
    if reason == "TARGET_HIT":
        return "closed_profit"
    if reason in ("STOP_LOSS", "TRAILING_STOP"):
        return "closed_profit" if pnl > 0 else "closed_loss"
    if reason == "MANUAL":
        return "closed_manual"
    return "closed_signal"   # WEAK_TECHNICAL / INSTITUTIONAL_EXIT / TIME_LIMIT
