"""
overnight_risk.py — Overnight Market Risk evaluation

Architecture:
  Frozen Daily Signal  →  Overnight Market Risk  →  Live Execution State
                                    ↓
                         ExecutionGuidance (execution_guidance.py)

Critical constraints:
  - This layer NEVER modifies trade_signal, PT score, setup_type, or any
    ForwardSignal frozen values.
  - Overnight Risk is an Execution Overlay, not a signal generator.
  - It does NOT produce BUY or SELL; it produces a risk_level used by
    ExecutionGuidanceEngine to modify execution behavior.

OVERNIGHT_RULE_VERSION is the single source of truth.
Bump only when threshold semantics or classification logic changes.
Single-field changes (wording, UI) do not warrant a version bump.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ── Single source of truth ────────────────────────────────────────────────────
OVERNIGHT_RULE_VERSION = "overnight_v1"

# ── PROVISIONAL thresholds ────────────────────────────────────────────────────
# ⚠️  These are engineering initial values, NOT statistically validated.
# They have NOT been optimized against historical Taiwan stock performance data.
# Do NOT claim these thresholds are evidence-based until the Forward dataset
# contains sufficient samples for statistical validation (target: 6+ months).
# To revise thresholds after validation: create overnight_v2 with new values.
# All existing overnight_v1 records must remain intact and unchanged.
OVERNIGHT_RISK_CONFIG: dict = {
    # Nasdaq Composite 1-day return (%) — PROVISIONAL
    "NASDAQ_MODERATE_DROP": -1.5,
    "NASDAQ_SEVERE_DROP":   -2.5,
    # Philadelphia Semiconductor Index 1-day return (%) — PROVISIONAL
    "SOX_MODERATE_DROP":    -2.0,
    "SOX_SEVERE_DROP":      -3.5,
    # S&P 500 1-day return (%) — PROVISIONAL
    "SP500_MODERATE_DROP":  -1.5,
    "SP500_SEVERE_DROP":    -2.5,
    # VIX % change from prior session — PROVISIONAL
    "VIX_MODERATE_SPIKE":   15.0,
    "VIX_SEVERE_SPIKE":     25.0,
    # VIX absolute level — PROVISIONAL
    "VIX_ABSOLUTE_HIGH":    30.0,
}

# ── Risk level constants ──────────────────────────────────────────────────────
RISK_GREEN   = "GREEN"
RISK_YELLOW  = "YELLOW"
RISK_RED     = "RED"
RISK_UNKNOWN = "UNKNOWN"

# ── Data quality constants ────────────────────────────────────────────────────
DQ_COMPLETE = "COMPLETE"
DQ_PARTIAL  = "PARTIAL"
DQ_STALE    = "STALE"
DQ_UNKNOWN  = "UNKNOWN"


@dataclass
class RiskReason:
    code:    str    # machine code, e.g. "SOX_SEVERE_DROP"
    value:   float  # raw value (return_pct or vix level)
    message: str    # plain-language explanation (Traditional Chinese)


@dataclass
class OvernightRiskResult:
    risk_level:   str                       # GREEN / YELLOW / RED / UNKNOWN
    risk_score:   Optional[float]           # nullable in v1
    reasons:      list[RiskReason] = field(default_factory=list)
    rule_version: str = OVERNIGHT_RULE_VERSION
    data_quality: str = DQ_UNKNOWN
    plain_text:   str = ""                  # UI summary sentence


def _derive_data_quality(
    sp500_ok: bool,
    nasdaq_ok: bool,
    sox_ok: bool,
    vix_ok: bool,
    any_stale: bool,
) -> str:
    """
    COMPLETE  = all four indicators have exact-session match data.
    PARTIAL   = at least one indicator missing, but at least one present.
    STALE     = any indicator returned wrong-session data.
    UNKNOWN   = no indicator data available at all.

    STALE takes priority over PARTIAL.
    UNKNOWN / STALE must never produce GREEN risk_level (enforced in evaluate_overnight_risk).
    """
    if any_stale:
        return DQ_STALE
    present = sum([sp500_ok, nasdaq_ok, sox_ok, vix_ok])
    if present == 4:
        return DQ_COMPLETE
    if present == 0:
        return DQ_UNKNOWN
    return DQ_PARTIAL


def evaluate_overnight_risk(
    sp500_return:  Optional[float],
    nasdaq_return: Optional[float],
    sox_return:    Optional[float],
    vix_close:     Optional[float],
    vix_change:    Optional[float],
    data_quality:  str,
) -> OvernightRiskResult:
    """
    Evaluate overnight market risk from index returns and VIX.

    Args:
        sp500_return:  S&P 500 1-day return (%)
        nasdaq_return: Nasdaq Composite 1-day return (%)
        sox_return:    Philadelphia SOX 1-day return (%)
        vix_close:     VIX absolute close level
        vix_change:    VIX % change from prior session
        data_quality:  COMPLETE / PARTIAL / STALE / UNKNOWN

    Returns:
        OvernightRiskResult — risk_level is NEVER GREEN when data_quality
        is STALE or UNKNOWN (fail-closed).
    """
    cfg = OVERNIGHT_RISK_CONFIG

    # Fail-closed: insufficient or stale data → UNKNOWN
    if data_quality in (DQ_STALE, DQ_UNKNOWN):
        return OvernightRiskResult(
            risk_level=RISK_UNKNOWN,
            risk_score=None,
            data_quality=data_quality,
            plain_text="隔夜市場資料不足，今日請以個股開盤後價格行為為主。",
        )

    reasons: list[RiskReason] = []
    red_count    = 0
    yellow_count = 0

    # ── SOX (semiconductor sector — most relevant for TW tech) ───────────────
    if sox_return is not None:
        if sox_return <= cfg["SOX_SEVERE_DROP"]:
            reasons.append(RiskReason(
                code="SOX_SEVERE_DROP", value=sox_return,
                message="美國半導體類股隔夜明顯下跌",
            ))
            red_count += 2   # weighted: SOX is highest relevance for TW
        elif sox_return <= cfg["SOX_MODERATE_DROP"]:
            reasons.append(RiskReason(
                code="SOX_MODERATE_DROP", value=sox_return,
                message="美國半導體類股隔夜走弱",
            ))
            yellow_count += 2

    # ── Nasdaq ───────────────────────────────────────────────────────────────
    if nasdaq_return is not None:
        if nasdaq_return <= cfg["NASDAQ_SEVERE_DROP"]:
            reasons.append(RiskReason(
                code="NASDAQ_SEVERE_DROP", value=nasdaq_return,
                message="美國科技股整體大跌",
            ))
            red_count += 1
        elif nasdaq_return <= cfg["NASDAQ_MODERATE_DROP"]:
            reasons.append(RiskReason(
                code="NASDAQ_WEAK", value=nasdaq_return,
                message="美國科技股整體偏弱",
            ))
            yellow_count += 1

    # ── S&P 500 ──────────────────────────────────────────────────────────────
    if sp500_return is not None:
        if sp500_return <= cfg["SP500_SEVERE_DROP"]:
            reasons.append(RiskReason(
                code="SP500_SEVERE_DROP", value=sp500_return,
                message="美國大盤整體明顯下跌",
            ))
            red_count += 1
        elif sp500_return <= cfg["SP500_MODERATE_DROP"]:
            reasons.append(RiskReason(
                code="SP500_WEAK", value=sp500_return,
                message="美國大盤整體偏弱",
            ))
            yellow_count += 1

    # ── VIX ──────────────────────────────────────────────────────────────────
    if vix_close is not None and vix_close >= cfg["VIX_ABSOLUTE_HIGH"]:
        reasons.append(RiskReason(
            code="VIX_HIGH", value=vix_close,
            message=f"市場恐慌程度偏高（VIX={vix_close:.1f}）",
        ))
        red_count += 1

    if vix_change is not None:
        if vix_change >= cfg["VIX_SEVERE_SPIKE"]:
            reasons.append(RiskReason(
                code="VIX_SEVERE_SPIKE", value=vix_change,
                message="市場恐慌指數急速上升",
            ))
            red_count += 1
        elif vix_change >= cfg["VIX_MODERATE_SPIKE"]:
            reasons.append(RiskReason(
                code="VIX_MODERATE_SPIKE", value=vix_change,
                message="市場恐慌指數明顯上升",
            ))
            yellow_count += 1

    # ── Aggregate risk level ──────────────────────────────────────────────────
    if red_count >= 1:
        risk_level = RISK_RED
    elif yellow_count >= 1:
        risk_level = RISK_YELLOW
    else:
        risk_level = RISK_GREEN

    # PARTIAL data → cannot produce GREEN; downgrade to YELLOW at minimum
    if data_quality == DQ_PARTIAL and risk_level == RISK_GREEN:
        risk_level = RISK_UNKNOWN

    # Plain-language summary
    plain_text = _build_plain_text(risk_level, reasons, data_quality)

    return OvernightRiskResult(
        risk_level=risk_level,
        risk_score=None,
        reasons=reasons,
        rule_version=OVERNIGHT_RULE_VERSION,
        data_quality=data_quality,
        plain_text=plain_text,
    )


def _build_plain_text(risk_level: str, reasons: list[RiskReason], data_quality: str) -> str:
    if data_quality == DQ_PARTIAL:
        return "隔夜部分市場資料缺失，判斷參考性有限，今日宜謹慎觀察開盤行為。"
    if risk_level == RISK_GREEN:
        return "昨晚全球市場沒有出現明顯風險，今天可以正常依個股進場條件判斷。"
    if risk_level == RISK_YELLOW:
        return "昨晚市場偏弱，今天開盤可能比較震盪。先觀察個股能不能穩住，再考慮進場。"
    if risk_level == RISK_RED:
        return (
            "昨晚市場出現明顯賣壓，今天開盤風險較高。"
            "昨日 BUY 訊號沒有消失，但不建議一開盤就急著買。"
        )
    return "隔夜市場資料不足，今日請以個股開盤後價格行為為主。"


def risk_reasons_to_json(reasons: list[RiskReason]) -> str:
    return json.dumps(
        [{"code": r.code, "value": round(r.value, 2), "message": r.message} for r in reasons],
        ensure_ascii=False,
    )


def risk_reasons_from_json(s: str) -> list[RiskReason]:
    if not s:
        return []
    try:
        data = json.loads(s)
        return [RiskReason(code=d["code"], value=d["value"], message=d["message"]) for d in data]
    except Exception:
        return []
