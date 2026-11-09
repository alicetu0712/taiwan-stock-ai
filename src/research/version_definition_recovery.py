"""
version_definition_recovery.py — Recover and document V1/V2/V3 parameter definitions.

RESEARCH ONLY. No production changes.

Purpose:
  Session 39 established that V1/V2 are PARTIAL (no parameter hash).
  This module computes parameter hashes from CURRENT CODE and documents them.
  The hashes reflect the code as of Session 40 — not necessarily the exact
  parameters used in Sessions 23-26 (pre-versioning era).

WARNING:
  If V2's EntryTimingAnalyzer was modified between its first use (Session 23)
  and Session 40, the hash computed here does NOT reflect the original parameters.
  The original parameters are UNVERIFIABLE without git history of the specific
  parameter constants.

Status:
  V1: RECOVERED (hash computable from current code — but historical accuracy PARTIAL)
  V2: RECOVERED (hash computable from current code — but historical accuracy PARTIAL)
  Hybrid V1: VERIFIED (frozen at commit 6602c3b, unchanged)
  V3: VERIFIED (frozen at commit 6602c3b, hash be43e8ca977d9fdd)
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class VersionDefinitionStatus(str, Enum):
    VERIFIED = "VERIFIED"           # Frozen commit + hash confirmed unchanged
    RECOVERED = "RECOVERED"         # Hash computed from current code; historical accuracy partial
    PARTIAL = "PARTIAL"             # Parameters documented but hash not computable
    INCOMPLETE = "VERSION_DEFINITION_INCOMPLETE"


@dataclass(frozen=True)
class VersionDefinitionRecord:
    """Complete definition record for one strategy version."""
    version_id: str
    display_name: str
    status: VersionDefinitionStatus
    scoring_engine: str             # always "foe_v1 / MODEL_VERSION v8.0"
    entry_rule: str
    exit_rule: str
    holding_period: str
    benchmark: str
    fees_pct: float
    comparison_engine_strategy: str  # A_direct / B_v1v2 / C_hybrid / D_v3
    parameter_hash: Optional[str]
    frozen_commit: Optional[str]
    code_file: str
    parameters: dict
    limitations: List[str] = field(default_factory=list)
    missing_items: List[str] = field(default_factory=list)


@dataclass
class VersionDefinitionReport:
    """Full recovery report for all versions."""
    versions: List[VersionDefinitionRecord]
    overall_status: VersionDefinitionStatus
    recovery_note: str

    def by_id(self, version_id: str) -> Optional[VersionDefinitionRecord]:
        return next((v for v in self.versions if v.version_id == version_id), None)

    def verified_versions(self) -> List[VersionDefinitionRecord]:
        return [v for v in self.versions if v.status == VersionDefinitionStatus.VERIFIED]

    def can_compare(self, id1: str, id2: str) -> bool:
        v1 = self.by_id(id1)
        v2 = self.by_id(id2)
        if v1 is None or v2 is None:
            return False
        return (
            v1.status in (VersionDefinitionStatus.VERIFIED, VersionDefinitionStatus.RECOVERED)
            and v2.status in (VersionDefinitionStatus.VERIFIED, VersionDefinitionStatus.RECOVERED)
        )


def _compute_v1_hash() -> str:
    params = {
        "strategy": "direct_buy_strong_buy",
        "entry_rule": "trade_signal_in_buy_strong_buy",
        "filter": "none",
        "fill": "next_open",
    }
    return hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:16]


def _compute_v2_hash() -> str:
    # Extracted from src/analyzers/entry_timing.py constants
    params = {
        "ma20_pullback_upper": 0.03,
        "ma20_pullback_lower": -0.05,
        "too_extended_ma20_gap": 15.0,
        "stop_buffer": 0.03,
    }
    return hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:16]


def build_session40_version_definitions() -> VersionDefinitionReport:
    """Build version definition records for all four strategy versions."""

    versions: List[VersionDefinitionRecord] = []

    # ── V1: Signal Only ───────────────────────────────────────────────────────
    versions.append(VersionDefinitionRecord(
        version_id="v1_signal_only",
        display_name="V1 — Signal Only (Original)",
        status=VersionDefinitionStatus.RECOVERED,
        scoring_engine="foe_v1 / MODEL_VERSION v8.0",
        entry_rule="BUY/STRONG_BUY trade_signal → fill at D+1 OPEN (no additional filter)",
        exit_rule="stop_price or target1 or 20D horizon (from forward_signals or reconstructed)",
        holding_period="Up to 20D",
        benchmark="0050",
        fees_pct=0.585,
        comparison_engine_strategy="A_direct",
        parameter_hash=_compute_v1_hash(),
        frozen_commit=None,
        code_file="src/research/v3_comparison_engine.py (STRATEGY_A A_direct simulation)",
        parameters={
            "strategy": "direct_buy_strong_buy",
            "entry_rule": "trade_signal_in_buy_strong_buy",
            "filter": "none",
            "fill": "next_open",
        },
        limitations=[
            "No frozen commit → cannot verify parameters unchanged from Sessions 23-25",
            "trade_signal='buy' includes decision_label='wait_pullback' (57 signals) — historical behavior unclear",
            "Parameter hash computed from current code, not from Session 23 snapshot",
        ],
        missing_items=[
            "Frozen commit hash",
            "Confirmation that trade_signal='buy' was used (vs decision_label='buy') in V1 era",
        ],
    ))

    # ── V2: Entry Timing Filtered ─────────────────────────────────────────────
    versions.append(VersionDefinitionRecord(
        version_id="v2_entry_timing",
        display_name="V2 — Entry Timing Filtered (MA20 Pullback)",
        status=VersionDefinitionStatus.RECOVERED,
        scoring_engine="foe_v1 / MODEL_VERSION v8.0",
        entry_rule=(
            "BUY/STRONG_BUY → EntryTimingAnalyzer → ENTRY_READY only "
            "(MA20 pullback zone: price within -5% to +3% of MA20, "
            "not too extended: MA20 gap < 15%)"
        ),
        exit_rule="stop_price = MA20 × (1 - 3%) or target1 or 20D horizon",
        holding_period="Up to 20D",
        benchmark="0050",
        fees_pct=0.585,
        comparison_engine_strategy="B_v1v2",
        parameter_hash=_compute_v2_hash(),
        frozen_commit=None,
        code_file="src/analyzers/entry_timing.py",
        parameters={
            "ma20_pullback_upper": 0.03,
            "ma20_pullback_lower": -0.05,
            "too_extended_ma20_gap": 15.0,
            "stop_buffer": 0.03,
        },
        limitations=[
            "No frozen commit → cannot verify MA20 thresholds unchanged from Sessions 23-26",
            "WAIT_FOR_PULLBACK label in V2 means 'try-pullback-then-enter' — not currently modeled",
            "effectiveness_analysis.json uses 150-stock sample, not full universe",
            "Parameter hash computed from current code, not from Session 23 snapshot",
        ],
        missing_items=[
            "Frozen commit hash for src/analyzers/entry_timing.py",
            "Confirmation that current MA20 thresholds match Sessions 23-25 usage",
        ],
    ))

    # ── Hybrid V1: P1–P4 Rules ────────────────────────────────────────────────
    versions.append(VersionDefinitionRecord(
        version_id="hybrid_v1",
        display_name="Hybrid V1 — P1–P4 Regime Rules (Frozen)",
        status=VersionDefinitionStatus.VERIFIED,
        scoring_engine="foe_v1 / MODEL_VERSION v8.0",
        entry_rule=(
            "V2 entry_label + market_regime + ma20_trend → P1–P4 rules: "
            "P1: Bear + WAIT_FOR_PULLBACK → WAIT_PULLBACK; "
            "P2: Flat MA20 + WAIT_FOR_PULLBACK → WAIT_PULLBACK; "
            "P3: default → DIRECT_NEXT_OPEN; "
            "P4: WAIT_FOR_BREAKOUT → DIRECT_NEXT_OPEN"
        ),
        exit_rule="stop_price or target1 or 20D horizon",
        holding_period="Up to 20D",
        benchmark="0050",
        fees_pct=0.585,
        comparison_engine_strategy="C_hybrid",
        parameter_hash="ma20_rising=0.3_ma20_falling=-0.3",
        frozen_commit="6602c3b",
        code_file="src/research/hybrid_entry_strategy.py",
        parameters={
            "ma20_rising_threshold": 0.3,
            "ma20_falling_threshold": -0.3,
        },
        limitations=[
            "hybrid_forward_decision table has 21 rows (all RETROSPECTIVE_RECONSTRUCTION) — no live evidence",
            "P1–P4 rules were frozen but their out-of-sample performance is unverified",
        ],
        missing_items=[],
    ))

    # ── V3: Advanced Entry Timing ─────────────────────────────────────────────
    versions.append(VersionDefinitionRecord(
        version_id="v3_entry_timing",
        display_name="V3 — Advanced Entry Timing (MA20+MA60+Slope+Volume, Frozen)",
        status=VersionDefinitionStatus.VERIFIED,
        scoring_engine="foe_v1 / MODEL_VERSION v8.0",
        entry_rule=(
            "V3EntryTimingAnalyzer: MA20+MA60 level+slope+volume+regime → "
            "DIRECT_ENTRY / WAIT_MA20_PULLBACK / WAIT_MA60_SUPPORT / "
            "WAIT_BREAKOUT_CONFIRMATION / AVOID_CHASING / NO_ENTRY"
        ),
        exit_rule="V3 own stop (MA20 × (1-STOP_BUFFER)) or target or 20D horizon",
        holding_period="Up to 20D (or WAIT entry delay)",
        benchmark="0050",
        fees_pct=0.585,
        comparison_engine_strategy="D_v3",
        parameter_hash="be43e8ca977d9fdd",
        frozen_commit="6602c3b",
        code_file="src/research/v3_entry_strategy.py",
        parameters={
            "ma20_rising_threshold": 0.3,
            "ma20_falling_threshold": -0.3,
            "ma60_rising_threshold": 0.1,
            "ma60_falling_threshold": -0.1,
            "stop_buffer": 0.03,
        },
        limitations=[
            "Parameter hash be43e8ca refers to V3EntryTimingAnalyzer parameters, not V3ComparisonEngine",
            "V3ComparisonEngine (PARAMETER_HASH=1feb7a6b294a063d) wraps V3 in a comparison framework",
            "WAIT outcomes are counted as 0% return in comparison engine (no delayed-fill tracking)",
        ],
        missing_items=[],
    ))

    # Overall status
    n_verified = sum(1 for v in versions if v.status == VersionDefinitionStatus.VERIFIED)
    n_recovered = sum(1 for v in versions if v.status == VersionDefinitionStatus.RECOVERED)

    if n_verified == 4:
        overall = VersionDefinitionStatus.VERIFIED
    elif n_verified + n_recovered == 4:
        overall = VersionDefinitionStatus.RECOVERED
    else:
        overall = VersionDefinitionStatus.PARTIAL

    recovery_note = (
        f"{n_verified}/4 versions VERIFIED (Hybrid V1 + V3). "
        f"{n_recovered}/4 versions RECOVERED (V1 + V2: hash computed from current code, "
        f"historical accuracy PARTIAL). "
        "V1/V2 can participate in CONDITIONAL comparison with explicit PARTIAL caveat."
    )

    return VersionDefinitionReport(
        versions=versions,
        overall_status=overall,
        recovery_note=recovery_note,
    )
