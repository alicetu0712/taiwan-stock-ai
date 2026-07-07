"""
risk.py — 風險管理引擎（PRD Chapter 12）

計算 Risk Score（0-100，越高越安全）。
從六個面向評估：公司、市場、產業、技術、流動性、總體經濟。
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class RiskResult:
    """風險分析結果"""

    stock_id: str
    risk_score: float = 100.0  # 0-100，越高越安全
    risk_grade: str = "A"  # A/B/C/D/E
    company_risk: str = "low"
    technical_risk: str = "low"
    market_risk: str = "low"
    liquidity_risk: str = "low"
    risk_factors: List[str] = field(default_factory=list)
    summary: str = ""


class RiskAnalyzer:
    """
    風險分析引擎。
    整合公司財務風險、技術風險、市場風險、流動性風險。
    """

    def analyze(
        self,
        stock_id: str,
        technical_result=None,  # TechnicalResult
        behavior_result=None,  # MarketBehaviorResult
        fin_summary: dict = None,
        market_sentiment: dict = None,
        close: float = None,
        volume: float = None,
        avg_volume: float = None,
        upcoming_events: List[str] = None,
    ) -> RiskResult:
        """主要入口：綜合風險評分。"""
        result = RiskResult(stock_id=stock_id)
        score = 100.0
        risk_factors = []

        # ── 技術風險（PRD 12.6）─────────────────────────────
        if technical_result:
            tech_deduct, tech_factors = self._technical_risk(technical_result)
            score -= tech_deduct
            risk_factors.extend(tech_factors)
            if tech_deduct > 20:
                result.technical_risk = "high"
            elif tech_deduct > 10:
                result.technical_risk = "medium"

        # ── 籌碼風險 ─────────────────────────────────────────
        if behavior_result:
            chip_deduct, chip_factors = self._chip_risk(behavior_result)
            score -= chip_deduct
            risk_factors.extend(chip_factors)

        # ── 公司財務風險（PRD 12.3）─────────────────────────
        if fin_summary:
            fin_deduct, fin_factors = self._company_risk(fin_summary)
            score -= fin_deduct
            risk_factors.extend(fin_factors)
            if fin_deduct > 20:
                result.company_risk = "high"
            elif fin_deduct > 10:
                result.company_risk = "medium"

        # ── 流動性風險（PRD 12.7）───────────────────────────
        liq_deduct, liq_factors = self._liquidity_risk(volume, avg_volume)
        score -= liq_deduct
        risk_factors.extend(liq_factors)
        if liq_deduct > 15:
            result.liquidity_risk = "high"

        # ── 市場風險（PRD 12.4）─────────────────────────────
        if market_sentiment:
            mkt_deduct, mkt_factors = self._market_risk(market_sentiment)
            score -= mkt_deduct
            risk_factors.extend(mkt_factors)
            if mkt_deduct > 10:
                result.market_risk = "medium"

        # ── 事件風險（PRD 11.4）─────────────────────────────
        if upcoming_events:
            evt_deduct, evt_factors = self._event_risk(upcoming_events)
            score -= evt_deduct
            risk_factors.extend(evt_factors)

        result.risk_score = round(max(0.0, min(100.0, score)), 1)
        result.risk_grade = self._to_grade(result.risk_score)
        result.risk_factors = risk_factors
        result.summary = self._build_summary(result)

        logger.debug(
            f"{stock_id}: Risk Score={result.risk_score:.1f} ({result.risk_grade})"
        )
        return result

    # ── 子評估方法 ────────────────────────────────────────────

    def _technical_risk(self, tech) -> tuple:
        """技術面風險扣分。"""
        deduct = 0
        factors = []

        # RSI 過熱
        if tech.rsi is not None:
            if tech.rsi > 80:
                deduct += 25
                factors.append(f"RSI {tech.rsi:.0f} 嚴重過熱（>80），短線回調風險高")
            elif tech.rsi > 75:
                deduct += 15
                factors.append(f"RSI {tech.rsi:.0f} 過熱（>75）")

        # 股價偏離 MA20
        if tech.close and tech.ma20:
            dev = (tech.close - tech.ma20) / tech.ma20 * 100
            if dev > 20:
                deduct += 20
                factors.append(f"股價偏離 MA20 達 {dev:.1f}%，追高風險大")
            elif dev > 15:
                deduct += 10
                factors.append(f"股價偏離 MA20 達 {dev:.1f}%，略為過熱")

        # 接近壓力區
        if tech.resistance and tech.close and tech.close >= tech.resistance * 0.97:
            deduct += 10
            factors.append("接近前波壓力區，需留意短線賣壓")

        # 均線空頭排列
        if tech.ma_trend == "bearish":
            deduct += 15
            factors.append("均線呈空頭排列，趨勢偏弱")

        # 技術面自帶風險信號
        for sig in tech.risk_signals:
            if sig not in factors:
                factors.append(sig)

        return deduct, factors

    def _chip_risk(self, behavior) -> tuple:
        """籌碼風險扣分。"""
        deduct = 0
        factors = []

        if behavior.foreign_signal == "bearish":
            deduct += 15
            factors.append("外資持續賣超，市場資金流出")
        if behavior.trust_signal == "bearish":
            deduct += 10
            factors.append("投信調節持股")
        if behavior.margin_signal == "risky":
            deduct += 15
            factors.append("融資快速增加，散戶大量追價，短線風險升高")

        return deduct, factors

    def _company_risk(self, fin_summary: dict) -> tuple:
        """公司財務風險扣分。"""
        deduct = 0
        factors = []

        eps_trend = fin_summary.get("eps_trend", "unknown")
        if eps_trend == "down":
            deduct += 20
            factors.append("EPS 呈衰退趨勢，獲利能力下降")

        roe_trend = fin_summary.get("roe_trend", "unknown")
        if roe_trend == "down":
            deduct += 15
            factors.append("ROE 下降，股東權益報酬率惡化")

        debt_ratio = fin_summary.get("debt_ratio")
        if debt_ratio and debt_ratio > 70:
            deduct += 15
            factors.append(f"負債比率 {debt_ratio:.0f}% 偏高，財務槓桿風險需關注")

        free_cf = fin_summary.get("free_cash_flow")
        if free_cf is not None and free_cf < 0:
            deduct += 10
            factors.append("自由現金流為負")

        return deduct, factors

    def _liquidity_risk(
        self,
        volume: Optional[float],
        avg_volume: Optional[float],
    ) -> tuple:
        """流動性風險扣分。"""
        deduct = 0
        factors = []

        if volume is None or avg_volume is None:
            return deduct, factors

        if avg_volume < 100:  # 日均成交量 < 100 張
            deduct += 25
            factors.append(f"成交量偏低（均量 {avg_volume:.0f} 張），流動性不足")
        elif avg_volume < 500:
            deduct += 10
            factors.append(f"成交量略低（均量 {avg_volume:.0f} 張），部位調整彈性有限")

        # 今日量異常萎縮
        if volume < avg_volume * 0.3:
            deduct += 5
            factors.append("今日成交量異常萎縮")

        return deduct, factors

    def _market_risk(self, market_sentiment: dict) -> tuple:
        """市場整體風險扣分。"""
        deduct = 0
        factors = []

        sentiment = market_sentiment.get("sentiment", "Neutral")
        if sentiment == "Bearish":
            deduct += 15
            factors.append("大盤情緒偏空，整體市場風險升高")
        elif sentiment == "Neutral":
            deduct += 5

        return deduct, factors

    def _event_risk(self, events: List[str]) -> tuple:
        """即將到來的重大事件風險扣分。"""
        deduct = 0
        factors = []

        if not events:
            return deduct, factors

        for evt in events:
            evt_upper = evt.upper()
            if "財報" in evt_upper:
                deduct += 10
                factors.append(f"即將公布財報：{evt}，短期波動可能增加")
            elif "法說" in evt_upper:
                deduct += 8
                factors.append(f"即將舉行法說會：{evt}，關注管理層展望")
            elif "FED" in evt_upper or "聯準會" in evt_upper:
                deduct += 8
                factors.append("聯準會即將公布利率決策，市場可能波動")
            elif "CPI" in evt_upper:
                deduct += 5
                factors.append("CPI 數據即將公布，通膨走勢仍存不確定性")

        # 扣分上限
        deduct = min(deduct, 30)
        return deduct, factors

    def _to_grade(self, score: float) -> str:
        if score >= 80:
            return "A"  # 低風險
        elif score >= 65:
            return "B"  # 普通
        elif score >= 50:
            return "C"  # 偏高
        elif score >= 35:
            return "D"  # 高風險
        return "E"  # 避免研究

    def _build_summary(self, r: "RiskResult") -> str:
        if not r.risk_factors:
            return "整體風險可控。"
        top = r.risk_factors[:3]
        desc = "；".join(top)
        grade_desc = {
            "A": "整體風險偏低",
            "B": "風險普通，可適度關注",
            "C": "風險偏高，建議謹慎",
            "D": "高風險，建議等待訊號改善",
            "E": "風險過高，建議迴避",
        }
        return f"{grade_desc.get(r.risk_grade, '')}。主要風險：{desc}。"
