"""
tests/test_hybrid_shadow_preflight.py — PF01–PF20: Preflight safety gate tests.

Coverage:
  PF01–PF05  Environment checks
  PF06–PF10  Database isolation checks
  PF11–PF15  Data integrity checks
  PF16–PF20  Cron safety checks + overall result
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.hybrid_shadow_preflight import (
    STATUS_BLOCK,
    STATUS_PASS,
    STATUS_WARN,
    CheckResult,
    _cron_hour_for_taiwan_1600,
    check_cron_script_paths,
    check_dailyprice_freshness,
    check_db_integrity,
    check_db_path_isolation,
    check_dependencies,
    check_exit_codes,
    check_lock_available,
    check_logs_dir,
    check_no_duplicate_cron,
    check_no_neon_in_cron_env,
    check_ohlc_continuity_gate,
    check_project_root,
    check_python_version,
    check_research_tables_exist,
    check_sqlite_magic,
    check_timezone,
    check_wal_orphan,
    run_preflight,
)


# ---------------------------------------------------------------------------
# PF01–PF05  Environment
# ---------------------------------------------------------------------------

def test_PF01_python_version_pass():
    result = check_python_version()
    assert result.status == STATUS_PASS
    assert "3." in result.detail


def test_PF02_project_root_pass():
    result = check_project_root()
    assert result.status == STATUS_PASS


def test_PF03_logs_dir_created():
    result = check_logs_dir()
    assert result.status == STATUS_PASS
    logs = Path(__file__).parent.parent / "logs"
    assert logs.exists()


def test_PF04_timezone_taipei_available():
    result = check_timezone()
    assert result.status == STATUS_PASS
    assert "Asia/Taipei" in result.detail


def test_PF05_dependencies_present():
    result = check_dependencies()
    assert result.status == STATUS_PASS
    assert "requests" in result.detail


# ---------------------------------------------------------------------------
# PF06–PF10  Database isolation
# ---------------------------------------------------------------------------

def test_PF06_sqlite_magic_on_real_db():
    result = check_sqlite_magic()
    assert result.status == STATUS_PASS
    assert "SQLite" in result.detail


def test_PF07_db_path_isolation_uses_sqlite():
    result = check_db_path_isolation()
    assert result.status in (STATUS_PASS, STATUS_WARN)
    assert "SQLite" in result.detail or "sqlite" in result.detail.lower()


def test_PF08_no_neon_writes_in_cron_path():
    result = check_no_neon_in_cron_env()
    assert result.status == STATUS_PASS
    assert "Neon write isolation confirmed" in result.detail


def test_PF09_research_tables_exist():
    result = check_research_tables_exist()
    assert result.status == STATUS_PASS
    assert "hybrid_forward_decision" in result.detail or "3 research tables" in result.detail


def test_PF10_sqlite_magic_fails_on_non_sqlite(tmp_path):
    """Non-SQLite file should return BLOCKED."""
    fake_db = tmp_path / "fake.db"
    fake_db.write_bytes(b"PK\x03\x04not_a_sqlite_file_at_all")

    with patch("scripts.hybrid_shadow_preflight.DB_PATH", fake_db):
        result = check_sqlite_magic()
    assert result.status == STATUS_BLOCK
    assert "NOT a SQLite" in result.detail


# ---------------------------------------------------------------------------
# PF11–PF15  Data integrity
# ---------------------------------------------------------------------------

def test_PF11_dailyprice_freshness_on_real_db():
    result = check_dailyprice_freshness()
    # Last date should be 2026-11-05 (gap=0)
    assert result.status == STATUS_PASS
    assert "2026-11-05" in result.detail


def test_PF12_dailyprice_freshness_blocked_when_no_data(tmp_path):
    empty_db = tmp_path / "empty.db"
    conn = sqlite3.connect(str(empty_db))
    conn.execute("CREATE TABLE daily_prices (stock_id TEXT, date TEXT, close REAL)")
    conn.close()

    with patch("scripts.hybrid_shadow_preflight.DB_PATH", empty_db):
        result = check_dailyprice_freshness()
    assert result.status == STATUS_BLOCK
    assert "No 0050" in result.detail


def test_PF13_ohlc_gate_pass_on_real_db():
    # Uses last confirmed data date (2026-11-05) to avoid live dependency before cron (16:00 Taiwan).
    with patch("scripts.hybrid_shadow_preflight.date") as mock_date:
        mock_date.today.return_value = date(2026, 11, 5)
        result = check_ohlc_continuity_gate()
    assert result.status == STATUS_PASS
    assert "PASS" in result.detail
    assert "missing=0" in result.detail


def test_PF13_ohlc_gate_live_health():
    """Live data check — skips automatically if today's 0050 data not in DB yet (before cron 16:00 Taiwan)."""
    import sqlite3 as _sq
    db = Path(__file__).parent.parent / "data" / "platform.db"
    with _sq.connect(str(db)) as conn:
        today_count = conn.execute(
            "SELECT COUNT(*) FROM daily_prices WHERE stock_id='0050' AND date=?",
            (str(date.today()),),
        ).fetchone()[0]
    if today_count == 0:
        import pytest as _pytest
        _pytest.skip(f"No 0050 data for {date.today()} yet — run after cron (16:00 Taiwan)")
    result = check_ohlc_continuity_gate()
    assert result.status == STATUS_PASS, f"Live gate FAIL: {result.detail}"


def test_PF14_db_integrity_on_real_db():
    result = check_db_integrity()
    assert result.status == STATUS_PASS
    assert "integrity_check=ok" in result.detail
    assert "fk_violations=0" in result.detail


def test_PF15_wal_orphan_detects_platform2_wal():
    """The orphan 'platform 2.db-wal' should trigger a WARNING."""
    result = check_wal_orphan()
    # We know this file exists
    assert result.status == STATUS_WARN
    assert "platform 2.db-wal" in result.detail


# ---------------------------------------------------------------------------
# PF16–PF20  Cron safety + overall
# ---------------------------------------------------------------------------

def test_PF16_lock_available_when_no_lock_file(tmp_path):
    with patch("scripts.hybrid_shadow_preflight.LOCK_FILE", tmp_path / "no.lock"):
        result = check_lock_available()
    assert result.status == STATUS_PASS


def test_PF17_cron_script_paths_valid():
    result = check_cron_script_paths()
    assert result.status == STATUS_PASS
    assert "--execute" in result.detail
    # Cron hour must be 16 (local Asia/Taipei) on UTC+8 system
    import time as _t
    offset = int(-_t.timezone / 3600)
    expected_hour = str(16 if offset == 8 else (16 - offset) % 24)
    assert f"0 {expected_hour}" in result.detail


def test_PF18_exit_codes_check_pass():
    result = check_exit_codes()
    assert result.status == STATUS_PASS
    assert "BLOCKED_*" in result.detail or "statuses present" in result.detail


def test_PF19_no_duplicate_cron_when_clean():
    # Either no entry OR exactly one entry → PASS; 2+ entries → WARNING
    result = check_no_duplicate_cron()
    assert result.status == STATUS_PASS, (
        f"Expected PASS (0 or 1 entries), got {result.status}: {result.detail}"
    )


def test_PF20_run_preflight_overall_conditional():
    """Full preflight should return CONDITIONAL (warnings present, no blocks)."""
    # Uses 2026-11-05 as today to avoid live data dependency before cron (16:00 Taiwan).
    with patch("scripts.hybrid_shadow_preflight.date") as mock_date:
        mock_date.today.return_value = date(2026, 11, 5)
        mock_date.fromisoformat = date.fromisoformat
        overall, checks = run_preflight()

    # No blocks expected (gate is PASS, DB is good)
    blocked = [c for c in checks if c.status == STATUS_BLOCK]
    assert blocked == [], f"Unexpected blocks: {[c.name for c in blocked]}"

    # Overall must be PASS or CONDITIONAL
    assert overall in (STATUS_PASS, "CONDITIONAL"), f"Unexpected overall={overall}"

    # Must have at least the WAL orphan warning
    warned = [c for c in checks if c.status == STATUS_WARN]
    assert len(warned) >= 1


# ---------------------------------------------------------------------------
# Extra: CheckResult serialization
# ---------------------------------------------------------------------------

def test_PF_checkresult_to_dict():
    r = CheckResult("test_name", STATUS_PASS, "some detail")
    d = r.to_dict()
    assert d["name"] == "test_name"
    assert d["status"] == STATUS_PASS
    assert d["detail"] == "some detail"


def test_PF_json_output():
    """Preflight --json output is valid JSON with expected keys."""
    overall, checks = run_preflight()
    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "overall": overall,
        "checks": [c.to_dict() for c in checks],
    }
    json_str = json.dumps(result)
    parsed = json.loads(json_str)
    assert "overall" in parsed
    assert "checks" in parsed
    assert len(parsed["checks"]) >= 20


# ---------------------------------------------------------------------------
# PF21–PF23  Timezone-aware cron hour
# ---------------------------------------------------------------------------

def test_PF21_cron_hour_utc8_returns_16():
    """On UTC+8 (Asia/Taipei), cron hour for Taiwan 16:00 should be 16."""
    with patch("scripts.hybrid_shadow_preflight._time.timezone", -8 * 3600):
        hour, label = _cron_hour_for_taiwan_1600()
    assert hour == "16"
    assert "16" in label


def test_PF22_cron_hour_utc0_returns_8():
    """On UTC+0, cron hour for Taiwan 16:00 should be 8."""
    with patch("scripts.hybrid_shadow_preflight._time.timezone", 0):
        hour, label = _cron_hour_for_taiwan_1600()
    assert hour == "8"
    assert "UTC" in label


def test_PF23_cron_timezone_note_in_check():
    """check_timezone detail should mention system offset and cron hour."""
    result = check_timezone()
    assert result.status == STATUS_PASS
    assert "UTC+" in result.detail or "UTC+" in result.detail
    assert "cron" in result.detail.lower()


# ---------------------------------------------------------------------------
# CM01–CM05  Missed run detection (hybrid_shadow_cron)
# ---------------------------------------------------------------------------

def test_CM01_no_missed_when_last_run_today(tmp_path):
    """No missed sessions when last run was today."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from scripts.hybrid_shadow_cron import _detect_missed_runs
    from unittest.mock import patch

    today = date.today()
    with (
        patch("scripts.hybrid_shadow_cron.date") as mock_date,
        patch("scripts.hybrid_shadow_cron.sqlite3.connect") as mock_conn,
    ):
        mock_date.today.return_value = today
        mock_date.fromisoformat = date.fromisoformat
        mock_conn.return_value.__enter__ = lambda s: s
        mock_conn.return_value.execute.return_value.fetchone.return_value = (str(today),)
        mock_conn.return_value.close = lambda: None
        result = _detect_missed_runs({})
    assert result["trading_days_since_last_run"] == 0
    assert result["alert"] is False


def test_CM02_missed_sessions_between_dates():
    """Detect missed sessions when last run was before today."""
    from scripts.hybrid_shadow_cron import _detect_missed_runs
    from unittest.mock import patch

    last_run = date(2026, 11, 3)   # Monday
    today_ = date(2026, 11, 5)     # Wednesday (11-04 Tue is a trading day)

    with (
        patch("scripts.hybrid_shadow_cron.date") as mock_date,
        patch("scripts.hybrid_shadow_cron.sqlite3.connect") as mock_conn,
    ):
        mock_date.today.return_value = today_
        mock_date.fromisoformat = date.fromisoformat
        mock_conn.return_value.__enter__ = lambda s: s
        mock_conn.return_value.execute.return_value.fetchone.return_value = (str(last_run),)
        mock_conn.return_value.close = lambda: None
        result = _detect_missed_runs({})

    # 11-04 is a trading day, so at least 1 missed
    assert result["alert"] is True
    assert "2026-11-04" in result["missed_dates"]


def test_CM03_no_missed_when_no_state():
    """When no state and no DB record, missed run detection returns no alert."""
    from scripts.hybrid_shadow_cron import _detect_missed_runs
    from unittest.mock import patch

    with patch("scripts.hybrid_shadow_cron.sqlite3.connect") as mock_conn:
        mock_conn.return_value.execute.return_value.fetchone.return_value = (None,)
        mock_conn.return_value.close = lambda: None
        result = _detect_missed_runs({})

    assert result["last_execute_date"] is None
    assert result["alert"] is False


def test_CM04_missed_run_does_not_modify_decisions(tmp_path):
    """Missed run detection is read-only — does not write or modify decisions."""
    from scripts.hybrid_shadow_cron import _detect_missed_runs
    from unittest.mock import patch

    with (
        patch("scripts.hybrid_shadow_cron.date") as mock_date,
        patch("scripts.hybrid_shadow_cron.sqlite3.connect") as mock_conn,
    ):
        mock_date.today.return_value = date(2026, 11, 5)
        mock_date.fromisoformat = date.fromisoformat
        mock_conn.return_value.execute.return_value.fetchone.return_value = ("2026-11-03",)
        mock_conn.return_value.close = lambda: None
        result = _detect_missed_runs({})

    # Result is a dict, not writing anything
    assert isinstance(result, dict)
    assert "missed_dates" in result


def test_CM05_check_missed_flag_does_not_install_cron():
    """--check-missed must not add extra cron entries (count must not increase)."""
    import subprocess
    # Count entries before
    before = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    count_before = before.stdout.count("hybrid_shadow_cron")

    result = subprocess.run(
        ["python3", "scripts/hybrid_shadow_cron.py", "--check-missed"],
        capture_output=True, text=True, cwd=str(Path(__file__).parent.parent)
    )
    assert result.returncode == 0

    # Count must not have increased
    after = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    count_after = after.stdout.count("hybrid_shadow_cron")
    assert count_after == count_before, (
        f"--check-missed must not modify crontab (before={count_before}, after={count_after})"
    )
