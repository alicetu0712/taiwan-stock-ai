"""
Session 41 validation tests.
Groups: SA (Statistical Significance Audit), RP (Reproduction),
        AC (Avoid Chasing), RB (Robustness), OR (Outcome Readiness),
        ES (Evidence Strength)
"""
import sqlite3

import pytest

# ---------------------------------------------------------------------------
# In-memory helpers
# ---------------------------------------------------------------------------

def _build_comparison_rows(strategy_data: dict) -> list:
    """Build minimal ComparisonRow-like objects for in-memory tests."""
    rows = []
    for strategy, signals in strategy_data.items():
        for item in signals:
            rows.append(type("R", (), {
                "stock_id": item["stock_id"],
                "signal_date": item["signal_date"],
                "strategy": strategy,
                "net_return": item["net_return"],
                "benchmark_return": item.get("benchmark_return", -0.04),
                "v3_decision": item.get("v3_decision"),
                "filled": item.get("filled", True),
            })())
    return rows


# ---------------------------------------------------------------------------
# SA: Statistical Significance Audit (in-memory)
# ---------------------------------------------------------------------------

class TestSA01_ClusteredTest:
    """SA01: cluster-corrected test with known data gives expected result."""

    def _make_strat_returns(self):
        import sys
        sys.path.insert(0, "src")
        from collections import defaultdict
        strat = defaultdict(dict)
        # 7 dates, ~10 signals each; D_v3 returns 0, A_direct returns -0.05
        dates = [f"2026-10-{d:02d}" for d in range(9, 16)]
        for i, dt in enumerate(dates):
            for j in range(10):
                key = (f"S{i*10+j:04d}", dt)
                strat["D_v3"][key] = 0.0
                strat["A_direct"][key] = -0.05
        return strat

    def test_sa01_cluster_count(self):
        import sys
        sys.path.insert(0, "src")
        from research.statistical_significance_audit import _run_clustered_test
        strat = self._make_strat_returns()
        result = _run_clustered_test(strat, "D_v3", "A_direct")
        assert result.n_clusters == 7

    def test_sa01_grand_mean_positive(self):
        import sys
        sys.path.insert(0, "src")
        from research.statistical_significance_audit import _run_clustered_test
        strat = self._make_strat_returns()
        result = _run_clustered_test(strat, "D_v3", "A_direct")
        assert result.grand_mean == pytest.approx(0.05, abs=1e-6)

    def test_sa01_p_value_lt05_with_consistent_data(self):
        import sys
        sys.path.insert(0, "src")
        from research.statistical_significance_audit import _run_clustered_test
        strat = self._make_strat_returns()
        result = _run_clustered_test(strat, "D_v3", "A_direct")
        # All 7 dates have exact delta 0.05 → t-stat = infinity, p ≈ 0
        assert result.p_value_ttest < 0.05


class TestSA02_DowngradeLogic:
    """SA02: SIGNIFICANT_POSITIVE is downgraded when CI includes zero."""

    def test_sa02_inconclusive_verdict_when_ci_includes_zero(self):
        import sys
        sys.path.insert(0, "src")
        from research.statistical_significance_audit import (
            SignificanceVerdict,
            _run_clustered_test,
        )
        from collections import defaultdict

        strat = defaultdict(dict)
        # 7 dates with opposite sign alternating → CI definitely includes zero
        dates = [f"2026-10-{d:02d}" for d in range(9, 16)]
        signs = [1, -1, 1, -1, 1, -1, 1]
        for i, (dt, sign) in enumerate(zip(dates, signs)):
            for j in range(5):
                key = (f"S{i*5+j:04d}", dt)
                strat["D_v3"][key] = sign * 0.05
                strat["A_direct"][key] = 0.0
        result = _run_clustered_test(strat, "D_v3", "A_direct")
        assert result.ci_includes_zero
        assert result.corrected_verdict == SignificanceVerdict.SIGNIFICANCE_INCONCLUSIVE

    def test_sa02_downgraded_flag(self):
        import sys
        sys.path.insert(0, "src")
        from research.statistical_significance_audit import _run_clustered_test
        from collections import defaultdict

        strat = defaultdict(dict)
        dates = [f"2026-10-{d:02d}" for d in range(9, 16)]
        signs = [1, -1, 1, -1, 1, -1, 1]
        for i, (dt, sign) in enumerate(zip(dates, signs)):
            for j in range(5):
                key = (f"S{i*5+j:04d}", dt)
                strat["D_v3"][key] = sign * 0.05
                strat["A_direct"][key] = 0.0
        result = _run_clustered_test(strat, "D_v3", "A_direct", "SIGNIFICANT_POSITIVE")
        assert result.downgraded


class TestSA03_MicroClusterWarning:
    """SA03: dates with n < 10 get MICRO_CLUSTER warning."""

    def test_sa03_micro_cluster_identified(self):
        import sys
        sys.path.insert(0, "src")
        from research.statistical_significance_audit import _run_clustered_test
        from collections import defaultdict

        strat = defaultdict(dict)
        # Date 1 has n=4 (micro), others n=20
        for j in range(4):
            key = (f"TINY{j:03d}", "2026-10-09")
            strat["D_v3"][key] = 0.1
            strat["A_direct"][key] = 0.0
        for d in range(10, 16):
            dt = f"2026-10-{d:02d}"
            for j in range(20):
                key = (f"S{d*20+j:04d}", dt)
                strat["D_v3"][key] = 0.02
                strat["A_direct"][key] = 0.0

        result = _run_clustered_test(strat, "D_v3", "A_direct")
        assert "2026-10-09" in result.micro_cluster_dates

    def test_sa03_non_micro_dates_not_flagged(self):
        import sys
        sys.path.insert(0, "src")
        from research.statistical_significance_audit import _run_clustered_test
        from collections import defaultdict

        strat = defaultdict(dict)
        for d in range(9, 16):
            dt = f"2026-10-{d:02d}"
            for j in range(20):
                key = (f"S{d*20+j:04d}", dt)
                strat["D_v3"][key] = 0.02
                strat["A_direct"][key] = 0.0

        result = _run_clustered_test(strat, "D_v3", "A_direct")
        assert len(result.micro_cluster_dates) == 0


class TestSA04_LodoSignStability:
    """SA04: leave-one-date-out sign stability."""

    def test_sa04_stable_sign_all_positive_dates(self):
        import sys
        sys.path.insert(0, "src")
        from research.statistical_significance_audit import _run_lodo
        from collections import defaultdict

        strat = defaultdict(dict)
        dates = [f"2026-10-{d:02d}" for d in range(9, 16)]
        for i, dt in enumerate(dates):
            for j in range(10):
                key = (f"S{i*10+j:04d}", dt)
                strat["D_v3"][key] = 0.03
                strat["A_direct"][key] = 0.0
        results = _run_lodo(strat, "D_v3", "A_direct", full_grand_mean=0.03)
        assert all(not r.sign_change for r in results)

    def test_sa04_sign_change_detected_when_one_date_flips(self):
        import sys
        sys.path.insert(0, "src")
        from research.statistical_significance_audit import _run_lodo
        from collections import defaultdict

        strat = defaultdict(dict)
        dates = [f"2026-10-{d:02d}" for d in range(9, 16)]
        # 6 dates with +0.03; one date with -1.0 (drives overall mean negative)
        for i, dt in enumerate(dates):
            ret = -1.0 if i == 0 else 0.03
            for j in range(10):
                key = (f"S{i*10+j:04d}", dt)
                strat["D_v3"][key] = ret
                strat["A_direct"][key] = 0.0

        import numpy as np
        date_means = [-1.0 if i == 0 else 0.03 for i in range(7)]
        full_gm = float(np.mean(date_means))
        results = _run_lodo(strat, "D_v3", "A_direct", full_grand_mean=full_gm)
        # Dropping date 2026-10-09 should flip positive
        drop_09 = next(r for r in results if r.dropped_date == "2026-10-09")
        assert drop_09.sign_change


class TestSA05_AuditReportIntegration:
    """SA05: Integration test using real DB."""

    def test_sa05_three_comparisons_all_downgraded(self):
        import sys
        sys.path.insert(0, "src")
        conn = sqlite3.connect("data/platform.db")
        from research.statistical_significance_audit import build_session41_significance_audit
        report = build_session41_significance_audit(conn)
        conn.close()
        assert report.s40_verdicts_downgraded == 3

    def test_sa05_effective_n_eq_7(self):
        import sys
        sys.path.insert(0, "src")
        conn = sqlite3.connect("data/platform.db")
        from research.statistical_significance_audit import build_session41_significance_audit
        report = build_session41_significance_audit(conn)
        conn.close()
        assert report.effective_n == 7

    def test_sa05_all_cis_include_zero(self):
        import sys
        sys.path.insert(0, "src")
        conn = sqlite3.connect("data/platform.db")
        from research.statistical_significance_audit import build_session41_significance_audit
        report = build_session41_significance_audit(conn)
        conn.close()
        assert all(c.ci_includes_zero for c in report.comparisons)

    def test_sa05_lodo_no_sign_changes(self):
        import sys
        sys.path.insert(0, "src")
        conn = sqlite3.connect("data/platform.db")
        from research.statistical_significance_audit import build_session41_significance_audit
        report = build_session41_significance_audit(conn)
        conn.close()
        # DIRECTIONALLY_STABLE: no sign changes in LODO
        assert all(not r.sign_change for r in report.lodo_results)

    def test_sa05_documentation_discrepancy_note_present(self):
        import sys
        sys.path.insert(0, "src")
        conn = sqlite3.connect("data/platform.db")
        from research.statistical_significance_audit import build_session41_significance_audit
        report = build_session41_significance_audit(conn)
        conn.close()
        assert "2026-10-12" in report.documentation_discrepancy_note

    def test_sa05_micro_cluster_dates_identified(self):
        import sys
        sys.path.insert(0, "src")
        conn = sqlite3.connect("data/platform.db")
        from research.statistical_significance_audit import build_session41_significance_audit
        report = build_session41_significance_audit(conn)
        conn.close()
        # Oct 10 and Oct 11 have n=4 each
        c = report.comparisons[0]  # D_v3 vs A_direct
        assert len(c.micro_cluster_dates) >= 1


# ---------------------------------------------------------------------------
# RP: Session 40 Reproduction
# ---------------------------------------------------------------------------

class TestRP01_AllMetricsReproduced:
    """RP01: All 10 S40 metrics reproduced within tolerance."""

    def test_rp01_overall_status_all_reproduced(self):
        import sys
        sys.path.insert(0, "src")
        conn = sqlite3.connect("data/platform.db")
        from research.session40_reproduction import build_session40_reproduction_report
        rpt = build_session40_reproduction_report(conn)
        conn.close()
        assert rpt.overall_status == "ALL_REPRODUCED"

    def test_rp01_no_failures(self):
        import sys
        sys.path.insert(0, "src")
        conn = sqlite3.connect("data/platform.db")
        from research.session40_reproduction import build_session40_reproduction_report
        rpt = build_session40_reproduction_report(conn)
        conn.close()
        assert rpt.n_failed == 0

    def test_rp01_d_v3_delta_vs_a_direct_reproduced(self):
        import sys
        sys.path.insert(0, "src")
        conn = sqlite3.connect("data/platform.db")
        from research.session40_reproduction import build_session40_reproduction_report, ReproductionStatus
        rpt = build_session40_reproduction_report(conn)
        conn.close()
        entry = next(e for e in rpt.entries if e.metric_name == "D_v3_vs_A_direct_delta")
        assert entry.status == ReproductionStatus.REPRODUCED
        assert abs(entry.actual_value - 0.036565) < 0.0001

    def test_rp01_signal_date_discrepancy_documented(self):
        import sys
        sys.path.insert(0, "src")
        conn = sqlite3.connect("data/platform.db")
        from research.session40_reproduction import build_session40_reproduction_report
        rpt = build_session40_reproduction_report(conn)
        conn.close()
        assert "2026-10-09" in rpt.signal_date_discrepancy

    def test_rp01_all_strategy_means_reproduced(self):
        import sys
        sys.path.insert(0, "src")
        conn = sqlite3.connect("data/platform.db")
        from research.session40_reproduction import build_session40_reproduction_report, ReproductionStatus
        rpt = build_session40_reproduction_report(conn)
        conn.close()
        mean_entries = [e for e in rpt.entries if e.metric_name.endswith("_mean_net")]
        assert all(e.status == ReproductionStatus.REPRODUCED for e in mean_entries)


class TestRP02_ReproductionStatus:
    """RP02: ReproductionStatus enum values."""

    def test_rp02_status_enum_values(self):
        import sys
        sys.path.insert(0, "src")
        from research.session40_reproduction import ReproductionStatus
        assert ReproductionStatus.REPRODUCED.value == "REPRODUCED"
        assert ReproductionStatus.NOT_REPRODUCED.value == "NOT_REPRODUCED"
        assert ReproductionStatus.SOURCE_UNAVAILABLE.value == "SOURCE_UNAVAILABLE"

    def test_rp02_n_entries_eq_10(self):
        import sys
        sys.path.insert(0, "src")
        conn = sqlite3.connect("data/platform.db")
        from research.session40_reproduction import build_session40_reproduction_report
        rpt = build_session40_reproduction_report(conn)
        conn.close()
        assert rpt.n_entries == 10


# ---------------------------------------------------------------------------
# AC: Avoid Chasing Analysis
# ---------------------------------------------------------------------------

class TestAC01_SubgroupDecisions:
    """AC01: Subgroup analysis covers expected V3 decisions."""

    def test_ac01_avoid_chasing_present(self):
        import sys
        sys.path.insert(0, "src")
        conn = sqlite3.connect("data/platform.db")
        from research.avoid_chasing_analysis import build_avoid_chasing_report
        rpt = build_avoid_chasing_report(conn)
        conn.close()
        decisions = [sg.v3_decision for sg in rpt.subgroups]
        assert "AVOID_CHASING" in decisions

    def test_ac01_no_entry_present(self):
        import sys
        sys.path.insert(0, "src")
        conn = sqlite3.connect("data/platform.db")
        from research.avoid_chasing_analysis import build_avoid_chasing_report
        rpt = build_avoid_chasing_report(conn)
        conn.close()
        decisions = [sg.v3_decision for sg in rpt.subgroups]
        assert "NO_ENTRY" in decisions

    def test_ac01_direct_entry_present(self):
        import sys
        sys.path.insert(0, "src")
        conn = sqlite3.connect("data/platform.db")
        from research.avoid_chasing_analysis import build_avoid_chasing_report
        rpt = build_avoid_chasing_report(conn)
        conn.close()
        decisions = [sg.v3_decision for sg in rpt.subgroups]
        assert "DIRECT_ENTRY" in decisions

    def test_ac01_avoid_chasing_a_direct_negative(self):
        import sys
        sys.path.insert(0, "src")
        conn = sqlite3.connect("data/platform.db")
        from research.avoid_chasing_analysis import build_avoid_chasing_report
        rpt = build_avoid_chasing_report(conn)
        conn.close()
        sg = next(s for s in rpt.subgroups if s.v3_decision == "AVOID_CHASING")
        # AVOID_CHASING stocks declined in A_direct
        assert sg.mean_a_direct_return < 0

    def test_ac01_avoid_chasing_v3_zero_return(self):
        import sys
        sys.path.insert(0, "src")
        conn = sqlite3.connect("data/platform.db")
        from research.avoid_chasing_analysis import build_avoid_chasing_report
        rpt = build_avoid_chasing_report(conn)
        conn.close()
        sg = next(s for s in rpt.subgroups if s.v3_decision == "AVOID_CHASING")
        # V3 avoids → 0% return
        assert sg.mean_v3_return == pytest.approx(0.0, abs=1e-6)

    def test_ac01_direct_entry_vs_adirect_negative(self):
        import sys
        sys.path.insert(0, "src")
        conn = sqlite3.connect("data/platform.db")
        from research.avoid_chasing_analysis import build_avoid_chasing_report
        rpt = build_avoid_chasing_report(conn)
        conn.close()
        sg = next(s for s in rpt.subgroups if s.v3_decision == "DIRECT_ENTRY")
        # S40 doc claimed +2.86% vs A_direct, but actual paired = -0.56%
        # Verify the correction is present
        assert sg.s40_doc_note != ""

    def test_ac01_causal_verdict_not_causal(self):
        import sys
        sys.path.insert(0, "src")
        conn = sqlite3.connect("data/platform.db")
        from research.avoid_chasing_analysis import build_avoid_chasing_report, CausalVerdict
        rpt = build_avoid_chasing_report(conn)
        conn.close()
        assert rpt.causal_verdict == CausalVerdict.DESCRIPTIVE_ASSOCIATION_ONLY

    def test_ac01_total_avoided_54(self):
        import sys
        sys.path.insert(0, "src")
        conn = sqlite3.connect("data/platform.db")
        from research.avoid_chasing_analysis import build_avoid_chasing_report
        rpt = build_avoid_chasing_report(conn)
        conn.close()
        assert rpt.total_avoided == 54

    def test_ac01_confounding_factors_non_empty(self):
        import sys
        sys.path.insert(0, "src")
        conn = sqlite3.connect("data/platform.db")
        from research.avoid_chasing_analysis import build_avoid_chasing_report
        rpt = build_avoid_chasing_report(conn)
        conn.close()
        assert len(rpt.confounding_factors) >= 3


# ---------------------------------------------------------------------------
# RB: Robustness & Sensitivity
# ---------------------------------------------------------------------------

class TestRB01_LodoStability:
    """RB01: LODO analysis shows directional stability."""

    def test_rb01_verdict_directionally_stable(self):
        import sys
        sys.path.insert(0, "src")
        conn = sqlite3.connect("data/platform.db")
        from research.robustness_sensitivity import build_robustness_report, RobustnessVerdict
        rpt = build_robustness_report(conn)
        conn.close()
        assert rpt.overall_verdict == RobustnessVerdict.DIRECTIONALLY_STABLE

    def test_rb01_no_sign_changes(self):
        import sys
        sys.path.insert(0, "src")
        conn = sqlite3.connect("data/platform.db")
        from research.robustness_sensitivity import build_robustness_report
        rpt = build_robustness_report(conn)
        conn.close()
        assert rpt.n_sign_changes == 0

    def test_rb01_seven_lodo_entries(self):
        import sys
        sys.path.insert(0, "src")
        conn = sqlite3.connect("data/platform.db")
        from research.robustness_sensitivity import build_robustness_report
        rpt = build_robustness_report(conn)
        conn.close()
        assert len(rpt.lodo_entries) == 7

    def test_rb01_all_lodo_cis_include_zero(self):
        import sys
        sys.path.insert(0, "src")
        conn = sqlite3.connect("data/platform.db")
        from research.robustness_sensitivity import build_robustness_report
        rpt = build_robustness_report(conn)
        conn.close()
        assert all(e.ci_includes_zero for e in rpt.lodo_entries)

    def test_rb01_lodo_grand_means_all_positive(self):
        import sys
        sys.path.insert(0, "src")
        conn = sqlite3.connect("data/platform.db")
        from research.robustness_sensitivity import build_robustness_report
        rpt = build_robustness_report(conn)
        conn.close()
        assert all(e.grand_mean_pct > 0 for e in rpt.lodo_entries)


class TestRB02_TxCostSensitivity:
    """RB02: Transaction cost sensitivity check."""

    def test_rb02_tx_sensitivity_exists(self):
        import sys
        sys.path.insert(0, "src")
        conn = sqlite3.connect("data/platform.db")
        from research.robustness_sensitivity import build_robustness_report
        rpt = build_robustness_report(conn)
        conn.close()
        assert rpt.tx_cost_sensitivity is not None

    def test_rb02_base_fees_585bps(self):
        import sys
        sys.path.insert(0, "src")
        conn = sqlite3.connect("data/platform.db")
        from research.robustness_sensitivity import build_robustness_report
        rpt = build_robustness_report(conn)
        conn.close()
        assert rpt.tx_cost_sensitivity.fees_base == pytest.approx(0.00585, abs=1e-5)

    def test_rb02_verdict_enum_values(self):
        import sys
        sys.path.insert(0, "src")
        from research.robustness_sensitivity import RobustnessVerdict
        assert "DIRECTIONALLY_STABLE" in [v.value for v in RobustnessVerdict]
        assert "RESULT_UNSTABLE" in [v.value for v in RobustnessVerdict]


# ---------------------------------------------------------------------------
# OR: Outcome Readiness
# ---------------------------------------------------------------------------

class TestOR01_TwentyDReadiness:
    """OR01: 20D outcome readiness correctly flags NOT_YET_MATURE."""

    def test_or01_verdict_no_signals_mature(self):
        import sys
        sys.path.insert(0, "src")
        conn = sqlite3.connect("data/platform.db")
        from research.outcome_readiness import build_20d_outcome_readiness_report
        rpt = build_20d_outcome_readiness_report(conn)
        conn.close()
        # As of Nov 09, not all Oct 2026 signals are 20D mature
        assert rpt.overall_verdict in ("NO_SIGNALS_MATURE", "PARTIAL_MATURITY")

    def test_or01_344_signals_checked(self):
        import sys
        sys.path.insert(0, "src")
        conn = sqlite3.connect("data/platform.db")
        from research.outcome_readiness import build_20d_outcome_readiness_report
        rpt = build_20d_outcome_readiness_report(conn)
        conn.close()
        assert rpt.n_signals_checked == 344

    def test_or01_horizon_days_eq_20(self):
        import sys
        sys.path.insert(0, "src")
        conn = sqlite3.connect("data/platform.db")
        from research.outcome_readiness import build_20d_outcome_readiness_report
        rpt = build_20d_outcome_readiness_report(conn)
        conn.close()
        assert rpt.horizon_days_needed == 20

    def test_or01_maturity_dates_set(self):
        import sys
        sys.path.insert(0, "src")
        conn = sqlite3.connect("data/platform.db")
        from research.outcome_readiness import build_20d_outcome_readiness_report
        rpt = build_20d_outcome_readiness_report(conn)
        conn.close()
        assert rpt.earliest_maturity_date < rpt.latest_maturity_date

    def test_or01_note_contains_caution(self):
        import sys
        sys.path.insert(0, "src")
        conn = sqlite3.connect("data/platform.db")
        from research.outcome_readiness import build_20d_outcome_readiness_report
        rpt = build_20d_outcome_readiness_report(conn)
        conn.close()
        assert "DO NOT" in rpt.note or "read-only" in rpt.note

    def test_or01_maturity_enum_values(self):
        import sys
        sys.path.insert(0, "src")
        from research.outcome_readiness import OutcomeMaturity
        assert OutcomeMaturity.MATURED.value == "MATURED"
        assert OutcomeMaturity.NOT_YET_MATURE.value == "NOT_YET_MATURE"


# ---------------------------------------------------------------------------
# ES: Evidence Strength Report
# ---------------------------------------------------------------------------

class TestES01_EvidenceStrength:
    """ES01: Evidence strength report contains expected verdicts."""

    def test_es01_ranking_conditional(self):
        import sys
        sys.path.insert(0, "src")
        conn = sqlite3.connect("data/platform.db")
        from research.evidence_strength_report import build_evidence_strength_report, RankingVerdict
        rpt = build_evidence_strength_report(conn)
        conn.close()
        assert rpt.ranking_verdict == RankingVerdict.RANKING_CONDITIONAL

    def test_es01_activation_blocked(self):
        import sys
        sys.path.insert(0, "src")
        conn = sqlite3.connect("data/platform.db")
        from research.evidence_strength_report import build_evidence_strength_report
        rpt = build_evidence_strength_report(conn)
        conn.close()
        assert "ACTIVATION_BLOCKED" in rpt.activation_verdict

    def test_es01_statistical_confidence_unverified(self):
        import sys
        sys.path.insert(0, "src")
        conn = sqlite3.connect("data/platform.db")
        from research.evidence_strength_report import build_evidence_strength_report
        rpt = build_evidence_strength_report(conn)
        conn.close()
        assert "UNVERIFIED" in rpt.statistical_confidence

    def test_es01_market_avoidance_driven(self):
        import sys
        sys.path.insert(0, "src")
        conn = sqlite3.connect("data/platform.db")
        from research.evidence_strength_report import build_evidence_strength_report
        rpt = build_evidence_strength_report(conn)
        conn.close()
        assert "MARKET_AVOIDANCE_DRIVEN" in rpt.attribution_identifiability

    def test_es01_multiple_dimensions(self):
        import sys
        sys.path.insert(0, "src")
        conn = sqlite3.connect("data/platform.db")
        from research.evidence_strength_report import build_evidence_strength_report
        rpt = build_evidence_strength_report(conn)
        conn.close()
        assert len(rpt.dimensions) >= 5

    def test_es01_evidence_level_enum(self):
        import sys
        sys.path.insert(0, "src")
        from research.evidence_strength_report import EvidenceLevel
        assert EvidenceLevel.STRONG.value == "STRONG"
        assert EvidenceLevel.ABSENT.value == "ABSENT"

    def test_es01_in_sample_evidence_weak(self):
        import sys
        sys.path.insert(0, "src")
        conn = sqlite3.connect("data/platform.db")
        from research.evidence_strength_report import build_evidence_strength_report, EvidenceLevel
        rpt = build_evidence_strength_report(conn)
        conn.close()
        in_sample = next((d for d in rpt.dimensions if d.dimension == "in_sample_5d"), None)
        assert in_sample is not None
        assert in_sample.evidence_level == EvidenceLevel.WEAK

    def test_es01_no_ranking_supported(self):
        import sys
        sys.path.insert(0, "src")
        conn = sqlite3.connect("data/platform.db")
        from research.evidence_strength_report import build_evidence_strength_report, RankingVerdict
        rpt = build_evidence_strength_report(conn)
        conn.close()
        assert rpt.ranking_verdict != RankingVerdict.RANKING_SUPPORTED
