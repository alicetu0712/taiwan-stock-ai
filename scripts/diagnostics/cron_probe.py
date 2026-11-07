#!/usr/bin/env python3
"""
Cron Probe — Session 33
Isolated scheduler verification probe.

Completely isolated from the trading system:
- No imports from src.research or scripts
- No database connections (SQLite or Neon)
- No network calls
- No API key access
- No ForwardSignals / Hybrid shadow interaction

Usage:
    python3 scripts/diagnostics/cron_probe.py --dry-run
    python3 scripts/diagnostics/cron_probe.py --execute
    python3 scripts/diagnostics/cron_probe.py --execute --output-dir /tmp/probe
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import uuid
import zoneinfo
from pathlib import Path

PROBE_VERSION = "v1"
TAIWAN_TZ = zoneinfo.ZoneInfo("Asia/Taipei")


def _build_record() -> dict:
    utc_now = datetime.datetime.now(datetime.UTC)
    taiwan_now = utc_now.astimezone(TAIWAN_TZ)
    return {
        "probe_version": PROBE_VERSION,
        "test_id": str(uuid.uuid4()),
        "utc_timestamp": utc_now.isoformat(),
        "taiwan_timestamp": taiwan_now.isoformat(),
        "pid": os.getpid(),
        "uid": os.getuid(),
        "python_executable": sys.executable,
        "working_directory": os.getcwd(),
        "exit_code": 0,
    }


def dry_run() -> int:
    record = _build_record()
    record["mode"] = "dry_run"
    print(json.dumps(record, indent=2))
    return 0


def execute(output_dir: Path) -> int:
    record = _build_record()
    record["mode"] = "execute"
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
    out_path = output_dir / f"cron_probe_{ts}_{os.getpid()}.json"
    out_path.write_text(json.dumps(record, indent=2))
    print(json.dumps(record, indent=2))
    print(f"OUTPUT: {out_path}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Isolated cron probe — no trading code, no DB, no network"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Print probe record to stdout only")
    mode.add_argument("--execute", action="store_true", help="Write probe record to output-dir")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("/tmp/cron_probe_output"),
        help="Directory to write output JSON (default: /tmp/cron_probe_output)",
    )
    args = parser.parse_args(argv)
    if args.dry_run:
        return dry_run()
    return execute(args.output_dir)


if __name__ == "__main__":
    sys.exit(main())
