"""
scripts/migrate_trade_lifecycle.py — Phase 1 Trade Lifecycle Schema Migration

此腳本是唯一允許在 Production PostgreSQL 建立以下三張表的授權管道：
  - actual_positions
  - trade_executions
  - position_plan_changes

安全機制：
  - 預設 --env=local（連本地 SQLite），需明確傳 --env=production 才連 Neon。
  - --dry-run 模式：只顯示執行計畫，不寫入任何資料。
  - 4-step Preflight：先驗證既有表 Schema，偵測 Drift 立即中止，再建立缺失表。
  - Schema 驗證以 ORM metadata 為唯一依據（Base.metadata），不維護重複清單。
  - 執行後完整 Post-Migration 驗證。
  - 不執行 DROP TABLE / ALTER existing columns / DELETE / UPDATE。

Validation Result Classification:
  PASS    = 已驗證且一致
  FAIL    = 已確認 Schema 不一致
  BLOCKED = 無法完成驗證（Inspector 例外、unreadable metadata）
  N/A     = ORM 未宣告此約束，DB 端亦不期望有

執行方式：
  python scripts/migrate_trade_lifecycle.py --dry-run     # 只顯示計畫
  python scripts/migrate_trade_lifecycle.py               # 本地 SQLite
  python scripts/migrate_trade_lifecycle.py --env production  # Neon Production

正式部署前 Runbook：
  Step 0 — 建立 Neon Database Branch（隔離快照）
    neon branches create --name migration-$(date +%Y%m%d)
    # 記錄 branch ID 以供回滾使用

  Step 1 — 記錄 Migration 前狀態
    python scripts/migrate_trade_lifecycle.py --env production --dry-run
    # 確認三張表尚未存在，且受保護的舊表狀態正常

  Step 2 — 執行 Migration（需 GitHub Environment 人工批准）
    python scripts/migrate_trade_lifecycle.py --env production
    # 或透過 GitHub Actions migrate.yml (workflow_dispatch + production approval)

  Step 3 — 驗證
    python scripts/migrate_trade_lifecycle.py --env production --dry-run
    # 已全部存在 → 顯示 "無需 Migration" 且 Schema 驗證通過

Migration 失敗處理：
  - PostgreSQL DDL 使用 engine.begin() 包裹，失敗時自動 rollback（atomic）。
  - 如 rollback 確認成功，修復問題後重新執行 Step 2。
  - 如 rollback 不確定，使用 Step 0 建立的 branch 還原：
    neon branches reset --branch migration-$(date +%Y%m%d)
  - 不得自動執行 DROP TABLE。
  - 必須確認應用程式版本與 Schema 相容後才能重新部署。

⚠️  禁止把以下語句當成一般回滾方案：
  DROP TABLE actual_positions / trade_executions / position_plan_changes
  以上操作會永久刪除生產資料，必須明確授權後才能執行。
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

# ── Operational constants ─────────────────────────────────────────────
# (schema-comparison constants removed: derived from ORM metadata at runtime)

_REQUIRED_TABLES = ["actual_positions", "trade_executions", "position_plan_changes"]

_PROTECTED_TABLES = {
    "user_trades",
    "position_monitor",
    "forward_signals",
    "analysis_results",
    "recommendations",
    "stocks",
    "daily_prices",
}

# ── Migration state machine ───────────────────────────────────────────

# Three states per migration — only PENDING may proceed to DDL.
_MIG_APPLIED = "APPLIED"  # fully and correctly applied → skip
_MIG_PENDING = "PENDING"  # cleanly absent, safe to apply → execute DDL
_MIG_BLOCKED = "BLOCKED"  # ambiguous / partial / unsafe → stop everything


class MigrationBlockedError(RuntimeError):
    """Raised by verify() or drift_check() when a migration is in an
    ambiguous, partial, or unsafe state and requires human review before
    any DDL may proceed.
    """


_V1_2_INDEX_NAME = "uix_te_idempotency_key"
_V1_2_EXPECTED_COLUMNS = ["idempotency_key"]
_V1_2_EXPECTED_PREDICATE = "idempotency_key IS NOT NULL"
_V1_2_SCHEMA = "public"

# Map pg_constraint confdeltype / confupdtype → SQL keyword
_PG_CONFTYPE_MAP: dict[str, str] = {
    "a": "NO ACTION",
    "r": "RESTRICT",
    "c": "CASCADE",
    "n": "SET NULL",
    "d": "SET DEFAULT",
}


def _normalize_pg_predicate(expr: str | None) -> str | None:
    """Normalize a pg_get_expr() result for comparison.

    PG returns e.g. '(idempotency_key IS NOT NULL)' — strip outer parens,
    collapse whitespace, uppercase for case-insensitive compare.
    """
    if expr is None:
        return None
    return expr.strip().strip("()").upper().replace("  ", " ").strip()


# Single SQL for full partial-index catalog inspection.
# Returns at most 2 rows (LIMIT 2 detects duplicate name collisions).
# Columns: indisunique, indisvalid, indisready, predicate, tbl_schema, key_columns,
#          indnkeyatts_count, indnatts
# key_columns: array_agg of non-expression key-only columns (INCLUDE excluded via
#   indnkeyatts, expression columns excluded via attnum > 0), ordered by index pos.
# indnkeyatts_count: number of key-only columns (excludes INCLUDE columns).
# indnatts: total index columns (key + INCLUDE); indnatts > indnkeyatts → INCLUDE present.
_PG_PARTIAL_INDEX_SQL = """
    SELECT
        pi.indisunique,
        pi.indisvalid,
        pi.indisready,
        pg_get_expr(pi.indpred, pi.indrelid)              AS predicate,
        n.nspname                                          AS tbl_schema,
        (
            SELECT COALESCE(
                array_agg(a.attname ORDER BY k.pos),
                ARRAY[]::text[]
            )
            FROM   unnest(pi.indkey) WITH ORDINALITY AS k(attnum, pos)
            JOIN   pg_attribute a
                   ON  a.attrelid = pi.indrelid
                   AND a.attnum   = k.attnum
            WHERE  k.attnum > 0
              AND  k.pos    <= pi.indnkeyatts
        )                                                  AS key_columns,
        pi.indnkeyatts                                     AS indnkeyatts_count,
        pi.indnatts                                        AS indnatts
    FROM   pg_index     pi
    JOIN   pg_class     tc ON tc.oid = pi.indrelid
    JOIN   pg_class     ic ON ic.oid = pi.indexrelid
    JOIN   pg_namespace n  ON n.oid  = tc.relnamespace
    WHERE  tc.relname = :tbl
      AND  ic.relname = :idx_name
      AND  n.nspname  = :schema
    LIMIT  2
"""


def _verify_pg_partial_index_catalog(
    insp,
    tbl: str,
    index_name: str,
    expected_columns: list[str],
    expected_predicate: str | None,
    schema_name: str = "public",
) -> bool:
    """Full pg catalog validation for a partial unique index.

    Checks (in order):
      1. Exactly one result row (LIMIT 2 — duplicate names in same schema = BLOCKED)
      2. Schema matches schema_name
      3. indisunique = True
      4. indisvalid  = True
      5. indisready  = True
      6. Key columns (excluding INCLUDE / expression) == expected_columns (ordered)
      7. Predicate matches expected_predicate (normalized, case-insensitive)
         — None expected_predicate means a general (non-partial) index is acceptable

    Returns True  — all checks pass (APPLIED).
    Returns False — index not found in this schema (PENDING, safe to create).
    Raises MigrationBlockedError — any check fails or catalog read errors.
    """
    from sqlalchemy import text

    engine = getattr(insp, "engine", None) or getattr(insp, "bind", None)
    if engine is None:
        raise MigrationBlockedError(
            f"PostgreSQL catalog 驗證失敗：無法從 Inspector 取得 engine "
            f"({schema_name}.{tbl}.{index_name})"
        )

    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(_PG_PARTIAL_INDEX_SQL),
                {"tbl": tbl, "idx_name": index_name, "schema": schema_name},
            ).fetchall()
    except MigrationBlockedError:
        raise
    except Exception as exc:
        raise MigrationBlockedError(
            f"PostgreSQL catalog 讀取失敗 ({schema_name}.{tbl}.{index_name}): {exc}"
        ) from exc

    if len(rows) == 0:
        return False  # Index absent in this schema → PENDING

    if len(rows) > 1:
        raise MigrationBlockedError(
            f"PostgreSQL catalog 回傳多筆結果 ({len(rows)} rows) for "
            f"index={index_name!r} table={tbl!r} schema={schema_name!r} — "
            "資料庫 Schema 異常，請人工確認。"
        )

    (
        indisunique,
        indisvalid,
        indisready,
        predicate_raw,
        tbl_schema,
        key_columns,
        indnkeyatts_count,
        indnatts,
    ) = rows[0]

    errors: list[str] = []

    # Check 2: schema (should match what we queried, but be explicit)
    if tbl_schema != schema_name:
        errors.append(f"tbl_schema: 實際={tbl_schema!r}, 預期={schema_name!r}")

    # Check 3: unique
    if not indisunique:
        errors.append("Unique=False — Index 非 Unique")

    # Check 4: valid
    if not indisvalid:
        errors.append(
            "indisvalid=False — Index 建立未完成或已損壞，請人工確認後重新執行"
        )

    # Check 5: ready
    if not indisready:
        errors.append(
            "indisready=False — Index 尚未 ready（可能正在建立），請稍後重新執行"
        )

    if errors:
        raise MigrationBlockedError(
            f"Index {index_name!r} ({schema_name}.{tbl}) catalog 驗證失敗：\n"
            + "\n".join(f"  - {e}" for e in errors)
        )

    # Check 6a: Expression index detection
    # key_columns only contains attnum>0 entries; if fewer than indnkeyatts_count,
    # some key positions have attnum=0 (expression columns).
    actual_cols = list(key_columns) if key_columns else []
    if len(actual_cols) < indnkeyatts_count:
        raise MigrationBlockedError(
            f"Index {index_name!r} ({schema_name}.{tbl}) 包含 Expression Columns "
            f"(key_columns={actual_cols!r}, indnkeyatts={indnkeyatts_count}) — "
            "此平台不使用 Expression Index，請人工確認後刪除並重新執行 Migration。"
        )

    # Check 6b: INCLUDE columns detection (PG 11+ INCLUDE clause)
    if indnatts > indnkeyatts_count:
        raise MigrationBlockedError(
            f"Index {index_name!r} ({schema_name}.{tbl}) 包含 INCLUDE Columns "
            f"(indnatts={indnatts} > indnkeyatts={indnkeyatts_count}) — "
            "此平台不使用 INCLUDE Columns，請人工確認後刪除並重新執行 Migration。"
        )

    # Check 6c: key columns (including order)
    if actual_cols != expected_columns:
        raise MigrationBlockedError(
            f"Index {index_name!r} ({schema_name}.{tbl}) key columns 不符合預期：\n"
            f"  實際  : {actual_cols!r}\n"
            f"  預期  : {expected_columns!r}\n"
            "  請人工確認後刪除並重新執行 Migration。"
        )

    # Check 7: predicate
    if expected_predicate is not None:
        actual_pred = _normalize_pg_predicate(predicate_raw)
        expected_pred = _normalize_pg_predicate(expected_predicate)

        if actual_pred is None:
            raise MigrationBlockedError(
                f"Index {index_name!r} ({schema_name}.{tbl}) 是一般 Unique Index"
                "（無 predicate），\n"
                f"  但 Schema Contract 要求 Partial Index "
                f"(WHERE {expected_predicate})。\n"
                "  請刪除現有 index 後重新執行 Migration。"
            )
        if actual_pred != expected_pred:
            raise MigrationBlockedError(
                f"Index {index_name!r} ({schema_name}.{tbl}) predicate 不符合預期：\n"
                f"  實際  : {predicate_raw!r}\n"
                f"  預期  : {expected_predicate!r}\n"
                "  請人工確認後刪除並重新執行 Migration。"
            )

    return True


def _verify_idempotency_unique_index(insp, tbl: str) -> bool:
    """Return True iff a correct unique index on exactly [idempotency_key] exists.

    Schema contract by dialect:
      PostgreSQL — partial unique index named uix_te_idempotency_key with
                   predicate (idempotency_key IS NOT NULL), indisvalid, indisready.
                   If the named index is absent (e.g. only ORM inline UC exists),
                   returns False (PENDING) so the migration can create it.
      SQLite     — any correct unique index or inline UNIQUE constraint on
                   [idempotency_key] is accepted (SQLite has no partial indexes).

    Raises MigrationBlockedError on:
      - Non-unique or multi-column index (caught by drift_check first)
      - PG catalog read failure
      - PG index invalid / not ready
      - PG predicate missing or wrong
    """
    target = ["idempotency_key"]
    is_pg = insp.dialect.name == "postgresql"

    if is_pg:
        # Check via pg catalog: look for our named partial index specifically.
        # Validates schema, table, columns, unique, predicate, indisvalid, indisready.
        # If only an ORM-created general unique constraint exists (not our named
        # partial index), returns False so migration creates the partial index.
        return _verify_pg_partial_index_catalog(
            insp,
            tbl,
            _V1_2_INDEX_NAME,
            _V1_2_EXPECTED_COLUMNS,
            _V1_2_EXPECTED_PREDICATE,
            schema_name=_V1_2_SCHEMA,
        )

    # SQLite: accept named unique index or ORM inline UNIQUE constraint
    for idx in insp.get_indexes(tbl):
        if idx.get("unique") and (idx.get("column_names") or []) == target:
            return True
    for uc in insp.get_unique_constraints(tbl):
        if (uc.get("column_names") or []) == target:
            return True
    return False


def _drift_check_idempotency_unique_index(insp, tbl: str) -> None:
    """Raise MigrationBlockedError if any index on idempotency_key is malformed.

    Detects partial-migration state before verify() runs:
      - Non-unique index on idempotency_key → BLOCKED (wrong spec)
      - Multi-column index including idempotency_key → BLOCKED (unexpected)

    A correctly structured unique single-column index will be caught by
    verify() as APPLIED and this function will return None (no-op).
    """
    target_col = "idempotency_key"
    for idx in insp.get_indexes(tbl):
        cols = idx.get("column_names") or []
        if target_col not in cols:
            continue
        if not idx.get("unique"):
            raise MigrationBlockedError(
                f"idempotency_key 欄位存在非 Unique Index "
                f"（name={idx.get('name')!r}, unique=False）"
                "— 部分套用或手動建立的不正確 Index。"
                "請人工確認並刪除後重新執行。"
            )
        if cols != [target_col]:
            raise MigrationBlockedError(
                f"idempotency_key 存在 Unique Index 但欄位組合不正確："
                f" 實際 {cols!r}，預期 {[target_col]!r}"
                "— 請人工確認後重新執行。"
            )


def _verify_fk(
    insp,
    tbl: str,
    local_col: str,
    ref_table: str,
    ref_col: str,
    on_delete: str | None = None,
    *,
    src_schema: str = "public",
    ref_schema: str | None = None,
    on_update: str | None = None,
) -> bool:
    """Strict FK verification (PostgreSQL-only migrations).

    Checks (inspector first, then PG catalog for convalidated + confdeltype/confupdtype):
      1. FK on local_col exists — False (PENDING) if absent
      2. referred_schema  (None = same schema; explicit value if cross-schema)
      3. referred_table
      4. referred_columns
      5. ON DELETE rule  (authoritative from pg_constraint.confdeltype on PG)
      6. ON UPDATE rule  (authoritative from pg_constraint.confupdtype on PG)
      7. pg_constraint.convalidated = True

    src_schema: schema of the source (FK-owning) table, used to scope the catalog query
    so that a same-named table in another schema cannot produce a false PASS.

    on_delete / on_update are case-insensitive; empty / None from inspector → "NO ACTION".
    Raises MigrationBlockedError if FK exists but ANY attribute mismatches,
    catalog returns 0 rows (metadata inconsistency), 2+ rows (unexpected), or read fails.
    """
    try:
        fks = insp.get_foreign_keys(tbl)
    except Exception as exc:
        raise MigrationBlockedError(f"FK Inspector 讀取失敗 ({tbl}): {exc}") from exc

    # Find FK by local column
    matching = [
        fk for fk in fks if (fk.get("constrained_columns") or [None])[0] == local_col
    ]

    if not matching:
        return False  # FK entirely absent → PENDING

    fk = matching[0]
    errors: list[str] = []

    # Check 2: referred_schema
    actual_ref_schema = fk.get("referred_schema")
    if actual_ref_schema != ref_schema:
        errors.append(
            f"referred_schema: 實際={actual_ref_schema!r}, 預期={ref_schema!r}"
        )

    # Check 3: referred_table
    actual_ref_tbl = fk.get("referred_table")
    if actual_ref_tbl != ref_table:
        errors.append(f"referred_table: 實際={actual_ref_tbl!r}, 預期={ref_table!r}")

    # Check 4: referred_columns
    actual_ref_cols = fk.get("referred_columns") or []
    if actual_ref_cols != [ref_col]:
        errors.append(f"referred_columns: 實際={actual_ref_cols!r}, 預期={[ref_col]!r}")

    # Checks 5-7 require the PG catalog for authoritative values
    if insp.dialect.name == "postgresql":
        engine = getattr(insp, "engine", None) or getattr(insp, "bind", None)
        if engine is None:
            raise MigrationBlockedError(
                f"PostgreSQL FK catalog 驗證失敗：無法從 Inspector 取得 engine "
                f"({src_schema}.{tbl}.{local_col})"
            )
        try:
            from sqlalchemy import text

            with engine.connect() as conn:
                # Scope query to src_schema to prevent false PASS from a same-named
                # table in another schema.  LIMIT 2 detects unexpected duplicates.
                cat_rows = conn.execute(
                    text("""
                        SELECT
                            c.convalidated,
                            c.confdeltype,
                            c.confupdtype
                        FROM   pg_constraint c
                        JOIN   pg_class      t   ON  t.oid  = c.conrelid
                        JOIN   pg_namespace  ns  ON  ns.oid = t.relnamespace
                        JOIN   pg_attribute  a   ON  a.attrelid = c.conrelid
                                                 AND a.attnum   = c.conkey[1]
                        WHERE  t.relname   = :tbl
                          AND  ns.nspname  = :src_schema
                          AND  a.attname   = :col
                          AND  c.contype   = 'f'
                        LIMIT 2
                        """),
                    {"tbl": tbl, "src_schema": src_schema, "col": local_col},
                ).fetchall()
        except MigrationBlockedError:
            raise
        except Exception as exc:
            raise MigrationBlockedError(
                f"PostgreSQL pg_constraint 讀取失敗 ({src_schema}.{tbl}.{local_col}): {exc}"
            ) from exc

        if len(cat_rows) == 0:
            # Inspector found the FK but pg_constraint has no matching row —
            # metadata inconsistency (or wrong src_schema), cannot validate safely.
            raise MigrationBlockedError(
                f"FK {src_schema}.{tbl}.{local_col} が Inspector に存在しますが "
                "pg_constraint に見つかりません — metadata 不整合、人工確認が必要です"
            )

        if len(cat_rows) > 1:
            raise MigrationBlockedError(
                f"FK catalog 查詢回傳多筆結果 ({len(cat_rows)} rows) for "
                f"{src_schema}.{tbl}.{local_col} — 資料庫 Schema 異常，請人工確認。"
            )

        convalidated, confdeltype_ch, confupdtype_ch = cat_rows[0]

        # Check 5: ON DELETE (authoritative from confdeltype)
        if on_delete is not None:
            actual_od = _PG_CONFTYPE_MAP.get(confdeltype_ch, confdeltype_ch)
            expected_od = on_delete.upper().strip()
            if actual_od != expected_od:
                errors.append(
                    f"ON DELETE: 實際={actual_od!r} (confdeltype={confdeltype_ch!r}), "
                    f"預期={expected_od!r}"
                )

        # Check 6: ON UPDATE (authoritative from confupdtype)
        if on_update is not None:
            actual_ou = _PG_CONFTYPE_MAP.get(confupdtype_ch, confupdtype_ch)
            expected_ou = on_update.upper().strip()
            if actual_ou != expected_ou:
                errors.append(
                    f"ON UPDATE: 實際={actual_ou!r} (confupdtype={confupdtype_ch!r}), "
                    f"預期={expected_ou!r}"
                )

        # Check 7: convalidated
        if not convalidated:
            errors.append(
                "pg_constraint.convalidated=False — FK 已建立但 VALIDATE 未完成，"
                "可能無法正確約束現有資料"
            )

    else:
        # Non-PG: use inspector options for ON DELETE / ON UPDATE (best-effort)
        if on_delete is not None:
            raw_od = (fk.get("options") or {}).get("ondelete") or ""
            actual_od = raw_od.upper().strip() or "NO ACTION"
            if actual_od != on_delete.upper().strip():
                errors.append(
                    f"ON DELETE: 實際={actual_od!r}, 預期={on_delete.upper()!r}"
                )
        if on_update is not None:
            raw_ou = (fk.get("options") or {}).get("onupdate") or ""
            actual_ou = raw_ou.upper().strip() or "NO ACTION"
            if actual_ou != on_update.upper().strip():
                errors.append(
                    f"ON UPDATE: 實際={actual_ou!r}, 預期={on_update.upper()!r}"
                )

    if errors:
        raise MigrationBlockedError(
            f"FK {tbl}.{local_col} → {ref_table}.{ref_col} 結構不正確：\n"
            + "\n".join(f"  - {e}" for e in errors)
        )

    return True


def _assess_migration_state(insp, tbl: str, mig: dict) -> tuple[str, str]:
    """Strict three-state assessment for a single migration entry.

    Returns (state, reason):
      APPLIED  — verify() returned True → already fully applied
      PENDING  — drift_check passed AND verify() returned False → safe to apply
      BLOCKED  — any exception from verify()/drift_check(), non-boolean return,
                 or explicitly raised MigrationBlockedError

    Only PENDING transitions to DDL execution. BLOCKED stops the loop.
    """
    # Step 1: optional drift_check — detects known-bad partial states
    drift_check = mig.get("drift_check")
    if drift_check is not None:
        try:
            drift_check(insp, tbl)
        except MigrationBlockedError as exc:
            return _MIG_BLOCKED, f"drift_check: {exc}"
        except Exception as exc:
            return (
                _MIG_BLOCKED,
                f"drift_check 引發未預期例外 ({type(exc).__name__}): {exc}",
            )

    # Step 2: verify — determine whether migration has been applied
    try:
        result = mig["verify"](insp, tbl)
    except MigrationBlockedError as exc:
        return _MIG_BLOCKED, f"verify: {exc}"
    except Exception as exc:
        return _MIG_BLOCKED, f"verify() 引發例外 ({type(exc).__name__}): {exc}"

    if result is True:
        return _MIG_APPLIED, "已完整套用"
    if result is False:
        return _MIG_PENDING, "尚未套用，符合套用前置條件"
    return _MIG_BLOCKED, f"verify() 回傳非布林值 {result!r}，無法判定狀態"


# ── Approved versioned migrations ─────────────────────────────────────
# Each entry is a known, reviewed schema upgrade for an EXISTING table.
# Keys:
#   name        — unique identifier (used in log messages and error reports)
#   table       — target table name
#   description — human-readable description
#   verify      — callable(insp, tbl) → bool | raises MigrationBlockedError
#   drift_check — optional callable(insp, tbl) → None | raises MigrationBlockedError
#   sql_pg      — DDL for PostgreSQL
#   sql_sqlite  — DDL for SQLite (omit if pg_only)
#   pg_only     — if True, skip on SQLite dialects
#
# Only ADD operations permitted — no DROP / ALTER existing columns / DELETE.
_APPROVED_MIGRATIONS: list[dict] = [
    {
        "name": "v1.1_add_idempotency_key",
        "table": "trade_executions",
        "description": "Add idempotency_key column (VARCHAR 64, nullable)",
        "verify": lambda insp, tbl: "idempotency_key"
        in {c["name"] for c in insp.get_columns(tbl)},
        "sql_pg": (
            "ALTER TABLE trade_executions"
            " ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(64)"
        ),
        "sql_sqlite": "ALTER TABLE trade_executions ADD COLUMN idempotency_key TEXT",
    },
    {
        "name": "v1.2_add_idempotency_key_unique_index",
        "table": "trade_executions",
        "description": "Unique index on idempotency_key (partial WHERE NOT NULL on PG)",
        # drift_check: detects non-unique or multi-column index on idempotency_key
        #              before verify() runs — prevents fail-open on partial state.
        # verify: checks exact column set ["idempotency_key"] + unique=True
        #         via either get_indexes() (ALTER TABLE path) or
        #         get_unique_constraints() (ORM CREATE TABLE path).
        # NULL handling: PostgreSQL partial index (WHERE NOT NULL) allows multiple
        #   NULLs; SQLite UNIQUE also allows multiple NULLs.  Both semantics are
        #   correct for backward-compatible old rows with NULL idempotency_key.
        "drift_check": _drift_check_idempotency_unique_index,
        "verify": _verify_idempotency_unique_index,
        "sql_pg": (
            "CREATE UNIQUE INDEX IF NOT EXISTS uix_te_idempotency_key"
            " ON trade_executions(idempotency_key)"
            " WHERE idempotency_key IS NOT NULL"
        ),
        "sql_sqlite": (
            "CREATE UNIQUE INDEX IF NOT EXISTS uix_te_idempotency_key"
            " ON trade_executions(idempotency_key)"
        ),
    },
    {
        "name": "v1.3_add_fk_actual_positions_fwd_signals",
        "table": "actual_positions",
        "description": (
            "FK actual_positions.forward_signal_id → forward_signals.id RESTRICT"
        ),
        "pg_only": True,
        # Strict: verifies local_col, ref_table, ref_col, ON DELETE RESTRICT,
        # convalidated=True via pg_constraint catalog.
        # Strict: verifies local_col, ref_schema, ref_table, ref_col,
        # ON DELETE RESTRICT, ON UPDATE NO ACTION, convalidated=True via pg catalog.
        "verify": lambda insp, tbl: _verify_fk(
            insp,
            tbl,
            local_col="forward_signal_id",
            ref_table="forward_signals",
            ref_col="id",
            on_delete="RESTRICT",
            on_update="NO ACTION",
        ),
        "sql_pg": (
            "ALTER TABLE actual_positions ADD CONSTRAINT fk_ap_fwd_signal"
            " FOREIGN KEY (forward_signal_id)"
            " REFERENCES forward_signals(id) ON DELETE RESTRICT"
        ),
    },
    {
        "name": "v1.4_add_fk_trade_executions_positions",
        "table": "trade_executions",
        "description": (
            "FK trade_executions.position_id → actual_positions.id RESTRICT"
        ),
        "pg_only": True,
        "verify": lambda insp, tbl: _verify_fk(
            insp,
            tbl,
            local_col="position_id",
            ref_table="actual_positions",
            ref_col="id",
            on_delete="RESTRICT",
            on_update="NO ACTION",
        ),
        "sql_pg": (
            "ALTER TABLE trade_executions ADD CONSTRAINT fk_te_position"
            " FOREIGN KEY (position_id)"
            " REFERENCES actual_positions(id) ON DELETE RESTRICT"
        ),
    },
    {
        "name": "v1.5_add_fk_position_plan_changes_positions",
        "table": "position_plan_changes",
        "description": (
            "FK position_plan_changes.position_id → actual_positions.id RESTRICT"
        ),
        "pg_only": True,
        # Strict: verifies local_col, ref_schema, ref_table, ref_col,
        # ON DELETE RESTRICT, ON UPDATE NO ACTION, convalidated=True via pg catalog.
        "verify": lambda insp, tbl: _verify_fk(
            insp,
            tbl,
            local_col="position_id",
            ref_table="actual_positions",
            ref_col="id",
            on_delete="RESTRICT",
            on_update="NO ACTION",
        ),
        "sql_pg": (
            "ALTER TABLE position_plan_changes ADD CONSTRAINT fk_ppc_position"
            " FOREIGN KEY (position_id)"
            " REFERENCES actual_positions(id) ON DELETE RESTRICT"
        ),
    },
    {
        "name": "v1.6_add_fk_trade_executions_linked_signal",
        "table": "trade_executions",
        "description": (
            "FK trade_executions.linked_forward_signal_id"
            " → forward_signals.id RESTRICT"
        ),
        "pg_only": True,
        "verify": lambda insp, tbl: _verify_fk(
            insp,
            tbl,
            local_col="linked_forward_signal_id",
            ref_table="forward_signals",
            ref_col="id",
            on_delete="RESTRICT",
            on_update="NO ACTION",
        ),
        "sql_pg": (
            "ALTER TABLE trade_executions ADD CONSTRAINT fk_te_linked_signal"
            " FOREIGN KEY (linked_forward_signal_id)"
            " REFERENCES forward_signals(id) ON DELETE RESTRICT"
        ),
    },
]


def _preflight_migration_plan(
    insp, is_pg: bool, existing_tables: list
) -> list[tuple[dict, str, str]]:
    """Assess ALL applicable migrations before any DDL is executed.

    Returns list of (mig, state, reason) for every in-scope migration.
    Never executes DDL.  The caller must check for BLOCKED entries before
    proceeding.
    """
    plan: list[tuple[dict, str, str]] = []
    for mig in _APPROVED_MIGRATIONS:
        tbl = mig["table"]
        if tbl not in existing_tables:
            continue
        if mig.get("pg_only") and not is_pg:
            logger.info(
                f"  [{mig['name']}] preflight 跳過 "
                f"(pg_only, dialect={insp.dialect.name})"
            )
            continue
        state, reason = _assess_migration_state(insp, tbl, mig)
        plan.append((mig, state, reason))
    return plan


def _log_ddl_audit(
    audit_log: list[dict],
    ddl_planned: int,
    ddl_attempted: int,
    ddl_committed: int,
    ddl_rolled_back: int,
    ddl_unknown: int = 0,
) -> None:
    """Log the DDL execution audit trail.

    Counters are strictly separated:
      planned      — dry-run only: migrations that would execute DDL
      attempted    — real runs: DDL transactions started (engine.begin entered)
      committed    — real runs: DDL transactions confirmed committed
      rolled_back  — real runs: application-level exception, rollback confirmed
      unknown      — real runs: connection-level error (OperationalError/InterfaceError);
                     commit may or may not have reached the server — requires human review
    """
    logger.info(
        f"DDL Audit — planned={ddl_planned}, attempted={ddl_attempted}, "
        f"committed={ddl_committed}, rolled_back={ddl_rolled_back}, "
        f"unknown={ddl_unknown}"
    )
    for rec in audit_log:
        logger.info(
            f"  [{rec['name']}] {rec['result']}"
            f"  start={rec['start']}  end={rec['end']}"
        )


def _apply_pending_migrations(engine, existing_tables: list, dry_run: bool) -> int:
    """Global preflight → controlled execution → DDL audit.

    Phase 1 — Global Preflight (NO DDL):
      Assess ALL applicable migrations.  If ANY are BLOCKED, stop immediately.
      At this point DDL attempted = 0 (guaranteed — no DDL runs in preflight).

    Phase 2 — Controlled Execution:
      Execute only PENDING migrations, one at a time, in order.
      Per-migration: record start/end time, SQL attempted, commit/rollback result.

    Phase 3 — Audit Log:
      Log the complete DDL audit: attempted / committed / rolled_back counts
      and per-migration timing.

    Returns committed count (int) for backward compatibility with callers.
    Raises RuntimeError on BLOCKED (Phase 1) or execution failure (Phase 2).
    """
    import datetime

    from sqlalchemy import inspect as _insp
    from sqlalchemy import text

    insp = _insp(engine)
    is_pg = engine.dialect.name == "postgresql"

    # ── Phase 1: Global Preflight ──────────────────────────────────────
    plan = _preflight_migration_plan(insp, is_pg, existing_tables)

    for mig, state, reason in plan:
        if state == _MIG_APPLIED:
            logger.info(f"  [{mig['name']}] APPLIED — {reason}")
        elif state == _MIG_PENDING:
            logger.info(f"  [{mig['name']}] PENDING — {reason}")
        # BLOCKED entries are collected below

    blocked = [(mig, reason) for mig, state, reason in plan if state == _MIG_BLOCKED]
    if blocked:
        lines = [
            f"  [{mig['name']}] (table={mig['table']}) — {reason}"
            for mig, reason in blocked
        ]
        msg = (
            "Global Preflight BLOCKED — DDL attempted = 0（所有 Migration 未執行）\n"
            "  以下問題必須人工解決後再重新執行：\n" + "\n".join(lines)
        )
        logger.error(msg)
        raise RuntimeError(msg)

    pending = [(mig, reason) for mig, state, reason in plan if state == _MIG_PENDING]

    n_applied = sum(1 for _, s, _ in plan if s == _MIG_APPLIED)
    logger.info(
        f"Global Preflight 通過 — APPLIED={n_applied}, "
        f"PENDING={len(pending)}, BLOCKED=0"
    )

    if not pending:
        return 0

    # ── Phase 2: Controlled Execution ─────────────────────────────────
    # Counters are strictly separated — no arithmetic inference between them.
    ddl_planned = 0  # dry-run: migrations that would execute DDL
    ddl_attempted = 0  # real: DDL transactions started
    ddl_committed = 0  # real: DDL transactions confirmed committed
    ddl_rolled_back = 0  # real: application-level error, rollback confirmed
    ddl_unknown = 0  # real: connection-level error, commit result uncertain
    audit_log: list[dict] = []

    for mig, _reason in pending:
        tbl = mig["table"]
        sql = mig["sql_pg"] if is_pg else mig.get("sql_sqlite", "")
        if not sql:
            msg = (
                f"Migration [{mig['name']}] BLOCKED — "
                f"此 dialect ({engine.dialect.name}) 無對應 SQL"
            )
            logger.error(msg)
            raise RuntimeError(msg)

        record: dict = {
            "name": mig["name"],
            "table": tbl,
            "sql": sql,
            "start": None,
            "end": None,
            "result": None,
        }

        if dry_run:
            # Dry-run: plan only — nothing is written to the database.
            logger.info(f"  [DRY-RUN] Would apply [{mig['name']}] (PENDING): {sql}")
            record["start"] = record["end"] = datetime.datetime.now(
                datetime.timezone.utc
            ).isoformat()
            record["result"] = "DRY_RUN"
            audit_log.append(record)
            ddl_planned += 1  # dry-run counter; NOT added to ddl_committed
            continue

        logger.info(f"  Applying [{mig['name']}] (PENDING): {mig['description']}")
        record["start"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        ddl_attempted += 1
        try:
            with engine.begin() as conn:
                conn.execute(text(sql))
            # Commit confirmed — engine.begin() context manager exits cleanly
            record["end"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            record["result"] = "COMMITTED"
            ddl_committed += 1  # incremented only on confirmed commit
            logger.info(f"  [{mig['name']}] ✓ COMMITTED")
        except Exception as exc:
            record["end"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

            # Distinguish connection-level errors from application-level errors.
            # OperationalError / InterfaceError may occur DURING COMMIT — in that case
            # the transaction result is uncertain (UNKNOWN).  Application-level errors
            # (IntegrityError, ProgrammingError, etc.) occur before commit and SQLAlchemy
            # guarantees a rollback was attempted (ROLLED_BACK).
            try:
                from sqlalchemy.exc import InterfaceError as _IfErr
                from sqlalchemy.exc import OperationalError as _OpErr

                _is_conn_err = isinstance(exc, (_OpErr, _IfErr))
            except ImportError:
                _is_conn_err = False

            if _is_conn_err:
                record["result"] = "UNKNOWN"
                ddl_unknown += 1
                logger.error(f"  [{mig['name']}] UNKNOWN (connection error): {exc}")
                audit_log.append(record)
                _log_ddl_audit(
                    audit_log,
                    ddl_planned,
                    ddl_attempted,
                    ddl_committed,
                    ddl_rolled_back,
                    ddl_unknown,
                )
                raise RuntimeError(
                    f"Migration [{mig['name']}] 連線中斷 — 交易結果 UNKNOWN，"
                    f"必須人工確認資料庫狀態後再重新執行：{exc}\n"
                    f"  DDL: attempted={ddl_attempted}, committed={ddl_committed}, "
                    f"rolled_back={ddl_rolled_back}, unknown={ddl_unknown}\n"
                    "請確認 Schema 狀態後重新執行。"
                ) from exc
            else:
                # Application-level error — SQLAlchemy auto-rollback on exception
                record["result"] = "ROLLED_BACK"
                ddl_rolled_back += 1
                logger.error(f"  [{mig['name']}] ROLLED_BACK: {exc}")
                audit_log.append(record)
                _log_ddl_audit(
                    audit_log,
                    ddl_planned,
                    ddl_attempted,
                    ddl_committed,
                    ddl_rolled_back,
                    ddl_unknown,
                )
                raise RuntimeError(
                    f"已核准 Migration [{mig['name']}] 執行失敗：{exc}\n"
                    f"  DDL: attempted={ddl_attempted}, committed={ddl_committed}, "
                    f"rolled_back={ddl_rolled_back}\n"
                    "請人工確認資料庫狀態後重新執行。"
                ) from exc
        audit_log.append(record)

    # ── Phase 3: Audit Log ─────────────────────────────────────────────
    _log_ddl_audit(
        audit_log,
        ddl_planned,
        ddl_attempted,
        ddl_committed,
        ddl_rolled_back,
        ddl_unknown,
    )
    # Return planned count for dry-run, committed count for real runs.
    return ddl_planned if dry_run else ddl_committed


# ── Engine ────────────────────────────────────────────────────────────


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


# ── ORM-derived schema extraction ────────────────────────────────────


def _get_orm_schema(tbl_name: str) -> dict:
    """從 SQLAlchemy ORM metadata 提取期望的 Schema 規格。

    以 Base.metadata 為單一真相來源，避免與 ORM 定義脫鉤。
    回傳 dict 包含 columns / pks / fks / unique_constraints / indexes。
    """
    from sqlalchemy import UniqueConstraint as SA_UC

    from src.database import Base

    if tbl_name not in Base.metadata.tables:
        raise RuntimeError(
            f"[BLOCKED] {tbl_name}: ORM Base.metadata 中找不到此表 — "
            "請確認 ORM 模型已正確定義"
        )

    orm_tbl = Base.metadata.tables[tbl_name]

    # Columns
    cols: dict[str, dict] = {}
    for col in orm_tbl.columns:
        cols[col.name] = {
            "nullable": col.nullable,
            "primary_key": col.primary_key,
            "type": col.type,
        }

    # PKs
    pks = {name for name, info in cols.items() if info["primary_key"]}

    # FK constraints — from column.foreign_keys
    fks: list[dict] = []
    for col in orm_tbl.columns:
        for fk in col.foreign_keys:
            try:
                ref_table = fk.column.table.name
                ref_col = fk.column.name
                ondelete = (
                    getattr(fk.constraint, "ondelete", None) or ""
                ).upper() or None
                fks.append(
                    {
                        "local_col": col.name,
                        "ref_table": ref_table,
                        "ref_col": ref_col,
                        "ondelete": ondelete,
                    }
                )
            except Exception as e:
                raise RuntimeError(
                    f"[BLOCKED] {tbl_name}.{col.name}: FK 定義無法解析 — {e}"
                ) from e

    # Unique constraints
    uc_sets: list[frozenset] = []
    for c in orm_tbl.constraints:
        if isinstance(c, SA_UC) and list(c.columns.keys()):
            uc_sets.append(frozenset(c.columns.keys()))

    # Indexes (from ORM index=True columns)
    idx_col_sets: list[frozenset] = [
        frozenset({col.name}) for col in orm_tbl.columns if getattr(col, "index", False)
    ]

    return {
        "columns": cols,
        "pks": pks,
        "fks": fks,
        "unique_constraints": uc_sets,
        "indexes": idx_col_sets,
    }


# ── Schema validation ─────────────────────────────────────────────────


def _validate_schema(engine, tables: list) -> None:
    """全面 Schema 驗證（ORM metadata 為單一真相來源）。

    9 大檢查點：
      1. ORM metadata lookup (BLOCKED if missing)
      2. Column names      (FAIL if missing)
      3. NOT NULL          (PG only, FAIL)
      4. NUMERIC p/s       (PG only, FAIL/BLOCKED)
      5. VARCHAR length    (PG only, FAIL/BLOCKED)
      6. Primary Key       (FAIL/BLOCKED)
      7. Foreign Key       (FAIL/BLOCKED; N/A if ORM has none)
      8. Unique Constraint (FAIL/BLOCKED; N/A if ORM has none)
      9. Index             (FAIL/BLOCKED)

    PASS    = 已驗證且一致
    FAIL    = 已確認 Schema 不一致
    BLOCKED = 無法完成驗證
    N/A     = ORM 未宣告此約束

    發現任何 FAIL 或 BLOCKED → raise RuntimeError（列出全部問題）。
    禁止自動修復任何 Schema Drift。
    """
    from sqlalchemy import Numeric, String
    from sqlalchemy import inspect as _insp

    insp = _insp(engine)
    is_pg = engine.dialect.name == "postgresql"
    issues: list[str] = []

    for tbl_name in tables:
        # ── Check 1: ORM metadata lookup ─────────────────────────────
        try:
            orm = _get_orm_schema(tbl_name)
        except RuntimeError as e:
            issues.append(str(e))
            continue

        # ── Get actual columns from DB ────────────────────────────────
        try:
            actual_cols_raw = insp.get_columns(tbl_name)
        except Exception as e:
            issues.append(f"[BLOCKED] {tbl_name}: 無法讀取欄位 — {e}")
            continue

        actual_cols = {c["name"]: c for c in actual_cols_raw}

        # ── Check 2: Column names ─────────────────────────────────────
        expected_names = set(orm["columns"])
        missing_names = expected_names - set(actual_cols)
        if missing_names:
            issues.append(
                f"[FAIL] {tbl_name}: 缺少欄位 {sorted(missing_names)} — "
                f"Expected all of {sorted(expected_names)}"
            )
            continue  # 後續型別驗證無意義
        logger.info(f"  {tbl_name}: Check 2 (columns) PASS ({len(actual_cols)} cols)")

        # ── Check 3: NOT NULL (PG only) ───────────────────────────────
        if is_pg:
            nn_ok = True
            for col_name, col_info in sorted(orm["columns"].items()):
                if col_info["nullable"] or col_info["primary_key"]:
                    continue  # nullable=True or PK (implicitly NOT NULL)
                actual = actual_cols.get(col_name, {})
                if actual.get("nullable", True):
                    issues.append(
                        f"[FAIL] {tbl_name}.{col_name}: NOT NULL — "
                        f"Expected NOT NULL, Actual nullable=True"
                    )
                    nn_ok = False
            if nn_ok:
                logger.info(f"  {tbl_name}: Check 3 (NOT NULL) PASS")

        # ── Check 4: NUMERIC precision/scale (PG only) ───────────────
        if is_pg:
            num_ok = True
            for col_name, col_info in sorted(orm["columns"].items()):
                t = col_info["type"]
                if not isinstance(t, Numeric) or t.precision is None:
                    continue
                exp_prec, exp_scale = t.precision, t.scale
                actual = actual_cols.get(col_name, {})
                act_type = actual.get("type")
                act_prec = getattr(act_type, "precision", None)
                act_scale = getattr(act_type, "scale", None)
                if act_prec is None or act_scale is None:
                    issues.append(
                        f"[BLOCKED] {tbl_name}.{col_name}: 無法讀取 NUMERIC precision "
                        f"(type={act_type!r}) — Expected NUMERIC({exp_prec},{exp_scale})"
                    )
                    num_ok = False
                elif act_prec != exp_prec or act_scale != exp_scale:
                    issues.append(
                        f"[FAIL] {tbl_name}.{col_name}: NUMERIC — "
                        f"Expected ({exp_prec},{exp_scale}), "
                        f"Actual ({act_prec},{act_scale})"
                    )
                    num_ok = False
            if num_ok:
                logger.info(f"  {tbl_name}: Check 4 (NUMERIC) PASS")

        # ── Check 5: VARCHAR length (PG only) ─────────────────────────
        if is_pg:
            vc_ok = True
            for col_name, col_info in sorted(orm["columns"].items()):
                t = col_info["type"]
                if not isinstance(t, String) or t.length is None:
                    continue
                exp_len = t.length
                actual = actual_cols.get(col_name, {})
                act_type = actual.get("type")
                act_len = getattr(act_type, "length", None)
                if act_len is None:
                    issues.append(
                        f"[BLOCKED] {tbl_name}.{col_name}: 無法讀取 VARCHAR length "
                        f"(type={act_type!r}) — Expected VARCHAR({exp_len})"
                    )
                    vc_ok = False
                elif act_len != exp_len:
                    issues.append(
                        f"[FAIL] {tbl_name}.{col_name}: VARCHAR length — "
                        f"Expected VARCHAR({exp_len}), Actual VARCHAR({act_len})"
                    )
                    vc_ok = False
            if vc_ok:
                logger.info(f"  {tbl_name}: Check 5 (VARCHAR) PASS")

        # ── Check 6: Primary Key ──────────────────────────────────────
        try:
            pk_info = insp.get_pk_constraint(tbl_name)
            actual_pks = set(pk_info.get("constrained_columns", []))
            if orm["pks"] != actual_pks:
                issues.append(
                    f"[FAIL] {tbl_name}: PK — "
                    f"Expected {sorted(orm['pks'])}, Actual {sorted(actual_pks)}"
                )
            else:
                logger.info(f"  {tbl_name}: Check 6 (PK) PASS {sorted(actual_pks)}")
        except Exception as e:
            issues.append(f"[BLOCKED] {tbl_name}: PK 無法讀取 — {e}")

        # ── Check 7: Foreign Key constraints ─────────────────────────
        if orm["fks"]:
            try:
                actual_fks_raw = insp.get_foreign_keys(tbl_name)
                # Build lookup: (local_col, ref_table, ref_col) → full fk dict
                actual_fk_map: dict = {}
                for afk in actual_fks_raw:
                    lc = (afk.get("constrained_columns") or [None])[0]
                    rt = afk.get("referred_table")
                    rc = (afk.get("referred_columns") or [None])[0]
                    if lc and rt and rc:
                        actual_fk_map[(lc, rt, rc)] = afk

                fk_ok = True
                for spec in orm["fks"]:
                    key = (spec["local_col"], spec["ref_table"], spec["ref_col"])
                    if key not in actual_fk_map:
                        issues.append(
                            f"[FAIL] {tbl_name}.{spec['local_col']}: FK 缺失 — "
                            f"Expected → {spec['ref_table']}.{spec['ref_col']}"
                        )
                        fk_ok = False
                    elif is_pg and spec["ondelete"]:
                        # Check ON DELETE on PostgreSQL (where it's enforced)
                        afk = actual_fk_map[key]
                        actual_od = (
                            (afk.get("options") or {}).get("ondelete") or ""
                        ).upper()
                        if actual_od and actual_od != spec["ondelete"]:
                            issues.append(
                                f"[FAIL] {tbl_name}.{spec['local_col']}: FK ON DELETE — "
                                f"Expected {spec['ondelete']}, Actual {actual_od}"
                            )
                            fk_ok = False

                if fk_ok:
                    logger.info(
                        f"  {tbl_name}: Check 7 (FK) PASS "
                        f"({len(orm['fks'])} constraints)"
                    )
            except Exception as e:
                issues.append(f"[BLOCKED] {tbl_name}: FK 無法讀取 — {e}")
        else:
            logger.info(f"  {tbl_name}: Check 7 (FK) N/A (ORM 無 ForeignKey() 宣告)")

        # ── Check 8: Unique Constraints ───────────────────────────────
        # ALTER TABLE path (e.g., idempotency_key) may use CREATE UNIQUE INDEX
        # instead of ADD CONSTRAINT — check both get_unique_constraints() and
        # unique entries in get_indexes() to accept either implementation.
        if orm["unique_constraints"]:
            try:
                actual_ucs = insp.get_unique_constraints(tbl_name)
                actual_idxs = insp.get_indexes(tbl_name)
                covered: set[frozenset] = {
                    frozenset(uc.get("column_names", [])) for uc in actual_ucs
                }
                for idx in actual_idxs:
                    if idx.get("unique"):
                        covered.add(frozenset(idx.get("column_names", [])))
                missing_ucs = [s for s in orm["unique_constraints"] if s not in covered]
                if missing_ucs:
                    issues.append(
                        f"[FAIL] {tbl_name}: Unique Constraint 缺失 — "
                        f"Expected {[sorted(s) for s in missing_ucs]}"
                    )
                else:
                    logger.info(f"  {tbl_name}: Check 8 (UC) PASS")
            except Exception as e:
                issues.append(f"[BLOCKED] {tbl_name}: UC 無法讀取 — {e}")
        else:
            logger.info(f"  {tbl_name}: Check 8 (UC) N/A (ORM 無 UniqueConstraint)")

        # ── Check 9: Indexes ──────────────────────────────────────────
        try:
            actual_idxs = insp.get_indexes(tbl_name)
            actual_idx_col_sets = [
                frozenset(idx.get("column_names", [])) for idx in actual_idxs
            ]
            idx_ok = True
            for expected_col_set in orm["indexes"]:
                if not any(expected_col_set <= act for act in actual_idx_col_sets):
                    col_name = next(iter(expected_col_set))
                    issues.append(
                        f"[FAIL] {tbl_name}.{col_name}: index 缺失 " f"(ORM index=True)"
                    )
                    idx_ok = False
            if idx_ok:
                logger.info(
                    f"  {tbl_name}: Check 9 (Index) PASS "
                    f"({sorted(idx.get('name', '?') for idx in actual_idxs if idx.get('name'))})"
                )
        except Exception as e:
            issues.append(f"[BLOCKED] {tbl_name}: Index 無法讀取 — {e}")

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


# ── Table creation ────────────────────────────────────────────────────


def _create_tables(engine, missing: list, dry_run: bool) -> None:
    """按依賴順序建立缺失的新表。

    PostgreSQL: DDL wrapped in engine.begin() → atomic rollback on failure.
    SQLite: DDL is not fully transactional; warn user.
    建立順序：actual_positions → trade_executions → position_plan_changes
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


def _validate_protected_tables_untouched(engine, before_cols: dict) -> None:
    """確認受保護的舊表欄位未被修改。"""
    from sqlalchemy import inspect

    insp = inspect(engine)
    for tbl, cols_before in before_cols.items():
        try:
            cols_after = {c["name"] for c in insp.get_columns(tbl)}
        except Exception:
            continue
        removed = cols_before - cols_after
        if removed:
            raise RuntimeError(f"受保護的表 {tbl} 被意外修改！刪除欄位：{removed}")
    logger.info("受保護的舊表完整性確認 ✓")


# ── Main ──────────────────────────────────────────────────────────────


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

    # ── Step 2: Apply approved versioned migrations to existing tables ──
    if already_exist:
        logger.info(f"\n── Step 2: 套用已核准版本化 Migration（{already_exist}）──")
        n = _apply_pending_migrations(engine, already_exist, dry_run)
        if n:
            logger.info(
                f"已套用 {n} 個 Migration ({'dry-run' if dry_run else '實際寫入'}) ✓"
            )
        else:
            logger.info("無待套用的 Migration")

    # ── Step 3: Validate existing tables (should PASS after Step 2) ──
    if already_exist:
        logger.info(f"\n── Step 3: 驗證既有表 Schema（{already_exist}）──")
        try:
            _validate_schema(engine, already_exist)
            logger.info("既有表 Schema 驗證通過 ✓")
        except RuntimeError as drift_err:
            logger.error("\n" + "=" * 60)
            logger.error("Schema Drift 偵測！Migration 中止。")
            logger.error("=" * 60)
            logger.error(str(drift_err))
            logger.error("\n既有表存在 Schema 不一致，不執行任何 DDL。")
            logger.error(
                "若 Drift 屬於預期升級，請將其加入 _APPROVED_MIGRATIONS 後重新執行。"
            )
            logger.error("若 Drift 屬於異常，請人工修復後重新執行。")
            sys.exit(2)

    if not missing:
        logger.info("\n三張表已全部存在，Schema 驗證通過。無需 Migration。")
        sys.exit(0)

    # ── Step 4: Controlled Migration ─────────────────────────────────
    protected_snapshot: dict = {}
    for tbl in _PROTECTED_TABLES:
        try:
            protected_snapshot[tbl] = {c["name"] for c in insp.get_columns(tbl)}
        except Exception:
            pass

    logger.info(f"\n── Step 4: Controlled Migration（{missing}）──")
    _create_tables(engine, missing, dry_run)

    if dry_run:
        logger.info("\n[DRY-RUN] 以上為 Migration 計畫，未執行任何寫入。")
        sys.exit(0)

    # ── Step 5: Post-Migration Validation ────────────────────────────
    logger.info("\n── Step 5: Post-Migration 完整驗證 ──")
    _validate_schema(engine, _REQUIRED_TABLES)
    _validate_protected_tables_untouched(engine, protected_snapshot)

    logger.info("\n" + "=" * 60)
    logger.info("Migration 完成 ✓  (Steps 1-5 全部通過)")
    logger.info("=" * 60)
    logger.info("\n後續步驟：")
    logger.info("  1. 確認 GitHub Actions Daily Pipeline 正常執行")
    logger.info("  2. 在 Dashboard 記錄第一筆 ACTUAL 成交，確認寫入正常")
    logger.info("  3. 若需回滾，使用 Migration 前建立的 Neon Branch 還原")
    logger.info("     （不得使用 DROP TABLE 刪除生產資料）")


if __name__ == "__main__":
    main()
