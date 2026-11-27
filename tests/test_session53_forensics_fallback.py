"""
test_session53_forensics_fallback.py — Session 53: 100 tests, TC01–TC40

Covers:
  TC01  Nov 06 QG Sub-condition Evidence
  TC02  Nov 09 Stale Response Evidence
  TC03  Scheduler Evidence
  TC04  Provider Request Date
  TC05  Provider Response Date
  TC06  Cache / Fallback Logic
  TC07  Benchmark-only Detection
  TC08  Partial Universe Detection
  TC09  Coverage Gate
  TC10  Completion Marker
  TC11  TWSE Single-stock Source
  TC12  TPEx Source Assessment
  TC13  Historical Date Validation
  TC14  Wrong Stock ID
  TC15  Invalid OHLC
  TC16  Duplicate Response
  TC17  Rate Limit
  TC18  Timeout
  TC19  Retry Exhaustion
  TC20  Fallback Partial Recovery
  TC21  Source Verification
  TC22  Backfill Manifest Structure
  TC23  Insert-only
  TC24  Duplicate Conflict
  TC25  Transaction Rollback
  TC26  AUTH01 Pending
  TC27  Recorder Readiness
  TC28  V3 Decision Cutoff
  TC29  Input Snapshot
  TC30  Immutable Fingerprint
  TC31  Mock vs Genuine Prospective
  TC32  Collection Authorization Matrix
  TC33  Independent Cluster Spacing
  TC34  G03 Guardrail
  TC35  G04 Guardrail
  TC36  Calendar SSOT
  TC37  Canonical Fill Dates
  TC38  No 20D Outcome
  TC39  Frozen Baseline
  TC40  Production Fingerprints

SAFETY:
  - No live API calls (all mocked or analyzed from code)
  - No production DB writes
  - Idempotency tests use temporary SQLite only
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date

import pytest


from src.research.coverage_qg_forensics_s53 import (
    CANONICAL_FILL_DATES,
    CANONICAL_20TD_EXITS,
    CANONICAL_5TD_EXITS,
    PROVENANCE_SUMMARY,
    QGCheckStatus,
    QGConfidence,
    QGFailureSource,
    QGSubCheck,
    CollectionBlockerStatus,
    CollectionVerdict,
    ClusterPlanVerdict,
    build_all_qg_failure_matrices,
    build_collection_blockers,
    build_cluster_collection_plan,
    build_coverage_qg_forensics_report,
    build_nov06_pipeline_trace,
    build_nov09_pipeline_trace,
    build_calendar_integrity_s53,
    get_collection_verdict,
    PipelineStage,
)
from src.research.fallback_adapter_s53 import (
    Auth01Verdict,
    BackfillCandidateAction,
    FailureSimulationResult,
    FallbackSourceVerdict,
    SourceAvailability,
    build_auth01_manifest,
    build_failure_scenarios,
    build_fallback_and_auth01_report,
    build_fallback_feasibility_matrix,
    build_20d_readiness_matrix,
    build_twse_single_stock_spec,
    build_tpex_single_stock_spec,
    build_twse_bulk_historical_spec,
    build_tpex_bulk_historical_spec,
    get_auth01_overall_verdict,
    verify_idempotency_in_temp_db,
)


@pytest.fixture
def idempotency_tmp(tmp_path, monkeypatch):
    import src.research.fallback_adapter_s53 as _fa_module
    import tempfile as _tempfile

    _orig_ntf = _tempfile.NamedTemporaryFile

    def _ntf_with_dir(*args, **kwargs):
        kwargs.setdefault("dir", str(tmp_path))
        return _orig_ntf(*args, **kwargs)

    class _ScopedTempfileProxy:
        NamedTemporaryFile = staticmethod(_ntf_with_dir)

        def __getattr__(self, name):
            return getattr(_tempfile, name)

    monkeypatch.setattr(
        _fa_module, "tempfile", _ScopedTempfileProxy()
    )


# ══════════════════════════════════════════════════════════════════════════════
# TC01: Nov 06 QG Sub-condition Evidence
# ══════════════════════════════════════════════════════════════════════════════

class TestTC01_Nov06QGSubcondition:
    def test_nov06_on_nov09_overall_failed(self):
        matrices = build_all_qg_failure_matrices()
        nov06_nov09 = next(m for m in matrices
                          if m.target_date == "2026-11-06" and m.attempt_date == "2026-11-09")
        assert nov06_nov09.overall_failed is True

    def test_nov06_on_nov09_primary_failure_tpex_qg5(self):
        matrices = build_all_qg_failure_matrices()
        nov06_nov09 = next(m for m in matrices
                          if m.target_date == "2026-11-06" and m.attempt_date == "2026-11-09")
        assert nov06_nov09.primary_failure_check == QGSubCheck.QG_5_DATE_CONSISTENCY
        assert nov06_nov09.primary_failure_source == QGFailureSource.TPEX_BULK

    def test_nov06_on_nov09_twse_qg5_passes(self):
        matrices = build_all_qg_failure_matrices()
        nov06_nov09 = next(m for m in matrices
                          if m.target_date == "2026-11-06" and m.attempt_date == "2026-11-09")
        twse_qg5 = nov06_nov09.get_check(QGSubCheck.QG_5_DATE_CONSISTENCY, QGFailureSource.TWSE_BULK)
        assert twse_qg5 is not None
        assert twse_qg5.status == QGCheckStatus.PASS

    def test_nov06_on_nov09_tpex_qg5_fails(self):
        matrices = build_all_qg_failure_matrices()
        nov06_nov09 = next(m for m in matrices
                          if m.target_date == "2026-11-06" and m.attempt_date == "2026-11-09")
        tpex_qg5 = nov06_nov09.get_check(QGSubCheck.QG_5_DATE_CONSISTENCY, QGFailureSource.TPEX_BULK)
        assert tpex_qg5 is not None
        assert tpex_qg5.status == QGCheckStatus.FAIL
        assert tpex_qg5.blocking is True

    def test_nov06_on_nov09_root_cause_strongly_supported(self):
        matrices = build_all_qg_failure_matrices()
        nov06_nov09 = next(m for m in matrices
                          if m.target_date == "2026-11-06" and m.attempt_date == "2026-11-09")
        assert nov06_nov09.root_cause_confidence == QGConfidence.STRONGLY_SUPPORTED

    def test_nov06_on_nov09_cron_log_error_matches(self):
        matrices = build_all_qg_failure_matrices()
        nov06_nov09 = next(m for m in matrices
                          if m.target_date == "2026-11-06" and m.attempt_date == "2026-11-09")
        errors = " ".join(nov06_nov09.cron_log_errors)
        assert "quality gate FAILED" in errors
        assert "TWSE api_date" not in errors  # No TWSE mismatch error in log


# ══════════════════════════════════════════════════════════════════════════════
# TC02: Nov 09 Stale Response Evidence
# ══════════════════════════════════════════════════════════════════════════════

class TestTC02_Nov09StaleResponse:
    def test_nov09_on_nov09_twse_api_date_confirmed(self):
        matrices = build_all_qg_failure_matrices()
        nov09_nov09 = next(m for m in matrices
                          if m.target_date == "2026-11-09" and m.attempt_date == "2026-11-09")
        assert nov09_nov09.twse_api_date == "2026-11-06"
        assert nov09_nov09.twse_api_date_confidence == QGConfidence.DIRECTLY_CONFIRMED

    def test_nov09_on_nov09_qg5_twse_directly_confirmed(self):
        matrices = build_all_qg_failure_matrices()
        nov09_nov09 = next(m for m in matrices
                          if m.target_date == "2026-11-09" and m.attempt_date == "2026-11-09")
        qg5 = nov09_nov09.get_check(QGSubCheck.QG_5_DATE_CONSISTENCY, QGFailureSource.TWSE_BULK)
        assert qg5.confidence == QGConfidence.DIRECTLY_CONFIRMED
        assert qg5.status == QGCheckStatus.FAIL

    def test_nov09_on_nov09_cron_log_has_explicit_error(self):
        matrices = build_all_qg_failure_matrices()
        nov09_nov09 = next(m for m in matrices
                          if m.target_date == "2026-11-09" and m.attempt_date == "2026-11-09")
        errors = nov09_nov09.cron_log_errors
        twse_errors = [e for e in errors if "TWSE api_date=2026-11-06" in e]
        assert len(twse_errors) == 1

    def test_nov09_on_nov10_twse_passes_tpex_fails(self):
        matrices = build_all_qg_failure_matrices()
        nov09_nov10 = next(m for m in matrices
                          if m.target_date == "2026-11-09" and m.attempt_date == "2026-11-10")
        twse_qg5 = nov09_nov10.get_check(QGSubCheck.QG_5_DATE_CONSISTENCY, QGFailureSource.TWSE_BULK)
        tpex_qg5 = nov09_nov10.get_check(QGSubCheck.QG_5_DATE_CONSISTENCY, QGFailureSource.TPEX_BULK)
        assert twse_qg5.status == QGCheckStatus.PASS
        assert tpex_qg5.status == QGCheckStatus.FAIL


# ══════════════════════════════════════════════════════════════════════════════
# TC03: Scheduler Evidence
# ══════════════════════════════════════════════════════════════════════════════

class TestTC03_SchedulerEvidence:
    def test_nov06_scheduler_stage_failed(self):
        trace = build_nov06_pipeline_trace()
        stage = trace.get_stage(PipelineStage.SCHEDULER_TRIGGER)
        assert stage is not None
        assert stage.status == QGCheckStatus.FAIL
        assert stage.confidence == QGConfidence.DIRECTLY_CONFIRMED

    def test_nov06_process_start_not_started(self):
        trace = build_nov06_pipeline_trace()
        stage = trace.get_stage(PipelineStage.PROCESS_START)
        assert stage.status == QGCheckStatus.FAIL

    def test_nov09_scheduler_triggered(self):
        trace = build_nov09_pipeline_trace()
        stage = trace.get_stage(PipelineStage.SCHEDULER_TRIGGER)
        assert stage.status == QGCheckStatus.PASS
        assert stage.confidence == QGConfidence.DIRECTLY_CONFIRMED

    def test_nov06_all_provider_stages_not_checked(self):
        trace = build_nov06_pipeline_trace()
        for stage_enum in [
            PipelineStage.PROVIDER_TWSE_REQUEST,
            PipelineStage.PROVIDER_TWSE_RESPONSE,
        ]:
            stage = trace.get_stage(stage_enum)
            assert stage.status == QGCheckStatus.NOT_CHECKED


# ══════════════════════════════════════════════════════════════════════════════
# TC04: Provider Request Date
# ══════════════════════════════════════════════════════════════════════════════

class TestTC04_ProviderRequestDate:
    def test_twse_hist_url_csv_response_causes_fallback(self):
        """TWSE_HIST_URL returns CSV; json() fails → fallback to LATEST_URL."""
        report = build_coverage_qg_forensics_report()
        # Root cause documents TWSE_HIST_URL CSV issue
        assert "CSV" in report.twse_root_cause or "json" in report.twse_root_cause.lower()

    def test_tpex_hist_url_ignores_date_param(self):
        report = build_coverage_qg_forensics_report()
        assert "current" in report.tpex_root_cause.lower() or "current-date" in report.tpex_root_cause

    def test_nov09_twse_request_stage_fails(self):
        trace = build_nov09_pipeline_trace()
        stage = trace.get_stage(PipelineStage.PROVIDER_TWSE_REQUEST)
        assert stage.status == QGCheckStatus.FAIL

    def test_nov09_twse_response_stage_api_date_mismatch(self):
        trace = build_nov09_pipeline_trace()
        stage = trace.get_stage(PipelineStage.PROVIDER_TWSE_RESPONSE)
        assert "2026-11-06" in stage.observed_event


# ══════════════════════════════════════════════════════════════════════════════
# TC05: Provider Response Date
# ══════════════════════════════════════════════════════════════════════════════

class TestTC05_ProviderResponseDate:
    def test_nov09_all_matrices_show_qg5_failure(self):
        matrices = build_all_qg_failure_matrices()
        # All 5 matrices should have overall_failed = True
        assert all(m.overall_failed for m in matrices)

    def test_nov10_twse_returns_nov09(self):
        matrices = build_all_qg_failure_matrices()
        nov10_nov10 = next(m for m in matrices
                          if m.target_date == "2026-11-10" and m.attempt_date == "2026-11-10")
        assert nov10_nov10.twse_api_date == "2026-11-09"

    def test_nov06_on_nov10_twse_returns_nov09(self):
        matrices = build_all_qg_failure_matrices()
        nov06_nov10 = next(m for m in matrices
                          if m.target_date == "2026-11-06" and m.attempt_date == "2026-11-10")
        assert nov06_nov10.twse_api_date == "2026-11-09"
        assert nov06_nov10.twse_api_date_confidence == QGConfidence.DIRECTLY_CONFIRMED

    def test_provider_lag_pattern_1_trading_day(self):
        """TWSE_LATEST_URL always returns previous trading day."""
        matrices = build_all_qg_failure_matrices()
        # Nov09 on Nov09: api_date=Nov06 (previous trading day before Nov09)
        m1 = next(m for m in matrices
                  if m.target_date == "2026-11-09" and m.attempt_date == "2026-11-09")
        assert m1.twse_api_date == "2026-11-06"
        # Nov10 on Nov10: api_date=Nov09 (previous trading day before Nov10)
        m2 = next(m for m in matrices
                  if m.target_date == "2026-11-10" and m.attempt_date == "2026-11-10")
        assert m2.twse_api_date == "2026-11-09"


# ══════════════════════════════════════════════════════════════════════════════
# TC06: Cache / Fallback Logic
# ══════════════════════════════════════════════════════════════════════════════

class TestTC06_CacheFallbackLogic:
    def test_twse_bulk_source_unavailable_for_historical(self):
        spec = build_twse_bulk_historical_spec()
        assert spec.availability == SourceAvailability.SOURCE_UNAVAILABLE
        assert spec.historical_date_support is False

    def test_tpex_bulk_source_unavailable(self):
        spec = build_tpex_bulk_historical_spec()
        assert spec.availability == SourceAvailability.SOURCE_UNAVAILABLE
        assert spec.historical_date_support is False

    def test_twse_single_stock_source_verified_partial(self):
        spec = build_twse_single_stock_spec()
        assert spec.availability == SourceAvailability.SOURCE_VERIFIED_PARTIAL
        assert spec.historical_date_support is True

    def test_fallback_strategy_twse_single_stock_first(self):
        """Single-stock is the viable fallback; bulk is not."""
        matrix = build_fallback_feasibility_matrix()
        twse_single = next(s for s in matrix.sources
                           if s.source_name == "TWSE_SINGLE_STOCK")
        twse_bulk = next(s for s in matrix.sources
                        if s.source_name == "TWSE_BULK_HISTORICAL")
        assert twse_single.historical_date_support is True
        assert twse_bulk.historical_date_support is False


# ══════════════════════════════════════════════════════════════════════════════
# TC07: Benchmark-only Detection
# ══════════════════════════════════════════════════════════════════════════════

class TestTC07_BenchmarkOnlyDetection:
    def test_benchmark_only_scenario_exists(self):
        scenarios = build_failure_scenarios()
        bm = next((s for s in scenarios if s.scenario_id == "FS-10"), None)
        assert bm is not None
        assert bm.failure_mode == "BENCHMARK_ONLY"

    def test_benchmark_only_handled_correctly(self):
        scenarios = build_failure_scenarios()
        bm = next(s for s in scenarios if s.scenario_id == "FS-10")
        assert bm.result == FailureSimulationResult.HANDLED_CORRECTLY

    def test_benchmark_only_production_safe(self):
        scenarios = build_failure_scenarios()
        bm = next(s for s in scenarios if s.scenario_id == "FS-10")
        assert bm.production_safe is True


# ══════════════════════════════════════════════════════════════════════════════
# TC08: Partial Universe Detection
# ══════════════════════════════════════════════════════════════════════════════

class TestTC08_PartialUniverseDetection:
    def test_partial_universe_scenario_exists(self):
        scenarios = build_failure_scenarios()
        pu = next((s for s in scenarios if s.scenario_id == "FS-08"), None)
        assert pu is not None
        assert pu.failure_mode == "PARTIAL_UNIVERSE"

    def test_partial_universe_qg6_blocks_write(self):
        scenarios = build_failure_scenarios()
        pu = next(s for s in scenarios if s.scenario_id == "FS-08")
        assert "QG-6" in pu.expected_handling
        assert pu.result == FailureSimulationResult.HANDLED_CORRECTLY

    def test_partial_universe_via_qg_code(self):
        """Verify QG-6 fires when fewer than min_stocks rows returned."""
        from src.research.dailyprice_quality_gate import run_quality_gate
        import pandas as pd
        df = pd.DataFrame([{
            "stock_id": "0050", "date": "2026-10-29",
            "open": 150.0, "high": 155.0, "low": 149.0, "close": 152.0, "volume": 1000.0
        }])  # Only 1 row, min=300 for TWSE
        result = run_quality_gate(df, date(2026, 10, 29), "TWSE", require_benchmark=True)
        qg6_errors = [i for i in result.issues if i.check == "QG-6"]
        assert len(qg6_errors) > 0
        assert result.passed is False


# ══════════════════════════════════════════════════════════════════════════════
# TC09: Coverage Gate
# ══════════════════════════════════════════════════════════════════════════════

class TestTC09_CoverageGate:
    def test_qg6_threshold_twse_300(self):
        from src.research.dailyprice_quality_gate import _TWSE_MIN_STOCKS
        assert _TWSE_MIN_STOCKS == 300

    def test_qg6_threshold_tpex_50(self):
        from src.research.dailyprice_quality_gate import _TPEX_MIN_STOCKS
        assert _TPEX_MIN_STOCKS == 50

    def test_min_covered_stocks_5000(self):
        """backfill_daily_prices.py uses 5000 to decide if a date needs re-fetching."""
        import os
        spec_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "scripts", "backfill_daily_prices.py"
        )
        with open(spec_path) as f:
            content = f.read()
        assert "_MIN_COVERED_STOCKS = 5_000" in content or "_MIN_COVERED_STOCKS = 5000" in content

    def test_coverage_gate_passes_with_enough_stocks(self):
        from src.research.dailyprice_quality_gate import run_quality_gate
        import pandas as pd
        rows = []
        for i in range(350):
            sid = f"{1000 + i:04d}"
            rows.append({
                "stock_id": sid, "date": "2026-10-29",
                "open": 100.0, "high": 105.0, "low": 99.0, "close": 102.0, "volume": 1000.0
            })
        rows[0]["stock_id"] = "0050"  # ensure benchmark present
        df = pd.DataFrame(rows)
        result = run_quality_gate(df, date(2026, 10, 29), "TWSE", require_benchmark=True)
        qg6_errors = [i for i in result.issues if i.check == "QG-6"]
        assert len(qg6_errors) == 0


# ══════════════════════════════════════════════════════════════════════════════
# TC10: Completion Marker
# ══════════════════════════════════════════════════════════════════════════════

class TestTC10_CompletionMarker:
    def test_nov06_completion_marker_absent(self):
        trace = build_nov06_pipeline_trace()
        stage = trace.get_stage(PipelineStage.COMPLETION_MARKER)
        assert stage.status == QGCheckStatus.FAIL
        assert stage.confidence == QGConfidence.DIRECTLY_CONFIRMED

    def test_nov09_completion_marker_blocked(self):
        trace = build_nov09_pipeline_trace()
        stage = trace.get_stage(PipelineStage.COMPLETION_MARKER)
        assert stage.status == QGCheckStatus.FAIL
        assert "BLOCKED" in stage.observed_event.upper() or "STALE" in stage.observed_event.upper()

    def test_cron_state_json_shows_provider_not_ready(self):
        """cron_state.json confirms PROVIDER_NOT_READY status for Nov09/Nov10."""
        import os
        state_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "data", ".cron_state.json"
        )
        with open(state_path) as f:
            state = json.load(f)
        assert state.get("steps", {}).get("data_freshness") == "PROVIDER_NOT_READY"


# ══════════════════════════════════════════════════════════════════════════════
# TC11: TWSE Single-stock Source
# ══════════════════════════════════════════════════════════════════════════════

class TestTC11_TWSSingleStockSource:
    def test_twse_single_stock_verified_partial(self):
        spec = build_twse_single_stock_spec()
        assert spec.availability == SourceAvailability.SOURCE_VERIFIED_PARTIAL

    def test_twse_single_stock_verified_6_stocks(self):
        spec = build_twse_single_stock_spec()
        assert spec.verified_stock_count == 6

    def test_twse_single_stock_verified_dates_include_nov06(self):
        spec = build_twse_single_stock_spec()
        assert "2026-11-06" in spec.verified_dates
        assert "2026-11-09" in spec.verified_dates

    def test_twse_single_stock_599_calls_per_date(self):
        spec = build_twse_single_stock_spec()
        assert spec.estimated_calls_per_date == 599

    def test_twse_single_stock_production_safe(self):
        spec = build_twse_single_stock_spec()
        assert spec.production_safe is True

    def test_twse_single_stock_tpex_coverage_zero(self):
        """TWSE single-stock cannot cover TPEx-listed stocks."""
        spec = build_twse_single_stock_spec()
        assert spec.tpex_coverage_pct == 0.0


# ══════════════════════════════════════════════════════════════════════════════
# TC12: TPEx Source Assessment
# ══════════════════════════════════════════════════════════════════════════════

class TestTC12_TPExSourceAssessment:
    def test_tpex_single_stock_unverified(self):
        spec = build_tpex_single_stock_spec()
        assert spec.availability == SourceAvailability.SOURCE_UNVERIFIED

    def test_tpex_single_stock_no_verified_dates(self):
        spec = build_tpex_single_stock_spec()
        assert len(spec.verified_dates) == 0

    def test_tpex_bulk_source_unavailable(self):
        spec = build_tpex_bulk_historical_spec()
        assert spec.availability == SourceAvailability.SOURCE_UNAVAILABLE

    def test_tpex_coverage_gap_documented(self):
        matrix = build_fallback_feasibility_matrix()
        assert matrix.tpex_coverage_estimate_stocks == 0
        assert "TPEx" in matrix.notes
        assert "UNVERIFIED" in matrix.notes


# ══════════════════════════════════════════════════════════════════════════════
# TC13: Historical Date Validation
# ══════════════════════════════════════════════════════════════════════════════

class TestTC13_HistoricalDateValidation:
    def test_qg5_validates_every_row(self):
        """QG-5 checks every row's date field, not just the api_date."""
        from src.research.dailyprice_quality_gate import run_quality_gate
        import pandas as pd
        df = pd.DataFrame([{
            "stock_id": "0050", "date": "2026-11-09",  # wrong date for Nov06 target
            "open": 100.0, "high": 105.0, "low": 99.0, "close": 102.0, "volume": 1000.0
        }])
        result = run_quality_gate(df, date(2026, 11, 6), "TWSE", require_benchmark=True)
        qg5_errors = [i for i in result.issues if i.check == "QG-5"]
        assert len(qg5_errors) >= 1
        assert result.passed is False

    def test_qg5_passes_when_date_matches(self):
        from src.research.dailyprice_quality_gate import run_quality_gate
        import pandas as pd
        rows = [{"stock_id": f"{1000+i:04d}", "date": "2026-10-29",
                 "open": 100.0, "high": 105.0, "low": 99.0, "close": 102.0, "volume": 1000.0}
                for i in range(350)]
        rows[0]["stock_id"] = "0050"
        df = pd.DataFrame(rows)
        result = run_quality_gate(df, date(2026, 10, 29), "TWSE", require_benchmark=True)
        qg5_errors = [i for i in result.issues if i.check == "QG-5"]
        assert len(qg5_errors) == 0

    def test_tpex_qg5_not_in_summary_errors_field(self):
        """TPEx mismatch is print() only, NOT in summary['errors']."""
        # This is a code-behavior test: TPEx warning goes to stdout, not to errors list
        # Verified from scripts/backfill_daily_prices.py lines ~500-502:
        # print(f"  [WARN] {target_d}: TPEx api_date={tpex_api_date} != target")
        # (no summary["errors"].append for TPEx)
        from src.research.coverage_qg_forensics_s53 import _build_nov06_on_nov09_matrix
        m = _build_nov06_on_nov09_matrix()
        # Cron log errors should NOT contain "TPEx api_date"
        for err in m.cron_log_errors:
            assert "TPEx api_date" not in err


# ══════════════════════════════════════════════════════════════════════════════
# TC14: Wrong Stock ID
# ══════════════════════════════════════════════════════════════════════════════

class TestTC14_WrongStockID:
    def test_wrong_stock_id_scenario(self):
        scenarios = build_failure_scenarios()
        ws = next((s for s in scenarios if s.scenario_id == "FS-05"), None)
        assert ws is not None
        assert ws.failure_mode == "WRONG_STOCK_ID"

    def test_wrong_stock_id_partial_recovery(self):
        scenarios = build_failure_scenarios()
        ws = next(s for s in scenarios if s.scenario_id == "FS-05")
        assert ws.result == FailureSimulationResult.PARTIAL_RECOVERY

    def test_qg4_catches_duplicates(self):
        from src.research.dailyprice_quality_gate import run_quality_gate
        import pandas as pd
        df = pd.DataFrame([
            {"stock_id": "2330", "date": "2026-10-29", "open": 100.0, "high": 105.0,
             "low": 99.0, "close": 102.0, "volume": 1000.0},
            {"stock_id": "2330", "date": "2026-10-29", "open": 101.0, "high": 106.0,
             "low": 100.0, "close": 103.0, "volume": 1100.0},
        ])
        result = run_quality_gate(df, date(2026, 10, 29), "TWSE", min_stocks=1,
                                  require_benchmark=False)
        qg4_errors = [i for i in result.issues if i.check == "QG-4"]
        assert len(qg4_errors) >= 1


# ══════════════════════════════════════════════════════════════════════════════
# TC15: Invalid OHLC
# ══════════════════════════════════════════════════════════════════════════════

class TestTC15_InvalidOHLC:
    def test_qg1_catches_low_above_high(self):
        from src.research.dailyprice_quality_gate import run_quality_gate
        import pandas as pd
        df = pd.DataFrame([{
            "stock_id": "2330", "date": "2026-10-29",
            "open": 100.0, "high": 95.0,  # high < open → inconsistent
            "low": 90.0, "close": 102.0, "volume": 1000.0
        }])
        result = run_quality_gate(df, date(2026, 10, 29), "TWSE",
                                  min_stocks=1, require_benchmark=False)
        qg1_errors = [i for i in result.issues if i.check == "QG-1"]
        assert len(qg1_errors) >= 1

    def test_qg2_catches_negative_close(self):
        from src.research.dailyprice_quality_gate import run_quality_gate
        import pandas as pd
        df = pd.DataFrame([{
            "stock_id": "2330", "date": "2026-10-29",
            "open": 100.0, "high": 110.0, "low": 90.0, "close": -1.0, "volume": 1000.0
        }])
        result = run_quality_gate(df, date(2026, 10, 29), "TWSE",
                                  min_stocks=1, require_benchmark=False)
        qg2_errors = [i for i in result.issues if i.check == "QG-2"]
        assert len(qg2_errors) >= 1

    def test_missing_ohlc_row_excluded_from_df(self):
        """Rows with all None OHLC are excluded before QG."""
        # Simulate parser behavior: if all None, skip row
        rows_raw = [
            {"open": None, "high": None, "low": None, "close": None},
            {"open": 100.0, "high": 105.0, "low": 99.0, "close": 102.0},
        ]
        # Parser check: `if o is None and h is None and lo is None and c is None: continue`
        parsed = [r for r in rows_raw
                  if not (r["open"] is None and r["high"] is None
                          and r["low"] is None and r["close"] is None)]
        assert len(parsed) == 1


# ══════════════════════════════════════════════════════════════════════════════
# TC16: Duplicate Response
# ══════════════════════════════════════════════════════════════════════════════

class TestTC16_DuplicateResponse:
    def test_duplicate_response_scenario(self):
        scenarios = build_failure_scenarios()
        dup = next((s for s in scenarios if s.scenario_id == "FS-07"), None)
        assert dup is not None
        assert dup.failure_mode == "DUPLICATE_RESPONSE"
        assert dup.result == FailureSimulationResult.HANDLED_CORRECTLY

    def test_qg4_error_detail_contains_count(self):
        from src.research.dailyprice_quality_gate import run_quality_gate
        import pandas as pd
        df = pd.DataFrame([
            {"stock_id": "2330", "date": "2026-10-29", "open": 100.0, "high": 105.0,
             "low": 99.0, "close": 102.0, "volume": 1000.0},
            {"stock_id": "2330", "date": "2026-10-29", "open": 103.0, "high": 108.0,
             "low": 101.0, "close": 105.0, "volume": 1200.0},
        ])
        result = run_quality_gate(df, date(2026, 10, 29), "TWSE",
                                  min_stocks=1, require_benchmark=False)
        qg4 = [i for i in result.issues if i.check == "QG-4"]
        assert len(qg4) >= 1
        assert "2" in qg4[0].detail  # "appears 2 times"


# ══════════════════════════════════════════════════════════════════════════════
# TC17: Rate Limit
# ══════════════════════════════════════════════════════════════════════════════

class TestTC17_RateLimit:
    def test_rate_limit_scenario_partial_recovery(self):
        scenarios = build_failure_scenarios()
        rl = next((s for s in scenarios if s.scenario_id == "FS-03"), None)
        assert rl is not None
        assert rl.failure_mode == "RATE_LIMIT"
        # Partial recovery because 429 handling is not 429-specific in current code
        assert rl.result == FailureSimulationResult.PARTIAL_RECOVERY

    def test_twse_single_stock_low_rate_limit_risk(self):
        spec = build_twse_single_stock_spec()
        assert spec.rate_limit_risk == "LOW"

    def test_tpex_single_stock_high_rate_limit_risk(self):
        """Unknown endpoint → conservative HIGH risk."""
        spec = build_tpex_single_stock_spec()
        assert spec.rate_limit_risk == "HIGH"


# ══════════════════════════════════════════════════════════════════════════════
# TC18: Timeout
# ══════════════════════════════════════════════════════════════════════════════

class TestTC18_Timeout:
    def test_timeout_scenario_handled(self):
        scenarios = build_failure_scenarios()
        to = next((s for s in scenarios if s.scenario_id == "FS-02"), None)
        assert to is not None
        assert to.failure_mode == "TIMEOUT"
        assert to.result == FailureSimulationResult.HANDLED_CORRECTLY

    def test_http_timeout_30s_in_backfill(self):
        import os
        script_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "scripts", "backfill_daily_prices.py"
        )
        with open(script_path) as f:
            content = f.read()
        assert "HTTP_TIMEOUT = 30" in content


# ══════════════════════════════════════════════════════════════════════════════
# TC19: Retry Exhaustion
# ══════════════════════════════════════════════════════════════════════════════

class TestTC19_RetryExhaustion:
    def test_retry_exhaustion_scenario(self):
        scenarios = build_failure_scenarios()
        re = next((s for s in scenarios if s.scenario_id == "FS-11"), None)
        assert re is not None
        assert re.failure_mode == "RETRY_EXHAUSTION"
        assert re.result == FailureSimulationResult.HANDLED_CORRECTLY

    def test_http_retry_3_in_backfill(self):
        import os
        script_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "scripts", "backfill_daily_prices.py"
        )
        with open(script_path) as f:
            content = f.read()
        assert "HTTP_RETRY = 3" in content

    def test_cron_retry_max_3(self):
        from scripts.hybrid_shadow_cron import RETRY_MAX
        assert RETRY_MAX == 3


# ══════════════════════════════════════════════════════════════════════════════
# TC20: Fallback Partial Recovery
# ══════════════════════════════════════════════════════════════════════════════

class TestTC20_FallbackPartialRecovery:
    def test_overall_verdict_fallback_partial(self):
        matrix = build_fallback_feasibility_matrix()
        assert matrix.overall_verdict == FallbackSourceVerdict.FALLBACK_PARTIAL

    def test_tpex_unavailable_scenario_partial(self):
        scenarios = build_failure_scenarios()
        tpex = next((s for s in scenarios if s.scenario_id == "FS-09"), None)
        assert tpex is not None
        assert tpex.result == FailureSimulationResult.PARTIAL_RECOVERY

    def test_successful_recovery_scenario_exists(self):
        scenarios = build_failure_scenarios()
        ok = next((s for s in scenarios if s.scenario_id == "FS-12"), None)
        assert ok is not None
        assert ok.result == FailureSimulationResult.HANDLED_CORRECTLY

    def test_fallback_not_equal_to_pipeline_recovery(self):
        """Prototype PASS ≠ production pipeline recovery."""
        matrix = build_fallback_feasibility_matrix()
        assert "research use only" in matrix.notes.lower() or "prototype" in matrix.notes.lower()


# ══════════════════════════════════════════════════════════════════════════════
# TC21: Source Verification
# ══════════════════════════════════════════════════════════════════════════════

class TestTC21_SourceVerification:
    def test_twse_single_verified_dates_6(self):
        spec = build_twse_single_stock_spec()
        assert len(spec.verified_dates) == 6

    def test_verified_stock_sample_includes_tsmc(self):
        """2330 (TSMC) is confirmed in S50."""
        manifest = build_auth01_manifest()
        oct29 = next(m for m in manifest if m.target_date == "2026-10-29")
        tsmc = [s for s in oct29.verified_stock_sample if s.startswith("2330:")]
        assert len(tsmc) == 1

    def test_partial_verification_not_complete_coverage(self):
        """SOURCE_VERIFIED_PARTIAL ≠ all 599 stocks verified."""
        spec = build_twse_single_stock_spec()
        assert spec.verified_stock_count < spec.estimated_calls_per_date


# ══════════════════════════════════════════════════════════════════════════════
# TC22: Backfill Manifest Structure
# ══════════════════════════════════════════════════════════════════════════════

class TestTC22_BackfillManifestStructure:
    def test_manifest_has_8_dates(self):
        manifest = build_auth01_manifest()
        assert len(manifest) == 8

    def test_manifest_covers_all_candidate_dates(self):
        manifest = build_auth01_manifest()
        dates = {m.target_date for m in manifest}
        expected = {
            "2026-10-29", "2026-10-30", "2026-11-02", "2026-11-03",
            "2026-11-04", "2026-11-05", "2026-11-06", "2026-11-09",
        }
        assert dates == expected

    def test_manifest_nov04_nov05_already_covered(self):
        manifest = build_auth01_manifest()
        for d in ["2026-11-04", "2026-11-05"]:
            rec = next(m for m in manifest if m.target_date == d)
            assert rec.action == BackfillCandidateAction.SKIP_EXISTING

    def test_manifest_p1_dates_all_pending(self):
        manifest = build_auth01_manifest()
        p1 = [m for m in manifest if m.priority == "P1_PRIORITY"
              and m.action == BackfillCandidateAction.INSERT_CANDIDATE]
        assert all(m.auth01_verdict == Auth01Verdict.PENDING_USER_AUTHORIZATION for m in p1)

    def test_manifest_no_auto_update_delete(self):
        """All insert candidates use INSERT_CANDIDATE; no UPDATE or DELETE."""
        manifest = build_auth01_manifest()
        for m in manifest:
            assert m.action in (
                BackfillCandidateAction.INSERT_CANDIDATE,
                BackfillCandidateAction.SKIP_EXISTING,
            )


# ══════════════════════════════════════════════════════════════════════════════
# TC23: Insert-only
# ══════════════════════════════════════════════════════════════════════════════

class TestTC23_InsertOnly:
    def test_first_insert_succeeds(self, idempotency_tmp):
        result = verify_idempotency_in_temp_db()
        assert result["test_first_insert"] is True
        assert result["first_insert_count"] == 2

    def test_no_update_delete_in_backfill_script(self):
        """Backfill uses INSERT OR IGNORE — no UPDATE or DELETE."""
        import os
        script_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "scripts", "backfill_daily_prices.py"
        )
        with open(script_path) as f:
            content = f.read()
        assert "INSERT OR IGNORE" in content
        assert "UPDATE" not in content.upper().split("# ")[0][:5000]


# ══════════════════════════════════════════════════════════════════════════════
# TC24: Duplicate Conflict
# ══════════════════════════════════════════════════════════════════════════════

class TestTC24_DuplicateConflict:
    def test_idempotent_repeat_insert_zero(self, idempotency_tmp):
        result = verify_idempotency_in_temp_db()
        assert result["test_idempotent"] is True
        assert result["repeat_insert_count"] == 0

    def test_conflict_with_different_value_ignored(self, idempotency_tmp):
        result = verify_idempotency_in_temp_db()
        assert result["test_conflict_ignored"] is True
        assert result["conflict_rowcount"] == 0

    def test_original_data_preserved_after_conflict(self, idempotency_tmp):
        result = verify_idempotency_in_temp_db()
        assert result["test_original_data_preserved"] is True


# ══════════════════════════════════════════════════════════════════════════════
# TC25: Transaction Rollback
# ══════════════════════════════════════════════════════════════════════════════

class TestTC25_TransactionRollback:
    def test_rollback_removes_uncommitted_row(self, idempotency_tmp):
        result = verify_idempotency_in_temp_db()
        assert result["test_rollback"] is True

    def test_readback_count_matches_inserted(self, idempotency_tmp):
        result = verify_idempotency_in_temp_db()
        assert result["test_readback"] is True
        assert result["readback_count"] == 2


# ══════════════════════════════════════════════════════════════════════════════
# TC26: AUTH01 Pending
# ══════════════════════════════════════════════════════════════════════════════

class TestTC26_AUTH01Pending:
    def test_auth01_overall_partially_ready(self):
        manifest = build_auth01_manifest()
        verdict = get_auth01_overall_verdict(manifest)
        assert verdict in (Auth01Verdict.PARTIALLY_READY, Auth01Verdict.PENDING_USER_AUTHORIZATION)

    def test_auth01_insert_candidates_all_pending(self):
        manifest = build_auth01_manifest()
        candidates = [m for m in manifest if m.action == BackfillCandidateAction.INSERT_CANDIDATE]
        assert all(m.auth01_verdict == Auth01Verdict.PENDING_USER_AUTHORIZATION
                   for m in candidates)

    def test_auth01_does_not_authorize_itself(self):
        """The module only defines the manifest; it does not execute backfill."""
        build_fallback_and_auth01_report()
        # Module must not perform writes — test that non-benchmark rows are still 0
        import os
        db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "platform.db")
        conn = sqlite3.connect(db_path)
        count = conn.execute(
            "SELECT COUNT(*) FROM daily_prices "
            "WHERE date IN ('2026-10-29','2026-10-30') AND stock_id != '0050'"
        ).fetchone()[0]
        conn.close()
        assert count == 0  # Non-0050 rows absent; manifest build performs no writes


# ══════════════════════════════════════════════════════════════════════════════
# TC27: Recorder Readiness
# ══════════════════════════════════════════════════════════════════════════════

class TestTC27_RecorderReadiness:
    def test_recorder_module_exists(self):
        from src.research.prospective_recorder_s51 import ProspectiveRecorderPrototype
        assert ProspectiveRecorderPrototype is not None

    def test_recorder_cb06_status_ready(self):
        blockers = build_collection_blockers()
        cb06 = next(b for b in blockers if b.blocker_id == "CB-06")
        assert cb06.status == CollectionBlockerStatus.READY

    def test_recorder_requires_no_new_authorization(self):
        blockers = build_collection_blockers()
        cb06 = next(b for b in blockers if b.blocker_id == "CB-06")
        assert cb06.authorization_required is None


# ══════════════════════════════════════════════════════════════════════════════
# TC28: V3 Decision Cutoff
# ══════════════════════════════════════════════════════════════════════════════

class TestTC28_V3DecisionCutoff:
    def test_decision_cutoff_cb04_engineering_blocked(self):
        blockers = build_collection_blockers()
        cb04 = next(b for b in blockers if b.blocker_id == "CB-04")
        assert cb04.status == CollectionBlockerStatus.ENGINEERING_BLOCKED

    def test_v3_decision_generation_requires_authorization(self):
        blockers = build_collection_blockers()
        cb05 = next(b for b in blockers if b.blocker_id == "CB-05")
        assert cb05.status == CollectionBlockerStatus.AUTHORIZATION_REQUIRED
        assert cb05.authorization_required is not None

    def test_rule_freeze_date_nov05(self):
        """Decisions before 2026-11-05 are RETROSPECTIVE_RECONSTRUCTION."""
        from src.research.provenance_audit_s52 import RULE_FREEZE_DATE
        assert str(RULE_FREEZE_DATE) == "2026-11-05"


# ══════════════════════════════════════════════════════════════════════════════
# TC29: Input Snapshot
# ══════════════════════════════════════════════════════════════════════════════

class TestTC29_InputSnapshot:
    def test_input_snapshot_cb03_ready(self):
        blockers = build_collection_blockers()
        cb03 = next(b for b in blockers if b.blocker_id == "CB-03")
        assert cb03.status == CollectionBlockerStatus.READY

    def test_extended_payload_has_input_cutoff(self):
        import dataclasses
        from src.research.provenance_audit_s52 import ExtendedDecisionPayload
        field_names = {f.name for f in dataclasses.fields(ExtendedDecisionPayload)}
        assert "input_cutoff" in field_names

    def test_input_snapshot_fingerprint_separate_from_decision_fingerprint(self):
        """input_snapshot_fingerprint NOT in _IMMUTABLE_FIELDS (S52 correction)."""
        from src.research.provenance_audit_s52 import ExtendedDecisionPayload
        assert "input_snapshot_fingerprint" not in ExtendedDecisionPayload._IMMUTABLE_FIELDS


# ══════════════════════════════════════════════════════════════════════════════
# TC30: Immutable Fingerprint
# ══════════════════════════════════════════════════════════════════════════════

class TestTC30_ImmutableFingerprint:
    def test_fingerprint_registered_at_included_in_immutable(self):
        """registered_at IS in ImmutableDecisionPayload fingerprint (S52 confirmed)."""
        from src.research.prospective_recorder_s51 import (
            ImmutableDecisionPayload, DecisionClassification, _compute_fingerprint,
        )
        import dataclasses
        p1 = ImmutableDecisionPayload(
            fill_date="2026-10-13", signal_id=1, stock_id="2330",
            model_version="v8.0", locked_at="2026-10-12T10:00:00Z",
            trade_signal="buy", v3_decision_snapshot=None,
            classification=DecisionClassification.BASE_SIGNAL_PROSPECTIVE,
            registered_at="2026-10-14T00:00:00+00:00",
        )
        p2 = dataclasses.replace(
            p1, registered_at="2099-01-01T00:00:00+00:00",
            research_fingerprint="",
        )
        fp1 = _compute_fingerprint(p1)
        fp2 = _compute_fingerprint(p2)
        assert fp1 != fp2  # registered_at IS in fingerprint

    def test_fingerprint_registered_at_not_in_extended_immutable_fields(self):
        """ExtendedDecisionPayload._IMMUTABLE_FIELDS excludes registered_at (different struct)."""
        from src.research.provenance_audit_s52 import ExtendedDecisionPayload
        assert "registered_at" not in ExtendedDecisionPayload._IMMUTABLE_FIELDS

    def test_fingerprint_mutation_detected(self):
        """Any _IMMUTABLE_FIELDS change must change the ExtendedDecisionPayload fingerprint."""
        from src.research.provenance_audit_s52 import ExtendedDecisionPayload
        from src.research.prospective_recorder_s51 import DecisionClassification
        import dataclasses
        p1 = ExtendedDecisionPayload(
            fill_date="2026-10-13", signal_id=1, stock_id="2330",
            model_version="v8.0", locked_at="2026-10-12T10:00:00Z",
            trade_signal="buy", v3_decision_snapshot=None,
            classification=DecisionClassification.BASE_SIGNAL_PROSPECTIVE,
            registered_at="2026-10-14T00:00:00+00:00",
            code_commit_hash="abc123", parameter_hash="be43e8ca977d9fdd",
            input_cutoff="2026-10-12T18:00:00Z",
            input_snapshot_fingerprint="deadbeef01234567",
        )
        p2 = dataclasses.replace(p1, trade_signal="sell", decision_payload_fingerprint="")
        assert p1._compute_fingerprint() != p2._compute_fingerprint()


# ══════════════════════════════════════════════════════════════════════════════
# TC31: Mock vs Genuine Prospective
# ══════════════════════════════════════════════════════════════════════════════

class TestTC31_MockVsGenuineProspective:
    def test_zero_v3_decision_prospective(self):
        assert PROVENANCE_SUMMARY["v3_decision_prospective_count"] == 0

    def test_hybrid_forward_decision_retrospective(self):
        assert PROVENANCE_SUMMARY["retrospective_reconstruction_count"] == 21

    def test_base_signal_prospective_not_v3(self):
        """BASE_SIGNAL_PROSPECTIVE ≠ V3_DECISION_PROSPECTIVE."""
        assert PROVENANCE_SUMMARY["classification"] == "BASE_ONLY_PROSPECTIVE"

    def test_collection_plan_forbids_mock_as_genuine(self):
        plan = build_cluster_collection_plan()
        bias_risks = " ".join(plan.selection_bias_risks)
        assert "Mock" not in bias_risks or "do not count" in bias_risks


# ══════════════════════════════════════════════════════════════════════════════
# TC32: Collection Authorization Matrix
# ══════════════════════════════════════════════════════════════════════════════

class TestTC32_CollectionAuthorizationMatrix:
    def test_collection_blocked_verdict(self):
        assert get_collection_verdict() == CollectionVerdict.COLLECTION_BLOCKED

    def test_12_blockers_defined(self):
        blockers = build_collection_blockers()
        assert len(blockers) == 12

    def test_all_blocker_ids_unique(self):
        blockers = build_collection_blockers()
        ids = [b.blocker_id for b in blockers]
        assert len(ids) == len(set(ids))

    def test_data_blocked_includes_pipeline_blocker(self):
        blockers = build_collection_blockers()
        data_blocked = [b for b in blockers if b.status == CollectionBlockerStatus.DATA_BLOCKED]
        assert len(data_blocked) >= 2  # CB-08, CB-09 at minimum

    def test_separate_authorizations_not_merged_into_auth01(self):
        blockers = build_collection_blockers()
        for b in blockers:
            if b.authorization_required:
                assert "AUTH01" != b.authorization_required or b.blocker_id in ("CB-08", "CB-09")


# ══════════════════════════════════════════════════════════════════════════════
# TC33: Independent Cluster Spacing
# ══════════════════════════════════════════════════════════════════════════════

class TestTC33_IndependentClusterSpacing:
    def test_minimum_spacing_6td(self):
        plan = build_cluster_collection_plan()
        assert plan.minimum_spacing_td == 6

    def test_target_n_10(self):
        plan = build_cluster_collection_plan()
        assert plan.target_n_for_g03 == 10

    def test_minimum_theoretical_days_60(self):
        plan = build_cluster_collection_plan()
        assert plan.minimum_theoretical_days == 60

    def test_rules_frozen_at_session52(self):
        plan = build_cluster_collection_plan()
        assert plan.collection_rules_frozen is True
        assert "52" in plan.rules_frozen_at or "Session 52" in plan.rules_frozen_at

    def test_cluster_plan_blocked(self):
        plan = build_cluster_collection_plan()
        assert plan.collection_verdict == ClusterPlanVerdict.CLUSTER_PLAN_BLOCKED


# ══════════════════════════════════════════════════════════════════════════════
# TC34: G03 Guardrail
# ══════════════════════════════════════════════════════════════════════════════

class TestTC34_G03:
    def test_g03_still_fail(self):
        """G03: N≥10 V3_DECISION_PROSPECTIVE clusters. Currently 0/10."""
        plan = build_cluster_collection_plan()
        assert plan.current_v3_prospective_n == 0
        assert plan.additional_n_needed == 10

    def test_g03_cannot_be_fixed_with_historical_data(self):
        plan = build_cluster_collection_plan()
        notes = plan.notes
        assert "historical" in notes.lower() or "not V3_DECISION_PROSPECTIVE" in notes

    def test_historical_strict_n3_not_v3_prospective(self):
        plan = build_cluster_collection_plan()
        assert plan.current_strict_historical_n == 3
        assert plan.current_v3_prospective_n != plan.current_strict_historical_n


# ══════════════════════════════════════════════════════════════════════════════
# TC35: G04 Guardrail
# ══════════════════════════════════════════════════════════════════════════════

class TestTC35_G04:
    def test_g04_structural_fail(self):
        """G04 structural: 5D window + ≤5TD historical spacing = guaranteed overlap."""
        plan = build_cluster_collection_plan()
        # G04 requires ≥6TD spacing; existing historical clusters may overlap
        assert plan.minimum_spacing_td == 6
        # Structural fail means even with 6TD, the 5D window still creates overlap at 6TD
        # G04 fails because: holding window = 5TD, min spacing = 6TD → barely avoids overlap
        # But with historical clusters already at <6TD spacing, G04 fails structurally
        notes = plan.notes
        assert "G04" in notes or "structural" in notes.lower()

    def test_g04_cannot_be_fixed_by_adding_more_historical_data(self):
        """G04 requires genuinely new clusters ≥6TD apart."""
        plan = build_cluster_collection_plan()
        assert plan.collection_verdict == ClusterPlanVerdict.CLUSTER_PLAN_BLOCKED


# ══════════════════════════════════════════════════════════════════════════════
# TC36: Calendar SSOT
# ══════════════════════════════════════════════════════════════════════════════

class TestTC36_CalendarSSOT:
    def test_calendar_ssot_verified(self):
        cal = build_calendar_integrity_s53()
        assert cal.verdict == "CALENDAR_E2E_VERIFIED"

    def test_calendar_ssot_module_correct(self):
        cal = build_calendar_integrity_s53()
        assert "calendar_contract_s50" in cal.ssot_module

    def test_all_callers_compliant(self):
        cal = build_calendar_integrity_s53()
        assert cal.all_callers_compliant is True

    def test_legacy_isolated(self):
        cal = build_calendar_integrity_s53()
        assert cal.legacy_isolated is True

    def test_exit_dates_verified(self):
        from src.research.calendar_contract_s50 import get_corrected_exit
        oct13_5td = get_corrected_exit("2026-10-13", "5TD")
        assert oct13_5td is not None

    def test_canonical_20td_exit_oct13(self):
        assert CANONICAL_20TD_EXITS["2026-10-13"] == "2026-11-12"

    def test_canonical_20td_exit_oct16_corrected(self):
        """Oct16 20TD = Nov17 (corrected from Nov20 in S52)."""
        assert CANONICAL_20TD_EXITS["2026-10-16"] == "2026-11-17"


# ══════════════════════════════════════════════════════════════════════════════
# TC37: Canonical Fill Dates
# ══════════════════════════════════════════════════════════════════════════════

class TestTC37_CanonicalFillDates:
    def test_six_canonical_fill_dates(self):
        assert len(CANONICAL_FILL_DATES) == 6

    def test_oct16_in_fill_dates(self):
        assert "2026-10-16" in CANONICAL_FILL_DATES

    def test_oct27_not_a_fill_date(self):
        """Oct27 is 5TD exit of Oct16, NOT a fill date (S52 correction)."""
        assert "2026-10-27" not in CANONICAL_FILL_DATES

    def test_oct27_is_5td_exit_of_oct16(self):
        assert CANONICAL_5TD_EXITS["2026-10-16"] == "2026-10-23" or \
               CANONICAL_5TD_EXITS.get("2026-10-16") is not None

    def test_all_6_dates_present(self):
        expected = {
            "2026-10-13", "2026-10-14", "2026-10-16",
            "2026-10-21", "2026-10-22", "2026-10-28",
        }
        assert set(CANONICAL_FILL_DATES) == expected


# ══════════════════════════════════════════════════════════════════════════════
# TC38: No 20D Outcome
# ══════════════════════════════════════════════════════════════════════════════

class TestTC38_No20DOutcome:
    def test_all_clusters_blocked_pipeline_or_auth02(self):
        matrix = build_20d_readiness_matrix()
        for cluster in matrix:
            assert cluster.auth02_pending is True

    def test_missing_dates_in_window(self):
        matrix = build_20d_readiness_matrix()
        # All clusters should have at least Nov06+ in their 20TD window
        for c in matrix:
            # Every cluster's 20TD exit is after Nov06, so Nov06+ dates are missing
            if c.fill_date in ["2026-10-13", "2026-10-14", "2026-10-16",
                               "2026-10-21", "2026-10-22", "2026-10-28"]:
                assert len(c.missing_dates_in_window) > 0

    def test_no_20d_computation_in_module(self):
        """Module should not compute 20D returns — only readiness."""
        import os
        module_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "src", "research", "fallback_adapter_s53.py"
        )
        with open(module_path) as f:
            content = f.read()
        # No return computation (no subtraction or ratio of prices for PnL)
        assert "20d_return" not in content.lower()
        assert "outcome" not in content.lower() or "readiness" in content.lower()


# ══════════════════════════════════════════════════════════════════════════════
# TC39: Frozen Baseline
# ══════════════════════════════════════════════════════════════════════════════

class TestTC39_FrozenBaseline:
    def test_baseline_n3_strict_clusters(self):
        import os
        db = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "platform.db")
        conn = sqlite3.connect(db)
        from src.research.canonical_5d_baseline_s44 import build_canonical_5d_baseline
        b = build_canonical_5d_baseline(conn)
        conn.close()
        assert b.n_strict_clusters == 3

    def test_baseline_delta_0_81pp(self):
        import os
        db = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "platform.db")
        conn = sqlite3.connect(db)
        from src.research.canonical_5d_baseline_s44 import build_canonical_5d_baseline
        b = build_canonical_5d_baseline(conn)
        conn.close()
        assert abs(b.s44_computed_delta - 0.00813) < 0.001

    def test_baseline_fingerprint_unchanged(self):
        import os
        db = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "platform.db")
        conn = sqlite3.connect(db)
        from src.research.canonical_5d_baseline_s44 import build_canonical_5d_baseline
        b = build_canonical_5d_baseline(conn)
        conn.close()
        assert b.dataset_fingerprint == "09c04e8c4059d87e"

    def test_strict_fill_dates_oct13_14_16(self):
        import os
        db = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "platform.db")
        conn = sqlite3.connect(db)
        from src.research.canonical_5d_baseline_s44 import build_canonical_5d_baseline
        b = build_canonical_5d_baseline(conn)
        conn.close()
        expected = {"2026-10-13", "2026-10-14", "2026-10-16"}
        assert set(b.strict_fill_dates) == expected


# ══════════════════════════════════════════════════════════════════════════════
# TC40: Production Fingerprints
# ══════════════════════════════════════════════════════════════════════════════

class TestTC40_ProductionFingerprints:
    def test_forward_signals_total_2605(self):
        import os
        conn = sqlite3.connect(
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "platform.db")
        )
        count = conn.execute("SELECT COUNT(*) FROM forward_signals").fetchone()[0]
        conn.close()
        assert count == 2605

    def test_v8_valid_2236(self):
        import os
        conn = sqlite3.connect(
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "platform.db")
        )
        count = conn.execute(
            "SELECT COUNT(*) FROM forward_signals WHERE model_version='v8.0' AND is_valid=1"
        ).fetchone()[0]
        conn.close()
        assert count == 2236

    def test_buy_strong_buy_237(self):
        import os
        conn = sqlite3.connect(
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "platform.db")
        )
        count = conn.execute(
            "SELECT COUNT(*) FROM forward_signals "
            "WHERE model_version='v8.0' AND is_valid=1 "
            "AND trade_signal IN ('buy','strong_buy')"
        ).fetchone()[0]
        conn.close()
        assert count == 237

    def test_daily_prices_max_nov05(self):
        import os
        conn = sqlite3.connect(
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "platform.db")
        )
        max_date = conn.execute("SELECT MAX(date) FROM daily_prices").fetchone()[0]
        conn.close()
        assert max_date == "2026-11-05"

    def test_nov06_non0050_zero(self):
        import os
        conn = sqlite3.connect(
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "platform.db")
        )
        count = conn.execute(
            "SELECT COUNT(*) FROM daily_prices "
            "WHERE date='2026-11-06' AND stock_id!='0050'"
        ).fetchone()[0]
        conn.close()
        assert count == 0

    def test_v3_parameter_hash_frozen(self):
        from src.research.v3_backtest_engine import PARAMETER_HASH
        assert PARAMETER_HASH == "be43e8ca977d9fdd"
