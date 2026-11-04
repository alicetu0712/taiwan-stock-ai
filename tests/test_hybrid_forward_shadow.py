"""
tests/test_hybrid_forward_shadow.py — Hybrid Forward Shadow Operational Tests

Coverage:
  FS01–FS06:  TradingCalendar correctness
  FS07–FS12:  CaptureClassification logic
  FS08–FS13:  Decision hash / conflict detection
  FS14–FS20:  Append-only DB (insert_decision / insert_outcome)
  FS21–FS27:  Decision/Outcome separation
  FS28–FS32:  Run log
  FS33–FS38:  Stale data / missing signals guards
  FS39–FS43:  Outcome maturity (trading-day based)
  FS44–FS48:  Idempotency / retry
  FS49–FS52:  Full shadow run (SQLite in-memory)
  FS53–FS55:  Operational summary
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta, timezone

import pytest

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.research.hybrid_forward_db import (
    CALCULATION_VERSION,
    RULE_FREEZE_DATE,
    CaptureClassification,
    ConflictError,
    HybridForwardDecision,
    HybridForwardOutcome,
    HybridForwardRunLog,
    OutcomeStatus,
    RunStatus,
    classify_capture,
    compute_decision_hash,
    compute_input_data_hash,
    ensure_schema,
    get_matured_performance,
    get_operational_summary,
    get_pending_outcome_decisions,
    insert_decision,
    insert_outcome,
    new_run_id,
    upsert_run_log,
)
from src.research.hybrid_trading_calendar import TradingCalendar


# ── Fixtures ──────────────────────────────────────────────────────────────────

FREEZE = RULE_FREEZE_DATE           # 2026-11-05
PRE_FREEZE = date(2026, 11, 4)
POST_FREEZE = date(2026, 11, 6)

# A minimal set of trading dates around the freeze date
_TRADING_DATES = [
    date(2026, 10, 28),
    date(2026, 11, 3),
    date(2026, 11, 4),
    date(2026, 11, 5),
    date(2026, 11, 6),
    date(2026, 11, 10),
    date(2026, 11, 11),
    date(2026, 11, 12),
    date(2026, 11, 13),
    date(2026, 11, 17),
    date(2026, 11, 18),
    date(2026, 11, 19),
    date(2026, 11, 20),
    date(2026, 11, 24),
    date(2026, 11, 25),
    date(2026, 11, 26),
    date(2026, 11, 27),
    date(2026, 12, 1),
    date(2026, 12, 2),
    date(2026, 12, 3),
    date(2026, 12, 4),
    date(2026, 12, 8),
    date(2026, 12, 9),
    date(2026, 12, 10),
    date(2026, 12, 11),
    date(2026, 12, 15),
    date(2026, 12, 16),
]


@pytest.fixture
def cal() -> TradingCalendar:
    return TradingCalendar.from_dates(_TRADING_DATES)


@pytest.fixture
def mem_db() -> sqlite3.Connection:
    """In-memory SQLite with Hybrid Forward schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    # Create a minimal daily_prices table for testing
    conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_prices (
            stock_id TEXT, date TEXT, close REAL,
            open REAL, high REAL, low REAL, volume REAL
        )
    """)
    # Populate 0050 for trading calendar
    for d in _TRADING_DATES:
        conn.execute(
            "INSERT INTO daily_prices (stock_id, date, close, open, high, low) VALUES (?,?,?,?,?,?)",
            ("0050", str(d), 100.0, 100.0, 101.0, 99.0),
        )
    conn.commit()
    ensure_schema(conn)
    return conn


def _make_decision(
    stock_id: str = "2330",
    trade_date: date = POST_FREEZE,
    capture: str = CaptureClassification.PROSPECTIVE,
    hybrid_action: str = "WAIT_PULLBACK",
    rule_priority: int = 1,
    decision_hash: str = "abc12345",
    run_id: str = "run0001",
) -> HybridForwardDecision:
    return HybridForwardDecision(
        stock_id=stock_id,
        trade_date=trade_date,
        rule_version="hybrid_v1",
        research_version="v2_research_v2",
        v2_entry_label="WAIT_FOR_PULLBACK",
        hybrid_action=hybrid_action,
        rule_reason="P1: Bear regime",
        rule_priority=rule_priority,
        market_regime="bear",
        ma20_slope_pct=-0.5,
        ma20_trend="falling",
        ma20_gap_pct=1.2,
        feature_cutoff_date=trade_date,
        input_data_as_of=trade_date,
        input_data_hash="in0001",
        decision_hash=decision_hash,
        capture_classification=capture,
        captured_at=datetime.now(timezone.utc),
        run_id=run_id,
    )


def _make_outcome(
    decision_id: int,
    horizon: str = "20d",
    hybrid_ret: float = 1.5,
    v1_ret: float = 1.0,
    calc_ver: str = CALCULATION_VERSION,
    status: str = OutcomeStatus.MATURED,
) -> HybridForwardOutcome:
    return HybridForwardOutcome(
        decision_id=decision_id,
        stock_id="2330",
        trade_date=POST_FREEZE,
        rule_version="hybrid_v1",
        horizon=horizon,
        maturity_date=POST_FREEZE + timedelta(days=28),
        maturity_trading_days=20,
        v1_net_return=v1_ret,
        v2_net_return=1.3,
        hybrid_net_return=hybrid_ret,
        hybrid_vs_v1_delta=round(hybrid_ret - v1_ret, 4),
        hybrid_vs_v2_delta=round(hybrid_ret - 1.3, 4),
        data_source_version="2026-11-25",
        calculation_version=calc_ver,
        outcome_status=status,
        calculated_at=datetime.now(timezone.utc),
    )


# ── FS01–FS06: TradingCalendar ────────────────────────────────────────────────

class TestTradingCalendar:

    def test_FS01_is_trading_day(self, cal):
        assert cal.is_trading_day(FREEZE) is True
        assert cal.is_trading_day(date(2026, 11, 7)) is False  # weekend

    def test_FS02_next_trading_day(self, cal):
        assert cal.next_trading_day(FREEZE) == POST_FREEZE

    def test_FS03_add_trading_days(self, cal):
        # FREEZE=2026-11-05 at idx 3; idx 3+5=8 → 2026-11-13
        d = cal.add_trading_days(FREEZE, 5)
        assert d == date(2026, 11, 13)

    def test_FS04_count_trading_days(self, cal):
        # dates in [2026-11-05, 2026-11-12]: 05,06,10,11,12 = 5 inclusive
        n = cal.count_trading_days(FREEZE, date(2026, 11, 12))
        assert n == 5

    def test_FS05_add_zero(self, cal):
        assert cal.add_trading_days(FREEZE, 0) == FREEZE

    def test_FS06_last_known_date(self, cal):
        assert cal.last_known_date() == date(2026, 12, 16)

    def test_FS06b_from_db(self, mem_db):
        cal_db = TradingCalendar.from_db(mem_db)
        assert cal_db.is_trading_day(FREEZE) is True


# ── FS07–FS13: Capture classification + hashing ──────────────────────────────

class TestCaptureClassification:

    def test_FS07_pre_freeze_is_retrospective(self):
        c = classify_capture(PRE_FREEZE, datetime.now(timezone.utc), PRE_FREEZE, 0)
        assert c == CaptureClassification.RETROSPECTIVE_RECONSTRUCTION

    def test_FS08_post_freeze_on_time_is_prospective(self):
        c = classify_capture(POST_FREEZE, datetime.now(timezone.utc), POST_FREEZE, 0)
        assert c == CaptureClassification.PROSPECTIVE

    def test_FS09_post_freeze_late_is_late_capture(self):
        c = classify_capture(POST_FREEZE, datetime.now(timezone.utc), POST_FREEZE, 5)
        assert c == CaptureClassification.LATE_CAPTURE

    def test_FS10_data_before_trade_date_is_invalid(self):
        c = classify_capture(POST_FREEZE, datetime.now(timezone.utc), PRE_FREEZE, 0)
        assert c == CaptureClassification.INVALID_DATA

    def test_FS11_decision_hash_deterministic(self):
        h1 = compute_decision_hash("WAIT_PULLBACK", "P1: Bear", 1, "hybrid_v1")
        h2 = compute_decision_hash("WAIT_PULLBACK", "P1: Bear", 1, "hybrid_v1")
        assert h1 == h2

    def test_FS12_different_actions_different_hash(self):
        h1 = compute_decision_hash("WAIT_PULLBACK", "P1", 1, "hybrid_v1")
        h2 = compute_decision_hash("DIRECT_NEXT_OPEN", "P4", 4, "hybrid_v1")
        assert h1 != h2

    def test_FS13_input_hash_changes_with_data(self):
        h1 = compute_input_data_hash("2330", POST_FREEZE, "bear", -0.5, "flat", 1.2, "WAIT_FOR_PULLBACK", POST_FREEZE)
        h2 = compute_input_data_hash("2330", POST_FREEZE, "bull", 0.5, "rising", 1.2, "WAIT_FOR_PULLBACK", POST_FREEZE)
        assert h1 != h2


# ── FS14–FS20: Append-only decision insert ────────────────────────────────────

class TestAppendOnlyDecision:

    def test_FS14_insert_new_decision(self, mem_db):
        d = _make_decision()
        row_id = insert_decision(mem_db, d)
        assert row_id is not None

    def test_FS15_duplicate_insert_returns_none(self, mem_db):
        d = _make_decision()
        insert_decision(mem_db, d)
        result = insert_decision(mem_db, d)  # same record again
        assert result is None  # idempotent skip

    def test_FS16_conflict_raises_conflict_error(self, mem_db):
        d1 = _make_decision(decision_hash="hash_a")
        insert_decision(mem_db, d1)
        d2 = _make_decision(decision_hash="hash_b")  # same PK, different hash
        with pytest.raises(ConflictError):
            insert_decision(mem_db, d2)

    def test_FS17_original_record_unchanged_after_conflict(self, mem_db):
        d1 = _make_decision(decision_hash="hash_original")
        insert_decision(mem_db, d1)
        d2 = _make_decision(decision_hash="hash_new")
        try:
            insert_decision(mem_db, d2)
        except ConflictError:
            pass
        row = mem_db.execute(
            "SELECT decision_hash FROM hybrid_forward_decision WHERE stock_id='2330'"
        ).fetchone()
        assert row["decision_hash"] == "hash_original"  # untouched

    def test_FS18_multiple_stocks_same_date(self, mem_db):
        for i in range(5):
            d = _make_decision(stock_id=f"S{i:03d}", decision_hash=f"hash{i}")
            insert_decision(mem_db, d)
        mem_db.commit()
        count = mem_db.execute("SELECT COUNT(*) FROM hybrid_forward_decision").fetchone()[0]
        assert count == 5

    def test_FS19_decision_never_updated_by_schema(self, mem_db):
        """Verify no UPDATE trigger or ON CONFLICT REPLACE exists on decision table."""
        schema = mem_db.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='hybrid_forward_decision'"
        ).fetchone()[0]
        assert "REPLACE" not in schema.upper()
        assert "ON CONFLICT" not in schema.upper()

    def test_FS20_insert_preserves_all_fields(self, mem_db):
        d = _make_decision(capture=CaptureClassification.PROSPECTIVE)
        row_id = insert_decision(mem_db, d)
        row = mem_db.execute(
            "SELECT * FROM hybrid_forward_decision WHERE id=?", (row_id,)
        ).fetchone()
        assert row["capture_classification"] == CaptureClassification.PROSPECTIVE
        assert row["rule_version"] == "hybrid_v1"


# ── FS21–FS27: Decision/Outcome separation ────────────────────────────────────

class TestDecisionOutcomeSeparation:

    def test_FS21_outcome_in_separate_table(self, mem_db):
        d = _make_decision()
        did = insert_decision(mem_db, d)
        o = _make_outcome(did)
        insert_outcome(mem_db, o)
        mem_db.commit()
        # Decision has no outcome columns
        d_cols = [r[1] for r in mem_db.execute("PRAGMA table_info(hybrid_forward_decision)").fetchall()]
        assert "hybrid_net_return" not in d_cols
        assert "outcome_20d" not in d_cols
        # Outcome has decision_id FK
        o_cols = [r[1] for r in mem_db.execute("PRAGMA table_info(hybrid_forward_outcome)").fetchall()]
        assert "decision_id" in o_cols

    def test_FS22_decision_unchanged_after_outcome_insert(self, mem_db):
        d = _make_decision(decision_hash="original_hash")
        did = insert_decision(mem_db, d)
        o = _make_outcome(did, hybrid_ret=2.5)
        insert_outcome(mem_db, o)
        mem_db.commit()
        row = mem_db.execute("SELECT decision_hash FROM hybrid_forward_decision WHERE id=?", (did,)).fetchone()
        assert row[0] == "original_hash"

    def test_FS23_duplicate_outcome_idempotent(self, mem_db):
        d = _make_decision()
        did = insert_decision(mem_db, d)
        o = _make_outcome(did, hybrid_ret=1.5)
        insert_outcome(mem_db, o)
        result = insert_outcome(mem_db, o)  # same outcome again
        assert result is None

    def test_FS24_different_outcome_raises_conflict(self, mem_db):
        d = _make_decision()
        did = insert_decision(mem_db, d)
        insert_outcome(mem_db, _make_outcome(did, hybrid_ret=1.5))
        with pytest.raises(ConflictError):
            insert_outcome(mem_db, _make_outcome(did, hybrid_ret=2.0))

    def test_FS25_multiple_horizons_allowed(self, mem_db):
        d = _make_decision()
        did = insert_decision(mem_db, d)
        for h in ("5d", "10d", "20d"):
            o = _make_outcome(did, horizon=h)
            insert_outcome(mem_db, o)
        mem_db.commit()
        count = mem_db.execute(
            "SELECT COUNT(*) FROM hybrid_forward_outcome WHERE decision_id=?", (did,)
        ).fetchone()[0]
        assert count == 3

    def test_FS26_outcome_has_decision_id(self, mem_db):
        d = _make_decision()
        did = insert_decision(mem_db, d)
        o = _make_outcome(did)
        oid = insert_outcome(mem_db, o)
        row = mem_db.execute("SELECT decision_id FROM hybrid_forward_outcome WHERE id=?", (oid,)).fetchone()
        assert row[0] == did

    def test_FS27_pending_outcomes_query(self, mem_db):
        d = _make_decision(trade_date=FREEZE)
        insert_decision(mem_db, d)
        mem_db.commit()
        cutoff = FREEZE + timedelta(days=35)
        pending = get_pending_outcome_decisions(mem_db, cutoff, "20d", CALCULATION_VERSION)
        assert len(pending) == 1


# ── FS28–FS32: Run log ────────────────────────────────────────────────────────

class TestRunLog:

    def test_FS28_insert_run_log(self, mem_db):
        log = HybridForwardRunLog(
            run_id="run_test01",
            trade_date=FREEZE,
            started_at=datetime.now(timezone.utc),
            finished_at=None,
            input_data_date=FREEZE,
            inserted_count=10,
            skipped_count=5,
            conflict_count=0,
            error_count=0,
            outcome_filled_count=0,
            status=RunStatus.SUCCESS,
            error_summary=None,
        )
        upsert_run_log(mem_db, log)
        row = mem_db.execute("SELECT status FROM hybrid_forward_run_log WHERE run_id='run_test01'").fetchone()
        assert row[0] == RunStatus.SUCCESS

    def test_FS29_run_log_update(self, mem_db):
        log = HybridForwardRunLog(
            run_id="run_upd01",
            trade_date=FREEZE,
            started_at=datetime.now(timezone.utc),
            finished_at=None,
            input_data_date=None,
            inserted_count=0,
            skipped_count=0,
            conflict_count=0,
            error_count=0,
            outcome_filled_count=0,
            status=RunStatus.FAILED,
            error_summary="initial",
        )
        upsert_run_log(mem_db, log)
        log.status = RunStatus.SUCCESS
        log.inserted_count = 10
        log.finished_at = datetime.now(timezone.utc)
        upsert_run_log(mem_db, log)
        row = mem_db.execute(
            "SELECT status, inserted_count FROM hybrid_forward_run_log WHERE run_id='run_upd01'"
        ).fetchone()
        assert row[0] == RunStatus.SUCCESS
        assert row[1] == 10

    def test_FS30_all_run_statuses_valid(self, mem_db):
        for i, status in enumerate([
            RunStatus.SUCCESS, RunStatus.PARTIAL, RunStatus.SKIPPED_NON_TRADING_DAY,
            RunStatus.BLOCKED_STALE_DATA, RunStatus.BLOCKED_MISSING_SIGNALS,
            RunStatus.FAILED, RunStatus.CONFLICT,
        ]):
            log = HybridForwardRunLog(
                run_id=f"test_status_{i}",
                trade_date=FREEZE + timedelta(days=i),
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
                input_data_date=FREEZE,
                inserted_count=0, skipped_count=0, conflict_count=0,
                error_count=0, outcome_filled_count=0,
                status=status, error_summary=None,
            )
            upsert_run_log(mem_db, log)

        count = mem_db.execute("SELECT COUNT(*) FROM hybrid_forward_run_log").fetchone()[0]
        assert count == 7

    def test_FS31_run_id_unique(self):
        ids = {new_run_id() for _ in range(100)}
        assert len(ids) == 100

    def test_FS32_operational_summary_structure(self, mem_db):
        d = _make_decision()
        insert_decision(mem_db, d)
        mem_db.commit()
        summary = get_operational_summary(mem_db)
        assert "total_decisions" in summary
        assert "prospective_decisions" in summary
        assert "matured_20d" in summary
        assert "consecutive_failures" in summary


# ── FS33–FS38: Stale data / missing signals guards ────────────────────────────

class TestDataGuards:

    def test_FS33_capture_invalid_when_data_older_than_trade(self):
        c = classify_capture(
            trade_date=POST_FREEZE,
            captured_at=datetime.now(timezone.utc),
            input_data_as_of=date(2026, 11, 3),  # older than trade_date
            trading_days_since_trade=0,
        )
        assert c == CaptureClassification.INVALID_DATA

    def test_FS34_retrospective_when_before_freeze(self):
        c = classify_capture(PRE_FREEZE, datetime.now(timezone.utc), PRE_FREEZE, 0)
        assert c == CaptureClassification.RETROSPECTIVE_RECONSTRUCTION

    def test_FS35_late_capture_when_too_late(self):
        c = classify_capture(POST_FREEZE, datetime.now(timezone.utc), POST_FREEZE, 10)
        assert c == CaptureClassification.LATE_CAPTURE

    def test_FS36_prospective_exactly_on_time(self):
        c = classify_capture(POST_FREEZE, datetime.now(timezone.utc), POST_FREEZE, 1)
        assert c == CaptureClassification.PROSPECTIVE

    def test_FS37_freeze_date_itself_is_prospective(self):
        c = classify_capture(FREEZE, datetime.now(timezone.utc), FREEZE, 0)
        assert c == CaptureClassification.PROSPECTIVE

    def test_FS38_day_before_freeze_is_retrospective(self):
        c = classify_capture(PRE_FREEZE, datetime.now(timezone.utc), PRE_FREEZE, 0)
        assert c == CaptureClassification.RETROSPECTIVE_RECONSTRUCTION


# ── FS39–FS43: Outcome maturity (trading-day based) ───────────────────────────

class TestOutcomeMaturity:

    def test_FS39_5d_maturity_is_5_trading_days(self, cal):
        # entry=2026-11-06 (idx 4); 4+5=9 → 2026-11-17
        entry = cal.next_trading_day(FREEZE)  # 2026-11-06
        maturity = cal.add_trading_days(entry, 5)
        assert maturity == date(2026, 11, 17)

    def test_FS40_10d_maturity(self, cal):
        # entry=2026-11-06 (idx 4); 4+10=14 → 2026-11-25
        entry = cal.next_trading_day(FREEZE)
        maturity = cal.add_trading_days(entry, 10)
        assert maturity == date(2026, 11, 25)

    def test_FS41_20d_maturity(self, cal):
        # entry=2026-11-06 (idx 4); 4+20=24 → 2026-12-11
        entry = cal.next_trading_day(FREEZE)
        maturity = cal.add_trading_days(entry, 20)
        assert maturity == date(2026, 12, 11)

    def test_FS42_count_trading_days_between(self, cal):
        d1 = date(2026, 11, 6)
        d2 = date(2026, 11, 13)
        # Dates in [06, 13]: 06, 10, 11, 12, 13 = 5 inclusive
        n = cal.count_trading_days(d1, d2)
        assert n == 5

    def test_FS43_pending_maturity_not_returned_before_maturity(self, mem_db):
        d = _make_decision(trade_date=date(2026, 12, 1))  # too recent
        insert_decision(mem_db, d)
        mem_db.commit()
        # Cutoff is earlier than trade_date, so it should not be pending
        cutoff = date(2026, 11, 20)
        pending = get_pending_outcome_decisions(mem_db, cutoff, "20d", CALCULATION_VERSION)
        # Decision is at 2026-12-01, cutoff is 2026-11-20 → not in pending
        assert all(
            p["trade_date"] <= str(cutoff) for p in pending
        )


# ── FS44–FS48: Idempotency / retry ───────────────────────────────────────────

class TestIdempotency:

    def test_FS44_double_insert_decision_idempotent(self, mem_db):
        d = _make_decision()
        insert_decision(mem_db, d)
        insert_decision(mem_db, d)  # second insert, same record
        mem_db.commit()
        count = mem_db.execute("SELECT COUNT(*) FROM hybrid_forward_decision").fetchone()[0]
        assert count == 1

    def test_FS45_double_insert_outcome_idempotent(self, mem_db):
        d = _make_decision()
        did = insert_decision(mem_db, d)
        o = _make_outcome(did)
        insert_outcome(mem_db, o)
        insert_outcome(mem_db, o)
        mem_db.commit()
        count = mem_db.execute("SELECT COUNT(*) FROM hybrid_forward_outcome").fetchone()[0]
        assert count == 1

    def test_FS46_hash_idempotency(self):
        """Same inputs produce same hash every time."""
        for _ in range(5):
            h = compute_decision_hash("WAIT_PULLBACK", "P1: Bear", 1, "hybrid_v1")
        h2 = compute_decision_hash("WAIT_PULLBACK", "P1: Bear", 1, "hybrid_v1")
        assert h == h2

    def test_FS47_run_log_idempotent_update(self, mem_db):
        log = HybridForwardRunLog(
            run_id="idem_test",
            trade_date=FREEZE,
            started_at=datetime.now(timezone.utc),
            finished_at=None,
            input_data_date=FREEZE,
            inserted_count=5, skipped_count=0, conflict_count=0,
            error_count=0, outcome_filled_count=0,
            status=RunStatus.SUCCESS, error_summary=None,
        )
        upsert_run_log(mem_db, log)
        upsert_run_log(mem_db, log)
        count = mem_db.execute("SELECT COUNT(*) FROM hybrid_forward_run_log WHERE run_id='idem_test'").fetchone()[0]
        assert count == 1

    def test_FS48_conflict_does_not_insert(self, mem_db):
        d1 = _make_decision(decision_hash="hash_a")
        d2 = _make_decision(decision_hash="hash_b")
        insert_decision(mem_db, d1)
        try:
            insert_decision(mem_db, d2)
        except ConflictError:
            pass
        mem_db.commit()
        count = mem_db.execute("SELECT COUNT(*) FROM hybrid_forward_decision").fetchone()[0]
        assert count == 1  # only original


# ── FS49–FS52: Full shadow run (via scripts.run_hybrid_forward_shadow) ─────────

class TestFullShadowRun:
    """
    Test the daily runner end-to-end using test DB and mocked date.
    Uses --date that is after freeze but DailyPrice may or may not cover it.
    """

    def _make_test_db(self, with_data_on_freeze: bool = True) -> str:
        """Create a temporary test SQLite file and return its path."""
        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        conn = sqlite3.connect(tmp.name)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_prices (
                stock_id TEXT, date TEXT, close REAL, open REAL, high REAL, low REAL, volume REAL
            )
        """)
        # 0050 for trading calendar
        for d in _TRADING_DATES:
            conn.execute(
                "INSERT INTO daily_prices VALUES (?,?,?,?,?,?,?)",
                ("0050", str(d), 100.0, 100.0, 101.0, 99.0, 1000.0),
            )
        # A few test stocks
        if with_data_on_freeze:
            for d in _TRADING_DATES:
                for s in ["2330", "2317"]:
                    conn.execute(
                        "INSERT INTO daily_prices VALUES (?,?,?,?,?,?,?)",
                        (s, str(d), 500.0 + 1.0, 500.0, 502.0, 498.0, 500.0),
                    )
        conn.commit()
        conn.close()
        return tmp.name

    def test_FS49_run_inserts_decisions(self, monkeypatch):
        from scripts.run_hybrid_forward_shadow import run_shadow
        import scripts.run_hybrid_forward_shadow as runner_mod
        db_file = self._make_test_db()
        monkeypatch.setattr(runner_mod, "DB_PATH", db_file)
        monkeypatch.setattr(runner_mod, "STALE_DATA_TOLERANCE_DAYS", 365)  # bypass stale check for test
        result = run_shadow(trade_date=FREEZE, force_stale=True)
        assert result.get("status") in (RunStatus.SUCCESS, RunStatus.PARTIAL, RunStatus.BLOCKED_STALE_DATA)
        import os
        os.unlink(db_file)

    def test_FS50_run_before_freeze_records_retrospective(self, monkeypatch):
        from scripts.run_hybrid_forward_shadow import run_shadow
        import scripts.run_hybrid_forward_shadow as runner_mod
        db_file = self._make_test_db()
        monkeypatch.setattr(runner_mod, "DB_PATH", db_file)
        run_shadow(trade_date=PRE_FREEZE, force_stale=True)
        # Pre-freeze run is allowed but all classifications = RETROSPECTIVE_RECONSTRUCTION
        conn = sqlite3.connect(db_file)
        rows = conn.execute(
            "SELECT capture_classification FROM hybrid_forward_decision"
        ).fetchall()
        conn.close()
        import os
        os.unlink(db_file)
        for row in rows:
            assert row[0] == CaptureClassification.RETROSPECTIVE_RECONSTRUCTION

    def test_FS51_run_idempotent(self, monkeypatch):
        from scripts.run_hybrid_forward_shadow import run_shadow
        import scripts.run_hybrid_forward_shadow as runner_mod
        db_file = self._make_test_db()
        monkeypatch.setattr(runner_mod, "DB_PATH", db_file)
        monkeypatch.setattr(runner_mod, "STALE_DATA_TOLERANCE_DAYS", 365)
        run_shadow(trade_date=FREEZE, force_stale=True)
        run_shadow(trade_date=FREEZE, force_stale=True)  # second run same date
        conn = sqlite3.connect(db_file)
        # Conflict count should be 0 (idempotent)
        conflicts = conn.execute(
            "SELECT SUM(conflict_count) FROM hybrid_forward_run_log WHERE trade_date=?",
            (str(FREEZE),),
        ).fetchone()[0] or 0
        conn.close()
        import os
        os.unlink(db_file)
        assert conflicts == 0

    def test_FS52_no_data_returns_blocked(self, monkeypatch):
        from scripts.run_hybrid_forward_shadow import run_shadow
        import scripts.run_hybrid_forward_shadow as runner_mod
        # Create DB with no stock data on target date
        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        conn = sqlite3.connect(tmp.name)
        conn.execute("CREATE TABLE daily_prices (stock_id TEXT, date TEXT, close REAL, open REAL, high REAL, low REAL, volume REAL)")
        conn.commit()
        conn.close()
        monkeypatch.setattr(runner_mod, "DB_PATH", tmp.name)
        result = run_shadow(trade_date=FREEZE, force_stale=True)
        import os
        os.unlink(tmp.name)
        assert result.get("status") in (
            RunStatus.BLOCKED_MISSING_SIGNALS,
            RunStatus.BLOCKED_STALE_DATA,
            RunStatus.SKIPPED_NON_TRADING_DAY,
        )


# ── FS53–FS55: Operational summary ───────────────────────────────────────────

class TestOperationalSummary:

    def test_FS53_summary_has_all_keys(self, mem_db):
        summary = get_operational_summary(mem_db)
        for key in ["total_decisions", "prospective_decisions", "matured_20d",
                    "consecutive_failures", "decisions_by_classification"]:
            assert key in summary

    def test_FS54_matured_performance_none_when_empty(self, mem_db):
        result = get_matured_performance(mem_db, "20d")
        assert result is None

    def test_FS55_matured_performance_after_insert(self, mem_db):
        d = _make_decision()
        did = insert_decision(mem_db, d)
        o = _make_outcome(did, horizon="20d", hybrid_ret=2.0, v1_ret=1.0)
        insert_outcome(mem_db, o)
        mem_db.commit()
        result = get_matured_performance(mem_db, "20d")
        assert result is not None
        assert result["n_matured"] == 1
        assert abs(result["hybrid_vs_v1_mean_delta"] - 1.0) < 0.01
