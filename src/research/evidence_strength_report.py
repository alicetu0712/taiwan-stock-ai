"""
PART I: V3 Evidence Strength Report — Session 41.

Compiles evidence across all sessions (S27-S41) and delivers final verdict.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import Enum


class EvidenceLevel(str, Enum):
    STRONG = "STRONG"
    MODERATE = "MODERATE"
    WEAK = "WEAK"
    ABSENT = "ABSENT"
    CONFLICTED = "CONFLICTED"


class RankingVerdict(str, Enum):
    RANKING_SUPPORTED = "RANKING_SUPPORTED"
    RANKING_CONDITIONAL = "RANKING_CONDITIONAL"
    RANKING_NOT_SUPPORTED = "RANKING_NOT_SUPPORTED"


@dataclass(frozen=True)
class EvidenceDimension:
    dimension: str
    session: int
    finding: str
    evidence_level: EvidenceLevel
    limitations: str


@dataclass(frozen=True)
class V3EvidenceStrengthReport:
    session: int
    dimensions: tuple[EvidenceDimension, ...]
    statistical_confidence: str
    regime_diversity: str
    attribution_identifiability: str
    ranking_verdict: RankingVerdict
    activation_verdict: str
    summary: str


def build_evidence_strength_report(conn: sqlite3.Connection) -> V3EvidenceStrengthReport:
    dimensions = (
        EvidenceDimension(
            dimension="in_sample_5d",
            session=27,
            finding=(
                "D_v3 vs A_direct: uncorrected delta +3.66%, p=0.0 (274 signals). "
                "Cluster-corrected (S41): p=0.1791, CI=[-3.95%,+16.93%] → SIGNIFICANCE_INCONCLUSIVE."
            ),
            evidence_level=EvidenceLevel.WEAK,
            limitations=(
                "7 trading dates, single regime, in-sample scoring. "
                "Bootstrap CI overconfident (treats 274 as independent). "
                "Formal cluster correction downgrades SIGNIFICANT_POSITIVE."
            ),
        ),
        EvidenceDimension(
            dimension="v1_vs_v2_effectiveness",
            session=40,
            finding=(
                "effectiveness_analysis.json N=2953, V2-V1 delta=+0.0572%, "
                "CI=[-0.046%,+0.157%], CI includes zero. NOT significant."
            ),
            evidence_level=EvidenceLevel.WEAK,
            limitations=(
                "150-stock simulated sample. CI includes zero. "
                "2/10 windows significant (W2, W8) — insufficient consistency."
            ),
        ),
        EvidenceDimension(
            dimension="walk_forward_v3",
            session=28,
            finding=(
                "10/10 WF windows PASS. Net return +1.33%. "
                "MARKET_AVOIDANCE_DRIVEN verdict. INSUFFICIENT_EVIDENCE."
            ),
            evidence_level=EvidenceLevel.WEAK,
            limitations=(
                "Walk-forward windows use same foe_v1 in-sample scoring. "
                "Market avoidance, not entry timing selection. "
                "Regime overlap not controlled."
            ),
        ),
        EvidenceDimension(
            dimension="prospective_shadow",
            session=29,
            finding="FRAMEWORK_READY. NO_PROSPECTIVE_EVIDENCE. CRON_ACCEPTANCE_PENDING.",
            evidence_level=EvidenceLevel.ABSENT,
            limitations=(
                "No real prospective data yet. Cron frozen. "
                "V3 not activated in production."
            ),
        ),
        EvidenceDimension(
            dimension="market_avoidance_attribution",
            session=41,
            finding=(
                "0050 avg -2.16% per date (actual; S40 doc -4.65% was incorrect). "
                "Fill rate 68.6% → exposure reduction ~0.67ppt (corrected estimate). "
                "AVOID_CHASING n=41 mean A_direct -3.87%; NO_ENTRY n=13 mean A_direct -4.30%. "
                "Attribution: MARKET_AVOIDANCE_DRIVEN (confirmed)."
            ),
            evidence_level=EvidenceLevel.MODERATE,
            limitations=(
                "Association, not causation. "
                "Avoidance only helps during market decline. "
                "No evidence of avoidance quality in bull markets."
            ),
        ),
        EvidenceDimension(
            dimension="stock_selection",
            session=41,
            finding=(
                "V3 and all baselines use identical foe_v1 scoring. "
                "DIRECT_ENTRY n=82 mean alpha +2.86% — but confounded by exit rule. "
                "STOCK_SELECTION_UNIDENTIFIABLE."
            ),
            evidence_level=EvidenceLevel.ABSENT,
            limitations=(
                "Identical scoring engine. Exit rule difference not isolated. "
                "Cannot attribute within-invested outperformance to stock selection."
            ),
        ),
        EvidenceDimension(
            dimension="entry_timing",
            session=41,
            finding=(
                "WAIT decisions result in 0% return in comparison engine "
                "(no fill = no contribution). "
                "Cannot track if delayed fills outperform. "
                "ENTRY_TIMING_UNIDENTIFIABLE."
            ),
            evidence_level=EvidenceLevel.ABSENT,
            limitations=(
                "Comparison engine architecture prevents entry timing measurement. "
                "WAIT_BREAKOUT_CONF n=73 alpha +3.92% is market avoidance, not entry timing."
            ),
        ),
        EvidenceDimension(
            dimension="robustness_lodo",
            session=41,
            finding=(
                "LODO (7 dates): sign never changes → DIRECTIONALLY_STABLE. "
                "But CI always includes zero in LODO. "
                "LODO grand means range: 2.45% to 7.83%."
            ),
            evidence_level=EvidenceLevel.WEAK,
            limitations=(
                "Wide LODO range indicates instability in magnitude. "
                "2 micro-cluster dates (n=4) drive variance. "
                "Dropping them collapses grand mean to ~1.12%."
            ),
        ),
    )

    return V3EvidenceStrengthReport(
        session=41,
        dimensions=dimensions,
        statistical_confidence="STATISTICAL_CONFIDENCE_UNVERIFIED — cluster-corrected CI includes zero",
        regime_diversity="SINGLE_REGIME — all signals in bull→declining Oct 2026",
        attribution_identifiability="MARKET_AVOIDANCE_DRIVEN — stock selection & entry timing unidentifiable",
        ranking_verdict=RankingVerdict.RANKING_CONDITIONAL,
        activation_verdict="ACTIVATION_BLOCKED — 6 open blockers, cron frozen, V3 not activated",
        summary=(
            "V3 shows directional positive evidence on 5D horizon in Oct 2026 declining market. "
            "However, statistical significance cannot be confirmed with only 7 trading dates. "
            "The advantage is driven by market avoidance during a brief market decline — "
            "not by superior stock selection or entry timing. "
            "Minimum requirement for RANKING_SUPPORTED: "
            "≥25 independent dates, multi-regime coverage, cluster-corrected CI excludes zero."
        ),
    )
