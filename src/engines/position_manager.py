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

import config as _cfg

logger = logging.getLogger(__name__)

# Shadow Trading integrity: 執行窗口最大允許落後天數。
# 0 = pipeline 必須在 expected_execution_date 當日執行；隔天跑即視為錯過。
# 若設 1，允許 1 個日曆日的 pipeline 延遲（但開盤價已為昨日資訊，非即時）。
# 保守設為 0：只有 as_of_date == expected_execution_date 才能激活。
MAX_EXECUTION_LAG_DAYS: int = 0

# 依等級建議基準持倉比例（信心調整前）
# 最終持倉受 config.POSITION_SIZING["max_single_pct"] 硬性上限約束
POSITION_SIZE_MAP = {
    "A+": 20.0,
    "A": 20.0,
    "B": 10.0,
    "C": 5.0,
    "D": 0.0,
}

# 技術面轉弱閾值（低於此分數發出警示）
WEAK_TIMING_THRESHOLD = 45.0
WEAK_BEHAVIOR_THRESHOLD = 40.0

# 追蹤停損觸發條件
TRAILING_BREAKEVEN_PCT = 8.0  # 浮盈 >= 8%：停損移至進場價（保本）
TRAILING_LOCK_PCT = 12.0  # 浮盈 >= 12%：停損移至 +6%（鎖利）
TRAILING_LOCK_FLOOR = 6.0  # 鎖利後停損保留的最低獲利 %

# 時間停損：持倉超過此日曆天數且無明顯方向，強制出場
TIME_LIMIT_DAYS = 45  # ≈ 30 個交易日


@dataclass
class ExitSignal:
    stock_id: str
    reason: str  # TARGET_HIT / STOP_LOSS / WEAK_TECHNICAL / INSTITUTIONAL_EXIT
    current_price: float
    pnl_pct: float
    detail: str


def _compute_position_pct(rec_level: str, confidence: float) -> float:
    """計算倉位百分比，上限強制為 config.max_single_pct。"""
    max_single_pct = _cfg.POSITION_SIZING.get("max_single_pct", 20.0)
    base_pct = POSITION_SIZE_MAP.get(rec_level, 10.0)
    conf_adj = round((confidence - 80.0) / 10.0 * 5.0)
    new_pct = max(base_pct - 10, min(base_pct + 10, base_pct + conf_adj))
    return round(min(new_pct, max_single_pct), 0)


def create_pending_position(
    session,
    stock_id: str,
    stock_name: str,
    signal_date: date,
    expected_execution_date: date,
    rec_level: str,
    rec_score: float,
    confidence: float,
    target_price: float,
    stop_loss_price: float,
    target_pct: float,
    stop_loss_pct: float,
    ai_rationale: str = "",
) -> bool:
    """
    Signal Date 建立 pending_open 持倉（無進場價）。

    規則：
      - 同一 stock_id 若已有 pending_open 或 active 持倉，跳過（防重複）。
      - entry_price / date_entered 留 NULL，待 activate_pending_positions 填入。
      - 不得使用 fallback close 或推估價格。
    """
    from src.database import PositionMonitor

    already = (
        session.query(PositionMonitor)
        .filter(
            PositionMonitor.stock_id == stock_id,
            PositionMonitor.status.in_(["pending_open", "active"]),
        )
        .first()
    )
    if already:
        logger.info(f"[Position] {stock_id} 已有 pending_open/active 持倉，跳過")
        return False

    new_pct = _compute_position_pct(rec_level, confidence)
    logger.info(
        f"[Position] {stock_id} 倉位：{new_pct:.0f}%（base={POSITION_SIZE_MAP.get(rec_level,10):.0f}%"
        f", conf={confidence:.0f}%, cap={_cfg.POSITION_SIZING.get('max_single_pct',20):.0f}%）"
    )

    pos = PositionMonitor(
        stock_id=stock_id,
        stock_name=stock_name,
        signal_date=signal_date,
        expected_execution_date=expected_execution_date,
        entry_price=None,        # 未執行，不得填收盤價
        date_entered=None,       # 未執行
        target_price=target_price,
        stop_loss_price=stop_loss_price,
        target_pct=target_pct,
        stop_loss_pct=stop_loss_pct,
        position_pct=new_pct,
        ai_price_rationale=ai_rationale,
        rec_level=rec_level,
        rec_score=rec_score,
        confidence=confidence,
        status="pending_open",
    )
    session.add(pos)
    session.flush()
    logger.info(
        f"[Position] pending_open 建立 {stock_id}（{stock_name}）"
        f"  signal={signal_date}  exec_date={expected_execution_date}"
        f"  目標 {target_price}（+{target_pct:.1f}%）停損 {stop_loss_price}（{stop_loss_pct:.1f}%）"
    )
    return True


def activate_pending_positions(session, as_of_date: date) -> int:
    """
    Execution Date：將 pending_open 持倉轉為 active（填入真實 open 進場價）。

    Shadow Trading 完整性規則：
      - 僅當 as_of_date == expected_execution_date（或在 MAX_EXECUTION_LAG_DAYS 範圍內）才激活。
      - 超過執行窗口 → status = 'missed_execution'（不得事後補成交）。
      - 進場價必須來自 DailyPrice.open；open 不存在時，不激活、不 fallback。
      - 檢查訊號有效性：is_valid=False 或 lifecycle 異常 → status = 'cancelled'。
    Returns: 激活筆數
    """
    from src.database import DailyPrice, PositionMonitor, Recommendation

    pending = (
        session.query(PositionMonitor)
        .filter(
            PositionMonitor.status == "pending_open",
            PositionMonitor.expected_execution_date.isnot(None),
            PositionMonitor.expected_execution_date <= as_of_date,
        )
        .all()
    )
    if not pending:
        return 0

    activated = 0
    for pos in pending:
        exec_date = pos.expected_execution_date

        # ── Shadow Trading 完整性：逾期執行窗口 ──────────────
        lag = (as_of_date - exec_date).days
        if lag > MAX_EXECUTION_LAG_DAYS:
            pos.status = "missed_execution"
            logger.warning(
                f"[Position] {pos.stock_id} exec_date={exec_date} lag={lag}d "
                f"> MAX_EXECUTION_LAG_DAYS={MAX_EXECUTION_LAG_DAYS} "
                "→ missed_execution（不得事後補成交）"
            )
            continue

        # ── 檢查訊號有效性（signal_date 對應的 Recommendation）──
        if pos.signal_date:
            rec = (
                session.query(Recommendation)
                .filter(
                    Recommendation.stock_id == pos.stock_id,
                    Recommendation.date == pos.signal_date,
                )
                .first()
            )
            if rec is not None:
                if getattr(rec, "is_valid", True) is False:
                    pos.status = "cancelled"
                    logger.info(f"[Position] {pos.stock_id} signal is_valid=False → cancelled")
                    continue
                lifecycle = getattr(rec, "lifecycle_status", None)
                if lifecycle is not None and lifecycle not in ("active", None, ""):
                    pos.status = "cancelled"
                    logger.info(
                        f"[Position] {pos.stock_id} lifecycle={lifecycle} → cancelled"
                    )
                    continue

        # ── 取真實開盤進場價 ──────────────────────────────────
        dp = (
            session.query(DailyPrice)
            .filter(
                DailyPrice.stock_id == pos.stock_id,
                DailyPrice.date == exec_date,
            )
            .first()
        )
        if dp is None or dp.open is None or dp.open <= 0:
            logger.info(
                f"[Position] {pos.stock_id} exec_date={exec_date}"
                " open 尚未取得，保持 pending_open"
            )
            continue

        # ── 激活：NEXT_OPEN_HISTORICAL ─────────────────────────
        # 注意：pipeline 在收盤後執行，open 為已知資訊（歷史模擬語意）。
        # 欲取得 LIVE_PREOPEN_OBSERVED，需在盤前單獨建立 pre-open execution 流程。
        now = datetime.utcnow()
        pos.entry_price            = dp.open
        pos.date_entered           = exec_date
        pos.entry_source           = "NEXT_OPEN"
        pos.shadow_trading_type    = "NEXT_OPEN_HISTORICAL"
        pos.execution_recorded_at  = now
        pos.status                 = "active"
        pos.updated_at             = now
        activated += 1
        logger.info(
            f"[Position] 激活 {pos.stock_id}  進場價 {dp.open:.2f}（{exec_date}）"
            f" [NEXT_OPEN_HISTORICAL / pipeline 收盤後執行，open 已知]"
        )

    # flush all state changes (activated, missed_execution, cancelled)
    session.flush()
    return activated


def open_position(
    session,
    stock_id: str,
    stock_name: str,
    entry_date: date,
    entry_price: float,
    rec_level: str,
    rec_score: float,
    confidence: float,
    target_price: float,
    stop_loss_price: float,
    target_pct: float,
    stop_loss_pct: float,
    ai_rationale: str = "",
) -> bool:
    """已確認進場價時直接建立 active 持倉（後向相容，供測試及手動呼叫）。

    正式 Shadow Trading 流程請改用 create_pending_position + activate_pending_positions。
    """
    from src.database import PositionMonitor

    if entry_price is None or entry_price <= 0:
        logger.warning(f"[Position] {stock_id} open_position 缺 entry_price，拒絕建倉")
        return False

    existing = (
        session.query(PositionMonitor)
        .filter(
            PositionMonitor.stock_id == stock_id,
            PositionMonitor.status.in_(["pending_open", "active"]),
        )
        .first()
    )
    if existing:
        logger.info(f"[Position] {stock_id} 已有 pending_open/active 持倉，跳過建立")
        return False

    max_single_pct = _cfg.POSITION_SIZING.get("max_single_pct", 20.0)
    base_pct = POSITION_SIZE_MAP.get(rec_level, 10.0)
    conf_adj = round((confidence - 80.0) / 10.0 * 5.0)
    new_pct = max(base_pct - 10, min(base_pct + 10, base_pct + conf_adj))
    new_pct = min(new_pct, max_single_pct)
    new_pct = round(new_pct, 0)
    logger.info(
        f"[Position] {stock_id} 倉位：{base_pct:.0f}%（基準）× 信心 {confidence:.0f}% → {new_pct:.0f}%"
    )

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
        stock_id=stock_id,
        stock_name=stock_name,
        signal_date=entry_date,
        expected_execution_date=entry_date,
        date_entered=entry_date,
        entry_price=entry_price,
        entry_source="CONFIRMED",
        target_price=target_price,
        stop_loss_price=stop_loss_price,
        target_pct=target_pct,
        stop_loss_pct=stop_loss_pct,
        position_pct=new_pct,
        ai_price_rationale=ai_rationale,
        rec_level=rec_level,
        rec_score=rec_score,
        confidence=confidence,
        status="active",
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
    price_map: dict,  # {stock_id: current_close_price}
    timing_map: dict = None,  # {stock_id: timing_score}  （可選）
    behavior_map: dict = None,  # {stock_id: behavior_score}（可選）
) -> list:
    """
    掃描所有 active 持倉，回傳出場訊號列表。
    不自動關倉，由呼叫者決定是否執行 close_position。
    """
    from src.database import PositionMonitor

    timing_map = timing_map or {}
    behavior_map = behavior_map or {}

    positions = (
        session.query(PositionMonitor).filter(PositionMonitor.status == "active").all()
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
                    logger.info(
                        f"[Trailing] {sid} 浮盈 {pnl:.1f}%，停損上移至 +{TRAILING_LOCK_FLOOR}%（{locked:.2f}）"
                    )
            elif pnl >= TRAILING_BREAKEVEN_PCT:
                if pos.entry_price > (pos.stop_loss_price or 0):
                    pos.stop_loss_price = pos.entry_price
                    logger.info(
                        f"[Trailing] {sid} 浮盈 {pnl:.1f}%，停損移至保本（{pos.entry_price:.2f}）"
                    )

        # 1. 目標價達成
        if pos.target_price and current_price >= pos.target_price:
            signals.append(
                ExitSignal(
                    stock_id=sid,
                    reason="TARGET_HIT",
                    current_price=current_price,
                    pnl_pct=round(pnl, 2),
                    detail=f"現價 {current_price:.2f} 達目標 {pos.target_price:.2f}（+{pnl:.1f}%）",
                )
            )
            continue

        # 2. 停損觸發
        if pos.stop_loss_price and current_price <= pos.stop_loss_price:
            signals.append(
                ExitSignal(
                    stock_id=sid,
                    reason="STOP_LOSS",
                    current_price=current_price,
                    pnl_pct=round(pnl, 2),
                    detail=f"現價 {current_price:.2f} 跌破停損 {pos.stop_loss_price:.2f}（{pnl:.1f}%）",
                )
            )
            continue

        # 3. 技術面轉弱
        t_score = timing_map.get(sid)
        b_score = behavior_map.get(sid)
        if t_score is not None and b_score is not None:
            if t_score < WEAK_TIMING_THRESHOLD and b_score < WEAK_BEHAVIOR_THRESHOLD:
                signals.append(
                    ExitSignal(
                        stock_id=sid,
                        reason="WEAK_TECHNICAL",
                        current_price=current_price,
                        pnl_pct=round(pnl, 2),
                        detail=f"技術分 {t_score:.0f}、籌碼分 {b_score:.0f} 雙雙偏弱",
                    )
                )
                continue

        # 4. 法人持續賣超
        if b_score is not None and b_score < WEAK_BEHAVIOR_THRESHOLD:
            signals.append(
                ExitSignal(
                    stock_id=sid,
                    reason="INSTITUTIONAL_EXIT",
                    current_price=current_price,
                    pnl_pct=round(pnl, 2),
                    detail=f"法人籌碼大幅轉向，市場行為分 {b_score:.0f}",
                )
            )
            continue

        # 5. 30 交易日（≈45 日曆天）強制出場：持倉虧損且無方向，釋放資本
        # 邏輯：pnl < 0（虧損），且無停損觸發（沒有跌到停損），持倉時間太長
        # 小浮盈（0~8%）給更多時間，只要不在虧損就繼續持有
        if pos.date_entered:
            held_days = (trade_date - pos.date_entered).days
            if (
                held_days >= TIME_LIMIT_DAYS
                and pnl < 0
                and abs(pnl) < TRAILING_BREAKEVEN_PCT
            ):
                signals.append(
                    ExitSignal(
                        stock_id=sid,
                        reason="TIME_LIMIT",
                        current_price=current_price,
                        pnl_pct=round(pnl, 2),
                        detail=f"持倉 {held_days} 天小幅虧損（{pnl:+.1f}%）且無明顯復甦，釋放資本",
                    )
                )
            elif held_days >= TIME_LIMIT_DAYS * 2 and abs(pnl) < TRAILING_BREAKEVEN_PCT:
                # 超過 90 天（≈60 交易日）不管盈虧都強制出場
                signals.append(
                    ExitSignal(
                        stock_id=sid,
                        reason="TIME_LIMIT",
                        current_price=current_price,
                        pnl_pct=round(pnl, 2),
                        detail=f"持倉 {held_days} 天超過雙倍時限（{pnl:+.1f}%），強制釋放資本",
                    )
                )

    return signals


def close_position(
    session,
    stock_id: str,
    exit_date: date,
    exit_price: float,
    exit_reason: str,
) -> Optional[object]:
    """關閉指定股票的活躍持倉。"""
    from src.database import PositionMonitor

    pos = (
        session.query(PositionMonitor)
        .filter(
            PositionMonitor.stock_id == stock_id,
            PositionMonitor.status == "active",
        )
        .first()
    )
    if not pos:
        return None

    pnl = (exit_price - pos.entry_price) / pos.entry_price * 100
    pos.status = _exit_status(exit_reason, pnl)
    pos.exit_date = exit_date
    pos.exit_price = exit_price
    pos.exit_reason = exit_reason
    pos.pnl_pct = round(pnl, 2)

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
    return "closed_signal"  # WEAK_TECHNICAL / INSTITUTIONAL_EXIT / TIME_LIMIT
