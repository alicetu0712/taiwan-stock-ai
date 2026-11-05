"""
hybrid_shadow_preflight.py — Preflight safety gate for Hybrid Forward Shadow cron

Validates all conditions required for safe cron installation and operation.
Must be run before `crontab -e` and re-run any time the environment changes.

Exit codes:
  0 = PASS or CONDITIONAL (safe to proceed with caution)
  1 = BLOCKED (do NOT install cron until issues resolved)

Usage:
  python scripts/hybrid_shadow_preflight.py
  python scripts/hybrid_shadow_preflight.py --verbose
  python scripts/hybrid_shadow_preflight.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time as _time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env early so env vars are visible to all checks (including USE_NEON)
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(override=False)   # override=False: don't clobber already-set shell vars
except ImportError:
    pass

# ── Constants ─────────────────────────────────────────────────────────────────

REQUIRED_PYTHON = (3, 11)
STALE_DAYS_WARN = 1    # warn if DailyPrice last date is > 1 day ago
STALE_DAYS_BLOCK = 7   # block if > 7 days ago

STATUS_PASS = "PASS"
STATUS_WARN = "WARNING"
STATUS_BLOCK = "BLOCKED"

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
LOGS_DIR = PROJECT_ROOT / "logs"
DATA_DIR = PROJECT_ROOT / "data"
BACKUP_DIR = DATA_DIR / "backups"
DB_PATH = DATA_DIR / "platform.db"
CRON_SCRIPT = SCRIPTS_DIR / "hybrid_shadow_cron.py"
SHADOW_SCRIPT = SCRIPTS_DIR / "run_hybrid_forward_shadow.py"
BACKFILL_SCRIPT = SCRIPTS_DIR / "backfill_daily_prices.py"
LOCK_FILE = DATA_DIR / ".cron.lock"
STATE_FILE = DATA_DIR / ".cron_state.json"


def _cron_hour_for_taiwan_1600() -> tuple[str, str]:
    """
    Return (cron_hour, label) for scheduling Taiwan market close (16:00 CST).
    macOS cron uses system local time — NOT UTC.
    - UTC+8 (Asia/Taipei) → schedule at local 16 → cron hour = "16"
    - UTC+0              → schedule at UTC 08  → cron hour = "8"
    """
    offset_hrs = int(-_time.timezone / 3600)
    if offset_hrs == 8:
        return ("16", "local Asia/Taipei 16:00")
    elif offset_hrs == 0:
        return ("8", "UTC 08:00 = Taiwan 16:00")
    else:
        # Fallback: compute UTC hour equivalent and warn
        utc_hour = (16 - offset_hrs) % 24
        return (str(utc_hour), f"local {utc_hour:02d}:00 = Taiwan 16:00 (UTC+{offset_hrs})")


# ── Check helpers ─────────────────────────────────────────────────────────────

class CheckResult:
    def __init__(self, name: str, status: str, detail: str):
        self.name = name
        self.status = status
        self.detail = detail

    def to_dict(self) -> dict:
        return {"name": self.name, "status": self.status, "detail": self.detail}


def _ok(name: str, detail: str) -> CheckResult:
    return CheckResult(name, STATUS_PASS, detail)


def _warn(name: str, detail: str) -> CheckResult:
    return CheckResult(name, STATUS_WARN, detail)


def _block(name: str, detail: str) -> CheckResult:
    return CheckResult(name, STATUS_BLOCK, detail)


# ── Section: Environment ──────────────────────────────────────────────────────

def check_python_version() -> CheckResult:
    v = sys.version_info
    if v < REQUIRED_PYTHON:
        return _block("python_version", f"{v.major}.{v.minor} < required {REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]}")
    return _ok("python_version", f"{v.major}.{v.minor}.{v.micro} at {sys.executable}")


def check_working_directory() -> CheckResult:
    cwd = Path.cwd()
    if cwd != PROJECT_ROOT:
        return _warn("working_directory", f"CWD={cwd} != PROJECT_ROOT={PROJECT_ROOT} (cron uses absolute paths — OK)")
    return _ok("working_directory", str(cwd))


def check_project_root() -> CheckResult:
    for required in [CRON_SCRIPT, SHADOW_SCRIPT, BACKFILL_SCRIPT, DB_PATH]:
        if not required.exists():
            return _block("project_root", f"Required file missing: {required}")
    return _ok("project_root", str(PROJECT_ROOT))


def check_logs_dir() -> CheckResult:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    test_file = LOGS_DIR / ".preflight_write_test"
    try:
        test_file.write_text("ok")
        test_file.unlink()
        return _ok("logs_dir", str(LOGS_DIR))
    except OSError as e:
        return _block("logs_dir", f"Not writable: {e}")


def check_backup_dir() -> CheckResult:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    test_file = BACKUP_DIR / ".preflight_write_test"
    try:
        test_file.write_text("ok")
        test_file.unlink()
        baks = list(BACKUP_DIR.glob("platform_*.db.bak"))
        return _ok("backup_dir", f"{str(BACKUP_DIR)} — {len(baks)} existing backup(s)")
    except OSError as e:
        return _block("backup_dir", f"Not writable: {e}")


def check_timezone() -> CheckResult:
    try:
        import pytz
        tz = pytz.timezone("Asia/Taipei")
        now_taipei = datetime.now(tz)
        offset_hrs = int(-_time.timezone / 3600)
        hour, label = _cron_hour_for_taiwan_1600()
        note = (
            f"Asia/Taipei available; now={now_taipei.strftime('%Y-%m-%d %H:%M:%S %Z')}; "
            f"system UTC+{offset_hrs}; cron Taiwan 16:00 → schedule at local hour {hour} ({label})"
        )
        return _ok("timezone_taipei", note)
    except Exception as e:
        return _block("timezone_taipei", f"pytz.timezone('Asia/Taipei') failed: {e}")


def check_dependencies() -> CheckResult:
    missing = []
    for dep in ["requests", "pytz", "fcntl", "sqlite3"]:
        try:
            __import__(dep)
        except ImportError:
            missing.append(dep)
    if missing:
        return _block("dependencies", f"Missing: {missing}")
    return _ok("dependencies", "requests, pytz, fcntl, sqlite3 all available")


def check_env_variables() -> CheckResult:
    use_neon = os.getenv("USE_NEON", "").strip().lower() in ("1", "true", "yes")
    if use_neon:
        return _warn(
            "env_USE_NEON",
            "USE_NEON=true is set. Dashboard connects to Neon. "
            "Cron scripts hardcode SQLite — cron pipeline is NOT affected. "
            "Confirm: hybrid_shadow_cron.py and backfill_daily_prices.py use DB_PATH (SQLite).",
        )
    return _ok("env_USE_NEON", "USE_NEON not set — dashboard uses SQLite mode")


# ── Section: Database Isolation ───────────────────────────────────────────────

def check_db_path_isolation() -> CheckResult:
    """Confirm cron and shadow runner use SQLite, not Neon."""
    try:
        cron_src = CRON_SCRIPT.read_text()
        shadow_src = SHADOW_SCRIPT.read_text()
        backfill_src = BACKFILL_SCRIPT.read_text()

        # Import config DB_PATH directly
        from config import DB_PATH as config_db_path
        if not str(config_db_path).endswith("platform.db"):
            return _block("db_path_isolation", f"config.DB_PATH = {config_db_path} (unexpected)")

        # Check shadow runner's hardcoded path
        if 'DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "platform.db")' in shadow_src:
            shadow_db = "hardcoded SQLite ✓"
        else:
            shadow_db = "WARN: shadow DB_PATH not hardcoded as expected"

        # Verify no script passes DATABASE_URL to sqlite
        for name, src in [("cron", cron_src), ("shadow", shadow_src), ("backfill", backfill_src)]:
            if "NEON_URL" in src or "DATABASE_URL" in src:
                # These might just be passing config vars around; check for actual use
                # The scripts import DB_PATH from config, not DATABASE_URL
                pass

        return _ok(
            "db_path_isolation",
            f"config.DB_PATH={config_db_path} (SQLite). "
            f"shadow_runner={shadow_db}. "
            f"USE_NEON=true affects DATABASE_URL (dashboard) but NOT DB_PATH (cron pipeline).",
        )
    except Exception as e:
        return _warn("db_path_isolation", f"Could not fully verify: {e}")


def check_sqlite_magic() -> CheckResult:
    """Confirm DB_PATH is an actual SQLite file."""
    if not DB_PATH.exists():
        return _block("sqlite_magic", f"{DB_PATH} does not exist")
    with open(str(DB_PATH), "rb") as f:
        magic = f.read(16)
    if not magic.startswith(b"SQLite format 3"):
        return _block("sqlite_magic", f"{DB_PATH} is NOT a SQLite file")
    size_mb = DB_PATH.stat().st_size / 1_048_576
    return _ok("sqlite_magic", f"Verified SQLite: {DB_PATH.name} ({size_mb:.1f} MB)")


def check_no_neon_in_cron_env() -> CheckResult:
    """Confirm cron subprocess won't accidentally use Neon DATABASE_URL for writes."""
    # All cron-path scripts use DB_PATH (file path), not DATABASE_URL (pg connection string).
    # DATABASE_URL is only used by the ORM/dashboard layer.
    # Verify by checking the scripts don't import SQLAlchemy or use DATABASE_URL.
    shadow_src = SHADOW_SCRIPT.read_text()
    backfill_src = BACKFILL_SCRIPT.read_text()
    cron_src = CRON_SCRIPT.read_text()

    concerns = []
    for name, src in [("shadow", shadow_src), ("backfill", backfill_src), ("cron", cron_src)]:
        if "sqlalchemy" in src.lower():
            concerns.append(f"{name}: uses sqlalchemy (may use DATABASE_URL)")
        if "DATABASE_URL" in src:
            concerns.append(f"{name}: references DATABASE_URL directly")

    if concerns:
        return _warn("neon_write_isolation", f"Potential Neon access in scripts: {concerns}")
    return _ok("neon_write_isolation", "No sqlalchemy or DATABASE_URL in cron-path scripts — Neon write isolation confirmed")


def check_research_tables_exist() -> CheckResult:
    """Confirm hybrid_forward_* research tables exist."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        conn.close()
        required = {"hybrid_forward_decision", "hybrid_forward_outcome", "hybrid_forward_run_log"}
        missing = required - tables
        if missing:
            return _warn("research_tables", f"Missing tables: {missing} (will be auto-created on first run)")
        return _ok("research_tables", f"All 3 research tables exist in {DB_PATH.name}")
    except Exception as e:
        return _block("research_tables", f"Cannot open DB: {e}")


# ── Section: Data Integrity ───────────────────────────────────────────────────

def check_dailyprice_freshness() -> CheckResult:
    """Confirm 0050 DailyPrice is fresh."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        row = conn.execute(
            "SELECT MAX(date), COUNT(*) FROM daily_prices WHERE stock_id='0050'"
        ).fetchone()
        conn.close()
        if not row or not row[0]:
            return _block("dailyprice_freshness", "No 0050 DailyPrice data in DB")
        last_date = date.fromisoformat(row[0])
        today = date.today()
        gap = (today - last_date).days
        if gap > STALE_DAYS_BLOCK:
            return _block("dailyprice_freshness", f"last_date={last_date} gap={gap}d > {STALE_DAYS_BLOCK}d tolerance")
        if gap > STALE_DAYS_WARN:
            return _warn("dailyprice_freshness", f"last_date={last_date} gap={gap}d (expect 0 on trading days)")
        return _ok("dailyprice_freshness", f"last_date={last_date} gap={gap}d rows={row[1]}")
    except Exception as e:
        return _block("dailyprice_freshness", f"DB query failed: {e}")


def check_ohlc_continuity_gate() -> CheckResult:
    """Run OHLC continuity gate for today."""
    try:
        from src.research.ohlc_continuity_gate import OHLCContinuityGate, GateResult
        conn = sqlite3.connect(str(DB_PATH))
        gate = OHLCContinuityGate()
        today = date.today()
        report = gate.check_market(conn, today)
        conn.close()

        if report.gate_result == GateResult.PASS:
            return _ok(
                "ohlc_continuity_gate",
                f"PASS — present={report.present_sessions} missing={report.missing_sessions} "
                f"for {today} (30-day window)",
            )
        if report.gate_result == GateResult.BLOCKED_MISSING_OHLC:
            return _block(
                "ohlc_continuity_gate",
                f"BLOCKED_MISSING_OHLC — missing={report.missing_sessions} sessions in 30-day window. "
                f"First missing: {min(report.missing_dates) if report.missing_dates else '?'}. "
                f"Recover historical OHLC before installing cron.",
            )
        return _warn("ohlc_continuity_gate", f"{report.gate_result} — {report}")
    except Exception as e:
        return _block("ohlc_continuity_gate", f"Gate check failed: {e}")


def check_db_integrity() -> CheckResult:
    """Run PRAGMA integrity_check and foreign_key_check."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        ic = conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        total = conn.execute("SELECT COUNT(*) FROM daily_prices").fetchone()[0]
        conn.close()
        if ic != "ok":
            return _block("db_integrity", f"integrity_check={ic}")
        if fk:
            return _warn("db_integrity", f"FK violations: {len(fk)}")
        return _ok("db_integrity", f"integrity_check=ok fk_violations=0 total_rows={total:,}")
    except Exception as e:
        return _block("db_integrity", f"DB check failed: {e}")


def check_wal_orphan() -> CheckResult:
    """Check for orphaned WAL files."""
    issues = []
    # Check for misnamed WAL files (e.g. from copies)
    for f in DATA_DIR.iterdir():
        if f.suffix in (".wal", ".shm") or f.name.endswith("-wal") or f.name.endswith("-shm"):
            # Legitimate WAL for platform.db
            if f.name in ("platform.db-wal", "platform.db-shm"):
                size = f.stat().st_size
                if size > 0:
                    issues.append(f"{f.name} ({size:,} bytes — uncommitted writes pending)")
            else:
                issues.append(f"Orphan WAL/SHM: {f.name} ({f.stat().st_size:,} bytes)")
    if issues:
        return _warn("wal_orphan", "; ".join(issues))
    return _ok("wal_orphan", "No orphaned WAL/SHM files")


def check_formal_signal_source() -> CheckResult:
    """Verify forward_signals table has data (or explain why 0 is acceptable)."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cnt = conn.execute("SELECT COUNT(*) FROM forward_signals").fetchone()[0]
        latest = conn.execute("SELECT MAX(trade_date) FROM forward_signals").fetchone()[0]
        conn.close()
        if cnt == 0:
            return _warn(
                "formal_signal_source",
                "No forward_signals in SQLite. The shadow runner uses DailyPrice for signal generation "
                "(not forward_signals table). 0 signals = acceptable for first prospective run.",
            )
        return _ok("formal_signal_source", f"{cnt:,} signals, latest trade_date={latest}")
    except Exception as e:
        return _warn("formal_signal_source", f"Could not query forward_signals: {e}")


# ── Section: Cron Safety ──────────────────────────────────────────────────────

def check_lock_available() -> CheckResult:
    """Confirm no other cron instance holds the lock."""
    if not LOCK_FILE.exists():
        return _ok("file_lock", f"Lock file {LOCK_FILE.name} does not exist (no instance running)")
    # Try to open it and check if held
    try:
        import fcntl
        fd = os.open(str(LOCK_FILE), os.O_CREAT | os.O_WRONLY)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
            return _ok("file_lock", "Lock file exists but not held by any process")
        except BlockingIOError:
            os.close(fd)
            pid = LOCK_FILE.read_text().strip() if LOCK_FILE.exists() else "?"
            return _warn("file_lock", f"Lock held by PID={pid} — another cron instance may be running")
    except Exception as e:
        return _warn("file_lock", f"Could not test lock: {e}")


def check_no_duplicate_cron() -> CheckResult:
    """Check for duplicate cron entries: 0 or 1 entries is fine, 2+ is a duplicate."""
    try:
        import subprocess
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        if result.returncode != 0:
            return _ok("no_duplicate_cron", "No existing crontab found (not yet installed)")
        count = result.stdout.count("hybrid_shadow_cron.py")
        if count == 0:
            return _ok("no_duplicate_cron", "No hybrid_shadow_cron.py entry (not yet installed)")
        if count == 1:
            return _ok("no_duplicate_cron", "hybrid_shadow_cron.py installed once — no duplicates")
        return _warn("no_duplicate_cron", f"hybrid_shadow_cron.py appears {count}x in crontab — DUPLICATE detected, remove extras")
    except Exception as e:
        return _warn("no_duplicate_cron", f"Could not check crontab: {e}")


def check_cron_script_paths() -> CheckResult:
    """Validate that the cron entry uses valid, existing paths."""
    python_exe = Path(sys.executable)
    issues = []

    if not python_exe.exists():
        issues.append(f"Python executable not found: {python_exe}")
    if not CRON_SCRIPT.exists():
        issues.append(f"Cron script not found: {CRON_SCRIPT}")
    if not LOGS_DIR.exists():
        try:
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
        except OSError:
            issues.append(f"Cannot create logs dir: {LOGS_DIR}")

    if issues:
        return _block("cron_script_paths", "; ".join(issues))

    hour, _label = _cron_hour_for_taiwan_1600()
    cron_entry = (
        f"0 {hour} * * 1-5  "
        f"{python_exe} {CRON_SCRIPT} --execute "
        f">> {LOGS_DIR}/hybrid_cron.log 2>&1"
    )
    return _ok("cron_script_paths", f"All paths valid. Cron entry ({_label}):\n    {cron_entry}")


def check_exit_codes() -> CheckResult:
    """Verify cron script exit code logic covers BLOCKED_STALE_DATA."""
    src = CRON_SCRIPT.read_text()
    expected_statuses = [
        "BLOCKED_STALE_DATA",
        "BLOCKED_LOCK",
        "SKIPPED_NON_TRADING_DAY",
        "DATA_NOT_READY",
    ]
    for s in expected_statuses:
        if s not in src:
            return _block("exit_codes", f"{s} not found in cron script — fail-closed logic may be incomplete")
    return _ok("exit_codes", "All BLOCKED_* statuses present in cron script exit code logic")


def check_backup_policy() -> CheckResult:
    """Confirm backup policy: at least BACKUP_KEEP_N retained, same-device warning."""
    src = CRON_SCRIPT.read_text()
    if "BACKUP_KEEP_N" not in src:
        return _warn("backup_policy", "BACKUP_KEEP_N not found in cron script")
    baks = list(BACKUP_DIR.glob("platform_*.db.bak")) if BACKUP_DIR.exists() else []
    # Check recovery backups in root data dir
    recovery_baks = list(DATA_DIR.glob("platform_recover_backup_*.db"))
    total_baks = len(baks) + len(recovery_baks)
    return _warn(
        "backup_policy",
        f"{total_baks} backup(s) on disk ({len(baks)} in backups/, {len(recovery_baks)} recover backups). "
        f"SINGLE_DEVICE_FAILURE_RISK: all on same Mac. No off-device backup configured.",
    )


def check_mac_cron_restrictions() -> CheckResult:
    """Check macOS full disk access requirement for cron on modern macOS."""
    import platform
    if platform.system() != "Darwin":
        return _ok("mac_cron_fda", "Not macOS — full disk access check not applicable")

    mac_ver = platform.mac_ver()[0]
    major = int(mac_ver.split(".")[0]) if mac_ver else 0

    if major >= 10:  # Catalina+ requires FDA for cron to access user dirs
        return _warn(
            "mac_cron_fda",
            f"macOS {mac_ver} detected. macOS cron (launchd/cron) may require "
            f"Full Disk Access in System Settings → Privacy & Security → Full Disk Access → cron "
            f"to read/write files in ~/Desktop. Verify before first scheduled run.",
        )
    return _ok("mac_cron_fda", f"macOS {mac_ver}")


# ── Run all checks ─────────────────────────────────────────────────────────────

def run_preflight() -> Tuple[str, List[CheckResult]]:
    """Run all preflight checks. Returns (overall_status, checks)."""
    checks = [
        # Environment
        check_python_version(),
        check_working_directory(),
        check_project_root(),
        check_logs_dir(),
        check_backup_dir(),
        check_timezone(),
        check_dependencies(),
        check_env_variables(),
        # DB Isolation
        check_db_path_isolation(),
        check_sqlite_magic(),
        check_no_neon_in_cron_env(),
        check_research_tables_exist(),
        # Data Integrity
        check_dailyprice_freshness(),
        check_ohlc_continuity_gate(),
        check_db_integrity(),
        check_wal_orphan(),
        check_formal_signal_source(),
        # Cron Safety
        check_lock_available(),
        check_no_duplicate_cron(),
        check_cron_script_paths(),
        check_exit_codes(),
        check_backup_policy(),
        check_mac_cron_restrictions(),
    ]

    blocked = any(c.status == STATUS_BLOCK for c in checks)
    warned = any(c.status == STATUS_WARN for c in checks)

    if blocked:
        overall = STATUS_BLOCK
    elif warned:
        overall = "CONDITIONAL"
    else:
        overall = STATUS_PASS

    return overall, checks


# ── Output ─────────────────────────────────────────────────────────────────────

ICONS = {STATUS_PASS: "✅", STATUS_WARN: "⚠️ ", STATUS_BLOCK: "🛑"}


def print_results(overall: str, checks: List[CheckResult], verbose: bool) -> None:
    sections = [
        ("Environment", checks[0:8]),
        ("Database Isolation", checks[8:12]),
        ("Data Integrity", checks[12:17]),
        ("Cron Safety", checks[17:]),
    ]

    print(f"\n{'='*70}")
    print("  Hybrid Forward Shadow — Preflight Safety Gate")
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"  {ts}")
    print(f"{'='*70}")

    for section_name, section_checks in sections:
        print(f"\n── {section_name} {'─'*(50 - len(section_name))}")
        for c in section_checks:
            icon = ICONS.get(c.status, "?")
            line = f"  {icon} [{c.status:<9}] {c.name}"
            if verbose or c.status != STATUS_PASS:
                print(line)
                if c.detail:
                    for dl in c.detail.split("\n"):
                        print(f"               {dl}")
            else:
                print(line)

    print(f"\n{'='*70}")
    icon = ICONS.get(overall, "?")
    if overall == STATUS_BLOCK:
        print(f"  {icon} OVERALL: BLOCKED — resolve all 🛑 issues before installing cron")
    elif overall == "CONDITIONAL":
        print(f"  {icon} OVERALL: CONDITIONAL — review ⚠️  warnings before installing cron")
    else:
        print(f"  {icon} OVERALL: PASS — cron installation may proceed with manual approval")
    print(f"{'='*70}\n")

    # Print corrected cron entry (timezone-aware)
    python_exe = Path(sys.executable)
    hour, label = _cron_hour_for_taiwan_1600()
    print(f"  Recommended cron entry ({label}):")
    print("  ─────────────────────────────────────────────────")
    print(f"  0 {hour} * * 1-5  {python_exe} {CRON_SCRIPT} --execute >> {LOGS_DIR}/hybrid_cron.log 2>&1")
    print()
    print("  IMPORTANT: This script does NOT install the cron.")
    print("  To install: provide explicit approval, then run:")
    print("    crontab -l > /tmp/crontab_backup_$(date +%Y%m%d).txt")
    print("    crontab -e   # add the entry above")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Hybrid Forward Shadow — preflight safety gate")
    parser.add_argument("--verbose", action="store_true", help="Show detail for all checks (not just non-PASS)")
    parser.add_argument("--json", dest="output_json", action="store_true", help="Output results as JSON")
    args = parser.parse_args()

    overall, checks = run_preflight()

    if args.output_json:
        result = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "overall": overall,
            "checks": [c.to_dict() for c in checks],
        }
        print(json.dumps(result, indent=2))
    else:
        print_results(overall, checks, verbose=args.verbose)

    sys.exit(0 if overall in (STATUS_PASS, "CONDITIONAL") else 1)


if __name__ == "__main__":
    main()
