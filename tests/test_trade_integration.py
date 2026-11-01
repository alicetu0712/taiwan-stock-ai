"""
tests/test_trade_integration.py — Trade Lifecycle Phase 1B 整合測試

對應需求第七節 12 個驗收場景：
1.  正式 BUY (AI_SIGNAL) → 手動確認 → ACTUAL 建倉
2.  MANUAL → ACTUAL 建倉
3.  加碼後平均成本更新
4.  部分出場後剩餘持股與損益更新
5.  全部出場後持倉關閉
6.  重複提交不產生重複成交
7.  PAPER 不進入 ACTUAL 統計
8.  ForwardSignal 不被 trade_service 修改
9.  歷史 user_trades 不被覆寫
10. 缺失股價不產生損益數值（enrich_positions 回傳 None）
11. 過期股價標記 price_stale=True，不隱含為現價
12. Pipeline 不自動建立真實持倉（AST import 掃描）
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest


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


def _d(v):
    return Decimal(str(v))


def _make_forward_signal(session, stock_id="2330", is_valid=True):
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


# ── 1. AI_SIGNAL → ACTUAL 建倉 ────────────────────────────────────────────────


class TestScenario1_AiSignalToActual:
    def test_ai_signal_creates_position_with_snapshot(self):
        """正式 BUY → 手動確認 → ACTUAL 持倉建立，original_plan_snapshot 凍結。"""
        import json

        import src.services.trade_service as svc

        session = _make_session()
        fs = _make_forward_signal(session)
        pos = svc.create_position(
            session,
            "2330",
            "台積電",
            "AI_SIGNAL",
            date(2026, 10, 31),
            forward_signal_id=fs.id,
            target_price=_d("980"),
            stop_price=_d("860"),
        )
        svc.add_execution(
            session,
            pos.id,
            "BUY",
            date(2026, 10, 31),
            execution_price=_d("905"),
            shares=1000,
            actual_fee=_d("129"),
            transaction_tax=_d("0"),
        )
        assert pos.signal_source == "AI_SIGNAL"
        assert pos.forward_signal_id == fs.id
        assert pos.remaining_shares == 1000
        snap = json.loads(pos.original_plan_snapshot)
        assert snap["decision_label"] == "buy"
        assert snap["entry_low"] == 900.0
        session.rollback()

    def test_snapshot_not_modified_after_update_plan(self):
        """修改計畫（update_plan）不得覆寫 original_plan_snapshot。"""
        import json

        import src.services.trade_service as svc

        session = _make_session()
        fs = _make_forward_signal(session)
        pos = svc.create_position(
            session,
            "2330",
            "台積電",
            "AI_SIGNAL",
            date(2026, 10, 31),
            forward_signal_id=fs.id,
            stop_price=_d("860"),
        )
        original_snap = pos.original_plan_snapshot
        svc.update_plan(session, pos.id, "stop_price", _d("880"), "移動停損")
        assert pos.original_plan_snapshot == original_snap  # 凍結，不可改
        snap = json.loads(pos.original_plan_snapshot)
        assert snap["stop_price"] == 860.0  # 原始值
        session.rollback()


# ── 2. MANUAL → ACTUAL 建倉 ───────────────────────────────────────────────────


class TestScenario2_ManualActual:
    def test_manual_position_no_snapshot(self):
        import src.services.trade_service as svc

        session = _make_session()
        pos = svc.create_position(
            session, "2454", "聯發科", "MANUAL", date(2026, 10, 31)
        )
        svc.add_execution(
            session,
            pos.id,
            "BUY",
            date(2026, 10, 31),
            execution_price=_d("1000"),
            shares=100,
            actual_fee=_d("143"),
            transaction_tax=_d("0"),
        )
        assert pos.signal_source == "MANUAL"
        assert pos.forward_signal_id is None
        assert pos.original_plan_snapshot is None
        assert pos.remaining_shares == 100
        session.rollback()


# ── 3. 加碼後平均成本更新 ─────────────────────────────────────────────────────


class TestScenario3_Averaging:
    def test_mwac_after_averaging_up(self):
        """加碼後 MWAC 正確計算。"""
        import src.services.trade_service as svc

        session = _make_session()
        pos = svc.create_position(
            session, "2330", "台積電", "MANUAL", date(2026, 10, 30)
        )
        # 第一筆：1000股 @ 900
        svc.add_execution(
            session,
            pos.id,
            "BUY",
            date(2026, 10, 31),
            execution_price=_d("900"),
            shares=1000,
            actual_fee=_d("0"),
            transaction_tax=_d("0"),
        )
        # 加碼：500股 @ 960 → avg = (900000+480000)/1500 = 920
        svc.add_execution(
            session,
            pos.id,
            "BUY",
            date(2026, 11, 1),
            execution_price=_d("960"),
            shares=500,
            actual_fee=_d("0"),
            transaction_tax=_d("0"),
        )
        assert pos.remaining_shares == 1500
        assert pos.avg_cost_per_share == _d("920.0000")
        assert pos.total_cost_basis == _d("1380000.00")
        session.rollback()


# ── 4. 部分出場後剩餘持股與損益 ───────────────────────────────────────────────


class TestScenario4_PartialExit:
    def test_partial_sell_updates_status_and_pnl(self):
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
            execution_price=_d("900"),
            shares=2000,
            actual_fee=_d("0"),
            transaction_tax=_d("0"),
        )
        # 賣 1000 @ 980 fee=139 tax=294
        svc.add_execution(
            session,
            pos.id,
            "SELL",
            date(2026, 11, 1),
            execution_price=_d("980"),
            shares=1000,
            actual_fee=_d("139"),
            transaction_tax=_d("294"),
        )
        assert pos.status == "partially_closed"
        assert pos.remaining_shares == 1000
        # proceeds = 980000 - 139 - 294 = 979567; cost_of_sold = 900*1000=900000
        assert pos.realized_pnl == _d("79567.00")
        assert pos.avg_cost_per_share == _d("900.0000")
        session.rollback()


# ── 5. 全部出場後持倉關閉 ─────────────────────────────────────────────────────


class TestScenario5_FullExit:
    def test_full_sell_closes_position(self):
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
            execution_price=_d("900"),
            shares=1000,
            actual_fee=_d("0"),
            transaction_tax=_d("0"),
        )
        svc.add_execution(
            session,
            pos.id,
            "SELL",
            date(2026, 11, 1),
            execution_price=_d("980"),
            shares=1000,
            actual_fee=_d("0"),
            transaction_tax=_d("0"),
        )
        assert pos.status == "closed"
        assert pos.remaining_shares == 0
        assert pos.close_date == date(2026, 11, 1)
        active = svc.get_active_positions(session)
        assert pos.id not in [p.id for p in active]
        session.rollback()


# ── 6. 重複提交防護 ───────────────────────────────────────────────────────────


class TestScenario6_DuplicateProtection:
    def test_same_parameters_in_window_rejected(self):
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
            execution_price=_d("900"),
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
                execution_price=_d("900"),
                shares=1000,
                actual_fee=_d("0"),
                transaction_tax=_d("0"),
            )
        execs = svc.get_executions(session, pos.id)
        assert len(execs) == 1  # 只有一筆
        session.rollback()


# ── 7. PAPER 不進入 ACTUAL 統計 ───────────────────────────────────────────────


class TestScenario7_PaperIsolation:
    def test_paper_position_not_in_active_positions(self):
        import src.services.trade_service as svc
        from src.database import ActualPosition, PositionMonitor

        session = _make_session()
        # PAPER
        pm = PositionMonitor(
            stock_id="2330",
            stock_name="台積電",
            date_entered=date(2026, 10, 31),
            entry_price=900.0,
            entry_source="NEXT_OPEN",
            status="active",
        )
        session.add(pm)
        # ACTUAL
        pos = svc.create_position(
            session, "2454", "聯發科", "MANUAL", date(2026, 10, 31)
        )
        session.flush()

        active = svc.get_active_positions(session)
        assert all(isinstance(p, ActualPosition) for p in active)
        actual_ids = [p.id for p in active]
        assert pos.id in actual_ids
        session.rollback()

    def test_paper_pnl_not_mixed_with_actual_pnl(self):
        """
        ACTUAL realized_pnl 只計 trade_executions；
        PositionMonitor.pnl_pct 獨立存在，不影響 ACTUAL 計算。
        """
        import src.services.trade_service as svc
        from src.database import PositionMonitor

        session = _make_session()
        pm = PositionMonitor(
            stock_id="2330",
            stock_name="台積電",
            date_entered=date(2026, 10, 31),
            entry_price=900.0,
            entry_source="NEXT_OPEN",
            status="active",
            pnl_pct=50.0,  # PAPER 損益
        )
        session.add(pm)
        pos = svc.create_position(
            session, "2330", "台積電", "MANUAL", date(2026, 10, 31)
        )
        svc.add_execution(
            session,
            pos.id,
            "BUY",
            date(2026, 10, 31),
            execution_price=_d("900"),
            shares=1000,
            actual_fee=_d("0"),
            transaction_tax=_d("0"),
        )
        session.flush()
        # ACTUAL realized_pnl 不受 PAPER 影響
        assert pos.realized_pnl == _d("0.00")
        session.rollback()


# ── 8. ForwardSignal 不被 trade_service 修改 ─────────────────────────────────


class TestScenario8_ForwardSignalImmutable:
    def test_create_position_does_not_modify_forward_signal(self):
        import src.services.trade_service as svc
        from src.database import ForwardSignal

        session = _make_session()
        fs = _make_forward_signal(session)
        original_score = fs.total_score
        original_valid = fs.is_valid

        pos = svc.create_position(
            session,
            "2330",
            "台積電",
            "AI_SIGNAL",
            date(2026, 10, 31),
            forward_signal_id=fs.id,
        )
        svc.add_execution(
            session,
            pos.id,
            "BUY",
            date(2026, 10, 31),
            execution_price=_d("905"),
            shares=1000,
            actual_fee=_d("0"),
            transaction_tax=_d("0"),
        )
        session.flush()
        # Re-query
        fs_after = session.query(ForwardSignal).filter_by(id=fs.id).first()
        assert fs_after.total_score == original_score
        assert fs_after.is_valid == original_valid
        session.rollback()


# ── 9. 歷史 user_trades 不被覆寫 ─────────────────────────────────────────────


class TestScenario9_UserTradesPreserved:
    def test_user_trades_table_unchanged(self):
        from sqlalchemy import text

        import src.services.trade_service as svc

        session = _make_session()
        # 建立一筆 ACTUAL 成交
        pos = svc.create_position(
            session, "2330", "台積電", "MANUAL", date(2026, 10, 31)
        )
        svc.add_execution(
            session,
            pos.id,
            "BUY",
            date(2026, 10, 31),
            execution_price=_d("900"),
            shares=1000,
            actual_fee=_d("0"),
            transaction_tax=_d("0"),
        )
        session.flush()
        count = session.execute(text("SELECT COUNT(*) FROM user_trades")).scalar()
        assert count == 0  # user_trades 不受影響
        session.rollback()


# ── 10. 缺失股價不產生誤導性損益 ─────────────────────────────────────────────


class TestScenario10_MissingPrice:
    def test_no_price_data_returns_none_pnl(self):
        import src.services.trade_service as svc
        from src.services.actual_position_service import enrich_positions

        session = _make_session()
        pos = svc.create_position(
            session, "9999", "無資料股", "MANUAL", date(2026, 10, 31)
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
        enriched = enrich_positions(session, [pos])
        e = enriched[0]
        assert e["current_price"] is None
        assert e["unrealized_pnl"] is None
        assert e["unrealized_pct"] is None
        assert e["price_stale"] is None  # None = no data, distinct from stale
        session.rollback()


# ── 11. 過期股價標記 price_stale=True ─────────────────────────────────────────


class TestScenario11_StalePrice:
    def test_old_price_flagged_stale(self):
        import src.services.trade_service as svc
        from src.database import DailyPrice
        from src.services.actual_position_service import enrich_positions

        session = _make_session()
        pos = svc.create_position(
            session, "2330", "台積電", "MANUAL", date(2026, 10, 30)
        )
        svc.add_execution(
            session,
            pos.id,
            "BUY",
            date(2026, 10, 31),
            execution_price=_d("900"),
            shares=1000,
            actual_fee=_d("0"),
            transaction_tax=_d("0"),
        )
        old_date = date.today() - timedelta(days=10)
        session.add(DailyPrice(stock_id="2330", date=old_date, close=950.0))
        session.flush()
        enriched = enrich_positions(session, [pos])
        e = enriched[0]
        assert e["price_stale"] is True
        assert e["price_age_days"] == 10
        # 雖然有 pnl 數字，但 price_stale=True 告知 UI 不應視為即時市值
        assert e["unrealized_pnl"] is not None  # 計算值存在
        session.rollback()


# ── 12. Pipeline 不自動建立真實持倉 ──────────────────────────────────────────


class TestScenario12_PipelineIsolation:
    def test_pipeline_modules_do_not_import_trade_service(self):
        """AST 掃描：pipeline 相關模組不可 import trade_service。"""
        import ast
        import os

        pipeline_files = [
            "scripts/run_daily.py",
            "src/services/candidate_pool_service.py",
            "src/services/live_execution_service.py",
        ]

        def get_imports(fpath):
            with open(fpath) as f:
                tree = ast.parse(f.read(), filename=fpath)
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports += [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.append(node.module)
            return imports

        for fpath in pipeline_files:
            if not os.path.exists(fpath):
                continue
            imps = get_imports(fpath)
            for imp in imps:
                assert "trade_service" not in imp, (
                    f"{fpath} imports trade_service ({imp}) — "
                    "pipeline must not create ACTUAL positions"
                )

    def test_trade_service_has_no_pipeline_imports(self):
        """trade_service.py 不得 import pipeline/pipeline-related modules。"""
        import ast

        with open("src/services/trade_service.py") as f:
            tree = ast.parse(f.read())
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports += [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
        forbidden = ["run_daily", "candidate_pool_service", "live_execution_service"]
        for imp in imports:
            for fb in forbidden:
                assert (
                    fb not in imp
                ), f"trade_service.py imports {imp!r} which references pipeline module"
