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
import os
import sqlite3
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.hybrid_shadow_preflight import (
    STATUS_BLOCK,
    STATUS_PASS,
    STATUS_WARN,
    CheckResult,
    check_backup_dir,
    check_backup_policy,
    check_cron_script_paths,
    check_dailyprice_freshness,
    check_db_integrity,
    check_db_path_isolation,
    check_dependencies,
    check_env_variables,
    check_exit_codes,
    check_formal_signal_source,
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
    result = check_ohlc_continuity_gate()
    assert result.status == STATUS_PASS
    assert "PASS" in result.detail
    assert "missing=0" in result.detail


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
    assert "0 8" in result.detail


def test_PF18_exit_codes_check_pass():
    result = check_exit_codes()
    assert result.status == STATUS_PASS
    assert "BLOCKED_*" in result.detail or "statuses present" in result.detail


def test_PF19_no_duplicate_cron_when_clean():
    # crontab -l will return no hybrid_shadow_cron entry
    result = check_no_duplicate_cron()
    assert result.status == STATUS_PASS


def test_PF20_run_preflight_overall_conditional():
    """Full preflight should return CONDITIONAL (warnings present, no blocks)."""
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
