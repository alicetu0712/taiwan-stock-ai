"""
tests/test_production_reliability.py — Production Reliability Regression Tests

Covers:
  M1  _verify_schema_integrity raises on missing required column
  M2  _verify_schema_integrity passes on complete schema
  M3  _safe_add_cols is idempotent (second call is no-op, no data loss)
  S1  _reset_pg_sequences raises RuntimeError when sequence reset fails
  S2  _reset_pg_sequences skips tables that do not exist (fresh DB scenario)
  S3  sync_table second sync does not duplicate rows (dedup correctness)
  F1  write_forward_signals populates _last_fs_diagnosis with gate_rejected for L1
  F2  write_forward_signals populates _last_fs_diagnosis with gate_rejected for L2a
  F3  write_forward_signals populates _last_fs_diagnosis with all_dedup on second insert
  F4  write_forward_signals populates _last_fs_diagnosis with ok on fresh insert
"""

from datetime import date
from unittest.mock import MagicMock, patch, call

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_sqlite(init: bool = True):
    """Return an in-memory SQLite engine, optionally initialised."""
    engine = create_engine("sqlite:///:memory:")
    if init:
        from src.database import Base, init_db
        init_db(engine)
    return engine


# ── M1-M3: Migration Fail-Closed ─────────────────────────────────────────────

class TestMigrationFailClosed:

    def test_M1_missing_required_column_raises(self):
        """M1: _verify_schema_integrity raises RuntimeError when required column absent."""
        from src.database import _verify_schema_integrity, Base

        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)

        # Recreate forward_signals without is_valid to simulate a migration gap.
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS forward_signals"))
            conn.execute(text(
                "CREATE TABLE forward_signals ("
                "id INTEGER PRIMARY KEY, "
                "trade_date DATE NOT NULL, "
                "stock_id VARCHAR(10) NOT NULL"
                ")"
            ))

        with pytest.raises(RuntimeError, match="is_valid"):
            _verify_schema_integrity(engine)

    def test_M2_complete_schema_passes(self):
        """M2: _verify_schema_integrity passes after normal init_db()."""
        from src.database import _verify_schema_integrity

        engine = _make_sqlite(init=True)
        # Should not raise
        _verify_schema_integrity(engine)

    def test_M3_safe_add_cols_idempotent(self):
        """M3: calling _safe_add_cols twice with the same column list is a no-op."""
        from src.database import _safe_add_cols, Base

        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)

        new_cols = [("test_col_idempotent", "INTEGER DEFAULT 0")]
        _safe_add_cols(engine, "analysis_results", new_cols)
        _safe_add_cols(engine, "analysis_results", new_cols)  # second call — should not raise

        from sqlalchemy import inspect as _insp
        cols = {c["name"] for c in _insp(engine).get_columns("analysis_results")}
        assert "test_col_idempotent" in cols

    def test_M3_idempotent_does_not_destroy_data(self):
        """M3b: re-running migration does not alter existing rows."""
        from src.database import Base, AnalysisResult

        engine = _make_sqlite(init=True)
        Session = sessionmaker(bind=engine)
        s = Session()
        ar = AnalysisResult(stock_id="2330", date=date(2026, 10, 29), total_score=80.0)
        s.add(ar); s.commit()
        row_id = ar.id
        s.close()

        # Re-run all migrations
        from src.database import init_db
        init_db(engine)

        s2 = Session()
        reloaded = s2.query(AnalysisResult).filter_by(id=row_id).first()
        assert reloaded is not None, "Row must survive re-migration"
        assert reloaded.total_score == 80.0
        s2.close()


# ── S1-S3: Sequence Integrity ─────────────────────────────────────────────────

class TestSequenceIntegrity:

    def test_S1_reset_raises_on_existing_table_failure(self):
        """S1: _reset_pg_sequences raises RuntimeError when setval fails on an existing table."""
        from scripts.sync_to_neon import _reset_pg_sequences

        # Build a mock engine that reports the table as existing but fails on setval.
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        # pg_tables query returns analysis_results as existing
        mock_conn.execute.side_effect = _make_selective_pg_execute(
            existing_tables={"analysis_results"},
            fail_on_setval=True,
        )

        mock_engine = MagicMock()
        mock_engine.connect.return_value = mock_conn
        mock_engine.dialect.name = "postgresql"

        with pytest.raises(RuntimeError, match="Sequence reset FAILED"):
            _reset_pg_sequences(mock_engine)

    def test_S2_skips_nonexistent_table_silently(self):
        """S2: _reset_pg_sequences silently skips tables not yet created."""
        from scripts.sync_to_neon import _reset_pg_sequences

        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.side_effect = _make_selective_pg_execute(
            existing_tables=set(),  # no tables exist
            fail_on_setval=False,
        )

        mock_engine = MagicMock()
        mock_engine.connect.return_value = mock_conn

        # Should not raise
        _reset_pg_sequences(mock_engine)

    def test_S3_sync_no_duplicate_on_second_run(self):
        """S3: sync_table on the same data twice produces exactly 1 row in destination."""
        from src.database import AnalysisResult, Base
        from scripts.sync_to_neon import sync_table

        src = create_engine("sqlite:///:memory:")
        dst = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(src)
        Base.metadata.create_all(dst)

        SrcS = sessionmaker(bind=src)
        DstS = sessionmaker(bind=dst)

        s = SrcS()
        s.add(AnalysisResult(stock_id="2330", date=date(2026, 10, 20), total_score=70.0))
        s.commit(); s.close()

        for _ in range(2):
            ss, ds = SrcS(), DstS()
            sync_table(ss, ds, AnalysisResult, key_fields=["stock_id", "date"], days=365)
            ss.close(); ds.close()

        ds = DstS()
        cnt = ds.query(AnalysisResult).filter_by(stock_id="2330", date=date(2026, 10, 20)).count()
        assert cnt == 1, f"Expected 1 row after two syncs, got {cnt}"
        ds.close()


# ── Mock helpers for sequence tests ─────────────────────────────────────────

def _make_selective_pg_execute(existing_tables: set, fail_on_setval: bool):
    """
    Returns a side_effect callable for mock_conn.execute that:
    - Returns existing_tables for the pg_tables query
    - Returns a scalar MAX(id) = 0 for SELECT COALESCE(MAX(id), 0)
    - Raises Exception for setval if fail_on_setval=True
    """
    call_count = [0]

    def _execute(stmt, *args, **kwargs):
        stmt_str = str(stmt)
        # pg_tables query
        if "pg_tables" in stmt_str:
            mock_result = MagicMock()
            mock_result.fetchall.return_value = [(t,) for t in existing_tables]
            return mock_result
        # MAX(id) query
        if "MAX(id)" in stmt_str or "COALESCE" in stmt_str:
            mock_result = MagicMock()
            mock_result.scalar.return_value = 0
            return mock_result
        # setval
        if "setval" in stmt_str.lower():
            if fail_on_setval:
                raise Exception("permission denied for sequence analysis_results_id_seq")
            return MagicMock()
        return MagicMock()

    return _execute


# ── F1-F4: Forward Signal Integrity ──────────────────────────────────────────

class TestForwardSignalDiagnosis:
    """Verify _last_fs_diagnosis is correctly populated for each write_forward_signals path."""

    def _base_engine(self):
        return _make_sqlite(init=True)

    def _session(self, engine):
        return sessionmaker(bind=engine)()

    def _seed_gates(self, session, trade_date: date, include_0050: bool = True):
        """Seed DailyPrice + Stock rows to satisfy L2a and L3 gates.

        L2 now counts DISTINCT analysis-universe stocks (joined to Stock table),
        so we must add Stock rows alongside DailyPrice rows.
        """
        from src.database import DailyPrice, Stock
        for i in range(1, 250):
            sid = str(1000 + i)
            session.add(Stock(stock_id=sid, name=f"Seed_{sid}", market="TWSE"))
            session.add(DailyPrice(stock_id=sid, date=trade_date, close=100.0))
        if include_0050:
            session.add(DailyPrice(stock_id="0050", date=trade_date, close=80.0))
        session.commit()

    def test_F1_gate_L1_non_trading_day(self):
        """F1: L1 gate rejection sets status='gate_rejected', gate_rejected_by='L1'."""
        import src.services.research_backtest_service as svc

        engine = self._base_engine()
        s = self._session(engine)

        non_trading = date(2026, 2, 7)  # Saturday
        fake_ar = MagicMock()
        fake_ar.stock_id = "2330"

        svc.write_forward_signals(s, non_trading, [fake_ar])
        diag = svc._last_fs_diagnosis

        assert diag["status"] == "gate_rejected"
        assert diag["gate_rejected_by"] == "L1"
        assert diag["inserted"] == 0
        s.close()

    def test_F2_gate_L2a_insufficient_market(self):
        """F2: L2a gate rejection (< min_count DailyPrices) → gate_rejected_by='L2a'."""
        import src.services.research_backtest_service as svc
        from src.database import DailyPrice

        engine = self._base_engine()
        s = self._session(engine)

        trade_date = date(2026, 10, 29)
        # Add only 5 stocks (below min_count of 200)
        for i in range(5):
            s.add(DailyPrice(stock_id=str(2000 + i), date=trade_date, close=50.0))
        s.commit()

        fake_ar = MagicMock()
        fake_ar.stock_id = "2330"

        svc.write_forward_signals(s, trade_date, [fake_ar])
        diag = svc._last_fs_diagnosis

        assert diag["status"] == "gate_rejected"
        assert diag["gate_rejected_by"] == "L2a"
        s.close()

    def test_F3_all_dedup_on_second_insert(self):
        """F3: second write on same trade_date + stock_id → status='all_dedup'."""
        import src.services.research_backtest_service as svc
        from src.database import DailyPrice, Stock

        engine = self._base_engine()
        s = self._session(engine)
        trade_date = date(2026, 10, 29)
        self._seed_gates(s, trade_date)

        # Add stock to DB
        s.add(Stock(stock_id="2330", name="台積電", market="TWSE"))
        s.add(DailyPrice(stock_id="2330", date=trade_date, close=700.0, open=695.0))
        s.commit()

        from tests.test_forward_signal_integrity import _make_ar
        ar = _make_ar(stock_id="2330")

        svc.write_forward_signals(s, trade_date, [ar])  # first → inserts
        svc.write_forward_signals(s, trade_date, [ar])  # second → all_dedup
        diag = svc._last_fs_diagnosis

        assert diag["status"] == "all_dedup"
        assert diag["inserted"] == 0
        assert diag["n_existing"] == 1
        s.close()

    def test_F4_ok_on_fresh_insert(self):
        """F4: fresh insert → status='ok', inserted=1."""
        import src.services.research_backtest_service as svc
        from src.database import DailyPrice, Stock

        engine = self._base_engine()
        s = self._session(engine)
        trade_date = date(2026, 10, 29)
        self._seed_gates(s, trade_date)

        s.add(Stock(stock_id="2330", name="台積電", market="TWSE"))
        s.add(DailyPrice(stock_id="2330", date=trade_date, close=700.0, open=695.0))
        s.commit()

        from tests.test_forward_signal_integrity import _make_ar
        svc.write_forward_signals(s, trade_date, [_make_ar(stock_id="2330")])
        diag = svc._last_fs_diagnosis

        assert diag["status"] == "ok"
        assert diag["inserted"] == 1
        s.close()
