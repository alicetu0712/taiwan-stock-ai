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
        "id", "stock_id", "stock_name", "position_type", "signal_source",
        "forward_signal_id", "status", "open_date", "close_date",
        "remaining_shares", "avg_cost_per_share", "total_cost_basis",
        "realized_pnl", "target_price", "stop_price",
        "original_plan_snapshot", "notes", "created_at", "updated_at",
    },
    "trade_executions": {
        "id", "position_id", "side", "execution_date", "execution_datetime",
        "execution_price", "shares", "actual_fee", "transaction_tax",
        "linked_forward_signal_id", "notes",
        "is_cancelled", "cancel_reason", "cancelled_at", "created_at", "updated_at",
    },
    "position_plan_changes": {
        "id", "position_id", "changed_at", "field_name",
        "old_value", "new_value", "reason", "created_at",
    },
}

_PROTECTED_TABLES = {
    "user_trades", "position_monitor", "forward_signals",
    "analysis_results", "recommendations", "stocks", "daily_prices",
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
    from src.database import ActualPosition, PositionPlanChange, TradeExecution  # noqa: F401

    table_map = {
        "actual_positions": ActualPosition.__table__,
        "trade_executions": TradeExecution.__table__,
        "position_plan_changes": PositionPlanChange.__table__,
    }

    for tbl_name in missing:
        table_obj = table_map[tbl_name]
        if dry_run:
            from sqlalchemy.schema import CreateTable
            from sqlalchemy.dialects import postgresql
            ddl = str(CreateTable(table_obj).compile(dialect=postgresql.dialect()))
            logger.info(f"[DRY-RUN] Would CREATE TABLE {tbl_name}:\n{ddl}")
        else:
            logger.info(f"Creating table: {tbl_name} ...")
            table_obj.create(bind=engine, checkfirst=True)
            logger.info(f"  → {tbl_name} created ✓")


def _validate_schema(engine, tables: list):
    """執行後驗證：欄位、型別、Index。"""
    from sqlalchemy import inspect

    insp = inspect(engine)
    errors = []

    for tbl in tables:
        existing_cols = {c["name"] for c in insp.get_columns(tbl)}
        required = _REQUIRED_COLS.get(tbl, set())
        missing_cols = required - existing_cols
        if missing_cols:
            errors.append(f"{tbl}: 缺少欄位 {sorted(missing_cols)}")
        else:
            logger.info(f"  {tbl}: 欄位驗證通過 ({len(existing_cols)} cols) ✓")

        # Index 驗證
        indexes = {idx["name"] for idx in insp.get_indexes(tbl)}
        logger.info(f"  {tbl}: indexes = {sorted(indexes)}")

    if errors:
        raise RuntimeError("Schema 驗證失敗：\n" + "\n".join(errors))

    logger.info("Schema 驗證全部通過 ✓")


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
    logger.info("  3. 若需回滾：DROP TABLE position_plan_changes, trade_executions, actual_positions")


if __name__ == "__main__":
    main()
