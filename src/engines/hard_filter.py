"""
hard_filter.py — 硬性篩選（PRD Chapter 4.3）

第一層篩選：淘汰明顯不符合長期投資條件的公司。
所有條件皆可調整（見 config.py HARD_FILTER）。
未通過者不進入後續分析。
"""

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional, Tuple

import pandas as pd

from config import HARD_FILTER, EXCLUDE_KEYWORDS

logger = logging.getLogger(__name__)


@dataclass
class FilterResult:
    """篩選結果"""
    stock_id:    str
    passed:      bool
    fail_reason: str = ""
    checks:      dict = field(default_factory=dict)


class HardFilter:
    """
    硬性篩選引擎。

    篩選條件（依 PRD Chapter 4.3）：
    公司基本條件：上市年數、市值、資本額、日成交金額
    財務條件：EPS > 0、ROE ≥ 15%、ROA ≥ 8%、負債比 ≤ 60%
    成長條件：近 3-5 年趨勢
    排除條件：全額交割、財務異常等
    """

    def __init__(self, config: dict = None):
        self.cfg = config or HARD_FILTER

    # 金融業關鍵字（銀行、保險、證券、金控負債比結構性偏高，ROA 較低）
    _FINANCE_KEYWORDS = ("銀行", "保險", "證券", "金控", "票券", "金融", "壽險", "產險")

    def filter_stock(
        self,
        stock_id:     str,
        listing_date: Optional[date] = None,
        market_cap_b: Optional[float] = None,   # 億元
        capital_b:    Optional[float] = None,    # 億元
        avg_daily_amt_m: Optional[float] = None, # 百萬元
        eps_ttm:      Optional[float] = None,
        roe_avg:      Optional[float] = None,    # %
        roa_avg:      Optional[float] = None,    # %
        debt_ratio:   Optional[float] = None,    # %
        eps_trend:    str = "unknown",
        revenue_trend: str = "unknown",
        is_full_cash_delivery: bool = False,     # 全額交割股
        has_major_violation: bool = False,       # 重大違法
        name:         str = "",
        industry:     str = "",
    ) -> FilterResult:
        """
        對單一股票執行硬性篩選。
        回傳 FilterResult（passed=True/False, fail_reason）
        """
        checks = {}

        # ── 排除條件 ──────────────────────────────────────────
        if is_full_cash_delivery:
            return FilterResult(stock_id, False, "全額交割股", checks)

        if has_major_violation:
            return FilterResult(stock_id, False, "重大違法或風險事件", checks)

        # 排除 ETF、權證等
        if name and any(kw in name.upper() for kw in EXCLUDE_KEYWORDS):
            return FilterResult(stock_id, False, f"排除標的類型（{name}）", checks)

        # ── 公司基本條件 ──────────────────────────────────────
        # 上市年數
        if listing_date is not None:
            years = (date.today() - listing_date).days / 365.25
            ok = years >= self.cfg["min_listing_years"]
            checks["listing_years"] = (ok, f"{years:.1f} 年")
            if not ok:
                return FilterResult(stock_id, False, f"上市未滿 {self.cfg['min_listing_years']} 年（{years:.1f}年）", checks)

        # 市值
        if market_cap_b is not None:
            ok = market_cap_b >= self.cfg["min_market_cap_b"]
            checks["market_cap"] = (ok, f"{market_cap_b:.1f} 億")
            if not ok:
                return FilterResult(stock_id, False, f"市值不足（{market_cap_b:.1f} 億 < {self.cfg['min_market_cap_b']} 億）", checks)

        # 資本額
        if capital_b is not None:
            ok = capital_b >= self.cfg["min_capital_b"]
            checks["capital"] = (ok, f"{capital_b:.1f} 億")
            if not ok:
                return FilterResult(stock_id, False, f"資本額不足（{capital_b:.1f} 億 < {self.cfg['min_capital_b']} 億）", checks)

        # 平均日成交金額
        if avg_daily_amt_m is not None:
            ok = avg_daily_amt_m >= self.cfg["min_avg_daily_amt_m"]
            checks["avg_daily_amt"] = (ok, f"{avg_daily_amt_m:.1f}M")
            if not ok:
                return FilterResult(stock_id, False, f"流動性不足（日均成交 {avg_daily_amt_m:.1f}M < {self.cfg['min_avg_daily_amt_m']}M）", checks)

        # ── 產業別閾值（金融業結構性負債高、ROA 較低，採放寬標準）──────
        is_finance = any(kw in (industry + name) for kw in self._FINANCE_KEYWORDS)
        min_roe       = 8.0  if is_finance else self.cfg["min_roe"]
        min_roa       = 0.5  if is_finance else self.cfg["min_roa"]
        max_debt      = 95.0 if is_finance else self.cfg["max_debt_ratio"]

        # ── 財務條件 ──────────────────────────────────────────
        if eps_ttm is not None:
            ok = eps_ttm > self.cfg["min_ttm_eps"]
            checks["eps_ttm"] = (ok, f"TTM EPS={eps_ttm:.2f}")
            if not ok:
                return FilterResult(stock_id, False, f"TTM EPS ≤ 0（虧損，EPS={eps_ttm:.2f}）", checks)

        if roe_avg is not None:
            ok = roe_avg >= min_roe
            checks["roe"] = (ok, f"ROE={roe_avg:.1f}%")
            if not ok:
                label = "（金融業）" if is_finance else ""
                return FilterResult(stock_id, False, f"ROE 不足{label}（{roe_avg:.1f}% < {min_roe}%）", checks)

        if roa_avg is not None:
            ok = roa_avg >= min_roa
            checks["roa"] = (ok, f"ROA={roa_avg:.1f}%")
            if not ok:
                label = "（金融業）" if is_finance else ""
                return FilterResult(stock_id, False, f"ROA 不足{label}（{roa_avg:.1f}% < {min_roa}%）", checks)

        if debt_ratio is not None:
            ok = debt_ratio <= max_debt
            checks["debt_ratio"] = (ok, f"負債比={debt_ratio:.1f}%")
            if not ok:
                return FilterResult(stock_id, False, f"負債比過高（{debt_ratio:.1f}% > {max_debt}%）", checks)

        # ── 成長趨勢 ──────────────────────────────────────────
        if eps_trend == "down":
            return FilterResult(stock_id, False, "EPS 近期持續衰退", checks)

        if revenue_trend == "down":
            return FilterResult(stock_id, False, "營收近期持續衰退", checks)

        # ✅ 通過全部篩選
        return FilterResult(stock_id, True, "", checks)


def run_hard_filter(
    price_df:    pd.DataFrame,
    stock_info:  dict,    # {stock_id: {market_cap_b, capital_b, listing_date, ...}}
    fin_summary: dict,    # {stock_id: financial_summary dict}
    config:      dict = None,
) -> Tuple[List[str], List[FilterResult]]:
    """
    批次執行硬性篩選。
    回傳 (通過名單, 所有篩選結果列表)
    """
    hf = HardFilter(config)
    passed = []
    all_results = []

    # 計算各股平均日成交金額（近20日）
    if "amount" in price_df.columns and "stock_id" in price_df.columns:
        avg_amt = (
            price_df.sort_values("date")
            .groupby("stock_id")["amount"]
            .apply(lambda x: x.tail(20).mean())
            .to_dict()
        )
    else:
        avg_amt = {}

    total = len(price_df["stock_id"].unique()) if "stock_id" in price_df.columns else 0
    logger.info(f"Running Hard Filter on {total} stocks...")

    stocks_to_filter = price_df["stock_id"].unique() if "stock_id" in price_df.columns else []

    for sid in stocks_to_filter:
        info = stock_info.get(sid, {})
        fin  = fin_summary.get(sid, {})

        r = hf.filter_stock(
            stock_id     = sid,
            name         = info.get("name", ""),
            industry     = info.get("industry", ""),
            listing_date = info.get("listing_date"),
            market_cap_b = info.get("market_cap_b"),
            capital_b    = info.get("capital_b"),
            avg_daily_amt_m = avg_amt.get(sid),
            eps_ttm      = fin.get("eps_ttm"),
            roe_avg      = fin.get("roe_avg"),
            roa_avg      = fin.get("roa_avg"),
            debt_ratio   = fin.get("debt_ratio"),
            eps_trend    = fin.get("eps_trend", "unknown"),
            revenue_trend = fin.get("revenue_trend", "unknown"),
        )
        all_results.append(r)
        if r.passed:
            passed.append(sid)

    qualified = len(passed)
    logger.info(f"Hard Filter: {qualified}/{total} stocks passed.")

    # 記錄部分失敗原因供分析
    if all_results:
        fail_reasons = {}
        for r in all_results:
            if not r.passed:
                reason = r.fail_reason.split("（")[0].split("不足")[0].strip()
                fail_reasons[reason] = fail_reasons.get(reason, 0) + 1
        top_fails = sorted(fail_reasons.items(), key=lambda x: -x[1])[:5]
        logger.info(f"Top fail reasons: {top_fails}")

    return passed, all_results
