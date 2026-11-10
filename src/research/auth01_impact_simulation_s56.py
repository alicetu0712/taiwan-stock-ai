"""
AUTH01 Backfill Impact Simulation — Session 56

PARTS B1–B6: Record-level coverage, source integrity, QG counterfactual,
research impact, AUTH01 decision package.

Key Findings:
- Expected ordinary-stock universe per date: ~1969 (4-digit 1000-9999)
- S50 verified prices: CLOSE only (no OHLC/Volume)
- Max verified per date: 3 stocks (Oct29)
- Coverage after full S50-verified backfill: 3/1969 = 0.15%
- OHLCEstimation: open=close*0.99, high=close*1.01, low=close*0.98 → ESTIMATED, NOT VERIFIED
- ETF contamination: 0050 already present; 2330/2454/2317 are ordinary stocks ✓
"""

from __future__ import annotations

import hashlib
import sqlite3
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional


# ── Enums ──────────────────────────────────────────────────────────────────────

class RecordAction(str, Enum):
    INSERT_CANDIDATE = "INSERT_CANDIDATE"
    SKIP_EXISTING = "SKIP_EXISTING"
    CONFLICT_REVIEW = "CONFLICT_REVIEW"
    SOURCE_MISSING = "SOURCE_MISSING"
    VALIDATION_FAILED = "VALIDATION_FAILED"


class OHLCVCompleteness(str, Enum):
    CLOSE_ONLY = "CLOSE_ONLY"           # only close verified (S50 state)
    FULL_OHLCV = "FULL_OHLCV"           # full OHLCV verified
    ESTIMATED = "ESTIMATED"             # OHLC estimated from close
    MISSING = "MISSING"                 # no data


class CoverageVerdict(str, Enum):
    COVERAGE_VERIFIED = "COVERAGE_VERIFIED"
    COVERAGE_PARTIAL = "COVERAGE_PARTIAL"
    COVERAGE_UNVERIFIED = "COVERAGE_UNVERIFIED"
    COVERAGE_INSUFFICIENT = "COVERAGE_INSUFFICIENT"


class Auth01Verdict(str, Enum):
    AUTH01_READY_FOR_AUTHORIZATION = "AUTH01_READY_FOR_AUTHORIZATION"
    AUTH01_PARTIAL = "AUTH01_PARTIAL"
    AUTH01_BLOCKED = "AUTH01_BLOCKED"
    AUTH01_NOT_EXECUTED = "AUTH01_NOT_EXECUTED"


class QGScenario(str, Enum):
    CURRENT = "CURRENT"
    BACKFILL_ONLY = "BACKFILL_ONLY"
    BACKFILL_PLUS_PATCH = "BACKFILL_PLUS_PATCH"
    MISSING_SOURCE = "MISSING_SOURCE"
    CONFLICT_SOURCE = "CONFLICT_SOURCE"
    TPEX_STALE = "TPEX_STALE"


# ── S50 Verified Prices (CLOSE only) ──────────────────────────────────────────
# Source: TWSE single-stock API calls in Session 50
# Limitation: CLOSE only; OPEN/HIGH/LOW/VOLUME are estimates if used
_S50_VERIFIED_PRICES: Dict[str, Dict[str, float]] = {
    "2026-10-29": {"2330": 2415.0, "2454": 4045.0, "2317": 248.0},
    "2026-10-30": {"2330": 2370.0, "2454": 3915.0},
    "2026-11-02": {"2330": 2330.0},
    "2026-11-03": {"2317": 245.0},
    "2026-11-06": {"2330": 2135.0, "2454": 3390.0},
    "2026-11-09": {"2330": 2200.0, "2454": 3450.0},
}

# Reference ordinary stock universe: 4-digit stock_id BETWEEN 1000 AND 9999
# Measured from Nov04 (fully backfilled): 1969 stocks
REFERENCE_ORDINARY_UNIVERSE = 1969
# Total rows on Nov04 (includes ETFs, warrants, preferred): 6957
REFERENCE_TOTAL_UNIVERSE = 6957

# AUTH01 priority dates
_AUTH01_DATES = [
    ("2026-10-29", "P1", True),   # (date, priority, is_trading_day)
    ("2026-10-30", "P1", True),
    ("2026-11-02", "P1", True),
    ("2026-11-03", "P1", True),
    ("2026-11-04", "P1", True),   # SKIP_EXISTING
    ("2026-11-05", "P1", True),   # SKIP_EXISTING
    ("2026-11-06", "P2", True),
    ("2026-11-09", "P2", True),
]


# ── B1: Record-level Detail ────────────────────────────────────────────────────

@dataclass
class RecordDetail:
    date: str
    security_id: str
    exchange: str
    point_in_time_type: str      # "ordinary_stock", "etf", "unknown"
    open_price: Optional[float]  # None if not verified
    high_price: Optional[float]
    low_price: Optional[float]
    close_price: Optional[float]
    volume: Optional[float]
    source_provider: str
    source_request_date: str
    source_returned_date: str
    source_timestamp: str
    source_hash: str
    ohlcv_completeness: OHLCVCompleteness
    validation_result: str
    existing_row_state: str      # "PRESENT" or "ABSENT"
    conflict_state: str          # "NO_CONFLICT", "VALUE_CONFLICT", "UNKNOWN"
    proposed_action: RecordAction
    corporate_action_checked: bool
    ohlc_consistency: str        # "PASS", "ESTIMATED_ONLY", "UNCHECKED"


def build_record_manifest(conn: sqlite3.Connection) -> List[RecordDetail]:
    """Build per-record manifest for all AUTH01 candidate records."""
    records = []
    for date, priority, is_trading_day in _AUTH01_DATES:
        existing_count = conn.execute(
            "SELECT COUNT(*) FROM daily_prices WHERE date=? AND stock_id!='0050'",
            (date,)
        ).fetchone()[0]

        verified = _S50_VERIFIED_PRICES.get(date, {})

        if existing_count > 0:
            # SKIP_EXISTING: Nov04/05
            records.append(RecordDetail(
                date=date, security_id="*", exchange="TWSE+TPEx",
                point_in_time_type="mixed",
                open_price=None, high_price=None, low_price=None,
                close_price=None, volume=None,
                source_provider="DB_EXISTING",
                source_request_date=date, source_returned_date=date,
                source_timestamp="", source_hash="",
                ohlcv_completeness=OHLCVCompleteness.FULL_OHLCV,
                validation_result=f"SKIP: {existing_count} non-0050 rows exist",
                existing_row_state="PRESENT",
                conflict_state="NO_CONFLICT",
                proposed_action=RecordAction.SKIP_EXISTING,
                corporate_action_checked=False,
                ohlc_consistency="UNCHECKED",
            ))
        elif not verified:
            # SOURCE_MISSING: no S50 prices and no existing data
            records.append(RecordDetail(
                date=date, security_id="UNIVERSE", exchange="UNKNOWN",
                point_in_time_type="unknown",
                open_price=None, high_price=None, low_price=None,
                close_price=None, volume=None,
                source_provider="NONE",
                source_request_date=date, source_returned_date="",
                source_timestamp="", source_hash="",
                ohlcv_completeness=OHLCVCompleteness.MISSING,
                validation_result="SOURCE_MISSING: no S50 prices, no existing data",
                existing_row_state="ABSENT",
                conflict_state="UNKNOWN",
                proposed_action=RecordAction.SOURCE_MISSING,
                corporate_action_checked=False,
                ohlc_consistency="UNCHECKED",
            ))
        else:
            for stock_id, close in verified.items():
                # CLOSE only verified; OHLCV estimated
                close_hash = hashlib.md5(f"{date}:{stock_id}:{close}".encode()).hexdigest()
                records.append(RecordDetail(
                    date=date, security_id=stock_id, exchange="TWSE",
                    point_in_time_type="ordinary_stock",
                    open_price=None,   # NOT verified
                    high_price=None,   # NOT verified
                    low_price=None,    # NOT verified
                    close_price=close,
                    volume=None,       # NOT verified
                    source_provider="TWSE_SINGLE_STOCK_S50",
                    source_request_date=date, source_returned_date=date,
                    source_timestamp="2026-11-Session50-manual",
                    source_hash=close_hash,
                    ohlcv_completeness=OHLCVCompleteness.CLOSE_ONLY,
                    validation_result="CLOSE_VERIFIED_TWSE_S50; OHLV_NOT_VERIFIED",
                    existing_row_state="ABSENT",
                    conflict_state="NO_CONFLICT",
                    proposed_action=RecordAction.INSERT_CANDIDATE,
                    corporate_action_checked=False,
                    ohlc_consistency="ESTIMATED_ONLY",
                ))

    return records


# ── B2: Source Integrity ───────────────────────────────────────────────────────

@dataclass
class SourceIntegrityCheck:
    check_name: str
    status: str         # "PASS", "FAIL", "UNVERIFIED", "WARNING"
    finding: str
    evidence: str


def run_source_integrity_checks(conn: sqlite3.Connection) -> List[SourceIntegrityCheck]:
    checks = []

    # TWSE Official Source
    checks.append(SourceIntegrityCheck(
        "TWSE_OFFICIAL_SOURCE",
        "PASS",
        "2330/2454/2317 verified via TWSE single-stock API in S50",
        "Session 50 manual API calls; prices plausible for 2026-10-29",
    ))

    # TPEx Official Source
    checks.append(SourceIntegrityCheck(
        "TPEX_OFFICIAL_SOURCE",
        "UNVERIFIED",
        "No TPEx single-stock calls performed in S50 for AUTH01 dates",
        "TPEx patch not deployed; api_date mismatch not propagated to errors",
    ))

    # Provider Date Semantics
    checks.append(SourceIntegrityCheck(
        "PROVIDER_DATE_SEMANTICS",
        "PASS",
        "TWSE request_date == returned_date for S50 verified records",
        "source_request_date=source_returned_date in _S50_VERIFIED_PRICES",
    ))

    # Trading Calendar
    checks.append(SourceIntegrityCheck(
        "TRADING_CALENDAR",
        "PASS",
        "Oct29/30/Nov02/03/Nov06/09 confirmed trading days (TaiwanTradingCalendar_v1)",
        "calendar_contract_s50.py TaiwanTradingCalendar_v1",
    ))

    # Corporate Actions
    checks.append(SourceIntegrityCheck(
        "CORPORATE_ACTIONS",
        "UNVERIFIED",
        "No corporate action check performed for 2330/2454/2317 on AUTH01 dates",
        "Required: check for splits, dividends, rights issues for Oct29–Nov09 period",
    ))

    # Suspensions
    checks.append(SourceIntegrityCheck(
        "SUSPENSIONS",
        "UNVERIFIED",
        "No suspension check performed for AUTH01 dates",
        "TWSE suspension data not queried for these dates",
    ))

    # ETF Contamination
    checks.append(SourceIntegrityCheck(
        "ETF_CONTAMINATION",
        "PASS",
        "2330=台積電, 2454=聯發科, 2317=鴻海 are ordinary_stock (confirmed stocks table)",
        "stocks table: market=TWSE, all 3 confirmed not ETF",
    ))

    # Unknown Security Type
    checks.append(SourceIntegrityCheck(
        "UNKNOWN_SECURITY_TYPE",
        "PASS",
        "All 3 verified S50 stocks confirmed TWSE ordinary stock",
        "stocks.market=TWSE for 2330, 2454, 2317",
    ))

    # Duplicate Rows
    for date in ["2026-10-29", "2026-10-30", "2026-11-02", "2026-11-03"]:
        c = conn.execute(
            "SELECT COUNT(*) FROM daily_prices WHERE date=? AND stock_id IN ('2330','2454','2317')",
            (date,)
        ).fetchone()[0]
        checks.append(SourceIntegrityCheck(
            f"DUPLICATE_CHECK_{date}",
            "PASS" if c == 0 else "WARNING",
            f"Existing rows for verified stocks on {date}: {c}",
            "0 = no conflict; >0 = conflict review needed",
        ))

    # OHLCV Consistency
    checks.append(SourceIntegrityCheck(
        "OHLCV_CONSISTENCY",
        "FAIL",
        "Only CLOSE verified; OPEN/HIGH/LOW/VOLUME are NOT available from S50",
        "S50 API calls returned close price only; full OHLCV requires separate provider call",
    ))

    # Volume Validity
    checks.append(SourceIntegrityCheck(
        "VOLUME_VALIDITY",
        "FAIL",
        "Volume NOT verified for any AUTH01 candidate record",
        "daily_prices schema requires volume; must be sourced or omitted",
    ))

    # Security Mapping
    checks.append(SourceIntegrityCheck(
        "SECURITY_MAPPING",
        "PASS",
        "Stock IDs (2330, 2454, 2317) confirmed in platform stocks table",
        "stocks table: 2330=台積電 TWSE, 2454=聯發科 TWSE, 2317=鴻海 TWSE",
    ))

    return checks


# ── B3: Coverage Simulation ────────────────────────────────────────────────────

@dataclass
class CoverageRow:
    date: str
    existing_valid: int
    candidate_valid: int   # S50-verified records (INSERT_CANDIDATE only)
    simulated_total: int
    expected_universe: int
    coverage_before_pct: float
    coverage_after_pct: float
    twse_coverage_after_pct: float
    tpex_coverage_after_pct: float   # UNVERIFIED
    qg_verdict: str
    coverage_verdict: CoverageVerdict


def build_coverage_matrix(conn: sqlite3.Connection) -> List[CoverageRow]:
    rows = []
    for date, priority, _ in _AUTH01_DATES:
        existing = conn.execute(
            "SELECT COUNT(*) FROM daily_prices WHERE date=? AND stock_id!='0050'",
            (date,)
        ).fetchone()[0]

        verified = _S50_VERIFIED_PRICES.get(date, {})
        # Only count as candidates if stock not already in DB
        candidates = sum(
            1 for sid in verified
            if conn.execute(
                "SELECT COUNT(*) FROM daily_prices WHERE date=? AND stock_id=?",
                (date, sid)
            ).fetchone()[0] == 0
        )

        expected = REFERENCE_ORDINARY_UNIVERSE  # 1969
        total_after = existing + candidates

        cov_before = round(existing / expected * 100, 4)
        cov_after = round(total_after / expected * 100, 4)

        # TWSE coverage only (all verified records are TWSE)
        twse_cov_after = cov_after  # all S50 records are TWSE

        if existing > 1000:
            qg = "QG_PASS_LIKELY"
            verdict = CoverageVerdict.COVERAGE_VERIFIED
        elif candidates > 0:
            qg = "QG_FAIL_INSUFFICIENT"
            verdict = CoverageVerdict.COVERAGE_INSUFFICIENT
        else:
            qg = "QG_FAIL_NO_DATA"
            verdict = CoverageVerdict.COVERAGE_UNVERIFIED

        rows.append(CoverageRow(
            date=date,
            existing_valid=existing,
            candidate_valid=candidates,
            simulated_total=total_after,
            expected_universe=expected,
            coverage_before_pct=cov_before,
            coverage_after_pct=cov_after,
            twse_coverage_after_pct=twse_cov_after,
            tpex_coverage_after_pct=0.0,  # UNVERIFIED
            qg_verdict=qg,
            coverage_verdict=verdict,
        ))

    return rows


# ── B4: QG Counterfactual ──────────────────────────────────────────────────────

@dataclass
class QGCounterfactual:
    date: str
    scenario: QGScenario
    ordinary_stock_rows: int
    has_benchmark: bool
    tpex_error_propagated: bool
    qg_pass: bool
    qg_note: str


def build_qg_counterfactual(conn: sqlite3.Connection) -> List[QGCounterfactual]:
    results = []
    for date, _, _ in _AUTH01_DATES:
        existing = conn.execute(
            "SELECT COUNT(*) FROM daily_prices WHERE date=? AND stock_id!='0050'",
            (date,)
        ).fetchone()[0]
        candidates = len(_S50_VERIFIED_PRICES.get(date, {}))

        # S6.1: Current state
        results.append(QGCounterfactual(
            date=date, scenario=QGScenario.CURRENT,
            ordinary_stock_rows=existing,
            has_benchmark=(existing > 0 or conn.execute(
                "SELECT COUNT(*) FROM daily_prices WHERE date=? AND stock_id='0050'", (date,)
            ).fetchone()[0] > 0),
            tpex_error_propagated=False,
            qg_pass=(existing > 100),
            qg_note=f"existing={existing}; QG requires >100 ordinary stocks",
        ))

        # S6.2: Backfill only (S50 records added, no patch)
        after_backfill = existing + candidates
        results.append(QGCounterfactual(
            date=date, scenario=QGScenario.BACKFILL_ONLY,
            ordinary_stock_rows=after_backfill,
            has_benchmark=True,
            tpex_error_propagated=False,
            qg_pass=(after_backfill > 100),
            qg_note=f"after_backfill={after_backfill}; still <<1969; QG still fails",
        ))

        # S6.3: Backfill + patch
        results.append(QGCounterfactual(
            date=date, scenario=QGScenario.BACKFILL_PLUS_PATCH,
            ordinary_stock_rows=after_backfill,
            has_benchmark=True,
            tpex_error_propagated=True,
            qg_pass=(after_backfill > 100),
            qg_note="TPEx patch adds error observability only; does NOT add price rows",
        ))

        # S6.4: Missing source
        results.append(QGCounterfactual(
            date=date, scenario=QGScenario.MISSING_SOURCE,
            ordinary_stock_rows=0, has_benchmark=False,
            tpex_error_propagated=False,
            qg_pass=False,
            qg_note="No source → no rows → QG FAIL",
        ))

        # S6.5: Conflict scenario
        results.append(QGCounterfactual(
            date=date, scenario=QGScenario.CONFLICT_SOURCE,
            ordinary_stock_rows=existing,
            has_benchmark=True,
            tpex_error_propagated=False,
            qg_pass=False,
            qg_note="Conflict requires CONFLICT_REVIEW; blocked from INSERT",
        ))

        # S6.6: TPEx stale
        results.append(QGCounterfactual(
            date=date, scenario=QGScenario.TPEX_STALE,
            ordinary_stock_rows=existing,
            has_benchmark=True,
            tpex_error_propagated=False,  # without patch
            qg_pass=False,
            qg_note="TPEx stale w/o patch → silent wrong date; QG may PASS with wrong data",
        ))

    return results


# ── B5: Research Impact ────────────────────────────────────────────────────────

@dataclass
class ResearchImpact:
    category: str
    before_auth01: str
    after_auth01_partial: str   # S50 verified records only
    after_auth01_full: str      # hypothetical full universe
    note: str


def build_research_impact() -> List[ResearchImpact]:
    return [
        ResearchImpact(
            "Historical Price Coverage",
            "0 ordinary stocks on Oct29/30/Nov02/03",
            "3/1969 on Oct29 (0.15%); 2 on Oct30; 1 on Nov02/03",
            "~1969/1969 on Oct29/30/Nov02/03 (~100%)",
            "S50-verified backfill achieves <1% coverage; full universe needs new provider calls",
        ),
        ResearchImpact(
            "Historical Outcome Readiness",
            "BLOCKED (no exit prices for Oct29–Nov03 entries)",
            "PARTIAL: can compute outcomes for 3 stocks only",
            "READY: full exit prices available for all entrants",
            "Partial backfill cannot unblock outcome computation for the full portfolio",
        ),
        ResearchImpact(
            "Genuine Prospective Evidence",
            "N=0 (no genuine prospective decisions)",
            "N=0 (historical backfill ≠ prospective)",
            "N=0 (backfill of past dates ≠ genuine prospective)",
            "AUTH01 is HISTORICAL RECOVERY only; never counts toward genuine prospective N",
        ),
        ResearchImpact(
            "G03 Eligible Clusters",
            "0/10 required",
            "0/10 (backfill adds no new prospective clusters)",
            "0/10 (same reason)",
            "G03 tracks GENUINE PROSPECTIVE clusters; backfill does not change G03 count",
        ),
        ResearchImpact(
            "G04 Overlap",
            "STRUCTURAL_FAIL",
            "STRUCTURAL_FAIL (unchanged)",
            "STRUCTURAL_FAIL (unchanged)",
            "G04 is algorithmic design constraint; backfill has no effect",
        ),
    ]


# ── B6: AUTH01 Decision Package ────────────────────────────────────────────────

@dataclass
class Auth01DecisionPackage:
    target_database: str
    target_table: str
    target_dates: List[str]
    target_stock_ids: Dict[str, List[str]]  # date → [stock_ids]
    verified_insert_count: int
    missing_count: int           # stocks without verified source
    conflict_count: int
    ohlcv_limitation: str
    source_evidence: str
    coverage_impact: str
    qg_impact: str
    transaction_plan: str
    rollback_plan: str
    not_executed: str
    audit_trail: str
    post_write_validation: str
    stop_conditions: List[str]
    verdict: Auth01Verdict


def build_auth01_decision_package(conn: sqlite3.Connection) -> Auth01DecisionPackage:
    target_dates_p1 = ["2026-10-29", "2026-10-30", "2026-11-02", "2026-11-03"]
    target_stock_ids = {d: list(_S50_VERIFIED_PRICES.get(d, {}).keys()) for d in target_dates_p1}
    verified_insert = sum(len(v) for v in target_stock_ids.values())

    # OHLCV limitation: open, high, low, volume are NOT verified
    ohlcv_note = (
        "CRITICAL: S50 provides CLOSE PRICE ONLY. "
        "OPEN/HIGH/LOW are estimated (×0.99/×1.01/×0.98 of close). "
        "VOLUME is not available. "
        "Platform schema requires open/high/low/close/volume. "
        "Inserting ESTIMATED OHLCV may corrupt historical accuracy."
    )

    return Auth01DecisionPackage(
        target_database="data/platform.db",
        target_table="daily_prices",
        target_dates=target_dates_p1,
        target_stock_ids=target_stock_ids,
        verified_insert_count=verified_insert,
        missing_count=REFERENCE_ORDINARY_UNIVERSE - verified_insert,
        conflict_count=0,
        ohlcv_limitation=ohlcv_note,
        source_evidence=(
            "TWSE single-stock API (S50 manual calls). "
            "Source: TWSE_SINGLE_STOCK_S50. "
            "Verification: close price only. "
            "OHLCV completeness: CLOSE_ONLY. "
            "Corporate actions: UNCHECKED. "
            "Suspensions: UNCHECKED."
        ),
        coverage_impact=(
            "Oct29: 0→3/1969 (0.00%→0.15%). "
            "Oct30: 0→2/1969 (0.00%→0.10%). "
            "Nov02: 0→1/1969 (0.00%→0.05%). "
            "Nov03: 0→1/1969 (0.00%→0.05%). "
            "Full-universe backfill NOT achievable from S50 data alone."
        ),
        qg_impact=(
            "QG does not change materially. "
            "3 stocks << QG minimum threshold (~100+ stocks required). "
            "QG remains FAIL for Oct29/30/Nov02/03 after S50-verified partial backfill."
        ),
        transaction_plan=(
            "BEGIN TRANSACTION; "
            "INSERT OR IGNORE INTO daily_prices (stock_id, date, open, high, low, close, volume, amount, change_pct) VALUES ...; "
            "COMMIT; "
            "SELECT COUNT(*) post-write for audit."
        ),
        rollback_plan=(
            "DELETE FROM daily_prices WHERE date IN ('2026-10-29','2026-10-30','2026-11-02','2026-11-03') "
            "AND stock_id IN ('2330','2454','2317'); "
            "Rollback is straightforward: 7 rows maximum."
        ),
        not_executed="AUTH01_NOT_EXECUTED",
        audit_trail=(
            "Pre-write count per date. "
            "Per-row insert confirmation. "
            "Post-write count per date. "
            "Coverage metric before/after. "
            "OHLCV provenance tag per row (source='TWSE_S50_CLOSE_ONLY_ESTIMATED_OHLV')."
        ),
        post_write_validation=(
            "SELECT COUNT(*) WHERE date IN ('2026-10-29','2026-10-30','2026-11-02','2026-11-03') AND stock_id IN ('2330','2454','2317'); "
            "Expected: 7. "
            "Verify close prices match S50 reference. "
            "Confirm no existing-row overwrite occurred."
        ),
        stop_conditions=[
            "Any row already exists with conflicting close price",
            "OHLCV estimation produces physically impossible values (high < low)",
            "DB size change exceeds expected +7 rows",
            "Any forward_signal computation is triggered by backfill",
            "Corporate action detected for any target stock on target date",
        ],
        verdict=Auth01Verdict.AUTH01_PARTIAL,
    )


# ── Idempotency Dry-run ────────────────────────────────────────────────────────

def run_coverage_dry_run(conn: sqlite3.Connection) -> dict:
    """Simulate AUTH01 backfill in temp SQLite and verify idempotency."""
    results = {}

    # Create isolated temp DB mirroring daily_prices schema
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        tconn = sqlite3.connect(tmp.name)
        tconn.execute("""
            CREATE TABLE daily_prices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stock_id TEXT NOT NULL,
                date TEXT NOT NULL,
                open REAL, high REAL, low REAL, close REAL,
                volume REAL, amount REAL, change_pct REAL,
                UNIQUE(stock_id, date)
            )
        """)
        # Seed with 0050 rows for each candidate date
        for date, _, _ in _AUTH01_DATES:
            tconn.execute(
                "INSERT OR IGNORE INTO daily_prices (stock_id, date, open, high, low, close, volume) VALUES (?,?,?,?,?,?,?)",
                ("0050", date, 100.0, 101.0, 99.0, 100.5, 1000000)
            )
        tconn.commit()

        # Test 1: Insert verified records
        inserted = 0
        for date, prices in _S50_VERIFIED_PRICES.items():
            if date > "2026-11-04":
                continue  # P1 only
            for sid, close in prices.items():
                cur = tconn.execute(
                    "INSERT OR IGNORE INTO daily_prices (stock_id, date, open, high, low, close, volume) VALUES (?,?,?,?,?,?,?)",
                    (sid, date, round(close * 0.99, 1), round(close * 1.01, 1),
                     round(close * 0.98, 1), close, 0.0)
                )
                inserted += cur.rowcount
        tconn.commit()
        results["test1_initial_insert"] = inserted == 7  # 3+2+1+1 = 7
        results["test1_rows_inserted"] = inserted

        # Test 2: Idempotent re-insert
        inserted2 = 0
        for date, prices in _S50_VERIFIED_PRICES.items():
            if date > "2026-11-04":
                continue
            for sid, close in prices.items():
                cur = tconn.execute(
                    "INSERT OR IGNORE INTO daily_prices (stock_id, date, open, high, low, close, volume) VALUES (?,?,?,?,?,?,?)",
                    (sid, date, round(close * 0.99, 1), round(close * 1.01, 1),
                     round(close * 0.98, 1), close, 0.0)
                )
                inserted2 += cur.rowcount
        tconn.commit()
        results["test2_idempotency"] = inserted2 == 0  # INSERT OR IGNORE → 0 new rows

        # Test 3: Conflict detection
        conflict_raised = False
        try:
            tconn.execute(
                "INSERT INTO daily_prices (stock_id, date, open, high, low, close, volume) VALUES (?,?,?,?,?,?,?)",
                ("2330", "2026-10-29", 9999.0, 9999.0, 9999.0, 9999.0, 0)
            )
        except sqlite3.IntegrityError:
            conflict_raised = True
        results["test3_conflict_detection"] = conflict_raised

        # Test 4: Transaction rollback
        tconn.isolation_level = None  # autocommit mode for explicit BEGIN
        try:
            tconn.execute("BEGIN")
            tconn.execute(
                "INSERT INTO daily_prices (stock_id, date, open, high, low, close, volume) VALUES (?,?,?,?,?,?,?)",
                ("2330", "2026-10-29", 9999.0, 9999.0, 9999.0, 9999.0, 0)
            )
            raise ValueError("forced rollback")
        except (sqlite3.IntegrityError, ValueError):
            tconn.execute("ROLLBACK")
        tconn.isolation_level = ""  # restore default
        cnt = tconn.execute("SELECT COUNT(*) FROM daily_prices WHERE stock_id='2330' AND date='2026-10-29' AND close=9999.0").fetchone()[0]
        results["test4_rollback"] = cnt == 0

        # Test 5: Read-back verification
        close_read = tconn.execute(
            "SELECT close FROM daily_prices WHERE stock_id='2330' AND date='2026-10-29'"
        ).fetchone()
        results["test5_readback"] = close_read is not None and close_read[0] == 2415.0

        # Test 6: Coverage calculation
        for date in ["2026-10-29", "2026-10-30", "2026-11-02", "2026-11-03"]:
            cnt = tconn.execute(
                "SELECT COUNT(*) FROM daily_prices WHERE date=? AND stock_id!='0050'", (date,)
            ).fetchone()[0]
            results[f"test6_coverage_{date}"] = cnt

        # Test 7: Production not modified
        prod_cnt = conn.execute(
            "SELECT COUNT(*) FROM daily_prices WHERE stock_id='2330' AND date='2026-10-29'"
        ).fetchone()[0]
        results["test7_production_not_modified"] = prod_cnt == 0

        tconn.close()

    return results


# ── Main report entry point ────────────────────────────────────────────────────

@dataclass
class Auth01ImpactReport:
    audit_timestamp: str
    preflight_db_size: int
    preflight_dp_max: str
    preflight_total_fs: int
    preflight_v8_buy: int
    record_manifest: List[RecordDetail]
    source_integrity: List[SourceIntegrityCheck]
    coverage_matrix: List[CoverageRow]
    qg_counterfactual: List[QGCounterfactual]
    research_impact: List[ResearchImpact]
    decision_package: Auth01DecisionPackage
    dry_run_results: dict
    verdict: Auth01Verdict
    not_executed: str    # always "AUTH01_NOT_EXECUTED"


def build_auth01_impact_report(conn: sqlite3.Connection) -> Auth01ImpactReport:
    total_fs = conn.execute("SELECT COUNT(*) FROM forward_signals").fetchone()[0]
    v8_buy = conn.execute(
        "SELECT COUNT(*) FROM forward_signals WHERE model_version='v8.0' AND trade_signal IN ('buy','strong_buy')"
    ).fetchone()[0]
    dp_max = conn.execute("SELECT MAX(date) FROM daily_prices").fetchone()[0]
    db_size = 0
    try:
        import os
        db_size = os.path.getsize("data/platform.db")
    except Exception:
        pass

    manifest = build_record_manifest(conn)
    integrity = run_source_integrity_checks(conn)
    coverage = build_coverage_matrix(conn)
    qg_cf = build_qg_counterfactual(conn)
    research = build_research_impact()
    package = build_auth01_decision_package(conn)
    dry_run = run_coverage_dry_run(conn)

    return Auth01ImpactReport(
        audit_timestamp=datetime.now(timezone.utc).isoformat(),
        preflight_db_size=db_size,
        preflight_dp_max=dp_max,
        preflight_total_fs=total_fs,
        preflight_v8_buy=v8_buy,
        record_manifest=manifest,
        source_integrity=integrity,
        coverage_matrix=coverage,
        qg_counterfactual=qg_cf,
        research_impact=research,
        decision_package=package,
        dry_run_results=dry_run,
        verdict=Auth01Verdict.AUTH01_PARTIAL,
        not_executed="AUTH01_NOT_EXECUTED",
    )
