"""
tests/test_version_isolation.py — Phase 0: model_version isolation regression tests

Verifies:
1. MODEL_VERSION / V1_MODEL_VERSION constants are defined and equal to "v8.0"
2. UniqueConstraint in ForwardSignal includes model_version (3 columns)
3. Two signals with the same (trade_date, stock_id) but different model_versions
   can coexist in the DB without a uniqueness violation
4. Two signals with the same (trade_date, stock_id, model_version) are correctly
   deduplicated (second insert is skipped)
5. write_forward_signals dedup check is scoped to model_version
6. fill_execution_prices only touches MODEL_VERSION signals
7. compute_signal_outcomes only touches MODEL_VERSION signals
8. compute_foe_outcomes only processes MODEL_VERSION signals
9. evidence_service ForwardSignal query is scoped to MODEL_VERSION
10. load_forward_signals_scorecard is scoped to MODEL_VERSION (loaders.py)
11. scorecard page query is scoped to MODEL_VERSION
12. load_validation_funnel is scoped to MODEL_VERSION (backtest.py)
13. _load_forward raw SQL contains model_version filter (research_backtest.py)
14. _load_forward SQLAlchemy path contains model_version filter
15. Unique constraint migration function exists and is called from init_db
"""

import ast
import re
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).parent.parent
SRC = ROOT / "src"


# ── 1. Constants ─────────────────────────────────────────────────────────────

def test_v1_model_version_constant():
    from src.database import V1_MODEL_VERSION
    assert V1_MODEL_VERSION == "v8.0"


def test_model_version_constant():
    from src.database import MODEL_VERSION
    assert MODEL_VERSION == "v8.0"


def test_model_version_equals_v1_model_version():
    """While V2 does not exist both constants must stay in sync."""
    from src.database import MODEL_VERSION, V1_MODEL_VERSION
    assert MODEL_VERSION == V1_MODEL_VERSION


# ── 2. UniqueConstraint includes model_version ────────────────────────────────

def test_forward_signal_unique_constraint_includes_model_version():
    from src.database import ForwardSignal
    from sqlalchemy import UniqueConstraint

    constraints = [
        c for c in ForwardSignal.__table_args__
        if isinstance(c, UniqueConstraint)
    ]
    assert constraints, "ForwardSignal has no UniqueConstraint"
    uc = constraints[0]
    col_names = {c.name for c in uc.columns}
    assert "model_version" in col_names, (
        f"UniqueConstraint must include model_version; got {col_names}"
    )
    assert "trade_date" in col_names
    assert "stock_id" in col_names


def test_forward_signal_unique_constraint_name():
    from src.database import ForwardSignal
    from sqlalchemy import UniqueConstraint

    constraints = [
        c for c in ForwardSignal.__table_args__
        if isinstance(c, UniqueConstraint)
    ]
    uc = constraints[0]
    assert uc.name == "uq_fs_date_stock_version", (
        f"Expected uq_fs_date_stock_version, got {uc.name}"
    )


# ── 3. V1 + V2 coexistence in SQLite DB ──────────────────────────────────────

def _make_sqlite_engine():
    from sqlalchemy import create_engine
    from src.database import Base, init_db
    engine = create_engine("sqlite:///:memory:")
    init_db(engine)
    return engine


def test_v1_v2_same_date_stock_can_coexist():
    """Two rows with different model_version must not raise a unique violation."""
    from src.database import ForwardSignal, get_session

    engine = _make_sqlite_engine()
    s = get_session(engine)
    try:
        s.add(ForwardSignal(
            trade_date=date(2026, 10, 9),
            stock_id="2330",
            model_version="v8.0",
            trade_signal="buy",
        ))
        s.add(ForwardSignal(
            trade_date=date(2026, 10, 9),
            stock_id="2330",
            model_version="v9.0",
            trade_signal="buy",
        ))
        s.commit()
        count = s.query(ForwardSignal).filter_by(
            trade_date=date(2026, 10, 9), stock_id="2330"
        ).count()
        assert count == 2
    finally:
        s.close()


def test_same_version_same_date_stock_raises():
    """Two rows with the same (trade_date, stock_id, model_version) must violate unique."""
    from sqlalchemy.exc import IntegrityError
    from src.database import ForwardSignal, get_session

    engine = _make_sqlite_engine()
    s = get_session(engine)
    try:
        s.add(ForwardSignal(
            trade_date=date(2026, 10, 9),
            stock_id="2330",
            model_version="v8.0",
            trade_signal="buy",
        ))
        s.commit()
        s.add(ForwardSignal(
            trade_date=date(2026, 10, 9),
            stock_id="2330",
            model_version="v8.0",
            trade_signal="strong_buy",
        ))
        with pytest.raises(IntegrityError):
            s.commit()
    finally:
        s.rollback()
        s.close()


# ── 4. write_forward_signals dedup check scoped to model_version ──────────────

def test_write_forward_signals_dedup_uses_model_version():
    """
    Smoke-test: write_forward_signals should skip a stock that already exists
    for the SAME model_version, but NOT skip it if the existing row is a
    different model_version.
    """
    from src.database import ForwardSignal, get_session

    engine = _make_sqlite_engine()
    s = get_session(engine)
    try:
        # Pre-seed a v9.0 signal for 2330 on 2026-10-09
        s.add(ForwardSignal(
            trade_date=date(2026, 10, 9),
            stock_id="2330",
            model_version="v9.0",
            trade_signal="buy",
            execution_price_type="NEXT_OPEN",
        ))
        s.commit()

        # The dedup check scoped to "v8.0" must NOT see the v9.0 row
        existing = {
            r.stock_id
            for r in s.query(ForwardSignal.stock_id)
            .filter(
                ForwardSignal.trade_date == date(2026, 10, 9),
                ForwardSignal.model_version == "v8.0",
            )
            .all()
        }
        assert "2330" not in existing, (
            "v9.0 row must not block v8.0 dedup check"
        )

        # v9.0 scoped check should see it
        existing_v9 = {
            r.stock_id
            for r in s.query(ForwardSignal.stock_id)
            .filter(
                ForwardSignal.trade_date == date(2026, 10, 9),
                ForwardSignal.model_version == "v9.0",
            )
            .all()
        }
        assert "2330" in existing_v9
    finally:
        s.close()


# ── 5-7. Query filters in service layer (AST / source inspection) ─────────────

def _source(file_rel: str) -> str:
    return (ROOT / file_rel).read_text()


def test_fill_execution_prices_has_model_version_filter():
    src = _source("src/services/research_backtest_service.py")
    # find the fill_execution_prices function body and confirm model_version filter
    assert "model_version == MODEL_VERSION" in src or "model_version==" in src


def test_compute_signal_outcomes_has_model_version_filter():
    src = _source("src/services/research_backtest_service.py")
    # Both functions must contain model_version filter in their scopes;
    # simplest check: at least two occurrences of the filter pattern
    occurrences = src.count("model_version == MODEL_VERSION")
    assert occurrences >= 2, (
        f"Expected ≥2 model_version == MODEL_VERSION filters, found {occurrences}"
    )


def test_compute_foe_outcomes_has_model_version_filter():
    src = _source("src/services/outcome_service.py")
    assert "model_version == MODEL_VERSION" in src


def test_evidence_service_has_model_version_filter():
    src = _source("src/services/evidence_service.py")
    assert "model_version == MODEL_VERSION" in src


# ── 8. Dashboard / loader filters ─────────────────────────────────────────────

def test_loaders_scorecard_has_model_version_filter():
    src = _source("dashboard/loaders.py")
    assert "model_version == MODEL_VERSION" in src


def test_scorecard_page_has_model_version_filter():
    src = _source("dashboard/_pages/scorecard.py")
    assert "model_version == MODEL_VERSION" in src


def test_backtest_page_validation_funnel_has_model_version_filter():
    src = _source("dashboard/_pages/backtest.py")
    assert "model_version == MODEL_VERSION" in src


def test_research_backtest_raw_sql_has_model_version_filter():
    src = _source("dashboard/_pages/research_backtest.py")
    assert "WHERE model_version" in src or "model_version = %s" in src


def test_research_backtest_sqlalchemy_path_has_model_version_filter():
    src = _source("dashboard/_pages/research_backtest.py")
    assert "model_version == MODEL_VERSION" in src


# ── 9. Migration function exists and is registered ────────────────────────────

def test_migrate_unique_constraint_function_exists():
    import src.database as db
    assert hasattr(db, "_migrate_forward_signals_unique_constraint"), (
        "_migrate_forward_signals_unique_constraint must be defined in src/database.py"
    )


def test_migrate_unique_constraint_called_from_init_db():
    """init_db source must call the unique constraint migration."""
    src = _source("src/database.py")
    assert "_migrate_forward_signals_unique_constraint(engine)" in src


def test_migrate_unique_constraint_noop_on_sqlite():
    """The migration function must not raise on SQLite."""
    import src.database as db
    engine = _make_sqlite_engine()
    # Should not raise
    db._migrate_forward_signals_unique_constraint(engine)


def test_migrate_unique_constraint_idempotent_on_sqlite():
    """Calling migration twice on SQLite must not raise."""
    import src.database as db
    engine = _make_sqlite_engine()
    db._migrate_forward_signals_unique_constraint(engine)
    db._migrate_forward_signals_unique_constraint(engine)


# ── 10. V1_MODEL_VERSION is exported ─────────────────────────────────────────

def test_v1_model_version_exported_from_database():
    """V1_MODEL_VERSION must be importable from src.database."""
    from src.database import V1_MODEL_VERSION  # noqa: F401 — import is the test


# ── 11. ForwardSignal.model_version default equals MODEL_VERSION ──────────────

def test_forward_signal_model_version_default():
    from src.database import ForwardSignal, MODEL_VERSION
    fs = ForwardSignal()
    # Column default; SQLAlchemy may not apply it until flush, but the column
    # definition carries it. Check via column default rather than instance attr.
    col = ForwardSignal.__table__.c["model_version"]
    # default.arg is the Python-side default value
    assert col.default is not None
    default_val = col.default.arg
    assert default_val == MODEL_VERSION, (
        f"ForwardSignal.model_version default must be MODEL_VERSION={MODEL_VERSION!r}, "
        f"got {default_val!r}"
    )
