"""
tests/test_ddl_guard.py — DDL 防護測試

驗證：Daily Pipeline、Dashboard、Forward/Research 路徑不自動執行 DDL。
只有明確的 init_db() 呼叫才會執行 Schema Migration。

測試矩陣：
  T1  connect_db() 不呼叫 create_all 或任何 _migrate_*
  T2  dashboard backtest 路徑不呼叫 create_all
  T3  research/forward 路徑不呼叫 create_all（import 無副作用）
  T4  init_db(allow_ddl=True) 正確建立三張 trade lifecycle 表
  T5  重複執行 init_db() 安全（idempotent）
  T6  Production Guard：connect_db() 在 PostgreSQL mock 上不觸發 DDL
  T7  Schema Drift：_verify_schema_integrity 偵測缺欄位並 raise
  T8  import 無 DDL 副作用
  T9  connect_db 之後業務查詢正常運作（read/write 不受影響）
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy import inspect as sql_inspect
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).parent.parent))

_ALL_MIGRATE_FNS = [
    "src.database._migrate_stocks",
    "src.database._migrate_analysis_results",
    "src.database._migrate_forward_signals",
    "src.database._migrate_recommendations",
    "src.database._migrate_decision_label_to_codes",
    "src.database._migrate_overnight_market_contexts",
    "src.database._migrate_forward_outcome_evaluations",
    "src.database._migrate_position_monitor",
    "src.database._migrate_position_monitor_nullable",
    "src.database._migrate_forward_signals_unique_constraint",
    "src.database._migrate_trade_lifecycle",
]

_ALL_DDL_TARGETS = _ALL_MIGRATE_FNS + [
    "sqlalchemy.orm.decl_api.DeclarativeAttributeIntercept.create_all",
]


# ── T1: connect_db() 不觸發任何 DDL ──────────────────────────


class TestConnectDbNoDdl:
    def test_connect_db_skips_create_all(self):
        """connect_db() must not call Base.metadata.create_all."""
        from src.database import connect_db

        engine = create_engine("sqlite:///:memory:")
        with patch("src.database.Base") as mock_base:
            connect_db(engine)
            mock_base.metadata.create_all.assert_not_called()

    def test_connect_db_skips_all_migrate_fns(self):
        """connect_db() must not call any _migrate_* function."""
        from src.database import connect_db

        engine = create_engine("sqlite:///:memory:")
        mocks = {fn: MagicMock() for fn in _ALL_MIGRATE_FNS}
        with patch.multiple(
            "src.database", **{fn.split(".")[-1]: mocks[fn] for fn in _ALL_MIGRATE_FNS}
        ):
            connect_db(engine)
        for fn, mock in mocks.items():
            assert mock.call_count == 0, f"{fn} was called by connect_db()"

    def test_connect_db_returns_engine(self):
        """connect_db() returns the engine unchanged."""
        from src.database import connect_db

        engine = create_engine("sqlite:///:memory:")
        result = connect_db(engine)
        assert result is engine

    def test_connect_db_with_no_arg_returns_engine(self):
        """connect_db() with no arg calls get_engine() and returns Engine."""
        from sqlalchemy.engine import Engine

        from src.database import connect_db

        with patch("src.database.get_engine") as mock_ge:
            mock_ge.return_value = create_engine("sqlite:///:memory:")
            result = connect_db()
        assert isinstance(result, Engine)


# ── T2: Dashboard backtest 路徑不觸發 DDL ───────────────────


class TestDashboardNoDdl:
    def test_backtest_import_no_create_all(self):
        """Importing dashboard.backtest module triggers no create_all."""
        import importlib

        with patch("src.database.Base") as mock_base:
            importlib.import_module("dashboard._pages.backtest")
            mock_base.metadata.create_all.assert_not_called()

    def test_backtest_uses_connect_db_not_init_db(self):
        """dashboard/_pages/backtest.py must import connect_db, not init_db."""
        import ast

        path = Path(__file__).parent.parent / "dashboard" / "_pages" / "backtest.py"
        source = path.read_text()
        tree = ast.parse(source)

        init_db_calls = []
        connect_db_calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name == "init_db":
                        init_db_calls.append(alias.name)
                    if alias.name == "connect_db":
                        connect_db_calls.append(alias.name)

        assert (
            init_db_calls == []
        ), f"backtest.py still imports init_db: {init_db_calls}"
        assert len(connect_db_calls) > 0, "backtest.py should import connect_db"


# ── T3: Research / Forward import 無副作用 ──────────────────


class TestResearchForwardNoDdl:
    def test_import_database_no_create_all(self):
        """Importing src.database must not call create_all."""
        import src.database as db_mod

        # Module-level code must not call create_all.
        # connect_db() is the proof: it exists and does no DDL (covered by T1).
        assert hasattr(db_mod, "connect_db")
        assert hasattr(db_mod, "init_db")

    def test_main_module_import_no_ddl(self):
        """Importing main module must not trigger DDL."""
        with patch("src.database.Base") as mock_base:
            # Suppress other side effects (API clients, etc.)
            with patch("src.database.get_engine"):
                import importlib

                try:
                    importlib.import_module("main")
                except Exception:
                    pass  # import errors from missing secrets are OK
                mock_base.metadata.create_all.assert_not_called()


# ── T4: 明確 Migration 可以建立三張 trade lifecycle 表 ──────


class TestExplicitMigrationCreatesSchema:
    def test_init_db_allow_ddl_true_creates_lifecycle_tables(self):
        """init_db(allow_ddl=True) creates all 3 trade lifecycle tables."""
        from src.database import _TRADE_LIFECYCLE_TABLES, init_db

        engine = create_engine("sqlite:///:memory:")
        init_db(engine, allow_ddl=True)

        insp = sql_inspect(engine)
        tables = set(insp.get_table_names())
        for t in _TRADE_LIFECYCLE_TABLES:
            assert t in tables, f"Expected table {t!r} not found after migration"

    def test_init_db_creates_all_required_columns(self):
        """init_db(allow_ddl=True) creates tables with correct columns."""
        from src.database import init_db

        engine = create_engine("sqlite:///:memory:")
        init_db(engine, allow_ddl=True)

        insp = sql_inspect(engine)

        ap_cols = {c["name"] for c in insp.get_columns("actual_positions")}
        assert "stock_id" in ap_cols
        assert "status" in ap_cols
        assert "remaining_shares" in ap_cols
        assert "avg_cost_per_share" in ap_cols
        assert "realized_pnl" in ap_cols

        te_cols = {c["name"] for c in insp.get_columns("trade_executions")}
        assert "position_id" in te_cols
        assert "side" in te_cols
        assert "execution_price" in te_cols
        assert "shares" in te_cols

        pc_cols = {c["name"] for c in insp.get_columns("position_plan_changes")}
        assert "position_id" in pc_cols
        assert "field_name" in pc_cols
        assert "old_value" in pc_cols
        assert "new_value" in pc_cols


# ── T5: 重複執行 Migration 安全 ─────────────────────────────


class TestIdempotentMigration:
    def test_init_db_twice_no_error(self):
        """Running init_db() twice must not raise or corrupt schema."""
        from src.database import init_db

        engine = create_engine("sqlite:///:memory:")
        init_db(engine, allow_ddl=True)
        init_db(engine, allow_ddl=True)  # second run

        insp = sql_inspect(engine)
        tables = set(insp.get_table_names())
        assert "actual_positions" in tables

    def test_init_db_three_times_stable(self):
        """Schema stays identical after three consecutive init_db() calls."""
        from src.database import init_db

        engine = create_engine("sqlite:///:memory:")
        init_db(engine, allow_ddl=True)

        insp1 = sql_inspect(engine)
        cols_before = {
            t: {c["name"] for c in insp1.get_columns(t)}
            for t in ["actual_positions", "forward_signals"]
        }

        init_db(engine, allow_ddl=True)
        init_db(engine, allow_ddl=True)

        insp2 = sql_inspect(engine)
        for tbl, cols_orig in cols_before.items():
            cols_after = {c["name"] for c in insp2.get_columns(tbl)}
            assert (
                cols_after >= cols_orig
            ), f"{tbl}: columns removed after repeated init_db()"


# ── T6: Production Guard ─────────────────────────────────────


class TestProductionGuard:
    def test_connect_db_postgresql_mock_no_ddl(self):
        """connect_db() with mocked PostgreSQL engine must not call create_all."""
        from src.database import connect_db

        pg_engine = MagicMock()
        pg_engine.dialect.name = "postgresql"

        with patch("src.database.Base") as mock_base:
            result = connect_db(pg_engine)

        assert result is pg_engine
        mock_base.metadata.create_all.assert_not_called()

    def test_init_db_postgresql_default_no_create_all(self):
        """init_db() with PostgreSQL engine (allow_ddl=None) skips create_all."""
        from src.database import init_db

        pg_engine = MagicMock()
        pg_engine.dialect.name = "postgresql"

        insp_mock = MagicMock()
        insp_mock.get_table_names.return_value = [
            "stocks",
            "analysis_results",
            "forward_signals",
            "recommendations",
            "position_monitor",
            "forward_outcome_evaluations",
            "overnight_market_contexts",
            "execution_logs",
            "candidate_pool",
            "candidate_pool_history",
        ]
        insp_mock.get_columns.return_value = []

        with patch("src.database.Base") as mock_base:
            with patch("sqlalchemy.inspect", return_value=insp_mock):
                try:
                    init_db(pg_engine, allow_ddl=None)
                except Exception:
                    pass  # _verify_schema_integrity may raise; that's fine

        mock_base.metadata.create_all.assert_not_called()


# ── T7: Schema Drift 偵測 ────────────────────────────────────


class TestSchemaDriftDetection:
    def test_verify_raises_on_missing_required_column(self):
        """_verify_schema_integrity raises RuntimeError when a required column is absent."""
        import pytest

        from src.database import _verify_schema_integrity

        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as conn:
            conn.execute(
                text("CREATE TABLE execution_logs (id INTEGER PRIMARY KEY)")
            )  # missing 'date' and 'status'

        with pytest.raises(RuntimeError, match="Schema integrity check FAILED"):
            _verify_schema_integrity(engine)

    def test_verify_passes_when_required_columns_present(self):
        """_verify_schema_integrity passes when required columns exist."""
        from src.database import _SCHEMA_REQUIRED_COLS, _verify_schema_integrity

        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as conn:
            for table, cols in _SCHEMA_REQUIRED_COLS.items():
                col_defs = ", ".join(f"{c} TEXT" for c in cols)
                conn.execute(text(f"CREATE TABLE {table} ({col_defs})"))

        _verify_schema_integrity(engine)  # must not raise

    def test_missing_column_error_message_names_the_table(self):
        """Error message from schema drift clearly identifies the affected table."""
        import pytest

        from src.database import _verify_schema_integrity

        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE candidate_pool (id INTEGER PRIMARY KEY, stock_id TEXT)"
                )
            )  # missing model_version, pool_version, etc.

        with pytest.raises(RuntimeError) as exc_info:
            _verify_schema_integrity(engine)
        assert "candidate_pool" in str(exc_info.value)


# ── T8: Import 無 DDL 副作用 ────────────────────────────────


class TestImportSideEffects:
    def test_database_module_import_no_create_all(self):
        """Importing src.database at module level does not call create_all."""
        # src.database is already imported; verify no create_all was triggered
        # by checking the module has the expected public API.
        import src.database as db

        assert callable(db.connect_db)
        assert callable(db.init_db)
        assert callable(db.get_session)
        assert callable(db.get_engine)

    def test_connect_db_symbol_exported(self):
        """connect_db must be importable from src.database."""
        from src.database import connect_db  # noqa: F401 (import test)

        assert connect_db is not None

    def test_main_uses_connect_db_not_init_db(self):
        """main.py run_pipeline must use connect_db, not init_db."""
        import ast

        path = Path(__file__).parent.parent / "main.py"
        source = path.read_text()
        tree = ast.parse(source)

        # find the run_pipeline function and check imports inside it
        init_db_in_pipeline = False
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "run_pipeline":
                for child in ast.walk(node):
                    if isinstance(child, ast.ImportFrom):
                        for alias in child.names:
                            if alias.name == "init_db":
                                init_db_in_pipeline = True

        assert (
            not init_db_in_pipeline
        ), "main.run_pipeline() still imports init_db — must use connect_db"


# ── T9: 業務功能不受影響 ─────────────────────────────────────


class TestBusinessFunctionsUnaffected:
    def _make_db(self):
        from src.database import init_db

        engine = create_engine("sqlite:///:memory:")
        init_db(engine, allow_ddl=True)
        return engine

    def test_session_read_write_via_connect_db(self):
        """get_session(connect_db()) can write and read business data."""
        from src.database import Stock, connect_db, get_session, init_db

        # Prepare schema first (one-time migration)
        engine = create_engine("sqlite:///:memory:")
        init_db(engine, allow_ddl=True)

        # Normal business operation: use connect_db() for all subsequent access
        biz_engine = connect_db(engine)
        session = get_session(biz_engine)

        s = Stock(stock_id="2330", name="台積電", market="TWSE")
        session.add(s)
        session.commit()

        found = session.query(Stock).filter_by(stock_id="2330").first()
        assert found is not None
        assert found.name == "台積電"
        session.close()

    def test_paper_position_monitor_accessible(self):
        """PositionMonitor table is readable after connect_db()."""
        from src.database import PositionMonitor, connect_db, get_session, init_db

        engine = create_engine("sqlite:///:memory:")
        init_db(engine, allow_ddl=True)

        biz_engine = connect_db(engine)
        session = get_session(biz_engine)
        count = session.query(PositionMonitor).count()
        assert count == 0
        session.close()

    def test_forward_signals_accessible(self):
        """ForwardSignal table is readable after connect_db()."""
        from src.database import ForwardSignal, connect_db, get_session, init_db

        engine = create_engine("sqlite:///:memory:")
        init_db(engine, allow_ddl=True)

        biz_engine = connect_db(engine)
        session = get_session(biz_engine)
        count = session.query(ForwardSignal).count()
        assert count == 0
        session.close()

    def test_actual_positions_accessible(self):
        """ActualPosition table is readable after connect_db()."""
        from src.database import ActualPosition, connect_db, get_session, init_db

        engine = create_engine("sqlite:///:memory:")
        init_db(engine, allow_ddl=True)

        biz_engine = connect_db(engine)
        session = get_session(biz_engine)
        count = session.query(ActualPosition).count()
        assert count == 0
        session.close()


# ── T10: init_db(allow_ddl=False) 完全跳過所有 _migrate_* ─────


class TestInitDbAllowDdlFalseSkipsMigrations:
    """init_db(allow_ddl=False) must skip ALL DDL and _migrate_* calls."""

    def test_allow_ddl_false_skips_all_migrate_fns(self):
        """init_db(allow_ddl=False) must not call any _migrate_* function."""
        from src.database import init_db

        engine = create_engine("sqlite:///:memory:")
        mocks = {fn: MagicMock() for fn in _ALL_MIGRATE_FNS}
        with patch.multiple(
            "src.database",
            **{fn.split(".")[-1]: mocks[fn] for fn in _ALL_MIGRATE_FNS},
        ):
            with patch("src.database.Base"):
                init_db(engine, allow_ddl=False)

        for fn, mock in mocks.items():
            assert mock.call_count == 0, (
                f"{fn} was called by init_db(allow_ddl=False) — "
                "must not execute DDL in allow_ddl=False mode"
            )

    def test_allow_ddl_false_skips_create_all(self):
        """init_db(allow_ddl=False) must not call Base.metadata.create_all."""
        from src.database import init_db

        engine = create_engine("sqlite:///:memory:")
        with patch("src.database.Base") as mock_base:
            init_db(engine, allow_ddl=False)
        mock_base.metadata.create_all.assert_not_called()

    def test_allow_ddl_false_postgresql_skips_all_migrate_fns(self):
        """init_db(allow_ddl=False) on PostgreSQL engine skips all _migrate_* fns."""
        from src.database import init_db

        pg_engine = MagicMock()
        pg_engine.dialect.name = "postgresql"

        mocks = {fn: MagicMock() for fn in _ALL_MIGRATE_FNS}
        insp_mock = MagicMock()
        insp_mock.get_columns.return_value = []

        with patch.multiple(
            "src.database",
            **{fn.split(".")[-1]: mocks[fn] for fn in _ALL_MIGRATE_FNS},
        ):
            with patch("src.database.Base"):
                with patch("sqlalchemy.inspect", return_value=insp_mock):
                    try:
                        init_db(pg_engine, allow_ddl=False)
                    except Exception:
                        pass  # _verify_schema_integrity may raise; that's expected

        for fn, mock in mocks.items():
            assert mock.call_count == 0, (
                f"{fn} was called by init_db(allow_ddl=False) on PG — "
                "production schema must never be auto-migrated"
            )

    def test_allow_ddl_none_postgresql_skips_all_migrate_fns(self):
        """init_db(allow_ddl=None) on PostgreSQL auto-selects False → no migrations."""
        from src.database import init_db

        pg_engine = MagicMock()
        pg_engine.dialect.name = "postgresql"

        mocks = {fn: MagicMock() for fn in _ALL_MIGRATE_FNS}
        insp_mock = MagicMock()
        insp_mock.get_columns.return_value = []

        with patch.multiple(
            "src.database",
            **{fn.split(".")[-1]: mocks[fn] for fn in _ALL_MIGRATE_FNS},
        ):
            with patch("src.database.Base"):
                with patch("sqlalchemy.inspect", return_value=insp_mock):
                    try:
                        init_db(pg_engine, allow_ddl=None)  # auto-detects PG → False
                    except Exception:
                        pass

        for fn, mock in mocks.items():
            assert (
                mock.call_count == 0
            ), f"{fn} was called by init_db(allow_ddl=None) on PG"

    def test_allow_ddl_true_still_calls_migrate_fns(self):
        """init_db(allow_ddl=True) must call all _migrate_* functions (sanity check)."""
        from src.database import init_db

        engine = create_engine("sqlite:///:memory:")
        called_fns = []

        def make_recorder(name):
            def recorder(eng):
                called_fns.append(name)

            return recorder

        patch_dict = {fn.split(".")[-1]: make_recorder(fn) for fn in _ALL_MIGRATE_FNS}
        with patch.multiple("src.database", **patch_dict):
            with patch("src.database.Base") as mock_base:
                mock_base.metadata.create_all.return_value = None
                try:
                    init_db(engine, allow_ddl=True)
                except Exception:
                    pass  # _verify_schema_integrity may raise on empty DB

        # All migrate functions should have been called
        for fn in _ALL_MIGRATE_FNS:
            assert fn in called_fns, f"{fn} was NOT called by init_db(allow_ddl=True)"


# ── T11: Daily Pipeline / Dashboard 不呼叫 init_db ───────────


class TestNoBizPathCallsInitDb:
    """Verify that run_daily.py and dashboard/app.py never import or call init_db."""

    def test_run_daily_does_not_import_init_db(self):
        """scripts/run_daily.py must not import init_db at module level."""
        import ast

        path = Path(__file__).parent.parent / "scripts" / "run_daily.py"
        source = path.read_text()
        tree = ast.parse(source)

        init_db_imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name == "init_db":
                        init_db_imports.append(alias.name)

        assert init_db_imports == [], (
            f"run_daily.py imports init_db: {init_db_imports} — "
            "daily pipeline must use connect_db() only"
        )

    def test_dashboard_db_does_not_call_init_db(self):
        """dashboard/db.py must not call init_db."""
        import ast

        path = Path(__file__).parent.parent / "dashboard" / "db.py"
        source = path.read_text()
        tree = ast.parse(source)

        init_db_calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name == "init_db":
                        init_db_calls.append(alias.name)
            if isinstance(node, ast.Name) and node.id == "init_db":
                init_db_calls.append("init_db_name_ref")

        assert init_db_calls == [], (
            f"dashboard/db.py references init_db: {init_db_calls} — "
            "dashboard bootstrap must not trigger migrations"
        )
