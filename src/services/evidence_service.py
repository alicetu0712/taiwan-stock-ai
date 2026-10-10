"""
evidence_service.py — Decision Center「類似訊號歷史績效」パネル用データ

Architecture:
- research_evidence(): in-sample (before RESEARCH_CUTOFF_DATE) stats
- forward_evidence(): OOS (ForwardSignal records after cutoff) stats
- Both filter by setup_type + market_regime
- NEVER used to change BUY/WAIT label — display/context only
"""

import bisect
import logging
from datetime import timedelta

import numpy as np

logger = logging.getLogger(__name__)


def _evidence_tier(n: int) -> tuple:
    """Returns (emoji, label) for sample size."""
    if n < 10:
        return "🔴", "樣本不足"
    if n < 30:
        return "🟡", "初步觀察"
    if n < 100:
        return "🟢", "有一定參考價值"
    return "🟢", "樣本充足，建議搭配 CI 判讀"


def get_current_regime(engine=None) -> str:
    """
    Compute current 0050-based market regime.
    bull = close > MA60 AND MA60 slope up
    bear = close < MA60 AND MA60 slope down
    neutral = everything else
    """
    try:
        from src.database import DailyPrice, get_session
        s = get_session(engine)
        rows = (
            s.query(DailyPrice.date, DailyPrice.close)
            .filter(DailyPrice.stock_id == "0050")
            .order_by(DailyPrice.date.desc())
            .limit(90)
            .all()
        )
        s.close()
        if len(rows) < 62:
            return "neutral"
        rows = list(reversed(rows))
        closes = [r.close for r in rows]
        ma60 = sum(closes[-60:]) / 60
        ma60_prev = sum(closes[-70:-10]) / 60 if len(closes) >= 70 else ma60
        slope = "up" if ma60 > ma60_prev * 1.001 else "down" if ma60 < ma60_prev * 0.999 else "flat"
        current = closes[-1]
        if current > ma60 and slope == "up":
            return "bull"
        if current < ma60 and slope == "down":
            return "bear"
        return "neutral"
    except Exception as e:
        logger.warning(f"get_current_regime: {e}")
        return "neutral"


def _compute_0050_regime_map(engine=None) -> dict:
    """Returns {date: regime} for all 0050 dates."""
    try:
        from src.database import DailyPrice, get_session
        s = get_session(engine)
        rows = (
            s.query(DailyPrice.date, DailyPrice.close)
            .filter(DailyPrice.stock_id == "0050")
            .order_by(DailyPrice.date)
            .all()
        )
        s.close()
        if len(rows) < 61:
            return {}
        dates = [r.date for r in rows]
        closes = [r.close for r in rows]
        regime_map = {}
        for i in range(60, len(dates)):
            ma60 = sum(closes[i - 60:i]) / 60
            ma60_prev = sum(closes[i - 70:i - 10]) / 60 if i >= 70 else ma60
            slope = "up" if ma60 > ma60_prev * 1.001 else "down" if ma60 < ma60_prev * 0.999 else "flat"
            c = closes[i]
            if c > ma60 and slope == "up":
                regime_map[dates[i]] = "bull"
            elif c < ma60 and slope == "down":
                regime_map[dates[i]] = "bear"
            else:
                regime_map[dates[i]] = "neutral"
        return regime_map
    except Exception as e:
        logger.warning(f"_compute_0050_regime_map: {e}")
        return {}


def _compute_forward_alpha(
    observations: list,
    price_map: dict,
    sorted_dates_map: dict,
    p0050_map: dict,
    sorted_0050: list,
    n_days: int,
) -> list:
    """Compute n_days forward alpha (stock − 0050) for each observation."""
    results = []
    for stock_id, signal_date, entry_close in observations:
        if not entry_close or entry_close <= 0:
            continue
        idx_0050 = bisect.bisect_right(sorted_0050, signal_date)
        if idx_0050 == 0:
            continue
        p0050_sig = p0050_map.get(sorted_0050[idx_0050 - 1])
        if not p0050_sig or p0050_sig <= 0:
            continue
        sdates = sorted_dates_map.get(stock_id, [])
        idx_s = bisect.bisect_right(sdates, signal_date)
        target_idx = idx_s + n_days - 1
        if target_idx >= len(sdates):
            continue
        fwd_stock = price_map.get(stock_id, {}).get(sdates[target_idx])
        target_0050 = idx_0050 + n_days - 1
        if target_0050 >= len(sorted_0050):
            continue
        fwd_0050 = p0050_map.get(sorted_0050[target_0050])
        if not (fwd_stock and fwd_0050):
            continue
        results.append(
            (fwd_stock - entry_close) / entry_close
            - (fwd_0050 - p0050_sig) / p0050_sig
        )
    return results


def _alpha_stats(alphas: list) -> dict:
    if not alphas:
        return {"mean": None, "median": None, "winrate": None}
    a = np.array(alphas) * 100
    return {
        "mean":    round(float(np.mean(a)), 2),
        "median":  round(float(np.median(a)), 2),
        "winrate": round(float(np.mean(a > 0)) * 100, 1),
    }


def research_evidence(setup_type: str, market_regime: str, engine=None) -> dict:
    """
    In-sample evidence: AnalysisResult rows before RESEARCH_CUTOFF_DATE
    that match setup_type and computed market_regime.
    """
    empty = {
        "n": 0, "setup_type": setup_type, "regime": market_regime,
        "alpha_20d": {"mean": None, "median": None, "winrate": None},
        "alpha_60d": {"mean": None, "median": None, "winrate": None},
        "tier_emoji": "🔴", "tier_label": "樣本不足",
    }
    try:
        from src.database import AnalysisResult, DailyPrice, RESEARCH_CUTOFF_DATE, get_session
        s = get_session(engine)
        ar_rows = (
            s.query(AnalysisResult)
            .filter(
                AnalysisResult.date < RESEARCH_CUTOFF_DATE,
                AnalysisResult.setup_type == setup_type,
            )
            .all()
        )
        if not ar_rows:
            s.close()
            return empty

        regime_map = _compute_0050_regime_map(engine)
        if not regime_map:
            s.close()
            return empty

        matching = [
            (r.stock_id, r.date)
            for r in ar_rows
            if regime_map.get(r.date) == market_regime
        ]
        if not matching:
            s.close()
            return empty

        stock_ids = list({sid for sid, _ in matching})
        min_date = min(d for _, d in matching)
        max_date = max(d for _, d in matching) + timedelta(days=120)

        price_rows = (
            s.query(DailyPrice)
            .filter(
                DailyPrice.stock_id.in_(stock_ids + ["0050"]),
                DailyPrice.date >= min_date,
                DailyPrice.date <= max_date,
            )
            .order_by(DailyPrice.stock_id, DailyPrice.date)
            .all()
        )
        s.close()

        price_map: dict = {}
        for row in price_rows:
            if row.stock_id not in price_map:
                price_map[row.stock_id] = {}
            price_map[row.stock_id][row.date] = row.close
        sorted_dates_map = {sid: sorted(dm.keys()) for sid, dm in price_map.items()}
        p0050_map = price_map.get("0050", {})
        sorted_0050 = sorted(p0050_map.keys())

        observations = [
            (sid, sig_date, price_map.get(sid, {}).get(sig_date))
            for sid, sig_date in matching
            if price_map.get(sid, {}).get(sig_date)
        ]

        alphas_20 = _compute_forward_alpha(observations, price_map, sorted_dates_map, p0050_map, sorted_0050, 20)
        alphas_60 = _compute_forward_alpha(observations, price_map, sorted_dates_map, p0050_map, sorted_0050, 60)

        n = len(alphas_20)
        tier_emoji, tier_label = _evidence_tier(n)
        return {
            "n": n,
            "setup_type": setup_type,
            "regime": market_regime,
            "alpha_20d": _alpha_stats(alphas_20),
            "alpha_60d": _alpha_stats(alphas_60),
            "tier_emoji": tier_emoji,
            "tier_label": tier_label,
        }
    except Exception as e:
        logger.warning(f"research_evidence({setup_type}, {market_regime}): {e}")
        return empty


def forward_evidence(setup_type: str, market_regime: str, engine=None) -> dict:
    """
    OOS evidence: ForwardSignal records matching setup_type + market_regime_at_signal.
    Forward returns computed on-the-fly from DailyPrice.
    """
    empty = {
        "total_recorded": 0, "matured_20d": 0, "matured_60d": 0,
        "alpha_20d": {"mean": None, "median": None, "winrate": None},
        "alpha_60d": {"mean": None, "median": None, "winrate": None},
        "tier_emoji": "🔴", "tier_label": "尚無 OOS 資料",
    }
    try:
        from src.database import ForwardSignal, DailyPrice, get_session
        s = get_session(engine)
        fs_rows = (
            s.query(ForwardSignal)
            .filter(ForwardSignal.setup_type == setup_type)
            .all()
        )
        if not fs_rows:
            s.close()
            return empty

        # Include records where regime field is NULL (legacy before schema v2)
        matching = [
            r for r in fs_rows
            if r.market_regime_at_signal is None or r.market_regime_at_signal == market_regime
        ]
        total = len(matching)
        if total == 0:
            s.close()
            return empty

        stock_ids = list({r.stock_id for r in matching})
        min_date = min(r.trade_date for r in matching)
        max_date = max(r.trade_date for r in matching) + timedelta(days=120)

        price_rows = (
            s.query(DailyPrice)
            .filter(
                DailyPrice.stock_id.in_(stock_ids + ["0050"]),
                DailyPrice.date >= min_date,
                DailyPrice.date <= max_date,
            )
            .order_by(DailyPrice.stock_id, DailyPrice.date)
            .all()
        )
        s.close()

        price_map: dict = {}
        for row in price_rows:
            if row.stock_id not in price_map:
                price_map[row.stock_id] = {}
            price_map[row.stock_id][row.date] = row.close
        sorted_dates_map = {sid: sorted(dm.keys()) for sid, dm in price_map.items()}
        p0050_map = price_map.get("0050", {})
        sorted_0050 = sorted(p0050_map.keys())

        observations_20 = []
        observations_60 = []
        for r in matching:
            entry = r.close_at_signal or price_map.get(r.stock_id, {}).get(r.trade_date)
            if not entry:
                continue
            sdates = sorted_dates_map.get(r.stock_id, [])
            idx_s = bisect.bisect_right(sdates, r.trade_date)
            if idx_s + 19 < len(sdates):
                observations_20.append((r.stock_id, r.trade_date, entry))
            if idx_s + 59 < len(sdates):
                observations_60.append((r.stock_id, r.trade_date, entry))

        alphas_20 = _compute_forward_alpha(observations_20, price_map, sorted_dates_map, p0050_map, sorted_0050, 20)
        alphas_60 = _compute_forward_alpha(observations_60, price_map, sorted_dates_map, p0050_map, sorted_0050, 60)

        n_m20 = len(alphas_20)
        tier_emoji, tier_label = _evidence_tier(n_m20)
        return {
            "total_recorded": total,
            "matured_20d": n_m20,
            "matured_60d": len(alphas_60),
            "alpha_20d": _alpha_stats(alphas_20),
            "alpha_60d": _alpha_stats(alphas_60),
            "tier_emoji": tier_emoji,
            "tier_label": tier_label,
        }
    except Exception as e:
        logger.warning(f"forward_evidence({setup_type}, {market_regime}): {e}")
        return empty


def evidence_narrative(re_ev: dict, fe_ev: dict) -> str:
    """
    Plain-language interpretation combining research + forward evidence.
    Conservative: never overstates weak evidence.
    """
    r_n      = re_ev.get("n", 0)
    r_alpha20 = re_ev.get("alpha_20d", {}).get("mean")
    r_wr20    = re_ev.get("alpha_20d", {}).get("winrate")
    f_total   = fe_ev.get("total_recorded", 0)
    f_m20     = fe_ev.get("matured_20d", 0)
    f_alpha20 = fe_ev.get("alpha_20d", {}).get("mean")

    if r_n < 10:
        if f_total == 0:
            return "歷史樣本不足，目前無法評估此型態的統計可靠度。"
        return (
            f"歷史樣本不足（{r_n} 筆），無法評估 In-Sample 可靠度。"
            f"已開始累積 Forward 記錄（{f_total} 筆），持續觀察中。"
        )

    parts = []
    if r_alpha20 is not None and r_wr20 is not None:
        direction = "正 Alpha" if r_alpha20 > 0 else "負 Alpha"
        parts.append(
            f"歷史 {r_n} 筆類似情境顯示平均 20D {direction}（{r_alpha20:+.1f}%）、勝率 {r_wr20:.0f}%。"
        )

    if f_m20 < 10:
        parts.append(
            f"真實 Forward 樣本仍少（{f_m20} 筆 20D 已成熟），目前不能判定策略長期有效性。"
        )
    elif f_alpha20 is not None and r_alpha20 is not None:
        if (f_alpha20 > 0) == (r_alpha20 > 0):
            parts.append(
                f"Forward 初步結果（{f_alpha20:+.1f}%）方向與 Research 一致，具有初步支持。"
            )
        else:
            parts.append(
                f"Forward 結果（{f_alpha20:+.1f}%）方向與 Research 不一致，需持續觀察差異原因。"
            )

    return " ".join(parts) if parts else "資料不足以生成解讀。"
