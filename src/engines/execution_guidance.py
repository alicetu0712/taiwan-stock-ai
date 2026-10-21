"""
execution_guidance.py — Final execution guidance from signal + overnight + live state

Architecture:
  daily_signal (Frozen)
        ↓
  overnight_risk (OvernightMarketContext)
        ↓
  live_execution_status (LiveStatus)
        ↓
  ExecutionGuidance

Critical constraints:
  - Does NOT modify trade_signal, PT score, setup_type, or any frozen values.
  - Does NOT produce BUY or SELL signals.
  - LiveStatus is NOT modified; Overnight Risk is a separate dimension.
  - For ENTRY_RECONFIRMED + RED: guidance is PROCEED but with caution flag —
    live evidence of individual stock strength is not blocked by overnight risk.
  - Time-decay of overnight risk (open phase vs afternoon) is not implemented
    in v1 but the architecture allows future extension via session_phase param.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from src.engines.live_decision import LiveStatus
from src.engines.overnight_risk import RISK_GREEN, RISK_RED, RISK_UNKNOWN, RISK_YELLOW


class ExecutionGuidance(str, Enum):
    PROCEED                 = "proceed"
    WAIT_OPEN_CONFIRMATION  = "wait_open_confirmation"
    WAIT_STABILIZATION      = "wait_stabilization"
    WAIT_RECONFIRMATION     = "wait_reconfirmation"
    DO_NOT_CHASE            = "do_not_chase"
    INVALIDATED             = "invalidated"
    DATA_INSUFFICIENT       = "data_insufficient"
    NOT_APPLICABLE          = "not_applicable"    # non-BUY signal


_GUIDANCE_META: dict[ExecutionGuidance, dict] = {
    ExecutionGuidance.PROCEED: {
        "icon": "✅", "label": "可依計劃進場",
        "color": "#00897b", "bg": "#e0f2f1",
    },
    ExecutionGuidance.WAIT_OPEN_CONFIRMATION: {
        "icon": "⏸", "label": "等開盤確認",
        "color": "#f57f17", "bg": "#fff8e1",
    },
    ExecutionGuidance.WAIT_STABILIZATION: {
        "icon": "⏸", "label": "暫緩進場",
        "color": "#e65100", "bg": "#fff3e0",
    },
    ExecutionGuidance.WAIT_RECONFIRMATION: {
        "icon": "⏸", "label": "等待更明確轉強",
        "color": "#1565c0", "bg": "#e3f2fd",
    },
    ExecutionGuidance.DO_NOT_CHASE: {
        "icon": "🚫", "label": "不追價",
        "color": "#78909c", "bg": "#eceff1",
    },
    ExecutionGuidance.INVALIDATED: {
        "icon": "❌", "label": "訊號失效",
        "color": "#b71c1c", "bg": "#ffcdd2",
    },
    ExecutionGuidance.DATA_INSUFFICIENT: {
        "icon": "⚪", "label": "資料不足",
        "color": "#9e9e9e", "bg": "#f5f5f5",
    },
    ExecutionGuidance.NOT_APPLICABLE: {
        "icon": "—", "label": "不適用",
        "color": "#bdbdbd", "bg": "#fafafa",
    },
}


@dataclass
class GuidanceResult:
    guidance:      ExecutionGuidance
    plain_text:    str
    caution:       bool = False   # True when PROCEED but with elevated caution
    caution_text:  str = ""


# ── Guidance lookup table ─────────────────────────────────────────────────────
# Rows: LiveStatus.  Columns: overnight risk level (GREEN, YELLOW, RED, UNKNOWN).
# UNKNOWN is treated conservatively (like YELLOW for IN_RANGE, like RED for drops).
#
# PRD §10 explicitly specifies:
#   BUY + GREEN + IN_RANGE → PROCEED
#   BUY + YELLOW + IN_RANGE → WAIT_OPEN_CONFIRMATION
#   BUY + RED + IN_RANGE → WAIT_STABILIZATION
#   BUY + RED + RAPID_DROP → WAIT_STABILIZATION
#   BUY + RED + WATCHING_LOW → WAIT_RECONFIRMATION
#   BUY + RED + ENTRY_RECONFIRMED → PROCEED (caution, not blocked)
#
# Extension point for time-decay (Phase 2): session_phase parameter can be added
# to this function to weight OPEN_PHASE more heavily on overnight risk.

_GUIDANCE_TABLE: dict[LiveStatus, dict[str, ExecutionGuidance]] = {
    LiveStatus.IN_RANGE: {
        RISK_GREEN:   ExecutionGuidance.PROCEED,
        RISK_YELLOW:  ExecutionGuidance.WAIT_OPEN_CONFIRMATION,
        RISK_RED:     ExecutionGuidance.WAIT_STABILIZATION,
        RISK_UNKNOWN: ExecutionGuidance.WAIT_OPEN_CONFIRMATION,
    },
    LiveStatus.BELOW_RANGE: {
        RISK_GREEN:   ExecutionGuidance.PROCEED,
        RISK_YELLOW:  ExecutionGuidance.WAIT_OPEN_CONFIRMATION,
        RISK_RED:     ExecutionGuidance.WAIT_STABILIZATION,
        RISK_UNKNOWN: ExecutionGuidance.WAIT_OPEN_CONFIRMATION,
    },
    LiveStatus.ABOVE_RANGE: {
        RISK_GREEN:   ExecutionGuidance.DO_NOT_CHASE,
        RISK_YELLOW:  ExecutionGuidance.DO_NOT_CHASE,
        RISK_RED:     ExecutionGuidance.DO_NOT_CHASE,
        RISK_UNKNOWN: ExecutionGuidance.DO_NOT_CHASE,
    },
    LiveStatus.CHASING: {
        RISK_GREEN:   ExecutionGuidance.DO_NOT_CHASE,
        RISK_YELLOW:  ExecutionGuidance.DO_NOT_CHASE,
        RISK_RED:     ExecutionGuidance.DO_NOT_CHASE,
        RISK_UNKNOWN: ExecutionGuidance.DO_NOT_CHASE,
    },
    LiveStatus.RAPID_DROP: {
        RISK_GREEN:   ExecutionGuidance.WAIT_STABILIZATION,
        RISK_YELLOW:  ExecutionGuidance.WAIT_STABILIZATION,
        RISK_RED:     ExecutionGuidance.WAIT_STABILIZATION,
        RISK_UNKNOWN: ExecutionGuidance.WAIT_STABILIZATION,
    },
    LiveStatus.WATCHING_LOW: {
        RISK_GREEN:   ExecutionGuidance.PROCEED,
        RISK_YELLOW:  ExecutionGuidance.WAIT_OPEN_CONFIRMATION,
        RISK_RED:     ExecutionGuidance.WAIT_RECONFIRMATION,
        RISK_UNKNOWN: ExecutionGuidance.WAIT_RECONFIRMATION,
    },
    LiveStatus.ENTRY_RECONFIRMED: {
        # PRD: "不要因 Overnight RED 永久封鎖 ENTRY_RECONFIRMED"
        # Live evidence of individual stock strength overrides overnight risk.
        # Result is PROCEED in all cases, but caution=True for RED/UNKNOWN.
        RISK_GREEN:   ExecutionGuidance.PROCEED,
        RISK_YELLOW:  ExecutionGuidance.PROCEED,
        RISK_RED:     ExecutionGuidance.PROCEED,
        RISK_UNKNOWN: ExecutionGuidance.PROCEED,
    },
    LiveStatus.STOP_WARNING: {
        RISK_GREEN:   ExecutionGuidance.WAIT_STABILIZATION,
        RISK_YELLOW:  ExecutionGuidance.WAIT_STABILIZATION,
        RISK_RED:     ExecutionGuidance.WAIT_STABILIZATION,
        RISK_UNKNOWN: ExecutionGuidance.WAIT_STABILIZATION,
    },
}


def evaluate_execution_guidance(
    trade_signal:  str,
    live_status:   LiveStatus,
    overnight_risk: str,
) -> GuidanceResult:
    """
    Combine frozen daily signal, overnight risk, and live execution status
    into a single execution guidance recommendation.

    Args:
        trade_signal:   "buy" | "strong_buy" | other
        live_status:    current LiveStatus from evaluate_entry_status()
        overnight_risk: OVERNIGHT_RISK_LEVEL string (GREEN/YELLOW/RED/UNKNOWN)

    Returns:
        GuidanceResult — guidance + plain_text + optional caution flag

    Frozen signal invariant: this function reads trade_signal but never modifies it.
    """
    # Non-BUY signals: guidance is not applicable
    if trade_signal not in ("buy", "strong_buy"):
        return GuidanceResult(
            guidance=ExecutionGuidance.NOT_APPLICABLE,
            plain_text="",
        )

    # CANCEL: signal invalidated regardless of overnight
    if live_status == LiveStatus.CANCEL:
        return GuidanceResult(
            guidance=ExecutionGuidance.INVALIDATED,
            plain_text="訊號已因跌破停損而失效。",
        )

    # NO_RANGE / DATE_UNKNOWN: cannot evaluate
    if live_status in (LiveStatus.NO_RANGE, LiveStatus.DATE_UNKNOWN, LiveStatus.NON_BUY):
        return GuidanceResult(
            guidance=ExecutionGuidance.DATA_INSUFFICIENT,
            plain_text="報價資料不足，無法提供今日執行建議。",
        )

    # Normalize unknown overnight_risk values
    if overnight_risk not in (RISK_GREEN, RISK_YELLOW, RISK_RED, RISK_UNKNOWN):
        overnight_risk = RISK_UNKNOWN

    # Lookup from table
    row = _GUIDANCE_TABLE.get(live_status)
    if row is None:
        return GuidanceResult(
            guidance=ExecutionGuidance.DATA_INSUFFICIENT,
            plain_text="",
        )

    guidance = row.get(overnight_risk, ExecutionGuidance.WAIT_OPEN_CONFIRMATION)

    # Caution flag: ENTRY_RECONFIRMED under elevated risk
    caution = (
        live_status == LiveStatus.ENTRY_RECONFIRMED
        and overnight_risk in (RISK_RED, RISK_UNKNOWN)
    )
    caution_text = (
        "股價已從低點明顯回升，個股表現開始抵抗市場弱勢；若其他進場條件仍成立，可以重新評估，但今日市場波動仍高，執行宜謹慎。"
        if caution else ""
    )

    plain_text = _build_guidance_plain(guidance, overnight_risk, live_status, caution)

    return GuidanceResult(
        guidance=guidance,
        plain_text=plain_text,
        caution=caution,
        caution_text=caution_text,
    )


def _build_guidance_plain(
    guidance: ExecutionGuidance,
    overnight_risk: str,
    live_status: LiveStatus,
    caution: bool,
) -> str:
    if caution:
        return "股價已重新轉強，但今日市場波動仍高，若執行應更謹慎。"

    if guidance == ExecutionGuidance.PROCEED:
        if overnight_risk == RISK_GREEN:
            return "昨日 BUY 條件成立，市場環境穩定，可依個股進場計劃執行。"
        return "個股已重新轉強，進場條件改善，可重新評估執行。"

    if guidance == ExecutionGuidance.WAIT_OPEN_CONFIRMATION:
        return (
            "昨日買進條件仍成立，但隔夜市場偏弱，"
            "今天先觀察開盤是否穩定再考慮進場。"
        )

    if guidance == ExecutionGuidance.WAIT_STABILIZATION:
        if live_status in (LiveStatus.RAPID_DROP, LiveStatus.STOP_WARNING):
            return (
                "隔夜市場偏弱，加上個股目前走勢偏弱，"
                "暫時不要進場，等待跌勢停止後再評估。"
            )
        return (
            "昨日模型仍看多，但隔夜市場風險明顯升高，"
            "今天不建議一開盤就進場，先等待價格穩定。"
        )

    if guidance == ExecutionGuidance.WAIT_RECONFIRMATION:
        return (
            "股價已開始止跌，但隔夜市場風險仍高，"
            "等待更明確的轉強訊號後再考慮進場。"
        )

    if guidance == ExecutionGuidance.DO_NOT_CHASE:
        return "股價已超出進場區，不追價。"

    if guidance == ExecutionGuidance.INVALIDATED:
        return "訊號已失效。"

    return ""


def guidance_meta(guidance: ExecutionGuidance) -> dict:
    """Return display metadata (icon, label, color, bg) for a guidance value."""
    return _GUIDANCE_META.get(guidance, _GUIDANCE_META[ExecutionGuidance.DATA_INSUFFICIENT])
