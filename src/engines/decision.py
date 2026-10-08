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

from config import (
    AFFORDABILITY,
    RECOMMENDATION_LEVELS,
    RECOMMENDATION_RULES,
    SCORE_WEIGHTS,
    WATCH_LIST_RULES,
)

logger = logging.getLogger(__name__)


@dataclass
class StockRecommendation:
    """單一股票推薦結果"""

    stock_id: str
    name: str = ""
    date: Optional[date] = None
    # 各模組分數
    quality_score: float = 0.0      # Fundamental（0-100）
    timing_score: float = 0.0       # Price/Technical（0-100）
    behavior_score: float = 0.0     # Momentum/Behavior（0-100）
    intelligence_score: float = 0.0  # Institutional/Flow（0-100）
    risk_score: float = 100.0        # Risk（0-100，越高越安全）
    total_score: float = 0.0
    # 推薦等級與信心
    rec_level: str = "D"
    stars: str = "★☆☆☆☆"
    confidence: float = 0.0
    # Explainable AI
    summary: str = ""
    advantages: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    watch_points: List[str] = field(default_factory=list)
    ai_conclusion: str = ""
    # 附加資訊
    quality_grade: str = "D"
    close: Optional[float] = None
    volume: Optional[float] = None
    market: str = ""
    industry: str = ""
    skip_reason: str = ""
    # 橫斷面排名
    percentile: float = 0.0
    tier: str = "none"
    # 分數動能（由 main.py _enrich_score_changes 填入）
    score_change_5d: Optional[float] = None
    score_change_10d: Optional[float] = None
    timing_change_5d: Optional[float] = None
    behavior_change_5d: Optional[float] = None
    # 推薦冷卻
    days_since_rec: Optional[int] = None
    on_cooldown: bool = False
    cooldown_override: bool = False
    # ── V2 Price Trend 欄位 ──────────────────────────────────
    price_trend_score: float = 0.0    # PriceTrend 0-100（V2: 45%）
    setup_type: str = "none"          # breakout/pullback_buy/pullback_hold/trending/breakdown/none
    ma20_gap: Optional[float] = None  # (close−MA20)/MA20 × 100%
    trade_signal: str = "wait"        # strong_buy/buy/wait/reduce/sell
    # ── 短線交易關鍵欄位 ─────────────────────────────────────
    atr: Optional[float] = None       # 14日 ATR（止損/目標計算用）
    entry_low: Optional[float] = None
    entry_high: Optional[float] = None
    stop_price: Optional[float] = None
    target1: Optional[float] = None
    target2: Optional[float] = None
    expected_holding: str = ""
    vol_ratio: Optional[float] = None


class DecisionEngine:
    """
    AI 決策引擎（CIO AI）。

    評分公式（PRD Chapter 9）：
    Total Score = Quality(40%) + Timing(25%) + Behavior(20%) + Intelligence(10%) - Risk Penalty(5%)
    """

    def __init__(self, weights: dict = None, rules: dict = None):
        self.weights = weights or SCORE_WEIGHTS
        self.rules = rules or RECOMMENDATION_RULES

    def evaluate(
        self,
        stock_id: str,
        quality_result=None,
        technical_result=None,
        behavior_result=None,
        risk_result=None,
        price_trend_result=None,      # V2 新增
        intelligence_score: float = 60.0,
        has_real_intelligence: bool = False,
        name: str = "",
        close: Optional[float] = None,
        volume: Optional[float] = None,
        market: str = "",
        industry: str = "",
        trade_date: Optional[date] = None,
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

        # ── 提取各模組分數 ──────────────────────────────────────
        q_score  = quality_result.quality_score if quality_result else 0.0
        # V2: timing_score 改為 momentum_score (RSI+MACD)；若無 V2 欄位則 fallback 舊 timing_score
        t_score  = getattr(technical_result, "momentum_score",
                           (technical_result.timing_score if technical_result else 0.0))
        b_score  = behavior_result.behavior_score if behavior_result else 50.0
        r_score  = risk_result.risk_score if risk_result else 100.0
        pt_score = price_trend_result.price_trend_score if price_trend_result else 0.0
        has_chip = behavior_result.has_real_chip_data if behavior_result else False

        rec.quality_score      = q_score
        rec.timing_score       = t_score   # momentum
        rec.behavior_score     = b_score
        rec.risk_score         = r_score
        rec.price_trend_score  = pt_score
        rec.quality_grade      = quality_result.quality_grade if quality_result else "D"

        # ── V2 Price Trend 細節 ─────────────────────────────────
        if price_trend_result:
            rec.setup_type   = price_trend_result.setup_type
            rec.ma20_gap     = price_trend_result.ma20_gap
            rec.vol_ratio    = price_trend_result.volume_ratio
            rec.trade_signal = price_trend_result.trade_signal
            rec.expected_holding = self._estimate_holding(rec.setup_type)
        elif technical_result:
            # fallback to technical_result (V1 compat)
            rec.setup_type = getattr(technical_result, "setup_type", "none")
            rec.vol_ratio  = getattr(technical_result, "vol_ratio", None)
            rec.expected_holding = self._estimate_holding(rec.setup_type)

        # ── ATR 進出場計算 ──────────────────────────────────────
        if technical_result:
            rec.atr = getattr(technical_result, "atr", None)
            if close and rec.atr:
                atr = rec.atr
                rec.entry_low  = round(close - 0.3 * atr, 2)
                rec.entry_high = round(close + 0.3 * atr, 2)
                rec.stop_price = round(close - 2.0 * atr, 2)
                rec.target1    = round(close + 2.5 * atr, 2)
                rec.target2    = round(close + 5.0 * atr, 2)

        # ── 計算綜合評分（Dynamic Weighting）─────────────────────
        # V2 weights: price_trend(45%) + timing/momentum(15%) + behavior(15%) + quality(20%) + risk(5%)
        w = dict(self.weights)

        if q_score == 0.0:
            # 無基本面資料：把 quality 等比分給 price_trend / timing / behavior
            active = {k: v for k, v in w.items()
                      if k not in ("quality", "risk", "intelligence") and v > 0}
            active_sum = sum(active.values())
            if active_sum > 0:
                extra = w["quality"]
                for k in active:
                    w[k] += extra * (w[k] / active_sum)
            w["quality"] = 0.0

        if not has_chip:
            # 無真實籌碼資料：把 behavior 分給 price_trend / timing
            active = {k: v for k, v in w.items()
                      if k in ("price_trend", "timing") and v > 0}
            active_sum = sum(active.values())
            if active_sum > 0:
                extra = w["behavior"]
                for k in active:
                    w[k] += extra * (w[k] / active_sum)
            w["behavior"] = 0.0
            b_score = 0.0

        # intelligence 在 V2 中為 0，不影響計算
        base_score = (
            pt_score * w.get("price_trend", 0)
            + t_score  * w["timing"]
            + b_score  * w["behavior"]
            + q_score  * w["quality"]
        )
        risk_penalty = (100 - r_score) * w["risk"]
        total_score = round(max(0.0, min(100.0, base_score - risk_penalty)), 1)
        rec.total_score = total_score

        # ── 推薦等級 ──────────────────────────────────────────
        rec.rec_level, rec.stars = self._to_level(total_score)

        # ── 信心分數 ──────────────────────────────────────────
        rec.confidence = self._calc_confidence(
            quality_result, technical_result, behavior_result, risk_result
        )

        # ── Explainable AI（收集加分/扣分因素）────────────────
        advantages = []
        risks = []

        if quality_result:
            advantages.extend(quality_result.factors_plus[:3])
            risks.extend(quality_result.factors_minus[:2])

        if technical_result:
            if technical_result.ma_trend == "bullish":
                advantages.append("均線多頭排列，中期趨勢健康")
            if technical_result.volume_signal == "price_up_vol_up":
                advantages.append("量價俱揚，買盤積極")
            if (
                technical_result.three_major
                if hasattr(technical_result, "three_major")
                else False
            ):
                advantages.append("三大法人同步買超")
            risks.extend(technical_result.risk_signals[:2])

        if behavior_result:
            advantages.extend(behavior_result.factors_plus[:2])
            risks.extend(behavior_result.factors_minus[:2])

        if risk_result:
            risks.extend(risk_result.risk_factors[:3])

        rec.advantages = list(dict.fromkeys(advantages))[:5]  # 去重，最多5條
        rec.risks = list(dict.fromkeys(risks))[:5]
        rec.watch_points = self._build_watch_points(
            quality_result, technical_result, trade_date
        )
        rec.summary = self._build_summary(rec)
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
        bear_mode: bool = False,
        caution_mode: bool = False,
    ) -> Tuple[List[StockRecommendation], str]:
        """
        Core Picks：依總分絕對值排序，可重複出現（不受 cooldown 限制）。
        New Opportunities 另由 select_opportunities() 產生。
        """
        max_n = max_n or self.rules["max_daily_recs"]
        min_conf = self.rules["min_confidence"]

        allowed_levels = ("A+", "A", "B")
        if bear_mode:
            allowed_levels = ("A+", "A")
            max_n = 1
            min_conf = max(min_conf, 75.0)
            logger.info(
                f"[Decision] 空頭模式：僅接受 A/A+，信心≥{min_conf:.0f}%，最多 1 檔"
            )
        elif caution_mode:
            max_n = min(max_n, 2)
            min_conf = max(min_conf, 75.0)
            logger.info(
                f"[Decision] 謹慎模式：接受 A+/A/B，信心≥{min_conf:.0f}%，最多 {max_n} 檔"
            )
        else:
            logger.info(
                f"[Decision] 多頭模式：接受 A+/A/B，信心≥{min_conf:.0f}%，最多 {max_n} 檔"
            )

        # ── V2 多關卡篩選 ────────────────────────────────────────
        # Gate 1: 等級 + 信心（原有）
        # Gate 2: PriceTrend >= 60（趨勢門檻），V1 compat 用 timing_score 代替
        # Gate 3: 排除 breakdown（無論分數多高，趨勢已破壞）
        # Gate 4: trade_signal != "sell"
        def _passes_v2_gate(r: StockRecommendation) -> bool:
            pt = r.price_trend_score
            # 若 price_trend_score 未填（V1 資料），用 timing_score 近似
            trend_ok = (pt >= 60) if pt > 0 else (r.timing_score >= 55)
            if not trend_ok:
                return False
            if r.setup_type == "breakdown":
                return False
            if r.trade_signal == "sell":
                return False
            return True

        qualified = [
            r for r in candidates
            if r.confidence >= min_conf
            and r.rec_level in allowed_levels
            and _passes_v2_gate(r)
        ]

        if not qualified:
            reason = (
                f"今日沒有符合本研究策略的股票。"
                f"（信心≥{min_conf:.0f}%、等級{'/'.join(allowed_levels)}、"
                f"PriceTrend≥60 且無 breakdown，三關卡均未通過）"
            )
            return [], reason

        qualified.sort(key=lambda r: r.total_score, reverse=True)
        top_n: list = []
        industry_count: dict = {}
        max_per_industry = 2
        for r in qualified:
            ind = (r.industry or "其他").strip()
            if industry_count.get(ind, 0) >= max_per_industry:
                continue
            top_n.append(r)
            industry_count[ind] = industry_count.get(ind, 0) + 1
            if len(top_n) >= max_n:
                break
        reason = f"今日共有 {len(qualified)} 檔符合條件，Core Picks 取評分最高的 {len(top_n)} 檔（同產業上限 {max_per_industry} 支）。"
        return top_n, reason

    def select_opportunities(
        self,
        candidates: List[StockRecommendation],
        exclude_ids: set,
        max_n: int = 5,
        min_score: float = 55.0,
        min_score_momentum: float = 5.0,
        min_component_change: float = 8.0,
    ) -> List[StockRecommendation]:
        """
        Rising Opportunities：近 5D 分數快速轉強的標的（獨立於 Core Picks）。

        入選條件（全部 AND）：
          1. 不在 Core Picks 名單（exclude_ids）
          2. total_score >= 55（品質底線，比 Core 寬鬆）
          3. 不在冷卻期，或已觸發 breakout exception
          4. score_change_5d >= 5（總分近 5D 上升 5 分以上）
          5. timing_change_5d >= 8 OR behavior_change_5d >= 8（至少一個分項也明顯改善）

        排序：score_change_5d 降序。
        """
        opps = []
        for r in candidates:
            if r.stock_id in exclude_ids:
                continue
            if r.total_score < min_score:
                continue
            if r.on_cooldown and not r.cooldown_override:
                continue
            # 總分動能必要條件
            if r.score_change_5d is None or r.score_change_5d < min_score_momentum:
                continue
            # 至少一個分項也有明顯改善
            component_rising = (
                (r.timing_change_5d is not None and r.timing_change_5d >= min_component_change)
                or (r.behavior_change_5d is not None and r.behavior_change_5d >= min_component_change)
            )
            if not component_rising:
                continue
            opps.append(r)

        opps.sort(key=lambda r: (r.score_change_5d or 0), reverse=True)
        result = opps[:max_n]
        for r in result:
            r.tier = "opportunity"
        return result

    def assign_percentiles(
        self, candidates: List[StockRecommendation]
    ) -> List[StockRecommendation]:
        """
        為當日所有候選股計算橫斷面 percentile（依 total_score 排名）。

        percentile = 分數不高於本檔的候選比例 × 100（0-100，越高代表當日相對越強）。
        會直接寫入每檔的 .percentile 欄位並回傳同一份 list。
        """
        n = len(candidates)
        if n == 0:
            return candidates
        if n == 1:
            candidates[0].percentile = 100.0
            return candidates
        # 依分數升冪排名，計算每檔的 percentile rank
        ordered = sorted(candidates, key=lambda r: r.total_score)
        for i, r in enumerate(ordered):
            # i 檔分數 <= 本檔（含自己）；用 (低於本檔的數量)/(n-1) 標準化到 0-100
            below = sum(1 for x in ordered if x.total_score < r.total_score)
            r.percentile = round(below / (n - 1) * 100, 1)
        return candidates

    def select_watchlist(
        self,
        candidates: List[StockRecommendation],
        exclude_ids: Optional[set] = None,
    ) -> List[StockRecommendation]:
        """
        選出「觀察名單」：未達正式推薦、但為當日相對最強的一群。

        採雙軌條件（見 config.WATCH_LIST_RULES）：
          - 絕對底線：total_score >= min_score
          - 相對排名：percentile >= top_percentile（當日前 X%）
          - 信心：confidence >= min_confidence
        會先呼叫 assign_percentiles，並將入選者 tier 設為 "watch"。
        """
        exclude_ids = exclude_ids or set()
        self.assign_percentiles(candidates)

        rules = WATCH_LIST_RULES
        watch = [
            r
            for r in candidates
            if r.stock_id not in exclude_ids
            and r.total_score >= rules["min_score"]
            and r.percentile >= rules["top_percentile"]
            and r.confidence >= rules["min_confidence"]
        ]
        watch.sort(key=lambda r: r.total_score, reverse=True)
        watch = watch[: rules["max_watch"]]
        for r in watch:
            r.tier = "watch"
        return watch

    def select_affordable(
        self,
        candidates: List[StockRecommendation],
        max_price: Optional[float] = None,
        max_lot_cost: Optional[float] = None,
    ) -> List[StockRecommendation]:
        """
        可負擔性榜（預算榜）：在「評分之後」額外篩出資金可負擔的最佳標的。

        重要：股票評分本身完全不看股價，此處不對任何股票加減分；
        高價股只是不出現在這張榜，而非被扣分。

        條件（見 config.AFFORDABILITY，可由參數覆寫）：
          - 股價 <= max_price
          - 單張成本（股價 × 每張股數）<= max_lot_cost
          - total_score >= min_score（品質底線，避免列出便宜但體質差的股票）
        依 total_score 由高到低排序，取前 max_list 檔。
        """
        cfg = AFFORDABILITY
        max_price = cfg["max_price"] if max_price is None else max_price
        max_lot_cost = cfg["max_lot_cost"] if max_lot_cost is None else max_lot_cost
        shares = cfg["shares_per_lot"]
        min_score = cfg["min_score"]

        affordable = []
        for r in candidates:
            price = r.close
            if price is None or price <= 0:
                continue
            if max_price is not None and price > max_price:
                continue
            if max_lot_cost is not None and price * shares > max_lot_cost:
                continue
            if r.total_score < min_score:
                continue
            affordable.append(r)

        affordable.sort(key=lambda r: r.total_score, reverse=True)
        return affordable[: cfg["max_list"]]

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
        短線信心分數：以技術面為主軸，基本面負責排除惡化。
        - 技術面是主要驅動，技術差直接大幅扣分
        - 基本面惡化（D級）才扣分；中性/良好不扣
        - 籌碼缺失扣分但影響較小
        """
        confidence = 100.0

        # 技術面是主軸：技術差 → 大幅扣分
        if technical_result is None or technical_result.timing_score == 0:
            confidence -= 30
        elif technical_result.timing_score < 50:
            confidence -= 20
        elif technical_result.timing_score < 60:
            confidence -= 10

        # 基本面：只在明顯惡化時扣分（D = 惡化，C = 小扣）
        if quality_result and quality_result.has_sufficient_data:
            if quality_result.quality_grade == "D":
                confidence -= 20   # 基本面明顯惡化
            elif quality_result.quality_grade == "C":
                confidence -= 8
            # A/A+/B：不扣分（技術優先，基本面只負責排除惡化）
        else:
            confidence -= 8    # 無財務資料：小幅扣（不確定因素）

        # 籌碼缺失
        if behavior_result is None:
            confidence -= 5

        # 風險
        if risk_result:
            if risk_result.risk_score < 50:
                confidence -= 20
            elif risk_result.risk_score < 65:
                confidence -= 10

        # Setup 型態加分
        if technical_result:
            st = getattr(technical_result, "setup_type", "none")
            if st in ("breakout", "pullback_hold"):
                confidence += 5

        return round(max(0.0, min(100.0, confidence)), 1)

    def _estimate_holding(self, setup_type: str) -> str:
        return {
            "breakout":     "15–30 交易日",
            "pullback_hold": "20–40 交易日",
            "trending":     "20–50 交易日",
            "none":         "20–40 交易日",
        }.get(setup_type, "20–40 交易日")

    def _build_summary(self, rec: StockRecommendation) -> str:
        """一句話推薦摘要（短線版）。"""
        setup_desc = {
            "breakout":     "突破型，股價接近或站上20日新高",
            "pullback_hold": "回踩守穩，回踩均線後支撐有效",
            "trending":     "趨勢延伸，均線多頭排列中",
            "none":         "等待更明確的進場訊號",
        }
        level_desc = {
            "A+": "Short-term Bullish（強勢）",
            "A":  "Short-term Bullish",
            "B":  "Watch（接近條件）",
            "C":  "觀望",
            "D":  "不建議",
        }
        setup = setup_desc.get(rec.setup_type, "")
        level = level_desc.get(rec.rec_level, "")
        return f"{level}；{setup}" if setup and rec.rec_level in ("A+", "A", "B") else level

    def _build_conclusion(self, rec: StockRecommendation) -> str:
        """短線決策結論：技術面為主，基本面確認。"""
        parts = []

        # 技術面（主軸）
        if rec.timing_score >= 75:
            parts.append(f"技術面強勢（{rec.timing_score:.0f}分），{rec.summary}")
        elif rec.timing_score >= 60:
            parts.append(f"技術面偏多（{rec.timing_score:.0f}分），有進場條件")
        else:
            parts.append(f"技術面偏弱（{rec.timing_score:.0f}分），建議等待轉強")

        # 基本面（確認角色）
        if rec.quality_grade in ("A+", "A"):
            parts.append(f"基本面確認無惡化（{rec.quality_grade}）")
        elif rec.quality_grade == "D":
            parts.append(f"注意：基本面出現惡化訊號，需謹慎")

        # 法人
        if rec.behavior_score >= 70:
            parts.append("籌碼面偏多，法人有買進跡象")

        # 進出場參考
        if rec.entry_low and rec.stop_price and rec.target1:
            parts.append(
                f"參考進場 {rec.entry_low}–{rec.entry_high}，"
                f"止損 {rec.stop_price}，"
                f"目標 {rec.target1}（T1）/ {rec.target2}（T2）"
            )
            parts.append(f"預估持有：{rec.expected_holding}")

        if rec.risks:
            parts.append(f"主要風險：{'；'.join(rec.risks[:2])}")

        return "。".join(parts) + "。"

    def _build_watch_points(
        self,
        quality_result,
        technical_result,
        trade_date,
    ) -> List[str]:
        """短線觀察重點：技術面為主。"""
        points = []

        if technical_result:
            st = getattr(technical_result, "setup_type", "none")
            if st == "breakout":
                points.append("確認突破後能否站穩，量能是否持續")
            elif st == "pullback_hold":
                points.append("確認 MA20 是否守穩，不破支撐")
            elif st == "trending":
                points.append("確認均線多頭排列持續，量不萎縮")
            if technical_result.resistance:
                points.append(f"關注前波壓力 {technical_result.resistance:.2f} 是否有效突破")
        if quality_result and quality_result.factors_minus:
            points.append(f"基本面注意：{quality_result.factors_minus[0]}")
        points.append("法人籌碼是否連續買超")

        return points[:4]
