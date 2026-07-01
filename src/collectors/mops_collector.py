"""
mops_collector.py — 公開資訊觀測站 (MOPS) 財務資料收集器

資料來源：https://mops.twse.com.tw/mops/api/
  t164sb04 — 合併綜合損益表（EPS、毛利率、營益率、淨利率）
  t164sb03 — 合併資產負債表（總資產、負債、權益、流動比率）

特點：官方 API，無 IP 封鎖，所有上市/上櫃公司均有資料。
     ROE/ROA 由損益表+資產負債表計算得出。
"""

import logging
import time
import random
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_BASE    = "https://mops.twse.com.tw/mops/api/"
_HEADERS = {
    "Content-Type": "application/json",
    "Origin":       "https://mops.twse.com.tw",
    "Referer":      "https://mops.twse.com.tw/mops/",
    "User-Agent":   (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}
_TIMEOUT  = 20
_MAX_YEARS = 7


def _roc_to_ad(roc_year: int) -> int:
    return roc_year + 1911


def _ad_to_roc(ad_year: int) -> int:
    return ad_year - 1911


def _parse_num(s) -> Optional[float]:
    if s is None:
        return None
    s = str(s).replace(",", "").strip()
    if not s or s in ("-", "N/A", "－", "--"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _post(endpoint: str, payload: dict) -> Optional[dict]:
    try:
        resp = requests.post(
            _BASE + endpoint,
            headers=_HEADERS,
            json=payload,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        j = resp.json()
        if j.get("code") == 200:
            return j.get("result")
        logger.debug(f"[mops] {endpoint} code={j.get('code')} msg={j.get('message')}")
        return None
    except Exception as e:
        logger.warning(f"[mops] {endpoint} 請求失敗：{e}")
        return None


def _parse_income(result: dict) -> dict:
    """從損益表結果解析各項財務指標。"""
    out = {
        "eps": None, "gross_margin": None, "op_margin": None,
        "net_margin": None, "net_income": None, "revenue": None,
    }
    if not result:
        return out

    for item in result.get("reportList", []):
        name = item[0].strip().replace("　", "")
        if len(item) < 2:
            continue

        val  = _parse_num(item[1]) if len(item) > 1 else None
        pct  = _parse_num(item[2]) if len(item) > 2 else None

        if ("營業收入合計" in name or "收入合計" in name) and out["revenue"] is None:
            out["revenue"] = val
        if "毛利" in name and "淨額" in name and out["gross_margin"] is None:
            out["gross_margin"] = pct
        if "營業利益" in name and "淨額" not in name and out["op_margin"] is None:
            out["op_margin"] = pct
        if "本期淨利" in name and out["net_income"] is None:
            out["net_income"] = val
            out["net_margin"]  = pct
        if "基本每股盈餘" in name and item[1] and out["eps"] is None:
            out["eps"] = _parse_num(item[1])

    return out


def _parse_balance(result: dict) -> dict:
    """從資產負債表結果解析各項財務指標。"""
    out = {
        "total_assets": None, "total_liab": None, "equity": None,
        "current_assets": None, "current_liab": None,
        "debt_ratio": None, "current_ratio": None,
    }
    if not result:
        return out

    for item in result.get("reportList", []):
        name = item[0].strip().replace("　", "")
        val  = _parse_num(item[1]) if len(item) > 1 else None
        pct  = _parse_num(item[2]) if len(item) > 2 else None

        if "流動資產合計" in name:
            out["current_assets"] = val
        if "流動負債合計" in name:
            out["current_liab"] = val
        if "資產總額" in name or "資產總計" in name:
            out["total_assets"] = val
        if "負債總額" in name or "負債總計" in name:
            out["total_liab"] = val
            out["debt_ratio"] = pct          # 負債總額 % = 負債比
        if "權益總額" in name or "權益總計" in name or "股東權益總計" in name:
            out["equity"] = val

    if out["current_assets"] and out["current_liab"] and out["current_liab"] != 0:
        out["current_ratio"] = round(out["current_assets"] / out["current_liab"], 2)

    return out


def fetch_annual_financials(stock_id: str, roc_year: int) -> Optional[dict]:
    """
    取得指定股票、指定年度（民國年）的年度財務資料（Q4 = 全年）。

    回傳 dict：
      year, eps, roe, roa, gross_margin, op_margin, net_margin,
      debt_ratio, current_ratio
    """
    payload_base = {
        "companyId": stock_id,
        "dataType": "2",
        "season": "4",
        "year": str(roc_year),
        "subsidiaryCompanyId": "",
    }

    income  = _parse_income(_post("t164sb04", payload_base))
    balance = _parse_balance(_post("t164sb03", payload_base))

    eps = income.get("eps")
    if eps is None and income.get("net_income") is None:
        return None            # 兩個 API 都沒資料，跳過

    # 計算 ROE / ROA
    roe, roa = None, None
    ni = income.get("net_income")
    if ni and balance.get("equity") and balance["equity"] != 0:
        roe = round(ni / balance["equity"] * 100, 2)
    if ni and balance.get("total_assets") and balance["total_assets"] != 0:
        roa = round(ni / balance["total_assets"] * 100, 2)

    return {
        "year":          _roc_to_ad(roc_year),
        "eps":           eps,
        "roe":           roe,
        "roa":           roa,
        "gross_margin":  income.get("gross_margin"),
        "op_margin":     income.get("op_margin"),
        "net_margin":    income.get("net_margin"),
        "debt_ratio":    balance.get("debt_ratio"),
        "current_ratio": balance.get("current_ratio"),
    }


def fetch_multi_year(stock_id: str, n_years: int = _MAX_YEARS) -> list:
    """
    取得過去 N 年的年度財務資料。
    回傳 list of dict（newest first），最多 n_years 筆。
    每次請求間隔短暫隨機延遲。
    """
    from datetime import date
    current_roc = date.today().year - 1911
    results = []

    for roc_year in range(current_roc - 1, current_roc - n_years - 1, -1):
        rec = fetch_annual_financials(stock_id, roc_year)
        if rec:
            results.append(rec)
        # 避免速率限制
        time.sleep(random.uniform(0.3, 0.6))

        if len(results) >= n_years:
            break

    logger.debug(f"[mops] {stock_id}：取得 {len(results)} 年資料")
    return results
