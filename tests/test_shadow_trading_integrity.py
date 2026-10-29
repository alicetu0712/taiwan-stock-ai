"""
tests/test_shadow_trading_integrity.py — Shadow Trading Integrity Tests

Item 1: Execution Timestamp Integrity
  T_ST_1  activate_pending_positions 設定 shadow_trading_type = NEXT_OPEN_HISTORICAL
  T_ST_2  execution_recorded_at 被記錄（非 NULL）
  T_ST_3  NEXT_OPEN_HISTORICAL != LIVE_PREOPEN_OBSERVED（型態不同）
  T_ST_4  SIGNAL_CLOSE_LEGACY 持倉 shadow_trading_type 為 NULL（不計入新版績效）

Item 2: Evidence Alpha Consistency
  T_EA_1  research_evidence 與 forward_evidence 的 alpha_cost_convention 相同
  T_EA_2  _compute_forward_alpha 扣除 ROUND_TRIP_COST（股票側）
  T_EA_3  0050 benchmark 不扣成本
  T_EA_4  research alpha < raw spread（驗證成本有被扣除）
  T_EA_5  alpha_cost_convention 欄位存在於兩個 function 的 return dict
"""

from datetime import date, datetime

import pytest

ROUND_TRIP_COST = 0.585
ROUND_TRIP_DECIMAL = ROUND_TRIP_COST / 100


# ─────────────────────────────────────────────────────────────────────────────
# Item 1: Execution Timestamp Integrity
# ─────────────────────────────────────────────────────────────────────────────

class TestExecutionTimestampIntegrity:

    def test_activated_position_has_next_open_historical_type(self, tmp_path):
        """T_ST_1: activate_pending_positions 激活後 shadow_trading_type = NEXT_OPEN_HISTORICAL。"""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from src.database import Base, DailyPrice, PositionMonitor, Stock, init_db
        from src.engines import position_manager

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

        assert pos.shadow_trading_type == "NEXT_OPEN_HISTORICAL", (
            f"Expected NEXT_OPEN_HISTORICAL, got '{pos.shadow_trading_type}'"
        )
        s.close()

    def test_execution_recorded_at_is_set(self, tmp_path):
        """T_ST_2: execution_recorded_at 在激活時必須填入，且不為 NULL。"""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from src.database import Base, DailyPrice, PositionMonitor, Stock, init_db
        from src.engines import position_manager

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

        before = datetime.utcnow()
        position_manager.activate_pending_positions(s, date(2026, 10, 13))
        after = datetime.utcnow()
        s.refresh(pos)

        assert pos.execution_recorded_at is not None, "execution_recorded_at 不得為 NULL"
        assert before <= pos.execution_recorded_at <= after, (
            f"execution_recorded_at={pos.execution_recorded_at} 不在激活時間範圍內"
        )
        s.close()

    def test_live_preopen_type_not_assigned_by_current_pipeline(self):
        """T_ST_3: 目前 pipeline 不會將 shadow_trading_type 賦值為 LIVE_PREOPEN_OBSERVED。
        此測試確認現有架構不偽裝成盤前即時執行。
        LIVE_PREOPEN_OBSERVED 只能出現在注釋中，不得出現在賦值語句右側。
        """
        import inspect
        from src.engines import position_manager

        src = inspect.getsource(position_manager.activate_pending_positions)
        assert 'shadow_trading_type    = "NEXT_OPEN_HISTORICAL"' in src or \
               'shadow_trading_type = "NEXT_OPEN_HISTORICAL"' in src, (
            "activate_pending_positions 必須將 shadow_trading_type 設為 NEXT_OPEN_HISTORICAL"
        )
        # 賦值語句不得為 LIVE_PREOPEN_OBSERVED（允許出現在注釋中）
        assign_live = 'shadow_trading_type    = "LIVE_PREOPEN_OBSERVED"'
        assign_live2 = 'shadow_trading_type = "LIVE_PREOPEN_OBSERVED"'
        assert assign_live not in src and assign_live2 not in src, (
            "activate_pending_positions 不得將 shadow_trading_type 賦值為 LIVE_PREOPEN_OBSERVED"
        )

    def test_legacy_positions_have_null_shadow_trading_type(self, tmp_path):
        """T_ST_4: SIGNAL_CLOSE_LEGACY 持倉 shadow_trading_type 必須為 NULL（不計入新版績效）。"""
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import sessionmaker

        from src.database import Base, PositionMonitor, _migrate_position_monitor, init_db

        engine = create_engine(f"sqlite:///{tmp_path}/test.db")
        init_db(engine)
        Session = sessionmaker(bind=engine)
        s = Session()

        # 插入舊版 active 持倉（無 shadow_trading_type）
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO position_monitor "
                "(stock_id, stock_name, date_entered, entry_price, rec_level, "
                "rec_score, confidence, target_price, stop_loss_price, "
                "target_pct, stop_loss_pct, position_pct, status) "
                "VALUES ('2330', '台積電', '2026-10-08', 56.0, 'B', "
                "80.0, 75.0, 70.0, 50.0, 10.0, -10.0, 10.0, 'active')"
            ))

        _migrate_position_monitor(engine)

        pos = s.query(PositionMonitor).filter_by(stock_id="2330").first()
        s.refresh(pos)
        assert pos.entry_source == "SIGNAL_CLOSE_LEGACY"
        assert pos.shadow_trading_type is None, (
            f"SIGNAL_CLOSE_LEGACY 持倉的 shadow_trading_type 應為 NULL，"
            f"got '{pos.shadow_trading_type}'"
        )
        s.close()


# ─────────────────────────────────────────────────────────────────────────────
# Item 2: Evidence Alpha Consistency
# ─────────────────────────────────────────────────────────────────────────────

class TestEvidenceAlphaConsistency:

    def test_compute_forward_alpha_deducts_cost(self):
        """T_EA_2: _compute_forward_alpha 扣除 ROUND_TRIP_COST（股票側）。"""
        from src.services.evidence_service import _compute_forward_alpha, _ROUND_TRIP_COST_DECIMAL

        # Synthetic: entry_close=100, fwd_stock=110 (+10%), fwd_0050=105 (+5%)
        # Expected alpha = (0.10 - ROUND_TRIP_DECIMAL) - 0.05
        observations = [("2330", date(2026, 1, 10), 100.0)]
        price_map = {"2330": {date(2026, 1, 10): 100.0, date(2026, 1, 15): 110.0}}
        sorted_dates_map = {"2330": [date(2026, 1, 10), date(2026, 1, 15)]}
        p0050_map = {date(2026, 1, 10): 100.0, date(2026, 1, 15): 105.0}
        sorted_0050 = [date(2026, 1, 10), date(2026, 1, 15)]

        result = _compute_forward_alpha(
            observations, price_map, sorted_dates_map, p0050_map, sorted_0050, n_days=1
        )

        assert len(result) == 1
        expected = (110.0 - 100.0) / 100.0 - _ROUND_TRIP_COST_DECIMAL - (105.0 - 100.0) / 100.0
        assert abs(result[0] - expected) < 1e-9, (
            f"alpha={result[0]:.6f} != expected={expected:.6f}"
        )

    def test_benchmark_not_deducted(self):
        """T_EA_3: 0050 benchmark 不扣成本。"""
        from src.services.evidence_service import _compute_forward_alpha, _ROUND_TRIP_COST_DECIMAL

        # stock 原地不動（0%），0050 也不動（0%）
        # alpha = (0 - cost) - 0 = -cost
        observations = [("2330", date(2026, 1, 10), 100.0)]
        price_map = {"2330": {date(2026, 1, 10): 100.0, date(2026, 1, 11): 100.0}}
        sorted_dates_map = {"2330": [date(2026, 1, 10), date(2026, 1, 11)]}
        p0050_map = {date(2026, 1, 10): 100.0, date(2026, 1, 11): 100.0}
        sorted_0050 = [date(2026, 1, 10), date(2026, 1, 11)]

        result = _compute_forward_alpha(
            observations, price_map, sorted_dates_map, p0050_map, sorted_0050, n_days=1
        )

        assert len(result) == 1
        # alpha = (0 - cost) - 0 = -ROUND_TRIP_DECIMAL
        assert abs(result[0] - (-_ROUND_TRIP_COST_DECIMAL)) < 1e-9, (
            f"Expected -ROUND_TRIP_DECIMAL={-_ROUND_TRIP_COST_DECIMAL:.6f}, got {result[0]:.6f}"
        )

    def test_research_alpha_less_than_raw_spread(self):
        """T_EA_4: research alpha < raw spread（確認成本已扣除）。"""
        from src.services.evidence_service import _compute_forward_alpha

        observations = [("2330", date(2026, 1, 10), 100.0)]
        price_map = {"2330": {date(2026, 1, 10): 100.0, date(2026, 1, 11): 110.0}}
        sorted_dates_map = {"2330": [date(2026, 1, 10), date(2026, 1, 11)]}
        p0050_map = {date(2026, 1, 10): 100.0, date(2026, 1, 11): 105.0}
        sorted_0050 = [date(2026, 1, 10), date(2026, 1, 11)]

        alphas = _compute_forward_alpha(
            observations, price_map, sorted_dates_map, p0050_map, sorted_0050, n_days=1
        )
        assert len(alphas) == 1
        raw_spread = (110.0 - 100.0) / 100.0 - (105.0 - 100.0) / 100.0  # 0.10 - 0.05 = 0.05
        assert alphas[0] < raw_spread, (
            f"alpha={alphas[0]:.6f} should be less than raw spread={raw_spread:.6f}"
        )

    def test_alpha_cost_convention_in_research_evidence_success_path(self):
        """T_EA_5a: research_evidence 成功路徑的 return dict 必須包含 alpha_cost_convention。
        用 source inspection 驗證，不依賴測試資料。
        """
        import inspect
        from src.services import evidence_service

        src = inspect.getsource(evidence_service.research_evidence)
        assert '"alpha_cost_convention"' in src, (
            "research_evidence 成功路徑缺少 alpha_cost_convention 欄位"
        )
        assert '"stock_net_minus_bench_raw"' in src, (
            "research_evidence 缺少 stock_net_minus_bench_raw 常數值"
        )

    def test_alpha_cost_convention_in_forward_evidence_success_path(self):
        """T_EA_5b: forward_evidence 成功路徑的 return dict 必須包含 alpha_cost_convention。
        兩個函式的常數值相同 → 可以直接比較 alpha 數字。
        """
        import inspect
        from src.services import evidence_service

        re_src = inspect.getsource(evidence_service.research_evidence)
        fe_src = inspect.getsource(evidence_service.forward_evidence)

        for fn_name, src in [("research_evidence", re_src), ("forward_evidence", fe_src)]:
            assert '"alpha_cost_convention"' in src, (
                f"{fn_name} 成功路徑缺少 alpha_cost_convention 欄位"
            )
            assert '"stock_net_minus_bench_raw"' in src, (
                f"{fn_name} 缺少 stock_net_minus_bench_raw 值"
            )

    def test_round_trip_decimal_value(self):
        """_ROUND_TRIP_COST_DECIMAL = 0.585 / 100 = 0.00585（確認常數正確）。"""
        from src.services.evidence_service import _ROUND_TRIP_COST_DECIMAL

        assert abs(_ROUND_TRIP_COST_DECIMAL - 0.585 / 100) < 1e-10, (
            f"_ROUND_TRIP_COST_DECIMAL={_ROUND_TRIP_COST_DECIMAL} != 0.00585"
        )

    def test_alpha_formula_matches_foe_v1(self):
        """alpha 公式與 foe_v1 / forward_evidence 一致：stock_net - bench_raw。"""
        from src.services.evidence_service import _compute_forward_alpha, _ROUND_TRIP_COST_DECIMAL

        observations = [("2330", date(2026, 1, 10), 100.0)]
        price_map = {"2330": {date(2026, 1, 10): 100.0, date(2026, 1, 11): 108.0}}
        sorted_dates_map = {"2330": [date(2026, 1, 10), date(2026, 1, 11)]}
        p0050_map = {date(2026, 1, 10): 100.0, date(2026, 1, 11): 103.0}
        sorted_0050 = [date(2026, 1, 10), date(2026, 1, 11)]

        alphas = _compute_forward_alpha(
            observations, price_map, sorted_dates_map, p0050_map, sorted_0050, n_days=1
        )

        # foe_v1 formula
        entry = 100.0
        exit_s = 108.0
        bench_entry = 100.0
        bench_exit = 103.0
        stock_net = (exit_s - entry) / entry - _ROUND_TRIP_COST_DECIMAL
        bench_raw = (bench_exit - bench_entry) / bench_entry
        foe_alpha = stock_net - bench_raw

        assert len(alphas) == 1
        assert abs(alphas[0] - foe_alpha) < 1e-9, (
            f"evidence alpha={alphas[0]:.6f} != foe_v1 alpha={foe_alpha:.6f}"
        )
