"""
hybrid_trading_calendar.py — Taiwan Trading Calendar for Forward Shadow Maturity

Uses 0050 DailyPrice data as the trading-day proxy (consistent with regime
calculation in effectiveness_analyzer.py).

RESEARCH ONLY — no production dependency.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import List, Optional, Sequence


class TradingCalendar:
    """
    Provides trading-day lookups from a sorted list of known trading dates.

    Built from 0050's DailyPrice records; dates without 0050 price data are
    treated as non-trading days.

    Usage:
        cal = TradingCalendar.from_db(conn)
        entry_date = cal.next_trading_day(signal_date)
        maturity = cal.add_trading_days(entry_date, 20)
        n = cal.count_trading_days(entry_date, maturity)
        is_trading = cal.is_trading_day(signal_date)
    """

    def __init__(self, trading_dates: Sequence[date]) -> None:
        self._dates: List[date] = sorted(set(trading_dates))
        self._set: frozenset = frozenset(self._dates)
        self._idx = {d: i for i, d in enumerate(self._dates)}

    @classmethod
    def from_db(cls, conn: sqlite3.Connection, start: Optional[date] = None, end: Optional[date] = None) -> "TradingCalendar":
        """Load trading dates from 0050 DailyPrice in SQLite."""
        query = "SELECT DISTINCT date FROM daily_prices WHERE stock_id='0050'"
        params: list = []
        if start:
            query += " AND date >= ?"
            params.append(str(start))
        if end:
            query += " AND date <= ?"
            params.append(str(end))
        query += " ORDER BY date"
        rows = conn.execute(query, params).fetchall()
        dates = [date.fromisoformat(r[0]) for r in rows]
        return cls(dates)

    @classmethod
    def from_dates(cls, dates: Sequence[date]) -> "TradingCalendar":
        return cls(dates)

    def is_trading_day(self, d: date) -> bool:
        return d in self._set

    def next_trading_day(self, d: date, include_self: bool = False) -> Optional[date]:
        """
        First trading day strictly after d (or on d if include_self=True).
        Returns None if no such day in the calendar.
        """
        for td in self._dates:
            if include_self and td >= d:
                return td
            if not include_self and td > d:
                return td
        return None

    def add_trading_days(self, d: date, n: int) -> Optional[date]:
        """
        Return the trading day n trading days after d (d must be a trading day).
        If d is not a trading day, start from the next trading day after d.
        Returns None if calendar is too short.
        """
        if n < 0:
            return None
        start = d if self.is_trading_day(d) else self.next_trading_day(d)
        if start is None:
            return None
        idx = self._idx.get(start)
        if idx is None:
            return None
        target_idx = idx + n
        if target_idx >= len(self._dates):
            return None
        return self._dates[target_idx]

    def count_trading_days(self, start: date, end: date) -> int:
        """
        Count trading days in [start, end] inclusive.
        Both endpoints must be trading days or the count will be from the
        next trading day at or after start to the next at or after end.
        """
        s = start if self.is_trading_day(start) else self.next_trading_day(start, include_self=True)
        e = end if self.is_trading_day(end) else self.next_trading_day(end, include_self=True)
        if s is None or e is None or e < s:
            return 0
        si = self._idx.get(s, -1)
        ei = self._idx.get(e, -1)
        if si < 0 or ei < 0:
            return 0
        return ei - si + 1

    def last_known_date(self) -> Optional[date]:
        return self._dates[-1] if self._dates else None

    def all_dates(self) -> List[date]:
        return list(self._dates)
