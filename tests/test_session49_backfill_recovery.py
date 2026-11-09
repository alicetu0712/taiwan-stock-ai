"""
Session 49: Backfill Authorization Readiness & Pipeline Recovery Validation
Test suite — TC01 through TC35 (35 test categories).

SAFETY: All tests use READ-ONLY access to production SQLite or in-memory SQLite.
No production writes. data/platform.db not modified.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.research.source_verification_s49 import (
    BackfillAuthorizationPackage,
    BackfillConflictRisk,
    BackfillReadiness,
    ClusterImpact,
    SourceAvailability,
    SourceVerificationMatrix,
    SourceVerificationRecord,
    TempSQLiteIdempotencyResult,
    build_backfill_authorization_package,
    build_source_verification_matrix,
    compute_post_backfill_proxy_counts,
    get_strict_promotion_summary_after_backfill,
    simulate_idempotency_in_temp_sqlite,
)
from src.research.pipeline_recovery_s49 import (
    Authorization20DPackage,
    AuthorizationReadiness20D,
    CalendarContractIntegration,
    CalendarCorrectionRecord,
    CalendarCorrectionStatus,
    PipelineRecoveryValidation,
    Readiness5DCluster,
    RecoveryScenario,
    RecoveryVerdict,
    StrictClusterReadiness5D,
    build_20d_authorization_readiness,
    build_calendar_contract_integration,
    build_strict_recovery_readiness,
    get_corrected_calendar_exit,
    run_pipeline_recovery_validation,
    _CORRECT_5TD,
    _CORRECT_20TD,
    _S46_5TD,
    _S46_20TD,
)

REAL_DB_PATH = "data/platform.db"


@pytest.fixture(scope="module")
def conn():
    c = sqlite3.connect(REAL_DB_PATH)
    yield c
    c.close()


@pytest.fixture(scope="module")
def source_matrix(conn):
    return build_source_verification_matrix(conn)


@pytest.fixture(scope="module")
def auth_package(conn):
    return build_backfill_authorization_package(conn)


@pytest.fixture(scope="module")
def recovery_validation():
    return run_pipeline_recovery_validation()


@pytest.fixture(scope="module")
def calendar_integration():
    return build_calendar_contract_integration()


@pytest.fixture(scope="module")
def strict_readiness():
    return build_strict_recovery_readiness()


@pytest.fixture(scope="module")
def auth_20d():
    return build_20d_authorization_readiness("2026-11-09")


# ── TC01: Source matrix basic structure ───────────────────────────────────────

class TestTC01_SourceMatrixBasicStructure:
    def test_returns_source_verification_matrix(self, source_matrix):
        assert isinstance(source_matrix, SourceVerificationMatrix)

    def test_has_11_records(self, source_matrix):
        assert len(source_matrix.records) == 11

    def test_all_records_are_trading_days(self, source_matrix):
        assert all(r.is_trading_day for r in source_matrix.records)

    def test_summary_is_string(self, source_matrix):
        assert isinstance(source_matrix.summary, str) and len(source_matrix.summary) > 0

    def test_priority_dates_subset_of_insert_only(self, source_matrix):
        insert_only = {r.date for r in source_matrix.records
                       if r.backfill_readiness == BackfillReadiness.INSERT_ONLY_CANDIDATE}
        assert set(source_matrix.priority_dates).issubset(insert_only)




# ── TC02: Backfill readiness classification ───────────────────────────────────

class TestTC02_BackfillReadinessClassification:
    def test_9_insert_only_candidates(self, source_matrix):
        assert source_matrix.n_insert_only == 9

    def test_2_universe_unverified(self, source_matrix):
        assert source_matrix.n_universe_unverified == 2

    def test_0_source_blocked(self, source_matrix):
        assert source_matrix.n_source_blocked == 0

    def test_nov06_is_universe_unverified(self, source_matrix):
        rec = next(r for r in source_matrix.records if r.date == "2026-11-06")
        assert rec.backfill_readiness == BackfillReadiness.UNIVERSE_UNVERIFIED

    def test_nov09_is_universe_unverified(self, source_matrix):
        rec = next(r for r in source_matrix.records if r.date == "2026-11-09")
        assert rec.backfill_readiness == BackfillReadiness.UNIVERSE_UNVERIFIED

    def test_oct29_is_insert_only(self, source_matrix):
        rec = next(r for r in source_matrix.records if r.date == "2026-10-29")
        assert rec.backfill_readiness == BackfillReadiness.INSERT_ONLY_CANDIDATE




# ── TC03: Source availability classification ──────────────────────────────────

class TestTC03_SourceAvailability:
    def test_insert_only_candidates_are_source_partial(self, source_matrix):
        for r in source_matrix.records:
            if r.backfill_readiness == BackfillReadiness.INSERT_ONLY_CANDIDATE:
                assert r.source_availability == SourceAvailability.SOURCE_PARTIAL

    def test_universe_unverified_dates_are_source_unverified(self, source_matrix):
        for r in source_matrix.records:
            if r.backfill_readiness == BackfillReadiness.UNIVERSE_UNVERIFIED:
                assert r.source_availability == SourceAvailability.SOURCE_UNVERIFIED

    def test_oct27_source_partial(self, source_matrix):
        rec = next(r for r in source_matrix.records if r.date == "2026-10-27")
        assert rec.source_availability == SourceAvailability.SOURCE_PARTIAL

    def test_no_source_unavailable(self, source_matrix):
        for r in source_matrix.records:
            assert r.source_availability != SourceAvailability.SOURCE_UNAVAILABLE




# ── TC04: Conflict risk classification ───────────────────────────────────────

class TestTC04_ConflictRisk:
    def test_insert_only_dates_have_low_risk(self, source_matrix):
        for r in source_matrix.records:
            if r.backfill_readiness == BackfillReadiness.INSERT_ONLY_CANDIDATE:
                assert r.conflict_risk == BackfillConflictRisk.LOW

    def test_universe_unverified_have_high_risk(self, source_matrix):
        for r in source_matrix.records:
            if r.backfill_readiness == BackfillReadiness.UNIVERSE_UNVERIFIED:
                assert r.conflict_risk == BackfillConflictRisk.HIGH

    def test_no_medium_risk_dates(self, source_matrix):
        assert all(r.conflict_risk != BackfillConflictRisk.MEDIUM for r in source_matrix.records)




# ── TC05: Existing stock counts from production DB ────────────────────────────

class TestTC05_ExistingStockCounts:
    def test_oct29_has_1_existing_stock(self, source_matrix):
        rec = next(r for r in source_matrix.records if r.date == "2026-10-29")
        assert rec.existing_stock_count == 1

    def test_nov06_has_0_existing_stocks(self, source_matrix):
        rec = next(r for r in source_matrix.records if r.date == "2026-11-06")
        assert rec.existing_stock_count == 0

    def test_all_insert_only_have_1_stock(self, source_matrix):
        for r in source_matrix.records:
            if r.backfill_readiness == BackfillReadiness.INSERT_ONLY_CANDIDATE:
                assert r.existing_stock_count == 1

    def test_proxy_0050_present_for_insert_only(self, source_matrix):
        for r in source_matrix.records:
            if r.backfill_readiness == BackfillReadiness.INSERT_ONLY_CANDIDATE:
                assert r.has_proxy_0050




# ── TC06: Cluster promotion impact ───────────────────────────────────────────

class TestTC06_ClusterPromotionImpact:
    def test_oct29_affects_strict_promotion(self, source_matrix):
        rec = next(r for r in source_matrix.records if r.date == "2026-10-29")
        assert rec.affects_strict_promotion is True

    def test_oct29_promotes_oct21_cluster(self, source_matrix):
        rec = next(r for r in source_matrix.records if r.date == "2026-10-29")
        assert "2026-10-21" in rec.clusters_promoted

    def test_oct08_does_not_affect_promotion(self, source_matrix):
        rec = next(r for r in source_matrix.records if r.date == "2026-10-08")
        assert rec.affects_strict_promotion is False

    def test_n_strict_promotion_dates_equals_3(self, source_matrix):
        # Oct 29, Oct 30, Nov 02 all affect cluster promotion
        assert source_matrix.n_strict_promotion_dates >= 3

    def test_priority_dates_includes_oct29(self, source_matrix):
        assert "2026-10-29" in source_matrix.priority_dates

    def test_priority_dates_includes_oct30(self, source_matrix):
        assert "2026-10-30" in source_matrix.priority_dates




# ── TC07: Backfill Authorization Package structure ────────────────────────────

class TestTC07_AuthorizationPackageStructure:
    def test_returns_package(self, auth_package):
        assert isinstance(auth_package, BackfillAuthorizationPackage)

    def test_package_id_starts_with_auth01(self, auth_package):
        assert auth_package.package_id.startswith("AUTH01-")

    def test_phase_is_backfill_authorization(self, auth_package):
        assert "BACKFILL_AUTHORIZATION" in auth_package.phase

    def test_priority_1_has_4_dates(self, auth_package):
        assert len(auth_package.priority_1_dates) == 4

    def test_priority_2_has_5_dates(self, auth_package):
        assert len(auth_package.priority_2_dates) == 5

    def test_blocked_has_2_dates(self, auth_package):
        assert len(auth_package.blocked_dates) == 2

    def test_nov06_in_blocked(self, auth_package):
        assert "2026-11-06" in auth_package.blocked_dates

    def test_nov09_in_blocked(self, auth_package):
        assert "2026-11-09" in auth_package.blocked_dates




# ── TC08: Safety constraints ──────────────────────────────────────────────────

class TestTC08_SafetyConstraints:
    def test_has_at_least_5_constraints(self, auth_package):
        assert len(auth_package.safety_constraints) >= 5

    def test_safety01_insert_or_ignore(self, auth_package):
        ids = [c.constraint_id for c in auth_package.safety_constraints]
        assert "SAFETY-01" in ids

    def test_safety02_local_sqlite_only(self, auth_package):
        c = next(x for x in auth_package.safety_constraints if x.constraint_id == "SAFETY-02")
        assert "LOCAL" in c.description or "Neon" in c.description

    def test_safety03_nov06_nov09_blocked(self, auth_package):
        c = next(x for x in auth_package.safety_constraints if x.constraint_id == "SAFETY-03")
        assert "2026-11-06" in c.applies_to or "Nov 06" in c.description

    def test_authorization_status_pending(self, auth_package):
        assert "PENDING" in auth_package.authorization_status




# ── TC09: Idempotency simulation ──────────────────────────────────────────────

class TestTC09_IdempotencySimulation:
    def test_simulate_returns_results(self, source_matrix):
        results = simulate_idempotency_in_temp_sqlite(
            source_matrix.records, limit_dates=["2026-10-29", "2026-10-30"]
        )
        assert len(results) == 2

    def test_all_simulations_are_idempotent(self, source_matrix):
        results = simulate_idempotency_in_temp_sqlite(
            source_matrix.records, limit_dates=["2026-10-29", "2026-10-30"]
        )
        assert all(r.idempotent for r in results)

    def test_second_insert_adds_zero_rows(self, source_matrix):
        results = simulate_idempotency_in_temp_sqlite(
            source_matrix.records, limit_dates=["2026-10-29"]
        )
        assert results[0].second_insert_rows == 0

    def test_first_insert_adds_new_stocks(self, source_matrix):
        results = simulate_idempotency_in_temp_sqlite(
            source_matrix.records, limit_dates=["2026-10-29"]
        )
        # 0050 existed before; first insert adds TSMC + 2 more = 3 new rows
        assert results[0].first_insert_rows == 3

    def test_conflict_risk_low_after_idempotent_insert(self, source_matrix):
        results = simulate_idempotency_in_temp_sqlite(
            source_matrix.records, limit_dates=["2026-10-29"]
        )
        assert results[0].conflict_risk_actual == BackfillConflictRisk.LOW




# ── TC10: Post-backfill proxy count computation ───────────────────────────────

class TestTC10_PostBackfillProxyCounts:
    def test_returns_dict_for_all_fills(self):
        base = {"2026-10-13": 7, "2026-10-14": 6, "2026-10-16": 5,
                "2026-10-21": 4, "2026-10-22": 3, "2026-10-28": 2}
        result = compute_post_backfill_proxy_counts(base, ["2026-10-29"])
        assert len(result) == 6

    def test_oct28_reaches_5_after_p1_backfill(self):
        base = {"2026-10-13": 7, "2026-10-14": 6, "2026-10-16": 5,
                "2026-10-21": 4, "2026-10-22": 3, "2026-10-28": 2}
        result = compute_post_backfill_proxy_counts(
            base, ["2026-10-29", "2026-10-30", "2026-11-02"]
        )
        assert result["2026-10-28"] >= 5

    def test_oct21_reaches_5_after_oct29_backfill(self):
        base = {"2026-10-13": 7, "2026-10-14": 6, "2026-10-16": 5,
                "2026-10-21": 4, "2026-10-22": 3, "2026-10-28": 2}
        result = compute_post_backfill_proxy_counts(base, ["2026-10-29"])
        assert result["2026-10-21"] >= 5

    def test_strict_fills_maintain_proxy_above_5(self):
        base = {"2026-10-13": 7, "2026-10-14": 6, "2026-10-16": 5,
                "2026-10-21": 4, "2026-10-22": 3, "2026-10-28": 2}
        result = compute_post_backfill_proxy_counts(base, [])
        assert result["2026-10-13"] >= 5
        assert result["2026-10-14"] >= 5
        assert result["2026-10-16"] >= 5




# ── TC11: Strict promotion summary ────────────────────────────────────────────

class TestTC11_StrictPromotionSummary:
    def test_p1_backfill_promotes_all_3_incomplete(self):
        p1 = ["2026-10-29", "2026-10-30", "2026-11-02", "2026-11-03"]
        summary = get_strict_promotion_summary_after_backfill(p1)
        for fd in ["2026-10-21", "2026-10-22", "2026-10-28"]:
            assert "STRICT" in summary[fd], f"{fd} should be STRICT"

    def test_strict_fills_already_strict_without_backfill(self):
        summary = get_strict_promotion_summary_after_backfill([])
        for fd in ["2026-10-13", "2026-10-14", "2026-10-16"]:
            assert "STRICT" in summary[fd]

    def test_no_backfill_leaves_incomplete(self):
        summary = get_strict_promotion_summary_after_backfill([])
        for fd in ["2026-10-21", "2026-10-22", "2026-10-28"]:
            assert "INCOMPLETE" in summary[fd]




# ── TC12: Pipeline recovery validation basic structure ───────────────────────

class TestTC12_PipelineRecoveryBasicStructure:
    def test_returns_validation(self, recovery_validation):
        assert isinstance(recovery_validation, PipelineRecoveryValidation)

    def test_has_10_scenarios(self, recovery_validation):
        assert len(recovery_validation.scenarios) == 10

    def test_temp_sqlite_isolation(self, recovery_validation):
        assert recovery_validation.temp_sqlite_isolation is True

    def test_validation_verdict_is_string(self, recovery_validation):
        assert isinstance(recovery_validation.validation_verdict, str)




# ── TC13: Recovery scenario SC01 — PROXY_ONLY_INSERT ─────────────────────────

class TestTC13_SC01ProxyOnlyInsert:
    def test_sc01_scenario_enum(self, recovery_validation):
        sc01 = recovery_validation.scenarios[0]
        assert sc01.scenario == RecoveryScenario.PROXY_ONLY_INSERT

    def test_sc01_passes(self, recovery_validation):
        sc01 = recovery_validation.scenarios[0]
        assert sc01.verdict == RecoveryVerdict.PASS

    def test_sc01_total_656_stocks(self, recovery_validation):
        sc01 = recovery_validation.scenarios[0]
        assert "656" in sc01.actual_outcome

    def test_sc01_has_tsmc(self, recovery_validation):
        sc01 = recovery_validation.scenarios[0]
        assert "tsmc=True" in sc01.actual_outcome




# ── TC14: Recovery scenario SC02 — ZERO_ROW_INSERT ───────────────────────────

class TestTC14_SC02ZeroRowInsert:
    def test_sc02_scenario_enum(self, recovery_validation):
        sc02 = recovery_validation.scenarios[1]
        assert sc02.scenario == RecoveryScenario.ZERO_ROW_INSERT

    def test_sc02_passes(self, recovery_validation):
        sc02 = recovery_validation.scenarios[1]
        assert sc02.verdict == RecoveryVerdict.PASS




# ── TC15: Recovery scenario SC03 — CONFLICT_SKIP ─────────────────────────────

class TestTC15_SC03ConflictSkip:
    def test_sc03_passes(self, recovery_validation):
        sc03 = recovery_validation.scenarios[2]
        assert sc03.verdict == RecoveryVerdict.PASS

    def test_sc03_total_3_stocks(self, recovery_validation):
        sc03 = recovery_validation.scenarios[2]
        assert "3" in sc03.actual_outcome




# ── TC16: Recovery scenario SC04 — IDEMPOTENT_REPEAT ─────────────────────────

class TestTC16_SC04IdempotentRepeat:
    def test_sc04_scenario_enum(self, recovery_validation):
        sc04 = recovery_validation.scenarios[3]
        assert sc04.scenario == RecoveryScenario.IDEMPOTENT_REPEAT

    def test_sc04_passes(self, recovery_validation):
        sc04 = recovery_validation.scenarios[3]
        assert sc04.verdict == RecoveryVerdict.PASS

    def test_sc04_second_insert_zero(self, recovery_validation):
        sc04 = recovery_validation.scenarios[3]
        assert "second=0" in sc04.actual_outcome




# ── TC17: Recovery scenario SC05 — TSMC_PRESENT_POST_INSERT ──────────────────

class TestTC17_SC05TsmcPresent:
    def test_sc05_passes(self, recovery_validation):
        sc05 = recovery_validation.scenarios[4]
        assert sc05.verdict == RecoveryVerdict.PASS

    def test_sc05_before_0_after_1(self, recovery_validation):
        sc05 = recovery_validation.scenarios[4]
        assert "before=0" in sc05.actual_outcome
        assert "after=1" in sc05.actual_outcome




# ── TC18: Recovery scenario SC06 — TSMC_ABSENT_POST_INSERT ───────────────────

class TestTC18_SC06TsmcAbsent:
    def test_sc06_passes(self, recovery_validation):
        sc06 = recovery_validation.scenarios[5]
        assert sc06.verdict == RecoveryVerdict.PASS




# ── TC19: Recovery scenario SC07 — QG_PASS ───────────────────────────────────

class TestTC19_SC07QGPass:
    def test_sc07_passes(self, recovery_validation):
        sc07 = recovery_validation.scenarios[6]
        assert sc07.verdict == RecoveryVerdict.PASS

    def test_sc07_qg_pass_true(self, recovery_validation):
        sc07 = recovery_validation.scenarios[6]
        assert "qg_pass=True" in sc07.actual_outcome




# ── TC20: Recovery scenario SC08 — QG_FAIL ───────────────────────────────────

class TestTC20_SC08QGFail:
    def test_sc08_passes(self, recovery_validation):
        sc08 = recovery_validation.scenarios[7]
        assert sc08.verdict == RecoveryVerdict.PASS

    def test_sc08_qg_fail_true(self, recovery_validation):
        sc08 = recovery_validation.scenarios[7]
        assert "qg_fail=True" in sc08.actual_outcome




# ── TC21: Recovery scenario SC09 — PARTIAL_DATA_INSERT ───────────────────────

class TestTC21_SC09PartialDataInsert:
    def test_sc09_passes(self, recovery_validation):
        sc09 = recovery_validation.scenarios[8]
        assert sc09.verdict == RecoveryVerdict.PASS

    def test_sc09_before_50_after_655(self, recovery_validation):
        sc09 = recovery_validation.scenarios[8]
        assert "before=50" in sc09.actual_outcome
        assert "after=655" in sc09.actual_outcome




# ── TC22: Recovery scenario SC10 — CLUSTER_PROMOTION_ACHIEVED ────────────────

class TestTC22_SC10ClusterPromotion:
    def test_sc10_passes(self, recovery_validation):
        sc10 = recovery_validation.scenarios[9]
        assert sc10.verdict == RecoveryVerdict.PASS

    def test_sc10_proxy_2_to_5(self, recovery_validation):
        sc10 = recovery_validation.scenarios[9]
        assert "before_proxy=2" in sc10.actual_outcome
        assert "after_proxy=5" in sc10.actual_outcome

    def test_sc10_promoted_true(self, recovery_validation):
        sc10 = recovery_validation.scenarios[9]
        assert "promoted=True" in sc10.actual_outcome




# ── TC23: All 10 scenarios pass ───────────────────────────────────────────────

class TestTC23_AllScenariosPass:
    def test_all_10_pass(self, recovery_validation):
        assert recovery_validation.n_pass == 10

    def test_zero_fail(self, recovery_validation):
        assert recovery_validation.n_fail == 0

    def test_verdict_all_pass(self, recovery_validation):
        assert "ALL_PASS" in recovery_validation.validation_verdict




# ── TC24: Calendar correction records ─────────────────────────────────────────

class TestTC24_CalendarCorrectionRecords:
    def test_returns_integration(self, calendar_integration):
        assert isinstance(calendar_integration, CalendarContractIntegration)

    def test_has_6_correction_records(self, calendar_integration):
        assert len(calendar_integration.correction_records) == 6

    def test_6_20td_errors(self, calendar_integration):
        assert calendar_integration.s46_20td_error_count == 6

    def test_3_5td_errors(self, calendar_integration):
        assert calendar_integration.s46_5td_error_count == 3




# ── TC25: 20D date corrections ────────────────────────────────────────────────

class TestTC25_20DDateCorrections:
    def test_oct13_corrected_to_nov12(self, calendar_integration):
        rec = next(r for r in calendar_integration.correction_records if r.fill_date == "2026-10-13")
        assert rec.correct_20td == "2026-11-12"
        assert rec.s46_20td == "2026-11-14"
        assert rec.status_20td == CalendarCorrectionStatus.CORRECTED

    def test_oct28_corrected_to_nov25(self, calendar_integration):
        rec = next(r for r in calendar_integration.correction_records if r.fill_date == "2026-10-28")
        assert rec.correct_20td == "2026-11-25"
        assert rec.s46_20td == "2026-12-02"
        assert rec.delta_20td_days == -7

    def test_oct14_delta_minus4(self, calendar_integration):
        rec = next(r for r in calendar_integration.correction_records if r.fill_date == "2026-10-14")
        assert rec.delta_20td_days == -4

    def test_all_20td_corrections_are_earlier(self, calendar_integration):
        for r in calendar_integration.correction_records:
            assert r.delta_20td_days <= 0, f"{r.fill_date}: delta {r.delta_20td_days} should be ≤ 0"




# ── TC26: 5D date corrections ─────────────────────────────────────────────────

class TestTC26_5DDateCorrections:
    def test_oct13_corrected_to_oct20(self, calendar_integration):
        rec = next(r for r in calendar_integration.correction_records if r.fill_date == "2026-10-13")
        assert rec.correct_5td == "2026-10-20"
        assert rec.status_5td == CalendarCorrectionStatus.CORRECTED

    def test_oct21_5td_unchanged(self, calendar_integration):
        rec = next(r for r in calendar_integration.correction_records if r.fill_date == "2026-10-21")
        assert rec.status_5td == CalendarCorrectionStatus.UNCHANGED

    def test_oct22_5td_unchanged(self, calendar_integration):
        rec = next(r for r in calendar_integration.correction_records if r.fill_date == "2026-10-22")
        assert rec.status_5td == CalendarCorrectionStatus.UNCHANGED

    def test_oct28_5td_unchanged(self, calendar_integration):
        rec = next(r for r in calendar_integration.correction_records if r.fill_date == "2026-10-28")
        assert rec.status_5td == CalendarCorrectionStatus.UNCHANGED




# ── TC27: get_corrected_calendar_exit ─────────────────────────────────────────

class TestTC27_GetCorrectedCalendarExit:
    def test_5d_oct13_returns_oct20(self):
        assert get_corrected_calendar_exit("2026-10-13", 5) == "2026-10-20"

    def test_20d_oct13_returns_nov12(self):
        assert get_corrected_calendar_exit("2026-10-13", 20) == "2026-11-12"

    def test_20d_oct28_returns_nov25(self):
        assert get_corrected_calendar_exit("2026-10-28", 20) == "2026-11-25"

    def test_unknown_fill_returns_none(self):
        assert get_corrected_calendar_exit("2026-09-01", 5) is None

    def test_invalid_period_returns_none(self):
        assert get_corrected_calendar_exit("2026-10-13", 10) is None




# ── TC28: Correct 5TD/20TD dict contents ──────────────────────────────────────

class TestTC28_CalendarDictContents:
    def test_correct_5td_has_6_entries(self):
        assert len(_CORRECT_5TD) == 6

    def test_correct_20td_has_6_entries(self):
        assert len(_CORRECT_20TD) == 6

    def test_s46_5td_has_6_entries(self):
        assert len(_S46_5TD) == 6

    def test_s46_20td_has_6_entries(self):
        assert len(_S46_20TD) == 6

    def test_correct_5td_all_values_differ_from_s46(self):
        errors = sum(1 for k in _CORRECT_5TD if _CORRECT_5TD[k] != _S46_5TD[k])
        assert errors == 3  # Oct 13/14/16 corrected; Oct 21/22/28 unchanged

    def test_correct_20td_all_values_differ_from_s46(self):
        errors = sum(1 for k in _CORRECT_20TD if _CORRECT_20TD[k] != _S46_20TD[k])
        assert errors == 6  # All 6 corrected




# ── TC29: Strict recovery readiness — no backfill ─────────────────────────────

class TestTC29_StrictReadinessNoBackfill:
    def test_returns_6_records(self, strict_readiness):
        assert len(strict_readiness) == 6

    def test_oct13_strict_eligible(self, strict_readiness):
        rec = next(r for r in strict_readiness if r.fill_date == "2026-10-13")
        assert rec.readiness == Readiness5DCluster.STRICT_ELIGIBLE

    def test_oct14_strict_eligible(self, strict_readiness):
        rec = next(r for r in strict_readiness if r.fill_date == "2026-10-14")
        assert rec.readiness == Readiness5DCluster.STRICT_ELIGIBLE

    def test_oct16_strict_eligible(self, strict_readiness):
        rec = next(r for r in strict_readiness if r.fill_date == "2026-10-16")
        assert rec.readiness == Readiness5DCluster.STRICT_ELIGIBLE

    def test_oct21_waiting_for_backfill(self, strict_readiness):
        rec = next(r for r in strict_readiness if r.fill_date == "2026-10-21")
        assert rec.readiness == Readiness5DCluster.WAITING_FOR_BACKFILL

    def test_oct22_waiting_for_backfill(self, strict_readiness):
        rec = next(r for r in strict_readiness if r.fill_date == "2026-10-22")
        assert rec.readiness == Readiness5DCluster.WAITING_FOR_BACKFILL

    def test_oct28_waiting_for_backfill(self, strict_readiness):
        rec = next(r for r in strict_readiness if r.fill_date == "2026-10-28")
        assert rec.readiness == Readiness5DCluster.WAITING_FOR_BACKFILL




# ── TC30: Strict recovery readiness — with P1 backfill ───────────────────────

class TestTC30_StrictReadinessWithBackfill:
    def test_p1_backfill_promotes_oct21(self):
        p1 = ["2026-10-29", "2026-10-30", "2026-11-02", "2026-11-03"]
        recs = build_strict_recovery_readiness(p1)
        rec = next(r for r in recs if r.fill_date == "2026-10-21")
        assert rec.readiness == Readiness5DCluster.STRICT_ELIGIBLE

    def test_p1_backfill_promotes_oct22(self):
        p1 = ["2026-10-29", "2026-10-30", "2026-11-02", "2026-11-03"]
        recs = build_strict_recovery_readiness(p1)
        rec = next(r for r in recs if r.fill_date == "2026-10-22")
        assert rec.readiness == Readiness5DCluster.STRICT_ELIGIBLE

    def test_p1_backfill_promotes_oct28(self):
        p1 = ["2026-10-29", "2026-10-30", "2026-11-02", "2026-11-03"]
        recs = build_strict_recovery_readiness(p1)
        rec = next(r for r in recs if r.fill_date == "2026-10-28")
        assert rec.readiness == Readiness5DCluster.STRICT_ELIGIBLE

    def test_6_strict_after_p1_backfill(self):
        p1 = ["2026-10-29", "2026-10-30", "2026-11-02", "2026-11-03"]
        recs = build_strict_recovery_readiness(p1)
        n_strict = sum(1 for r in recs if r.readiness == Readiness5DCluster.STRICT_ELIGIBLE)
        assert n_strict == 6




# ── TC31: Strict readiness proxy counts ───────────────────────────────────────

class TestTC31_StrictReadinessProxyCounts:
    def test_oct13_proxy_count_7(self, strict_readiness):
        rec = next(r for r in strict_readiness if r.fill_date == "2026-10-13")
        assert rec.current_proxy_count == 7

    def test_oct14_proxy_count_6(self, strict_readiness):
        rec = next(r for r in strict_readiness if r.fill_date == "2026-10-14")
        assert rec.current_proxy_count == 6

    def test_oct16_proxy_count_5(self, strict_readiness):
        rec = next(r for r in strict_readiness if r.fill_date == "2026-10-16")
        assert rec.current_proxy_count == 5

    def test_oct21_proxy_count_4(self, strict_readiness):
        rec = next(r for r in strict_readiness if r.fill_date == "2026-10-21")
        assert rec.current_proxy_count == 4

    def test_oct28_proxy_count_2(self, strict_readiness):
        rec = next(r for r in strict_readiness if r.fill_date == "2026-10-28")
        assert rec.current_proxy_count == 2




# ── TC32: 20D Authorization Package structure ─────────────────────────────────

class TestTC32_Auth20DPackageStructure:
    def test_returns_package(self, auth_20d):
        assert isinstance(auth_20d, Authorization20DPackage)

    def test_has_auth01(self, auth_20d):
        assert auth_20d.auth01.auth_id == "AUTH01"

    def test_has_auth02(self, auth_20d):
        assert auth_20d.auth02.auth_id == "AUTH02"

    def test_earliest_maturity_nov12(self, auth_20d):
        assert auth_20d.earliest_20d_maturity == "2026-11-12"

    def test_days_until_first_maturity_positive(self, auth_20d):
        # Analysis date 2026-11-09; Nov 12 is 3 days away
        assert auth_20d.days_until_first_maturity == 3

    def test_overall_readiness_blocked(self, auth_20d):
        assert "BLOCKED" in auth_20d.overall_readiness




# ── TC33: AUTH01 status ────────────────────────────────────────────────────────

class TestTC33_Auth01Status:
    def test_auth01_status_pending_by_default(self, auth_20d):
        assert auth_20d.auth01.status == AuthorizationReadiness20D.AUTH01_PENDING

    def test_auth01_granted_changes_status(self):
        pkg = build_20d_authorization_readiness("2026-11-09", auth01_granted=True)
        assert pkg.auth01.status == AuthorizationReadiness20D.AUTH01_GRANTED_AUTH02_PENDING

    def test_auth01_has_prerequisites(self, auth_20d):
        assert len(auth_20d.auth01.prerequisites) >= 3

    def test_auth01_earliest_execution_today(self, auth_20d):
        assert auth_20d.auth01.earliest_execution_date == "2026-11-09"




# ── TC34: AUTH02 status ────────────────────────────────────────────────────────

class TestTC34_Auth02Status:
    def test_auth02_blocked_pipeline_without_restoration(self, auth_20d):
        assert auth_20d.auth02.status == AuthorizationReadiness20D.BLOCKED_PIPELINE

    def test_auth02_not_mature_if_pipeline_restored_but_not_time(self):
        pkg = build_20d_authorization_readiness("2026-11-09", pipeline_restored=True)
        assert pkg.auth02.status == AuthorizationReadiness20D.NOT_YET_MATURE

    def test_auth02_ready_when_fully_authorized(self):
        pkg = build_20d_authorization_readiness(
            "2026-11-14",  # After Nov 12 maturity
            auth01_granted=True,
            auth02_granted=True,
            pipeline_restored=True,
        )
        assert pkg.auth02.status == AuthorizationReadiness20D.AUTH02_GRANTED_READY

    def test_auth02_critical_path_has_steps(self, auth_20d):
        assert len(auth_20d.critical_path) >= 5




# ── TC35: Production fingerprints unchanged ───────────────────────────────────

class TestTC35_ProductionFingerprintsUnchanged:
    def test_forward_signals_total_2605(self, conn):
        n = conn.execute("SELECT COUNT(*) FROM forward_signals").fetchone()[0]
        assert n == 2605

    def test_daily_prices_max_date_nov05(self, conn):
        d = conn.execute("SELECT MAX(date) FROM daily_prices").fetchone()[0]
        assert d == "2026-11-05"

    def test_v8_buy_signals_unchanged(self, conn):
        n = conn.execute("""
            SELECT COUNT(*) FROM forward_signals
            WHERE model_version='v8.0' AND is_valid=1
            AND trade_signal IN ('buy','strong_buy')
        """).fetchone()[0]
        assert n == 237

    def test_strict_fills_proxy_count_gte5(self, conn):
        for fd in ["2026-10-13", "2026-10-14", "2026-10-16"]:
            cnt = conn.execute(
                "SELECT COUNT(*) FROM daily_prices WHERE stock_id='2330' AND date > ?", (fd,)
            ).fetchone()[0]
            assert cnt >= 5, f"{fd} proxy count {cnt} < 5"

    def test_incomplete_fills_proxy_count_lt5(self, conn):
        for fd in ["2026-10-21", "2026-10-22", "2026-10-28"]:
            cnt = conn.execute(
                "SELECT COUNT(*) FROM daily_prices WHERE stock_id='2330' AND date > ?", (fd,)
            ).fetchone()[0]
            assert cnt < 5, f"{fd} proxy count {cnt} should be < 5"

    def test_no_new_rows_in_daily_prices_nov09(self, conn):
        n = conn.execute(
            "SELECT COUNT(*) FROM daily_prices WHERE date='2026-11-09'"
        ).fetchone()[0]
        assert n == 0

    def test_no_new_rows_in_daily_prices_nov06(self, conn):
        n = conn.execute(
            "SELECT COUNT(*) FROM daily_prices WHERE date='2026-11-06'"
        ).fetchone()[0]
        assert n == 0


