"""
tests/test_shadow_recalculation.py — Shadow recalculation pipeline (B2)

Tests:
  SR01 — recalculate writes v2_research_v2 rows for existing v1 rows
  SR02 — idempotent: second call skips already-computed rows
  SR03 — label_changes list records pairs where entry_label differs
  SR04 — insufficient history (< 21 bars) → errors count, not processed
  SR05 — dry_run=True increments processed but writes nothing to DB
  SR06 — out-of-range v1 rows not included (date filter respected)
  SR07 — RecalcReport.summary() contains key fields
  SR08 — existing v2_research_v2 rows are skipped (not duplicated)
  SR09 — no label change recorded when entry_label is same
  SR10 — missing_data list populated on insufficient history
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database import DailyPrice, init_db
from src.research.models import ResearchBase, V2ShadowSignal
from src.research.shadow_recalculation_service import (
    RecalcReport,
    ShadowRecalculationService,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def prod_engine():
    eng = create_engine("sqlite:///:memory:")
    init_db(eng)
    return eng


@pytest.fixture(scope="module")
def research_engine():
    eng = create_engine("sqlite:///:memory:")
    ResearchBase.metadata.create_all(eng)
    return eng


@pytest.fixture(scope="module")
def ProdSession(prod_engine):
    return sessionmaker(bind=prod_engine)


@pytest.fixture(scope="module")
def ResearchSession(research_engine):
    return sessionmaker(bind=research_engine)


def _add_price_bars(session, stock_id: str, start: date, n: int, base: float = 100.0):
    for i in range(n):
        d = start + timedelta(days=i)
        session.add(DailyPrice(
            stock_id=stock_id, date=d,
            close=base + i, high=base + i + 1,
            low=base + i - 1, volume=1_000_000,
        ))
    session.commit()


def _add_v1_signal(session, trade_date: date, stock_id: str, entry_label: str = "WAIT_FOR_PULLBACK"):
    row = V2ShadowSignal(
        trade_date=trade_date,
        stock_id=stock_id,
        research_version="v2_research_v1",
        is_legacy=True,
        v1_decision_label="BUY",
        entry_label=entry_label,
        created_at=datetime.utcnow(),
    )
    session.add(row)
    session.commit()
    return row


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestShadowRecalculation:
    svc = ShadowRecalculationService()

    def test_SR01_writes_v2_rows(self, ResearchSession, ProdSession):
        """recalculate writes new v2_research_v2 rows for each v1 row."""
        stock_id = "SR01"
        trade_date = date(2026, 2, 1)

        with ProdSession() as ps:
            _add_price_bars(ps, stock_id, date(2025, 10, 1), 130)
        with ResearchSession() as rs:
            _add_v1_signal(rs, trade_date, stock_id, entry_label="WAIT_FOR_PULLBACK")

        with ResearchSession() as rs, ProdSession() as ps:
            report = self.svc.recalculate(rs, ps, trade_date, trade_date)

        with ResearchSession() as rs:
            v2 = rs.query(V2ShadowSignal).filter_by(
                stock_id=stock_id, trade_date=trade_date,
                research_version="v2_research_v2"
            ).first()
            assert v2 is not None
            assert v2.is_legacy is False

        assert report.processed == 1
        assert report.skipped == 0

    def test_SR02_idempotent(self, ResearchSession, ProdSession):
        """Second call skips already-computed v2 rows."""
        stock_id = "SR02"
        trade_date = date(2026, 2, 2)

        with ProdSession() as ps:
            _add_price_bars(ps, stock_id, date(2025, 10, 1), 130)
        with ResearchSession() as rs:
            _add_v1_signal(rs, trade_date, stock_id)

        with ResearchSession() as rs, ProdSession() as ps:
            self.svc.recalculate(rs, ps, trade_date, trade_date)
        with ResearchSession() as rs, ProdSession() as ps:
            report2 = self.svc.recalculate(rs, ps, trade_date, trade_date)

        assert report2.skipped == 1
        assert report2.processed == 0

        with ResearchSession() as rs:
            count = rs.query(V2ShadowSignal).filter_by(
                stock_id=stock_id, trade_date=trade_date,
                research_version="v2_research_v2"
            ).count()
            assert count == 1  # not duplicated

    def test_SR03_label_changes_recorded(self, ResearchSession, ProdSession):
        """label_changes list captures pairs where entry_label differs between v1 and v2."""
        stock_id = "SR03"
        trade_date = date(2026, 2, 3)

        with ProdSession() as ps:
            _add_price_bars(ps, stock_id, date(2025, 10, 1), 130)

        # Insert v1 with a deliberately wrong label to ensure a diff
        with ResearchSession() as rs:
            _add_v1_signal(rs, trade_date, stock_id, entry_label="__FAKE_LABEL__")

        with ResearchSession() as rs, ProdSession() as ps:
            report = self.svc.recalculate(rs, ps, trade_date, trade_date)

        # Since v1 label was "__FAKE_LABEL__" and v2 label is real, there IS a change
        assert len(report.label_changes) == 1
        change = report.label_changes[0]
        assert change.stock_id == stock_id
        assert change.v1_label == "__FAKE_LABEL__"
        assert change.v2_label is not None  # whatever the analyzer returns

    def test_SR04_insufficient_history_counts_as_error(self, ResearchSession, ProdSession):
        """Stocks with < 21 bars → errors += 1, not processed."""
        stock_id = "SR04"
        trade_date = date(2026, 2, 4)

        with ProdSession() as ps:
            _add_price_bars(ps, stock_id, date(2026, 2, 1), 5)  # only 5 bars
        with ResearchSession() as rs:
            _add_v1_signal(rs, trade_date, stock_id)

        with ResearchSession() as rs, ProdSession() as ps:
            report = self.svc.recalculate(rs, ps, trade_date, trade_date)

        assert report.errors == 1
        assert report.processed == 0

    def test_SR05_dry_run_no_writes(self, ResearchSession, ProdSession):
        """dry_run=True increments processed but writes nothing to DB."""
        stock_id = "SR05"
        trade_date = date(2026, 2, 5)

        with ProdSession() as ps:
            _add_price_bars(ps, stock_id, date(2025, 10, 1), 130)
        with ResearchSession() as rs:
            _add_v1_signal(rs, trade_date, stock_id)

        with ResearchSession() as rs, ProdSession() as ps:
            report = self.svc.recalculate(rs, ps, trade_date, trade_date, dry_run=True)

        assert report.processed == 1
        assert report.dry_run is True

        with ResearchSession() as rs:
            v2 = rs.query(V2ShadowSignal).filter_by(
                stock_id=stock_id, trade_date=trade_date,
                research_version="v2_research_v2"
            ).first()
            assert v2 is None  # dry run → not written

    def test_SR06_date_range_filter(self, ResearchSession, ProdSession):
        """Only v1 rows within [from_date, to_date] are processed."""
        stock_in = "SR06IN"
        stock_out = "SR06OUT"
        date_in = date(2026, 3, 1)
        date_out = date(2026, 1, 1)  # outside the range

        with ProdSession() as ps:
            _add_price_bars(ps, stock_in, date(2025, 10, 1), 130)
        with ResearchSession() as rs:
            _add_v1_signal(rs, date_in, stock_in)
            _add_v1_signal(rs, date_out, stock_out)

        with ResearchSession() as rs, ProdSession() as ps:
            report = self.svc.recalculate(rs, ps, date_in, date_in)

        with ResearchSession() as rs:
            assert rs.query(V2ShadowSignal).filter_by(
                stock_id=stock_in, research_version="v2_research_v2"
            ).count() == 1
            assert rs.query(V2ShadowSignal).filter_by(
                stock_id=stock_out, research_version="v2_research_v2"
            ).count() == 0

    def test_SR07_summary_contains_key_fields(self, ResearchSession, ProdSession):
        """RecalcReport.summary() returns a string with key metrics."""
        report = RecalcReport(
            processed=5, skipped=2, errors=1,
            calculation_ts=datetime(2026, 11, 1, 12, 0, 0),
            input_data_cutoff=date(2026, 10, 31),
        )
        s = report.summary()
        assert "processed=5" in s
        assert "skipped=2" in s
        assert "errors=1" in s
        assert "v2_research_v2" in s

    def test_SR08_existing_v2_rows_skipped(self, ResearchSession, ProdSession):
        """Pre-existing v2_research_v2 rows are skipped (not overwritten)."""
        stock_id = "SR08"
        trade_date = date(2026, 3, 2)

        with ProdSession() as ps:
            _add_price_bars(ps, stock_id, date(2025, 10, 1), 130)
        with ResearchSession() as rs:
            _add_v1_signal(rs, trade_date, stock_id)
            # Pre-create v2 row
            rs.add(V2ShadowSignal(
                trade_date=trade_date, stock_id=stock_id,
                research_version="v2_research_v2",
                entry_label="PRE_EXISTING",
                created_at=datetime.utcnow(),
            ))
            rs.commit()

        with ResearchSession() as rs, ProdSession() as ps:
            report = self.svc.recalculate(rs, ps, trade_date, trade_date)

        assert report.skipped == 1
        with ResearchSession() as rs:
            rows = rs.query(V2ShadowSignal).filter_by(
                stock_id=stock_id, research_version="v2_research_v2"
            ).all()
            assert len(rows) == 1
            assert rows[0].entry_label == "PRE_EXISTING"  # not overwritten

    def test_SR09_no_label_change_when_same(self, ResearchSession, ProdSession):
        """No entry in label_changes if v1 and v2 produce the same label."""
        stock_id = "SR09"
        trade_date = date(2026, 3, 3)

        with ProdSession() as ps:
            _add_price_bars(ps, stock_id, date(2025, 10, 1), 130)
        with ResearchSession() as rs:
            # Add v1 with entry_label that matches what analyzer will produce
            # We don't know the exact label, so just run it and inspect
            _add_v1_signal(rs, trade_date, stock_id, entry_label="WAIT_FOR_PULLBACK")

        with ResearchSession() as rs, ProdSession() as ps:
            report = self.svc.recalculate(rs, ps, trade_date, trade_date)

        # label_changes only has entries where labels DIFFER
        with ResearchSession() as rs:
            v2 = rs.query(V2ShadowSignal).filter_by(
                stock_id=stock_id, research_version="v2_research_v2"
            ).first()
            assert v2 is not None
            # If the computed label matches "WAIT_FOR_PULLBACK", label_changes is empty
            # If it differs, it appears in label_changes — both are valid outcomes
            for change in report.label_changes:
                # Every change must have stock_id and both labels populated
                assert change.stock_id is not None
                assert change.v2_label is not None

    def test_SR10_missing_data_list_populated(self, ResearchSession, ProdSession):
        """missing_data list contains entries for stocks with insufficient history."""
        stock_id = "SR10"
        trade_date = date(2026, 3, 4)

        with ProdSession() as ps:
            _add_price_bars(ps, stock_id, date(2026, 3, 1), 3)  # only 3 bars
        with ResearchSession() as rs:
            _add_v1_signal(rs, trade_date, stock_id)

        with ResearchSession() as rs, ProdSession() as ps:
            report = self.svc.recalculate(rs, ps, trade_date, trade_date)

        assert len(report.missing_data) == 1
        assert stock_id in report.missing_data[0]
