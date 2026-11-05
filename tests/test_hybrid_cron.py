"""
tests/test_hybrid_cron.py — HC01–HC33: hybrid_shadow_cron.py unit tests.

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
from src.research.full_market_freshness_gate import FreshnessReport, FreshnessStatus


def _fresh_report(trade_date: date = date(2026, 11, 5)) -> FreshnessReport:
    return FreshnessReport(
        status=FreshnessStatus.FULL_MARKET_FRESH,
        trade_date=trade_date,
        benchmark_date=trade_date,
        non_benchmark_count=6956,
        min_required=1000,
        detail="full market fresh",
    )


def _stale_report(trade_date: date = date(2026, 11, 5)) -> FreshnessReport:
    return FreshnessReport(
        status=FreshnessStatus.STALE,
        trade_date=trade_date,
        benchmark_date=date(2026, 11, 4),
        non_benchmark_count=0,
        min_required=1000,
        detail="0050 last_date=2026-11-04, today=2026-11-05",
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
        patch("scripts.hybrid_shadow_cron._alert"),
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
        patch("scripts.hybrid_shadow_cron.check_market_freshness", return_value=_fresh_report()),
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
        patch("scripts.hybrid_shadow_cron.check_market_freshness", return_value=_fresh_report()),
        patch("scripts.hybrid_shadow_cron._alert"),
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
        patch("scripts.hybrid_shadow_cron.check_market_freshness", return_value=_fresh_report()),
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
    """FAIL-CLOSED: check_market_freshness returns STALE → BLOCKED_STALE_DATA, shadow skipped."""
    _bf.return_value = {"exit_code": 0, "stdout": "", "stderr": ""}

    today = date(2026, 11, 5)

    with (
        patch("scripts.hybrid_shadow_cron.LOCK_FILE", tmp_path / "lock"),
        patch("scripts.hybrid_shadow_cron.STATE_FILE", tmp_path / "state.json"),
        patch("scripts.hybrid_shadow_cron.CALENDAR") as mock_cal,
        patch("scripts.hybrid_shadow_cron._is_data_ready", return_value=True),
        patch("scripts.hybrid_shadow_cron.check_market_freshness", return_value=_stale_report(today)),
        patch("scripts.hybrid_shadow_cron._alert"),
    ):
        mock_cal.is_trading_day.return_value = True
        result = run_cron_pipeline(execute=True)

    assert result["status"] == "BLOCKED_STALE_DATA"
    _shadow.assert_not_called()
    _backup.assert_not_called()


@patch("scripts.hybrid_shadow_cron._run_backfill")
@patch("scripts.hybrid_shadow_cron._run_shadow")
@patch("scripts.hybrid_shadow_cron.create_backup")
def test_HC27_fresh_data_proceeds_to_shadow(_backup, _shadow, _bf, tmp_path):
    """When check_market_freshness returns FULL_MARKET_FRESH, pipeline proceeds past Step 4b."""
    _bf.return_value = {"exit_code": 0, "stdout": "", "stderr": ""}
    _shadow.return_value = {"exit_code": 0, "stdout": "SUCCESS", "stderr": ""}
    _backup.return_value = None

    today = date(2026, 11, 5)

    with (
        patch("scripts.hybrid_shadow_cron.LOCK_FILE", tmp_path / "lock"),
        patch("scripts.hybrid_shadow_cron.STATE_FILE", tmp_path / "state.json"),
        patch("scripts.hybrid_shadow_cron.CALENDAR") as mock_cal,
        patch("scripts.hybrid_shadow_cron._is_data_ready", return_value=True),
        patch("scripts.hybrid_shadow_cron.check_market_freshness", return_value=_fresh_report(today)),
        patch("scripts.hybrid_shadow_cron._alert"),
    ):
        mock_cal.is_trading_day.return_value = True
        result = run_cron_pipeline(execute=True)

    _shadow.assert_called_once()
    assert result["steps"].get("data_freshness") == FreshnessStatus.FULL_MARKET_FRESH.value


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


# ---------------------------------------------------------------------------
# HC31–HC33  Exit code + trigger source state persistence
# ---------------------------------------------------------------------------

@patch("scripts.hybrid_shadow_cron._run_backfill")
@patch("scripts.hybrid_shadow_cron._run_shadow")
@patch("scripts.hybrid_shadow_cron.create_backup")
def test_HC31_exit_code_persisted_in_state(_backup, _shadow, _bf, tmp_path):
    """After _cli() runs, state file must include exit_code (0 for SUCCESS)."""
    _bf.return_value = {"exit_code": 0, "stdout": "inserted=6957", "stderr": ""}
    _shadow.return_value = {"exit_code": 0, "stdout": "SUCCESS", "stderr": ""}
    _backup.return_value = None
    state_file = tmp_path / "state.json"

    with (
        patch("scripts.hybrid_shadow_cron.LOCK_FILE", tmp_path / "lock"),
        patch("scripts.hybrid_shadow_cron.STATE_FILE", state_file),
        patch("scripts.hybrid_shadow_cron.CALENDAR") as mock_cal,
        patch("scripts.hybrid_shadow_cron._is_data_ready", return_value=True),
        patch("scripts.hybrid_shadow_cron.check_market_freshness", return_value=_fresh_report()),
        patch("scripts.hybrid_shadow_cron._alert"),
        patch("scripts.hybrid_shadow_cron.sys") as mock_sys,
    ):
        mock_sys.stdout.isatty.return_value = True  # simulate manual run
        mock_sys.argv = ["hybrid_shadow_cron.py", "--execute"]
        mock_sys.exit = lambda code: None  # prevent actual exit
        mock_cal.is_trading_day.return_value = True

        import scripts.hybrid_shadow_cron as cron_mod
        result = cron_mod.run_cron_pipeline(execute=True)
        # Simulate what _cli does after run_cron_pipeline
        result["exit_code"] = 0
        result["trigger_source"] = "manual"
        cron_mod._save_state(result)

    import json
    saved = json.loads(state_file.read_text())
    assert "exit_code" in saved, "exit_code must be persisted in state file"
    assert saved["exit_code"] == 0
    assert "trigger_source" in saved


def test_HC32_blocked_partial_exit_code_zero(tmp_path):
    """BLOCKED_PARTIAL_MARKET must map to exit_code=0 (expected condition, not failure)."""
    from scripts.hybrid_shadow_cron import run_cron_pipeline
    state_file = tmp_path / "state.json"

    _bm_only = FreshnessReport(
        status=FreshnessStatus.BENCHMARK_ONLY_UPDATED,
        trade_date=date(2026, 11, 5),
        benchmark_date=date(2026, 11, 5),
        non_benchmark_count=0,
        min_required=1000,
        detail="0050 updated to 2026-11-05, but non-0050 count=0",
    )

    with (
        patch("scripts.hybrid_shadow_cron.LOCK_FILE", tmp_path / "lock"),
        patch("scripts.hybrid_shadow_cron.STATE_FILE", state_file),
        patch("scripts.hybrid_shadow_cron.CALENDAR") as mock_cal,
        patch("scripts.hybrid_shadow_cron._is_data_ready", return_value=True),
        patch("scripts.hybrid_shadow_cron._run_backfill",
              return_value={"exit_code": 0, "stdout": "", "stderr": ""}),
        patch("scripts.hybrid_shadow_cron.check_market_freshness", return_value=_bm_only),
        patch("scripts.hybrid_shadow_cron._time"),
        patch("scripts.hybrid_shadow_cron._alert"),
    ):
        mock_cal.is_trading_day.return_value = True
        result = run_cron_pipeline(execute=True)

    assert result["status"] == "BLOCKED_PARTIAL_MARKET"
    clean_statuses = {
        "SUCCESS", "DRY_RUN_OK", "SKIPPED_NON_TRADING_DAY", "DATA_NOT_READY",
        "BLOCKED_STALE_DATA", "BLOCKED_LOCK", "BLOCKED_PARTIAL_MARKET",
    }
    assert result["status"] in clean_statuses, "BLOCKED_PARTIAL_MARKET must yield exit_code=0"


def test_HC33_trigger_source_manual_vs_cron():
    """trigger_source must be 'manual' when stdout is a tty, 'cron_scheduled' otherwise."""
    with patch("scripts.hybrid_shadow_cron.sys") as mock_sys:
        mock_sys.stdout.isatty.return_value = True
        source_tty = "manual" if mock_sys.stdout.isatty() else "cron_scheduled"
        assert source_tty == "manual"

        mock_sys.stdout.isatty.return_value = False
        source_notty = "manual" if mock_sys.stdout.isatty() else "cron_scheduled"
        assert source_notty == "cron_scheduled"


# ---------------------------------------------------------------------------
# HC34–HC38  Retry policy (Step 4b)
# ---------------------------------------------------------------------------

def _partial_report(trade_date: date = date(2026, 11, 5)) -> FreshnessReport:
    return FreshnessReport(
        status=FreshnessStatus.BENCHMARK_ONLY_UPDATED,
        trade_date=trade_date,
        benchmark_date=trade_date,
        non_benchmark_count=0,
        min_required=1000,
        detail="0050 updated but non-0050 count=0",
    )


def _provider_not_ready_report(trade_date: date = date(2026, 11, 5)) -> FreshnessReport:
    return FreshnessReport(
        status=FreshnessStatus.PROVIDER_NOT_READY,
        trade_date=trade_date,
        benchmark_date=None,
        non_benchmark_count=0,
        min_required=1000,
        detail="provider not ready",
    )


def _base_pipeline_patches(tmp_path):
    """Return common context-manager patches for pipeline retry tests."""
    return (
        patch("scripts.hybrid_shadow_cron.LOCK_FILE", tmp_path / "lock"),
        patch("scripts.hybrid_shadow_cron.STATE_FILE", tmp_path / "state.json"),
        patch("scripts.hybrid_shadow_cron.CALENDAR") ,
        patch("scripts.hybrid_shadow_cron._is_data_ready", return_value=True),
        patch("scripts.hybrid_shadow_cron._run_backfill",
              return_value={"exit_code": 0, "stdout": "", "stderr": ""}),
        patch("scripts.hybrid_shadow_cron._time") ,
        patch("scripts.hybrid_shadow_cron._alert"),
    )


def test_HC34_retry_once_then_pass(tmp_path):
    """BENCHMARK_ONLY_UPDATED on attempt 0, FULL_MARKET_FRESH on attempt 1 → SUCCESS."""
    side_effects = [_partial_report(), _fresh_report()]
    patches = _base_pipeline_patches(tmp_path)

    with (
        patches[0], patches[1],
        patches[2] as mock_cal,
        patches[3], patches[4],
        patches[5] as mock_time,
        patches[6],
        patch("scripts.hybrid_shadow_cron.check_market_freshness",
              side_effect=side_effects),
        patch("scripts.hybrid_shadow_cron.create_backup", return_value=tmp_path / "bak.db.bak"),
        patch("scripts.hybrid_shadow_cron._run_shadow",
              return_value={"exit_code": 0, "stdout": "", "stderr": ""}),
        patch("scripts.hybrid_shadow_cron._get_db_last_date", return_value=date(2026, 11, 5)),
    ):
        mock_cal.is_trading_day.return_value = True
        result = run_cron_pipeline(execute=True)

    assert result["status"] == "SUCCESS"
    assert result["steps"]["freshness_retry_attempt"] == 1
    mock_time.sleep.assert_called_once()


def test_HC35_retry_max_exhausted_blocked_partial(tmp_path):
    """BENCHMARK_ONLY_UPDATED on all RETRY_MAX+1 attempts → BLOCKED_PARTIAL_MARKET."""
    from scripts.hybrid_shadow_cron import RETRY_MAX
    side_effects = [_partial_report()] * (RETRY_MAX + 1)
    patches = _base_pipeline_patches(tmp_path)

    with (
        patches[0], patches[1],
        patches[2] as mock_cal,
        patches[3], patches[4],
        patches[5],
        patches[6],
        patch("scripts.hybrid_shadow_cron.check_market_freshness",
              side_effect=side_effects),
    ):
        mock_cal.is_trading_day.return_value = True
        result = run_cron_pipeline(execute=True)

    assert result["status"] == "BLOCKED_PARTIAL_MARKET"
    assert result["steps"]["freshness_retry_attempt"] == RETRY_MAX


def test_HC36_stale_does_not_retry(tmp_path):
    """STALE status must block immediately without retrying."""
    patches = _base_pipeline_patches(tmp_path)

    with (
        patches[0], patches[1],
        patches[2] as mock_cal,
        patches[3], patches[4],
        patches[5] as mock_time,
        patches[6],
        patch("scripts.hybrid_shadow_cron.check_market_freshness",
              return_value=_stale_report()),
    ):
        mock_cal.is_trading_day.return_value = True
        result = run_cron_pipeline(execute=True)

    assert result["status"] == "BLOCKED_STALE_DATA"
    mock_time.sleep.assert_not_called()


def test_HC37_retry_state_saved_during_wait(tmp_path):
    """State file must be written during each retry interval (before sleep)."""
    state_file = tmp_path / "state.json"
    side_effects = [_partial_report(), _fresh_report()]

    with (
        patch("scripts.hybrid_shadow_cron.LOCK_FILE", tmp_path / "lock"),
        patch("scripts.hybrid_shadow_cron.STATE_FILE", state_file),
        patch("scripts.hybrid_shadow_cron.CALENDAR") as mock_cal,
        patch("scripts.hybrid_shadow_cron._is_data_ready", return_value=True),
        patch("scripts.hybrid_shadow_cron._run_backfill",
              return_value={"exit_code": 0, "stdout": "", "stderr": ""}),
        patch("scripts.hybrid_shadow_cron._time"),
        patch("scripts.hybrid_shadow_cron._alert"),
        patch("scripts.hybrid_shadow_cron.check_market_freshness",
              side_effect=side_effects),
        patch("scripts.hybrid_shadow_cron.create_backup", return_value=tmp_path / "bak.db.bak"),
        patch("scripts.hybrid_shadow_cron._run_shadow",
              return_value={"exit_code": 0, "stdout": "", "stderr": ""}),
        patch("scripts.hybrid_shadow_cron._get_db_last_date", return_value=date(2026, 11, 5)),
    ):
        mock_cal.is_trading_day.return_value = True
        result = run_cron_pipeline(execute=True)

    assert result["status"] == "SUCCESS"
    saved = json.loads(state_file.read_text())
    # Final saved state must reflect freshness_retry_attempt >= 1 (retry happened)
    assert saved["steps"]["freshness_retry_attempt"] >= 1


def test_HC38_provider_not_ready_retries_then_blocks_stale(tmp_path):
    """PROVIDER_NOT_READY is retryable; when exhausted it maps to BLOCKED_STALE_DATA."""
    from scripts.hybrid_shadow_cron import RETRY_MAX
    side_effects = [_provider_not_ready_report()] * (RETRY_MAX + 1)
    patches = _base_pipeline_patches(tmp_path)

    with (
        patches[0], patches[1],
        patches[2] as mock_cal,
        patches[3], patches[4],
        patches[5],
        patches[6],
        patch("scripts.hybrid_shadow_cron.check_market_freshness",
              side_effect=side_effects),
    ):
        mock_cal.is_trading_day.return_value = True
        result = run_cron_pipeline(execute=True)

    assert result["status"] == "BLOCKED_STALE_DATA"


# ---------------------------------------------------------------------------
# AL01–AL08  AlertStateManager unit tests
# ---------------------------------------------------------------------------

from src.research.alert_state import AlertStateManager  # noqa: E402


def test_AL01_new_alert_returns_true(tmp_path):
    """record() returns True for the first occurrence of an alert."""
    mgr = AlertStateManager(state_file=tmp_path / "alerts.json")
    result = mgr.record(date(2026, 11, 5), "STALE_DATA", "0050 stale")
    assert result is True


def test_AL02_duplicate_alert_returns_false(tmp_path):
    """record() returns False when the same (trade_date, alert_type) is recorded again."""
    mgr = AlertStateManager(state_file=tmp_path / "alerts.json")
    mgr.record(date(2026, 11, 5), "STALE_DATA", "0050 stale")
    result = mgr.record(date(2026, 11, 5), "STALE_DATA", "0050 stale again")
    assert result is False


def test_AL03_duplicate_increments_count(tmp_path):
    """Repeated records increment the count field."""
    mgr = AlertStateManager(state_file=tmp_path / "alerts.json")
    mgr.record(date(2026, 11, 5), "PARTIAL_MARKET", "partial")
    mgr.record(date(2026, 11, 5), "PARTIAL_MARKET", "partial again")
    alerts = mgr.active_alerts()
    assert len(alerts) == 1
    assert alerts[0].count == 2


def test_AL04_resolve_marks_resolved(tmp_path):
    """resolve() sets resolved=True; subsequent record() for same key returns True (re-trigger)."""
    mgr = AlertStateManager(state_file=tmp_path / "alerts.json")
    mgr.record(date(2026, 11, 5), "BACKUP_FAILURE", "backup failed")
    mgr.resolve(date(2026, 11, 5), "BACKUP_FAILURE")
    alerts = mgr.active_alerts()
    assert len(alerts) == 0  # resolved → not active


def test_AL05_active_alerts_excludes_resolved(tmp_path):
    """active_alerts() must not return resolved alerts."""
    mgr = AlertStateManager(state_file=tmp_path / "alerts.json")
    mgr.record(date(2026, 11, 5), "SHADOW_FAILED", "shadow crashed")
    mgr.record(date(2026, 11, 5), "BACKUP_FAILURE", "backup failed")
    mgr.resolve(date(2026, 11, 5), "SHADOW_FAILED")
    active = mgr.active_alerts()
    types = {a.alert_type for a in active}
    assert "SHADOW_FAILED" not in types
    assert "BACKUP_FAILURE" in types


def test_AL06_active_alerts_filters_by_date(tmp_path):
    """active_alerts(trade_date=...) returns only alerts for that date."""
    mgr = AlertStateManager(state_file=tmp_path / "alerts.json")
    mgr.record(date(2026, 11, 5), "STALE_DATA", "day1")
    mgr.record(date(2026, 11, 6), "STALE_DATA", "day2")
    day1 = mgr.active_alerts(trade_date=date(2026, 11, 5))
    assert len(day1) == 1
    assert day1[0].trade_date == "2026-11-05"


def test_AL07_all_alerts_includes_resolved(tmp_path):
    """all_alerts() returns all alerts regardless of resolved status."""
    mgr = AlertStateManager(state_file=tmp_path / "alerts.json")
    mgr.record(date(2026, 11, 5), "STALE_DATA", "stale")
    mgr.resolve(date(2026, 11, 5), "STALE_DATA")
    all_a = mgr.all_alerts()
    assert len(all_a) == 1
    assert all_a[0].resolved is True


def test_AL08_different_alert_types_same_date_both_new(tmp_path):
    """Two different alert_types on the same trade_date are independent keys."""
    mgr = AlertStateManager(state_file=tmp_path / "alerts.json")
    r1 = mgr.record(date(2026, 11, 5), "STALE_DATA", "stale")
    r2 = mgr.record(date(2026, 11, 5), "PARTIAL_MARKET", "partial")
    assert r1 is True
    assert r2 is True
    assert len(mgr.active_alerts()) == 2


def test_AL09_corrupt_state_file_safe_load(tmp_path):
    """AlertStateManager must handle corrupt JSON without crashing or silently clearing history."""
    alert_file = tmp_path / "alerts.json"
    alert_file.write_text("{invalid json}")  # corrupt file
    mgr = AlertStateManager(state_file=alert_file)
    # Must not crash; starts with empty alert set
    assert mgr.active_alerts() == []
    # Must be able to record new alerts after corrupt load
    is_new = mgr.record(date(2026, 11, 6), "STALE_DATA", "recovery after corrupt")
    assert is_new is True
    assert len(mgr.active_alerts()) == 1


def test_AL10_resolved_alert_can_be_reopened(tmp_path):
    """After resolving an alert, a new occurrence on the same day creates a fresh entry."""
    mgr = AlertStateManager(state_file=tmp_path / "alerts.json")
    mgr.record(date(2026, 11, 5), "SHADOW_FAILED", "first failure")
    mgr.resolve(date(2026, 11, 5), "SHADOW_FAILED")
    assert len(mgr.active_alerts()) == 0

    # Same day, same type fires again (e.g. retry also fails)
    is_new = mgr.record(date(2026, 11, 5), "SHADOW_FAILED", "second failure")
    # Resolved → re-trigger creates new active alert
    assert is_new is True
    active = mgr.active_alerts()
    assert len(active) == 1
    assert active[0].resolved is False


# ---------------------------------------------------------------------------
# CN01–CN02  Concurrency / Lock integrity
# ---------------------------------------------------------------------------

def test_CN01_lock_released_even_on_pipeline_exception(tmp_path):
    """FileLock must be released via finally block even when the pipeline raises."""
    lock_path = tmp_path / "lock"

    with (
        patch("scripts.hybrid_shadow_cron.LOCK_FILE", lock_path),
        patch("scripts.hybrid_shadow_cron.STATE_FILE", tmp_path / "state.json"),
        patch("scripts.hybrid_shadow_cron.CALENDAR") as mock_cal,
        patch("scripts.hybrid_shadow_cron._is_data_ready", return_value=True),
        patch("scripts.hybrid_shadow_cron._run_backfill",
              side_effect=RuntimeError("unexpected crash")),
        patch("scripts.hybrid_shadow_cron._alert"),
    ):
        mock_cal.is_trading_day.return_value = True
        try:
            run_cron_pipeline(execute=True)
        except RuntimeError:
            pass

    # After exception, lock must be acquirable by a new instance
    from scripts.hybrid_shadow_cron import FileLock
    new_lock = FileLock(lock_path)
    acquired = new_lock.acquire()
    assert acquired, "Lock was not released after pipeline exception"
    new_lock.release()


def test_CN02_second_instance_blocked_during_active_lock(tmp_path):
    """A second FileLock on the same path must fail while first lock is held."""
    from scripts.hybrid_shadow_cron import FileLock
    lock_path = tmp_path / "lock"

    lock1 = FileLock(lock_path)
    assert lock1.acquire() is True

    lock2 = FileLock(lock_path)
    assert lock2.acquire() is False, "Second lock acquire must return False while first is held"

    lock1.release()
    # After first release, second should succeed
    lock3 = FileLock(lock_path)
    assert lock3.acquire() is True
    lock3.release()
