"""
tests/test_outcome_evaluation.py — foe_v1 pre-registration rule verification

These tests verify that the evaluation engine adheres to foe_v1 pre-registered rules.
They run against pure functions only (no DB).

Sections:
  A. Constants and version separation
  B. Baseline entry (Path A)
  C. Aware entry (Path B) — window, validation, edge cases
  D. MAE/MFE correctness + invariants
  E. Stop/T1 detection and SAME_DAY_AMBIGUOUS
  F. Horizon computation
  G. Overnight eligibility (legacy boundary)
  H. Regression: invariant tests
"""

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.engines.outcome_evaluation import (
    EPT_BASELINE_NEXT_OPEN,
    EXCL_MISSING_VALID_NEXT_OPEN_ENTRY,
    EXCL_NO_OVERNIGHT_DATA,
    EXEC_DATA_INSUFFICIENT,
    EXEC_EXECUTED,
    EXEC_EXPIRED_BEFORE_ENTRY,
    EXEC_INVALIDATED_BEFORE_ENTRY,
    EXEC_NOT_APPLICABLE,
    EXEC_PENDING,
    FOE_V1_AWARE_ENTRY_WINDOW_TRADING_DAYS,
    FORWARD_OUTCOME_PROTOCOL_VERSION,
    ODQ_BENCHMARK_MISSING,
    ODQ_COMPLETE,
    ODQ_INCOMPLETE_HORIZON,
    OUTCOME_NEITHER,
    OUTCOME_SAME_DAY_AMBIGUOUS,
    OUTCOME_STOP_FIRST,
    OUTCOME_T1_FIRST,
    PATH_AWARE,
    PATH_BASELINE,
    _LiveEvent,
    _scan_mae_mfe,
    _scan_stop_t1,
    check_overnight_eligibility,
    compute_horizon_bundle,
    find_aware_entry,
    find_baseline_entry,
)

# ── Section A: Constants ──────────────────────────────────────────────────────


class TestProtocolConstants:

    def test_protocol_version_string(self):
        assert FORWARD_OUTCOME_PROTOCOL_VERSION == "foe_v1"

    def test_aware_window_is_three(self):
        # Pre-registered: 3, not 5 or 7
        assert FOE_V1_AWARE_ENTRY_WINDOW_TRADING_DAYS == 3

    def test_path_type_constants(self):
        assert PATH_BASELINE == "BASELINE_NEXT_OPEN"
        assert PATH_AWARE == "OVERNIGHT_AWARE_RECONFIRMED"

    def test_versions_do_not_collide_with_overnight(self):
        from src.engines.overnight_risk import OVERNIGHT_RULE_VERSION

        assert FORWARD_OUTCOME_PROTOCOL_VERSION != OVERNIGHT_RULE_VERSION

    def test_versions_do_not_collide_with_live(self):
        from src.engines.live_decision import LIVE_RULE_VERSION

        assert FORWARD_OUTCOME_PROTOCOL_VERSION != LIVE_RULE_VERSION


# ── Section B: Baseline entry ─────────────────────────────────────────────────


class TestBaselineEntry:

    def _make(
        self,
        exec_date=date(2026, 10, 22),
        price=198.0,
        price_type="NEXT_OPEN",
        open_0050=None,
    ):
        return find_baseline_entry(
            execution_date=exec_date,
            execution_price=price,
            execution_price_type=price_type,
            open_0050_map=open_0050 or {date(2026, 10, 22): 175.0},
        )

    def test_valid_next_open_is_executed(self):
        r = self._make()
        assert r.entry_status == EXEC_EXECUTED
        assert r.entry_date == date(2026, 10, 22)
        assert r.entry_price == 198.0
        assert r.entry_price_type == EPT_BASELINE_NEXT_OPEN

    def test_baseline_entry_day_included_in_mae_mfe(self):
        r = self._make()
        assert r.mae_mfe_start_date == date(2026, 10, 22)  # same as entry_date
        assert r.entry_day_excursion_excluded is False

    def test_missing_execution_price_is_ineligible(self):
        r = find_baseline_entry(
            execution_date=date(2026, 10, 22),
            execution_price=None,
            execution_price_type="NEXT_OPEN",
            open_0050_map={},
        )
        assert r.entry_status in (EXEC_DATA_INSUFFICIENT, EXEC_NOT_APPLICABLE)
        assert r.exclusion_reason == EXCL_MISSING_VALID_NEXT_OPEN_ENTRY

    def test_signal_close_legacy_is_not_applicable(self):
        r = find_baseline_entry(
            execution_date=date(2026, 10, 22),
            execution_price=200.0,
            execution_price_type="SIGNAL_CLOSE_LEGACY",
            open_0050_map={},
        )
        assert r.entry_status == EXEC_NOT_APPLICABLE
        assert r.exclusion_reason == EXCL_MISSING_VALID_NEXT_OPEN_ENTRY

    def test_baseline_never_substitutes_signal_close(self):
        # If execution_price is None, result must be ineligible — no fallback
        r = find_baseline_entry(
            execution_date=date(2026, 10, 22),
            execution_price=None,
            execution_price_type="NEXT_OPEN",
            open_0050_map={date(2026, 10, 22): 175.0},
        )
        assert r.entry_price is None
        assert r.entry_status != EXEC_EXECUTED

    def test_no_timing_approximation_for_baseline(self):
        r = self._make()
        assert r.benchmark_timing_approximation is False

    def test_missing_0050_open_still_executed(self):
        # Baseline is still EXECUTED; missing benchmark captured in horizon data_quality
        r = find_baseline_entry(
            execution_date=date(2026, 10, 22),
            execution_price=198.0,
            execution_price_type="NEXT_OPEN",
            open_0050_map={},  # no 0050
        )
        assert r.entry_status == EXEC_EXECUTED
        assert r.benchmark_entry_price is None


# ── Section C: Aware entry ────────────────────────────────────────────────────

# Trading calendar: Mon–Fri for a few weeks
_TC = [
    date(2026, 10, 19),
    date(2026, 10, 20),
    date(2026, 10, 21),
    date(2026, 10, 22),
    date(2026, 10, 23),
    date(2026, 10, 26),
    date(2026, 10, 27),
    date(2026, 10, 28),
]


def _ev(trade_date, price=200.0, quality="valid", observed_offset_min=0):
    """Create a synthetic _LiveEvent."""
    obs = datetime(
        trade_date.year, trade_date.month, trade_date.day, 10, observed_offset_min, 0
    )
    yyyymmdd = trade_date.strftime("%Y%m%d")
    return _LiveEvent(
        observed_at=obs,
        current_price=price,
        quote_quality=quality,
        quote_trade_date=yyyymmdd,
    )


class TestAwareEntryWindow:

    # execution_date = 2026-10-22 (Day 1)
    # Day 2 = 2026-10-23, Day 3 = 2026-10-26
    EXEC = date(2026, 10, 22)

    def _find(self, events, invalidation_events=None, as_of_date=date(2026, 11, 1)):
        return find_aware_entry(
            execution_date=self.EXEC,
            live_events=events,
            invalidation_events=invalidation_events or [],
            as_of_date=as_of_date,
            trading_calendar=_TC,
            open_0050_map={d: 175.0 for d in _TC},
        )

    def test_reconfirm_on_day1_is_executed(self):
        ev = _ev(date(2026, 10, 22))
        r = self._find([ev])
        assert r.entry_status == EXEC_EXECUTED
        assert r.entry_date == date(2026, 10, 22)

    def test_reconfirm_on_day2_is_executed(self):
        ev = _ev(date(2026, 10, 23))
        r = self._find([ev])
        assert r.entry_status == EXEC_EXECUTED
        assert r.entry_date == date(2026, 10, 23)

    def test_reconfirm_on_day3_is_executed(self):
        ev = _ev(date(2026, 10, 26))
        r = self._find([ev])
        assert r.entry_status == EXEC_EXECUTED
        assert r.entry_date == date(2026, 10, 26)

    def test_reconfirm_on_day4_outside_window_is_expired(self):
        # Day 4 = 2026-10-27, outside the 3-day window
        ev = _ev(date(2026, 10, 27))
        r = self._find([ev])
        assert r.entry_status == EXEC_EXPIRED_BEFORE_ENTRY

    def test_no_reconfirm_after_window_is_expired(self):
        r = self._find([])  # as_of_date > window_end (2026-11-01 > 2026-10-26)
        assert r.entry_status == EXEC_EXPIRED_BEFORE_ENTRY

    def test_no_reconfirm_within_window_is_pending(self):
        r = self._find([], as_of_date=date(2026, 10, 23))  # Day 2, window not yet over
        assert r.entry_status == EXEC_PENDING

    def test_earliest_event_selected_not_latest(self):
        ev1 = _ev(date(2026, 10, 22), price=200.0, observed_offset_min=30)
        ev2 = _ev(date(2026, 10, 22), price=210.0, observed_offset_min=45)
        r = self._find([ev2, ev1])  # out of order
        assert r.entry_price == 200.0  # earliest


class TestAwareEntryValidation:

    EXEC = date(2026, 10, 22)

    def _find(self, events, invalidation_events=None):
        return find_aware_entry(
            execution_date=self.EXEC,
            live_events=events,
            invalidation_events=invalidation_events or [],
            as_of_date=date(2026, 11, 1),
            trading_calendar=_TC,
            open_0050_map={d: 175.0 for d in _TC},
        )

    def test_stale_quote_rejected(self):
        ev = _ev(date(2026, 10, 22), quality="stale")
        r = self._find([ev])
        assert r.entry_status == EXEC_EXPIRED_BEFORE_ENTRY  # no valid event

    def test_unknown_quote_rejected(self):
        ev = _ev(date(2026, 10, 22), quality="unknown")
        r = self._find([ev])
        assert r.entry_status == EXEC_EXPIRED_BEFORE_ENTRY

    def test_zero_price_rejected(self):
        ev = _ev(date(2026, 10, 22), price=0.0)
        r = self._find([ev])
        assert r.entry_status == EXEC_EXPIRED_BEFORE_ENTRY

    def test_negative_price_rejected(self):
        ev = _ev(date(2026, 10, 22), price=-1.0)
        r = self._find([ev])
        assert r.entry_status == EXEC_EXPIRED_BEFORE_ENTRY

    def test_cancel_before_reconfirm_is_invalidated_before_entry(self):
        # CANCEL on Day1 10:09, ENTRY_RECONFIRMED on Day1 10:30
        # Cancel comes first → INVALIDATED_BEFORE_ENTRY
        cancel = _ev(date(2026, 10, 22), observed_offset_min=9)
        recon = _ev(date(2026, 10, 22), observed_offset_min=30)
        r = self._find([recon], invalidation_events=[cancel])
        assert r.entry_status == EXEC_INVALIDATED_BEFORE_ENTRY

    def test_aware_uses_event_current_price_not_daily_close(self):
        ev = _ev(date(2026, 10, 22), price=198.0)
        r = self._find([ev])
        assert r.entry_status == EXEC_EXECUTED
        assert r.entry_price == 198.0  # from event.current_price, not DailyPrice.close

    def test_aware_entry_day_excluded_from_mae_mfe(self):
        ev = _ev(date(2026, 10, 22))
        r = self._find([ev])
        assert r.entry_day_excursion_excluded is True
        # mae_mfe_start_date should be next trading day after entry
        assert r.mae_mfe_start_date == date(2026, 10, 23)  # next_td(2026-10-22)

    def test_aware_benchmark_timing_approximation_true(self):
        ev = _ev(date(2026, 10, 22))
        r = self._find([ev])
        assert r.benchmark_timing_approximation is True

    def test_rapid_drop_does_not_cause_invalidated_before_entry(self):
        # RAPID_DROP does NOT generate a CANCEL event → no invalidation_events → EXECUTED
        ev = _ev(date(2026, 10, 22))
        r = self._find([ev])  # no invalidation_events
        assert r.entry_status == EXEC_EXECUTED

    def test_not_executed_is_not_zero_return(self):
        # When no ENTRY_RECONFIRMED, aware path must NOT produce 0% return
        r = self._find([])
        assert r.entry_status == EXEC_EXPIRED_BEFORE_ENTRY
        assert r.entry_price is None  # no price assigned


# ── Section C2: P0-1 Temporal-order regression tests ─────────────────────────


class TestAwareEntryTemporalOrder:
    """
    P0-1 regression: INVALIDATED_BEFORE_ENTRY requires temporal proof.
    Must use event observed_at, NOT final Recommendation.lifecycle_status.
    """

    EXEC = date(2026, 10, 22)
    # Day1=10/22, Day2=10/23, Day3=10/26, Day4=10/27 (outside window)

    def _find(self, events, invalidation_events=None, as_of_date=date(2026, 11, 1)):
        return find_aware_entry(
            execution_date=self.EXEC,
            live_events=events,
            invalidation_events=invalidation_events or [],
            as_of_date=as_of_date,
            trading_calendar=_TC,
            open_0050_map={d: 175.0 for d in _TC},
        )

    def test_reconfirm_day1_then_cancel_day3_is_executed(self):
        """P0-1 key regression: entry first → EXECUTED even with later CANCEL."""
        recon = _ev(date(2026, 10, 22), observed_offset_min=30)  # Day1 10:30
        cancel = _ev(date(2026, 10, 26), observed_offset_min=10)  # Day3 10:10 (later)
        r = self._find([recon], invalidation_events=[cancel])
        assert r.entry_status == EXEC_EXECUTED
        assert r.entry_date == date(2026, 10, 22)

    def test_cancel_day1_before_reconfirm_is_invalidated(self):
        """P0-1 key regression: CANCEL before ENTRY_RECONFIRMED → INVALIDATED_BEFORE_ENTRY."""
        cancel = _ev(date(2026, 10, 22), observed_offset_min=9)  # Day1 10:09
        recon = _ev(date(2026, 10, 22), observed_offset_min=30)  # Day1 10:30 (later)
        r = self._find([recon], invalidation_events=[cancel])
        assert r.entry_status == EXEC_INVALIDATED_BEFORE_ENTRY

    def test_cancel_within_window_no_reconfirm_is_invalidated(self):
        """CANCEL on Day3, no ENTRY_RECONFIRMED → INVALIDATED_BEFORE_ENTRY."""
        cancel = _ev(date(2026, 10, 26), observed_offset_min=10)
        r = self._find([], invalidation_events=[cancel])
        assert r.entry_status == EXEC_INVALIDATED_BEFORE_ENTRY

    def test_cancel_after_window_no_reconfirm_is_expired(self):
        """CANCEL on Day4 (outside window), no ENTRY_RECONFIRMED → EXPIRED_BEFORE_ENTRY."""
        cancel = _ev(date(2026, 10, 27), observed_offset_min=10)  # Day4, outside
        r = self._find([], invalidation_events=[cancel])
        assert r.entry_status == EXEC_EXPIRED_BEFORE_ENTRY

    def test_no_events_window_passed_is_expired(self):
        r = self._find([])
        assert r.entry_status == EXEC_EXPIRED_BEFORE_ENTRY

    def test_reconfirm_same_time_as_cancel_is_executed(self):
        """Tie (same observed_at) → EXECUTED (entry wins ties, §temporal-order)."""
        ts = _ev(date(2026, 10, 22), observed_offset_min=30)
        r = self._find([ts], invalidation_events=[ts])  # same object = same timestamp
        assert r.entry_status == EXEC_EXECUTED


# ── Section C3: P0-2 Alpha formula regression ─────────────────────────────────


class TestAlphaFormula:
    """P0-2 regression: benchmark must NOT have round_trip_cost deducted."""

    def _make_dates(self, n):
        start = date(2026, 1, 5)
        dates, d = [], start
        while len(dates) < n + 2:
            if d.weekday() < 5:
                dates.append(d)
            d += timedelta(days=1)
        return dates[: n + 2]

    def test_alpha_exact_cost_not_applied_to_benchmark(self):
        """
        Stock raw +10%, 0050 raw +5%, cost=0.585%:
          Stock Net = 10.0 - 0.585 = 9.415%
          Benchmark =  5.0          (no cost)
          Alpha     =  9.415 - 5.0 = 4.415%  ← correct

        Old bug: benchmark also deducted 0.585% → alpha = 9.415 - 4.415 = 5.0% ← wrong
        """
        dates = self._make_dates(22)
        entry = dates[0]
        exit_d = dates[20]

        close_map = {d: 100.0 for d in dates}
        close_map[exit_d] = 110.0
        high_map = {d: v + 1 for d, v in close_map.items()}
        low_map = {d: v - 1 for d, v in close_map.items()}

        b_close = {d: 100.0 for d in dates}
        b_close[exit_d] = 105.0

        bundle = compute_horizon_bundle(
            entry_price=100.0,
            entry_date=entry,
            mae_mfe_start_date=entry,
            n_days=20,
            stop_price=None,
            target1=None,
            stock_dates=dates,
            close_map=close_map,
            high_map=high_map,
            low_map=low_map,
            benchmark_entry_price=100.0,
            benchmark_entry_date=entry,
            benchmark_dates=dates,
            benchmark_close_map=b_close,
            round_trip_cost=0.585,
        )
        assert bundle.data_quality == ODQ_COMPLETE
        assert abs(bundle.return_pct - 9.415) < 0.001, f"stock net={bundle.return_pct}"
        assert abs(bundle.alpha_pct - 4.415) < 0.001, f"alpha={bundle.alpha_pct}"

    def test_alpha_not_inflated_by_cost_cancellation(self):
        """Verify the old bug is absent: alpha must NOT equal 5.0%."""
        dates = self._make_dates(22)
        entry = dates[0]
        exit_d = dates[20]

        close_map = {d: 100.0 for d in dates}
        close_map[exit_d] = 110.0
        high_map = {d: v + 1 for d, v in close_map.items()}
        low_map = {d: v - 1 for d, v in close_map.items()}
        b_close = {d: 100.0 for d in dates}
        b_close[exit_d] = 105.0

        bundle = compute_horizon_bundle(
            entry_price=100.0,
            entry_date=entry,
            mae_mfe_start_date=entry,
            n_days=20,
            stop_price=None,
            target1=None,
            stock_dates=dates,
            close_map=close_map,
            high_map=high_map,
            low_map=low_map,
            benchmark_entry_price=100.0,
            benchmark_entry_date=entry,
            benchmark_dates=dates,
            benchmark_close_map=b_close,
            round_trip_cost=0.585,
        )
        assert bundle.alpha_pct is not None
        # Old bug would give alpha ≈ 5.0% (costs cancel); correct is 4.415%
        assert (
            abs(bundle.alpha_pct - 5.0) > 0.1
        ), "alpha must not equal 5.0% (cost-cancellation bug)"
        assert abs(bundle.alpha_pct - 4.415) < 0.001

    def test_zero_cost_alpha_equals_raw_spread(self):
        """With zero cost, alpha = stock_raw - benchmark_raw exactly."""
        dates = self._make_dates(22)
        entry = dates[0]
        exit_d = dates[20]

        close_map = {d: 100.0 for d in dates}
        close_map[exit_d] = 112.0
        high_map = {d: v + 1 for d, v in close_map.items()}
        low_map = {d: v - 1 for d, v in close_map.items()}
        b_close = {d: 100.0 for d in dates}
        b_close[exit_d] = 105.0

        bundle = compute_horizon_bundle(
            entry_price=100.0,
            entry_date=entry,
            mae_mfe_start_date=entry,
            n_days=20,
            stop_price=None,
            target1=None,
            stock_dates=dates,
            close_map=close_map,
            high_map=high_map,
            low_map=low_map,
            benchmark_entry_price=100.0,
            benchmark_entry_date=entry,
            benchmark_dates=dates,
            benchmark_close_map=b_close,
            round_trip_cost=0.0,
        )
        # stock raw = 12%, benchmark raw = 5%, cost = 0 → alpha = 7%
        assert abs(bundle.return_pct - 12.0) < 0.001
        assert abs(bundle.alpha_pct - 7.0) < 0.001


# ── Section D: MAE / MFE ──────────────────────────────────────────────────────


def _make_ohlc(dates, prices):
    """Build close/high/low maps from (date, close, high, low) tuples."""
    close_map, high_map, low_map = {}, {}, {}
    for d, c, hi, lo in prices:
        close_map[d] = c
        high_map[d] = hi
        low_map[d] = lo
    return close_map, high_map, low_map


class TestMAEMFE:

    # 5-day toy calendar
    D = [
        date(2026, 10, 22),
        date(2026, 10, 23),
        date(2026, 10, 26),
        date(2026, 10, 27),
        date(2026, 10, 28),
    ]
    # close, high, low per day
    PRICES = [
        (D[0], 200, 205, 192),  # entry day
        (D[1], 195, 198, 188),
        (D[2], 202, 210, 196),
        (D[3], 198, 204, 190),
        (D[4], 205, 208, 198),
    ]

    def _maps(self):
        return _make_ohlc(self.D, self.PRICES)

    def test_baseline_entry_day_included(self):
        close_map, high_map, low_map = self._maps()
        # Baseline: scan_start = entry_date (D[0])
        mae, mfe, _ = _scan_mae_mfe(
            200.0, self.D[0], self.D[3], self.D, high_map, low_map
        )
        # D[0] low=192 → (192/200-1)*100 = -4.0
        assert mae is not None
        assert mae <= (192 / 200 - 1) * 100 + 0.01  # -4.0 or lower

    def test_aware_entry_day_excluded(self):
        close_map, high_map, low_map = self._maps()
        # Aware: scan_start = D[1] (next_td after D[0])
        mae, mfe, _ = _scan_mae_mfe(
            200.0, self.D[1], self.D[3], self.D, high_map, low_map
        )
        # D[0] is excluded; D[1] low=188 → (188/200-1)*100 = -6.0
        # But D[1] is scan start so 188 should be included
        assert mae is not None
        assert abs(mae - (188 / 200 - 1) * 100) < 0.1

    def test_mae_uses_low_not_close(self):
        close_map, high_map, low_map = self._maps()
        mae, _, _ = _scan_mae_mfe(
            200.0, self.D[0], self.D[1], self.D, high_map, low_map
        )
        # D[0] close=200 (flat), but low=192
        assert mae is not None
        assert mae < 0.0  # negative (adverse)

    def test_mfe_uses_high_not_close(self):
        close_map, high_map, low_map = self._maps()
        _, mfe, _ = _scan_mae_mfe(
            200.0, self.D[0], self.D[2], self.D, high_map, low_map
        )
        # D[2] high=210 → (210/200-1)*100 = 5.0
        assert mfe is not None
        assert mfe >= (210 / 200 - 1) * 100 - 0.01


class TestMAEMFEInvariants:
    """
    foe_v1 invariant: MAE60 <= MAE20, MFE60 >= MFE20
    because 60D window strictly includes 20D window.
    """

    def _build_ohlc(self, n_days, entry_price=100.0):
        """Build at least n_days+2 trading-day OHLC entries."""
        start = date(2026, 1, 5)  # Monday
        dates = []
        d = start
        while len(dates) < n_days + 2:
            if d.weekday() < 5:
                dates.append(d)
            d += timedelta(days=1)
        close_map = {d: entry_price + i * 0.5 for i, d in enumerate(dates)}
        high_map = {d: v + 2 for d, v in close_map.items()}
        low_map = {d: v - 3 for d, v in close_map.items()}
        return dates, close_map, high_map, low_map

    def test_mae60_le_mae20(self):
        dates, close_map, high_map, low_map = self._build_ohlc(65)
        entry_date = dates[0]
        # shared scan_start
        mae20, _, _ = _scan_mae_mfe(
            100.0, entry_date, dates[20], dates, high_map, low_map
        )
        mae60, _, _ = _scan_mae_mfe(
            100.0, entry_date, dates[60], dates, high_map, low_map
        )
        assert mae20 is not None and mae60 is not None
        assert mae60 <= mae20 + 1e-9, f"mae60={mae60:.4f} must be ≤ mae20={mae20:.4f}"

    def test_mfe60_ge_mfe20(self):
        dates, close_map, high_map, low_map = self._build_ohlc(65)
        entry_date = dates[0]
        _, mfe20, _ = _scan_mae_mfe(
            100.0, entry_date, dates[20], dates, high_map, low_map
        )
        _, mfe60, _ = _scan_mae_mfe(
            100.0, entry_date, dates[60], dates, high_map, low_map
        )
        assert mfe20 is not None and mfe60 is not None
        assert mfe60 >= mfe20 - 1e-9, f"mfe60={mfe60:.4f} must be ≥ mfe20={mfe20:.4f}"


# ── Section E: Stop / T1 detection ───────────────────────────────────────────


class TestStopT1Detection:

    D = [
        date(2026, 10, 22),
        date(2026, 10, 23),
        date(2026, 10, 26),
        date(2026, 10, 27),
        date(2026, 10, 28),
    ]

    def _scan(self, prices, stop, t1, start=None, end=None):
        close_map, high_map, low_map = _make_ohlc(self.D, prices)
        s = start or self.D[0]
        e = end or self.D[-1]
        return _scan_stop_t1(
            100.0, stop, t1, s, e, self.D, high_map, low_map, close_map
        )

    # price data: (close, high, low) per day — entry price = 100
    # D[0] = flat, D[1] = drops, D[2] = rises, D[3] = ambiguous, D[4] = neither
    _PRICES = [
        (D[0], 100, 102, 98),
        (D[1], 90, 92, 78),  # low=78 → stop at 80
        (D[2], 112, 120, 108),  # high=120 → t1 at 115
        (D[3], 100, 118, 79),  # both: low<=80, high>=115 → SAME_DAY_AMBIGUOUS
        (D[4], 102, 105, 97),
    ]

    def test_t1_only_hit(self):
        outcome, _, t_date, _ = self._scan(
            [(d, 100, 102, 98) for d in self.D[:2]]
            + [(self.D[2], 115, 120, 112)]
            + [(d, 100, 102, 98) for d in self.D[3:]],
            stop=80,
            t1=115,
        )
        assert outcome == OUTCOME_T1_FIRST
        assert t_date == self.D[2]

    def test_stop_only_hit(self):
        outcome, s_date, _, _ = self._scan(
            [(d, 100, 102, 98) for d in self.D[:1]]
            + [(self.D[1], 90, 92, 78)]  # low=78 <= stop=80
            + [(d, 100, 102, 98) for d in self.D[2:]],
            stop=80,
            t1=115,
        )
        assert outcome == OUTCOME_STOP_FIRST
        assert s_date == self.D[1]

    def test_stop_earlier_than_t1(self):
        prices = [
            (self.D[0], 100, 102, 98),
            (self.D[1], 90, 92, 79),  # stop hit (low=79 <= 80)
            (self.D[2], 116, 120, 112),  # t1 hit (high=120 >= 115)
            (self.D[3], 100, 102, 98),
            (self.D[4], 100, 102, 98),
        ]
        outcome, s_date, t_date, _ = self._scan(prices, stop=80, t1=115)
        assert outcome == OUTCOME_STOP_FIRST
        assert s_date == self.D[1]
        assert t_date == self.D[2]

    def test_t1_earlier_than_stop(self):
        prices = [
            (self.D[0], 100, 102, 98),
            (self.D[1], 116, 120, 112),  # t1 hit (high >= 115)
            (self.D[2], 90, 92, 79),  # stop hit (low <= 80)
            (self.D[3], 100, 102, 98),
            (self.D[4], 100, 102, 98),
        ]
        outcome, s_date, t_date, _ = self._scan(prices, stop=80, t1=115)
        assert outcome == OUTCOME_T1_FIRST
        assert t_date == self.D[1]
        assert s_date == self.D[2]

    def test_same_day_ambiguous(self):
        prices = [
            (self.D[0], 100, 102, 98),
            (self.D[1], 100, 120, 78),  # high >= 115 AND low <= 80 → AMBIGUOUS
            (self.D[2], 100, 102, 98),
            (self.D[3], 100, 102, 98),
            (self.D[4], 100, 102, 98),
        ]
        outcome, s_date, t_date, _ = self._scan(prices, stop=80, t1=115)
        assert outcome == OUTCOME_SAME_DAY_AMBIGUOUS
        assert s_date == t_date == self.D[1]

    def test_neither_when_no_hit(self):
        prices = [(d, 100, 102, 98) for d in self.D]
        outcome, s, t, _ = self._scan(prices, stop=80, t1=115)
        assert outcome == OUTCOME_NEITHER
        assert s is None and t is None

    def test_no_stop_price_means_stop_never_hit(self):
        prices = [(d, 100, 102, 78) for d in self.D]  # low=78 would hit stop
        outcome, s, t, _ = self._scan(prices, stop=None, t1=115)
        assert s is None

    def test_same_day_ambiguous_excluded_from_resolved_denominator(self):
        # Verify SAME_DAY_AMBIGUOUS is a distinct code (§24)
        prices = [(self.D[0], 100, 120, 78)] + [(d, 100, 102, 98) for d in self.D[1:]]
        outcome, _, _, _ = self._scan(prices, stop=80, t1=115)
        assert outcome == OUTCOME_SAME_DAY_AMBIGUOUS
        # Caller (dashboard) must exclude SAME_DAY_AMBIGUOUS from resolved denominator


# ── Section F: Horizon computation ───────────────────────────────────────────


class TestHorizonComputation:

    def _make_dates(self, n):
        start = date(2026, 1, 5)
        dates, d = [], start
        while len(dates) < n + 5:
            if d.weekday() < 5:
                dates.append(d)
            d += timedelta(days=1)
        return dates[: n + 2]

    def test_20d_return_uses_nth_close(self):
        dates = self._make_dates(25)
        entry_price = 100.0
        close_map = {d: 100.0 + i for i, d in enumerate(dates)}
        high_map = {d: v + 1 for d, v in close_map.items()}
        low_map = {d: v - 1 for d, v in close_map.items()}

        bundle = compute_horizon_bundle(
            entry_price=entry_price,
            entry_date=dates[0],
            mae_mfe_start_date=dates[0],
            n_days=20,
            stop_price=None,
            target1=None,
            stock_dates=dates,
            close_map=close_map,
            high_map=high_map,
            low_map=low_map,
            benchmark_entry_price=100.0,
            benchmark_entry_date=dates[0],
            benchmark_dates=dates,
            benchmark_close_map=close_map,
            round_trip_cost=0.0,
        )
        assert bundle.data_quality != ODQ_INCOMPLETE_HORIZON
        # Exit close = close_map[dates[20]] = 100 + 20 = 120
        assert bundle.return_pct is not None
        assert abs(bundle.return_pct - 20.0) < 0.1

    def test_incomplete_horizon_when_exit_date_missing(self):
        dates = [date(2026, 10, 22), date(2026, 10, 23)]  # only 2 days, need 20
        close_map = {d: 100.0 for d in dates}
        high_map = {d: 101.0 for d in dates}
        low_map = {d: 99.0 for d in dates}

        bundle = compute_horizon_bundle(
            entry_price=100.0,
            entry_date=dates[0],
            mae_mfe_start_date=dates[0],
            n_days=20,
            stop_price=None,
            target1=None,
            stock_dates=dates,
            close_map=close_map,
            high_map=high_map,
            low_map=low_map,
            benchmark_entry_price=100.0,
            benchmark_entry_date=dates[0],
            benchmark_dates=dates,
            benchmark_close_map=close_map,
            round_trip_cost=0.0,
        )
        assert bundle.data_quality == ODQ_INCOMPLETE_HORIZON
        assert bundle.return_pct is None

    def test_benchmark_missing_produces_none_alpha(self):
        dates = self._make_dates(25)
        close_map = {d: 100.0 + i for i, d in enumerate(dates)}
        high_map = {d: v + 1 for d, v in close_map.items()}
        low_map = {d: v - 1 for d, v in close_map.items()}

        bundle = compute_horizon_bundle(
            entry_price=100.0,
            entry_date=dates[0],
            mae_mfe_start_date=dates[0],
            n_days=20,
            stop_price=None,
            target1=None,
            stock_dates=dates,
            close_map=close_map,
            high_map=high_map,
            low_map=low_map,
            benchmark_entry_price=None,
            benchmark_entry_date=None,
            benchmark_dates=[],
            benchmark_close_map={},
            round_trip_cost=0.0,
        )
        assert bundle.alpha_pct is None
        assert bundle.data_quality == ODQ_BENCHMARK_MISSING

    def test_cost_deducted_from_return(self):
        dates = self._make_dates(25)
        close_map = {d: 100.0 for d in dates}  # flat price → 0% raw return
        high_map = {d: 101.0 for d in dates}
        low_map = {d: 99.0 for d in dates}

        bundle = compute_horizon_bundle(
            entry_price=100.0,
            entry_date=dates[0],
            mae_mfe_start_date=dates[0],
            n_days=20,
            stop_price=None,
            target1=None,
            stock_dates=dates,
            close_map=close_map,
            high_map=high_map,
            low_map=low_map,
            benchmark_entry_price=100.0,
            benchmark_entry_date=dates[0],
            benchmark_dates=dates,
            benchmark_close_map=close_map,
            round_trip_cost=0.585,
        )
        assert bundle.return_pct is not None
        assert abs(bundle.return_pct - (-0.585)) < 0.01


# ── Section G: Legacy boundary ───────────────────────────────────────────────


class TestLegacyBoundary:

    def test_no_overnight_context_is_excluded(self):
        reason = check_overnight_eligibility(
            execution_date=date(2026, 10, 22),
            overnight_context_id=None,
            overnight_rule_version=None,
        )
        assert reason == EXCL_NO_OVERNIGHT_DATA

    def test_with_context_is_eligible(self):
        reason = check_overnight_eligibility(
            execution_date=date(2026, 10, 22),
            overnight_context_id=42,
            overnight_rule_version="overnight_v1",
        )
        assert reason is None

    def test_legacy_signal_must_not_enter_formal_overnight_cohort(self):
        # Simulate a ForwardSignal that predates overnight_v1 (no context)
        reason = check_overnight_eligibility(
            execution_date=date(2026, 10, 1),  # before overnight_v1 was live
            overnight_context_id=None,
            overnight_rule_version=None,
        )
        assert reason == EXCL_NO_OVERNIGHT_DATA

    def test_cannot_use_retroactive_context(self):
        # Even if a retroactive context were inserted (which is forbidden),
        # code that checks cannot tell the difference — the prevention is operational
        # (we never create retroactive contexts in collect flow).
        # This test documents the rule: retroactive backfill is not permitted.
        # Verification is done by ensuring NO_OVERNIGHT_DATA is the only allowed
        # exclusion for signals without a live overnight context.
        reason = check_overnight_eligibility(
            execution_date=date(2026, 10, 1),
            overnight_context_id=None,
            overnight_rule_version=None,
        )
        assert reason == EXCL_NO_OVERNIGHT_DATA  # correct exclusion, not a fake GREEN


# ── Section H: Regression invariants ─────────────────────────────────────────


class TestRegressionInvariants:

    def test_aware_window_constant_is_three_not_five(self):
        """Pre-registration: this constant must not silently change."""
        assert FOE_V1_AWARE_ENTRY_WINDOW_TRADING_DAYS == 3

    def test_protocol_version_frozen(self):
        assert FORWARD_OUTCOME_PROTOCOL_VERSION == "foe_v1"

    def test_stop_first_stop_hit_date_set(self):
        dates = [date(2026, 10, 22), date(2026, 10, 23), date(2026, 10, 26)]
        close_map = {d: 100.0 for d in dates}
        high_map = {d: 102.0 for d in dates}
        low_map = {dates[0]: 99, dates[1]: 79, dates[2]: 98}  # day1 hits stop
        outcome, s_date, t_date, _ = _scan_stop_t1(
            100.0, 80, 115, dates[0], dates[2], dates, high_map, low_map, close_map
        )
        assert outcome == OUTCOME_STOP_FIRST
        assert s_date == date(2026, 10, 23)

    def test_mfe_positive_when_price_rises(self):
        dates = [date(2026, 10, 22), date(2026, 10, 23)]
        high_map = {dates[0]: 105, dates[1]: 110}
        low_map = {dates[0]: 98, dates[1]: 100}
        _, mfe, _ = _scan_mae_mfe(100.0, dates[0], dates[1], dates, high_map, low_map)
        assert mfe is not None and mfe > 0

    def test_mae_negative_when_price_falls(self):
        dates = [date(2026, 10, 22), date(2026, 10, 23)]
        high_map = {dates[0]: 101, dates[1]: 102}
        low_map = {dates[0]: 95, dates[1]: 93}
        mae, _, _ = _scan_mae_mfe(100.0, dates[0], dates[1], dates, high_map, low_map)
        assert mae is not None and mae < 0
