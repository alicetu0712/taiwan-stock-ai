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

from src.utils.dedup_utils import dedup_by_trading_days

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
        return {"mean": None, "median": None, "winrate": None, "p25": None, "p75": None, "p10": None, "p90": None}
    a = np.array(alphas) * 100
    return {
        "mean":    round(float(np.mean(a)), 2),
        "median":  round(float(np.median(a)), 2),
        "winrate": round(float(np.mean(a > 0)) * 100, 1),
        "p25":     round(float(np.percentile(a, 25)), 2),
        "p75":     round(float(np.percentile(a, 75)), 2),
        "p10":     round(float(np.percentile(a, 10)), 2),
        "p90":     round(float(np.percentile(a, 90)), 2),
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

        sorted_matching = sorted(matching, key=lambda x: x[1])
        dedup_m20 = dedup_by_trading_days(sorted_matching, 20, sorted_dates_map, sorted_0050)
        dedup_m60 = dedup_by_trading_days(sorted_matching, 60, sorted_dates_map, sorted_0050)

        obs_20 = [
            (sid, d, price_map.get(sid, {}).get(d))
            for sid, d in dedup_m20
            if price_map.get(sid, {}).get(d)
        ]
        obs_60 = [
            (sid, d, price_map.get(sid, {}).get(d))
            for sid, d in dedup_m60
            if price_map.get(sid, {}).get(d)
        ]

        alphas_20 = _compute_forward_alpha(obs_20, price_map, sorted_dates_map, p0050_map, sorted_0050, 20)
        alphas_60 = _compute_forward_alpha(obs_60, price_map, sorted_dates_map, p0050_map, sorted_0050, 60)

        n = len(alphas_20)
        tier_emoji, tier_label = _evidence_tier(n)
        return {
            "n":          n,
            "n_raw":      len(matching),
            "n_dedup_20": len(dedup_m20),
            "n_dedup_60": len(dedup_m60),
            "setup_type": setup_type,
            "regime":     market_regime,
            "alpha_20d":  _alpha_stats(alphas_20),
            "alpha_60d":  _alpha_stats(alphas_60),
            "tier_emoji": tier_emoji,
            "tier_label": tier_label,
        }
    except Exception as e:
        logger.warning(f"research_evidence({setup_type}, {market_regime}): {e}")
        return empty


def forward_evidence(setup_type: str, market_regime: str, engine=None) -> dict:
    """
    OOS evidence: ForwardSignal records matching setup_type + market_regime_at_signal.
    Uses stored alpha_20d/alpha_60d (computed by compute_signal_outcomes with correct
    NEXT_OPEN execution assumption).

    STRICT: NEXT_OPEN and SIGNAL_CLOSE_LEGACY records are NEVER mixed.
    Only NEXT_OPEN records with execution_price filled contribute to alpha stats.
    Legacy records are counted but excluded from alpha computation.
    """
    empty = {
        "total_recorded": 0, "matured_20d": 0, "matured_60d": 0,
        "n_legacy": 0,
        "alpha_20d": {"mean": None, "median": None, "winrate": None, "p25": None, "p75": None, "p10": None, "p90": None},
        "alpha_60d": {"mean": None, "median": None, "winrate": None, "p25": None, "p75": None, "p10": None, "p90": None},
        "tier_emoji": "🔴", "tier_label": "尚無 OOS 資料",
    }
    try:
        from src.database import DailyPrice, ForwardSignal, get_session
        s = get_session(engine)
        fs_rows = (
            s.query(ForwardSignal)
            .filter(ForwardSignal.setup_type == setup_type)
            .all()
        )
        # 載入 0050 交易日曆供 dedup 用
        cal_rows = (
            s.query(DailyPrice.date)
            .filter(DailyPrice.stock_id == "0050")
            .order_by(DailyPrice.date)
            .all()
        )
        s.close()
        market_calendar = sorted([r.date for r in cal_rows])

        if not fs_rows:
            return empty

        # Strict regime match; NULL market_regime_at_signal excluded
        matching = [r for r in fs_rows if r.market_regime_at_signal == market_regime]
        if not matching:
            return empty

        # ── STRICT TYPE SPLIT ──────────────────────────────────────────
        # NEXT_OPEN and SIGNAL_CLOSE_LEGACY use different execution assumptions
        # (next-day open vs signal-day close). Mixing them produces a blended
        # alpha that is meaningless because the two entry prices are not comparable.
        next_open = [r for r in matching if r.execution_price_type == "NEXT_OPEN"]
        legacy    = [r for r in matching if r.execution_price_type != "NEXT_OPEN"]
        n_legacy  = len(legacy)

        # Use stored alpha from compute_signal_outcomes() — already correctly computed
        # with NEXT_OPEN logic (execution_date open vs 0050 open same day).
        # Stored as %, convert to decimal for _alpha_stats().
        matured_20_raw = [r for r in next_open
                          if r.outcomes_computed_at is not None and r.alpha_20d is not None]
        matured_60_raw = [r for r in next_open
                          if r.outcomes_computed_at is not None and r.alpha_60d is not None]

        # ── DEDUP：同股票 20D/60D 冷卻，避免重疊成效視窗 ──────────────
        # 連續五天 BUY 同一支股票 = 五個樣本，但後續 20 天高度重疊，
        # 不能視為五次獨立驗證。
        def _dedup_forward(records, n_days):
            """按 trade_date 排序後套用 n_days 冷卻去重，回傳 kept 的記錄集合 key。"""
            pairs = sorted([(r.stock_id, r.trade_date) for r in records],
                           key=lambda x: x[1])
            kept = dedup_by_trading_days(pairs, n_days, market_calendar=market_calendar)
            return set(kept)

        kept_20 = _dedup_forward(matured_20_raw, 20)
        kept_60 = _dedup_forward(matured_60_raw, 60)

        alphas_20 = [r.alpha_20d / 100.0 for r in matured_20_raw
                     if (r.stock_id, r.trade_date) in kept_20]
        alphas_60 = [r.alpha_60d / 100.0 for r in matured_60_raw
                     if (r.stock_id, r.trade_date) in kept_60]

        n_m20 = len(alphas_20)
        tier_emoji, tier_label = _evidence_tier(n_m20)
        return {
            "total_recorded": len(next_open),
            "n_legacy":       n_legacy,
            "n_raw_20d":      len(matured_20_raw),   # 去重前
            "n_raw_60d":      len(matured_60_raw),
            "matured_20d":    n_m20,                  # 去重後
            "matured_60d":    len(alphas_60),
            "alpha_20d":      _alpha_stats(alphas_20),
            "alpha_60d":      _alpha_stats(alphas_60),
            "tier_emoji":     tier_emoji,
            "tier_label":     tier_label,
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


def monte_carlo_dist(
    stock_id: str,
    current_price: float,
    n_days: int = 20,
    n_sims: int = 1000,
    lookback: int = 252,
    engine=None,
) -> dict:
    """
    Stock historical-volatility Monte Carlo price distribution.

    Answers: "Given this stock's own historical daily volatility, where might
    the price distribute at n_days?"

    This is NOT setup-conditioned evidence. Use Historical Analog (research_evidence /
    forward_evidence) for setup × regime conditional stats.

    Method: fit Student-t to daily log returns (heavier tails than normal),
    simulate n_sims paths with ZERO drift (volatility only — no directional forecast).
    Returns price percentiles at day n_days.
    """
    empty = {
        "p10": None, "p25": None, "p50": None, "p75": None, "p90": None,
        "n_hist": 0, "sigma_daily": None,
    }
    if not current_price or current_price <= 0:
        return empty
    try:
        from scipy import stats as sp_stats
        from src.database import DailyPrice, get_session

        s = get_session(engine)
        rows = (
            s.query(DailyPrice.close)
            .filter(
                DailyPrice.stock_id == stock_id,
                DailyPrice.close.isnot(None),
                DailyPrice.close > 0,
            )
            .order_by(DailyPrice.date.desc())
            .limit(lookback + 1)
            .all()
        )
        s.close()

        if len(rows) < 21:
            return empty

        closes = np.array([r.close for r in reversed(rows)], dtype=float)
        log_returns = np.diff(np.log(closes))

        if len(log_returns) < 20:
            return empty

        # Fit Student-t distribution; override loc=0 (zero-drift — pure volatility)
        df_t, _loc, scale_t = sp_stats.t.fit(log_returns)

        rng = np.random.default_rng(42)
        sim_returns = sp_stats.t.rvs(
            df_t, loc=0.0, scale=scale_t,
            size=(n_sims, n_days), random_state=rng,
        )
        cum_log_ret = sim_returns.sum(axis=1)
        final_prices = current_price * np.exp(cum_log_ret)

        return {
            "p10":       round(float(np.percentile(final_prices, 10)), 2),
            "p25":       round(float(np.percentile(final_prices, 25)), 2),
            "p50":       round(float(np.percentile(final_prices, 50)), 2),
            "p75":       round(float(np.percentile(final_prices, 75)), 2),
            "p90":       round(float(np.percentile(final_prices, 90)), 2),
            "n_hist":    len(log_returns),
            "sigma_daily": round(float(scale_t) * 100, 2),
        }
    except Exception as e:
        logger.warning(f"monte_carlo_dist({stock_id}): {e}")
        return empty
