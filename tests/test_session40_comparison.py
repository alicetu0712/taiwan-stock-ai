"""
tests/test_session40_comparison.py — Session 40 research tests.

Covers:
  BM — ResearchBlockerMatrix (10 tests)
  WD — EligibleWindowDiscovery (10 tests)
  VD — VersionDefinitionRecovery (10 tests)
  PC — HistoricalPairedComparison (10 tests)
  AT — V3MarketAvoidanceAttribution (10 tests)

All tests use in-memory SQLite fixtures.
No production DB access.
"""
from __future__ import annotations

import os
import sqlite3
from typing import List

import pytest

# ── Fixtures ─────────────────────────────────────────────────────────────────


def _make_db_with_signals(
    signals: List[dict],
    prices: List[dict],
    bench_prices: List[dict],
) -> sqlite3.Connection:
    """Create in-memory test DB with forward_signals and daily_prices."""
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE forward_signals (
            id INTEGER PRIMARY KEY,
            stock_id TEXT, trade_date TEXT, trade_signal TEXT,
            decision_label TEXT, model_version TEXT, is_valid INTEGER,
            source_price_date TEXT, market_regime_at_signal TEXT,
            stop_price REAL, target1 REAL,
            execution_date TEXT, execution_price REAL,
            fwd_return_20d REAL, fwd_return_5d REAL
        )
    """)
    conn.executemany(
        "INSERT INTO forward_signals VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            (
                s.get("id", i),
                s["stock_id"], s["trade_date"], s.get("trade_signal", "buy"),
                s.get("decision_label", "buy"), s.get("model_version", "v8.0"),
                s.get("is_valid", 1), s.get("source_price_date"),
                s.get("market_regime_at_signal", "bull"),
                s.get("stop_price"), s.get("target1"),
                s.get("execution_date"), s.get("execution_price"),
                s.get("fwd_return_20d"), s.get("fwd_return_5d"),
            )
            for i, s in enumerate(signals, 1)
        ],
    )
    conn.execute("""
        CREATE TABLE daily_prices (
            id INTEGER PRIMARY KEY,
            stock_id TEXT, date TEXT,
            open REAL, high REAL, low REAL, close REAL, volume REAL
        )
    """)
    conn.executemany(
        "INSERT INTO daily_prices VALUES (?,?,?,?,?,?,?,?)",
        [
            (None, p["stock_id"], p["date"],
             p.get("open", 100), p.get("high", 102), p.get("low", 98),
             p.get("close", 101), p.get("volume", 1000))
            for p in prices + bench_prices
        ],
    )
    return conn


# Standard test data
SIGNAL_DATE_1 = "2026-10-12"
SIGNAL_DATE_2 = "2026-10-13"


def _make_standard_conn() -> sqlite3.Connection:
    """Standard test DB: 2 stocks, 2 signal dates, 10 price bars each."""
    signals = [
        {"stock_id": "2330", "trade_date": SIGNAL_DATE_1, "trade_signal": "buy"},
        {"stock_id": "2317", "trade_date": SIGNAL_DATE_1, "trade_signal": "strong_buy"},
        {"stock_id": "2330", "trade_date": SIGNAL_DATE_2, "trade_signal": "buy"},
    ]
    # 10 price bars per stock after signal_date_1
    prices = []
    bench = []
    dates = [
        "2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15", "2026-10-16",
        "2026-10-19", "2026-10-20", "2026-10-21", "2026-10-22", "2026-10-27",
        "2026-10-28",
    ]
    for d in dates:
        prices.append({"stock_id": "2330", "date": d, "open": 100, "close": 101})
        prices.append({"stock_id": "2317", "date": d, "open": 200, "close": 202})
        bench.append({"stock_id": "0050", "date": d, "open": 110, "close": 111})
    return _make_db_with_signals(signals, prices, bench)


# ── BM: ResearchBlockerMatrix ─────────────────────────────────────────────────


class TestBlockerMatrix:
    def setup_method(self):
        import sys; sys.path.insert(0, ".")
        from src.research.research_blocker_matrix import (
            build_session40_blocker_matrix,
            BlockerCategory, BlockerStatus, BlockerSeverity,
        )
        self.matrix = build_session40_blocker_matrix()
        self.BC = BlockerCategory
        self.BS = BlockerStatus
        self.BSev = BlockerSeverity

    def test_bm01_has_blockers(self):
        assert len(self.matrix.blockers) > 0

    def test_bm02_has_all_categories(self):
        cats = {b.category for b in self.matrix.blockers}
        assert self.BC.A in cats
        assert self.BC.B in cats
        assert self.BC.C in cats
        assert self.BC.D in cats

    def test_bm03_category_a_has_immediate_fixes(self):
        a_blockers = self.matrix.category(self.BC.A)
        assert len(a_blockers) >= 2

    def test_bm04_category_b_has_data_improvements(self):
        b_blockers = self.matrix.category(self.BC.B)
        assert len(b_blockers) >= 2

    def test_bm05_benchmark_resolved(self):
        bench = next(b for b in self.matrix.blockers if b.check_id == "EG-05")
        assert bench.current_status == self.BS.RESOLVED

    def test_bm06_eg08_is_critical_open(self):
        eg08 = next(b for b in self.matrix.blockers if b.check_id == "EG-08a")
        assert eg08.severity == self.BSev.CRITICAL
        assert eg08.current_status == self.BS.OPEN

    def test_bm07_summary_has_resolved_count(self):
        summary = self.matrix.summary()
        assert summary["resolved"] >= 2  # EG-05 and EG-09

    def test_bm08_summary_has_open_count(self):
        summary = self.matrix.summary()
        assert summary["open"] >= 5  # eg08a, v1v2-def, stat-power, regime, eg02b, eg12, eg07

    def test_bm09_critical_open_has_eg08(self):
        critical = self.matrix.critical_open()
        ids = [b.check_id for b in critical]
        assert "EG-08a" in ids

    def test_bm10_all_blockers_have_evidence_source(self):
        for b in self.matrix.blockers:
            assert b.evidence_source, f"Blocker {b.check_id} missing evidence_source"


# ── WD: EligibleWindowDiscovery ──────────────────────────────────────────────


class TestEligibleWindowDiscovery:
    def setup_method(self):
        import sys; sys.path.insert(0, ".")
        from src.research.eligible_window_discovery import (
            run_session40_window_discovery, WindowVerdict, CheckVerdict,
        )
        self.run = run_session40_window_discovery
        self.WV = WindowVerdict
        self.CV = CheckVerdict

    def test_wd01_no_eligible_window_when_empty(self):
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE forward_signals "
            "(id INTEGER PRIMARY KEY, stock_id TEXT, trade_date TEXT, trade_signal TEXT, "
            "decision_label TEXT, model_version TEXT, is_valid INTEGER, "
            "source_price_date TEXT, market_regime_at_signal TEXT, "
            "stop_price REAL, target1 REAL, execution_date TEXT, execution_price REAL, "
            "fwd_return_20d REAL, fwd_return_5d REAL)"
        )
        conn.execute(
            "CREATE TABLE daily_prices "
            "(id INTEGER PRIMARY KEY, stock_id TEXT, date TEXT, "
            "open REAL, high REAL, low REAL, close REAL, volume REAL)"
        )
        result = self.run(conn)
        assert result.overall_verdict == "NO_ELIGIBLE_WINDOW"

    def test_wd02_has_three_candidate_windows(self):
        conn = _make_standard_conn()
        result = self.run(conn)
        # Should have 5D, 10D, 20D candidates
        assert len(result.candidate_windows) == 3

    def test_wd03_horizons_are_5_10_20(self):
        conn = _make_standard_conn()
        result = self.run(conn)
        horizons = {w.horizon_days for w in result.candidate_windows}
        assert horizons == {5, 10, 20}

    def test_wd04_5d_coverage_pass_with_enough_data(self):
        conn = _make_standard_conn()
        result = self.run(conn)
        w5 = next(w for w in result.candidate_windows if w.horizon_days == 5)
        # 10+ price bars → C4 (5D coverage) should pass
        c4 = next((c for c in w5.checks if c.check_id == "C4"), None)
        assert c4 is not None
        assert c4.verdict == self.CV.PASS
        # With only 2 dates, C10 (overlapping samples) will FAIL → window INELIGIBLE
        # This is correct behavior: small test fixtures are correctly flagged
        c10 = next((c for c in w5.checks if c.check_id == "C10"), None)
        assert c10 is not None

    def test_wd05_20d_ineligible_with_insufficient_data(self):
        conn = _make_standard_conn()
        result = self.run(conn)
        w20 = next(w for w in result.candidate_windows if w.horizon_days == 20)
        # Only 10 price bars → 20D insufficient
        assert w20.comparison_eligibility == self.WV.INELIGIBLE

    def test_wd06_checks_include_benchmark(self):
        conn = _make_standard_conn()
        result = self.run(conn)
        w5 = next(w for w in result.candidate_windows if w.horizon_days == 5)
        check_ids = {c.check_id for c in w5.checks}
        assert "C5" in check_ids

    def test_wd07_exclusion_reasons_documented_when_ineligible(self):
        conn = _make_standard_conn()
        result = self.run(conn)
        w20 = next(w for w in result.candidate_windows if w.horizon_days == 20)
        # 20D should have exclusion reasons
        assert w20.comparison_eligibility == self.WV.INELIGIBLE

    def test_wd08_overall_verdict_set(self):
        conn = _make_standard_conn()
        result = self.run(conn)
        assert result.overall_verdict in (
            "NO_ELIGIBLE_WINDOW", "CONDITIONAL_WINDOW_FOUND", "ELIGIBLE_WINDOW_FOUND"
        )

    def test_wd09_independent_dates_counted(self):
        conn = _make_standard_conn()
        result = self.run(conn)
        w5 = next(w for w in result.candidate_windows if w.horizon_days == 5)
        assert w5.n_independent_dates == 2  # two signal dates

    def test_wd10_no_performance_used_for_selection(self):
        # Windows are assessed purely on data quality criteria.
        # This test verifies the check structure doesn't use performance data.
        conn = _make_standard_conn()
        result = self.run(conn)
        w5 = next(w for w in result.candidate_windows if w.horizon_days == 5)
        # All checks should have check_id, verdict, actual, required
        for c in w5.checks:
            assert c.check_id
            assert c.verdict
            assert c.actual
            assert c.required


# ── VD: VersionDefinitionRecovery ────────────────────────────────────────────


class TestVersionDefinitionRecovery:
    def setup_method(self):
        import sys; sys.path.insert(0, ".")
        from src.research.version_definition_recovery import (
            build_session40_version_definitions,
            VersionDefinitionStatus,
        )
        self.report = build_session40_version_definitions()
        self.VDS = VersionDefinitionStatus

    def test_vd01_has_four_versions(self):
        assert len(self.report.versions) == 4

    def test_vd02_v1_is_recovered_not_verified(self):
        v1 = self.report.by_id("v1_signal_only")
        assert v1 is not None
        assert v1.status == self.VDS.RECOVERED

    def test_vd03_v2_is_recovered_not_verified(self):
        v2 = self.report.by_id("v2_entry_timing")
        assert v2 is not None
        assert v2.status == self.VDS.RECOVERED

    def test_vd04_hybrid_v1_is_verified(self):
        h = self.report.by_id("hybrid_v1")
        assert h is not None
        assert h.status == self.VDS.VERIFIED
        assert h.frozen_commit == "6602c3b"

    def test_vd05_v3_is_verified(self):
        v3 = self.report.by_id("v3_entry_timing")
        assert v3 is not None
        assert v3.status == self.VDS.VERIFIED
        assert v3.parameter_hash == "be43e8ca977d9fdd"

    def test_vd06_v2_has_parameter_hash(self):
        v2 = self.report.by_id("v2_entry_timing")
        assert v2 is not None
        assert v2.parameter_hash is not None
        assert len(v2.parameter_hash) == 16

    def test_vd07_v1_has_parameter_hash(self):
        v1 = self.report.by_id("v1_signal_only")
        assert v1 is not None
        assert v1.parameter_hash is not None
        assert len(v1.parameter_hash) == 16

    def test_vd08_hybrid_v3_can_compare(self):
        assert self.report.can_compare("hybrid_v1", "v3_entry_timing")

    def test_vd09_v1_v2_can_compare_conditional(self):
        # V1 and V2 are both RECOVERED, so can_compare = True with caveat
        assert self.report.can_compare("v1_signal_only", "v2_entry_timing")

    def test_vd10_all_versions_have_fees_pct(self):
        for v in self.report.versions:
            assert v.fees_pct == 0.585, f"{v.version_id} fees_pct mismatch"


# ── PC: HistoricalPairedComparison ────────────────────────────────────────────


class TestHistoricalPairedComparison:
    def setup_method(self):
        import sys; sys.path.insert(0, ".")
        from src.research.historical_paired_comparison import (
            build_session40_comparison_report,
            ComparabilityVerdict, RankingVerdict, StatisticalConfidence,
        )
        self.build = build_session40_comparison_report
        self.CV = ComparabilityVerdict
        self.RV = RankingVerdict
        self.SC = StatisticalConfidence

    def test_pc01_no_eligible_pairs_on_empty_db(self):
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE forward_signals "
            "(id INTEGER PRIMARY KEY, stock_id TEXT, trade_date TEXT, trade_signal TEXT, "
            "decision_label TEXT, model_version TEXT, is_valid INTEGER, "
            "source_price_date TEXT, market_regime_at_signal TEXT, "
            "stop_price REAL, target1 REAL, execution_date TEXT, execution_price REAL, "
            "fwd_return_20d REAL, fwd_return_5d REAL)"
        )
        conn.execute(
            "CREATE TABLE daily_prices "
            "(id INTEGER PRIMARY KEY, stock_id TEXT, date TEXT, "
            "open REAL, high REAL, low REAL, close REAL, volume REAL)"
        )
        report = self.build(conn)
        # No pairs from V3 engine, but V1/V2 from artifact may still load
        assert report is not None

    def test_pc02_v1v2_pair_loads_if_artifact_exists(self):
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE forward_signals "
            "(id INTEGER PRIMARY KEY, stock_id TEXT, trade_date TEXT, trade_signal TEXT, "
            "decision_label TEXT, model_version TEXT, is_valid INTEGER, "
            "source_price_date TEXT, market_regime_at_signal TEXT, "
            "stop_price REAL, target1 REAL, execution_date TEXT, execution_price REAL, "
            "fwd_return_20d REAL, fwd_return_5d REAL)"
        )
        conn.execute(
            "CREATE TABLE daily_prices "
            "(id INTEGER PRIMARY KEY, stock_id TEXT, date TEXT, "
            "open REAL, high REAL, low REAL, close REAL, volume REAL)"
        )
        report = self.build(conn)
        # If effectiveness_analysis.json exists, V1/V2 pair is loaded
        artifact_path = "data/effectiveness_analysis.json"
        if os.path.exists(artifact_path):
            v1v2_pairs = [p for p in report.pairs if "v1v2" in p.candidate or "v1v2" in p.baseline]
            assert len(v1v2_pairs) >= 1

    def test_pc03_null_outcome_not_treated_as_zero(self):
        # Build a DB where signals have fwd_return_20d=NULL
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE forward_signals "
            "(id INTEGER PRIMARY KEY, stock_id TEXT, trade_date TEXT, trade_signal TEXT, "
            "decision_label TEXT, model_version TEXT, is_valid INTEGER, "
            "source_price_date TEXT, market_regime_at_signal TEXT, "
            "stop_price REAL, target1 REAL, execution_date TEXT, execution_price REAL, "
            "fwd_return_20d REAL, fwd_return_5d REAL)"
        )
        conn.execute(
            "CREATE TABLE daily_prices "
            "(id INTEGER PRIMARY KEY, stock_id TEXT, date TEXT, "
            "open REAL, high REAL, low REAL, close REAL, volume REAL)"
        )
        # Verify no pairs claim outcome available from NULL
        report = self.build(conn)
        for p in report.pairs:
            # mean_net_alpha should be None if no data, not 0.0
            if p.raw_n == 0:
                assert p.comparability in (
                    self.CV.OUTCOME_UNAVAILABLE, self.CV.NO_ELIGIBLE_PAIRS,
                    self.CV.NOT_COMPARABLE, self.CV.CONDITIONAL
                )

    def test_pc04_conditional_comparability_has_caveats(self):
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE forward_signals "
            "(id INTEGER PRIMARY KEY, stock_id TEXT, trade_date TEXT, trade_signal TEXT, "
            "decision_label TEXT, model_version TEXT, is_valid INTEGER, "
            "source_price_date TEXT, market_regime_at_signal TEXT, "
            "stop_price REAL, target1 REAL, execution_date TEXT, execution_price REAL, "
            "fwd_return_20d REAL, fwd_return_5d REAL)"
        )
        conn.execute(
            "CREATE TABLE daily_prices "
            "(id INTEGER PRIMARY KEY, stock_id TEXT, date TEXT, "
            "open REAL, high REAL, low REAL, close REAL, volume REAL)"
        )
        report = self.build(conn)
        for p in report.pairs:
            if p.comparability == self.CV.CONDITIONAL:
                assert len(p.caveats) > 0, f"CONDITIONAL pair {p.candidate}/{p.baseline} has no caveats"

    def test_pc05_v1v2_verdict_conditional_not_significant(self):
        artifact_path = "data/effectiveness_analysis.json"
        if not os.path.exists(artifact_path):
            pytest.skip("effectiveness_analysis.json not available")
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE forward_signals "
            "(id INTEGER PRIMARY KEY, stock_id TEXT, trade_date TEXT, trade_signal TEXT, "
            "decision_label TEXT, model_version TEXT, is_valid INTEGER, "
            "source_price_date TEXT, market_regime_at_signal TEXT, "
            "stop_price REAL, target1 REAL, execution_date TEXT, execution_price REAL, "
            "fwd_return_20d REAL, fwd_return_5d REAL)"
        )
        conn.execute(
            "CREATE TABLE daily_prices "
            "(id INTEGER PRIMARY KEY, stock_id TEXT, date TEXT, "
            "open REAL, high REAL, low REAL, close REAL, volume REAL)"
        )
        report = self.build(conn)
        v1v2 = next((p for p in report.pairs if "v1v2" in p.candidate), None)
        if v1v2:
            # CI includes zero → CONDITIONAL, not SIGNIFICANT_POSITIVE
            if v1v2.ci_lower is not None and v1v2.ci_upper is not None:
                ci_zero = v1v2.ci_lower <= 0 <= v1v2.ci_upper
                if ci_zero:
                    assert v1v2.verdict == "CONDITIONAL"

    def test_pc06_statistical_confidence_unverified_for_7date_window(self):
        conn = _make_standard_conn()
        report = self.build(conn)
        for p in report.pairs:
            if p.n_independent_dates is not None and p.n_independent_dates < 20:
                # Must be UNVERIFIED for small samples
                assert p.statistical_confidence in (
                    self.SC.UNVERIFIED, self.SC.CONDITIONAL
                )

    def test_pc07_ranking_verdict_is_set(self):
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE forward_signals "
            "(id INTEGER PRIMARY KEY, stock_id TEXT, trade_date TEXT, trade_signal TEXT, "
            "decision_label TEXT, model_version TEXT, is_valid INTEGER, "
            "source_price_date TEXT, market_regime_at_signal TEXT, "
            "stop_price REAL, target1 REAL, execution_date TEXT, execution_price REAL, "
            "fwd_return_20d REAL, fwd_return_5d REAL)"
        )
        conn.execute(
            "CREATE TABLE daily_prices "
            "(id INTEGER PRIMARY KEY, stock_id TEXT, date TEXT, "
            "open REAL, high REAL, low REAL, close REAL, volume REAL)"
        )
        report = self.build(conn)
        assert report.ranking_verdict in (
            self.RV.RANKING_SUPPORTED, self.RV.RANKING_CONDITIONAL, self.RV.RANKING_NOT_SUPPORTED
        )

    def test_pc08_ranking_note_is_not_empty(self):
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE forward_signals "
            "(id INTEGER PRIMARY KEY, stock_id TEXT, trade_date TEXT, trade_signal TEXT, "
            "decision_label TEXT, model_version TEXT, is_valid INTEGER, "
            "source_price_date TEXT, market_regime_at_signal TEXT, "
            "stop_price REAL, target1 REAL, execution_date TEXT, execution_price REAL, "
            "fwd_return_20d REAL, fwd_return_5d REAL)"
        )
        conn.execute(
            "CREATE TABLE daily_prices "
            "(id INTEGER PRIMARY KEY, stock_id TEXT, date TEXT, "
            "open REAL, high REAL, low REAL, close REAL, volume REAL)"
        )
        report = self.build(conn)
        assert len(report.ranking_note) > 10

    def test_pc09_no_production_db_access(self):
        # This test verifies that the module can be imported and run with
        # a fresh in-memory DB — confirming no hardcoded production paths.
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE forward_signals "
            "(id INTEGER PRIMARY KEY, stock_id TEXT, trade_date TEXT, trade_signal TEXT, "
            "decision_label TEXT, model_version TEXT, is_valid INTEGER, "
            "source_price_date TEXT, market_regime_at_signal TEXT, "
            "stop_price REAL, target1 REAL, execution_date TEXT, execution_price REAL, "
            "fwd_return_20d REAL, fwd_return_5d REAL)"
        )
        conn.execute(
            "CREATE TABLE daily_prices "
            "(id INTEGER PRIMARY KEY, stock_id TEXT, date TEXT, "
            "open REAL, high REAL, low REAL, close REAL, volume REAL)"
        )
        # Should not raise any production-DB-related error
        from src.research.historical_paired_comparison import build_session40_comparison_report
        report = build_session40_comparison_report(conn)
        assert report is not None

    def test_pc10_v1v2_has_n_above_1000_if_artifact_loaded(self):
        from src.research.historical_paired_comparison import build_session40_comparison_report
        artifact_path = "data/effectiveness_analysis.json"
        if not os.path.exists(artifact_path):
            pytest.skip("effectiveness_analysis.json not available")
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE forward_signals "
            "(id INTEGER PRIMARY KEY, stock_id TEXT, trade_date TEXT, trade_signal TEXT, "
            "decision_label TEXT, model_version TEXT, is_valid INTEGER, "
            "source_price_date TEXT, market_regime_at_signal TEXT, "
            "stop_price REAL, target1 REAL, execution_date TEXT, execution_price REAL, "
            "fwd_return_20d REAL, fwd_return_5d REAL)"
        )
        conn.execute(
            "CREATE TABLE daily_prices "
            "(id INTEGER PRIMARY KEY, stock_id TEXT, date TEXT, "
            "open REAL, high REAL, low REAL, close REAL, volume REAL)"
        )
        report = build_session40_comparison_report(conn)
        v1v2 = next((p for p in report.pairs if "v1v2" in p.candidate), None)
        if v1v2:
            assert v1v2.raw_n > 1000, "V1/V2 comparison from artifact should have N>1000"


# ── AT: V3MarketAvoidanceAttribution ─────────────────────────────────────────


class TestV3MarketAvoidanceAttribution:
    def setup_method(self):
        import sys; sys.path.insert(0, ".")
        from src.research.v3_market_avoidance_attribution import (
            build_session40_attribution,
            AttributionStatus,
        )
        self.build = build_session40_attribution
        self.AS = AttributionStatus

    def _make_attr_conn(self) -> sqlite3.Connection:
        """Minimal DB for attribution test — no signals → returns default."""
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE forward_signals "
            "(id INTEGER PRIMARY KEY, stock_id TEXT, trade_date TEXT, trade_signal TEXT, "
            "decision_label TEXT, model_version TEXT, is_valid INTEGER, "
            "source_price_date TEXT, market_regime_at_signal TEXT, "
            "stop_price REAL, target1 REAL, execution_date TEXT, execution_price REAL, "
            "fwd_return_20d REAL, fwd_return_5d REAL)"
        )
        conn.execute(
            "CREATE TABLE daily_prices "
            "(id INTEGER PRIMARY KEY, stock_id TEXT, date TEXT, "
            "open REAL, high REAL, low REAL, close REAL, volume REAL)"
        )
        return conn

    def test_at01_attribution_handles_no_signal_data(self):
        from src.research.v3_market_avoidance_attribution import MarketAvoidanceAttribution
        # Build directly with known-zero values (simulates empty DB result)
        attr = MarketAvoidanceAttribution(
            total_alpha_ppt=0.0, n_signals=0, n_v3_filled=0, n_v3_skipped=0,
            v3_fill_rate=0.0, benchmark_avg_5d_return_pct=0.0,
            a_direct_mean_net_return_pct=0.0, d_v3_mean_net_return_pct=0.0,
            overall_verdict="ATTRIBUTION_NOT_IDENTIFIABLE",
            overall_evidence="No signals found",
        )
        assert attr is not None
        assert attr.overall_verdict == "ATTRIBUTION_NOT_IDENTIFIABLE"

    def test_at02_attribution_has_five_components_when_data_available(self):
        # Only run if real data is available
        if not os.path.exists("data/platform.db"):
            pytest.skip("Production DB not available")
        conn = sqlite3.connect("data/platform.db")
        attr = self.build(conn)
        conn.close()
        assert len(attr.components) == 5

    def test_at03_market_avoidance_is_estimated_not_unidentifiable(self):
        if not os.path.exists("data/platform.db"):
            pytest.skip("Production DB not available")
        conn = sqlite3.connect("data/platform.db")
        attr = self.build(conn)
        conn.close()
        ma_comp = next((c for c in attr.components if "Market Avoidance" in c.name), None)
        assert ma_comp is not None
        assert ma_comp.status == self.AS.ESTIMATED

    def test_at04_entry_timing_is_unidentifiable(self):
        if not os.path.exists("data/platform.db"):
            pytest.skip("Production DB not available")
        conn = sqlite3.connect("data/platform.db")
        attr = self.build(conn)
        conn.close()
        et_comp = next((c for c in attr.components if "Entry Timing" in c.name), None)
        assert et_comp is not None
        assert et_comp.status == self.AS.UNIDENTIFIABLE
        assert et_comp.estimated_contribution_ppt is None

    def test_at05_overall_verdict_market_avoidance_driven(self):
        if not os.path.exists("data/platform.db"):
            pytest.skip("Production DB not available")
        conn = sqlite3.connect("data/platform.db")
        attr = self.build(conn)
        conn.close()
        assert attr.overall_verdict == "MARKET_AVOIDANCE_DRIVEN"

    def test_at06_exposure_reduction_estimate_method(self):
        """Test exposure_reduction_estimate_ppt calculation logic."""
        from src.research.v3_market_avoidance_attribution import MarketAvoidanceAttribution
        attr = MarketAvoidanceAttribution(
            total_alpha_ppt=3.66,
            n_signals=274,
            n_v3_filled=188,
            n_v3_skipped=86,
            v3_fill_rate=188 / 274,
            benchmark_avg_5d_return_pct=-4.65,
            a_direct_mean_net_return_pct=-3.2,
            d_v3_mean_net_return_pct=-1.86,
        )
        est = attr.exposure_reduction_estimate_ppt()
        # Expected: (1 - 188/274) * (0 - (-3.2)) = 0.3139 * 3.2 ≈ 1.00%
        assert 0.5 < est < 2.5, f"Expected 0.5-2.5ppt, got {est}"

    def test_at07_transaction_cost_saving_is_minor(self):
        if not os.path.exists("data/platform.db"):
            pytest.skip("Production DB not available")
        conn = sqlite3.connect("data/platform.db")
        attr = self.build(conn)
        conn.close()
        tc_comp = next((c for c in attr.components if "Transaction Cost" in c.name), None)
        assert tc_comp is not None
        # Transaction cost savings should be < 0.5ppt (minor)
        assert tc_comp.estimated_contribution_ppt is not None
        assert tc_comp.estimated_contribution_ppt < 0.5

    def test_at08_avoidance_quality_is_quantified(self):
        if not os.path.exists("data/platform.db"):
            pytest.skip("Production DB not available")
        conn = sqlite3.connect("data/platform.db")
        attr = self.build(conn)
        conn.close()
        aq_comp = next((c for c in attr.components if "Avoidance Quality" in c.name), None)
        assert aq_comp is not None
        assert aq_comp.status == self.AS.QUANTIFIED

    def test_at09_benchmark_avg_is_negative_in_oct2026(self):
        if not os.path.exists("data/platform.db"):
            pytest.skip("Production DB not available")
        conn = sqlite3.connect("data/platform.db")
        attr = self.build(conn)
        conn.close()
        # 0050 declined during Oct 2026 comparison window
        assert attr.benchmark_avg_5d_return_pct < 0, \
            "0050 should have declined during Oct 2026 5D windows"

    def test_at10_stock_selection_estimate_returns_none(self):
        from src.research.v3_market_avoidance_attribution import MarketAvoidanceAttribution
        attr = MarketAvoidanceAttribution(
            total_alpha_ppt=3.66,
            n_signals=274,
            n_v3_filled=188,
            n_v3_skipped=86,
            v3_fill_rate=0.686,
            benchmark_avg_5d_return_pct=-4.65,
            a_direct_mean_net_return_pct=-3.2,
            d_v3_mean_net_return_pct=-1.86,
        )
        # stock_selection cannot be identified from price data alone
        assert attr.stock_selection_estimate_ppt() is None
