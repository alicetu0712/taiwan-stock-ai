"""
tests/test_trade_service.py — TradeService Phase 1A regression tests

覆蓋：
1.  create_position: AI_SIGNAL / MANUAL / 驗證錯誤
2.  add_execution: BUY/SELL 基本路徑、含手續費
3.  MWAC: 兩次 BUY 後的加權均價
4.  SELL 部分出場 (partially_closed) / 全數出場 (closed)
5.  超賣保護（SELL > remaining）
6.  重複提交防護（60s 視窗）
7.  cancel_execution: 軟刪除 + 重新彙總
8.  取消 BUY 後 SELL 變超賣 → 拋 TradeSvcError
9.  update_plan: 稽核記錄
10. get_active_positions: 只回傳 open / partially_closed
11. get_executions: include_cancelled flag
12. ACTUAL / PAPER 隔離（PositionMonitor 不可出現在 get_active_positions）
"""

from datetime import date
from decimal import Decimal

import pytest

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_engine():
    from sqlalchemy import create_engine

    from src.database import init_db

    engine = create_engine("sqlite:///:memory:")
    init_db(engine)
    return engine


def _make_session(engine=None):
    from src.database import get_session

    if engine is None:
        engine = _make_engine()
    return get_session(engine)


def _make_forward_signal(session, stock_id="2330", is_valid=True):
    """在 DB 建立一筆最小可用的 ForwardSignal。"""
    from src.database import ForwardSignal

    fs = ForwardSignal(
        trade_date=date(2026, 10, 30),
        stock_id=stock_id,
        stock_name="台積電",
        total_score=72.0,
        rec_level="A",
        confidence=68.0,
        entry_low=900.0,
        entry_high=920.0,
        stop_price=860.0,
        target1=980.0,
        target2=1050.0,
        decision_label="buy",
        is_valid=is_valid,
    )
    session.add(fs)
    session.flush()
    return fs


def _d(v) -> Decimal:
    return Decimal(str(v))


# ── create_position ───────────────────────────────────────────────────────────


class TestCreatePosition:
    def test_manual_happy_path(self):
        import src.services.trade_service as svc

        session = _make_session()
        pos = svc.create_position(
            session,
            stock_id="2330",
            stock_name="台積電",
            signal_source="MANUAL",
            open_date=date(2026, 10, 30),
        )
        assert pos.id is not None
        assert pos.stock_id == "2330"
        assert pos.signal_source == "MANUAL"
        assert pos.position_type == "ACTUAL"
        assert pos.status == "open"
        assert pos.remaining_shares == 0
        assert pos.forward_signal_id is None
        assert pos.original_plan_snapshot is None
        session.rollback()

    def test_ai_signal_happy_path(self):
        import src.services.trade_service as svc

        session = _make_session()
        fs = _make_forward_signal(session)
        pos = svc.create_position(
            session,
            stock_id="2330",
            stock_name="台積電",
            signal_source="AI_SIGNAL",
            open_date=date(2026, 10, 30),
            forward_signal_id=fs.id,
        )
        assert pos.forward_signal_id == fs.id
        assert pos.original_plan_snapshot is not None
        import json

        snap = json.loads(pos.original_plan_snapshot)
        assert snap["decision_label"] == "buy"
        assert snap["rec_level"] == "A"
        session.rollback()

    def test_manual_forward_signal_id_ignored(self):
        """MANUAL + forward_signal_id 被靜默忽略（設為 None）。"""
        import src.services.trade_service as svc

        session = _make_session()
        pos = svc.create_position(
            session,
            stock_id="2330",
            stock_name="台積電",
            signal_source="MANUAL",
            open_date=date(2026, 10, 30),
            forward_signal_id=99999,
        )
        assert pos.forward_signal_id is None
        session.rollback()

    def test_invalid_signal_source(self):
        import src.services.trade_service as svc

        session = _make_session()
        with pytest.raises(svc.TradeSvcError, match="signal_source"):
            svc.create_position(
                session, "2330", "台積電", "UNKNOWN", date(2026, 10, 30)
            )
        session.rollback()

    def test_ai_signal_missing_forward_signal_id(self):
        import src.services.trade_service as svc

        session = _make_session()
        with pytest.raises(svc.TradeSvcError, match="forward_signal_id 必填"):
            svc.create_position(
                session, "2330", "台積電", "AI_SIGNAL", date(2026, 10, 30)
            )
        session.rollback()

    def test_ai_signal_nonexistent_forward_signal_id(self):
        import src.services.trade_service as svc

        session = _make_session()
        with pytest.raises(svc.TradeSvcError, match="不存在"):
            svc.create_position(
                session,
                "2330",
                "台積電",
                "AI_SIGNAL",
                date(2026, 10, 30),
                forward_signal_id=99999,
            )
        session.rollback()

    def test_ai_signal_invalid_forward_signal(self):
        import src.services.trade_service as svc

        session = _make_session()
        fs = _make_forward_signal(session, is_valid=False)
        with pytest.raises(svc.TradeSvcError, match="is_valid=False"):
            svc.create_position(
                session,
                "2330",
                "台積電",
                "AI_SIGNAL",
                date(2026, 10, 30),
                forward_signal_id=fs.id,
            )
        session.rollback()


# ── add_execution (BUY) ────────────────────────────────────────────────────────


class TestAddExecutionBuy:
    def _pos(self, session):
        import src.services.trade_service as svc

        return svc.create_position(
            session, "2330", "台積電", "MANUAL", date(2026, 10, 30)
        )

    def test_buy_updates_position(self):
        import src.services.trade_service as svc

        session = _make_session()
        pos = self._pos(session)
        svc.add_execution(
            session,
            pos.id,
            "BUY",
            date(2026, 10, 31),
            execution_price=_d("100.00"),
            shares=1000,
            actual_fee=_d("0"),
            transaction_tax=_d("0"),
        )
        assert pos.remaining_shares == 1000
        assert pos.avg_cost_per_share == _d("100.0000")
        assert pos.total_cost_basis == _d("100000.00")
        assert pos.status == "open"
        session.rollback()

    def test_buy_with_fee_included_in_cost_basis(self):
        import src.services.trade_service as svc

        session = _make_session()
        pos = self._pos(session)
        svc.add_execution(
            session,
            pos.id,
            "BUY",
            date(2026, 10, 31),
            execution_price=_d("100.00"),
            shares=1000,
            actual_fee=_d("143.00"),
            transaction_tax=_d("0"),
        )
        # avg = (100000 + 143) / 1000 = 100.143
        assert pos.total_cost_basis == _d("100143.00")
        assert pos.avg_cost_per_share == _d("100.1430")
        session.rollback()

    def test_mwac_two_buys(self):
        """兩次 BUY 的加權均價計算。"""
        import src.services.trade_service as svc

        session = _make_session()
        pos = self._pos(session)
        # BUY 1000 @ 100 → cost=100000, avg=100
        svc.add_execution(
            session,
            pos.id,
            "BUY",
            date(2026, 10, 31),
            execution_price=_d("100"),
            shares=1000,
            actual_fee=_d("0"),
            transaction_tax=_d("0"),
        )
        # BUY 1000 @ 120 → total cost=220000, avg=110
        svc.add_execution(
            session,
            pos.id,
            "BUY",
            date(2026, 11, 1),
            execution_price=_d("120"),
            shares=1000,
            actual_fee=_d("0"),
            transaction_tax=_d("0"),
        )
        assert pos.remaining_shares == 2000
        assert pos.avg_cost_per_share == _d("110.0000")
        assert pos.total_cost_basis == _d("220000.00")
        session.rollback()

    def test_add_buy_to_nonexistent_position(self):
        import src.services.trade_service as svc

        session = _make_session()
        with pytest.raises(svc.TradeSvcError, match="不存在"):
            svc.add_execution(
                session,
                99999,
                "BUY",
                date(2026, 10, 31),
                execution_price=_d("100"),
                shares=1000,
                actual_fee=_d("0"),
                transaction_tax=_d("0"),
            )
        session.rollback()

    def test_invalid_side(self):
        import src.services.trade_service as svc

        session = _make_session()
        pos = self._pos(session)
        with pytest.raises(svc.TradeSvcError, match="BUY 或 SELL"):
            svc.add_execution(
                session,
                pos.id,
                "SHORT",
                date(2026, 10, 31),
                execution_price=_d("100"),
                shares=1000,
                actual_fee=_d("0"),
                transaction_tax=_d("0"),
            )
        session.rollback()

    def test_zero_shares_rejected(self):
        import src.services.trade_service as svc

        session = _make_session()
        pos = self._pos(session)
        with pytest.raises(svc.TradeSvcError, match="shares"):
            svc.add_execution(
                session,
                pos.id,
                "BUY",
                date(2026, 10, 31),
                execution_price=_d("100"),
                shares=0,
                actual_fee=_d("0"),
                transaction_tax=_d("0"),
            )
        session.rollback()

    def test_zero_price_rejected(self):
        import src.services.trade_service as svc

        session = _make_session()
        pos = self._pos(session)
        with pytest.raises(svc.TradeSvcError, match="execution_price"):
            svc.add_execution(
                session,
                pos.id,
                "BUY",
                date(2026, 10, 31),
                execution_price=_d("0"),
                shares=1000,
                actual_fee=_d("0"),
                transaction_tax=_d("0"),
            )
        session.rollback()


# ── add_execution (SELL) ───────────────────────────────────────────────────────


class TestAddExecutionSell:
    def _open_pos_with_2000_shares(self, session):
        """BUY 2000 股 @ 100，回傳 pos。"""
        import src.services.trade_service as svc

        pos = svc.create_position(
            session, "2330", "台積電", "MANUAL", date(2026, 10, 30)
        )
        svc.add_execution(
            session,
            pos.id,
            "BUY",
            date(2026, 10, 31),
            execution_price=_d("100"),
            shares=2000,
            actual_fee=_d("0"),
            transaction_tax=_d("0"),
        )
        return pos

    def test_partial_sell_status(self):
        import src.services.trade_service as svc

        session = _make_session()
        pos = self._open_pos_with_2000_shares(session)
        svc.add_execution(
            session,
            pos.id,
            "SELL",
            date(2026, 11, 1),
            execution_price=_d("120"),
            shares=1000,
            actual_fee=_d("0"),
            transaction_tax=_d("0"),
        )
        assert pos.status == "partially_closed"
        assert pos.remaining_shares == 1000
        # realized = (120×1000 - 0 - 0) - 100×1000 = 20000
        assert pos.realized_pnl == _d("20000.00")
        assert pos.close_date is None
        session.rollback()

    def test_full_sell_closes_position(self):
        import src.services.trade_service as svc

        session = _make_session()
        pos = self._open_pos_with_2000_shares(session)
        svc.add_execution(
            session,
            pos.id,
            "SELL",
            date(2026, 11, 1),
            execution_price=_d("120"),
            shares=2000,
            actual_fee=_d("0"),
            transaction_tax=_d("0"),
        )
        assert pos.status == "closed"
        assert pos.remaining_shares == 0
        assert pos.close_date == date(2026, 11, 1)
        assert pos.realized_pnl == _d("40000.00")
        session.rollback()

    def test_sell_with_fee_and_tax(self):
        """SELL 側手續費與交易稅正確扣除。"""
        import src.services.trade_service as svc

        session = _make_session()
        pos = self._open_pos_with_2000_shares(session)
        # SELL 1000 @ 120, fee=86, tax=360
        # gross proceeds = 120000 - 86 - 360 = 119554
        # cost_of_sold = 100 * 1000 = 100000
        # realized = 119554 - 100000 = 19554
        svc.add_execution(
            session,
            pos.id,
            "SELL",
            date(2026, 11, 1),
            execution_price=_d("120"),
            shares=1000,
            actual_fee=_d("86"),
            transaction_tax=_d("360"),
        )
        assert pos.realized_pnl == _d("19554.00")
        session.rollback()

    def test_oversell_rejected(self):
        import src.services.trade_service as svc

        session = _make_session()
        pos = self._open_pos_with_2000_shares(session)
        with pytest.raises(svc.TradeSvcError, match="超過剩餘持倉"):
            svc.add_execution(
                session,
                pos.id,
                "SELL",
                date(2026, 11, 1),
                execution_price=_d("120"),
                shares=3000,
                actual_fee=_d("0"),
                transaction_tax=_d("0"),
            )
        session.rollback()

    def test_sell_on_closed_position_rejected(self):
        import src.services.trade_service as svc

        session = _make_session()
        pos = self._open_pos_with_2000_shares(session)
        svc.add_execution(
            session,
            pos.id,
            "SELL",
            date(2026, 11, 1),
            execution_price=_d("120"),
            shares=2000,
            actual_fee=_d("0"),
            transaction_tax=_d("0"),
        )
        assert pos.status == "closed"
        with pytest.raises(svc.TradeSvcError, match="已完全出場"):
            svc.add_execution(
                session,
                pos.id,
                "SELL",
                date(2026, 11, 2),
                execution_price=_d("120"),
                shares=1000,
                actual_fee=_d("0"),
                transaction_tax=_d("0"),
            )
        session.rollback()


# ── 重複提交防護 ───────────────────────────────────────────────────────────────


class TestDuplicateProtection:
    def test_duplicate_buy_within_window(self):
        """相同參數連續提交兩次，第二次應拒絕。"""
        import src.services.trade_service as svc

        session = _make_session()
        pos = svc.create_position(
            session, "2330", "台積電", "MANUAL", date(2026, 10, 30)
        )
        svc.add_execution(
            session,
            pos.id,
            "BUY",
            date(2026, 10, 31),
            execution_price=_d("100"),
            shares=1000,
            actual_fee=_d("0"),
            transaction_tax=_d("0"),
        )
        with pytest.raises(svc.TradeSvcError, match="重複提交"):
            svc.add_execution(
                session,
                pos.id,
                "BUY",
                date(2026, 10, 31),
                execution_price=_d("100"),
                shares=1000,
                actual_fee=_d("0"),
                transaction_tax=_d("0"),
            )
        session.rollback()

    def test_different_price_not_duplicate(self):
        """價格不同 → 不觸發重複防護。"""
        import src.services.trade_service as svc

        session = _make_session()
        pos = svc.create_position(
            session, "2330", "台積電", "MANUAL", date(2026, 10, 30)
        )
        svc.add_execution(
            session,
            pos.id,
            "BUY",
            date(2026, 10, 31),
            execution_price=_d("100"),
            shares=1000,
            actual_fee=_d("0"),
            transaction_tax=_d("0"),
        )
        # 不同價格，不應觸發重複防護
        exec2 = svc.add_execution(
            session,
            pos.id,
            "BUY",
            date(2026, 10, 31),
            execution_price=_d("101"),
            shares=1000,
            actual_fee=_d("0"),
            transaction_tax=_d("0"),
        )
        assert exec2.id is not None
        session.rollback()

    def test_cancelled_exec_does_not_trigger_duplicate(self):
        """取消後的成交不影響重複偵測。"""
        import src.services.trade_service as svc

        session = _make_session()
        pos = svc.create_position(
            session, "2330", "台積電", "MANUAL", date(2026, 10, 30)
        )
        exec1 = svc.add_execution(
            session,
            pos.id,
            "BUY",
            date(2026, 10, 31),
            execution_price=_d("100"),
            shares=1000,
            actual_fee=_d("0"),
            transaction_tax=_d("0"),
        )
        svc.cancel_execution(session, exec1.id, "test cancel")
        # 取消後相同參數應可重新提交
        exec2 = svc.add_execution(
            session,
            pos.id,
            "BUY",
            date(2026, 10, 31),
            execution_price=_d("100"),
            shares=1000,
            actual_fee=_d("0"),
            transaction_tax=_d("0"),
        )
        assert exec2.id is not None
        session.rollback()


# ── cancel_execution ───────────────────────────────────────────────────────────


class TestCancelExecution:
    def test_cancel_buy_resets_position(self):
        import src.services.trade_service as svc

        session = _make_session()
        pos = svc.create_position(
            session, "2330", "台積電", "MANUAL", date(2026, 10, 30)
        )
        exec1 = svc.add_execution(
            session,
            pos.id,
            "BUY",
            date(2026, 10, 31),
            execution_price=_d("100"),
            shares=1000,
            actual_fee=_d("0"),
            transaction_tax=_d("0"),
        )
        assert pos.remaining_shares == 1000

        svc.cancel_execution(session, exec1.id, "輸入錯誤")

        assert exec1.is_cancelled is True
        assert exec1.cancel_reason == "輸入錯誤"
        assert pos.remaining_shares == 0
        assert pos.status == "open"
        session.rollback()

    def test_cancel_sell_restores_remaining(self):
        import src.services.trade_service as svc

        session = _make_session()
        pos = svc.create_position(
            session, "2330", "台積電", "MANUAL", date(2026, 10, 30)
        )
        svc.add_execution(
            session,
            pos.id,
            "BUY",
            date(2026, 10, 31),
            execution_price=_d("100"),
            shares=2000,
            actual_fee=_d("0"),
            transaction_tax=_d("0"),
        )
        exec_sell = svc.add_execution(
            session,
            pos.id,
            "SELL",
            date(2026, 11, 1),
            execution_price=_d("120"),
            shares=1000,
            actual_fee=_d("0"),
            transaction_tax=_d("0"),
        )
        assert pos.status == "partially_closed"
        svc.cancel_execution(session, exec_sell.id, "誤按賣出")
        assert pos.status == "open"
        assert pos.remaining_shares == 2000
        assert pos.realized_pnl == _d("0.00")
        session.rollback()

    def test_cancel_buy_that_would_cause_oversell(self):
        """取消 BUY 後若 SELL > 累計 BUY，_recalculate_position 應拋 TradeSvcError。"""
        import src.services.trade_service as svc

        session = _make_session()
        pos = svc.create_position(
            session, "2330", "台積電", "MANUAL", date(2026, 10, 30)
        )
        exec_buy = svc.add_execution(
            session,
            pos.id,
            "BUY",
            date(2026, 10, 31),
            execution_price=_d("100"),
            shares=2000,
            actual_fee=_d("0"),
            transaction_tax=_d("0"),
        )
        svc.add_execution(
            session,
            pos.id,
            "SELL",
            date(2026, 11, 1),
            execution_price=_d("120"),
            shares=2000,
            actual_fee=_d("0"),
            transaction_tax=_d("0"),
        )
        assert pos.status == "closed"
        with pytest.raises(svc.TradeSvcError):
            svc.cancel_execution(session, exec_buy.id, "test")
        session.rollback()

    def test_double_cancel_rejected(self):
        import src.services.trade_service as svc

        session = _make_session()
        pos = svc.create_position(
            session, "2330", "台積電", "MANUAL", date(2026, 10, 30)
        )
        exec1 = svc.add_execution(
            session,
            pos.id,
            "BUY",
            date(2026, 10, 31),
            execution_price=_d("100"),
            shares=1000,
            actual_fee=_d("0"),
            transaction_tax=_d("0"),
        )
        svc.cancel_execution(session, exec1.id, "reason")
        with pytest.raises(svc.TradeSvcError, match="已取消"):
            svc.cancel_execution(session, exec1.id, "again")
        session.rollback()

    def test_cancel_nonexistent_rejected(self):
        import src.services.trade_service as svc

        session = _make_session()
        with pytest.raises(svc.TradeSvcError, match="不存在"):
            svc.cancel_execution(session, 99999, "reason")
        session.rollback()


# ── update_plan ────────────────────────────────────────────────────────────────


class TestUpdatePlan:
    def _pos(self, session):
        import src.services.trade_service as svc

        return svc.create_position(
            session,
            "2330",
            "台積電",
            "MANUAL",
            date(2026, 10, 30),
            target_price=_d("980"),
            stop_price=_d("860"),
        )

    def test_update_target_price_creates_audit(self):
        import src.services.trade_service as svc
        from src.database import PositionPlanChange

        session = _make_session()
        pos = self._pos(session)
        change = svc.update_plan(
            session, pos.id, "target_price", _d("1000"), "突破新高調整"
        )
        assert isinstance(change, PositionPlanChange)
        assert change.field_name == "target_price"
        assert change.new_value == _d("1000")
        assert pos.target_price == _d("1000")
        session.rollback()

    def test_update_stop_price_creates_audit(self):
        import src.services.trade_service as svc

        session = _make_session()
        pos = self._pos(session)
        change = svc.update_plan(session, pos.id, "stop_price", _d("880"), "移動停損")
        assert change.old_value == _d("860")
        assert change.new_value == _d("880")
        assert pos.stop_price == _d("880")
        session.rollback()

    def test_invalid_field_name(self):
        import src.services.trade_service as svc

        session = _make_session()
        pos = self._pos(session)
        with pytest.raises(svc.TradeSvcError, match="target_price 或 stop_price"):
            svc.update_plan(session, pos.id, "avg_cost_per_share", _d("100"), "x")
        session.rollback()

    def test_update_plan_nonexistent_position(self):
        import src.services.trade_service as svc

        session = _make_session()
        with pytest.raises(svc.TradeSvcError, match="不存在"):
            svc.update_plan(session, 99999, "target_price", _d("1000"), "x")
        session.rollback()


# ── get_active_positions / get_executions ─────────────────────────────────────


class TestQueryMethods:
    def test_get_active_positions_excludes_closed(self):
        import src.services.trade_service as svc

        session = _make_session()
        pos1 = svc.create_position(
            session, "2330", "台積電", "MANUAL", date(2026, 10, 30)
        )
        pos2 = svc.create_position(
            session, "2454", "聯發科", "MANUAL", date(2026, 10, 30)
        )
        # pos2 買進後全數賣出 → closed
        svc.add_execution(
            session,
            pos2.id,
            "BUY",
            date(2026, 10, 31),
            execution_price=_d("1000"),
            shares=100,
            actual_fee=_d("0"),
            transaction_tax=_d("0"),
        )
        svc.add_execution(
            session,
            pos2.id,
            "SELL",
            date(2026, 11, 1),
            execution_price=_d("1100"),
            shares=100,
            actual_fee=_d("0"),
            transaction_tax=_d("0"),
        )
        assert pos2.status == "closed"

        active = svc.get_active_positions(session)
        active_ids = [p.id for p in active]
        assert pos1.id in active_ids
        assert pos2.id not in active_ids
        session.rollback()

    def test_get_active_positions_includes_partially_closed(self):
        import src.services.trade_service as svc

        session = _make_session()
        pos = svc.create_position(
            session, "2330", "台積電", "MANUAL", date(2026, 10, 30)
        )
        svc.add_execution(
            session,
            pos.id,
            "BUY",
            date(2026, 10, 31),
            execution_price=_d("100"),
            shares=2000,
            actual_fee=_d("0"),
            transaction_tax=_d("0"),
        )
        svc.add_execution(
            session,
            pos.id,
            "SELL",
            date(2026, 11, 1),
            execution_price=_d("120"),
            shares=1000,
            actual_fee=_d("0"),
            transaction_tax=_d("0"),
        )
        assert pos.status == "partially_closed"
        active = svc.get_active_positions(session)
        assert pos.id in [p.id for p in active]
        session.rollback()

    def test_get_executions_excludes_cancelled_by_default(self):
        import src.services.trade_service as svc

        session = _make_session()
        pos = svc.create_position(
            session, "2330", "台積電", "MANUAL", date(2026, 10, 30)
        )
        exec1 = svc.add_execution(
            session,
            pos.id,
            "BUY",
            date(2026, 10, 31),
            execution_price=_d("100"),
            shares=1000,
            actual_fee=_d("0"),
            transaction_tax=_d("0"),
        )
        svc.cancel_execution(session, exec1.id, "test")
        exec2 = svc.add_execution(
            session,
            pos.id,
            "BUY",
            date(2026, 10, 31),
            execution_price=_d("101"),
            shares=500,
            actual_fee=_d("0"),
            transaction_tax=_d("0"),
        )
        active_execs = svc.get_executions(session, pos.id)
        assert len(active_execs) == 1
        assert active_execs[0].id == exec2.id

        all_execs = svc.get_executions(session, pos.id, include_cancelled=True)
        assert len(all_execs) == 2
        session.rollback()

    def test_actual_paper_isolation(self):
        """get_active_positions 只回傳 ACTUAL 層，PositionMonitor 不可出現。"""
        import src.services.trade_service as svc
        from src.database import PositionMonitor

        session = _make_session()
        # 建立一個 PositionMonitor（PAPER 層）
        pm = PositionMonitor(
            stock_id="2330",
            stock_name="台積電",
            date_entered=date(2026, 10, 31),
            entry_price=100.0,
            entry_source="NEXT_OPEN",
            status="active",
        )
        session.add(pm)
        session.flush()

        # 建立一個 ACTUAL 持倉
        pos = svc.create_position(
            session, "2454", "聯發科", "MANUAL", date(2026, 10, 30)
        )

        active = svc.get_active_positions(session)
        active_ids = [p.id for p in active]
        assert pos.id in active_ids
        # PositionMonitor 不應出現在回傳結果（型別不同）
        from src.database import ActualPosition

        for p in active:
            assert isinstance(p, ActualPosition)
        session.rollback()
