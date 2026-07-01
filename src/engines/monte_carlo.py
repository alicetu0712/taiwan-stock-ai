"""
monte_carlo.py — 蒙地卡羅價格路徑模擬

用歷史日報酬率分布，模擬未來 N 日的 M 條價格路徑。
輸出：目標價達成機率、停損觸發機率、預期報酬分布。
"""

import logging
import numpy as np
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class MonteCarloResult:
    stock_id: str
    entry_price: float
    target_price: float
    stop_loss_price: float
    sim_days: int
    n_paths: int

    # 機率
    prob_target: float       # 達到目標價的機率
    prob_stop_loss: float    # 觸及停損的機率
    prob_neutral: float      # 兩者都沒觸及

    # 期末分布（第 sim_days 日）
    median_price: float
    pct_5: float             # 5th percentile（壞情況）
    pct_25: float
    pct_75: float
    pct_95: float            # 95th percentile（好情況）
    expected_pnl_pct: float  # 期望報酬%

    # 路徑資料（供繪圖用，最多 50 條採樣）
    sample_paths: list        # list of list[float]（每條路徑每日價格）
    days: list                # [0, 1, 2, ..., sim_days]


def simulate(
    stock_id: str,
    entry_price: float,
    target_price: float,
    stop_loss_price: float,
    daily_returns: list,        # 歷史日報酬率序列（float list，e.g. [0.01, -0.02, ...]）
    sim_days: int = 20,
    n_paths: int = 1000,
    sample_n: int = 50,         # 繪圖用採樣路徑數
) -> Optional[MonteCarloResult]:
    """
    執行蒙地卡羅模擬。

    Args:
        daily_returns: 歷史日報酬率（至少需要 30 筆）
    Returns:
        MonteCarloResult 或 None（資料不足時）
    """
    if len(daily_returns) < 30:
        logger.warning(f"{stock_id}: 歷史報酬率不足 30 筆，無法模擬")
        return None

    rets = np.array(daily_returns, dtype=float)
    mu  = float(np.mean(rets))
    sig = float(np.std(rets))

    if sig == 0:
        logger.warning(f"{stock_id}: 報酬率標準差為 0")
        return None

    # 模擬 n_paths 條路徑
    rng = np.random.default_rng(seed=42)
    simulated = rng.normal(loc=mu, scale=sig, size=(n_paths, sim_days))

    # 每條路徑的累積價格
    # price[t] = entry_price × ∏(1 + r_i) for i in 0..t
    cum_ret = np.cumprod(1 + simulated, axis=1)   # shape: (n_paths, sim_days)
    prices  = entry_price * cum_ret                # shape: (n_paths, sim_days)

    # 是否在路徑中任何一天觸及目標/停損
    hit_target    = np.any(prices >= target_price,    axis=1)  # (n_paths,)
    hit_stop_loss = np.any(prices <= stop_loss_price, axis=1)

    # 同時觸及時，以先觸及的為準（簡化：假設目標優先）
    prob_target    = float(np.mean(hit_target & ~hit_stop_loss) +
                           np.mean(hit_target & hit_stop_loss) * 0.5)
    prob_stop_loss = float(np.mean(hit_stop_loss & ~hit_target) +
                           np.mean(hit_target & hit_stop_loss) * 0.5)
    prob_neutral   = max(0.0, 1.0 - prob_target - prob_stop_loss)

    # 期末價格分布
    final_prices = prices[:, -1]
    median_price = float(np.median(final_prices))
    pct_5        = float(np.percentile(final_prices, 5))
    pct_25       = float(np.percentile(final_prices, 25))
    pct_75       = float(np.percentile(final_prices, 75))
    pct_95       = float(np.percentile(final_prices, 95))
    expected_pnl = float((np.mean(final_prices) - entry_price) / entry_price * 100)

    # 採樣路徑（供繪圖）
    idx = rng.choice(n_paths, size=min(sample_n, n_paths), replace=False)
    days_list = list(range(sim_days + 1))
    sample_paths = []
    for i in idx:
        path = [entry_price] + list(prices[i].tolist())
        sample_paths.append(path)

    return MonteCarloResult(
        stock_id=stock_id,
        entry_price=entry_price,
        target_price=target_price,
        stop_loss_price=stop_loss_price,
        sim_days=sim_days,
        n_paths=n_paths,
        prob_target=round(prob_target * 100, 1),
        prob_stop_loss=round(prob_stop_loss * 100, 1),
        prob_neutral=round(prob_neutral * 100, 1),
        median_price=round(median_price, 2),
        pct_5=round(pct_5, 2),
        pct_25=round(pct_25, 2),
        pct_75=round(pct_75, 2),
        pct_95=round(pct_95, 2),
        expected_pnl_pct=round(expected_pnl, 2),
        sample_paths=sample_paths,
        days=days_list,
    )
