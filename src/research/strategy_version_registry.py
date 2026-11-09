"""
StrategyVersionRegistry — research-only module.

Formally documents the V1 / V2 / Hybrid_V1 / V3 strategy definitions
reconstructed from code analysis.

CRITICAL FINDING (Session 39):
All four strategy variants use the SAME underlying scoring engine (foe_v1 /
MODEL_VERSION v8.0). They differ ONLY in entry timing rules applied AFTER
the scoring engine generates BUY/STRONG_BUY signals.

The user's "V1/V2/V3" question is therefore about entry timing optimization,
not scoring model improvement.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional


REGISTRY_VERSION = "v1.0"
SOURCE_SESSION = "session39"


class VersionStatus(str, Enum):
    VERIFIED = "VERIFIED"
    # Parameters confirmed: code exists, hash stored, frozen state documented

    PARTIAL = "PARTIAL"
    # Core logic found in code but some parameters are undocumented or unversioned

    UNVERIFIED = "UNVERIFIED"
    # Version claimed to exist but no authoritative parameter record found


class ComponentType(str, Enum):
    SCORING_ENGINE = "SCORING_ENGINE"
    # Produces the raw BUY/STRONG_BUY/WAIT/etc. signal scores

    ENTRY_TIMING_FILTER = "ENTRY_TIMING_FILTER"
    # Applied after scoring; determines WHEN to enter

    COMBINED = "COMBINED"
    # Scoring + entry timing packaged together


@dataclass(frozen=True)
class StrategyVersion:
    version_id: str
    display_name: str
    status: VersionStatus
    component_type: ComponentType

    # Strategy logic
    scoring_engine: str           # e.g. "foe_v1 / MODEL_VERSION v8.0"
    entry_rule: str               # e.g. "BUY/STRONG_BUY → NEXT_OPEN"
    exit_rule: str                # e.g. "stop_price or target1 or 20D horizon"
    holding_period: str           # e.g. "max 20 trading days"

    # Verification
    parameter_hash: Optional[str]
    frozen_at: Optional[str]
    frozen_commit: Optional[str]
    code_file: str
    code_class_or_func: str

    # Comparison engine mapping
    comparison_engine_strategy: Optional[str]  # A_direct / B_v1v2 / C_hybrid / D_v3

    # Caveats
    known_limitations: List[str]
    unverified_items: List[str]

    @property
    def is_fully_verified(self) -> bool:
        return self.status == VersionStatus.VERIFIED

    @property
    def has_parameter_hash(self) -> bool:
        return self.parameter_hash is not None


class StrategyVersionRegistry:
    """
    Authoritative registry of V1/V2/Hybrid_V1/V3 strategy definitions.

    All definitions are RECONSTRUCTED from code analysis — no original design
    documents exist. Any item marked PARTIAL or UNVERIFIED must be resolved
    before it can be used in a fair comparison ranking.

    Usage:
        registry = StrategyVersionRegistry()
        v1 = registry.get("v1_signal_only")
        all_versions = registry.all()
    """

    _VERSIONS: Dict[str, StrategyVersion] = {}

    def __init__(self) -> None:
        self._versions = self._build_registry()

    def get(self, version_id: str) -> StrategyVersion:
        if version_id not in self._versions:
            raise KeyError(f"Unknown version_id: {version_id!r}")
        return self._versions[version_id]

    def all(self) -> List[StrategyVersion]:
        return list(self._versions.values())

    def verified_versions(self) -> List[StrategyVersion]:
        return [v for v in self._versions.values()
                if v.status == VersionStatus.VERIFIED]

    def can_compare(self, v1_id: str, v2_id: str) -> bool:
        """True only if BOTH versions are at least PARTIAL status."""
        try:
            a = self.get(v1_id)
            b = self.get(v2_id)
            return (a.status != VersionStatus.UNVERIFIED
                    and b.status != VersionStatus.UNVERIFIED)
        except KeyError:
            return False

    @staticmethod
    def _build_registry() -> Dict[str, StrategyVersion]:
        return {
            "v1_signal_only": StrategyVersion(
                version_id="v1_signal_only",
                display_name="V1 — Signal Only (Original)",
                status=VersionStatus.PARTIAL,
                component_type=ComponentType.ENTRY_TIMING_FILTER,
                scoring_engine="foe_v1 / MODEL_VERSION v8.0",
                entry_rule=(
                    "Take all BUY / STRONG_BUY ForwardSignals (decision_label). "
                    "Enter at D+1 OPEN price (NEXT_OPEN execution). "
                    "No additional entry-timing filter applied."
                ),
                exit_rule="stop_price trigger or target1 hit or 20D horizon",
                holding_period="max 20 trading days",
                parameter_hash=None,
                frozen_at=None,
                frozen_commit=None,
                code_file="src/research/v3_comparison_engine.py",
                code_class_or_func="V3ComparisonEngine._simulate_strategy (STRATEGY_B)",
                comparison_engine_strategy="B_v1v2",
                known_limitations=[
                    "No entry-timing filter — enters regardless of price vs MA20",
                    "Same fwd_return_20d source as V2/V3 (NEXT_OPEN price); "
                    "V1 actual fills not separately tracked",
                    "BUY/STRONG_BUY thresholds defined in foe_v1; threshold history unversioned",
                ],
                unverified_items=[
                    "No parameter hash stored for V1 decision thresholds",
                    "Historical BUY/STRONG_BUY threshold values not recorded",
                    "Transaction cost assumptions not explicitly documented for V1",
                ],
            ),

            "v2_entry_timing": StrategyVersion(
                version_id="v2_entry_timing",
                display_name="V2 — Entry Timing Filtered",
                status=VersionStatus.PARTIAL,
                component_type=ComponentType.ENTRY_TIMING_FILTER,
                scoring_engine="foe_v1 / MODEL_VERSION v8.0",
                entry_rule=(
                    "Take BUY / STRONG_BUY ForwardSignals. "
                    "Apply EntryTimingAnalyzer (entry_timing.py). "
                    "Enter ONLY when entry_label == ENTRY_READY. "
                    "WAIT_FOR_PULLBACK, TOO_EXTENDED etc. → skip. "
                    "Uses MA20 level as primary filter (no MA60, no slope)."
                ),
                exit_rule="stop_price trigger or target1 hit or 20D horizon",
                holding_period="max 20 trading days",
                parameter_hash=None,
                frozen_at=None,
                frozen_commit=None,
                code_file="src/analyzers/entry_timing.py",
                code_class_or_func="EntryTimingAnalyzer.analyze",
                comparison_engine_strategy="B_v1v2",
                known_limitations=[
                    "Return comparison uses ForwardSignal.fwd_return_20d (NEXT_OPEN based); "
                    "V2 actual entry price not simulated separately → returns are lower bounds",
                    "V2ShadowSignal only exists for stocks + dates where foe_v1 generated signals",
                    "V2 missed signals (WAIT_FOR_PULLBACK etc.) not tracked in outcome DB",
                ],
                unverified_items=[
                    "EntryTimingAnalyzer parameters (MA20 thresholds, vol_ratio cutoffs) "
                    "are embedded in code without a parameter hash",
                    "No frozen commit documented for EntryTimingAnalyzer",
                    "Exact V2 definition used in Sessions 23–26 not reconstructable from "
                    "current code if entry_timing.py was modified",
                ],
            ),

            "hybrid_v1": StrategyVersion(
                version_id="hybrid_v1",
                display_name="Hybrid V1 — P1–P4 Rules (Frozen)",
                status=VersionStatus.VERIFIED,
                component_type=ComponentType.ENTRY_TIMING_FILTER,
                scoring_engine="foe_v1 / MODEL_VERSION v8.0",
                entry_rule=(
                    "Take BUY / STRONG_BUY ForwardSignals. "
                    "Apply HybridDecisionService P1–P4 rules: "
                    "P1: Bear + WAIT_FOR_PULLBACK → WAIT_PULLBACK. "
                    "P2: Flat MA20 + WAIT_FOR_PULLBACK → WAIT_PULLBACK. "
                    "P3: (default) all others → DIRECT_NEXT_OPEN. "
                    "P4: WAIT_FOR_BREAKOUT always → DIRECT_NEXT_OPEN. "
                    "Uses V2 label as input + market_regime + ma20_trend."
                ),
                exit_rule="stop_price trigger or target1 hit or 20D horizon",
                holding_period="max 20 trading days",
                parameter_hash="hybrid_v1 (ma20_rising=0.3, ma20_falling=-0.3)",
                frozen_at="2026-11-05T00:00:00",
                frozen_commit="6602c3b",
                code_file="src/research/hybrid_entry_strategy.py",
                code_class_or_func="HybridDecisionService",
                comparison_engine_strategy="C_hybrid",
                known_limitations=[
                    "P1–P4 rules were empirically derived; no independent validation",
                    "Market regime input uses overnight_market_contexts table which may be sparse",
                ],
                unverified_items=[],
            ),

            "v3_entry_timing": StrategyVersion(
                version_id="v3_entry_timing",
                display_name="V3 — Advanced Entry Timing (Research)",
                status=VersionStatus.VERIFIED,
                component_type=ComponentType.ENTRY_TIMING_FILTER,
                scoring_engine="foe_v1 / MODEL_VERSION v8.0",
                entry_rule=(
                    "Take BUY / STRONG_BUY ForwardSignals. "
                    "Apply V3EntryTimingAnalyzer: "
                    "Uses MA20 + MA60 (level AND slope), 3-class volume signature, "
                    "market regime adaptation, multi-setup confidence score. "
                    "Outputs: DIRECT_ENTRY / WAIT_MA20_PULLBACK / WAIT_MA60_SUPPORT / "
                    "WAIT_BREAKOUT_CONFIRMATION / AVOID_CHASING / NO_ENTRY."
                ),
                exit_rule="stop_price trigger or target1 hit or 20D horizon",
                holding_period="max 20 trading days",
                parameter_hash="be43e8ca977d9fdd",
                frozen_at="2026-11-05",
                frozen_commit="6602c3b",
                code_file="src/research/v3_entry_strategy.py",
                code_class_or_func="V3EntryTimingAnalyzer",
                comparison_engine_strategy="D_v3",
                known_limitations=[
                    "In-sample only — 0 out-of-sample windows (Session 28)",
                    "0 genuine prospective decisions (Session 36)",
                    "Market avoidance confirmed as primary driver (Session 28)",
                    "Stock selection advantage not independently isolated",
                ],
                unverified_items=[],
            ),
        }


# ---------------------------------------------------------------------------
# Version comparison eligibility check
# ---------------------------------------------------------------------------

@dataclass
class VersionPairComparability:
    v1_id: str
    v2_id: str
    is_comparable: bool
    shared_scoring_engine: bool
    shared_data_source: bool
    shared_exit_rule: bool
    status: str
    blockers: List[str]


def assess_version_pair(
    registry: StrategyVersionRegistry,
    v1_id: str,
    v2_id: str,
) -> VersionPairComparability:
    try:
        v1 = registry.get(v1_id)
        v2 = registry.get(v2_id)
    except KeyError as e:
        return VersionPairComparability(
            v1_id=v1_id, v2_id=v2_id, is_comparable=False,
            shared_scoring_engine=False, shared_data_source=False,
            shared_exit_rule=False, status="VERSION_NOT_FOUND",
            blockers=[str(e)],
        )

    blockers: List[str] = []

    # Both must be at least PARTIAL
    if v1.status == VersionStatus.UNVERIFIED:
        blockers.append(f"{v1_id}: VERSION_DEFINITION_UNVERIFIED")
    if v2.status == VersionStatus.UNVERIFIED:
        blockers.append(f"{v2_id}: VERSION_DEFINITION_UNVERIFIED")

    # Both must have unverified_items resolved for a strict comparison
    if v1.unverified_items:
        blockers.append(
            f"{v1_id}: {len(v1.unverified_items)} unverified parameters"
        )
    if v2.unverified_items:
        blockers.append(
            f"{v2_id}: {len(v2.unverified_items)} unverified parameters"
        )

    shared_scoring = v1.scoring_engine == v2.scoring_engine
    if not shared_scoring:
        blockers.append("Different scoring engines — comparison conflates scoring vs timing")

    shared_exit = v1.exit_rule == v2.exit_rule
    shared_data = True  # all versions use the same ForwardSignals source

    is_comparable = len(blockers) == 0

    return VersionPairComparability(
        v1_id=v1_id,
        v2_id=v2_id,
        is_comparable=is_comparable,
        shared_scoring_engine=shared_scoring,
        shared_data_source=shared_data,
        shared_exit_rule=shared_exit,
        status="COMPARABLE" if is_comparable else "NOT_COMPARABLE",
        blockers=blockers,
    )
