"""
migrate_entry_timing_v2.py — Manual migration for V2 shadow tables.

NEVER run on Production Neon automatically.
Run manually from local or staging:
  python scripts/migrate_entry_timing_v2.py [--dry-run]

Creates (if missing):
  - v2_shadow_signals
  - v2_shadow_outcomes

Adds missing columns (if table already exists but schema is stale):
  - v2_shadow_signals.research_version VARCHAR(30) DEFAULT 'v2_research_v1'
  - v2_shadow_signals.is_legacy BOOLEAN DEFAULT FALSE
  - ix_v2_shadow_signals_research_version index

Upgrades unique constraints (PostgreSQL only):
  - DROP uq_v2ss_date_stock         (old 2-col: trade_date, stock_id)
  - ADD  uq_v2ss_date_stock_version (new 3-col: trade_date, stock_id, research_version)

Atomicity guarantee:
  All column additions AND constraint upgrade execute in a single PostgreSQL transaction.
  If any step fails, the entire migration rolls back — no partial schema left behind.
  This applies only to main(); _migrate_columns() and _migrate_constraints() are
  standalone helpers kept for unit tests.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Columns required in v2_shadow_signals that may be absent in stale schema.
# Each entry: (column_name, ALTER TABLE DDL, index DDL or None)
_REQUIRED_COLUMNS: list[tuple[str, str, str | None]] = [
    (
        "research_version",
        "ALTER TABLE v2_shadow_signals "
        "ADD COLUMN research_version VARCHAR(30) NOT NULL DEFAULT 'v2_research_v1'",
        "CREATE INDEX IF NOT EXISTS ix_v2_shadow_signals_research_version "
        "ON v2_shadow_signals(research_version)",
    ),
    (
        "is_legacy",
        "ALTER TABLE v2_shadow_signals ADD COLUMN is_legacy BOOLEAN NOT NULL DEFAULT FALSE",
        None,
    ),
]

# Constraint upgrades (PostgreSQL only).
# Format: (table, old_constraint_name_or_None, new_constraint_name, new_ddl_fragment)
# Prerequisite: columns in new constraint must already exist in the same transaction.
_CONSTRAINT_UPGRADES: list[tuple[str, str | None, str, str]] = [
    (
        "v2_shadow_signals",
        "uq_v2ss_date_stock",           # old 2-col constraint (trade_date, stock_id)
        "uq_v2ss_date_stock_version",   # new 3-col constraint name
        "ADD CONSTRAINT uq_v2ss_date_stock_version "
        "UNIQUE (trade_date, stock_id, research_version)",
    ),
]


# ---------------------------------------------------------------------------
# Inspection helpers (read-only, used by both main() and unit tests)
# ---------------------------------------------------------------------------

def _pending_columns(insp) -> list[tuple[str, str, str | None]]:
    """Return list of (col_name, alter_ddl, index_ddl) for columns not yet in the table."""
    table_name = "v2_shadow_signals"
    if table_name not in set(insp.get_table_names()):
        return []
    existing = {c["name"] for c in insp.get_columns(table_name)}
    return [(col, ddl, idx) for col, ddl, idx in _REQUIRED_COLUMNS if col not in existing]


def _pending_constraints(engine, insp) -> list[tuple[str | None, str]]:
    """Return list of (drop_sql or None, add_sql) for needed constraint upgrades.

    PostgreSQL only — SQLite does not support ALTER TABLE DROP CONSTRAINT.
    """
    if engine.dialect.name != "postgresql":
        return []
    result = []
    for table_name, old_name, new_name, new_ddl in _CONSTRAINT_UPGRADES:
        if table_name not in set(insp.get_table_names()):
            continue
        existing = {c["name"] for c in insp.get_unique_constraints(table_name)}
        if new_name in existing:
            continue
        drop = (
            f"ALTER TABLE {table_name} DROP CONSTRAINT {old_name}"
            if (old_name and old_name in existing)
            else None
        )
        result.append((drop, f"ALTER TABLE {table_name} {new_ddl}"))
    return result


# ---------------------------------------------------------------------------
# Standalone helpers (kept for unit test backward compatibility)
# ---------------------------------------------------------------------------

def _migrate_columns(engine, insp, dry_run: bool) -> int:
    """Add missing columns. Each column in its own transaction.

    Used by unit tests (VM01–VM05). Production migration uses main() which is atomic.
    """
    from sqlalchemy import text

    table_name = "v2_shadow_signals"
    if table_name not in set(insp.get_table_names()):
        return 0

    existing_cols = {c["name"] for c in insp.get_columns(table_name)}
    changes = 0

    for col_name, alter_ddl, index_ddl in _REQUIRED_COLUMNS:
        if col_name in existing_cols:
            continue
        prefix = "[DRY-RUN] " if dry_run else ""
        print(f"{prefix}ADD COLUMN {table_name}.{col_name}")
        if index_ddl:
            print(f"{prefix}CREATE INDEX ix_v2_shadow_signals_{col_name}")
        if not dry_run:
            with engine.begin() as conn:
                conn.execute(text(alter_ddl))
                if index_ddl:
                    conn.execute(text(index_ddl))
        changes += 1

    return changes


def _migrate_constraints(engine, insp, dry_run: bool) -> int:
    """Upgrade unique constraints. PostgreSQL only.

    Used by unit tests (VM11–VM15). Production migration uses main() which is atomic.
    """
    from sqlalchemy import text

    if engine.dialect.name != "postgresql":
        return 0

    changes = 0

    for table_name, old_name, new_name, new_ddl in _CONSTRAINT_UPGRADES:
        if table_name not in set(insp.get_table_names()):
            continue

        from sqlalchemy import inspect as sa_inspect
        fresh_insp = sa_inspect(engine)
        existing_constraints = {c["name"] for c in fresh_insp.get_unique_constraints(table_name)}

        if new_name in existing_constraints:
            continue

        prefix = "[DRY-RUN] " if dry_run else ""
        if old_name and old_name in existing_constraints:
            print(f"{prefix}DROP CONSTRAINT {old_name} ON {table_name}")
        print(f"{prefix}ALTER TABLE {table_name} {new_ddl}")

        if not dry_run:
            with engine.begin() as conn:
                if old_name and old_name in existing_constraints:
                    conn.execute(text(f"ALTER TABLE {table_name} DROP CONSTRAINT {old_name}"))
                conn.execute(text(f"ALTER TABLE {table_name} {new_ddl}"))

        changes += 1

    return changes


# ---------------------------------------------------------------------------
# Main — fully atomic execution
# ---------------------------------------------------------------------------

def main(dry_run: bool = False) -> int:
    """Execute all pending schema changes in a single atomic PostgreSQL transaction.

    Execution order within the atomic block:
      1. ADD COLUMN research_version (+ index)
      2. ADD COLUMN is_legacy
      3. DROP old 2-col constraint
      4. ADD new 3-col constraint (references research_version — must add column first)

    If any step raises, the entire transaction rolls back automatically.
    """
    from config import DATABASE_URL
    from sqlalchemy import create_engine, inspect, text

    from src.research.models import ResearchBase, V2ShadowOutcome, V2ShadowSignal

    engine = create_engine(DATABASE_URL, echo=False, future=True)
    insp = inspect(engine)
    existing = set(insp.get_table_names())

    tables_to_create = [V2ShadowSignal.__tablename__, V2ShadowOutcome.__tablename__]
    pending_tables = [t for t in tables_to_create if t not in existing]

    # --- Plan phase (all reads, no writes) ---
    col_plan = _pending_columns(insp)
    con_plan = _pending_constraints(engine, insp)

    if not pending_tables and not col_plan and not con_plan:
        print("✓ V2 shadow tables already exist and schema is up to date — nothing to do.")
        return 0

    # Print plan
    prefix = "[DRY-RUN] " if dry_run else ""
    for col_name, _, index_ddl in col_plan:
        print(f"{prefix}ADD COLUMN v2_shadow_signals.{col_name}")
        if index_ddl:
            idx_name = index_ddl.split("EXISTS ")[1].split(" ON")[0]
            print(f"{prefix}CREATE INDEX {idx_name}")
    for drop_sql, add_sql in con_plan:
        if drop_sql:
            con_name = drop_sql.split("CONSTRAINT ")[1].split()[0]
            print(f"{prefix}DROP CONSTRAINT {con_name} ON v2_shadow_signals")
        print(f"{prefix}{add_sql}")
    for t in pending_tables:
        print(f"{prefix}CREATE TABLE {t}")

    if dry_run:
        total = len(col_plan) + len(con_plan) + len(pending_tables)
        print(f"\nDry-run complete — {total} change(s) would be applied.")
        return 0

    # --- Execute phase: ALL column + constraint DDL in ONE atomic transaction ---
    if col_plan or con_plan:
        with engine.begin() as conn:  # single BEGIN … COMMIT for all DDL
            for _, alter_ddl, index_ddl in col_plan:
                conn.execute(text(alter_ddl))
                if index_ddl:
                    conn.execute(text(index_ddl))
            for drop_sql, add_sql in con_plan:
                if drop_sql:
                    conn.execute(text(drop_sql))
                conn.execute(text(add_sql))

    # Create missing tables (independent of column/constraint migration)
    if pending_tables:
        ResearchBase.metadata.create_all(engine, checkfirst=True)
        insp2 = inspect(engine)
        after = set(insp2.get_table_names())
        for t in tables_to_create:
            if t not in after:
                print(f"ERROR: {t} still missing after create_all", file=sys.stderr)
                return 1
        print(f"\n✓ Created {len(pending_tables)} table(s): {', '.join(pending_tables)}")

    if col_plan:
        print(f"✓ Added {len(col_plan)} missing column(s) to v2_shadow_signals")
    if con_plan:
        print(f"✓ Upgraded {len(con_plan)} constraint(s) on v2_shadow_signals")

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create V2 shadow tables and migrate schema")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be created without executing",
    )
    args = parser.parse_args()
    sys.exit(main(dry_run=args.dry_run))
