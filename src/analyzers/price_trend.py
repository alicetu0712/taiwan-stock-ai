"""
price_trend.py — Price / MA / Volume 趨勢分析（V2 架構 45% 核心）

從 technical.py 獨立拆出：「趨勢」與「技術指標」是兩件不同的事。

評分構成（0-100，等比映射自原始 45 分滿分）：
  ① MA Structure      12  均線相對位置（Price > MA5 > MA10 > MA20 > MA60）
  ② MA Slope           8  MA20（0-5）+ MA60（0-3）趨勢方向
  ③ Price/MA Deviation  8  乖離率：追高風險 & 回踩機會
  ④ Breakout/Pullback  10  交易型態辨識（含量比加權）
  ⑤ Volume Confirm     7  成交量確認真假突破

Trade Signal（進場者視角）：strong_buy / buy / wait / reduce / sell
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from config import TA_CONFIG

logger = logging.getLogger(__name__)

_RAW_MAX = 45.0


@dataclass
class PriceTrendResult:
    stock_id: str
    price_trend_score: float = 0.0   # 0-100

    # Sub-scores (raw, for debug / backtest attribution)
    ma_structure_score: float = 0.0  # max 12
    ma_slope_score: float = 0.0      # max 8
    deviation_score: float = 0.0     # max 8
    setup_score: float = 0.0         # max 10
    volume_score: float = 0.0        # max 7

    # MA values
    close: Optional[float] = None
    ma5:   Optional[float] = None
    ma10:  Optional[float] = None
    ma20:  Optional[float] = None
    ma60:  Optional[float] = None

    # Key metrics (stored in DB)
    ma20_gap: Optional[float] = None     # (close − MA20) / MA20 × 100
    ma60_gap: Optional[float] = None
    volume_ratio: Optional[float] = None

    # Trend & Setup
    ma_trend: str = "neutral"           # bullish / bullish_weak / neutral / bearish
    ma20_slope: str = "neutral"         # up / flat / down
    ma60_slope: str = "neutral"
    setup_type: str = "none"            # breakout / pullback_buy / pullback_hold
                                        # trending / overextended / breakdown / none
    trade_signal: str = "wait"          # strong_buy / buy / wait / reduce / sell

    risk_signals: List[str] = field(default_factory=list)
    summary: str = ""


class PriceTrendAnalyzer:
    MIN_HISTORY = TA_CONFIG["min_history"]

    def analyze(self, stock_id: str, history: pd.DataFrame) -> PriceTrendResult:
        result = PriceTrendResult(stock_id=stock_id)

        if history is None or len(history) < self.MIN_HISTORY:
            result.summary = f"歷史資料不足（{len(history) if history is not None else 0}天）"
            return result

        hist = history.sort_values("date").reset_index(drop=True)
        close  = hist["close"].values.astype(float)
        volume = hist["volume"].values.astype(float) if "volume" in hist.columns else np.ones(len(hist))
        high   = hist["high"].values.astype(float) if "high" in hist.columns else close
        low    = hist["low"].values.astype(float) if "low" in hist.columns else close  # noqa: F841

        risk_signals = []

        # ── 計算均線 ─────────────────────────────────────────────
        ma_vals = self._calc_mas(close)
        cur = float(close[-1])
        result.close = cur
        result.ma5  = ma_vals.get("ma5")
        result.ma10 = ma_vals.get("ma10")
        result.ma20 = ma_vals.get("ma20")
        result.ma60 = ma_vals.get("ma60")

        # ── ① MA Structure（12分）────────────────────────────────
        ms_score, ma_trend = self._score_ma_structure(cur, ma_vals)
        result.ma_structure_score = ms_score
        result.ma_trend = ma_trend

        # ── ② MA Slope（8分）─────────────────────────────────────
        sl_score, ma20_slope, ma60_slope = self._score_ma_slope(close)
        result.ma_slope_score = sl_score
        result.ma20_slope = ma20_slope
        result.ma60_slope = ma60_slope

        # ── ③ Deviation（8分）────────────────────────────────────
        dv_score, ma20_gap, ma60_gap = self._score_deviation(cur, ma_vals)
        result.deviation_score = dv_score
        result.ma20_gap = ma20_gap
        result.ma60_gap = ma60_gap

        # ── ④ Breakout / Pullback Setup（10分）───────────────────
        vol_ratio = self._calc_vol_ratio(volume)
        result.volume_ratio = vol_ratio
        breakout_20d, near_20d = self._check_breakout(close, high)
        setup = self._detect_setup(cur, ma_vals, ma_trend, ma20_slope, breakout_20d, near_20d, vol_ratio)
        result.setup_type = setup
        result.setup_score = self._score_setup(setup, vol_ratio)

        # ── ⑤ Volume Confirmation（7分）──────────────────────────
        result.volume_score = self._score_volume(close, volume, setup, vol_ratio)

        # ── 合計 → normalize to 0-100 ────────────────────────────
        raw = (result.ma_structure_score + result.ma_slope_score +
               result.deviation_score + result.setup_score + result.volume_score)
        result.price_trend_score = round(max(0.0, min(100.0, raw / _RAW_MAX * 100)), 1)

        # ── Risk Signals ──────────────────────────────────────────
        if ma20_gap is not None and ma20_gap >= 15:
            risk_signals.append(f"MA20 乖離 {ma20_gap:.1f}%，追高風險高")
        elif ma20_gap is not None and ma20_gap >= 10:
            risk_signals.append(f"MA20 乖離 {ma20_gap:.1f}%，留意拉回")
        if setup == "breakdown":
            risk_signals.append("跌破 MA20 且均線下彎，趨勢破壞")
        result.risk_signals = risk_signals

        # ── Trade Signal ──────────────────────────────────────────
        result.trade_signal = self._determine_signal(result)
        result.summary = self._build_summary(result)

        logger.debug(
            f"{stock_id}: PriceTrend={result.price_trend_score:.1f} "
            f"Setup={setup} Signal={result.trade_signal} MA20Gap={ma20_gap}"
        )
        return result

    # ── 均線計算 ──────────────────────────────────────────────────

    def _calc_mas(self, close: np.ndarray) -> Dict[str, float]:
        n = len(close)
        return {
            f"ma{p}": float(np.mean(close[-p:]))
            for p in TA_CONFIG["ma_periods"] if n >= p
        }

    # ── ① MA Structure ────────────────────────────────────────────

    def _score_ma_structure(self, cur: float, mas: Dict) -> Tuple[float, str]:
        """多頭層級（12分）：完美排列最高，完美空頭最低"""
        ma5  = mas.get("ma5")
        ma10 = mas.get("ma10")
        ma20 = mas.get("ma20")
        ma60 = mas.get("ma60")

        if ma5 and ma10 and ma20 and ma60:
            if cur > ma5 > ma10 > ma20 > ma60:   return 12.0, "bullish"
            if cur > ma5 > ma20 > ma60:           return 10.0, "bullish"
            if cur > ma20 > ma60:                 return 8.0,  "bullish"
            if cur > ma20 and cur > ma60:         return 6.0,  "bullish_weak"
            if cur > ma20 or cur > ma60:          return 4.0,  "neutral"
            if cur < ma5 < ma10 < ma20 < ma60:   return 0.0,  "bearish"
            if cur < ma20 < ma60:                 return 1.0,  "bearish"
            if cur < ma20:                        return 2.0,  "bearish"
            return 3.0, "neutral"

        if ma5 and ma20:
            if cur > ma5 > ma20:   return 8.0, "bullish"
            if cur > ma20:         return 5.0, "bullish_weak"
            if cur < ma20:         return 2.0, "bearish"

        return 4.0, "neutral"

    # ── ② MA Slope ────────────────────────────────────────────────

    def _score_ma_slope(self, close: np.ndarray) -> Tuple[float, str, str]:
        """MA20 斜率（0-5）+ MA60 斜率（0-3）共 8 分"""
        n = len(close)
        score = 0.0
        ma20_slope = "flat"
        ma60_slope = "flat"

        if n >= 25:
            ma20_now = float(np.mean(close[-20:]))
            ma20_5d  = float(np.mean(close[-25:-5]))
            pct = (ma20_now - ma20_5d) / ma20_5d * 100 if ma20_5d else 0
            if pct > 0.3:
                score += 5; ma20_slope = "up"
            elif pct > 0.05:
                score += 3; ma20_slope = "up"
            elif pct > -0.05:
                score += 2; ma20_slope = "flat"
            elif pct > -0.3:
                score += 1; ma20_slope = "down"
            else:
                score += 0; ma20_slope = "down"

        if n >= 70:
            ma60_now = float(np.mean(close[-60:]))
            ma60_10d = float(np.mean(close[-70:-10]))
            pct = (ma60_now - ma60_10d) / ma60_10d * 100 if ma60_10d else 0
            if pct > 0.2:
                score += 3; ma60_slope = "up"
            elif pct > -0.1:
                score += 2; ma60_slope = "flat"
            else:
                score += 0; ma60_slope = "down"

        return min(score, 8.0), ma20_slope, ma60_slope

    # ── ③ Deviation ──────────────────────────────────────────────

    def _score_deviation(
        self, cur: float, mas: Dict
    ) -> Tuple[float, Optional[float], Optional[float]]:
        """乖離率（8分）：健康位置加分，過熱扣分，回踩帶中高分"""
        ma20 = mas.get("ma20")
        ma60 = mas.get("ma60")
        ma20_gap = None
        ma60_gap = None
        score = 4.0  # default 中性

        if ma20 and ma20 > 0:
            ma20_gap = round((cur - ma20) / ma20 * 100, 2)
            if   0   <= ma20_gap <  3:  score = 8.0   # 健康位置
            elif 3   <= ma20_gap <  5:  score = 7.0
            elif 5   <= ma20_gap <  8:  score = 5.0
            elif 8   <= ma20_gap < 12:  score = 3.0
            elif 12  <= ma20_gap < 15:  score = 1.0
            elif ma20_gap >= 15:        score = 0.0   # 過熱，不追
            elif -5  <  ma20_gap < 0:   score = 6.0   # 回踩帶（接近MA20）
            elif -10 <  ma20_gap <= -5: score = 3.0   # 跌到MA20下方
            else:                       score = 1.0   # 深度跌破

        if ma60 and ma60 > 0:
            ma60_gap = round((cur - ma60) / ma60 * 100, 2)

        return score, ma20_gap, ma60_gap

    # ── ④ Breakout / Pullback ─────────────────────────────────────

    def _calc_vol_ratio(self, volume: np.ndarray) -> Optional[float]:
        if len(volume) < 20:
            return None
        vol_ma = float(np.mean(volume[-20:]))
        return round(float(volume[-1]) / vol_ma, 2) if vol_ma > 0 else None

    def _check_breakout(self, close: np.ndarray, high: np.ndarray) -> Tuple[bool, bool]:
        n = len(close)
        if n < 20:
            return False, False
        high_20d = float(np.max(high[-20:]))
        cur_close = float(close[-1])
        recent_high = float(np.max(high[-5:])) if n >= 5 else float(high[-1])
        return (recent_high >= high_20d * 0.999), (cur_close >= high_20d * 0.95)

    def _detect_setup(
        self, cur: float, mas: Dict, ma_trend: str, ma20_slope: str,
        breakout_20d: bool, near_20d: bool, vol_ratio: Optional[float]
    ) -> str:
        ma10 = mas.get("ma10")
        ma20 = mas.get("ma20")

        # Breakdown：跌破 MA20 且均線下彎
        if ma20 and cur < ma20 and ma_trend == "bearish" and ma20_slope == "down":
            return "breakdown"

        # Overextended：MA20 乖離 > 15%
        if ma20 and ma20 > 0 and (cur - ma20) / ma20 * 100 > 15:
            return "overextended"

        # Breakout：近20日高點突破（量的差異由 volume_score 體現）
        if breakout_20d or near_20d:
            return "breakout"

        # Pullback Buy：多頭排列，回踩 MA10 附近（±5%），仍在 MA20 上，縮量
        if ma10 and ma20 and ma_trend in ("bullish", "bullish_weak") and \
           abs((cur - ma10) / ma10) <= 0.05 and cur > ma20 and \
           (vol_ratio is None or vol_ratio <= 1.2):
            return "pullback_buy"

        # Pullback Hold：多頭排列，回踩 MA20（0-4%以內）守穩
        if ma20 and ma_trend in ("bullish", "bullish_weak") and \
           0 <= (cur - ma20) / ma20 <= 0.04:
            return "pullback_hold"

        # Trending：多頭排列延伸
        if ma_trend == "bullish" and ma20_slope == "up":
            return "trending"

        return "none"

    def _score_setup(self, setup: str, vol_ratio: Optional[float]) -> float:
        """Setup 基礎分（10分）：突破依量比加減分"""
        base = {
            "breakout":      8.0,
            "pullback_buy":  9.0,
            "pullback_hold": 7.0,
            "trending":      6.0,
            "overextended":  2.0,
            "breakdown":     0.0,
            "none":          3.0,
        }.get(setup, 3.0)

        if setup == "breakout" and vol_ratio is not None:
            if vol_ratio >= 1.5:
                base = min(base + 2, 10)
            elif vol_ratio < 0.8:
                base = max(base - 2, 0)

        return base

    # ── ⑤ Volume Confirmation ─────────────────────────────────────

    def _score_volume(
        self, close: np.ndarray, volume: np.ndarray, setup: str, vol_ratio: Optional[float]
    ) -> float:
        """量能確認（7分）：突破放量高分，縮量回踩高分，爆量跌破最低"""
        if vol_ratio is None or len(close) < 2:
            return 3.0

        price_up = float(close[-1]) >= float(close[-2])

        if setup == "breakout":
            if vol_ratio >= 2.0:  return 7.0
            if vol_ratio >= 1.5:  return 6.0
            if vol_ratio >= 1.0:  return 4.0
            return 2.0

        if setup in ("pullback_buy", "pullback_hold"):
            if vol_ratio <= 0.6:  return 7.0  # 縮量回踩最健康
            if vol_ratio <= 1.0:  return 5.0
            if vol_ratio <= 1.5:  return 3.0
            return 1.0            # 放量回踩：賣壓疑慮

        if setup == "breakdown":
            if vol_ratio >= 2.0:  return 0.0  # 爆量跌破：強賣訊
            if vol_ratio >= 1.5:  return 1.0
            return 2.0

        if setup == "trending":
            if price_up and vol_ratio >= 1.2:  return 6.0
            if price_up:                        return 4.0
            return 3.0

        if price_up and vol_ratio >= 1.5:  return 5.0
        if price_up:                        return 3.0
        return 2.0

    # ── Trade Signal ──────────────────────────────────────────────

    def _determine_signal(self, r: PriceTrendResult) -> str:
        """進場者視角：沒有持股的人應該怎麼做"""
        setup = r.setup_type
        trend = r.ma_trend
        gap   = r.ma20_gap or 0.0

        if setup == "breakdown":
            return "sell"

        if setup == "overextended" or gap >= 15:
            return "wait"

        if setup == "pullback_buy" and trend in ("bullish", "bullish_weak") and r.ma20_slope == "up":
            if r.volume_ratio is not None and r.volume_ratio <= 0.8:
                return "strong_buy"   # 縮量回踩最佳
            return "buy"

        if setup == "breakout" and trend in ("bullish", "bullish_weak"):
            if r.volume_ratio is not None and r.volume_ratio >= 1.5:
                return "strong_buy"   # 放量突破
            return "buy"

        if setup in ("pullback_hold", "trending") and trend in ("bullish", "bullish_weak"):
            return "buy"

        if trend == "bearish" and r.ma20_slope == "down":
            return "reduce"

        return "wait"

    # ── Summary ───────────────────────────────────────────────────

    def _build_summary(self, r: PriceTrendResult) -> str:
        signal_label = {
            "strong_buy": "強買", "buy": "買進",
            "wait": "等待", "reduce": "減碼", "sell": "賣出",
        }
        setup_label = {
            "breakout":      "突破前高",
            "pullback_buy":  "回踩MA10買點",
            "pullback_hold": "回踩MA20守穩",
            "trending":      "趨勢延伸",
            "overextended":  "過度乖離",
            "breakdown":     "趨勢破壞",
            "none":          "無明確型態",
        }
        trend_label = {
            "bullish": "均線多頭", "bullish_weak": "短均線偏多",
            "neutral": "趨勢中性", "bearish": "均線空頭",
        }
        parts = [
            f"訊號[{signal_label.get(r.trade_signal, r.trade_signal)}]",
            setup_label.get(r.setup_type, ""),
            trend_label.get(r.ma_trend, ""),
        ]
        if r.ma20_gap is not None:
            parts.append(f"MA20乖離{'%+.1f' % r.ma20_gap}%")
        if r.volume_ratio is not None:
            parts.append(f"量比{r.volume_ratio:.1f}×")
        if r.risk_signals:
            parts.append(f"注意：{r.risk_signals[0]}")
        return "；".join(p for p in parts if p) + "。"


def analyze_all_price_trends(price_history: pd.DataFrame) -> dict:
    """批次分析所有股票的 Price Trend，供 main.py Step 5 使用"""
    analyzer = PriceTrendAnalyzer()
    results = {}
    grouped = price_history.groupby("stock_id")
    total = len(grouped)
    logger.info(f"Running price trend analysis on {total} stocks...")
    for i, (sid, hist) in enumerate(grouped):
        if i % 200 == 0:
            logger.info(f"  Price trend progress: {i}/{total}")
        results[sid] = analyzer.analyze(sid, hist)
    qualified = sum(1 for r in results.values() if r.price_trend_score > 0)
    logger.info(f"Price trend analysis complete: {qualified}/{total} stocks scored.")
    return results
