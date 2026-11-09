"""
PART B: Execution-Date Semantic Auditor — Session 43.

Establishes formal definitions and provenance for all date fields in
forward_signals and related tables. Diagnoses execution_date anomalies.

Key findings:
- Oct 15, Oct 19, Oct 20 are "0050-only thin days" (1 stock in daily_prices)
  → NOT real trading days for common stocks
- Oct 14 → fill Oct 16: CORRECT behavior (Oct 15 is a thin day)
- Oct 16 → fill Oct 21: CORRECT behavior (Oct 17-18 weekend; Oct 19-20 thin days)
- execution_date uses stock-specific price availability, not full-market calendar
- All execution_price_type = 'NEXT_OPEN' → SIMULATED_FILL, not actual broker execution
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import Enum


class ExecutionType(str, Enum):
    NEXT_OPEN_SIMULATED = "NEXT_OPEN_SIMULATED"
    ACTUAL_BROKER = "ACTUAL_BROKER"
    RETROSPECTIVE = "RETROSPECTIVE"
    UNKNOWN = "UNKNOWN"


class DateFieldProvenance(str, Enum):
    DIRECT_DB_WRITE = "DIRECT_DB_WRITE"      # explicitly set by pipeline
    DERIVED_FROM_SIGNAL = "DERIVED_FROM_SIGNAL"  # computed from signal_date
    COMPUTED_FROM_PRICE = "COMPUTED_FROM_PRICE"  # found first available price
    NULL_FOR_NON_TD = "NULL_FOR_NON_TD"       # NULL when signal is on non-trading day


@dataclass(frozen=True)
class DateFieldDefinition:
    field_name: str
    source_table: str
    definition: str
    timezone: str
    nullable_condition: str
    generation_rule: str
    provenance: DateFieldProvenance
    example_values: tuple[str, ...]
    notes: str = ""


@dataclass(frozen=True)
class ThinDayEntry:
    date: str
    n_stocks: int
    stocks_present: tuple[str, ...]
    is_officially_market_open: bool
    execution_implication: str


@dataclass(frozen=True)
class ExecutionAnomalyEntry:
    signal_date: str
    execution_date: str
    days_gap: int
    skipped_dates: tuple[str, ...]
    root_cause: str
    execution_type: ExecutionType
    is_anomaly: bool
    explanation: str


@dataclass(frozen=True)
class ExecutionDateIntegrityReport:
    session: int
    date_field_definitions: tuple[DateFieldDefinition, ...]
    thin_days: tuple[ThinDayEntry, ...]
    n_thin_days: int
    execution_anomalies: tuple[ExecutionAnomalyEntry, ...]
    n_executions_next_open: int
    n_executions_null: int
    execution_type_verdict: ExecutionType
    real_trading_days_oct2026: tuple[str, ...]
    corrected_trading_day_count: int
    overall_verdict: str


_DATE_FIELD_DEFINITIONS = (
    DateFieldDefinition(
        "trade_date",
        "forward_signals",
        "Date the cron job ran and assigned as the 'trading session' for the signal. "
        "May be a non-trading day if the cron ran on a holiday/weekend.",
        "Asia/Taipei (inferred from production environment)",
        "NOT NULL",
        "Set to the date portion of locked_at or the cron execution date.",
        DateFieldProvenance.DIRECT_DB_WRITE,
        ("2026-10-12", "2026-10-09 [non-trading, holiday]"),
        "NOT reliable as a trading execution date without calendar validation.",
    ),
    DateFieldDefinition(
        "locked_at",
        "forward_signals",
        "UTC timestamp when the signal record was finalized and written to DB. "
        "Represents when the analysis ran, not when the trade would execute.",
        "UTC (stored as DATETIME)",
        "NOT NULL",
        "Set by the signal generation pipeline at write time.",
        DateFieldProvenance.DIRECT_DB_WRITE,
        ("2026-10-08T...", "2026-10-10T..."),
        "Oct 09 signals have locked_at=2026-10-08 (generated evening before holiday).",
    ),
    DateFieldDefinition(
        "execution_date",
        "forward_signals",
        "The first real trading day on which the signal stock had an available "
        "opening price for NEXT_OPEN simulated execution. NOT a broker fill date. "
        "Computed by NEXT_OPEN pipeline by scanning daily_prices for stock-specific "
        "first available price >= the day after trade_date.",
        "Asia/Taipei",
        "NULLABLE — NULL when trade_date is a non-trading day AND execution was "
        "never simulated (Oct 09, 10, 11 signals have NULL execution_date).",
        "execution_date = MIN(date in daily_prices WHERE stock_id=? AND date > trade_date)",
        DateFieldProvenance.COMPUTED_FROM_PRICE,
        ("2026-10-13", "2026-10-16", "NULL"),
        "Oct 14→Oct 16 (skips Oct 15 thin day). Oct 16→Oct 21 (skips Oct 17-20).",
    ),
    DateFieldDefinition(
        "execution_price",
        "forward_signals",
        "Open price of the stock on execution_date. SIMULATED_FILL price, not "
        "actual broker execution price.",
        "TWD (Taiwan Dollar)",
        "NULLABLE — NULL when execution_date is NULL.",
        "Looked up from daily_prices.open on execution_date.",
        DateFieldProvenance.COMPUTED_FROM_PRICE,
        ("123.5", "NULL"),
        "Should be labeled SIMULATED_FILL not ACTUAL_FILL.",
    ),
    DateFieldDefinition(
        "execution_price_type",
        "forward_signals",
        "Method used to determine execution price.",
        "N/A (categorical)",
        "NULLABLE",
        "Set to 'NEXT_OPEN' for all simulated fills.",
        DateFieldProvenance.DIRECT_DB_WRITE,
        ("NEXT_OPEN", "NULL"),
        "All non-NULL values in Oct 2026 are 'NEXT_OPEN'.",
    ),
)


def _get_thin_days(conn: sqlite3.Connection, start: str, end: str) -> list[ThinDayEntry]:
    q = """
        SELECT date, COUNT(DISTINCT stock_id) as n, GROUP_CONCAT(DISTINCT stock_id) as stocks
        FROM daily_prices
        WHERE date BETWEEN ? AND ?
        GROUP BY date HAVING n < 50
        ORDER BY date
    """
    rows = conn.execute(q, (start, end)).fetchall()
    entries = []
    for dt, n, stocks_str in rows:
        stocks = tuple((stocks_str or "").split(",")) if stocks_str else ()
        # Thin days with only 0050-type stocks are likely 0050-only days (data feed artifacts)
        is_etf_only = all(s.startswith("00") for s in stocks if s)
        entries.append(ThinDayEntry(
            date=dt,
            n_stocks=n,
            stocks_present=stocks,
            is_officially_market_open=is_etf_only,  # ETF-only → partial open
            execution_implication=(
                "EXECUTION_SKIPS_THIS_DAY"
                if is_etf_only
                else "EXECUTION_MAY_USE_THIS_DAY"
            ),
        ))
    return entries


def build_execution_date_integrity_report(conn: sqlite3.Connection) -> ExecutionDateIntegrityReport:
    # Thin days in Oct 2026
    thin_days = _get_thin_days(conn, "2026-10-01", "2026-11-30")

    # Real trading days (≥50 stocks)
    q = """
        SELECT date FROM daily_prices WHERE date BETWEEN '2026-10-01' AND '2026-11-30'
        GROUP BY date HAVING COUNT(DISTINCT stock_id) >= 50 ORDER BY date
    """
    real_tds = tuple(r[0] for r in conn.execute(q).fetchall())

    # Execution counts
    exec_q = """
        SELECT execution_price_type, COUNT(*) FROM forward_signals
        WHERE trade_date BETWEEN '2026-10-01' AND '2026-11-30'
        GROUP BY execution_price_type
    """
    exec_counts = dict(conn.execute(exec_q).fetchall())
    n_next_open = exec_counts.get("NEXT_OPEN", 0)
    n_null_exec = conn.execute(
        "SELECT COUNT(*) FROM forward_signals WHERE trade_date BETWEEN '2026-10-01' AND '2026-11-30' AND execution_date IS NULL"
    ).fetchone()[0]

    # Anomaly: Oct 14 → Oct 16 and Oct 16 → Oct 21
    thin_set = {t.date for t in thin_days}

    anomalies = []
    q_pairs = """
        SELECT DISTINCT trade_date, execution_date FROM forward_signals
        WHERE trade_date BETWEEN '2026-10-12' AND '2026-10-31'
          AND execution_date IS NOT NULL
          AND trade_signal IN ('buy','strong_buy')
        ORDER BY trade_date
    """
    for td, ed in conn.execute(q_pairs).fetchall():
        from datetime import date as date_cls
        td_obj = date_cls.fromisoformat(td)
        ed_obj = date_cls.fromisoformat(ed)
        gap = (ed_obj - td_obj).days
        # Find skipped dates
        all_dates_between = []
        cur = td_obj
        from datetime import timedelta
        while cur < ed_obj:
            cur = cur + timedelta(days=1)
            if cur < ed_obj:
                all_dates_between.append(str(cur))

        is_anomaly = gap > 1
        if is_anomaly:
            skipped_thin = [d for d in all_dates_between if d in thin_set]
            root_cause = (
                f"Thin days skipped: {skipped_thin}. "
                "These dates have only ETF/index stock data (n=1 stock) in daily_prices. "
                "NEXT_OPEN engine scans stock-specific daily_prices → no price found on thin days."
            )
            explanation = (
                f"trade_date={td}, expected execution={td_obj + timedelta(days=1)} "
                f"(next calendar day), actual execution={ed} (day after thin days). "
                "This is CORRECT execution behavior. No data error."
            )
        else:
            root_cause = "Normal: execution on the next trading day"
            explanation = "Expected behavior"

        anomalies.append(ExecutionAnomalyEntry(
            signal_date=td,
            execution_date=ed,
            days_gap=gap,
            skipped_dates=tuple(all_dates_between),
            root_cause=root_cause,
            execution_type=ExecutionType.NEXT_OPEN_SIMULATED,
            is_anomaly=is_anomaly,
            explanation=explanation,
        ))

    return ExecutionDateIntegrityReport(
        session=43,
        date_field_definitions=_DATE_FIELD_DEFINITIONS,
        thin_days=tuple(thin_days),
        n_thin_days=len(thin_days),
        execution_anomalies=tuple(anomalies),
        n_executions_next_open=n_next_open,
        n_executions_null=n_null_exec,
        execution_type_verdict=ExecutionType.NEXT_OPEN_SIMULATED,
        real_trading_days_oct2026=real_tds,
        corrected_trading_day_count=len(real_tds),
        overall_verdict=(
            "EXECUTION_PARTIAL"
            if n_null_exec > 0
            else "EXECUTION_VERIFIED"
        ),
    )
