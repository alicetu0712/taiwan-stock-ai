"""
scripts/migrate_trade_lifecycle.py — Phase 1 Trade Lifecycle Schema Migration

此腳本是唯一允許在 Production PostgreSQL 建立以下三張表的授權管道：
  - actual_positions
  - trade_executions
  - position_plan_changes

安全機制：
  - 預設 --env=local（連本地 SQLite），需明確傳 --env=production 才連 Neon。
  - --dry-run 模式：只顯示執行計畫，不寫入任何資料。
  - 不執行 DROP TABLE / ALTER existing columns / DELETE / UPDATE。
  - 4-step Preflight：先驗證既有表 Schema，偵測 Drift 立即中止，再建立缺失表。
  - 執行後完整 Post-Migration 驗證（欄位、型別、NOT NULL、NUMERIC 精度、PK、FK、
    Unique Constraint、Index）。

Validation Result Classification:
  PASS    = 已驗證且一致
  FAIL    = 已確認 Schema 不一致（欄位缺失、型別錯誤、PK 錯誤、Index 缺失等）
  BLOCKED = 無法完成驗證（Inspector 例外、無法讀取 metadata）
  N/A     = ORM 未宣告此約束，DB 端亦不期望有

執行方式：
  # Dry-run（不寫入，只顯示計畫）
  python scripts/migrate_trade_lifecycle.py --dry-run

  # 連本地資料庫（預設）
  python scripts/migrate_trade_lifecycle.py

  # 連 Neon Production（需 NEON_URL 環境變數或 .env）
  python scripts/migrate_trade_lifecycle.py --env production

  # Production dry-run
  python scripts/migrate_trade_lifecycle.py --env production --dry-run

復原方案：
  三張新表均為空表，Migration 失敗或需回滾時執行：
    DROP TABLE IF EXISTS position_plan_changes;
    DROP TABLE IF EXISTS trade_executions;
    DROP TABLE IF EXISTS actual_positions;
  舊表（user_trades / position_monitor / forward_signals）不受影響。
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("migrate_trade_lifecycle")

_REQUIRED_TABLES = ["actual_positions", "trade_executions", "position_plan_changes"]

_REQUIRED_COLS = {
    "actual_positions": {
        "id",
        "stock_id",
        "stock_name",
        "position_type",
        "signal_source",
        "forward_signal_id",
        "status",
        "open_date",
        "close_date",
        "remaining_shares",
        "avg_cost_per_share",
        "total_cost_basis",
        "realized_pnl",
        "target_price",
        "stop_price",
        "original_plan_snapshot",
        "notes",
        "created_at",
        "updated_at",
    },
    "trade_executions": {
        "id",
        "position_id",
        "side",
        "execution_date",
        "execution_datetime",
        "execution_price",
        "shares",
        "actual_fee",
        "transaction_tax",
        "linked_forward_signal_id",
        "notes",
        "is_cancelled",
        "cancel_reason",
        "cancelled_at",
        "created_at",
        "updated_at",
    },
    "position_plan_changes": {
        "id",
        "position_id",
        "changed_at",
        "field_name",
        "old_value",
        "new_value",
        "reason",
        "created_at",
    },
}

# NOT NULL columns per table (from ORM nullable=False)
_NOT_NULL_COLS = {
    "actual_positions": {
        "stock_id",
        "position_type",
        "signal_source",
        "status",
        "open_date",
        "remaining_shares",
        "avg_cost_per_share",
        "total_cost_basis",
        "realized_pnl",
    },
    "trade_executions": {
        "position_id",
        "side",
        "execution_date",
        "execution_price",
        "shares",
        "actual_fee",
        "transaction_tax",
        "is_cancelled",
    },
    "position_plan_changes": {
        "position_id",
        "changed_at",
        "field_name",
    },
}

# Expected NUMERIC(precision, scale) per column (PostgreSQL only)
_NUMERIC_PRECISION = {
    "actual_positions": {
        "avg_cost_per_share": (12, 4),
        "total_cost_basis": (14, 2),
        "realized_pnl": (14, 2),
        "target_price": (10, 2),
        "stop_price": (10, 2),
    },
    "trade_executions": {
        "execution_price": (10, 2),
        "actual_fee": (10, 2),
        "transaction_tax": (10, 2),
    },
    "position_plan_changes": {
        "old_value": (10, 2),
        "new_value": (10, 2),
    },
}

# VARCHAR / String max-length constraints (from ORM String(n), PostgreSQL only)
_VARCHAR_LENGTHS = {
    "actual_positions": {
        "stock_id": 10,
        "stock_name": 50,
        "position_type": 10,
        "signal_source": 20,
        "status": 20,
    },
    "trade_executions": {
        "side": 4,
        "cancel_reason": 200,
    },
    "position_plan_changes": {
        "field_name": 30,
    },
}

# Expected primary key columns per table
_PRIMARY_KEYS = {
    "actual_positions": {"id"},
    "trade_executions": {"id"},
    "position_plan_changes": {"id"},
}

# Columns that must have an index (from ORM index=True)
_INDEXED_COLS = {
    "actual_positions": {"stock_id"},
    "trade_executions": {"position_id"},
    "position_plan_changes": {"position_id"},
}

# Expected unique constraint column sets per table.
# ORM defines NO UniqueConstraint() for any of these three tables.
_UNIQUE_CONSTRAINTS: dict = {
    "actual_positions": [],
    "trade_executions": [],
    "position_plan_changes": [],
}

# FK constraints from ORM metadata.
# The ORM intentionally declares NO ForeignKey() for position_id / forward_signal_id
# (cross-table references managed at application layer, not DB-level FK constraints).
# Validation for these tables: N/A (no DB-level FK expected).
_FK_CONSTRAINTS: dict = {
    "actual_positions": [],
    "trade_executions": [],
    "position_plan_changes": [],
}

_PROTECTED_TABLES = {
    "user_trades",
    "position_monitor",
    "forward_signals",
    "analysis_results",
    "recommendations",
    "stocks",
    "daily_prices",
}


def _get_engine(env: str):
    """連接指定環境的資料庫，回傳 engine。"""
    from sqlalchemy import create_engine

    if env == "production":
        import os

        from dotenv import load_dotenv

        load_dotenv()
        url = os.environ.get("NEON_URL", "")
        if not url:
            logger.error("NEON_URL 未設定。請在 .env 或環境變數中設定 NEON_URL。")
            sys.exit(1)
        url = url.replace("postgres://", "postgresql://", 1)
        logger.info("Production mode: connecting to Neon PostgreSQL")
        engine = create_engine(url, connect_args={"sslmode": "require"})
    else:
        from config import DATABASE_URL

        logger.info(f"Local mode: {DATABASE_URL[:50]}")
        engine = create_engine(DATABASE_URL)

    from sqlalchemy import text

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        logger.error(f"資料庫連線失敗：{e}")
        sys.exit(1)

    return engine


def _validate_fk_details(
    tbl: str, expected_fks: list, actual_fks: list, issues: list
) -> None:
    """Compare ORM-declared FK constraints vs DB (used only when ORM declares FKs)."""
    actual_by_col: dict = {}
    for fk in actual_fks:
        constrained = fk.get("constrained_columns", [])
        if constrained:
            actual_by_col[constrained[0]] = fk

    for exp in expected_fks:
        local_col = exp.get("local_col")
        ref_table = exp.get("referred_table")
        ref_col = exp.get("referred_col")
        actual = actual_by_col.get(local_col)
        if actual is None:
            issues.append(
                f"[FAIL] {tbl}.{local_col}: FK 缺失 — "
                f"Expected FK → {ref_table}.{ref_col}, Actual none"
            )
            continue
        actual_ref_table = actual.get("referred_table")
        if actual_ref_table != ref_table:
            issues.append(
                f"[FAIL] {tbl}.{local_col}: FK 參照表 — "
                f"Expected → {ref_table}, Actual → {actual_ref_table}"
            )
        exp_on_delete = exp.get("ondelete")
        actual_on_delete = (actual.get("options") or {}).get("ondelete")
        if exp_on_delete and exp_on_delete != actual_on_delete:
            issues.append(
                f"[FAIL] {tbl}.{local_col}: FK ON DELETE — "
                f"Expected {exp_on_delete}, Actual {actual_on_delete}"
            )


def _create_tables(engine, missing: list, dry_run: bool) -> None:
    """按依賴順序建立缺失的新表。

    PostgreSQL: DDL wrapped in explicit transaction (atomic rollback on failure).
    SQLite: DDL is not fully transactional; warn and proceed.
    建立順序：actual_positions → trade_executions → position_plan_changes
    （後兩者在應用層依賴 actual_positions.id）
    """
    from src.database import (  # noqa: F401
        ActualPosition,
        PositionPlanChange,
        TradeExecution,
    )

    table_map = {
        "actual_positions": ActualPosition.__table__,
        "trade_executions": TradeExecution.__table__,
        "position_plan_changes": PositionPlanChange.__table__,
    }

    if dry_run:
        from sqlalchemy.dialects import postgresql as pg_dialect
        from sqlalchemy.schema import CreateTable

        for tbl_name in _REQUIRED_TABLES:
            if tbl_name not in missing:
                continue
            ddl = str(
                CreateTable(table_map[tbl_name]).compile(dialect=pg_dialect.dialect())
            )
            logger.info(f"[DRY-RUN] Would CREATE TABLE {tbl_name}:\n{ddl}")
        return

    is_pg = engine.dialect.name == "postgresql"
    if is_pg:
        logger.info("PostgreSQL DDL 使用 engine.begin() 交易保護（atomic）")
    else:
        logger.warning(
            "SQLite DDL 不完全支援 atomic rollback。"
            "若 Migration 中途失敗，請手動確認資料庫狀態。"
        )

    try:
        with engine.begin() as conn:
            for tbl_name in _REQUIRED_TABLES:
                if tbl_name not in missing:
                    continue
                table_obj = table_map[tbl_name]
                logger.info(f"  CREATE TABLE {tbl_name} ...")
                table_obj.create(bind=conn, checkfirst=True)
                logger.info(f"  → {tbl_name} ✓")
    except Exception as e:
        if is_pg:
            logger.error(f"建表失敗（PostgreSQL 已自動回滾）：{e}")
        else:
            logger.error(f"建表失敗：{e}")
        raise


def _validate_schema(engine, tables: list) -> None:
    """全面 Schema 驗證（9 大檢查點，16 項子檢查）。

    Result classification:
      PASS    = 已驗證且一致
      FAIL    = 已確認 Schema 不一致
      BLOCKED = 無法完成驗證（Inspector 例外、metadata 無法讀取）
      N/A     = ORM 未宣告此約束，DB 端亦不期望有

    只有非必要的純診斷性資訊使用 WARNING。
    所有必要約束驗證失敗 → FAIL 或 BLOCKED，不得回報 PASS 後繼續。

    Error format:
      [FAIL]    Table.Column: 說明 — Expected X, Actual Y
      [BLOCKED] Table: 說明 — {exception}

    若有任何 FAIL 或 BLOCKED：raise RuntimeError，列出全部問題。
    禁止自動修復任何 Schema Drift。
    """
    from sqlalchemy import inspect as _insp

    insp = _insp(engine)
    is_pg = engine.dialect.name == "postgresql"
    issues: list[str] = []

    for tbl in tables:
        # ── Check 1: Table 可讀（欄位 metadata）──────────────────────
        try:
            cols_info = insp.get_columns(tbl)
        except Exception as e:
            issues.append(f"[BLOCKED] {tbl}: 無法讀取欄位資訊 — {e}")
            continue

        existing_cols = {c["name"]: c for c in cols_info}

        # ── Check 2: Column 名稱存在性 ──────────────────────────────
        required = _REQUIRED_COLS.get(tbl, set())
        missing_cols = required - set(existing_cols)
        if missing_cols:
            issues.append(
                f"[FAIL] {tbl}: 缺少欄位 {sorted(missing_cols)} — "
                f"Expected all of {sorted(required)}"
            )
            continue  # 缺欄位 → 後續型別驗證無意義
        logger.info(f"  {tbl}: Check 2 (Column names) PASS ({len(existing_cols)} cols)")

        # ── Check 3: NOT NULL 約束（PostgreSQL only）─────────────────
        if is_pg:
            not_null = _NOT_NULL_COLS.get(tbl, set())
            nn_ok = True
            for col_name in sorted(not_null):
                col = existing_cols.get(col_name)
                if col is None:
                    continue
                if col.get("nullable", True):
                    issues.append(
                        f"[FAIL] {tbl}.{col_name}: NOT NULL — "
                        f"Expected NOT NULL, Actual nullable=True"
                    )
                    nn_ok = False
            if nn_ok:
                logger.info(f"  {tbl}: Check 3 (NOT NULL) PASS")

        # ── Check 4: NUMERIC precision/scale（PostgreSQL only）───────
        if is_pg:
            numeric_checks = _NUMERIC_PRECISION.get(tbl, {})
            num_ok = True
            for col_name, (exp_prec, exp_scale) in sorted(numeric_checks.items()):
                col = existing_cols.get(col_name)
                if col is None:
                    continue
                col_type = col.get("type")
                actual_prec = getattr(col_type, "precision", None)
                actual_scale = getattr(col_type, "scale", None)
                if actual_prec is None or actual_scale is None:
                    # Cannot read precision → BLOCKED (not Warning)
                    issues.append(
                        f"[BLOCKED] {tbl}.{col_name}: 無法讀取 NUMERIC precision/scale "
                        f"(type={col_type!r}) — "
                        f"Expected NUMERIC({exp_prec},{exp_scale})"
                    )
                    num_ok = False
                elif actual_prec != exp_prec or actual_scale != exp_scale:
                    issues.append(
                        f"[FAIL] {tbl}.{col_name}: NUMERIC precision — "
                        f"Expected NUMERIC({exp_prec},{exp_scale}), "
                        f"Actual NUMERIC({actual_prec},{actual_scale})"
                    )
                    num_ok = False
            if num_ok and numeric_checks:
                logger.info(f"  {tbl}: Check 4 (NUMERIC precision) PASS")

        # ── Check 5: VARCHAR 長度（PostgreSQL only）──────────────────
        if is_pg:
            varchar_checks = _VARCHAR_LENGTHS.get(tbl, {})
            vc_ok = True
            for col_name, exp_len in sorted(varchar_checks.items()):
                col = existing_cols.get(col_name)
                if col is None:
                    continue
                col_type = col.get("type")
                actual_len = getattr(col_type, "length", None)
                if actual_len is None:
                    issues.append(
                        f"[BLOCKED] {tbl}.{col_name}: 無法讀取 VARCHAR length "
                        f"(type={col_type!r}) — "
                        f"Expected VARCHAR({exp_len})"
                    )
                    vc_ok = False
                elif actual_len != exp_len:
                    issues.append(
                        f"[FAIL] {tbl}.{col_name}: VARCHAR length — "
                        f"Expected VARCHAR({exp_len}), "
                        f"Actual VARCHAR({actual_len})"
                    )
                    vc_ok = False
            if vc_ok and varchar_checks:
                logger.info(f"  {tbl}: Check 5 (VARCHAR length) PASS")

        # ── Check 6: Primary Key ─────────────────────────────────────
        try:
            pk_info = insp.get_pk_constraint(tbl)
            pk_cols = set(pk_info.get("constrained_columns", []))
            expected_pk = _PRIMARY_KEYS.get(tbl, {"id"})
            if expected_pk != pk_cols:
                issues.append(
                    f"[FAIL] {tbl}: PK — "
                    f"Expected {sorted(expected_pk)}, "
                    f"Actual {sorted(pk_cols)}"
                )
            else:
                logger.info(f"  {tbl}: Check 6 (PK) PASS {sorted(pk_cols)}")
        except Exception as e:
            issues.append(f"[BLOCKED] {tbl}: 無法讀取 PK constraint — {e}")

        # ── Check 7: Foreign Key ─────────────────────────────────────
        # ORM 未宣告 ForeignKey()（intentional: application-layer refs only）
        expected_fks = _FK_CONSTRAINTS.get(tbl, [])
        try:
            actual_fks = insp.get_foreign_keys(tbl)
            if expected_fks:
                # ORM declares FKs → must validate in detail
                _validate_fk_details(tbl, expected_fks, actual_fks, issues)
                logger.info(f"  {tbl}: Check 7 (FK) PASS")
            else:
                # ORM has no FK declared → N/A; warn if DB has unexpected FKs
                if actual_fks:
                    logger.warning(
                        f"  {tbl}: Check 7 (FK) N/A — "
                        f"ORM 無 FK 宣告，但 DB 有 {len(actual_fks)} 個 FK constraint "
                        f"（可能為手動建立）"
                    )
                else:
                    logger.info(f"  {tbl}: Check 7 (FK) N/A — ORM 無 ForeignKey() 宣告")
        except Exception as e:
            if expected_fks:
                issues.append(f"[BLOCKED] {tbl}: 無法讀取 FK constraints — {e}")
            else:
                logger.warning(
                    f"  {tbl}: Check 7 (FK) 讀取失敗（{e}），ORM 無 FK 宣告，跳過"
                )

        # ── Check 8: Unique Constraint ───────────────────────────────
        expected_ucs = [frozenset(s) for s in _UNIQUE_CONSTRAINTS.get(tbl, [])]
        try:
            actual_ucs = insp.get_unique_constraints(tbl)
            # Compare by column sets (ignore auto-generated constraint names)
            actual_uc_sets = [
                frozenset(uc.get("column_names", [])) for uc in actual_ucs
            ]
            missing_ucs = [s for s in expected_ucs if s not in actual_uc_sets]
            if missing_ucs:
                issues.append(
                    f"[FAIL] {tbl}: Unique Constraint 缺失 — "
                    f"Expected {[sorted(s) for s in missing_ucs]}"
                )
            else:
                logger.info(
                    f"  {tbl}: Check 8 (Unique Constraint) PASS "
                    f"({len(actual_uc_sets)} found, {len(expected_ucs)} expected)"
                )
        except Exception as e:
            if expected_ucs:
                issues.append(f"[BLOCKED] {tbl}: 無法讀取 Unique Constraints — {e}")
            else:
                logger.warning(
                    f"  {tbl}: Check 8 (UC) 讀取失敗（{e}），ORM 無 UC 宣告，跳過"
                )

        # ── Check 9: Index 存在性 ────────────────────────────────────
        try:
            indexes = insp.get_indexes(tbl)
            indexed_col_sets = [
                frozenset(idx.get("column_names", [])) for idx in indexes
            ]
            required_idx = _INDEXED_COLS.get(tbl, set())
            idx_ok = True
            for col_name in sorted(required_idx):
                has_idx = any({col_name} <= col_set for col_set in indexed_col_sets)
                if not has_idx:
                    issues.append(
                        f"[FAIL] {tbl}.{col_name}: Index — "
                        f"ORM 定義 index=True，DB 無對應 index"
                    )
                    idx_ok = False
            if idx_ok:
                logger.info(
                    f"  {tbl}: Check 9 (Index) PASS "
                    f"({sorted(idx.get('name', '?') for idx in indexes if idx.get('name'))})"
                )
        except Exception as e:
            issues.append(f"[BLOCKED] {tbl}: 無法讀取 Index 資訊 — {e}")

    if issues:
        fail_count = sum(1 for i in issues if i.startswith("[FAIL]"))
        blocked_count = sum(1 for i in issues if i.startswith("[BLOCKED]"))
        raise RuntimeError(
            f"Schema 驗證失敗 — {fail_count} FAIL, {blocked_count} BLOCKED：\n"
            + "\n".join(f"  {i}" for i in issues)
            + "\n\n"
            "Migration 不會自動修復以上差異（禁止 AUTO ALTER / DROP）。\n"
            "請人工審核並修復後重新執行。"
        )

    logger.info(f"Schema 完整驗證通過 ✓ ({len(tables)} 張表)")


def _validate_protected_tables_untouched(engine, before_cols: dict):
    """確認受保護的舊表欄位未被修改。"""
    from sqlalchemy import inspect

    insp = inspect(engine)
    for tbl, cols_before in before_cols.items():
        try:
            cols_after = {c["name"] for c in insp.get_columns(tbl)}
        except Exception:
            continue
        added = cols_after - cols_before
        removed = cols_before - cols_after
        if added or removed:
            raise RuntimeError(
                f"受保護的表 {tbl} 被意外修改！"
                f"新增欄位：{added}，刪除欄位：{removed}"
            )
    logger.info("受保護的舊表完整性確認 ✓")


def main():
    parser = argparse.ArgumentParser(
        description="Phase 1 Trade Lifecycle Schema Migration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--env",
        choices=["local", "production"],
        default="local",
        help="目標環境（預設：local）。Production 需要 NEON_URL。",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只顯示執行計畫，不實際寫入。",
    )
    args = parser.parse_args()

    dry_run = args.dry_run
    env = args.env

    logger.info("=" * 60)
    logger.info("Phase 1 Trade Lifecycle Migration")
    logger.info(f"  env      = {env}")
    logger.info(f"  dry_run  = {dry_run}")
    logger.info("=" * 60)

    if env == "production" and not dry_run:
        confirm = input(
            "\n⚠️  即將對 Production Neon 資料庫執行 Schema Migration。\n"
            "請輸入 'yes' 確認（其他輸入取消）：> "
        )
        if confirm.strip().lower() != "yes":
            logger.info("Migration 取消。")
            sys.exit(0)

    engine = _get_engine(env)

    # ── Step 1: Preflight ────────────────────────────────────────────
    logger.info("\n── Step 1: Preflight ──")
    from sqlalchemy import inspect as _insp

    insp = _insp(engine)
    all_tables = set(insp.get_table_names())
    missing = [t for t in _REQUIRED_TABLES if t not in all_tables]
    already_exist = [t for t in _REQUIRED_TABLES if t in all_tables]

    protected_present = _PROTECTED_TABLES & all_tables
    logger.info(f"受保護的既有表：{sorted(protected_present)}")
    logger.info(f"已存在的目標表：{already_exist}")
    logger.info(f"缺失的目標表  ：{missing}")

    # ── Step 2: Validate existing tables FIRST (Stop on Drift) ──────
    if already_exist:
        logger.info(f"\n── Step 2: 驗證既有表 Schema（{already_exist}）──")
        try:
            _validate_schema(engine, already_exist)
            logger.info("既有表 Schema 驗證通過 ✓")
        except RuntimeError as drift_err:
            logger.error("\n" + "=" * 60)
            logger.error("Schema Drift 偵測！Migration 中止。")
            logger.error("=" * 60)
            logger.error(str(drift_err))
            logger.error("\n既有表存在 Schema 不一致，不執行任何 DDL。")
            logger.error("請人工修復後重新執行。")
            sys.exit(2)

    if not missing:
        logger.info("\n三張表已全部存在，Schema 驗證通過。無需 Migration。")
        sys.exit(0)

    # ── Step 3: Controlled Migration ─────────────────────────────────
    # Snapshot protected tables for post-migration integrity check
    protected_snapshot: dict = {}
    for tbl in _PROTECTED_TABLES:
        try:
            protected_snapshot[tbl] = {c["name"] for c in insp.get_columns(tbl)}
        except Exception:
            pass

    logger.info(f"\n── Step 3: Controlled Migration（{missing}）──")
    _create_tables(engine, missing, dry_run)

    if dry_run:
        logger.info("\n[DRY-RUN] 以上為 Migration 計畫，未執行任何寫入。")
        sys.exit(0)

    # ── Step 4: Post-Migration Validation ────────────────────────────
    logger.info("\n── Step 4: Post-Migration 完整驗證 ──")
    _validate_schema(engine, _REQUIRED_TABLES)
    _validate_protected_tables_untouched(engine, protected_snapshot)

    logger.info("\n" + "=" * 60)
    logger.info("Migration 完成 ✓")
    logger.info("=" * 60)
    logger.info("\n後續步驟：")
    logger.info("  1. 確認 GitHub Actions Daily Pipeline 正常執行")
    logger.info("  2. 在 Dashboard 記錄第一筆 ACTUAL 成交，確認寫入正常")
    logger.info(
        "  3. 若需回滾：DROP TABLE position_plan_changes, "
        "trade_executions, actual_positions"
    )


if __name__ == "__main__":
    main()
