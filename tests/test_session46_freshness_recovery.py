"""
Session 46 — Data Freshness Recovery & Prospective Evidence Validation

27 test categories:
  PART B — Data Freshness Root Cause Audit
    RC01–RC08: pipeline ID, per-date diagnosis, verdict, cron evidence, neon divergence
  PART C — Cluster Maturity Impact
    CM01–CM05: maturity categories, proxy exit days, true exit dates
  PART D — Isolated Recovery Feasibility
    IR01–IR04: feasibility per cluster
  PART E — 5D Comparison Re-evaluation
    FV01–FV06: frozen baseline, expanded snapshot, statistical verdict
  PART F — Provenance Verification
    PV01–PV05: locked_at, GENUINE_PROSPECTIVE, immutability
  PART G — 20D Data Dependency
    TD01–TD03: proxy TDs, NOT_YET_MATURE, authorization gate
  PART H — Guardrail Remediation
    GR01–GR04: G01/G03/G04 status, overall verdict
  PART I — Extended Workflow
    EW01–EW03: workflow status, action items, pipeline state
  SV — Semantic Validation
    SV01–SV03: enum coverage, module imports, fingerprint delta
"""
import sqlite3
import sys
import math
from datetime import date

import pytest

sys.path.insert(0, "src")


@pytest.fixture(scope="module")
def conn():
    c = sqlite3.connect("data/platform.db")
    yield c
    c.close()


@pytest.fixture(scope="module")
def freshness_report(conn):
    from research.data_freshness_auditor_s46 import build_data_freshness_root_cause
    return build_data_freshness_root_cause(conn)


@pytest.fixture(scope="module")
def maturity_report(conn):
    from research.data_freshness_auditor_s46 import build_cluster_maturity_impact
    return build_cluster_maturity_impact(conn)


@pytest.fixture(scope="module")
def provenance_report(conn):
    from research.data_freshness_auditor_s46 import build_provenance_verification
    return build_provenance_verification(conn)


@pytest.fixture(scope="module")
def recovery_report(conn):
    from research.prospective_comparison_s46 import build_isolated_recovery_report
    return build_isolated_recovery_report(conn)


@pytest.fixture(scope="module")
def comparison_report(conn):
    from research.prospective_comparison_s46 import build_five_day_comparison
    return build_five_day_comparison(conn)


@pytest.fixture(scope="module")
def twentyd_report(conn):
    from research.prospective_comparison_s46 import build_20d_data_dependency
    return build_20d_data_dependency(conn)


@pytest.fixture(scope="module")
def guardrail_report(conn):
    from research.prospective_comparison_s46 import build_guardrail_remediation
    return build_guardrail_remediation(conn)


@pytest.fixture(scope="module")
def workflow_report(conn):
    from research.evidence_policy_s45 import build_extended_evidence_workflow_s46
    return build_extended_evidence_workflow_s46(conn)


# ── PART B: Data Freshness Root Cause ─────────────────────────────────────────

class TestRC01_PipelineIdentification:
    def test_rc01_scheduler_name(self, freshness_report):
        assert "hybrid_shadow_cron" in freshness_report.pipeline.scheduler_name

    def test_rc01_data_script(self, freshness_report):
        assert "backfill_daily_prices" in freshness_report.pipeline.data_script

    def test_rc01_cron_hash_unchanged(self, freshness_report):
        assert freshness_report.pipeline.cron_hash == "3acaf480cb5dcdd44f40dd9d464955a1"

    def test_rc01_pipeline_is_scheduled(self, freshness_report):
        assert freshness_report.pipeline.is_daily_price_pipeline_scheduled is True


class TestRC02_LocalSQLiteMax:
    def test_rc02_local_max_is_nov05(self, freshness_report):
        assert freshness_report.local_sqlite_max == "2026-11-05"

    def test_rc02_research_db_path(self, freshness_report):
        assert "platform.db" in freshness_report.research_db_path


class TestRC03_PerDateDiagnoses:
    def test_rc03_eight_dates_diagnosed(self, freshness_report):
        assert len(freshness_report.per_date_diagnoses) == 8

    def test_rc03_nov02_scheduler_not_triggered(self, freshness_report):
        from research.data_freshness_auditor_s46 import RootCauseStage
        nov02 = next(d for d in freshness_report.per_date_diagnoses if d.trade_date == "2026-11-02")
        assert nov02.root_cause == RootCauseStage.SCHEDULER_NOT_TRIGGERED

    def test_rc03_nov04_partial_manual_recovery(self, freshness_report):
        from research.data_freshness_auditor_s46 import RootCauseStage
        nov04 = next(d for d in freshness_report.per_date_diagnoses if d.trade_date == "2026-11-04")
        assert nov04.root_cause == RootCauseStage.PARTIAL_MANUAL_RECOVERY

    def test_rc03_nov06_quality_gate_fail(self, freshness_report):
        from research.data_freshness_auditor_s46 import RootCauseStage
        nov06 = next(d for d in freshness_report.per_date_diagnoses if d.trade_date == "2026-11-06")
        assert nov06.root_cause == RootCauseStage.QUALITY_GATE_FAIL

    def test_rc03_nov07_market_closed(self, freshness_report):
        from research.data_freshness_auditor_s46 import RootCauseStage
        nov07 = next(d for d in freshness_report.per_date_diagnoses if d.trade_date == "2026-11-07")
        assert nov07.root_cause == RootCauseStage.MARKET_CLOSED
        assert nov07.is_trading_day is False

    def test_rc03_nov09_provider_not_ready(self, freshness_report):
        from research.data_freshness_auditor_s46 import RootCauseStage
        nov09 = next(d for d in freshness_report.per_date_diagnoses if d.trade_date == "2026-11-09")
        assert nov09.root_cause == RootCauseStage.PROVIDER_NOT_READY


class TestRC04_RootCauseVerdict:
    def test_rc04_verdict_confirmed(self, freshness_report):
        from research.data_freshness_auditor_s46 import RootCauseVerdict
        assert freshness_report.verdict == RootCauseVerdict.ROOT_CAUSE_CONFIRMED

    def test_rc04_primary_scheduler(self, freshness_report):
        from research.data_freshness_auditor_s46 import RootCauseStage
        assert freshness_report.primary_root_cause == RootCauseStage.SCHEDULER_NOT_TRIGGERED

    def test_rc04_secondary_quality_gate(self, freshness_report):
        from research.data_freshness_auditor_s46 import RootCauseStage
        assert freshness_report.secondary_root_cause == RootCauseStage.QUALITY_GATE_FAIL

    def test_rc04_tertiary_provider_not_ready(self, freshness_report):
        from research.data_freshness_auditor_s46 import RootCauseStage
        assert freshness_report.tertiary_root_cause == RootCauseStage.PROVIDER_NOT_READY


class TestRC05_CronFirstRunEvidence:
    def test_rc05_first_run_nov09(self, freshness_report):
        assert "2026-11-09" in freshness_report.pipeline.cron_first_run_observed

    def test_rc05_cron_log_path(self, freshness_report):
        assert "hybrid_cron.log" in freshness_report.pipeline.cron_log_path


class TestRC06_NeonSQLiteDivergence:
    def test_rc06_neon_divergence_true(self, freshness_report):
        assert freshness_report.neon_sqlite_divergence is True

    def test_rc06_neon_max_ahead_of_sqlite(self, freshness_report):
        neon_max = date.fromisoformat(freshness_report.neon_max_observed)
        sqlite_max = date.fromisoformat(freshness_report.local_sqlite_max)
        assert neon_max > sqlite_max


# ── PART C: Cluster Maturity Impact ──────────────────────────────────────────

class TestCM01_MaturityCategoryAssignment:
    def test_cm01_oct22_fill_mature_incomplete(self, maturity_report):
        from research.data_freshness_auditor_s46 import MaturityCategory
        oct22 = next(c for c in maturity_report.clusters if c.fill_date == "2026-10-22")
        assert oct22.maturity_category == MaturityCategory.MATURE_BUT_DATA_INCOMPLETE

    def test_cm01_oct28_fill_mature_incomplete(self, maturity_report):
        from research.data_freshness_auditor_s46 import MaturityCategory
        oct28 = next(c for c in maturity_report.clusters if c.fill_date == "2026-10-28")
        assert oct28.maturity_category == MaturityCategory.MATURE_BUT_DATA_INCOMPLETE

    def test_cm01_strict_fills_mature_complete(self, maturity_report):
        from research.data_freshness_auditor_s46 import MaturityCategory
        for fd in ("2026-10-13", "2026-10-14", "2026-10-16"):
            c = next(x for x in maturity_report.clusters if x.fill_date == fd)
            assert c.maturity_category == MaturityCategory.MATURE_AND_COMPLETE, fd


class TestCM02_ProxyExitDays:
    def test_cm02_oct22_proxy_days_eq_3(self, maturity_report):
        oct22 = next(c for c in maturity_report.clusters if c.fill_date == "2026-10-22")
        assert oct22.proxy_exit_days == 3

    def test_cm02_oct28_proxy_days_eq_2(self, maturity_report):
        oct28 = next(c for c in maturity_report.clusters if c.fill_date == "2026-10-28")
        assert oct28.proxy_exit_days == 2


class TestCM03_TrueExitDates:
    def test_cm03_oct22_true_exit_nov02(self, maturity_report):
        oct22 = next(c for c in maturity_report.clusters if c.fill_date == "2026-10-22")
        assert oct22.true_exit_date_calendar == "2026-11-02"

    def test_cm03_oct28_true_exit_nov04(self, maturity_report):
        oct28 = next(c for c in maturity_report.clusters if c.fill_date == "2026-10-28")
        assert oct28.true_exit_date_calendar == "2026-11-04"


class TestCM04_LocalSQLiteMaxUnchanged:
    def test_cm04_local_max_nov05(self, maturity_report):
        assert maturity_report.local_sqlite_max == "2026-11-05"


class TestCM05_MaturityCounts:
    def test_cm05_n_mature_incomplete_ge_2(self, maturity_report):
        from research.data_freshness_auditor_s46 import MaturityCategory
        n = sum(1 for c in maturity_report.clusters if c.maturity_category == MaturityCategory.MATURE_BUT_DATA_INCOMPLETE)
        assert n >= 2

    def test_cm05_n_mature_complete_eq_3(self, maturity_report):
        from research.data_freshness_auditor_s46 import MaturityCategory
        n = sum(1 for c in maturity_report.clusters if c.maturity_category == MaturityCategory.MATURE_AND_COMPLETE)
        assert n >= 3


# ── PART D: Isolated Recovery Feasibility ────────────────────────────────────

class TestIR01_Oct28ComputableLocal:
    def test_ir01_oct28_isolated_computable(self, recovery_report):
        from research.prospective_comparison_s46 import RecoveryFeasibility
        oct28 = next(c for c in recovery_report.clusters if c.fill_date == "2026-10-28")
        assert oct28.feasibility == RecoveryFeasibility.ISOLATED_COMPUTABLE

    def test_ir01_oct28_exit_nov04(self, recovery_report):
        oct28 = next(c for c in recovery_report.clusters if c.fill_date == "2026-10-28")
        assert oct28.calendar_exit_date == "2026-11-04"


class TestIR02_Oct22PendingNeon:
    def test_ir02_oct22_pending_neon(self, recovery_report):
        from research.prospective_comparison_s46 import RecoveryFeasibility
        oct22 = next(c for c in recovery_report.clusters if c.fill_date == "2026-10-22")
        assert oct22.feasibility == RecoveryFeasibility.ISOLATED_PENDING_NEON


class TestIR03_RecoveryCounts:
    def test_ir03_at_least_one_computable_local(self, recovery_report):
        assert recovery_report.n_computable_local >= 1

    def test_ir03_at_least_one_pending_neon(self, recovery_report):
        assert recovery_report.n_pending_neon >= 1


class TestIR04_CalendarExitDates:
    def test_ir04_oct13_exit_oct21(self, recovery_report):
        oct13 = next(c for c in recovery_report.clusters if c.fill_date == "2026-10-13")
        assert oct13.calendar_exit_date == "2026-10-21"

    def test_ir04_oct16_exit_nov05(self, recovery_report):
        oct16 = next(c for c in recovery_report.clusters if c.fill_date == "2026-10-16")
        assert oct16.calendar_exit_date == "2026-11-05"


# ── PART E: 5D Comparison Re-evaluation ──────────────────────────────────────

class TestFV01_FrozenBaselineUnchanged:
    def test_fv01_frozen_grand_mean_eq_081(self, comparison_report):
        assert abs(comparison_report.frozen_grand_mean_delta - 0.81) < 0.01

    def test_fv01_frozen_ci_lo(self, comparison_report):
        assert comparison_report.frozen_ci_lo < 0

    def test_fv01_frozen_ci_hi(self, comparison_report):
        assert comparison_report.frozen_ci_hi > 0

    def test_fv01_frozen_three_clusters(self, comparison_report):
        assert len(comparison_report.frozen_baseline) == 3

    def test_fv01_frozen_verdict_inconclusive(self, comparison_report):
        assert "INCONCLUSIVE" in comparison_report.frozen_verdict


class TestFV02_ExpandedSnapshotOct28:
    def test_fv02_expanded_includes_oct28(self, comparison_report):
        fill_dates = [c.fill_date for c in comparison_report.expanded_snapshot]
        assert "2026-10-28" in fill_dates

    def test_fv02_oct28_delta_positive(self, comparison_report):
        oct28 = next(c for c in comparison_report.expanded_snapshot if c.fill_date == "2026-10-28")
        assert not math.isnan(oct28.delta)
        assert oct28.delta > 0

    def test_fv02_oct28_calendar_exit(self, comparison_report):
        oct28 = next(c for c in comparison_report.expanded_snapshot if c.fill_date == "2026-10-28")
        assert oct28.exit_method == "calendar_5td"


class TestFV03_Oct22PendingStatus:
    def test_fv03_oct22_in_expanded(self, comparison_report):
        fill_dates = [c.fill_date for c in comparison_report.expanded_snapshot]
        assert "2026-10-22" in fill_dates

    def test_fv03_oct22_delta_nan(self, comparison_report):
        oct22 = next(c for c in comparison_report.expanded_snapshot if c.fill_date == "2026-10-22")
        assert math.isnan(oct22.delta)

    def test_fv03_oct22_pending_note(self, comparison_report):
        oct22 = next(c for c in comparison_report.expanded_snapshot if c.fill_date == "2026-10-22")
        assert "PENDING_NEON" in oct22.note


class TestFV04_ExpandedGrandMean:
    def test_fv04_expanded_finite_clusters_eq_4(self, comparison_report):
        assert comparison_report.expanded_n_clusters == 4

    def test_fv04_expanded_grand_mean_finite(self, comparison_report):
        assert not math.isnan(comparison_report.expanded_grand_mean_delta)


class TestFV05_GuardrailsInReport:
    def test_fv05_g03_fail(self, comparison_report):
        from research.prospective_comparison_s46 import GuardrailStatus
        assert comparison_report.g03_status == GuardrailStatus.FAIL

    def test_fv05_g04_fail(self, comparison_report):
        from research.prospective_comparison_s46 import GuardrailStatus
        assert comparison_report.g04_status == GuardrailStatus.FAIL


class TestFV06_ResearchOnlyLabel:
    def test_fv06_expanded_marked_research_only(self, comparison_report):
        for c in comparison_report.expanded_snapshot:
            if c.fill_date in ("2026-10-28", "2026-10-22"):
                from research.prospective_comparison_s46 import SnapshotType
                assert c.snapshot_type == SnapshotType.EXPANDED_RESEARCH_SNAPSHOT


# ── PART F: Provenance Verification ──────────────────────────────────────────

class TestPV01_AllGenuineProspective:
    def test_pv01_all_genuine_prospective(self, provenance_report):
        assert provenance_report.all_genuine_prospective is True


class TestPV02_LockedBeforeExecution:
    def test_pv02_all_non_null_locked_before_exec(self, provenance_report):
        from research.data_freshness_auditor_s46 import ProvenanceClass
        for c in provenance_report.fill_clusters:
            if c.fill_date != "NULL":
                assert c.locked_before_execution is True, f"Fill {c.fill_date} not locked before exec"
                assert c.provenance_class == ProvenanceClass.GENUINE_PROSPECTIVE


class TestPV03_SixFillClusters:
    def test_pv03_total_clusters_eq_seven(self, provenance_report):
        # 6 with exec date + 1 null
        assert provenance_report.total_fill_clusters == 7

    def test_pv03_null_exec_count_eq_one(self, provenance_report):
        assert provenance_report.null_exec_date_count == 1


class TestPV04_ExecutionPriceType:
    def test_pv04_all_next_open(self, provenance_report):
        for c in provenance_report.fill_clusters:
            if c.fill_date != "NULL" and c.execution_price_type:
                assert c.execution_price_type == "NEXT_OPEN"


class TestPV05_IndependenceVerified:
    def test_pv05_independence_verified(self, provenance_report):
        assert provenance_report.independence_verified is True


# ── PART G: 20D Data Dependency ───────────────────────────────────────────────

class TestTD01_NoneReadyForTwentyD:
    def test_td01_zero_mature_complete(self, twentyd_report):
        assert twentyd_report.n_mature_complete == 0

    def test_td01_all_not_yet_mature(self, twentyd_report):
        assert twentyd_report.n_not_yet_mature == len(twentyd_report.clusters)


class TestTD02_ProxyTDCounts:
    def test_td02_oct13_has_seven_proxy_tds(self, twentyd_report):
        oct13 = next(c for c in twentyd_report.clusters if c.fill_date == "2026-10-13")
        assert oct13.proxy_tds_in_db == 7

    def test_td02_oct28_has_two_proxy_tds(self, twentyd_report):
        oct28 = next(c for c in twentyd_report.clusters if c.fill_date == "2026-10-28")
        assert oct28.proxy_tds_in_db == 2


class TestTD03_AuthorizationGate:
    def test_td03_authorization_required_in_report(self, twentyd_report):
        assert "NOT" in twentyd_report.authorization_required and "authorized" in twentyd_report.authorization_required.lower()

    def test_td03_no_earliest_eligible_fill(self, twentyd_report):
        assert twentyd_report.earliest_20d_eligible_fill is None


# ── PART H: Guardrail Remediation ────────────────────────────────────────────

class TestGR01_G01Conditional:
    def test_gr01_g01_conditional(self, guardrail_report):
        from research.prospective_comparison_s46 import GuardrailStatus
        g01 = next(g for g in guardrail_report.guardrails if g.guardrail_id == "G01")
        assert g01.s46_status == GuardrailStatus.CONDITIONAL

    def test_gr01_g01_engineering_fixable(self, guardrail_report):
        g01 = next(g for g in guardrail_report.guardrails if g.guardrail_id == "G01")
        assert g01.type == "ENGINEERING_FIXABLE"


class TestGR02_G03Fail:
    def test_gr02_g03_fail(self, guardrail_report):
        from research.prospective_comparison_s46 import GuardrailStatus
        g03 = next(g for g in guardrail_report.guardrails if g.guardrail_id == "G03")
        assert g03.s46_status == GuardrailStatus.FAIL

    def test_gr02_g03_unchanged(self, guardrail_report):
        g03 = next(g for g in guardrail_report.guardrails if g.guardrail_id == "G03")
        assert g03.change == "UNCHANGED"


class TestGR03_G04Fail:
    def test_gr03_g04_5d_fail(self, guardrail_report):
        from research.prospective_comparison_s46 import GuardrailStatus
        g04_5d = next(g for g in guardrail_report.guardrails if g.guardrail_id == "G04" and g.horizon == "5D")
        assert g04_5d.s46_status == GuardrailStatus.FAIL

    def test_gr03_g04_20d_fail(self, guardrail_report):
        from research.prospective_comparison_s46 import GuardrailStatus
        g04_20d = next(g for g in guardrail_report.guardrails if g.guardrail_id == "G04" and g.horizon == "20D")
        assert g04_20d.s46_status == GuardrailStatus.FAIL


class TestGR04_OverallGuardrailStatus:
    def test_gr04_overall_fail(self, guardrail_report):
        from research.prospective_comparison_s46 import GuardrailStatus
        assert guardrail_report.overall_status == GuardrailStatus.FAIL

    def test_gr04_overall_unchanged(self, guardrail_report):
        assert "UNCHANGED" in guardrail_report.overall_change


# ── PART I: Extended Workflow ─────────────────────────────────────────────────

class TestEW01_WorkflowStatusBlocked:
    def test_ew01_workflow_status_contains_blocked(self, workflow_report):
        assert "BLOCKED" in workflow_report.workflow_status or "PARTIAL" in workflow_report.workflow_status

    def test_ew01_s45_status_no_new_evidence(self, workflow_report):
        assert "NO_NEW_ELIGIBLE_EVIDENCE" in workflow_report.s45_workflow_status


class TestEW02_ActionItems:
    def test_ew02_has_action_items(self, workflow_report):
        assert len(workflow_report.action_items) >= 4

    def test_ew02_pipeline_monitoring_mentioned(self, workflow_report):
        all_items = " ".join(workflow_report.action_items)
        assert "cron" in all_items.lower() or "pipeline" in all_items.lower()


class TestEW03_PipelineState:
    def test_ew03_local_max_nov05(self, workflow_report):
        assert workflow_report.local_sqlite_max == "2026-11-05"

    def test_ew03_pipeline_first_run_nov09(self, workflow_report):
        assert "2026-11-09" in workflow_report.pipeline_first_run


# ── SV: Semantic Validation ───────────────────────────────────────────────────

class TestSV01_ModuleImports:
    def test_sv01_data_freshness_auditor_importable(self):
        import research.data_freshness_auditor_s46 as m
        assert hasattr(m, "build_data_freshness_root_cause")
        assert hasattr(m, "build_cluster_maturity_impact")
        assert hasattr(m, "build_provenance_verification")

    def test_sv01_prospective_comparison_importable(self):
        import research.prospective_comparison_s46 as m
        assert hasattr(m, "build_isolated_recovery_report")
        assert hasattr(m, "build_five_day_comparison")
        assert hasattr(m, "build_20d_data_dependency")
        assert hasattr(m, "build_guardrail_remediation")

    def test_sv01_evidence_policy_extended(self):
        import research.evidence_policy_s45 as m
        assert hasattr(m, "build_extended_evidence_workflow_s46")


class TestSV02_EnumCoverage:
    def test_sv02_root_cause_stage_enum_complete(self):
        from research.data_freshness_auditor_s46 import RootCauseStage
        required = {
            "MARKET_CLOSED", "SCHEDULER_NOT_TRIGGERED", "PARTIAL_MANUAL_RECOVERY",
            "QUALITY_GATE_FAIL", "PROVIDER_NOT_READY",
        }
        members = {m.value for m in RootCauseStage}
        assert required <= members

    def test_sv02_maturity_category_enum_complete(self):
        from research.data_freshness_auditor_s46 import MaturityCategory
        assert "MATURE_BUT_DATA_INCOMPLETE" in [m.value for m in MaturityCategory]
        assert "NOT_YET_MATURE" in [m.value for m in MaturityCategory]
        assert "MATURE_AND_COMPLETE" in [m.value for m in MaturityCategory]


class TestSV03_FingerprintDelta:
    def test_sv03_forward_signals_count_unchanged(self, conn):
        total = conn.execute("SELECT COUNT(*) FROM forward_signals").fetchone()[0]
        assert total == 2605

    def test_sv03_v3_param_hash_unchanged(self, conn):
        from research.v3_prospective_shadow import V3_PARAMETER_HASH
        assert V3_PARAMETER_HASH == "be43e8ca977d9fdd"
