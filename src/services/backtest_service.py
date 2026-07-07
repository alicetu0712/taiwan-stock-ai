"""
backtest_service.py — 回測計算服務層

純 Python 業務邏輯，無 Streamlit 依賴。
dashboard/pages/backtest.py 的 @st.cache_data 函數委託此 Service。
"""

import logging
from collections import defaultdict
from datetime import date

import pandas as pd

logger = logging.getLogger(__name__)

ROUND_TRIP_COST = 0.585  # 買進+賣出合計交易成本（%）


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
