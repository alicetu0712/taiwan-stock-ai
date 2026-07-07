"""
fundamental.py — 基本面分析引擎（PRD Chapter 5）

計算 Company Quality Score（0-100）並給出等級（A+/A/B/C/D）。
遵循原則：趨勢優先、穩定優先、同產業比較。
"""

import logging
import math
from dataclasses import dataclass, field
from typing import List, Optional

from config import QUALITY_CONFIG

logger = logging.getLogger(__name__)


@dataclass
class FundamentalResult:
    """基本面分析結果"""
    stock_id:         str
    quality_score:    float = 0.0       # 0-100
    quality_grade:    str   = "D"       # A+/A/B/C/D
    roe_score:        float = 0.0
    roa_score:        float = 0.0
    eps_score:        float = 0.0
    margin_score:     float = 0.0
    finance_score:    float = 0.0
    valuation_score:  float = 0.0
    revenue_score:    float = 0.0
    factors_plus:     List[str] = field(default_factory=list)
    factors_minus:    List[str] = field(default_factory=list)
    summary:          str   = ""
    has_sufficient_data: bool = False


class FundamentalAnalyzer:
    """
    基本面分析引擎。
    輸入：財務摘要 dict（來自 financial_collector）
    輸出：FundamentalResult
    """

    # 各子評分最大分數
    WEIGHTS = {
        "roe":        20,   # ROE 分析
        "roa":        15,   # ROA 分析
        "eps":        35,   # EPS 趨勢（含連續成長獎勵，最高 35）
        "margin":     15,   # 毛利率
        "finance":    15,   # 財務健康
        "valuation":  10,   # 估值
        "revenue":     5,   # 營收趨勢
    }

    def analyze(self, stock_id: str, fin_summary: dict) -> FundamentalResult:
        """
        主要入口：依財務摘要計算基本面評分。
        """
        result = FundamentalResult(stock_id=stock_id)

        if not fin_summary.get("has_data", False):
            result.summary = "財務資料不足，無法進行基本面評分。"
            return result

        result.has_sufficient_data = True
        factors_plus  = []
        factors_minus = []

        # ── ROE 分析（最高 20 分）────────────────────────────
        roe_list = fin_summary.get("roe_5y", [])
        roe_avg  = fin_summary.get("roe_avg")
        roe_score, roe_plus, roe_minus = self._score_roe(roe_avg, roe_list)
        result.roe_score = roe_score
        factors_plus.extend(roe_plus)
        factors_minus.extend(roe_minus)

        # ── ROA 分析（最高 15 分）────────────────────────────
        roa_avg = fin_summary.get("roa_avg")
        roa_score, roa_plus, roa_minus = self._score_roa(roa_avg)
        result.roa_score = roa_score
        factors_plus.extend(roa_plus)
        factors_minus.extend(roa_minus)

        # ── EPS 趨勢分析（最高 20 分）───────────────────────
        eps_ttm   = fin_summary.get("eps_ttm")
        eps_trend = fin_summary.get("eps_trend", "unknown")
        eps_5y    = fin_summary.get("eps_5y", [])
        eps_score, eps_plus, eps_minus = self._score_eps(eps_ttm, eps_trend, eps_5y)
        result.eps_score = eps_score
        factors_plus.extend(eps_plus)
        factors_minus.extend(eps_minus)

        # ── 毛利率分析（最高 15 分）─────────────────────────
        gm_avg = fin_summary.get("gross_margin_avg")
        margin_score, gm_plus, gm_minus = self._score_gross_margin(gm_avg)
        result.margin_score = margin_score
        factors_plus.extend(gm_plus)
        factors_minus.extend(gm_minus)

        # ── 財務健康分析（最高 15 分）───────────────────────
        debt_ratio = fin_summary.get("debt_ratio")
        free_cf    = fin_summary.get("free_cash_flow")
        current_r  = fin_summary.get("current_ratio")
        fin_score, fin_plus, fin_minus = self._score_financial_health(
            debt_ratio, free_cf, current_r
        )
        result.finance_score = fin_score
        factors_plus.extend(fin_plus)
        factors_minus.extend(fin_minus)

        # ── 估值分析（最高 10 分）───────────────────────────
        per = fin_summary.get("per")
        pbr = fin_summary.get("pbr")
        val_score, val_plus, val_minus = self._score_valuation(per, pbr)
        result.valuation_score = val_score
        factors_plus.extend(val_plus)
        factors_minus.extend(val_minus)

        # ── 營收趨勢（最高 5 分）────────────────────────────
        rev_trend = fin_summary.get("revenue_trend", "unknown")
        rev_score, rev_plus, rev_minus = self._score_revenue(rev_trend)
        result.revenue_score = rev_score
        factors_plus.extend(rev_plus)
        factors_minus.extend(rev_minus)

        # ── 計算綜合分數 ──────────────────────────────────
        total = (
            roe_score + roa_score + eps_score + margin_score +
            fin_score + val_score + rev_score
        )
        max_total = sum(self.WEIGHTS.values())
        normalized = round(total / max_total * 100, 1)
        normalized = max(0.0, min(100.0, normalized))

        result.quality_score   = normalized
        result.quality_grade   = self._to_grade(normalized)
        result.factors_plus    = factors_plus
        result.factors_minus   = factors_minus
        result.summary         = self._build_summary(result)

        logger.debug(f"{stock_id}: Quality Score={normalized:.1f} ({result.quality_grade})")
        return result

    # ── 子評分方法 ────────────────────────────────────────────

    def _score_roe(self, roe_avg: Optional[float], roe_list: List[float]):
        """ROE 評分（最高 20 分）"""
        score = 0.0
        plus, minus = [], []
        cfg = QUALITY_CONFIG["roe"]

        if roe_avg is None:
            return score, plus, minus

        # 絕對值評分
        if roe_avg >= cfg["excellent"]:    # ≥20%
            score += 20
            plus.append(f"ROE 長期維持 {roe_avg:.1f}%（非常優秀，≥20%）")
        elif roe_avg >= cfg["great"]:      # ≥15%
            score += 15
            plus.append(f"ROE {roe_avg:.1f}%（優秀，≥15%）")
        elif roe_avg >= cfg["good"]:       # ≥10%
            score += 10
            plus.append(f"ROE {roe_avg:.1f}%（良好）")
        elif roe_avg >= cfg["pass"]:       # ≥8%
            score += 5
        else:
            minus.append(f"ROE {roe_avg:.1f}% 偏低（<8%）")

        # 趨勢加分
        if len(roe_list) >= 4:
            trend = _trend_direction(roe_list)
            if trend == "up":
                score += 2
                plus.append("ROE 呈現上升趨勢")
            elif trend == "down":
                score -= 3
                minus.append("ROE 呈現下降趨勢")

        return max(0.0, min(score, 20)), plus, minus

    def _score_roa(self, roa_avg: Optional[float]):
        """ROA 評分（最高 15 分）"""
        score = 0.0
        plus, minus = [], []
        cfg = QUALITY_CONFIG["roa"]

        if roa_avg is None:
            return score, plus, minus

        if roa_avg >= cfg["excellent"]:    # ≥12%
            score += 15
            plus.append(f"ROA {roa_avg:.1f}%（非常優秀，≥12%）")
        elif roa_avg >= cfg["great"]:      # ≥8%
            score += 11
            plus.append(f"ROA {roa_avg:.1f}%（優秀，≥8%）")
        elif roa_avg >= cfg["good"]:       # ≥5%
            score += 7
        elif roa_avg >= cfg["pass"]:       # ≥3%
            score += 4
        else:
            minus.append(f"ROA {roa_avg:.1f}% 偏低，資產利用效率不佳")

        return max(0.0, min(score, 15)), plus, minus

    def _score_eps(
        self,
        eps_ttm: Optional[float],
        eps_trend: str,
        eps_5y: List[float],
    ):
        """EPS 評分（最高 20 分）"""
        score = 0.0
        plus, minus = [], []

        if eps_ttm is None:
            return score, plus, minus

        # TTM EPS > 0（基本要求）
        if eps_ttm <= 0:
            minus.append(f"TTM EPS {eps_ttm:.2f}（虧損）")
            return 0.0, plus, minus

        score += 5   # 基本分：EPS > 0

        # EPS 趨勢
        if eps_trend == "up":
            score += 10
            plus.append("EPS 近五年整體呈上升趨勢")
        elif eps_trend == "stable":
            score += 6
        elif eps_trend == "down":
            score -= 2
            minus.append("EPS 近期呈下降趨勢")

        # 連續正成長（績優股核心特徵）
        valid_eps = [v for v in eps_5y if v is not None and v > 0]
        if len(valid_eps) >= 5:
            last_5 = valid_eps[-5:]
            if all(last_5[i] > last_5[i - 1] for i in range(1, 5)):
                score += 15
                plus.append("連續 5 年 EPS 正成長（績優核心特徵）")
            elif all(last_5[-3:][i] > last_5[-3:][i - 1] for i in range(1, 3)):
                score += 8
                plus.append("連續 3 年 EPS 正成長")
        elif len(valid_eps) >= 3:
            last_3 = valid_eps[-3:]
            if all(last_3[i] > last_3[i - 1] for i in range(1, 3)):
                score += 8
                plus.append("連續 3 年 EPS 正成長")

        # 近四季波動（穩定性加分）
        if len(eps_5y) >= 8:
            recent_8 = [v for v in eps_5y[-8:] if v is not None and v > 0]
            if len(recent_8) >= 4:
                cv = _coeff_variation(recent_8)
                if cv < 0.2:
                    score += 5
                    plus.append("EPS 波動小，獲利穩定")
                elif cv > 0.5:
                    minus.append("EPS 波動較大")

        return max(0.0, min(score, 35)), plus, minus

    def _score_gross_margin(self, gm_avg: Optional[float]):
        """毛利率評分（最高 15 分）"""
        score = 0.0
        plus, minus = [], []
        cfg = QUALITY_CONFIG["gross_margin"]

        if gm_avg is None:
            return score, plus, minus

        if gm_avg >= cfg["excellent"]:   # ≥40%
            score += 15
            plus.append(f"毛利率 {gm_avg:.1f}%（產品競爭力強，≥40%）")
        elif gm_avg >= cfg["great"]:     # ≥30%
            score += 11
            plus.append(f"毛利率 {gm_avg:.1f}%（良好，≥30%）")
        elif gm_avg >= cfg["good"]:      # ≥20%
            score += 7
        elif gm_avg >= cfg["pass"]:      # ≥10%
            score += 4
        else:
            minus.append(f"毛利率 {gm_avg:.1f}% 偏低，競爭壓力可能較大")

        return max(0.0, min(score, 15)), plus, minus

    def _score_financial_health(
        self,
        debt_ratio: Optional[float],
        free_cf: Optional[float],
        current_ratio: Optional[float],
    ):
        """財務健康評分（最高 15 分）"""
        score = 0.0
        plus, minus = [], []
        cfg = QUALITY_CONFIG["debt_ratio"]

        if debt_ratio is not None:
            if debt_ratio <= cfg["safe"]:
                score += 6
                plus.append(f"負債比率 {debt_ratio:.1f}%（低，財務穩健）")
            elif debt_ratio <= cfg["moderate"]:
                score += 4
            elif debt_ratio <= cfg["risky"]:
                score += 2
            else:
                minus.append(f"負債比率 {debt_ratio:.1f}% 偏高（>60%）")

        if free_cf is not None:
            if free_cf > 0:
                score += 5
                plus.append("自由現金流為正，財務體質健康")
            else:
                score -= 2
                minus.append("自由現金流為負，需關注資金狀況")

        if current_ratio is not None:
            if current_ratio >= 2.0:
                score += 4
                plus.append(f"流動比率 {current_ratio:.1f}（短期償債能力強）")
            elif current_ratio >= 1.5:
                score += 2
            elif current_ratio < 1.0:
                minus.append(f"流動比率 {current_ratio:.1f} 偏低，短期流動性存在風險")

        return max(0.0, min(score, 15)), plus, minus

    def _score_valuation(
        self,
        per: Optional[float],
        pbr: Optional[float],
    ):
        """估值評分（最高 10 分）"""
        score = 5.0   # 預設中立
        plus, minus = [], []

        if per is not None and per > 0:
            if per <= 15:
                score += 3
                plus.append(f"本益比 {per:.1f} 倍（估值合理偏低）")
            elif per <= 25:
                pass   # 普通，不加分也不扣分
            elif per <= 40:
                score -= 2
                minus.append(f"本益比 {per:.1f} 倍（估值偏高，需留意）")
            else:
                score -= 4
                minus.append(f"本益比 {per:.1f} 倍（估值過高）")

        if pbr is not None and pbr > 0:
            if pbr <= 2.0:
                score += 2
                plus.append(f"股價淨值比 {pbr:.1f}（合理）")
            elif pbr > 5.0:
                score -= 1
                minus.append(f"股價淨值比 {pbr:.1f}（偏高）")

        return max(0.0, min(score, 10)), plus, minus

    def _score_revenue(self, rev_trend: str):
        """營收趨勢評分（最高 5 分）"""
        score = 0.0
        plus, minus = [], []

        if rev_trend == "up":
            score = 5
            plus.append("近期月營收呈成長趨勢")
        elif rev_trend == "stable":
            score = 3
        elif rev_trend == "down":
            score = 0
            minus.append("近期月營收呈衰退趨勢")

        return score, plus, minus

    def _to_grade(self, score: float) -> str:
        if score >= 85:   return "A+"
        elif score >= 75: return "A"
        elif score >= 65: return "B"
        elif score >= 50: return "C"
        return "D"

    def _build_summary(self, r: "FundamentalResult") -> str:
        """生成基本面分析摘要文字。"""
        grade_desc = {
            "A+": "企業體質非常優秀",
            "A":  "企業體質良好",
            "B":  "企業體質尚可",
            "C":  "企業體質普通",
            "D":  "企業體質較弱",
        }
        desc = grade_desc.get(r.quality_grade, "")
        plus_str = "；".join(r.factors_plus[:3]) if r.factors_plus else "無明顯加分因素"
        return f"{desc}（{r.quality_score:.1f}分）。主要優勢：{plus_str}。"


# ── 工具函式 ──────────────────────────────────────────────────

def _trend_direction(values: List[float]) -> str:
    """簡單趨勢方向判斷。"""
    if not values or len(values) < 3:
        return "unknown"
    import numpy as np
    try:
        clean = [v for v in values if v is not None and not math.isnan(v)]
        if len(clean) < 3:
            return "unknown"
        x = list(range(len(clean)))
        slope = np.polyfit(x, clean, 1)[0]
        mean_v = abs(sum(clean) / len(clean))
        if mean_v < 1e-6:
            return "stable"
        rel_slope = slope / mean_v
        if rel_slope > 0.05:
            return "up"
        elif rel_slope < -0.05:
            return "down"
        return "stable"
    except Exception as e:
        logger.debug(f"revenue trend calc failed: {e}")
        return "unknown"


def _coeff_variation(values: List[float]) -> float:
    """變異係數（CV）= std / mean，衡量穩定性。"""
    import numpy as np
    try:
        arr = [v for v in values if v is not None and not math.isnan(v)]
        if not arr:
            return 0.0
        mean = sum(arr) / len(arr)
        if abs(mean) < 1e-6:
            return 0.0
        std = (sum((v - mean) ** 2 for v in arr) / len(arr)) ** 0.5
        return std / abs(mean)
    except Exception as e:
        logger.debug(f"_coeff_variation failed: {e}")
        return 0.0
