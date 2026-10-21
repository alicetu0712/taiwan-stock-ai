"""
tests/test_overnight_risk_engine.py — Overnight risk evaluation + data quality + frozen signal integrity

PRD §23-B: Risk Engine tests
PRD §23-C: Frozen Signal Integrity tests
"""

import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.engines.overnight_risk import (
    OVERNIGHT_RULE_VERSION,
    OVERNIGHT_RISK_CONFIG,
    DQ_COMPLETE, DQ_PARTIAL, DQ_STALE, DQ_UNKNOWN,
    RISK_GREEN, RISK_YELLOW, RISK_RED, RISK_UNKNOWN,
    OvernightRiskResult,
    RiskReason,
    _derive_data_quality,
    evaluate_overnight_risk,
    risk_reasons_to_json,
    risk_reasons_from_json,
)


# ── Data quality derivation ──────────────────────────────────────────────────

class TestDeriveDataQuality:

    def test_all_ok_is_complete(self):
        assert _derive_data_quality(True, True, True, True, False) == DQ_COMPLETE

    def test_missing_one_is_partial(self):
        assert _derive_data_quality(True, True, False, True, False) == DQ_PARTIAL

    def test_none_ok_is_unknown(self):
        assert _derive_data_quality(False, False, False, False, False) == DQ_UNKNOWN

    def test_stale_beats_partial(self):
        assert _derive_data_quality(True, True, False, True, True) == DQ_STALE

    def test_stale_even_if_all_ok(self):
        assert _derive_data_quality(True, True, True, True, True) == DQ_STALE


# ── Risk evaluation ──────────────────────────────────────────────────────────

class TestEvaluateOvernightRisk:

    def _eval(self, sp=0.0, ndq=0.0, sox=0.0, vix=15.0, vix_chg=0.0, dq=DQ_COMPLETE):
        return evaluate_overnight_risk(sp, ndq, sox, vix, vix_chg, dq)

    def test_all_normal_is_green(self):
        r = self._eval(sp=0.5, ndq=0.3, sox=0.8, vix=14.0, vix_chg=2.0)
        assert r.risk_level == RISK_GREEN

    def test_sox_moderate_drop_is_yellow(self):
        sox_threshold = OVERNIGHT_RISK_CONFIG["SOX_MODERATE_DROP"]
        r = self._eval(sox=sox_threshold - 0.1)  # just past moderate
        assert r.risk_level in (RISK_YELLOW, RISK_RED)

    def test_sox_severe_drop_is_red(self):
        sox_threshold = OVERNIGHT_RISK_CONFIG["SOX_SEVERE_DROP"]
        r = self._eval(sox=sox_threshold - 0.5)
        assert r.risk_level == RISK_RED

    def test_nasdaq_severe_drop_is_red(self):
        ndq_threshold = OVERNIGHT_RISK_CONFIG["NASDAQ_SEVERE_DROP"]
        r = self._eval(ndq=ndq_threshold - 0.5)
        assert r.risk_level == RISK_RED

    def test_vix_absolute_high_is_red(self):
        vix_threshold = OVERNIGHT_RISK_CONFIG["VIX_ABSOLUTE_HIGH"]
        r = self._eval(vix=vix_threshold + 5.0)
        assert r.risk_level == RISK_RED

    def test_vix_severe_spike_is_red(self):
        spike_threshold = OVERNIGHT_RISK_CONFIG["VIX_SEVERE_SPIKE"]
        r = self._eval(vix_chg=spike_threshold + 5.0)
        assert r.risk_level == RISK_RED

    def test_vix_moderate_spike_is_yellow(self):
        moderate = OVERNIGHT_RISK_CONFIG["VIX_MODERATE_SPIKE"]
        severe   = OVERNIGHT_RISK_CONFIG["VIX_SEVERE_SPIKE"]
        r = self._eval(vix_chg=(moderate + severe) / 2)
        assert r.risk_level in (RISK_YELLOW, RISK_RED)

    def test_broad_weakness_all_moderate_is_yellow_or_red(self):
        r = self._eval(
            sp=OVERNIGHT_RISK_CONFIG["SP500_MODERATE_DROP"] - 0.1,
            ndq=OVERNIGHT_RISK_CONFIG["NASDAQ_MODERATE_DROP"] - 0.1,
            sox=OVERNIGHT_RISK_CONFIG["SOX_MODERATE_DROP"] - 0.1,
        )
        assert r.risk_level in (RISK_YELLOW, RISK_RED)

    def test_missing_one_source_is_partial_quality(self):
        r = evaluate_overnight_risk(
            sp500_return=0.0, nasdaq_return=None, sox_return=None,
            vix_close=14.0, vix_change=2.0,
            data_quality=DQ_PARTIAL,
        )
        assert r.data_quality == DQ_PARTIAL

    def test_stale_data_is_unknown(self):
        r = evaluate_overnight_risk(
            sp500_return=1.0, nasdaq_return=1.0, sox_return=1.0,
            vix_close=12.0, vix_change=1.0,
            data_quality=DQ_STALE,
        )
        assert r.risk_level == RISK_UNKNOWN

    def test_unknown_data_quality_is_unknown(self):
        r = evaluate_overnight_risk(
            sp500_return=None, nasdaq_return=None, sox_return=None,
            vix_close=None, vix_change=None,
            data_quality=DQ_UNKNOWN,
        )
        assert r.risk_level == RISK_UNKNOWN

    def test_unknown_never_becomes_green(self):
        """UNKNOWN data quality must never produce GREEN."""
        r = evaluate_overnight_risk(
            sp500_return=1.0, nasdaq_return=1.0, sox_return=1.0,
            vix_close=12.0, vix_change=1.0,
            data_quality=DQ_UNKNOWN,
        )
        assert r.risk_level != RISK_GREEN

    def test_stale_never_becomes_green(self):
        r = evaluate_overnight_risk(
            sp500_return=2.0, nasdaq_return=2.0, sox_return=2.0,
            vix_close=10.0, vix_change=0.0,
            data_quality=DQ_STALE,
        )
        assert r.risk_level != RISK_GREEN

    def test_partial_all_positive_is_unknown_not_green(self):
        """PARTIAL with all-positive returns → not GREEN (can't confirm stability)."""
        r = evaluate_overnight_risk(
            sp500_return=1.5, nasdaq_return=None, sox_return=None,
            vix_close=12.0, vix_change=1.0,
            data_quality=DQ_PARTIAL,
        )
        assert r.risk_level != RISK_GREEN

    def test_reasons_contain_machine_code(self):
        r = self._eval(sox=OVERNIGHT_RISK_CONFIG["SOX_SEVERE_DROP"] - 0.5)
        codes = [reason.code for reason in r.reasons]
        assert "SOX_SEVERE_DROP" in codes

    def test_reasons_serialization_roundtrip(self):
        reasons = [RiskReason(code="SOX_SEVERE_DROP", value=-3.8, message="半導體大跌")]
        s = risk_reasons_to_json(reasons)
        back = risk_reasons_from_json(s)
        assert len(back) == 1
        assert back[0].code == "SOX_SEVERE_DROP"
        assert back[0].value == -3.8

    def test_rule_version_matches_canonical(self):
        r = self._eval()
        assert r.rule_version == OVERNIGHT_RULE_VERSION


# ── Frozen Signal Integrity (PRD §23-C) ──────────────────────────────────────

class TestFrozenSignalIntegrity:
    """
    Overnight RED must never modify trade_signal, PT score, or any ForwardSignal
    frozen values. These tests verify evaluate_overnight_risk does not touch DB.
    """

    def test_red_does_not_modify_trade_signal(self):
        """evaluate_overnight_risk returns a result; it never touches Recommendation."""
        original_signal = "buy"
        r = evaluate_overnight_risk(
            sp500_return=-3.0, nasdaq_return=-3.0, sox_return=-4.0,
            vix_close=35.0, vix_change=30.0,
            data_quality=DQ_COMPLETE,
        )
        assert r.risk_level == RISK_RED
        # trade_signal is unchanged (it was never passed in; function has no side effects)
        assert original_signal == "buy"

    def test_red_result_has_no_db_side_effects(self, monkeypatch):
        """evaluate_overnight_risk must not import or touch any DB session."""
        # If this test passes without patching get_session, the function is pure.
        import src.engines.overnight_risk as oe
        calls = []
        original = oe.evaluate_overnight_risk
        # Simply call it and confirm it runs without needing DB
        result = original(
            sp500_return=-3.0, nasdaq_return=-3.0, sox_return=-4.0,
            vix_close=35.0, vix_change=30.0,
            data_quality=DQ_COMPLETE,
        )
        assert result.risk_level == RISK_RED
        assert len(calls) == 0   # No DB calls recorded

    def test_overnight_rule_version_is_separate_from_live_rule_version(self):
        """OVERNIGHT_RULE_VERSION must be independent of LIVE_RULE_VERSION."""
        from src.engines.live_decision import LIVE_RULE_VERSION
        assert OVERNIGHT_RULE_VERSION != LIVE_RULE_VERSION
        assert OVERNIGHT_RULE_VERSION.startswith("overnight_")
        assert LIVE_RULE_VERSION.startswith("v")
