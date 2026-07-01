"""
decision.py — AI 決策引擎（PRD Chapter 9）

整合所有分析模組輸出，產生最終推薦名單。
實現 AI Investment Committee（PRD Chapter 4.6）概念。

模組角色：
  - 基本面分析師：Company Quality Score
  - 技術分析師：Timing Score
  - 籌碼分析師：Market Behavior Score
  - 風險管理師：Risk Score
  - 市場情報：Intelligence Score（簡化版）
  - CIO AI：整合所有分析 → Final Recommendation
"""

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional, Tuple

from config import SCORE_WEIGHTS, RECOMMENDATION_LEVELS, RECOMMENDATION_RULES

logger = logging.getLogger(__name__)


@dataclass
class StockRecommendation:
    """單一股票推薦結果"""
    stock_id:           str
    name:               str = ""
    date:               Optional[date] = None
    # 各模組分數
    quality_score:      float = 0.0    # 基本面（0-100）
    timing_score:       float = 0.0    # 技術面（0-100）
    behavior_score:     float = 0.0    # 市場行為（0-100）
    intelligence_score: float = 0.0    # 市場情報（0-100）
    risk_score:         float = 100.0  # 風險（0-100，越高越安全）
    total_score:        float = 0.0    # 綜合評分（0-100）
    # 推薦等級與信心
    rec_level:          str = "D"       # A+/A/B/C/D
    stars:              str = "★☆☆☆☆"
    confidence:         float = 0.0    # 信心分數（0-100%）
    # Explainable AI
    summary:            str = ""        # 一句話推薦摘要
    advantages:         List[str] = field(default_factory=list)
    risks:              List[str] = field(default_factory=list)
    watch_points:       List[str] = field(default_factory=list)
    ai_conclusion:      str = ""        # AI CIO 結論
    # 附加資訊
    quality_grade:      str = "D"
    close:              Optional[float] = None
    volume:             Optional[float] = None
    market:             str = ""
    industry:           str = ""
    skip_reason:        str = ""        # 若無推薦，說明原因


class DecisionEngine:
    """
    AI 決策引擎（CIO AI）。

    評分公式（PRD Chapter 9）：
    Total Score = Quality(40%) + Timing(25%) + Behavior(20%) + Intelligence(10%) - Risk Penalty(5%)
    """

    def __init__(self, weights: dict = None, rules: dict = None):
        self.weights = weights or SCORE_WEIGHTS
        self.rules   = rules   or RECOMMENDATION_RULES

    def evaluate(
        self,
        stock_id:           str,
        quality_result    = None,
        technical_result  = None,
        behavior_result   = None,
        risk_result       = None,
        intelligence_score: float = 60.0,
        name:             str = "",
        close:            Optional[float] = None,
        volume:           Optional[float] = None,
        market:           str = "",
        industry:         str = "",
        trade_date:       Optional[date] = None,
    ) -> StockRecommendation:
        """
        整合所有分析結果，計算綜合評分並決定推薦等級。
        """
        rec = StockRecommendation(
            stock_id=stock_id,
            name=name,
            date=trade_date,
            close=close,
            volume=volume,
            market=market,
            industry=industry,
            intelligence_score=intelligence_score,
        )

        # 提取各模組分數
        q_score = quality_result.quality_score  if quality_result  else 0.0
        t_score = technical_result.timing_score if technical_result else 0.0
        b_score = behavior_result.behavior_score if behavior_result else 50.0
        r_score = risk_result.risk_score         if risk_result     else 100.0

        rec.quality_score  = q_score
        rec.timing_score   = t_score
        rec.behavior_score = b_score
        rec.risk_score     = r_score
        rec.quality_grade  = quality_result.quality_grade if quality_result else "D"

        # ── 計算綜合評分（Dynamic Weighting：quality 缺失時重分配權重）──
        w = dict(self.weights)
        if q_score == 0.0:
            # 把 quality 的 40% 等比例分給 timing / behavior / intelligence
            non_q_sum = w["timing"] + w["behavior"] + w["intelligence"]
            extra = w["quality"]
            w["timing"]       += extra * (w["timing"]       / non_q_sum)
            w["behavior"]     += extra * (w["behavior"]     / non_q_sum)
            w["intelligence"] += extra * (w["intelligence"] / non_q_sum)
            w["quality"] = 0.0

        base_score = (
            q_score     * w["quality"]    +
            t_score     * w["timing"]     +
            b_score     * w["behavior"]   +
            intelligence_score * w["intelligence"]
        )
        # 風險扣分（risk_score 越低代表風險越高，對 total 造成扣分）
        risk_penalty = (100 - r_score) * w["risk"]
        total_score  = base_score - risk_penalty
        total_score  = round(max(0.0, min(100.0, total_score)), 1)
        rec.total_score = total_score

        # ── 推薦等級 ──────────────────────────────────────────
        rec.rec_level, rec.stars = self._to_level(total_score)

        # ── 信心分數 ──────────────────────────────────────────
        rec.confidence = self._calc_confidence(
            quality_result, technical_result, behavior_result, risk_result
        )

        # ── Explainable AI（收集加分/扣分因素）────────────────
        advantages = []
        risks      = []

        if quality_result:
            advantages.extend(quality_result.factors_plus[:3])
            risks.extend(quality_result.factors_minus[:2])

        if technical_result:
            if technical_result.ma_trend == "bullish":
                advantages.append("均線多頭排列，中期趨勢健康")
            if technical_result.volume_signal == "price_up_vol_up":
                advantages.append("量價俱揚，買盤積極")
            if technical_result.three_major if hasattr(technical_result, "three_major") else False:
                advantages.append("三大法人同步買超")
            risks.extend(technical_result.risk_signals[:2])

        if behavior_result:
            advantages.extend(behavior_result.factors_plus[:2])
            risks.extend(behavior_result.factors_minus[:2])

        if risk_result:
            risks.extend(risk_result.risk_factors[:3])

        rec.advantages   = list(dict.fromkeys(advantages))[:5]  # 去重，最多5條
        rec.risks        = list(dict.fromkeys(risks))[:5]
        rec.watch_points = self._build_watch_points(quality_result, technical_result, trade_date)
        rec.summary      = self._build_summary(rec)
        rec.ai_conclusion = self._build_conclusion(rec)

        logger.debug(
            f"{stock_id} ({name}): Total={total_score:.1f} | "
            f"Q={q_score:.0f} T={t_score:.0f} B={b_score:.0f} R={r_score:.0f} | "
            f"Level={rec.rec_level} Confidence={rec.confidence:.0f}%"
        )
        return rec

    def select_top_n(
        self,
        candidates: List[StockRecommendation],
        max_n: int = None,
    ) -> Tuple[List[StockRecommendation], str]:
        """
        從候選名單中選出 Top N。
        若無符合條件者，回傳空列表並附說明。
        """
        max_n     = max_n or self.rules["max_daily_recs"]
        min_conf  = self.rules["min_confidence"]
        min_score = self.rules["min_total_score"]

        # 篩選符合最低標準的候選
        qualified = [
            r for r in candidates
            if r.confidence >= min_conf
            and r.total_score >= min_score
            and r.rec_level in ("A+", "A", "B")
        ]

        if not qualified:
            reason = (
                f"今日沒有符合本研究策略的股票。"
                f"（所有分析股票中，無符合最低信心門檻 {min_conf}% 且綜合評分 ≥ {min_score} 分的標的）"
            )
            return [], reason

        # 依總分降序，取 Top N
        qualified.sort(key=lambda r: r.total_score, reverse=True)
        top_n  = qualified[:max_n]
        reason = f"今日共有 {len(qualified)} 檔符合條件，推薦其中評分最高的 {len(top_n)} 檔。"
        return top_n, reason

    # ── 私有方法 ──────────────────────────────────────────────

    def _to_level(self, score: float) -> Tuple[str, str]:
        """根據總分對應推薦等級。"""
        for level, cfg in RECOMMENDATION_LEVELS.items():
            if score >= cfg["min_score"]:
                return level, cfg["stars"]
        return "D", "★☆☆☆☆"

    def _calc_confidence(
        self,
        quality_result,
        technical_result,
        behavior_result,
        risk_result,
    ) -> float:
        """
        計算分析信心分數（0-100%）。
        主要受：資料完整性、各模組一致性、風險高低 影響。
        """
        confidence = 100.0

        # 資料完整性扣分
        if quality_result is None or not quality_result.has_sufficient_data:
            confidence -= 20   # 缺少基本面資料
        if technical_result is None or technical_result.timing_score == 0:
            confidence -= 15
        if behavior_result is None:
            confidence -= 10

        # 各模組一致性：若方向不一致，降低信心
        if quality_result and technical_result:
            q_good = quality_result.quality_score >= 70
            t_good = technical_result.timing_score >= 60
            if q_good and not t_good:
                confidence -= 10   # 基本面好但技術面不佳
            elif not q_good and t_good:
                confidence -= 15   # 只有技術面好，不符合「先基本面」原則

        # 風險高時降低信心
        if risk_result:
            if risk_result.risk_score < 50:
                confidence -= 20
            elif risk_result.risk_score < 65:
                confidence -= 10

        return round(max(0.0, min(100.0, confidence)), 1)

    def _build_summary(self, rec: StockRecommendation) -> str:
        """一句話推薦摘要。"""
        level_desc = {
            "A+": "基本面與技術面均優秀，強烈建議深入研究",
            "A":  "公司體質良好，值得持續追蹤",
            "B":  "基本面不錯，等待更佳進場時機",
            "C":  "目前條件不夠理想，建議觀望",
            "D":  "不建議研究",
        }
        return level_desc.get(rec.rec_level, "")

    def _build_conclusion(self, rec: StockRecommendation) -> str:
        """AI CIO 最終結論（在 Claude 分析前的預填版本）。"""
        parts = []

        if rec.quality_score >= 75:
            parts.append(f"公司品質評分 {rec.quality_score:.0f} 分（{rec.quality_grade} 級），基本面優秀")
        elif rec.quality_score >= 60:
            parts.append(f"公司品質評分 {rec.quality_score:.0f} 分，基本面尚可")
        else:
            parts.append(f"公司品質評分 {rec.quality_score:.0f} 分，基本面需持續觀察")

        if rec.timing_score >= 70:
            parts.append("技術面偏多，現為較佳觀察時機")
        elif rec.timing_score >= 50:
            parts.append("技術面中性，等待更明確方向")
        else:
            parts.append("技術面偏弱，建議等待改善再考慮")

        if rec.risks:
            parts.append(f"主要風險：{'；'.join(rec.risks[:2])}")

        if rec.confidence < 70:
            parts.append(f"本次分析信心分數 {rec.confidence:.0f}%，建議持續觀察後再評估")

        return "。".join(parts) + "。"

    def _build_watch_points(
        self,
        quality_result,
        technical_result,
        trade_date,
    ) -> List[str]:
        """建議觀察重點。"""
        points = []

        if technical_result:
            if technical_result.resistance:
                points.append(f"觀察是否突破前波高點 {technical_result.resistance:.2f}")
        if quality_result and quality_result.has_sufficient_data:
            points.append("下季財報 EPS 是否持續改善")
            points.append("月營收 YoY 是否維持成長")

        points.append("三大法人籌碼是否持續流入")

        return points[:4]
