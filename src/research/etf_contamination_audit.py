"""
ETFContaminationAudit — research-only module.

Quantifies ETF contamination in ForwardSignals using official TWSE/TPEx classification.
Session 38 official-verified finding: 213/2236 v8.0 signals (9.52%) are from ETF securities.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from src.research.security_classification import (
    OfficialUniverse,
    SecurityClassificationService,
    SecurityType,
    SignalAuditResult,
)


AUDIT_VERSION = "v1.0"
SOURCE_SESSION = "session38"


@dataclass(frozen=True)
class ContaminationSummary:
    model_version: str
    total_signals: int
    total_unique_stocks: int

    verified_common_signals: int     # TWSE_COMMON + TPEX_COMMON
    verified_twse_signals: int
    verified_tpex_signals: int
    etf_signals: int                 # ETF_OFFICIAL + ETF_PROBABLE
    delisted_probable_signals: int   # TWSE_COMMON_DELISTED_PROBABLE
    unknown_signals: int             # UNKNOWN

    verified_common_stocks: int
    etf_stocks: int

    @property
    def etf_contamination_pct(self) -> float:
        if self.total_signals == 0:
            return 0.0
        return self.etf_signals / self.total_signals * 100.0

    @property
    def clean_pct(self) -> float:
        if self.total_signals == 0:
            return 0.0
        return self.verified_common_signals / self.total_signals * 100.0

    @property
    def contamination_verdict(self) -> str:
        pct = self.etf_contamination_pct
        if pct == 0.0:
            return "CLEAN"
        if pct < 1.0:
            return "NEGLIGIBLE"
        if pct < 5.0:
            return "MINOR"
        if pct < 15.0:
            return "MODERATE"
        return "SEVERE"


@dataclass
class ETFContaminationAudit:
    """
    Audits ForwardSignals for ETF contamination using official classification.

    Example:
        audit = ETFContaminationAudit(official_universe)
        summary = audit.run(
            signal_stock_ids=fs_stock_ids,
            signal_counts=fs_signal_counts,
            model_version="v8.0",
        )
    """

    service: SecurityClassificationService

    @classmethod
    def from_official(cls, official: OfficialUniverse, master_ids=None) -> "ETFContaminationAudit":
        return cls(service=SecurityClassificationService(official, master_ids))

    def run(
        self,
        signal_stock_ids: Sequence[str],
        model_version: str,
        signal_counts: Optional[Dict[str, int]] = None,
    ) -> ContaminationSummary:
        audit: SignalAuditResult = self.service.audit_signals(
            signal_stock_ids, signal_counts
        )
        verified_twse = (
            audit.signals_by_type.get(SecurityType.TWSE_COMMON_ACTIVE, 0)
            + audit.signals_by_type.get(SecurityType.ORPHAN_TWSE_COMMON, 0)
        )
        verified_tpex = (
            audit.signals_by_type.get(SecurityType.TPEX_COMMON_ACTIVE, 0)
            + audit.signals_by_type.get(SecurityType.ORPHAN_TPEX_COMMON, 0)
        )
        return ContaminationSummary(
            model_version=model_version,
            total_signals=audit.total_signals,
            total_unique_stocks=audit.total_unique_stocks,
            verified_common_signals=verified_twse + verified_tpex,
            verified_twse_signals=verified_twse,
            verified_tpex_signals=verified_tpex,
            etf_signals=audit.etf_signal_count(),
            delisted_probable_signals=audit.signals_by_type.get(
                SecurityType.TWSE_COMMON_DELISTED_PROBABLE, 0
            ),
            unknown_signals=audit.signals_by_type.get(SecurityType.UNKNOWN, 0),
            verified_common_stocks=audit.stocks_by_type.get(SecurityType.TWSE_COMMON_ACTIVE, 0)
            + audit.stocks_by_type.get(SecurityType.TPEX_COMMON_ACTIVE, 0)
            + audit.stocks_by_type.get(SecurityType.ORPHAN_TWSE_COMMON, 0),
            etf_stocks=audit.stocks_by_type.get(SecurityType.ETF_OFFICIAL, 0)
            + audit.stocks_by_type.get(SecurityType.ETF_PROBABLE, 0),
        )

    def etf_stock_ids(self, signal_stock_ids: Sequence[str]) -> List[str]:
        """Return list of ETF stock_ids in the signal set."""
        return sorted(self.service.audit_signals(signal_stock_ids).etf_stock_ids())


@dataclass(frozen=True)
class CleanUniverseDataset:
    """
    Represents a signal dataset filtered to verified common stocks only.
    Used to compare ETF-contaminated vs clean performance analysis.
    """
    model_version: str
    dataset_label: str            # "A_original", "B_clean", "C_sensitivity"
    description: str
    total_signals_original: int
    total_signals_filtered: int
    etf_signals_removed: int
    unique_stocks_filtered: int

    @property
    def filter_pct(self) -> float:
        if self.total_signals_original == 0:
            return 0.0
        return self.etf_signals_removed / self.total_signals_original * 100.0

    @property
    def retained_pct(self) -> float:
        return 100.0 - self.filter_pct


def build_clean_universe_comparison(
    original_summary: ContaminationSummary,
) -> List[CleanUniverseDataset]:
    """
    Build Dataset A, B, C comparison from a ContaminationSummary.

    A = original (all signals including ETF)
    B = clean (verified common stocks only)
    C = sensitivity boundary (all non-ETF — includes probable delisted)
    """
    return [
        CleanUniverseDataset(
            model_version=original_summary.model_version,
            dataset_label="A_original",
            description="All v8.0 valid signals (including ETF and unclassified)",
            total_signals_original=original_summary.total_signals,
            total_signals_filtered=original_summary.total_signals,
            etf_signals_removed=0,
            unique_stocks_filtered=original_summary.total_unique_stocks,
        ),
        CleanUniverseDataset(
            model_version=original_summary.model_version,
            dataset_label="B_clean",
            description="Official-verified common stocks only (TWSE + TPEx); ETF removed",
            total_signals_original=original_summary.total_signals,
            total_signals_filtered=original_summary.verified_common_signals,
            etf_signals_removed=original_summary.etf_signals,
            unique_stocks_filtered=original_summary.verified_common_stocks,
        ),
        CleanUniverseDataset(
            model_version=original_summary.model_version,
            dataset_label="C_sensitivity",
            description="Removes ETF only; retains probable delisted and unknowns for sensitivity check",
            total_signals_original=original_summary.total_signals,
            total_signals_filtered=(
                original_summary.total_signals
                - original_summary.etf_signals
            ),
            etf_signals_removed=original_summary.etf_signals,
            unique_stocks_filtered=(
                original_summary.total_unique_stocks - original_summary.etf_stocks
            ),
        ),
    ]
