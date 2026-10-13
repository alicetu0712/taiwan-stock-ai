"""
tests/test_live_background_service.py — Active Signal 日期邏輯 regression tests

核心保護：LiveExecutionEvent.signal_date 必須與 ForwardSignal.trade_date 對齊。
日期錯一天 → 整批 Forward Alpha 分析無法與 ForwardSignal cohort 對應。

A. _active_signal_dates() — 純日期邏輯（不需 DB）
   1. 週一訊號 → 週二才開始監控
   2. 週四訊號 → 跨假日（10/09）+ 週末 → 下週一（10/12）才開始
   3. 週五訊號 → 跨週末 → 下週一才開始
   4. signal_date == today → exec_date > today → 盤中不能偷跑
   5. 超過 SIGNAL_ACTIVE_DAYS → 不監控
   6. 回傳的日期數量 ≤ SIGNAL_ACTIVE_DAYS

B. _get_active_buy_signals() — DB 過濾邏輯（in-memory DB）
   7. 有效 BUY Signal → 出現在結果
   8. is_valid=False → 排除
   9. trade_signal=wait → 排除
   10. trade_signal=sell → 排除
   11. tier=opportunity → 排除（非 Core Picks）
   12. signal_date == today → 排除（exec_date > today，未到可執行日）
   13. 訊號價從 DailyPrice 正確帶入 rec['price']
   14. rec dict 包含 signal_date 欄位（LiveExecutionEvent 需要）

已知 2026-10 台股日曆（測試使用固定日期避免日曆更新破壞測試）：
  2026-10-07 Wed  TRADING_DAY  → next: 10/08
  2026-10-08 Thu  TRADING_DAY  → next: 10/12  （因 10/09 假日 + 週末）
  2026-10-09 Fri  HOLIDAY
  2026-10-10 Sat  WEEKEND
  2026-10-11 Sun  WEEKEND
  2026-10-12 Mon  TRADING_DAY  → next: 10/13
  2026-10-13 Tue  TRADING_DAY  → next: 10/14
  2026-10-14 Wed  TRADING_DAY  → next: 10/15
  2026-10-16 Fri  TRADING_DAY  → next: 10/19
  2026-10-19 Mon  TRADING_DAY  → next: 10/20
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
    _active_signal_dates,
    _get_active_buy_signals,
    SIGNAL_ACTIVE_DAYS,
)


# ── 固定測試日期（使用已驗證的 2026-10 台股日曆）─────────────────────────────

D_WED_0  = date(2026, 10, 7)    # 週三，交易日
D_THU    = date(2026, 10, 8)    # 週四，交易日（next: 10/12，跨假日+週末）
D_HOL    = date(2026, 10, 9)    # 假日（重陽）
D_SAT    = date(2026, 10, 10)   # 週六
D_SUN    = date(2026, 10, 11)   # 週日
D_MON    = date(2026, 10, 12)   # 週一，交易日
D_TUE    = date(2026, 10, 13)   # 週二，交易日（今日系統日期）
D_WED    = date(2026, 10, 14)   # 週三，交易日
D_FRI    = date(2026, 10, 16)   # 週五，交易日（next: 10/19）
D_MON2   = date(2026, 10, 19)   # 下週一，交易日


# ─────────────────────────────────────────────────────────────────────────────
# A. _active_signal_dates() — 純日期邏輯
# ─────────────────────────────────────────────────────────────────────────────

class TestActiveSignalDates:

    def test_monday_signal_active_tuesday(self):
        """週一 10/12 訊號 → exec=10/13（週二），週二監控時應包含。"""
        result = _active_signal_dates(D_TUE)
        assert D_MON in result, f"10/12 should be active on 10/13, got: {result}"

    def test_thursday_signal_skips_holiday_weekend(self):
        """週四 10/08 訊號 → exec=10/12（跨假日 10/09 + 週末 10/10~11）。
        週一 10/12 監控時應包含 10/08。"""
        result = _active_signal_dates(D_MON)
        assert D_THU in result, f"10/08 should be active on 10/12, got: {result}"

    def test_friday_signal_active_next_monday(self):
        """週五 10/16 訊號 → exec=10/19（下週一），週一才開始監控。"""
        result = _active_signal_dates(D_MON2)
        assert D_FRI in result, f"10/16 should be active on 10/19, got: {result}"

    def test_today_signal_not_active_today(self):
        """signal_date == today → exec_date = tomorrow → 今天盤中不能偷跑。"""
        result = _active_signal_dates(D_TUE)
        assert D_TUE not in result, f"10/13 should NOT be active on 10/13, got: {result}"

    def test_holiday_not_in_signal_dates(self):
        """假日 10/09 不是有效 signal_date（pipeline 不在假日跑），不應出現。"""
        for today in [D_MON, D_TUE, D_WED]:
            result = _active_signal_dates(today)
            assert D_HOL not in result, f"{D_HOL} (holiday) should never be a signal_date"

    def test_weekend_not_in_signal_dates(self):
        """週六/日不是有效 signal_date，不應出現。"""
        for today in [D_MON, D_TUE, D_WED]:
            result = _active_signal_dates(today)
            assert D_SAT not in result, "Saturday should never be a signal_date"
            assert D_SUN not in result, "Sunday should never be a signal_date"

    def test_count_does_not_exceed_signal_active_days(self):
        """回傳的 signal_date 數量 ≤ SIGNAL_ACTIVE_DAYS。"""
        for today in [D_TUE, D_WED, D_MON2]:
            result = _active_signal_dates(today)
            assert len(result) <= SIGNAL_ACTIVE_DAYS, (
                f"Got {len(result)} signal_dates for {today}, max is {SIGNAL_ACTIVE_DAYS}"
            )

    def test_beyond_active_days_excluded(self):
        """第 SIGNAL_ACTIVE_DAYS+1 個交易日的訊號不應被監控（已超出有效期）。"""
        # on 10/14: 3 active dates = [10/13, 10/12, 10/08]
        # 第 4 個往前算是 10/07 → 不應出現
        result = _active_signal_dates(D_WED)   # today = 10/14
        assert len(result) == SIGNAL_ACTIVE_DAYS
        assert D_WED_0 not in result, f"10/07 (4th day) should not be active on 10/14"

    def test_all_returned_dates_are_trading_days(self):
        """_active_signal_dates 只應回傳交易日。"""
        from src.core.trading_calendar import is_trading_day
        for today in [D_TUE, D_WED, D_MON2]:
            for d in _active_signal_dates(today):
                assert is_trading_day(d), f"{d} in result for {today} is not a trading day"

    def test_all_returned_exec_dates_lte_today(self):
        """每個回傳的 signal_date 的 exec_date 必須 ≤ today。"""
        from src.core.trading_calendar import next_trading_day
        for today in [D_TUE, D_WED, D_MON2]:
            for sig_d in _active_signal_dates(today):
                exec_d = next_trading_day(sig_d)
                assert exec_d is not None
                assert exec_d <= today, (
                    f"signal_date={sig_d} → exec_date={exec_d} > today={today}"
                )


# ─────────────────────────────────────────────────────────────────────────────
# B. _get_active_buy_signals() — DB 過濾邏輯
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def db_session_factory():
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
def patched_db(db_session_factory):
    def _test_session(engine=None):
        return db_session_factory()

    with patch("src.database.get_session", side_effect=_test_session):
        yield db_session_factory


def _add_rec(factory, stock_id="3042", signal_date=D_MON, trade_signal="buy",
             is_valid=True, tier="recommend", entry_low=193.9, entry_high=204.1,
             stop_price=165.1, target1=241.4, stock_name="晶技"):
    s = factory()
    s.add(Recommendation(
        date=signal_date,
        stock_id=stock_id,
        stock_name=stock_name,
        trade_signal=trade_signal,
        is_valid=is_valid,
        tier=tier,
        entry_low=entry_low, entry_high=entry_high,
        stop_price=stop_price, target1=target1,
    ))
    s.commit()
    s.close()


def _add_price(factory, stock_id="3042", price_date=D_MON, close=204.5):
    s = factory()
    s.add(DailyPrice(stock_id=stock_id, date=price_date, close=close,
                     open=203.0, high=206.0, low=202.0, volume=5000))
    s.commit()
    s.close()


class TestGetActiveBuySignals:

    # today = D_TUE (10/13); active_signal_dates = [10/12, 10/08, 10/07]
    TODAY = D_TUE

    def test_valid_buy_signal_appears(self, patched_db):
        """有效 BUY Signal 在 active_signal_dates 內 → 出現在結果。"""
        _add_rec(patched_db, signal_date=D_MON)
        _add_price(patched_db, price_date=D_MON)
        result = _get_active_buy_signals(self.TODAY)
        assert any(r["sid"] == "3042" for r in result)

    def test_invalid_rec_excluded(self, patched_db):
        """is_valid=False → 排除（不得進入 Live Forward Dataset）。"""
        _add_rec(patched_db, signal_date=D_MON, is_valid=False)
        _add_price(patched_db, price_date=D_MON)
        result = _get_active_buy_signals(self.TODAY)
        assert not any(r["sid"] == "3042" for r in result)

    def test_wait_signal_excluded(self, patched_db):
        """trade_signal=wait → 排除（只監控 BUY / BUY★）。"""
        _add_rec(patched_db, signal_date=D_MON, trade_signal="wait")
        _add_price(patched_db, price_date=D_MON)
        result = _get_active_buy_signals(self.TODAY)
        assert not any(r["sid"] == "3042" for r in result)

    def test_sell_signal_excluded(self, patched_db):
        """trade_signal=sell → 排除。"""
        _add_rec(patched_db, signal_date=D_MON, trade_signal="sell")
        _add_price(patched_db, price_date=D_MON)
        result = _get_active_buy_signals(self.TODAY)
        assert not any(r["sid"] == "3042" for r in result)

    def test_opportunity_tier_excluded(self, patched_db):
        """tier=opportunity（Rising Opportunities）→ 排除（只監控 Core Picks）。"""
        _add_rec(patched_db, signal_date=D_MON, tier="opportunity")
        _add_price(patched_db, price_date=D_MON)
        result = _get_active_buy_signals(self.TODAY)
        assert not any(r["sid"] == "3042" for r in result)

    def test_signal_from_today_excluded(self, patched_db):
        """signal_date == today → exec_date = tomorrow → 盤中不能偷跑。"""
        # 今天是 10/13，在 DB 塞一筆 10/13 的 BUY
        _add_rec(patched_db, signal_date=self.TODAY)
        _add_price(patched_db, price_date=self.TODAY)
        result = _get_active_buy_signals(self.TODAY)
        # 10/13 exec_date = 10/14 > 10/13 → 不應出現
        assert not any(r["sid"] == "3042" for r in result), (
            "Signal from today should not appear (exec_date > today)"
        )

    def test_signal_price_from_daily_price(self, patched_db):
        """rec['price'] 應從 DailyPrice 取 signal_date 的收盤價。"""
        _add_rec(patched_db, signal_date=D_MON)
        _add_price(patched_db, price_date=D_MON, close=204.5)
        result = _get_active_buy_signals(self.TODAY)
        rec = next((r for r in result if r["sid"] == "3042"), None)
        assert rec is not None
        assert rec["price"] == 204.5

    def test_signal_date_field_in_rec(self, patched_db):
        """rec dict 必須包含 signal_date 欄位（LiveExecutionEvent 需要正確 signal_date）。"""
        _add_rec(patched_db, signal_date=D_MON)
        _add_price(patched_db, price_date=D_MON)
        result = _get_active_buy_signals(self.TODAY)
        rec = next((r for r in result if r["sid"] == "3042"), None)
        assert rec is not None
        assert "signal_date" in rec, "rec dict must have signal_date field"
        assert rec["signal_date"] == D_MON

    def test_strong_buy_also_included(self, patched_db):
        """trade_signal=strong_buy 也應被監控。"""
        _add_rec(patched_db, signal_date=D_MON, trade_signal="strong_buy")
        _add_price(patched_db, price_date=D_MON)
        result = _get_active_buy_signals(self.TODAY)
        assert any(r["sid"] == "3042" for r in result)

    def test_multiple_active_signal_dates(self, patched_db):
        """不同 signal_dates 的訊號（例如 10/12 和 10/08）可同時 Active。"""
        _add_rec(patched_db, stock_id="3042", signal_date=D_MON)
        _add_price(patched_db, stock_id="3042", price_date=D_MON, close=204.5)
        _add_rec(patched_db, stock_id="1513", signal_date=D_THU)   # 10/08
        _add_price(patched_db, stock_id="1513", price_date=D_THU, close=150.0)
        result = _get_active_buy_signals(self.TODAY)
        sids = {r["sid"] for r in result}
        assert "3042" in sids
        assert "1513" in sids

    def test_holiday_signal_date_never_found(self, patched_db):
        """假日（10/09）不會是有效 signal_date（pipeline 不在假日跑），
        即使 DB 裡有這筆記錄也不應被 _get_active_buy_signals 撈到。"""
        _add_rec(patched_db, signal_date=D_HOL)
        _add_price(patched_db, price_date=D_HOL)
        result = _get_active_buy_signals(self.TODAY)
        assert not any(r["sid"] == "3042" for r in result), (
            "Holiday signal_date should never be queried"
        )
