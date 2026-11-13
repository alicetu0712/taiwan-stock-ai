"""
backfill_daily_prices_protected.py — Entry guard wrapper for backfill execution

This is NOT a replacement for backfill_daily_prices.py. All backfill logic remains
in that module. This wrapper adds a defense-in-depth invocation guard before
the --execute path, enforcing that execute calls come from an authorized context.

Authorization hierarchy:
  1. BACKFILL_ALLOW_DIRECT=1  — maintenance override (must be explicit)
  2. CALLED_FROM_WRAPPER=1    — set by hybrid_shadow_cron wrappers
  3. Parent process name       — parent cmdline contains 'hybrid_shadow_cron'

Dry-run (no --execute) is always allowed, unchanged from the base script.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.backfill_daily_prices import _default_start, run_backfill
from scripts.scheduler_safety_guards import BackfillEntryGuard


def main() -> None:
    default_start = _default_start()
    parser = argparse.ArgumentParser(
        description=(
            "Protected DailyPrice backfill entry point. "
            "Requires wrapper authorization for --execute. "
            "Dry-run is always allowed."
        )
    )
    parser.add_argument(
        "--start", default=str(default_start),
        help=f"Start date YYYY-MM-DD (default: {default_start})",
    )
    parser.add_argument(
        "--end", default=str(date.today()),
        help=f"End date YYYY-MM-DD (default: today = {date.today()})",
    )
    parser.add_argument(
        "--execute", action="store_true",
        help="Actually write to DB. Requires wrapper authorization.",
    )
    parser.add_argument(
        "--db", default=None,
        help="Override DB path (default: data/platform.db)",
    )
    args = parser.parse_args()

    # Defense-in-depth: check authorization before any --execute path.
    # Dry-run always passes (check_invocation returns True when is_execute=False).
    authorized, message = BackfillEntryGuard.check_invocation(is_execute=args.execute)

    if not authorized:
        print(f"[BACKFILL_GUARD] BLOCKED: {message}", file=sys.stderr)
        print(
            "[BACKFILL_GUARD] No data was read or written.",
            file=sys.stderr,
        )
        sys.exit(2)  # exit code 2 = safety block (not a backfill failure)

    if args.execute and "AUTHORIZED_MAINTENANCE" in message:
        print(f"[BACKFILL_GUARD] WARNING: {message}", file=sys.stderr)

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)

    if start > end:
        print(f"[INFO] start={start} > end={end}: DB already current, nothing to backfill")
        sys.exit(0)

    run_backfill(start=start, end=end, execute=args.execute, db_path=args.db)


if __name__ == "__main__":
    main()
