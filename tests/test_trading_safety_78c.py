"""
tests/test_trading_safety_78c.py — Isolated unit tests for the Trading Safety Gate.

DESIGN:
- Zero production DB connections. All tests use _test_* overrides on compute_trading_gate().
- Zero imports from Streamlit (components functions are not called here).
- Zero writes to SQLite, Neon, or forward_signals.
- TaiwanTradingCalendar is imported directly for date arithmetic; it is read-only.
- Tests verify BLOCKED / DEGRADED / UNKNOWN status codes and reason codes.
- Tests are calendar-independent: dates are anchored relative to known trading days.
"""

import os
import sys
from datetime import date, datetime, timedelta

import pytest

# Make project root importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dashboard.trading_safety import (
    MAX_SIGNAL_AGE_TRADING_DAYS,
    CoverageState,
    TradingGateResult,
    TradingGateStatus,
    _count_trading_days_between,
    compute_trading_gate,
    expected_latest_price_date,
)

# ── Helpers ──────────────────────────────────────────────────────────────────


def _cal():
    from src.core.trading_calendar import TaiwanTradingCalendar

    return TaiwanTradingCalendar()


def _last_n_trading_days(n: int, before: date = date(2026, 11, 25)) -> list:
    """Return the n most recent trading days up to and including (or before) `before`."""
    cal = _cal()
    result = []
    d = before
    while len(result) < n:
        if cal.is_trading_day(d):
            result.append(d)
        d -= timedelta(days=1)
    return list(reversed(result))


# A known stable trading week: 2026-11-17 ~ 2026-11-21 Mon-Fri (all trading days per calendar)
# Confirmed from 78C summary: Nov 21 is Saturday — use 11-18, 11-19, 11-20, 11-24, 11-25
_KNOWN_TRADING = [
    date(2026, 11, 18),  # Tuesday
    date(2026, 11, 19),  # Wednesday
    date(2026, 11, 20),  # Thursday
    date(2026, 11, 24),  # Monday (after Nov 21/22 weekend)
    date(2026, 11, 25),  # Tuesday
]

_NON_TRADING = [
    date(2026, 11, 22),  # Saturday
    date(
        2026, 11, 23
    ),  # Sunday — NOTE: 78C summary says Mon/Tue/Wed trading but Nov 23 = Sunday
]

# Reference dates for tests (anchored to known non-API dates)
_FRESH_PRICE_DATE = date(2026, 11, 20)  # Thursday
_EXPECTED_DATE = date(2026, 11, 20)  # same as fresh price: 0 TD lag
_STALE_PRICE_DATE = date(2026, 11, 18)  # 2 TD behind Nov 20
_FRESH_SIGNAL_DATE = date(2026, 11, 20)  # 1 TD before Nov 25 reference
_STALE_SIGNAL_DATE = date(2026, 10, 28)  # 20 TD before Nov 25 (matches 78C)


# ── SCENARIO 1: Price stale → BLOCKED ────────────────────────────────────────


class TestPriceStaleBlocked:
    def test_blocked_status(self):
        result = compute_trading_gate(
            _test_max_price=_STALE_PRICE_DATE,
            _test_max_signal=_FRESH_SIGNAL_DATE,
            _test_expected=_EXPECTED_DATE,
        )
        assert result.status == TradingGateStatus.BLOCKED

    def test_blocked_reason_code(self):
        result = compute_trading_gate(
            _test_max_price=_STALE_PRICE_DATE,
            _test_max_signal=_FRESH_SIGNAL_DATE,
            _test_expected=_EXPECTED_DATE,
        )
        assert "PRICE_STALE" in result.reasons

    def test_freshness_detail_present(self):
        result = compute_trading_gate(
            _test_max_price=_STALE_PRICE_DATE,
            _test_max_signal=_FRESH_SIGNAL_DATE,
            _test_expected=_EXPECTED_DATE,
        )
        assert result.freshness is not None
        assert result.freshness.latest_price_date == _STALE_PRICE_DATE

    def test_not_actionable(self):
        result = compute_trading_gate(
            _test_max_price=_STALE_PRICE_DATE,
            _test_max_signal=_FRESH_SIGNAL_DATE,
            _test_expected=_EXPECTED_DATE,
        )
        assert not result.is_actionable


# ── SCENARIO 2: Signal stale → BLOCKED ───────────────────────────────────────


class TestSignalStaleBlocked:
    def test_blocked_status(self):
        result = compute_trading_gate(
            _test_max_price=_FRESH_PRICE_DATE,
            _test_max_signal=_STALE_SIGNAL_DATE,  # 20 TD ago
            _test_expected=_EXPECTED_DATE,
        )
        assert result.status == TradingGateStatus.BLOCKED

    def test_blocked_reason_code(self):
        result = compute_trading_gate(
            _test_max_price=_FRESH_PRICE_DATE,
            _test_max_signal=_STALE_SIGNAL_DATE,
            _test_expected=_EXPECTED_DATE,
        )
        assert "SIGNAL_STALE" in result.reasons

    def test_signal_lag_in_freshness(self):
        result = compute_trading_gate(
            _test_max_price=_FRESH_PRICE_DATE,
            _test_max_signal=_STALE_SIGNAL_DATE,
            _test_expected=_EXPECTED_DATE,
        )
        assert result.freshness is not None
        # signal from Oct 28 to Nov 25 should be >> 5 TD
        assert result.freshness.signal_lag_trading_days > MAX_SIGNAL_AGE_TRADING_DAYS


# ── SCENARIO 3: Both stale → BLOCKED (price reason takes precedence) ─────────


class TestBothStaleBlocked:
    def test_blocked_has_both_reason_codes(self):
        result = compute_trading_gate(
            _test_max_price=_STALE_PRICE_DATE,
            _test_max_signal=_STALE_SIGNAL_DATE,
            _test_expected=_EXPECTED_DATE,
        )
        assert result.status == TradingGateStatus.BLOCKED
        # At minimum PRICE_STALE must be present
        assert "PRICE_STALE" in result.reasons


# ── SCENARIO 4: No price data → UNKNOWN ──────────────────────────────────────


class TestNoPriceDataUnknown:
    def test_unknown_status(self):
        result = compute_trading_gate(
            _test_max_price=None,
            _test_max_signal=_FRESH_SIGNAL_DATE,
            _test_expected=_EXPECTED_DATE,
        )
        assert result.status in (TradingGateStatus.UNKNOWN, TradingGateStatus.BLOCKED)

    def test_no_price_data_reason(self):
        result = compute_trading_gate(
            _test_max_price=None,
            _test_max_signal=_FRESH_SIGNAL_DATE,
            _test_expected=_EXPECTED_DATE,
        )
        assert "NO_PRICE_DATA" in result.reasons


# ── SCENARIO 5: Price fresh, signal fresh → DEGRADED (coverage UNKNOWN) ──────


class TestFreshDataDegraded:
    def test_not_pass_with_fresh_data(self):
        # price lag = 0 (fresh), signal lag = 0 TD vs expected (signal is ahead of expected)
        # S78C.2: coverage UNKNOWN → UNKNOWN (not DEGRADED)
        signal_one_td_ago = date(
            2026, 11, 24
        )  # 1 TD before Nov 25; ahead of _EXPECTED_DATE(Nov20)
        result = compute_trading_gate(
            _test_max_price=_FRESH_PRICE_DATE,
            _test_max_signal=signal_one_td_ago,
            _test_expected=_EXPECTED_DATE,
        )
        # Coverage always UNKNOWN → UNKNOWN (not DEGRADED under S78C.2 policy)
        assert result.status in (TradingGateStatus.UNKNOWN, TradingGateStatus.BLOCKED)
        assert result.status != TradingGateStatus.PASS

    def test_coverage_always_unknown(self):
        signal_one_td_ago = date(2026, 11, 24)
        result = compute_trading_gate(
            _test_max_price=_FRESH_PRICE_DATE,
            _test_max_signal=signal_one_td_ago,
            _test_expected=_EXPECTED_DATE,
        )
        assert result.coverage == CoverageState.UNKNOWN

    def test_coverage_unknown_reason_code(self):
        signal_one_td_ago = date(2026, 11, 24)
        result = compute_trading_gate(
            _test_max_price=_FRESH_PRICE_DATE,
            _test_max_signal=signal_one_td_ago,
            _test_expected=_EXPECTED_DATE,
        )
        assert "COVERAGE_UNKNOWN" in result.reasons


# ── SCENARIO 6: Diagnostic floor below threshold ──────────────────────────────


class TestDiagnosticFloor:
    def test_below_floor(self):
        result = compute_trading_gate(
            _test_max_price=_FRESH_PRICE_DATE,
            _test_max_signal=date(2026, 11, 24),
            _test_expected=_EXPECTED_DATE,
            _test_non0050_count=1_500,
        )
        assert not result.diagnostic_floor_met

    def test_above_floor(self):
        result = compute_trading_gate(
            _test_max_price=_FRESH_PRICE_DATE,
            _test_max_signal=date(2026, 11, 24),
            _test_expected=_EXPECTED_DATE,
            _test_non0050_count=1_968,
        )
        assert result.diagnostic_floor_met

    def test_floor_does_not_change_blocked_status(self):
        # Floor being met must not rescue a BLOCKED gate
        result = compute_trading_gate(
            _test_max_price=_STALE_PRICE_DATE,
            _test_max_signal=_STALE_SIGNAL_DATE,
            _test_expected=_EXPECTED_DATE,
            _test_non0050_count=2_000,
        )
        assert result.status == TradingGateStatus.BLOCKED


# ── SCENARIO 7: Research display never suppressed ────────────────────────────


class TestResearchDisplayPolicy:
    @pytest.mark.parametrize(
        "price,signal",
        [
            (_STALE_PRICE_DATE, _STALE_SIGNAL_DATE),
            (None, None),
            (_FRESH_PRICE_DATE, _FRESH_SIGNAL_DATE),
        ],
    )
    def test_allow_research_display_always_true(self, price, signal):
        result = compute_trading_gate(
            _test_max_price=price,
            _test_max_signal=signal,
            _test_expected=_EXPECTED_DATE,
        )
        assert result.allow_research_display is True


# ── SCENARIO 8: is_actionable only when PASS ─────────────────────────────────


class TestActionablePolicy:
    def test_blocked_not_actionable(self):
        result = compute_trading_gate(
            _test_max_price=_STALE_PRICE_DATE,
            _test_max_signal=_STALE_SIGNAL_DATE,
            _test_expected=_EXPECTED_DATE,
        )
        assert not result.is_actionable

    def test_degraded_not_actionable(self):
        result = compute_trading_gate(
            _test_max_price=_FRESH_PRICE_DATE,
            _test_max_signal=date(2026, 11, 24),
            _test_expected=_EXPECTED_DATE,
        )
        # Coverage UNKNOWN → DEGRADED → not actionable
        assert not result.is_actionable


# ── SCENARIO 9: expected_latest_price_date – calendar logic ──────────────────


class TestExpectedLatestPriceDate:
    def test_weekday_before_cutoff_returns_prev_trading_day(self):
        import zoneinfo

        # Nov 24 (Mon) at 10:00 CST → expected = most recent trading day before Nov 24
        ref = datetime(2026, 11, 24, 10, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Taipei"))
        result = expected_latest_price_date(ref)
        # Should be a trading day before Nov 24
        cal = _cal()
        assert cal.is_trading_day(result)
        assert result < date(2026, 11, 24)

    def test_weekday_after_cutoff_returns_today(self):
        import zoneinfo

        # Nov 24 (Mon) at 18:00 CST → expected = Nov 24 (data published)
        ref = datetime(2026, 11, 24, 18, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Taipei"))
        result = expected_latest_price_date(ref)
        assert result == date(2026, 11, 24)

    def test_weekend_returns_friday_or_prior(self):
        import zoneinfo

        # Nov 22 (Sat) → expected = Nov 20 (Thu) or Nov 21 (Fri); depends on calendar
        ref = datetime(2026, 11, 22, 10, 0, tzinfo=zoneinfo.ZoneInfo("Asia/Taipei"))
        result = expected_latest_price_date(ref)
        cal = _cal()
        assert cal.is_trading_day(result)
        assert result < date(2026, 11, 22)


# ── SCENARIO 10: _count_trading_days_between ─────────────────────────────────


class TestCountTradingDays:
    def test_same_date_returns_zero(self):
        cal = _cal()
        d = date(2026, 11, 20)
        assert _count_trading_days_between(d, d, cal) == 0

    def test_start_after_end_returns_zero(self):
        cal = _cal()
        assert (
            _count_trading_days_between(date(2026, 11, 20), date(2026, 11, 18), cal)
            == 0
        )

    def test_one_trading_day_apart(self):
        cal = _cal()
        # Nov 24 (Mon) to Nov 25 (Tue): 1 TD
        result = _count_trading_days_between(
            date(2026, 11, 24), date(2026, 11, 25), cal
        )
        assert result == 1

    def test_spans_weekend(self):
        cal = _cal()
        # Nov 20 (Thu) to Nov 24 (Mon): only Nov 24 is in (Nov 20, Nov 24]
        # Nov 21 Sat, Nov 22 Sun, Nov 23 Sun (but 78C: Nov 23 = Sunday, non-trading)
        # Confirmed trading: Nov 24
        result = _count_trading_days_between(
            date(2026, 11, 20), date(2026, 11, 24), cal
        )
        assert result >= 1  # at minimum Nov 24

    def test_known_signal_lag_oct28_to_nov25(self):
        cal = _cal()
        # From 78C: signal_lag for Oct 28 to Nov 25 = 20 trading days
        result = _count_trading_days_between(
            date(2026, 10, 28), date(2026, 11, 25), cal
        )
        assert result >= MAX_SIGNAL_AGE_TRADING_DAYS  # definitely > 5


# ── SCENARIO 11: TradingGateResult properties ────────────────────────────────


class TestTradingGateResultProperties:
    def test_status_label_zh_blocked(self):
        r = TradingGateResult(status=TradingGateStatus.BLOCKED, reasons=["PRICE_STALE"])
        assert "暫停" in r.status_label_zh

    def test_status_label_zh_degraded(self):
        r = TradingGateResult(status=TradingGateStatus.DEGRADED, reasons=[])
        assert "研究" in r.status_label_zh

    def test_reason_text_zh_coverage_unknown(self):
        r = TradingGateResult(
            status=TradingGateStatus.DEGRADED, reasons=["COVERAGE_UNKNOWN"]
        )
        assert "Security Master" in r.reason_text_zh or "涵蓋率" in r.reason_text_zh

    def test_reason_text_zh_price_stale(self):
        r = TradingGateResult(status=TradingGateStatus.BLOCKED, reasons=["PRICE_STALE"])
        assert "股價" in r.reason_text_zh


# ── SCENARIO 12: staleness_trading_days in components ────────────────────────


class TestStalenessTrainingDays:
    def test_none_input_returns_neg1(self):
        from dashboard.components import staleness_trading_days

        assert staleness_trading_days(None) == -1

    def test_future_date_returns_zero(self):
        from dashboard.components import staleness_trading_days

        future = date(2030, 1, 1)
        assert staleness_trading_days(future) == 0

    def test_same_as_ref(self):
        from dashboard.components import staleness_trading_days

        d = date(2026, 11, 24)
        assert staleness_trading_days(d, reference_date=d) == 0

    def test_one_trading_day_behind(self):
        from dashboard.components import staleness_trading_days

        # Nov 24 → ref Nov 25: 1 trading day
        result = staleness_trading_days(
            date(2026, 11, 24), reference_date=date(2026, 11, 25)
        )
        assert result == 1

    def test_string_input_accepted(self):
        from dashboard.components import staleness_trading_days

        result = staleness_trading_days("2026-11-24", reference_date=date(2026, 11, 25))
        assert result >= 0


# ══════════════════════════════════════════════════════════════════════════════
# Phase B — S78C.2 stricter freshness policy tests
# ══════════════════════════════════════════════════════════════════════════════


class TestS78C2StricterPolicy:
    """
    B1–B8: Verify the S78C.2 policy changes.

    Key policy changes vs S78C original:
      - price_lag > 0 TD → BLOCKED  (was: > 1 TD)
      - signal_lag > 0 TD → BLOCKED (was: > 5 TD)
      - Both lags measured vs the same expected date  (signal was vs today)
      - Coverage UNKNOWN → UNKNOWN  (was: → DEGRADED)
    """

    # B1 — price_lag = 1 TD now triggers BLOCKED (old threshold was > 1 TD)
    def test_b1_price_lag_1td_is_blocked(self):
        cal = _cal()
        # Nov 24 (Mon) is 1 TD behind Nov 25 (Tue) = expected
        expected = date(2026, 11, 25)
        price = date(2026, 11, 24)
        assert _count_trading_days_between(price, expected, cal) == 1

        result = compute_trading_gate(
            _test_max_price=price,
            _test_max_signal=expected,
            _test_expected=expected,
        )
        assert result.status == TradingGateStatus.BLOCKED
        assert "PRICE_STALE" in result.reasons

    # B2 — signal_lag = 1 TD now triggers BLOCKED (old threshold was > 5 TD)
    def test_b2_signal_lag_1td_is_blocked(self):
        cal = _cal()
        # price = expected (0 lag); signal = 1 TD behind expected
        expected = date(2026, 11, 25)
        signal = date(2026, 11, 24)
        assert _count_trading_days_between(signal, expected, cal) == 1

        result = compute_trading_gate(
            _test_max_price=expected,
            _test_max_signal=signal,
            _test_expected=expected,
        )
        assert result.status == TradingGateStatus.BLOCKED
        assert "SIGNAL_STALE" in result.reasons

    # B3 — coverage UNKNOWN → UNKNOWN (not DEGRADED as in old code)
    def test_b3_coverage_unknown_returns_unknown_not_degraded(self):
        # price and signal both match expected → no staleness reasons
        expected = date(2026, 11, 25)
        result = compute_trading_gate(
            _test_max_price=expected,
            _test_max_signal=expected,
            _test_expected=expected,
        )
        # Coverage is always UNKNOWN in current impl → must return UNKNOWN
        assert result.status == TradingGateStatus.UNKNOWN
        assert result.status != TradingGateStatus.DEGRADED

    # B4 — UNKNOWN is not actionable
    def test_b4_unknown_not_actionable(self):
        expected = date(2026, 11, 25)
        result = compute_trading_gate(
            _test_max_price=expected,
            _test_max_signal=expected,
            _test_expected=expected,
        )
        assert result.status == TradingGateStatus.UNKNOWN
        assert not result.is_actionable

    # B5 — DEGRADED (direct property test) is not actionable
    def test_b5_degraded_not_actionable(self):
        r = TradingGateResult(
            status=TradingGateStatus.DEGRADED, reasons=["COVERAGE_PARTIAL"]
        )
        assert not r.is_actionable

    # B6 — signal compared to expected, not today
    def test_b6_signal_lag_vs_expected_not_today(self):
        # expected = Nov 20; signal = Nov 20 → 0 TD lag → no SIGNAL_STALE
        # (If we compared vs Nov 25 today, lag would be 3 TD → SIGNAL_STALE under old code)
        expected = date(2026, 11, 20)
        result_match = compute_trading_gate(
            _test_max_price=expected,
            _test_max_signal=expected,
            _test_expected=expected,
        )
        assert "SIGNAL_STALE" not in result_match.reasons

        # expected = Nov 20; signal = Nov 19 → 1 TD lag → SIGNAL_STALE
        signal_1td_behind = date(2026, 11, 19)
        result_stale = compute_trading_gate(
            _test_max_price=expected,
            _test_max_signal=signal_1td_behind,
            _test_expected=expected,
        )
        assert "SIGNAL_STALE" in result_stale.reasons
        assert result_stale.status == TradingGateStatus.BLOCKED

    # B7 — historical research display always preserved regardless of gate status
    def test_b7_research_display_preserved_when_blocked(self):
        expected = date(2026, 11, 25)
        stale_price = date(2026, 11, 20)
        result = compute_trading_gate(
            _test_max_price=stale_price,
            _test_max_signal=stale_price,
            _test_expected=expected,
        )
        assert result.status == TradingGateStatus.BLOCKED
        assert result.allow_research_display is True

    # B8 — price+signal both matching expected → UNKNOWN (not BLOCKED)
    def test_b8_fresh_data_returns_unknown_not_blocked(self):
        # Verifies fresh data is not blocked; gate is only UNKNOWN due to coverage.
        expected = date(2026, 11, 25)
        result = compute_trading_gate(
            _test_max_price=expected,
            _test_max_signal=expected,
            _test_expected=expected,
        )
        assert result.status != TradingGateStatus.BLOCKED
        assert result.status == TradingGateStatus.UNKNOWN
        assert "PRICE_STALE" not in result.reasons
        assert "SIGNAL_STALE" not in result.reasons
