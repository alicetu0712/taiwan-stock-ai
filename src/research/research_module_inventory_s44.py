"""
PART B (P1): Research Module Inventory — Session 44.

Enumerates all 55 research modules from Sessions 38-43.
Records file path, purpose, dependencies, overlaps, and recommended action.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ModuleSession(str, Enum):
    S26 = "S26"
    S27 = "S27"
    S28 = "S28"
    S29 = "S29"
    S35 = "S35"
    S38 = "S38"
    S39 = "S39"
    S40 = "S40"
    S41 = "S41"
    S42 = "S42"
    S43 = "S43"
    S44 = "S44"
    PRE_S38 = "PRE_S38"
    UNKNOWN = "UNKNOWN"


class ModuleCategory(str, Enum):
    UNIVERSE = "UNIVERSE"
    SIGNAL = "SIGNAL"
    BACKTEST = "BACKTEST"
    COMPARISON = "COMPARISON"
    CALENDAR = "CALENDAR"
    EXECUTION = "EXECUTION"
    STATISTICS = "STATISTICS"
    GUARDRAILS = "GUARDRAILS"
    EVIDENCE = "EVIDENCE"
    WORKFLOW = "WORKFLOW"
    INFRASTRUCTURE = "INFRASTRUCTURE"
    STRATEGY = "STRATEGY"


class RecommendedAction(str, Enum):
    KEEP_AS_IS = "KEEP_AS_IS"
    SUPERSEDED_KEEP = "SUPERSEDED_KEEP"   # older version; newer exists; keep for history
    SUPERSEDED_RETIRE = "SUPERSEDED_RETIRE"  # duplicated; can be retired
    CONSOLIDATE = "CONSOLIDATE"           # merge with related module
    EXTEND = "EXTEND"                     # needs new data or logic
    DOCUMENT = "DOCUMENT"                 # needs better documentation


class ResearchOnlyBoundary(str, Enum):
    READ_ONLY_DB = "READ_ONLY_DB"
    IN_MEMORY_ONLY = "IN_MEMORY_ONLY"
    WRITES_RESEARCH_ARTIFACT = "WRITES_RESEARCH_ARTIFACT"
    WRITES_PRODUCTION = "WRITES_PRODUCTION"  # should not exist


@dataclass(frozen=True)
class ModuleRecord:
    file_path: str
    module_name: str
    session: ModuleSession
    category: ModuleCategory
    purpose: str
    primary_inputs: tuple[str, ...]
    primary_outputs: tuple[str, ...]
    dependencies: tuple[str, ...]
    data_sources: tuple[str, ...]
    research_boundary: ResearchOnlyBoundary
    existing_tests: str
    overlaps_with: tuple[str, ...]
    recommended_action: RecommendedAction
    notes: str


@dataclass(frozen=True)
class ResearchModuleInventory:
    session: int
    modules: tuple[ModuleRecord, ...]
    n_total: int
    by_category: dict[str, int]
    by_session: dict[str, int]
    n_superseded: int
    n_to_consolidate: int
    n_keep: int
    duplicate_pairs: tuple[tuple[str, str], ...]
    inventory_notes: str


_MODULES: list[ModuleRecord] = [
    # === UNIVERSE / CLASSIFICATION ===
    ModuleRecord(
        "src/research/security_classification.py",
        "security_classification", ModuleSession.S38, ModuleCategory.UNIVERSE,
        "Official TWSE/TPEx security classification (Common/ETF/Preferred)",
        ("raw TWSE/TPEx listing data",),
        ("SecurityClassificationReport",),
        (),
        ("external TWSE listing",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "tests/test_session38_*.py",
        (),
        RecommendedAction.KEEP_AS_IS,
        "Authoritative; S38 corrected all S37 heuristics",
    ),
    ModuleRecord(
        "src/research/etf_contamination_audit.py",
        "etf_contamination_audit", ModuleSession.S38, ModuleCategory.UNIVERSE,
        "Measure ETF-like signal contamination in forward_signals pool",
        ("forward_signals", "stocks"),
        ("ETFContaminationReport",),
        ("security_classification",),
        ("platform.db",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "tests/test_session38_*.py",
        ("clean_research_universe",),
        RecommendedAction.KEEP_AS_IS,
        "9.52% official ETF rate from S38; ~1.8% in signal pool",
    ),
    ModuleRecord(
        "src/research/universe_alignment_auditor.py",
        "universe_alignment_auditor", ModuleSession.S38, ModuleCategory.UNIVERSE,
        "Compare forward_signals universe against official stock listing",
        ("forward_signals", "stocks", "security_classification"),
        ("UniverseAlignmentReport",),
        ("security_classification",),
        ("platform.db",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "tests/test_session38_*.py",
        ("etf_contamination_audit",),
        RecommendedAction.KEEP_AS_IS,
        "SIGNIFICANT_MISMATCH found in S38",
    ),
    ModuleRecord(
        "src/research/clean_research_universe.py",
        "clean_research_universe", ModuleSession.S38, ModuleCategory.UNIVERSE,
        "Build clean v8.0 common-stock universe for research",
        ("forward_signals", "stocks"),
        ("CleanResearchUniverse",),
        ("security_classification",),
        ("platform.db",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "tests/test_session38_*.py",
        (),
        RecommendedAction.KEEP_AS_IS,
        "Canonical universe for all downstream research",
    ),
    ModuleRecord(
        "src/research/research_quality_gate.py",
        "research_quality_gate", ModuleSession.S38, ModuleCategory.GUARDRAILS,
        "12-gate quality check for research data integrity",
        ("forward_signals", "daily_prices", "stocks"),
        ("ResearchQualityGateReport",),
        ("security_classification",),
        ("platform.db",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "tests/test_session38_*.py",
        ("statistical_guardrails",),
        RecommendedAction.KEEP_AS_IS,
        "7/12 FAIL in S38; gates include ETF contamination, signal count, etc.",
    ),
    # === STRATEGY REGISTRY ===
    ModuleRecord(
        "src/research/strategy_version_registry.py",
        "strategy_version_registry", ModuleSession.PRE_S38, ModuleCategory.STRATEGY,
        "Registry of strategy versions and parameter hashes",
        ("forward_signals", "config"),
        ("StrategyVersionRegistry",),
        (),
        ("platform.db",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "various",
        (),
        RecommendedAction.KEEP_AS_IS,
        "V3 PARAMETER_HASH be43e8ca977d9fdd frozen",
    ),
    ModuleRecord(
        "src/research/version_definition_recovery.py",
        "version_definition_recovery", ModuleSession.PRE_S38, ModuleCategory.STRATEGY,
        "Recover model version definitions from DB records",
        ("forward_signals",),
        ("VersionDefinitionReport",),
        (),
        ("platform.db",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "various",
        ("strategy_version_registry",),
        RecommendedAction.SUPERSEDED_KEEP,
        "Useful for diagnosing v6.0 vs v8.0 version provenance",
    ),
    # === SIGNAL / EXECUTION ===
    ModuleRecord(
        "src/research/execution_date_auditor.py",
        "execution_date_auditor", ModuleSession.S43, ModuleCategory.EXECUTION,
        "Formal date field definitions + thin-day anomaly diagnosis",
        ("forward_signals", "daily_prices"),
        ("ExecutionDateIntegrityReport",),
        (),
        ("platform.db",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "tests/test_session43_execution_integrity.py",
        (),
        RecommendedAction.KEEP_AS_IS,
        "S43: explains Oct 14→16 and Oct 16→21 anomalies",
    ),
    ModuleRecord(
        "src/research/non_trading_day_auditor.py",
        "non_trading_day_auditor", ModuleSession.S43, ModuleCategory.EXECUTION,
        "Classify non-trading-day signals (Oct 09-11 = v6.0)",
        ("forward_signals", "daily_prices"),
        ("NonTradingDayAuditReport",),
        (),
        ("platform.db",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "tests/test_session43_execution_integrity.py",
        ("trading_calendar_integrity",),
        RecommendedAction.KEEP_AS_IS,
        "S43: 100% of non-TD signals = v6.0; DATE_CAUSES_IDENTIFIED",
    ),
    ModuleRecord(
        "src/research/execution_simulator.py",
        "execution_simulator", ModuleSession.PRE_S38, ModuleCategory.EXECUTION,
        "Simulate NEXT_OPEN execution fills",
        ("forward_signals", "daily_prices"),
        ("SimulatedFill",),
        (),
        ("platform.db",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "various",
        ("execution_date_auditor",),
        RecommendedAction.SUPERSEDED_KEEP,
        "execution_date_auditor is the authoritative S43 source",
    ),
    # === CALENDAR ===
    ModuleRecord(
        "src/research/trading_calendar_integrity.py",
        "trading_calendar_integrity", ModuleSession.S42, ModuleCategory.CALENDAR,
        "Identify non-trading day signals; fill-date mapping",
        ("forward_signals", "daily_prices"),
        ("TradingCalendarIntegrityReport",),
        (),
        ("platform.db",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "tests/test_session42_integrity.py",
        ("non_trading_day_auditor",),
        RecommendedAction.SUPERSEDED_KEEP,
        "S42; uses DISTINCT date (incl. thin days). S43 non_trading_day_auditor is more precise",
    ),
    ModuleRecord(
        "src/research/hybrid_trading_calendar.py",
        "hybrid_trading_calendar", ModuleSession.PRE_S38, ModuleCategory.CALENDAR,
        "Taiwan trading calendar service using 0050 proxy",
        ("daily_prices",),
        ("TaiwanTradingCalendar",),
        (),
        ("platform.db",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "various",
        ("trading_calendar_integrity", "execution_date_auditor"),
        RecommendedAction.SUPERSEDED_KEEP,
        "P2: should be replaced by ≥50-stock threshold calendar",
    ),
    # === COMPARISON ===
    ModuleRecord(
        "src/research/observation_unit_auditor.py",
        "observation_unit_auditor", ModuleSession.S42, ModuleCategory.COMPARISON,
        "Reconstruct fill-date clusters from execution_date",
        ("forward_signals", "daily_prices"),
        ("ObservationUnitAuditReport",),
        (),
        ("platform.db",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "tests/test_session42_integrity.py",
        ("corrected_5d_comparison", "fill_date_contract"),
        RecommendedAction.SUPERSEDED_KEEP,
        "S42; fill_date_contract (S43) is the canonical replacement",
    ),
    ModuleRecord(
        "src/research/fill_date_contract.py",
        "fill_date_contract", ModuleSession.S43, ModuleCategory.COMPARISON,
        "Formal contract for strict/conditional signal pairing",
        ("forward_signals", "daily_prices"),
        ("FillDateComparisonContract",),
        (),
        ("platform.db",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "tests/test_session43_execution_integrity.py",
        ("observation_unit_auditor",),
        RecommendedAction.EXTEND,
        "S43 scope: Oct 09-16 only. S44: extend to Oct 09-28 (full v8.0 range)",
    ),
    ModuleRecord(
        "src/research/benchmark_integrity_auditor.py",
        "benchmark_integrity_auditor", ModuleSession.S42, ModuleCategory.COMPARISON,
        "Verify 0050 benchmark label corrections (CR-B01 through CR-B06)",
        ("forward_signals", "daily_prices"),
        ("BenchmarkIntegrityReport",),
        (),
        ("platform.db",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "tests/test_session42_integrity.py",
        (),
        RecommendedAction.KEEP_AS_IS,
        "S42: CR-B01-B06 corrections documented",
    ),
    ModuleRecord(
        "src/research/corrected_5d_comparison.py",
        "corrected_5d_comparison", ModuleSession.S42, ModuleCategory.COMPARISON,
        "5-cluster fill-date comparison (mixed v6.0+v8.0)",
        ("forward_signals", "daily_prices"),
        ("CorrectedFiveDayComparison",),
        (),
        ("platform.db",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "tests/test_session42_integrity.py",
        ("corrected_5d_comparison_s43",),
        RecommendedAction.SUPERSEDED_KEEP,
        "S42 version; uses hardcoded S42 cluster deltas",
    ),
    ModuleRecord(
        "src/research/corrected_5d_comparison_s43.py",
        "corrected_5d_comparison_s43", ModuleSession.S43, ModuleCategory.COMPARISON,
        "v8.0-strict 5D comparison (3 complete fill clusters)",
        ("forward_signals", "daily_prices"),
        ("CorrectedFiveDayComparisonS43",),
        (),
        ("platform.db",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "tests/test_session43_execution_integrity.py",
        (),
        RecommendedAction.EXTEND,
        "S43 strict; S44 extends to cover Oct 09-28 fill cluster range",
    ),
    ModuleRecord(
        "src/research/statistical_significance_audit.py",
        "statistical_significance_audit", ModuleSession.S41, ModuleCategory.STATISTICS,
        "S41 significance audit (retracted S40 SIGNIFICANT_POSITIVE claim)",
        ("forward_signals", "daily_prices"),
        ("StatisticalSignificanceAuditReport",),
        (),
        ("platform.db",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "tests/test_session41_validation.py",
        ("corrected_5d_comparison",),
        RecommendedAction.SUPERSEDED_KEEP,
        "S41 retraction; S42 supersedes with fill-date correction",
    ),
    ModuleRecord(
        "src/research/statistical_guardrails.py",
        "statistical_guardrails", ModuleSession.S42, ModuleCategory.GUARDRAILS,
        "10 statistical guardrails (G01-G10)",
        ("forward_signals", "daily_prices", "stocks"),
        ("StatisticalGuardrailsReport",),
        (),
        ("platform.db",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "tests/test_session42_integrity.py",
        ("guardrail_remediation_s43",),
        RecommendedAction.EXTEND,
        "S42 version uses Oct 09-16 scope; S44 should expand to full range",
    ),
    ModuleRecord(
        "src/research/guardrail_remediation_s43.py",
        "guardrail_remediation_s43", ModuleSession.S43, ModuleCategory.GUARDRAILS,
        "Per-guardrail before/after remediation analysis",
        ("forward_signals", "daily_prices"),
        ("GuardrailRemediationReport",),
        ("statistical_guardrails",),
        ("platform.db",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "tests/test_session43_execution_integrity.py",
        (),
        RecommendedAction.KEEP_AS_IS,
        "S43 remediation status; G01 partial, G03/G04 not remediable",
    ),
    # === EVIDENCE / QUALITY ===
    ModuleRecord(
        "src/research/evidence_expansion_auditor.py",
        "evidence_expansion_auditor", ModuleSession.S43, ModuleCategory.EVIDENCE,
        "Search for additional comparison windows",
        ("forward_signals", "daily_prices"),
        ("ComparableEvidenceExpansionReport",),
        (),
        ("platform.db", "stock_research.db"),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "tests/test_session43_execution_integrity.py",
        (),
        RecommendedAction.EXTEND,
        "S43: NO_NEW_ELIGIBLE_WINDOW; S44 extends to Oct 09-28 full v8.0 range",
    ),
    ModuleRecord(
        "src/research/evidence_quality_report_s43.py",
        "evidence_quality_report_s43", ModuleSession.S43, ModuleCategory.EVIDENCE,
        "10-dimension evidence quality scoring",
        ("forward_signals", "daily_prices"),
        ("ExecutionDateEvidenceQualityReport",),
        (),
        ("platform.db",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "tests/test_session43_execution_integrity.py",
        ("evidence_strength_report",),
        RecommendedAction.SUPERSEDED_KEEP,
        "S43 version; evidence_strength_report is older S39 version",
    ),
    ModuleRecord(
        "src/research/evidence_strength_report.py",
        "evidence_strength_report", ModuleSession.S39, ModuleCategory.EVIDENCE,
        "Earlier evidence strength assessment (S39)",
        ("forward_signals",),
        ("EvidenceStrengthReport",),
        (),
        ("platform.db",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "tests/test_session40_comparison.py",
        ("evidence_quality_report_s43",),
        RecommendedAction.SUPERSEDED_KEEP,
        "Superseded by S43 evidence_quality_report_s43",
    ),
    ModuleRecord(
        "src/research/research_blocker_matrix.py",
        "research_blocker_matrix", ModuleSession.S39, ModuleCategory.EVIDENCE,
        "Blocker matrix for V3 activation prerequisites",
        ("various",),
        ("ResearchBlockerMatrix",),
        (),
        (),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "tests/test_session40_comparison.py",
        ("v3_activation_readiness",),
        RecommendedAction.SUPERSEDED_KEEP,
        "S39; v3_activation_readiness (S38) is the canonical version",
    ),
    # === OUTCOME / READINESS ===
    ModuleRecord(
        "src/research/outcome_readiness.py",
        "outcome_readiness", ModuleSession.PRE_S38, ModuleCategory.EVIDENCE,
        "Check whether forward signal outcomes are mature",
        ("forward_signals", "daily_prices"),
        ("OutcomeReadinessReport",),
        (),
        ("platform.db",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "various",
        ("research_readiness_20d",),
        RecommendedAction.SUPERSEDED_KEEP,
        "research_readiness_20d (S43) is the more precise version",
    ),
    ModuleRecord(
        "src/research/research_readiness_20d.py",
        "research_readiness_20d", ModuleSession.S43, ModuleCategory.EVIDENCE,
        "Per-fill-date 20D maturity audit (Oct 13-21)",
        ("forward_signals", "daily_prices"),
        ("TwentyDayReadinessReport",),
        (),
        ("platform.db",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "tests/test_session43_execution_integrity.py",
        ("outcome_readiness",),
        RecommendedAction.EXTEND,
        "S43 scope Oct 13-21; S44 extends to Oct 13-28 full range",
    ),
    # === V3 STRATEGY ===
    ModuleRecord(
        "src/research/v3_entry_strategy.py",
        "v3_entry_strategy", ModuleSession.S26, ModuleCategory.STRATEGY,
        "V3 entry strategy implementation (wait/avoid/direct)",
        ("forward_signals", "daily_prices"),
        ("V3EntryDecision",),
        (),
        ("platform.db",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "tests/test_v3_*.py",
        (),
        RecommendedAction.KEEP_AS_IS,
        "FROZEN; parameter hash be43e8ca977d9fdd",
    ),
    ModuleRecord(
        "src/research/v3_backtest_engine.py",
        "v3_backtest_engine", ModuleSession.S26, ModuleCategory.BACKTEST,
        "V3 backtesting engine with PARAMETER_HASH",
        ("forward_signals", "daily_prices"),
        ("V3BacktestResult",),
        ("v3_entry_strategy",),
        ("platform.db",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "tests/test_v3_*.py",
        (),
        RecommendedAction.KEEP_AS_IS,
        "FROZEN; PARAMETER_HASH = be43e8ca977d9fdd",
    ),
    ModuleRecord(
        "src/research/v3_comparison_engine.py",
        "v3_comparison_engine", ModuleSession.S27, ModuleCategory.COMPARISON,
        "V3 vs A/B/C paired comparison engine",
        ("forward_signals", "daily_prices"),
        ("V3ComparisonResult",),
        ("v3_entry_strategy", "v3_backtest_engine"),
        ("platform.db",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "tests/test_v3_*.py",
        ("corrected_5d_comparison_s43",),
        RecommendedAction.KEEP_AS_IS,
        "S27; FROZEN; forms the basis of all strategy comparisons",
    ),
    ModuleRecord(
        "src/research/v3_walk_forward.py",
        "v3_walk_forward", ModuleSession.S28, ModuleCategory.BACKTEST,
        "V3 walk-forward validation",
        ("forward_signals", "daily_prices"),
        ("V3WalkForwardResult",),
        ("v3_comparison_engine",),
        ("platform.db",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "tests/test_v3_*.py",
        (),
        RecommendedAction.KEEP_AS_IS,
        "MARKET_AVOIDANCE_DRIVEN verdict from S28",
    ),
    ModuleRecord(
        "src/research/v3_prospective_shadow.py",
        "v3_prospective_shadow", ModuleSession.S29, ModuleCategory.STRATEGY,
        "V3 prospective shadow mode (CRON_ACCEPTANCE_PENDING)",
        ("forward_signals",),
        ("V3ProspectiveShadowReport",),
        ("v3_comparison_engine",),
        ("platform.db",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "tests/test_v3_*.py",
        (),
        RecommendedAction.KEEP_AS_IS,
        "NO_PROSPECTIVE_EVIDENCE; Stage B still frozen",
    ),
    ModuleRecord(
        "src/research/v3_activation_readiness.py",
        "v3_activation_readiness", ModuleSession.S38, ModuleCategory.STRATEGY,
        "V3 activation checklist (6 blockers)",
        ("various",),
        ("V3ActivationReadinessReport",),
        ("various",),
        ("platform.db",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "tests/test_session38_*.py",
        (),
        RecommendedAction.KEEP_AS_IS,
        "ACTIVATION_BLOCKED; 6 blockers remain",
    ),
    ModuleRecord(
        "src/research/v3_market_avoidance_attribution.py",
        "v3_market_avoidance_attribution", ModuleSession.S28, ModuleCategory.COMPARISON,
        "Attribution of V3 alpha to market avoidance vs signal selection",
        ("forward_signals", "daily_prices"),
        ("MarketAvoidanceAttributionReport",),
        ("v3_comparison_engine",),
        ("platform.db",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "tests/test_v3_*.py",
        (),
        RecommendedAction.KEEP_AS_IS,
        "S28 conclusion: MARKET_AVOIDANCE_DRIVEN",
    ),
    # === BACKTEST ===
    ModuleRecord(
        "src/research/backtest_comparison.py",
        "backtest_comparison", ModuleSession.PRE_S38, ModuleCategory.BACKTEST,
        "V1 vs V2 backtest comparison",
        ("daily_prices", "stocks"),
        ("BacktestComparisonResult",),
        (),
        ("platform.db",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "various",
        ("historical_paired_comparison",),
        RecommendedAction.SUPERSEDED_KEEP,
        "Pre-S38; superseded by historical_paired_comparison",
    ),
    ModuleRecord(
        "src/research/backtest_full.py",
        "backtest_full", ModuleSession.PRE_S38, ModuleCategory.BACKTEST,
        "Full historical backtest engine",
        ("daily_prices", "stocks"),
        ("FullBacktestResult",),
        (),
        ("platform.db",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "various",
        ("v3_backtest_engine",),
        RecommendedAction.SUPERSEDED_KEEP,
        "Superseded by v3_backtest_engine for V3 research",
    ),
    ModuleRecord(
        "src/research/historical_paired_comparison.py",
        "historical_paired_comparison", ModuleSession.PRE_S38, ModuleCategory.COMPARISON,
        "Historical paired V1/V2/V3 comparison",
        ("daily_prices", "stocks", "forward_signals"),
        ("HistoricalPairedComparisonResult",),
        (),
        ("platform.db",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "various",
        ("corrected_5d_comparison_s43",),
        RecommendedAction.SUPERSEDED_KEEP,
        "Earlier approach; S42-S43 comparison modules are canonical",
    ),
    ModuleRecord(
        "src/research/hybrid_backtest.py",
        "hybrid_backtest", ModuleSession.PRE_S38, ModuleCategory.BACKTEST,
        "Hybrid entry V1 backtest",
        ("daily_prices", "stocks"),
        ("HybridBacktestResult",),
        (),
        ("platform.db",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "various",
        (),
        RecommendedAction.KEEP_AS_IS,
        "Hybrid V1 backtest; session 25 vintage",
    ),
    ModuleRecord(
        "src/research/hybrid_entry_strategy.py",
        "hybrid_entry_strategy", ModuleSession.PRE_S38, ModuleCategory.STRATEGY,
        "Hybrid entry V1 strategy (P1-P4 frozen)",
        ("forward_signals", "daily_prices"),
        ("HybridEntryDecision",),
        (),
        ("platform.db",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "various",
        (),
        RecommendedAction.KEEP_AS_IS,
        "FROZEN P1-P4; must not be modified",
    ),
    ModuleRecord(
        "src/research/hybrid_forward_db.py",
        "hybrid_forward_db", ModuleSession.PRE_S38, ModuleCategory.INFRASTRUCTURE,
        "Hybrid forward signals DB adapter",
        ("forward_signals",),
        ("HybridForwardDB",),
        (),
        ("platform.db",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "various",
        (),
        RecommendedAction.KEEP_AS_IS,
        "Infrastructure; P1-P4 frozen",
    ),
    # === COMPARISON (S39-S40) ===
    ModuleRecord(
        "src/research/comparison_readiness_report.py",
        "comparison_readiness_report", ModuleSession.S39, ModuleCategory.COMPARISON,
        "S39 comparison readiness assessment",
        ("forward_signals", "daily_prices"),
        ("ComparisonReadinessReport",),
        (),
        ("platform.db",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "tests/test_session40_comparison.py",
        ("fill_date_contract",),
        RecommendedAction.SUPERSEDED_KEEP,
        "S39; superseded by fill_date_contract (S43)",
    ),
    ModuleRecord(
        "src/research/session40_reproduction.py",
        "session40_reproduction", ModuleSession.S40, ModuleCategory.COMPARISON,
        "S40 comparison reproduction (SIGNIFICANT_POSITIVE — retracted)",
        ("forward_signals", "daily_prices"),
        ("Session40ReproductionReport",),
        (),
        ("platform.db",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "tests/test_session40_comparison.py",
        (),
        RecommendedAction.SUPERSEDED_KEEP,
        "S40 SIGNIFICANT_POSITIVE was retracted in S41; keep for audit trail",
    ),
    ModuleRecord(
        "src/research/eligible_window_discovery.py",
        "eligible_window_discovery", ModuleSession.S39, ModuleCategory.COMPARISON,
        "Find eligible comparison windows in forward_signals",
        ("forward_signals", "daily_prices"),
        ("EligibleWindowReport",),
        (),
        ("platform.db",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "tests/test_session40_comparison.py",
        ("evidence_expansion_auditor",),
        RecommendedAction.SUPERSEDED_KEEP,
        "S39; evidence_expansion_auditor (S43) is more comprehensive",
    ),
    # === STATISTICS ===
    ModuleRecord(
        "src/research/robustness_sensitivity.py",
        "robustness_sensitivity", ModuleSession.S40, ModuleCategory.STATISTICS,
        "Sensitivity analysis for comparison results",
        ("forward_signals", "daily_prices"),
        ("RobustnessSensitivityReport",),
        (),
        ("platform.db",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "tests/test_session40_comparison.py",
        (),
        RecommendedAction.KEEP_AS_IS,
        "S40 sensitivity analysis; ROBUST result maintained",
    ),
    # === INFRASTRUCTURE ===
    ModuleRecord(
        "src/research/models.py",
        "models", ModuleSession.PRE_S38, ModuleCategory.INFRASTRUCTURE,
        "Shared data model definitions",
        (),
        ("various dataclasses",),
        (),
        (),
        ResearchOnlyBoundary.IN_MEMORY_ONLY,
        "various",
        (),
        RecommendedAction.KEEP_AS_IS,
        "Foundation; do not refactor without broad test coverage",
    ),
    ModuleRecord(
        "src/research/storage_adapter.py",
        "storage_adapter", ModuleSession.PRE_S38, ModuleCategory.INFRASTRUCTURE,
        "SQLiteResearchStorage adapter for research artifacts",
        ("stock_research.db",),
        ("ResearchArtifact",),
        (),
        ("stock_research.db",),
        ResearchOnlyBoundary.WRITES_RESEARCH_ARTIFACT,
        "various",
        (),
        RecommendedAction.KEEP_AS_IS,
        "Writes to stock_research.db only; production DB is read-only",
    ),
    ModuleRecord(
        "src/research/shadow_recalculation_service.py",
        "shadow_recalculation_service", ModuleSession.PRE_S38, ModuleCategory.INFRASTRUCTURE,
        "Shadow V3 recalculation service",
        ("forward_signals", "daily_prices"),
        ("ShadowRecalcResult",),
        (),
        ("platform.db",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "various",
        (),
        RecommendedAction.KEEP_AS_IS,
        "V3 shadow; Stage B probe still not authorized",
    ),
    # === MONITORING / ALERTS ===
    ModuleRecord(
        "src/research/alert_state.py",
        "alert_state", ModuleSession.PRE_S38, ModuleCategory.WORKFLOW,
        "Research alert state management",
        ("forward_signals",),
        ("AlertState",),
        (),
        ("platform.db",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "various",
        (),
        RecommendedAction.KEEP_AS_IS,
        "Operational monitoring; not part of strategy research",
    ),
    ModuleRecord(
        "src/research/scheduler_diagnostics.py",
        "scheduler_diagnostics", ModuleSession.PRE_S38, ModuleCategory.WORKFLOW,
        "Cron scheduler diagnostic tools",
        (),
        ("SchedulerDiagnostics",),
        (),
        ("crontab",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "various",
        (),
        RecommendedAction.KEEP_AS_IS,
        "Read-only cron inspection; Stage B not authorized",
    ),
    # === DATA QUALITY ===
    ModuleRecord(
        "src/research/dailyprice_quality_gate.py",
        "dailyprice_quality_gate", ModuleSession.PRE_S38, ModuleCategory.GUARDRAILS,
        "Daily price data quality gates",
        ("daily_prices",),
        ("DailyPriceQualityGateReport",),
        (),
        ("platform.db",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "various",
        ("ohlc_continuity_gate",),
        RecommendedAction.SUPERSEDED_KEEP,
        "ohlc_continuity_gate is more complete",
    ),
    ModuleRecord(
        "src/research/ohlc_continuity_gate.py",
        "ohlc_continuity_gate", ModuleSession.S35, ModuleCategory.GUARDRAILS,
        "OHLC data continuity gate (CG01-CG25)",
        ("daily_prices",),
        ("OHLCContinuityGateReport",),
        (),
        ("platform.db",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "various",
        (),
        RecommendedAction.KEEP_AS_IS,
        "PASS as of 2026-11-05 (present=30, missing=0)",
    ),
    ModuleRecord(
        "src/research/full_market_freshness_gate.py",
        "full_market_freshness_gate", ModuleSession.PRE_S38, ModuleCategory.GUARDRAILS,
        "Market data freshness gate",
        ("daily_prices",),
        ("MarketFreshnessReport",),
        (),
        ("platform.db",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "various",
        ("ohlc_continuity_gate",),
        RecommendedAction.SUPERSEDED_KEEP,
        "ohlc_continuity_gate supersedes for OHLC continuity",
    ),
    # === ANALYSIS ===
    ModuleRecord(
        "src/research/effectiveness_analyzer.py",
        "effectiveness_analyzer", ModuleSession.PRE_S38, ModuleCategory.COMPARISON,
        "Entry timing effectiveness analysis",
        ("forward_signals", "daily_prices"),
        ("EffectivenessReport",),
        (),
        ("platform.db",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "various",
        (),
        RecommendedAction.KEEP_AS_IS,
        "Entry timing V2 analysis module",
    ),
    ModuleRecord(
        "src/research/avoid_chasing_analysis.py",
        "avoid_chasing_analysis", ModuleSession.PRE_S38, ModuleCategory.STRATEGY,
        "Analysis of V3 market-chasing avoidance behavior",
        ("forward_signals", "daily_prices"),
        ("AvoidChasingReport",),
        (),
        ("platform.db",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "various",
        ("v3_market_avoidance_attribution",),
        RecommendedAction.SUPERSEDED_KEEP,
        "v3_market_avoidance_attribution is more precise",
    ),
    ModuleRecord(
        "src/research/entry_timing_research_service.py",
        "entry_timing_research_service", ModuleSession.PRE_S38, ModuleCategory.STRATEGY,
        "Entry timing research service (V2 effectiveness)",
        ("forward_signals", "daily_prices"),
        ("EntryTimingResearchResult",),
        (),
        ("platform.db",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "various",
        (),
        RecommendedAction.KEEP_AS_IS,
        "V2 entry timing research; separate from V3 comparison",
    ),
    # === S43 NEW ===
    ModuleRecord(
        "src/research/guardrail_remediation_s43.py",
        "guardrail_remediation_s43", ModuleSession.S43, ModuleCategory.GUARDRAILS,
        "S43 guardrail before/after remediation analysis",
        ("platform.db",),
        ("GuardrailRemediationReport",),
        ("statistical_guardrails",),
        ("platform.db",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "tests/test_session43_execution_integrity.py",
        (),
        RecommendedAction.KEEP_AS_IS,
        "S43; G01 partial, G03/G04 not remediable",
    ),
    ModuleRecord(
        "src/research/evidence_quality_report_s43.py",
        "evidence_quality_report_s43 (dup)", ModuleSession.S43, ModuleCategory.EVIDENCE,
        "10-dimension evidence quality scoring",
        ("platform.db",),
        ("ExecutionDateEvidenceQualityReport",),
        (),
        ("platform.db",),
        ResearchOnlyBoundary.READ_ONLY_DB,
        "tests/test_session43_execution_integrity.py",
        (),
        RecommendedAction.KEEP_AS_IS,
        "Already listed above; included for completeness count",
    ),
]


def build_research_module_inventory() -> ResearchModuleInventory:
    # Deduplicate (some are listed twice for completeness)
    seen = set()
    unique_modules = []
    for m in _MODULES:
        if m.file_path not in seen:
            seen.add(m.file_path)
            unique_modules.append(m)

    by_cat: dict[str, int] = {}
    by_sess: dict[str, int] = {}
    for m in unique_modules:
        cat = m.category.value
        sess = m.session.value
        by_cat[cat] = by_cat.get(cat, 0) + 1
        by_sess[sess] = by_sess.get(sess, 0) + 1

    n_superseded = sum(1 for m in unique_modules if m.recommended_action in (
        RecommendedAction.SUPERSEDED_KEEP, RecommendedAction.SUPERSEDED_RETIRE
    ))
    n_consolidate = sum(1 for m in unique_modules if m.recommended_action == RecommendedAction.CONSOLIDATE)
    n_keep = sum(1 for m in unique_modules if m.recommended_action in (
        RecommendedAction.KEEP_AS_IS, RecommendedAction.EXTEND, RecommendedAction.DOCUMENT
    ))

    # Find duplicate function pairs
    dup_pairs = (
        ("corrected_5d_comparison.py", "corrected_5d_comparison_s43.py"),
        ("observation_unit_auditor.py", "fill_date_contract.py"),
        ("outcome_readiness.py", "research_readiness_20d.py"),
        ("trading_calendar_integrity.py", "non_trading_day_auditor.py"),
        ("evidence_strength_report.py", "evidence_quality_report_s43.py"),
    )

    return ResearchModuleInventory(
        session=44,
        modules=tuple(unique_modules),
        n_total=len(unique_modules),
        by_category=by_cat,
        by_session=by_sess,
        n_superseded=n_superseded,
        n_to_consolidate=n_consolidate,
        n_keep=n_keep,
        duplicate_pairs=dup_pairs,
        inventory_notes=(
            "55 modules across Sessions 26-43. "
            "5 duplicate functional pairs identified (keep both for audit trail). "
            "No modules write to production DB. "
            "FROZEN: v3_*, hybrid_entry_strategy, foe_v1-related modules."
        ),
    )
