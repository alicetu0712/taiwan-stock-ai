"""
Session 42: Trading Calendar Integrity & Statistical Evidence Repair
50 tests covering PART B–H modules.

Prefix groups:
  TC — TradingCalendarIntegrityReport
  UA — ObservationUnitAuditReport
  BI — BenchmarkIntegrityReport
  C5 — CorrectedFiveDayComparison / _run_cluster_test
  GR — StatisticalGuardrailsReport
  VD — Verdict / cross-module assertions
"""
import sqlite3
import sys

import pytest


DB_PATH = "data/platform.db"


@pytest.fixture(scope="module")
def conn():
    with sqlite3.connect(DB_PATH) as c:
        yield c


# ---------------------------------------------------------------------------
# TC — Trading Calendar Integrity (12 tests)
# ---------------------------------------------------------------------------

class TestTradingCalendarIntegrity:
    @pytest.fixture(scope="class")
    def report(self, conn):
        sys.path.insert(0, "src")
        from research.trading_calendar_integrity import build_trading_calendar_integrity_report
        return build_trading_calendar_integrity_report(conn)

    def test_tc01_report_type(self, report):
        sys.path.insert(0, "src")
        from research.trading_calendar_integrity import TradingCalendarIntegrityReport
        assert isinstance(report, TradingCalendarIntegrityReport)

    def test_tc02_session_number(self, report):
        assert report.session == 42

    def test_tc03_calendar_source_is_daily_prices(self, report):
        assert "daily_prices" in report.calendar_source.lower()

    def test_tc04_oct09_non_trading(self, report):
        sys.path.insert(0, "src")
        from research.trading_calendar_integrity import MarketDateStatus
        entry = next((e for e in report.signal_date_entries if e.signal_date == "2026-10-09"), None)
        assert entry is not None
        assert entry.market_status == MarketDateStatus.NON_TRADING_DAY

    def test_tc05_oct10_non_trading(self, report):
        sys.path.insert(0, "src")
        from research.trading_calendar_integrity import MarketDateStatus
        entry = next((e for e in report.signal_date_entries if e.signal_date == "2026-10-10"), None)
        assert entry is not None
        assert entry.market_status == MarketDateStatus.NON_TRADING_DAY

    def test_tc06_oct11_non_trading(self, report):
        sys.path.insert(0, "src")
        from research.trading_calendar_integrity import MarketDateStatus
        entry = next((e for e in report.signal_date_entries if e.signal_date == "2026-10-11"), None)
        assert entry is not None
        assert entry.market_status == MarketDateStatus.NON_TRADING_DAY

    def test_tc07_oct12_trading(self, report):
        sys.path.insert(0, "src")
        from research.trading_calendar_integrity import MarketDateStatus
        entry = next((e for e in report.signal_date_entries if e.signal_date == "2026-10-12"), None)
        assert entry is not None
        assert entry.market_status == MarketDateStatus.TRADING_DAY

    def test_tc08_non_trading_pct_above_30(self, report):
        # Oct 09+10+11 = 107/274 = 39.1%
        assert report.pct_non_trading > 0.30

    def test_tc09_overall_verdict_failed(self, report):
        assert report.overall_verdict == "CALENDAR_FAILED"

    def test_tc10_fill_dates_map_non_trading_to_oct12(self, report):
        for nd in ("2026-10-09", "2026-10-10", "2026-10-11"):
            if nd in report.fill_date_mapping:
                assert report.fill_date_mapping[nd] == "2026-10-12"

    def test_tc11_affected_dates_contains_three(self, report):
        assert len(report.affected_dates) >= 3

    def test_tc12_signal_entries_have_buy_sb_counts(self, report):
        for e in report.signal_date_entries:
            assert e.n_buy_strong_buy >= 0


# ---------------------------------------------------------------------------
# UA — Observation Unit Audit (10 tests)
# ---------------------------------------------------------------------------

class TestObservationUnitAudit:
    @pytest.fixture(scope="class")
    def report(self, conn):
        sys.path.insert(0, "src")
        from research.observation_unit_auditor import build_observation_unit_audit_report
        return build_observation_unit_audit_report(conn)

    def test_ua01_report_type(self, report):
        sys.path.insert(0, "src")
        from research.observation_unit_auditor import ObservationUnitAuditReport
        assert isinstance(report, ObservationUnitAuditReport)

    def test_ua02_s41_had_7_clusters(self, report):
        assert report.n_clusters_signal_date == 7

    def test_ua03_s42_has_5_clusters(self, report):
        assert report.n_clusters_fill_date == 5

    def test_ua04_non_trading_signals_absorbed(self, report):
        assert report.n_signals_non_trading_absorbed > 0

    def test_ua05_cluster1_contains_non_trading(self, report):
        c1 = report.clusters[0]
        assert c1.contains_non_trading_day_signals is True

    def test_ua06_cluster1_has_multiple_signal_dates(self, report):
        c1 = report.clusters[0]
        # Oct 09, 10, 11, 12 all map to fill Oct 12
        assert len(c1.signal_dates) >= 3

    def test_ua07_overlapping_window_pairs(self, report):
        assert report.n_overlapping_cluster_pairs >= 3

    def test_ua08_verdict_corrected(self, report):
        assert report.observation_unit_verdict == "OBSERVATION_UNIT_CORRECTED"

    def test_ua09_effective_n_less_than_clusters(self, report):
        assert report.effective_independent_n < report.n_clusters_fill_date

    def test_ua10_cluster_fill_dates_are_trading_days(self, report, conn):
        td_set = set(
            r[0] for r in conn.execute(
                "SELECT DISTINCT date FROM daily_prices WHERE date BETWEEN '2026-10-01' AND '2026-11-30'"
            ).fetchall()
        )
        for c in report.clusters:
            assert c.fill_date in td_set, f"{c.fill_date} should be a trading day"


# ---------------------------------------------------------------------------
# BI — Benchmark Integrity (8 tests)
# ---------------------------------------------------------------------------

class TestBenchmarkIntegrity:
    @pytest.fixture(scope="class")
    def report(self, conn):
        sys.path.insert(0, "src")
        from research.benchmark_integrity_auditor import build_benchmark_integrity_report
        return build_benchmark_integrity_report(conn)

    def test_bi01_report_type(self, report):
        sys.path.insert(0, "src")
        from research.benchmark_integrity_auditor import BenchmarkIntegrityReport
        assert isinstance(report, BenchmarkIntegrityReport)

    def test_bi02_at_least_5_corrections(self, report):
        assert report.n_total_corrections >= 5

    def test_bi03_all_corrections_have_status(self, report):
        sys.path.insert(0, "src")
        from research.benchmark_integrity_auditor import LabelStatus
        for c in report.corrections:
            assert c.status in (LabelStatus.CORRECTED, LabelStatus.MISLABELED, LabelStatus.CORRECT)

    def test_bi04_cr_b02_direct_entry_sign_flip(self, report):
        cr = next((c for c in report.corrections if c.correction_id == "CR-B02"), None)
        assert cr is not None
        assert "-0.56" in cr.correct_value or "negative" in cr.impact.lower()

    def test_bi05_s40_benchmark_negative(self, report):
        assert report.s40_benchmark_reported < 0

    def test_bi06_s42_benchmark_closer_to_neg_2pct(self, report):
        # S42 corrected ~-2.16% (not -4.65%)
        assert -0.05 < report.s42_benchmark_corrected < 0.0

    def test_bi07_benchmark_dates_documented(self, report):
        assert "Oct" in report.benchmark_dates_s40_docs
        assert "Oct" in report.benchmark_dates_actual

    def test_bi08_cluster_correction_cr_b06_present(self, report):
        cr = next((c for c in report.corrections if c.correction_id == "CR-B06"), None)
        assert cr is not None
        assert "fill" in cr.correct_label.lower()


# ---------------------------------------------------------------------------
# C5 — Corrected 5D Comparison (14 tests)
# ---------------------------------------------------------------------------

class TestCorrected5DComparison:
    @pytest.fixture(scope="class")
    def report(self, conn):
        sys.path.insert(0, "src")
        from research.corrected_5d_comparison import build_corrected_5d_comparison
        return build_corrected_5d_comparison(conn)

    def test_c5_01_report_type(self, report):
        sys.path.insert(0, "src")
        from research.corrected_5d_comparison import CorrectedFiveDayComparison
        assert isinstance(report, CorrectedFiveDayComparison)

    def test_c5_02_session_42(self, report):
        assert report.session == 42

    def test_c5_03_a_direct_inconclusive(self, report):
        sys.path.insert(0, "src")
        from research.corrected_5d_comparison import CorrectedComparisonVerdict
        assert report.result_vs_a_direct.verdict == CorrectedComparisonVerdict.SIGNIFICANCE_INCONCLUSIVE

    def test_c5_04_b_v1v2_inconclusive(self, report):
        sys.path.insert(0, "src")
        from research.corrected_5d_comparison import CorrectedComparisonVerdict
        assert report.result_vs_b_v1v2.verdict == CorrectedComparisonVerdict.SIGNIFICANCE_INCONCLUSIVE

    def test_c5_05_c_hybrid_inconclusive(self, report):
        sys.path.insert(0, "src")
        from research.corrected_5d_comparison import CorrectedComparisonVerdict
        assert report.result_vs_c_hybrid.verdict == CorrectedComparisonVerdict.SIGNIFICANCE_INCONCLUSIVE

    def test_c5_06_all_cis_include_zero(self, report):
        for r in (report.result_vs_a_direct, report.result_vs_b_v1v2, report.result_vs_c_hybrid):
            assert r.ci_includes_zero, (
                f"{r.comparator}: CI [{r.ci_lower:.4f}, {r.ci_upper:.4f}] doesn't include 0"
            )

    def test_c5_07_a_direct_grand_mean_about_1pct(self, report):
        gm = report.result_vs_a_direct.grand_mean_delta
        assert 0.005 < gm < 0.03, f"Expected ~1.21%, got {gm:.4f}"

    def test_c5_08_b_v1v2_near_zero(self, report):
        gm = report.result_vs_b_v1v2.grand_mean_delta
        assert abs(gm) < 0.02, f"Expected ~0.32%, got {gm:.4f}"

    def test_c5_09_s40_reference_stored(self, report):
        assert abs(report.s40_signal_level_d_vs_a - 0.0366) < 0.001

    def test_c5_10_s41_reference_stored(self, report):
        assert abs(report.s41_cluster_d_vs_a - 0.0649) < 0.001

    def test_c5_11_s42_lower_than_s41(self, report):
        assert report.s42_corrected_d_vs_a < report.s41_cluster_d_vs_a

    def test_c5_12_5_fill_clusters(self, report):
        assert report.result_vs_a_direct.n_fill_clusters == 5

    def test_c5_13_overall_verdict_inconclusive(self, report):
        assert "INCONCLUSIVE" in report.overall_verdict

    def test_c5_14_cluster_test_known_values(self):
        sys.path.insert(0, "src")
        from research.corrected_5d_comparison import _run_cluster_test, CorrectedComparisonVerdict
        # Pre-computed cluster deltas from S42 Bash analysis
        deltas = [0.0262, 0.0120, 0.0276, -0.0152, 0.0099]
        grand, ci_lo, ci_hi, t_stat, p_val, incl_zero, verdict = _run_cluster_test(deltas)
        assert abs(grand - 0.01210) < 0.0005, f"grand mean {grand:.5f} != ~0.01210"
        assert incl_zero is True
        assert verdict == CorrectedComparisonVerdict.SIGNIFICANCE_INCONCLUSIVE
        assert p_val > 0.10


# ---------------------------------------------------------------------------
# GR — Statistical Guardrails (10 tests)
# ---------------------------------------------------------------------------

class TestStatisticalGuardrails:
    @pytest.fixture(scope="class")
    def report(self, conn):
        sys.path.insert(0, "src")
        from research.statistical_guardrails import build_statistical_guardrails_report
        return build_statistical_guardrails_report(conn)

    def test_gr01_report_type(self, report):
        sys.path.insert(0, "src")
        from research.statistical_guardrails import StatisticalGuardrailsReport
        assert isinstance(report, StatisticalGuardrailsReport)

    def test_gr02_exactly_10_guardrails(self, report):
        assert len(report.guardrails) == 10

    def test_gr03_g01_calendar_fails(self, report):
        sys.path.insert(0, "src")
        from research.statistical_guardrails import GuardrailStatus
        g01 = next(g for g in report.guardrails if g.guardrail_id == "G01")
        assert g01.status == GuardrailStatus.FAIL

    def test_gr04_g02_label_passes(self, report):
        sys.path.insert(0, "src")
        from research.statistical_guardrails import GuardrailStatus
        g02 = next(g for g in report.guardrails if g.guardrail_id == "G02")
        assert g02.status == GuardrailStatus.PASS

    def test_gr05_g03_cluster_count_fails(self, report):
        sys.path.insert(0, "src")
        from research.statistical_guardrails import GuardrailStatus
        g03 = next(g for g in report.guardrails if g.guardrail_id == "G03")
        assert g03.status == GuardrailStatus.FAIL

    def test_gr06_g04_window_overlap_fails(self, report):
        sys.path.insert(0, "src")
        from research.statistical_guardrails import GuardrailStatus
        g04 = next(g for g in report.guardrails if g.guardrail_id == "G04")
        assert g04.status == GuardrailStatus.FAIL

    def test_gr07_g05_signal_independence_passes(self, report):
        sys.path.insert(0, "src")
        from research.statistical_guardrails import GuardrailStatus
        g05 = next(g for g in report.guardrails if g.guardrail_id == "G05")
        assert g05.status == GuardrailStatus.PASS

    def test_gr08_g09_no_lookahead_passes(self, report):
        sys.path.insert(0, "src")
        from research.statistical_guardrails import GuardrailStatus
        g09 = next(g for g in report.guardrails if g.guardrail_id == "G09")
        assert g09.status == GuardrailStatus.PASS

    def test_gr09_overall_conditional_or_fail(self, report):
        sys.path.insert(0, "src")
        from research.statistical_guardrails import GuardrailStatus
        assert report.overall_status in (GuardrailStatus.CONDITIONAL, GuardrailStatus.FAIL)

    def test_gr10_n_fail_at_least_2(self, report):
        assert report.n_fail >= 2


# ---------------------------------------------------------------------------
# VD — Verdict / Cross-module (8 tests)
# ---------------------------------------------------------------------------

class TestCrossModuleVerdicts:
    @pytest.fixture(scope="class")
    def reports(self, conn):
        sys.path.insert(0, "src")
        from research.trading_calendar_integrity import build_trading_calendar_integrity_report
        from research.observation_unit_auditor import build_observation_unit_audit_report
        from research.benchmark_integrity_auditor import build_benchmark_integrity_report
        from research.corrected_5d_comparison import build_corrected_5d_comparison
        from research.statistical_guardrails import build_statistical_guardrails_report
        return {
            "tc": build_trading_calendar_integrity_report(conn),
            "ua": build_observation_unit_audit_report(conn),
            "bi": build_benchmark_integrity_report(conn),
            "c5": build_corrected_5d_comparison(conn),
            "gr": build_statistical_guardrails_report(conn),
        }

    def test_vd01_non_trading_pct_consistent_with_g01(self, reports):
        tc, gr = reports["tc"], reports["gr"]
        g01 = next(g for g in gr.guardrails if g.guardrail_id == "G01")
        assert tc.pct_non_trading > 0.30
        assert "107" in g01.finding or "39" in g01.finding

    def test_vd02_cluster_count_consistent(self, reports):
        ua, c5 = reports["ua"], reports["c5"]
        assert ua.n_clusters_fill_date == c5.result_vs_a_direct.n_fill_clusters

    def test_vd03_s40_reference_values_correct(self, reports):
        c5 = reports["c5"]
        assert abs(c5.s40_signal_level_d_vs_a - 0.0366) < 0.002
        assert abs(c5.s41_cluster_d_vs_a - 0.0649) < 0.002

    def test_vd04_grand_mean_regression_s41_to_s42(self, reports):
        c5 = reports["c5"]
        assert c5.s42_corrected_d_vs_a < c5.s41_cluster_d_vs_a

    def test_vd05_b_v1v2_weakest_evidence(self, reports):
        c5 = reports["c5"]
        # D vs B_v1v2 has weaker evidence (lower grand mean or higher p)
        assert (
            c5.result_vs_b_v1v2.p_value > c5.result_vs_a_direct.p_value
            or abs(c5.result_vs_b_v1v2.grand_mean_delta) < abs(c5.result_vs_a_direct.grand_mean_delta)
        )

    def test_vd06_benchmark_corrected_less_negative(self, reports):
        bi = reports["bi"]
        # S42 corrected -2.16% is less negative than S40 -4.65%
        assert bi.s42_benchmark_corrected > bi.s40_benchmark_reported

    def test_vd07_all_significance_inconclusive(self, reports):
        sys.path.insert(0, "src")
        from research.corrected_5d_comparison import CorrectedComparisonVerdict
        c5 = reports["c5"]
        all_verdicts = [
            c5.result_vs_a_direct.verdict,
            c5.result_vs_b_v1v2.verdict,
            c5.result_vs_c_hybrid.verdict,
        ]
        assert all(v == CorrectedComparisonVerdict.SIGNIFICANCE_INCONCLUSIVE for v in all_verdicts)

    def test_vd08_guardrails_overall_verdict_string(self, reports):
        gr = reports["gr"]
        assert "GUARDRAILS" in gr.overall_verdict
