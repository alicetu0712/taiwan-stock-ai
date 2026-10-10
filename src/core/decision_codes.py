"""
decision_codes.py — Stable decision identifiers (single source of truth)

DB / filter layer uses codes (e.g. "strong_buy").
UI layer translates: to_display("strong_buy") → "BUY ★".

Renaming a display label never touches the DB or any filter logic.
"""

from enum import Enum


class DecisionCode(str, Enum):
    STRONG_BUY    = "strong_buy"
    BUY           = "buy"
    WAIT_PULLBACK = "wait_pullback"
    WAIT          = "wait"
    REDUCE        = "reduce"
    SELL          = "sell"


# Ordered strongest-buy → strongest-sell (used for selectbox ordering)
ORDERED: tuple["DecisionCode", ...] = (
    DecisionCode.STRONG_BUY,
    DecisionCode.BUY,
    DecisionCode.WAIT_PULLBACK,
    DecisionCode.WAIT,
    DecisionCode.REDUCE,
    DecisionCode.SELL,
)

_DISPLAY: dict["DecisionCode", str] = {
    DecisionCode.STRONG_BUY:    "BUY ★",
    DecisionCode.BUY:           "BUY",
    DecisionCode.WAIT_PULLBACK: "WAIT FOR PULLBACK",
    DecisionCode.WAIT:          "WAIT",
    DecisionCode.REDUCE:        "REDUCE",
    DecisionCode.SELL:          "SELL / AVOID",
}

_COLOR: dict["DecisionCode", str] = {
    DecisionCode.STRONG_BUY:    "#1a7f4b",
    DecisionCode.BUY:           "#2ecc71",
    DecisionCode.WAIT_PULLBACK: "#f39c12",
    DecisionCode.WAIT:          "#95a5a6",
    DecisionCode.REDUCE:        "#e67e22",
    DecisionCode.SELL:          "#e74c3c",
}

# Legacy display-string → code (used for DB migration only)
_LEGACY_DISPLAY_TO_CODE: dict[str, str] = {
    "BUY ★":            DecisionCode.STRONG_BUY.value,
    "BUY":              DecisionCode.BUY.value,
    "WAIT FOR PULLBACK": DecisionCode.WAIT_PULLBACK.value,
    "WAIT":             DecisionCode.WAIT.value,
    "REDUCE":           DecisionCode.REDUCE.value,
    "SELL / AVOID":     DecisionCode.SELL.value,
}


def to_display(code: str | None) -> str:
    """Translate code → display label. Unknown code returns code as-is."""
    if code is None:
        return "—"
    try:
        return _DISPLAY[DecisionCode(code)]
    except (ValueError, KeyError):
        return code


def to_color(code: str | None) -> str:
    """Translate code → badge hex color."""
    if code is None:
        return "#666"
    try:
        return _COLOR[DecisionCode(code)]
    except (ValueError, KeyError):
        return "#666"


def all_codes() -> list[str]:
    """All codes in display order."""
    return [c.value for c in ORDERED]


def buy_codes() -> tuple[str, str]:
    """Codes that represent buy signals."""
    return (DecisionCode.STRONG_BUY.value, DecisionCode.BUY.value)


def migrate_display_to_code(label: str | None) -> str | None:
    """Convert a legacy display-string value to its code. Returns None unchanged."""
    if label is None:
        return None
    return _LEGACY_DISPLAY_TO_CODE.get(label, label)
