"""
market_behavior.py — 市場行為分析引擎（PRD Chapter 7）

計算 Market Behavior Score（0-100）。
分析：外資、投信、自營商、融資、融券、市場情緒。
遵循原則：連續性優於單日、價格必須配合資金、多方交叉驗證。
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class MarketBehaviorResult:
    """市場行為分析結果"""
    stock_id:           str
    behavior_score:     float = 0.0    # 0-100
    has_real_chip_data: bool  = False  # 是否有真實籌碼資料（False=無資料，給中性分）
    foreign_signal:     str   = "neutral"   # bullish / bearish / neutral
    trust_signal:       str   = "neutral"
    dealer_signal:      str   = "neutral"
    three_major:        bool  = False    # 三大法人同步買超
    margin_signal:      str   = "neutral"   # healthy / risky
    factors_plus:       List[str] = field(default_factory=list)
    factors_minus:      List[str] = field(default_factory=list)
    summary:            str   = ""


class MarketBehaviorAnalyzer:
    """
    市場行為分析引擎。
    輸入：個股籌碼歷史資料（DataFrame：date, foreign_net, trust_net, dealer_net, total_net）
    輸出：MarketBehaviorResult
    """

    WEIGHTS = {
        "foreign": 35,
        "trust":   30,
        "dealer":  15,
        "margin":  20,
    }

    def analyze(
        self,
        stock_id: str,
        chip_history: pd.DataFrame,
        margin_history: Optional[pd.DataFrame] = None,
    ) -> MarketBehaviorResult:
        """主要入口：分析個股市場行為。"""
        result = MarketBehaviorResult(stock_id=stock_id)

        if chip_history is None or chip_history.empty:
            result.summary = "無籌碼資料，跳過市場行為分析。"
            result.behavior_score = 50.0   # 給中性分數
            return result

        chip = chip_history.sort_values("date").reset_index(drop=True)
        score     = 0.0
        plus, minus = [], []

        # ── 外資分析（最高 35 分）────────────────────────────
        foreign_score, f_sig, f_plus, f_minus = self._analyze_institutional(
            chip, "foreign_net", label="外資",
            max_score=self.WEIGHTS["foreign"]
        )
        score += foreign_score
        result.foreign_signal = f_sig
        plus.extend(f_plus)
        minus.extend(f_minus)

        # ── 投信分析（最高 30 分）────────────────────────────
        trust_score, t_sig, t_plus, t_minus = self._analyze_institutional(
            chip, "trust_net", label="投信",
            max_score=self.WEIGHTS["trust"]
        )
        score += trust_score
        result.trust_signal = t_sig
        plus.extend(t_plus)
        minus.extend(t_minus)

        # ── 自營商分析（最高 15 分）──────────────────────────
        dealer_score, d_sig, d_plus, d_minus = self._analyze_institutional(
            chip, "dealer_net", label="自營商",
            max_score=self.WEIGHTS["dealer"]
        )
        score += dealer_score
        result.dealer_signal = d_sig
        plus.extend(d_plus)
        minus.extend(d_minus)

        # ── 三大法人同步買超 ──────────────────────────────────
        result.three_major = self._check_three_major_sync(chip)
        if result.three_major:
            score += 5
            plus.append("三大法人同步買超，資金流向一致")

        # ── 融資分析（最高 20 分）────────────────────────────
        if margin_history is not None and not margin_history.empty:
            margin_score, m_sig, m_plus, m_minus = self._analyze_margin(
                margin_history, chip
            )
            score += margin_score
            result.margin_signal = m_sig
            plus.extend(m_plus)
            minus.extend(m_minus)
        else:
            score += 10   # 無融資資料，給中性分數

        result.behavior_score     = round(max(0.0, min(100.0, score)), 1)
        result.has_real_chip_data = True
        result.factors_plus   = plus
        result.factors_minus  = minus
        result.summary        = self._build_summary(result)

        logger.debug(f"{stock_id}: Behavior Score={result.behavior_score:.1f}")
        return result

    # ── 分析子方法 ────────────────────────────────────────────

    def _analyze_institutional(
        self,
        chip: pd.DataFrame,
        col: str,
        label: str,
        max_score: float,
    ):
        """通用法人分析（外資/投信/自營商）"""
        score = 0.0
        plus, minus = [], []

        if col not in chip.columns:
            return max_score * 0.5, "neutral", plus, minus

        # 過去 3/5/20 日
        n3  = chip[col].tail(3).sum()
        n5  = chip[col].tail(5).sum()
        n20 = chip[col].tail(20).sum()

        # 判斷連續買超天數
        consec_buy = 0
        for v in reversed(chip[col].tolist()):
            if v > 0:
                consec_buy += 1
            else:
                break

        if n3 > 0 and n5 > 0 and n20 > 0:
            # 三個區間都是買超
            score = max_score
            plus.append(f"{label}近 3/5/20 日均買超")
        elif n5 > 0:
            score = max_score * 0.75
            plus.append(f"{label}近五日買超")
        elif n3 > 0:
            score = max_score * 0.5
        elif n3 < 0 and n5 < 0:
            score = 0.0
            minus.append(f"{label}持續賣超")
        else:
            score = max_score * 0.3   # 中性

        # 連續買超天數加分
        if consec_buy >= 5:
            score = min(score + max_score * 0.1, max_score)
            plus.append(f"{label}連續買超 {consec_buy} 天")
        elif consec_buy >= 3:
            score = min(score + max_score * 0.05, max_score)

        # 由賣轉買
        if len(chip) >= 4:
            prev_5 = chip[col].iloc[-5:-1].sum() if len(chip) >= 5 else 0
            if prev_5 < 0 and n3 > 0:
                score = min(score + max_score * 0.1, max_score)
                plus.append(f"{label}由賣轉買，籌碼改善")

        if score > max_score * 0.7:
            sig = "bullish"
        elif score < max_score * 0.3:
            sig = "bearish"
        else:
            sig = "neutral"

        return score, sig, plus, minus

    def _check_three_major_sync(self, chip: pd.DataFrame) -> bool:
        """確認三大法人是否同步買超（近 3 日合計）。"""
        cols = ["foreign_net", "trust_net", "dealer_net"]
        for col in cols:
            if col not in chip.columns:
                return False
            if chip[col].tail(3).sum() <= 0:
                return False
        return True

    def _analyze_margin(
        self,
        margin: pd.DataFrame,
        chip: pd.DataFrame,
    ):
        """融資分析（最高 20 分）"""
        score = 10.0   # 中性起點
        plus, minus = [], []

        if "margin_balance" not in margin.columns:
            return score, "neutral", plus, minus

        mg = margin.sort_values("date").tail(20)
        if len(mg) < 5:
            return score, "neutral", plus, minus

        # 融資是否快速增加（過去5日增幅）
        mg_bal = mg["margin_balance"].tolist()
        if len(mg_bal) >= 5:
            change_pct = (mg_bal[-1] - mg_bal[-5]) / (abs(mg_bal[-5]) + 1e-6) * 100

            if change_pct > 20:
                score -= 10
                minus.append(f"融資快速增加 {change_pct:.0f}%，散戶追價風險升高")
                sig = "risky"
            elif change_pct > 10:
                score -= 5
                minus.append("融資略增，注意散戶追價")
                sig = "watch"
            elif change_pct < -10:
                score += 5
                plus.append("融資減少，籌碼趨於健康")
                sig = "healthy"
            else:
                sig = "neutral"
        else:
            sig = "neutral"

        # 融券回補（可能軋空）
        if "short_balance" in margin.columns and len(mg) >= 3:
            short_recent = mg["short_balance"].tail(3).mean()
            short_prev   = mg["short_balance"].iloc[:-3].tail(5).mean() if len(mg) >= 8 else short_recent
            if short_recent < short_prev * 0.8 and short_recent > 1000:
                plus.append("融券回補，可能形成軋空行情")
                score += 3

        return max(0.0, min(score, 20)), sig, plus, minus

    def _build_summary(self, r: "MarketBehaviorResult") -> str:
        parts = []
        if r.three_major:
            parts.append("三大法人同步買超")
        else:
            sig_map = {"bullish": "持續買超", "bearish": "賣超", "neutral": "中性"}
            if r.foreign_signal != "neutral":
                parts.append(f"外資{sig_map.get(r.foreign_signal, '')}")
            if r.trust_signal == "bullish":
                parts.append("投信積極布局")
        if r.margin_signal == "risky":
            parts.append("融資快增，散戶追價風險較高")
        elif r.margin_signal == "healthy":
            parts.append("籌碼結構健康")
        if not parts:
            parts.append("籌碼方向中性")
        return "；".join(parts) + "。"


def analyze_market_sentiment(
    all_prices: pd.DataFrame,
    trade_date,
) -> dict:
    """
    分析大盤市場情緒（Bullish / Neutral / Bearish）。
    """
    if all_prices.empty:
        return {"sentiment": "Neutral", "summary": "無市場資料。"}

    day_data = all_prices[all_prices["date"] == trade_date] if "date" in all_prices.columns else all_prices
    if day_data.empty:
        day_data = all_prices

    up_count    = (day_data["change_pct"] > 0).sum() if "change_pct" in day_data.columns else 0
    down_count  = (day_data["change_pct"] < 0).sum() if "change_pct" in day_data.columns else 0
    total_count = len(day_data)
    up_ratio    = up_count / total_count if total_count > 0 else 0

    if up_ratio >= 0.6:
        sentiment = "Bullish"
        desc = f"今日上漲 {up_count} 家，下跌 {down_count} 家，市場偏多"
    elif up_ratio <= 0.4:
        sentiment = "Bearish"
        desc = f"今日上漲 {up_count} 家，下跌 {down_count} 家，市場偏空"
    else:
        sentiment = "Neutral"
        desc = f"今日上漲 {up_count} 家，下跌 {down_count} 家，市場中性"

    return {
        "sentiment":   sentiment,
        "up_count":    int(up_count),
        "down_count":  int(down_count),
        "total_count": int(total_count),
        "up_ratio":    round(float(up_ratio), 3),
        "summary":     desc,
    }
