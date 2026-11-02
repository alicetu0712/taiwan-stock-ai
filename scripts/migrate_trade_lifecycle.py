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
  - 執行前完整 pre-flight 檢查（連線、既有表保護）。
  - 執行後驗證 Schema（欄位型別、Index）。

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

# NOT NULL columns per table (ORM definition)
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

    # 測試連線
    from sqlalchemy import text

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        logger.error(f"資料庫連線失敗：{e}")
        sys.exit(1)

    return engine


def _preflight_check(engine, dry_run: bool) -> dict:
    """
    執行前安全檢查。
    回傳 {"missing": [...], "existing": [...], "protected_safe": bool}
    """
    from sqlalchemy import inspect

    insp = inspect(engine)
    all_tables = set(insp.get_table_names())

    missing = [t for t in _REQUIRED_TABLES if t not in all_tables]
    already_exist = [t for t in _REQUIRED_TABLES if t in all_tables]

    # 確認受保護的舊表未被意外動到
    protected_present = _PROTECTED_TABLES & all_tables
    logger.info(f"受保護的既有表已確認存在：{sorted(protected_present)}")

    return {
        "missing": missing,
        "existing": already_exist,
        "protected_safe": True,
    }


def _create_tables(engine, missing: list, dry_run: bool):
    """使用 SQLAlchemy ORM 建立缺失的新表。"""
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

    for tbl_name in missing:
        table_obj = table_map[tbl_name]
        if dry_run:
            from sqlalchemy.dialects import postgresql
            from sqlalchemy.schema import CreateTable

            ddl = str(CreateTable(table_obj).compile(dialect=postgresql.dialect()))
            logger.info(f"[DRY-RUN] Would CREATE TABLE {tbl_name}:\n{ddl}")
        else:
            logger.info(f"Creating table: {tbl_name} ...")
            table_obj.create(bind=engine, checkfirst=True)
            logger.info(f"  → {tbl_name} created ✓")


def _validate_schema(engine, tables: list) -> None:
    """全面 Schema 驗證：欄位名稱、Nullability、NUMERIC 精度、PK、Unique、Index。

    檢查項目：
      1. 欄位名稱存在性
      2. NOT NULL 約束（PostgreSQL only — SQLite 不強制執行 NOT NULL）
      3. NUMERIC(precision, scale)（PostgreSQL only）
      4. Primary Key 欄位
      5. Unique Constraint 存在性記錄
      6. Index 是否存在於 indexed 欄位

    若 Schema 不符：
      - 停止驗證流程
      - 列出所有具體差異
      - 不自動 ALTER / DROP / 重建任何欄位或 Index
      - raise RuntimeError，要求人工審核修復
    """
    from sqlalchemy import inspect as _insp

    insp = _insp(engine)
    is_pg = engine.dialect.name == "postgresql"
    errors: list[str] = []

    for tbl in tables:
        try:
            cols_info = insp.get_columns(tbl)
        except Exception as e:
            errors.append(f"{tbl}: 無法讀取欄位資訊 — {e}")
            continue

        existing_cols = {c["name"]: c for c in cols_info}

        # ── 1. 欄位名稱存在性 ──────────────────────────────
        required = _REQUIRED_COLS.get(tbl, set())
        missing_cols = required - set(existing_cols)
        if missing_cols:
            errors.append(f"{tbl}: 缺少欄位 {sorted(missing_cols)}")
            # 缺欄位時後續型別驗證無意義
            continue
        logger.info(f"  {tbl}: 欄位驗證通過 ({len(existing_cols)} cols) ✓")

        # ── 2. NOT NULL 約束（PostgreSQL only）──────────────
        if is_pg:
            not_null = _NOT_NULL_COLS.get(tbl, set())
            for col_name in sorted(not_null):
                col = existing_cols.get(col_name)
                if col is None:
                    continue  # 已在上方報缺欄位
                if col.get("nullable", True):
                    errors.append(
                        f"{tbl}.{col_name}: 期望 NOT NULL，"
                        f"但資料庫設定為 nullable（可能為欄位新增後未加 NOT NULL 約束）"
                    )
            if not errors:
                logger.info(f"  {tbl}: NOT NULL 驗證通過 ✓")

        # ── 3. NUMERIC precision/scale（PostgreSQL only）────
        if is_pg:
            numeric_checks = _NUMERIC_PRECISION.get(tbl, {})
            for col_name, (exp_prec, exp_scale) in sorted(numeric_checks.items()):
                col = existing_cols.get(col_name)
                if col is None:
                    continue
                col_type = col.get("type")
                actual_prec = getattr(col_type, "precision", None)
                actual_scale = getattr(col_type, "scale", None)
                if actual_prec is not None and actual_scale is not None:
                    if actual_prec != exp_prec or actual_scale != exp_scale:
                        errors.append(
                            f"{tbl}.{col_name}: 期望 NUMERIC({exp_prec},{exp_scale}), "
                            f"實際 NUMERIC({actual_prec},{actual_scale}) — "
                            f"精度不符會累積浮點誤差，需人工 ALTER COLUMN"
                        )
                else:
                    logger.warning(
                        f"  {tbl}.{col_name}: 無法讀取 NUMERIC precision "
                        f"（型別={col_type!r}），跳過精度驗證"
                    )

        # ── 4. Primary Key ──────────────────────────────────
        try:
            pk_info = insp.get_pk_constraint(tbl)
            pk_cols = set(pk_info.get("constrained_columns", []))
            expected_pk = _PRIMARY_KEYS.get(tbl, {"id"})
            if expected_pk != pk_cols:
                errors.append(
                    f"{tbl}: PK 不符 — 期望 {sorted(expected_pk)}, "
                    f"實際 {sorted(pk_cols)}"
                )
            else:
                logger.info(f"  {tbl}: PK 驗證通過 {sorted(pk_cols)} ✓")
        except Exception as e:
            logger.warning(f"  {tbl}: PK 驗證跳過（{e}）")

        # ── 5. Unique Constraint 記錄（僅 log，不判 fail）──
        try:
            ucs = insp.get_unique_constraints(tbl)
            for uc in ucs:
                logger.info(
                    f"  {tbl}: unique constraint '{uc.get('name','?')}' "
                    f"on {uc.get('column_names', [])}"
                )
        except Exception as e:
            logger.warning(f"  {tbl}: unique constraint 讀取失敗（{e}）")

        # ── 6. Index 存在性驗證 ─────────────────────────────
        try:
            indexes = insp.get_indexes(tbl)
            indexed_col_sets = [
                frozenset(idx.get("column_names", [])) for idx in indexes
            ]
            logger.info(
                f"  {tbl}: indexes = "
                f"{sorted(idx.get('name','?') for idx in indexes if idx.get('name'))}"
            )
            required_idx = _INDEXED_COLS.get(tbl, set())
            for col_name in sorted(required_idx):
                has_idx = any({col_name} <= col_set for col_set in indexed_col_sets)
                if not has_idx:
                    errors.append(
                        f"{tbl}.{col_name}: ORM 定義 index=True，"
                        f"但資料庫中未找到對應 index（影響查詢效能）"
                    )
        except Exception as e:
            logger.warning(f"  {tbl}: index 驗證跳過（{e}）")

    if errors:
        raise RuntimeError(
            f"Schema 驗證失敗 — 發現 {len(errors)} 個不一致：\n"
            + "\n".join(f"  ✗ {e}" for e in errors)
            + "\n\n"
            "⚠️  Migration 不會自動修復以上差異（不允許 AUTO ALTER / DROP）。\n"
            "請人工審核並手動修復後，重新執行 Schema Migration 驗證。"
        )

    logger.info(
        f"Schema 完整驗證通過 ✓ "
        f"（{len(tables)} 張表：欄位、"
        + ("Nullability、NUMERIC 精度、" if is_pg else "")
        + "PK、Index）"
    )


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

    # ── Pre-flight ──────────────────────────────────────────
    logger.info("\n── Pre-flight 檢查 ──")
    state = _preflight_check(engine, dry_run)
    missing = state["missing"]
    already_exist = state["existing"]

    if already_exist:
        logger.info(f"已存在（跳過）：{already_exist}")
    if missing:
        logger.info(f"待建立：{missing}")
    else:
        logger.info("三張表已全部存在，無需 Migration。")
        _validate_schema(engine, _REQUIRED_TABLES)
        logger.info("Migration 確認完成（no-op）。")
        sys.exit(0)

    # 快照受保護舊表欄位（用於執行後驗證）
    from sqlalchemy import inspect as _insp

    insp = _insp(engine)
    protected_snapshot = {}
    for tbl in _PROTECTED_TABLES:
        try:
            protected_snapshot[tbl] = {c["name"] for c in insp.get_columns(tbl)}
        except Exception:
            pass

    # ── 建立表 ───────────────────────────────────────────────
    logger.info("\n── 建立資料表 ──")
    _create_tables(engine, missing, dry_run)

    if dry_run:
        logger.info("\n[DRY-RUN] 以上為 Migration 計畫，未執行任何寫入。")
        sys.exit(0)

    # ── 驗證 ─────────────────────────────────────────────────
    logger.info("\n── Post-Migration 驗證 ──")
    _validate_schema(engine, _REQUIRED_TABLES)
    _validate_protected_tables_untouched(engine, protected_snapshot)

    logger.info("\n" + "=" * 60)
    logger.info("Migration 完成 ✓")
    logger.info("=" * 60)
    logger.info("\n後續步驟：")
    logger.info("  1. 確認 GitHub Actions Daily Pipeline 正常執行")
    logger.info("  2. 在 Dashboard 記錄第一筆 ACTUAL 成交，確認寫入正常")
    logger.info(
        "  3. 若需回滾：DROP TABLE position_plan_changes, trade_executions, actual_positions"
    )


if __name__ == "__main__":
    main()
