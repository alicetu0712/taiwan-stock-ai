"""
scripts/hybrid_shadow_cron.py — Daily automation wrapper for Hybrid Forward Shadow

SAFETY CONSTRAINTS (enforced at startup):
  1. Only writes to local SQLite — NEVER touches production Neon.
  2. File lock prevents concurrent execution (fcntl.flock on macOS/Linux).
  3. Checks Taiwan market data readiness before fetching (>= 15:30 Taiwan time).
  4. Requires backfill QG to pass before running shadow runner.
  5. Creates DB backup before every shadow run.
  6. Dry-run default — requires --execute to do any writes or shadow run.
  7. Idempotent: safe to call multiple times in the same day.

NOT installed automatically. Configure crontab with explicit approval only.

Recommended crontab line (Taiwan 16:00 = UTC 08:00):
  0 8 * * 1-5  /path/to/python3 /path/to/stock_platform/scripts/hybrid_shadow_cron.py --execute >> /path/to/stock_platform/logs/cron.log 2>&1

Usage:
  python scripts/hybrid_shadow_cron.py                 # dry-run, all checks only
  python scripts/hybrid_shadow_cron.py --execute        # full run with writes
  python scripts/hybrid_shadow_cron.py --execute --no-backup  # skip backup (testing only)
  python scripts/hybrid_shadow_cron.py --status         # print last run status and exit
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import pytz

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import DB_PATH
from src.core.trading_calendar import TaiwanTradingCalendar

# ── Constants ─────────────────────────────────────────────────────────────────

TAIWAN_TZ = pytz.timezone("Asia/Taipei")
DATA_READY_HOUR = 15
DATA_READY_MINUTE = 30

LOCK_FILE = Path(__file__).parent.parent / "data" / ".cron.lock"
BACKUP_DIR = Path(__file__).parent.parent / "data" / "backups"
LOG_DIR = Path(__file__).parent.parent / "logs"
STATE_FILE = Path(__file__).parent.parent / "data" / ".cron_state.json"

BACKUP_KEEP_N = 7           # number of backups to retain
MIN_BACKUP_SIZE_BYTES = 100_000  # safety: refuse backup if DB seems empty

SCRIPTS_DIR = Path(__file__).parent
PYTHON = sys.executable
CALENDAR = TaiwanTradingCalendar()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now_taipei() -> datetime:
    return datetime.now(TAIWAN_TZ)


def _is_data_ready(now_taipei: Optional[datetime] = None) -> bool:
    """True if Taiwan time >= 15:30 (TWSE/TPEx data expected published)."""
    if now_taipei is None:
        now_taipei = _now_taipei()
    t = now_taipei.time()
    return (t.hour, t.minute) >= (DATA_READY_HOUR, DATA_READY_MINUTE)


def _get_db_last_date() -> Optional[date]:
    if not os.path.isfile(str(DB_PATH)):
        return None
    try:
        conn = sqlite3.connect(str(DB_PATH))
        row = conn.execute(
            "SELECT MAX(date) FROM daily_prices WHERE stock_id='0050'"
        ).fetchone()
        conn.close()
        return date.fromisoformat(row[0]) if row and row[0] else None
    except Exception:
        return None


def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str))


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"[{ts}] {msg}"
    print(line, flush=True)


# ── File lock ─────────────────────────────────────────────────────────────────

class FileLock:
    """Non-blocking exclusive file lock using fcntl.flock (macOS/Linux)."""

    def __init__(self, path: Path):
        self._path = path
        self._fd: Optional[int] = None

    def acquire(self) -> bool:
        """Returns True if lock acquired; False if another process holds it."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._fd = os.open(str(self._path), os.O_CREAT | os.O_WRONLY)
        try:
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            os.write(self._fd, f"{os.getpid()}\n".encode())
            return True
        except BlockingIOError:
            os.close(self._fd)
            self._fd = None
            return False

    def release(self) -> None:
        if self._fd is not None:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
                os.close(self._fd)
            except Exception:
                pass
            self._fd = None


# ── Backup ────────────────────────────────────────────────────────────────────

def create_backup(db_path: str, today: date) -> Optional[Path]:
    """
    Copy SQLite DB to data/backups/platform_YYYYMMDD_HHMMSS.db.bak.
    Returns the backup path or None on failure.
    """
    src = Path(db_path)
    if not src.is_file():
        _log(f"[backup] SKIP — DB not found: {db_path}")
        return None

    size = src.stat().st_size
    if size < MIN_BACKUP_SIZE_BYTES:
        _log(f"[backup] SKIP — DB too small ({size} bytes), looks empty")
        return None

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = BACKUP_DIR / f"platform_{today.strftime('%Y%m%d')}_{ts}.db.bak"

    try:
        shutil.copy2(str(src), str(dest))
        actual_size = dest.stat().st_size
        if actual_size < MIN_BACKUP_SIZE_BYTES:
            dest.unlink(missing_ok=True)
            _log(f"[backup] FAIL — copied file too small ({actual_size} bytes)")
            return None
        _log(f"[backup] Created: {dest.name} ({actual_size:,} bytes) ✓")
        _rotate_backups()
        return dest
    except Exception as exc:
        _log(f"[backup] ERROR — {exc}")
        return None


def _rotate_backups() -> None:
    """Delete oldest backups beyond BACKUP_KEEP_N."""
    baks = sorted(BACKUP_DIR.glob("platform_*.db.bak"))
    to_delete = baks[:-BACKUP_KEEP_N] if len(baks) > BACKUP_KEEP_N else []
    for f in to_delete:
        f.unlink(missing_ok=True)
        _log(f"[backup] Rotated out: {f.name}")


def list_backups() -> list:
    if not BACKUP_DIR.exists():
        return []
    baks = sorted(BACKUP_DIR.glob("platform_*.db.bak"))
    return [{"name": b.name, "size": b.stat().st_size, "mtime": b.stat().st_mtime} for b in baks]


# ── Sub-process runners ───────────────────────────────────────────────────────

def _run_backfill(execute: bool) -> dict:
    """
    Run backfill_daily_prices.py as a subprocess.
    Returns {"exit_code": int, "stdout": str, "stderr": str}.
    """
    cmd = [PYTHON, str(SCRIPTS_DIR / "backfill_daily_prices.py")]
    if execute:
        cmd.append("--execute")

    _log(f"[backfill] Running: {' '.join(cmd[-2:])}")
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(SCRIPTS_DIR.parent))
    if result.returncode != 0:
        _log(f"[backfill] FAILED (exit={result.returncode})")
        if result.stderr:
            _log(f"[backfill] stderr: {result.stderr[:500]}")
    else:
        # Print last N lines of stdout (progress summary)
        lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
        for line in lines[-8:]:
            _log(f"[backfill] {line}")
        _log("[backfill] Done (exit=0) ✓")

    return {"exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


def _run_shadow() -> dict:
    """
    Run run_hybrid_forward_shadow.py for today.
    Returns {"exit_code": int, "stdout": str, "stderr": str}.
    """
    cmd = [PYTHON, str(SCRIPTS_DIR / "run_hybrid_forward_shadow.py")]
    _log(f"[shadow] Running: {cmd[-1].split('/')[-1]}")
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(SCRIPTS_DIR.parent))
    if result.returncode != 0:
        _log(f"[shadow] FAILED (exit={result.returncode})")
        if result.stderr:
            _log(f"[shadow] stderr: {result.stderr[:500]}")
    else:
        lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
        for line in lines[-10:]:
            _log(f"[shadow] {line}")
        _log("[shadow] Done (exit=0) ✓")
    return {"exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


# ── Main pipeline ─────────────────────────────────────────────────────────────

def run_cron_pipeline(execute: bool = False, skip_backup: bool = False) -> dict:
    """
    Full daily cron pipeline.

    Steps (all skipped in dry-run unless execute=True):
      1. Acquire file lock
      2. Taiwan time + calendar check
      3. Data readiness check (>= 15:30 Taiwan)
      4. Backfill DailyPrice (dry-run or execute)
      5. Create DB backup (if execute and backfill succeeded)
      6. Run shadow runner (if execute and backfill succeeded)
      7. Save state, release lock

    Returns a summary dict with keys: status, steps, today, taiwan_time, etc.
    """
    today = date.today()
    now_taiwan = _now_taipei()
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    result: dict = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "today": str(today),
        "taiwan_time": now_taiwan.strftime("%Y-%m-%dT%H:%M:%S %Z"),
        "execute": execute,
        "steps": {},
        "status": "UNKNOWN",
    }

    _log("=" * 60)
    _log(f"Hybrid Shadow Cron — {'EXECUTE' if execute else 'DRY-RUN'}")
    _log(f"Taiwan time: {now_taiwan.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    _log("=" * 60)

    # ── Step 1: File lock ─────────────────────────────────────────────────────
    lock = FileLock(LOCK_FILE)
    if not lock.acquire():
        _log("[cron] BLOCKED — another cron instance already running (lock held)")
        result["status"] = "BLOCKED_LOCK"
        result["steps"]["lock"] = "blocked"
        return result

    result["steps"]["lock"] = "acquired"

    try:
        # ── Step 2: Calendar check ────────────────────────────────────────────
        if not CALENDAR.is_trading_day(today):
            _log(f"[cron] {today} is not a trading day — exiting cleanly")
            result["status"] = "SKIPPED_NON_TRADING_DAY"
            result["steps"]["calendar"] = "non_trading"
            _save_state(result)
            return result

        result["steps"]["calendar"] = "trading_day"
        _log(f"[cron] {today} is a trading day ✓")

        # ── Step 3: Data readiness check ──────────────────────────────────────
        data_ready = _is_data_ready(now_taiwan)
        result["steps"]["data_ready"] = data_ready
        if not data_ready:
            _log(
                f"[cron] Data NOT ready yet — Taiwan time {now_taiwan.strftime('%H:%M')} "
                f"< {DATA_READY_HOUR:02d}:{DATA_READY_MINUTE:02d} (TWSE/TPEx close at 13:30, data published ~15:30)"
            )
            if execute:
                _log("[cron] WARN — running --execute before data ready; backfill QG-5 will block wrong-date writes")
            else:
                result["status"] = "DATA_NOT_READY"
                _save_state(result)
                return result

        # ── Step 4: Backfill ──────────────────────────────────────────────────
        backfill_result = _run_backfill(execute=execute)
        result["steps"]["backfill"] = {
            "exit_code": backfill_result["exit_code"],
            "executed": execute,
        }
        if backfill_result["exit_code"] != 0:
            _log("[cron] Backfill FAILED — aborting pipeline")
            result["status"] = "BACKFILL_FAILED"
            _save_state(result)
            return result

        if not execute:
            _log("[cron] DRY-RUN complete — backfill checked, no writes. Add --execute to run for real.")
            result["status"] = "DRY_RUN_OK"
            _save_state(result)
            return result

        # ── Step 4b: Fail-closed data freshness verification ─────────────────
        # backfill returning exit_code=0 does NOT guarantee today's data was written.
        # QG-5 may block a wrong-date API response with exit_code=0 and 0 rows written.
        # FAIL-CLOSED: if today's data is not in DB, abort — do NOT run shadow runner.
        # This prevents generating PROSPECTIVE decisions with stale input_data_as_of.
        last_date_post_backfill = _get_db_last_date()
        if last_date_post_backfill != today:
            _log(
                f"[cron] BLOCKED_STALE_DATA — backfill did not update DB to today ({today}). "
                f"last_data_date={last_date_post_backfill}. "
                f"Possible causes: data not yet published (try after 15:30), "
                f"QG-5 blocked wrong-date API response, or API unavailable. "
                f"Aborting shadow runner — no PROSPECTIVE decision will be generated."
            )
            result["status"] = "BLOCKED_STALE_DATA"
            result["steps"]["data_freshness"] = f"STALE: last={last_date_post_backfill}"
            _save_state(result)
            return result
        result["steps"]["data_freshness"] = "OK"
        _log(f"[cron] Data freshness verified: last_data_date={last_date_post_backfill} ✓")

        # ── Step 5: Backup ────────────────────────────────────────────────────
        if skip_backup:
            _log("[cron] Backup SKIPPED (--no-backup flag)")
            result["steps"]["backup"] = "skipped"
        else:
            backup_path = create_backup(str(DB_PATH), today)
            if backup_path is None:
                _log("[cron] Backup FAILED — continuing anyway (shadow will still run)")
                result["steps"]["backup"] = "failed"
            else:
                result["steps"]["backup"] = str(backup_path.name)

        # ── Step 6: Shadow runner ─────────────────────────────────────────────
        shadow_result = _run_shadow()
        result["steps"]["shadow"] = {
            "exit_code": shadow_result["exit_code"],
        }

        # Parse final DB state
        last_date = _get_db_last_date()
        result["last_data_date"] = str(last_date) if last_date else None

        if shadow_result["exit_code"] != 0:
            _log("[cron] Shadow runner FAILED")
            result["status"] = "SHADOW_FAILED"
        else:
            result["status"] = "SUCCESS"
            _log("[cron] Pipeline SUCCESS ✓")

    finally:
        lock.release()
        result["steps"]["lock"] = "released"
        _save_state(result)

    return result


# ── Status command ─────────────────────────────────────────────────────────────

def print_status() -> None:
    """Print last cron run state and backup inventory."""
    state = _load_state()
    if state:
        print("\n── Last Cron Run ─────────────────────────────────────────────")
        print(f"  run_at:        {state.get('run_at', 'unknown')}")
        print(f"  today:         {state.get('today', '?')}")
        print(f"  taiwan_time:   {state.get('taiwan_time', '?')}")
        print(f"  status:        {state.get('status', '?')}")
        print(f"  execute:       {state.get('execute', '?')}")
        steps = state.get("steps", {})
        for k, v in steps.items():
            print(f"  step[{k}]:      {v}")
        if "last_data_date" in state:
            print(f"  last_data_date: {state['last_data_date']}")
    else:
        print("No cron state found — cron has never run with --execute.")

    print("\n── DB DailyPrice Status ──────────────────────────────────────")
    last = _get_db_last_date()
    today = date.today()
    if last:
        gap = (today - last).days
        status_icon = "✓" if gap <= 1 else ("⚠" if gap <= 7 else "✗")
        print(f"  last_data_date: {last} ({status_icon} gap={gap} days)")
    else:
        print("  last_data_date: None (no DailyPrice data)")

    print("\n── Backups ───────────────────────────────────────────────────")
    baks = list_backups()
    if baks:
        for b in baks[-5:]:
            sz = b["size"] / 1_048_576
            print(f"  {b['name']}  ({sz:.1f} MB)")
        if len(baks) > 5:
            print(f"  ... and {len(baks)-5} older backup(s)")
    else:
        print("  No backups found in data/backups/")

    print("\n── Recommended Crontab ───────────────────────────────────────")
    proj_dir = str(Path(__file__).parent.parent.resolve())
    py = sys.executable
    print("  # Taiwan 16:00 = UTC 08:00; Mon–Fri")
    print(f"  0 8 * * 1-5  {py} {proj_dir}/scripts/hybrid_shadow_cron.py --execute >> {proj_dir}/logs/cron.log 2>&1")


# ── CLI ────────────────────────────────────────────────────────────────────────

def _cli() -> None:
    parser = argparse.ArgumentParser(
        description="Daily automation wrapper for Hybrid Forward Shadow"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually write data and run shadow runner (default: dry-run only)",
    )
    parser.add_argument(
        "--no-backup",
        dest="skip_backup",
        action="store_true",
        help="Skip DB backup before shadow run (for testing only)",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Print last run status and backup inventory, then exit",
    )
    args = parser.parse_args()

    if args.status:
        print_status()
        sys.exit(0)

    result = run_cron_pipeline(execute=args.execute, skip_backup=args.skip_backup)

    # BLOCKED_* statuses are expected/intentional; use exit_code=0 so cron doesn't alert.
    # FAILED_* and SHADOW_FAILED use exit_code=1 to trigger cron failure notifications.
    clean_statuses = {
        "SUCCESS", "DRY_RUN_OK", "SKIPPED_NON_TRADING_DAY", "DATA_NOT_READY",
        "BLOCKED_STALE_DATA", "BLOCKED_LOCK",
    }
    exit_code = 0 if result["status"] in clean_statuses else 1
    sys.exit(exit_code)


if __name__ == "__main__":
    _cli()
