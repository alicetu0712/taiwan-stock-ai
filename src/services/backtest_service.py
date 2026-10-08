"""
backtest_service.py — 回測計算服務層

純 Python 業務邏輯，無 Streamlit 依賴。
dashboard/pages/backtest.py 的 @st.cache_data 函數委託此 Service。
"""

import logging
from collections import defaultdict
from datetime import date
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

ROUND_TRIP_COST = 0.585  # 買進+賣出合計交易成本（%）

_FACTOR_COLS = [
    "quality_score",
    "timing_score",
    "behavior_score",
    "intelligence_score",
    "risk_score",
    "total_score",
]


def _ret_at(plist: list, ref_date: date, n_trading_days: int):
    """從 ref_date 起第 n_trading_days 個交易日的報酬率和進場價。"""
    after = [(d, c) for d, c in plist if d >= ref_date and c]
    if not after:
        return None, None
    entry = after[0][1]
    if len(after) > n_trading_days:
        exit_c = after[n_trading_days][1]
        return round((exit_c - entry) / entry * 100, 2), entry
    return None, entry


def _alpha(ret_val, benchmark_val):
    if ret_val is not None and benchmark_val is not None:
        return round(ret_val - benchmark_val, 2)
    return None


class BacktestService:
    """回測計算服務。"""

    @staticmethod
    def compute_backtest_data() -> pd.DataFrame:
        """
        查詢所有歷史推薦，計算 20/60 日報酬率及對比 0050/0056 的 Alpha。

        Returns:
            pd.DataFrame with columns:
                date, stock_id, confidence, entry,
                ret_20d, ret_60d,
                b0050_20, b0056_20, b0050_60, b0056_60,
                a0050_20, a0056_20, a0050_60, a0056_60,
                data_flag
        """
        try:
            from src.database import DailyPrice, Recommendation, get_session

            s = get_session()
            recs = s.query(Recommendation).order_by(Recommendation.date).all()
            all_ids = {r.stock_id for r in recs} | {"0050", "0056"}
            all_prices_q = (
                s.query(DailyPrice)
                .filter(DailyPrice.stock_id.in_(all_ids))
                .order_by(DailyPrice.stock_id, DailyPrice.date)
                .all()
            )
            s.close()
        except Exception as e:
            logger.exception(
                f"BacktestService.compute_backtest_data DB query failed: {e}"
            )
            return pd.DataFrame()

        price_map: dict = defaultdict(list)
        for p in all_prices_q:
            price_map[p.stock_id].append((p.date, p.close))

        # 去重：同一股票 20 個交易日內不重複計算
        last_rec_date: dict = {}
        deduped_recs = []
        for r in sorted(recs, key=lambda x: x.date):
            prev = last_rec_date.get(r.stock_id)
            if prev is None:
                deduped_recs.append(r)
                last_rec_date[r.stock_id] = r.date
            else:
                sp_chk = price_map.get(r.stock_id, [])
                tdays = sum(1 for d, _ in sp_chk if prev < d <= r.date)
                if tdays >= 20:
                    deduped_recs.append(r)
                    last_rec_date[r.stock_id] = r.date

        today_dt = date.today()
        rows = []
        for r in deduped_recs:
            sp = price_map.get(r.stock_id, [])
            if not sp:
                continue
            s20, entry = _ret_at(sp, r.date, 20)
            s60, _ = _ret_at(sp, r.date, 60)

            data_flag = None
            if s20 is None and entry is not None and (today_dt - r.date).days > 35:
                after_rec = [(d, c) for d, c in sp if d > r.date and c]
                if after_rec:
                    s20 = round(
                        (after_rec[-1][1] - entry) / entry * 100 - ROUND_TRIP_COST, 2
                    )
                    data_flag = "⚠️ 停牌"
                else:
                    s20 = round(-100.0 - ROUND_TRIP_COST, 2)
                    data_flag = "❌ 下市"

            if s20 is not None and data_flag is None:
                s20 = round(s20 - ROUND_TRIP_COST, 2)
            if s60 is not None:
                s60 = round(s60 - ROUND_TRIP_COST, 2)

            b0050_20, _ = _ret_at(price_map.get("0050", []), r.date, 20)
            b0050_60, _ = _ret_at(price_map.get("0050", []), r.date, 60)
            b0056_20, _ = _ret_at(price_map.get("0056", []), r.date, 20)
            b0056_60, _ = _ret_at(price_map.get("0056", []), r.date, 60)

            if b0050_20 is not None:
                b0050_20 = round(b0050_20 - ROUND_TRIP_COST, 2)
            if b0050_60 is not None:
                b0050_60 = round(b0050_60 - ROUND_TRIP_COST, 2)
            if b0056_20 is not None:
                b0056_20 = round(b0056_20 - ROUND_TRIP_COST, 2)
            if b0056_60 is not None:
                b0056_60 = round(b0056_60 - ROUND_TRIP_COST, 2)

            rows.append(
                {
                    "date": r.date,
                    "stock_id": r.stock_id,
                    "confidence": r.confidence,
                    "entry": entry,
                    "ret_20d": s20,
                    "ret_60d": s60,
                    "b0050_20": b0050_20,
                    "b0056_20": b0056_20,
                    "b0050_60": b0050_60,
                    "b0056_60": b0056_60,
                    "a0050_20": _alpha(s20, b0050_20),
                    "a0056_20": _alpha(s20, b0056_20),
                    "a0050_60": _alpha(s60, b0050_60),
                    "a0056_60": _alpha(s60, b0056_60),
                    "data_flag": data_flag,
                }
            )
        return pd.DataFrame(rows)

    @staticmethod
    def compute_baseline(n_sim: int = 1000) -> dict:
        """
        Monte Carlo：隨機選股 n_sim 次，回傳 20 日報酬率分布。

        Returns:
            {"sim_means": list[float], "n_sim": int} or {}
        """
        import bisect as _bs
        import random as _rnd

        try:
            from src.database import AnalysisResult as _AR
            from src.database import DailyPrice, Recommendation, get_session

            s = get_session()
            recs = s.query(Recommendation).order_by(Recommendation.date).all()
            ar_rows = s.query(_AR.date, _AR.stock_id).all()
            ar_stock_ids = {ar_sid for _, ar_sid in ar_rows}
            all_ids = {r.stock_id for r in recs} | {"0050", "0056"} | ar_stock_ids
            all_prices_q = (
                s.query(DailyPrice)
                .filter(DailyPrice.stock_id.in_(all_ids))
                .order_by(DailyPrice.stock_id, DailyPrice.date)
                .all()
            )
            s.close()
        except Exception as e:
            logger.exception(f"BacktestService.compute_baseline DB query failed: {e}")
            return {}

        price_map: dict = defaultdict(list)
        for p in all_prices_q:
            price_map[p.stock_id].append((p.date, p.close))

        def _ret20(plist, ref_date):
            after = [(d, c) for d, c in plist if d >= ref_date and c]
            if len(after) <= 20:
                return None
            return (after[20][1] - after[0][1]) / after[0][1] * 100

        _last: dict = {}
        deduped = []
        for r in sorted(recs, key=lambda x: x.date):
            prev = _last.get(r.stock_id)
            if prev is None:
                deduped.append(r)
                _last[r.stock_id] = r.date
            else:
                tdays = sum(
                    1 for d, _ in price_map.get(r.stock_id, []) if prev < d <= r.date
                )
                if tdays >= 20:
                    deduped.append(r)
                    _last[r.stock_id] = r.date

        dates_idx = {
            sid: sorted(d for d, _ in plist) for sid, plist in price_map.items()
        }

        def _tdays(sid, d1, d2):
            dl = dates_idx.get(sid, [])
            return _bs.bisect_right(dl, d2) - _bs.bisect_right(dl, d1)

        analyzed_by_date: dict = defaultdict(set)
        for ar_date, ar_sid in ar_rows:
            analyzed_by_date[ar_date].add(ar_sid)

        pool_per_rec = []
        for r in deduped:
            day_pool = analyzed_by_date.get(r.date, set())
            alts = [sid for sid in day_pool if sid != r.stock_id and price_map.get(sid)]
            if not alts:
                alts = [
                    sid for sid in all_ids if sid != r.stock_id and price_map.get(sid)
                ]
            pool_per_rec.append((r.date, alts))

        _rng = _rnd.Random(42)
        sim_means = []
        for _ in range(n_sim):
            sim_rets = []
            last_pick: dict = {}
            for ref_date, alts in pool_per_rec:
                if not alts:
                    continue
                eligible = [
                    sid
                    for sid in alts
                    if last_pick.get(sid) is None
                    or _tdays(sid, last_pick[sid], ref_date) >= 20
                ]
                picked = _rng.choice(eligible if eligible else alts)
                last_pick[picked] = ref_date
                ret = _ret20(price_map[picked], ref_date)
                if ret is not None:
                    sim_rets.append(ret - ROUND_TRIP_COST)
            if sim_rets:
                sim_means.append(sum(sim_rets) / len(sim_rets))
        return {"sim_means": sim_means, "n_sim": n_sim}

    @staticmethod
    def compute_signal_quality(min_obs: int = 10) -> dict:
        """
        模型修正：計算各因子維度的 IC（Spearman 相關）與 IC IR。

        使用 AnalysisResult（每日全截面）+ DailyPrice 計算各因子對
        20/60 日前向報酬的預測力，識別 signal quality 瓶頸。

        Returns:
            {
                "factor_ic": {
                    factor_name: {
                        "ic_20": float | None,
                        "ic_60": float | None,
                        "ic_20_ir": float | None,   # IC / std(monthly IC)
                        "ic_60_ir": float | None,
                        "t_20": float | None,       # t-stat: IC sqrt(n) / std
                        "t_60": float | None,
                        "n_20": int,
                        "n_60": int,
                    }
                },
                "monthly_ic": pd.DataFrame,         # columns: ym, factor, ic_20, n
                "n_obs": int,                       # 有效觀測數（至少有一個 forward ret）
            }
            或 {} 若 DB 查詢失敗。
        """
        try:
            from src.database import AnalysisResult, DailyPrice, get_session

            s = get_session()
            ar_rows = s.query(AnalysisResult).all()
            all_ids = {r.stock_id for r in ar_rows}
            all_prices_q = (
                s.query(DailyPrice)
                .filter(DailyPrice.stock_id.in_(all_ids))
                .order_by(DailyPrice.stock_id, DailyPrice.date)
                .all()
            )
            s.close()
        except Exception as e:
            logger.exception(f"BacktestService.compute_signal_quality DB query failed: {e}")
            return {}

        price_map: dict = defaultdict(list)
        for p in all_prices_q:
            price_map[p.stock_id].append((p.date, p.close))

        # 建立觀測記錄（每筆 AnalysisResult + 對應前向報酬）
        records = []
        for r in ar_rows:
            sp = price_map.get(r.stock_id, [])
            ret20, _ = _ret_at(sp, r.date, 20)
            ret60, _ = _ret_at(sp, r.date, 60)
            if ret20 is None and ret60 is None:
                continue
            row: dict = {
                "date": r.date,
                "stock_id": r.stock_id,
                "ret_20": ret20,
                "ret_60": ret60,
            }
            for f in _FACTOR_COLS:
                row[f] = getattr(r, f, None)
            records.append(row)

        if not records:
            return {}

        df = pd.DataFrame(records)

        try:
            from scipy.stats import spearmanr as _spearmanr
        except ImportError:
            logger.error("scipy not installed; cannot compute IC")
            return {}

        # ── 整體 IC 與 t-stat ──────────────────────────────────
        factor_ic: dict = {}
        for f in _FACTOR_COLS:
            ic20 = ic60 = t20 = t60 = None
            n20 = n60 = 0

            v20 = df.dropna(subset=[f, "ret_20"])
            v60 = df.dropna(subset=[f, "ret_60"])
            n20 = len(v20)
            n60 = len(v60)

            if n20 >= min_obs:
                corr, _ = _spearmanr(v20[f], v20["ret_20"])
                ic20 = round(float(corr), 4)
                import math
                # Fisher z t-stat approximation
                t20 = round(ic20 * math.sqrt(n20), 4)

            if n60 >= min_obs:
                corr, _ = _spearmanr(v60[f], v60["ret_60"])
                ic60 = round(float(corr), 4)
                import math
                t60 = round(ic60 * math.sqrt(n60), 4)

            factor_ic[f] = {
                "ic_20": ic20,
                "ic_60": ic60,
                "t_20": t20,
                "t_60": t60,
                "n_20": n20,
                "n_60": n60,
                "ic_20_ir": None,
                "ic_60_ir": None,
            }

        # ── 逐月 IC（用於時間穩定性診斷）──────────────────────
        def _ym(d):
            return d.strftime("%Y-%m") if hasattr(d, "strftime") else str(d)[:7]

        df["ym"] = df["date"].apply(_ym)
        monthly_rows = []
        for ym, grp in df.groupby("ym"):
            for f in _FACTOR_COLS:
                v = grp.dropna(subset=[f, "ret_20"])
                if len(v) < min_obs:
                    continue
                corr, _ = _spearmanr(v[f], v["ret_20"])
                monthly_rows.append({"ym": ym, "factor": f, "ic_20": round(float(corr), 4), "n": len(v)})

        monthly_ic_df = pd.DataFrame(monthly_rows) if monthly_rows else pd.DataFrame(
            columns=["ym", "factor", "ic_20", "n"]
        )

        # ── IC IR（月 IC 序列的均值/標準差）───────────────────
        if not monthly_ic_df.empty:
            for f in _FACTOR_COLS:
                sub = monthly_ic_df[monthly_ic_df["factor"] == f]["ic_20"]
                if len(sub) >= 3 and sub.std() > 0:
                    ir = round(float(sub.mean() / sub.std()), 4)
                    factor_ic[f]["ic_20_ir"] = ir

        return {
            "factor_ic": factor_ic,
            "monthly_ic": monthly_ic_df,
            "n_obs": len(df),
        }

    # ──────────────────────────────────────────────────────────────
    # V1 vs V2 策略比較
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def compute_v1_v2_comparison() -> dict:
        """
        對所有歷史 recommend tier 推薦，用當時可用的價格資料重跑
        PriceTrendAnalyzer，模擬 V2 三關卡（PT≥60 AND setup≠breakdown
        AND signal≠sell），比較兩版策略的績效指標。

        Returns dict with keys:
            summary      : pd.DataFrame  — V1/V2/V2-fail 三組彙總
            by_setup     : pd.DataFrame  — 按 setup_type 分組
            by_deviation : pd.DataFrame  — 按 MA20 乖離率分組
            detail       : pd.DataFrame  — 每筆推薦明細
        """
        try:
            from src.database import DailyPrice, Recommendation, get_session
            s = get_session()
            recs = (
                s.query(Recommendation)
                .filter(Recommendation.tier == "recommend")
                .order_by(Recommendation.date)
                .all()
            )
            all_ids = {r.stock_id for r in recs} | {"0050"}
            price_rows = (
                s.query(DailyPrice)
                .filter(DailyPrice.stock_id.in_(all_ids))
                .order_by(DailyPrice.stock_id, DailyPrice.date)
                .all()
            )
            s.close()
        except Exception as e:
            logger.exception(f"compute_v1_v2_comparison DB query failed: {e}")
            return {}

        # price_map: stock_id -> sorted [(date, open, high, low, close, volume)]
        from collections import defaultdict
        price_map: dict = defaultdict(list)
        for p in price_rows:
            price_map[p.stock_id].append((p.date, p.open, p.high, p.low, p.close, p.volume))

        # 去重（同股 20 交易日內只取第一筆）
        last_date: dict = {}
        deduped = []
        for r in recs:
            prev = last_date.get(r.stock_id)
            if prev is None:
                deduped.append(r)
                last_date[r.stock_id] = r.date
            else:
                tdays = sum(1 for d, *_ in price_map.get(r.stock_id, []) if prev < d <= r.date)
                if tdays >= 20:
                    deduped.append(r)
                    last_date[r.stock_id] = r.date

        # 建立 PriceTrendAnalyzer 並計算每筆推薦的 V2 指標
        try:
            from src.analyzers.price_trend import PriceTrendAnalyzer
            pt_engine = PriceTrendAnalyzer()
        except Exception as e:
            logger.error(f"PriceTrendAnalyzer import failed: {e}")
            return {}

        import math
        rows_out = []
        today_dt = date.today()

        for r in deduped:
            sp_full = price_map.get(r.stock_id, [])
            # 取截至 rec date 的最近 90 筆（≈ 4 個月）
            hist = [(d, o, h, lo, c, v) for d, o, h, lo, c, v in sp_full if d <= r.date]
            if len(hist) < 20:
                continue

            # 組成 DataFrame 供 PriceTrendAnalyzer 使用
            import pandas as _pd
            hist_df = _pd.DataFrame([
                {"date": str(d), "open": o, "high": h, "low": lo,
                 "close": c, "volume": v}
                for d, o, h, lo, c, v in hist[-90:]
            ])

            # 重跑 V2 分析
            try:
                pt_result = pt_engine.analyze(r.stock_id, hist_df)
            except Exception as _exc:
                logger.debug(f"PT analyze failed for {r.stock_id}: {_exc}")
                pt_result = None

            pt_score  = pt_result.price_trend_score if pt_result else 0.0
            setup     = pt_result.setup_type         if pt_result else "none"
            signal    = pt_result.trade_signal       if pt_result else "wait"
            ma20_gap  = pt_result.ma20_gap           if pt_result else None
            ma60_gap  = pt_result.ma60_gap           if pt_result else None
            vol_ratio = pt_result.volume_ratio       if pt_result else None
            ma60_slope = pt_result.ma60_slope        if pt_result else "flat"
            pt_ma20   = pt_result.ma20               if pt_result else None
            pt_ma60   = pt_result.ma60               if pt_result else None

            # V2 關卡判斷
            v2_pass = (pt_score >= 60) and (setup != "breakdown") and (signal != "sell")

            # MA60 支撐候選分組（條件：價格 < MA20 且 MA20 > MA60 且 MA60 向上 且縮量）
            ma60_bracket = None
            if (ma20_gap is not None and ma20_gap < 0
                    and ma60_gap is not None and abs(ma60_gap) <= 5.0
                    and ma60_slope == "up"
                    and pt_ma20 is not None and pt_ma60 is not None and pt_ma20 > pt_ma60
                    and (vol_ratio is None or vol_ratio <= 1.0)):
                ab = abs(ma60_gap)
                if ab <= 1.0:
                    ma60_bracket = "≤1%"
                elif ab <= 2.0:
                    ma60_bracket = "1–2%"
                elif ab <= 3.0:
                    ma60_bracket = "2–3%"
                else:
                    ma60_bracket = "3–5%"

            # MA20 乖離率分組
            if ma20_gap is None:
                dev_bracket = "—"
            elif ma20_gap < 0:
                dev_bracket = "< 0%"
            elif ma20_gap < 3:
                dev_bracket = "0–3%"
            elif ma20_gap < 5:
                dev_bracket = "3–5%"
            elif ma20_gap < 8:
                dev_bracket = "5–8%"
            elif ma20_gap < 12:
                dev_bracket = "8–12%"
            else:
                dev_bracket = "≥12%"

            # 計算前向報酬
            sp_close = [(d, c) for d, _, _, _, c, _ in sp_full]
            s20, entry = _ret_at(sp_close, r.date, 20)
            s60, _     = _ret_at(sp_close, r.date, 60)

            # 補全停牌/下市
            data_flag = None
            if s20 is None and entry is not None and (today_dt - r.date).days > 35:
                after = [(d, c) for d, c in sp_close if d > r.date and c]
                if after:
                    s20 = round((after[-1][1] - entry) / entry * 100 - ROUND_TRIP_COST, 2)
                    data_flag = "⚠️ 停牌"
                else:
                    s20 = round(-100.0 - ROUND_TRIP_COST, 2)
                    data_flag = "❌ 下市"

            if s20 is not None and data_flag is None:
                s20 = round(s20 - ROUND_TRIP_COST, 2)
            if s60 is not None:
                s60 = round(s60 - ROUND_TRIP_COST, 2)

            # 0050 基準
            sp_0050 = [(d, c) for d, _, _, _, c, _ in price_map.get("0050", [])]
            b0050_20, _ = _ret_at(sp_0050, r.date, 20)
            b0050_60, _ = _ret_at(sp_0050, r.date, 60)
            if b0050_20 is not None:
                b0050_20 = round(b0050_20 - ROUND_TRIP_COST, 2)
            if b0050_60 is not None:
                b0050_60 = round(b0050_60 - ROUND_TRIP_COST, 2)

            rows_out.append({
                "date":        r.date,
                "stock_id":    r.stock_id,
                "stock_name":  r.stock_name or "",
                "pt_score":    round(pt_score, 1),
                "setup":       setup,
                "signal":      signal,
                "ma20_gap":    round(ma20_gap, 1) if ma20_gap is not None else None,
                "ma60_gap":    round(ma60_gap, 1) if ma60_gap is not None else None,
                "vol_ratio":   round(vol_ratio, 2) if vol_ratio is not None else None,
                "dev_bracket": dev_bracket,
                "ma60_bracket": ma60_bracket,
                "v2_pass":     v2_pass,
                "ret_20d":     s20,
                "ret_60d":     s60,
                "b0050_20":    b0050_20,
                "b0050_60":    b0050_60,
                "alpha_20d":   _alpha(s20, b0050_20),
                "alpha_60d":   _alpha(s60, b0050_60),
                "data_flag":   data_flag,
            })

        if not rows_out:
            return {}

        detail = pd.DataFrame(rows_out)

        def _group_stats(sub: pd.DataFrame, hold: int) -> dict:
            """計算一個子集的彙總指標。"""
            ret_col   = f"ret_{hold}d"
            alpha_col = f"alpha_{hold}d"
            r = sub[ret_col].dropna()
            a = sub[alpha_col].dropna()
            n = len(r)
            if n == 0:
                return {"n": 0}
            mean_ret   = round(r.mean(), 2)
            mean_alpha = round(a.mean(), 2) if len(a) else None
            win_rate   = round((r > 0).mean() * 100, 1)
            sharpe     = round(r.mean() / r.std() * (252 / hold) ** 0.5, 2) if r.std() > 0 else None
            cum        = (1 + r / 100).cumprod()
            mdd        = round(((cum - cum.cummax()) / cum.cummax() * 100).min(), 2)
            return {
                "n":          n,
                "mean_ret":   mean_ret,
                "mean_alpha": mean_alpha,
                "win_rate":   win_rate,
                "sharpe":     sharpe,
                "mdd":        mdd,
            }

        # ── 彙總表：V1 / V2-pass / V2-fail ──────────────────────
        groups = {
            "V1 全集":   detail,
            "V2 通過":   detail[detail["v2_pass"]],
            "V2 篩掉":   detail[~detail["v2_pass"]],
        }
        summary_rows = []
        for label, sub in groups.items():
            s20 = _group_stats(sub, 20)
            s60 = _group_stats(sub, 60)
            summary_rows.append({
                "策略":        label,
                "樣本數":      s20.get("n", 0),
                "20D均報酬%":  s20.get("mean_ret"),
                "20D Alpha%":  s20.get("mean_alpha"),
                "20D勝率%":    s20.get("win_rate"),
                "20D Sharpe":  s20.get("sharpe"),
                "20D MDD%":    s20.get("mdd"),
                "60D均報酬%":  s60.get("mean_ret"),
                "60D Alpha%":  s60.get("mean_alpha"),
                "60D勝率%":    s60.get("win_rate"),
                "60D Sharpe":  s60.get("sharpe"),
                "60D MDD%":    s60.get("mdd"),
            })
        summary_df = pd.DataFrame(summary_rows)

        # ── 按 setup_type 分組 ──────────────────────────────────
        setup_rows = []
        for setup_val, sub in detail.groupby("setup"):
            s20 = _group_stats(sub, 20)
            s60 = _group_stats(sub, 60)
            setup_rows.append({
                "Setup":       setup_val,
                "樣本數":      s20.get("n", 0),
                "20D均報酬%":  s20.get("mean_ret"),
                "20D勝率%":    s20.get("win_rate"),
                "20D Sharpe":  s20.get("sharpe"),
                "20D MDD%":    s20.get("mdd"),
                "60D均報酬%":  s60.get("mean_ret"),
                "60D勝率%":    s60.get("win_rate"),
                "60D Sharpe":  s60.get("sharpe"),
            })
        by_setup_df = pd.DataFrame(setup_rows).sort_values("20D均報酬%", ascending=False)

        # ── 按乖離率分組 ────────────────────────────────────────
        dev_order = ["< 0%", "0–3%", "3–5%", "5–8%", "8–12%", "≥12%", "—"]
        dev_rows = []
        for bracket, sub in detail.groupby("dev_bracket"):
            s20 = _group_stats(sub, 20)
            s60 = _group_stats(sub, 60)
            dev_rows.append({
                "MA20 乖離":   bracket,
                "樣本數":      s20.get("n", 0),
                "20D均報酬%":  s20.get("mean_ret"),
                "20D勝率%":    s20.get("win_rate"),
                "20D Sharpe":  s20.get("sharpe"),
                "20D MDD%":    s20.get("mdd"),
                "60D均報酬%":  s60.get("mean_ret"),
                "60D勝率%":    s60.get("win_rate"),
            })
        by_dev_df = (
            pd.DataFrame(dev_rows)
            .assign(_order=lambda df: df["MA20 乖離"].map(
                {v: i for i, v in enumerate(dev_order)}
            ))
            .sort_values("_order")
            .drop(columns="_order")
            .reset_index(drop=True)
        )

        # ── MA60 支撐距離驗證（數據驗證是否值得升為 BUY）──────────
        bracket_order_ma60 = ["≤1%", "1–2%", "2–3%", "3–5%"]
        ma60_candidates = detail[detail["ma60_bracket"].notna()].copy()
        ma60_rows = []
        for bracket in bracket_order_ma60:
            sub = ma60_candidates[ma60_candidates["ma60_bracket"] == bracket]
            if len(sub) == 0:
                continue
            s20 = _group_stats(sub, 20)
            s60 = _group_stats(sub, 60)
            ma60_rows.append({
                "MA60 距離":   bracket,
                "樣本數":      s20.get("n", 0),
                "20D均報酬%":  s20.get("mean_ret"),
                "20D Alpha%":  s20.get("mean_alpha"),
                "20D勝率%":    s20.get("win_rate"),
                "20D Sharpe":  s20.get("sharpe"),
                "20D MDD%":    s20.get("mdd"),
                "60D均報酬%":  s60.get("mean_ret"),
                "60D Alpha%":  s60.get("mean_alpha"),
                "60D勝率%":    s60.get("win_rate"),
                "60D Sharpe":  s60.get("sharpe"),
            })
        # 全部候選合計 + V1 基準對照
        if not ma60_candidates.empty:
            for label, sub in [("全部 MA60 候選 ≤5%", ma60_candidates),
                                ("V1 全集（對照）", detail)]:
                s20 = _group_stats(sub, 20)
                s60 = _group_stats(sub, 60)
                ma60_rows.append({
                    "MA60 距離":   label,
                    "樣本數":      s20.get("n", 0),
                    "20D均報酬%":  s20.get("mean_ret"),
                    "20D Alpha%":  s20.get("mean_alpha"),
                    "20D勝率%":    s20.get("win_rate"),
                    "20D Sharpe":  s20.get("sharpe"),
                    "20D MDD%":    s20.get("mdd"),
                    "60D均報酬%":  s60.get("mean_ret"),
                    "60D Alpha%":  s60.get("mean_alpha"),
                    "60D勝率%":    s60.get("win_rate"),
                    "60D Sharpe":  s60.get("sharpe"),
                })
        by_ma60_df = pd.DataFrame(ma60_rows)

        return {
            "summary":      summary_df,
            "by_setup":     by_setup_df,
            "by_deviation": by_dev_df,
            "by_ma60_gap":  by_ma60_df,
            "detail":       detail,
        }
