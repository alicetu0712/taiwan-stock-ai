"""
fundamental.py — 基本面篩除引擎（短線波段版）

目標：排除基本面明顯惡化的股票；不以估值選股。
核心邏輯：「股價轉強 → 確認基本面沒有反向惡化 → 推薦」

評分構成（100分）：
  EPS YoY 成長    40  最新年度 EPS vs 前一年
  月營收趨勢      25  近期月營收方向（YoY/MoM）
  毛利率趨勢      20  毛利率是否穩定/上升
  營益率趨勢      15  營業利益率方向

移除（不適合短線）：ROE、ROA、負債比、估值(P/E)、P/B
"""

import logging
import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class FundamentalResult:
    stock_id: str
    quality_score: float = 0.0   # 0-100
    quality_grade: str = "D"     # A+/A/B/C/D
    eps_score: float = 0.0
    revenue_score: float = 0.0
    margin_score: float = 0.0
    op_margin_score: float = 0.0
    factors_plus: List[str] = field(default_factory=list)
    factors_minus: List[str] = field(default_factory=list)
    summary: str = ""
    has_sufficient_data: bool = False
    # 保留相容性（decision.py 讀取）
    roe_score: float = 0.0
    roa_score: float = 0.0
    finance_score: float = 0.0
    valuation_score: float = 0.0
    revenue_score: float = 0.0


class FundamentalAnalyzer:
    """
    短線基本面排除引擎。
    重點：近期 EPS/營收/毛利率/營益率是否惡化。
    非重點：P/E 是否便宜、ROE 是否高（長線邏輯）。
    """

    WEIGHTS = {
        "eps":      40,   # EPS YoY 成長
        "revenue":  25,   # 月營收趨勢
        "margin":   20,   # 毛利率趨勢
        "op_margin": 15,  # 營益率趨勢
    }

    def analyze(self, stock_id: str, fin_summary: dict) -> FundamentalResult:
        result = FundamentalResult(stock_id=stock_id)

        if not fin_summary.get("has_data", False):
            result.summary = "財務資料不足，基本面無法評估（以中性分處理）。"
            result.quality_score = 50.0   # 資料缺失給中性分，不阻擋技術面好的股票
            result.quality_grade = "B"
            return result

        result.has_sufficient_data = True
        plus, minus = [], []

        # ── EPS YoY（40分）──────────────────────────────────
        eps_score, ep, em = self._score_eps_yoy(fin_summary)
        result.eps_score = eps_score
        plus.extend(ep); minus.extend(em)

        # ── 月營收趨勢（25分）────────────────────────────────
        rev_score, rp, rm = self._score_revenue(fin_summary)
        result.revenue_score = rev_score
        plus.extend(rp); minus.extend(rm)

        # ── 毛利率趨勢（20分）────────────────────────────────
        margin_score, mp, mm = self._score_gross_margin(fin_summary)
        result.margin_score = margin_score
        plus.extend(mp); minus.extend(mm)

        # ── 營益率趨勢（15分）────────────────────────────────
        op_score, op, om = self._score_op_margin(fin_summary)
        result.op_margin_score = op_score
        plus.extend(op); minus.extend(om)

        total = eps_score + rev_score + margin_score + op_score
        max_total = sum(self.WEIGHTS.values())
        normalized = round(total / max_total * 100, 1)
        normalized = max(0.0, min(100.0, normalized))

        result.quality_score = normalized
        result.quality_grade = self._to_grade(normalized)
        result.factors_plus = plus
        result.factors_minus = minus
        result.summary = self._build_summary(result)

        logger.debug(f"{stock_id}: Fundamental Score={normalized:.1f} ({result.quality_grade})")
        return result

    # ── 子評分 ────────────────────────────────────────────────

    def _score_eps_yoy(self, fin: dict) -> Tuple[float, List[str], List[str]]:
        """EPS YoY 成長（40分）"""
        plus, minus = [], []

        # 優先用 eps_yoy（年度 YoY）
        eps_yoy = fin.get("eps_yoy")
        eps_5y = fin.get("eps_5y", [])
        eps_ttm = fin.get("eps_ttm")

        # 虧損直接給低分
        if eps_ttm is not None and eps_ttm <= 0:
            minus.append(f"近期 EPS {eps_ttm:.2f}（虧損），基本面偏弱")
            return 5.0, plus, minus

        if eps_yoy is not None:
            if eps_yoy >= 30:
                score = 40.0
                plus.append(f"EPS YoY +{eps_yoy:.0f}%，獲利明顯加速")
            elif eps_yoy >= 15:
                score = 32.0
                plus.append(f"EPS YoY +{eps_yoy:.0f}%，獲利穩健成長")
            elif eps_yoy >= 5:
                score = 24.0
                plus.append(f"EPS YoY +{eps_yoy:.0f}%，獲利小幅成長")
            elif eps_yoy >= -5:
                score = 18.0   # 持平，不扣也不加
            elif eps_yoy >= -20:
                score = 10.0
                minus.append(f"EPS YoY {eps_yoy:.0f}%，獲利衰退中，需留意")
            else:
                score = 4.0
                minus.append(f"EPS YoY {eps_yoy:.0f}%，獲利大幅衰退")
            return score, plus, minus

        # 備案：從 eps_5y 推估趨勢
        eps_trend = fin.get("eps_trend", "unknown")
        if eps_trend == "up":
            plus.append("EPS 近年呈上升趨勢")
            return 28.0, plus, minus
        elif eps_trend == "stable":
            return 20.0, plus, minus
        elif eps_trend == "down":
            minus.append("EPS 近年呈下降趨勢")
            return 8.0, plus, minus

        return 20.0, plus, minus   # 未知給中性

    def _score_revenue(self, fin: dict) -> Tuple[float, List[str], List[str]]:
        """月營收趨勢（25分）"""
        plus, minus = [], []
        rev_trend = fin.get("revenue_trend", "unknown")
        rev_yoy = fin.get("revenue_yoy_avg")

        score = 12.0  # 未知給中性

        if rev_yoy is not None:
            if rev_yoy >= 20:
                score = 25.0
                plus.append(f"月營收 YoY +{rev_yoy:.0f}%，營收強勁成長")
            elif rev_yoy >= 5:
                score = 20.0
                plus.append(f"月營收 YoY +{rev_yoy:.0f}%，營收成長")
            elif rev_yoy >= -5:
                score = 14.0
            elif rev_yoy >= -15:
                score = 7.0
                minus.append(f"月營收 YoY {rev_yoy:.0f}%，營收衰退")
            else:
                score = 2.0
                minus.append(f"月營收 YoY {rev_yoy:.0f}%，營收明顯衰退")
        elif rev_trend == "up":
            score = 20.0
            plus.append("月營收近期呈成長趨勢")
        elif rev_trend == "down":
            score = 5.0
            minus.append("月營收近期呈衰退趨勢")
        elif rev_trend == "stable":
            score = 14.0

        return score, plus, minus

    def _score_gross_margin(self, fin: dict) -> Tuple[float, List[str], List[str]]:
        """毛利率趨勢（20分）"""
        plus, minus = [], []
        gm_avg = fin.get("gross_margin_avg")
        gm_trend = fin.get("gross_margin_trend", "unknown")

        score = 10.0  # 中性基礎分

        if gm_avg is not None:
            if gm_avg >= 40:
                score = 18.0
                plus.append(f"毛利率 {gm_avg:.0f}%，競爭壁壘強")
            elif gm_avg >= 25:
                score = 14.0
                plus.append(f"毛利率 {gm_avg:.0f}%，產品力良好")
            elif gm_avg >= 10:
                score = 10.0
            else:
                score = 5.0
                minus.append(f"毛利率 {gm_avg:.0f}%，競爭壓力較大")

        # 趨勢修正（±2-4分）
        if gm_trend == "up":
            score = min(score + 4, 20)
            plus.append("毛利率呈改善趨勢")
        elif gm_trend == "down":
            score = max(score - 4, 0)
            minus.append("毛利率呈下滑趨勢，需關注競爭壓力")

        return max(0.0, min(score, 20)), plus, minus

    def _score_op_margin(self, fin: dict) -> Tuple[float, List[str], List[str]]:
        """營益率趨勢（15分）"""
        plus, minus = [], []
        op_avg = fin.get("op_margin_avg")
        op_trend = fin.get("op_margin_trend", "unknown")

        score = 7.0   # 中性基礎分

        if op_avg is not None:
            if op_avg >= 15:
                score = 13.0
                plus.append(f"營益率 {op_avg:.0f}%，獲利能力強")
            elif op_avg >= 8:
                score = 10.0
            elif op_avg >= 3:
                score = 7.0
            else:
                score = 3.0
                minus.append(f"營益率 {op_avg:.0f}%，本業獲利能力偏弱")

        if op_trend == "up":
            score = min(score + 3, 15)
            plus.append("營益率呈改善趨勢")
        elif op_trend == "down":
            score = max(score - 3, 0)
            minus.append("營益率呈下滑趨勢")

        return max(0.0, min(score, 15)), plus, minus

    def _to_grade(self, score: float) -> str:
        if score >= 80:
            return "A+"
        elif score >= 65:
            return "A"
        elif score >= 45:
            return "B"
        elif score >= 30:
            return "C"
        return "D"

    def _build_summary(self, r: "FundamentalResult") -> str:
        grade_desc = {
            "A+": "近期獲利/營收均在成長，基本面正向",
            "A":  "基本面穩健，無明顯惡化",
            "B":  "基本面中性，需持續觀察",
            "C":  "基本面有部分衰退訊號",
            "D":  "基本面明顯惡化，需謹慎",
        }
        desc = grade_desc.get(r.quality_grade, "")
        minus_str = "；".join(r.factors_minus[:2]) if r.factors_minus else "無"
        return f"{desc}（{r.quality_score:.0f}分）。注意：{minus_str}。"
