"""
tests/test_hybrid_cron.py — HC01–HC30: hybrid_shadow_cron.py unit tests.

All tests are offline (no network calls, no subprocess execution).
Real file I/O is restricted to temp dirs.

Coverage:
  HC01–HC05  FileLock semantics
  HC06–HC09  _is_data_ready()
  HC10–HC12  create_backup() / _rotate_backups()
  HC13–HC16  run_cron_pipeline() calendar + data-ready short-circuits
  HC17–HC20  run_cron_pipeline() full flow (mocked backfill + shadow)
  HC21–HC23  State persistence
  HC24–HC25  print_status() smoke test + list_backups()
  HC26–HC27  Fail-closed stale data (Step 4b abort)
  HC28–HC30  Calendar + recovery regression
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Bring scripts/ onto sys.path
# ---------------------------------------------------------------------------
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from scripts.hybrid_shadow_cron import (  # noqa: E402
    FileLock,
    _is_data_ready,
    _load_state,
    _rotate_backups,
    _save_state,
    create_backup,
    list_backups,
    run_cron_pipeline,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_sqlite_db(path: str) -> None:
    """Create a minimal SQLite DB large enough to pass MIN_BACKUP_SIZE_BYTES."""
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS daily_prices "
        "(stock_id TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL)"
    )
    # Insert enough rows so DB size > 100 KB
    rows = [(f"{i:04d}", "2026-11-04", 10.0, 11.0, 9.5, 10.5, 1000.0) for i in range(2000)]
    conn.executemany("INSERT INTO daily_prices VALUES (?,?,?,?,?,?,?)", rows)
    conn.execute(
        "INSERT INTO daily_prices VALUES ('0050', '2026-11-04', 190.0, 192.0, 189.0, 191.0, 5000.0)"
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# HC01–HC05  FileLock
# ---------------------------------------------------------------------------

def test_HC01_lock_acquire_release(tmp_path):
    lock = FileLock(tmp_path / "test.lock")
    assert lock.acquire() is True
    lock.release()


def test_HC02_lock_blocks_second_process(tmp_path):
    lock_path = tmp_path / "test.lock"
    lock1 = FileLock(lock_path)
    lock2 = FileLock(lock_path)
    assert lock1.acquire() is True
    assert lock2.acquire() is False  # second process blocked
    lock1.release()


def test_HC03_lock_reacquire_after_release(tmp_path):
    lock = FileLock(tmp_path / "test.lock")
    assert lock.acquire() is True
    lock.release()
    assert lock.acquire() is True  # re-acquire succeeds
    lock.release()


def test_HC04_lock_release_idempotent(tmp_path):
    lock = FileLock(tmp_path / "test.lock")
    lock.release()  # releasing without acquiring should not raise


def test_HC05_lock_creates_parent_dirs(tmp_path):
    deep_path = tmp_path / "a" / "b" / "c" / "lock.lock"
    lock = FileLock(deep_path)
    assert lock.acquire() is True
    lock.release()
    assert deep_path.parent.exists()


# ---------------------------------------------------------------------------
# HC06–HC09  _is_data_ready()
# ---------------------------------------------------------------------------

def _taipei_at(h: int, m: int):
    """Fake timezone-aware taipei datetime at given hour:minute."""
    import pytz
    tz = pytz.timezone("Asia/Taipei")
    return tz.localize(datetime(2026, 11, 5, h, m, 0))


def test_HC06_data_ready_after_1530():
    assert _is_data_ready(_taipei_at(15, 30)) is True


def test_HC07_data_ready_after_1600():
    assert _is_data_ready(_taipei_at(16, 0)) is True


def test_HC08_data_not_ready_before_1530():
    assert _is_data_ready(_taipei_at(15, 29)) is False


def test_HC09_data_not_ready_at_noon():
    assert _is_data_ready(_taipei_at(12, 0)) is False


# ---------------------------------------------------------------------------
# HC10–HC12  create_backup() / _rotate_backups()
# ---------------------------------------------------------------------------

def test_HC10_create_backup_success(tmp_path):
    db_file = tmp_path / "platform.db"
    _make_sqlite_db(str(db_file))

    backup_dir = tmp_path / "backups"
    with (
        patch("scripts.hybrid_shadow_cron.DB_PATH", db_file),
        patch("scripts.hybrid_shadow_cron.BACKUP_DIR", backup_dir),
    ):
        result = create_backup(str(db_file), date(2026, 11, 5))

    assert result is not None
    assert result.exists()
    assert result.suffix == ".bak"
    assert "20261105" in result.name


def test_HC11_backup_missing_db_returns_none(tmp_path):
    result = create_backup(str(tmp_path / "nonexistent.db"), date(2026, 11, 5))
    assert result is None


def test_HC12_rotate_keeps_last_n(tmp_path):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    # Create 10 dummy .db.bak files
    for i in range(10):
        f = backup_dir / f"platform_2026110{i}_T120000Z.db.bak"
        f.write_bytes(b"x" * 1000)

    with patch("scripts.hybrid_shadow_cron.BACKUP_DIR", backup_dir):
        _rotate_backups()

    remaining = sorted(backup_dir.glob("*.db.bak"))
    # Should keep BACKUP_KEEP_N=7 most recent
    assert len(remaining) == 7
    # The newest 7 survive
    for r in remaining:
        assert any(str(i) in r.name for i in range(3, 10))


# ---------------------------------------------------------------------------
# HC13–HC16  run_cron_pipeline() short-circuit paths (no subprocess)
# ---------------------------------------------------------------------------

@patch("scripts.hybrid_shadow_cron._run_backfill")
@patch("scripts.hybrid_shadow_cron._run_shadow")
def test_HC13_dry_run_does_not_call_shadow(_shadow, _bf, tmp_path):
    with (
        patch("scripts.hybrid_shadow_cron.LOCK_FILE", tmp_path / "lock"),
        patch("scripts.hybrid_shadow_cron.STATE_FILE", tmp_path / "state.json"),
        patch("scripts.hybrid_shadow_cron.CALENDAR") as mock_cal,
        patch("scripts.hybrid_shadow_cron._is_data_ready", return_value=True),
    ):
        mock_cal.is_trading_day.return_value = True
        _bf.return_value = {"exit_code": 0, "stdout": "", "stderr": ""}
        result = run_cron_pipeline(execute=False)

    assert result["status"] == "DRY_RUN_OK"
    _shadow.assert_not_called()


@patch("scripts.hybrid_shadow_cron._run_backfill")
@patch("scripts.hybrid_shadow_cron._run_shadow")
def test_HC14_non_trading_day_skipped(_shadow, _bf, tmp_path):
    with (
        patch("scripts.hybrid_shadow_cron.LOCK_FILE", tmp_path / "lock"),
        patch("scripts.hybrid_shadow_cron.STATE_FILE", tmp_path / "state.json"),
        patch("scripts.hybrid_shadow_cron.CALENDAR") as mock_cal,
    ):
        mock_cal.is_trading_day.return_value = False
        result = run_cron_pipeline(execute=True)

    assert result["status"] == "SKIPPED_NON_TRADING_DAY"
    _bf.assert_not_called()
    _shadow.assert_not_called()


@patch("scripts.hybrid_shadow_cron._run_backfill")
@patch("scripts.hybrid_shadow_cron._run_shadow")
def test_HC15_data_not_ready_stops_pipeline(_shadow, _bf, tmp_path):
    with (
        patch("scripts.hybrid_shadow_cron.LOCK_FILE", tmp_path / "lock"),
        patch("scripts.hybrid_shadow_cron.STATE_FILE", tmp_path / "state.json"),
        patch("scripts.hybrid_shadow_cron.CALENDAR") as mock_cal,
        patch("scripts.hybrid_shadow_cron._is_data_ready", return_value=False),
    ):
        mock_cal.is_trading_day.return_value = True
        result = run_cron_pipeline(execute=False)

    assert result["status"] == "DATA_NOT_READY"
    _bf.assert_not_called()


@patch("scripts.hybrid_shadow_cron._run_backfill")
@patch("scripts.hybrid_shadow_cron._run_shadow")
def test_HC16_backfill_failure_stops_pipeline(_shadow, _bf, tmp_path):
    with (
        patch("scripts.hybrid_shadow_cron.LOCK_FILE", tmp_path / "lock"),
        patch("scripts.hybrid_shadow_cron.STATE_FILE", tmp_path / "state.json"),
        patch("scripts.hybrid_shadow_cron.CALENDAR") as mock_cal,
        patch("scripts.hybrid_shadow_cron._is_data_ready", return_value=True),
    ):
        mock_cal.is_trading_day.return_value = True
        _bf.return_value = {"exit_code": 1, "stdout": "", "stderr": "fetch error"}
        result = run_cron_pipeline(execute=True)

    assert result["status"] == "BACKFILL_FAILED"
    _shadow.assert_not_called()


# ---------------------------------------------------------------------------
# HC17–HC20  run_cron_pipeline() full success path
# ---------------------------------------------------------------------------

@patch("scripts.hybrid_shadow_cron._run_backfill")
@patch("scripts.hybrid_shadow_cron._run_shadow")
@patch("scripts.hybrid_shadow_cron.create_backup")
def test_HC17_full_success_pipeline(_backup, _shadow, _bf, tmp_path):
    _bf.return_value = {"exit_code": 0, "stdout": "inserted=6957", "stderr": ""}
    _shadow.return_value = {"exit_code": 0, "stdout": "SUCCESS", "stderr": ""}
    _backup.return_value = Path(tmp_path / "platform_20261105_T160000Z.db.bak")

    with (
        patch("scripts.hybrid_shadow_cron.LOCK_FILE", tmp_path / "lock"),
        patch("scripts.hybrid_shadow_cron.STATE_FILE", tmp_path / "state.json"),
        patch("scripts.hybrid_shadow_cron.CALENDAR") as mock_cal,
        patch("scripts.hybrid_shadow_cron._is_data_ready", return_value=True),
        patch("scripts.hybrid_shadow_cron._get_db_last_date", return_value=date(2026, 11, 5)),
    ):
        mock_cal.is_trading_day.return_value = True
        result = run_cron_pipeline(execute=True)

    assert result["status"] == "SUCCESS"
    _backup.assert_called_once()
    _shadow.assert_called_once()


@patch("scripts.hybrid_shadow_cron._run_backfill")
@patch("scripts.hybrid_shadow_cron._run_shadow")
@patch("scripts.hybrid_shadow_cron.create_backup")
def test_HC18_shadow_failure_recorded(_backup, _shadow, _bf, tmp_path):
    _bf.return_value = {"exit_code": 0, "stdout": "", "stderr": ""}
    _shadow.return_value = {"exit_code": 1, "stdout": "", "stderr": "shadow error"}
    _backup.return_value = None  # backup failed too

    with (
        patch("scripts.hybrid_shadow_cron.LOCK_FILE", tmp_path / "lock"),
        patch("scripts.hybrid_shadow_cron.STATE_FILE", tmp_path / "state.json"),
        patch("scripts.hybrid_shadow_cron.CALENDAR") as mock_cal,
        patch("scripts.hybrid_shadow_cron._is_data_ready", return_value=True),
        patch("scripts.hybrid_shadow_cron._get_db_last_date", return_value=date(2026, 11, 5)),
    ):
        mock_cal.is_trading_day.return_value = True
        result = run_cron_pipeline(execute=True)

    assert result["status"] == "SHADOW_FAILED"


@patch("scripts.hybrid_shadow_cron._run_backfill")
@patch("scripts.hybrid_shadow_cron._run_shadow")
@patch("scripts.hybrid_shadow_cron.create_backup")
def test_HC19_skip_backup_flag(_backup, _shadow, _bf, tmp_path):
    _bf.return_value = {"exit_code": 0, "stdout": "", "stderr": ""}
    _shadow.return_value = {"exit_code": 0, "stdout": "SUCCESS", "stderr": ""}

    with (
        patch("scripts.hybrid_shadow_cron.LOCK_FILE", tmp_path / "lock"),
        patch("scripts.hybrid_shadow_cron.STATE_FILE", tmp_path / "state.json"),
        patch("scripts.hybrid_shadow_cron.CALENDAR") as mock_cal,
        patch("scripts.hybrid_shadow_cron._is_data_ready", return_value=True),
        patch("scripts.hybrid_shadow_cron._get_db_last_date", return_value=date(2026, 11, 5)),
    ):
        mock_cal.is_trading_day.return_value = True
        result = run_cron_pipeline(execute=True, skip_backup=True)

    assert result["status"] == "SUCCESS"
    _backup.assert_not_called()
    assert result["steps"].get("backup") == "skipped"


@patch("scripts.hybrid_shadow_cron._run_backfill")
@patch("scripts.hybrid_shadow_cron._run_shadow")
def test_HC20_concurrent_lock_blocked(_shadow, _bf, tmp_path):
    lock_path = tmp_path / "lock"
    lock_holder = FileLock(lock_path)
    lock_holder.acquire()

    with (
        patch("scripts.hybrid_shadow_cron.LOCK_FILE", lock_path),
        patch("scripts.hybrid_shadow_cron.STATE_FILE", tmp_path / "state.json"),
    ):
        result = run_cron_pipeline(execute=True)

    lock_holder.release()
    assert result["status"] == "BLOCKED_LOCK"
    _bf.assert_not_called()
    _shadow.assert_not_called()


# ---------------------------------------------------------------------------
# HC21–HC23  State persistence
# ---------------------------------------------------------------------------

def test_HC21_state_save_and_load(tmp_path):
    state_file = tmp_path / "state.json"
    sample = {"status": "SUCCESS", "today": "2026-11-05", "steps": {"lock": "released"}}
    with patch("scripts.hybrid_shadow_cron.STATE_FILE", state_file):
        _save_state(sample)
        loaded = _load_state()
    assert loaded["status"] == "SUCCESS"
    assert loaded["today"] == "2026-11-05"


def test_HC22_load_state_missing_file(tmp_path):
    with patch("scripts.hybrid_shadow_cron.STATE_FILE", tmp_path / "nonexistent.json"):
        state = _load_state()
    assert state == {}


def test_HC23_state_written_on_non_trading_day(tmp_path):
    state_file = tmp_path / "state.json"
    with (
        patch("scripts.hybrid_shadow_cron.LOCK_FILE", tmp_path / "lock"),
        patch("scripts.hybrid_shadow_cron.STATE_FILE", state_file),
        patch("scripts.hybrid_shadow_cron.CALENDAR") as mock_cal,
    ):
        mock_cal.is_trading_day.return_value = False
        run_cron_pipeline(execute=True)
    assert state_file.exists()
    state = json.loads(state_file.read_text())
    assert state["status"] == "SKIPPED_NON_TRADING_DAY"


# ---------------------------------------------------------------------------
# HC24–HC25  Smoke tests
# ---------------------------------------------------------------------------

def test_HC24_list_backups_empty(tmp_path):
    with patch("scripts.hybrid_shadow_cron.BACKUP_DIR", tmp_path / "backups"):
        baks = list_backups()
    assert baks == []


def test_HC25_list_backups_returns_files(tmp_path):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    for name in ["platform_20261105_T160000Z.db.bak", "platform_20261106_T160000Z.db.bak"]:
        (backup_dir / name).write_bytes(b"x" * 500)

    with patch("scripts.hybrid_shadow_cron.BACKUP_DIR", backup_dir):
        baks = list_backups()

    assert len(baks) == 2
    names = [b["name"] for b in baks]
    assert "platform_20261105_T160000Z.db.bak" in names


# ---------------------------------------------------------------------------
# HC26–HC27  Fail-closed stale data (Step 4b abort)
# ---------------------------------------------------------------------------

@patch("scripts.hybrid_shadow_cron._run_backfill")
@patch("scripts.hybrid_shadow_cron._run_shadow")
@patch("scripts.hybrid_shadow_cron.create_backup")
def test_HC26_stale_data_aborts_before_shadow(_backup, _shadow, _bf, tmp_path):
    """FAIL-CLOSED: backfill exit_code=0 but DB still has yesterday → BLOCKED_STALE_DATA."""
    _bf.return_value = {"exit_code": 0, "stdout": "", "stderr": ""}

    today = date(2026, 11, 5)
    yesterday = date(2026, 11, 4)

    with (
        patch("scripts.hybrid_shadow_cron.LOCK_FILE", tmp_path / "lock"),
        patch("scripts.hybrid_shadow_cron.STATE_FILE", tmp_path / "state.json"),
        patch("scripts.hybrid_shadow_cron.CALENDAR") as mock_cal,
        patch("scripts.hybrid_shadow_cron._is_data_ready", return_value=True),
        patch("scripts.hybrid_shadow_cron._get_db_last_date", return_value=yesterday),
        patch("scripts.hybrid_shadow_cron.date") as mock_date,
    ):
        mock_cal.is_trading_day.return_value = True
        mock_date.today.return_value = today
        result = run_cron_pipeline(execute=True)

    assert result["status"] == "BLOCKED_STALE_DATA"
    _shadow.assert_not_called()
    _backup.assert_not_called()


@patch("scripts.hybrid_shadow_cron._run_backfill")
@patch("scripts.hybrid_shadow_cron._run_shadow")
@patch("scripts.hybrid_shadow_cron.create_backup")
def test_HC27_fresh_data_proceeds_to_shadow(_backup, _shadow, _bf, tmp_path):
    """When DB last_date == today, pipeline proceeds past Step 4b."""
    _bf.return_value = {"exit_code": 0, "stdout": "", "stderr": ""}
    _shadow.return_value = {"exit_code": 0, "stdout": "SUCCESS", "stderr": ""}
    _backup.return_value = None

    today = date(2026, 11, 5)

    with (
        patch("scripts.hybrid_shadow_cron.LOCK_FILE", tmp_path / "lock"),
        patch("scripts.hybrid_shadow_cron.STATE_FILE", tmp_path / "state.json"),
        patch("scripts.hybrid_shadow_cron.CALENDAR") as mock_cal,
        patch("scripts.hybrid_shadow_cron._is_data_ready", return_value=True),
        patch("scripts.hybrid_shadow_cron._get_db_last_date", return_value=today),
        patch("scripts.hybrid_shadow_cron.date") as mock_date,
    ):
        mock_cal.is_trading_day.return_value = True
        mock_date.today.return_value = today
        result = run_cron_pipeline(execute=True)

    _shadow.assert_called_once()
    assert result["steps"].get("data_freshness") == "OK"


# ---------------------------------------------------------------------------
# HC28–HC30  Calendar fix + recovery regression (live DB integration)
# ---------------------------------------------------------------------------

def test_HC28_calendar_09_28_is_holiday():
    """2026-09-28 must be a holiday after calendar fix (TWSE confirmed closed)."""
    from src.core.trading_calendar import TaiwanTradingCalendar
    cal = TaiwanTradingCalendar()
    assert not cal.is_trading_day(date(2026, 9, 28)), "09-28 should be holiday (TWSE confirmed closed)"


def test_HC29_calendar_1023_1026_are_holidays():
    """2026-10-23 and 2026-10-26 must be holidays (typhoon closure confirmed by TWSE FMTQIK)."""
    from src.core.trading_calendar import TaiwanTradingCalendar
    cal = TaiwanTradingCalendar()
    assert not cal.is_trading_day(date(2026, 10, 23)), "10-23 should be holiday (typhoon)"
    assert not cal.is_trading_day(date(2026, 10, 26)), "10-26 should be holiday (typhoon bridge)"


import pytest

@pytest.mark.skipif(
    not (Path(__file__).parent.parent / "data" / "platform.db").exists(),
    reason="data/platform.db not found",
)
def test_HC30_ohlc_gate_pass_after_recovery():
    """After calendar fix + 0050 backfill, market gate must return PASS for 2026-11-05."""
    import sqlite3 as _sqlite3
    from src.research.ohlc_continuity_gate import GateResult, OHLCContinuityGate
    db = Path(__file__).parent.parent / "data" / "platform.db"
    conn = _sqlite3.connect(str(db))
    gate = OHLCContinuityGate()
    report = gate.check_market(conn, date(2026, 11, 5))
    conn.close()
    assert report.gate_result == GateResult.PASS, (
        f"Expected PASS but got {report.gate_result}; "
        f"missing={report.missing_sessions} dates={report.missing_dates}"
    )
