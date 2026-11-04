"""
tests/test_entry_timing.py — Unit tests for EntryTimingAnalyzer (Phase B/C/D)

Coverage:
  - Insufficient data guard
  - TOO_EXTENDED branch
  - Resistance state: broken / not broken
  - Look-ahead bias prevention (prior_20d_high excludes today)
  - MA20 pullback zone detection
  - Breakout confirmation (with/without volume)
  - R/R computation
  - Label decision: each branch
  - V2ShadowSignal model isolation (never references Base)
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from src.analyzers.entry_timing import (
    ENTRY_READY,
    INSUFFICIENT_DATA,
    NO_VALID_SETUP,
    RISK_REWARD_UNFAVORABLE,
    TOO_EXTENDED,
    TOO_EXTENDED_MA20_GAP,
    WAIT_FOR_BREAKOUT,
    WAIT_FOR_PULLBACK,
    EntryTimingAnalyzer,
    EntryTimingResult,
)

# ── Helpers ────────────────────────────────────────────────────────────────


def _make_history(
    n: int = 60,
    base_close: float = 100.0,
    today_close: float = None,
    today_high: float = None,
    vol_today: float = None,
    vol_ma: float = 1_000_000.0,
) -> pd.DataFrame:
    """
    Build synthetic OHLCV DataFrame.
    - close[:n-1] = base_close
    - close[n-1]  = today_close (default base_close)
    - high[:n-1]  = base_close (flat 20d high)
    - high[n-1]   = today_high (default base_close)
    - volume      = vol_ma except last bar = vol_today (default vol_ma)
    """
    dates = [date(2026, 1, 1) + timedelta(days=i) for i in range(n)]
    close = np.full(n, base_close)
    high = np.full(n, base_close)
    low = np.full(n, base_close * 0.98)
    volume = np.full(n, vol_ma)

    if today_close is not None:
        close[-1] = today_close
    if today_high is not None:
        high[-1] = today_high
    if vol_today is not None:
        volume[-1] = vol_today

    return pd.DataFrame(
        {"date": dates, "close": close, "high": high, "low": low, "volume": volume}
    )


# ── Class 1: Insufficient Data ─────────────────────────────────────────────


class TestInsufficientData:
    def test_none_returns_insufficient(self):
        a = EntryTimingAnalyzer()
        r = a.analyze("0050", None)
        assert r.entry_label == INSUFFICIENT_DATA

    def test_empty_df_returns_insufficient(self):
        a = EntryTimingAnalyzer()
        r = a.analyze("0050", pd.DataFrame())
        assert r.entry_label == INSUFFICIENT_DATA

    def test_20_bars_returns_insufficient(self):
        # Need >= 21
        a = EntryTimingAnalyzer()
        hist = _make_history(n=20)
        r = a.analyze("0050", hist)
        assert r.entry_label == INSUFFICIENT_DATA

    def test_21_bars_passes_guard(self):
        a = EntryTimingAnalyzer()
        hist = _make_history(n=21)
        r = a.analyze("0050", hist)
        assert r.entry_label != INSUFFICIENT_DATA
        assert r.data_bars == 21


# ── Class 2: Look-Ahead Bias Prevention ───────────────────────────────────


class TestNoLookaheadBias:
    """
    If today's close is higher than all prior bars' highs,
    prior_20d_high must NOT include today — only high[-21:-1].
    """

    def test_prior_20d_high_excludes_today(self):
        # all prior highs = 100, today high = 200
        a = EntryTimingAnalyzer()
        hist = _make_history(
            n=60, base_close=100.0, today_close=200.0, today_high=200.0
        )
        r = a.analyze("0050", hist)
        # prior_20d_high should still be 100, not 200
        assert r.prior_20d_high is not None
        assert r.prior_20d_high == pytest.approx(100.0, abs=0.01)

    def test_resistance_broken_uses_prior_high(self):
        # today close (101) barely breaks prior high (100)
        a = EntryTimingAnalyzer()
        hist = _make_history(n=60, base_close=100.0, today_close=101.0)
        r = a.analyze("0050", hist)
        assert r.resistance_broken is True

    def test_no_breakout_when_at_prior_high(self):
        # today close exactly equals prior high (not strictly above)
        a = EntryTimingAnalyzer()
        hist = _make_history(n=60, base_close=100.0, today_close=100.0)
        r = a.analyze("0050", hist)
        assert r.resistance_broken is False


# ── Class 3: TOO_EXTENDED ─────────────────────────────────────────────────


class TestTooExtended:
    def test_ma20_gap_above_threshold_returns_too_extended(self):
        # MA20 ≈ base_close, today close = base_close * (1 + TOO_EXTENDED_MA20_GAP/100 + margin)
        a = EntryTimingAnalyzer()
        extended = 100.0 * (1 + (TOO_EXTENDED_MA20_GAP + 2) / 100)
        hist = _make_history(n=60, base_close=100.0, today_close=extended)
        r = a.analyze("0050", hist)
        assert r.entry_label == TOO_EXTENDED

    def test_ma20_gap_just_below_threshold_does_not_extend(self):
        a = EntryTimingAnalyzer()
        # 14% above MA20 — below threshold of 15%
        close_14 = 100.0 * 1.14
        hist = _make_history(n=60, base_close=100.0, today_close=close_14)
        r = a.analyze("0050", hist)
        assert r.entry_label != TOO_EXTENDED


# ── Class 4: Breakout Confirmation ────────────────────────────────────────


class TestBreakoutConfirmation:
    def test_breakout_with_volume_gives_entry_ready(self):
        # close > prior high + good volume + R/R ok
        a = EntryTimingAnalyzer()
        # MA20 ≈ 100 (base), prior high = 100, today close = 102, vol high
        hist = _make_history(
            n=60,
            base_close=100.0,
            today_close=102.0,
            vol_today=2_000_000.0,
            vol_ma=1_000_000.0,
        )
        r = a.analyze("0050", hist)
        assert r.resistance_broken is True
        assert r.breakout_volume_confirmed is True
        assert r.entry_label == ENTRY_READY

    def test_breakout_without_volume_gives_wait_for_breakout(self):
        a = EntryTimingAnalyzer()
        # close barely above prior high but vol_today < vol_ma
        hist = _make_history(
            n=60,
            base_close=100.0,
            today_close=101.0,
            vol_today=500_000.0,
            vol_ma=1_000_000.0,
        )
        r = a.analyze("0050", hist)
        assert r.resistance_broken is True
        assert r.breakout_volume_confirmed is False
        assert r.entry_label == WAIT_FOR_BREAKOUT

    def test_breakout_volume_flag_false_when_below_resistance(self):
        a = EntryTimingAnalyzer()
        hist = _make_history(n=60, base_close=100.0, today_close=98.0)
        r = a.analyze("0050", hist)
        assert r.breakout_volume_confirmed is False


# ── Class 5: MA20 Pullback Zone ───────────────────────────────────────────


class TestMA20PullbackZone:
    def test_at_ma20_in_pullback_zone(self):
        a = EntryTimingAnalyzer()
        # today close = MA20 (base_close)
        hist = _make_history(n=60, base_close=100.0, today_close=100.0)
        r = a.analyze("0050", hist)
        assert r.in_ma20_pullback_zone is True

    def test_slightly_above_ma20_still_in_zone(self):
        a = EntryTimingAnalyzer()
        hist = _make_history(n=60, base_close=100.0, today_close=102.5)
        r = a.analyze("0050", hist)
        assert r.in_ma20_pullback_zone is True  # +2.5% < +3%

    def test_above_zone_not_in_pullback(self):
        a = EntryTimingAnalyzer()
        hist = _make_history(n=60, base_close=100.0, today_close=104.0)
        r = a.analyze("0050", hist)
        assert r.in_ma20_pullback_zone is False

    def test_slightly_below_ma20_still_in_zone(self):
        a = EntryTimingAnalyzer()
        hist = _make_history(n=60, base_close=100.0, today_close=96.0)
        r = a.analyze("0050", hist)
        # -4% < -5% threshold → still in zone
        assert r.in_ma20_pullback_zone is True


# ── Class 6: R/R Computation ──────────────────────────────────────────────


class TestRRComputation:
    def test_rr_ratio_positive_when_stop_below_entry(self):
        a = EntryTimingAnalyzer()
        hist = _make_history(
            n=60,
            base_close=100.0,
            today_close=102.0,
            vol_today=2_000_000.0,
            vol_ma=1_000_000.0,
        )
        r = a.analyze("0050", hist)
        assert r.risk is not None
        assert r.reward is not None
        assert r.rr_ratio is not None
        assert r.rr_ratio > 0

    def test_stop_set_below_ma20(self):
        # Stop is MA20 * (1 - STOP_BUFFER) — 3% below MA20
        a = EntryTimingAnalyzer()
        hist = _make_history(
            n=60, base_close=100.0, today_close=102.0, vol_today=2_000_000.0
        )
        r = a.analyze("0050", hist)
        assert r.stop_price is not None
        assert r.stop_price < r.ma20  # stop is below MA20

    def test_rr_zero_when_reward_is_zero(self):
        a = EntryTimingAnalyzer()
        # today close = MA20 = prior_high: target = prior_high, reward = 0, rr = 0
        hist = _make_history(n=60, base_close=100.0, today_close=100.0)
        r = a.analyze("0050", hist)
        # stop = 97, risk = 3, target = prior_high (100), reward = 0, R/R = 0.0
        assert r.rr_ratio is not None
        assert r.rr_ratio == pytest.approx(0.0, abs=0.05)


# ── Class 7: Label Decisions ──────────────────────────────────────────────


class TestLabelDecisions:
    def test_wait_for_pullback_when_above_zone_below_resistance(self):
        a = EntryTimingAnalyzer()
        # Build history with:
        #   - prior bars: close=100, high=112 (resistance above today's price)
        #   - today: close=106 (+6% above MA20≈100), high=106
        # → above pullback zone, below resistance (112) → WAIT_FOR_PULLBACK
        n = 60
        dates = [date(2026, 1, 1) + timedelta(days=i) for i in range(n)]
        close_arr = [100.0] * (n - 1) + [106.0]
        high_arr = [112.0] * (n - 1) + [106.0]
        low_arr = [c * 0.98 for c in close_arr]
        vol_arr = [1_000_000.0] * n
        hist = pd.DataFrame(
            {
                "date": dates,
                "close": close_arr,
                "high": high_arr,
                "low": low_arr,
                "volume": vol_arr,
            }
        )
        r = a.analyze("0050", hist)
        assert r.resistance_broken is False
        assert r.entry_label == WAIT_FOR_PULLBACK

    def test_wait_for_breakout_near_resistance(self):
        a = EntryTimingAnalyzer()
        # today = 98.5, prior highs = 100 → 1.5% below → near resistance
        # but entry (98.5) < stop (MA20*0.97 ≈ 96.8) is fine — near-resistance check runs first
        hist = _make_history(n=60, base_close=100.0, today_close=98.5)
        r = a.analyze("0050", hist)
        assert r.dist_to_resistance_pct is not None
        assert r.dist_to_resistance_pct <= 3.0
        assert r.entry_label == WAIT_FOR_BREAKOUT

    def test_no_valid_setup_deep_below_resistance(self):
        a = EntryTimingAnalyzer()
        # today = 90, prior high = 100 → 10% below
        hist = _make_history(n=60, base_close=100.0, today_close=90.0)
        r = a.analyze("0050", hist)
        assert r.entry_label == NO_VALID_SETUP

    def test_risk_reward_unfavorable_when_pullback_rr_low(self):
        a = EntryTimingAnalyzer()
        # MA20 pullback case with R/R < MIN_RR_RATIO
        # Need: in_ma20_pullback_zone=True, resistance NOT broken, R/R < 2
        # Price at MA20 (zone), prior_high just barely above → reward tiny vs risk
        # Build: prior highs = 102 (very close to today), today close = 100 (at MA20)
        # stop = 97, risk=3, target=102, reward=2, R/R=0.67 < 2 → RISK_REWARD_UNFAVORABLE
        n = 60
        dates = [date(2026, 1, 1) + timedelta(days=i) for i in range(n)]
        close_arr = [100.0] * n
        # prior_high = 103.1 → dist = 3.1% (not "near"), MA20 ≈ 100, in pullback zone
        # stop = 97, risk = 3, target = 103.1, reward = 3.1, R/R ≈ 1.03 < 2 → unfavorable
        # prior_high = 103 → dist = 3% (at boundary, > 3% needed for not near-resistance)
        high_arr3 = [103.1] * (n - 1) + [100.0]  # prior highs = 103.1
        df3 = pd.DataFrame(
            {
                "date": dates,
                "close": close_arr,
                "high": high_arr3,
                "low": [c * 0.98 for c in close_arr],
                "volume": [1_000_000.0] * n,
            }
        )
        r3 = a.analyze("0050", df3)
        # prior_20d_high = 103.1, today = 100, dist = 3.1% (not "near"), MA20 = 100
        # stop = 97, risk = 3, target = 103.1, reward = 3.1, R/R = 1.03 < 2 → RISK_REWARD_UNFAVORABLE
        assert r3.entry_label == RISK_REWARD_UNFAVORABLE


# ── Class 8: Result Fields ────────────────────────────────────────────────


class TestResultFields:
    def test_result_has_stock_id(self):
        a = EntryTimingAnalyzer()
        hist = _make_history(n=60)
        r = a.analyze("2330", hist)
        assert r.stock_id == "2330"

    def test_reasons_list_populated(self):
        a = EntryTimingAnalyzer()
        hist = _make_history(
            n=60, base_close=100.0, today_close=102.0, vol_today=2_000_000.0
        )
        r = a.analyze("2330", hist)
        assert isinstance(r.reasons, list)
        assert len(r.reasons) >= 1

    def test_entry_price_is_today_close(self):
        a = EntryTimingAnalyzer()
        hist = _make_history(n=60, base_close=100.0, today_close=105.0)
        r = a.analyze("0050", hist)
        assert r.entry_price == pytest.approx(105.0, abs=0.01)

    def test_vol_ratio_computed(self):
        a = EntryTimingAnalyzer()
        # vol[-20:] includes today's 2M + 19 prior bars of 1M → mean = (19+2)/20 = 1.05M
        # vol_ratio = 2M / 1.05M ≈ 1.9
        hist = _make_history(n=60, vol_today=2_000_000.0, vol_ma=1_000_000.0)
        r = a.analyze("0050", hist)
        assert r.vol_ratio is not None
        assert r.vol_ratio == pytest.approx(1.9, abs=0.15)


# ── Class 9: Model Isolation ──────────────────────────────────────────────


class TestModelIsolation:
    def test_research_base_separate_from_database_base(self):
        from src.database import Base
        from src.research.models import ResearchBase

        assert ResearchBase is not Base

    def test_v2_shadow_signal_uses_research_base(self):
        from src.research.models import ResearchBase, V2ShadowSignal

        assert V2ShadowSignal.__table__.metadata is ResearchBase.metadata

    def test_v2_shadow_outcome_uses_research_base(self):
        from src.research.models import ResearchBase, V2ShadowOutcome

        assert V2ShadowOutcome.__table__.metadata is ResearchBase.metadata

    def test_v2_tables_not_in_production_base(self):
        from src.database import Base

        prod_tables = set(Base.metadata.tables.keys())
        assert "v2_shadow_signals" not in prod_tables
        assert "v2_shadow_outcomes" not in prod_tables

    def test_v2_signal_table_name(self):
        from src.research.models import V2ShadowSignal

        assert V2ShadowSignal.__tablename__ == "v2_shadow_signals"

    def test_v2_outcome_table_name(self):
        from src.research.models import V2ShadowOutcome

        assert V2ShadowOutcome.__tablename__ == "v2_shadow_outcomes"

    def test_v2_signal_unique_constraint(self):
        from src.research.models import V2ShadowSignal

        constraints = {c.name for c in V2ShadowSignal.__table__.constraints}
        assert "uq_v2ss_date_stock" in constraints

    def test_v2_outcome_unique_constraint(self):
        from src.research.models import V2ShadowOutcome

        constraints = {c.name for c in V2ShadowOutcome.__table__.constraints}
        assert "uq_v2so_date_stock" in constraints


# ── Class 10: Entry Timing Labels Completeness ───────────────────────────


class TestLabelsCompleteness:
    def test_all_labels_exported(self):
        from src.analyzers.entry_timing import ALL_LABELS

        assert ENTRY_READY in ALL_LABELS
        assert INSUFFICIENT_DATA in ALL_LABELS
        assert TOO_EXTENDED in ALL_LABELS
        assert WAIT_FOR_PULLBACK in ALL_LABELS
        assert WAIT_FOR_BREAKOUT in ALL_LABELS
        assert NO_VALID_SETUP in ALL_LABELS
        assert RISK_REWARD_UNFAVORABLE in ALL_LABELS

    def test_result_dataclass_has_expected_fields(self):
        r = EntryTimingResult(stock_id="0050")
        assert hasattr(r, "entry_label")
        assert hasattr(r, "prior_20d_high")
        assert hasattr(r, "dist_to_resistance_pct")
        assert hasattr(r, "in_ma20_pullback_zone")
        assert hasattr(r, "breakout_volume_confirmed")
        assert hasattr(r, "rr_ratio")
        assert hasattr(r, "reasons")
        assert hasattr(r, "data_bars")
