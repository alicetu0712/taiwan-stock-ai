"""
tests/test_actual_position_service.py — actual_position_service 單元測試
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


def _add_price(session, stock_id, price_date, close):
    from src.database import DailyPrice

    session.add(DailyPrice(stock_id=stock_id, date=price_date, close=close))
    session.flush()


def _make_position(session, stock_id="2330", buy_price=100.0, shares=1000):
    import src.services.trade_service as svc

    pos = svc.create_position(session, stock_id, "台積電", "MANUAL", date(2026, 10, 30))
    svc.add_execution(
        session,
        pos.id,
        "BUY",
        date(2026, 10, 31),
        execution_price=Decimal(str(buy_price)),
        shares=shares,
        actual_fee=Decimal("0"),
        transaction_tax=Decimal("0"),
    )
    return pos


# ── get_latest_price ──────────────────────────────────────────────────────────


class TestGetLatestPrice:
    def test_no_data_returns_none_triple(self):
        from src.services.actual_position_service import get_latest_price

        session = _make_session()
        price, price_date, age = get_latest_price(session, "9999")
        assert price is None
        assert price_date is None
        assert age is None
        session.rollback()

    def test_returns_latest_close(self):
        from src.services.actual_position_service import get_latest_price

        session = _make_session()
        _add_price(session, "2330", date(2026, 10, 20), 900.0)
        _add_price(session, "2330", date(2026, 10, 21), 920.0)
        price, price_date, _ = get_latest_price(session, "2330")
        assert price == 920.0
        assert price_date == date(2026, 10, 21)
        session.rollback()

    def test_age_days_calculated(self):
        from src.services.actual_position_service import get_latest_price

        session = _make_session()
        old = date.today() - timedelta(days=10)
        _add_price(session, "2330", old, 850.0)
        _, _, age = get_latest_price(session, "2330")
        assert age == 10
        session.rollback()

    def test_isolates_by_stock_id(self):
        from src.services.actual_position_service import get_latest_price

        session = _make_session()
        _add_price(session, "2330", date(2026, 10, 21), 920.0)
        _add_price(session, "2454", date(2026, 10, 21), 1100.0)
        price_2330, _, _ = get_latest_price(session, "2330")
        price_2454, _, _ = get_latest_price(session, "2454")
        assert price_2330 == 920.0
        assert price_2454 == 1100.0
        session.rollback()


# ── calc_unrealized_pnl ───────────────────────────────────────────────────────


class TestCalcUnrealizedPnl:
    def test_profit(self):
        from src.services.actual_position_service import calc_unrealized_pnl

        result = calc_unrealized_pnl(Decimal("100"), 1000, 120.0)
        assert result == Decimal("20000")

    def test_loss(self):
        from src.services.actual_position_service import calc_unrealized_pnl

        result = calc_unrealized_pnl(Decimal("100"), 1000, 80.0)
        assert result == Decimal("-20000")

    def test_zero_remaining_shares(self):
        from src.services.actual_position_service import calc_unrealized_pnl

        result = calc_unrealized_pnl(Decimal("100"), 0, 120.0)
        assert result == Decimal("0")

    def test_break_even(self):
        from src.services.actual_position_service import calc_unrealized_pnl

        result = calc_unrealized_pnl(Decimal("100"), 500, 100.0)
        assert result == Decimal("0")


# ── enrich_positions ──────────────────────────────────────────────────────────


class TestEnrichPositions:
    def test_no_price_data(self):
        from src.services.actual_position_service import enrich_positions

        session = _make_session()
        pos = _make_position(session, "9999")
        enriched = enrich_positions(session, [pos])
        e = enriched[0]
        assert e["current_price"] is None
        assert e["unrealized_pnl"] is None
        assert e["price_stale"] is None
        session.rollback()

    def test_fresh_price_computes_pnl(self):
        from src.services.actual_position_service import enrich_positions

        session = _make_session()
        pos = _make_position(session, "2330", buy_price=100.0, shares=1000)
        _add_price(session, "2330", date.today() - timedelta(days=1), 120.0)
        enriched = enrich_positions(session, [pos])
        e = enriched[0]
        assert e["current_price"] == 120.0
        assert e["unrealized_pnl"] == pytest.approx(20000.0)
        assert e["unrealized_pct"] == pytest.approx(20.0)
        assert e["price_stale"] is False
        session.rollback()

    def test_stale_price_flagged(self):
        from src.services.actual_position_service import enrich_positions

        session = _make_session()
        pos = _make_position(session, "2330")
        _add_price(session, "2330", date.today() - timedelta(days=10), 110.0)
        enriched = enrich_positions(session, [pos])
        e = enriched[0]
        assert e["price_stale"] is True
        assert e["price_age_days"] == 10

    def test_returns_json_serializable_types(self):
        """enriched dict 必須全部是純 Python 型別（可序列化）。"""
        from src.services.actual_position_service import enrich_positions

        session = _make_session()
        pos = _make_position(session, "2330")
        _add_price(session, "2330", date.today() - timedelta(days=1), 120.0)
        enriched = enrich_positions(session, [pos])
        e = enriched[0]
        import json

        json.dumps(e)  # should not raise
        session.rollback()

    def test_zero_remaining_no_pnl(self):
        """已平倉持倉：remaining=0，unrealized_pnl 應為 None（不計算）。"""
        import src.services.trade_service as svc
        from src.services.actual_position_service import enrich_positions

        session = _make_session()
        pos = _make_position(session, "2330", buy_price=100.0, shares=1000)
        svc.add_execution(
            session,
            pos.id,
            "SELL",
            date(2026, 11, 1),
            execution_price=Decimal("120"),
            shares=1000,
            actual_fee=Decimal("0"),
            transaction_tax=Decimal("0"),
        )
        assert pos.status == "closed"
        _add_price(session, "2330", date.today() - timedelta(days=1), 120.0)
        enriched = enrich_positions(session, [pos])
        e = enriched[0]
        assert e["unrealized_pnl"] is None
        session.rollback()
