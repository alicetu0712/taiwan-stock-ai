"""
Pipeline Recovery Validation and 20D Calendar Contract Integration
— Session 49 PARTS D, E, F, G (P3–P6).

PART D: Temporary SQLite pipeline recovery scenarios (10 scenarios).
  Simulates 10 pipeline recovery cases in in-memory SQLite.
  Does NOT modify data/platform.db.

PART E: 20D Calendar Contract Integration.
  Creates a corrected calendar wrapper for prospective_comparison_s46.py.
  The original S46 module has 6/6 20D errors and 3/6 5D errors.
  This module provides corrected dates WITHOUT modifying the original S46 file.
  Corrected values are from calendar_contract_s48._CORRECT_5TD/_CORRECT_20TD.

PART F: Strict 5D Recovery Readiness per cluster.
  WAITING_FOR_BACKFILL if data needed is in source_verification P1 list.
  SOURCE_BLOCKED if source is UNIVERSE_UNVERIFIED.

PART G: 20D Authorization Readiness (AUTH01/AUTH02 package).
  AUTH01 = data backfill authorization (Oct 29/30/Nov 02/03)
  AUTH02 = 20D outcome computation authorization (after Nov 12)

SAFETY: READ-ONLY research. All scenario simulations use Temporary SQLite.
  prospective_comparison_s46.py is NOT modified.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class RecoveryScenario(str, Enum):
    PROXY_ONLY_INSERT = "PROXY_ONLY_INSERT"       # Existing 0050 row; insert ~655 more
    ZERO_ROW_INSERT = "ZERO_ROW_INSERT"            # Empty date; insert all from scratch
    PARTIAL_DATA_INSERT = "PARTIAL_DATA_INSERT"    # Mixed existing; selective insert
    CONFLICT_SKIP = "CONFLICT_SKIP"                # INSERT OR IGNORE; some rows skipped
    TSMC_PRESENT_POST_INSERT = "TSMC_PRESENT_POST_INSERT"   # TSMC appears after insert
    TSMC_ABSENT_POST_INSERT = "TSMC_ABSENT_POST_INSERT"     # TSMC still absent after insert
    QG_PASS_AFTER_INSERT = "QG_PASS_AFTER_INSERT"           # Stock count ≥ 300
    QG_FAIL_AFTER_INSERT = "QG_FAIL_AFTER_INSERT"           # Stock count < 300
    IDEMPOTENT_REPEAT = "IDEMPOTENT_REPEAT"                 # Repeat insert; 0 new rows
    CLUSTER_PROMOTION_ACHIEVED = "CLUSTER_PROMOTION_ACHIEVED"  # TSMC count crosses 5


class RecoveryVerdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    PARTIAL = "PARTIAL"


class CalendarCorrectionStatus(str, Enum):
    CORRECTED = "CORRECTED"      # S46 date was wrong; this module has correct date
    UNCHANGED = "UNCHANGED"      # S46 date was already correct
    NOT_IN_S46 = "NOT_IN_S46"    # Date not present in S46 module


class Readiness5DCluster(str, Enum):
    STRICT_ELIGIBLE = "STRICT_ELIGIBLE"
    WAITING_FOR_BACKFILL = "WAITING_FOR_BACKFILL"   # P1 backfill resolves this
    SOURCE_BLOCKED = "SOURCE_BLOCKED"               # Requires unresolved source
    PERMANENTLY_INCOMPLETE = "PERMANENTLY_INCOMPLETE"


class AuthorizationReadiness20D(str, Enum):
    AUTH01_PENDING = "AUTH01_PENDING"           # Backfill not yet authorized
    AUTH01_GRANTED_AUTH02_PENDING = "AUTH01_GRANTED_AUTH02_PENDING"
    AUTH02_GRANTED_READY = "AUTH02_GRANTED_READY"
    BLOCKED_PIPELINE = "BLOCKED_PIPELINE"       # Pipeline not restored
    BLOCKED_NO_DATA = "BLOCKED_NO_DATA"         # Exit date data unavailable
    NOT_YET_MATURE = "NOT_YET_MATURE"           # 20TD not yet reached


# ---------------------------------------------------------------------------
# Hard-coded corrected calendar data (from calendar_contract_s48)
# ---------------------------------------------------------------------------

# Corrected 5D dates (5th real trading day after fill_date)
_CORRECT_5TD: Dict[str, str] = {
    "2026-10-13": "2026-10-20",   # S46 had 2026-10-21 (CORRECTED)
    "2026-10-14": "2026-10-21",   # S46 had 2026-10-28 (CORRECTED)
    "2026-10-16": "2026-10-27",   # S46 had 2026-11-05 (CORRECTED)
    "2026-10-21": "2026-10-30",   # S46 correct (UNCHANGED)
    "2026-10-22": "2026-11-02",   # S46 correct (UNCHANGED)
    "2026-10-28": "2026-11-04",   # S46 correct (UNCHANGED)
}

# Corrected 20D dates (20th real trading day after fill_date)
_CORRECT_20TD: Dict[str, str] = {
    "2026-10-13": "2026-11-12",   # S46 had 2026-11-14 (CORRECTED, Δ=-2d)
    "2026-10-14": "2026-11-13",   # S46 had 2026-11-17 (CORRECTED, Δ=-4d)
    "2026-10-16": "2026-11-17",   # S46 had 2026-11-19 (CORRECTED, Δ=-2d)
    "2026-10-21": "2026-11-20",   # S46 had 2026-11-24 (CORRECTED, Δ=-4d)
    "2026-10-22": "2026-11-23",   # S46 had 2026-11-25 (CORRECTED, Δ=-2d)
    "2026-10-28": "2026-11-25",   # S46 had 2026-12-02 (CORRECTED, Δ=-7d)
}

# S46 original (erroneous) dates for reference
_S46_5TD: Dict[str, str] = {
    "2026-10-13": "2026-10-21",
    "2026-10-14": "2026-10-28",
    "2026-10-16": "2026-11-05",
    "2026-10-21": "2026-10-30",
    "2026-10-22": "2026-11-02",
    "2026-10-28": "2026-11-04",
}

_S46_20TD: Dict[str, str] = {
    "2026-10-13": "2026-11-14",
    "2026-10-14": "2026-11-17",
    "2026-10-16": "2026-11-19",
    "2026-10-21": "2026-11-24",
    "2026-10-22": "2026-11-25",
    "2026-10-28": "2026-12-02",
}

# 20D pipeline data requirements (which dates must have full price data)
_20D_EXIT_DATA_REQUIREMENTS: Dict[str, str] = {
    "2026-10-13": "2026-11-12",   # earliest exit; Nov 12 data needed
    "2026-10-14": "2026-11-13",
    "2026-10-16": "2026-11-17",
    "2026-10-21": "2026-11-20",
    "2026-10-22": "2026-11-23",
    "2026-10-28": "2026-11-25",
}

# Which fill dates are strict-eligible (proxy ≥ 5) WITHOUT backfill?
_CURRENT_STRICT_FILLS = {"2026-10-13", "2026-10-14", "2026-10-16"}
# Which fills need backfill of P1 dates to become strict?
_BACKFILL_DEPENDENT_FILLS = {
    "2026-10-21": ["2026-10-29"],
    "2026-10-22": ["2026-10-29", "2026-10-30"],
    "2026-10-28": ["2026-10-29", "2026-10-30", "2026-11-02"],
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class RecoveryScenarioResult:
    scenario_id: str
    scenario: RecoveryScenario
    description: str
    setup: str
    expected_outcome: str
    actual_outcome: str
    verdict: RecoveryVerdict
    notes: str


@dataclass
class PipelineRecoveryValidation:
    scenarios: List[RecoveryScenarioResult]
    n_pass: int
    n_fail: int
    n_partial: int
    validation_verdict: str
    temp_sqlite_isolation: bool


@dataclass
class CalendarCorrectionRecord:
    fill_date: str
    s46_5td: str
    correct_5td: str
    s46_20td: str
    correct_20td: str
    status_5td: CalendarCorrectionStatus
    status_20td: CalendarCorrectionStatus
    delta_5td_days: int
    delta_20td_days: int


@dataclass
class CalendarContractIntegration:
    """
    Corrected calendar contract for prospective_comparison_s46.py.
    Does NOT modify the original module. Provides corrected values as an
    overlay — callers should prefer these values over s46 hardcodes.
    """
    correction_records: List[CalendarCorrectionRecord]
    correct_5td: Dict[str, str]
    correct_20td: Dict[str, str]
    s46_5td_error_count: int
    s46_20td_error_count: int
    integration_note: str


@dataclass
class StrictClusterReadiness5D:
    fill_date: str
    current_proxy_count: int
    threshold: int
    readiness: Readiness5DCluster
    blocking_dates: List[str]
    notes: str


@dataclass
class AuthorizationItem20D:
    auth_id: str
    description: str
    status: AuthorizationReadiness20D
    prerequisites: List[str]
    earliest_execution_date: str
    notes: str


@dataclass
class Authorization20DPackage:
    auth01: AuthorizationItem20D
    auth02: AuthorizationItem20D
    overall_readiness: str
    earliest_20d_maturity: str
    days_until_first_maturity: int
    critical_path: List[str]


# ---------------------------------------------------------------------------
# PART D: Pipeline Recovery Validation (Temporary SQLite)
# ---------------------------------------------------------------------------

def _create_temp_schema(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_prices (
            date TEXT NOT NULL,
            stock_id TEXT NOT NULL,
            open REAL, high REAL, low REAL, close REAL, volume INTEGER,
            PRIMARY KEY (date, stock_id)
        )
    """)
    conn.commit()


def _run_scenario(
    scenario_id: str,
    scenario: RecoveryScenario,
    description: str,
    setup_fn,
    test_fn,
) -> RecoveryScenarioResult:
    """Run one scenario in isolated temp SQLite."""
    mem = sqlite3.connect(":memory:")
    _create_temp_schema(mem)

    setup_desc = setup_fn(mem)
    actual, verdict, notes = test_fn(mem)

    mem.close()
    return RecoveryScenarioResult(
        scenario_id=scenario_id,
        scenario=scenario,
        description=description,
        setup=setup_desc,
        expected_outcome=scenario.value,
        actual_outcome=actual,
        verdict=verdict,
        notes=notes,
    )


def run_pipeline_recovery_validation() -> PipelineRecoveryValidation:
    """
    Run 10 recovery scenarios in Temporary SQLite (READ-ONLY research).
    All in-memory; no production DB touched.
    """
    results: List[RecoveryScenarioResult] = []

    # SC01: PROXY_ONLY_INSERT — insert ~655 stocks into date with existing 0050
    def sc01_setup(c):
        c.execute("INSERT INTO daily_prices (date,stock_id,close) VALUES ('2026-10-29','0050',99.5)")
        c.commit()
        return "1 row (0050 proxy) pre-inserted for 2026-10-29"

    def sc01_test(c):
        # Simulate a realistic backfill batch: 1000-series codes avoid 0050 collision
        # IDs 1000-1653 = 654 stocks + TSMC (2330) = 655 new rows; 0050 duplicate skipped
        rows = [("2026-10-29", f"{i}", 100.0) for i in range(1000, 1654)]  # 654 stocks
        rows.append(("2026-10-29", "2330", 2415.0))  # TSMC
        rows.append(("2026-10-29", "0050", 99.5))    # duplicate; must be ignored
        for r in rows:
            c.execute("INSERT OR IGNORE INTO daily_prices (date,stock_id,close) VALUES (?,?,?)", r)
        c.commit()
        n = c.execute("SELECT COUNT(*) FROM daily_prices WHERE date='2026-10-29'").fetchone()[0]
        has_tsmc = c.execute("SELECT COUNT(*) FROM daily_prices WHERE date='2026-10-29' AND stock_id='2330'").fetchone()[0]
        actual = f"total={n}, has_tsmc={has_tsmc>0}"
        # 1 existing (0050) + 654 new + TSMC = 656 total; duplicate 0050 skipped
        verdict = RecoveryVerdict.PASS if n == 656 and has_tsmc > 0 else RecoveryVerdict.FAIL
        return actual, verdict, "0050 proxy preserved; 655 new stocks inserted including TSMC"

    results.append(_run_scenario("SC01", RecoveryScenario.PROXY_ONLY_INSERT,
                                  "Insert 655 stocks into proxy-only date (Oct 29)", sc01_setup, sc01_test))

    # SC02: ZERO_ROW_INSERT — insert into completely empty date (Nov 06 simulation)
    def sc02_setup(c):
        return "No pre-existing rows for 2026-11-06"

    def sc02_test(c):
        rows = [("2026-11-06", f"{i:04d}", 50.0) for i in range(1, 300)]
        for r in rows:
            c.execute("INSERT OR IGNORE INTO daily_prices (date,stock_id,close) VALUES (?,?,?)", r)
        c.commit()
        n = c.execute("SELECT COUNT(*) FROM daily_prices WHERE date='2026-11-06'").fetchone()[0]
        actual = f"total={n}"
        verdict = RecoveryVerdict.PASS if n == 299 else RecoveryVerdict.FAIL
        return actual, verdict, "Fresh insert into empty date"

    results.append(_run_scenario("SC02", RecoveryScenario.ZERO_ROW_INSERT,
                                  "Insert 299 stocks into empty date (Nov 06 sim)", sc02_setup, sc02_test))

    # SC03: CONFLICT_SKIP — INSERT OR IGNORE skips existing rows
    def sc03_setup(c):
        c.execute("INSERT INTO daily_prices (date,stock_id,close) VALUES ('2026-10-30','0050',99.0)")
        c.execute("INSERT INTO daily_prices (date,stock_id,close) VALUES ('2026-10-30','2330',2370.0)")
        c.commit()
        return "2 rows pre-inserted: 0050 and 2330"

    def sc03_test(c):
        # Attempt to insert same rows again
        for stock, price in [("0050", 99.0), ("2330", 2370.0), ("2454", 1500.0)]:
            c.execute("INSERT OR IGNORE INTO daily_prices (date,stock_id,close) VALUES ('2026-10-30',?,?)",
                      (stock, price))
        c.commit()
        n = c.execute("SELECT COUNT(*) FROM daily_prices WHERE date='2026-10-30'").fetchone()[0]
        actual = f"total={n}"
        verdict = RecoveryVerdict.PASS if n == 3 else RecoveryVerdict.FAIL
        return actual, verdict, "Existing rows skipped; only new stock 2454 inserted"

    results.append(_run_scenario("SC03", RecoveryScenario.CONFLICT_SKIP,
                                  "INSERT OR IGNORE conflict skip test", sc03_setup, sc03_test))

    # SC04: IDEMPOTENT_REPEAT — repeat insert; second batch adds 0 rows
    def sc04_setup(c):
        return "Empty DB; Oct 29 date"

    def sc04_test(c):
        rows = [("2026-10-29", "0050", 99.5), ("2026-10-29", "2330", 2415.0), ("2026-10-29", "2454", 1520.0)]
        c1 = sum(c.execute("INSERT OR IGNORE INTO daily_prices (date,stock_id,close) VALUES (?,?,?)",r).rowcount for r in rows)
        c.commit()
        c2 = sum(c.execute("INSERT OR IGNORE INTO daily_prices (date,stock_id,close) VALUES (?,?,?)",r).rowcount for r in rows)
        c.commit()
        actual = f"first={c1}, second={c2}"
        verdict = RecoveryVerdict.PASS if c1 == 3 and c2 == 0 else RecoveryVerdict.FAIL
        return actual, verdict, "Idempotent: second insert adds 0 rows"

    results.append(_run_scenario("SC04", RecoveryScenario.IDEMPOTENT_REPEAT,
                                  "Idempotency: repeat insert adds 0 rows", sc04_setup, sc04_test))

    # SC05: TSMC_PRESENT_POST_INSERT — TSMC appears after backfill
    def sc05_setup(c):
        c.execute("INSERT INTO daily_prices (date,stock_id,close) VALUES ('2026-10-29','0050',99.5)")
        c.commit()
        return "0050 only; TSMC absent before insert"

    def sc05_test(c):
        before = c.execute("SELECT COUNT(*) FROM daily_prices WHERE date='2026-10-29' AND stock_id='2330'").fetchone()[0]
        c.execute("INSERT OR IGNORE INTO daily_prices (date,stock_id,close) VALUES ('2026-10-29','2330',2415.0)")
        c.commit()
        after = c.execute("SELECT COUNT(*) FROM daily_prices WHERE date='2026-10-29' AND stock_id='2330'").fetchone()[0]
        actual = f"before={before}, after={after}"
        verdict = RecoveryVerdict.PASS if before == 0 and after == 1 else RecoveryVerdict.FAIL
        return actual, verdict, "TSMC presence confirmed after backfill"

    results.append(_run_scenario("SC05", RecoveryScenario.TSMC_PRESENT_POST_INSERT,
                                  "TSMC (2330) presence verified after Oct 29 insert", sc05_setup, sc05_test))

    # SC06: TSMC_ABSENT_POST_INSERT — verify TSMC is absent when not in batch
    def sc06_setup(c):
        return "Empty DB; partial batch without 2330"

    def sc06_test(c):
        rows = [("2026-10-29", "0050", 99.5), ("2026-10-29", "2454", 1520.0)]
        for r in rows:
            c.execute("INSERT OR IGNORE INTO daily_prices (date,stock_id,close) VALUES (?,?,?)", r)
        c.commit()
        has_tsmc = c.execute("SELECT COUNT(*) FROM daily_prices WHERE date='2026-10-29' AND stock_id='2330'").fetchone()[0]
        actual = f"tsmc_present={has_tsmc}"
        verdict = RecoveryVerdict.PASS if has_tsmc == 0 else RecoveryVerdict.FAIL
        return actual, verdict, "Correctly detects TSMC absent when not in insert batch"

    results.append(_run_scenario("SC06", RecoveryScenario.TSMC_ABSENT_POST_INSERT,
                                  "TSMC absent when not included in backfill batch", sc06_setup, sc06_test))

    # SC07: QG_PASS_AFTER_INSERT — stock count ≥ 300 after insert
    def sc07_setup(c):
        return "Empty DB for 2026-10-30"

    def sc07_test(c):
        for i in range(1, 401):
            c.execute("INSERT OR IGNORE INTO daily_prices (date,stock_id,close) VALUES ('2026-10-30',?,?)",
                      (f"{i:04d}", 100.0))
        c.commit()
        n = c.execute("SELECT COUNT(DISTINCT stock_id) FROM daily_prices WHERE date='2026-10-30'").fetchone()[0]
        qg_pass = n >= 300
        actual = f"count={n}, qg_pass={qg_pass}"
        verdict = RecoveryVerdict.PASS if qg_pass else RecoveryVerdict.FAIL
        return actual, verdict, "Quality gate passes (≥300 stocks)"

    results.append(_run_scenario("SC07", RecoveryScenario.QG_PASS_AFTER_INSERT,
                                  "Quality gate: ≥300 stocks after Oct 30 backfill", sc07_setup, sc07_test))

    # SC08: QG_FAIL_AFTER_INSERT — stock count < 300 (simulates partial batch)
    def sc08_setup(c):
        return "Empty DB; simulate partial 100-stock batch"

    def sc08_test(c):
        for i in range(1, 101):
            c.execute("INSERT OR IGNORE INTO daily_prices (date,stock_id,close) VALUES ('2026-11-06',?,?)",
                      (f"{i:04d}", 50.0))
        c.commit()
        n = c.execute("SELECT COUNT(DISTINCT stock_id) FROM daily_prices WHERE date='2026-11-06'").fetchone()[0]
        qg_fail = n < 300
        actual = f"count={n}, qg_fail={qg_fail}"
        verdict = RecoveryVerdict.PASS if qg_fail else RecoveryVerdict.FAIL
        return actual, verdict, "Quality gate fails (100 < 300 stocks); UNIVERSE_UNVERIFIED"

    results.append(_run_scenario("SC08", RecoveryScenario.QG_FAIL_AFTER_INSERT,
                                  "Quality gate: <300 stocks (simulates UNIVERSE_UNVERIFIED)", sc08_setup, sc08_test))

    # SC09: PARTIAL_DATA_INSERT — mixed existing rows, selective insert
    def sc09_setup(c):
        # Pre-insert 50 stocks
        for i in range(1, 51):
            c.execute("INSERT INTO daily_prices (date,stock_id,close) VALUES ('2026-11-02',?,?)",
                      (f"{i:04d}", 100.0))
        c.commit()
        return "50 rows pre-existing for 2026-11-02"

    def sc09_test(c):
        before = c.execute("SELECT COUNT(*) FROM daily_prices WHERE date='2026-11-02'").fetchone()[0]
        # Insert 655 total; 50 overlap → 605 new rows
        inserted = 0
        for i in range(1, 656):
            cur = c.execute("INSERT OR IGNORE INTO daily_prices (date,stock_id,close) VALUES ('2026-11-02',?,?)",
                            (f"{i:04d}", 100.0))
            inserted += cur.rowcount
        c.commit()
        after = c.execute("SELECT COUNT(*) FROM daily_prices WHERE date='2026-11-02'").fetchone()[0]
        actual = f"before={before}, inserted={inserted}, after={after}"
        verdict = RecoveryVerdict.PASS if before == 50 and inserted == 605 and after == 655 else RecoveryVerdict.FAIL
        return actual, verdict, "Partial pre-existing: 50 skipped, 605 inserted, 655 total"

    results.append(_run_scenario("SC09", RecoveryScenario.PARTIAL_DATA_INSERT,
                                  "Partial pre-existing data; selective insert Nov 02", sc09_setup, sc09_test))

    # SC10: CLUSTER_PROMOTION_ACHIEVED — TSMC count crosses 5 after backfill
    def sc10_setup(c):
        # Simulate: Oct 28 fill, only 2 TSMC dates exist (Nov 04/05)
        for d in ["2026-11-04", "2026-11-05"]:
            c.execute("INSERT INTO daily_prices (date,stock_id,close) VALUES (?,'2330',2500.0)", (d,))
        c.commit()
        return "2 TSMC dates exist (Nov 04/05); proxy_count=2 for Oct 28"

    def sc10_test(c):
        # Count TSMC dates after Oct 28 before backfill
        before = c.execute("SELECT COUNT(*) FROM daily_prices WHERE stock_id='2330' AND date > '2026-10-28'").fetchone()[0]
        # Add Oct 29/30/Nov 02 TSMC data (simulating backfill)
        for d, price in [("2026-10-29", 2415.0), ("2026-10-30", 2370.0), ("2026-11-02", 2390.0)]:
            c.execute("INSERT OR IGNORE INTO daily_prices (date,stock_id,close) VALUES (?,'2330',?)", (d, price))
        c.commit()
        after = c.execute("SELECT COUNT(*) FROM daily_prices WHERE stock_id='2330' AND date > '2026-10-28'").fetchone()[0]
        promoted = after >= 5
        actual = f"before_proxy={before}, after_proxy={after}, promoted={promoted}"
        verdict = RecoveryVerdict.PASS if before == 2 and after == 5 and promoted else RecoveryVerdict.FAIL
        return actual, verdict, "Oct 28 cluster proxy 2→5; STRICT_ELIGIBLE achieved"

    results.append(_run_scenario("SC10", RecoveryScenario.CLUSTER_PROMOTION_ACHIEVED,
                                  "Oct 28 cluster promotion: proxy 2→5 via backfill", sc10_setup, sc10_test))

    n_pass = sum(1 for r in results if r.verdict == RecoveryVerdict.PASS)
    n_fail = sum(1 for r in results if r.verdict == RecoveryVerdict.FAIL)
    n_partial = sum(1 for r in results if r.verdict == RecoveryVerdict.PARTIAL)

    verdict_str = "ALL_PASS" if n_fail == 0 else f"PARTIAL ({n_pass}/10 PASS)"

    return PipelineRecoveryValidation(
        scenarios=results,
        n_pass=n_pass,
        n_fail=n_fail,
        n_partial=n_partial,
        validation_verdict=verdict_str,
        temp_sqlite_isolation=True,
    )


# ---------------------------------------------------------------------------
# PART E: 20D Calendar Contract Integration
# ---------------------------------------------------------------------------

def _days_between(d1: str, d2: str) -> int:
    """Calendar days difference (d2 - d1). Negative = d2 is earlier."""
    from datetime import date
    a = date.fromisoformat(d1)
    b = date.fromisoformat(d2)
    return (b - a).days


def build_calendar_contract_integration() -> CalendarContractIntegration:
    """
    Build corrected calendar contract for prospective_comparison_s46.py.
    Original S46 module NOT modified.
    """
    records = []
    n_5td_errors = 0
    n_20td_errors = 0

    for fd in sorted(_CORRECT_5TD.keys()):
        s46_5 = _S46_5TD[fd]
        cor_5 = _CORRECT_5TD[fd]
        s46_20 = _S46_20TD[fd]
        cor_20 = _CORRECT_20TD[fd]

        status_5 = CalendarCorrectionStatus.UNCHANGED if s46_5 == cor_5 else CalendarCorrectionStatus.CORRECTED
        status_20 = CalendarCorrectionStatus.UNCHANGED if s46_20 == cor_20 else CalendarCorrectionStatus.CORRECTED

        if status_5 == CalendarCorrectionStatus.CORRECTED:
            n_5td_errors += 1
        if status_20 == CalendarCorrectionStatus.CORRECTED:
            n_20td_errors += 1

        delta_5 = _days_between(s46_5, cor_5)
        delta_20 = _days_between(s46_20, cor_20)

        records.append(CalendarCorrectionRecord(
            fill_date=fd,
            s46_5td=s46_5,
            correct_5td=cor_5,
            s46_20td=s46_20,
            correct_20td=cor_20,
            status_5td=status_5,
            status_20td=status_20,
            delta_5td_days=delta_5,
            delta_20td_days=delta_20,
        ))

    return CalendarContractIntegration(
        correction_records=records,
        correct_5td=dict(_CORRECT_5TD),
        correct_20td=dict(_CORRECT_20TD),
        s46_5td_error_count=n_5td_errors,
        s46_20td_error_count=n_20td_errors,
        integration_note=(
            f"S46 had {n_5td_errors}/6 5TD errors and {n_20td_errors}/6 20TD errors. "
            "This module provides corrected values as an overlay. "
            "prospective_comparison_s46.py was NOT modified. "
            "Callers should use correct_5td/correct_20td from this module "
            "instead of _CALENDAR_5TD/_CALENDAR_20TD from S46."
        ),
    )


def get_corrected_calendar_exit(fill_date: str, holding_period: int = 5) -> Optional[str]:
    """Return corrected exit date for a fill. holding_period: 5 or 20."""
    if holding_period == 5:
        return _CORRECT_5TD.get(fill_date)
    if holding_period == 20:
        return _CORRECT_20TD.get(fill_date)
    return None


# ---------------------------------------------------------------------------
# PART F: Strict 5D Recovery Readiness per cluster
# ---------------------------------------------------------------------------

def build_strict_recovery_readiness(
    backfill_complete_dates: Optional[List[str]] = None,
) -> List[StrictClusterReadiness5D]:
    """
    Returns strictness readiness per cluster.
    backfill_complete_dates: dates that have been successfully backfilled (optional).
    Without backfill, Oct 21/22/28 remain WAITING_FOR_BACKFILL.
    """
    completed = set(backfill_complete_dates or [])

    base_proxy = {
        "2026-10-13": 7, "2026-10-14": 6, "2026-10-16": 5,
        "2026-10-21": 4, "2026-10-22": 3, "2026-10-28": 2,
    }

    # Recompute proxy counts if backfill_complete_dates provided
    if completed:
        # Add completed dates to TSMC date set
        existing_tsmc = {
            "2026-10-13", "2026-10-14", "2026-10-16",
            "2026-10-21", "2026-10-22", "2026-10-28",
            "2026-11-04", "2026-11-05",
        }
        all_tsmc = existing_tsmc | completed
        for fd in list(base_proxy.keys()):
            base_proxy[fd] = sum(1 for d in all_tsmc if d > fd)

    results = []
    for fd in ["2026-10-13", "2026-10-14", "2026-10-16",
               "2026-10-21", "2026-10-22", "2026-10-28"]:
        cnt = base_proxy[fd]
        if cnt >= 5:
            readiness = Readiness5DCluster.STRICT_ELIGIBLE
            blocking = []
            notes = f"STRICT: proxy_count={cnt} ≥ 5"
        elif fd in _BACKFILL_DEPENDENT_FILLS:
            needed = _BACKFILL_DEPENDENT_FILLS[fd]
            missing_needed = [d for d in needed if d not in completed]
            if not missing_needed:
                readiness = Readiness5DCluster.STRICT_ELIGIBLE
                blocking = []
                notes = f"STRICT (after backfill): proxy_count={cnt}"
            else:
                readiness = Readiness5DCluster.WAITING_FOR_BACKFILL
                blocking = missing_needed
                notes = (
                    f"INCOMPLETE: proxy_count={cnt}/5. "
                    f"Need backfill of: {', '.join(missing_needed)}"
                )
        else:
            readiness = Readiness5DCluster.SOURCE_BLOCKED
            blocking = []
            notes = "Cannot promote without resolving UNIVERSE_UNVERIFIED source"

        results.append(StrictClusterReadiness5D(
            fill_date=fd,
            current_proxy_count=cnt,
            threshold=5,
            readiness=readiness,
            blocking_dates=blocking,
            notes=notes,
        ))

    return results


# ---------------------------------------------------------------------------
# PART G: 20D Authorization Readiness (AUTH01/AUTH02)
# ---------------------------------------------------------------------------

def build_20d_authorization_readiness(
    analysis_date: str = "2026-11-09",
    auth01_granted: bool = False,
    auth02_granted: bool = False,
    pipeline_restored: bool = False,
) -> Authorization20DPackage:
    """
    Build AUTH01 (backfill) + AUTH02 (20D computation) authorization readiness.
    """
    earliest_20d = "2026-11-12"  # Oct 13 fill → 20TD

    from datetime import date
    today = date.fromisoformat(analysis_date)
    maturity = date.fromisoformat(earliest_20d)
    days_until = (maturity - today).days

    if auth01_granted:
        auth01_status = AuthorizationReadiness20D.AUTH01_GRANTED_AUTH02_PENDING
    else:
        auth01_status = AuthorizationReadiness20D.AUTH01_PENDING

    if not pipeline_restored:
        auth02_status = AuthorizationReadiness20D.BLOCKED_PIPELINE
    elif days_until > 0:
        auth02_status = AuthorizationReadiness20D.NOT_YET_MATURE
    elif auth02_granted:
        auth02_status = AuthorizationReadiness20D.AUTH02_GRANTED_READY
    else:
        auth02_status = AuthorizationReadiness20D.AUTH01_GRANTED_AUTH02_PENDING

    auth01 = AuthorizationItem20D(
        auth_id="AUTH01",
        description="Backfill Oct 29/30/Nov 02/03 into local SQLite (not Neon)",
        status=auth01_status,
        prerequisites=[
            "SAFETY-01: INSERT OR IGNORE idempotency verified",
            "SAFETY-02: Local SQLite only (not Neon)",
            "SAFETY-05: Use backfill_daily_prices.py with --research-only --execute",
            "QG validation must pass for each backfilled date",
        ],
        earliest_execution_date="2026-11-09",
        notes=(
            "9/11 dates are INSERT_ONLY_CANDIDATE (source verified). "
            "Nov 06/09 blocked (UNIVERSE_UNVERIFIED). "
            "If Oct 29/30/Nov 02/03 backfilled: strict count 3→6."
        ),
    )

    auth02 = AuthorizationItem20D(
        auth_id="AUTH02",
        description="Compute 20D return outcomes for Oct 13/14/16 fills",
        status=auth02_status,
        prerequisites=[
            "AUTH01 completed: pipeline restored, Nov 06–25 data available",
            "Nov 12 (earliest 20D exit) has ≥300 stocks in local SQLite",
            "Holding-period convention specified: calendar 20TD vs price-available 20TD",
            "No retrospective reconstruction — only genuine prospective data",
        ],
        earliest_execution_date=earliest_20d,
        notes=(
            f"Earliest exit: {earliest_20d} (Oct 13 fill). "
            f"Latest exit: 2026-11-25 (Oct 28 fill). "
            f"TODAY={analysis_date}; {days_until} calendar days until first maturity. "
            "G03/G04 guardrails still FAIL even with 20D data."
        ),
    )

    critical_path = [
        "1. AUTHORIZE AUTH01: backfill Oct 29/30/Nov 02/03",
        "2. EXECUTE backfill; validate QG for each date",
        "3. RESTORE pipeline (fix QUALITY_GATE_FAIL + PROVIDER_NOT_READY)",
        "4. WAIT for Nov 12 (Oct 13 20D maturity)",
        "5. CONFIRM Nov 12–25 data in local SQLite (≥300 stocks)",
        "6. AUTHORIZE AUTH02: compute 20D outcomes",
        "7. NOTE: G03/G04 still FAIL — SIGNIFICANCE_INCONCLUSIVE persists",
    ]

    overall = "ACTIVATION_BLOCKED" if not (auth01_granted and auth02_granted and pipeline_restored) else "AUTHORIZED"

    return Authorization20DPackage(
        auth01=auth01,
        auth02=auth02,
        overall_readiness=overall,
        earliest_20d_maturity=earliest_20d,
        days_until_first_maturity=days_until,
        critical_path=critical_path,
    )
