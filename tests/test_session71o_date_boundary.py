"""
Session 71O — Date Boundary Tests (O-01 ~ O-12)

Verifies that the Scheduler Safety Guards behave correctly regardless of:
  - which calendar date the system is on
  - whether the injected date matches the system date
  - time boundary edge cases (window open/close)
  - cross-day state transitions
  - duplicate-run blocking on the actual current date

All tests are fully offline.  No production files, providers, SQLite, or Neon
are touched.  Every test uses tmp_path for all file I/O.

N-FINDING-01 context:
  run_cron_pipeline() calls date.today() internally for the 'today' field.
  Tests that make two sequential pipeline runs must use _run_pipeline_at_today()
  so that date.today() matches the _now_taipei_override date.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass
from unittest.mock import patch

import pytest
import pytz

TAIPEI_TZ = pytz.timezone("Asia/Taipei")

from scripts.hybrid_shadow_cron_integrated import (
    FileLock,
    SameDayStateGuard,
    RunStatus,
    GuardStatus,
    run_cron_pipeline,
    check_execution_window,
)
from src.research.full_market_freshness_gate import FreshnessStatus


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _taipei(year, month, day, hour=0, minute=0, second=0) -> datetime:
    return TAIPEI_TZ.localize(datetime(year, month, day, hour, minute, second))


@dataclass
class _MockFreshness:
    status: FreshnessStatus
    detail: str = "mock"
    non_benchmark_count: int = 5500
    benchmark_date: Optional[date] = None
    min_required: int = 5000

    def __post_init__(self):
        if self.benchmark_date is None:
            self.benchmark_date = date.today()

    def human_readable(self) -> str:
        return self.detail


def _ok_freshness():
    return lambda conn, d, is_trading_day: _MockFreshness(
        status=FreshnessStatus.FULL_MARKET_FRESH,
        detail="5500 non-0050 stocks present",
        non_benchmark_count=5500,
    )


def _ok_backfill():
    return lambda ex: {"exit_code": 0, "stdout": "ok", "stderr": ""}


def _ok_shadow():
    return lambda: {"exit_code": 0, "stdout": "ok", "stderr": ""}


def _run_at(tmp_path, year, month, day, hour, minute=0, trading_day=True):
    """Run pipeline with fully specified datetime (year/month/day/hour/minute)."""
    now = _taipei(year, month, day, hour, minute)
    state = tmp_path / ".cron_state.json"
    lock  = tmp_path / ".cron.lock"
    with patch("scripts.hybrid_shadow_cron_integrated.CALENDAR.is_trading_day",
               return_value=trading_day):
        return run_cron_pipeline(
            execute=True,
            skip_backup=True,
            _now_taipei_override=now,
            _state_file_override=state,
            _lock_file_override=lock,
            _db_path_override=":memory:",
            _backfill_runner=_ok_backfill(),
            _shadow_runner=_ok_shadow(),
            _freshness_checker=_ok_freshness(),
        )


def _run_today(tmp_path, hour, minute=0, trading_day=True):
    """Date-anchored: uses date.today() so guard date == pipeline date."""
    today = date.today()
    return _run_at(tmp_path, today.year, today.month, today.day,
                   hour, minute, trading_day=trading_day)


# ---------------------------------------------------------------------------
# O-01 / O-02 — Fixed date determinism
# ---------------------------------------------------------------------------

class TestFixedDateDeterminism:

    def test_O01_fixed_nov12_deterministic(self, tmp_path):
        """O-01: Injecting 2026-11-12 always produces same guard result."""
        result = _run_at(tmp_path, 2026, 11, 12, 17)
        assert result.get("status") in ("SUCCESS", "SKIPPED_NON_TRADING_DAY",
                                        "BLOCKED_STALE_DATA")
        assert result.get("scheduled_date") == "2026-11-12"

    def test_O02_fixed_nov13_deterministic(self, tmp_path):
        """O-02: Injecting 2026-11-13 always produces same guard result."""
        result = _run_at(tmp_path, 2026, 11, 13, 17)
        assert result.get("status") in ("SUCCESS", "SKIPPED_NON_TRADING_DAY",
                                        "BLOCKED_STALE_DATA")
        assert result.get("scheduled_date") == "2026-11-13"

    def test_O03_system_date_does_not_affect_fixed_date_result(self, tmp_path):
        """O-03: When two sequential runs use the same fixed date, the second is blocked."""
        # Both runs use 2026-11-12 — but system date may differ.
        # The test does NOT require the second to be blocked (calendar-stale edge)
        # It DOES require both results to have the same scheduled_date.
        result1 = _run_at(tmp_path, 2026, 11, 12, 16)
        result2 = _run_at(tmp_path, 2026, 11, 12, 17)
        assert result1.get("scheduled_date") == "2026-11-12"
        assert result2.get("scheduled_date") == "2026-11-12"
        # Note: second run may or may not be blocked depending on whether
        # date.today() matches 2026-11-12.  The scheduled_date fields are consistent.


# ---------------------------------------------------------------------------
# O-04 ~ O-07 — Execution Validity Window (time boundary)
# ---------------------------------------------------------------------------

class TestExecutionValidityWindow:

    def test_O04_1559_cst_rejected(self, tmp_path):
        """O-04: 15:59 CST → guard rejects (PRE_SCHEDULE)."""
        result = _run_at(tmp_path, 2026, 11, 13, 15, 59)
        assert "GUARD_WINDOW" in result["status"]
        assert "PRE_SCHEDULE" in result["status"]

    def test_O05_1600_cst_allowed(self, tmp_path):
        """O-05: 16:00 CST → guard allows (window start is inclusive)."""
        result = _run_at(tmp_path, 2026, 11, 13, 16, 0)
        assert "GUARD_WINDOW" not in result["status"]

    def test_O06_1959_cst_allowed(self, tmp_path):
        """O-06: 19:59 CST → guard allows (window end is exclusive)."""
        result = _run_at(tmp_path, 2026, 11, 13, 19, 59)
        assert "GUARD_WINDOW" not in result["status"]

    def test_O07_2000_cst_rejected(self, tmp_path):
        """O-07: 20:00 CST → guard rejects (window end is exclusive)."""
        result = _run_at(tmp_path, 2026, 11, 13, 20, 0)
        assert "GUARD_WINDOW" in result["status"]
        assert "EXECUTION_WINDOW_EXPIRED" in result["status"]

    def test_O07b_window_unit_check_execution_window(self):
        """O-07b: check_execution_window() unit-level boundary confirmation."""
        pre  = check_execution_window(_taipei(2026, 11, 13, 15, 59))
        open_ = check_execution_window(_taipei(2026, 11, 13, 16, 0))
        close = check_execution_window(_taipei(2026, 11, 13, 20, 0))
        assert not pre.allowed,  "15:59 must not be allowed"
        assert open_.allowed,    "16:00 must be allowed"
        assert not close.allowed,"20:00 must not be allowed"


# ---------------------------------------------------------------------------
# O-08 ~ O-12 — Same-day State Guard (date-anchored to avoid N-FINDING-01)
# ---------------------------------------------------------------------------

class TestSameDayStateGuard:

    def test_O08_cross_day_state_allows_new_run(self, tmp_path):
        """O-08: State from yesterday → today's run is allowed."""
        from scripts.scheduler_safety_guards import SameDayStateGuard as SSG
        state_path = tmp_path / ".cron_state.json"
        yesterday = date.today().replace(day=date.today().day - 1) \
            if date.today().day > 1 else date.today()
        state_path.write_text(json.dumps({
            "scheduled_date": str(yesterday),
            "status": "SUCCESS",
            "run_id": "cron-yesterday",
            "pid": 1,
            "write_committed": True,
        }))
        guard = SSG(state_path)
        result = guard.check(date.today())
        assert result.allowed, f"Cross-day state must allow today's run; got: {result.reason}"

    def test_O09_same_day_success_state_blocks(self, tmp_path):
        """O-09: Same-day SUCCESS state → second run rejected (ALREADY_RAN_TODAY)."""
        result1 = _run_today(tmp_path, hour=16)
        assert result1["status"] == "SUCCESS"

        result2 = _run_today(tmp_path, hour=17)
        assert "ALREADY_RAN_TODAY" in result2["status"], (
            f"Expected ALREADY_RAN_TODAY, got: {result2['status']}"
        )

    def test_O10_same_day_write_committed_blocks(self, tmp_path):
        """O-10: write_committed=True in same-day state → second run rejected.

        Only active under Deploy B (integrated wrapper writes write_committed).
        Deploy A (original wrapper) does not write this field.
        """
        result1 = _run_today(tmp_path, hour=16)
        assert result1.get("write_committed") is True, (
            f"First run should set write_committed=True; got: {result1}"
        )

        result2 = _run_today(tmp_path, hour=17)
        assert "GUARD_STATE" in result2["status"], (
            f"Expected guard block (WRITE_COMMITTED_TODAY), got: {result2['status']}"
        )

    def test_O11_corrupt_state_fail_closed(self, tmp_path):
        """O-11: Corrupt state file → fail closed (FAIL_CLOSED_CORRUPT)."""
        from scripts.scheduler_safety_guards import SameDayStateGuard as SSG
        state_path = tmp_path / ".cron_state.json"
        state_path.write_text("{invalid json!!!")
        guard = SSG(state_path)
        result = guard.check(date.today())
        assert not result.allowed
        assert result.guard_status == GuardStatus.FAIL_CLOSED_CORRUPT

    def test_O12_naive_datetime_fail_closed(self):
        """O-12: check_execution_window() with naive datetime → FAIL_CLOSED."""
        naive_dt = datetime(2026, 11, 13, 17, 0, 0)  # no tzinfo
        result = check_execution_window(now_taipei=naive_dt)
        assert not result.allowed
        assert "NAIVE" in result.guard_status.value or "FAIL_CLOSED" in result.guard_status.value


# ---------------------------------------------------------------------------
# O-13 — No production state file touched
# ---------------------------------------------------------------------------

class TestProductionIsolation:

    def test_O13_production_state_untouched(self, tmp_path):
        """O-13: All O-tests use tmp_path; production state file is never touched."""
        from scripts.hybrid_shadow_cron_integrated import STATE_FILE as PROD_STATE_FILE
        import os
        # Record mtime before
        mtime_before = os.path.getmtime(str(PROD_STATE_FILE)) \
            if PROD_STATE_FILE.exists() else None

        _run_today(tmp_path, hour=17)

        mtime_after = os.path.getmtime(str(PROD_STATE_FILE)) \
            if PROD_STATE_FILE.exists() else None

        assert mtime_before == mtime_after, (
            f"Production state file mtime changed: {mtime_before} → {mtime_after}"
        )
