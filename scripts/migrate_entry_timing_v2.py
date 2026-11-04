"""
migrate_entry_timing_v2.py — Manual migration for V2 shadow tables.

NEVER run on Production Neon automatically.
Run manually from local or staging:
  python scripts/migrate_entry_timing_v2.py [--dry-run]

Creates:
  - v2_shadow_signals
  - v2_shadow_outcomes
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main(dry_run: bool = False) -> int:
    from config import DATABASE_URL
    from sqlalchemy import create_engine, inspect

    from src.research.models import ResearchBase, V2ShadowOutcome, V2ShadowSignal

    engine = create_engine(DATABASE_URL, echo=False, future=True)
    insp = inspect(engine)
    existing = set(insp.get_table_names())

    tables_to_create = [
        V2ShadowSignal.__tablename__,
        V2ShadowOutcome.__tablename__,
    ]
    pending = [t for t in tables_to_create if t not in existing]

    if not pending:
        print("✓ V2 shadow tables already exist — nothing to do.")
        return 0

    for t in pending:
        print(f"{'[DRY-RUN] ' if dry_run else ''}CREATE TABLE {t}")

    if dry_run:
        print(f"\nDry-run complete — {len(pending)} table(s) would be created.")
        return 0

    ResearchBase.metadata.create_all(engine, checkfirst=True)

    # verify
    insp2 = inspect(engine)
    after = set(insp2.get_table_names())
    for t in tables_to_create:
        if t not in after:
            print(f"ERROR: {t} still missing after create_all", file=sys.stderr)
            return 1

    print(f"\n✓ Created {len(pending)} table(s): {', '.join(pending)}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create V2 shadow tables")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be created without executing",
    )
    args = parser.parse_args()
    sys.exit(main(dry_run=args.dry_run))
