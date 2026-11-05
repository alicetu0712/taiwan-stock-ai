"""
dailyprice_quality_gate.py — DailyPrice data quality validation

Used by backfill_daily_prices.py before writing to local SQLite.
Also callable standalone to audit existing data.

Checks:
  QG-1  OHLC consistency: low <= min(open,close) and high >= max(open,close) and all > 0
  QG-2  Price bounds: 0.1 <= close <= 20000 (conservative range for TWSE stocks)
  QG-3  Volume non-negative: volume >= 0
  QG-4  No intra-batch duplicates: same stock_id cannot appear twice
  QG-5  Date consistency: every row's date == requested date
  QG-6  Coverage threshold: row_count >= min_expected_stocks (default 300 for TWSE, 50 for TPEx)
  QG-7  Benchmark presence: 0050 must be present in TWSE results
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Conservative defaults; can be overridden per call
_TWSE_MIN_STOCKS = 300
_TPEX_MIN_STOCKS = 50
_PRICE_MIN = 0.1       # TWSE: stocks trade at minimum NT$0.10
_TPEX_PRICE_MIN = 0.01 # TPEx: penny stocks can trade as low as NT$0.01
_PRICE_MAX = 20_000.0


@dataclass
class QGIssue:
    check: str    # QG-1 … QG-7
    stock_id: Optional[str]
    detail: str
    severity: str  # "error" | "warning"


@dataclass
class QualityGateResult:
    target_date: date
    market: str            # "TWSE" | "TPEx" | "combined"
    total_rows: int
    pass_rows: int
    fail_rows: int
    issues: List[QGIssue] = field(default_factory=list)
    passed: bool = True    # False if any error-severity issue found

    def add_error(self, check: str, detail: str, stock_id: Optional[str] = None) -> None:
        self.issues.append(QGIssue(check=check, stock_id=stock_id, detail=detail, severity="error"))
        self.passed = False
        self.fail_rows += 1

    def add_warning(self, check: str, detail: str, stock_id: Optional[str] = None) -> None:
        self.issues.append(QGIssue(check=check, stock_id=stock_id, detail=detail, severity="warning"))

    def summary_str(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return (
            f"[QualityGate {status}] {self.target_date} {self.market}: "
            f"{self.pass_rows}/{self.total_rows} rows OK, "
            f"{len([i for i in self.issues if i.severity=='error'])} errors, "
            f"{len([i for i in self.issues if i.severity=='warning'])} warnings"
        )


def run_quality_gate(
    df: pd.DataFrame,
    target_date: date,
    market: str,
    min_stocks: Optional[int] = None,
    require_benchmark: bool = True,
    price_min: Optional[float] = None,
) -> QualityGateResult:
    """
    Validate a DataFrame of price rows fetched for target_date.

    df must have columns: stock_id, date, open, high, low, close, volume
    Returns QualityGateResult; result.passed=False if any error-level check fails.
    """
    if min_stocks is None:
        min_stocks = _TWSE_MIN_STOCKS if market == "TWSE" else _TPEX_MIN_STOCKS
    if price_min is None:
        price_min = _PRICE_MIN if market == "TWSE" else _TPEX_PRICE_MIN

    result = QualityGateResult(
        target_date=target_date,
        market=market,
        total_rows=len(df),
        pass_rows=0,
        fail_rows=0,
    )

    if df.empty:
        result.add_error("QG-6", f"Empty DataFrame — 0 rows returned (expected >= {min_stocks})")
        return result

    required_cols = {"stock_id", "date", "open", "high", "low", "close", "volume"}
    missing_cols = required_cols - set(df.columns)
    if missing_cols:
        result.add_error("QG-0", f"Missing columns: {missing_cols}")
        return result

    # QG-4: no intra-batch duplicates
    dup_sids = df["stock_id"].value_counts()
    for sid, cnt in dup_sids[dup_sids > 1].items():
        result.add_error("QG-4", f"stock_id={sid} appears {cnt} times in batch", stock_id=str(sid))

    # QG-5: date consistency
    if "date" in df.columns:
        wrong_date = df[df["date"].astype(str) != str(target_date)]
        for _, row in wrong_date.iterrows():
            result.add_error(
                "QG-5",
                f"row date={row['date']} != requested {target_date}",
                stock_id=str(row.get("stock_id", "?")),
            )

    # QG-6: coverage threshold
    if len(df) < min_stocks:
        result.add_error(
            "QG-6",
            f"Only {len(df)} rows returned; expected >= {min_stocks}. "
            f"API may have returned wrong/empty date.",
        )

    # QG-7: benchmark presence for TWSE
    if require_benchmark and market == "TWSE":
        if "0050" not in df["stock_id"].values:
            result.add_error("QG-7", "0050 missing from TWSE batch — API response may be incomplete")

    # Per-row QG-1, QG-2, QG-3
    fail_count = 0
    for _, row in df.iterrows():
        sid = str(row.get("stock_id", "?"))
        try:
            o = float(row["open"]) if row["open"] is not None else None
            h = float(row["high"]) if row["high"] is not None else None
            lo = float(row["low"]) if row["low"] is not None else None
            c = float(row["close"]) if row["close"] is not None else None
            vol = float(row["volume"]) if row["volume"] is not None else None
        except (TypeError, ValueError):
            result.add_error("QG-1", "Non-numeric OHLCV", stock_id=sid)
            fail_count += 1
            continue

        row_ok = True

        # QG-1: OHLC consistency (only check if all present)
        if o is not None and h is not None and lo is not None and c is not None:
            if lo <= 0 or h <= 0 or o <= 0 or c <= 0:
                result.add_error("QG-1", f"Non-positive OHLC: o={o} h={h} l={lo} c={c}", stock_id=sid)
                row_ok = False
            elif not (lo <= min(o, c) and h >= max(o, c) and lo <= h):
                result.add_error("QG-1", f"OHLC inconsistency: o={o} h={h} l={lo} c={c}", stock_id=sid)
                row_ok = False

        # QG-2: price bounds (close only, most critical)
        if c is not None:
            if c < price_min or c > _PRICE_MAX:
                result.add_error("QG-2", f"close={c} out of bounds [{price_min}, {_PRICE_MAX}]", stock_id=sid)
                row_ok = False

        # QG-3: volume non-negative
        if vol is not None and vol < 0:
            result.add_error("QG-3", f"volume={vol} < 0", stock_id=sid)
            row_ok = False

        if not row_ok:
            fail_count += 1
        else:
            result.pass_rows += 1

    return result


def audit_existing_data(
    conn,
    target_date: date,
    market: Optional[str] = None,
) -> QualityGateResult:
    """
    Audit DailyPrice rows already in the SQLite database for target_date.
    conn: sqlite3.Connection
    Note: daily_prices has no market column; market param only affects QG-7 benchmark check.
    """
    rows = conn.execute(
        "SELECT stock_id, date, open, high, low, close, volume "
        "FROM daily_prices WHERE date = ?",
        (str(target_date),),
    ).fetchall()

    if not rows:
        df = pd.DataFrame(columns=["stock_id", "date", "open", "high", "low", "close", "volume"])
    else:
        df = pd.DataFrame(rows, columns=["stock_id", "date", "open", "high", "low", "close", "volume"])

    mkt_label = market or "combined"
    return run_quality_gate(df, target_date, mkt_label, require_benchmark=(market == "TWSE"))
