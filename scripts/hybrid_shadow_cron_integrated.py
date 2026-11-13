"""
scripts/hybrid_shadow_cron_integrated.py — Session 71K Integration Candidate

ISOLATION NOTE (Session 71K):
  This is the deployment candidate for Session 71K.
  It is NOT the file that production cron currently points to.
  Production cron uses: scripts/hybrid_shadow_cron.py (SHA: 46209171...)

  This file will ONLY become production when explicitly authorized.
  Deployment diff: rename this file to hybrid_shadow_cron.py after hash verification.

  Changes from hybrid_shadow_cron.py (SHA 46209171...):
    1. Import scheduler_safety_guards (new module from Session 71J)
    2. Add Execution Validity Window guard (before lock acquisition)
    3. Add Same-day State Guard (after lock acquisition)
    4. Write RUNNING state before backfill
    5. Write WRITE_COMMITTED state after FULL_MARKET_FRESH confirmed
    6. Write SUCCESS/QG_BLOCKED/PROVIDER_FAILED states at pipeline end
    7. Make _save_state() atomic (os.replace on tmp file)
    8. Add _now_taipei_override / _state_file_override / _lock_file_override
       injection parameters for testability (no-op in production: pass None)

  Zero changes to:
    - QG-1 ~ QG-7 logic
    - RC-2 filter
    - Provider call structure
    - SQLite write location
    - Shadow runner logic
    - Trading calendar logic
    - Backup logic
    - Exit code policy
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
import time as _time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pytz

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import DB_PATH
from src.core.trading_calendar import TaiwanTradingCalendar
from src.research.full_market_freshness_gate import (
    FreshnessStatus,
    check_market_freshness,
)
from src.research.alert_state import AlertStateManager

from scripts.scheduler_safety_guards import (
    GuardStatus,
    RunState,
    RunStatus,
    SameDayStateGuard,
    check_execution_window,
    make_run_id,
)

# ── Constants ──────────────────────────────────────────────────────────────────

TAIWAN_TZ = pytz.timezone("Asia/Taipei")
DATA_READY_HOUR = 15
DATA_READY_MINUTE = 30

LOCK_FILE = Path(__file__).parent.parent / "data" / ".cron.lock"
BACKUP_DIR = Path(__file__).parent.parent / "data" / "backups"
LOG_DIR = Path(__file__).parent.parent / "logs"
STATE_FILE = Path(__file__).parent.parent / "data" / ".cron_state.json"

BACKUP_KEEP_N = 7
MIN_BACKUP_SIZE_BYTES = 100_000

SCRIPTS_DIR = Path(__file__).parent
PYTHON = sys.executable
CALENDAR = TaiwanTradingCalendar()

RETRY_MAX = 3
RETRY_INTERVAL_MINUTES = 30
_RETRYABLE_STATUSES = frozenset({
    FreshnessStatus.BENCHMARK_ONLY_UPDATED,
    FreshnessStatus.PARTIAL_MARKET_UPDATE,
    FreshnessStatus.PROVIDER_NOT_READY,
})


# ── Helpers ────────────────────────────────────────────────────────────────────

def _now_taipei() -> datetime:
    return datetime.now(TAIWAN_TZ)


def _is_data_ready(now_taipei: Optional[datetime] = None) -> bool:
    if now_taipei is None:
        now_taipei = _now_taipei()
    t = now_taipei.time()
    return (t.hour, t.minute) >= (DATA_READY_HOUR, DATA_READY_MINUTE)


def _get_db_last_date(db_path: Optional[str] = None) -> Optional[date]:
    path = db_path or str(DB_PATH)
    if not os.path.isfile(path):
        return None
    try:
        conn = sqlite3.connect(path)
        row = conn.execute(
            "SELECT MAX(date) FROM daily_prices WHERE stock_id='0050'"
        ).fetchone()
        conn.close()
        return date.fromisoformat(row[0]) if row and row[0] else None
    except Exception:
        return None


def _load_state(state_file: Optional[Path] = None) -> dict:
    path = state_file or STATE_FILE
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return {}


def _save_state(state: dict, state_file: Optional[Path] = None) -> None:
    """Atomic write: write to .tmp then os.replace to target."""
    path = state_file or STATE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    # Strip secrets before persisting (defensive)
    safe = {k: v for k, v in state.items()
            if k not in ("database_url", "api_key", "password", "secret")}
    tmp.write_text(json.dumps(safe, indent=2, default=str))
    os.replace(tmp, path)


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"[{ts}] {msg}"
    print(line, flush=True)


def _alert(trade_date: date, alert_type: str, message: str) -> None:
    try:
        mgr = AlertStateManager()
        is_new = mgr.record(trade_date, alert_type, message)
        _log(f"[alert] {'NEW' if is_new else 'DUP'} {alert_type} on {trade_date}: {message}")
    except Exception as exc:
        _log(f"[alert] ERROR recording {alert_type}: {exc}")


# ── File lock ──────────────────────────────────────────────────────────────────

class FileLock:
    """Non-blocking exclusive file lock using fcntl.flock (macOS/Linux)."""

    def __init__(self, path: Path):
        self._path = path
        self._fd: Optional[int] = None

    def acquire(self) -> bool:
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


# ── Backup ─────────────────────────────────────────────────────────────────────

def create_backup(db_path: str, today: date) -> Optional[Path]:
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


# ── Sub-process runners ────────────────────────────────────────────────────────

def _run_backfill(execute: bool, scripts_dir: Optional[Path] = None) -> dict:
    sd = scripts_dir or SCRIPTS_DIR
    # Prefer guarded (S71M lock-based) → protected (S71L env-var) → base (advisory only).
    # All set CALLED_FROM_WRAPPER=1; guarded also verifies lock is held.
    guarded = sd / "backfill_daily_prices_guarded.py"
    protected = sd / "backfill_daily_prices_protected.py"
    base = sd / "backfill_daily_prices.py"
    target_script = guarded if guarded.exists() else (protected if protected.exists() else base)
    cmd = [PYTHON, str(target_script)]
    if execute:
        cmd.append("--execute")
    env = {**os.environ, "CALLED_FROM_WRAPPER": "1"}
    _log(f"[backfill] Running: {target_script.name}" + (" --execute" if execute else "") + f" (lock+env authorized)")
    result = subprocess.run(cmd, capture_output=True, text=True,
                            cwd=str(sd.parent), env=env)
    if result.returncode != 0:
        _log(f"[backfill] FAILED (exit={result.returncode})")
        if result.stderr:
            _log(f"[backfill] stderr: {result.stderr[:500]}")
    else:
        lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
        for line in lines[-8:]:
            _log(f"[backfill] {line}")
        _log("[backfill] Done (exit=0) ✓")
    return {"exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


def _run_shadow(scripts_dir: Optional[Path] = None) -> dict:
    sd = scripts_dir or SCRIPTS_DIR
    cmd = [PYTHON, str(sd / "run_hybrid_forward_shadow.py")]
    _log(f"[shadow] Running: {cmd[-1].split('/')[-1]}")
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(sd.parent))
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


# ── Main pipeline ──────────────────────────────────────────────────────────────

def run_cron_pipeline(
    execute: bool = False,
    skip_backup: bool = False,
    # Clock + path injection for testing (pass None to use production defaults)
    _now_taipei_override: Optional[datetime] = None,
    _state_file_override: Optional[Path] = None,
    _lock_file_override: Optional[Path] = None,
    _db_path_override: Optional[str] = None,
    _backfill_runner: Optional[object] = None,   # callable(execute) -> dict
    _shadow_runner: Optional[object] = None,      # callable() -> dict
    _freshness_checker: Optional[object] = None,  # callable(conn, date, is_trading_day) -> report
) -> dict:
    """
    Full daily cron pipeline with Scheduler Safety Guards.

    Steps:
      0a. Execution Validity Window guard (16:00–20:00 CST)
       1. Acquire file lock
      1b. Same-day State Guard (read + check)
      1c. Mark RUNNING in state file
       2. Taiwan time + calendar check
       3. Data readiness check (>= 15:30 Taiwan)
       4. Backfill DailyPrice
      4b. Full-market freshness verification (with retry)
      4c. Mark WRITE_COMMITTED after freshness FULL_MARKET_FRESH
       5. Create DB backup
       6. Run shadow runner
       7. Mark SUCCESS, release lock

    Injection parameters (_*_override) are for offline testing ONLY.
    Pass None (default) for all production runs.
    """
    effective_state_file = _state_file_override or STATE_FILE
    effective_lock_file  = _lock_file_override or LOCK_FILE
    effective_db_path    = _db_path_override or str(DB_PATH)

    today = date.today()
    now_taiwan = _now_taipei_override or _now_taipei()
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
    _log(f"Hybrid Shadow Cron (Integrated) — {'EXECUTE' if execute else 'DRY-RUN'}")
    _log(f"Taiwan time: {now_taiwan.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    _log("=" * 60)

    # ── Step 0a: Execution Validity Window guard ───────────────────────────────
    # Rejects execution outside 16:00–20:00 CST to prevent cross-day catch-up.
    # Runs BEFORE lock acquisition — no lock taken if window rejected.
    window = check_execution_window(now_taipei=now_taiwan)
    result["steps"]["execution_window"] = window.guard_status.value
    result["scheduled_date"] = str(window.scheduled_date)

    if not window.allowed:
        _log(f"[guard/window] REJECTED: {window.reason}")
        result["status"] = f"GUARD_WINDOW_{window.guard_status.value}"
        # Do NOT save state on window reject (prevents polluting state with rejected run)
        return result

    _log(f"[guard/window] ALLOWED: {window.reason}")

    # ── Step 1: File lock ──────────────────────────────────────────────────────
    lock = FileLock(effective_lock_file)
    if not lock.acquire():
        _log("[cron] BLOCKED — another cron instance already running (lock held)")
        result["status"] = "BLOCKED_LOCK"
        result["steps"]["lock"] = "blocked"
        return result

    result["steps"]["lock"] = "acquired"

    # Initialise guard with the effective state file path
    state_guard = SameDayStateGuard(effective_state_file)
    run_id = make_run_id(window.scheduled_date)

    try:
        # ── Step 1b: Same-day State Guard ────────────────────────────────────
        guard_check = state_guard.check(window.scheduled_date)
        result["steps"]["same_day_guard"] = guard_check.guard_status.value
        result["guard_run_id"] = guard_check.prior_run_id

        if not guard_check.allowed:
            _log(f"[guard/state] REJECTED: {guard_check.reason}")
            result["status"] = f"GUARD_STATE_{guard_check.guard_status.value}"
            return result

        _log(f"[guard/state] ALLOWED: {guard_check.reason}")

        # ── Step 1c: Mark RUNNING ─────────────────────────────────────────────
        # Merge guard state into the existing result dict before first save.
        run_state = RunState(
            run_id=run_id,
            scheduled_date=str(window.scheduled_date),
            actual_start_utc=datetime.now(timezone.utc).isoformat(),
            pid=os.getpid(),
            status=RunStatus.RUNNING.value,
            guard_decision=GuardStatus.ALLOWED.value,
            write_committed=False,
        )
        result.update({
            "run_id": run_state.run_id,
            "scheduled_date": run_state.scheduled_date,
            "schema_version": run_state.schema_version,
            "pid": run_state.pid,
            "status": RunStatus.RUNNING.value,
            "write_committed": False,
        })
        _save_state(result, effective_state_file)
        _log(f"[guard/state] Marked RUNNING (run_id={run_id})")

        # ── Step 2: Calendar check ────────────────────────────────────────────
        if not CALENDAR.is_trading_day(today):
            _log(f"[cron] {today} is not a trading day — exiting cleanly")
            result["status"] = "SKIPPED_NON_TRADING_DAY"
            result["steps"]["calendar"] = "non_trading"
            _save_state(result, effective_state_file)
            return result

        result["steps"]["calendar"] = "trading_day"
        _log(f"[cron] {today} is a trading day ✓")

        # ── Step 3: Data readiness check ──────────────────────────────────────
        data_ready = _is_data_ready(now_taiwan)
        result["steps"]["data_ready"] = data_ready
        if not data_ready:
            _log(
                f"[cron] Data NOT ready yet — Taiwan time {now_taiwan.strftime('%H:%M')} "
                f"< {DATA_READY_HOUR:02d}:{DATA_READY_MINUTE:02d}"
            )
            if execute:
                _log("[cron] WARN — running --execute before data ready; QG-5 will block wrong-date writes")
            else:
                result["status"] = "DATA_NOT_READY"
                _save_state(result, effective_state_file)
                return result

        # ── Step 4: Backfill ──────────────────────────────────────────────────
        if _backfill_runner is not None:
            backfill_result = _backfill_runner(execute)
        else:
            backfill_result = _run_backfill(execute=execute)

        result["steps"]["backfill"] = {
            "exit_code": backfill_result["exit_code"],
            "executed": execute,
        }
        if backfill_result["exit_code"] != 0:
            _log("[cron] Backfill FAILED — aborting pipeline")
            result["status"] = "BACKFILL_FAILED"
            _alert(today, "STALE_DATA",
                   f"backfill_daily_prices.py failed (exit={backfill_result['exit_code']}) on {today}")
            _save_state(result, effective_state_file)
            return result

        if not execute:
            _log("[cron] DRY-RUN complete — backfill checked, no writes. Add --execute to run for real.")
            result["status"] = "DRY_RUN_OK"
            _save_state(result, effective_state_file)
            return result

        # ── Step 4b: Full-market freshness verification (with retry) ─────────
        for _retry_attempt in range(RETRY_MAX + 1):
            if _freshness_checker is not None:
                db_conn_check = None
                freshness_report = _freshness_checker(db_conn_check, today, is_trading_day=True)
            else:
                db_conn_check = sqlite3.connect(effective_db_path)
                freshness_report = check_market_freshness(
                    db_conn_check, today, is_trading_day=True
                )
                db_conn_check.close()

            freshness_status = freshness_report.status
            result["steps"]["data_freshness"] = freshness_status.value
            result["steps"]["data_freshness_detail"] = freshness_report.detail
            result["steps"]["freshness_retry_attempt"] = _retry_attempt

            if freshness_status == FreshnessStatus.FULL_MARKET_FRESH:
                _log(
                    f"[cron] Full-market freshness PASS: "
                    f"{freshness_report.non_benchmark_count:,} non-0050 stocks on {today} ✓"
                    + (f" (retry {_retry_attempt})" if _retry_attempt > 0 else "")
                )
                # ── Step 4c: Mark WRITE_COMMITTED ───────────────────────────
                # Data confirmed written to SQLite. Even if shadow fails, block re-write.
                result["write_committed"] = True
                _save_state(result, effective_state_file)
                _log(f"[guard/state] Marked WRITE_COMMITTED (run_id={run_id})")
                break

            if freshness_status in _RETRYABLE_STATUSES and _retry_attempt < RETRY_MAX:
                _log(
                    f"[cron] {freshness_status.value} — retry {_retry_attempt + 1}/{RETRY_MAX} "
                    f"in {RETRY_INTERVAL_MINUTES}m. {freshness_report.detail}"
                )
                result["steps"]["freshness_retry_attempt"] = _retry_attempt + 1
                _save_state(result, effective_state_file)
                _time.sleep(RETRY_INTERVAL_MINUTES * 60)
                if execute:
                    _log(f"[cron] Retry {_retry_attempt + 1}: re-running backfill")
                    if _backfill_runner is not None:
                        _backfill_runner(True)
                    else:
                        _run_backfill(execute=True)
                continue

            if freshness_status in (
                FreshnessStatus.STALE, FreshnessStatus.PROVIDER_NOT_READY
            ):
                retry_note = f" (after {_retry_attempt} retries)" if _retry_attempt > 0 else ""
                _log(f"[cron] BLOCKED_STALE_DATA{retry_note}")
                result["status"] = "BLOCKED_STALE_DATA"
                _alert(today, "STALE_DATA", f"{freshness_status.value}: {freshness_report.detail}")
            elif freshness_status in (
                FreshnessStatus.BENCHMARK_ONLY_UPDATED, FreshnessStatus.PARTIAL_MARKET_UPDATE
            ):
                _log(f"[cron] BLOCKED_PARTIAL_MARKET (after {_retry_attempt} retries)")
                result["status"] = "BLOCKED_PARTIAL_MARKET"
                _alert(today, "PARTIAL_MARKET",
                       f"{freshness_status.value} after {_retry_attempt} retries on {today}")
            else:
                _log(f"[cron] BLOCKED_STALE_DATA — freshness unknown: {freshness_report.detail}")
                result["status"] = "BLOCKED_STALE_DATA"
                _alert(today, "STALE_DATA", f"UNKNOWN freshness: {freshness_report.detail}")
            _save_state(result, effective_state_file)
            return result

        # ── Step 5: Backup ────────────────────────────────────────────────────
        if skip_backup:
            _log("[cron] Backup SKIPPED (--no-backup flag)")
            result["steps"]["backup"] = "skipped"
        else:
            backup_path = create_backup(effective_db_path, today)
            if backup_path is None:
                _log("[cron] Backup FAILED — continuing anyway")
                result["steps"]["backup"] = "failed"
                _alert(today, "BACKUP_FAILURE", f"create_backup returned None on {today}")
            else:
                result["steps"]["backup"] = str(backup_path.name)

        # ── Step 6: Shadow runner ─────────────────────────────────────────────
        if _shadow_runner is not None:
            shadow_result = _shadow_runner()
        else:
            shadow_result = _run_shadow()

        result["steps"]["shadow"] = {"exit_code": shadow_result["exit_code"]}

        last_date = _get_db_last_date(effective_db_path)
        result["last_data_date"] = str(last_date) if last_date else None

        if shadow_result["exit_code"] != 0:
            _log("[cron] Shadow runner FAILED")
            result["status"] = "SHADOW_FAILED"
            # write_committed=True is already in result — SQLite data IS written
            # Shadow failure does NOT allow re-write of daily prices
            _alert(today, "SHADOW_FAILED",
                   f"run_hybrid_forward_shadow.py exit={shadow_result['exit_code']} on {today}")
        else:
            result["status"] = "SUCCESS"
            _log("[cron] Pipeline SUCCESS ✓")

    finally:
        lock.release()
        result["steps"]["lock"] = "released"
        _save_state(result, effective_state_file)

    return result


# ── Missed run detection (unchanged from production) ──────────────────────────

def _detect_missed_runs(state: dict) -> dict:
    today = date.today()
    result: dict = {
        "today": str(today),
        "last_execute_date": None,
        "missed_dates": [],
        "trading_days_since_last_run": 0,
        "alert": False,
    }
    last_execute_date: Optional[date] = None
    try:
        conn = sqlite3.connect(str(DB_PATH))
        row = conn.execute(
            "SELECT MAX(trade_date) FROM hybrid_forward_run_log "
            "WHERE status IN ('SUCCESS','BLOCKED_MISSING_SIGNALS','BLOCKED_STALE_DATA')"
        ).fetchone()
        conn.close()
        if row and row[0]:
            last_execute_date = date.fromisoformat(row[0])
    except Exception:
        pass
    if last_execute_date is None and state.get("execute") and state.get("today"):
        try:
            last_execute_date = date.fromisoformat(state["today"])
        except (ValueError, TypeError):
            pass
    if last_execute_date is None:
        return result
    result["last_execute_date"] = str(last_execute_date)
    missed: list[date] = []
    d = last_execute_date + timedelta(days=1)
    while d < today:
        if CALENDAR.is_trading_day(d):
            missed.append(d)
        d += timedelta(days=1)
    result["missed_dates"] = [str(x) for x in missed]
    result["trading_days_since_last_run"] = len(missed)
    result["alert"] = len(missed) > 0
    return result


# ── Status / CLI (unchanged from production) ──────────────────────────────────

def print_status() -> None:
    state = _load_state()
    if state:
        print("\n── Last Cron Run ─────────────────────────────────────────────")
        for k in ("run_at", "today", "taiwan_time", "status", "execute", "run_id", "write_committed"):
            if k in state:
                print(f"  {k}: {state[k]}")
        steps = state.get("steps", {})
        for k, v in steps.items():
            print(f"  step[{k}]: {v}")
    else:
        print("No cron state found.")

    print("\n── DB DailyPrice Status ──────────────────────────────────────")
    last = _get_db_last_date()
    today = date.today()
    if last:
        gap = (today - last).days
        icon = "✓" if gap <= 1 else ("⚠" if gap <= 7 else "✗")
        print(f"  last_data_date: {last} ({icon} gap={gap} days)")
    else:
        print("  last_data_date: None")


def _cli() -> None:
    parser = argparse.ArgumentParser(
        description="Daily automation wrapper for Hybrid Forward Shadow (Integrated)"
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--no-backup", dest="skip_backup", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--check-missed", dest="check_missed", action="store_true")
    args = parser.parse_args()

    if args.status:
        print_status()
        sys.exit(0)

    if args.check_missed:
        state = _load_state()
        from scripts.hybrid_shadow_cron import _print_missed_runs
        _print_missed_runs(state)
        sys.exit(0)

    trigger_source = "manual" if sys.stdout.isatty() else "cron_scheduled"

    result = run_cron_pipeline(execute=args.execute, skip_backup=args.skip_backup)

    clean_statuses = {
        "SUCCESS", "DRY_RUN_OK", "SKIPPED_NON_TRADING_DAY", "DATA_NOT_READY",
        "BLOCKED_STALE_DATA", "BLOCKED_LOCK", "BLOCKED_PARTIAL_MARKET",
        "SKIPPED_NON_TRADING_DAY",
    }
    # Guard rejections are clean exits (not pipeline failures)
    if result["status"].startswith("GUARD_"):
        clean_statuses.add(result["status"])

    exit_code = 0 if result["status"] in clean_statuses else 1
    result["exit_code"] = exit_code
    result["trigger_source"] = trigger_source
    _save_state(result)

    sys.exit(exit_code)


if __name__ == "__main__":
    _cli()
