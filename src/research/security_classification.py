"""
SecurityClassificationService — research-only module.

Classifies stock_ids using official TWSE/TPEx OpenAPI sources.
Per Session 38 requirement: classification MUST use official source data as primary;
code-length heuristics are only applied as fallback with explicit uncertainty labels.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, FrozenSet, Iterator, Mapping, Optional, Sequence


SC_VERSION = "v1.0"
SOURCE_DATE = "2026-11-08"


class SecurityType(str, Enum):
    TWSE_COMMON_ACTIVE = "TWSE_COMMON_ACTIVE"
    # Stock appears in TWSE official common stock list (上市公司基本資料)

    TPEX_COMMON_ACTIVE = "TPEX_COMMON_ACTIVE"
    # Stock appears in TPEx official common stock list (上櫃公司基本資料)

    ETF_OFFICIAL = "ETF_OFFICIAL"
    # Stock is in TWSE 0-prefix group and confirmed NOT in TWSE/TPEx common lists;
    # name data in platform confirms ETF identity (元大台灣50, 富邦科技, etc.)

    ETF_PROBABLE = "ETF_PROBABLE"
    # 0-prefix 5/6-digit code, not in any official common stock list;
    # very likely ETF/leveraged ETF based on Taiwan exchange naming conventions
    # but NOT name-verified in our master

    TWSE_COMMON_DELISTED_PROBABLE = "TWSE_COMMON_DELISTED_PROBABLE"
    # 4-digit code, NOT in current TWSE API → likely delisted TWSE common stock
    # Cannot confirm without historical delisting records

    ORPHAN_TWSE_COMMON = "ORPHAN_TWSE_COMMON"
    # In current TWSE official list, but NOT in platform's stocks master table
    # Present in daily_prices as orphan record

    ORPHAN_TPEX_COMMON = "ORPHAN_TPEX_COMMON"
    # In current TPEx official list, but NOT in platform's stocks master table

    UNKNOWN = "UNKNOWN"
    # Cannot classify by any available method


CONFIDENCE = {
    SecurityType.TWSE_COMMON_ACTIVE: "HIGH",
    SecurityType.TPEX_COMMON_ACTIVE: "HIGH",
    SecurityType.ETF_OFFICIAL: "HIGH",
    SecurityType.ETF_PROBABLE: "MEDIUM",
    SecurityType.TWSE_COMMON_DELISTED_PROBABLE: "MEDIUM",
    SecurityType.ORPHAN_TWSE_COMMON: "HIGH",
    SecurityType.ORPHAN_TPEX_COMMON: "HIGH",
    SecurityType.UNKNOWN: "LOW",
}

# 4-digit 0-prefix ETFs that appear in our stocks master with verified names.
# These are name-verified via the stocks.name field.
MASTER_VERIFIED_ETF_IDS: FrozenSet[str] = frozenset({
    "0050", "0051", "0052", "0053", "0055", "0056", "0057",
    "0060", "0061", "0080", "0081",
})


@dataclass(frozen=True)
class ClassifiedSecurity:
    stock_id: str
    security_type: SecurityType
    confidence: str
    in_master: bool
    source_note: str


@dataclass
class OfficialUniverse:
    """Holds the two official common stock universes fetched from TWSE/TPEx APIs."""
    twse_ids: FrozenSet[str]
    tpex_ids: FrozenSet[str]
    source_date: str = SOURCE_DATE
    twse_count: int = field(init=False)
    tpex_count: int = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "twse_count", len(self.twse_ids))
        object.__setattr__(self, "tpex_count", len(self.tpex_ids))

    @property
    def all_common_ids(self) -> FrozenSet[str]:
        return self.twse_ids | self.tpex_ids


class SecurityClassificationService:
    """
    Classifies platform stock_ids against official TWSE/TPEx universe.

    Usage (research-only):
        service = SecurityClassificationService(official_universe, master_ids)
        result = service.classify("2330")   # → TWSE_COMMON_ACTIVE
        result = service.classify("0050")   # → ETF_OFFICIAL
    """

    def __init__(
        self,
        official: OfficialUniverse,
        master_ids: Optional[FrozenSet[str]] = None,
    ) -> None:
        self._official = official
        self._master_ids: FrozenSet[str] = master_ids or frozenset()

    # ------------------------------------------------------------------ #
    # Core classification                                                  #
    # ------------------------------------------------------------------ #

    def classify(self, stock_id: str) -> ClassifiedSecurity:
        in_master = stock_id in self._master_ids

        if stock_id in self._official.twse_ids:
            if in_master:
                return ClassifiedSecurity(
                    stock_id, SecurityType.TWSE_COMMON_ACTIVE, "HIGH", True,
                    "In TWSE official common stock list; in platform master"
                )
            return ClassifiedSecurity(
                stock_id, SecurityType.ORPHAN_TWSE_COMMON, "HIGH", False,
                "In TWSE official common stock list; NOT in platform master (orphan)"
            )

        if stock_id in self._official.tpex_ids:
            if in_master:
                return ClassifiedSecurity(
                    stock_id, SecurityType.TPEX_COMMON_ACTIVE, "HIGH", True,
                    "In TPEx official common stock list; in platform master"
                )
            return ClassifiedSecurity(
                stock_id, SecurityType.ORPHAN_TPEX_COMMON, "HIGH", False,
                "In TPEx official common stock list; NOT in platform master (orphan)"
            )

        # Not in any official common stock list — apply heuristics with explicit labels
        if stock_id in MASTER_VERIFIED_ETF_IDS:
            return ClassifiedSecurity(
                stock_id, SecurityType.ETF_OFFICIAL, "HIGH", in_master,
                "0-prefix; NOT in TWSE/TPEx common lists; name-verified as ETF in platform master"
            )

        if stock_id.startswith("0"):
            return ClassifiedSecurity(
                stock_id, SecurityType.ETF_PROBABLE, "MEDIUM", in_master,
                "0-prefix; NOT in TWSE/TPEx common lists; likely ETF/leveraged ETF (naming convention)"
            )

        # 4-digit code, not in any official list, not 0-prefix
        if len(stock_id) == 4 and stock_id.isdigit():
            return ClassifiedSecurity(
                stock_id, SecurityType.TWSE_COMMON_DELISTED_PROBABLE, "MEDIUM", in_master,
                "4-digit; NOT in current TWSE/TPEx active lists; probable delisted TWSE common stock"
            )

        return ClassifiedSecurity(
            stock_id, SecurityType.UNKNOWN, "LOW", in_master,
            "Cannot classify by available official sources or heuristics"
        )

    def classify_many(self, stock_ids: Sequence[str]) -> Dict[str, ClassifiedSecurity]:
        return {sid: self.classify(sid) for sid in stock_ids}

    # ------------------------------------------------------------------ #
    # Audit helpers                                                        #
    # ------------------------------------------------------------------ #

    def audit_master(self, master_ids: Optional[Sequence[str]] = None) -> "MasterAuditResult":
        ids = list(master_ids) if master_ids is not None else list(self._master_ids)
        classified = self.classify_many(ids)
        counts: Dict[SecurityType, int] = {}
        for c in classified.values():
            counts[c.security_type] = counts.get(c.security_type, 0) + 1
        return MasterAuditResult(
            total=len(ids),
            by_type=counts,
            classified=classified,
        )

    def audit_signals(
        self,
        signal_stock_ids: Sequence[str],
        signal_counts: Optional[Mapping[str, int]] = None,
    ) -> "SignalAuditResult":
        """
        Classify all stock_ids present in a signal dataset.

        signal_counts maps stock_id → number of signals.
        If omitted, each stock_id counts as 1 signal.
        """
        classified = self.classify_many(signal_stock_ids)
        counts = signal_counts or {sid: 1 for sid in signal_stock_ids}

        signal_by_type: Dict[SecurityType, int] = {}
        stock_by_type: Dict[SecurityType, int] = {}
        for sid, c in classified.items():
            signal_by_type[c.security_type] = (
                signal_by_type.get(c.security_type, 0) + counts.get(sid, 0)
            )
            stock_by_type[c.security_type] = stock_by_type.get(c.security_type, 0) + 1

        total_signals = sum(counts.get(sid, 0) for sid in signal_stock_ids)
        return SignalAuditResult(
            total_signals=total_signals,
            total_unique_stocks=len(signal_stock_ids),
            signals_by_type=signal_by_type,
            stocks_by_type=stock_by_type,
            classified=classified,
        )


@dataclass
class MasterAuditResult:
    total: int
    by_type: Dict[SecurityType, int]
    classified: Dict[str, ClassifiedSecurity]

    def type_count(self, t: SecurityType) -> int:
        return self.by_type.get(t, 0)

    def common_stock_count(self) -> int:
        return (
            self.type_count(SecurityType.TWSE_COMMON_ACTIVE)
            + self.type_count(SecurityType.TPEX_COMMON_ACTIVE)
        )

    def etf_count(self) -> int:
        return (
            self.type_count(SecurityType.ETF_OFFICIAL)
            + self.type_count(SecurityType.ETF_PROBABLE)
        )


@dataclass
class SignalAuditResult:
    total_signals: int
    total_unique_stocks: int
    signals_by_type: Dict[SecurityType, int]
    stocks_by_type: Dict[SecurityType, int]
    classified: Dict[str, ClassifiedSecurity]

    def etf_signal_count(self) -> int:
        return (
            self.signals_by_type.get(SecurityType.ETF_OFFICIAL, 0)
            + self.signals_by_type.get(SecurityType.ETF_PROBABLE, 0)
        )

    def common_stock_signal_count(self) -> int:
        return (
            self.signals_by_type.get(SecurityType.TWSE_COMMON_ACTIVE, 0)
            + self.signals_by_type.get(SecurityType.TPEX_COMMON_ACTIVE, 0)
        )

    def etf_contamination_pct(self) -> float:
        if self.total_signals == 0:
            return 0.0
        return self.etf_signal_count() / self.total_signals * 100.0

    def etf_stock_ids(self) -> Iterator[str]:
        for sid, c in self.classified.items():
            if c.security_type in (SecurityType.ETF_OFFICIAL, SecurityType.ETF_PROBABLE):
                yield sid
