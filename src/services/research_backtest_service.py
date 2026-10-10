"""
research_backtest_service.py — Research Backtest 服務層

資料來源：
  In-Sample  : analysis_results WHERE date < RESEARCH_CUTOFF_DATE
  Out-of-Sample: forward_signals WHERE trade_date >= RESEARCH_CUTOFF_DATE

嚴格 no look-ahead bias 原則：
  - features 取自 analysis date（當日已知）
  - MA60 / MA60 slope 由 daily_prices 到 analysis date 為止計算
  - forward return 從 analysis date close 起算，往後 N 個交易日
  - benchmark 0050 同日進出場

兩個資料集嚴格隔離，禁止混用。
"""

import bisect
import logging
from collections import defaultdict
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

logger = logging.getLogger(__name__)

def _get_cutoff():
    from src.database import RESEARCH_CUTOFF_DATE
    return RESEARCH_CUTOFF_DATE

ROUND_TRIP_COST = 0.585  # 買進 + 賣出合計（%）

# ── 排序順序 ──────────────────────────────────────────────────
PT_BUCKET_ORDER   = ["<40", "40-50", "50-60", "60-70", "70-80", "80+"]
MA20_BRACKET_ORDER = ["< -10%", "-10% to -5%", "-5% to 0%",
                      "0% to 5%", "5% to 10%", "> 10%"]
MA60_BRACKET_ORDER = ["< -5%", "-5% to 0%", "0% to 3%", "3% to 5%", "> 5%"]


# ── 分組輔助函數（模組層級，供 tests 直接呼叫）──────────────────

def pt_bucket(score) -> str:
    if score is None or (isinstance(score, float) and np.isnan(score)):
        return "N/A"
    s = float(score)
    if s < 40:  return "<40"
    if s < 50:  return "40-50"
    if s < 60:  return "50-60"
    if s < 70:  return "60-70"
    if s < 80:  return "70-80"
    return "80+"


def ma20_bracket(gap) -> str:
    if gap is None or (isinstance(gap, float) and np.isnan(gap)):
        return "N/A"
    g = float(gap)
    if g <= -10: return "< -10%"
    if g <= -5:  return "-10% to -5%"
    if g <= 0:   return "-5% to 0%"
    if g <= 5:   return "0% to 5%"
    if g <= 10:  return "5% to 10%"
    return "> 10%"


def ma60_bracket(gap) -> str:
    if gap is None or (isinstance(gap, float) and np.isnan(gap)):
        return "N/A"
    g = float(gap)
    if g <= -5: return "< -5%"
    if g < 0:   return "-5% to 0%"
    if g < 3:   return "0% to 3%"
    if g < 5:   return "3% to 5%"
    return "> 5%"


def dedup_observations(df: pd.DataFrame, n_days: int, sorted_dates: dict) -> pd.DataFrame:
    """
    同股票在 n_days 個「交易日」內只保留第一筆 signal，消除前向報酬重疊。

    計數邏輯：利用 sorted_dates[stock_id] 直接 bisect，O(log N) per row。
    若該股無 price 資料，以日曆天 / 1.4 近似。
    """
    if df.empty:
        return df.copy()
    df_sorted = df.sort_values(["stock_id", "date"]).reset_index(drop=True)
    last_kept: dict = {}
    keep: list = []
    for _, row in df_sorted.iterrows():
        sid = row["stock_id"]
        d   = row["date"]
        prev = last_kept.get(sid)
        if prev is None:
            keep.append(True)
            last_kept[sid] = d
        else:
            sdates = sorted_dates.get(sid, [])
            if sdates:
                lo = bisect.bisect_right(sdates, prev)
                hi = bisect.bisect_right(sdates, d)
                tdays = hi - lo
            else:
                tdays = int((d - prev).days / 1.4)
            if tdays >= n_days:
                keep.append(True)
                last_kept[sid] = d
            else:
                keep.append(False)
    return df_sorted[keep].reset_index(drop=True)


def compute_stats(alpha_list: list) -> dict:
    """
    One-sample t-test H0: mean alpha = 0，加 Cohen's d 效應量與 bootstrap 95% CI。

    bootstrap CI 是 t-test CI 的 sanity check：
    股票 Alpha 分布通常右偏、有厚尾，t-test 假設未必成立。
    若兩者 CI 大幅分歧，以 bootstrap 為準。
    """
    arr = np.array(
        [x for x in alpha_list if x is not None and not np.isnan(float(x))],
        dtype=float,
    )
    n = len(arr)
    empty = {
        "n": n, "mean": None, "median": None, "std": None,
        "ci_low": None, "ci_high": None, "p_value": None, "win_rate": None,
        "cohens_d": None, "boot_ci_low": None, "boot_ci_high": None,
    }
    if n < 2:
        return empty
    mean = float(np.mean(arr))
    median = float(np.median(arr))
    std = float(np.std(arr, ddof=1))
    se = std / np.sqrt(n)
    _, p_val = sp_stats.ttest_1samp(arr, 0)
    ci = sp_stats.t.interval(0.95, df=n - 1, loc=mean, scale=se)
    win_rate = float(np.mean(arr > 0) * 100)

    # Effect size: Cohen's d (one-sample, H0: μ=0)
    # 0.2 = small, 0.5 = medium, 0.8 = large
    cohens_d = round(mean / std, 3) if std > 0 else 0.0

    # Bootstrap 95% CI (2 000 resamples, percentile method, seeded for reproducibility)
    rng = np.random.default_rng(42)
    boot_means = np.fromiter(
        (np.mean(rng.choice(arr, size=n, replace=True)) for _ in range(2000)),
        dtype=float, count=2000,
    )
    boot_ci_low  = round(float(np.percentile(boot_means, 2.5)), 2)
    boot_ci_high = round(float(np.percentile(boot_means, 97.5)), 2)

    return {
        "n":            n,
        "mean":         round(mean, 2),
        "median":       round(median, 2),
        "std":          round(std, 2),
        "ci_low":       round(float(ci[0]), 2),
        "ci_high":      round(float(ci[1]), 2),
        "p_value":      round(float(p_val), 3),
        "win_rate":     round(win_rate, 1),
        "cohens_d":     cohens_d,
        "boot_ci_low":  boot_ci_low,
        "boot_ci_high": boot_ci_high,
    }


# ── 主服務 ────────────────────────────────────────────────────

class ResearchBacktestService:
    """
    In-sample 回測服務，資料源為 analysis_results（cutoff 前）。
    使用 compute() 取得所有分組統計結果。
    """

    def compute(self) -> dict:
        """
        Returns dict:
          raw_df              — 有 alpha_20d 的完整資料列
          by_pt_bucket        — PT score 分組統計
          by_setup            — setup type 分組統計
          by_ma20             — MA20 偏離分組統計
          by_ma60             — MA60 距離分組統計
          by_month            — 月份分組統計
          by_regime           — market regime 分組統計
          cutoff              — RESEARCH_CUTOFF_DATE
          n_total_candidates  — cutoff 前 analysis_results 總筆數
          n_usable            — 有 20D forward return 的筆數
        """
        raw_df, n_total, sorted_dates = self._build_raw_df()

        if raw_df.empty:
            return {
                "raw_df": raw_df,
                "cutoff": _get_cutoff(),
                "n_total_candidates": n_total,
                "n_usable": 0,
            }

        usable = raw_df[raw_df["alpha_20d"].notna()].copy()

        # PT coverage — NULL 保持 NULL，不估算、不填 0
        n_with_pt    = int(usable["pt_score"].notna().sum())
        n_without_pt = int(usable["pt_score"].isna().sum())
        pt_coverage  = round(n_with_pt / len(usable) * 100, 1) if len(usable) > 0 else 0.0

        # PT bucket 統計只含有真實 pt_score 的列，N/A 不得納入績效比較
        pt_usable = usable[usable["pt_bucket"] != "N/A"]

        # ── 樣本獨立性診斷 ─────────────────────────────────────
        dedup_20 = dedup_observations(usable, 20, sorted_dates)
        dedup_60 = dedup_observations(usable, 60, sorted_dates)

        def _si_stats(df):
            return {
                "stats_20d": compute_stats(df["alpha_20d"].tolist()),
                "stats_60d": compute_stats(df["alpha_60d"].tolist()),
            }

        sample_independence = {
            "raw":      {"n": len(usable),  **_si_stats(usable)},
            "dedup_20": {"n": len(dedup_20), **_si_stats(dedup_20)},
            "dedup_60": {"n": len(dedup_60), **_si_stats(dedup_60)},
        }

        return {
            "raw_df":             usable,
            "by_pt_bucket":       self._group_stats(pt_usable, "pt_bucket", PT_BUCKET_ORDER),
            "by_setup":           self._group_stats(usable, "setup_type",   None),
            "by_ma20":            self._group_stats(usable, "ma20_bracket", MA20_BRACKET_ORDER),
            "by_ma60":            self._group_stats(usable, "ma60_bracket", MA60_BRACKET_ORDER),
            "by_month":           self._group_stats(usable, "ym",           None),
            "by_regime":          self._group_stats(usable, "regime",       ["bull", "neutral", "bear"]),
            "cutoff":             _get_cutoff(),
            "n_total_candidates": n_total,
            "n_usable":           len(usable),
            "n_with_pt":          n_with_pt,
            "n_without_pt":       n_without_pt,
            "pt_coverage_pct":    pt_coverage,
            "sample_independence": sample_independence,
        }

    # ── 內部：建構原始 DataFrame ──────────────────────────────

    def _build_raw_df(self):
        from src.database import AnalysisResult, DailyPrice, get_session

        cutoff = _get_cutoff()
        s = get_session()
        ar_rows = (
            s.query(
                AnalysisResult.stock_id,
                AnalysisResult.date,
                AnalysisResult.price_trend_score,
                AnalysisResult.setup_type,
                AnalysisResult.trade_signal,
                AnalysisResult.ma20_gap,
                AnalysisResult.volume_ratio,
                AnalysisResult.total_score,
                AnalysisResult.timing_score,
                AnalysisResult.behavior_score,
                AnalysisResult.rec_level,
            )
            .filter(AnalysisResult.date < cutoff)
            .all()
        )
        n_total = len(ar_rows)

        stock_ids = {r.stock_id for r in ar_rows} | {"0050"}
        prices_q = (
            s.query(DailyPrice)
            .filter(DailyPrice.stock_id.in_(stock_ids))
            .order_by(DailyPrice.stock_id, DailyPrice.date)
            .all()
        )
        s.close()

        # ── 建 price 索引 ──────────────────────────────────────
        # sorted_dates[sid]  = sorted list of dates
        # price_dict[sid][d] = close
        sorted_dates: dict = defaultdict(list)
        price_dict: dict   = defaultdict(dict)
        for p in prices_q:
            if p.close and p.close > 0:
                price_dict[p.stock_id][p.date] = p.close
        for sid in price_dict:
            sorted_dates[sid] = sorted(price_dict[sid].keys())

        # ── 預計算 MA60 與 MA60 slope ──────────────────────────
        # ma60_map[sid][d]       = (close, ma60_val_or_None)
        # ma60_slope_map[sid][d] = "up"/"down"/"flat"
        ma60_map: dict       = {}
        ma60_slope_map: dict = {}
        for sid, dates in sorted_dates.items():
            closes = [price_dict[sid][d] for d in dates]
            n = len(closes)
            d2ma60  = {}
            d2slope = {}
            for i, d in enumerate(dates):
                if i >= 59:
                    ma60_now = float(np.mean(closes[i - 59: i + 1]))
                    d2ma60[d] = (closes[i], ma60_now)
                    if i >= 64:
                        ma60_5ago = float(np.mean(closes[i - 64: i - 4]))
                        if ma60_now > ma60_5ago * 1.005:
                            d2slope[d] = "up"
                        elif ma60_now < ma60_5ago * 0.995:
                            d2slope[d] = "down"
                        else:
                            d2slope[d] = "flat"
                    else:
                        d2slope[d] = "flat"
                else:
                    d2ma60[d]  = (closes[i], None)
                    d2slope[d] = "flat"
            ma60_map[sid]       = d2ma60
            ma60_slope_map[sid] = d2slope

        # ── 0050 regime（當日 0050 close + MA60 slope）────────────
        # Bull    : close > MA60 且 slope up   → 趨勢確認多頭
        # Bear    : close < MA60 且 slope down → 趨勢確認空頭
        # Neutral : 其他（slope flat、或位置與趨勢方向不一致的過渡期）
        regime_map: dict = {}
        _0050_slope = ma60_slope_map.get("0050", {})
        for d, (close, ma60) in ma60_map.get("0050", {}).items():
            if ma60 is not None:
                slope = _0050_slope.get(d, "flat")
                if close > ma60 and slope == "up":
                    regime_map[d] = "bull"
                elif close < ma60 and slope == "down":
                    regime_map[d] = "bear"
                else:
                    regime_map[d] = "neutral"

        # ── 前向報酬（O(log n) per lookup）────────────────────
        def _fwd(sid: str, entry_date: date, n_days: int):
            sdates = sorted_dates.get(sid, [])
            if not sdates:
                return None, None
            idx = bisect.bisect_left(sdates, entry_date)
            if idx >= len(sdates):
                return None, None
            entry = price_dict[sid][sdates[idx]]
            if idx + n_days < len(sdates):
                exit_c = price_dict[sid][sdates[idx + n_days]]
                return round((exit_c - entry) / entry * 100 - ROUND_TRIP_COST, 2), entry
            return None, entry

        # ── 組裝資料列 ──────────────────────────────────────────
        rows = []
        for ar in ar_rows:
            d = ar.date if isinstance(ar.date, date) else ar.date

            ret20, _ = _fwd(ar.stock_id, d, 20)
            ret60, _ = _fwd(ar.stock_id, d, 60)
            b20,   _ = _fwd("0050",      d, 20)
            b60,   _ = _fwd("0050",      d, 60)

            # MA60 gap（no look-ahead: 使用到 d 為止的 MA60）
            m60_info = ma60_map.get(ar.stock_id, {}).get(d)
            if m60_info:
                close_val, ma60_val = m60_info
                ma60_gap_v = (
                    round((close_val - ma60_val) / ma60_val * 100, 2)
                    if ma60_val else None
                )
            else:
                ma60_gap_v = None

            slope_v = ma60_slope_map.get(ar.stock_id, {}).get(d, "flat")

            a20 = round(ret20 - b20, 2) if (ret20 is not None and b20 is not None) else None
            a60 = round(ret60 - b60, 2) if (ret60 is not None and b60 is not None) else None

            ym = d.strftime("%Y-%m") if hasattr(d, "strftime") else str(d)[:7]

            rows.append({
                "date":         d,
                "stock_id":     ar.stock_id,
                "pt_score":     ar.price_trend_score,
                "setup_type":   ar.setup_type or "none",
                "trade_signal": ar.trade_signal or "",
                "ma20_gap":     ar.ma20_gap,
                "ma60_gap":     ma60_gap_v,
                "ma60_slope":   slope_v,
                "vol_ratio":    ar.volume_ratio,
                "total_score":  ar.total_score,
                "timing_score": ar.timing_score,
                "behavior_score": ar.behavior_score,
                "rec_level":    ar.rec_level,
                "ret_20d":      ret20,
                "ret_60d":      ret60,
                "b0050_20":     b20,
                "b0050_60":     b60,
                "alpha_20d":    a20,
                "alpha_60d":    a60,
                "pt_bucket":    pt_bucket(ar.price_trend_score),
                "ma20_bracket": ma20_bracket(ar.ma20_gap),
                "ma60_bracket": ma60_bracket(ma60_gap_v),
                "regime":       regime_map.get(d, "unknown"),
                "ym":           ym,
            })

        return pd.DataFrame(rows), n_total, sorted_dates

    # ── 分組統計 ──────────────────────────────────────────────

    @staticmethod
    def _group_stats(df: pd.DataFrame, group_col: str,
                     order: Optional[list]) -> pd.DataFrame:
        if group_col not in df.columns or df.empty:
            return pd.DataFrame()

        rows = []
        for grp_val, gdf in df.groupby(group_col, sort=False):
            s20 = compute_stats(gdf["alpha_20d"].tolist())
            s60 = compute_stats(gdf["alpha_60d"].tolist())
            rows.append({
                group_col:          grp_val,
                "n":                s20["n"],
                "20D均Alpha%":      s20["mean"],
                "20D中位Alpha%":    s20["median"],
                "20D Std":          s20["std"],
                "20D CI低":         s20["ci_low"],
                "20D CI高":         s20["ci_high"],
                "20D p值":          s20["p_value"],
                "20D勝率%":         s20["win_rate"],
                "20D Cohen'd":      s20["cohens_d"],
                "20D Boot CI低":    s20["boot_ci_low"],
                "20D Boot CI高":    s20["boot_ci_high"],
                "60D均Alpha%":      s60["mean"],
                "60D中位Alpha%":    s60["median"],
                "60D Std":          s60["std"],
                "60D CI低":         s60["ci_low"],
                "60D CI高":         s60["ci_high"],
                "60D p值":          s60["p_value"],
                "60D勝率%":         s60["win_rate"],
                "60D Cohen'd":      s60["cohens_d"],
                "60D Boot CI低":    s60["boot_ci_low"],
                "60D Boot CI高":    s60["boot_ci_high"],
            })

        out = pd.DataFrame(rows)
        if order and not out.empty:
            in_order  = [x for x in order if x in out[group_col].values]
            remainder = [x for x in out[group_col].values if x not in order]
            out = (
                out.set_index(group_col)
                .reindex(in_order + remainder)
                .reset_index()
            )
        return out


# ── Forward Signal 工具函數（供 main.py 呼叫）────────────────

def write_forward_signals(session, trade_date: date, today_ars: list) -> int:
    """
    凍結當日 analysis_results 為 forward_signals。

    Append-only：(trade_date, stock_id) 已存在則 skip，永不 UPDATE。
    Returns: 實際插入筆數
    """
    from src.database import DailyPrice, ForwardSignal, MODEL_VERSION, Recommendation, Stock
    from datetime import timedelta

    if not today_ars:
        return 0

    stock_ids = [ar.stock_id for ar in today_ars]

    # 批次查詢：最近 100 天歷史價格（含 0050 供 regime 計算）
    lookback = trade_date - timedelta(days=100)
    hist_rows = (
        session.query(DailyPrice.stock_id, DailyPrice.date, DailyPrice.close)
        .filter(
            DailyPrice.stock_id.in_(stock_ids + ["0050"]),
            DailyPrice.date >= lookback,
            DailyPrice.date <= trade_date,
            DailyPrice.close.isnot(None),
        )
        .order_by(DailyPrice.stock_id, DailyPrice.date)
        .all()
    )
    hist_map: dict   = defaultdict(list)
    close_on_day: dict = {}     # close_at_signal: 當日收盤
    for sid, d, c in hist_rows:
        if c and c > 0:
            hist_map[sid].append(c)
            if d == trade_date:
                close_on_day[sid] = c

    def _ma60_features(sid: str):
        closes = hist_map.get(sid, [])
        if len(closes) < 60:
            return None, "flat"
        ma60_now = float(np.mean(closes[-60:]))
        gap = round((closes[-1] - ma60_now) / ma60_now * 100, 2)
        if len(closes) >= 65:
            ma60_5ago = float(np.mean(closes[-65:-5]))
            slope = ("up"   if ma60_now > ma60_5ago * 1.005
                     else "down" if ma60_now < ma60_5ago * 0.995
                     else "flat")
        else:
            slope = "flat"
        return gap, slope

    # market_regime_at_signal: 0050 close + MA60 slope（三狀態，與 Research 分析一致）
    def _regime_0050() -> str:
        closes = hist_map.get("0050", [])
        if len(closes) < 60:
            return "unknown"
        ma60_now = float(np.mean(closes[-60:]))
        close_now = closes[-1]
        slope = "flat"
        if len(closes) >= 65:
            ma60_5ago = float(np.mean(closes[-65:-5]))
            slope = ("up"   if ma60_now > ma60_5ago * 1.005
                     else "down" if ma60_now < ma60_5ago * 0.995
                     else "flat")
        if close_now > ma60_now and slope == "up":
            return "bull"
        if close_now < ma60_now and slope == "down":
            return "bear"
        return "neutral"

    regime_today = _regime_0050()

    # 取股票名稱與產業
    stock_rows = (
        session.query(Stock.stock_id, Stock.name, Stock.industry)
        .filter(Stock.stock_id.in_(stock_ids))
        .all()
    )
    name_map     = {r.stock_id: r.name     for r in stock_rows}
    industry_map = {r.stock_id: r.industry for r in stock_rows}

    # candidate_rank: 當日所有 candidates 按 total_score 排名
    sorted_ars = sorted(today_ars, key=lambda x: (x.total_score or 0.0), reverse=True)
    rank_map = {ar.stock_id: i + 1 for i, ar in enumerate(sorted_ars)}

    # Recommendation 快照：Audit Trail 用（_save_recommendations 已先執行）
    rec_snap: dict = {
        r.stock_id: r
        for r in session.query(Recommendation)
        .filter(
            Recommendation.date == trade_date,
            Recommendation.stock_id.in_(stock_ids),
        )
        .all()
    }

    def _decision_label_for(ar) -> str | None:
        try:
            from src.engines.decision import decision_label as _dl
            label_result = _dl({
                "trade_signal": ar.trade_signal,
                "setup_type":   ar.setup_type,
                "ma20_gap":     ar.ma20_gap,
            })
            return label_result.get("label")
        except Exception:
            return None

    # 查已存在的 (trade_date, stock_id) 以避免衝突
    existing = {
        r.stock_id
        for r in session.query(ForwardSignal.stock_id)
        .filter(ForwardSignal.trade_date == trade_date)
        .all()
    }

    inserted = 0
    for ar in today_ars:
        if ar.stock_id in existing:
            continue  # append-only: 永不覆寫

        ma60_gap_v, ma60_slope_v = _ma60_features(ar.stock_id)
        rec = rec_snap.get(ar.stock_id)

        session.add(ForwardSignal(
            trade_date              = trade_date,
            stock_id                = ar.stock_id,
            stock_name              = name_map.get(ar.stock_id, ""),
            pt_score                = ar.price_trend_score,
            setup_type              = ar.setup_type,
            trade_signal            = ar.trade_signal,
            ma20_gap                = ar.ma20_gap,
            ma60_gap                = ma60_gap_v,
            ma60_slope              = ma60_slope_v,
            vol_ratio               = ar.volume_ratio,
            total_score             = ar.total_score,
            timing_score            = ar.timing_score,
            behavior_score          = ar.behavior_score,
            rec_level               = ar.rec_level,
            model_version           = MODEL_VERSION,
            confidence              = ar.confidence,
            industry                = industry_map.get(ar.stock_id),
            market_regime_at_signal = regime_today,
            close_at_signal         = close_on_day.get(ar.stock_id),
            candidate_rank          = rank_map.get(ar.stock_id),
            # ── 決策快照 ─────────────────────────────────────────
            entry_low               = rec.entry_low   if rec else None,
            entry_high              = rec.entry_high  if rec else None,
            stop_price              = rec.stop_price  if rec else None,
            target1                 = rec.target1     if rec else None,
            target2                 = rec.target2     if rec else None,
            decision_label          = _decision_label_for(ar),
        ))
        inserted += 1

    if inserted:
        session.commit()
    return inserted


def compute_signal_outcomes(session, as_of_date: date) -> int:
    """
    回填已成熟 ForwardSignal 的績效結果。

    成熟條件：trade_date + 30 calendar days <= as_of_date（約等於 20 trading days）
    僅處理 outcomes_computed_at IS NULL 的記錄。
    只計算有 decision_label（有進入推薦流程）的信號。
    Returns: 更新筆數
    """
    from datetime import datetime, timedelta

    from src.database import DailyPrice, ForwardSignal

    cutoff = as_of_date - timedelta(days=30)

    pending = (
        session.query(ForwardSignal)
        .filter(
            ForwardSignal.trade_date <= cutoff,
            ForwardSignal.outcomes_computed_at.is_(None),
            ForwardSignal.decision_label.isnot(None),
            ForwardSignal.close_at_signal.isnot(None),
            ForwardSignal.is_valid.isnot(False),  # exclude invalid (non-trading-day) records
        )
        .all()
    )
    if not pending:
        return 0

    stock_ids = list({r.stock_id for r in pending})
    min_date = min(r.trade_date for r in pending)
    max_date = max(r.trade_date for r in pending) + timedelta(days=150)

    price_rows = (
        session.query(DailyPrice.stock_id, DailyPrice.date, DailyPrice.close)
        .filter(
            DailyPrice.stock_id.in_(stock_ids + ["0050"]),
            DailyPrice.date >= min_date,
            DailyPrice.date <= max_date,
            DailyPrice.close.isnot(None),
        )
        .order_by(DailyPrice.stock_id, DailyPrice.date)
        .all()
    )

    price_map: dict = {}
    for sid, d, c in price_rows:
        if sid not in price_map:
            price_map[sid] = {}
        price_map[sid][d] = c
    sorted_dates_map = {sid: sorted(dm.keys()) for sid, dm in price_map.items()}
    p0050 = price_map.get("0050", {})
    sorted_0050 = sorted(p0050.keys())

    import bisect

    updated = 0
    for fs in pending:
        sdates = sorted_dates_map.get(fs.stock_id, [])
        idx_s = bisect.bisect_right(sdates, fs.trade_date)
        if idx_s == 0:
            continue

        idx_0050 = bisect.bisect_right(sorted_0050, fs.trade_date)
        if idx_0050 == 0:
            continue
        p0_entry = p0050.get(sorted_0050[idx_0050 - 1])
        if not p0_entry:
            continue

        entry = fs.close_at_signal
        stop  = fs.stop_price
        t1    = fs.target1

        def _return_at(n_days):
            target_idx = idx_s + n_days - 1
            if target_idx >= len(sdates):
                return None, None
            fwd_close = price_map.get(fs.stock_id, {}).get(sdates[target_idx])
            if not fwd_close:
                return None, None
            t0050_idx = idx_0050 + n_days - 1
            if t0050_idx >= len(sorted_0050):
                return None, None
            fwd_0050 = p0050.get(sorted_0050[t0050_idx])
            if not fwd_0050:
                return None, None
            ret = round((fwd_close - entry) / entry * 100, 2)
            alpha = round(ret - (fwd_0050 - p0_entry) / p0_entry * 100, 2)
            return ret, alpha

        ret_20, alpha_20 = _return_at(20)
        ret_60, alpha_60 = _return_at(60)

        # stop_triggered_day: first trading day (1-indexed) where close < stop
        stop_day = None
        if stop and stop > 0:
            for i in range(idx_s, min(idx_s + 20, len(sdates))):
                c = price_map.get(fs.stock_id, {}).get(sdates[i])
                if c and c < stop:
                    stop_day = i - idx_s + 1
                    break

        # t1_hit_day: first trading day (1-indexed) where close >= t1
        t1_day = None
        if t1 and t1 > 0:
            for i in range(idx_s, min(idx_s + 20, len(sdates))):
                c = price_map.get(fs.stock_id, {}).get(sdates[i])
                if c and c >= t1:
                    t1_day = i - idx_s + 1
                    break

        if t1_day:
            note = "T1_HIT"
        elif stop_day:
            note = "STOP_TRIGGERED"
        elif ret_20 is not None:
            note = "EXPIRED"
        else:
            note = None  # not enough data yet

        fs.fwd_return_20d     = ret_20
        fs.alpha_20d          = alpha_20
        fs.fwd_return_60d     = ret_60
        fs.alpha_60d          = alpha_60
        fs.stop_triggered_day = stop_day
        fs.t1_hit_day         = t1_day
        fs.outcome_note       = note
        if note:  # only mark computed when we got a result
            fs.outcomes_computed_at = datetime.utcnow()
        updated += 1

    if updated:
        session.commit()
    return updated
