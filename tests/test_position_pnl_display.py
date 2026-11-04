"""
tests/test_position_pnl_display.py — UI P&L Toast 顯示邏輯驗證

驗證 dashboard/_pages/position.py 中 partial_sell / full_sell toast 顯示的
P&L 資料來源契約：
  - 部分賣出 toast：本次已實現淨損益 = realized_after - realized_before
  - 全部賣出 toast：累計已實現淨損益 = pos.realized_pnl（全倉出場後的累計值）

這些測試不測試 Streamlit 渲染層（需要完整 Streamlit session），
而是驗證 UI 所依賴的 Trade Service / ORM 資料層契約。
Streamlit rerun 行為由 Browser E2E 測試（browser_e2e_test.py）覆蓋。

覆蓋場景：
  T01  BUY → 部分賣出：incremental P&L = cumulative（無前次已實現）
  T02  BUY → ADD → 部分賣出：incremental P&L < cumulative
  T03  BUY → ADD → 部分賣出 → 全部賣出：cumulative P&L（E2E reconciliation 場景）
  T04  費用扣除：手續費從淨損益中正確扣除
  T05  負損益：賣出低於均價
  T06  零損益：賣出等於均價（無費用）
  T07  已關倉：全數賣出後 status=closed, remaining=0
  T08  idempotent SELL：重複提交不雙重計入損益
  T09  多次部分賣出：每次 incremental 正確累加至 cumulative
  T10  Transaction tax 正確扣除（從 transaction_tax 欄位）
"""

from datetime import date
from decimal import Decimal

import pytest

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_session():
    from sqlalchemy import create_engine

    from src.database import get_session, init_db

    engine = create_engine("sqlite:///:memory:")
    init_db(engine)
    return get_session(engine)


def _d(v) -> Decimal:
    return Decimal(str(v))


def _create_pos(session, stock_id="2330"):
    import src.services.trade_service as svc

    return svc.create_position(
        session,
        stock_id,
        "測試股票",
        "MANUAL",
        date(2026, 10, 1),
    )


def _buy(session, pos_id, price, shares, fee=0, d=date(2026, 10, 1)):
    import src.services.trade_service as svc

    svc.add_execution(
        session,
        pos_id,
        "BUY",
        d,
        execution_price=_d(price),
        shares=shares,
        actual_fee=_d(fee),
        transaction_tax=_d(0),
    )


def _sell(session, pos_id, price, shares, fee=0, tax=0, d=date(2026, 11, 1), key=None):
    import src.services.trade_service as svc

    svc.add_execution(
        session,
        pos_id,
        "SELL",
        d,
        execution_price=_d(price),
        shares=shares,
        actual_fee=_d(fee),
        transaction_tax=_d(tax),
        idempotency_key=key,
    )


def _realized(pos) -> float:
    """Return pos.realized_pnl as float for assertion convenience."""
    return float(pos.realized_pnl)


# ── T01: BUY → 部分賣出（incremental = cumulative，無前次已實現） ──────────────


class TestT01PartialSellIncrementalNoPrevious:
    def test_incremental_equals_cumulative_when_no_prior_sells(self):
        """首次部分賣出：incremental P&L = cumulative（prev_realized=0）。"""
        session = _make_session()
        pos = _create_pos(session)
        _buy(session, pos.id, 100, 1000, fee=142)

        prev_realized = _realized(pos)  # 0.0 before any SELL
        _sell(session, pos.id, 110, 500, fee=214)

        this_pnl = _realized(pos) - prev_realized
        cumulative = _realized(pos)

        # net for this SELL: (110×500 - 214) - (100.142×500) = 54786 - 50071 = 4715
        # exact: cost_basis=100142, avg=100.142, cost_of_sold=50071, realized=54786-50071=4715
        assert this_pnl == cumulative
        assert this_pnl > 0
        assert pos.status == "partially_closed"
        assert pos.remaining_shares == 500
        session.rollback()


# ── T02: BUY → ADD → 部分賣出（incremental < cumulative，有前次 BUY 均攤） ────


class TestT02BuyAddPartialSellIncremental:
    def test_incremental_after_add_buy(self):
        """BUY + ADD → 部分賣出：incremental = cumulative（首次 SELL）。"""
        session = _make_session()
        pos = _create_pos(session)
        _buy(session, pos.id, 100, 1000, fee=142)
        _buy(session, pos.id, 105, 500, fee=75, d=date(2026, 10, 2))

        # avg_cost = (100142 + 52575) / 1500 = 101.8113...
        prev_realized = _realized(pos)  # 0.0 (no prior SELLs)
        assert prev_realized == 0.0

        _sell(session, pos.id, 110, 500, fee=214)

        this_pnl = _realized(pos) - prev_realized
        # realized = (110×500 - 214) - (101.8113...×500) = 54786 - 50905.67 = 3880.33
        assert abs(this_pnl - 3880.33) < 0.01
        assert pos.remaining_shares == 1000
        session.rollback()


# ── T03: BUY → ADD → 部分賣出 → 全部賣出（E2E reconciliation 場景） ──────────


class TestT03FullE2EReconciliation:
    """
    與 phase1b_release_readiness.md §C.2 完全一致的場景：
      BUY 1000@100 fee=142
      ADD  500@105 fee=75
      SELL 500@110 fee=214  → incremental = 3880.33
      SELL 1000@115 fee=442 → cumulative  = 16627.00
    """

    def setup_method(self):
        self.session = _make_session()
        self.pos = _create_pos(self.session)
        _buy(self.session, self.pos.id, 100, 1000, fee=142)
        _buy(self.session, self.pos.id, 105, 500, fee=75, d=date(2026, 10, 2))

    def test_partial_sell_incremental_pnl(self):
        prev = _realized(self.pos)
        _sell(self.session, self.pos.id, 110, 500, fee=214)
        incremental = _realized(self.pos) - prev
        assert abs(incremental - 3880.33) < 0.01, f"expected 3880.33, got {incremental}"

    def test_full_sell_cumulative_pnl(self):
        _sell(self.session, self.pos.id, 110, 500, fee=214)
        _sell(self.session, self.pos.id, 115, 1000, fee=442, d=date(2026, 11, 2))
        cumulative = _realized(self.pos)
        assert abs(cumulative - 16627.00) < 0.01, f"expected 16627.00, got {cumulative}"

    def test_wac_after_add(self):
        wac = float(self.pos.avg_cost_per_share)
        assert abs(wac - 101.8113) < 0.0001, f"expected WAC=101.8113, got {wac}"

    def test_full_sell_closes_position(self):
        _sell(self.session, self.pos.id, 110, 500, fee=214)
        _sell(self.session, self.pos.id, 115, 1000, fee=442, d=date(2026, 11, 2))
        assert self.pos.status == "closed"
        assert self.pos.remaining_shares == 0

    def teardown_method(self):
        self.session.rollback()


# ── T04: 費用扣除 ──────────────────────────────────────────────────────────────


class TestT04FeeDeduction:
    def test_fee_reduces_realized_pnl(self):
        """手續費正確從淨損益扣除。"""
        session = _make_session()
        pos = _create_pos(session)
        _buy(session, pos.id, 100, 1000, fee=0)  # avg_cost = 100.0

        # SELL 1000 @ 110, fee=0: gross = 10000, net = 10000
        _sell(session, pos.id, 110, 1000, fee=0)
        no_fee_pnl = _realized(pos)
        session.rollback()

        session2 = _make_session()
        pos2 = _create_pos(session2)
        _buy(session2, pos2.id, 100, 1000, fee=0)

        # SELL 1000 @ 110, fee=200: net = 10000 - 200 = 9800
        _sell(session2, pos2.id, 110, 1000, fee=200)
        fee_pnl = _realized(pos2)

        assert no_fee_pnl - fee_pnl == pytest.approx(200.0)
        assert fee_pnl == pytest.approx(9800.0)
        session2.rollback()


# ── T05: 負損益 ────────────────────────────────────────────────────────────────


class TestT05NegativePnl:
    def test_sell_below_avg_cost_gives_negative_pnl(self):
        """賣出低於均價時，已實現損益為負值。"""
        session = _make_session()
        pos = _create_pos(session)
        _buy(session, pos.id, 100, 1000, fee=0)

        _sell(session, pos.id, 90, 1000, fee=0)  # sell below cost

        cumulative = _realized(pos)
        assert cumulative == pytest.approx(-10000.0)
        assert pos.status == "closed"
        session.rollback()

    def test_sell_below_avg_cost_with_fee(self):
        """賣出低於均價加手續費，損失更大。"""
        session = _make_session()
        pos = _create_pos(session)
        _buy(session, pos.id, 100, 1000, fee=0)

        # realized = (90×1000 - 500) - 100×1000 = 89500 - 100000 = -10500
        _sell(session, pos.id, 90, 1000, fee=500)

        assert _realized(pos) == pytest.approx(-10500.0)
        session.rollback()


# ── T06: 零損益 ────────────────────────────────────────────────────────────────


class TestT06ZeroPnl:
    def test_sell_at_avg_cost_zero_pnl(self):
        """賣出等於均價（無費用）→ 損益為零。"""
        session = _make_session()
        pos = _create_pos(session)
        _buy(session, pos.id, 100, 1000, fee=0)

        _sell(session, pos.id, 100, 1000, fee=0)

        assert _realized(pos) == pytest.approx(0.0)
        assert pos.status == "closed"
        session.rollback()


# ── T07: 全數賣出後 closed ─────────────────────────────────────────────────────


class TestT07ClosedPosition:
    def test_full_sell_sets_closed_status(self):
        """全數賣出後 status=closed, remaining=0, close_date 已設定。"""
        session = _make_session()
        pos = _create_pos(session)
        _buy(session, pos.id, 100, 1000, fee=0)

        sell_date = date(2026, 11, 15)
        _sell(session, pos.id, 110, 1000, fee=0, d=sell_date)

        assert pos.status == "closed"
        assert pos.remaining_shares == 0
        assert pos.close_date == sell_date
        session.rollback()

    def test_partial_sell_sets_partially_closed(self):
        """部分賣出後 status=partially_closed, remaining > 0。"""
        session = _make_session()
        pos = _create_pos(session)
        _buy(session, pos.id, 100, 1000, fee=0)

        _sell(session, pos.id, 110, 400, fee=0)

        assert pos.status == "partially_closed"
        assert pos.remaining_shares == 600
        assert pos.close_date is None
        session.rollback()


# ── T08: Idempotent SELL ───────────────────────────────────────────────────────


class TestT08IdempotentSell:
    def test_double_submit_does_not_double_pnl(self):
        """相同 idempotency_key 的重複提交不雙重計入損益。"""
        session = _make_session()
        pos = _create_pos(session)
        _buy(session, pos.id, 100, 1000, fee=0)

        key = "test-idem-key-001"
        _sell(session, pos.id, 110, 500, fee=0, key=key)
        pnl_after_first = _realized(pos)

        _sell(session, pos.id, 110, 500, fee=0, key=key)  # duplicate
        pnl_after_second = _realized(pos)

        assert pnl_after_first == pnl_after_second, "重複提交不應改變 realized_pnl"
        assert pos.remaining_shares == 500, "重複提交不應多扣股數"
        session.rollback()


# ── T09: 多次部分賣出 ──────────────────────────────────────────────────────────


class TestT09MultiplePartialSells:
    def test_multiple_partial_sells_cumulate_correctly(self):
        """三次部分賣出：每次 incremental 加總等於最終 cumulative。"""
        session = _make_session()
        pos = _create_pos(session)
        _buy(session, pos.id, 100, 3000, fee=0)  # avg_cost=100, 3000 shares

        # sell 1
        prev1 = _realized(pos)
        _sell(session, pos.id, 110, 1000, fee=0, d=date(2026, 11, 1))
        inc1 = _realized(pos) - prev1  # (110-100)×1000 = 10000

        # sell 2
        prev2 = _realized(pos)
        _sell(session, pos.id, 115, 1000, fee=0, d=date(2026, 11, 2))
        inc2 = _realized(pos) - prev2  # (115-100)×1000 = 15000

        # sell 3
        prev3 = _realized(pos)
        _sell(session, pos.id, 108, 1000, fee=0, d=date(2026, 11, 3))
        inc3 = _realized(pos) - prev3  # (108-100)×1000 = 8000

        cumulative = _realized(pos)
        assert abs(inc1 - 10000) < 0.01
        assert abs(inc2 - 15000) < 0.01
        assert abs(inc3 - 8000) < 0.01
        assert abs((inc1 + inc2 + inc3) - cumulative) < 0.01
        assert abs(cumulative - 33000) < 0.01
        assert pos.status == "closed"
        session.rollback()


# ── T10: Transaction Tax ───────────────────────────────────────────────────────


class TestT10TransactionTax:
    def test_transaction_tax_deducted_separately_from_fee(self):
        """actual_fee 和 transaction_tax 分別都從淨損益扣除。"""
        session = _make_session()
        pos = _create_pos(session)
        _buy(session, pos.id, 100, 1000, fee=0)

        # fee=100, tax=300 → both deducted
        # realized = (110×1000 - 100 - 300) - 100×1000 = 9600
        _sell(session, pos.id, 110, 1000, fee=100, tax=300)

        assert _realized(pos) == pytest.approx(9600.0)
        session.rollback()
