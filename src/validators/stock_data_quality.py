"""
stock_data_quality.py — Per-stock data quality assessment

Two-layer architecture:
  Market-level: DataValidator (price_data / institutional / financial coverage)
  Stock-level:  StockDataQuality (this module) — annotates each recommendation

Each component flag:  ok / warning / missing
Overall confidence:   high / medium_high / medium / low

Rules (fail-conservative):
  - price or pt_score MISSING   → confidence = low
  - 2+ components MISSING       → confidence = low
  - 1 component MISSING         → confidence = medium
  - 2+ components WARNING       → confidence = medium
  - 1 component WARNING         → confidence = medium_high
  - all OK                      → confidence = high
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class DQFlag(str, Enum):
    OK      = "ok"
    WARNING = "warning"
    MISSING = "missing"


# Display helpers (UI layer calls these)
_FLAG_ICON = {DQFlag.OK: "✅", DQFlag.WARNING: "⚠️", DQFlag.MISSING: "❌"}

_CONFIDENCE_LABEL = {
    "high":        "高",
    "medium_high": "中高",
    "medium":      "中",
    "low":         "低",
}

_CONFIDENCE_COLOR = {
    "high":        "#00c851",
    "medium_high": "#88cc88",
    "medium":      "#ffbb33",
    "low":         "#ff4444",
}


@dataclass
class StockDataQuality:
    stock_id:    str
    price:       DQFlag = DQFlag.OK
    ma60:        DQFlag = DQFlag.OK
    volume:      DQFlag = DQFlag.OK
    pt_score:    DQFlag = DQFlag.OK
    institution: DQFlag = DQFlag.OK
    financial:   DQFlag = DQFlag.OK

    @property
    def confidence(self) -> str:
        flags = [self.price, self.ma60, self.volume, self.pt_score,
                 self.institution, self.financial]
        n_ok      = sum(1 for f in flags if f == DQFlag.OK)
        n_missing = sum(1 for f in flags if f == DQFlag.MISSING)
        n_warning = sum(1 for f in flags if f == DQFlag.WARNING)

        if self.price == DQFlag.MISSING or self.pt_score == DQFlag.MISSING:
            return "low"
        if n_missing >= 2:
            return "low"
        if n_missing == 1:
            return "medium"
        if n_warning >= 2:
            return "medium"
        if n_warning == 1:
            return "medium_high"
        return "high"

    def to_dict(self) -> dict:
        return {
            "price":       self.price.value,
            "ma60":        self.ma60.value,
            "volume":      self.volume.value,
            "pt_score":    self.pt_score.value,
            "institution": self.institution.value,
            "financial":   self.financial.value,
            "confidence":  self.confidence,
        }

    def flag_icon(self, component: str) -> str:
        flag = getattr(self, component, DQFlag.MISSING)
        return _FLAG_ICON.get(flag, "?")

    def confidence_label(self) -> str:
        return _CONFIDENCE_LABEL.get(self.confidence, self.confidence)

    def confidence_color(self) -> str:
        return _CONFIDENCE_COLOR.get(self.confidence, "#888")


def assess_stock_quality(
    stock_id: str,
    close: Optional[float],
    vol_ratio: Optional[float],
    pt_score: float,
    quality_score: float,
    intelligence_score: float,
    has_inst_data: bool,
    has_financial_data: bool,
) -> StockDataQuality:
    """
    Assess data quality for a single stock at recommendation time.

    Args:
        close:             rec.close (None if price unavailable)
        vol_ratio:         rec.vol_ratio (None if volume unavailable)
        pt_score:          rec.price_trend_score (0 if PT couldn't run)
        quality_score:     rec.quality_score (0 if no financial data)
        intelligence_score: rec.intelligence_score (0 if no inst data)
        has_inst_data:     stock_id appeared in today's inst_df
        has_financial_data: fin_summary["has_data"] == True
    """
    dq = StockDataQuality(stock_id=stock_id)

    # ── Price ────────────────────────────────────────────────────
    dq.price = DQFlag.OK if (close is not None and close > 0) else DQFlag.MISSING

    # ── MA60 (proxy: PT needs 60-day history; vol_ratio implies history) ──
    if pt_score > 0 or vol_ratio is not None:
        dq.ma60 = DQFlag.OK
    else:
        dq.ma60 = DQFlag.WARNING    # can't confirm sufficient price history

    # ── Volume ───────────────────────────────────────────────────
    if vol_ratio is not None:
        dq.volume = DQFlag.OK
    elif close is not None:
        dq.volume = DQFlag.WARNING  # price ok but no volume comparison
    else:
        dq.volume = DQFlag.MISSING

    # ── PT Score ─────────────────────────────────────────────────
    if pt_score > 0:
        dq.pt_score = DQFlag.OK
    elif close is not None:
        dq.pt_score = DQFlag.WARNING   # price exists but PT didn't produce score
    else:
        dq.pt_score = DQFlag.MISSING

    # ── Institutional ────────────────────────────────────────────
    if has_inst_data:
        dq.institution = DQFlag.OK
    elif intelligence_score > 0:
        dq.institution = DQFlag.WARNING    # stale/partial data contributed a score
    else:
        dq.institution = DQFlag.MISSING

    # ── Financial ────────────────────────────────────────────────
    if has_financial_data:
        dq.financial = DQFlag.OK
    elif quality_score > 5:
        dq.financial = DQFlag.WARNING      # historical data contributed a score
    else:
        dq.financial = DQFlag.MISSING

    return dq


def from_dict(d: dict) -> StockDataQuality:
    """Reconstruct from a stored JSON dict."""
    return StockDataQuality(
        stock_id    = d.get("stock_id", ""),
        price       = DQFlag(d.get("price",       DQFlag.MISSING.value)),
        ma60        = DQFlag(d.get("ma60",        DQFlag.MISSING.value)),
        volume      = DQFlag(d.get("volume",      DQFlag.MISSING.value)),
        pt_score    = DQFlag(d.get("pt_score",    DQFlag.MISSING.value)),
        institution = DQFlag(d.get("institution", DQFlag.MISSING.value)),
        financial   = DQFlag(d.get("financial",   DQFlag.MISSING.value)),
    )
