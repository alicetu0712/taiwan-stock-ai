"""
technical.py — 價格結構與技術面分析引擎（短線波段版）

核心邏輯：股價行為決定進場時機；成交量確認真假；RSI/MACD 輔助 Timing。
評分構成（100分）：
  價格結構/突破   35  20D新高、HH/HL、動能、放量確認
  MACD            20  Histogram 方向與擴張
  均線分析        20  均線結構7 + 價格位置4 + 均線斜率3 + 乖離率3 + 交叉3
  成交量確認      15  量比、漲跌量性質
  RSI             10  45-70 健康區間

Setup 類型：breakout / pullback_buy / pullback_hold / trending / breakdown / none
  pullback_buy：多頭排列中回踩 MA10 附近（縮量）後守穩 → 較佳進場點
  breakdown：跌破 MA20 且 MA5/10 下彎 → 賣出訊號
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from config import TA_CONFIG

logger = logging.getLogger(__name__)


@dataclass
class TechnicalResult:
    stock_id: str
    timing_score: float = 0.0
    ma_trend: str = "neutral"          # bullish / bearish / neutral
    volume_signal: str = "neutral"
    rsi: Optional[float] = None
    macd_signal: str = "neutral"
    kd_signal: str = "neutral"         # 保留相容性
    patterns: List[str] = field(default_factory=list)
    support: Optional[float] = None
    resistance: Optional[float] = None
    risk_signals: List[str] = field(default_factory=list)
    summary: str = ""
    ma5: Optional[float] = None
    ma20: Optional[float] = None
    ma60: Optional[float] = None
    ma120: Optional[float] = None
    ma240: Optional[float] = None
    close: Optional[float] = None
    # ── 新增：短線關鍵欄位 ──────────────────────────────────
    setup_type: str = "none"           # breakout / pullback_buy / pullback_hold / trending / breakdown / none
    breakout_20d: bool = False         # 近5日是否創20日新高
    hh_hl_structure: bool = False      # Higher Highs + Higher Lows 結構
    atr: Optional[float] = None        # 14日 ATR
    vol_ratio: Optional[float] = None  # 當日量 / 20日均量
    price_change_5d: Optional[float] = None  # 5日價格變化%
    near_20d_high: bool = False        # 股價在20日高點的95%以上
    price_structure_score: float = 0.0
    ma10: Optional[float] = None
    ma_deviation20: Optional[float] = None  # (Price - MA20) / MA20 * 100%
    ma_slope: str = "neutral"          # MA20 斜率方向：up / down / neutral


class TechnicalAnalyzer:
    MIN_HISTORY = TA_CONFIG["min_history"]

    def analyze(self, stock_id: str, history: pd.DataFrame) -> TechnicalResult:
        result = TechnicalResult(stock_id=stock_id)

        if history is None or len(history) < self.MIN_HISTORY:
            result.summary = f"歷史資料不足（{len(history) if history is not None else 0}天），無法技術分析。"
            return result

        hist = history.sort_values("date").reset_index(drop=True)
        close = hist["close"].values
        volume = hist["volume"].values
        high = hist["high"].values if "high" in hist.columns else close
        low = hist["low"].values if "low" in hist.columns else close

        score = 0.0
        risk_signals = []

        # ── 均線分析（20分）──────────────────────────────────
        ma_score, ma_trend, ma_vals, ma_dev, ma_slope = self._analyze_ma(close)
        score += ma_score
        result.ma_trend = ma_trend
        result.ma5 = ma_vals.get("ma5")
        result.ma10 = ma_vals.get("ma10")
        result.ma20 = ma_vals.get("ma20")
        result.ma60 = ma_vals.get("ma60")
        result.ma120 = ma_vals.get("ma120")
        result.ma240 = ma_vals.get("ma240")
        result.close = float(close[-1])
        result.ma_deviation20 = ma_dev
        result.ma_slope = ma_slope

        # ── 價格結構/突破（35分）────────────────────────────
        ps_score, ps_details = self._analyze_price_structure(close, high, low, volume)
        score += ps_score
        result.price_structure_score = ps_score
        result.breakout_20d = ps_details["breakout_20d"]
        result.hh_hl_structure = ps_details["hh_hl"]
        result.near_20d_high = ps_details["near_20d_high"]
        result.price_change_5d = ps_details["price_change_5d"]
        result.patterns = ps_details["patterns"]

        # ── 成交量（15分）────────────────────────────────────
        vol_score, vol_signal, vol_ratio = self._analyze_volume(close, volume)
        score += vol_score
        result.volume_signal = vol_signal
        result.vol_ratio = vol_ratio

        # ── MACD（20分）──────────────────────────────────────
        macd_score, macd_sig = self._analyze_macd(close)
        score += macd_score
        result.macd_signal = macd_sig

        # ── RSI（10分）───────────────────────────────────────
        rsi_val = self._calc_rsi(close, period=TA_CONFIG["rsi_period"])
        rsi_score, rsi_risk = self._score_rsi(rsi_val)
        score += rsi_score
        result.rsi = rsi_val
        if rsi_risk:
            risk_signals.append(rsi_risk)

        # ── ATR ─────────────────────────────────────────────
        result.atr = self._calc_atr(high, low, close)

        # ── 支撐壓力 ─────────────────────────────────────────
        result.support, result.resistance = self._find_support_resistance(
            close[-60:], high[-60:], low[-60:]
        )

        # ── 風險信號 ─────────────────────────────────────────
        if result.ma_deviation20 is not None and result.ma_deviation20 >= 15:
            risk_signals.append(f"MA20 乖離 {result.ma_deviation20:.1f}%，短線過熱勿追")
        elif result.ma_deviation20 is not None and result.ma_deviation20 >= 10:
            risk_signals.append(f"MA20 乖離 {result.ma_deviation20:.1f}%，留意拉回風險")
        if result.resistance and result.close and result.close >= result.resistance * 0.98:
            risk_signals.append("接近前波壓力區，追高需謹慎")
        if rsi_val and rsi_val > 80:
            risk_signals.append(f"RSI {rsi_val:.0f} 過熱")

        # ── Setup 判斷 ────────────────────────────────────────
        result.setup_type = self._detect_setup(result, ma_vals, close)

        result.timing_score = round(max(0.0, min(100.0, score)), 1)
        result.risk_signals = risk_signals
        result.summary = self._build_summary(result)

        logger.debug(f"{stock_id}: Timing={result.timing_score:.1f} Setup={result.setup_type}")
        return result

    # ── 分析子方法 ────────────────────────────────────────────

    def _analyze_ma(self, close: np.ndarray) -> Tuple[float, str, Dict, Optional[float], str]:
        """均線分析（20分）

        Sub-components:
          均線結構（多空排列）   7  MA5/10/20/60 相對位置
          股價 vs 均線位置      4  Price vs MA20 / MA60
          均線斜率              3  MA20 / MA60 是否向上
          乖離率                3  過度乖離懲罰 / 健康位置加分
          黃金/死亡交叉         3  MA5 穿越 MA20

        Returns: (score, trend, ma_vals, deviation20, slope_direction)
        """
        score = 0.0
        cfg = TA_CONFIG["ma_periods"]
        ma_vals = {}
        n = len(close)

        for period in cfg:
            if n >= period:
                ma_vals[f"ma{period}"] = float(np.mean(close[-period:]))

        cur = float(close[-1])
        ma5  = ma_vals.get("ma5")
        ma10 = ma_vals.get("ma10")
        ma20 = ma_vals.get("ma20")
        ma60 = ma_vals.get("ma60")
        trend = "neutral"
        slope_direction = "neutral"
        deviation = None

        # ── 均線結構（7分）──────────────────────────────────
        if ma5 and ma10 and ma20 and ma60:
            if ma5 > ma10 > ma20 > ma60:
                score += 7      # 完美多頭排列
                trend = "bullish"
            elif ma5 > ma20 > ma60:
                score += 5
                trend = "bullish"
            elif ma5 > ma20:
                score += 3
                trend = "bullish_weak"
            elif ma5 < ma10 < ma20 < ma60:
                score -= 4      # 完美空頭排列
                trend = "bearish"
            elif ma5 < ma20:
                score -= 2
                trend = "bearish"
        elif ma5 and ma20:
            if ma5 > ma20:
                score += 3
                trend = "bullish_weak"
            else:
                score -= 2
                trend = "bearish"

        # ── 股價 vs 均線位置（4分）──────────────────────────
        if ma20:
            if cur > ma20:
                score += 2
            else:
                score -= 2
        if ma60:
            if cur > ma60:
                score += 2
            else:
                score -= 2

        # ── 均線斜率（3分）：MA20 現值 vs 5日前 MA20 ────────
        if n >= 25:
            ma20_prev = float(np.mean(close[-25:-5]))
            ma20_now  = float(np.mean(close[-20:]))
            if ma20_now > ma20_prev * 1.001:
                score += 2
                slope_direction = "up"
            elif ma20_now < ma20_prev * 0.999:
                score -= 1
                slope_direction = "down"
        if n >= 65 and ma60:
            ma60_prev = float(np.mean(close[-65:-5]))
            ma60_now  = float(np.mean(close[-60:]))
            if ma60_now > ma60_prev * 1.001:
                score += 1

        # ── 乖離率（3分）────────────────────────────────────
        if ma20 and ma20 > 0:
            deviation = round((cur - ma20) / ma20 * 100, 2)
            if 0 <= deviation < 5:
                score += 2      # 健康位置，未過熱
            elif 5 <= deviation < 10:
                score += 1
            elif deviation >= 15:
                score -= 2      # 過度乖離，追高風險
            elif deviation >= 10:
                score -= 1
            # 略低於 MA20（-5% 到 0）：中性，讓 setup 判斷
            elif deviation < -5:
                score -= 1      # 跌到 MA20 下方一段，偏空

        # ── 黃金/死亡交叉（3分）─────────────────────────────
        if ma5 and ma20 and n >= 21:
            prev_ma5  = float(np.mean(close[-6:-1]))
            prev_ma20 = float(np.mean(close[-21:-1]))
            if prev_ma5 < prev_ma20 and ma5 >= ma20:
                score += 3      # MA5 黃金交叉 MA20
                if trend not in ("bullish",):
                    trend = "bullish_weak"
            elif prev_ma5 > prev_ma20 and ma5 < ma20:
                score -= 2      # MA5 死亡交叉 MA20
                if trend not in ("bearish",):
                    trend = "bearish"

        return max(0.0, min(score, 20)), trend, ma_vals, deviation, slope_direction

    def _analyze_price_structure(
        self, close: np.ndarray, high: np.ndarray, low: np.ndarray, volume: np.ndarray
    ) -> Tuple[float, dict]:
        """
        價格結構/突破分析（35分）
        - 20日新高近況      12
        - HH/HL 結構        8
        - 近5日動能          8
        - 成交放量型態        7
        """
        score = 0.0
        patterns = []
        n = len(close)

        # ── 20日新高（12分）─────────────────────────────────
        breakout_20d = False
        near_20d_high = False
        if n >= 20:
            high_20d = float(np.max(high[-20:]))
            cur_close = float(close[-1])
            # 近5日有沒有創20日新高
            recent_highs = high[-5:] if n >= 5 else high
            if float(np.max(recent_highs)) >= high_20d * 0.999:
                breakout_20d = True
                score += 12
                patterns.append("20日新高")
            elif cur_close >= high_20d * 0.95:
                near_20d_high = True
                score += 7
                patterns.append("接近20日高點")
            elif cur_close >= high_20d * 0.90:
                score += 3

        # ── HH/HL 結構（8分）────────────────────────────────
        hh_hl = False
        if n >= 15:
            # 比較近5日均高 vs 前5日均高；近5日均低 vs 前5日均低
            h_now = float(np.mean(high[-5:]))
            h_prev = float(np.mean(high[-10:-5]))
            l_now = float(np.mean(low[-5:]))
            l_prev = float(np.mean(low[-10:-5]))
            if h_now > h_prev and l_now > l_prev:
                hh_hl = True
                score += 8
                patterns.append("Higher High / Higher Low")
            elif h_now > h_prev:
                score += 4

        # ── 近5日動能（8分）─────────────────────────────────
        price_change_5d = None
        if n >= 6:
            price_change_5d = round((float(close[-1]) - float(close[-6])) / float(close[-6]) * 100, 2)
            if price_change_5d >= 5:
                score += 8
                patterns.append(f"5日漲幅 {price_change_5d:.1f}%")
            elif price_change_5d >= 2:
                score += 5
            elif price_change_5d >= 0:
                score += 2
            elif price_change_5d < -5:
                score -= 2

        # ── 放量突破型態（7分）──────────────────────────────
        if n >= 20 and len(volume) >= 20:
            vol_ma20 = float(np.mean(volume[-20:]))
            cur_vol = float(volume[-1])
            vol_ratio = cur_vol / vol_ma20 if vol_ma20 > 0 else 1.0
            cur_close = float(close[-1])
            prev_close = float(close[-2]) if n >= 2 else cur_close
            if cur_close > prev_close and vol_ratio >= 1.5:
                score += 7
                patterns.append(f"放量上漲 ({vol_ratio:.1f}×均量)")
            elif cur_close > prev_close and vol_ratio >= 1.2:
                score += 4

        return max(0.0, min(score, 35)), {
            "breakout_20d": breakout_20d,
            "near_20d_high": near_20d_high,
            "hh_hl": hh_hl,
            "price_change_5d": price_change_5d,
            "patterns": patterns,
        }

    def _analyze_volume(
        self, close: np.ndarray, volume: np.ndarray
    ) -> Tuple[float, str, Optional[float]]:
        """成交量確認（15分）"""
        if len(volume) < 20:
            return 0.0, "neutral", None

        vol_ma20 = float(np.mean(volume[-20:]))
        cur_vol = float(volume[-1])
        cur_close = float(close[-1])
        prev_close = float(close[-2]) if len(close) >= 2 else cur_close
        vol_ratio = cur_vol / vol_ma20 if vol_ma20 > 0 else 1.0

        price_up = cur_close > prev_close

        if price_up and vol_ratio >= 1.5:
            score, signal = 15.0, "price_up_vol_up"
        elif price_up and vol_ratio >= 1.2:
            score, signal = 11.0, "price_up_vol_up"
        elif price_up and vol_ratio >= 0.8:
            score, signal = 7.0, "price_up_vol_down"
        elif not price_up and vol_ratio >= 1.5:
            score, signal = 0.0, "price_down_vol_up"
        elif not price_up and vol_ratio >= 1.0:
            score, signal = 3.0, "price_down_vol_up"
        else:
            score, signal = 8.0, "price_down_vol_down"

        return score, signal, round(vol_ratio, 2)

    def _calc_rsi(self, close: np.ndarray, period: int = 14) -> Optional[float]:
        if len(close) < period + 1:
            return None
        try:
            deltas = np.diff(close)
            gains = np.where(deltas > 0, deltas, 0)
            losses = np.where(deltas < 0, -deltas, 0)
            avg_gain = np.mean(gains[:period])
            avg_loss = np.mean(losses[:period])
            for i in range(period, len(gains)):
                avg_gain = (avg_gain * (period - 1) + gains[i]) / period
                avg_loss = (avg_loss * (period - 1) + losses[i]) / period
            if avg_loss == 0:
                return 100.0
            rs = avg_gain / avg_loss
            return round(100 - 100 / (1 + rs), 2)
        except Exception as e:
            logger.debug(f"RSI calc failed: {e}")
            return None

    def _score_rsi(self, rsi: Optional[float]) -> Tuple[float, Optional[str]]:
        """RSI（10分）：45-70 為短線最佳健康區"""
        if rsi is None:
            return 5.0, None
        risk = None
        if 50 <= rsi <= 70:
            score = 10.0
        elif 45 <= rsi < 50:
            score = 7.0
        elif 70 < rsi <= 78:
            score = 4.0
            risk = f"RSI {rsi:.0f} 偏熱"
        elif rsi > 78:
            score = 0.0
            risk = f"RSI {rsi:.0f} 過熱，追高風險"
        elif 35 <= rsi < 45:
            score = 5.0
        else:
            score = 6.0   # RSI < 35，超賣反彈機會
        return score, risk

    def _analyze_macd(self, close: np.ndarray) -> Tuple[float, str]:
        """MACD（20分）：Histogram 方向與擴張"""
        if len(close) < TA_CONFIG["macd_slow"] + TA_CONFIG["macd_signal"]:
            return 0.0, "neutral"
        try:
            fast = TA_CONFIG["macd_fast"]
            slow = TA_CONFIG["macd_slow"]
            sig = TA_CONFIG["macd_signal"]
            ema_fast = _ema(close, fast)
            ema_slow = _ema(close, slow)
            macd_line = ema_fast - ema_slow
            signal_line = _ema(macd_line, sig)
            histogram = macd_line - signal_line

            cur_h = float(histogram[-1])
            prev_h = float(histogram[-2]) if len(histogram) >= 2 else cur_h

            if cur_h > 0 and cur_h > prev_h:
                score, sig_str = 20.0, "golden_strong"
            elif cur_h > 0:
                score, sig_str = 13.0, "golden"
            elif cur_h < 0 and cur_h > prev_h:
                score, sig_str = 6.0, "dead_recovering"
            else:
                score, sig_str = 0.0, "dead"

            # MACD 線突破 Signal 線
            if len(macd_line) >= 2:
                if macd_line[-2] < signal_line[-2] and macd_line[-1] >= signal_line[-1]:
                    score = min(score + 5, 20)
                    sig_str = "golden"

            return score, sig_str
        except Exception as e:
            logger.debug(f"MACD calc error: {e}")
            return 0.0, "neutral"

    def _calc_atr(
        self, high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14
    ) -> Optional[float]:
        """14日 ATR"""
        if len(close) < period + 1:
            return None
        try:
            tr_list = []
            for i in range(1, len(close)):
                h, l, pc = float(high[i]), float(low[i]), float(close[i - 1])
                tr = max(h - l, abs(h - pc), abs(l - pc))
                tr_list.append(tr)
            if len(tr_list) < period:
                return None
            atr = float(np.mean(tr_list[-period:]))
            return round(atr, 3)
        except Exception as e:
            logger.debug(f"ATR calc failed: {e}")
            return None

    def _find_support_resistance(
        self, close: np.ndarray, high: np.ndarray, low: np.ndarray
    ) -> Tuple[Optional[float], Optional[float]]:
        if len(close) < 20:
            return None, None
        try:
            return round(float(np.min(low[-20:])), 2), round(float(np.max(high[-20:])), 2)
        except Exception:
            return None, None

    def _detect_setup(self, r: TechnicalResult, ma_vals: Dict, close: np.ndarray) -> str:
        """
        Setup 判斷優先順序（高優先先判斷）：
        breakdown    — 跌破 MA20 且均線下彎：賣出訊號
        breakout     — 近20日新高 + 放量 + MACD 正向：突破買點
        pullback_buy — 多頭排列中回踩 MA10（5%內）縮量守穩：較佳進場點
        pullback_hold — 多頭排列中回踩 MA20（3%內）守穩：次優進場點
        trending     — 均線多頭排列 + HH/HL：趨勢延伸
        none         — 無明確型態
        """
        ma10 = ma_vals.get("ma10")
        ma20 = ma_vals.get("ma20")
        cur = r.close

        if cur is None:
            return "none"

        # Breakdown：跌破 MA20 且 MA 趨勢偏空（含放量加權）
        if ma20 and cur < ma20 and r.ma_trend == "bearish":
            return "breakdown"

        # Breakout：近20日新高 + MACD 正向
        # 有量突破 vs 無量突破 → 均算 breakout，量的差異由 vol_ratio 顯示
        if (r.breakout_20d or r.near_20d_high) and \
           r.macd_signal in ("golden", "golden_strong"):
            return "breakout"

        # Pullback Buy：多頭排列，回踩 MA10 附近（0-5%以上）且縮量
        # 代表健康拉回而非趨勢破壞，是較佳的低風險進場點
        if ma10 and r.ma_trend in ("bullish", "bullish_weak") and \
           0 <= (cur - ma10) / ma10 <= 0.05 and \
           r.macd_signal != "dead" and \
           (r.vol_ratio is None or r.vol_ratio <= 1.2):   # 縮量回踩更健康
            return "pullback_buy"

        # Pullback Hold：多頭排列，回踩 MA20 在3%以內守穩
        if ma20 and 0 <= (cur - ma20) / ma20 <= 0.03 and \
           r.ma_trend in ("bullish", "bullish_weak") and \
           r.macd_signal != "dead":
            return "pullback_hold"

        # Trending：完整多頭排列 + HH/HL 結構
        if r.ma_trend == "bullish" and r.hh_hl_structure:
            return "trending"

        return "none"

    def _build_summary(self, r: TechnicalResult) -> str:
        setup_desc = {
            "breakout":      "突破型態：站上20日新高",
            "pullback_buy":  "回踩買點：多頭排列中縮量回踩MA10",
            "pullback_hold": "回踩守穩：回踩MA20後守住",
            "trending":      "趨勢延伸：均線多頭排列持續向上",
            "breakdown":     "趨勢破壞：跌破MA20且均線下彎",
            "none":          "無明確型態",
        }
        parts = [setup_desc.get(r.setup_type, "")]
        ma_desc = {
            "bullish":      "均線多頭排列",
            "bullish_weak": "短均線在長均線上",
            "bearish":      "均線空頭排列",
            "neutral":      "均線方向中性",
        }
        parts.append(ma_desc.get(r.ma_trend, ""))
        if r.ma_deviation20 is not None:
            sign = "+" if r.ma_deviation20 >= 0 else ""
            parts.append(f"MA20乖離{sign}{r.ma_deviation20:.1f}%")
        if r.vol_ratio:
            parts.append(f"量比 {r.vol_ratio:.1f}×")
        if r.rsi:
            parts.append(f"RSI {r.rsi:.0f}")
        if r.macd_signal in ("golden", "golden_strong"):
            parts.append("MACD 偏多")
        elif r.macd_signal == "dead":
            parts.append("MACD 偏空")
        if r.risk_signals:
            parts.append(f"注意：{'；'.join(r.risk_signals[:2])}")
        return "；".join(p for p in parts if p) + "。"


# ── 工具函式 ──────────────────────────────────────────────────

def _ema(data: np.ndarray, period: int) -> np.ndarray:
    result = np.zeros_like(data, dtype=float)
    k = 2 / (period + 1)
    result[0] = data[0]
    for i in range(1, len(data)):
        result[i] = data[i] * k + result[i - 1] * (1 - k)
    return result


def analyze_all_stocks(price_history: pd.DataFrame) -> dict:
    analyzer = TechnicalAnalyzer()
    results = {}
    grouped = price_history.groupby("stock_id")
    total = len(grouped)
    logger.info(f"Running technical analysis on {total} stocks...")
    for i, (sid, hist) in enumerate(grouped):
        if i % 200 == 0:
            logger.info(f"  Technical analysis progress: {i}/{total}")
        results[sid] = analyzer.analyze(sid, hist)
    qualified = sum(1 for r in results.values() if r.timing_score > 0)
    logger.info(f"Technical analysis complete: {qualified}/{total} stocks scored.")
    return results
