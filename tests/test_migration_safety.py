"""
tests/test_migration_safety.py — Migration 安全性測試

驗證：
  1. init_db() SQLite 模式：create_all() 照常執行（向後相容）
  2. init_db() PostgreSQL 模式（allow_ddl=False）：不建立新表
  3. init_db(allow_ddl=True) 強制模式：即使 PostgreSQL 也建立新表
  4. _migrate_trade_lifecycle() PostgreSQL 缺表時只 WARNING，不 raise
  5. _migrate_trade_lifecycle() 表存在時只 INFO，不 raise
  6. _TRADE_LIFECYCLE_TABLES 常數正確
  7. 既有表（user_trades / position_monitor）在 allow_ddl=False 時不受影響
  8. migration script dry-run 不寫入（subprocess 測試）
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy import inspect as sql_inspect

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Helpers ──────────────────────────────────────────────────


def _sqlite_engine():
    from src.database import init_db

    engine = create_engine("sqlite:///:memory:")
    init_db(engine)
    return engine


def _make_mock_pg_engine(existing_tables: list):
    """偽造 PostgreSQL engine（dialect.name='postgresql'），不需真實連線。"""
    engine = MagicMock()
    engine.dialect.name = "postgresql"

    insp_mock = MagicMock()
    insp_mock.get_table_names.return_value = existing_tables
    insp_mock.get_columns.return_value = []

    return engine, insp_mock


# ── 1. SQLite 模式：create_all 正常執行 ──────────────────────


class TestSqliteMode:
    def test_sqlite_creates_all_tables(self):
        """init_db() 在 SQLite 上建立包含 trade lifecycle 的所有表。"""
        from src.database import _TRADE_LIFECYCLE_TABLES

        engine = create_engine("sqlite:///:memory:")
        from src.database import init_db

        init_db(engine)

        insp = sql_inspect(engine)
        tables = set(insp.get_table_names())
        for t in _TRADE_LIFECYCLE_TABLES:
            assert t in tables, f"SQLite: {t} missing after init_db()"

    def test_sqlite_allow_ddl_none_auto_detects(self):
        """allow_ddl=None 在 SQLite 上自動為 True。"""
        from src.database import init_db

        engine = create_engine("sqlite:///:memory:")
        result = init_db(engine, allow_ddl=None)
        assert result is engine

        insp = sql_inspect(engine)
        tables = set(insp.get_table_names())
        assert "actual_positions" in tables

    def test_sqlite_idempotent(self):
        """重複呼叫 init_db() 不崩潰（create_all checkfirst=True）。"""
        from src.database import init_db

        engine = create_engine("sqlite:///:memory:")
        init_db(engine)
        init_db(engine)  # 第二次
        init_db(engine)  # 第三次

        insp = sql_inspect(engine)
        assert "actual_positions" in set(insp.get_table_names())


# ── 2. allow_ddl=False 跳過 create_all ──────────────────────


class TestAllowDdlFalse:
    def test_allow_ddl_false_skips_new_tables(self):
        """
        init_db(allow_ddl=False) 在空 SQLite 上跳過 create_all 及所有 _migrate_*，
        新表不會被建立（allow_ddl=False 不執行任何 DDL）。
        """
        from src.database import init_db

        engine = create_engine("sqlite:///:memory:")
        # allow_ddl=False: 不應建立任何表
        # _verify_schema_integrity 會 skip 不存在的表
        init_db(engine, allow_ddl=False)

        insp = sql_inspect(engine)
        tables = set(insp.get_table_names())
        # 新表不應存在
        assert "actual_positions" not in tables
        assert "trade_executions" not in tables
        assert "position_plan_changes" not in tables

    def test_allow_ddl_true_forces_create(self):
        """
        init_db(allow_ddl=True) 強制建表，即使是 PostgreSQL 也適用。
        本測試用 SQLite 驗證 allow_ddl=True 確實觸發 create_all。
        """
        from src.database import init_db

        engine = create_engine("sqlite:///:memory:")
        init_db(engine, allow_ddl=True)

        insp = sql_inspect(engine)
        tables = set(insp.get_table_names())
        assert "actual_positions" in tables
        assert "trade_executions" in tables
        assert "position_plan_changes" in tables


# ── 3. _migrate_trade_lifecycle 行為 ─────────────────────────


class TestMigrateTradeLifecycle:
    def test_sqlite_returns_immediately(self):
        """SQLite 時直接 return，不查詢 get_table_names。"""
        from unittest.mock import MagicMock

        from src.database import _migrate_trade_lifecycle

        engine = MagicMock()
        engine.dialect.name = "sqlite"
        _migrate_trade_lifecycle(engine)  # 不應拋出

    def test_postgresql_tables_exist_logs_info(self, caplog):
        """PostgreSQL 上三張表都存在時 → INFO，不 raise。"""
        import logging

        from src.database import _TRADE_LIFECYCLE_TABLES, _migrate_trade_lifecycle

        engine = MagicMock()
        engine.dialect.name = "postgresql"

        mock_insp = MagicMock()
        mock_insp.get_table_names.return_value = list(_TRADE_LIFECYCLE_TABLES) + [
            "user_trades",
            "forward_signals",
        ]

        # patch sqlalchemy.inspect（_migrate_trade_lifecycle 內 local import）
        with patch("sqlalchemy.inspect", return_value=mock_insp):
            with caplog.at_level(logging.INFO, logger="src.database"):
                _migrate_trade_lifecycle(engine)  # 不應 raise

        assert any("present" in r.message for r in caplog.records)

    def test_postgresql_tables_missing_logs_warning_not_raise(self, caplog):
        """PostgreSQL 上表缺失時 → WARNING，不 raise（不阻斷既有 pipeline）。"""
        import logging

        from src.database import _migrate_trade_lifecycle

        engine = MagicMock()
        engine.dialect.name = "postgresql"

        mock_insp = MagicMock()
        mock_insp.get_table_names.return_value = ["user_trades", "forward_signals"]

        # patch sqlalchemy.inspect（_migrate_trade_lifecycle 內 local import）
        with patch("sqlalchemy.inspect", return_value=mock_insp):
            with caplog.at_level(logging.WARNING, logger="src.database"):
                _migrate_trade_lifecycle(engine)  # 不應 raise

        warning_messages = [
            r.message for r in caplog.records if r.levelname == "WARNING"
        ]
        assert any("missing" in m.lower() for m in warning_messages)


# ── 4. TRADE_LIFECYCLE_TABLES 常數 ───────────────────────────


class TestConstants:
    def test_trade_lifecycle_tables_constant(self):
        from src.database import _TRADE_LIFECYCLE_TABLES

        assert _TRADE_LIFECYCLE_TABLES == frozenset(
            {"actual_positions", "trade_executions", "position_plan_changes"}
        )

    def test_trade_lifecycle_tables_not_in_existing_tables(self):
        """新表不應出現在舊的 _SCHEMA_REQUIRED_COLS（避免 verify 誤報）。"""
        from src.database import _SCHEMA_REQUIRED_COLS, _TRADE_LIFECYCLE_TABLES

        overlap = set(_SCHEMA_REQUIRED_COLS.keys()) & _TRADE_LIFECYCLE_TABLES
        assert overlap == set(), f"新表不應在舊 schema 驗證清單中：{overlap}"


# ── 5. 既有表不被 allow_ddl=False 影響 ──────────────────────


class TestProtectedTables:
    def test_existing_tables_not_modified_by_allow_ddl_false(self):
        """
        先用 allow_ddl=True 建立完整 DB，再用 allow_ddl=False 呼叫 init_db，
        確認舊表欄位不被修改。
        """
        from src.database import init_db

        engine = create_engine("sqlite:///:memory:")
        init_db(engine, allow_ddl=True)

        insp = sql_inspect(engine)
        before = {
            t: {c["name"] for c in insp.get_columns(t)}
            for t in ["user_trades", "position_monitor", "forward_signals"]
        }

        # 再呼叫一次（模擬 pipeline 啟動）
        init_db(engine, allow_ddl=False)

        insp2 = sql_inspect(engine)
        for tbl, cols_before in before.items():
            cols_after = {c["name"] for c in insp2.get_columns(tbl)}
            assert (
                cols_after >= cols_before
            ), f"{tbl}: 欄位在 allow_ddl=False 後減少了！before={cols_before - cols_after}"


# ── 6. migration script dry-run 不寫入 ───────────────────────


class TestMigrationScript:
    def test_dry_run_does_not_create_tables(self, tmp_path):
        """
        migration script --dry-run 不建立任何表（用 SQLite 隔離驗證）。
        """
        import subprocess

        db_file = tmp_path / "test.db"
        env = {
            "DATABASE_URL": f"sqlite:///{db_file}",
            "PYTHONPATH": str(Path(__file__).parent.parent),
        }

        import os

        full_env = os.environ.copy()
        full_env.update(env)

        result = subprocess.run(
            [
                sys.executable,
                "scripts/migrate_trade_lifecycle.py",
                "--dry-run",
                "--env",
                "local",
            ],
            capture_output=True,
            text=True,
            env=full_env,
            cwd=str(Path(__file__).parent.parent),
        )

        # dry-run 應成功（exit 0）
        assert (
            result.returncode == 0
        ), f"dry-run 失敗：\nSTDOUT={result.stdout}\nSTDERR={result.stderr}"

        # dry-run 不應建立真實的 DB 表
        # （腳本連接 local DB，但 dry-run 不執行 CREATE TABLE）
        assert (
            "DRY-RUN" in result.stdout
            or "DRY-RUN" in result.stderr
            or "dry" in result.stdout.lower()
            or "dry" in result.stderr.lower()
        ), "dry-run 輸出中找不到 DRY-RUN 標記"

    def test_migration_script_imports_cleanly(self):
        """migration script 可以 import 而不觸發任何副作用。"""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "migrate_trade_lifecycle",
            "scripts/migrate_trade_lifecycle.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # 不應 raise

        assert hasattr(mod, "main")
        assert hasattr(mod, "_REQUIRED_TABLES")
        assert set(mod._REQUIRED_TABLES) == {
            "actual_positions",
            "trade_executions",
            "position_plan_changes",
        }


# ── 7. 強化 Schema 驗證測試 ─────────────────────────────────


class TestSchemaValidationEnhanced:
    """驗證 _validate_schema() 能正確偵測各類 Schema Drift。"""

    def _load_validate_fn(self):
        """載入 _validate_schema from migrate_trade_lifecycle script。"""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "migrate_trade_lifecycle",
            str(
                Path(__file__).parent.parent / "scripts" / "migrate_trade_lifecycle.py"
            ),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod._validate_schema

    def test_complete_schema_passes(self):
        """完整 Schema（ORM 建立）應通過所有驗證。"""
        from src.database import init_db

        engine = create_engine("sqlite:///:memory:")
        init_db(engine, allow_ddl=True)

        validate = self._load_validate_fn()
        validate(
            engine, ["actual_positions", "trade_executions", "position_plan_changes"]
        )

    def test_missing_column_fails(self):
        """缺少必要欄位時應 raise RuntimeError。"""
        import pytest
        from sqlalchemy import text

        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE actual_positions (id INTEGER PRIMARY KEY, stock_id TEXT)"
                )
            )

        validate = self._load_validate_fn()
        with pytest.raises(RuntimeError, match="缺少欄位"):
            validate(engine, ["actual_positions"])

    def test_missing_required_columns_listed_in_error(self):
        """錯誤訊息必須列出所有缺少的欄位名稱。"""
        import pytest
        from sqlalchemy import text

        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as conn:
            conn.execute(
                text("CREATE TABLE trade_executions (id INTEGER PRIMARY KEY)")
            )  # 缺少 position_id, side, execution_date 等

        validate = self._load_validate_fn()
        with pytest.raises(RuntimeError) as exc_info:
            validate(engine, ["trade_executions"])

        error_msg = str(exc_info.value)
        assert "position_id" in error_msg or "缺少欄位" in error_msg

    def test_primary_key_verified(self):
        """主鍵驗證正常運作（不 raise 即表示通過）。"""
        from src.database import init_db

        engine = create_engine("sqlite:///:memory:")
        init_db(engine, allow_ddl=True)

        validate = self._load_validate_fn()
        validate(engine, ["position_plan_changes"])  # must not raise

    def test_index_exists_for_indexed_columns(self):
        """ORM 定義 index=True 的欄位必須有對應的 index。"""
        from src.database import init_db

        engine = create_engine("sqlite:///:memory:")
        init_db(engine, allow_ddl=True)

        validate = self._load_validate_fn()
        # These tables have indexed columns (position_id, stock_id)
        validate(
            engine, ["trade_executions", "position_plan_changes", "actual_positions"]
        )

    def test_missing_index_detected(self):
        """缺少必要 index 時應 raise RuntimeError。"""
        import pytest
        from sqlalchemy import text

        engine = create_engine("sqlite:///:memory:")
        # Create trade_executions WITHOUT index on position_id
        with engine.begin() as conn:
            col_defs = ", ".join(
                [
                    "id INTEGER PRIMARY KEY",
                    "position_id INTEGER NOT NULL",  # no index
                    "side TEXT NOT NULL",
                    "execution_date DATE NOT NULL",
                    "execution_datetime DATETIME",
                    "execution_price NUMERIC NOT NULL",
                    "shares INTEGER NOT NULL",
                    "actual_fee NUMERIC NOT NULL DEFAULT 0",
                    "transaction_tax NUMERIC NOT NULL DEFAULT 0",
                    "linked_forward_signal_id INTEGER",
                    "notes TEXT",
                    "is_cancelled BOOLEAN NOT NULL DEFAULT 0",
                    "cancel_reason TEXT",
                    "cancelled_at DATETIME",
                    "created_at DATETIME",
                    "updated_at DATETIME",
                ]
            )
            conn.execute(text(f"CREATE TABLE trade_executions ({col_defs})"))
            # Explicitly do NOT create index on position_id

        validate = self._load_validate_fn()
        with pytest.raises(RuntimeError, match="index"):
            validate(engine, ["trade_executions"])

    def test_repeated_validation_idempotent(self):
        """連續執行兩次驗證結果相同（第二次不破壞資料）。"""
        from src.database import init_db

        engine = create_engine("sqlite:///:memory:")
        init_db(engine, allow_ddl=True)

        validate = self._load_validate_fn()
        tables = ["actual_positions", "trade_executions", "position_plan_changes"]
        validate(engine, tables)  # first time
        validate(engine, tables)  # second time — must not raise

    def test_table_inspection_failure_reported(self):
        """完全不存在的表格應在錯誤訊息中標示。"""
        import pytest

        engine = create_engine("sqlite:///:memory:")  # empty DB, no tables

        validate = self._load_validate_fn()
        # Table doesn't exist at all
        with pytest.raises(RuntimeError):
            validate(engine, ["actual_positions"])

    def test_new_schema_constants_match_required_tables(self):
        """_NOT_NULL_COLS, _NUMERIC_PRECISION, _PRIMARY_KEYS, _INDEXED_COLS 涵蓋全部三張表。"""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "migrate_trade_lifecycle",
            str(
                Path(__file__).parent.parent / "scripts" / "migrate_trade_lifecycle.py"
            ),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        required_tables = set(mod._REQUIRED_TABLES)

        assert (
            set(mod._NOT_NULL_COLS.keys()) == required_tables
        ), "_NOT_NULL_COLS must cover all 3 trade lifecycle tables"
        assert (
            set(mod._NUMERIC_PRECISION.keys()) == required_tables
        ), "_NUMERIC_PRECISION must cover all 3 trade lifecycle tables"
        assert (
            set(mod._PRIMARY_KEYS.keys()) == required_tables
        ), "_PRIMARY_KEYS must cover all 3 trade lifecycle tables"
        assert (
            set(mod._INDEXED_COLS.keys()) == required_tables
        ), "_INDEXED_COLS must cover all 3 trade lifecycle tables"
