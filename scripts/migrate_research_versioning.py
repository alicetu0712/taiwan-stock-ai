"""
scripts/migrate_research_versioning.py — Research versioning schema migration

SAFETY: This script operates ONLY on the research schema (v2_shadow_signals).
        It MUST NOT be run against the production database.
        It requires RESEARCH_DB_URL env var OR explicit --db-url argument.

Changes applied:
  1. ADD COLUMN research_version VARCHAR(30) NOT NULL DEFAULT 'v2_research_v1'
  2. ADD COLUMN is_legacy BOOLEAN NOT NULL DEFAULT FALSE
  3. UPDATE existing rows: is_legacy = TRUE (all pre-migration rows are legacy)
  4. DROP old unique index uq_v2ss_date_stock
  5. CREATE UNIQUE INDEX uq_v2ss_date_stock_version ON
         v2_shadow_signals (trade_date, stock_id, research_version)

Usage:
  # Dry run — shows SQL, no changes
  python scripts/migrate_research_versioning.py --dry-run

  # Apply to isolated research DB
  RESEARCH_DB_URL=postgresql://... python scripts/migrate_research_versioning.py --confirm

  # Or pass DB URL explicitly
  python scripts/migrate_research_versioning.py --db-url postgresql://... --confirm
"""

from __future__ import annotations

import argparse
import os
import sys
import textwrap

STEPS = [
    (
        "add_research_version",
        textwrap.dedent("""\
            ALTER TABLE v2_shadow_signals
            ADD COLUMN IF NOT EXISTS research_version VARCHAR(30)
                NOT NULL DEFAULT 'v2_research_v1';
        """),
    ),
    (
        "add_is_legacy",
        textwrap.dedent("""\
            ALTER TABLE v2_shadow_signals
            ADD COLUMN IF NOT EXISTS is_legacy BOOLEAN NOT NULL DEFAULT FALSE;
        """),
    ),
    (
        "mark_existing_as_legacy",
        textwrap.dedent("""\
            UPDATE v2_shadow_signals
            SET is_legacy = TRUE
            WHERE research_version = 'v2_research_v1'
              AND is_legacy = FALSE;
        """),
    ),
    (
        "drop_old_unique_index",
        textwrap.dedent("""\
            DROP INDEX IF EXISTS uq_v2ss_date_stock;
        """),
    ),
    (
        "create_new_unique_index",
        textwrap.dedent("""\
            CREATE UNIQUE INDEX IF NOT EXISTS uq_v2ss_date_stock_version
            ON v2_shadow_signals (trade_date, stock_id, research_version);
        """),
    ),
]

SAFETY_DENY_PATTERNS = [
    "actual_positions",
    "trade_executions",
    "forward_signals",
    "position_monitors",
    "daily_prices",
    "stocks",
    "financial_metrics",
]


def _safety_check(db_url: str) -> None:
    """Refuse to run if DB URL looks like production."""
    url_lower = db_url.lower()
    if any(pat in url_lower for pat in ["neon.tech", "prod", "production", "main"]):
        print("ERROR: DB URL looks like a production database. Aborting.")
        print(f"  URL: {db_url[:60]}...")
        sys.exit(2)


def _run(db_url: str, dry_run: bool) -> None:
    _safety_check(db_url)

    try:
        import psycopg2
    except ImportError:
        print("ERROR: psycopg2 not installed. pip install psycopg2-binary")
        sys.exit(1)

    print(f"\nResearch Versioning Migration")
    print(f"  DB  : {db_url[:70]}...")
    print(f"  Mode: {'DRY RUN (no changes)' if dry_run else 'APPLY'}")
    print()

    if not dry_run:
        conn = psycopg2.connect(db_url)
        conn.autocommit = False
        cur = conn.cursor()

        # Verify table exists and is research-only
        cur.execute(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_name = 'v2_shadow_signals'"
        )
        if cur.fetchone()[0] == 0:
            print("ERROR: v2_shadow_signals table not found. Wrong database?")
            conn.close()
            sys.exit(1)

        # Refuse if production tables are present
        cur.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_name = ANY(%s)",
            (SAFETY_DENY_PATTERNS,),
        )
        prod_tables = [r[0] for r in cur.fetchall()]
        if prod_tables:
            print(f"ERROR: Production tables found: {prod_tables}. Aborting.")
            conn.close()
            sys.exit(2)

    for step_name, sql in STEPS:
        print(f"  [{step_name}]")
        for line in sql.strip().splitlines():
            print(f"    {line}")
        if not dry_run:
            cur.execute(sql)
            print(f"    → executed ({cur.rowcount} rows affected)")
        print()

    if not dry_run:
        conn.commit()
        print("Migration committed.")

        # Verify
        cur.execute(
            "SELECT COUNT(*) FROM v2_shadow_signals WHERE research_version = 'v2_research_v1'"
        )
        legacy_count = cur.fetchone()[0]
        cur.execute(
            "SELECT COUNT(*) FROM pg_indexes "
            "WHERE tablename = 'v2_shadow_signals' "
            "AND indexname = 'uq_v2ss_date_stock_version'"
        )
        idx_exists = cur.fetchone()[0] > 0
        print(f"\nVerification:")
        print(f"  Rows with research_version='v2_research_v1': {legacy_count}")
        print(f"  New unique index exists: {idx_exists}")
        conn.close()
    else:
        print("Dry run complete — no changes made.")
        print("Re-run with --confirm to apply.")


def main() -> None:
    p = argparse.ArgumentParser(description="Research versioning migration (research DB only)")
    p.add_argument("--db-url", default=os.environ.get("RESEARCH_DB_URL", ""))
    p.add_argument("--dry-run", action="store_true", help="Print SQL without executing")
    p.add_argument("--confirm", action="store_true", help="Actually apply changes")
    args = p.parse_args()

    if not args.dry_run and not args.confirm:
        print("Specify --dry-run to preview or --confirm to apply changes.")
        sys.exit(1)

    if args.dry_run and args.confirm:
        print("Cannot use --dry-run and --confirm together.")
        sys.exit(1)

    if not args.dry_run and not args.db_url:
        print("ERROR: --db-url or RESEARCH_DB_URL env var required for --confirm.")
        sys.exit(1)

    _run(args.db_url, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
