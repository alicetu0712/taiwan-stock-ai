"""
PART B: Trading Calendar Integrity Auditor — Session 42.

Uses daily_prices as ground truth for trading days.
Classifies each forward signal's trade_date against official calendar.

Key finding: Oct 09, 10, 11 2026 are ALL non-trading days:
- Oct 09: holiday/補假 (National Day week)
- Oct 10: National Day (國慶日) + Saturday
- Oct 11: Sunday
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class MarketDateStatus(str, Enum):
    TRADING_DAY = "TRADING_DAY"
    NON_TRADING_DAY = "NON_TRADING_DAY"
    UNVERIFIED = "UNVERIFIED"


class SignalDateClassification(str, Enum):
    VALID_SIGNAL_DATE = "VALID_SIGNAL_DATE"      # signal on a trading day
    NON_TRADING_DAY_SIGNAL = "NON_TRADING_DAY_SIGNAL"  # signal on non-trading day
    TRADE_DATE_UNVERIFIED = "TRADE_DATE_UNVERIFIED"


@dataclass(frozen=True)
class SignalDateAuditEntry:
    signal_date: str
    market_status: MarketDateStatus
    classification: SignalDateClassification
    n_signals_total: int
    n_buy_strong_buy: int
    next_trading_day: Optional[str]  # the fill date for NEXT_OPEN execution
    note: str = ""


@dataclass(frozen=True)
class TradingCalendarIntegrityReport:
    session: int
    evaluation_date: str
    calendar_source: str                    # "daily_prices (ground truth)"
    calendar_version: str                   # based on data cutoff date
    signal_date_entries: tuple[SignalDateAuditEntry, ...]
    n_total_signals_buy_sb: int
    n_non_trading_day_signals: int
    n_trading_day_signals: int
    pct_non_trading: float
    affected_dates: tuple[str, ...]         # the non-trading dates in dataset
    fill_date_mapping: dict                 # signal_date -> fill_date
    overall_verdict: str


def _get_trading_days(conn: sqlite3.Connection, start: str, end: str) -> set[str]:
    q = "SELECT DISTINCT date FROM daily_prices WHERE date BETWEEN ? AND ? ORDER BY date"
    return set(r[0] for r in conn.execute(q, (start, end)).fetchall())


def _get_next_trading_day(date: str, trading_days: set[str]) -> Optional[str]:
    all_sorted = sorted(trading_days)
    try:
        for d in all_sorted:
            if d > date:
                return d
    except Exception:
        pass
    return None


def build_trading_calendar_integrity_report(conn: sqlite3.Connection) -> TradingCalendarIntegrityReport:
    trading_days = _get_trading_days(conn, "2026-10-01", "2026-11-30")

    # Ground truth cutoff
    max_dp_date = conn.execute("SELECT MAX(date) FROM daily_prices").fetchone()[0] or "unknown"

    # Get signal date breakdown
    q = """
        SELECT fs.trade_date, fs.trade_signal, COUNT(*) as n
        FROM forward_signals fs
        WHERE fs.trade_date BETWEEN '2026-10-01' AND '2026-10-31'
        GROUP BY fs.trade_date, fs.trade_signal
        ORDER BY fs.trade_date
    """
    rows = conn.execute(q).fetchall()

    # Aggregate by date
    date_totals: dict[str, int] = {}
    date_buy_sb: dict[str, int] = {}
    for trade_date, signal, n in rows:
        date_totals[trade_date] = date_totals.get(trade_date, 0) + n
        if signal in ("buy", "strong_buy"):
            date_buy_sb[trade_date] = date_buy_sb.get(trade_date, 0) + n

    entries = []
    fill_mapping: dict[str, str] = {}

    for sig_date in sorted(date_totals.keys()):
        if sig_date in trading_days:
            status = MarketDateStatus.TRADING_DAY
            classification = SignalDateClassification.VALID_SIGNAL_DATE
            note = ""
        else:
            status = MarketDateStatus.NON_TRADING_DAY
            classification = SignalDateClassification.NON_TRADING_DAY_SIGNAL
            # Determine why
            from datetime import date as date_cls
            try:
                d = date_cls.fromisoformat(sig_date)
                day_name = d.strftime("%A")
                if sig_date == "2026-10-10":
                    note = "National Day (國慶日) + Saturday"
                elif sig_date == "2026-10-11":
                    note = "Sunday"
                elif sig_date == "2026-10-09":
                    note = "Pre-National Day holiday (補假); Friday but market closed"
                else:
                    note = f"{day_name} non-trading"
            except Exception:
                note = "Non-trading"

        next_td = _get_next_trading_day(sig_date, trading_days)
        fill_mapping[sig_date] = next_td or sig_date

        entries.append(SignalDateAuditEntry(
            signal_date=sig_date,
            market_status=status,
            classification=classification,
            n_signals_total=date_totals[sig_date],
            n_buy_strong_buy=date_buy_sb.get(sig_date, 0),
            next_trading_day=next_td,
            note=note,
        ))

    n_buy_sb_total = sum(e.n_buy_strong_buy for e in entries)
    n_non_td = sum(e.n_buy_strong_buy for e in entries if e.market_status == MarketDateStatus.NON_TRADING_DAY)
    n_td = n_buy_sb_total - n_non_td
    affected = tuple(e.signal_date for e in entries if e.market_status == MarketDateStatus.NON_TRADING_DAY)

    if n_non_td == 0:
        verdict = "CALENDAR_VERIFIED"
    elif n_non_td / n_buy_sb_total < 0.1:
        verdict = "CALENDAR_PARTIAL"
    else:
        verdict = "CALENDAR_FAILED"

    return TradingCalendarIntegrityReport(
        session=42,
        evaluation_date=max_dp_date,
        calendar_source="daily_prices (ground truth from TWSE price feed)",
        calendar_version=f"as_of_{max_dp_date}",
        signal_date_entries=tuple(entries),
        n_total_signals_buy_sb=n_buy_sb_total,
        n_non_trading_day_signals=n_non_td,
        n_trading_day_signals=n_td,
        pct_non_trading=n_non_td / n_buy_sb_total if n_buy_sb_total > 0 else 0.0,
        affected_dates=affected,
        fill_date_mapping=fill_mapping,
        overall_verdict=verdict,
    )
