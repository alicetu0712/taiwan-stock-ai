"""
tests/test_session51_pipeline_root_cause.py — S51 Test Suite

PARTS B, C, D, E, F, G — Pipeline Root Cause, Calendar Audit,
Prospective Evidence Protocol, Collection Plan, Recorder, Auth01 Readiness.

40 test classes (TC01–TC40), regression > 3203 total.

Safety: all DB access is read-only; ProspectiveRecorder uses temp SQLite only.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from datetime import date, datetime, timezone
from typing import List

import pytest

# ── Module imports ─────────────────────────────────────────────────────────────

from src.research.pipeline_root_cause_s51 import (
    CalendarCallSite,
    CalendarCallSiteStatus,
    EvidenceLevel,
    PipelineRootCauseEvidenceMatrix,
    PipelineStage,
    PipelineTier,
    StageEvidence,
    TierDiagnosis,
    build_pipeline_root_cause_matrix,
    get_shadow_run_summary,
    get_tier_stock_counts,
)
from src.research.prospective_recorder_s51 import (
    Auth01ReadinessVerdict,
    BackfillAuthorizationReadiness,
    BackfillReadinessRecord,
    DecisionClassification,
    FillClusterEvidence,
    ImmutableDecisionPayload,
    ProspectiveClusterCollectionPlan,
    ProspectiveCollectionVerdict,
    ProspectiveRecorderPrototype,
    RULE_FREEZE_DATE,
    V3_PARAMETER_HASH,
    build_backfill_authorization_readiness,
    build_fill_cluster_evidence,
    build_prospective_collection_plan,
    classify_fill_cluster,
)

# ── Fixtures ───────────────────────────────────────────────────────────────────

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "platform.db",
)


@pytest.fixture(scope="module")
def conn():
    c = sqlite3.connect(DB_PATH)
    yield c
    c.close()


@pytest.fixture(scope="module")
def matrix():
    return build_pipeline_root_cause_matrix(DB_PATH)


@pytest.fixture(scope="module")
def fill_cluster_evidence():
    return build_fill_cluster_evidence(DB_PATH)


@pytest.fixture(scope="module")
def collection_plan():
    return build_prospective_collection_plan()


@pytest.fixture(scope="module")
def auth_readiness():
    return build_backfill_authorization_readiness(DB_PATH)


@pytest.fixture
def recorder():
    with ProspectiveRecorderPrototype() as r:
        yield r


# ── PART B: Pipeline Root Cause Evidence Matrix ───────────────────────────────

class TestTC01_MatrixStructure:
    def test_matrix_has_five_tiers(self, matrix):
        assert len(matrix.tiers) == 5

    def test_all_tier_values_present(self, matrix):
        tier_names = {t.tier for t in matrix.tiers}
        expected = {
            PipelineTier.TIER_655_FILL,
            PipelineTier.TIER_1_PROXY,
            PipelineTier.TIER_6957_BACKFILL,
            PipelineTier.BLOCKED_QG,
            PipelineTier.BLOCKED_STALE_DATA,
        }
        assert tier_names == expected

    def test_every_tier_has_ten_stages(self, matrix):
        for td in matrix.tiers:
            assert len(td.stages) == 10, f"Tier {td.tier} has {len(td.stages)} stages"

    def test_all_stage_types_covered(self, matrix):
        expected_stages = set(PipelineStage)
        for td in matrix.tiers:
            covered = {s.stage for s in td.stages}
            assert covered == expected_stages, f"Tier {td.tier} missing stages"

    def test_session_label(self, matrix):
        assert matrix.session == "S51"


class TestTC02_FingerprintVerification:
    def test_fingerprint_verified(self, matrix):
        assert matrix.fingerprint_verified is True

    def test_analysis_date(self, matrix):
        assert matrix.analysis_date == "2026-11-10"

    def test_get_tier_helper(self, matrix):
        td = matrix.get_tier(PipelineTier.TIER_655_FILL)
        assert td is not None
        assert td.tier == PipelineTier.TIER_655_FILL


class TestTC03_Tier655Fill:
    def test_dates(self, matrix):
        td = matrix.get_tier(PipelineTier.TIER_655_FILL)
        assert len(td.dates) == 6
        assert "2026-10-13" in td.dates
        assert "2026-10-28" in td.dates

    def test_stock_count(self, matrix):
        td = matrix.get_tier(PipelineTier.TIER_655_FILL)
        assert td.stock_count == 655

    def test_trigger_source(self, matrix):
        td = matrix.get_tier(PipelineTier.TIER_655_FILL)
        assert td.trigger_source == "manual"

    def test_provider_response_directly_confirmed(self, matrix):
        td = matrix.get_tier(PipelineTier.TIER_655_FILL)
        s = td.get_stage(PipelineStage.PROVIDER_RESPONSE)
        assert s.level == EvidenceLevel.DIRECTLY_CONFIRMED

    def test_provider_response_root_cause_contains_bulk(self, matrix):
        td = matrix.get_tier(PipelineTier.TIER_655_FILL)
        s = td.get_stage(PipelineStage.PROVIDER_RESPONSE)
        assert "TWSE_BULK" in s.root_cause

    def test_downstream_not_applicable(self, matrix):
        td = matrix.get_tier(PipelineTier.TIER_655_FILL)
        s = td.get_stage(PipelineStage.DOWNSTREAM_RESEARCH)
        assert s.level == EvidenceLevel.NOT_APPLICABLE


class TestTC04_Tier1Proxy:
    def test_dates(self, matrix):
        td = matrix.get_tier(PipelineTier.TIER_1_PROXY)
        assert len(td.dates) == 4
        assert "2026-10-29" in td.dates
        assert "2026-11-03" in td.dates

    def test_stock_count_is_one(self, matrix):
        td = matrix.get_tier(PipelineTier.TIER_1_PROXY)
        assert td.stock_count == 1

    def test_trigger_source_is_recover_script(self, matrix):
        td = matrix.get_tier(PipelineTier.TIER_1_PROXY)
        assert "recover" in td.trigger_source

    def test_provider_response_insufficient(self, matrix):
        td = matrix.get_tier(PipelineTier.TIER_1_PROXY)
        s = td.get_stage(PipelineStage.PROVIDER_RESPONSE)
        assert s.level == EvidenceLevel.INSUFFICIENT_EVIDENCE

    def test_persistence_directly_confirmed(self, matrix):
        td = matrix.get_tier(PipelineTier.TIER_1_PROXY)
        s = td.get_stage(PipelineStage.DATABASE_PERSISTENCE)
        assert s.level == EvidenceLevel.DIRECTLY_CONFIRMED

    def test_persistence_mentions_rowids(self, matrix):
        td = matrix.get_tier(PipelineTier.TIER_1_PROXY)
        s = td.get_stage(PipelineStage.DATABASE_PERSISTENCE)
        assert "rowid" in s.summary.lower() or "rowid" in (s.source or "").lower()

    def test_coverage_qg_root_cause_mentions_silent_failure(self, matrix):
        td = matrix.get_tier(PipelineTier.TIER_1_PROXY)
        s = td.get_stage(PipelineStage.COVERAGE_QUALITY_GATE)
        assert "SILENT_FAILURE" in (s.root_cause or "")


class TestTC05_Tier6957Backfill:
    def test_dates(self, matrix):
        td = matrix.get_tier(PipelineTier.TIER_6957_BACKFILL)
        assert "2026-11-04" in td.dates
        assert "2026-11-05" in td.dates

    def test_stock_count(self, matrix):
        td = matrix.get_tier(PipelineTier.TIER_6957_BACKFILL)
        assert td.stock_count == 6957

    def test_all_stages_non_na(self, matrix):
        td = matrix.get_tier(PipelineTier.TIER_6957_BACKFILL)
        na_count = sum(1 for s in td.stages if s.level == EvidenceLevel.NOT_APPLICABLE)
        # only DOWNSTREAM_RESEARCH might be NA but here it has content
        assert na_count == 0

    def test_downstream_mentions_retrospective(self, matrix):
        td = matrix.get_tier(PipelineTier.TIER_6957_BACKFILL)
        s = td.get_stage(PipelineStage.DOWNSTREAM_RESEARCH)
        assert "RETROSPECTIVE" in s.summary

    def test_completion_mentions_run_ids(self, matrix):
        td = matrix.get_tier(PipelineTier.TIER_6957_BACKFILL)
        s = td.get_stage(PipelineStage.COMPLETION_MARKER)
        assert "fc2b4b0f" in s.summary


class TestTC06_BlockedQG:
    def test_stock_count_zero(self, matrix):
        td = matrix.get_tier(PipelineTier.BLOCKED_QG)
        assert td.stock_count == 0

    def test_trigger_source_cron(self, matrix):
        td = matrix.get_tier(PipelineTier.BLOCKED_QG)
        assert td.trigger_source == "cron"

    def test_qg_stage_directly_confirmed(self, matrix):
        td = matrix.get_tier(PipelineTier.BLOCKED_QG)
        s = td.get_stage(PipelineStage.COVERAGE_QUALITY_GATE)
        assert s.level == EvidenceLevel.DIRECTLY_CONFIRMED

    def test_qg_root_cause_mentions_qg(self, matrix):
        td = matrix.get_tier(PipelineTier.BLOCKED_QG)
        s = td.get_stage(PipelineStage.COVERAGE_QUALITY_GATE)
        assert "QUALITY_GATE" in s.root_cause

    def test_security_mapping_hypothesis_only(self, matrix):
        td = matrix.get_tier(PipelineTier.BLOCKED_QG)
        s = td.get_stage(PipelineStage.SECURITY_MAPPING)
        assert s.level == EvidenceLevel.HYPOTHESIS_ONLY

    def test_provider_response_strongly_supported(self, matrix):
        td = matrix.get_tier(PipelineTier.BLOCKED_QG)
        s = td.get_stage(PipelineStage.PROVIDER_RESPONSE)
        assert s.level == EvidenceLevel.STRONGLY_SUPPORTED


class TestTC07_BlockedStaleData:
    def test_stock_count_zero(self, matrix):
        td = matrix.get_tier(PipelineTier.BLOCKED_STALE_DATA)
        assert td.stock_count == 0

    def test_scheduler_directly_confirmed(self, matrix):
        td = matrix.get_tier(PipelineTier.BLOCKED_STALE_DATA)
        s = td.get_stage(PipelineStage.SCHEDULER_TRIGGER)
        assert s.level == EvidenceLevel.DIRECTLY_CONFIRMED

    def test_provider_response_directly_confirmed(self, matrix):
        td = matrix.get_tier(PipelineTier.BLOCKED_STALE_DATA)
        s = td.get_stage(PipelineStage.PROVIDER_RESPONSE)
        assert s.level == EvidenceLevel.DIRECTLY_CONFIRMED

    def test_provider_response_mentions_api_date(self, matrix):
        td = matrix.get_tier(PipelineTier.BLOCKED_STALE_DATA)
        s = td.get_stage(PipelineStage.PROVIDER_RESPONSE)
        assert "api_date=2026-11-06" in s.summary

    def test_security_mapping_not_applicable(self, matrix):
        td = matrix.get_tier(PipelineTier.BLOCKED_STALE_DATA)
        s = td.get_stage(PipelineStage.SECURITY_MAPPING)
        assert s.level == EvidenceLevel.NOT_APPLICABLE

    def test_completion_marker_blocked(self, matrix):
        td = matrix.get_tier(PipelineTier.BLOCKED_STALE_DATA)
        s = td.get_stage(PipelineStage.COMPLETION_MARKER)
        assert "BLOCKED_STALE_DATA" in s.summary


class TestTC08_EvidenceLevelCounts:
    def test_directly_confirmed_majority(self, matrix):
        dc = matrix.count_by_evidence(EvidenceLevel.DIRECTLY_CONFIRMED)
        total = sum(len(td.stages) for td in matrix.tiers)
        assert dc / total >= 0.4  # at least 40% directly confirmed

    def test_no_uncategorized_stages(self, matrix):
        for td in matrix.tiers:
            for s in td.stages:
                assert s.level in EvidenceLevel

    def test_insufficient_evidence_limited(self, matrix):
        ie = matrix.count_by_evidence(EvidenceLevel.INSUFFICIENT_EVIDENCE)
        assert ie <= 10  # TIER_1_PROXY has the most unknowns


class TestTC09_TierDiagnosisVerdicts:
    def test_all_tiers_have_verdicts(self, matrix):
        for td in matrix.tiers:
            assert len(td.tier_verdict) > 20

    def test_tier_655_verdict_mentions_yfinance(self, matrix):
        td = matrix.get_tier(PipelineTier.TIER_655_FILL)
        assert "yfinance" in td.tier_verdict

    def test_tier_1_proxy_verdict_mentions_recover(self, matrix):
        td = matrix.get_tier(PipelineTier.TIER_1_PROXY)
        assert "recover" in td.tier_verdict.lower()

    def test_tier_stale_verdict_mentions_twse_bulk(self, matrix):
        td = matrix.get_tier(PipelineTier.BLOCKED_STALE_DATA)
        assert "TWSE_BULK_STALE" in td.tier_verdict


class TestTC10_RealDBVerification:
    def test_tier_stock_counts(self):
        counts = get_tier_stock_counts(DB_PATH)
        assert counts.get("TIER_655_FILL", 0) >= 400  # ~654 non-0050 for Oct 13
        assert counts.get("TIER_1_PROXY", 0) == 0     # 0050 not counted (stock_id!='0050')
        assert counts.get("TIER_6957_BACKFILL", 0) >= 5000
        assert counts.get("BLOCKED_QG", 0) == 0
        assert counts.get("BLOCKED_STALE_DATA", 0) == 0

    def test_shadow_run_summary_has_nov04_entries(self):
        runs = get_shadow_run_summary(DB_PATH)
        trade_dates = [r["trade_date"] for r in runs]
        assert "2026-11-04" in trade_dates

    def test_shadow_run_summary_has_success_status(self):
        runs = get_shadow_run_summary(DB_PATH)
        statuses = {r["status"] for r in runs}
        assert "SUCCESS" in statuses

    def test_shadow_run_nov04_inserted_21(self):
        runs = get_shadow_run_summary(DB_PATH)
        nov04_success = [r for r in runs if r["trade_date"] == "2026-11-04" and r["status"] == "SUCCESS"]
        total_inserted = sum(r.get("inserted_count", 0) for r in nov04_success)
        assert total_inserted == 21


# ── PART C: Calendar Call-site Audit ─────────────────────────────────────────

class TestTC11_CalendarAuditStructure:
    def test_audit_has_entries(self, matrix):
        assert len(matrix.calendar_call_sites) >= 6

    def test_all_statuses_are_valid_enum(self, matrix):
        for cs in matrix.calendar_call_sites:
            assert cs.status in CalendarCallSiteStatus

    def test_s46_is_legacy_frozen(self, matrix):
        s46_sites = [cs for cs in matrix.calendar_call_sites
                     if "s46" in cs.file_path or "prospective_comparison_s46" in cs.file_path]
        assert len(s46_sites) >= 1
        for cs in s46_sites:
            assert cs.status == CalendarCallSiteStatus.LEGACY_FROZEN
            assert cs.is_frozen_module is True


class TestTC12_CalendarSSOTCompliance:
    def test_s50_is_ssot_compliant(self, matrix):
        s50_sites = [cs for cs in matrix.calendar_call_sites
                     if "s50" in cs.file_path or "calendar_contract_s50" in cs.file_path]
        assert len(s50_sites) >= 1
        ssot = [cs for cs in s50_sites if cs.status == CalendarCallSiteStatus.SSOT_COMPLIANT]
        assert len(ssot) >= 1

    def test_no_legacy_active_bugs(self, matrix):
        bugs = [cs for cs in matrix.calendar_call_sites
                if cs.status == CalendarCallSiteStatus.LEGACY_ACTIVE_BUG]
        assert len(bugs) == 0, f"Found LEGACY_ACTIVE_BUG sites: {bugs}"

    def test_s48_s49_are_frozen(self, matrix):
        frozen = [cs for cs in matrix.calendar_call_sites if cs.is_frozen_module]
        paths = {cs.file_path for cs in frozen}
        # S46, S48, S49 should all be in frozen set
        frozen_markers = ["s46", "s48", "s49"]
        for marker in frozen_markers:
            assert any(marker in p for p in paths), f"No frozen site for {marker}"


class TestTC13_CalendarSSOTFunctionality:
    def test_s50_get_corrected_exit_5td(self):
        from src.research.calendar_contract_s50 import get_corrected_exit
        assert get_corrected_exit("2026-10-13", "5TD") == "2026-10-20"
        assert get_corrected_exit("2026-10-14", "5TD") == "2026-10-21"
        assert get_corrected_exit("2026-10-16", "5TD") == "2026-10-27"
        assert get_corrected_exit("2026-10-21", "5TD") == "2026-10-30"
        assert get_corrected_exit("2026-10-22", "5TD") == "2026-11-02"
        assert get_corrected_exit("2026-10-28", "5TD") == "2026-11-04"

    def test_s50_get_corrected_exit_20td(self):
        from src.research.calendar_contract_s50 import get_corrected_exit
        assert get_corrected_exit("2026-10-13", "20TD") == "2026-11-12"
        assert get_corrected_exit("2026-10-28", "20TD") == "2026-11-25"

    def test_s50_get_corrected_exit_unknown(self):
        from src.research.calendar_contract_s50 import get_corrected_exit
        assert get_corrected_exit("2026-09-01", "5TD") is None
        assert get_corrected_exit("2026-10-13", "10TD") is None


class TestTC14_S46Isolation:
    """Verify S46 erroneous dates are not accidentally used by S51 code."""

    def test_s51_root_cause_does_not_import_s46(self):
        import inspect
        import src.research.pipeline_root_cause_s51 as m51
        src_text = inspect.getsource(m51)
        # Must not IMPORT from s46; docstring mentions are allowed
        assert "from src.research.prospective_comparison_s46" not in src_text
        assert "import prospective_comparison_s46" not in src_text
        # Must not use the erroneous dicts
        assert "_CALENDAR_5TD[" not in src_text
        assert "_CALENDAR_20TD[" not in src_text

    def test_s51_recorder_does_not_import_s46(self):
        import inspect
        import src.research.prospective_recorder_s51 as m51r
        src_text = inspect.getsource(m51r)
        assert "from src.research.prospective_comparison_s46" not in src_text
        assert "import prospective_comparison_s46" not in src_text
        assert "_CALENDAR_5TD[" not in src_text
        assert "_CALENDAR_20TD[" not in src_text

    def test_s46_erroneous_5td_still_wrong(self):
        # Verify S46 erroneous dates are still different from corrected values
        # (do NOT fix them — S46 is frozen research evidence)
        from src.research.prospective_comparison_s46 import _CALENDAR_5TD
        from src.research.calendar_contract_s50 import get_corrected_exit
        # S46 had Oct 13 → Oct 21 (wrong; correct is Oct 20)
        assert _CALENDAR_5TD.get("2026-10-13") != get_corrected_exit("2026-10-13", "5TD")


class TestTC15_CalendarSSOTIntegrity:
    def test_ssot_fingerprint_stable(self):
        from src.research.calendar_contract_s50 import build_research_trading_calendar_contract
        contract = build_research_trading_calendar_contract()
        fp = contract.fingerprint
        assert len(fp) >= 8
        # Fingerprint must be deterministic across calls
        contract2 = build_research_trading_calendar_contract()
        assert contract.fingerprint == contract2.fingerprint


# ── PART D: Prospective Evidence Protocol ────────────────────────────────────

class TestTC16_DecisionClassificationEnum:
    def test_all_four_values_exist(self):
        expected = {
            "V3_DECISION_PROSPECTIVE",
            "BASE_SIGNAL_PROSPECTIVE",
            "RETROSPECTIVE_RECONSTRUCTION",
            "PROVENANCE_UNVERIFIED",
        }
        actual = {v.value for v in DecisionClassification}
        assert actual == expected

    def test_rule_freeze_date_is_nov05(self):
        assert RULE_FREEZE_DATE == date(2026, 11, 5)

    def test_v3_parameter_hash_frozen(self):
        assert V3_PARAMETER_HASH == "be43e8ca977d9fdd"


class TestTC17_ClassifyFillClusterLogic:
    def test_locked_before_prefreeze_returns_base_signal(self):
        cls, reason = classify_fill_cluster(
            execution_date="2026-10-13",
            first_locked_at="2026-10-12 06:42:52",
            signal_count=348,
            v3_decision_frozen=False,
        )
        assert cls == DecisionClassification.BASE_SIGNAL_PROSPECTIVE
        assert "V3" in reason

    def test_no_signals_returns_provenance_unverified(self):
        cls, reason = classify_fill_cluster(
            execution_date="2026-10-13",
            first_locked_at=None,
            signal_count=0,
        )
        assert cls == DecisionClassification.PROVENANCE_UNVERIFIED

    def test_null_locked_returns_provenance_unverified(self):
        cls, reason = classify_fill_cluster(
            execution_date="2026-10-13",
            first_locked_at=None,
            signal_count=5,
        )
        assert cls == DecisionClassification.PROVENANCE_UNVERIFIED

    def test_locked_after_execution_returns_retrospective(self):
        cls, _ = classify_fill_cluster(
            execution_date="2026-10-13",
            first_locked_at="2026-10-14 10:00:00",
            signal_count=10,
        )
        assert cls == DecisionClassification.RETROSPECTIVE_RECONSTRUCTION

    def test_v3_frozen_prefreeze_returns_v3_prospective(self):
        cls, _ = classify_fill_cluster(
            execution_date="2026-10-13",
            first_locked_at="2026-10-12 00:00:00",
            signal_count=10,
            v3_decision_frozen=True,
        )
        assert cls == DecisionClassification.V3_DECISION_PROSPECTIVE

    def test_v3_frozen_postfreeze_returns_v3_prospective(self):
        cls, _ = classify_fill_cluster(
            execution_date="2026-11-10",
            first_locked_at="2026-11-09 00:00:00",
            signal_count=10,
            v3_decision_frozen=True,
        )
        assert cls == DecisionClassification.V3_DECISION_PROSPECTIVE

    def test_no_v3_postfreeze_returns_base_signal(self):
        cls, _ = classify_fill_cluster(
            execution_date="2026-11-10",
            first_locked_at="2026-11-09 00:00:00",
            signal_count=10,
            v3_decision_frozen=False,
        )
        assert cls == DecisionClassification.BASE_SIGNAL_PROSPECTIVE


class TestTC18_FillClusterEvidenceFromDB:
    def test_returns_six_clusters(self, fill_cluster_evidence):
        assert len(fill_cluster_evidence) == 6

    def test_all_execution_dates_correct(self, fill_cluster_evidence):
        expected = {
            "2026-10-13", "2026-10-14", "2026-10-16",
            "2026-10-21", "2026-10-22", "2026-10-28",
        }
        actual = {c.execution_date for c in fill_cluster_evidence}
        assert actual == expected

    def test_all_locked_before_execution(self, fill_cluster_evidence):
        for c in fill_cluster_evidence:
            assert c.locked_before_execution, (
                f"{c.execution_date}: locked_at={c.first_locked_at} "
                "should be before execution_date"
            )

    def test_all_base_signal_prospective(self, fill_cluster_evidence):
        for c in fill_cluster_evidence:
            assert c.classification == DecisionClassification.BASE_SIGNAL_PROSPECTIVE, (
                f"{c.execution_date}: expected BASE_SIGNAL_PROSPECTIVE, got {c.classification}"
            )

    def test_no_v3_frozen(self, fill_cluster_evidence):
        for c in fill_cluster_evidence:
            assert c.v3_decision_frozen is False

    def test_signal_counts_positive(self, fill_cluster_evidence):
        for c in fill_cluster_evidence:
            assert c.signal_count_v8 > 0, f"{c.execution_date}: zero signals"

    def test_oct13_locked_at_matches_known(self, fill_cluster_evidence):
        oct13 = next(c for c in fill_cluster_evidence if c.execution_date == "2026-10-13")
        assert oct13.first_locked_at is not None
        assert oct13.first_locked_at[:10] == "2026-10-12"


class TestTC19_ProspectiveClassificationRationale:
    """Verify that the classification correctly reflects V3 non-activation."""

    def test_base_signal_means_v3_not_frozen(self, fill_cluster_evidence):
        for c in fill_cluster_evidence:
            if c.classification == DecisionClassification.BASE_SIGNAL_PROSPECTIVE:
                assert "V3" in c.classification_reason or "v3" in c.classification_reason.lower()

    def test_base_signal_means_locked_before_exec(self, fill_cluster_evidence):
        for c in fill_cluster_evidence:
            if c.classification == DecisionClassification.BASE_SIGNAL_PROSPECTIVE:
                assert c.locked_before_execution

    def test_all_prefreeze_dates(self, fill_cluster_evidence):
        for c in fill_cluster_evidence:
            exec_d = date.fromisoformat(c.execution_date)
            assert exec_d < RULE_FREEZE_DATE, (
                f"{c.execution_date} should be before RULE_FREEZE_DATE"
            )


class TestTC20_HybridForwardDecisionClassification:
    """Hybrid forward decisions (Nov 04) are RETROSPECTIVE_RECONSTRUCTION."""

    def test_all_decisions_retrospective(self, conn):
        rows = conn.execute(
            "SELECT capture_classification, COUNT(*) "
            "FROM hybrid_forward_decision GROUP BY capture_classification"
        ).fetchall()
        classifications = {r[0]: r[1] for r in rows}
        assert "RETROSPECTIVE_RECONSTRUCTION" in classifications
        total = sum(classifications.values())
        retro_count = classifications.get("RETROSPECTIVE_RECONSTRUCTION", 0)
        assert retro_count == total  # all decisions are RETROSPECTIVE

    def test_all_decisions_for_nov04(self, conn):
        rows = conn.execute(
            "SELECT DISTINCT trade_date FROM hybrid_forward_decision"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "2026-11-04"

    def test_nov04_before_rule_freeze_date(self):
        assert date(2026, 11, 4) < RULE_FREEZE_DATE

    def test_no_v3_prospective_decisions_exist(self, conn):
        rows = conn.execute(
            "SELECT COUNT(*) FROM hybrid_forward_decision "
            "WHERE capture_classification='V3_DECISION_PROSPECTIVE'"
        ).fetchone()
        assert rows[0] == 0


# ── PART E: Cluster Collection Protocol ──────────────────────────────────────

class TestTC21_CollectionPlanStructure:
    def test_target_n_is_ten(self, collection_plan):
        assert collection_plan.target_n == 10

    def test_min_td_gap_is_six(self, collection_plan):
        assert collection_plan.min_td_gap == 6

    def test_rule_freeze_date_embedded(self, collection_plan):
        assert collection_plan.rule_freeze_date == "2026-11-05"

    def test_v3_hash_frozen(self, collection_plan):
        assert collection_plan.v3_parameter_hash == "be43e8ca977d9fdd"

    def test_model_version_frozen(self, collection_plan):
        assert collection_plan.model_version == "v8.0"


class TestTC22_CollectionPlanCurrentState:
    def test_zero_v3_prospective(self, collection_plan):
        assert collection_plan.current_v3_prospective == 0

    def test_zero_base_signal_independent(self, collection_plan):
        # None of the existing clusters have ≥6 TD spacing from each other
        assert collection_plan.current_base_signal == 0

    def test_g03_fail(self, collection_plan):
        assert collection_plan.g03_status == "FAIL"

    def test_g04_fail(self, collection_plan):
        assert collection_plan.g04_status == "FAIL"

    def test_verdict_framework_ready(self, collection_plan):
        assert "FRAMEWORK_READY" in collection_plan.collection_verdict


class TestTC23_CollectionPlanCalculations:
    def test_clusters_needed_is_ten(self, collection_plan):
        assert collection_plan.clusters_needed() == 10

    def test_estimated_weeks_at_6td(self, collection_plan):
        # 10 clusters with 6 TD gap each = 54 TD = ~10.8 weeks
        weeks = collection_plan.estimated_weeks_remaining()
        assert 10.0 <= weeks <= 12.0

    def test_planned_clusters_has_pipeline_note(self, collection_plan):
        assert len(collection_plan.planned_clusters) >= 1
        note = collection_plan.planned_clusters[0].notes
        assert "pipeline" in note.lower() or "auth01" in note.lower()


class TestTC24_SpacingConstraintLogic:
    def test_6td_gap_scenario_exists(self):
        from src.research.calendar_contract_s50 import build_g04_dependence_study
        g04 = build_g04_dependence_study()
        s6 = next((s for s in g04.weekly_spacing_scenarios if s.min_td_gap == 6), None)
        assert s6 is not None, "Expected a ≥6 TD scenario"

    def test_5td_gap_still_fails_g04(self):
        from src.research.calendar_contract_s50 import build_g04_dependence_study
        g04 = build_g04_dependence_study()
        s5 = next((s for s in g04.weekly_spacing_scenarios if s.min_td_gap == 5), None)
        if s5 is not None:
            # Oct 21/Oct 28 = 40% overlap → still fails
            assert s5.g04_verdict.value in ("G04_FAIL", "FAIL")


class TestTC25_ProspectiveReadinessOverall:
    def test_activation_still_blocked(self):
        # G03/G04 both fail → activation blocked
        from src.research.calendar_contract_s50 import build_strict5d_eligibility_matrix
        em = build_strict5d_eligibility_matrix()
        assert not em.g03_now

    def test_no_v3_decision_exists_in_db(self, conn):
        # forward_signals has no v3-specific column confirming V3 activation
        rows = conn.execute(
            "SELECT COUNT(*) FROM hybrid_forward_decision"
        ).fetchone()
        total = rows[0]
        # All 21 are RETROSPECTIVE_RECONSTRUCTION — consistent with non-activation
        assert total == 21


# ── PART F: Prospective Recorder Prototype ───────────────────────────────────

class TestTC26_RecorderSafetyGuard:
    def test_refuses_production_db_path(self):
        with pytest.raises(ValueError, match="safety"):
            ProspectiveRecorderPrototype(db_path="/tmp/platform.db")

    def test_refuses_path_with_platform_db_name(self):
        with pytest.raises(ValueError):
            ProspectiveRecorderPrototype(db_path="/some/path/platform.db")

    def test_accepts_temp_path(self, recorder):
        assert recorder.count() == 0


class TestTC27_RecorderAppendOnly:
    def _make_payload(self, fill_date: str, signal_id: int) -> ImmutableDecisionPayload:
        return ImmutableDecisionPayload(
            fill_date=fill_date,
            signal_id=signal_id,
            stock_id="2330",
            model_version="v8.0",
            locked_at="2026-10-12 06:47:11",
            trade_signal="buy",
            v3_decision_snapshot=None,
            classification=DecisionClassification.BASE_SIGNAL_PROSPECTIVE,
            registered_at="2026-11-10T00:00:00Z",
        )

    def test_insert_increases_count(self, recorder):
        p = self._make_payload("2026-10-13", 1001)
        inserted = recorder.register(p)
        assert inserted is True
        assert recorder.count() == 1

    def test_duplicate_insert_is_idempotent(self):
        with ProspectiveRecorderPrototype() as r:
            p = self._make_payload("2026-10-13", 1002)
            first = r.register(p)
            second = r.register(p)
            assert first is True
            assert second is False
            assert r.count() == 1

    def test_different_fill_date_allowed(self):
        with ProspectiveRecorderPrototype() as r:
            r.register(self._make_payload("2026-10-13", 2001))
            r.register(self._make_payload("2026-10-14", 2002))
            assert r.count() == 2


class TestTC28_RecorderFingerprintVerification:
    def _make_payload(self) -> ImmutableDecisionPayload:
        return ImmutableDecisionPayload(
            fill_date="2026-10-13",
            signal_id=9999,
            stock_id="1234",
            model_version="v8.0",
            locked_at="2026-10-12 00:00:00",
            trade_signal="strong_buy",
            v3_decision_snapshot=None,
            classification=DecisionClassification.BASE_SIGNAL_PROSPECTIVE,
            registered_at="2026-11-10T00:00:00Z",
        )

    def test_payload_self_verification_passes(self):
        p = self._make_payload()
        assert p.verify() is True

    def test_mutation_detection(self):
        p = self._make_payload()
        original_fingerprint = p.research_fingerprint
        # Mutate a field
        p.trade_signal = "wait"
        # Fingerprint should no longer match
        assert p.verify() is False

    def test_fingerprint_deterministic(self):
        p1 = self._make_payload()
        p2 = self._make_payload()
        assert p1.research_fingerprint == p2.research_fingerprint

    def test_different_payloads_different_fingerprints(self):
        p1 = ImmutableDecisionPayload(
            fill_date="2026-10-13", signal_id=1,
            stock_id="2330", model_version="v8.0",
            locked_at="2026-10-12 00:00:00", trade_signal="buy",
            v3_decision_snapshot=None,
            classification=DecisionClassification.BASE_SIGNAL_PROSPECTIVE,
            registered_at="2026-11-10T00:00:00Z",
        )
        p2 = ImmutableDecisionPayload(
            fill_date="2026-10-13", signal_id=2,  # different signal_id
            stock_id="2330", model_version="v8.0",
            locked_at="2026-10-12 00:00:00", trade_signal="buy",
            v3_decision_snapshot=None,
            classification=DecisionClassification.BASE_SIGNAL_PROSPECTIVE,
            registered_at="2026-11-10T00:00:00Z",
        )
        assert p1.research_fingerprint != p2.research_fingerprint


class TestTC29_RecorderVerifyAll:
    def test_verify_all_returns_zero_invalid(self):
        with ProspectiveRecorderPrototype() as r:
            p = ImmutableDecisionPayload(
                fill_date="2026-10-13", signal_id=777,
                stock_id="2330", model_version="v8.0",
                locked_at="2026-10-12 00:00:00", trade_signal="buy",
                v3_decision_snapshot=None,
                classification=DecisionClassification.BASE_SIGNAL_PROSPECTIVE,
                registered_at="2026-11-10T00:00:00Z",
            )
            r.register(p)
            valid, invalid = r.verify_all()
            assert valid == 1
            assert invalid == 0

    def test_context_manager_cleans_up(self):
        db_path = None
        with ProspectiveRecorderPrototype() as r:
            db_path = r._db_path
        # After context manager exits, temp file should be deleted
        if db_path is not None:
            assert not os.path.exists(db_path)


class TestTC30_RecorderModelVersionEnforcement:
    def test_payload_model_version_stored(self):
        with ProspectiveRecorderPrototype() as r:
            p = ImmutableDecisionPayload(
                fill_date="2026-10-28", signal_id=555,
                stock_id="2454", model_version="v8.0",
                locked_at="2026-10-27 00:00:00", trade_signal="buy",
                v3_decision_snapshot=None,
                classification=DecisionClassification.BASE_SIGNAL_PROSPECTIVE,
                registered_at="2026-11-10T00:00:00Z",
            )
            r.register(p)
            row = r._conn.execute(
                "SELECT model_version, classification FROM prospective_decisions WHERE signal_id=555"
            ).fetchone()
            assert row is not None
            assert row[0] == "v8.0"
            assert row[1] == DecisionClassification.BASE_SIGNAL_PROSPECTIVE


# ── PART G: Backfill Authorization Readiness ─────────────────────────────────

class TestTC31_AuthReadinessStructure:
    def test_has_expected_dates(self, auth_readiness):
        date_strs = {r.date for r in auth_readiness.dates}
        for d in ["2026-10-29", "2026-10-30", "2026-11-02", "2026-11-03",
                  "2026-11-06", "2026-11-09"]:
            assert d in date_strs

    def test_tier1_proxy_dates_pending(self, auth_readiness):
        for r in auth_readiness.dates:
            if r.tier == "TIER_1_PROXY":
                assert r.auth01_verdict == Auth01ReadinessVerdict.PENDING_AUTHORIZATION

    def test_nov06_nov09_pending(self, auth_readiness):
        for r in auth_readiness.dates:
            if r.date in ("2026-11-06", "2026-11-09"):
                assert r.auth01_verdict == Auth01ReadinessVerdict.PENDING_AUTHORIZATION

    def test_nov04_nov05_already_covered(self, auth_readiness):
        for r in auth_readiness.dates:
            if r.date in ("2026-11-04", "2026-11-05"):
                assert r.auth01_verdict == Auth01ReadinessVerdict.ALREADY_COVERED

    def test_overall_pending(self, auth_readiness):
        assert auth_readiness.auth01_overall == "PENDING"


class TestTC32_AuthReadinessSourceVerification:
    def test_tier1_source_verified(self, auth_readiness):
        for r in auth_readiness.dates:
            if r.tier == "TIER_1_PROXY":
                assert r.source_verified is True

    def test_nov06_source_verified(self, auth_readiness):
        nov06 = next((r for r in auth_readiness.dates if r.date == "2026-11-06"), None)
        assert nov06 is not None
        assert nov06.source_verified is True

    def test_nov09_source_verified(self, auth_readiness):
        nov09 = next((r for r in auth_readiness.dates if r.date == "2026-11-09"), None)
        assert nov09 is not None
        assert nov09.source_verified is True


class TestTC33_AuthReadinessCurrentCounts:
    def test_tier1_stock_count_one(self, auth_readiness):
        for r in auth_readiness.dates:
            if r.tier == "TIER_1_PROXY":
                assert r.current_stock_count == 1

    def test_nov06_zero_stocks(self, auth_readiness):
        nov06 = next((r for r in auth_readiness.dates if r.date == "2026-11-06"), None)
        assert nov06.current_stock_count == 0

    def test_nov09_zero_stocks(self, auth_readiness):
        nov09 = next((r for r in auth_readiness.dates if r.date == "2026-11-09"), None)
        assert nov09.current_stock_count == 0

    def test_nov04_above_5000(self, auth_readiness):
        nov04 = next((r for r in auth_readiness.dates if r.date == "2026-11-04"), None)
        assert nov04 is not None
        assert nov04.current_stock_count >= 5000


class TestTC34_PendingDatesList:
    def test_pending_includes_tier1(self, auth_readiness):
        pending = auth_readiness.pending_dates()
        assert "2026-10-29" in pending

    def test_pending_includes_nov06_nov09(self, auth_readiness):
        pending = auth_readiness.pending_dates()
        assert "2026-11-06" in pending
        assert "2026-11-09" in pending

    def test_ready_dates_empty_no_auth(self, auth_readiness):
        ready = auth_readiness.ready_dates()
        assert len(ready) == 0


# ── PART H / I: 20D Readiness + Statistical Guardrails ───────────────────────

class TestTC35_TwentyDReadinessUnchanged:
    def test_all_clusters_blocked_pipeline(self):
        from src.research.calendar_contract_s50 import (
            TwentyDReadinessVerdict,
            build_20d_readiness_matrix,
        )
        m = build_20d_readiness_matrix(
            analysis_date="2026-11-10",
            auth01_granted=False,
            auth02_granted=False,
            pipeline_restored=False,
        )
        for c in m.clusters:
            assert c.verdict == TwentyDReadinessVerdict.BLOCKED_PIPELINE

    def test_nov12_hard_deadline(self):
        from src.research.calendar_contract_s50 import build_20d_readiness_matrix
        m = build_20d_readiness_matrix("2026-11-10", False, False, False)
        oct13 = next((c for c in m.clusters if c.fill_date == "2026-10-13"), None)
        assert oct13 is not None
        assert oct13.exit_20td_corrected == "2026-11-12"


class TestTC36_G04StillFails:
    def test_g04_weekly5td_scenario_fails(self):
        from src.research.calendar_contract_s50 import build_g04_dependence_study
        g04 = build_g04_dependence_study()
        s5 = next((s for s in g04.weekly_spacing_scenarios if s.min_td_gap == 5), None)
        if s5 is not None:
            assert s5.g04_verdict.value in ("G04_FAIL", "FAIL")

    def test_g04_current_verdict_fail(self):
        from src.research.calendar_contract_s50 import build_g04_dependence_study, G04WeeklySpacingVerdict
        g04 = build_g04_dependence_study()
        assert g04.g04_current_verdict == G04WeeklySpacingVerdict.G04_FAIL


class TestTC37_G03StillFails:
    def test_strict_clusters_lt_10(self):
        from src.research.calendar_contract_s50 import build_strict5d_eligibility_matrix
        em = build_strict5d_eligibility_matrix()
        assert em.n_strict_now < 10

    def test_g03_verdict_fail(self):
        from src.research.calendar_contract_s50 import build_strict5d_eligibility_matrix
        em = build_strict5d_eligibility_matrix()
        assert not em.g03_now


# ── Production Fingerprints ───────────────────────────────────────────────────

class TestTC38_ProductionFingerprintsUnchanged:
    def test_forward_signals_total_2605(self, conn):
        n = conn.execute("SELECT COUNT(*) FROM forward_signals").fetchone()[0]
        assert n == 2605

    def test_daily_prices_max_date_nov05(self, conn):
        d = conn.execute(
            "SELECT MAX(date) FROM daily_prices WHERE stock_id='0050'"
        ).fetchone()[0]
        assert d == "2026-11-05"

    def test_nov06_zero_rows(self, conn):
        n = conn.execute(
            "SELECT COUNT(*) FROM daily_prices WHERE date='2026-11-06'"
        ).fetchone()[0]
        assert n == 0

    def test_nov09_zero_rows(self, conn):
        n = conn.execute(
            "SELECT COUNT(*) FROM daily_prices WHERE date='2026-11-09'"
        ).fetchone()[0]
        assert n == 0

    def test_v8_buy_signals_237(self, conn):
        n = conn.execute(
            "SELECT COUNT(*) FROM forward_signals "
            "WHERE model_version='v8.0' AND trade_signal IN ('buy','strong_buy')"
        ).fetchone()[0]
        assert n == 237

    def test_tier1_proxy_dates_one_stock_each(self, conn):
        for d in ["2026-10-29", "2026-10-30", "2026-11-02", "2026-11-03"]:
            n = conn.execute(
                "SELECT COUNT(*) FROM daily_prices WHERE date=?", (d,)
            ).fetchone()[0]
            assert n == 1, f"Expected 1 row for {d}, got {n}"

    def test_nov04_above_6900_rows(self, conn):
        n = conn.execute(
            "SELECT COUNT(*) FROM daily_prices WHERE date='2026-11-04'"
        ).fetchone()[0]
        assert n >= 6900


class TestTC39_MatrixFingerprintVerified:
    def test_fingerprint_ok(self, matrix):
        assert matrix.fingerprint_verified is True

    def test_v3_hash_unchanged(self):
        assert V3_PARAMETER_HASH == "be43e8ca977d9fdd"


class TestTC40_SessionS51OverallVerdict:
    """High-level S51 verdict: ACTIVATION_BLOCKED, FRAMEWORK_READY_COLLECTION_PENDING."""

    def test_activation_still_blocked(self):
        # No path to activation: G03 FAIL, G04 FAIL, pipeline down
        from src.research.calendar_contract_s50 import build_strict5d_eligibility_matrix
        em = build_strict5d_eligibility_matrix()
        assert em.n_strict_now < 10

    def test_pipeline_root_cause_identified(self, matrix):
        td = matrix.get_tier(PipelineTier.BLOCKED_STALE_DATA)
        s = td.get_stage(PipelineStage.PROVIDER_RESPONSE)
        assert s.level == EvidenceLevel.DIRECTLY_CONFIRMED

    def test_prospective_evidence_framework_ready(self, collection_plan):
        assert "FRAMEWORK_READY" in collection_plan.collection_verdict

    def test_all_research_modules_no_production_writes(self):
        import inspect
        import src.research.pipeline_root_cause_s51 as m1
        import src.research.prospective_recorder_s51 as m2
        for m in [m1, m2]:
            src_text = inspect.getsource(m)
            # Should not contain INSERT/UPDATE/DELETE against platform.db path
            assert "INSERT INTO forward_signals" not in src_text
            assert "INSERT INTO daily_prices" not in src_text
            assert "DELETE FROM" not in src_text
