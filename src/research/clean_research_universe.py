"""
CleanResearchUniverseBuilder — research-only module.

Builds three canonical research signal datasets (A/B/C) using official
TWSE/TPEx classification from SecurityClassificationService (Session 38).

Dataset A — Original: all signals, no security-type filtering
Dataset B — Verified Common: TWSE / TPEx official common stocks only
Dataset C — Sensitivity: common stocks + UNKNOWN (excludes only confirmed ETFs)

No writes to any production table.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Dict, FrozenSet, List, Optional, Sequence

from src.research.security_classification import (
    OfficialUniverse,
    SecurityClassificationService,
    SecurityType,
)


BUILDER_VERSION = "v1.0"
SOURCE_SESSION = "session39"

_COMMON_TYPES: FrozenSet[SecurityType] = frozenset({
    SecurityType.TWSE_COMMON_ACTIVE,
    SecurityType.TPEX_COMMON_ACTIVE,
    SecurityType.ORPHAN_TWSE_COMMON,
    SecurityType.ORPHAN_TPEX_COMMON,
})
_ETF_TYPES: FrozenSet[SecurityType] = frozenset({
    SecurityType.ETF_OFFICIAL,
    SecurityType.ETF_PROBABLE,
})


class DatasetLabel(str, Enum):
    A_ORIGINAL = "A_original"
    B_VERIFIED_COMMON = "B_verified_common"
    C_SENSITIVITY = "C_sensitivity"


@dataclass
class SignalRecord:
    """Minimal representation of one signal for dataset building."""
    signal_id: str
    stock_id: str
    trade_date: str
    model_version: str
    decision_label: Optional[str] = None
    is_valid: bool = True


@dataclass
class DatasetDescriptor:
    """Fully described signal dataset with provenance metadata."""
    label: DatasetLabel
    version: str
    source_session: str
    source_date: str
    classification_snapshot_session: str
    description: str

    # Counts
    total_signals: int
    stock_count: int
    twse_signal_count: int
    tpex_signal_count: int
    etf_signal_count: int
    unknown_signal_count: int
    delisted_probable_count: int

    # Universe
    unique_dates: List[str]
    model_versions_included: List[str]

    # Exclusions applied (for B and C datasets)
    exclusion_reasons: List[str]

    # Fingerprint
    data_fingerprint: str

    @property
    def trading_date_count(self) -> int:
        return len(self.unique_dates)

    @property
    def etf_exclusion_pct(self) -> float:
        total_in_original = (
            self.total_signals + self.etf_signal_count
            if self.label != DatasetLabel.A_ORIGINAL else self.total_signals
        )
        if total_in_original == 0:
            return 0.0
        return self.etf_signal_count / total_in_original * 100.0

    def to_dict(self) -> Dict:
        return {
            "label": self.label.value,
            "version": self.version,
            "source_session": self.source_session,
            "total_signals": self.total_signals,
            "stock_count": self.stock_count,
            "twse_signal_count": self.twse_signal_count,
            "tpex_signal_count": self.tpex_signal_count,
            "etf_signal_count": self.etf_signal_count,
            "unknown_signal_count": self.unknown_signal_count,
            "data_fingerprint": self.data_fingerprint,
        }


def _fingerprint(records: Sequence[SignalRecord]) -> str:
    ids = sorted(f"{r.stock_id}:{r.trade_date}" for r in records)
    blob = json.dumps(ids, sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


class CleanResearchUniverseBuilder:
    """
    Builds Dataset A/B/C from a list of SignalRecords using official classification.

    Usage:
        builder = CleanResearchUniverseBuilder(official_universe)
        datasets = builder.build_all(signals, source_date="2026-11-08")
    """

    def __init__(
        self,
        official: OfficialUniverse,
        master_ids: Optional[FrozenSet[str]] = None,
    ) -> None:
        self._svc = SecurityClassificationService(official, master_ids)
        self._official = official

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def build_all(
        self,
        signals: Sequence[SignalRecord],
        source_date: str = "unknown",
        model_version_filter: Optional[str] = None,
    ) -> Dict[DatasetLabel, DatasetDescriptor]:
        working = [s for s in signals if model_version_filter is None
                   or s.model_version == model_version_filter]

        a = self._build_dataset_a(working, source_date)
        b = self._build_dataset_b(working, source_date)
        c = self._build_dataset_c(working, source_date)
        return {DatasetLabel.A_ORIGINAL: a,
                DatasetLabel.B_VERIFIED_COMMON: b,
                DatasetLabel.C_SENSITIVITY: c}

    # ------------------------------------------------------------------ #
    # Dataset builders                                                     #
    # ------------------------------------------------------------------ #

    def _build_dataset_a(
        self, signals: Sequence[SignalRecord], source_date: str
    ) -> DatasetDescriptor:
        classified = self._classify_signals(signals)
        return DatasetDescriptor(
            label=DatasetLabel.A_ORIGINAL,
            version=BUILDER_VERSION,
            source_session=SOURCE_SESSION,
            source_date=source_date,
            classification_snapshot_session="session38",
            description=(
                "All valid signals with no security-type filtering. "
                "Includes ETFs and unverified securities. "
                "Matches the state of the platform at signal generation time."
            ),
            total_signals=len(signals),
            stock_count=len({s.stock_id for s in signals}),
            twse_signal_count=classified["twse"],
            tpex_signal_count=classified["tpex"],
            etf_signal_count=classified["etf"],
            unknown_signal_count=classified["unknown"],
            delisted_probable_count=classified["delisted"],
            unique_dates=sorted({s.trade_date for s in signals}),
            model_versions_included=sorted({s.model_version for s in signals}),
            exclusion_reasons=[],
            data_fingerprint=_fingerprint(signals),
        )

    def _build_dataset_b(
        self, signals: Sequence[SignalRecord], source_date: str
    ) -> DatasetDescriptor:
        filtered = [s for s in signals if self._is_common_stock(s.stock_id)]
        classified = self._classify_signals(filtered)
        etf_removed = sum(1 for s in signals if self._is_etf(s.stock_id))
        unknown_removed = sum(1 for s in signals
                              if self._classify(s.stock_id) == SecurityType.UNKNOWN)
        delisted_removed = sum(1 for s in signals
                               if self._classify(s.stock_id)
                               == SecurityType.TWSE_COMMON_DELISTED_PROBABLE)
        return DatasetDescriptor(
            label=DatasetLabel.B_VERIFIED_COMMON,
            version=BUILDER_VERSION,
            source_session=SOURCE_SESSION,
            source_date=source_date,
            classification_snapshot_session="session38",
            description=(
                "Official TWSE / TPEx common stocks only. "
                "ETF (ETF_OFFICIAL + ETF_PROBABLE), TWSE_COMMON_DELISTED_PROBABLE, "
                "and UNKNOWN securities excluded. "
                "Recommended dataset for all future research."
            ),
            total_signals=len(filtered),
            stock_count=len({s.stock_id for s in filtered}),
            twse_signal_count=classified["twse"],
            tpex_signal_count=classified["tpex"],
            etf_signal_count=0,
            unknown_signal_count=0,
            delisted_probable_count=0,
            unique_dates=sorted({s.trade_date for s in filtered}),
            model_versions_included=sorted({s.model_version for s in filtered}),
            exclusion_reasons=[
                f"ETF (ETF_OFFICIAL + ETF_PROBABLE): {etf_removed} signals removed",
                f"TWSE_COMMON_DELISTED_PROBABLE: {delisted_removed} signals removed",
                f"UNKNOWN: {unknown_removed} signals removed",
            ],
            data_fingerprint=_fingerprint(filtered),
        )

    def _build_dataset_c(
        self, signals: Sequence[SignalRecord], source_date: str
    ) -> DatasetDescriptor:
        """
        Sensitivity dataset: remove confirmed ETFs, retain UNKNOWN (for sensitivity analysis).
        UNKNOWN securities are explicitly NOT treated as common stocks — they are
        included only to measure the sensitivity of results to this boundary.
        """
        filtered = [s for s in signals if not self._is_etf(s.stock_id)
                    and self._classify(s.stock_id)
                    != SecurityType.TWSE_COMMON_DELISTED_PROBABLE]
        classified = self._classify_signals(filtered)
        etf_removed = sum(1 for s in signals if self._is_etf(s.stock_id))
        return DatasetDescriptor(
            label=DatasetLabel.C_SENSITIVITY,
            version=BUILDER_VERSION,
            source_session=SOURCE_SESSION,
            source_date=source_date,
            classification_snapshot_session="session38",
            description=(
                "Sensitivity boundary: verified common stocks + UNKNOWN securities. "
                "UNKNOWN securities are NOT classified as common stocks — "
                "this dataset exists to measure result sensitivity to the ETF-only exclusion. "
                "Do NOT use as primary research dataset."
            ),
            total_signals=len(filtered),
            stock_count=len({s.stock_id for s in filtered}),
            twse_signal_count=classified["twse"],
            tpex_signal_count=classified["tpex"],
            etf_signal_count=0,
            unknown_signal_count=classified["unknown"],
            delisted_probable_count=0,
            unique_dates=sorted({s.trade_date for s in filtered}),
            model_versions_included=sorted({s.model_version for s in filtered}),
            exclusion_reasons=[
                f"ETF (ETF_OFFICIAL + ETF_PROBABLE): {etf_removed} signals removed",
                "TWSE_COMMON_DELISTED_PROBABLE: removed (look-ahead risk)",
                "NOTE: UNKNOWN securities RETAINED for sensitivity analysis only",
            ],
            data_fingerprint=_fingerprint(filtered),
        )

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _classify(self, stock_id: str) -> SecurityType:
        return self._svc.classify(stock_id).security_type

    def _is_common_stock(self, stock_id: str) -> bool:
        return self._classify(stock_id) in _COMMON_TYPES

    def _is_etf(self, stock_id: str) -> bool:
        return self._classify(stock_id) in _ETF_TYPES

    def _classify_signals(self, signals: Sequence[SignalRecord]) -> Dict[str, int]:
        counts: Dict[str, int] = {
            "twse": 0, "tpex": 0, "etf": 0, "unknown": 0, "delisted": 0
        }
        for s in signals:
            t = self._classify(s.stock_id)
            if t in (SecurityType.TWSE_COMMON_ACTIVE, SecurityType.ORPHAN_TWSE_COMMON):
                counts["twse"] += 1
            elif t in (SecurityType.TPEX_COMMON_ACTIVE, SecurityType.ORPHAN_TPEX_COMMON):
                counts["tpex"] += 1
            elif t in _ETF_TYPES:
                counts["etf"] += 1
            elif t == SecurityType.TWSE_COMMON_DELISTED_PROBABLE:
                counts["delisted"] += 1
            else:
                counts["unknown"] += 1
        return counts
