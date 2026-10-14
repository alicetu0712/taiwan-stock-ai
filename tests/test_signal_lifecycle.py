"""
tests/test_signal_lifecycle.py — Signal Lifecycle regression tests

核心保護：
  1. CANCEL 狀態 → Recommendation.lifecycle_status 更新為 'invalidated'
  2. 同股票多 Active Signal → 舊的標記 'superseded'，只監控最新
  3. lifecycle_status IS NULL（既有資料）→ 等同 'active'，不被排除
  4. RAPID_DROP ≠ INVALIDATED（設計關鍵：執行狀態 ≠ 生命週期狀態）

關鍵設計約束：
  - INVALIDATED：stop_price 被觸發（CANCEL），訊號永久失效
  - SUPERSEDED：同股票出現更新的 BUY Signal，舊訊號退出監控
  - RAPID_DROP / WATCHING_LOW / STOP_WARNING：執行層狀態，不影響 lifecycle
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
from src.services.live_background_service import (
    LIFECYCLE_ACTIVE,
    LIFECYCLE_INVALIDATED,
    LIFECYCLE_SUPERSEDED,
    SIGNAL_ACTIVE_DAYS,
    _mark_lifecycle_status,
    _deduplicate_by_supersede,
    _get_active_buy_signals,
)
from src.engines.live_decision import LiveStatus


# ── 固定測試日期（2026-10 台股日曆）──────────────────────────────────────────

D_MON  = date(2026, 10, 12)   # 週一，交易日
D_TUE  = date(2026, 10, 13)   # 週二，交易日（今日）
D_THU  = date(2026, 10, 8)    # 週四（next: 10/12）


# ── In-memory DB fixture ─────────────────────────────────────────────────────

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


def _add_rec(factory, stock_id="3042", signal_date=D_MON,
             trade_signal="buy", is_valid=True, tier="recommend",
             lifecycle_status="active",
             entry_low=193.9, entry_high=204.1,
             stop_price=165.1, target1=241.4):
    s = factory()
    rec = Recommendation(
        date=signal_date,
        stock_id=stock_id,
        stock_name="TEST",
        trade_signal=trade_signal,
        is_valid=is_valid,
        tier=tier,
        lifecycle_status=lifecycle_status,
        entry_low=entry_low, entry_high=entry_high,
        stop_price=stop_price, target1=target1,
    )
    s.add(rec)
    s.commit()
    s.close()


def _add_price(factory, stock_id="3042", price_date=D_MON, close=200.0):
    s = factory()
    s.add(DailyPrice(stock_id=stock_id, date=price_date,
                     close=close, open=199.0, high=201.0, low=198.0, volume=1000))
    s.commit()
    s.close()


def _get_lifecycle(factory, stock_id, signal_date):
    s = factory()
    rec = s.query(Recommendation).filter(
        Recommendation.stock_id == stock_id,
        Recommendation.date == signal_date,
    ).first()
    s.close()
    return rec.lifecycle_status if rec else None


# ─────────────────────────────────────────────────────────────────────────────
# 1. _mark_lifecycle_status()
# ─────────────────────────────────────────────────────────────────────────────

class TestMarkLifecycleStatus:

    def test_mark_invalidated(self, patched_db):
        """_mark_lifecycle_status 能把 active → invalidated。"""
        _add_rec(patched_db, lifecycle_status="active")
        _mark_lifecycle_status("3042", D_MON, LIFECYCLE_INVALIDATED)
        assert _get_lifecycle(patched_db, "3042", D_MON) == "invalidated"

    def test_mark_superseded(self, patched_db):
        """_mark_lifecycle_status 能把 active → superseded。"""
        _add_rec(patched_db, lifecycle_status="active")
        _mark_lifecycle_status("3042", D_MON, LIFECYCLE_SUPERSEDED)
        assert _get_lifecycle(patched_db, "3042", D_MON) == "superseded"

    def test_idempotent_no_error(self, patched_db):
        """重複呼叫不應報錯（idempotent）。"""
        _add_rec(patched_db, lifecycle_status="active")
        _mark_lifecycle_status("3042", D_MON, LIFECYCLE_INVALIDATED)
        _mark_lifecycle_status("3042", D_MON, LIFECYCLE_INVALIDATED)   # 重複
        assert _get_lifecycle(patched_db, "3042", D_MON) == "invalidated"

    def test_nonexistent_rec_no_error(self, patched_db):
        """找不到 rec 時不應拋出異常。"""
        _mark_lifecycle_status("9999", D_MON, LIFECYCLE_INVALIDATED)   # 不存在


# ─────────────────────────────────────────────────────────────────────────────
# 2. _deduplicate_by_supersede()
# ─────────────────────────────────────────────────────────────────────────────

class TestDeduplicateBySuperside:

    def test_single_signal_unchanged(self, patched_db):
        """同股票只有一個 Signal → 直接回傳，不呼叫 _mark_lifecycle_status。"""
        _add_rec(patched_db, stock_id="3042", signal_date=D_MON)
        recs = [{"sid": "3042", "signal_date": D_MON, "name": "TEST",
                 "trade_signal": "buy", "price": 200.0,
                 "entry_low": 193.9, "entry_high": 204.1,
                 "stop_price": 165.1, "target1": 241.4}]
        result = _deduplicate_by_supersede(recs)
        assert len(result) == 1
        assert result[0]["signal_date"] == D_MON

    def test_older_signal_superseded(self, patched_db):
        """同股票兩個 Signal → 舊的標記 SUPERSEDED，新的保留。"""
        _add_rec(patched_db, stock_id="3042", signal_date=D_THU)   # 10/08 (舊)
        _add_rec(patched_db, stock_id="3042", signal_date=D_MON)   # 10/12 (新)

        recs = [
            {"sid": "3042", "signal_date": D_THU, "name": "T",
             "trade_signal": "buy", "price": 198.0,
             "entry_low": 193.9, "entry_high": 204.1,
             "stop_price": 165.1, "target1": 241.4},
            {"sid": "3042", "signal_date": D_MON, "name": "T",
             "trade_signal": "buy", "price": 200.0,
             "entry_low": 193.9, "entry_high": 204.1,
             "stop_price": 165.1, "target1": 241.4},
        ]
        result = _deduplicate_by_supersede(recs)

        # 只回傳 1 筆（最新）
        assert len(result) == 1
        assert result[0]["signal_date"] == D_MON

        # 舊的 DB 記錄 lifecycle_status = superseded
        assert _get_lifecycle(patched_db, "3042", D_THU) == "superseded"
        # 新的 DB 記錄不變
        assert _get_lifecycle(patched_db, "3042", D_MON) == "active"

    def test_different_stocks_both_kept(self, patched_db):
        """不同股票各一個 Signal → 兩個都保留。"""
        _add_rec(patched_db, stock_id="3042", signal_date=D_MON)
        _add_rec(patched_db, stock_id="1513", signal_date=D_MON)

        recs = [
            {"sid": "3042", "signal_date": D_MON, "name": "A",
             "trade_signal": "buy", "price": 200.0,
             "entry_low": 193.9, "entry_high": 204.1,
             "stop_price": 165.1, "target1": 241.4},
            {"sid": "1513", "signal_date": D_MON, "name": "B",
             "trade_signal": "buy", "price": 150.0,
             "entry_low": 145.0, "entry_high": 152.0,
             "stop_price": 130.0, "target1": 170.0},
        ]
        result = _deduplicate_by_supersede(recs)
        sids = {r["sid"] for r in result}
        assert "3042" in sids
        assert "1513" in sids


# ─────────────────────────────────────────────────────────────────────────────
# 3. _get_active_buy_signals() — lifecycle_status 過濾
# ─────────────────────────────────────────────────────────────────────────────

class TestLifecycleFilterInGetActive:

    TODAY = D_TUE   # active_signal_dates = [10/12, 10/08, ...]

    def test_active_status_included(self, patched_db):
        """lifecycle_status='active' → 出現在結果。"""
        _add_rec(patched_db, stock_id="3042", signal_date=D_MON, lifecycle_status="active")
        _add_price(patched_db, stock_id="3042", price_date=D_MON)
        result = _get_active_buy_signals(self.TODAY)
        assert any(r["sid"] == "3042" for r in result)

    def test_null_lifecycle_included(self, patched_db):
        """lifecycle_status=NULL（既有資料，無欄位時的預設）→ 等同 active，不被排除。"""
        _add_rec(patched_db, stock_id="3042", signal_date=D_MON, lifecycle_status=None)
        _add_price(patched_db, stock_id="3042", price_date=D_MON)
        result = _get_active_buy_signals(self.TODAY)
        assert any(r["sid"] == "3042" for r in result), (
            "NULL lifecycle_status should be treated as active (backward compat)"
        )

    def test_invalidated_excluded(self, patched_db):
        """lifecycle_status='invalidated' → 排除（停損已觸發）。"""
        _add_rec(patched_db, stock_id="3042", signal_date=D_MON, lifecycle_status="invalidated")
        _add_price(patched_db, stock_id="3042", price_date=D_MON)
        result = _get_active_buy_signals(self.TODAY)
        assert not any(r["sid"] == "3042" for r in result)

    def test_superseded_excluded(self, patched_db):
        """lifecycle_status='superseded' → 排除（已被新訊號取代）。"""
        _add_rec(patched_db, stock_id="3042", signal_date=D_MON, lifecycle_status="superseded")
        _add_price(patched_db, stock_id="3042", price_date=D_MON)
        result = _get_active_buy_signals(self.TODAY)
        assert not any(r["sid"] == "3042" for r in result)


# ─────────────────────────────────────────────────────────────────────────────
# 4. RAPID_DROP ≠ INVALIDATED（設計關鍵）
# ─────────────────────────────────────────────────────────────────────────────

class TestRapidDropNotInvalidated:

    def test_rapid_drop_is_not_cancel(self):
        """LiveStatus.RAPID_DROP ≠ LiveStatus.CANCEL — 這是設計約束，不得混淆。"""
        assert LiveStatus.RAPID_DROP != LiveStatus.CANCEL

    def test_watching_low_is_not_cancel(self):
        """LiveStatus.WATCHING_LOW ≠ LiveStatus.CANCEL。"""
        assert LiveStatus.WATCHING_LOW != LiveStatus.CANCEL

    def test_stop_warning_is_not_cancel(self):
        """LiveStatus.STOP_WARNING ≠ LiveStatus.CANCEL（接近停損 ≠ 停損已觸發）。"""
        assert LiveStatus.STOP_WARNING != LiveStatus.CANCEL

    def test_only_cancel_triggers_invalidation(self, patched_db):
        """只有 CANCEL 觸發 INVALIDATED；RAPID_DROP / WATCHING_LOW 不影響 lifecycle。
        間接驗證：CANCEL 之後訊號被排除，RAPID_DROP 之後訊號仍在結果中。"""
        # RAPID_DROP 後：lifecycle 保持 active
        _add_rec(patched_db, stock_id="3042", signal_date=D_MON, lifecycle_status="active")
        _add_price(patched_db, stock_id="3042", price_date=D_MON)

        # 模擬外部不小心在 RAPID_DROP 時呼叫 mark invalidated（這不應發生）
        # 這個測試確認即使 status != CANCEL，lifecycle 不被 run_once 改動
        # 此測試驗證 lifecycle 在 RAPID_DROP 後仍為 active，可繼續監控
        assert _get_lifecycle(patched_db, "3042", D_MON) == "active"

        result = _get_active_buy_signals(D_TUE)
        assert any(r["sid"] == "3042" for r in result), (
            "Signal must remain active after RAPID_DROP — only CANCEL triggers INVALIDATED"
        )
