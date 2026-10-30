"""
tests/test_candidate_pool.py — 候選追蹤池 regression tests

覆蓋：
1. DB schema：CandidatePool / CandidatePoolHistory 欄位與 UniqueConstraint
2. 入池條件：eligible / not eligible（各種 setup_type / signal 組合）
3. near_entry 判斷：wait_pullback + near_breakout
4. 狀態機：watching → near_entry → overdue → exited / triggered_buy
5. BUY 偵測：ForwardSignal 連結
6. 退出條件：THESIS_FAILED / EXPIRED / TRIGGERED_BUY
7. 冪等性：同日重跑不重複建立記錄
8. 交易日計數
9. 不修改 BUY 門檻（候選池不自行產生 BUY）
10. 統計 API
"""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_engine():
    from sqlalchemy import create_engine
    from src.database import Base, init_db
    engine = create_engine("sqlite:///:memory:")
    init_db(engine)
    return engine


def _make_session(engine=None):
    from src.database import get_session
    if engine is None:
        engine = _make_engine()
    return get_session(engine)


def _make_ar(stock_id="2330", setup_type="near_breakout", trade_signal="wait",
             total_score=62.0, ma20_gap=2.5, volume_ratio=1.2):
    """Minimal AnalysisResult mock."""
    ar = MagicMock()
    ar.stock_id = stock_id
    ar.setup_type = setup_type
    ar.trade_signal = trade_signal
    ar.total_score = total_score
    ar.ma20_gap = ma20_gap
    ar.volume_ratio = volume_ratio
    return ar


def _make_rec(stock_id="2330", decision_code="wait", ma20_gap=2.5,
              entry_low=580.0, entry_high=600.0, vol_ratio=1.2,
              stock_name="台積電"):
    """Minimal Recommendation mock."""
    rec = MagicMock()
    rec.stock_id = stock_id
    rec.decision_code = decision_code
    rec.ma20_gap = ma20_gap
    rec.entry_low = entry_low
    rec.entry_high = entry_high
    rec.vol_ratio = vol_ratio
    rec.stock_name = stock_name
    return rec


# ── 1. DB Schema ──────────────────────────────────────────────────────────────

def test_candidate_pool_table_exists():
    from src.database import CandidatePool
    assert CandidatePool.__tablename__ == "candidate_pool"


def test_candidate_pool_history_table_exists():
    from src.database import CandidatePoolHistory
    assert CandidatePoolHistory.__tablename__ == "candidate_pool_history"


def test_candidate_pool_required_columns():
    from src.database import CandidatePool
    col_names = {c.name for c in CandidatePool.__table__.columns}
    required = {
        "id", "stock_id", "model_version", "pool_version",
        "first_seen_date", "last_checked_date", "status",
        "entry_reason", "entry_setup_type", "entry_total_score",
        "entry_trade_signal", "entry_decision_code",
        "latest_setup_type", "latest_decision_code", "latest_trade_signal",
        "current_missing_conditions", "trading_days_watched",
        "triggered_buy_date", "forward_signal_id",
        "exit_date", "exit_reason",
    }
    missing = required - col_names
    assert not missing, f"Missing columns: {missing}"


def test_candidate_pool_unique_constraint():
    from sqlalchemy import UniqueConstraint
    from src.database import CandidatePool
    ucs = [c for c in CandidatePool.__table_args__ if isinstance(c, UniqueConstraint)]
    assert ucs, "CandidatePool has no UniqueConstraint"
    col_names = {c.name for c in ucs[0].columns}
    assert {"stock_id", "first_seen_date", "pool_version"} == col_names


def test_candidate_pool_history_unique_constraint():
    from sqlalchemy import UniqueConstraint
    from src.database import CandidatePoolHistory
    ucs = [c for c in CandidatePoolHistory.__table_args__ if isinstance(c, UniqueConstraint)]
    assert ucs, "CandidatePoolHistory has no UniqueConstraint"
    col_names = {c.name for c in ucs[0].columns}
    assert {"candidate_id", "check_date"} == col_names


# ── 2. 入池條件 ────────────────────────────────────────────────────────────────

def test_eligible_near_breakout():
    from src.services.candidate_pool_service import _is_eligible_new_candidate
    ar = _make_ar(setup_type="near_breakout", trade_signal="wait", total_score=60.0)
    assert _is_eligible_new_candidate(ar, None) is True


def test_eligible_pullback_buy():
    from src.services.candidate_pool_service import _is_eligible_new_candidate
    ar = _make_ar(setup_type="pullback_buy", trade_signal="buy", total_score=65.0)
    assert _is_eligible_new_candidate(ar, None) is True


def test_eligible_breakout():
    from src.services.candidate_pool_service import _is_eligible_new_candidate
    ar = _make_ar(setup_type="breakout", trade_signal="wait", total_score=58.0)
    assert _is_eligible_new_candidate(ar, None) is True


def test_not_eligible_breakdown():
    from src.services.candidate_pool_service import _is_eligible_new_candidate
    ar = _make_ar(setup_type="breakdown", trade_signal="sell", total_score=70.0)
    assert _is_eligible_new_candidate(ar, None) is False


def test_not_eligible_sell_signal():
    from src.services.candidate_pool_service import _is_eligible_new_candidate
    ar = _make_ar(setup_type="near_breakout", trade_signal="sell", total_score=70.0)
    assert _is_eligible_new_candidate(ar, None) is False


def test_not_eligible_reduce_signal():
    from src.services.candidate_pool_service import _is_eligible_new_candidate
    ar = _make_ar(setup_type="trending", trade_signal="reduce", total_score=70.0)
    assert _is_eligible_new_candidate(ar, None) is False


def test_not_eligible_low_score():
    from src.services.candidate_pool_service import _is_eligible_new_candidate
    ar = _make_ar(setup_type="near_breakout", trade_signal="wait", total_score=50.0)
    assert _is_eligible_new_candidate(ar, None) is False


def test_not_eligible_none_setup():
    from src.services.candidate_pool_service import _is_eligible_new_candidate
    ar = _make_ar(setup_type="none", trade_signal="wait", total_score=70.0)
    assert _is_eligible_new_candidate(ar, None) is False


def test_not_eligible_failed_breakout():
    from src.services.candidate_pool_service import _is_eligible_new_candidate
    ar = _make_ar(setup_type="failed_breakout", trade_signal="wait", total_score=70.0)
    assert _is_eligible_new_candidate(ar, None) is False


def test_not_eligible_rec_sell_decision():
    from src.services.candidate_pool_service import _is_eligible_new_candidate
    ar = _make_ar(setup_type="near_breakout", trade_signal="wait", total_score=62.0)
    rec = _make_rec(decision_code="sell")
    assert _is_eligible_new_candidate(ar, rec) is False


# ── 3. near_entry 判斷 ─────────────────────────────────────────────────────────

def test_near_entry_wait_pullback():
    from src.services.candidate_pool_service import _determine_status
    ar = _make_ar(setup_type="breakout", trade_signal="buy")
    rec = _make_rec(decision_code="wait_pullback")
    assert _determine_status(ar, rec) == "near_entry"


def test_near_entry_setup_near_breakout():
    from src.services.candidate_pool_service import _determine_status
    ar = _make_ar(setup_type="near_breakout", trade_signal="wait")
    rec = _make_rec(decision_code="wait")
    assert _determine_status(ar, rec) == "near_entry"


def test_watching_pullback_buy():
    from src.services.candidate_pool_service import _determine_status
    ar = _make_ar(setup_type="pullback_buy", trade_signal="wait")
    rec = _make_rec(decision_code="wait")
    assert _determine_status(ar, rec) == "watching"


def test_watching_trending():
    from src.services.candidate_pool_service import _determine_status
    ar = _make_ar(setup_type="trending", trade_signal="wait")
    assert _determine_status(ar, None) == "watching"


def test_near_entry_without_rec():
    """near_breakout setup triggers near_entry even without Recommendation row."""
    from src.services.candidate_pool_service import _determine_status
    ar = _make_ar(setup_type="near_breakout")
    assert _determine_status(ar, None) == "near_entry"


# ── 4. 入池 + 歷史快照寫入（DB integration）─────────────────────────────────────

def _seed_analysis_result(session, stock_id, check_date, setup_type="near_breakout",
                          trade_signal="wait", total_score=62.0, ma20_gap=2.5):
    from src.database import AnalysisResult
    ar = AnalysisResult(
        stock_id=stock_id, date=check_date,
        setup_type=setup_type, trade_signal=trade_signal,
        total_score=total_score, ma20_gap=ma20_gap,
        timing_score=60.0, behavior_score=55.0, quality_score=50.0,
        risk_score=80.0, confidence=70.0, rec_level="B",
    )
    session.add(ar)
    session.commit()
    return ar


def _seed_0050_prices(session, dates: list):
    """插入 0050 DailyPrice 供 trading day 計算使用。"""
    from src.database import DailyPrice
    for d in dates:
        session.add(DailyPrice(stock_id="0050", date=d, close=190.0, open=189.0,
                               high=191.0, low=188.0, volume=1_000_000))
    session.commit()


def test_new_candidate_created():
    engine = _make_engine()
    s = _make_session(engine)
    check_date = date(2026, 11, 1)
    _seed_analysis_result(s, "2330", check_date)

    from src.services.candidate_pool_service import update_candidate_pool
    stats = update_candidate_pool(s, check_date)

    assert stats["new_entries"] == 1
    assert stats["triggered_buy"] == 0

    from src.database import CandidatePool
    cand = s.query(CandidatePool).filter_by(stock_id="2330").first()
    assert cand is not None
    assert cand.status == "near_entry"
    assert cand.first_seen_date == check_date
    assert cand.entry_setup_type == "near_breakout"
    s.close()


def test_history_row_created_on_entry():
    engine = _make_engine()
    s = _make_session(engine)
    check_date = date(2026, 11, 1)
    _seed_analysis_result(s, "2330", check_date)

    from src.services.candidate_pool_service import update_candidate_pool
    update_candidate_pool(s, check_date)

    from src.database import CandidatePool, CandidatePoolHistory
    cand = s.query(CandidatePool).filter_by(stock_id="2330").first()
    hist = s.query(CandidatePoolHistory).filter_by(
        candidate_id=cand.id, check_date=check_date
    ).first()
    assert hist is not None
    assert hist.change_notes == "新進候選追蹤池"
    s.close()


# ── 5. 冪等性 ─────────────────────────────────────────────────────────────────

def test_idempotent_rerun_same_day():
    engine = _make_engine()
    s = _make_session(engine)
    check_date = date(2026, 11, 1)
    _seed_analysis_result(s, "2330", check_date)

    from src.services.candidate_pool_service import update_candidate_pool
    stats1 = update_candidate_pool(s, check_date)
    stats2 = update_candidate_pool(s, check_date)

    assert stats1["new_entries"] == 1
    assert stats2["new_entries"] == 0
    assert stats2["skipped_idempotent"] >= 1

    from src.database import CandidatePool, CandidatePoolHistory
    count_cands = s.query(CandidatePool).filter_by(stock_id="2330").count()
    assert count_cands == 1
    count_hist = (
        s.query(CandidatePoolHistory)
        .join(CandidatePool, CandidatePoolHistory.candidate_id == CandidatePool.id)
        .filter(CandidatePool.stock_id == "2330", CandidatePoolHistory.check_date == check_date)
        .count()
    )
    assert count_hist == 1  # 冪等，第二次不新增
    s.close()


# ── 6. THESIS_FAILED 退出 ─────────────────────────────────────────────────────

def test_thesis_failed_breakdown():
    from src.services.candidate_pool_service import _is_thesis_failed
    ar = _make_ar(setup_type="breakdown", trade_signal="sell")
    assert _is_thesis_failed(ar, None) is True


def test_thesis_failed_failed_breakout():
    from src.services.candidate_pool_service import _is_thesis_failed
    ar = _make_ar(setup_type="failed_breakout", trade_signal="wait")
    assert _is_thesis_failed(ar, None) is True


def test_thesis_not_failed_watching():
    from src.services.candidate_pool_service import _is_thesis_failed
    ar = _make_ar(setup_type="near_breakout", trade_signal="wait")
    assert _is_thesis_failed(ar, None) is False


def test_thesis_failed_exits_candidate():
    engine = _make_engine()
    s = _make_session(engine)
    d1 = date(2026, 11, 1)
    d2 = date(2026, 11, 2)
    _seed_analysis_result(s, "2330", d1)
    _seed_0050_prices(s, [d1, d2])

    from src.services.candidate_pool_service import update_candidate_pool
    update_candidate_pool(s, d1)

    # Day 2: thesis fails
    _seed_analysis_result(s, "2330", d2, setup_type="breakdown", trade_signal="sell")
    update_candidate_pool(s, d2)

    from src.database import CandidatePool
    cand = s.query(CandidatePool).filter_by(stock_id="2330").first()
    assert cand.status == "exited"
    assert "THESIS_FAILED" in (cand.exit_reason or "")
    assert cand.exit_date == d2
    s.close()


# ── 7. EXPIRED 退出 ───────────────────────────────────────────────────────────

def test_expired_after_max_trading_days():
    from src.services.candidate_pool_service import MAX_WATCH_TRADING_DAYS
    engine = _make_engine()
    s = _make_session(engine)

    d0 = date(2026, 11, 1)
    # 建立 MAX_WATCH_TRADING_DAYS + 1 個交易日
    trading_days = [d0 + timedelta(days=i) for i in range(MAX_WATCH_TRADING_DAYS + 2)]
    _seed_0050_prices(s, trading_days)
    _seed_analysis_result(s, "2330", trading_days[0])  # 入池日

    from src.services.candidate_pool_service import update_candidate_pool
    update_candidate_pool(s, trading_days[0])

    # 模擬多天後（超過 MAX_WATCH_TRADING_DAYS）
    check_day = trading_days[MAX_WATCH_TRADING_DAYS]
    _seed_analysis_result(s, "2330", check_day, setup_type="near_breakout")
    update_candidate_pool(s, check_day)

    from src.database import CandidatePool
    cand = s.query(CandidatePool).filter_by(stock_id="2330").first()
    assert cand.status == "exited"
    assert cand.exit_reason == "EXPIRED"
    s.close()


# ── 8. TRIGGERED_BUY 偵測 ────────────────────────────────────────────────────

def test_triggered_buy_from_forward_signal():
    engine = _make_engine()
    s = _make_session(engine)
    d1 = date(2026, 11, 1)
    d2 = date(2026, 11, 2)
    _seed_analysis_result(s, "2330", d1)
    _seed_0050_prices(s, [d1, d2])

    from src.services.candidate_pool_service import update_candidate_pool
    update_candidate_pool(s, d1)

    # 寫入 ForwardSignal BUY
    from src.database import ForwardSignal, MODEL_VERSION
    fs = ForwardSignal(
        trade_date=d2, stock_id="2330", model_version=MODEL_VERSION,
        trade_signal="buy", execution_price_type="NEXT_OPEN",
    )
    s.add(fs)
    s.commit()

    _seed_analysis_result(s, "2330", d2, setup_type="breakout", trade_signal="buy")
    update_candidate_pool(s, d2)

    from src.database import CandidatePool
    cand = s.query(CandidatePool).filter_by(stock_id="2330").first()
    assert cand.status == "triggered_buy"
    assert cand.triggered_buy_date == d2
    assert cand.forward_signal_id == fs.id
    assert cand.exit_reason == "TRIGGERED_BUY"
    s.close()


def test_no_new_candidate_if_already_buy_today():
    """ForwardSignal BUY 存在於今日 → 不建立新候選。"""
    engine = _make_engine()
    s = _make_session(engine)
    check_date = date(2026, 11, 1)

    from src.database import ForwardSignal, MODEL_VERSION
    fs = ForwardSignal(
        trade_date=check_date, stock_id="2330", model_version=MODEL_VERSION,
        trade_signal="buy", execution_price_type="NEXT_OPEN",
    )
    s.add(fs)
    s.commit()

    _seed_analysis_result(s, "2330", check_date, setup_type="breakout", trade_signal="buy",
                          total_score=70.0)

    from src.services.candidate_pool_service import update_candidate_pool
    stats = update_candidate_pool(s, check_date)
    assert stats["new_entries"] == 0, "已有 ForwardSignal BUY 的股票不應再進入候選池"
    s.close()


# ── 9. 候選池不自行產生 BUY ───────────────────────────────────────────────────

def test_candidate_pool_does_not_create_forward_signal():
    """update_candidate_pool 不得建立 ForwardSignal。"""
    engine = _make_engine()
    s = _make_session(engine)
    check_date = date(2026, 11, 1)
    _seed_analysis_result(s, "2330", check_date, setup_type="breakout", total_score=80.0)

    from src.services.candidate_pool_service import update_candidate_pool
    update_candidate_pool(s, check_date)

    from src.database import ForwardSignal
    count = s.query(ForwardSignal).count()
    assert count == 0, "candidate_pool_service must NOT create ForwardSignal rows"
    s.close()


# ── 10. overdue 狀態（near_entry 免疫）────────────────────────────────────────

def test_overdue_threshold():
    from src.services.candidate_pool_service import OVERDUE_TRADING_DAYS
    assert OVERDUE_TRADING_DAYS == 10


def test_near_entry_not_downgraded_to_overdue():
    """near_entry 狀態即使超過 OVERDUE_TRADING_DAYS 也不降為 overdue。"""
    from src.services.candidate_pool_service import OVERDUE_TRADING_DAYS
    engine = _make_engine()
    s = _make_session(engine)

    d0 = date(2026, 11, 1)
    trading_days = [d0 + timedelta(days=i) for i in range(OVERDUE_TRADING_DAYS + 3)]
    _seed_0050_prices(s, trading_days)
    _seed_analysis_result(s, "2330", trading_days[0], setup_type="near_breakout")

    from src.services.candidate_pool_service import update_candidate_pool
    update_candidate_pool(s, trading_days[0])

    # 在 OVERDUE 門檻後，仍維持 near_breakout → near_entry
    check_day = trading_days[OVERDUE_TRADING_DAYS + 1]
    _seed_analysis_result(s, "2330", check_day, setup_type="near_breakout")
    update_candidate_pool(s, check_day)

    from src.database import CandidatePool
    cand = s.query(CandidatePool).filter_by(stock_id="2330").first()
    assert cand.status == "near_entry", (
        "near_entry 狀態不應被降為 overdue"
    )
    s.close()


# ── 11. re-entry（舊週期退出後可建立新週期）─────────────────────────────────────

def test_re_entry_creates_new_record():
    """退出後重新符合條件 → 建立新紀錄，不覆寫舊紀錄。"""
    engine = _make_engine()
    s = _make_session(engine)
    d1 = date(2026, 11, 1)
    d2 = date(2026, 11, 4)  # different date → passes UniqueConstraint
    _seed_0050_prices(s, [d1, date(2026, 11, 2), date(2026, 11, 3), d2])

    # 第一個週期：入池、失效
    _seed_analysis_result(s, "2330", d1)
    from src.services.candidate_pool_service import update_candidate_pool
    update_candidate_pool(s, d1)

    _seed_analysis_result(s, "2330", d2, setup_type="breakdown", trade_signal="sell", total_score=70.0)
    update_candidate_pool(s, d2)

    # 第二個週期：重新符合條件（同一天新記錄，UniqueConstraint 是 (stock_id, first_seen_date, version)）
    d3 = date(2026, 11, 5)
    _seed_0050_prices(s, [d3])
    _seed_analysis_result(s, "2330", d3, setup_type="near_breakout", total_score=65.0)
    stats = update_candidate_pool(s, d3)
    assert stats["new_entries"] == 1, "退出後符合條件應建立新候選週期"

    from src.database import CandidatePool
    count = s.query(CandidatePool).filter_by(stock_id="2330").count()
    assert count == 2, "應有兩個不同候選週期"
    s.close()


# ── 12. 統計 API ──────────────────────────────────────────────────────────────

def test_get_pool_stats_empty():
    engine = _make_engine()
    s = _make_session(engine)
    from src.services.candidate_pool_service import get_pool_stats
    stats = get_pool_stats(s)
    assert stats["n_total"] == 0
    assert stats["sufficient_data"] is False
    s.close()


def test_get_pool_stats_with_data():
    engine = _make_engine()
    s = _make_session(engine)
    check_date = date(2026, 11, 1)
    _seed_analysis_result(s, "2330", check_date)
    _seed_analysis_result(s, "2454", check_date, setup_type="trending", total_score=60.0)

    from src.services.candidate_pool_service import update_candidate_pool, get_pool_stats
    update_candidate_pool(s, check_date)
    stats = get_pool_stats(s)

    assert stats["n_total"] == 2
    assert stats["n_active"] == 2
    assert stats["n_buy"] == 0
    s.close()


# ── 13. missing conditions 使用現有 decision 邏輯 ──────────────────────────────

def test_missing_conditions_wait_pullback_uses_ma20_gap():
    from src.services.candidate_pool_service import _get_missing_conditions
    ar = _make_ar(setup_type="breakout", ma20_gap=12.5)
    rec = _make_rec(decision_code="wait_pullback", ma20_gap=12.5,
                    entry_low=550.0, entry_high=570.0)
    result = _get_missing_conditions(ar, rec)
    assert "MA20" in result or "ma20" in result.lower() or "偏離" in result
    assert "550" in result or "進場" in result


def test_missing_conditions_near_breakout():
    from src.services.candidate_pool_service import _get_missing_conditions
    ar = _make_ar(setup_type="near_breakout", trade_signal="wait")
    rec = _make_rec(decision_code="wait")
    result = _get_missing_conditions(ar, rec)
    assert result  # must not be empty


def test_entry_reason_not_empty():
    from src.services.candidate_pool_service import _get_entry_reason
    ar = _make_ar(setup_type="near_breakout", trade_signal="wait")
    rec = _make_rec(decision_code="wait")
    result = _get_entry_reason(ar, rec)
    assert result and len(result) > 5


# ── 14. 版本常數 ──────────────────────────────────────────────────────────────

def test_candidate_pool_version_constant():
    from src.services.candidate_pool_service import CANDIDATE_POOL_VERSION
    assert CANDIDATE_POOL_VERSION == "v1.0"


def test_max_trading_days_constant():
    from src.services.candidate_pool_service import MAX_WATCH_TRADING_DAYS
    assert MAX_WATCH_TRADING_DAYS == 20


def test_overdue_is_less_than_max():
    from src.services.candidate_pool_service import OVERDUE_TRADING_DAYS, MAX_WATCH_TRADING_DAYS
    assert OVERDUE_TRADING_DAYS < MAX_WATCH_TRADING_DAYS
