"""
tests/test_live_execution_service.py — record_if_transition() 資料完整性測試

核心不變量（每個測試都在保護其中一條）：
  1. 首次觀察（DB 無記錄）→ 必定寫入，prev_status=None
  2. 相同狀態持續 → 不寫入（idempotent，防每 10 秒一筆）
  3. 狀態改變 → 寫入，prev_status 來自 DB（不是 caller 傳入）
  4. 瀏覽器重開 / 多裝置 → DB 去重，不產生重複事件
  5. (stock_id, signal_date) 獨立 → 不同日期的狀態機互不影響
  6. live_rule_version 獨立 → 不同版本視為不同狀態機

使用 SQLite in-memory + StaticPool，完全不依賴 production DB。
所有測試透過 monkeypatch 替換 src.database.get_session。
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

from src.database import Base, LiveExecutionEvent
from src.engines.live_decision import LiveDecision, LiveStatus, _STATUS_META


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_ld(
    status: LiveStatus,
    current_price: float = 197.5,
    intraday_low: float = 195.0,
    drop_pct: float = -4.6,
    bounce_pct: float = 1.3,
    rr_current: float = 1.35,
) -> LiveDecision:
    """Build a minimal LiveDecision for testing (bypasses evaluate_entry_status)."""
    meta = _STATUS_META[status]
    return LiveDecision(
        status=status,
        icon=meta["icon"],
        label=meta["label"],
        color=meta["color"],
        bg=meta["bg"],
        reason="test",
        current_price=current_price,
        signal_price=204.5,
        pct_from_signal=-3.4,
        pct_from_entry=None,
        entry_low=193.9,
        entry_high=204.1,
        stop_price=165.1,
        target1=241.4,
        intraday_low=intraday_low,
        rr_current=rr_current,
        drop_pct=drop_pct,
        bounce_pct=bounce_pct,
        plain_text="",
    )


_REC = {
    "price":      204.5,
    "entry_low":  193.9,
    "entry_high": 204.1,
    "stop_price": 165.1,
    "target1":    241.4,
}

STOCK  = "3042"
SDATE  = date(2026, 10, 8)   # signal date


# ── In-memory DB fixture ──────────────────────────────────────────────────────

@pytest.fixture
def session_factory():
    """
    SQLite in-memory DB with StaticPool so all connections share the same DB.
    Yields a sessionmaker; each test gets a fresh DB.
    """
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
def patched_get_session(session_factory):
    """
    Patches src.database.get_session to return sessions from the test DB.
    Also patches LiveExecutionEvent reference so queries hit the same DB.
    """
    def _get_test_session(engine=None):
        return session_factory()

    with patch("src.database.get_session", side_effect=_get_test_session):
        yield session_factory


# ── Convenience: count records in test DB ────────────────────────────────────

def _count(factory, **filters) -> int:
    s = factory()
    q = s.query(LiveExecutionEvent)
    for k, v in filters.items():
        q = q.filter(getattr(LiveExecutionEvent, k) == v)
    n = q.count()
    s.close()
    return n


def _last(factory, stock_id=STOCK, signal_date=SDATE) -> LiveExecutionEvent | None:
    from src.services.live_execution_service import LIVE_RULE_VERSION
    s = factory()
    row = (
        s.query(LiveExecutionEvent)
        .filter(
            LiveExecutionEvent.stock_id == stock_id,
            LiveExecutionEvent.signal_date == signal_date,
            LiveExecutionEvent.live_rule_version == LIVE_RULE_VERSION,
        )
        .order_by(LiveExecutionEvent.observed_at.desc())
        .first()
    )
    s.expunge_all()
    s.close()
    return row


# ─────────────────────────────────────────────────────────────────────────────
# 1. 首次觀察
# ─────────────────────────────────────────────────────────────────────────────

class TestFirstObservation:

    def test_first_observation_writes(self, patched_get_session):
        from src.services.live_execution_service import record_if_transition
        ld = _make_ld(LiveStatus.RAPID_DROP)
        written = record_if_transition(STOCK, SDATE, ld, _REC, "20261008", "valid")
        assert written is True

    def test_first_observation_count(self, patched_get_session):
        from src.services.live_execution_service import record_if_transition
        ld = _make_ld(LiveStatus.RAPID_DROP)
        record_if_transition(STOCK, SDATE, ld, _REC, "20261008", "valid")
        assert _count(patched_get_session) == 1

    def test_first_observation_prev_status_is_none(self, patched_get_session):
        from src.services.live_execution_service import record_if_transition
        ld = _make_ld(LiveStatus.RAPID_DROP)
        record_if_transition(STOCK, SDATE, ld, _REC, "20261008", "valid")
        row = _last(patched_get_session)
        assert row is not None
        assert row.prev_status is None

    def test_first_observation_correct_live_status(self, patched_get_session):
        from src.services.live_execution_service import record_if_transition
        ld = _make_ld(LiveStatus.WATCHING_LOW)
        record_if_transition(STOCK, SDATE, ld, _REC, "20261008", "valid")
        row = _last(patched_get_session)
        assert row.live_status == "watching_low"


# ─────────────────────────────────────────────────────────────────────────────
# 2. 相同狀態 → 不重複寫入
# ─────────────────────────────────────────────────────────────────────────────

class TestIdempotency:

    def test_same_status_second_call_skips(self, patched_get_session):
        from src.services.live_execution_service import record_if_transition
        ld = _make_ld(LiveStatus.RAPID_DROP)
        record_if_transition(STOCK, SDATE, ld, _REC, "20261008", "valid")
        written = record_if_transition(STOCK, SDATE, ld, _REC, "20261008", "valid")
        assert written is False

    def test_same_status_stays_one_record(self, patched_get_session):
        from src.services.live_execution_service import record_if_transition
        ld = _make_ld(LiveStatus.RAPID_DROP)
        for _ in range(5):   # simulates 5 polls at 10-second intervals
            record_if_transition(STOCK, SDATE, ld, _REC, "20261008", "valid")
        assert _count(patched_get_session) == 1


# ─────────────────────────────────────────────────────────────────────────────
# 3. 狀態改變 → 寫入，prev_status 來自 DB
# ─────────────────────────────────────────────────────────────────────────────

class TestTransition:

    def test_status_change_writes(self, patched_get_session):
        from src.services.live_execution_service import record_if_transition
        record_if_transition(STOCK, SDATE, _make_ld(LiveStatus.RAPID_DROP),   _REC, "20261008", "valid")
        written = record_if_transition(STOCK, SDATE, _make_ld(LiveStatus.WATCHING_LOW), _REC, "20261008", "valid")
        assert written is True

    def test_transition_prev_status_from_db(self, patched_get_session):
        """prev_status in written record must reflect DB truth, not caller assumption."""
        from src.services.live_execution_service import record_if_transition
        record_if_transition(STOCK, SDATE, _make_ld(LiveStatus.RAPID_DROP),   _REC, "20261008", "valid")
        record_if_transition(STOCK, SDATE, _make_ld(LiveStatus.WATCHING_LOW), _REC, "20261008", "valid")
        row = _last(patched_get_session)
        assert row.live_status  == "watching_low"
        assert row.prev_status  == "rapid_drop"   # ← DB truth, not UI session

    def test_full_chain_three_writes(self, patched_get_session):
        """None → rapid_drop → watching_low → entry_reconfirmed: exactly 3 records."""
        from src.services.live_execution_service import record_if_transition
        record_if_transition(STOCK, SDATE, _make_ld(LiveStatus.RAPID_DROP),        _REC, "20261008", "valid")
        record_if_transition(STOCK, SDATE, _make_ld(LiveStatus.WATCHING_LOW),      _REC, "20261008", "valid")
        record_if_transition(STOCK, SDATE, _make_ld(LiveStatus.ENTRY_RECONFIRMED), _REC, "20261008", "valid")
        assert _count(patched_get_session) == 3

    def test_full_chain_correct_prev_linkage(self, patched_get_session):
        """Each event's prev_status must point to the previous event's live_status."""
        from src.services.live_execution_service import record_if_transition
        from src.database import get_session
        record_if_transition(STOCK, SDATE, _make_ld(LiveStatus.RAPID_DROP),        _REC, "20261008", "valid")
        record_if_transition(STOCK, SDATE, _make_ld(LiveStatus.WATCHING_LOW),      _REC, "20261008", "valid")
        record_if_transition(STOCK, SDATE, _make_ld(LiveStatus.ENTRY_RECONFIRMED), _REC, "20261008", "valid")

        s = patched_get_session()
        rows = s.query(LiveExecutionEvent).order_by(LiveExecutionEvent.observed_at).all()
        s.expunge_all()
        s.close()

        assert rows[0].prev_status  is None
        assert rows[0].live_status  == "rapid_drop"
        assert rows[1].prev_status  == "rapid_drop"
        assert rows[1].live_status  == "watching_low"
        assert rows[2].prev_status  == "watching_low"
        assert rows[2].live_status  == "entry_reconfirmed"


# ─────────────────────────────────────────────────────────────────────────────
# 4. 瀏覽器重開 / 多裝置不重複寫
# ─────────────────────────────────────────────────────────────────────────────

class TestBrowserReopenDedup:
    """
    P0 的核心保證：瀏覽器重開後 session_state 清空，但 DB 去重必須阻止重複事件。

    修正前：UI 傳 prev_status=None，函式認為是首次觀察 → 重複寫入。
    修正後：函式自己查 DB，發現已有相同狀態 → 跳過。
    """

    def test_reopen_same_status_no_duplicate(self, patched_get_session):
        from src.services.live_execution_service import record_if_transition
        # 第一個 session：寫入 RAPID_DROP
        record_if_transition(STOCK, SDATE, _make_ld(LiveStatus.RAPID_DROP), _REC, "20261008", "valid")
        # 模擬瀏覽器重開：UI session_state 清空，caller 認為 prev=None
        # 但狀態沒變，record_if_transition 查 DB 會發現已有 rapid_drop → 跳過
        written = record_if_transition(STOCK, SDATE, _make_ld(LiveStatus.RAPID_DROP), _REC, "20261008", "valid")
        assert written is False
        assert _count(patched_get_session) == 1   # 只有一筆

    def test_reopen_different_status_writes(self, patched_get_session):
        from src.services.live_execution_service import record_if_transition
        # 第一個 session：寫入 RAPID_DROP
        record_if_transition(STOCK, SDATE, _make_ld(LiveStatus.RAPID_DROP), _REC, "20261008", "valid")
        # 重開後股價已恢復 → WATCHING_LOW → 這是真正的轉換，應該寫入
        written = record_if_transition(STOCK, SDATE, _make_ld(LiveStatus.WATCHING_LOW), _REC, "20261008", "valid")
        assert written is True

    def test_multi_device_same_status_no_duplicate(self, patched_get_session):
        from src.services.live_execution_service import record_if_transition
        # Mac 和手機同時算出 RAPID_DROP
        ld = _make_ld(LiveStatus.RAPID_DROP)
        r1 = record_if_transition(STOCK, SDATE, ld, _REC, "20261008", "valid")
        r2 = record_if_transition(STOCK, SDATE, ld, _REC, "20261008", "valid")
        assert r1 is True
        assert r2 is False
        assert _count(patched_get_session) == 1


# ─────────────────────────────────────────────────────────────────────────────
# 5. (stock_id, signal_date) 獨立隔離
# ─────────────────────────────────────────────────────────────────────────────

class TestSignalDateIsolation:

    def test_different_dates_independent(self, patched_get_session):
        """同一檔股票，不同訊號日，各自獨立的狀態機。"""
        from src.services.live_execution_service import record_if_transition
        date_a = date(2026, 10, 8)
        date_b = date(2026, 10, 13)
        # date_a：已有 rapid_drop
        record_if_transition(STOCK, date_a, _make_ld(LiveStatus.RAPID_DROP), _REC, "20261008", "valid")
        # date_b：首次觀察 rapid_drop → 應寫（不應被 date_a 的記錄擋住）
        written = record_if_transition(STOCK, date_b, _make_ld(LiveStatus.RAPID_DROP), _REC, "20261013", "valid")
        assert written is True
        assert _count(patched_get_session) == 2

    def test_different_stocks_independent(self, patched_get_session):
        """不同股票，各自獨立的狀態機。"""
        from src.services.live_execution_service import record_if_transition
        r1 = record_if_transition("3042", SDATE, _make_ld(LiveStatus.RAPID_DROP),   _REC, "20261008", "valid")
        r2 = record_if_transition("1513", SDATE, _make_ld(LiveStatus.RAPID_DROP),   _REC, "20261008", "valid")
        assert r1 is True
        assert r2 is True
        assert _count(patched_get_session) == 2


# ─────────────────────────────────────────────────────────────────────────────
# 6. live_rule_version 隔離
# ─────────────────────────────────────────────────────────────────────────────

class TestRuleVersionIsolation:

    def test_different_rule_versions_independent(self, patched_get_session):
        """
        v1.0 和 v1.1 是不同的狀態機。
        如果 v1.0 已有 rapid_drop，用 v1.1 重跑同狀態應仍寫入（首次觀察 v1.1）。
        """
        from src.services import live_execution_service
        from src.engines import live_decision

        ld = _make_ld(LiveStatus.RAPID_DROP)
        original_lrv = live_execution_service.LIVE_RULE_VERSION

        try:
            # v1.0：寫一筆
            live_execution_service.LIVE_RULE_VERSION = "v1.0"
            from src.services.live_execution_service import record_if_transition
            r1 = record_if_transition(STOCK, SDATE, ld, _REC, "20261008", "valid")

            # v1.1：不同版本，應視為獨立（首次觀察 v1.1）
            live_execution_service.LIVE_RULE_VERSION = "v1.1"
            r2 = record_if_transition(STOCK, SDATE, ld, _REC, "20261008", "valid")

            assert r1 is True
            assert r2 is True
            assert _count(patched_get_session) == 2
        finally:
            live_execution_service.LIVE_RULE_VERSION = original_lrv


# ─────────────────────────────────────────────────────────────────────────────
# 7. 欄位完整性
# ─────────────────────────────────────────────────────────────────────────────

class TestFieldIntegrity:

    def test_all_key_fields_persisted(self, patched_get_session):
        """關鍵欄位都必須正確寫入 DB（訊號計劃快照 + 報價品質 + 版本）。"""
        from src.services.live_execution_service import record_if_transition, LIVE_RULE_VERSION
        from src.database import MODEL_VERSION

        ld = _make_ld(LiveStatus.WATCHING_LOW, current_price=197.5, intraday_low=195.0,
                      drop_pct=-4.6, bounce_pct=1.3, rr_current=1.35)
        record_if_transition(STOCK, SDATE, ld, _REC, "20261008", "valid")

        row = _last(patched_get_session)
        assert row.stock_id          == STOCK
        assert row.signal_date       == SDATE
        assert row.signal_price      == 204.5
        assert row.current_price     == 197.5
        assert row.intraday_low      == 195.0
        assert row.drop_pct          == -4.6
        assert row.bounce_pct        == 1.3
        assert row.rr_at_observation == 1.35
        assert row.entry_low         == 193.9
        assert row.stop_price        == 165.1
        assert row.target1           == 241.4
        assert row.quote_trade_date  == "20261008"
        assert row.quote_quality     == "valid"
        assert row.strategy_version  == MODEL_VERSION
        assert row.live_rule_version == LIVE_RULE_VERSION

    def test_quote_quality_preserved(self, patched_get_session):
        """unknown / stale 品質標記必須正確儲存（日後篩選低品質觀察用）。"""
        from src.services.live_execution_service import record_if_transition
        record_if_transition(STOCK, SDATE, _make_ld(LiveStatus.DATE_UNKNOWN), _REC, None, "unknown")
        row = _last(patched_get_session)
        assert row.quote_quality    == "unknown"
        assert row.quote_trade_date is None
