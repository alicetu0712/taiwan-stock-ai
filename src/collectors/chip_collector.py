"""
chip_collector.py — 籌碼資料蒐集

蒐集：三大法人買賣超（外資、投信、自營商）、融資融券
資料來源：TWSE OpenAPI + TPEx OpenAPI
"""

import logging
import time
from datetime import date
from typing import Optional

import pandas as pd
import requests

from src.collectors.base import BaseCollector

from config import (
    FINMIND_TOKEN,
    HTTP_HEADERS,
    HTTP_RETRY,
    HTTP_TIMEOUT,
    TPEX_API,
    TWSE_API,
)

logger = logging.getLogger(__name__)


def _get(url: str) -> Optional[list]:
    for attempt in range(HTTP_RETRY):
        try:
            resp = requests.get(url, headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"[Attempt {attempt+1}] GET {url} failed: {e}")
            if attempt < HTTP_RETRY - 1:
                time.sleep(2**attempt)
    return None


def fetch_twse_institutional() -> pd.DataFrame:
    """TWSE 三大法人每日買賣超（上市）。"""
    records = []

    # 外資
    data = _get(TWSE_API["foreign_net"])
    if data:
        for row in data:
            sid = str(row.get("Code", "")).strip()
            if not sid:
                continue
            records.append(
                {
                    "stock_id": sid,
                    "foreign_net": _to_float(row.get("Foreign_Investor_Diff")),
                }
            )

    df_foreign = (
        pd.DataFrame(records).set_index("stock_id") if records else pd.DataFrame()
    )

    # 投信
    records_trust = []
    data_trust = _get(TWSE_API["trust_net"])
    if data_trust:
        for row in data_trust:
            sid = str(row.get("Code", "")).strip()
            if not sid:
                continue
            records_trust.append(
                {
                    "stock_id": sid,
                    "trust_net": _to_float(row.get("Diff")),
                }
            )
    df_trust = (
        pd.DataFrame(records_trust).set_index("stock_id")
        if records_trust
        else pd.DataFrame()
    )

    # 自營商
    records_dealer = []
    data_dealer = _get(TWSE_API["dealer_net"])
    if data_dealer:
        for row in data_dealer:
            sid = str(row.get("Code", "")).strip()
            if not sid:
                continue
            records_dealer.append(
                {
                    "stock_id": sid,
                    "dealer_net": _to_float(row.get("Diff")),
                }
            )
    df_dealer = (
        pd.DataFrame(records_dealer).set_index("stock_id")
        if records_dealer
        else pd.DataFrame()
    )

    # 合併
    df = pd.DataFrame(
        index=list(
            set(list(df_foreign.index) + list(df_trust.index) + list(df_dealer.index))
        )
    )
    if not df_foreign.empty:
        df = df.join(df_foreign, how="left")
    if not df_trust.empty:
        df = df.join(df_trust, how="left")
    if not df_dealer.empty:
        df = df.join(df_dealer, how="left")

    df = df.reset_index().rename(columns={"index": "stock_id"})
    df["market"] = "TWSE"
    df["date"] = date.today()

    for col in ["foreign_net", "trust_net", "dealer_net"]:
        if col not in df.columns:
            df[col] = 0.0
        df[col] = df[col].fillna(0)

    df["total_net"] = df["foreign_net"] + df["trust_net"] + df["dealer_net"]
    logger.info(f"TWSE institutional: {len(df)} stocks")
    return df


def fetch_tpex_institutional() -> pd.DataFrame:
    """TPEx 三大法人每日買賣超（上櫃）。"""
    data = _get(TPEX_API["institutional"])
    if not data:
        return pd.DataFrame()

    records = []
    for row in data:
        sid = str(row.get("SecuritiesCompanyCode", "")).strip()
        if not sid:
            continue
        records.append(
            {
                "stock_id": sid,
                "market": "TPEx",
                "date": date.today(),
                "foreign_net": _to_float(row.get("ForeignInvestorBuySellDifference")),
                "trust_net": _to_float(row.get("InvestmentTrustBuySellDifference")),
                "dealer_net": _to_float(row.get("DealerBuySellDifference")),
            }
        )

    df = pd.DataFrame(records)
    if df.empty:
        return df
    for col in ["foreign_net", "trust_net", "dealer_net"]:
        df[col] = df[col].fillna(0)
    df["total_net"] = df["foreign_net"] + df["trust_net"] + df["dealer_net"]
    logger.info(f"TPEx institutional: {len(df)} stocks")
    return df


def fetch_all_institutional(trade_date: Optional[date] = None) -> pd.DataFrame:
    """合併上市 + 上櫃三大法人。"""
    twse = fetch_twse_institutional()
    tpex = fetch_tpex_institutional()
    df = pd.concat([twse, tpex], ignore_index=True)
    if trade_date:
        df["date"] = trade_date
    logger.info(f"Total institutional data: {len(df)} stocks")
    return df


def fetch_institutional_history_finmind(
    stock_id: str,
    start_date: str,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    """用 FinMind 取得個股法人歷史資料（用於趨勢分析）。"""
    if not FINMIND_TOKEN:
        return pd.DataFrame()
    try:
        from FinMind.data import DataLoader

        dl = DataLoader()
        dl.login_by_token(api_token=FINMIND_TOKEN)
        df = dl.taiwan_stock_institutional_investors(
            stock_id=stock_id,
            start_date=start_date,
            end_date=end_date or date.today().isoformat(),
        )
        if df.empty:
            return pd.DataFrame()

        df["date"] = pd.to_datetime(df["date"]).dt.date
        pivot = df.pivot_table(
            index="date",
            columns="name",
            values=["buy", "sell"],
            aggfunc="sum",
        ).reset_index()
        pivot.columns = [
            "_".join(str(c) for c in col).strip("_") if isinstance(col, tuple) else col
            for col in pivot.columns
        ]

        # 計算法人買賣超（使用標準化欄位名稱）
        result = pd.DataFrame()
        result["date"] = pivot["date"]
        result["stock_id"] = stock_id

        # 外資
        result["foreign_net"] = pivot.get(
            "buy_外陸資買賣超股數(不含外資自營商)", pd.Series(0, index=pivot.index)
        ) - pivot.get("sell_外陸資買賣超股數(不含外資自營商)", pd.Series(0, index=pivot.index))

        # 投信
        result["trust_net"] = pivot.get(
            "buy_投信買賣超股數", pd.Series(0, index=pivot.index)
        ) - pivot.get("sell_投信買賣超股數", pd.Series(0, index=pivot.index))

        result["total_net"] = result["foreign_net"] + result["trust_net"]
        return result

    except Exception as e:
        logger.warning(f"FinMind institutional history failed ({stock_id}): {e}")
        return pd.DataFrame()


def fetch_margin_trading(trade_date: Optional[date] = None) -> pd.DataFrame:
    """抓取融資融券資料（TWSE）。"""
    data = _get(TWSE_API["margin"])
    if not data:
        return pd.DataFrame()

    records = []
    for row in data:
        sid = str(row.get("Code", "")).strip()
        if not sid:
            continue
        try:
            records.append(
                {
                    "stock_id": sid,
                    "date": trade_date or date.today(),
                    "margin_buy": _to_float(row.get("Finance_Buy")),
                    "margin_sell": _to_float(row.get("Finance_Sell")),
                    "margin_balance": _to_float(row.get("Finance_Remain")),
                    "short_sell": _to_float(row.get("Short_Sell")),
                    "short_buy": _to_float(row.get("Short_Sell_Back")),
                    "short_balance": _to_float(row.get("Short_Remain")),
                }
            )
        except Exception as e:
            logger.debug(f"chip row parse skip: {e}")
            continue

    df = pd.DataFrame(records)
    for col in [
        "margin_buy",
        "margin_sell",
        "margin_balance",
        "short_sell",
        "short_buy",
        "short_balance",
    ]:
        if col in df.columns:
            df[col] = df[col].fillna(0)
    logger.info(f"Margin trading: {len(df)} stocks")
    return df


def _to_float(val) -> Optional[float]:
    if val is None:
        return None
    try:
        s = str(val).replace(",", "").strip()
        if s in ("--", "-", "", "N/A"):
            return None
        return float(s)
    except (ValueError, TypeError):
        return None


# ── 統一介面 ──────────────────────────────────────────────────


class ChipCollector(BaseCollector):
    """統一 Collector 介面。run() 回傳 CollectResult。"""

    name = "chip"

    def collect(self, trade_date: Optional[date] = None, **kwargs) -> pd.DataFrame:
        return fetch_all_institutional(trade_date)

    def validate(self, data: pd.DataFrame) -> tuple:
        if data is None or data.empty:
            return False, "institutional data is empty"
        required = {"stock_id", "foreign_net"}
        missing = required - set(data.columns)
        if missing:
            return False, f"missing columns: {missing}"
        return True, "ok"

    def parse(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        df["stock_id"] = df["stock_id"].astype(str).str.strip()
        for col in ("foreign_net", "trust_net", "dealer_net", "total_net"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df

    def save(self, df: pd.DataFrame, session) -> int:
        from src.database import InstitutionalData

        trade_date = df["date"].iloc[0] if "date" in df.columns else date.today()
        n = 0
        for _, row in df.iterrows():
            exists = (
                session.query(InstitutionalData)
                .filter_by(stock_id=row["stock_id"], date=trade_date)
                .first()
            )
            if not exists:
                session.add(
                    InstitutionalData(
                        stock_id=row["stock_id"],
                        date=trade_date,
                        foreign_net=row.get("foreign_net"),
                        trust_net=row.get("trust_net"),
                        dealer_net=row.get("dealer_net"),
                        total_net=row.get("total_net"),
                    )
                )
                n += 1
        session.commit()
        return n

    # run() 繼承自 BaseCollector — 回傳 CollectResult
