"""
tests/test_load_history_fix.py — Verifies _load_history() returns the NEWEST
lookback bars, not the oldest (regression from ASC+LIMIT bug).

Bug context:
  Before fix: order_by(asc(date)).limit(90) → oldest 90 bars
  After fix:  order_by(desc(date)).limit(90) then reversed → newest 90 bars

Tests:
  LH01 — 90+ bars in DB → result is 90 rows, newest 90 not oldest 90
  LH02 — Chronological order: last row date == as_of
  LH03 — Cross-year boundary handled correctly
  LH04 — No future data (date > as_of never returned)
  LH05 — Fewer bars than lookback → returns all, still chronological
  LH06 — Empty stock → returns None
  LH07 — as_of gap: as_of falls between trading days → closest prior bar is last
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database import DailyPrice, init_db
from src.research.entry_timing_research_service import EntryTimingResearchService


@pytest.fixture(scope="module")
def engine():
    eng = create_engine("sqlite:///:memory:")
    init_db(eng)
    return eng


@pytest.fixture(scope="module")
def session(engine):
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()


def _add_bars(session, stock_id: str, start: date, n: int, base_close: float = 100.0):
    """Insert n consecutive calendar-day bars starting from start."""
    for i in range(n):
        d = start + timedelta(days=i)
        session.add(
            DailyPrice(
                stock_id=stock_id,
                date=d,
                close=base_close + i,
                high=base_close + i + 1,
                low=base_close + i - 1,
                volume=1_000_000,
            )
        )
    session.commit()


svc = EntryTimingResearchService()


class TestLoadHistoryNewestFirst:
    def test_LH01_returns_newest_90_not_oldest(self, session):
        """With 150 bars, limit(90) must return rows 61-150 (newest 90), not rows 1-90."""
        stock_id = "LH01"
        start = date(2023, 1, 1)
        _add_bars(session, stock_id, start, 150)
        as_of = start + timedelta(days=149)

        df = svc._load_history(session, stock_id, as_of, lookback=90)

        assert df is not None
        assert len(df) == 90
        # Oldest bar in result should be row 61 (0-indexed 60) = start + 60 days
        expected_oldest = start + timedelta(days=60)
        assert df.iloc[0]["date"] == expected_oldest, (
            f"Oldest returned bar: {df.iloc[0]['date']}, expected {expected_oldest}. "
            "ASC+LIMIT bug may still be present."
        )

    def test_LH02_last_row_equals_as_of(self, session):
        """The last (most recent) row date must equal as_of."""
        stock_id = "LH02"
        start = date(2024, 1, 1)
        _add_bars(session, stock_id, start, 120)
        as_of = start + timedelta(days=119)

        df = svc._load_history(session, stock_id, as_of, lookback=90)

        assert df is not None
        assert df.iloc[-1]["date"] == as_of

    def test_LH03_chronological_order(self, session):
        """Returned rows must be strictly ascending by date."""
        stock_id = "LH03"
        start = date(2024, 6, 1)
        _add_bars(session, stock_id, start, 95)
        as_of = start + timedelta(days=94)

        df = svc._load_history(session, stock_id, as_of, lookback=90)

        dates = df["date"].tolist()
        assert dates == sorted(dates), "Rows not in chronological order"

    def test_LH04_cross_year_boundary(self, session):
        """Cross-year bars are handled correctly (Dec → Jan)."""
        stock_id = "LH04"
        start = date(2023, 10, 1)  # starts Oct 2023
        _add_bars(session, stock_id, start, 120)  # runs into early 2024
        as_of = start + timedelta(days=119)

        df = svc._load_history(session, stock_id, as_of, lookback=90)

        assert df is not None
        assert len(df) == 90
        # newest bar should be as_of
        assert df.iloc[-1]["date"] == as_of
        # oldest bar should be 90 bars back
        assert df.iloc[0]["date"] == as_of - timedelta(days=89)

    def test_LH05_no_future_data(self, session):
        """Bars after as_of must never appear even if they exist in the DB."""
        stock_id = "LH05"
        start = date(2025, 1, 1)
        _add_bars(session, stock_id, start, 200)  # lots of bars including future

        # as_of is 100 days in
        as_of = start + timedelta(days=99)
        df = svc._load_history(session, stock_id, as_of, lookback=90)

        assert df is not None
        assert all(row <= as_of for row in df["date"])

    def test_LH06_fewer_bars_than_lookback(self, session):
        """When fewer bars than lookback exist, return all in chronological order."""
        stock_id = "LH06"
        start = date(2026, 1, 1)
        _add_bars(session, stock_id, start, 30)
        as_of = start + timedelta(days=29)

        df = svc._load_history(session, stock_id, as_of, lookback=90)

        assert df is not None
        assert len(df) == 30
        assert df.iloc[-1]["date"] == as_of

    def test_LH07_empty_stock_returns_none(self, session):
        """Stock with no price data returns None, not empty DataFrame."""
        df = svc._load_history(session, "NONEXISTENT", date(2026, 6, 1), lookback=90)
        assert df is None

    def test_LH08_as_of_on_gap_day(self, session):
        """When as_of is not in DB, the most recent bar before as_of is last row."""
        stock_id = "LH08"
        start = date(2025, 3, 1)
        # Insert every other day (simulating non-trading days skipped)
        for i in range(60):
            d = start + timedelta(days=i * 2)  # every 2 days
            session.add(
                DailyPrice(
                    stock_id=stock_id,
                    date=d,
                    close=100.0 + i,
                    high=101.0 + i,
                    low=99.0 + i,
                    volume=1_000_000,
                )
            )
        session.commit()

        # as_of falls on an odd day (not in DB)
        last_bar_date = start + timedelta(days=118)  # last even-day bar
        as_of = start + timedelta(days=119)          # odd day — not in DB

        df = svc._load_history(session, stock_id, as_of, lookback=30)

        assert df is not None
        assert df.iloc[-1]["date"] == last_bar_date  # stops at last available bar
        assert all(row <= as_of for row in df["date"])
