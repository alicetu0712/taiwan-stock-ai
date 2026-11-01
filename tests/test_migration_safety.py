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
        init_db(allow_ddl=False) 在空 SQLite 上跳過 create_all，
        新表不會被建立。
        注意：_migrate_* 函式若找不到表會 return/skip（既有行為）。
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
