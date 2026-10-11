"""
test_dedup_utils.py — 共用 dedup_by_trading_days() 單元測試

驗證兩種計數路徑 + fail-closed 行為：
  1. 個股自身 sorted_dates_map
  2. market_calendar (0050 proxy)
  3. 無日曆：fail-closed（訊號排除，不猜）
"""

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.dedup_utils import dedup_by_trading_days


# ── helpers ───────────────────────────────────────────────────

def _mon_fri(start: date, end: date) -> list:
    """Generate Mon-Fri trading dates between start and end inclusive."""
    cal = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            cal.append(d)
        d += timedelta(days=1)
    return cal


# ── basic behaviour ───────────────────────────────────────────

class TestDedupByTradingDaysBasic:
    def test_empty_signals_returns_empty(self):
        assert dedup_by_trading_days([], 20) == []

    def test_single_signal_always_kept(self):
        result = dedup_by_trading_days([("A", date(2024, 1, 2))], 20)
        assert result == [("A", date(2024, 1, 2))]

    def test_different_stocks_always_independent(self):
        signals = [
            ("A", date(2024, 1, 2)),
            ("B", date(2024, 1, 2)),
        ]
        result = dedup_by_trading_days(signals, 20)
        assert len(result) == 2

    def test_gap_below_threshold_drops_second(self):
        cal = _mon_fri(date(2024, 1, 1), date(2024, 3, 31))
        signals = [
            ("A", date(2024, 1, 2)),
            ("A", date(2024, 1, 10)),  # 5 tdays < 20 → dropped
        ]
        result = dedup_by_trading_days(signals, 20, market_calendar=cal)
        assert result == [("A", date(2024, 1, 2))]

    def test_gap_above_threshold_keeps_both(self):
        cal = _mon_fri(date(2024, 1, 1), date(2024, 3, 31))
        signals = [
            ("A", date(2024, 1, 2)),
            ("A", date(2024, 3, 1)),  # ~42 tdays >> 20 → kept
        ]
        result = dedup_by_trading_days(signals, 20, market_calendar=cal)
        assert len(result) == 2

    def test_result_is_subsequence_of_input(self):
        cal = _mon_fri(date(2024, 1, 1), date(2024, 3, 31))
        signals = [
            ("A", date(2024, 1, 2)),
            ("A", date(2024, 1, 5)),
            ("B", date(2024, 1, 3)),
            ("A", date(2024, 3, 1)),
        ]
        result = dedup_by_trading_days(signals, 20, market_calendar=cal)
        for item in result:
            assert item in signals


# ── market_calendar path ───────────────────────────────────────

class TestDedupWithMarketCalendar:
    def setup_method(self):
        # Dense Mon-Fri calendar: Jan–Mar 2024
        self.cal = _mon_fri(date(2024, 1, 1), date(2024, 3, 31))

    def test_exactly_20_tdays_boundary_kept(self):
        # Jan 2 (Tue). 20 Mon-Fri days later = Jan 30 (Tue).
        # bisect counts elements in (Jan2, Jan30] = exactly 20.
        signals = [
            ("A", date(2024, 1, 2)),
            ("A", date(2024, 1, 30)),
        ]
        result = dedup_by_trading_days(signals, 20, market_calendar=self.cal)
        assert len(result) == 2

    def test_19_tdays_dropped(self):
        # Jan 2 → Jan 29 (Mon): bisect gives 19 tdays.
        signals = [
            ("A", date(2024, 1, 2)),
            ("A", date(2024, 1, 29)),
        ]
        result = dedup_by_trading_days(signals, 20, market_calendar=self.cal)
        assert len(result) == 1

    def test_weekend_signal_date_handled_gracefully(self):
        # Feb 10 2024 is Saturday — bisect still works (finds position)
        signals = [
            ("A", date(2024, 2, 5)),   # Mon
            ("A", date(2024, 2, 10)),  # Sat — 4 tdays < 20 → dropped
        ]
        result = dedup_by_trading_days(signals, 20, market_calendar=self.cal)
        assert len(result) == 1

    def test_market_calendar_used_over_fallback(self):
        # 28 cal days → int(28/1.4)=20 via fallback, but via Mon-Fri calendar
        # Jan 2 → Jan 30 = 20 tdays → boundary kept in both paths
        # Jan 2 → Jan 29 = 19 tdays via calendar (dropped), but 27/1.4=19 via fallback too
        # Use a longer gap to distinguish: 35 cal days → 25 tdays via Mon-Fri (kept)
        # but int(35/1.4) = 25 → same result; use just 29 cal days:
        # Jan 2 → Jan 31: 29 cal / 1.4 = 20 (boundary), Mon-Fri = 21 (kept either way)
        # Distinguishing case: truncated calendar that omits some days
        sparse_cal = [date(2024, 1, 2), date(2024, 2, 5)]  # only 2 dates → 1 tday between them
        signals = [
            ("A", date(2024, 1, 2)),
            ("A", date(2024, 2, 5)),  # 34 cal / 1.4 = 24 tdays via fallback (kept)
        ]
        # With sparse_cal: only 1 tday → dropped
        result_sparse = dedup_by_trading_days(signals, 20, market_calendar=sparse_cal)
        # With full cal: 24 tdays → kept
        result_full = dedup_by_trading_days(signals, 20, market_calendar=self.cal)
        assert len(result_sparse) == 1  # calendar used → 1 tday → dropped
        assert len(result_full) == 2    # calendar used → 24 tdays → kept


# ── sorted_dates_map path ──────────────────────────────────────

class TestDedupWithSortedDatesMap:
    def test_per_stock_dates_take_priority_over_calendar(self):
        # stock "A" has only 3 dates between Jan 2 and Feb 5 → 2 tdays < 20 → dropped
        # calendar would say ~24 tdays → kept
        stock_a_dates = [date(2024, 1, 2), date(2024, 1, 15), date(2024, 2, 5)]
        cal = _mon_fri(date(2024, 1, 1), date(2024, 3, 31))
        signals = [
            ("A", date(2024, 1, 2)),
            ("A", date(2024, 2, 5)),
        ]
        result = dedup_by_trading_days(signals, 3,
                                        sorted_dates_map={"A": stock_a_dates},
                                        market_calendar=cal)
        # elements in (Jan2, Feb5] in stock_a_dates = [Jan15, Feb5] = 2 tdays
        assert len(result) == 1  # 2 < 3 → dropped

    def test_unknown_stock_falls_back_to_calendar(self):
        cal = _mon_fri(date(2024, 1, 1), date(2024, 3, 31))
        signals = [
            ("UNKNOWN", date(2024, 1, 2)),
            ("UNKNOWN", date(2024, 1, 30)),  # 20 tdays via Mon-Fri → kept
        ]
        result = dedup_by_trading_days(signals, 20,
                                        sorted_dates_map={},
                                        market_calendar=cal)
        assert len(result) == 2


# ── fail-closed (no calendar) ─────────────────────────────────

class TestDedupNoCalendar:
    """When no trading calendar is available, independence cannot be confirmed.
    The first signal per stock is always kept; any subsequent signal is excluded."""

    def test_first_signal_always_kept(self):
        signals = [("A", date(2024, 1, 2))]
        result = dedup_by_trading_days(signals, 20)  # no calendar
        assert result == [("A", date(2024, 1, 2))]

    def test_subsequent_signal_excluded_no_calendar(self):
        # No calendar → independence unknown → second signal excluded (fail-closed)
        signals = [
            ("A", date(2024, 1, 2)),
            ("A", date(2024, 3, 1)),  # far apart but still excluded without calendar
        ]
        result = dedup_by_trading_days(signals, 20)
        assert result == [("A", date(2024, 1, 2))]

    def test_different_stocks_kept_regardless(self):
        # Different stocks never interact; each first signal is always kept
        signals = [
            ("A", date(2024, 1, 2)),
            ("B", date(2024, 1, 2)),
        ]
        result = dedup_by_trading_days(signals, 20)  # no calendar
        assert len(result) == 2

    def test_no_calendar_warning_logged(self, caplog):
        import logging
        signals = [
            ("A", date(2024, 1, 2)),
            ("A", date(2024, 3, 1)),
        ]
        with caplog.at_level(logging.WARNING, logger="src.utils.dedup_utils"):
            dedup_by_trading_days(signals, 20)
        assert any("fail-closed" in r.message for r in caplog.records)
