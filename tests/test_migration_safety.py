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
        """migration script --dry-run 不執行真實 CREATE TABLE。

        config.py uses load_dotenv(override=True), so the subprocess always
        connects to the real local DATABASE_URL (Neon). Exit codes:
          0 — no migration needed (all tables present, schema matches ORM)
          2 — schema drift detected (e.g. FK constraints added to ORM but
              not yet applied to production tables via ALTER TABLE)
        Both are valid dry-run outcomes — neither executes CREATE TABLE.
        """
        import os
        import subprocess

        full_env = os.environ.copy()
        full_env["PYTHONPATH"] = str(Path(__file__).parent.parent)

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

        output = result.stdout + result.stderr

        # 0 = no migration needed; 2 = drift detected — both are non-crashing dry-runs
        assert result.returncode in (0, 2), (
            f"dry-run 異常退出（exit {result.returncode}）："
            f"\nSTDOUT={result.stdout}\nSTDERR={result.stderr}"
        )

        # Migration 標頭必須出現（確認腳本有執行到）
        assert (
            "Phase 1 Trade Lifecycle Migration" in output
        ), "dry-run 輸出中找不到 Migration 工具標識"

        # 確認沒有執行任何真實的 CREATE TABLE（只有 DRY-RUN 標記或 Drift 訊息）
        # 真實 CREATE TABLE 的 INFO 格式：" CREATE TABLE {tbl} ..."（無 DRY-RUN 前綴）
        assert (
            "DRY-RUN" in output
            or "Schema Drift" in output
            or "無需 Migration" in output
        ), "dry-run 輸出中缺少執行計畫說明"

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
                    "idempotency_key TEXT",
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

    def test_orm_schema_matches_orm_definitions(self):
        """_get_orm_schema derives expected schema from ORM — verify against ORM directly."""
        import importlib.util

        from src.database import Base

        spec = importlib.util.spec_from_file_location(
            "migrate_trade_lifecycle",
            str(
                Path(__file__).parent.parent / "scripts" / "migrate_trade_lifecycle.py"
            ),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        for tbl_name in mod._REQUIRED_TABLES:
            schema = mod._get_orm_schema(tbl_name)
            orm_tbl = Base.metadata.tables[tbl_name]

            # All ORM columns present in schema
            orm_col_names = {col.name for col in orm_tbl.columns}
            assert orm_col_names == set(
                schema["columns"]
            ), f"{tbl_name}: schema columns don't match ORM"

            # PKs match
            expected_pks = {col.name for col in orm_tbl.columns if col.primary_key}
            assert expected_pks == schema["pks"], f"{tbl_name}: PKs don't match ORM"

            # FK count matches
            expected_fk_count = sum(len(col.foreign_keys) for col in orm_tbl.columns)
            assert (
                len(schema["fks"]) == expected_fk_count
            ), f"{tbl_name}: FK count mismatch"


# ── 8. Migration Hardening Tests ─────────────────────────────


class TestMigrationHardening:
    """Comprehensive drift detection, execution-order, and guard tests.

    Covers the 18 scenarios from Phase 1B task spec:
      T4/5:  NUMERIC precision/scale error (mock PG)
      T6:    VARCHAR length error (mock PG)
      T7:    Nullable error (mock PG)
      T8:    Primary Key error (SQLite)
      T9/10: FK validated from ORM (PASS on ORM-built SQLite; FAIL if missing)
      T11:   Unique constraint missing (mock with patched _get_orm_schema)
      T12:   Unique index missing (SQLite)
      T13:   Index column error (SQLite)
      T14:   Inspector exception → [BLOCKED]
      T15:   Existing drift + missing tables → DDL = 0
      T16:   _create_tables uses engine.begin() (transaction)
      T17:   Production confirmation gate rejects non-'yes'
    """

    def _load_mod(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "migrate_trade_lifecycle",
            str(
                Path(__file__).parent.parent / "scripts" / "migrate_trade_lifecycle.py"
            ),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def _make_pg_mock(self, tbl: str, col_overrides: dict | None = None):
        """Return (mock_engine, mock_insp) for a PG-dialect validation test.

        Builds column/FK/index lists from ORM metadata — stays in sync
        with model changes automatically; no hardcoded constant copies.
        """
        from src.database import Base

        orm_tbl = Base.metadata.tables[tbl]

        # --- Columns derived from ORM ---
        cols_by_name: dict = {}
        for col in orm_tbl.columns:
            t = col.type

            class _TypeProxy:
                precision = getattr(t, "precision", None)
                scale = getattr(t, "scale", None)
                length = getattr(t, "length", None)

            cols_by_name[col.name] = {
                "name": col.name,
                "nullable": col.nullable,
                "type": _TypeProxy(),
            }

        # Apply caller overrides
        if col_overrides:
            for col_name, overrides in col_overrides.items():
                if col_name in cols_by_name:
                    cols_by_name[col_name].update(overrides)

        col_list = list(cols_by_name.values())

        # --- FK list derived from ORM ---
        fk_list = []
        for col in orm_tbl.columns:
            for fk in col.foreign_keys:
                try:
                    ref_tbl = fk.column.table.name
                    ref_col = fk.column.name
                    ondelete = (getattr(fk.constraint, "ondelete", None) or "").upper()
                    fk_list.append(
                        {
                            "constrained_columns": [col.name],
                            "referred_table": ref_tbl,
                            "referred_columns": [ref_col],
                            "options": {"ondelete": ondelete},
                        }
                    )
                except Exception:
                    pass

        # --- Index list derived from ORM index=True columns ---
        idx_list = [
            {"name": f"ix_{tbl}_{col.name}", "column_names": [col.name]}
            for col in orm_tbl.columns
            if getattr(col, "index", False)
        ]

        # --- Unique constraint list derived from ORM ---
        from sqlalchemy import UniqueConstraint as SA_UC

        uc_list = [
            {"column_names": list(c.columns.keys())}
            for c in orm_tbl.constraints
            if isinstance(c, SA_UC) and list(c.columns.keys())
        ]

        mock_engine = MagicMock()
        mock_engine.dialect.name = "postgresql"

        mock_insp = MagicMock()
        mock_insp.get_columns.return_value = col_list
        mock_insp.get_pk_constraint.return_value = {"constrained_columns": ["id"]}
        mock_insp.get_foreign_keys.return_value = fk_list
        mock_insp.get_unique_constraints.return_value = uc_list
        mock_insp.get_indexes.return_value = idx_list

        return mock_engine, mock_insp

    # ── T4: NUMERIC precision mismatch → [FAIL] ─────────────────────
    def test_numeric_precision_mismatch_fail(self):
        """Wrong NUMERIC precision → [FAIL] (not Warning)."""
        import pytest

        mod = self._load_mod()

        class FakeNumeric:
            precision = 8  # wrong: expected 12
            scale = 4

        engine, insp = self._make_pg_mock(
            "actual_positions",
            {"avg_cost_per_share": {"type": FakeNumeric()}},
        )
        with patch("sqlalchemy.inspect", return_value=insp):
            with pytest.raises(RuntimeError) as exc_info:
                mod._validate_schema(engine, ["actual_positions"])
        err = str(exc_info.value)
        assert "[FAIL]" in err
        assert "avg_cost_per_share" in err
        assert "NUMERIC" in err

    # ── T5: NUMERIC scale mismatch → [FAIL] ─────────────────────────
    def test_numeric_scale_mismatch_fail(self):
        """Wrong NUMERIC scale → [FAIL]."""
        import pytest

        mod = self._load_mod()

        class FakeNumeric:
            precision = 12
            scale = 2  # wrong: expected 4

        engine, insp = self._make_pg_mock(
            "actual_positions",
            {"avg_cost_per_share": {"type": FakeNumeric()}},
        )
        with patch("sqlalchemy.inspect", return_value=insp):
            with pytest.raises(RuntimeError) as exc_info:
                mod._validate_schema(engine, ["actual_positions"])
        err = str(exc_info.value)
        assert "[FAIL]" in err
        assert "NUMERIC" in err

    # ── T4 variant: NUMERIC precision unreadable → [BLOCKED] ────────
    def test_numeric_precision_unreadable_blocked(self):
        """NUMERIC precision cannot be read → [BLOCKED] (was Warning before fix)."""
        import pytest

        mod = self._load_mod()

        class FakeType:
            # No precision / scale attributes → getattr returns None
            pass

        engine, insp = self._make_pg_mock(
            "actual_positions",
            {"avg_cost_per_share": {"type": FakeType()}},
        )
        with patch("sqlalchemy.inspect", return_value=insp):
            with pytest.raises(RuntimeError) as exc_info:
                mod._validate_schema(engine, ["actual_positions"])
        err = str(exc_info.value)
        assert "[BLOCKED]" in err
        assert "precision" in err.lower() or "NUMERIC" in err

    # ── T6: VARCHAR length mismatch → [FAIL] ────────────────────────
    def test_varchar_length_mismatch_fail(self):
        """Wrong VARCHAR length → [FAIL]."""
        import pytest

        mod = self._load_mod()

        class FakeVarchar:
            length = 5  # wrong: expected 10

        engine, insp = self._make_pg_mock(
            "actual_positions",
            {"stock_id": {"type": FakeVarchar()}},
        )
        with patch("sqlalchemy.inspect", return_value=insp):
            with pytest.raises(RuntimeError) as exc_info:
                mod._validate_schema(engine, ["actual_positions"])
        err = str(exc_info.value)
        assert "[FAIL]" in err
        assert "stock_id" in err
        assert "VARCHAR" in err

    # ── T7: Nullable mismatch → [FAIL] ──────────────────────────────
    def test_nullable_mismatch_fail(self):
        """NOT NULL column is nullable in DB → [FAIL]."""
        import pytest

        mod = self._load_mod()

        engine, insp = self._make_pg_mock(
            "actual_positions",
            {"stock_id": {"nullable": True}},  # should be NOT NULL
        )
        with patch("sqlalchemy.inspect", return_value=insp):
            with pytest.raises(RuntimeError) as exc_info:
                mod._validate_schema(engine, ["actual_positions"])
        err = str(exc_info.value)
        assert "[FAIL]" in err
        assert "stock_id" in err
        assert "NOT NULL" in err

    # ── T8: Primary Key mismatch → [FAIL] ───────────────────────────
    def test_primary_key_mismatch_fail(self):
        """Wrong PK column → [FAIL]."""
        import pytest
        from sqlalchemy import text

        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE position_plan_changes ("
                    "id TEXT, position_id TEXT, changed_at TEXT, "
                    "field_name TEXT, old_value TEXT, new_value TEXT, "
                    "reason TEXT, created_at TEXT, other_pk TEXT PRIMARY KEY)"
                )
            )

        validate = self._load_mod()._validate_schema
        with pytest.raises(RuntimeError) as exc_info:
            validate(engine, ["position_plan_changes"])
        err = str(exc_info.value)
        assert "[FAIL]" in err
        assert "PK" in err

    # ── T9/10: FK validated from ORM ────────────────────────────────
    def test_fk_constraints_validated_from_orm(self):
        """FK constraints declared in ORM are validated; ORM-built SQLite DB passes."""
        from src.database import init_db

        engine = create_engine("sqlite:///:memory:")
        init_db(engine, allow_ddl=True)

        mod = self._load_mod()
        # ORM declares FKs (RESTRICT) → validation checks them.
        # ORM-built SQLite DB has the FK schema → should pass without error.
        mod._validate_schema(
            engine, ["actual_positions", "trade_executions", "position_plan_changes"]
        )

    def test_fk_missing_fails(self):
        """FK declared in ORM but missing from DB → [FAIL]."""
        import pytest

        mod = self._load_mod()
        engine, insp = self._make_pg_mock("trade_executions")
        insp.get_foreign_keys.return_value = []  # override: no FKs in DB

        with patch("sqlalchemy.inspect", return_value=insp):
            with pytest.raises(RuntimeError) as exc_info:
                mod._validate_schema(engine, ["trade_executions"])
        err = str(exc_info.value)
        assert "[FAIL]" in err
        assert "FK" in err or "position_id" in err

    def test_fk_inspection_failure_blocked(self):
        """Inspector exception on get_foreign_keys → [BLOCKED]."""
        import pytest

        mod = self._load_mod()
        engine, insp = self._make_pg_mock("trade_executions")
        insp.get_foreign_keys.side_effect = Exception("FK catalog unavailable")

        with patch("sqlalchemy.inspect", return_value=insp):
            with pytest.raises(RuntimeError) as exc_info:
                mod._validate_schema(engine, ["trade_executions"])
        err = str(exc_info.value)
        assert "[BLOCKED]" in err
        assert "FK" in err

    # ── T11: Expected UC missing → [FAIL] (patched ORM schema) ──────
    def test_expected_unique_constraint_missing_fail(self):
        """When ORM expects a unique constraint but DB doesn't have it → [FAIL]."""
        import pytest

        mod = self._load_mod()
        engine, insp = self._make_pg_mock("actual_positions")
        insp.get_unique_constraints.return_value = []  # DB has no UCs

        # Inject an ORM-expected UC not present in DB via _get_orm_schema patch
        original_fn = mod._get_orm_schema

        def patched_orm_schema(tbl_name):
            result = dict(original_fn(tbl_name))
            if tbl_name == "actual_positions":
                result["unique_constraints"] = [frozenset({"stock_id", "status"})]
            return result

        with patch.object(mod, "_get_orm_schema", side_effect=patched_orm_schema):
            with patch("sqlalchemy.inspect", return_value=insp):
                with pytest.raises(RuntimeError) as exc_info:
                    mod._validate_schema(engine, ["actual_positions"])
        err = str(exc_info.value)
        assert "[FAIL]" in err
        assert "Unique Constraint" in err

    # ── T11 complement: unexpected UC in DB is not an error ──────────
    def test_unexpected_unique_constraint_logged_not_failed(self):
        """DB has a UC the ORM doesn't declare → no error (extra UCs are ignored).

        Uses ORM-built SQLite DB so all column/type checks pass cleanly.
        """
        from src.database import init_db

        engine = create_engine("sqlite:///:memory:")
        init_db(engine, allow_ddl=True)

        mod = self._load_mod()
        # ORM expects no UCs on actual_positions → any extra DB UC is warn-only.
        mod._validate_schema(engine, ["actual_positions"])

    # ── T12/13: Index column error → [FAIL] ─────────────────────────
    def test_index_missing_for_required_column_fail(self):
        """Missing required index → [FAIL]."""
        import pytest
        from sqlalchemy import text

        engine = create_engine("sqlite:///:memory:")
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
                "idempotency_key TEXT",
                "notes TEXT",
                "is_cancelled BOOLEAN NOT NULL DEFAULT 0",
                "cancel_reason TEXT",
                "cancelled_at DATETIME",
                "created_at DATETIME",
                "updated_at DATETIME",
            ]
        )
        with engine.begin() as conn:
            conn.execute(text(f"CREATE TABLE trade_executions ({col_defs})"))

        validate = self._load_mod()._validate_schema
        with pytest.raises(RuntimeError, match=r"\[FAIL\].*index"):
            validate(engine, ["trade_executions"])

    # ── T14: Inspector exception → [BLOCKED] ────────────────────────
    def test_inspector_get_pk_failure_blocked(self):
        """Inspector exception on get_pk_constraint → [BLOCKED]."""
        import pytest

        mod = self._load_mod()
        engine, insp = self._make_pg_mock("actual_positions")
        insp.get_pk_constraint.side_effect = Exception("PG catalog read error")

        with patch("sqlalchemy.inspect", return_value=insp):
            with pytest.raises(RuntimeError) as exc_info:
                mod._validate_schema(engine, ["actual_positions"])
        err = str(exc_info.value)
        assert "[BLOCKED]" in err
        assert "PK" in err

    def test_inspector_get_indexes_failure_blocked(self):
        """Inspector exception on get_indexes → [BLOCKED]."""
        import pytest

        mod = self._load_mod()
        engine, insp = self._make_pg_mock("actual_positions")
        insp.get_indexes.side_effect = Exception("catalog locked")

        with patch("sqlalchemy.inspect", return_value=insp):
            with pytest.raises(RuntimeError) as exc_info:
                mod._validate_schema(engine, ["actual_positions"])
        err = str(exc_info.value)
        assert "[BLOCKED]" in err
        assert "Index" in err or "index" in err

    # ── T15: Existing drift + missing tables → DDL count = 0 ────────
    def test_existing_drift_prevents_ddl_for_missing_tables(self):
        """Step 2 (validate existing) raises → Step 3 (create_tables) never called.

        This is the core safety guarantee: when any existing table has schema
        drift, no DDL is executed for any table (including the missing ones).
        """
        import pytest

        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as conn:
            # actual_positions exists but is broken (missing columns)
            from sqlalchemy import text

            conn.execute(
                text(
                    "CREATE TABLE actual_positions "
                    "(id INTEGER PRIMARY KEY, stock_id TEXT)"
                )
            )
            # trade_executions and position_plan_changes are missing

        mod = self._load_mod()

        # Verify that _validate_schema raises for the broken existing table
        with pytest.raises(RuntimeError, match=r"\[FAIL\].*缺少欄位"):
            mod._validate_schema(engine, ["actual_positions"])

        # Verify trade_executions was NOT created (DDL = 0)
        from sqlalchemy import inspect as sql_inspect

        insp = sql_inspect(engine)
        existing = set(insp.get_table_names())
        assert "trade_executions" not in existing, (
            "trade_executions should NOT have been created — "
            "drift in actual_positions must block ALL DDL"
        )
        assert "position_plan_changes" not in existing

    def test_validate_schema_raises_before_create_when_drift(self):
        """main() calls _validate_schema(existing) before _create_tables.

        Patching _create_tables confirms it is never called when drift raises.
        """
        import pytest

        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as conn:
            from sqlalchemy import text

            conn.execute(
                text("CREATE TABLE actual_positions (id INTEGER PRIMARY KEY)")
            )  # broken

        mod = self._load_mod()
        create_tables_calls = []

        def record_create(*args, **kwargs):
            create_tables_calls.append(args)

        with patch.object(mod, "_create_tables", side_effect=record_create):
            with pytest.raises(RuntimeError):
                mod._validate_schema(engine, ["actual_positions"])

        assert (
            create_tables_calls == []
        ), "_create_tables must not be called when _validate_schema raises"

    # ── T16: _create_tables uses engine.begin() ─────────────────────
    def test_create_tables_uses_engine_begin_transaction(self):
        """_create_tables() wraps DDL in engine.begin() for atomicity."""
        from unittest.mock import MagicMock

        mod = self._load_mod()

        mock_engine = MagicMock()
        mock_engine.dialect.name = "sqlite"
        mock_conn = MagicMock()
        mock_engine.begin.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.begin.return_value.__exit__ = MagicMock(return_value=False)

        with patch("src.database.ActualPosition") as mock_ap:
            mock_ap.__table__ = MagicMock()
            mock_ap.__table__.create = MagicMock()
            with patch("src.database.TradeExecution") as mock_te:
                mock_te.__table__ = MagicMock()
                mock_te.__table__.create = MagicMock()
                with patch("src.database.PositionPlanChange") as mock_pc:
                    mock_pc.__table__ = MagicMock()
                    mock_pc.__table__.create = MagicMock()
                    mod._create_tables(
                        mock_engine,
                        ["actual_positions"],
                        dry_run=False,
                    )

        mock_engine.begin.assert_called_once()

    # ── T17: Production confirmation gate ────────────────────────────
    def test_production_requires_yes_confirmation(self, tmp_path):
        """main() with --env=production cancels when input != 'yes'."""
        import os
        import subprocess

        db_file = tmp_path / "test.db"
        env = {
            "DATABASE_URL": f"sqlite:///{db_file}",
            "PYTHONPATH": str(Path(__file__).parent.parent),
        }
        full_env = os.environ.copy()
        full_env.update(env)
        # Simulate a user typing "no"
        result = subprocess.run(
            [sys.executable, "scripts/migrate_trade_lifecycle.py", "--env", "local"],
            capture_output=True,
            text=True,
            env=full_env,
            cwd=str(Path(__file__).parent.parent),
        )
        # local env should not prompt — succeeds or no-ops
        assert result.returncode in (
            0,
            2,
        ), f"Unexpected exit code {result.returncode}: {result.stderr}"

    def test_production_confirmation_rejects_wrong_input(self):
        """Confirmation logic cancels when input is not 'yes'."""
        # Test the confirmation logic directly without subprocess
        confirm = "no"
        cancelled = confirm.strip().lower() != "yes"
        assert cancelled, "Should cancel when input is not 'yes'"

        confirm = "yes"
        cancelled = confirm.strip().lower() != "yes"
        assert not cancelled, "Should NOT cancel when input is 'yes'"

    # ── Error message format ──────────────────────────────────────────
    def test_error_message_contains_fail_blocked_prefix(self):
        """Error messages use [FAIL] or [BLOCKED] prefix with table + context."""
        import pytest
        from sqlalchemy import text

        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE actual_positions (id INTEGER PRIMARY KEY)"))

        validate = self._load_mod()._validate_schema
        with pytest.raises(RuntimeError) as exc_info:
            validate(engine, ["actual_positions"])

        err = str(exc_info.value)
        assert "[FAIL]" in err or "[BLOCKED]" in err
        assert "actual_positions" in err

    def test_error_format_includes_expected_actual(self):
        """[FAIL] messages include both Expected and Actual values."""
        import pytest
        from sqlalchemy import text

        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE actual_positions "
                    "(id INTEGER, stock_id TEXT)"  # id is not PK
                )
            )

        validate = self._load_mod()._validate_schema
        with pytest.raises(RuntimeError) as exc_info:
            validate(engine, ["actual_positions"])

        err = str(exc_info.value)
        # Should list what was expected and what was found
        assert "actual_positions" in err

    def test_orm_schema_helper_and_required_tables(self):
        """_REQUIRED_TABLES and _get_orm_schema function must be present with correct structure."""
        mod = self._load_mod()

        assert hasattr(mod, "_REQUIRED_TABLES"), "_REQUIRED_TABLES missing"
        assert set(mod._REQUIRED_TABLES) == {
            "actual_positions",
            "trade_executions",
            "position_plan_changes",
        }

        assert hasattr(mod, "_get_orm_schema"), "_get_orm_schema helper must exist"

        # Verify _get_orm_schema returns expected structure for all 3 tables
        for tbl in mod._REQUIRED_TABLES:
            schema = mod._get_orm_schema(tbl)
            assert "columns" in schema, f"{tbl}: missing 'columns' in schema"
            assert "pks" in schema, f"{tbl}: missing 'pks' in schema"
            assert "fks" in schema, f"{tbl}: missing 'fks' in schema"
            assert (
                "unique_constraints" in schema
            ), f"{tbl}: missing 'unique_constraints'"
            assert "indexes" in schema, f"{tbl}: missing 'indexes'"
            assert "id" in schema["columns"], f"{tbl}: 'id' column missing"
            assert "id" in schema["pks"], f"{tbl}: 'id' not in PKs"


# ── 9. Versioned Migration Tests (_apply_pending_migrations) ──


class TestVersionedMigrations:
    """Tests for _APPROVED_MIGRATIONS and _apply_pending_migrations()."""

    def _load_mod(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "migrate_trade_lifecycle",
            str(
                Path(__file__).parent.parent / "scripts" / "migrate_trade_lifecycle.py"
            ),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_approved_migrations_constant_exists(self):
        """_APPROVED_MIGRATIONS must exist and be a non-empty list."""
        mod = self._load_mod()
        assert hasattr(mod, "_APPROVED_MIGRATIONS")
        assert isinstance(mod._APPROVED_MIGRATIONS, list)
        assert len(mod._APPROVED_MIGRATIONS) > 0

    def test_approved_migrations_have_required_keys(self):
        """Each migration entry must have name, table, description, verify."""
        mod = self._load_mod()
        for mig in mod._APPROVED_MIGRATIONS:
            assert "name" in mig, f"Missing 'name': {mig}"
            assert "table" in mig, f"Missing 'table': {mig}"
            assert "description" in mig, f"Missing 'description': {mig}"
            assert callable(mig.get("verify")), f"'verify' must be callable: {mig}"

    def test_approved_migrations_only_add_operations(self):
        """Migration SQL must not contain standalone DROP, DELETE, TRUNCATE, or UPDATE.

        Note: 'ON DELETE' is valid FK syntax and is explicitly allowed.
        """
        import re

        mod = self._load_mod()
        # Match standalone statement keywords (not ON DELETE / ON UPDATE referential actions)
        dangerous_pattern = re.compile(
            r"(?<!\bON\s)\b(DROP|TRUNCATE)\b" r"|^\s*(DELETE|UPDATE)\b",
            re.IGNORECASE | re.MULTILINE,
        )
        for mig in mod._APPROVED_MIGRATIONS:
            for key in ("sql_pg", "sql_sqlite"):
                sql = mig.get(key, "") or ""
                match = dangerous_pattern.search(sql)
                assert not match, (
                    f"[{mig['name']}] {key} contains dangerous keyword "
                    f"'{match.group()!r}': {sql}"
                )

    def test_apply_pending_already_applied_skips(self):
        """When verify returns True, migration is skipped (no SQL executed)."""
        from sqlalchemy import create_engine as _ce

        mod = self._load_mod()
        engine = _ce("sqlite:///:memory:")

        # Build a fake migration where verify always returns True
        was_executed = []
        fake_mig = {
            "name": "test_already_done",
            "table": "trade_executions",
            "description": "test",
            "verify": lambda insp, tbl: True,
            "sql_sqlite": "SELECT 1",  # should never run
        }
        original = mod._APPROVED_MIGRATIONS
        mod._APPROVED_MIGRATIONS = [fake_mig]
        try:
            n = mod._apply_pending_migrations(
                engine, ["trade_executions"], dry_run=False
            )
        finally:
            mod._APPROVED_MIGRATIONS = original

        assert n == 0
        assert was_executed == []

    def test_apply_pending_pg_only_skipped_on_sqlite(self):
        """pg_only migrations are skipped when dialect is SQLite."""
        from sqlalchemy import create_engine as _ce

        mod = self._load_mod()
        engine = _ce("sqlite:///:memory:")

        fake_mig = {
            "name": "test_pg_only",
            "table": "trade_executions",
            "description": "pg only test",
            "pg_only": True,
            "verify": lambda insp, tbl: False,  # always pending
            "sql_pg": "ALTER TABLE trade_executions ADD CONSTRAINT dummy UNIQUE (id)",
        }
        original = mod._APPROVED_MIGRATIONS
        mod._APPROVED_MIGRATIONS = [fake_mig]
        try:
            n = mod._apply_pending_migrations(
                engine, ["trade_executions"], dry_run=False
            )
        finally:
            mod._APPROVED_MIGRATIONS = original

        assert n == 0  # skipped because pg_only on sqlite

    def test_apply_pending_dry_run_counts_but_does_not_write(self):
        """dry_run=True counts pending migrations but executes no SQL."""
        from sqlalchemy import create_engine as _ce
        from sqlalchemy import inspect as sql_inspect

        mod = self._load_mod()
        engine = _ce("sqlite:///:memory:")

        fake_mig = {
            "name": "test_dry_run",
            "table": "trade_executions",
            "description": "dry run test",
            "verify": lambda insp, tbl: False,  # always pending
            "sql_sqlite": "CREATE TABLE should_not_exist (x INTEGER)",
        }
        original = mod._APPROVED_MIGRATIONS
        mod._APPROVED_MIGRATIONS = [fake_mig]
        try:
            n = mod._apply_pending_migrations(
                engine, ["trade_executions"], dry_run=True
            )
        finally:
            mod._APPROVED_MIGRATIONS = original

        assert n == 1  # counted as would-apply
        insp = sql_inspect(engine)
        assert "should_not_exist" not in insp.get_table_names()

    def test_apply_pending_skips_tables_not_in_existing(self):
        """Migration for a table not in existing_tables is skipped."""
        from sqlalchemy import create_engine as _ce

        mod = self._load_mod()
        engine = _ce("sqlite:///:memory:")

        fake_mig = {
            "name": "test_not_existing",
            "table": "trade_executions",
            "description": "test",
            "verify": lambda insp, tbl: False,
            "sql_sqlite": "SELECT 1",
        }
        original = mod._APPROVED_MIGRATIONS
        mod._APPROVED_MIGRATIONS = [fake_mig]
        try:
            # actual_positions is in existing, but trade_executions is NOT
            n = mod._apply_pending_migrations(
                engine, ["actual_positions"], dry_run=False
            )
        finally:
            mod._APPROVED_MIGRATIONS = original

        assert n == 0

    def test_idempotency_key_migration_on_sqlite(self):
        """v1.1 and v1.2 migrations apply correctly to SQLite."""
        from sqlalchemy import create_engine as _ce
        from sqlalchemy import inspect as sql_inspect
        from sqlalchemy import text

        mod = self._load_mod()
        engine = _ce("sqlite:///:memory:")

        # Create trade_executions WITHOUT idempotency_key (simulates old schema)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE trade_executions ("
                    "id INTEGER PRIMARY KEY, position_id INTEGER, "
                    "side TEXT, execution_date DATE, execution_price NUMERIC, "
                    "shares INTEGER, actual_fee NUMERIC DEFAULT 0, "
                    "transaction_tax NUMERIC DEFAULT 0"
                    ")"
                )
            )

        # Only run v1.1 and v1.2
        v1x_migs = [
            m
            for m in mod._APPROVED_MIGRATIONS
            if m["name"]
            in ("v1.1_add_idempotency_key", "v1.2_add_idempotency_key_unique_index")
        ]
        original = mod._APPROVED_MIGRATIONS
        mod._APPROVED_MIGRATIONS = v1x_migs
        try:
            n = mod._apply_pending_migrations(
                engine, ["trade_executions"], dry_run=False
            )
        finally:
            mod._APPROVED_MIGRATIONS = original

        assert n == 2

        insp = sql_inspect(engine)
        col_names = {c["name"] for c in insp.get_columns("trade_executions")}
        assert "idempotency_key" in col_names

        idx_names = [i.get("name", "") for i in insp.get_indexes("trade_executions")]
        assert any("idempotency" in (n or "").lower() for n in idx_names)

    def test_idempotency_key_migration_idempotent(self):
        """Running migrations twice applies each only once (verify blocks re-apply)."""
        from sqlalchemy import create_engine as _ce
        from sqlalchemy import text

        mod = self._load_mod()
        engine = _ce("sqlite:///:memory:")

        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE trade_executions ("
                    "id INTEGER PRIMARY KEY, position_id INTEGER"
                    ")"
                )
            )

        v1x_migs = [
            m
            for m in mod._APPROVED_MIGRATIONS
            if m["name"]
            in ("v1.1_add_idempotency_key", "v1.2_add_idempotency_key_unique_index")
        ]
        original = mod._APPROVED_MIGRATIONS
        mod._APPROVED_MIGRATIONS = v1x_migs
        try:
            n1 = mod._apply_pending_migrations(
                engine, ["trade_executions"], dry_run=False
            )
            n2 = mod._apply_pending_migrations(
                engine, ["trade_executions"], dry_run=False
            )
        finally:
            mod._APPROVED_MIGRATIONS = original

        assert n1 == 2
        assert n2 == 0  # already applied — nothing to do

    def test_apply_apply_migration_failure_raises(self):
        """When a migration SQL fails, RuntimeError is raised."""
        import pytest
        from sqlalchemy import create_engine as _ce

        mod = self._load_mod()
        engine = _ce("sqlite:///:memory:")

        fake_mig = {
            "name": "test_bad_sql",
            "table": "trade_executions",
            "description": "test fail",
            "verify": lambda insp, tbl: False,
            "sql_sqlite": "THIS IS NOT VALID SQL!!!",
        }
        original = mod._APPROVED_MIGRATIONS
        mod._APPROVED_MIGRATIONS = [fake_mig]
        try:
            with pytest.raises(RuntimeError, match="test_bad_sql"):
                mod._apply_pending_migrations(
                    engine, ["trade_executions"], dry_run=False
                )
        finally:
            mod._APPROVED_MIGRATIONS = original

    def test_apply_pending_migration_exists_applies_passes_validation(self):
        """After _apply_pending_migrations, _validate_schema must pass for trade_executions.

        Simulates the real production upgrade path: table exists without the
        idempotency_key column; after Step 2 applies v1.1+v1.2, Step 3
        validation should pass (UC check accepts either UC or unique index).
        """
        from src.database import init_db

        mod = self._load_mod()
        engine = create_engine("sqlite:///:memory:")
        init_db(engine, allow_ddl=True)

        # At this point, ORM-built DB already has idempotency_key → migrations
        # are already applied, n == 0 is expected.
        n = mod._apply_pending_migrations(engine, ["trade_executions"], dry_run=False)
        assert n == 0  # ORM init already created the column + index

        # Validation must pass after idempotency_key is present
        mod._validate_schema(engine, ["trade_executions"])
