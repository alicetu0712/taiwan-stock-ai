"""
UniverseAlignmentAuditor — research-only module.

Verifies alignment across three research phases:
  - Training / in-sample backtest era (Jul 2024 – May 2026)
  - Walk-forward validation era
  - Forward / prospective signal era (Oct 2026+)

Key concern: if the signal computation universe differs between training and
forward phases, model performance comparisons are biased.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List


AUDITOR_VERSION = "v1.0"


class AlignmentStatus(str, Enum):
    ALIGNED = "ALIGNED"
    # Universe composition is consistent across all phases

    PARTIAL_MISMATCH = "PARTIAL_MISMATCH"
    # Minor differences (e.g. new IPOs) that don't invalidate comparison

    SIGNIFICANT_MISMATCH = "SIGNIFICANT_MISMATCH"
    # Substantial universe differences that bias cross-phase comparisons

    UNVERIFIABLE = "UNVERIFIABLE"
    # Insufficient data to assess alignment


@dataclass(frozen=True)
class PhaseUniverse:
    """Describes the stock universe used in one research phase."""
    phase_name: str
    date_range: str
    total_stocks: int
    twse_common_count: int
    tpex_common_count: int
    etf_count: int
    delisted_probable_count: int
    unknown_count: int
    notes: str = ""

    @property
    def common_stock_count(self) -> int:
        return self.twse_common_count + self.tpex_common_count

    @property
    def etf_contamination_pct(self) -> float:
        if self.total_stocks == 0:
            return 0.0
        return self.etf_count / self.total_stocks * 100.0


@dataclass
class AlignmentGap:
    dimension: str          # e.g. "ETF contamination", "TPEx inclusion", "Stock count"
    training_value: str
    forward_value: str
    severity: str           # HIGH / MEDIUM / LOW
    implication: str


@dataclass
class UniverseAlignmentReport:
    training_phase: PhaseUniverse
    forward_phase: PhaseUniverse
    status: AlignmentStatus
    gaps: List[AlignmentGap]
    overall_verdict: str

    @property
    def has_critical_gaps(self) -> bool:
        return any(g.severity == "HIGH" for g in self.gaps)


class UniverseAlignmentAuditor:
    """
    Compares universe composition across research phases.

    Usage:
        auditor = UniverseAlignmentAuditor()
        report = auditor.build_report(training_phase, forward_phase)
    """

    SEVERITY_THRESHOLDS = {
        "etf_pct_delta": 5.0,       # >5% ETF shift is HIGH severity
        "stock_count_ratio": 0.70,   # <70% stock count retained is HIGH severity
        "tpex_delta": 50,            # >50 TPEx stocks added/removed is HIGH severity
    }

    def build_report(
        self,
        training_phase: PhaseUniverse,
        forward_phase: PhaseUniverse,
    ) -> UniverseAlignmentReport:
        gaps: List[AlignmentGap] = []

        # --- Gap 1: Stock count ---
        ratio = (
            forward_phase.total_stocks / training_phase.total_stocks
            if training_phase.total_stocks > 0 else 0.0
        )
        if ratio < self.SEVERITY_THRESHOLDS["stock_count_ratio"]:
            gaps.append(AlignmentGap(
                dimension="Total stock count",
                training_value=str(training_phase.total_stocks),
                forward_value=str(forward_phase.total_stocks),
                severity="HIGH",
                implication=(
                    f"Forward phase uses only {ratio:.0%} of training universe. "
                    "Signal distribution may differ substantially."
                ),
            ))

        # --- Gap 2: ETF contamination ---
        etf_delta = forward_phase.etf_contamination_pct - training_phase.etf_contamination_pct
        if abs(etf_delta) > self.SEVERITY_THRESHOLDS["etf_pct_delta"]:
            severity = "HIGH"
        elif abs(etf_delta) > 1.0:
            severity = "MEDIUM"
        else:
            severity = "LOW"
        if abs(etf_delta) > 0.5:
            gaps.append(AlignmentGap(
                dimension="ETF contamination rate",
                training_value=f"{training_phase.etf_contamination_pct:.1f}%",
                forward_value=f"{forward_phase.etf_contamination_pct:.1f}%",
                severity=severity,
                implication=(
                    "ETF presence in signals creates non-common-stock exposure "
                    "that inflates or deflates measured returns."
                ),
            ))

        # --- Gap 3: TPEx inclusion ---
        tpex_delta = forward_phase.tpex_common_count - training_phase.tpex_common_count
        if abs(tpex_delta) > self.SEVERITY_THRESHOLDS["tpex_delta"]:
            severity = "HIGH"
        elif abs(tpex_delta) > 0:
            severity = "MEDIUM"
        else:
            severity = "LOW"
        if abs(tpex_delta) > 0:
            gaps.append(AlignmentGap(
                dimension="TPEx common stock inclusion",
                training_value=str(training_phase.tpex_common_count),
                forward_value=str(forward_phase.tpex_common_count),
                severity=severity,
                implication=(
                    "Adding TPEx stocks to forward phase introduces ~897 new securities "
                    "not seen in training. Model was not trained on TPEx behavior."
                ),
            ))

        # --- Gap 4: Probable delisted in training ---
        if training_phase.delisted_probable_count > 0:
            gaps.append(AlignmentGap(
                dimension="Probable delisted in training universe",
                training_value=str(training_phase.delisted_probable_count),
                forward_value=str(forward_phase.delisted_probable_count),
                severity="MEDIUM",
                implication=(
                    "Delisted stocks in training pool introduce survivorship bias: "
                    "stocks that survived are overrepresented."
                ),
            ))

        # Determine overall status
        if not gaps:
            status = AlignmentStatus.ALIGNED
            verdict = "ALIGNED: No significant universe differences detected."
        elif any(g.severity == "HIGH" for g in gaps):
            status = AlignmentStatus.SIGNIFICANT_MISMATCH
            verdict = (
                "SIGNIFICANT_MISMATCH: "
                + "; ".join(g.dimension for g in gaps if g.severity == "HIGH")
                + " — cross-phase performance comparisons are unreliable."
            )
        else:
            status = AlignmentStatus.PARTIAL_MISMATCH
            verdict = (
                "PARTIAL_MISMATCH: Minor differences present. "
                "Comparisons conditional on noted caveats."
            )

        return UniverseAlignmentReport(
            training_phase=training_phase,
            forward_phase=forward_phase,
            status=status,
            gaps=gaps,
            overall_verdict=verdict,
        )


# ---------------------------------------------------------------------------
# Platform-specific known values (from Session 37/38 data gathering)
# ---------------------------------------------------------------------------

def build_session38_training_phase() -> PhaseUniverse:
    """
    Training era (Jul 2024 – May 2026): TWSE-only, clean master.
    ~720 stocks/day from the 826-entry stocks master.
    ETF count: 11 ETFs in master but excluded from common-stock strategy signals
    (they were not in the signal universe during this era per Session 37 data).
    """
    return PhaseUniverse(
        phase_name="Training / In-sample Backtest",
        date_range="2024-07-01 – 2026-05-30",
        total_stocks=720,
        twse_common_count=720,
        tpex_common_count=0,
        etf_count=0,
        delisted_probable_count=0,
        unknown_count=0,
        notes=(
            "~720 stocks/day from TWSE master during backtest era. "
            "ETFs were present in master (11) but not in signal pool for this era. "
            "TPEx entirely absent from master and signals."
        ),
    )


def build_session38_forward_phase() -> PhaseUniverse:
    """
    Forward signal era (Oct 12–28, 2026): mixed universe.
    394 master stocks + 203 TWSE orphans + 42 ETF-confirmed → ~639 unique stocks
    giving 2236 ForwardSignals v8.0.
    """
    return PhaseUniverse(
        phase_name="Forward / Prospective Signal Era",
        date_range="2026-10-12 – 2026-10-28",
        total_stocks=410,       # unique stock_ids in v8.0 FS
        twse_common_count=368,  # officially verified TWSE common (368 unique stocks)
        tpex_common_count=0,    # zero TPEx in ForwardSignals
        etf_count=42,           # confirmed ETF (all 0-prefix, official-verified not common)
        delisted_probable_count=0,
        unknown_count=0,
        notes=(
            "410 unique stock_ids in v8.0 FS: 368 TWSE common + 42 confirmed ETF. "
            "0 TPEx despite 895 TPEx stocks present as orphans in daily_prices. "
            "Only 394 of 826 master stocks appeared on signal dates (48% coverage). "
            "TRAIN-TEST UNIVERSE MISMATCH confirmed."
        ),
    )
