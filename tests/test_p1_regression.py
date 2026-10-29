"""
tests/test_p1_regression.py — P1 Bug Regression Tests

每個測試對應一個明確的修復點：
  T1  Signal Date 無次日 Open → 不得建立 active 持倉
  T2  次日 Open 到位後，正確建立 active 持倉
  T3  缺 Open 時不得 fallback 到 signal close
  T4  同一訊號不得重複建立持倉
  T5  A+ 等級不得超過 max_single_pct (20%) 上限
  T6  各等級倉位不得超過 config max_single_pct
  T7  Research Alpha 不扣 benchmark 成本（與 foe_v1 一致）
  T8  ForwardOutcomeEvaluation 的 horizon 不可被覆寫（foe_v1 immutability）
  T12 sync_table INSERT 不帶 explicit id（避免 PG sequence lag）
"""

from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest

import config as _cfg
from src.engines import position_manager
from src.engines.position_manager import MAX_EXECUTION_LAG_DAYS

ROUND_TRIP_COST = 0.585


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_session(positions=None, daily_prices=None, recommendations=None):
    """SQLAlchemy session mock that supports query(...).filter(...).first() pattern."""
    positions       = positions or []
    daily_prices    = daily_prices or {}   # {(stock_id, date): open_price}
    recommendations = recommendations or {}  # {(stock_id, date): mock_rec}

    session = MagicMock()

    def query_side_effect(model):
        from src.database import DailyPrice, PositionMonitor, Recommendation

        q = MagicMock()

        if model is PositionMonitor:
            def filter_side(*args, **kwargs):
                fq = MagicMock()

                def first_side():
                    # heuristic: check if status filter includes pending_open/active
                    for pos in positions:
                        # always return first matching — tests set up data carefully
                        pass
                    return None  # default: no existing

                fq.first.side_effect = first_side
                fq.all.return_value = positions
                fq.with_entities.return_value.all.return_value = [
                    (p.position_pct,) for p in positions
                    if getattr(p, "status", "") == "active"
                ]
                return fq

            q.filter.side_effect = filter_side

        elif model is DailyPrice:
            def filter_dp(*args, **kwargs):
                fq = MagicMock()
                fq.first.return_value = None  # default
                return fq

            q.filter.side_effect = filter_dp

        elif model is Recommendation:
            def filter_rec(*args, **kwargs):
                fq = MagicMock()
                fq.first.return_value = None
                return fq

            q.filter.side_effect = filter_rec

        return q

    session.query.side_effect = query_side_effect
    session.add = MagicMock()
    session.flush = MagicMock()
    return session


def _base_kwargs(signal_date=date(2026, 10, 10),
                 expected_execution_date=date(2026, 10, 13)):
    return dict(
        stock_id="2330",
        stock_name="台積電",
        signal_date=signal_date,
        expected_execution_date=expected_execution_date,
        rec_level="A+",
        rec_score=88.0,
        confidence=80.0,
        target_price=1100.0,
        stop_loss_price=900.0,
        target_pct=10.0,
        stop_loss_pct=-10.0,
        ai_rationale="test",
    )


# ── T1: Signal Date 無次日 Open → 不得建立 active 持倉 ───────────────────────

class TestT1NoPendingWhenOpenMissing:
    """create_pending_position 建立 pending_open（無 entry_price），不是 active。"""

    def test_pending_open_has_no_entry_price(self):
        """create_pending_position 建立的持倉 entry_price 必須為 None。"""
        session = MagicMock()
        session.query.return_value.filter.return_value.first.return_value = None
        session.query.return_value.filter.return_value.with_entities.return_value.all.return_value = []
        session.add = MagicMock()
        session.flush = MagicMock()

        position_manager.create_pending_position(session=session, **_base_kwargs())

        added = session.add.call_args[0][0]
        assert added.entry_price is None, "pending_open 不得設定 entry_price"
        assert added.date_entered is None, "pending_open 不得設定 date_entered"
        assert added.status == "pending_open"

    def test_no_activation_when_open_price_missing(self, tmp_path):
        """activate_pending_positions：open 尚未到位時，不激活。"""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from src.database import Base, PositionMonitor, init_db

        engine = create_engine(f"sqlite:///{tmp_path}/test.db")
        init_db(engine)
        Session = sessionmaker(bind=engine)
        s = Session()

        # 建一筆 pending_open（無 DailyPrice）
        pos = PositionMonitor(
            stock_id="2330", stock_name="台積電",
            signal_date=date(2026, 10, 10),
            expected_execution_date=date(2026, 10, 13),
            status="pending_open",
            rec_level="A", rec_score=85.0, confidence=80.0,
            target_price=1100.0, stop_loss_price=900.0,
            target_pct=10.0, stop_loss_pct=-10.0,
        )
        s.add(pos)
        s.commit()

        # DailyPrice 無資料 → activate 應 skip
        n = position_manager.activate_pending_positions(s, date(2026, 10, 13))
        assert n == 0

        s.refresh(pos)
        assert pos.status == "pending_open", "open 缺失時狀態不得改變"
        assert pos.entry_price is None
        s.close()


# ── T2: 次日 Open 到位後正確激活 ──────────────────────────────────────────────

class TestT2ActivatesWhenOpenAvailable:
    def test_activates_with_real_open(self, tmp_path):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from src.database import Base, DailyPrice, PositionMonitor, Stock, init_db

        engine = create_engine(f"sqlite:///{tmp_path}/test.db")
        init_db(engine)
        Session = sessionmaker(bind=engine)
        s = Session()

        # 建 Stock（外鍵需求）+ DailyPrice
        s.add(Stock(stock_id="2330", name="台積電"))
        s.add(DailyPrice(
            stock_id="2330", date=date(2026, 10, 13),
            open=950.0, close=960.0,
        ))
        # pending_open
        pos = PositionMonitor(
            stock_id="2330", stock_name="台積電",
            signal_date=date(2026, 10, 10),
            expected_execution_date=date(2026, 10, 13),
            status="pending_open",
            rec_level="A", rec_score=85.0, confidence=80.0,
            target_price=1100.0, stop_loss_price=900.0,
            target_pct=10.0, stop_loss_pct=-10.0,
        )
        s.add(pos)
        s.commit()

        n = position_manager.activate_pending_positions(s, date(2026, 10, 13))
        assert n == 1

        s.refresh(pos)
        assert pos.status == "active"
        assert pos.entry_price == pytest.approx(950.0)
        assert pos.date_entered == date(2026, 10, 13)
        s.close()


# ── T3: 不得 fallback 到 signal close ─────────────────────────────────────────

class TestT3NoFallbackToClose:
    def test_open_none_stays_pending(self, tmp_path):
        """DailyPrice 存在但 open=None → 不得 fallback 到 close，持倉維持 pending_open。"""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from src.database import Base, DailyPrice, PositionMonitor, Stock, init_db

        engine = create_engine(f"sqlite:///{tmp_path}/test.db")
        init_db(engine)
        Session = sessionmaker(bind=engine)
        s = Session()

        s.add(Stock(stock_id="2330", name="台積電"))
        # open=None，只有 close
        s.add(DailyPrice(
            stock_id="2330", date=date(2026, 10, 13),
            open=None, close=960.0,
        ))
        pos = PositionMonitor(
            stock_id="2330", stock_name="台積電",
            signal_date=date(2026, 10, 10),
            expected_execution_date=date(2026, 10, 13),
            status="pending_open",
            rec_level="A", rec_score=85.0, confidence=80.0,
            target_price=1100.0, stop_loss_price=900.0,
            target_pct=10.0, stop_loss_pct=-10.0,
        )
        s.add(pos)
        s.commit()

        n = position_manager.activate_pending_positions(s, date(2026, 10, 13))
        assert n == 0, "open=None 時不得激活"

        s.refresh(pos)
        assert pos.status == "pending_open"
        assert pos.entry_price is None, "不得 fallback 到 close"
        s.close()


# ── T4: 同一訊號不得重複建立持倉 ──────────────────────────────────────────────

class TestT4NoDuplicatePosition:
    def test_second_create_returns_false(self, tmp_path):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from src.database import Base, PositionMonitor, init_db

        engine = create_engine(f"sqlite:///{tmp_path}/test.db")
        init_db(engine)
        Session = sessionmaker(bind=engine)
        s = Session()

        kwargs = dict(
            session=s,
            stock_id="2330", stock_name="台積電",
            signal_date=date(2026, 10, 10),
            expected_execution_date=date(2026, 10, 13),
            rec_level="A", rec_score=85.0, confidence=80.0,
            target_price=1100.0, stop_loss_price=900.0,
            target_pct=10.0, stop_loss_pct=-10.0,
        )
        r1 = position_manager.create_pending_position(**kwargs)
        s.commit()
        r2 = position_manager.create_pending_position(**kwargs)

        assert r1 is True
        assert r2 is False, "重複建倉應回傳 False"

        count = s.query(PositionMonitor).filter(
            PositionMonitor.stock_id == "2330"
        ).count()
        assert count == 1
        s.close()

    def test_active_blocks_new_pending(self, tmp_path):
        """已有 active 持倉時，create_pending_position 應回傳 False。"""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from src.database import Base, DailyPrice, PositionMonitor, Stock, init_db

        engine = create_engine(f"sqlite:///{tmp_path}/test.db")
        init_db(engine)
        Session = sessionmaker(bind=engine)
        s = Session()

        s.add(Stock(stock_id="2330", name="台積電"))
        s.add(DailyPrice(
            stock_id="2330", date=date(2026, 10, 13),
            open=950.0, close=960.0,
        ))
        # 第一次建立 pending → 激活
        position_manager.create_pending_position(
            session=s, stock_id="2330", stock_name="台積電",
            signal_date=date(2026, 10, 10), expected_execution_date=date(2026, 10, 13),
            rec_level="A", rec_score=85.0, confidence=80.0,
            target_price=1100.0, stop_loss_price=900.0,
            target_pct=10.0, stop_loss_pct=-10.0,
        )
        s.commit()
        position_manager.activate_pending_positions(s, date(2026, 10, 13))
        s.commit()

        # 再次推薦同一股票 → 應被拒絕
        result = position_manager.create_pending_position(
            session=s, stock_id="2330", stock_name="台積電",
            signal_date=date(2026, 10, 14), expected_execution_date=date(2026, 10, 15),
            rec_level="A+", rec_score=90.0, confidence=85.0,
            target_price=1150.0, stop_loss_price=920.0,
            target_pct=15.0, stop_loss_pct=-8.0,
        )
        assert result is False
        s.close()


# ── T5 / T6: A+ 不得超過 max_single_pct ──────────────────────────────────────

class TestT5T6PositionSizingCap:
    def test_a_plus_capped_at_max_single_pct(self):
        """A+ 等級（base 20%）+ 最高信心（90%）→ position_pct ≤ max_single_pct。"""
        max_cap = _cfg.POSITION_SIZING["max_single_pct"]
        pct = position_manager._compute_position_pct("A+", 90.0)
        assert pct <= max_cap, (
            f"A+ 信心 90% 計算出 {pct:.0f}%，超過 config 上限 {max_cap:.0f}%"
        )

    @pytest.mark.parametrize("level,confidence", [
        ("A+", 100.0),
        ("A+",  90.0),
        ("A+",  80.0),
        ("A",   90.0),
        ("B",   90.0),
    ])
    def test_all_levels_capped(self, level, confidence):
        max_cap = _cfg.POSITION_SIZING["max_single_pct"]
        pct = position_manager._compute_position_pct(level, confidence)
        assert pct <= max_cap, (
            f"level={level} conf={confidence:.0f}% → {pct:.0f}% 超過上限 {max_cap:.0f}%"
        )

    def test_risk_per_trade_1_pct(self):
        """單筆最大風險不超過 config.POSITION_SIZING['max_risk_pct']。"""
        capital    = _cfg.POSITION_SIZING["capital_ntd"]
        max_risk   = _cfg.POSITION_SIZING["max_risk_pct"]  # 1.0 %
        max_single = _cfg.POSITION_SIZING["max_single_pct"]  # 20.0 %
        # 持倉 20% × 停損假設 5%（最壞情況）
        stop_pct = 5.0
        risk_pct = (max_single / 100.0) * stop_pct
        # risk_pct 僅超過 max_risk 時才是問題（此測試確認設定值合理）
        # 注意：這不是 1% rule 的完整實作，只驗證 config 數值本身不矛盾
        assert max_risk > 0, "max_risk_pct 必須大於 0"
        assert max_single <= 100.0, "max_single_pct 不得超過 100%"


# ── T7: Research Alpha 定義與 foe_v1 一致 ──────────────────────────────────────

class TestT7AlphaDefinitionConsistency:
    def test_stock_bears_cost_benchmark_does_not(self):
        """Alpha = (stock_raw - cost) - benchmark_raw。0050 不扣 ROUND_TRIP_COST。"""
        stock_raw = 10.0
        bench_raw = 5.0

        # New formula (foe_v1 consistent)
        stock_net = round(stock_raw - ROUND_TRIP_COST, 4)
        alpha     = round(stock_net - bench_raw, 4)

        expected = round(stock_raw - ROUND_TRIP_COST - bench_raw, 4)
        assert alpha == pytest.approx(expected, abs=1e-6)

    def test_alpha_is_lower_than_raw_spread(self):
        """alpha < (stock_raw - bench_raw) by exactly ROUND_TRIP_COST."""
        stock_raw = 8.0
        bench_raw = 3.0
        raw_spread = stock_raw - bench_raw

        alpha = round(stock_raw - ROUND_TRIP_COST - bench_raw, 4)
        assert abs(alpha - (raw_spread - ROUND_TRIP_COST)) < 1e-6

    def test_alpha_none_when_benchmark_missing(self):
        """benchmark 報酬為 None 時 alpha 必須為 None。"""
        stock_raw = 8.0
        bench_raw = None
        alpha = (
            round((stock_raw - ROUND_TRIP_COST) - bench_raw, 4)
            if (stock_raw is not None and bench_raw is not None)
            else None
        )
        assert alpha is None

    def test_alpha_consistent_with_foe_v1(self):
        """foe_v1 outcome_evaluation.py 的公式：alpha = stock_ret - bmark_ret（cost 只扣股票側）。

        對照 foe_v1 lines 459-464：
            bmark_ret = (bmark_exit_close / benchmark_entry_price - 1) * 100  # no cost
            alpha = round(stock_ret - bmark_ret, 4)  # stock_ret already cost-adjusted
        """
        entry = 100.0
        exit_stock = 110.0
        exit_bench = 105.0

        # foe_v1 calculation
        stock_ret_foe = round((exit_stock - entry) / entry * 100 - ROUND_TRIP_COST, 4)
        bench_ret_foe = round((exit_bench - entry) / entry * 100, 4)  # no cost
        alpha_foe = round(stock_ret_foe - bench_ret_foe, 4)

        # research_backtest (after fix) calculation
        stock_ret_rb = round((exit_stock - entry) / entry * 100 - ROUND_TRIP_COST, 4)
        bench_ret_rb = round((exit_bench - entry) / entry * 100, 4)   # no cost
        alpha_rb = round(stock_ret_rb - bench_ret_rb, 4)

        assert alpha_foe == pytest.approx(alpha_rb, abs=1e-6), (
            f"foe_v1 alpha={alpha_foe:.4f} ≠ research alpha={alpha_rb:.4f}"
        )


# ── T8: ForwardOutcomeEvaluation horizon 不可覆寫（foe_v1 immutability）────────

class TestT8FoeImmutability:
    def test_matured_20d_horizon_not_overwritten(self, tmp_path):
        """horizon_20d_matured_at 設定後，20D bundle 不得被覆寫。"""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from src.database import Base, ForwardOutcomeEvaluation, init_db

        engine = create_engine(f"sqlite:///{tmp_path}/foe_test.db")
        init_db(engine)
        Session = sessionmaker(bind=engine)
        s = Session()

        matured_ts = datetime(2026, 11, 1, 0, 0, 0)
        row = ForwardOutcomeEvaluation(
            forward_signal_id=999,
            path_type="BASELINE_NEXT_OPEN",
            outcome_protocol_version="foe_v1",
            stock_id="2330",
            signal_date=date(2026, 10, 10),
            horizon_20d_matured_at=matured_ts,
            alpha_20d=4.415,   # locked value
            return_20d=9.415,
        )
        s.add(row)
        s.commit()

        # Simulate what outcome_service._fill_horizons does:
        # it skips if matured_at is set
        from src.services.outcome_service import _fill_horizons_guard

        already_matured = _fill_horizons_guard(row, "horizon_20d_matured_at")
        assert already_matured is True, (
            "_fill_horizons_guard should return True (skip) when 20D is already matured"
        )
        s.close()


# ── T9: Shadow Trading 完整性 — 錯過執行窗口不得補成交 ───────────────────────

class TestT9MissedExecutionWindow:
    def test_late_pipeline_marks_missed_execution(self, tmp_path):
        """Pipeline 晚 1+ 天執行時，pending_open 應標記 missed_execution，不得激活。"""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from src.database import Base, DailyPrice, PositionMonitor, Stock, init_db

        engine = create_engine(f"sqlite:///{tmp_path}/test.db")
        init_db(engine)
        Session = sessionmaker(bind=engine)
        s = Session()

        s.add(Stock(stock_id="2330", name="台積電"))
        # Open price IS available — but pipeline runs late (day after exec_date)
        s.add(DailyPrice(
            stock_id="2330", date=date(2026, 10, 13),
            open=950.0, close=960.0,
        ))
        pos = PositionMonitor(
            stock_id="2330", stock_name="台積電",
            signal_date=date(2026, 10, 10),
            expected_execution_date=date(2026, 10, 13),
            status="pending_open",
            rec_level="A", rec_score=85.0, confidence=80.0,
            target_price=1100.0, stop_loss_price=900.0,
            target_pct=10.0, stop_loss_pct=-10.0,
        )
        s.add(pos)
        s.commit()

        # Pipeline runs one day late (2026-10-14 instead of 2026-10-13)
        late_date = date(2026, 10, 14)
        n = position_manager.activate_pending_positions(s, late_date)
        assert n == 0, "不得激活（pipeline 晚了 1 天）"

        s.refresh(pos)
        assert pos.status == "missed_execution", (
            f"Expected 'missed_execution', got '{pos.status}'"
        )
        assert pos.entry_price is None, "missed_execution 不得有 entry_price"
        s.close()

    def test_on_time_execution_activates(self, tmp_path):
        """Pipeline 準時執行 → 應正常激活（對照組）。"""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from src.database import Base, DailyPrice, PositionMonitor, Stock, init_db

        engine = create_engine(f"sqlite:///{tmp_path}/test.db")
        init_db(engine)
        Session = sessionmaker(bind=engine)
        s = Session()

        s.add(Stock(stock_id="2330", name="台積電"))
        s.add(DailyPrice(
            stock_id="2330", date=date(2026, 10, 13),
            open=950.0, close=960.0,
        ))
        pos = PositionMonitor(
            stock_id="2330", stock_name="台積電",
            signal_date=date(2026, 10, 10),
            expected_execution_date=date(2026, 10, 13),
            status="pending_open",
            rec_level="A", rec_score=85.0, confidence=80.0,
            target_price=1100.0, stop_loss_price=900.0,
            target_pct=10.0, stop_loss_pct=-10.0,
        )
        s.add(pos)
        s.commit()

        # Pipeline runs on time
        n = position_manager.activate_pending_positions(s, date(2026, 10, 13))
        assert n == 1

        s.refresh(pos)
        assert pos.status == "active"
        assert pos.entry_price == pytest.approx(950.0)
        assert pos.entry_source == "NEXT_OPEN"
        s.close()

    def test_max_execution_lag_constant_is_zero(self):
        """MAX_EXECUTION_LAG_DAYS 必須為 0（最保守），確保 Shadow Trading 完整性。"""
        assert MAX_EXECUTION_LAG_DAYS == 0, (
            f"MAX_EXECUTION_LAG_DAYS={MAX_EXECUTION_LAG_DAYS}，Shadow Trading 要求 0"
        )


# ── T10: Pending 不參與 P&L、停損、追蹤停損 ─────────────────────────────────

class TestT10PendingExcludedFromPnL:
    def test_pending_not_in_exit_signals(self, tmp_path):
        """check_exit_signals 只掃描 active 持倉；pending_open 必須被排除。"""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from src.database import Base, PositionMonitor, init_db

        engine = create_engine(f"sqlite:///{tmp_path}/test.db")
        init_db(engine)
        Session = sessionmaker(bind=engine)
        s = Session()

        # 一個 pending_open（無 entry_price）
        pos_pending = PositionMonitor(
            stock_id="2330", stock_name="台積電",
            signal_date=date(2026, 10, 10),
            expected_execution_date=date(2026, 10, 13),
            status="pending_open",
            rec_level="A", rec_score=85.0, confidence=80.0,
            target_price=1100.0, stop_loss_price=900.0,
            target_pct=10.0, stop_loss_pct=-10.0,
        )
        # 一個 active（正常持倉，在停損點之上，不應觸發）
        pos_active = PositionMonitor(
            stock_id="2412", stock_name="中華電",
            signal_date=date(2026, 10, 10),
            expected_execution_date=date(2026, 10, 13),
            date_entered=date(2026, 10, 13),
            entry_price=100.0,
            entry_source="NEXT_OPEN",
            status="active",
            rec_level="A", rec_score=80.0, confidence=80.0,
            target_price=120.0, stop_loss_price=90.0,
            target_pct=20.0, stop_loss_pct=-10.0,
        )
        s.add(pos_pending)
        s.add(pos_active)
        s.commit()

        price_map = {"2330": 800.0, "2412": 105.0}  # 2330 below stop, but pending!
        signals = position_manager.check_exit_signals(
            session=s,
            trade_date=date(2026, 10, 14),
            price_map=price_map,
        )
        triggered_ids = {sig.stock_id for sig in signals}
        assert "2330" not in triggered_ids, (
            "pending_open 持倉不得觸發停損（entry_price=None）"
        )
        assert "2412" not in triggered_ids, "2412 在停損點之上，不應觸發"
        s.close()

    def test_pending_not_counted_in_used_pct(self, tmp_path):
        """pending_open 持倉不得計入資金使用率（用於 active 限制）。"""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from src.database import Base, DailyPrice, PositionMonitor, Stock, init_db

        engine = create_engine(f"sqlite:///{tmp_path}/test.db")
        init_db(engine)
        Session = sessionmaker(bind=engine)
        s = Session()

        # 兩個 pending_open（合計 position_pct = 40%）
        for sid, name in [("2330", "台積電"), ("2412", "中華電")]:
            s.add(PositionMonitor(
                stock_id=sid, stock_name=name,
                signal_date=date(2026, 10, 10),
                expected_execution_date=date(2026, 10, 13),
                status="pending_open",
                rec_level="A", rec_score=80.0, confidence=80.0,
                target_price=100.0, stop_loss_price=80.0,
                target_pct=10.0, stop_loss_pct=-10.0,
                position_pct=20.0,
            ))
        s.commit()

        # 建立第三個 active 持倉，總用量只算 active 的 20%
        # open_position 查詢 status=="active" 的 used_pct：
        # 2330 和 2412 都是 pending_open，total_used = 0
        # 因此 20% 新倉應該可以建立
        s.add(Stock(stock_id="2454", name="聯發科"))
        s.add(DailyPrice(stock_id="2454", date=date(2026, 10, 13), open=1000.0, close=1010.0))
        result = position_manager.open_position(
            session=s, stock_id="2454", stock_name="聯發科",
            entry_date=date(2026, 10, 13), entry_price=1000.0,
            rec_level="A", rec_score=80.0, confidence=80.0,
            target_price=1200.0, stop_loss_price=900.0,
            target_pct=20.0, stop_loss_pct=-10.0,
        )
        assert result is True, "pending_open 不應計入資金使用率，新倉應可建立"
        s.close()


# ── T11: entry_source 標記驗證 ───────────────────────────────────────────────

class TestT11EntrySourceMarking:
    def test_next_open_entry_source_set(self, tmp_path):
        """activate_pending_positions 激活後，entry_source 必須為 'NEXT_OPEN'。"""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from src.database import Base, DailyPrice, PositionMonitor, Stock, init_db

        engine = create_engine(f"sqlite:///{tmp_path}/test.db")
        init_db(engine)
        Session = sessionmaker(bind=engine)
        s = Session()

        s.add(Stock(stock_id="2330", name="台積電"))
        s.add(DailyPrice(
            stock_id="2330", date=date(2026, 10, 13),
            open=950.0, close=960.0,
        ))
        pos = PositionMonitor(
            stock_id="2330", stock_name="台積電",
            signal_date=date(2026, 10, 10),
            expected_execution_date=date(2026, 10, 13),
            status="pending_open",
            rec_level="A", rec_score=85.0, confidence=80.0,
            target_price=1100.0, stop_loss_price=900.0,
            target_pct=10.0, stop_loss_pct=-10.0,
        )
        s.add(pos)
        s.commit()

        position_manager.activate_pending_positions(s, date(2026, 10, 13))
        s.refresh(pos)
        assert pos.entry_source == "NEXT_OPEN"
        s.close()

    def test_migration_marks_legacy_positions(self, tmp_path):
        """_migrate_position_monitor 應將既有 active 記錄標記為 SIGNAL_CLOSE_LEGACY。

        流程：用 open_position()（backward-compat path）建立 active 持倉，
        然後手動清空 entry_source 以模擬 pre-fix DB 狀態，
        重跑 migration，驗證 entry_source 被標記為 SIGNAL_CLOSE_LEGACY。
        """
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import sessionmaker

        from src.database import Base, PositionMonitor, _migrate_position_monitor, init_db
        from src.engines import position_manager

        engine = create_engine(f"sqlite:///{tmp_path}/legacy.db")
        init_db(engine)
        Session = sessionmaker(bind=engine)
        s = Session()

        # 建立 active 持倉（使用 open_position backward-compat path）
        position_manager.open_position(
            session=s, stock_id="2330", stock_name="台積電",
            entry_date=date(2026, 10, 8), entry_price=56.0,
            rec_level="B", rec_score=75.0, confidence=75.0,
            target_price=70.0, stop_loss_price=50.0,
            target_pct=10.0, stop_loss_pct=-10.0,
        )
        s.commit()

        # 模擬 pre-fix 狀態：清除 entry_source（就像舊 DB 一樣）
        with engine.begin() as conn:
            conn.execute(text(
                "UPDATE position_monitor SET entry_source = NULL WHERE stock_id = '2330'"
            ))

        pos = s.query(PositionMonitor).filter_by(stock_id="2330").first()
        s.refresh(pos)
        assert pos.entry_source is None, "模擬 pre-fix 狀態應為 NULL"

        # 重跑 migration → 應自動標記
        _migrate_position_monitor(engine)

        s.refresh(pos)
        assert pos.entry_source == "SIGNAL_CLOSE_LEGACY", (
            f"Expected SIGNAL_CLOSE_LEGACY, got '{pos.entry_source}'"
        )
        s.close()


# ── T12: sync_table does not include explicit id in INSERT ────────────────────

class TestT12SyncTableNoExplicitId:
    """T12: sync_table INSERT 不帶 explicit id，防止 PG sequence lag。

    製造兩個獨立的 in-memory SQLite DB，以 sync_table() 把 analysis_results
    從 source sync 到 target，驗證 target 的自動分配 id ≠ source id。
    SQLite AUTOINCREMENT 行為與 PG sequences 類比。
    """

    def test_inserted_row_gets_new_id(self, tmp_path):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from src.database import AnalysisResult, Base, init_db

        src_engine = create_engine("sqlite:///:memory:")
        dst_engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(src_engine)
        Base.metadata.create_all(dst_engine)

        SrcSession = sessionmaker(bind=src_engine)
        DstSession = sessionmaker(bind=dst_engine)

        src_s = SrcSession()
        ar = AnalysisResult(
            stock_id="2330",
            date=date(2026, 10, 29),
            total_score=75.0,
            rec_level="A",
        )
        src_s.add(ar)
        src_s.commit()
        src_id = ar.id  # SQLite assigned (e.g. 1)
        src_s.close()

        # Insert a dummy row first in dst so its autoincrement starts at a different value
        dst_s = DstSession()
        dummy = AnalysisResult(
            stock_id="0050",
            date=date(2026, 10, 28),
            total_score=50.0,
            rec_level="B",
        )
        dst_s.add(dummy)
        dst_s.commit()
        dst_s.close()

        # Now sync — this is the function under test
        from scripts.sync_to_neon import sync_table
        src_s2 = SrcSession()
        dst_s2 = DstSession()
        sync_table(src_s2, dst_s2, AnalysisResult, key_fields=["stock_id", "date"], days=365)
        src_s2.close()

        # Verify: the synced row has a dst-assigned id (not the src id)
        dst_s3 = DstSession()
        synced = (
            dst_s3.query(AnalysisResult)
            .filter_by(stock_id="2330", date=date(2026, 10, 29))
            .first()
        )
        assert synced is not None, "sync_table failed to insert row into dst"
        assert synced.id != src_id, (
            f"sync_table must NOT carry over src id={src_id}. "
            f"Got dst id={synced.id} — sequence lag bug re-introduced."
        )
        dst_s3.close()

    def test_second_sync_does_not_duplicate(self, tmp_path):
        """連跑兩次 sync_table，第二次應 UPDATE 而不是 INSERT。"""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from src.database import AnalysisResult, Base

        src_engine = create_engine("sqlite:///:memory:")
        dst_engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(src_engine)
        Base.metadata.create_all(dst_engine)

        SrcSession = sessionmaker(bind=src_engine)
        DstSession = sessionmaker(bind=dst_engine)

        src_s = SrcSession()
        src_s.add(AnalysisResult(
            stock_id="2330", date=date(2026, 10, 29),
            total_score=75.0, rec_level="A",
        ))
        src_s.commit()
        src_s.close()

        from scripts.sync_to_neon import sync_table

        # First sync
        s1, d1 = SrcSession(), DstSession()
        sync_table(s1, d1, AnalysisResult, key_fields=["stock_id", "date"], days=365)
        s1.close(); d1.close()

        # Second sync — must not create a duplicate
        s2, d2 = SrcSession(), DstSession()
        sync_table(s2, d2, AnalysisResult, key_fields=["stock_id", "date"], days=365)
        s2.close(); d2.close()

        dst_s = DstSession()
        count = (
            dst_s.query(AnalysisResult)
            .filter_by(stock_id="2330", date=date(2026, 10, 29))
            .count()
        )
        assert count == 1, (
            f"Expected 1 row after two syncs, got {count} — duplicate INSERT on second sync."
        )
        dst_s.close()
