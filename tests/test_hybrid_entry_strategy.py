"""
tests/test_hybrid_entry_strategy.py — Hybrid Entry Strategy V1 Tests

Coverage:
  HY01–HY05: HybridDecisionService rule tree
  HY06–HY08: HybridStrategyConfig immutability / defaults
  HY09–HY12: hybrid_action_to_simulation_params adapter
  HY13–HY17: HybridDecision dataclass fields and traceability
  HY18–HY22: annotate_hybrid (from hybrid_backtest.py)
  HY23–HY26: compute_three_strategy_comparison
  HY27–HY30: compute_action_distribution
  HY31–HY33: compute_hybrid_subgroup_analysis
  HY34–HY36: run_hybrid_analysis top-level
  HY37–HY40: no-lookahead / sample lineage parity
  HY41–HY43: idempotency / forward shadow schema correctness
  HY44       : rule version constants
"""

from __future__ import annotations

import sys
import os
from datetime import date, timedelta
from typing import List, Optional

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.research.hybrid_entry_strategy import (
    HybridAction,
    HybridDecision,
    HybridDecisionService,
    HybridForwardShadow,
    HybridStrategyConfig,
    RULE_VERSION,
    RULE_FROZEN_AT,
    RULE_FROZEN_COMMIT,
    MA20_RISING_THRESHOLD,
    MA20_FALLING_THRESHOLD,
    hybrid_action_to_simulation_params,
)
from src.research.hybrid_backtest import (
    HybridSignalResult,
    annotate_hybrid,
    compute_action_distribution,
    compute_hybrid_subgroup_analysis,
    compute_three_strategy_comparison,
    run_hybrid_analysis,
    IN_SAMPLE_WARNING,
)
from src.research.effectiveness_analyzer import EnrichedSignal


# ── Helpers ───────────────────────────────────────────────────────────────────

_BASE_DATE = date(2026, 11, 10)
_SVC = HybridDecisionService()


def _decide(
    entry_label: str = "WAIT_FOR_PULLBACK",
    market_regime: str = "bull",
    ma20_trend: str = "rising",
    stock_id: str = "2330",
    signal_date: date = _BASE_DATE,
    **kwargs,
) -> HybridDecision:
    return _SVC.decide(
        stock_id=stock_id,
        signal_date=signal_date,
        v2_entry_label=entry_label,
        market_regime=market_regime,
        ma20_trend=ma20_trend,
        **kwargs,
    )


def _make_enriched(
    v1_ret: float = 1.0,
    v2_ret: float = 1.5,
    entry_label: str = "WAIT_FOR_PULLBACK",
    market_regime: str = "bear",
    ma20_trend: str = "flat",
    ma20_slope_pct: float = 0.0,
    signal_date: Optional[date] = None,
    stock_id: str = "TEST",
    is_dedup_kept: bool = True,
    is_matured: bool = True,
) -> EnrichedSignal:
    d = signal_date or _BASE_DATE
    return EnrichedSignal(
        signal_date=d,
        stock_id=stock_id,
        entry_label=entry_label,
        entry_price=100.0,
        stop_price=97.0,
        target_price=106.0,
        ma20=100.0,
        ma20_gap_pct=0.5,
        prior_20d_high=105.0,
        ma20_slope_pct=ma20_slope_pct,
        ma20_trend=ma20_trend,
        market_regime=market_regime,
        v1_ret=v1_ret,
        v2_ret=v2_ret,
        paired_delta=round(v2_ret - v1_ret, 6),
        is_dedup_kept=is_dedup_kept,
        is_matured=is_matured,
    )


def _make_enriched_n(n: int, **overrides) -> List[EnrichedSignal]:
    return [
        _make_enriched(
            stock_id=f"S{i:03d}",
            signal_date=_BASE_DATE + timedelta(days=i * 5),
            **overrides,
        )
        for i in range(n)
    ]


# ── HY01–HY05: Rule tree ──────────────────────────────────────────────────────

class TestRuleTree:

    def test_HY01_p1_bear_pullback(self):
        """P1: Bear + WAIT_FOR_PULLBACK → WAIT_PULLBACK."""
        d = _decide(entry_label="WAIT_FOR_PULLBACK", market_regime="bear", ma20_trend="rising")
        assert d.hybrid_action == HybridAction.WAIT_PULLBACK
        assert d.rule_priority == 1

    def test_HY02_p2_flat_pullback(self):
        """P2: Flat MA20 + WAIT_FOR_PULLBACK → WAIT_PULLBACK (even in bull)."""
        d = _decide(entry_label="WAIT_FOR_PULLBACK", market_regime="bull", ma20_trend="flat")
        assert d.hybrid_action == HybridAction.WAIT_PULLBACK
        assert d.rule_priority == 2

    def test_HY03_p1_beats_p2_bear_flat(self):
        """Bear + Flat MA20 → P1 fires (priority 1 wins over priority 2)."""
        d = _decide(entry_label="WAIT_FOR_PULLBACK", market_regime="bear", ma20_trend="flat")
        assert d.rule_priority == 1  # P1 fires first

    def test_HY04_p3_bull_rising_direct(self):
        """P3: Bull + Rising MA20 → DIRECT_NEXT_OPEN."""
        d = _decide(entry_label="ENTRY_READY", market_regime="bull", ma20_trend="rising")
        assert d.hybrid_action == HybridAction.DIRECT_NEXT_OPEN
        assert d.rule_priority == 3

    def test_HY05_p4_default_direct(self):
        """P4: Neutral + flat → DIRECT_NEXT_OPEN (default)."""
        d = _decide(entry_label="ENTRY_READY", market_regime="neutral", ma20_trend="flat")
        assert d.hybrid_action == HybridAction.DIRECT_NEXT_OPEN
        assert d.rule_priority == 4

    def test_HY05b_wait_for_breakout_always_direct(self):
        """WAIT_FOR_BREAKOUT in bear + flat → DIRECT_NEXT_OPEN (rules only fire for WAIT_FOR_PULLBACK)."""
        d = _decide(entry_label="WAIT_FOR_BREAKOUT", market_regime="bear", ma20_trend="flat")
        assert d.hybrid_action == HybridAction.DIRECT_NEXT_OPEN


# ── HY06–HY08: Config ─────────────────────────────────────────────────────────

class TestConfig:

    def test_HY06_defaults(self):
        cfg = HybridStrategyConfig()
        assert cfg.version_id == RULE_VERSION
        assert cfg.frozen_at == RULE_FROZEN_AT
        assert cfg.frozen_commit == RULE_FROZEN_COMMIT
        assert cfg.ma20_rising_threshold == MA20_RISING_THRESHOLD
        assert cfg.ma20_falling_threshold == MA20_FALLING_THRESHOLD

    def test_HY07_custom_config_used(self):
        cfg = HybridStrategyConfig(version_id="test_v2")
        svc = HybridDecisionService(cfg)
        d = svc.decide("X", _BASE_DATE, "WAIT_FOR_PULLBACK", "bear", "rising")
        assert d.rule_version == "test_v2"

    def test_HY08_classify_ma20_trend(self):
        svc = HybridDecisionService()
        assert svc.classify_ma20_trend(0.4) == "rising"
        assert svc.classify_ma20_trend(-0.4) == "falling"
        assert svc.classify_ma20_trend(0.0) == "flat"
        assert svc.classify_ma20_trend(0.3) == "flat"   # exactly at threshold → flat
        assert svc.classify_ma20_trend(-0.3) == "flat"


# ── HY09–HY12: Simulation adapter ────────────────────────────────────────────

class TestSimAdapter:

    def test_HY09_wait_pullback_maps_correctly(self):
        label, high = hybrid_action_to_simulation_params(
            HybridAction.WAIT_PULLBACK, "WAIT_FOR_PULLBACK", 105.0
        )
        assert label == "WAIT_FOR_PULLBACK"
        assert high == 105.0

    def test_HY10_direct_next_open_maps_to_entry_ready(self):
        label, high = hybrid_action_to_simulation_params(
            HybridAction.DIRECT_NEXT_OPEN, "WAIT_FOR_PULLBACK", 105.0
        )
        assert label == "ENTRY_READY"

    def test_HY11_wait_breakout_maps_correctly(self):
        label, high = hybrid_action_to_simulation_params(
            HybridAction.WAIT_BREAKOUT, "WAIT_FOR_BREAKOUT", 110.0
        )
        assert label == "WAIT_FOR_BREAKOUT"
        assert high == 110.0

    def test_HY12_skip_preserves_original_label(self):
        label, high = hybrid_action_to_simulation_params(
            HybridAction.SKIP, "WAIT_FOR_PULLBACK", 105.0
        )
        assert label == "WAIT_FOR_PULLBACK"


# ── HY13–HY17: HybridDecision dataclass ──────────────────────────────────────

class TestHybridDecision:

    def test_HY13_all_fields_populated(self):
        d = _decide(
            entry_label="WAIT_FOR_PULLBACK",
            market_regime="bear",
            ma20_trend="rising",
            ma20_slope_pct=0.5,
            ma20_gap_pct=1.2,
        )
        assert d.stock_id == "2330"
        assert d.signal_date == _BASE_DATE
        assert d.v2_entry_label == "WAIT_FOR_PULLBACK"
        assert d.market_regime == "bear"
        assert d.ma20_trend == "rising"
        assert isinstance(d.ma20_slope_pct, float)
        assert d.rule_version == RULE_VERSION
        assert d.feature_cutoff_date == _BASE_DATE
        assert d.ma20_gap_pct == 1.2

    def test_HY14_feature_cutoff_equals_signal_date(self):
        """feature_cutoff_date must equal signal_date — no future data used."""
        sig_date = date(2026, 12, 1)
        d = _SVC.decide("X", sig_date, "ENTRY_READY", "bull", "rising")
        assert d.feature_cutoff_date == sig_date

    def test_HY15_rule_reason_contains_p_number(self):
        d = _decide("WAIT_FOR_PULLBACK", "bear", "flat")
        assert "P1:" in d.rule_reason

    def test_HY16_p2_reason_mentions_flat(self):
        d = _decide("WAIT_FOR_PULLBACK", "bull", "flat")
        assert "P2:" in d.rule_reason
        assert "flat" in d.rule_reason.lower() or "Flat" in d.rule_reason

    def test_HY17_calculated_at_is_set(self):
        from datetime import datetime
        d = _decide()
        assert isinstance(d.calculated_at, datetime)


# ── HY18–HY22: annotate_hybrid ────────────────────────────────────────────────

class TestAnnotateHybrid:

    def test_HY18_bear_pullback_uses_v2_ret(self):
        """Bear + WAIT_FOR_PULLBACK → hybrid_ret = v2_ret."""
        sigs = [_make_enriched(v1_ret=1.0, v2_ret=2.5, entry_label="WAIT_FOR_PULLBACK", market_regime="bear")]
        results = annotate_hybrid(sigs)
        assert len(results) == 1
        assert results[0].hybrid_action == HybridAction.WAIT_PULLBACK
        assert results[0].hybrid_ret == pytest.approx(2.5)

    def test_HY19_bull_rising_uses_v1_ret(self):
        """Bull + Rising + ENTRY_READY → hybrid_ret = v1_ret."""
        sigs = [_make_enriched(v1_ret=1.5, v2_ret=1.5, entry_label="ENTRY_READY",
                               market_regime="bull", ma20_trend="rising")]
        results = annotate_hybrid(sigs)
        assert results[0].hybrid_action == HybridAction.DIRECT_NEXT_OPEN
        assert results[0].hybrid_ret == pytest.approx(1.5)

    def test_HY20_switched_signal_uses_v1(self):
        """Bull + Rising + WAIT_FOR_PULLBACK → hybrid switches to DIRECT, uses v1_ret."""
        sigs = [_make_enriched(v1_ret=2.0, v2_ret=0.5, entry_label="WAIT_FOR_PULLBACK",
                               market_regime="bull", ma20_trend="rising")]
        results = annotate_hybrid(sigs)
        assert results[0].hybrid_action == HybridAction.DIRECT_NEXT_OPEN
        assert results[0].hybrid_ret == pytest.approx(2.0)

    def test_HY21_excludes_non_dedup(self):
        sig = _make_enriched(is_dedup_kept=False)
        results = annotate_hybrid([sig])
        assert len(results) == 0

    def test_HY22_excludes_non_matured(self):
        sig = _make_enriched(is_matured=False)
        results = annotate_hybrid([sig])
        assert len(results) == 0


# ── HY23–HY26: compute_three_strategy_comparison ─────────────────────────────

class TestThreeStrategyComparison:

    def _make_results_n(self, n: int, v1_ret=1.0, v2_ret=1.5,
                        hybrid_action=HybridAction.WAIT_PULLBACK) -> List[HybridSignalResult]:
        from src.research.hybrid_backtest import HybridSignalResult
        return [
            HybridSignalResult(
                signal_date=_BASE_DATE + timedelta(days=i * 5),
                stock_id=f"S{i:03d}",
                entry_label="WAIT_FOR_PULLBACK",
                market_regime="bear",
                ma20_trend="flat",
                ma20_slope_pct=0.0,
                ma20_gap_pct=1.0,
                v1_ret=v1_ret,
                v2_ret=v2_ret,
                hybrid_action=hybrid_action,
                rule_reason="P1",
                rule_priority=1,
                hybrid_ret=v2_ret if hybrid_action == HybridAction.WAIT_PULLBACK else v1_ret,
                v2_v1_delta=round(v2_ret - v1_ret, 6),
                hybrid_v1_delta=round(
                    (v2_ret if hybrid_action == HybridAction.WAIT_PULLBACK else v1_ret) - v1_ret,
                    6,
                ),
            )
            for i in range(n)
        ]

    def test_HY23_has_in_sample_warning(self):
        results = self._make_results_n(20)
        comp = compute_three_strategy_comparison(results)
        assert "in_sample_warning" in comp
        assert "IN-SAMPLE" in comp["in_sample_warning"] or "RETROSPECTIVE" in comp["in_sample_warning"]

    def test_HY24_strategy_counts_match(self):
        n = 30
        results = self._make_results_n(n)
        comp = compute_three_strategy_comparison(results)
        assert comp["strategies"]["v1"]["n"] == n
        assert comp["strategies"]["v2_fos"]["n"] == n
        assert comp["strategies"]["hybrid"]["n"] == n

    def test_HY25_hybrid_vs_v1_delta_correct(self):
        """When hybrid_ret = v2_ret = 2.0 and v1_ret = 1.0, delta = +1.0."""
        results = self._make_results_n(20, v1_ret=1.0, v2_ret=2.0)
        comp = compute_three_strategy_comparison(results)
        delta = comp["paired_deltas"]["hybrid_vs_v1"]["mean"]
        assert abs(delta - 1.0) < 0.01

    def test_HY26_empty_signals_returns_error(self):
        comp = compute_three_strategy_comparison([])
        assert "error" in comp


# ── HY27–HY30: compute_action_distribution ───────────────────────────────────

class TestActionDistribution:

    def test_HY27_action_counts_sum_to_total(self):
        sigs = _make_enriched_n(20)
        results = annotate_hybrid(sigs)
        dist = compute_action_distribution(results)
        total = sum(dist["action_counts"].values())
        assert total == dist["total"]

    def test_HY28_by_entry_label_present(self):
        sigs = _make_enriched_n(5) + _make_enriched_n(5, entry_label="ENTRY_READY", market_regime="bull", ma20_trend="rising")
        results = annotate_hybrid(sigs)
        dist = compute_action_distribution(results)
        assert "by_entry_label" in dist

    def test_HY29_bear_pullback_all_wait(self):
        """All bear + WAIT_FOR_PULLBACK → all WAIT_PULLBACK actions."""
        sigs = _make_enriched_n(10, entry_label="WAIT_FOR_PULLBACK", market_regime="bear", ma20_trend="rising")
        results = annotate_hybrid(sigs)
        dist = compute_action_distribution(results)
        assert dist["action_counts"].get("WAIT_PULLBACK", 0) == 10

    def test_HY30_empty_input(self):
        dist = compute_action_distribution([])
        assert dist == {}


# ── HY31–HY33: compute_hybrid_subgroup_analysis ──────────────────────────────

class TestSubgroupAnalysis:

    def _make_mixed_results(self) -> List[HybridSignalResult]:
        """Mix of bear/bull regimes and pullback/direct actions."""
        sigs_bear = _make_enriched_n(15, market_regime="bear", entry_label="WAIT_FOR_PULLBACK")
        sigs_bull = _make_enriched_n(15, market_regime="bull", entry_label="ENTRY_READY", ma20_trend="rising", v1_ret=2.0, v2_ret=2.0)
        return annotate_hybrid(sigs_bear + sigs_bull)

    def test_HY31_subgroup_keys_present(self):
        results = self._make_mixed_results()
        sub = compute_hybrid_subgroup_analysis(results)
        assert "by_hybrid_action" in sub
        assert "by_market_regime" in sub
        assert "by_ma20_trend" in sub
        assert "by_entry_label" in sub

    def test_HY32_bear_group_has_stats(self):
        results = self._make_mixed_results()
        sub = compute_hybrid_subgroup_analysis(results)
        bear_stats = sub["by_market_regime"].get("bear", {})
        assert bear_stats.get("n", 0) > 0

    def test_HY33_empty_input(self):
        sub = compute_hybrid_subgroup_analysis([])
        assert sub == {}


# ── HY34–HY36: run_hybrid_analysis ───────────────────────────────────────────

class TestRunHybridAnalysis:

    def test_HY34_full_pipeline_returns_all_keys(self):
        sigs = _make_enriched_n(30)
        result = run_hybrid_analysis(sigs)
        assert "in_sample_warning" in result
        assert "comparison" in result
        assert "action_distribution" in result
        assert "subgroup_analysis" in result
        assert "switch_summary" in result

    def test_HY35_switch_summary_counts_pullback_signals(self):
        sigs = _make_enriched_n(20, entry_label="WAIT_FOR_PULLBACK", market_regime="bear")
        result = run_hybrid_analysis(sigs)
        ss = result["switch_summary"]
        assert ss["total_wait_for_pullback"] == 20
        assert ss["kept_waiting"] == 20     # all bear → all keep waiting
        assert ss["switched_to_direct"] == 0

    def test_HY36_in_sample_warning_present(self):
        sigs = _make_enriched_n(10)
        result = run_hybrid_analysis(sigs)
        assert "RETROSPECTIVE" in result["in_sample_warning"] or "IN-SAMPLE" in result["in_sample_warning"]


# ── HY37–HY40: No-lookahead and sample lineage ───────────────────────────────

class TestNoLookahead:

    def test_HY37_feature_cutoff_equals_signal_date(self):
        """HybridDecision.feature_cutoff_date must never be after signal_date."""
        for regime in ("bull", "bear", "neutral", "unknown"):
            for trend in ("rising", "flat", "falling"):
                d = _decide(market_regime=regime, ma20_trend=trend)
                assert d.feature_cutoff_date <= d.signal_date

    def test_HY38_hybrid_ret_is_v1_or_v2(self):
        """hybrid_ret must be exactly v1_ret or v2_ret — no new simulation."""
        sigs = _make_enriched_n(30)
        results = annotate_hybrid(sigs)
        for r in results:
            is_v1 = abs(r.hybrid_ret - r.v1_ret) < 1e-9
            is_v2 = abs(r.hybrid_ret - r.v2_ret) < 1e-9
            assert is_v1 or is_v2, f"hybrid_ret={r.hybrid_ret} not equal to v1={r.v1_ret} or v2={r.v2_ret}"

    def test_HY39_hybrid_v1_delta_derived_from_hybrid_ret(self):
        """hybrid_v1_delta = hybrid_ret - v1_ret."""
        sigs = _make_enriched_n(20)
        results = annotate_hybrid(sigs)
        for r in results:
            expected = round(r.hybrid_ret - r.v1_ret, 6)
            assert abs(r.hybrid_v1_delta - expected) < 1e-8

    def test_HY40_in_sample_disclaimer_in_comparison(self):
        """Three-strategy comparison output must carry the in-sample warning."""
        sigs = _make_enriched_n(15)
        results = annotate_hybrid(sigs)
        comp = compute_three_strategy_comparison(results)
        assert "RETROSPECTIVE" in comp.get("in_sample_warning", "") or \
               "IN-SAMPLE" in comp.get("in_sample_warning", "")


# ── HY41–HY43: Idempotency / forward shadow ──────────────────────────────────

class TestForwardShadowIdempotency:

    def test_HY41_hybrid_decision_deterministic(self):
        """Same inputs → same decision (no randomness)."""
        d1 = _decide("WAIT_FOR_PULLBACK", "bear", "flat")
        d2 = _decide("WAIT_FOR_PULLBACK", "bear", "flat")
        assert d1.hybrid_action == d2.hybrid_action
        assert d1.rule_priority == d2.rule_priority
        assert d1.rule_reason == d2.rule_reason

    def test_HY42_annotate_hybrid_deterministic(self):
        """annotate_hybrid is pure — same input → same output."""
        sigs = _make_enriched_n(20)
        r1 = annotate_hybrid(sigs)
        r2 = annotate_hybrid(sigs)
        assert len(r1) == len(r2)
        for a, b in zip(r1, r2):
            assert a.hybrid_action == b.hybrid_action
            assert a.hybrid_ret == pytest.approx(b.hybrid_ret)

    def test_HY43_hybrid_forward_shadow_dataclass_has_pk_fields(self):
        """HybridForwardShadow must have all three fields of the idempotency key."""
        from datetime import datetime, timezone
        shadow = HybridForwardShadow(
            stock_id="2330",
            signal_date=_BASE_DATE,
            rule_version=RULE_VERSION,
            v2_entry_label="WAIT_FOR_PULLBACK",
            market_regime="bear",
            ma20_trend="flat",
            ma20_slope_pct=0.1,
            hybrid_action="WAIT_PULLBACK",
            rule_reason="P1",
            rule_priority=1,
            feature_cutoff_date=_BASE_DATE,
            calculated_at=datetime.now(timezone.utc),
        )
        assert shadow.stock_id == "2330"
        assert shadow.rule_version == RULE_VERSION
        assert shadow.outcome_20d is None  # not yet matured


# ── HY44: Constants ───────────────────────────────────────────────────────────

class TestConstants:

    def test_HY44_rule_version_frozen(self):
        assert RULE_VERSION == "hybrid_v1"
        assert RULE_FROZEN_AT == "2026-11-05T00:00:00"
        assert RULE_FROZEN_COMMIT == "6602c3b"

    def test_HY44b_ma20_thresholds(self):
        assert MA20_RISING_THRESHOLD == 0.3
        assert MA20_FALLING_THRESHOLD == -0.3
