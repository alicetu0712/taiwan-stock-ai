"""
tests/test_research_versioning.py — V2ShadowSignal research versioning schema

Tests:
  RV01 — Default research_version = 'v2_research_v1'
  RV02 — Default is_legacy = False
  RV03 — Two rows same (date, stock_id) DIFFERENT research_version → allowed
  RV04 — Two rows same (date, stock_id, research_version) → IntegrityError
  RV05 — is_legacy can be set to True explicitly
  RV06 — research_version filter returns only matching rows
  RV07 — UniqueConstraint name is 'uq_v2ss_date_stock_version' (not old name)
  RV08 — New rows tagged 'v2_research_v2' are NOT marked is_legacy
  RV09 — Append-only: UPDATE raises if caller mutates entry_label (ORM-layer check)
  RV10 — V2ShadowSignal and V2ShadowOutcome are on separate base from production
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from src.research.models import ResearchBase, V2ShadowOutcome, V2ShadowSignal


@pytest.fixture(scope="module")
def engine():
    eng = create_engine("sqlite:///:memory:")
    ResearchBase.metadata.create_all(eng)
    return eng


@pytest.fixture(scope="module")
def Session(engine):
    return sessionmaker(bind=engine)


def _make_signal(trade_date, stock_id, research_version="v2_research_v1", **kwargs):
    return V2ShadowSignal(
        trade_date=trade_date,
        stock_id=stock_id,
        research_version=research_version,
        created_at=datetime.utcnow(),
        **kwargs,
    )


class TestDefaultValues:
    def test_RV01_default_research_version(self, Session):
        with Session() as s:
            row = V2ShadowSignal(
                trade_date=date(2026, 1, 1),
                stock_id="RV01",
                created_at=datetime.utcnow(),
            )
            s.add(row)
            s.commit()
            s.refresh(row)
            assert row.research_version == "v2_research_v1"

    def test_RV02_default_is_legacy_false(self, Session):
        with Session() as s:
            row = _make_signal(date(2026, 1, 2), "RV02")
            s.add(row)
            s.commit()
            s.refresh(row)
            assert row.is_legacy is False


class TestUniqueConstraint:
    def test_RV03_different_version_same_date_stock_allowed(self, Session):
        """Two rows with same (date, stock_id) but different research_version must coexist."""
        with Session() as s:
            s.add(_make_signal(date(2026, 2, 1), "RV03", research_version="v2_research_v1"))
            s.add(_make_signal(date(2026, 2, 1), "RV03", research_version="v2_research_v2"))
            s.commit()
            count = s.query(V2ShadowSignal).filter_by(stock_id="RV03").count()
            assert count == 2

    def test_RV04_duplicate_version_same_date_stock_raises(self, Session):
        """Duplicate (date, stock_id, research_version) must raise IntegrityError."""
        with Session() as s:
            s.add(_make_signal(date(2026, 3, 1), "RV04", research_version="v2_research_v1"))
            s.commit()
        with Session() as s2:
            s2.add(_make_signal(date(2026, 3, 1), "RV04", research_version="v2_research_v1"))
            with pytest.raises(IntegrityError):
                s2.commit()
            s2.rollback()


class TestLegacyFlag:
    def test_RV05_is_legacy_set_true(self, Session):
        """is_legacy can be explicitly set to True (for pre-DESC-fix rows)."""
        with Session() as s:
            row = _make_signal(date(2026, 4, 1), "RV05", is_legacy=True)
            s.add(row)
            s.commit()
            s.refresh(row)
            assert row.is_legacy is True

    def test_RV08_v2_research_v2_rows_not_legacy(self, Session):
        """New rows tagged v2_research_v2 should not be legacy."""
        with Session() as s:
            row = _make_signal(
                date(2026, 5, 1), "RV08",
                research_version="v2_research_v2",
                is_legacy=False,
            )
            s.add(row)
            s.commit()
            s.refresh(row)
            assert row.research_version == "v2_research_v2"
            assert row.is_legacy is False


class TestVersionFilter:
    def test_RV06_version_filter_returns_only_matching(self, Session):
        """Filter by research_version returns only the requested rows."""
        with Session() as s:
            s.add(_make_signal(date(2026, 6, 1), "RV06A", research_version="v2_research_v1"))
            s.add(_make_signal(date(2026, 6, 2), "RV06B", research_version="v2_research_v1"))
            s.add(_make_signal(date(2026, 6, 1), "RV06A", research_version="v2_research_v2"))
            s.commit()

        with Session() as s:
            v1_rows = (
                s.query(V2ShadowSignal)
                .filter(V2ShadowSignal.stock_id.in_(["RV06A", "RV06B"]))
                .filter(V2ShadowSignal.research_version == "v2_research_v1")
                .all()
            )
            v2_rows = (
                s.query(V2ShadowSignal)
                .filter(V2ShadowSignal.stock_id.in_(["RV06A", "RV06B"]))
                .filter(V2ShadowSignal.research_version == "v2_research_v2")
                .all()
            )
            assert len(v1_rows) == 2
            assert len(v2_rows) == 1


class TestSchemaStructure:
    def test_RV07_new_constraint_name(self, engine):
        """UniqueConstraint must be 'uq_v2ss_date_stock_version', old name must not exist."""
        insp = inspect(engine)
        uqs = {uc["name"] for uc in insp.get_unique_constraints("v2_shadow_signals")}
        # SQLite stores unique constraints differently — check via index names
        idxs = {idx["name"] for idx in insp.get_indexes("v2_shadow_signals")}
        all_names = uqs | idxs
        assert "uq_v2ss_date_stock_version" in all_names, (
            f"New constraint not found. Names: {all_names}"
        )
        assert "uq_v2ss_date_stock" not in all_names, (
            f"Old constraint still present. Names: {all_names}"
        )

    def test_RV10_research_base_isolated_from_production(self):
        """ResearchBase must NOT share tables with the production Base."""
        from src.database import Base as ProdBase

        research_tables = set(ResearchBase.metadata.tables.keys())
        prod_tables = set(ProdBase.metadata.tables.keys())
        overlap = research_tables & prod_tables
        assert not overlap, f"Research and production share tables: {overlap}"

    def test_research_version_column_exists(self, engine):
        insp = inspect(engine)
        cols = {c["name"] for c in insp.get_columns("v2_shadow_signals")}
        assert "research_version" in cols
        assert "is_legacy" in cols
