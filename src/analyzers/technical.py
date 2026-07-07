"""
technical.py — 技術分析引擎（PRD Chapter 6）

計算 Technical Timing Score（0-100）。
遵循原則：
  1. 先基本面，再技術面
  2. 多指標交叉驗證
  3. 趨勢重於預測
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
    """技術分析結果"""

    stock_id: str
    timing_score: float = 0.0  # 0-100
    ma_trend: str = "neutral"  # bullish / bearish / neutral
    volume_signal: str = "neutral"  # up_vol / down_vol / neutral
    rsi: Optional[float] = None
    macd_signal: str = "neutral"  # golden / dead / neutral
    kd_signal: str = "neutral"
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


class TechnicalAnalyzer:
    """
    技術分析引擎。
    輸入：個股歷史 OHLCV DataFrame（至少 60 天）
    輸出：TechnicalResult
    """

    MIN_HISTORY = TA_CONFIG["min_history"]

    def analyze(self, stock_id: str, history: pd.DataFrame) -> TechnicalResult:
        """主要入口：分析個股技術面。"""
        result = TechnicalResult(stock_id=stock_id)

        if history is None or len(history) < self.MIN_HISTORY:
            result.summary = f"歷史資料不足（{len(history) if history is not None else 0} 天），無法進行技術分析。"
            return result

        hist = history.sort_values("date").reset_index(drop=True)
        close = hist["close"].values
        volume = hist["volume"].values
        high = hist["high"].values if "high" in hist.columns else close
        low = hist["low"].values if "low" in hist.columns else close

        score = 0.0
        risk_signals = []

        # ── MA 均線分析（最高 25 分）────────────────────────
        ma_score, ma_trend, ma_vals = self._analyze_ma(close)
        score += ma_score
        result.ma_trend = ma_trend
        result.ma5 = ma_vals.get("ma5")
        result.ma20 = ma_vals.get("ma20")
        result.ma60 = ma_vals.get("ma60")
        result.ma120 = ma_vals.get("ma120")
        result.ma240 = ma_vals.get("ma240")
        result.close = float(close[-1])

        # ── 成交量分析（最高 20 分）─────────────────────────
        vol_score, vol_signal = self._analyze_volume(close, volume)
        score += vol_score
        result.volume_signal = vol_signal

        # ── RSI 分析（最高 15 分）───────────────────────────
        rsi_val = self._calc_rsi(close, period=TA_CONFIG["rsi_period"])
        rsi_score, rsi_risk = self._score_rsi(rsi_val)
        score += rsi_score
        result.rsi = rsi_val
        if rsi_risk:
            risk_signals.append(rsi_risk)

        # ── MACD 分析（最高 20 分）──────────────────────────
        macd_score, macd_sig = self._analyze_macd(close)
        score += macd_score
        result.macd_signal = macd_sig

        # ── KD 分析（最高 10 分）────────────────────────────
        kd_score, kd_sig = self._analyze_kd(high, low, close)
        score += kd_score
        result.kd_signal = kd_sig

        # ── K 線型態（最高 10 分）───────────────────────────
        patterns, pat_score = self._detect_patterns(close, high, low, volume)
        score += pat_score
        result.patterns = patterns

        # ── 支撐壓力（參考用，不計分）───────────────────────
        result.support, result.resistance = self._find_support_resistance(
            close[-60:], high[-60:], low[-60:]
        )

        # ── 風險信號 ─────────────────────────────────────────
        if result.close and result.ma20 and result.close > result.ma20 * 1.15:
            risk_signals.append("股價距 MA20 超過 15%，短線可能過熱")
        if (
            result.resistance
            and result.close
            and result.close >= result.resistance * 0.98
        ):
            risk_signals.append("接近前波壓力區，追高需謹慎")

        # ── 最終評分 ─────────────────────────────────────────
        result.timing_score = round(max(0.0, min(100.0, score)), 1)
        result.risk_signals = risk_signals
        result.summary = self._build_summary(result)

        logger.debug(
            f"{stock_id}: Timing Score={result.timing_score:.1f}, MA={ma_trend}"
        )
        return result

    # ── 分析子方法 ────────────────────────────────────────────

    def _analyze_ma(self, close: np.ndarray) -> Tuple[float, str, Dict[str, float]]:
        """均線分析（最高 25 分）"""
        score = 0.0
        n = len(close)
        cfg = TA_CONFIG["ma_periods"]
        ma_vals = {}

        for period in cfg:
            if n >= period:
                ma_vals[f"ma{period}"] = float(np.mean(close[-period:]))

        cur = close[-1]
        ma5 = ma_vals.get("ma5")
        ma10 = ma_vals.get("ma10")
        ma20 = ma_vals.get("ma20")
        ma60 = ma_vals.get("ma60")
        ma120 = ma_vals.get("ma120")

        # 股價位置得分
        if ma20 and cur > ma20:
            score += 5
        if ma60 and cur > ma60:
            score += 5
        if ma120 and cur > ma120:
            score += 3

        # 多頭排列
        if ma5 and ma10 and ma20 and ma60:
            if ma5 > ma10 > ma20 > ma60:
                score += 12
                trend = "bullish"
            elif ma5 > ma20:
                score += 6
                trend = "bullish_weak"
            elif ma5 < ma20:
                score -= 5
                trend = "bearish"
            else:
                trend = "neutral"
        else:
            trend = "neutral"

        # 黃金交叉（MA5 突破 MA20）
        if ma5 and ma20 and n >= 21:
            prev_ma5 = float(np.mean(close[-6:-1]))
            prev_ma20 = float(np.mean(close[-21:-1]))
            if prev_ma5 < prev_ma20 and ma5 >= ma20:
                score += 3

        return max(0.0, min(score, 25)), trend, ma_vals

    def _analyze_volume(
        self, close: np.ndarray, volume: np.ndarray
    ) -> Tuple[float, str]:
        """成交量分析（最高 20 分）"""
        if len(volume) < 20:
            return 0.0, "neutral"

        vol_ma20 = float(np.mean(volume[-20:]))
        cur_vol = float(volume[-1])
        cur_close = float(close[-1])
        prev_close = float(close[-2]) if len(close) >= 2 else cur_close

        price_up = cur_close > prev_close
        vol_up = cur_vol > vol_ma20 * 1.2

        if price_up and vol_up:
            signal = "price_up_vol_up"
            score = 20.0
        elif price_up and not vol_up:
            signal = "price_up_vol_down"
            score = 5.0  # 追價意願不足
        elif not price_up and vol_up:
            signal = "price_down_vol_up"
            score = 0.0  # 賣壓增加
        else:
            signal = "price_down_vol_down"
            score = 10.0  # 中性，等待方向

        # 突破整理量增
        if vol_up and cur_vol > vol_ma20 * 1.5:
            score = min(score + 3, 20)

        return score, signal

    def _calc_rsi(self, close: np.ndarray, period: int = 14) -> Optional[float]:
        """計算 RSI。"""
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
        """RSI 評分（最高 15 分）"""
        if rsi is None:
            return 0.0, None

        risk = None
        if 55 <= rsi <= 70:
            score = 15.0  # 強勢健康
        elif 50 <= rsi < 55:
            score = 10.0
        elif 70 < rsi <= 80:
            score = 5.0
            risk = f"RSI {rsi:.0f} 接近過熱"
        elif rsi > 80:
            score = 0.0
            risk = f"RSI {rsi:.0f} 過熱，追高風險高"
        elif 30 <= rsi < 50:
            score = 5.0  # 偏弱但可能超賣
        else:
            score = 8.0  # RSI < 30，可能超賣回彈
        return score, risk

    def _analyze_macd(self, close: np.ndarray) -> Tuple[float, str]:
        """MACD 分析（最高 20 分）"""
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

            if cur_h > 0:
                if cur_h > prev_h:
                    score = 20.0
                    sig_str = "golden_strong"  # 柱狀體為正且增強
                else:
                    score = 12.0
                    sig_str = "golden"
            else:
                if cur_h > prev_h:
                    score = 5.0
                    sig_str = "dead_recovering"  # 柱狀體為負但改善中
                else:
                    score = 0.0
                    sig_str = "dead"

            # 黃金交叉（MACD 線突破 Signal 線）
            if len(macd_line) >= 2:
                if macd_line[-2] < signal_line[-2] and macd_line[-1] >= signal_line[-1]:
                    score = min(score + 5, 20)
                    sig_str = "golden"

            return score, sig_str
        except Exception as e:
            logger.debug(f"MACD calc error: {e}")
            return 0.0, "neutral"

    def _analyze_kd(
        self, high: np.ndarray, low: np.ndarray, close: np.ndarray
    ) -> Tuple[float, str]:
        """KD 分析（最高 10 分）"""
        period = TA_CONFIG["kd_period"]
        if len(close) < period:
            return 0.0, "neutral"
        try:
            # 計算 %K
            k_vals = []
            for i in range(period - 1, len(close)):
                h = max(high[i - period + 1 : i + 1])
                low_k = min(low[i - period + 1 : i + 1])
                if h == low_k:
                    k_vals.append(50.0)
                else:
                    k_vals.append((close[i] - low_k) / (h - low_k) * 100)

            k_series = np.array(k_vals)
            d_series = _ema(k_series, 3)  # %D = 3期移動平均

            k = float(k_series[-1])
            d = float(d_series[-1])
            k_prev = float(k_series[-2]) if len(k_series) >= 2 else k
            d_prev = float(d_series[-2]) if len(d_series) >= 2 else d

            if k_prev < d_prev and k >= d:
                # 黃金交叉
                if k < 30:
                    sig = "golden_low"  # 低檔黃金交叉（最佳）
                    score = 10.0
                else:
                    sig = "golden"
                    score = 7.0
            elif k_prev > d_prev and k <= d:
                sig = "dead"
                score = 0.0
            elif 20 <= k <= 80:
                sig = "neutral"
                score = 5.0
            elif k < 20:
                sig = "oversold"
                score = 6.0  # 可能超賣
            else:
                sig = "overbought"
                score = 2.0
            return score, sig
        except Exception as e:
            logger.debug(f"MACD/stoch score failed: {e}")
            return 0.0, "neutral"

    def _detect_patterns(
        self, close: np.ndarray, high: np.ndarray, low: np.ndarray, volume: np.ndarray
    ) -> Tuple[List[str], float]:
        """K 線型態偵測（最高 10 分）"""
        patterns = []
        score = 0.0

        if len(close) < 5:
            return patterns, score

        c = float(close[-1])
        c1 = float(close[-2])
        h = float(high[-1])
        low_val = float(low[-1])
        body = abs(c - c1)

        # 長紅 K（今日漲幅 > 3%）
        if c > c1 * 1.03 and (h - low_val) > 0 and body / (h - low_val) > 0.6:
            patterns.append("長紅K")
            score += 3

        # 多頭排列（MA5 > MA20）—— 快速判斷
        if len(close) >= 20:
            ma5_q = float(np.mean(close[-5:]))
            ma20_q = float(np.mean(close[-20:]))
            if ma5_q > ma20_q:
                patterns.append("多頭排列")
                score += 3

        # 放量突破
        if len(volume) >= 20:
            vol_ma20 = float(np.mean(volume[-20:]))
            if volume[-1] > vol_ma20 * 1.5 and c > c1:
                patterns.append("放量突破")
                score += 4

        # 錘頭（下影線長，可能反彈）
        if (c - low_val) > 2 * body and body < (h - low_val) * 0.3 and c > c1 * 0.99:
            patterns.append("錘頭")
            score += 2

        return patterns, min(score, 10)

    def _find_support_resistance(
        self, close: np.ndarray, high: np.ndarray, low: np.ndarray
    ) -> Tuple[Optional[float], Optional[float]]:
        """簡單支撐壓力估算（近期高低點）。"""
        if len(close) < 20:
            return None, None
        try:
            recent_high = float(np.max(high[-20:]))
            recent_low = float(np.min(low[-20:]))
            return round(recent_low, 2), round(recent_high, 2)
        except Exception as e:
            logger.debug(f"support/resistance calc failed: {e}")
            return None, None

    def _build_summary(self, r: "TechnicalResult") -> str:
        ma_desc = {
            "bullish": "均線呈多頭排列，中期趨勢健康",
            "bullish_weak": "短均線位於長均線上方，趨勢偏多",
            "bearish": "均線呈空頭排列，趨勢偏弱",
            "neutral": "均線方向中性",
        }
        vol_desc = {
            "price_up_vol_up": "量價俱揚，買盤積極",
            "price_up_vol_down": "漲量縮，追價意願不足",
            "price_down_vol_up": "跌量增，賣壓明顯",
            "price_down_vol_down": "量縮整理，等待方向",
        }
        parts = [
            ma_desc.get(r.ma_trend, ""),
            vol_desc.get(r.volume_signal, ""),
        ]
        if r.rsi:
            parts.append(f"RSI={r.rsi:.0f}")
        if r.macd_signal in ("golden", "golden_strong"):
            parts.append("MACD 偏多")
        elif r.macd_signal == "dead":
            parts.append("MACD 偏空")
        if r.risk_signals:
            parts.append(f"注意：{'；'.join(r.risk_signals[:2])}")
        return "；".join(p for p in parts if p) + "。"


# ── 工具函式 ──────────────────────────────────────────────────


def _ema(data: np.ndarray, period: int) -> np.ndarray:
    """指數移動平均。"""
    result = np.zeros_like(data, dtype=float)
    k = 2 / (period + 1)
    result[0] = data[0]
    for i in range(1, len(data)):
        result[i] = data[i] * k + result[i - 1] * (1 - k)
    return result


def analyze_all_stocks(
    price_history: pd.DataFrame,
) -> dict:
    """
    批次技術分析全市場股票。
    輸入：合併後的歷史股價 DataFrame（含 stock_id, date, open, high, low, close, volume）
    回傳：{stock_id: TechnicalResult}
    """
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
