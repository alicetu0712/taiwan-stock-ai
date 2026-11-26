"""
Session 39 tests: CleanResearchUniverseBuilder, StrategyVersionRegistry,
HistoricalResearchEligibilityGate, StrategyComparisonFramework,
V1V2V3ComparisonReadinessReport.

All tests use in-memory fixtures only — no production DB reads.
Naming: CU-xx (clean universe), VR-xx (version registry),
EG-xx (eligibility gate), CF-xx (comparison framework),
RR-xx (readiness report).
"""
from __future__ import annotations

from typing import FrozenSet, List

import pytest

from src.research.security_classification import OfficialUniverse
from src.research.clean_research_universe import (
    CleanResearchUniverseBuilder,
    DatasetLabel,
    SignalRecord,
)
from src.research.strategy_version_registry import (
    StrategyVersionRegistry,
    VersionStatus,
    assess_version_pair,
)
from src.research.comparison_readiness_report import (
    ComparabilityVerdict,
    EligibilityVerdict,
    ReadinessStatus,
    StrategyComparisonFramework,
    V1V2V3ComparisonReadinessReport,
    build_session39_readiness_report,
    run_historical_eligibility_gate,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def twse_ids() -> FrozenSet[str]:
    return frozenset({"2330", "2317", "2454", "1301", "2882"})


@pytest.fixture
def tpex_ids() -> FrozenSet[str]:
    return frozenset({"6271", "3673"})


@pytest.fixture
def official(twse_ids, tpex_ids) -> OfficialUniverse:
    return OfficialUniverse(twse_ids=twse_ids, tpex_ids=tpex_ids)


@pytest.fixture
def master_ids() -> FrozenSet[str]:
    return frozenset({"2330", "2317", "0050", "1107"})


@pytest.fixture
def mixed_signals() -> List[SignalRecord]:
    return [
        SignalRecord("s1", "2330", "2026-10-12", "v8.0", "buy"),
        SignalRecord("s2", "2317", "2026-10-12", "v8.0", "buy"),
        SignalRecord("s3", "2454", "2026-10-12", "v8.0", "wait"),   # TWSE orphan
        SignalRecord("s4", "0050", "2026-10-12", "v8.0", "buy"),    # ETF_OFFICIAL
        SignalRecord("s5", "00646", "2026-10-13", "v8.0", "buy"),   # ETF_PROBABLE
        SignalRecord("s6", "6271", "2026-10-13", "v8.0", "buy"),    # TPEX (orphan)
        SignalRecord("s7", "1107", "2026-10-13", "v8.0", "wait"),   # DELISTED_PROBABLE
        SignalRecord("s8", "12345", "2026-10-13", "v8.0", "buy"),   # UNKNOWN
    ]


@pytest.fixture
def builder(official, master_ids) -> CleanResearchUniverseBuilder:
    return CleanResearchUniverseBuilder(official, master_ids)


@pytest.fixture
def registry() -> StrategyVersionRegistry:
    return StrategyVersionRegistry()


# ---------------------------------------------------------------------------
# CU: CleanResearchUniverseBuilder
# ---------------------------------------------------------------------------

class TestCleanResearchUniverseBuilder:

    def test_cu01_build_all_returns_three_datasets(self, builder, mixed_signals):
        """CU-01: build_all returns all three DatasetLabel keys"""
        datasets = builder.build_all(mixed_signals)
        assert set(datasets.keys()) == {
            DatasetLabel.A_ORIGINAL,
            DatasetLabel.B_VERIFIED_COMMON,
            DatasetLabel.C_SENSITIVITY,
        }

    def test_cu02_dataset_a_includes_all_signals(self, builder, mixed_signals):
        """CU-02: Dataset A contains all input signals"""
        ds = builder.build_all(mixed_signals)[DatasetLabel.A_ORIGINAL]
        assert ds.total_signals == len(mixed_signals)

    def test_cu03_dataset_b_excludes_etf(self, builder, mixed_signals):
        """CU-03: Dataset B removes ETF signals"""
        ds = builder.build_all(mixed_signals)[DatasetLabel.B_VERIFIED_COMMON]
        # 0050 (ETF_OFFICIAL) and 00646 (ETF_PROBABLE) must be excluded
        assert ds.etf_signal_count == 0

    def test_cu04_dataset_b_excludes_unknown(self, builder, mixed_signals):
        """CU-04: Dataset B removes UNKNOWN securities"""
        ds = builder.build_all(mixed_signals)[DatasetLabel.B_VERIFIED_COMMON]
        assert ds.unknown_signal_count == 0

    def test_cu05_dataset_b_keeps_twse_common(self, builder, mixed_signals):
        """CU-05: Dataset B retains verified TWSE common stocks"""
        ds = builder.build_all(mixed_signals)[DatasetLabel.B_VERIFIED_COMMON]
        # 2330, 2317 (TWSE_COMMON_ACTIVE) + 2454 (ORPHAN_TWSE) + 6271 (ORPHAN_TPEX) = 4 signals
        assert ds.total_signals >= 4

    def test_cu06_dataset_b_smaller_than_a(self, builder, mixed_signals):
        """CU-06: Dataset B has fewer signals than Dataset A"""
        datasets = builder.build_all(mixed_signals)
        assert (datasets[DatasetLabel.B_VERIFIED_COMMON].total_signals <
                datasets[DatasetLabel.A_ORIGINAL].total_signals)

    def test_cu07_dataset_c_excludes_etf_keeps_unknown(self, builder, mixed_signals):
        """CU-07: Dataset C excludes ETF but retains UNKNOWN"""
        ds = builder.build_all(mixed_signals)[DatasetLabel.C_SENSITIVITY]
        assert ds.etf_signal_count == 0
        assert ds.unknown_signal_count > 0  # 12345 is UNKNOWN

    def test_cu08_dataset_fingerprints_are_distinct(self, builder, mixed_signals):
        """CU-08: Each dataset has a distinct fingerprint"""
        datasets = builder.build_all(mixed_signals)
        fps = [d.data_fingerprint for d in datasets.values()]
        assert len(set(fps)) == 3

    def test_cu09_exclusion_reasons_documented(self, builder, mixed_signals):
        """CU-09: Dataset B documents exclusion reasons"""
        ds = builder.build_all(mixed_signals)[DatasetLabel.B_VERIFIED_COMMON]
        assert len(ds.exclusion_reasons) > 0
        combined = " ".join(ds.exclusion_reasons)
        assert "ETF" in combined

    def test_cu10_model_version_filter(self, builder):
        """CU-10: model_version_filter restricts to specified version"""
        signals = [
            SignalRecord("s1", "2330", "2026-10-12", "v8.0"),
            SignalRecord("s2", "2317", "2026-10-12", "v6.0"),
        ]
        datasets = builder.build_all(signals, model_version_filter="v8.0")
        assert datasets[DatasetLabel.A_ORIGINAL].total_signals == 1

    def test_cu11_dataset_dates_sorted(self, builder, mixed_signals):
        """CU-11: unique_dates is sorted"""
        ds = builder.build_all(mixed_signals)[DatasetLabel.A_ORIGINAL]
        assert ds.unique_dates == sorted(ds.unique_dates)

    def test_cu12_session38_numbers_dataset_b(self, official):
        """CU-12: Session 38 known numbers: 213 ETF removed → 2023 signals"""
        # Simulate session 38 FS v8.0 data
        twse_large = frozenset(f"{i:04d}" for i in range(1000, 1368))
        etf_ids = frozenset({"0050", "0052", "0056", "00646"})
        full_official = OfficialUniverse(twse_ids=twse_large, tpex_ids=frozenset())
        builder_large = CleanResearchUniverseBuilder(full_official)
        signals = (
            [SignalRecord(f"s_{i}", sid, "2026-10-12", "v8.0") for i, sid in enumerate(twse_large)]
            + [SignalRecord(f"e_{i}", sid, "2026-10-12", "v8.0") for i, sid in enumerate(etf_ids)]
        )
        datasets = builder_large.build_all(signals)
        a = datasets[DatasetLabel.A_ORIGINAL]
        b = datasets[DatasetLabel.B_VERIFIED_COMMON]
        assert b.total_signals == a.total_signals - len(etf_ids)
        assert b.etf_signal_count == 0


# ---------------------------------------------------------------------------
# VR: StrategyVersionRegistry
# ---------------------------------------------------------------------------

class TestStrategyVersionRegistry:

    def test_vr01_registry_has_four_versions(self, registry):
        """VR-01: Registry contains exactly 4 strategy versions"""
        assert len(registry.all()) == 4

    def test_vr02_v3_is_verified(self, registry):
        """VR-02: V3 (v3_entry_timing) has VERIFIED status"""
        v3 = registry.get("v3_entry_timing")
        assert v3.status == VersionStatus.VERIFIED

    def test_vr03_hybrid_v1_is_verified(self, registry):
        """VR-03: Hybrid V1 has VERIFIED status and frozen commit"""
        hv1 = registry.get("hybrid_v1")
        assert hv1.status == VersionStatus.VERIFIED
        assert hv1.frozen_commit == "6602c3b"

    def test_vr04_v1_is_partial(self, registry):
        """VR-04: V1 has PARTIAL status (parameters unversioned)"""
        v1 = registry.get("v1_signal_only")
        assert v1.status == VersionStatus.PARTIAL

    def test_vr05_v2_is_partial(self, registry):
        """VR-05: V2 has PARTIAL status (EntryTimingAnalyzer unversioned)"""
        v2 = registry.get("v2_entry_timing")
        assert v2.status == VersionStatus.PARTIAL

    def test_vr06_v3_has_parameter_hash(self, registry):
        """VR-06: V3 has known parameter hash be43e8ca"""
        v3 = registry.get("v3_entry_timing")
        assert v3.parameter_hash == "be43e8ca977d9fdd"

    def test_vr07_all_versions_use_same_scoring_engine(self, registry):
        """VR-07: All 4 versions use the same foe_v1 scoring engine"""
        engines = {v.scoring_engine for v in registry.all()}
        assert len(engines) == 1
        assert "foe_v1" in list(engines)[0]

    def test_vr08_v1_has_no_parameter_hash(self, registry):
        """VR-08: V1 has no parameter hash (unversioned thresholds)"""
        v1 = registry.get("v1_signal_only")
        assert not v1.has_parameter_hash

    def test_vr09_verified_versions_count(self, registry):
        """VR-09: exactly 2 versions are VERIFIED (hybrid_v1 and v3)"""
        verified = registry.verified_versions()
        assert len(verified) == 2
        ids = {v.version_id for v in verified}
        assert "hybrid_v1" in ids
        assert "v3_entry_timing" in ids

    def test_vr10_version_pair_v3_hybrid_comparable(self, registry):
        """VR-10: V3 vs Hybrid_V1 are comparable (both VERIFIED, same engine)"""
        pair = assess_version_pair(registry, "v3_entry_timing", "hybrid_v1")
        assert pair.shared_scoring_engine is True

    def test_vr11_version_pair_v1_v2_not_strictly_comparable(self, registry):
        """VR-11: V1 vs V2 not strictly comparable (both PARTIAL, unverified params)"""
        pair = assess_version_pair(registry, "v1_signal_only", "v2_entry_timing")
        assert pair.is_comparable is False
        assert len(pair.blockers) > 0

    def test_vr12_comparison_engine_strategy_mapping(self, registry):
        """VR-12: V3 maps to D_v3, Hybrid maps to C_hybrid, V1 to B_v1v2"""
        assert registry.get("v3_entry_timing").comparison_engine_strategy == "D_v3"
        assert registry.get("hybrid_v1").comparison_engine_strategy == "C_hybrid"
        assert registry.get("v1_signal_only").comparison_engine_strategy == "B_v1v2"


# ---------------------------------------------------------------------------
# EG: HistoricalResearchEligibilityGate
# ---------------------------------------------------------------------------

class TestHistoricalResearchEligibilityGate:

    @pytest.fixture
    def gate_report(self):
        return run_historical_eligibility_gate()

    def test_eg01_gate_has_12_checks(self, gate_report):
        """EG-01: Gate produces exactly 12 checks"""
        assert len(gate_report.checks) == 12

    def test_eg02_check_ids_are_unique_sequential(self, gate_report):
        """EG-02: Check IDs are EG-01 through EG-12"""
        ids = {c.check_id for c in gate_report.checks}
        expected = {f"EG-{i:02d}" for i in range(1, 13)}
        assert ids == expected

    def test_eg03_point_in_time_flag_set(self, gate_report):
        """EG-03: POINT_IN_TIME_UNIVERSE_UNVERIFIED flag is set"""
        assert gate_report.point_in_time_flag is True

    def test_eg04_missing_outcomes_ineligible(self, gate_report):
        """EG-04: EG-08 (missing outcomes) → INELIGIBLE"""
        check = next(c for c in gate_report.checks if c.check_id == "EG-08")
        assert check.verdict == EligibilityVerdict.INELIGIBLE

    def test_eg05_survivorship_ineligible(self, gate_report):
        """EG-05: EG-12 (survivorship bias) → INELIGIBLE"""
        check = next(c for c in gate_report.checks if c.check_id == "EG-12")
        assert check.verdict == EligibilityVerdict.INELIGIBLE

    def test_eg06_official_classification_eligible(self, gate_report):
        """EG-06: EG-01 (official classification) → ELIGIBLE"""
        check = next(c for c in gate_report.checks if c.check_id == "EG-01")
        assert check.verdict == EligibilityVerdict.ELIGIBLE

    def test_eg07_no_duplicate_eligible(self, gate_report):
        """EG-07: EG-09 (no duplicates) → ELIGIBLE"""
        check = next(c for c in gate_report.checks if c.check_id == "EG-09")
        assert check.verdict == EligibilityVerdict.ELIGIBLE

    def test_eg08_overall_verdict_ineligible(self, gate_report):
        """EG-08: Overall → INELIGIBLE (3+ INELIGIBLE checks)"""
        assert gate_report.overall_verdict == EligibilityVerdict.INELIGIBLE

    def test_eg09_summary_has_counts(self, gate_report):
        """EG-09: Summary string contains verdict counts"""
        assert "INELIGIBLE" in gate_report.summary


# ---------------------------------------------------------------------------
# CF: StrategyComparisonFramework
# ---------------------------------------------------------------------------

class TestStrategyComparisonFramework:

    @pytest.fixture
    def framework(self):
        return StrategyComparisonFramework()

    def test_cf01_contract_fees_pct(self, framework):
        """CF-01: Contract uses FEES_PCT = 0.585%"""
        assert framework.CONTRACT.fees_pct == 0.585

    def test_cf02_contract_universe_b(self, framework):
        """CF-02: Contract requires Dataset B (verified common)"""
        assert "Dataset B" in framework.CONTRACT.eligible_universe

    def test_cf03_contract_benchmark_0050(self, framework):
        """CF-03: Contract uses 0050 as benchmark"""
        assert "0050" in framework.CONTRACT.benchmark

    def test_cf04_missingness_not_comparable(self, framework):
        """CF-04: Current session comparability → NOT_COMPARABLE"""
        result = framework.assess_session39_comparability()
        assert result.comparability_verdict == ComparabilityVerdict.NOT_COMPARABLE

    def test_cf05_missingness_zero_comparable_signals(self, framework):
        """CF-05: 0 signals are comparable today (all missing outcomes)"""
        result = framework.assess_session39_comparability()
        assert result.comparable_signals == 0

    def test_cf06_missing_outcome_equals_total(self, framework):
        """CF-06: missing_outcome count equals total_signals"""
        result = framework.assess_session39_comparability()
        assert result.missing_outcome == result.total_signals

    def test_cf07_etf_contamination_documented(self, framework):
        """CF-07: ETF contamination (213 signals) is documented in missingness"""
        result = framework.assess_session39_comparability()
        assert result.etf_contaminated == 213

    def test_cf08_contract_dedup_policy_documented(self, framework):
        """CF-08: Deduplication policy is documented"""
        assert "20D" in framework.CONTRACT.dedup_policy


# ---------------------------------------------------------------------------
# RR: V1V2V3ComparisonReadinessReport
# ---------------------------------------------------------------------------

class TestComparisonReadinessReport:

    @pytest.fixture
    def report(self) -> V1V2V3ComparisonReadinessReport:
        return build_session39_readiness_report()

    def test_rr01_report_has_10_dimensions(self, report):
        """RR-01: Readiness report has 10 dimensions"""
        assert len(report.dimensions) == 10

    def test_rr02_ranking_not_supported(self, report):
        """RR-02: Ranking is NOT supported (multiple BLOCKED dimensions)"""
        assert report.ranking_supported is False

    def test_rr03_outcome_availability_blocked(self, report):
        """RR-03: Outcome Availability dimension → BLOCKED"""
        dim = next(d for d in report.dimensions if d.name == "Outcome Availability")
        assert dim.status == ReadinessStatus.BLOCKED

    def test_rr04_oos_evidence_blocked(self, report):
        """RR-04: Out-of-sample Evidence → BLOCKED"""
        dim = next(d for d in report.dimensions if "Out-of-Sample" in d.name or "out-of-sample" in d.name.lower() or "OOS" in d.name)
        assert dim.status == ReadinessStatus.BLOCKED

    def test_rr05_transaction_costs_ready(self, report):
        """RR-05: Transaction Costs → READY (FEES_PCT consistent)"""
        dim = next(d for d in report.dimensions if "Transaction" in d.name)
        assert dim.status == ReadinessStatus.READY

    def test_rr06_minimum_viable_improvements_listed(self, report):
        """RR-06: At least 3 minimum viable improvements listed"""
        assert len(report.minimum_viable_improvements) >= 3

    def test_rr07_blocked_dimensions_have_blocker_text(self, report):
        """RR-07: All BLOCKED dimensions have non-empty blocker text"""
        for dim in report.by_status(ReadinessStatus.BLOCKED):
            assert dim.blocker is not None and len(dim.blocker) > 10

    def test_rr08_overall_verdict_ranking_not_supported(self, report):
        """RR-08: Overall verdict is RANKING_NOT_SUPPORTED"""
        assert report.overall_verdict == "RANKING_NOT_SUPPORTED"

    def test_rr09_blocked_count_matches(self, report):
        """RR-09: blocked_count matches BLOCKED dimensions"""
        assert report.blocked_count == len(report.by_status(ReadinessStatus.BLOCKED))

    def test_rr10_production_data_not_touched(self):
        """RR-10: Building readiness report requires no production DB access"""
        import sqlite3
        import sys
        from unittest.mock import patch

        _cf = sys.modules.get("tests.conftest")
        assert _cf is not None, "conftest not in sys.modules — guard state unknown"
        _guarded = _cf._guarded_connect
        assert sqlite3.connect is _guarded, (
            "GUARD NOT ACTIVE before RR-10 patch: sqlite3.connect is not _guarded_connect"
        )

        opened_dbs = []

        def _spy_connect(db, *args, **kwargs):
            if "platform.db" in str(db):
                opened_dbs.append(db)
            return _guarded(db, *args, **kwargs)

        with patch("sqlite3.connect", new=_spy_connect):
            report = build_session39_readiness_report()
            assert report is not None

        assert sqlite3.connect is _guarded, (
            "GUARD NOT RESTORED after RR-10 patch: sqlite3.connect is not _guarded_connect"
        )
        assert len(opened_dbs) == 0, f"Unexpectedly opened production DB: {opened_dbs}"

    def test_rr10_guard_effective_during_patch(self):
        """D1: Guard rejects forbidden paths while RR-10 spy is active."""
        import sqlite3
        import sys
        from unittest.mock import patch

        _cf = sys.modules.get("tests.conftest")
        assert _cf is not None, "conftest not in sys.modules"
        _guarded = _cf._guarded_connect
        assert sqlite3.connect is _guarded, "Guard must be active before patch"

        opened_dbs = []

        def _spy_connect(db, *args, **kwargs):
            if "platform.db" in str(db):
                opened_dbs.append(db)
            return _guarded(db, *args, **kwargs)

        _synthetic_forbidden = "data/platform.db"

        with patch("sqlite3.connect", new=_spy_connect):
            with pytest.raises(AssertionError, match="ISOLATION GUARD"):
                sqlite3.connect(_synthetic_forbidden)

        assert sqlite3.connect is _guarded, "Guard not restored after D1 patch exit"
        assert _synthetic_forbidden in opened_dbs, (
            f"Spy did not record forbidden attempt: opened_dbs={opened_dbs}"
        )

    def test_rr10_exception_safe_restoration(self):
        """D2: sqlite3.connect restores to guard after exception inside patch context."""
        import sqlite3
        import sys
        from unittest.mock import patch

        _cf = sys.modules.get("tests.conftest")
        assert _cf is not None, "conftest not in sys.modules"
        _guarded = _cf._guarded_connect
        assert sqlite3.connect is _guarded, "Guard must be active before patch"

        opened_dbs = []

        def _spy_connect(db, *args, **kwargs):
            if "platform.db" in str(db):
                opened_dbs.append(db)
            return _guarded(db, *args, **kwargs)

        with pytest.raises(RuntimeError, match="synthetic_rr10_exception"):
            with patch("sqlite3.connect", new=_spy_connect):
                raise RuntimeError("synthetic_rr10_exception")

        assert sqlite3.connect is _guarded, (
            "GUARD NOT RESTORED after exception in RR-10 patch context"
        )
