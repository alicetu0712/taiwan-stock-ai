"""
tests/test_position_monitor_nullable.py — Position Monitor nullable regression

Covers the exact failure: psycopg.errors.NotNullViolation on date_entered when
creating a pending_open record in Neon PostgreSQL.

  PM-1  pending_open with date_entered=None → write succeeds
  PM-2  pending_open with entry_price=None  → write succeeds
  PM-3  open_position (confirmed) with entry_price=None → rejected at validation
  PM-4  PG migration: column IS NOT NULL    → ALTER TABLE DROP NOT NULL issued
  PM-5  PG migration: column already nullable → ALTER TABLE NOT issued (idempotent)
  PM-5b SQLite engine                        → migration is a no-op
  PM-6  create_pending_position called twice → only 1 record (idempotent)
  PM-6b activate then create               → create returns False (already active)
  PM-7  creating PositionMonitor does NOT touch forward_signals / foe rows
"""

from datetime import date
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


# ── helpers ──────────────────────────────────────────────────────────────────

_SIGNAL_DATE = date(2026, 10, 29)
_EXEC_DATE   = date(2026, 10, 30)


def _make_sqlite():
    from src.database import Base, init_db
    engine = create_engine("sqlite:///:memory:")
    init_db(engine)
    return engine


def _session(engine):
    return sessionmaker(bind=engine)()


def _create_pending(session, stock_id: str = "2603") -> bool:
    from src.engines.position_manager import create_pending_position
    return create_pending_position(
        session=session,
        stock_id=stock_id,
        stock_name="長榮",
        signal_date=_SIGNAL_DATE,
        expected_execution_date=_EXEC_DATE,
        rec_level="A",
        rec_score=72.0,
        confidence=82.0,
        target_price=200.0,
        stop_loss_price=170.0,
        target_pct=12.0,
        stop_loss_pct=-5.0,
        ai_rationale="test",
    )


def _make_pg_mock_engine(is_nullable_map: dict):
    """Return a mock engine that looks like PostgreSQL.

    is_nullable_map: {"date_entered": "NO"|"YES", "entry_price": "NO"|"YES"}
    Returns (engine, alter_calls) where alter_calls accumulates DROP NOT NULL stmts.
    """
    alter_calls: list[str] = []

    def _execute(stmt, *args, **kwargs):
        stmt_str = str(stmt)
        result = MagicMock()
        if "information_schema.columns" in stmt_str:
            # Determine which column is being queried from the bind params.
            # args[0] is a dict like {"col": "date_entered"}
            col = (args[0] if args else kwargs.get("parameters", {})).get("col", "")
            nullable_val = is_nullable_map.get(col, "YES")
            result.fetchone.return_value = (nullable_val,)
        elif "DROP NOT NULL" in stmt_str:
            alter_calls.append(stmt_str)
        return result

    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_conn.execute.side_effect = _execute

    mock_engine = MagicMock()
    mock_engine.begin.return_value = mock_conn
    mock_engine.dialect.name = "postgresql"

    return mock_engine, alter_calls


# ── PM-1 / PM-2: pending_open NULL fields ────────────────────────────────────

class TestPendingOpenNullable:

    def test_PM1_date_entered_none_accepted(self):
        """PM-1: pending_open 建立時 date_entered=None 必須成功寫入 DB。"""
        from src.database import PositionMonitor

        engine = _make_sqlite()
        s = _session(engine)
        ok = _create_pending(s, "2603")
        s.commit()

        assert ok is True
        row = s.query(PositionMonitor).filter_by(stock_id="2603").first()
        assert row is not None
        assert row.date_entered is None, (
            f"pending_open must have date_entered=None, got {row.date_entered}"
        )
        assert row.status == "pending_open"
        s.close()

    def test_PM2_entry_price_none_accepted(self):
        """PM-2: pending_open 建立時 entry_price=None 必須成功寫入 DB。"""
        from src.database import PositionMonitor

        engine = _make_sqlite()
        s = _session(engine)
        ok = _create_pending(s, "2603")
        s.commit()

        assert ok is True
        row = s.query(PositionMonitor).filter_by(stock_id="2603").first()
        assert row is not None
        assert row.entry_price is None, (
            f"pending_open must have entry_price=None, got {row.entry_price}"
        )
        s.close()

    def test_PM1_expected_execution_date_preserved(self):
        """expected_execution_date 必須保留（不得因 pending 狀態被清除）。"""
        from src.database import PositionMonitor

        engine = _make_sqlite()
        s = _session(engine)
        _create_pending(s, "2603")
        s.commit()

        row = s.query(PositionMonitor).filter_by(stock_id="2603").first()
        assert row.expected_execution_date == _EXEC_DATE
        assert row.signal_date == _SIGNAL_DATE
        s.close()


# ── PM-3: confirmed entry validates price ─────────────────────────────────────

class TestConfirmedEntryValidation:

    def test_PM3_open_position_rejects_none_entry_price(self):
        """PM-3: open_position() with entry_price=None → returns False (not written)."""
        from src.database import PositionMonitor
        from src.engines.position_manager import open_position

        engine = _make_sqlite()
        s = _session(engine)

        result = open_position(
            session=s,
            stock_id="2330",
            stock_name="台積電",
            entry_date=_SIGNAL_DATE,
            entry_price=None,      # no price
            rec_level="A",
            rec_score=80.0,
            confidence=85.0,
            target_price=1000.0,
            stop_loss_price=800.0,
            target_pct=10.0,
            stop_loss_pct=-5.0,
        )
        assert result is False, "open_position must reject None entry_price"
        # Verify nothing was written
        count = s.query(PositionMonitor).filter_by(stock_id="2330").count()
        assert count == 0
        s.close()

    def test_PM3_open_position_rejects_zero_entry_price(self):
        """PM-3b: open_position() with entry_price=0 → returns False."""
        from src.engines.position_manager import open_position

        engine = _make_sqlite()
        s = _session(engine)

        result = open_position(
            session=s,
            stock_id="2330",
            stock_name="台積電",
            entry_date=_SIGNAL_DATE,
            entry_price=0.0,
            rec_level="A",
            rec_score=80.0,
            confidence=85.0,
            target_price=1000.0,
            stop_loss_price=800.0,
            target_pct=10.0,
            stop_loss_pct=-5.0,
        )
        assert result is False
        s.close()


# ── PM-4 / PM-5: PostgreSQL nullable migration ────────────────────────────────

class TestPositionMonitorMigrationPG:

    def test_PM4_drops_not_null_when_constrained(self):
        """PM-4: PG 欄位為 NOT NULL 時，migration 應發出 ALTER TABLE DROP NOT NULL。"""
        from src.database import _migrate_position_monitor_nullable

        engine, alter_calls = _make_pg_mock_engine({
            "date_entered": "NO",   # NOT NULL — must be fixed
            "entry_price":  "NO",   # NOT NULL — must be fixed
        })
        _migrate_position_monitor_nullable(engine)

        assert len(alter_calls) == 2, (
            f"Expected 2 DROP NOT NULL calls, got {len(alter_calls)}: {alter_calls}"
        )
        assert any("date_entered" in c for c in alter_calls)
        assert any("entry_price"  in c for c in alter_calls)

    def test_PM4_only_date_entered_needs_fix(self):
        """PM-4b: 只有 date_entered 為 NOT NULL 時，只發出一個 ALTER。"""
        from src.database import _migrate_position_monitor_nullable

        engine, alter_calls = _make_pg_mock_engine({
            "date_entered": "NO",   # NOT NULL
            "entry_price":  "YES",  # already nullable
        })
        _migrate_position_monitor_nullable(engine)

        assert len(alter_calls) == 1
        assert "date_entered" in alter_calls[0]

    def test_PM5_skips_already_nullable(self):
        """PM-5: 兩個欄位已可 NULL 時，不得發出任何 ALTER TABLE。"""
        from src.database import _migrate_position_monitor_nullable

        engine, alter_calls = _make_pg_mock_engine({
            "date_entered": "YES",  # already nullable
            "entry_price":  "YES",  # already nullable
        })
        _migrate_position_monitor_nullable(engine)

        assert len(alter_calls) == 0, (
            f"No ALTER should be issued for already-nullable columns, got: {alter_calls}"
        )

    def test_PM5_table_not_yet_created_skips(self):
        """PM-5b: 表尚未存在時（information_schema 無結果），跳過不報錯。"""
        from src.database import _migrate_position_monitor_nullable

        # information_schema returns None (table doesn't exist yet)
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        result_mock = MagicMock()
        result_mock.fetchone.return_value = None   # column not found
        mock_conn.execute.return_value = result_mock

        mock_engine = MagicMock()
        mock_engine.begin.return_value = mock_conn
        mock_engine.dialect.name = "postgresql"

        _migrate_position_monitor_nullable(mock_engine)  # must not raise

    def test_PM5b_sqlite_is_noop(self):
        """PM-5b: SQLite engine → migration 直接 return，不執行任何 SQL。"""
        from src.database import _migrate_position_monitor_nullable

        engine = create_engine("sqlite:///:memory:")
        # Should not raise, should not execute any SQL
        _migrate_position_monitor_nullable(engine)  # returns immediately

    def test_PM5_alter_failure_raises_runtime_error(self):
        """PM-5c: ALTER TABLE 失敗時，migration 應 raise RuntimeError（fail-closed）。"""
        from src.database import _migrate_position_monitor_nullable

        def _execute(stmt, *args, **kwargs):
            stmt_str = str(stmt)
            if "information_schema.columns" in stmt_str:
                result = MagicMock()
                result.fetchone.return_value = ("NO",)  # NOT NULL
                return result
            if "DROP NOT NULL" in stmt_str:
                raise Exception("permission denied for relation position_monitor")
            return MagicMock()

        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.side_effect = _execute

        mock_engine = MagicMock()
        mock_engine.begin.return_value = mock_conn
        mock_engine.dialect.name = "postgresql"

        with pytest.raises(RuntimeError, match="nullable migration failed"):
            _migrate_position_monitor_nullable(mock_engine)


# ── PM-6: idempotency ─────────────────────────────────────────────────────────

class TestPositionMonitorIdempotency:

    def test_PM6_second_create_pending_skipped(self):
        """PM-6: 同一 stock_id 的 pending_open 重複建立 → 第二次 returns False，DB 只有 1 筆。"""
        from src.database import PositionMonitor

        engine = _make_sqlite()
        s = _session(engine)

        first  = _create_pending(s, "2603")
        second = _create_pending(s, "2603")
        s.commit()

        assert first  is True
        assert second is False

        count = s.query(PositionMonitor).filter_by(stock_id="2603").count()
        assert count == 1, f"Expected 1 record, got {count}"
        s.close()

    def test_PM6b_create_after_activate_skipped(self):
        """PM-6b: pending_open → active 後，再次 create_pending_position → returns False。"""
        from src.database import DailyPrice, PositionMonitor

        engine = _make_sqlite()
        s = _session(engine)

        _create_pending(s, "2603")
        s.commit()

        # Seed DailyPrice.open so activate works
        s.add(DailyPrice(
            stock_id="2603",
            date=_EXEC_DATE,
            open=185.0,
            close=186.0,
        ))
        s.commit()

        from src.engines.position_manager import activate_pending_positions
        activated = activate_pending_positions(s, as_of_date=_EXEC_DATE)
        s.commit()
        assert activated == 1

        # Now the position is active — create should skip
        result = _create_pending(s, "2603")
        assert result is False

        count = s.query(PositionMonitor).filter_by(stock_id="2603").count()
        assert count == 1
        s.close()

    def test_PM6_different_stocks_allowed(self):
        """PM-6c: 不同 stock_id 可各自建立 pending_open。"""
        from src.database import PositionMonitor

        engine = _make_sqlite()
        s = _session(engine)

        r1 = _create_pending(s, "2603")
        r2 = _create_pending(s, "2330")
        s.commit()

        assert r1 is True
        assert r2 is True
        count = s.query(PositionMonitor).count()
        assert count == 2
        s.close()


# ── PM-7: isolation — no contamination of Forward tables ─────────────────────

class TestPositionMonitorIsolation:

    def test_PM7_forward_signal_unaffected(self):
        """PM-7: 建立 PositionMonitor 不得影響 forward_signals 資料。"""
        from src.database import ForwardSignal, PositionMonitor

        engine = _make_sqlite()
        s = _session(engine)

        # Insert a forward signal
        fs = ForwardSignal(
            trade_date=_SIGNAL_DATE,
            stock_id="2603",
            stock_name="長榮",
            pt_score=72.0,
            total_score=72.0,
            rec_level="A",
        )
        s.add(fs)
        s.commit()
        fs_id = fs.id

        # Now create a pending position
        _create_pending(s, "2603")
        s.commit()

        # ForwardSignal must be unchanged
        reloaded = s.query(ForwardSignal).filter_by(id=fs_id).first()
        assert reloaded is not None
        assert reloaded.trade_date == _SIGNAL_DATE
        assert reloaded.total_score == 72.0
        assert reloaded.is_valid is True or reloaded.is_valid is None

        # PositionMonitor must not contaminate ForwardSignal count
        fs_count = s.query(ForwardSignal).count()
        pm_count = s.query(PositionMonitor).count()
        assert fs_count == 1, f"ForwardSignal count should be 1, got {fs_count}"
        assert pm_count == 1, f"PositionMonitor count should be 1, got {pm_count}"
        s.close()

    def test_PM7_foe_rows_unaffected(self):
        """PM-7b: 建立 PositionMonitor 不得建立任何 ForwardOutcomeEvaluation 資料。"""
        from src.database import ForwardOutcomeEvaluation, PositionMonitor

        engine = _make_sqlite()
        s = _session(engine)

        _create_pending(s, "2603")
        s.commit()

        foe_count = s.query(ForwardOutcomeEvaluation).count()
        assert foe_count == 0, (
            f"Creating PositionMonitor must not create foe rows, got {foe_count}"
        )
        s.close()

    def test_PM7_activate_fills_entry_correctly(self):
        """PM-7c: activate_pending_positions 正確填入真實 open 進場價（非收盤、非推估）。"""
        from src.database import DailyPrice, PositionMonitor

        engine = _make_sqlite()
        s = _session(engine)

        _create_pending(s, "2603")
        s.commit()

        s.add(DailyPrice(
            stock_id="2603",
            date=_EXEC_DATE,
            open=187.5,
            close=188.0,
        ))
        s.commit()

        from src.engines.position_manager import activate_pending_positions
        activate_pending_positions(s, as_of_date=_EXEC_DATE)
        s.commit()

        pos = s.query(PositionMonitor).filter_by(stock_id="2603").first()
        assert pos.status == "active"
        assert pos.entry_price == 187.5,   f"entry_price must be open=187.5, got {pos.entry_price}"
        assert pos.date_entered == _EXEC_DATE
        assert pos.entry_source == "NEXT_OPEN"
        assert pos.shadow_trading_type == "NEXT_OPEN_HISTORICAL"
        s.close()
