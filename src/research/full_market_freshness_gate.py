"""
full_market_freshness_gate.py — Full-market DailyPrice freshness validation

Distinct from DailyPrice Quality Gate (content validity) and OHLC Continuity Gate
(historical completeness). This gate checks whether TODAY's market data is complete
across the full stock universe before allowing PROSPECTIVE decisions.

Statuses:
  FULL_MARKET_FRESH         0050 + >= MIN_COVERED_STOCKS non-0050 stocks present for today.
  PARTIAL_MARKET_UPDATE     0050 present for today, but non-0050 count < threshold.
  BENCHMARK_ONLY_UPDATED    0050 present for today, non-0050 count = 0 (most severe partial).
  STALE                     0050 not present for today (last date < today).
  PROVIDER_NOT_READY        0050 not present and today is a trading day (data not yet published).
  MARKET_CLOSED             Today is not a trading day.
  UNKNOWN                   Cannot determine status (e.g., DB error, empty DB).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Optional


MIN_COVERED_STOCKS = 5_000   # minimum non-0050 stocks required for FULL_MARKET_FRESH
# Calibrated against observed universe: TWSE+TPEx full day ≈ 6,956 non-0050 stocks (Nov 2026).
# TWSE-only ≈ 1,976 stocks — below this threshold → correctly shows PARTIAL_MARKET_UPDATE.
# 1,000 was insufficient: a TWSE-only write would pass as FULL_MARKET_FRESH.


class FreshnessStatus(str, Enum):
    FULL_MARKET_FRESH         = "FULL_MARKET_FRESH"
    PARTIAL_MARKET_UPDATE     = "PARTIAL_MARKET_UPDATE"
    BENCHMARK_ONLY_UPDATED    = "BENCHMARK_ONLY_UPDATED"
    STALE                     = "STALE"
    PROVIDER_NOT_READY        = "PROVIDER_NOT_READY"
    MARKET_CLOSED             = "MARKET_CLOSED"
    UNKNOWN                   = "UNKNOWN"


@dataclass
class FreshnessReport:
    status: FreshnessStatus
    trade_date: date
    benchmark_date: Optional[date]       # max date for 0050
    non_benchmark_count: int             # non-0050 stocks on trade_date
    min_required: int
    detail: str

    @property
    def is_blocked(self) -> bool:
        return self.status not in (FreshnessStatus.FULL_MARKET_FRESH, FreshnessStatus.MARKET_CLOSED)

    def human_readable(self) -> str:
        if self.status == FreshnessStatus.FULL_MARKET_FRESH:
            return f"全市場資料完整（{self.non_benchmark_count:,} 股，0050={self.benchmark_date}）"
        if self.status == FreshnessStatus.PARTIAL_MARKET_UPDATE:
            return (
                f"0050 已更新，但部分股票行情還沒到齊"
                f"（現有 {self.non_benchmark_count:,} 股，需要 >= {self.min_required:,} 股），"
                "因此暫停產生新的研究決策。"
            )
        if self.status == FreshnessStatus.BENCHMARK_ONLY_UPDATED:
            return (
                f"0050 已更新至 {self.benchmark_date}，但全市場股票資料尚未到齊（0 股）。"
                "TWSE 資料通常在台灣時間 15:30–16:00 發布。"
            )
        if self.status == FreshnessStatus.STALE:
            return (
                f"DailyPrice 已過期：0050 最新日期 {self.benchmark_date}，"
                f"今日為 {self.trade_date}。"
            )
        if self.status == FreshnessStatus.PROVIDER_NOT_READY:
            return "今日為交易日，但 TWSE/TPEx 資料尚未發布（通常 15:30 後可用）。"
        if self.status == FreshnessStatus.MARKET_CLOSED:
            return f"{self.trade_date} 為非交易日（例假日或週末）。"
        return f"無法判斷資料狀態：{self.detail}"


def check_market_freshness(
    conn: sqlite3.Connection,
    trade_date: date,
    min_covered_stocks: int = MIN_COVERED_STOCKS,
    is_trading_day: Optional[bool] = None,
) -> FreshnessReport:
    """
    Check whether DailyPrice data for trade_date is fully populated.

    Args:
        conn: SQLite connection to platform.db.
        trade_date: The date to check (usually today).
        min_covered_stocks: Minimum non-0050 stock count required for FULL_MARKET_FRESH.
        is_trading_day: Pre-computed trading day flag (skips calendar check if provided).

    Returns:
        FreshnessReport with status and human-readable detail.
    """
    # Optional short-circuit: caller tells us it's not a trading day
    if is_trading_day is False:
        return FreshnessReport(
            status=FreshnessStatus.MARKET_CLOSED,
            trade_date=trade_date,
            benchmark_date=None,
            non_benchmark_count=0,
            min_required=min_covered_stocks,
            detail=f"{trade_date} is not a trading day",
        )

    try:
        # 0050 (benchmark) freshness
        row = conn.execute(
            "SELECT MAX(date) FROM daily_prices WHERE stock_id='0050'"
        ).fetchone()
        benchmark_date_str = row[0] if row else None
        benchmark_date = date.fromisoformat(benchmark_date_str) if benchmark_date_str else None

        # Non-0050 count on trade_date
        non_bm_row = conn.execute(
            "SELECT COUNT(DISTINCT stock_id) FROM daily_prices "
            "WHERE stock_id != '0050' AND date = ?",
            (str(trade_date),),
        ).fetchone()
        non_bm_count = non_bm_row[0] if non_bm_row else 0

    except Exception as exc:
        return FreshnessReport(
            status=FreshnessStatus.UNKNOWN,
            trade_date=trade_date,
            benchmark_date=None,
            non_benchmark_count=0,
            min_required=min_covered_stocks,
            detail=f"DB query error: {exc}",
        )

    # Determine status
    if benchmark_date is None:
        status = FreshnessStatus.UNKNOWN
        detail = "No 0050 data in daily_prices"
    elif benchmark_date < trade_date:
        # 0050 not updated today — distinguish provider delay vs genuine stale
        if is_trading_day is True:
            status = FreshnessStatus.PROVIDER_NOT_READY
            detail = (
                f"0050 last_date={benchmark_date}, today={trade_date}; "
                "TWSE data not yet published (expected after 15:30 Taiwan)"
            )
        else:
            status = FreshnessStatus.STALE
            detail = f"0050 last_date={benchmark_date}, today={trade_date}"
    elif benchmark_date >= trade_date:
        # 0050 is at trade_date or newer — check full market coverage on trade_date
        if non_bm_count == 0:
            if benchmark_date > trade_date:
                # 0050 has NEWER data, but non-0050 count on trade_date is 0 —
                # could mean trade_date was never fully populated (e.g., manual 0050 recovery)
                status = FreshnessStatus.BENCHMARK_ONLY_UPDATED
                detail = (
                    f"0050 max_date={benchmark_date} >= {trade_date}, "
                    f"but non-0050 count on {trade_date}=0; "
                    "market data for this date was not fully backfilled"
                )
            else:
                status = FreshnessStatus.BENCHMARK_ONLY_UPDATED
                detail = (
                    f"0050 updated to {trade_date}, but non-0050 count=0; "
                    "full market data not yet published"
                )
        elif non_bm_count < min_covered_stocks:
            status = FreshnessStatus.PARTIAL_MARKET_UPDATE
            detail = (
                f"0050 max_date={benchmark_date}, non-0050 count on {trade_date}={non_bm_count} "
                f"< threshold={min_covered_stocks}"
            )
        else:
            status = FreshnessStatus.FULL_MARKET_FRESH
            detail = (
                f"0050 max_date={benchmark_date}, non-0050 count on {trade_date}={non_bm_count} "
                f">= threshold={min_covered_stocks}"
            )

    return FreshnessReport(
        status=status,
        trade_date=trade_date,
        benchmark_date=benchmark_date,
        non_benchmark_count=non_bm_count,
        min_required=min_covered_stocks,
        detail=detail,
    )
