"""
candidate_pool_service.py — 進場候選追蹤池

每日 pipeline Step 9e 呼叫 update_candidate_pool()。
追蹤候選股票從入池到正式 BUY 或失效的完整生命週期。

設計原則：
- 入池條件沿用現有 Decision Center 輸出，不新增選股門檻
- near_entry 狀態直接映射 decision_code == 'wait_pullback' 或 setup_type == 'near_breakout'
- triggered_buy 必須來自 ForwardSignal（唯一 BUY 來源）
- Pipeline 冪等：重跑同日不重複建立記錄
- 失敗必須拋出 RuntimeError（不得靜默忽略）
"""

import logging
from datetime import date, datetime
from typing import Optional

logger = logging.getLogger(__name__)

CANDIDATE_POOL_VERSION = "v1.0"

# 有明確技術型態的 setup_type（入池條件之一）
CANDIDATE_ELIGIBLE_SETUPS = frozenset({
    "breakout",
    "near_breakout",
    "pullback_buy",
    "pullback_hold",
    "trending",
})

# 技術型態已失效（觸發即時退出）
THESIS_FAILED_SETUPS = frozenset({"breakdown", "failed_breakout"})

CANDIDATE_MIN_SCORE = 55.0       # 品質底線（與 select_opportunities 對齊）
OVERDUE_TRADING_DAYS = 10        # 第 10 交易日起標記逾期
MAX_WATCH_TRADING_DAYS = 20      # 第 20 交易日強制退出

# ── 入池 / 狀態判斷 ──────────────────────────────────────────────────────────


def _is_eligible_new_candidate(ar, rec) -> bool:
    """
    判斷今日分析結果是否符合入池條件。
    沿用現有 Decision Center 輸出，不新增選股邏輯。
    """
    if (ar.setup_type or "none") not in CANDIDATE_ELIGIBLE_SETUPS:
        return False
    if (ar.trade_signal or "wait") in ("sell", "reduce"):
        return False
    if (ar.total_score or 0.0) < CANDIDATE_MIN_SCORE:
        return False
    if rec and (rec.decision_code or "wait") in ("sell", "reduce"):
        return False
    return True


def _is_thesis_failed(ar, rec) -> bool:
    """技術型態失效或明確賣出訊號 → 立即退出。"""
    if (ar.setup_type or "none") in THESIS_FAILED_SETUPS:
        return True
    if (ar.trade_signal or "wait") in ("sell", "reduce"):
        return True
    if rec and (rec.decision_code or "wait") in ("sell", "reduce"):
        return True
    return False


def _determine_status(ar, rec) -> str:
    """
    依現有 decision_label 邏輯判斷候選狀態。
    near_entry 條件：
      1. decision_code == 'wait_pullback'（模型看多，但現價偏離 MA20 > 門檻 → 等回測）
      2. setup_type == 'near_breakout'（接近突破關鍵壓力位）
    """
    dc = (rec.decision_code if rec else None) or "wait"
    st = ar.setup_type or "none"

    if dc == "wait_pullback":
        return "near_entry"
    if st == "near_breakout":
        return "near_entry"
    return "watching"


def _get_entry_reason(ar, rec) -> str:
    """生成入池原因（白話，沿用 entry_quality_label）。"""
    from src.engines.decision import entry_quality_label

    label = entry_quality_label({
        "trade_signal": ar.trade_signal or "wait",
        "setup_type": ar.setup_type or "none",
        "ma20_gap": ar.ma20_gap or 0.0,
    })
    setup_desc = {
        "breakout":     "突破型態確立",
        "near_breakout": "接近關鍵突破位置",
        "pullback_buy": "回測至支撐，型態健康",
        "pullback_hold": "上升趨勢中的健康回測",
        "trending":     "多頭趨勢延伸",
    }
    setup_text = setup_desc.get(ar.setup_type or "none", "技術型態待觀察")
    score_text = f"綜合 {ar.total_score:.0f} 分" if ar.total_score else ""
    parts = [p for p in [setup_text, label, score_text] if p]
    return "；".join(parts)


def _get_missing_conditions(ar, rec) -> str:
    """
    生成「距離正式 BUY 還缺什麼」說明。
    優先使用 decision_label 已有的邏輯，不新增 BUY 規則。
    """
    from src.engines.decision import tomorrow_triggers

    dc = (rec.decision_code if rec else None) or "wait"
    st = ar.setup_type or "none"

    # wait_pullback：使用現有 ma20_gap 資訊 + entry range
    if dc == "wait_pullback" and rec:
        gap = rec.ma20_gap or ar.ma20_gap or 0.0
        lo = rec.entry_low or 0
        hi = rec.entry_high or 0
        range_str = f"（目標進場區 {lo:.0f}–{hi:.0f}）" if lo and hi else ""
        return f"現價偏離 MA20 達 {gap:.1f}%，需回測至合理進場區{range_str}後再考慮進場"

    # 使用 decision.tomorrow_triggers 生成觀察重點
    triggers = tomorrow_triggers({
        "setup_type": st,
        "trade_signal": ar.trade_signal or "wait",
        "vol_ratio": (rec.vol_ratio if rec else None) or ar.volume_ratio,
        "ma20_gap": (rec.ma20_gap if rec else None) or ar.ma20_gap or 0.0,
    })
    if triggers:
        # 清理 emoji，最多取前 2 條
        cleaned = []
        for t in triggers[:2]:
            for prefix in ("⚠️ ", "✓ ", "❌ ", "⚠ "):
                t = t.replace(prefix, "")
            cleaned.append(t)
        return "；".join(cleaned)

    # fallback
    static = {
        "breakout":     "等待量能確認，量比需 ≥ 1.0x 且收在突破位以上",
        "near_breakout": "等待放量突破確認，收盤站上近20日高點",
        "pullback_buy": "等待支撐守穩確認，量縮止跌後可考慮進場",
        "pullback_hold": "等待 MA20 支撐守穩確認",
        "trending":     "趨勢延伸中，等待型態確認或下一個回測進場點",
    }
    return static.get(st, "持續觀察各項技術指標")


def _build_change_notes(cand, ar, rec) -> str:
    """
    比較今日狀態與昨日（cand.latest_*）快照，生成可讀的變化說明。
    在更新 cand.latest_* 之前呼叫。
    """
    notes = []
    new_setup = ar.setup_type or "none"
    old_setup = cand.latest_setup_type or "none"
    if new_setup != old_setup:
        notes.append(f"型態 {old_setup} → {new_setup}")

    new_dc = (rec.decision_code if rec else None) or "wait"
    old_dc = cand.latest_decision_code or "wait"
    if new_dc != old_dc:
        notes.append(f"決策碼 {old_dc} → {new_dc}")

    new_score = ar.total_score or 0.0
    old_score = cand.latest_total_score or 0.0
    if abs(new_score - old_score) >= 5.0:
        sign = "+" if new_score >= old_score else ""
        notes.append(f"總分 {old_score:.0f} → {new_score:.0f}（{sign}{new_score - old_score:.0f}）")

    return "，".join(notes) if notes else "各項指標穩定，無重大變化"


# ── 交易日計算 ────────────────────────────────────────────────────────────────


def _count_trading_days(session, start_date: date, end_date: date) -> int:
    """計算 (start_date, end_date] 之間的台股交易日數（含 end_date，不含 start_date）。"""
    from src.database import DailyPrice
    return (
        session.query(DailyPrice.date)
        .filter(
            DailyPrice.stock_id == "0050",
            DailyPrice.date > start_date,
            DailyPrice.date <= end_date,
            DailyPrice.close.isnot(None),
        )
        .count()
    )


# ── ForwardSignal BUY 偵測 ────────────────────────────────────────────────────


def _find_triggered_buy(session, stock_id: str, first_seen_date: date):
    """
    檢查自候選入池日起是否有正式 ForwardSignal BUY。
    僅查詢當前 MODEL_VERSION，避免跨版本污染。
    """
    from src.database import ForwardSignal, MODEL_VERSION
    return (
        session.query(ForwardSignal)
        .filter(
            ForwardSignal.stock_id == stock_id,
            ForwardSignal.model_version == MODEL_VERSION,
            ForwardSignal.trade_date >= first_seen_date,
            ForwardSignal.trade_signal.in_(["buy", "strong_buy"]),
        )
        .order_by(ForwardSignal.trade_date.desc())
        .first()
    )


# ── 主要服務函式 ──────────────────────────────────────────────────────────────


def update_candidate_pool(session, check_date: date) -> dict:
    """
    每日候選池更新（冪等）。

    執行順序：
      1. 載入今日 AnalysisResult（所有分析股票）與 Recommendation（supplementary）
      2. 更新現有 active 候選
      3. 新增今日符合條件的新候選
      4. 寫入 CandidatePoolHistory（每日快照）

    Returns: stats dict，pipeline log 用。
    Raises: RuntimeError — 任何 DB 寫入失敗都拋出，不靜默忽略。
    """
    from src.database import (
        AnalysisResult,
        CandidatePool,
        CandidatePoolHistory,
        ForwardSignal,
        MODEL_VERSION,
        Recommendation,
    )

    stats = {
        "new_entries": 0,
        "triggered_buy": 0,
        "thesis_failed": 0,
        "expired": 0,
        "overdue_marked": 0,
        "updated": 0,
        "skipped_idempotent": 0,
    }

    # ── 載入今日數據 ────────────────────────────────────────────
    today_ar_map = {
        r.stock_id: r
        for r in session.query(AnalysisResult).filter_by(date=check_date).all()
    }
    today_rec_map = {
        r.stock_id: r
        for r in session.query(Recommendation)
        .filter(
            Recommendation.date == check_date,
            Recommendation.is_valid.isnot(False),
        )
        .all()
    }
    # 今日已有 ForwardSignal BUY 的股票（不加入新候選，它們已是正式 BUY）
    today_buy_stocks = {
        r.stock_id
        for r in session.query(ForwardSignal.stock_id)
        .filter(
            ForwardSignal.trade_date == check_date,
            ForwardSignal.model_version == MODEL_VERSION,
            ForwardSignal.trade_signal.in_(["buy", "strong_buy"]),
        )
        .all()
    }

    # ── Step 1: 更新 active 候選 ─────────────────────────────────
    active_candidates = (
        session.query(CandidatePool)
        .filter(
            CandidatePool.status.in_(["watching", "near_entry", "overdue"]),
            CandidatePool.pool_version == CANDIDATE_POOL_VERSION,
            CandidatePool.model_version == MODEL_VERSION,
        )
        .all()
    )

    for cand in active_candidates:
        # 冪等性：今日已有歷史記錄就跳過
        already_done = (
            session.query(CandidatePoolHistory)
            .filter_by(candidate_id=cand.id, check_date=check_date)
            .first()
        )
        if already_done:
            stats["skipped_idempotent"] += 1
            continue

        old_status = cand.status
        ar = today_ar_map.get(cand.stock_id)
        rec = today_rec_map.get(cand.stock_id)
        change_notes = ""

        # ── BUY 偵測（優先）──────────────────────────────────────
        triggered = _find_triggered_buy(session, cand.stock_id, cand.first_seen_date)
        if triggered:
            cand.status = "triggered_buy"
            cand.triggered_buy_date = triggered.trade_date
            cand.forward_signal_id = triggered.id
            cand.exit_date = check_date
            cand.exit_reason = "TRIGGERED_BUY"
            change_notes = (
                f"正式 BUY 觸發（ForwardSignal #{triggered.id}，"
                f"進場日 {triggered.trade_date}）"
            )
            stats["triggered_buy"] += 1

        # ── 技術失效退出 ─────────────────────────────────────────
        elif ar and _is_thesis_failed(ar, rec):
            cand.status = "exited"
            cand.exit_date = check_date
            failed_reason = ar.setup_type or ar.trade_signal or "unknown"
            cand.exit_reason = f"THESIS_FAILED:{failed_reason}"
            change_notes = f"技術型態失效或賣出訊號（{failed_reason}）"
            stats["thesis_failed"] += 1

        # ── 正常更新 ─────────────────────────────────────────────
        else:
            # 計算觀察天數（用 DailyPrice 交易日曆）
            days = _count_trading_days(session, cand.first_seen_date, check_date)
            cand.trading_days_watched = days

            if days >= MAX_WATCH_TRADING_DAYS:
                cand.status = "exited"
                cand.exit_date = check_date
                cand.exit_reason = "EXPIRED"
                change_notes = f"觀察滿 {MAX_WATCH_TRADING_DAYS} 個交易日未觸發 BUY"
                stats["expired"] += 1
            elif ar:
                change_notes = _build_change_notes(cand, ar, rec)
                new_status = _determine_status(ar, rec)
                # watching → overdue（near_entry 不降級）
                if days >= OVERDUE_TRADING_DAYS and new_status == "watching":
                    new_status = "overdue"
                    if old_status != "overdue":
                        change_notes += f"（第 {days} 交易日，標記觀察逾期）"
                        stats["overdue_marked"] += 1
                if new_status != old_status:
                    pass  # change already in change_notes
                cand.status = new_status
                cand.latest_setup_type = ar.setup_type
                cand.latest_total_score = ar.total_score
                cand.latest_trade_signal = ar.trade_signal
                cand.latest_decision_code = rec.decision_code if rec else None
                cand.current_missing_conditions = _get_missing_conditions(ar, rec)
                stats["updated"] += 1
            else:
                # 今日不在分析宇宙，不退出但記錄缺席
                change_notes = "今日未出現於分析宇宙"
                stats["updated"] += 1

        cand.last_checked_date = check_date
        cand.updated_at = datetime.utcnow()

        session.add(CandidatePoolHistory(
            candidate_id=cand.id,
            check_date=check_date,
            status=cand.status,
            setup_type=(ar.setup_type if ar else cand.latest_setup_type),
            total_score=(ar.total_score if ar else cand.latest_total_score),
            decision_code=(rec.decision_code if rec else cand.latest_decision_code),
            trade_signal=(ar.trade_signal if ar else cand.latest_trade_signal),
            missing_conditions=cand.current_missing_conditions,
            change_notes=change_notes,
        ))

    # ── Step 2: 新增今日符合條件的候選 ──────────────────────────
    active_stock_ids = {
        c.stock_id
        for c in session.query(CandidatePool.stock_id)
        .filter(
            CandidatePool.status.in_(["watching", "near_entry", "overdue"]),
            CandidatePool.pool_version == CANDIDATE_POOL_VERSION,
            CandidatePool.model_version == MODEL_VERSION,
        )
        .all()
    }

    for ar in today_ar_map.values():
        if ar.stock_id in active_stock_ids:
            continue
        if ar.stock_id in today_buy_stocks:
            continue  # 今日已是正式 BUY，不另開候選週期
        rec = today_rec_map.get(ar.stock_id)
        if not _is_eligible_new_candidate(ar, rec):
            continue

        # 冪等性：今日已有入池記錄就跳過
        existing = (
            session.query(CandidatePool)
            .filter_by(
                stock_id=ar.stock_id,
                first_seen_date=check_date,
                pool_version=CANDIDATE_POOL_VERSION,
            )
            .first()
        )
        if existing:
            stats["skipped_idempotent"] += 1
            continue

        # 取股票名稱
        stock_name = (rec.stock_name if rec else None) or _resolve_stock_name(
            session, ar.stock_id
        )

        status = _determine_status(ar, rec)
        entry_reason = _get_entry_reason(ar, rec)
        missing = _get_missing_conditions(ar, rec)

        cand = CandidatePool(
            stock_id=ar.stock_id,
            stock_name=stock_name,
            model_version=MODEL_VERSION,
            pool_version=CANDIDATE_POOL_VERSION,
            first_seen_date=check_date,
            last_checked_date=check_date,
            status=status,
            trading_days_watched=1,
            entry_setup_type=ar.setup_type,
            entry_total_score=ar.total_score,
            entry_trade_signal=ar.trade_signal,
            entry_decision_code=(rec.decision_code if rec else None),
            entry_reason=entry_reason,
            latest_setup_type=ar.setup_type,
            latest_total_score=ar.total_score,
            latest_trade_signal=ar.trade_signal,
            latest_decision_code=(rec.decision_code if rec else None),
            current_missing_conditions=missing,
        )
        session.add(cand)
        session.flush()  # 取得 id

        session.add(CandidatePoolHistory(
            candidate_id=cand.id,
            check_date=check_date,
            status=status,
            setup_type=ar.setup_type,
            total_score=ar.total_score,
            decision_code=(rec.decision_code if rec else None),
            trade_signal=ar.trade_signal,
            missing_conditions=missing,
            change_notes="新進候選追蹤池",
        ))
        stats["new_entries"] += 1

    try:
        session.commit()
    except Exception as exc:
        session.rollback()
        raise RuntimeError(f"update_candidate_pool commit failed: {exc}") from exc

    logger.info(
        f"[candidate_pool] {check_date}: "
        f"new={stats['new_entries']} "
        f"buy={stats['triggered_buy']} "
        f"failed={stats['thesis_failed']} "
        f"expired={stats['expired']} "
        f"updated={stats['updated']} "
        f"idempotent_skip={stats['skipped_idempotent']}"
    )
    return stats


def _resolve_stock_name(session, stock_id: str) -> str:
    """從歷史 Recommendation 取得股票名稱，fallback 為 stock_id。"""
    from src.database import Recommendation
    row = (
        session.query(Recommendation.stock_name)
        .filter_by(stock_id=stock_id)
        .order_by(Recommendation.date.desc())
        .first()
    )
    return (row.stock_name if row and row.stock_name else None) or stock_id


# ── 查詢 API ──────────────────────────────────────────────────────────────────


def get_active_candidates(session, pool_version: str = CANDIDATE_POOL_VERSION) -> list:
    """返回所有 active 候選（watching / near_entry / overdue），附今日歷史快照。"""
    from src.database import CandidatePool, CandidatePoolHistory, MODEL_VERSION

    rows = (
        session.query(CandidatePool)
        .filter(
            CandidatePool.status.in_(["watching", "near_entry", "overdue"]),
            CandidatePool.pool_version == pool_version,
            CandidatePool.model_version == MODEL_VERSION,
        )
        .order_by(
            CandidatePool.status,           # near_entry first (alphabetical)
            CandidatePool.first_seen_date,
        )
        .all()
    )
    return rows


def get_recent_exits(session, days: int = 7, pool_version: str = CANDIDATE_POOL_VERSION) -> list:
    """返回最近 N 天退出的候選（triggered_buy 或 exited）。"""
    from datetime import timedelta
    from src.database import CandidatePool, MODEL_VERSION

    since = datetime.utcnow().date() - timedelta(days=days)
    return (
        session.query(CandidatePool)
        .filter(
            CandidatePool.status.in_(["triggered_buy", "exited"]),
            CandidatePool.exit_date.isnot(None),
            CandidatePool.exit_date >= since,
            CandidatePool.pool_version == pool_version,
            CandidatePool.model_version == MODEL_VERSION,
        )
        .order_by(CandidatePool.exit_date.desc())
        .all()
    )


def get_pool_stats(session, pool_version: str = CANDIDATE_POOL_VERSION) -> dict:
    """返回候選池累計統計。樣本不足時標注「資料累積中」。"""
    from src.database import CandidatePool, MODEL_VERSION

    all_rows = (
        session.query(CandidatePool)
        .filter(
            CandidatePool.pool_version == pool_version,
            CandidatePool.model_version == MODEL_VERSION,
        )
        .all()
    )

    n_total = len(all_rows)
    n_active = sum(1 for r in all_rows if r.status in ("watching", "near_entry", "overdue"))
    n_buy = sum(1 for r in all_rows if r.status == "triggered_buy")
    n_exited = sum(1 for r in all_rows if r.status == "exited")

    # 平均等待交易日數（僅計算已觸發 BUY 的）
    buy_days = [r.trading_days_watched for r in all_rows
                if r.status == "triggered_buy" and r.trading_days_watched]
    avg_days = round(sum(buy_days) / len(buy_days), 1) if buy_days else None

    # 轉換率：分母 = 已完成週期（buy + exited），不含仍在觀察的
    completed = n_buy + n_exited
    conversion_rate = round(n_buy / completed * 100, 1) if completed >= 5 else None

    return {
        "n_total": n_total,
        "n_active": n_active,
        "n_buy": n_buy,
        "n_exited": n_exited,
        "avg_wait_days": avg_days,
        "conversion_rate": conversion_rate,
        "sufficient_data": completed >= 5,
    }


def get_today_history(session, candidate_id: int, check_date: date):
    """取得某候選今日歷史快照（顯示「今日變化」用）。"""
    from src.database import CandidatePoolHistory
    return (
        session.query(CandidatePoolHistory)
        .filter_by(candidate_id=candidate_id, check_date=check_date)
        .first()
    )
