"""
trade_service.py — 使用者真實成交紀錄服務（ACTUAL 層）

設計原則：
  - 所有寫入操作原子完成（呼叫方負責 session.commit()）
  - 金額計算全部使用 Decimal，不用 Float
  - 移動加權平均成本法（MWAC）：
      BUY  → new_avg = (prev_cost_basis + price×shares + fee) / (prev_remaining + shares)
      SELL → realized += (price×shares - fee - tax) - avg_cost×shares_sold
             remaining_cost = prev_cost_basis - avg_cost×shares_sold
  - 成交永不刪除（is_cancelled 軟刪除）；取消後必須重新彙總持倉
  - pipeline / position_monitor 不得呼叫此模組
"""

import json
import logging
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

logger = logging.getLogger(__name__)

# 重複提交防護：相同欄位在此秒數內視為重複提交
_DUPLICATE_WINDOW_SECONDS = 60

# Decimal 精度常數
_P2 = Decimal("0.01")   # 金額（元）
_P4 = Decimal("0.0001")  # 均價（元，4 位小數）


class TradeSvcError(ValueError):
    """TradeService 業務邏輯錯誤（非 DB 層錯誤）。"""


# ── Public API ────────────────────────────────────────────────────────────────


def create_position(
    session,
    stock_id: str,
    stock_name: str,
    signal_source: str,
    open_date: date,
    target_price: Optional[Decimal] = None,
    stop_price: Optional[Decimal] = None,
    forward_signal_id: Optional[int] = None,
    notes: str = "",
):
    """
    建立真實持倉主檔。

    signal_source:
      'AI_SIGNAL' — 對應正式 BUY 推薦。forward_signal_id 必填，且 is_valid=True。
      'MANUAL'    — 使用者手動新增，與平台推薦無關。forward_signal_id 必須為 None。

    回傳新建的 ActualPosition（未 commit）。
    """
    from src.database import ActualPosition, ForwardSignal

    if signal_source not in ("AI_SIGNAL", "MANUAL"):
        raise TradeSvcError(
            f"signal_source 必須是 AI_SIGNAL 或 MANUAL，收到：{signal_source!r}"
        )

    if signal_source == "AI_SIGNAL":
        if forward_signal_id is None:
            raise TradeSvcError("signal_source=AI_SIGNAL 時，forward_signal_id 必填")
        fs = session.query(ForwardSignal).filter_by(id=forward_signal_id).first()
        if fs is None:
            raise TradeSvcError(f"forward_signal_id={forward_signal_id} 不存在")
        if not fs.is_valid:
            raise TradeSvcError(
                f"forward_signal_id={forward_signal_id} is_valid=False，不可建立持倉"
            )
        plan = {
            "trade_date": str(fs.trade_date),
            "entry_low": _to_float(fs.entry_low),
            "entry_high": _to_float(fs.entry_high),
            "stop_price": _to_float(fs.stop_price),
            "target1": _to_float(fs.target1),
            "target2": _to_float(fs.target2),
            "decision_label": fs.decision_label,
            "rec_level": fs.rec_level,
            "total_score": _to_float(fs.total_score),
            "confidence": _to_float(fs.confidence),
        }
        snapshot = json.dumps(plan, ensure_ascii=False)
    else:
        forward_signal_id = None
        snapshot = None

    pos = ActualPosition(
        stock_id=stock_id.strip(),
        stock_name=stock_name,
        position_type="ACTUAL",
        signal_source=signal_source,
        forward_signal_id=forward_signal_id,
        status="open",
        open_date=open_date,
        remaining_shares=0,
        avg_cost_per_share=Decimal("0"),
        total_cost_basis=Decimal("0"),
        realized_pnl=Decimal("0"),
        target_price=target_price,
        stop_price=stop_price,
        original_plan_snapshot=snapshot,
        notes=notes,
    )
    session.add(pos)
    session.flush()
    logger.info(
        f"[trade_service] create_position #{pos.id} {stock_id} ({signal_source})"
    )
    return pos


def add_execution(
    session,
    position_id: int,
    side: str,
    execution_date: date,
    execution_price: Decimal,
    shares: int,
    actual_fee: Decimal,
    transaction_tax: Decimal,
    execution_datetime: Optional[datetime] = None,
    linked_forward_signal_id: Optional[int] = None,
    notes: str = "",
):
    """
    新增一筆成交明細，並原子性重新彙總持倉。

    side: 'BUY' 或 'SELL'
    execution_price / actual_fee / transaction_tax 使用 Decimal。
    execution_datetime: UTC datetime（可選；使用者不知道時間則為 None）。

    防護：
      - 超賣（SELL > remaining_shares）→ TradeSvcError
      - 重複提交（相同內容在 _DUPLICATE_WINDOW_SECONDS 內）→ TradeSvcError
      - closed 持倉不可新增成交

    回傳新建的 TradeExecution（未 commit）。
    """
    from src.database import ActualPosition, TradeExecution

    _validate_execution_inputs(side, shares, execution_price, actual_fee, transaction_tax)

    pos = (
        session.query(ActualPosition)
        .filter_by(id=position_id)
        .with_for_update()
        .first()
    )
    if pos is None:
        raise TradeSvcError(f"actual_positions.id={position_id} 不存在")
    if pos.status == "closed":
        raise TradeSvcError(f"持倉 #{position_id} 已完全出場，不可新增成交")

    if side == "SELL" and shares > pos.remaining_shares:
        raise TradeSvcError(
            f"賣出 {shares} 股超過剩餘持倉 {pos.remaining_shares} 股，操作拒絕"
        )

    _check_duplicate(session, position_id, side, execution_date, execution_price, shares)

    exec_rec = TradeExecution(
        position_id=position_id,
        side=side,
        execution_date=execution_date,
        execution_datetime=execution_datetime,
        execution_price=execution_price,
        shares=shares,
        actual_fee=actual_fee,
        transaction_tax=transaction_tax,
        linked_forward_signal_id=linked_forward_signal_id,
        notes=notes,
        is_cancelled=False,
    )
    session.add(exec_rec)
    session.flush()

    _recalculate_position(session, pos)
    logger.info(
        f"[trade_service] add_execution #{exec_rec.id} {side} {shares}股 "
        f"@{execution_price} (pos #{position_id} {pos.stock_id})"
    )
    return exec_rec


def cancel_execution(session, execution_id: int, reason: str):
    """
    軟刪除一筆成交，並重新彙總整段持倉歷史。

    若取消後持倉歷史不合法（累計賣出 > 累計買進），拋出 TradeSvcError。
    原始成交記錄保留，只標記 is_cancelled=True（可稽核）。

    回傳已取消的 TradeExecution（未 commit）。
    """
    from src.database import ActualPosition, TradeExecution

    exec_rec = session.query(TradeExecution).filter_by(id=execution_id).first()
    if exec_rec is None:
        raise TradeSvcError(f"trade_executions.id={execution_id} 不存在")
    if exec_rec.is_cancelled:
        raise TradeSvcError(f"成交 #{execution_id} 已取消，不可重複取消")

    exec_rec.is_cancelled = True
    exec_rec.cancel_reason = reason
    exec_rec.cancelled_at = datetime.utcnow()
    exec_rec.updated_at = datetime.utcnow()
    session.flush()

    pos = (
        session.query(ActualPosition)
        .filter_by(id=exec_rec.position_id)
        .with_for_update()
        .first()
    )
    _recalculate_position(session, pos)
    logger.info(
        f"[trade_service] cancel_execution #{execution_id} "
        f"(pos #{pos.id} {pos.stock_id}): {reason}"
    )
    return exec_rec


def update_plan(
    session,
    position_id: int,
    field_name: str,
    new_value: Optional[Decimal],
    reason: str,
):
    """
    修改持倉計畫（target_price / stop_price），並建立不可刪除的稽核記錄。

    field_name: 'target_price' 或 'stop_price'
    原始 BUY 計畫（original_plan_snapshot）不可修改。

    回傳新建的 PositionPlanChange（未 commit）。
    """
    from src.database import ActualPosition, PositionPlanChange

    if field_name not in ("target_price", "stop_price"):
        raise TradeSvcError(
            f"field_name 只允許 target_price 或 stop_price，收到：{field_name!r}"
        )
    pos = session.query(ActualPosition).filter_by(id=position_id).first()
    if pos is None:
        raise TradeSvcError(f"actual_positions.id={position_id} 不存在")

    old_value = getattr(pos, field_name)
    setattr(pos, field_name, new_value)
    pos.updated_at = datetime.utcnow()

    change = PositionPlanChange(
        position_id=position_id,
        changed_at=datetime.utcnow(),
        field_name=field_name,
        old_value=old_value,
        new_value=new_value,
        reason=reason,
    )
    session.add(change)
    session.flush()
    logger.info(
        f"[trade_service] update_plan pos #{position_id}: "
        f"{field_name} {old_value} → {new_value}"
    )
    return change


def get_position(session, position_id: int):
    """回傳 ActualPosition 或 None。"""
    from src.database import ActualPosition

    return session.query(ActualPosition).filter_by(id=position_id).first()


def get_active_positions(session):
    """回傳所有 open / partially_closed 的 ActualPosition，按 open_date 倒序。"""
    from src.database import ActualPosition

    return (
        session.query(ActualPosition)
        .filter(ActualPosition.status.in_(["open", "partially_closed"]))
        .order_by(ActualPosition.open_date.desc())
        .all()
    )


def get_executions(session, position_id: int, include_cancelled: bool = False):
    """回傳指定持倉的成交明細，按日期 + id 正序。"""
    from src.database import TradeExecution

    q = session.query(TradeExecution).filter_by(position_id=position_id)
    if not include_cancelled:
        q = q.filter_by(is_cancelled=False)
    return q.order_by(TradeExecution.execution_date, TradeExecution.id).all()


# ── Internal helpers ──────────────────────────────────────────────────────────


def _validate_execution_inputs(side, shares, price, fee, tax):
    if side not in ("BUY", "SELL"):
        raise TradeSvcError(f"side 必須是 BUY 或 SELL，收到：{side!r}")
    if shares <= 0:
        raise TradeSvcError(f"shares 必須 > 0，收到：{shares}")
    if _d(price) <= 0:
        raise TradeSvcError(f"execution_price 必須 > 0，收到：{price}")
    if _d(fee) < 0:
        raise TradeSvcError(f"actual_fee 不得為負，收到：{fee}")
    if _d(tax) < 0:
        raise TradeSvcError(f"transaction_tax 不得為負，收到：{tax}")


def _check_duplicate(session, position_id, side, exec_date, price, shares):
    from src.database import TradeExecution

    cutoff = datetime.utcnow() - timedelta(seconds=_DUPLICATE_WINDOW_SECONDS)
    dup = (
        session.query(TradeExecution)
        .filter(
            TradeExecution.position_id == position_id,
            TradeExecution.side == side,
            TradeExecution.execution_date == exec_date,
            TradeExecution.shares == shares,
            TradeExecution.is_cancelled.is_(False),
            TradeExecution.created_at >= cutoff,
        )
        .filter(TradeExecution.execution_price == price)
        .first()
    )
    if dup is not None:
        raise TradeSvcError(
            f"偵測到可能重複提交（{_DUPLICATE_WINDOW_SECONDS}s 內已有相同成交 id={dup.id}）"
        )


def _recalculate_position(session, pos) -> None:
    """
    從所有未取消的成交記錄重新計算持倉彙總（移動加權平均成本法）。

    呼叫方已持有 with_for_update() 鎖，此函式僅做計算與 flush。

    BUY  側：
        cost_basis += price × shares + fee
        avg_cost = cost_basis / remaining

    SELL 側：
        cost_of_sold = avg_cost × shares_sold
        realized     += (price × shares - fee - tax) - cost_of_sold
        cost_basis   -= cost_of_sold
        avg_cost      = cost_basis / remaining  （remaining > 0 時）

    若任一 SELL 超過當時剩餘持倉，拋出 TradeSvcError（資料不一致）。
    """
    from src.database import TradeExecution

    execs = (
        session.query(TradeExecution)
        .filter_by(position_id=pos.id, is_cancelled=False)
        .order_by(TradeExecution.execution_date, TradeExecution.id)
        .all()
    )

    remaining = 0
    avg_cost = Decimal("0")
    cost_basis = Decimal("0")
    realized = Decimal("0")

    for ex in execs:
        price = _d(ex.execution_price)
        fee = _d(ex.actual_fee)
        tax = _d(ex.transaction_tax)
        sh = ex.shares

        if ex.side == "BUY":
            cost_basis += price * sh + fee
            remaining += sh
            avg_cost = cost_basis / remaining

        elif ex.side == "SELL":
            if sh > remaining:
                raise TradeSvcError(
                    f"持倉 #{pos.id} 歷史不一致：成交 #{ex.id} SELL {sh} 股，"
                    f"但當時剩餘僅 {remaining} 股。請先取消相關 SELL 成交再重試。"
                )
            cost_of_sold = avg_cost * sh
            realized += (price * sh - fee - tax) - cost_of_sold
            cost_basis -= cost_of_sold
            remaining -= sh
            avg_cost = cost_basis / remaining if remaining > 0 else Decimal("0")

    if remaining < 0:
        raise TradeSvcError(
            f"持倉 #{pos.id} 重新彙總後 remaining_shares={remaining}，資料嚴重不一致。"
        )

    pos.remaining_shares = remaining
    pos.avg_cost_per_share = avg_cost.quantize(_P4, rounding=ROUND_HALF_UP)
    pos.total_cost_basis = cost_basis.quantize(_P2, rounding=ROUND_HALF_UP)
    pos.realized_pnl = realized.quantize(_P2, rounding=ROUND_HALF_UP)

    total_bought = sum(e.shares for e in execs if e.side == "BUY")
    total_sold = sum(e.shares for e in execs if e.side == "SELL")

    if remaining == 0 and total_bought > 0:
        pos.status = "closed"
        last_sell = max(
            (e for e in execs if e.side == "SELL"),
            key=lambda e: (e.execution_date, e.id),
        )
        pos.close_date = last_sell.execution_date
    elif total_sold > 0 and remaining > 0:
        pos.status = "partially_closed"
    else:
        pos.status = "open"

    pos.updated_at = datetime.utcnow()
    session.flush()


def _d(v) -> Decimal:
    """Float / Numeric / str / None → Decimal（防止 SQLite 回傳 float 引起誤差）。"""
    if v is None:
        return Decimal("0")
    if isinstance(v, Decimal):
        return v
    return Decimal(str(float(v)))


def _to_float(v):
    """Decimal / float / None → float or None（JSON 序列化用）。"""
    if v is None:
        return None
    return float(v)
