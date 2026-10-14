"""
tests/test_live_signal_diagnostics.py — _select_live_signals() 診斷一致性測試

核心不變量：diagnostics 計數必須與 eligible list 相符
  - diag['eligible_count'] == len(eligible_recs)
  - diag['buy_count'] == actual BUY rows in DB
  - 各排除計數與 buy_count 加總一致（不多計、不少計）

測試矩陣：
  1. 全部 BUY 都是 Non-Core → eligible=0, excl_non_core=buy_count, warning 觸發
  2. 部分 BUY 是 recommend-tier → eligible>0, counts 正確
  3. is_valid=False 的 BUY → 被 excl_invalid 計入，不進 eligible
  4. lifecycle=invalidated → 被 excl_lifecycle 計入，不進 eligible
  5. 無任何 rec（pipeline 沒跑） → total_recs=0, buy_count=0
  6. 有 rec 但全是 WAIT → buy_count=0, eligible=0，不觸發 warning
  7. eligible_count 與 len(eligible_recs) 永遠一致（anti-regression）
"""

import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import Base, Recommendation, DailyPrice


# ── Fixed test dates ──────────────────────────────────────────────────────────

SIG_DATE = date(2026, 10, 13)   # signal_date; exec_date = 10/14
EXEC_DATE = date(2026, 10, 14)  # next_trading_day(SIG_DATE)
TODAY     = date(2026, 10, 14)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def db_factory():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    yield factory
    engine.dispose()


@pytest.fixture
def patched_db(db_factory):
    def _sess(engine=None):
        return db_factory()

    with patch("src.database.get_session", side_effect=_sess):
        yield db_factory


def _add_rec(factory, stock_id, trade_signal="buy", tier="recommend",
             is_valid=True, lifecycle_status="active",
             entry_low=190.0, entry_high=200.0, stop_price=160.0, target1=230.0,
             signal_date=SIG_DATE, stock_name="TEST"):
    s = factory()
    s.add(Recommendation(
        date=signal_date, stock_id=stock_id, stock_name=stock_name,
        trade_signal=trade_signal, tier=tier,
        is_valid=is_valid, lifecycle_status=lifecycle_status,
        entry_low=entry_low, entry_high=entry_high,
        stop_price=stop_price, target1=target1,
        confidence=80.0,
    ))
    s.commit()
    s.close()


def _add_price(factory, stock_id, price_date=SIG_DATE, close=200.0):
    s = factory()
    s.add(DailyPrice(
        stock_id=stock_id, date=price_date,
        close=close, open=199.0, high=201.0, low=198.0, volume=1000,
    ))
    s.commit()
    s.close()


def _run(signal_date=SIG_DATE, today=TODAY):
    """Call _select_live_signals with date.today() patched."""
    from dashboard._pages.live_monitor import _select_live_signals
    with patch("dashboard._pages.live_monitor.date") as mock_date:
        mock_date.today.return_value = today
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
        return _select_live_signals(signal_date)


# ─────────────────────────────────────────────────────────────────────────────
# 核心不變量：eligible_count == len(eligible_recs)
# ─────────────────────────────────────────────────────────────────────────────

class TestEligibleCountConsistency:

    def test_empty_db_counts_match(self, patched_db):
        """DB 無資料：兩者都是 0。"""
        eligible, diag = _run()
        assert diag["eligible_count"] == len(eligible)
        assert diag["eligible_count"] == 0

    def test_one_eligible_signal(self, patched_db):
        """1 個 eligible BUY：list 長度 = eligible_count = 1。"""
        _add_rec(patched_db, "3042")
        _add_price(patched_db, "3042")
        eligible, diag = _run()
        assert diag["eligible_count"] == len(eligible)
        assert diag["eligible_count"] == 1

    def test_multiple_eligible_counts_match(self, patched_db):
        """多個 eligible：list 與 count 永遠一致。"""
        for sid in ["3042", "2302", "3702"]:
            _add_rec(patched_db, sid)
            _add_price(patched_db, sid)
        eligible, diag = _run()
        assert diag["eligible_count"] == len(eligible)
        assert diag["eligible_count"] == 3


# ─────────────────────────────────────────────────────────────────────────────
# 排除計數正確性
# ─────────────────────────────────────────────────────────────────────────────

class TestExclusionCounts:

    def test_all_buy_non_core(self, patched_db):
        """全部 BUY 是 non-core → excl_non_core = buy_count, eligible = 0。"""
        _add_rec(patched_db, "2615", tier="opportunity")
        _add_rec(patched_db, "3023", tier="watch", trade_signal="strong_buy")
        eligible, diag = _run()
        assert diag["buy_count"] == 2
        assert diag["excl_non_core"] == 2
        assert diag["eligible_count"] == 0
        assert len(eligible) == 0

    def test_invalid_buy_excluded(self, patched_db):
        """is_valid=False 的 BUY → excl_invalid 計入，不進 eligible。"""
        _add_rec(patched_db, "3042", is_valid=False)
        _add_price(patched_db, "3042")
        eligible, diag = _run()
        assert diag["buy_count"] == 1
        assert diag["excl_invalid"] == 1
        assert diag["eligible_count"] == 0

    def test_lifecycle_invalidated_excluded(self, patched_db):
        """lifecycle=invalidated → excl_lifecycle 計入，不進 eligible。"""
        _add_rec(patched_db, "3042", lifecycle_status="invalidated")
        _add_price(patched_db, "3042")
        eligible, diag = _run()
        assert diag["buy_count"] == 1
        assert diag["excl_lifecycle"] == 1
        assert diag["eligible_count"] == 0
        assert len(eligible) == 0

    def test_lifecycle_superseded_excluded(self, patched_db):
        """lifecycle=superseded → excl_lifecycle 計入，不進 eligible。"""
        _add_rec(patched_db, "3042", lifecycle_status="superseded")
        _add_price(patched_db, "3042")
        eligible, diag = _run()
        assert diag["excl_lifecycle"] == 1
        assert diag["eligible_count"] == 0

    def test_lifecycle_null_treated_as_active(self, patched_db):
        """lifecycle=NULL（舊資料）→ 等同 active，進入 eligible。"""
        _add_rec(patched_db, "3042", lifecycle_status=None)
        _add_price(patched_db, "3042")
        eligible, diag = _run()
        assert diag["eligible_count"] == 1
        assert len(eligible) == 1

    def test_mixed_tiers_partial_eligible(self, patched_db):
        """混合 tier：recommend BUY 進 eligible，其餘被 excl_non_core。"""
        _add_rec(patched_db, "3042", tier="recommend")        # eligible
        _add_rec(patched_db, "2615", tier="opportunity")      # excl_non_core
        _add_rec(patched_db, "3702", tier="watch", trade_signal="strong_buy")  # excl_non_core
        for sid in ["3042", "2615", "3702"]:
            _add_price(patched_db, sid)
        eligible, diag = _run()
        assert diag["buy_count"] == 3
        assert diag["excl_non_core"] == 2
        assert diag["eligible_count"] == 1

    def test_wait_signal_not_in_buy_count(self, patched_db):
        """WAIT 訊號不計入 buy_count（只顯示 BUY/BUY★）。"""
        _add_rec(patched_db, "1513", trade_signal="wait")
        _add_price(patched_db, "1513")
        eligible, diag = _run()
        assert diag["buy_count"] == 0
        assert diag["eligible_count"] == 0
        assert diag["total_recs"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# 特殊情況
# ─────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:

    def test_no_recommendations_pipeline_not_run(self, patched_db):
        """完全沒有 rec（pipeline 沒跑）→ total_recs=0, buy_count=0。"""
        eligible, diag = _run()
        assert diag["total_recs"] == 0
        assert diag["buy_count"] == 0
        assert diag["eligible_count"] == 0

    def test_only_wait_recs_no_warning(self, patched_db):
        """只有 WAIT，buy_count=0 → 不觸發 warning（warning 只在 buy>0 但 eligible=0）。"""
        _add_rec(patched_db, "1513", trade_signal="wait")
        eligible, diag = _run()
        assert diag["buy_count"] == 0
        assert diag["eligible_count"] == 0
        # warning condition: buy_count > 0 AND eligible == 0 → False
        assert not (diag["buy_count"] > 0 and diag["eligible_count"] == 0)

    def test_buy_count_plus_exclusions_equals_total_buy(self, patched_db):
        """計數一致性：excl_invalid + excl_non_core + excl_lifecycle + eligible = buy_count。"""
        _add_rec(patched_db, "3042", tier="recommend")             # eligible
        _add_rec(patched_db, "2615", tier="opportunity")           # excl_non_core
        _add_rec(patched_db, "9999", is_valid=False)               # excl_invalid
        _add_rec(patched_db, "8888", lifecycle_status="invalidated")  # excl_lifecycle
        for sid in ["3042", "2615", "9999", "8888"]:
            _add_price(patched_db, sid)
        eligible, diag = _run()

        computed_total = (
            diag["excl_invalid"]
            + diag["excl_non_core"]
            + diag["excl_lifecycle"]
            + diag["not_yet_executable"]
            + diag["eligible_count"]
        )
        assert computed_total == diag["buy_count"], (
            f"Counts don't add up: {diag}"
        )

    def test_eligible_stocks_list_matches_eligible_recs(self, patched_db):
        """diag['eligible_stocks'] 的 sids 與 eligible_recs 的 sids 一致。"""
        _add_rec(patched_db, "3042", stock_name="晶技")
        _add_price(patched_db, "3042")
        eligible, diag = _run()
        stock_sids_in_diag = {s for s, _ in diag["eligible_stocks"]}
        stock_sids_in_list = {r.get("sid") for r in eligible}
        assert stock_sids_in_diag == stock_sids_in_list
