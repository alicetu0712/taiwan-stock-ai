"""
goodinfo_collector.py — goodinfo.tw 財務資料收集器

資料來源：goodinfo.tw（免費，無需 token，純 HTML 解析）
蒐集：年度 EPS、ROE、ROA、毛利率、營益率、淨利率、目前 PER/PBR
URL：StockBzPerformance.asp?STOCK_ID={stock_id}
"""

import logging
import re
import time
import random
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_BASE = "https://goodinfo.tw/tw"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "zh-TW,zh;q=0.9",
    "Referer": f"{_BASE}/index.asp",
}
_TIMEOUT = 20
_MAX_YEARS = 7


def _parse_num(s) -> Optional[float]:
    if s is None:
        return None
    s = re.sub(r"\(年化\)", "", str(s))
    s = re.sub(r"[^\d.\-+]", "", s.replace(",", "")).strip()
    if not s or s in ("-", "+", "."):
        return None
    try:
        v = float(s)
        return v if abs(v) < 1e9 else None
    except ValueError:
        return None


def _cells(row_html: str) -> list:
    """從 <tr> HTML 取出各 <td> 的純文字內容（strip HTML tags）。"""
    tds = re.findall(r"<td[^>]*>(.*?)</td>", row_html, re.DOTALL | re.IGNORECASE)
    result = []
    for td in tds:
        text = re.sub(r"<[^>]+>", " ", td)
        text = re.sub(r"\s+", " ", text).strip()
        result.append(text)
    return result


def fetch_annual_performance(stock_id: str) -> list:
    """
    抓取 goodinfo.tw 年度財務績效。

    回傳 list of dict，每筆代表一個年度：
      year, eps, roe, roa, gross_margin, op_margin, net_margin, per, pbr
    最多 _MAX_YEARS 筆，只含年度列（跳過季度列如 "26Q1"）。
    """
    url = f"{_BASE}/StockBzPerformance.asp?STOCK_ID={stock_id}"
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
        html = resp.content.decode("utf-8", errors="replace")  # 強制 UTF-8，避免 requests 誤判 ISO-8859-1
    except Exception as e:
        logger.warning(f"[goodinfo] {stock_id} 請求失敗：{e}")
        return []

    # 找年度財務績效表：含 EPS、ROE、ROA 且列數 > 20（Table 7，40列）
    # 注意：goodinfo 表頭欄位名為 "ROA (%)"，不是 "毛利率"
    tables = re.findall(r"<table[^>]*>(.*?)</table>", html, re.DOTALL | re.IGNORECASE)
    perf_table = None
    for t in tables:
        if "EPS" in t and "ROE" in t and "ROA" in t:
            rows_check = re.findall(r"<tr", t, re.IGNORECASE)
            if len(rows_check) > 20:
                perf_table = t
                break

    if perf_table is None:
        logger.warning(f"[goodinfo] {stock_id}：找不到績效表")
        return []

    # 解析目前 PER / PBR（從包含 "PBR" 欄位的另一個表格）
    current_per, current_pbr = None, None
    for t in tables:
        if "PER" in t and "PBR" in t and "PEG" in t:
            rows = re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.DOTALL)
            for row in rows:
                c = _cells(row)
                if len(c) >= 7:
                    pbr_val = _parse_num(c[5])
                    per_val = _parse_num(c[6])
                    if per_val and 0 < per_val < 500 and pbr_val and 0 < pbr_val < 100:
                        current_per = per_val
                        current_pbr = pbr_val
                        break
            break

    # 逐列解析年度財務資料
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", perf_table, re.DOTALL)
    results = []
    latest_year = True  # 第一筆年度列視為最新年度，補上 PER/PBR

    for row in rows:
        c = _cells(row)
        if len(c) < 19:
            continue

        year_str = c[0].strip()
        # 只處理純年度列（"2025", "2024"…），跳過季度（"26Q1"）和表頭
        if not re.match(r"^\d{4}$", year_str):
            continue

        year = int(year_str)
        if year < 2015:
            continue

        # 欄位對應（索引依 goodinfo 實際 <td> 順序）：
        # c[0]=年度  c[7]=營收  c[12]=毛利率  c[13]=營益率  c[15]=淨利率
        # c[16]=ROE  c[17]=ROA  c[18]=EPS
        record = {
            "year":         year,
            "eps":          _parse_num(c[18]),
            "roe":          _parse_num(c[16]),
            "roa":          _parse_num(c[17]),
            "gross_margin": _parse_num(c[12]),
            "op_margin":    _parse_num(c[13]),
            "net_margin":   _parse_num(c[15]),
            "per":          current_per if latest_year else None,
            "pbr":          current_pbr if latest_year else None,
        }
        latest_year = False

        if record["eps"] is not None:
            results.append(record)

        if len(results) >= _MAX_YEARS:
            break

    logger.debug(f"[goodinfo] {stock_id}：取得 {len(results)} 筆年度資料")
    return results


def build_financial_summary_from_db(stock_id: str, session, as_of_date=None) -> dict:
    """
    從本地 financial_quarters 表（quarter=0 為年度資料）
    組成 FundamentalAnalyzer.analyze() 所需的 fin_summary dict。

    呼叫前需確認 import_financials.py 已執行過，DB 有資料。
    """
    import numpy as np
    from src.database import FinancialQuarter

    _empty = {
        "stock_id": stock_id, "has_data": False,
        "eps_ttm": None, "eps_5y": [], "eps_trend": "unknown",
        "roe_avg": None, "roe_5y": [],
        "roa_avg": None,
        "gross_margin_avg": None,
        "debt_ratio": None, "free_cash_flow": None, "current_ratio": None,
        "per": None, "pbr": None,
        "revenue_trend": "unknown", "revenue_yoy_avg": None,
    }

    q = session.query(FinancialQuarter).filter_by(stock_id=stock_id, quarter=0)
    if as_of_date is not None:
        # 年報申報期限：當年度（Y）年報最晚於 Y+1 年 4 月 1 日公告
        # 只使用截至 as_of_date 已可公開的年度資料
        from datetime import date as _date
        d = as_of_date if isinstance(as_of_date, _date) else _date.fromisoformat(str(as_of_date))
        max_available_year = (d.year - 1) if d.month < 4 else d.year - 1
        q = q.filter(FinancialQuarter.year <= max_available_year)
    rows = q.order_by(FinancialQuarter.year.desc()).limit(_MAX_YEARS).all()

    if not rows:
        return _empty

    def _avg(vals):
        clean = [v for v in vals if v is not None]
        return round(sum(clean) / len(clean), 2) if clean else None

    def _trend(vals):
        clean = [v for v in vals if v is not None]
        if len(clean) < 3:
            return "unknown"
        x = list(range(len(clean)))
        slope = np.polyfit(x, clean, 1)[0]
        mean_v = abs(sum(clean) / len(clean))
        if mean_v < 1e-6:
            return "stable"
        rel = slope / mean_v
        if rel > 0.03:
            return "up"
        if rel < -0.03:
            return "down"
        return "stable"

    # rows 已按 year desc 排序；reversed() 得到 oldest→newest 順序
    eps_asc = [r.eps for r in reversed(rows)]
    roe_asc = [r.roe for r in reversed(rows)]

    return {
        "stock_id":         stock_id,
        "has_data":         True,
        "eps_ttm":          rows[0].eps,
        "eps_5y":           eps_asc[-5:],
        "eps_trend":        _trend(eps_asc),
        "roe_avg":          _avg([r.roe for r in rows[:5]]),
        "roe_5y":           roe_asc[-5:],
        "roa_avg":          _avg([r.roa for r in rows[:5]]),
        "gross_margin_avg": _avg([r.gross_margin for r in rows[:5]]),
        "debt_ratio":       rows[0].debt_ratio,
        "free_cash_flow":   rows[0].free_cash_flow,
        "current_ratio":    rows[0].current_ratio,
        "per":              rows[0].per,
        "pbr":              rows[0].pbr,
        "revenue_trend":    "unknown",
        "revenue_yoy_avg":  None,
    }
