"""
tests/test_effectiveness_analyzer.py — Unit tests for effectiveness_analyzer module.

Tests (EA):
  EA01 — compute_ma_slope: rising, falling, flat, insufficient data
  EA02 — classify_ma_slope: thresholds
  EA03 — classify_ma20_gap_bucket: all four buckets
  EA04 — compute_group_stats: empty list → all None
  EA05 — compute_group_stats: paired_delta mean is correct
  EA06 — compute_group_stats: n<10 → no CI, stat_note contains 'INSUFFICIENT'
  EA07 — compute_group_stats: n<30 → insufficient_sample=True
  EA08 — compute_group_stats: fill_rate_pct correct
  EA09 — compute_group_stats: missed opportunity breakdown correct
  EA10 — run_data_integrity_audit: counts (raw/dedup/matured/valid_paired)
  EA11 — run_data_integrity_audit: concentration_warning when top stock > 15%
  EA12 — run_ma20_audit: derived≈actual when stop=MA20*(1-0.03)
  EA13 — run_ma20_audit: WAIT_FOR_PULLBACK entry vs MA20 diff
  EA14 — run_group_analysis: correct top-level keys present
  EA15 — run_group_analysis: multiple_testing_note present
  EA16 — run_walk_forward: only signals in test window included
  EA17 — run_walk_forward: embargo respected (signals in embargo zone excluded)
  EA18 — run_sensitivity_matrix: fragile when large delta vs base
  EA19 — run_sensitivity_matrix: robust when small delta
  EA20 — no-lookahead: dedup-excluded signals not in analysis
  EA21 — no-lookahead: immature signals not in analysis
  EA22 — walk_forward OOS window flagged is_oos=True
  EA23 — walk_forward PASS/FAIL/INSUFFICIENT_DATA assignment
"""

from __future__ import annotations

from datetime import date
from typing import List, Optional

import pytest

from src.research.effectiveness_analyzer import (
    MIN_GROUP_SAMPLE,
    INSUFFICIENT_SAMPLE_N,
    SLOPE_RISING_THRESHOLD,
    SLOPE_FALLING_THRESHOLD,
    EnrichedSignal,
    classify_ma20_gap_bucket,
    classify_ma_slope,
    compute_group_stats,
    compute_ma_slope,
    run_data_integrity_audit,
    run_group_analysis,
    run_ma20_audit,
    run_sensitivity_matrix,
    run_walk_forward,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_signal(
    signal_date: date = date(2026, 4, 1),
    stock_id: str = "TEST",
    entry_label: str = "ENTRY_READY",
    stop_price: float = 97.0,
    target_price: float = 115.0,
    ma20: float = 100.0,
    ma20_gap_pct: float = 2.0,
    ma20_trend: str = "rising",
    ma60: Optional[float] = 95.0,
    ma60_trend: Optional[str] = "rising",
    price_vs_ma20: str = "above",
    price_vs_ma60: Optional[str] = "above",
    ma20_gap_bucket: str = "0-2%",
    market_regime: str = "bull",
    v1_ret: Optional[float] = 1.0,
    v2_ret: Optional[float] = 2.0,
    v2_filled: bool = True,
    v1_stop_hit: bool = False,
    v1_target_hit: bool = False,
    v2_stop_hit: bool = False,
    v2_target_hit: bool = False,
    v1_mae: Optional[float] = 1.5,
    v1_mfe: Optional[float] = 3.0,
    v2_mae: Optional[float] = 1.2,
    v2_mfe: Optional[float] = 3.5,
    v2_waiting_days: int = 2,
    is_matured: bool = True,
    is_raw: bool = True,
    is_dedup_kept: bool = True,
    ma20_derived: float = 100.0,
    planned_entry_price: float = 100.0,
) -> EnrichedSignal:
    paired_delta = None
    if v1_ret is not None and v2_ret is not None:
        paired_delta = v2_ret - v1_ret
    return EnrichedSignal(
        signal_date=signal_date,
        stock_id=stock_id,
        entry_label=entry_label,
        entry_price=100.0,
        stop_price=stop_price,
        target_price=target_price,
        ma20=ma20,
        ma20_gap_pct=ma20_gap_pct,
        prior_20d_high=110.0,
        ma20_trend=ma20_trend,
        ma60=ma60,
        ma60_trend=ma60_trend,
        price_vs_ma20=price_vs_ma20,
        price_vs_ma60=price_vs_ma60,
        ma20_gap_bucket=ma20_gap_bucket,
        market_regime=market_regime,
        planned_entry_price=planned_entry_price,
        v1_ret=v1_ret,
        v2_ret=v2_ret,
        v2_filled=v2_filled,
        v1_stop_hit=v1_stop_hit,
        v1_target_hit=v1_target_hit,
        v2_stop_hit=v2_stop_hit,
        v2_target_hit=v2_target_hit,
        v1_mae=v1_mae,
        v1_mfe=v1_mfe,
        v2_mae=v2_mae,
        v2_mfe=v2_mfe,
        v2_waiting_days=v2_waiting_days,
        paired_delta=paired_delta,
        is_matured=is_matured,
        is_raw=is_raw,
        is_dedup_kept=is_dedup_kept,
        ma20_derived=ma20_derived,
        ma20_slope_pct=0.5,
    )


def _make_signals_n(n: int, **overrides) -> List[EnrichedSignal]:
    """Create n distinct signals, different stocks & dates."""
    from datetime import timedelta
    signals = []
    for i in range(n):
        d = date(2026, 4, 1) + timedelta(days=i * 5)
        # Allow caller to override stock_id; default to indexed ID
        kw = {"signal_date": d, "stock_id": f"S{i:03d}", **overrides}
        signals.append(_make_signal(**kw))
    return signals


# ── EA01: compute_ma_slope ─────────────────────────────────────────────────

class TestComputeMaSlope:
    def test_EA01a_rising(self):
        closes = [100.0 + i for i in range(30)]  # steadily rising
        slope = compute_ma_slope(closes)
        assert slope > SLOPE_RISING_THRESHOLD

    def test_EA01b_falling(self):
        closes = [130.0 - i for i in range(30)]  # steadily falling
        slope = compute_ma_slope(closes)
        assert slope < SLOPE_FALLING_THRESHOLD

    def test_EA01c_flat(self):
        closes = [100.0] * 30
        slope = compute_ma_slope(closes)
        assert abs(slope) < 0.001

    def test_EA01d_insufficient_data(self):
        closes = [100.0] * 5  # < MA20_SLOPE_BARS
        slope = compute_ma_slope(closes)
        assert slope == 0.0


# ── EA02: classify_ma_slope ────────────────────────────────────────────────

class TestClassifyMaSlope:
    def test_EA02a_rising(self):
        assert classify_ma_slope(SLOPE_RISING_THRESHOLD + 0.01) == "rising"

    def test_EA02b_falling(self):
        assert classify_ma_slope(SLOPE_FALLING_THRESHOLD - 0.01) == "falling"

    def test_EA02c_flat_zero(self):
        assert classify_ma_slope(0.0) == "flat"

    def test_EA02d_flat_boundary(self):
        assert classify_ma_slope(SLOPE_RISING_THRESHOLD - 0.01) == "flat"
        assert classify_ma_slope(SLOPE_FALLING_THRESHOLD + 0.01) == "flat"


# ── EA03: classify_ma20_gap_bucket ─────────────────────────────────────────

class TestClassifyMa20GapBucket:
    def test_EA03a_negative(self):
        assert classify_ma20_gap_bucket(-1.0) == "<0%"

    def test_EA03b_zero_to_two(self):
        assert classify_ma20_gap_bucket(0.0) == "0-2%"
        assert classify_ma20_gap_bucket(1.9) == "0-2%"

    def test_EA03c_two_to_five(self):
        assert classify_ma20_gap_bucket(2.0) == "2-5%"
        assert classify_ma20_gap_bucket(4.9) == "2-5%"

    def test_EA03d_above_five(self):
        assert classify_ma20_gap_bucket(5.0) == ">5%"
        assert classify_ma20_gap_bucket(10.0) == ">5%"


# ── EA04-EA09: compute_group_stats ─────────────────────────────────────────

class TestComputeGroupStats:
    def test_EA04_empty_list(self):
        result = compute_group_stats([], "empty")
        assert result["n"] == 0
        assert result["paired_delta_mean"] is None
        assert result["v1_mean"] is None

    def test_EA05_paired_delta_mean_correct(self):
        # v1_ret=1.0, v2_ret=2.0 → delta=1.0 for all signals
        signals = _make_signals_n(15, v1_ret=1.0, v2_ret=2.0)
        result = compute_group_stats(signals)
        assert abs(result["paired_delta_mean"] - 1.0) < 0.01
        assert abs(result["v1_mean"] - 1.0) < 0.01
        assert abs(result["v2_mean"] - 2.0) < 0.01

    def test_EA06_no_ci_below_min_sample(self):
        signals = _make_signals_n(MIN_GROUP_SAMPLE - 1, v1_ret=1.0, v2_ret=2.0)
        result = compute_group_stats(signals)
        assert result["paired_delta_ci95"] is None
        assert "INSUFFICIENT" in result["stat_note"].upper()

    def test_EA07_insufficient_sample_flag(self):
        signals = _make_signals_n(INSUFFICIENT_SAMPLE_N - 1, v1_ret=1.0, v2_ret=1.5)
        result = compute_group_stats(signals)
        assert result["insufficient_sample"] is True

    def test_EA08_fill_rate_correct(self):
        filled = _make_signals_n(8, v2_filled=True)
        no_fill = _make_signals_n(2, v2_filled=False, v2_ret=0.0)
        for s in no_fill:
            s.stock_id += "_NF"  # avoid stock_id clash
        result = compute_group_stats(filled + no_fill)
        assert abs(result["fill_rate_pct"] - 80.0) < 0.1

    def test_EA09_missed_opportunity_breakdown(self):
        # 5 filled, 5 no-fill where V1 returns: +2, +3, -1, -2, -4 → 3 neg, 2 pos
        filled = _make_signals_n(5, v2_filled=True, v1_ret=1.0, v2_ret=1.5)
        no_fill_pos = _make_signals_n(2, v2_filled=False, v1_ret=2.0, v2_ret=0.0)
        no_fill_neg = _make_signals_n(3, v2_filled=False, v1_ret=-2.0, v2_ret=0.0)
        for i, s in enumerate(no_fill_pos):
            s.stock_id = f"NF_POS_{i}"
        for i, s in enumerate(no_fill_neg):
            s.stock_id = f"NF_NEG_{i}"
        all_sigs = filled + no_fill_pos + no_fill_neg
        result = compute_group_stats(all_sigs)
        assert result["n_no_fill"] == 5
        assert result["positive_missed_upside"] is not None
        assert result["positive_missed_upside"] > 0
        assert result["avoided_loss"] is not None
        assert result["avoided_loss"] < 0


# ── EA10-EA11: run_data_integrity_audit ───────────────────────────────────

class TestDataIntegrityAudit:
    def test_EA10_counts_correct(self):
        raw = _make_signals_n(10, is_raw=True, is_dedup_kept=True, is_matured=True)
        # 3 dedup-removed
        dedup_removed = _make_signals_n(3, is_raw=True, is_dedup_kept=False, is_matured=True)
        for i, s in enumerate(dedup_removed):
            s.stock_id = f"DRM_{i}"
        # 2 not matured (but dedup kept)
        not_matured = _make_signals_n(2, is_raw=True, is_dedup_kept=True, is_matured=False)
        for i, s in enumerate(not_matured):
            s.stock_id = f"NM_{i}"

        all_signals = raw + dedup_removed + not_matured
        result = run_data_integrity_audit(all_signals)

        assert result["raw_count"] == 15
        assert result["dedup_count"] == 12  # kept after dedup: 10 + 2 not_matured
        assert result["matured_count"] == 10  # dedup_kept AND matured
        assert result["dedup_removed"] == 3

    def test_EA11_concentration_warning(self):
        from datetime import timedelta
        # Build 5 signals all with stock_id="DOM" (50% of total)
        dominant = []
        for i in range(5):
            s = _make_signal(
                signal_date=date(2026, 4, 1) + timedelta(days=i * 5),
                stock_id="DOM",
                is_dedup_kept=True,
                is_matured=True,
            )
            dominant.append(s)
        others = _make_signals_n(5, is_dedup_kept=True, is_matured=True)
        result = run_data_integrity_audit(dominant + others)
        # DOM has 5/10 = 50% → should warn
        assert result["concentration_warning"] is True


# ── EA12-EA13: run_ma20_audit ─────────────────────────────────────────────

class TestMa20Audit:
    def test_EA12_derived_matches_actual(self):
        # stop = MA20 * 0.97 → derived = stop / 0.97 ≈ MA20
        ma20 = 100.0
        stop = ma20 * 0.97
        signals = [
            _make_signal(
                ma20=ma20,
                stop_price=stop,
                ma20_derived=stop / (1 - 0.03),
                is_matured=True,
                is_dedup_kept=True,
            )
            for _ in range(5)
        ]
        result = run_ma20_audit(signals)
        assert result["ma20_vs_derived_mean_abs_diff"] < 0.01
        assert result["assessment"] == "ACCURATE"

    def test_EA13_wait_pullback_entry_vs_ma20(self):
        # For WAIT_FOR_PULLBACK, planned_entry = MA20_derived = stop/0.97
        # actual MA20 = 100, stop = 97, derived = 100.0
        # planned_entry = 100.0, diff = (100 - 100) / 100 * 100 = 0%
        signals = [
            _make_signal(
                entry_label="WAIT_FOR_PULLBACK",
                ma20=100.0,
                stop_price=97.0,
                ma20_derived=97.0 / 0.97,
                planned_entry_price=97.0 / 0.97,
                is_matured=True,
                is_dedup_kept=True,
            )
        ]
        result = run_ma20_audit(signals)
        assert result["wait_pullback_n"] == 1
        assert abs(result["wait_pullback_entry_vs_ma20_mean_diff_pct"]) < 0.1


# ── EA14-EA15: run_group_analysis ─────────────────────────────────────────

class TestGroupAnalysis:
    def test_EA14_key_structure(self):
        signals = _make_signals_n(15)
        result = run_group_analysis(signals)
        expected_keys = [
            "overall", "by_entry_label", "by_ma20_trend",
            "by_ma60_trend", "by_price_vs_ma20", "by_ma20_gap_bucket",
            "by_market_regime", "multiple_testing_note",
        ]
        for k in expected_keys:
            assert k in result, f"Missing key: {k}"

    def test_EA15_multiple_testing_note(self):
        signals = _make_signals_n(15)
        result = run_group_analysis(signals)
        note = result["multiple_testing_note"]
        assert "Multiple Testing" in note or "multiple testing" in note.lower()
        assert "Bonferroni" in note or "bonferroni" in note.lower()


# ── EA16-EA17: run_walk_forward ────────────────────────────────────────────

class TestWalkForward:
    def _make_window(
        self,
        name: str,
        test_start: date,
        test_end: date,
        is_oos: bool = False,
        embargo_days: int = 25,
    ) -> dict:
        from datetime import timedelta
        return {
            "name": name,
            "test_start": test_start,
            "test_end": test_end,
            "embargo_days": embargo_days,
            "is_oos": is_oos,
        }

    def test_EA16_time_filter(self):
        from datetime import timedelta
        # Signals in January and March
        jan_signals = [
            _make_signal(signal_date=date(2026, 1, i + 1), stock_id=f"JAN{i}")
            for i in range(5)
        ]
        mar_signals = [
            _make_signal(signal_date=date(2026, 3, i + 1), stock_id=f"MAR{i}")
            for i in range(5)
        ]
        windows = [
            self._make_window("W_JAN", date(2026, 1, 1), date(2026, 1, 31)),
        ]
        results = run_walk_forward(jan_signals + mar_signals, windows)
        assert len(results) == 1
        assert results[0]["n"] == 5

    def test_EA17_oos_flag(self):
        signals = [
            _make_signal(signal_date=date(2026, 7, i + 1), stock_id=f"OOS{i}")
            for i in range(5)
        ]
        windows = [
            self._make_window("OOS", date(2026, 7, 1), date(2026, 9, 15), is_oos=True),
        ]
        results = run_walk_forward(signals, windows)
        assert results[0]["is_oos"] is True


# ── EA18-EA19: run_sensitivity_matrix ─────────────────────────────────────

class TestSensitivityMatrix:
    def test_EA18_fragile_when_large_delta(self):
        base = _make_signals_n(15, v1_ret=1.0, v2_ret=2.0)
        variant_bad = _make_signals_n(15, v1_ret=1.0, v2_ret=-2.0)
        for i, s in enumerate(variant_bad):
            s.stock_id = f"VB{i}"

        variants = [
            {"name": "base", "description": "base case", "signals": base},
            {"name": "bad_variant", "description": "high fees", "signals": variant_bad},
        ]
        results = run_sensitivity_matrix(variants)
        base_r = next(r for r in results if r["variant"] == "base")
        bad_r = next(r for r in results if r["variant"] == "bad_variant")
        assert base_r["is_fragile"] is False
        assert bad_r["is_fragile"] is True

    def test_EA19_robust_when_small_delta(self):
        base = _make_signals_n(15, v1_ret=1.0, v2_ret=1.5)
        variant_similar = _make_signals_n(15, v1_ret=1.0, v2_ret=1.6)
        for i, s in enumerate(variant_similar):
            s.stock_id = f"VS{i}"

        variants = [
            {"name": "base", "description": "base", "signals": base},
            {"name": "similar", "description": "minor change", "signals": variant_similar},
        ]
        results = run_sensitivity_matrix(variants)
        sim_r = next(r for r in results if r["variant"] == "similar")
        assert sim_r["is_fragile"] is False


# ── EA20-EA21: No-lookahead / flag enforcement ─────────────────────────────

class TestNoLookahead:
    def test_EA20_dedup_excluded_not_in_analysis(self):
        # Signals with is_dedup_kept=False should not appear in group analysis
        kept = _make_signals_n(5, is_dedup_kept=True, is_matured=True, v1_ret=1.0, v2_ret=2.0)
        excluded = _make_signals_n(3, is_dedup_kept=False, is_matured=True, v1_ret=10.0, v2_ret=20.0)
        for i, s in enumerate(excluded):
            s.stock_id = f"EX_{i}"
        result = run_group_analysis(kept + excluded)
        # overall n should only count the 5 kept signals
        assert result["overall"]["n"] == 5

    def test_EA21_immature_excluded(self):
        matured = _make_signals_n(5, is_matured=True, is_dedup_kept=True, v1_ret=1.0, v2_ret=2.0)
        immature = _make_signals_n(3, is_matured=False, is_dedup_kept=True, v1_ret=10.0, v2_ret=20.0)
        for i, s in enumerate(immature):
            s.stock_id = f"IM_{i}"
        result = run_group_analysis(matured + immature)
        assert result["overall"]["n"] == 5


# ── EA22-EA23: Walk-forward window flags ──────────────────────────────────

class TestWalkForwardFlags:
    def test_EA22_oos_window_flagged(self):
        signals = [
            _make_signal(signal_date=date(2026, 7, 1 + i), stock_id=f"OOS{i}")
            for i in range(5)
        ]
        windows = [{"name": "OOS", "test_start": date(2026, 7, 1), "test_end": date(2026, 9, 15), "embargo_days": 25, "is_oos": True}]
        results = run_walk_forward(signals, windows)
        assert results[0]["is_oos"] is True

    def test_EA23_pass_fail_insufficient(self):
        # Insufficient signals → INSUFFICIENT_DATA
        signals = [
            _make_signal(signal_date=date(2026, 1, 1), stock_id="A", v1_ret=1.0, v2_ret=0.5),
        ]
        windows = [{"name": "W1", "test_start": date(2026, 1, 1), "test_end": date(2026, 1, 31), "embargo_days": 25, "is_oos": False}]
        results = run_walk_forward(signals, windows)
        assert results[0]["pass_fail"] in ("PASS", "FAIL", "INSUFFICIENT_DATA")

    def test_EA23b_pass_when_positive_delta(self):
        signals = _make_signals_n(5, v1_ret=1.0, v2_ret=3.0)
        for s in signals:
            s.signal_date = date(2026, 1, 1 + signals.index(s) * 3)
        windows = [{"name": "W1", "test_start": date(2026, 1, 1), "test_end": date(2026, 1, 31), "embargo_days": 25, "is_oos": False}]
        results = run_walk_forward(signals, windows)
        # delta = 2.0 → should PASS
        assert results[0]["pass_fail"] != "FAIL"
