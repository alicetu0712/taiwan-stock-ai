"""
financial_collector.py — 財務資料蒐集

資料來源：FinMind API（需要 Token）
蒐集：季度財報（EPS、ROE、ROA、毛利率等）、月營收

若無 FinMind Token，系統會跳過基本面分析並記錄警告。
"""

import logging
from datetime import date, datetime
from typing import Optional

import pandas as pd

from config import FINMIND_TOKEN

logger = logging.getLogger(__name__)


def _get_dataloader():
    """建立 FinMind DataLoader 並登入。"""
    try:
        from FinMind.data import DataLoader
        dl = DataLoader()
        if FINMIND_TOKEN:
            dl.login_by_token(api_token=FINMIND_TOKEN)
        return dl
    except ImportError:
        logger.warning("FinMind package not installed. Run: pip install FinMind")
        return None
    except Exception as e:
        logger.warning(f"FinMind login failed: {e}")
        return None


def fetch_monthly_revenue(
    stock_id: str,
    start_date: str = "2020-01-01",
) -> pd.DataFrame:
    """
    取得月營收資料。
    回傳欄位：stock_id, year, month, revenue（百萬）, yoy_growth（%）
    """
    dl = _get_dataloader()
    if dl is None:
        return pd.DataFrame()
    try:
        df = dl.taiwan_stock_month_revenue(
            stock_id=stock_id,
            start_date=start_date,
        )
        if df.empty:
            return pd.DataFrame()

        df = df.rename(columns={
            "stock_id": "stock_id",
            "revenue": "revenue",
            "revenue_year": "year",
            "revenue_month": "month",
        })

        # 計算 YoY
        df = df.sort_values(["year", "month"]).reset_index(drop=True)
        df["yoy_growth"] = df["revenue"].pct_change(12) * 100

        df["stock_id"] = stock_id
        df["revenue"]  = df["revenue"] / 1_000     # 轉換為百萬元

        cols = [c for c in ["stock_id", "year", "month", "revenue", "yoy_growth"] if c in df.columns]
        return df[cols].dropna(subset=["revenue"])

    except Exception as e:
        logger.warning(f"Monthly revenue fetch failed ({stock_id}): {e}")
        return pd.DataFrame()


def fetch_financial_statements(
    stock_id: str,
    start_date: str = "2018-01-01",
) -> pd.DataFrame:
    """
    取得季度財務報表（毛利率、營業利益率、淨利率等）。
    回傳欄位：stock_id, year, quarter, gross_margin, op_margin, net_margin
    """
    dl = _get_dataloader()
    if dl is None:
        return pd.DataFrame()
    try:
        df = dl.taiwan_stock_financial_statement(
            stock_id=stock_id,
            start_date=start_date,
        )
        if df.empty:
            return pd.DataFrame()

        # FinMind 財報欄位依版本可能不同，做彈性處理
        df["stock_id"] = stock_id
        result_rows = []

        for _, row in df.iterrows():
            t = str(row.get("type", ""))
            val = row.get("value", None)
            date_str = str(row.get("date", ""))
            try:
                year    = int(date_str[:4])
                quarter = _date_to_quarter(date_str)
            except Exception:
                continue
            result_rows.append({
                "stock_id": stock_id,
                "year":     year,
                "quarter":  quarter,
                "type":     t,
                "value":    val,
            })

        if not result_rows:
            return pd.DataFrame()

        df_long = pd.DataFrame(result_rows)
        # Pivot 轉寬格式
        df_wide = df_long.pivot_table(
            index=["stock_id", "year", "quarter"],
            columns="type",
            values="value",
            aggfunc="last",
        ).reset_index()
        df_wide.columns.name = None
        return df_wide

    except Exception as e:
        logger.warning(f"Financial statements fetch failed ({stock_id}): {e}")
        return pd.DataFrame()


def fetch_profitability(
    stock_id: str,
    start_date: str = "2018-01-01",
) -> pd.DataFrame:
    """
    取得季度獲利能力指標（EPS、ROE、ROA 等）。
    """
    dl = _get_dataloader()
    if dl is None:
        return pd.DataFrame()
    try:
        df = dl.taiwan_stock_per_pbr_detail(
            stock_id=stock_id,
            start_date=start_date,
        )
        if df.empty:
            # 嘗試備用 API
            return _fetch_profitability_fallback(stock_id, start_date)

        df["stock_id"] = stock_id
        df["date"] = pd.to_datetime(df.get("date", df.index))
        df["year"]    = df["date"].dt.year
        df["quarter"] = df["date"].dt.month.map({1:1, 2:1, 3:1, 4:2, 5:2, 6:2, 7:3, 8:3, 9:3, 10:4, 11:4, 12:4})

        return df

    except Exception as e:
        logger.warning(f"Profitability fetch failed ({stock_id}): {e}")
        return _fetch_profitability_fallback(stock_id, start_date)


def _fetch_profitability_fallback(stock_id: str, start_date: str) -> pd.DataFrame:
    """備用：嘗試 FinMind 另一個 API 取 ROE/ROA。"""
    dl = _get_dataloader()
    if dl is None:
        return pd.DataFrame()
    try:
        df = dl.taiwan_stock_balance_sheet(
            stock_id=stock_id,
            start_date=start_date,
        )
        if df.empty:
            return pd.DataFrame()
        df["stock_id"] = stock_id
        return df
    except Exception as e:
        logger.debug(f"Profitability fallback also failed ({stock_id}): {e}")
        return pd.DataFrame()


def fetch_eps_history(
    stock_id: str,
    start_date: str = "2018-01-01",
) -> pd.DataFrame:
    """
    取得季度 EPS。
    回傳欄位：stock_id, year, quarter, eps
    """
    dl = _get_dataloader()
    if dl is None:
        return pd.DataFrame()
    try:
        df = dl.taiwan_stock_financial_statement(
            stock_id=stock_id,
            start_date=start_date,
        )
        if df.empty:
            return pd.DataFrame()

        eps_rows = df[df["type"].str.contains("EPS|每股盈餘", na=False, case=False)].copy()
        if eps_rows.empty:
            return pd.DataFrame()

        eps_rows["stock_id"] = stock_id
        eps_rows["year"]     = pd.to_datetime(eps_rows["date"]).dt.year
        eps_rows["quarter"]  = pd.to_datetime(eps_rows["date"]).dt.month.map(
            {1:1, 2:1, 3:1, 4:2, 5:2, 6:2, 7:3, 8:3, 9:3, 10:4, 11:4, 12:4}
        )
        eps_rows = eps_rows.rename(columns={"value": "eps"})
        return eps_rows[["stock_id", "year", "quarter", "eps"]].dropna()

    except Exception as e:
        logger.warning(f"EPS fetch failed ({stock_id}): {e}")
        return pd.DataFrame()


def build_financial_summary(
    stock_id: str,
    n_years: int = 5,
    as_of_date=None,
) -> dict:
    """
    整合所有財務指標，回傳供基本面分析用的 dict。
    包含：eps_ttm, roe_avg, roa_avg, gross_margin_avg, debt_ratio, 趨勢判斷

    資料優先順序：
      1. 本地 DB（由 scripts/import_financials.py 從 goodinfo.tw 預先填入）
      2. FinMind API（需要 FINMIND_TOKEN，且 FinMind Python library 在 macOS 可能 segfault）
    """
    # ── 優先從本地 DB 讀取（goodinfo.tw 已匯入的年度資料）────
    db_summary = _build_summary_from_db(stock_id, as_of_date=as_of_date)
    if db_summary.get("has_data"):
        return db_summary

    cutoff = as_of_date or date.today()
    start = f"{cutoff.year - n_years - 1}-01-01"
    summary = {
        "stock_id":        stock_id,
        "has_data":        False,
        "eps_ttm":         None,
        "eps_5y":          [],
        "roe_avg":         None,
        "roa_avg":         None,
        "gross_margin_avg": None,
        "debt_ratio":      None,
        "revenue_yoy_avg": None,
        "revenue_trend":   "unknown",
        "eps_trend":       "unknown",
        "roe_trend":       "unknown",
    }

    if not FINMIND_TOKEN:
        logger.debug(f"No FinMind token and no DB data; skipping financial summary for {stock_id}.")
        return summary

    # --- 月營收 ---
    rev_df = fetch_monthly_revenue(stock_id, start)
    if not rev_df.empty and "yoy_growth" in rev_df.columns:
        recent = rev_df.tail(12)
        summary["revenue_yoy_avg"] = recent["yoy_growth"].mean()
        trend = _calc_trend(rev_df["revenue"].tolist())
        summary["revenue_trend"] = trend
        summary["has_data"] = True

    # --- EPS（季報公告截止：Q1=5/15, Q2=8/14, Q3=11/14, Q4=3/31 隔年）---
    eps_df = fetch_eps_history(stock_id, start)
    if not eps_df.empty:
        # 過濾未來資料：只保留截至 as_of_date 已可公告的季度
        def _is_available(row) -> bool:
            y, q = int(row["year"]), int(row["quarter"])
            cutoff_d = cutoff
            deadlines = {1: (y, 5, 15), 2: (y, 8, 14), 3: (y, 11, 14), 4: (y+1, 3, 31)}
            dl = deadlines.get(q)
            if not dl:
                return False
            from datetime import date as _d
            return cutoff_d >= _d(*dl)
        eps_df = eps_df[eps_df.apply(_is_available, axis=1)]
        eps_list = eps_df.sort_values(["year", "quarter"])["eps"].tolist()
        summary["eps_5y"] = eps_list[-20:]
        # TTM EPS = 最近四季之和
        if len(eps_list) >= 4:
            summary["eps_ttm"] = sum(eps_list[-4:])
        trend = _calc_trend(eps_list)
        summary["eps_trend"] = trend
        summary["has_data"] = True

    return summary


def _calc_trend(series: list) -> str:
    """簡單線性趨勢判斷：取最後 N 點。"""
    if len(series) < 4:
        return "unknown"
    import numpy as np
    try:
        values = [v for v in series if v is not None and not pd.isna(v)]
        if len(values) < 4:
            return "unknown"
        recent = values[-min(12, len(values)):]
        x = list(range(len(recent)))
        slope = np.polyfit(x, recent, 1)[0]
        mean_val = abs(sum(recent) / len(recent))
        if mean_val < 1e-6:
            return "stable"
        rel_slope = slope / mean_val
        if rel_slope > 0.03:
            return "up"
        elif rel_slope < -0.03:
            return "down"
        else:
            return "stable"
    except Exception:
        return "unknown"


def _date_to_quarter(date_str: str) -> int:
    try:
        m = int(date_str[5:7])
        return (m - 1) // 3 + 1
    except Exception:
        return 1


def _build_summary_from_db(stock_id: str, as_of_date=None) -> dict:
    """
    從本地 financial_quarters 表讀取 goodinfo.tw 匯入的年度資料（quarter=0），
    組成 FundamentalAnalyzer 所需的 fin_summary dict。
    """
    from src.collectors.goodinfo_collector import build_financial_summary_from_db
    from config import DB_PATH
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    _empty = {"stock_id": stock_id, "has_data": False}

    try:
        _engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
        _Session = sessionmaker(bind=_engine)
        _session = _Session()
        try:
            return build_financial_summary_from_db(stock_id, _session, as_of_date=as_of_date)
        finally:
            _session.close()
    except Exception as e:
        logger.debug(f"DB summary failed for {stock_id}: {e}")
        return _empty
