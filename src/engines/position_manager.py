"""
position_manager.py — 持倉管理與出場訊號引擎

功能：
  1. 推薦時建立持倉追蹤記錄（open_position）
  2. 每日掃描活躍持倉，偵測出場訊號（check_exit_signals）
  3. 手動關倉（close_position）
"""

import logging
from dataclasses import dataclass
from datetime import date
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

    pos = PositionMonitor(
        stock_id          = stock_id,
        stock_name        = stock_name,
        date_entered      = entry_date,
        entry_price       = entry_price,
        target_price      = target_price,
        stop_loss_price   = stop_loss_price,
        target_pct        = target_pct,
        stop_loss_pct     = stop_loss_pct,
        position_pct      = POSITION_SIZE_MAP.get(rec_level, 10.0),
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
    if reason == "STOP_LOSS":
        return "closed_loss"
    if reason == "MANUAL":
        return "closed_manual"
    return "closed_signal"
