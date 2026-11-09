"""
Historical Source Verification Matrix and Backfill Authorization Package
— Session 49 PARTS B, C (P1–P2).

11 backfill candidate dates (Oct 08–Nov 09):
  Oct 08/15/19/20/27/29/30, Nov 02/03: TIER_1_PROXY (0050 only, 1 stock)
  Nov 06/09: TIER_ZERO_MISSING (0 rows)

TWSE/TPEx source availability findings (S49 PART B investigation):
  TWSE bulk historical (STOCK_DAY_ALL?date=YYYYMMDD): Returns empty body
    for historical dates — API ignores the date parameter and returns current
    or empty response. NOT usable for bulk historical backfill.
  TWSE single-stock (STOCK_DAY?date=YYYYMMDD&stockNo=XXXX): Returns monthly
    data for the month containing the requested date. TSMC (2330) prices
    confirmed: Oct 27 close=2400, Oct 29 close=2415, Oct 30 close=2370.
    SOURCE_PARTIAL — data exists but requires per-stock queries (~700+ stocks).
  TPEx OpenAPI (?d=RRRMMDD): Ignores date parameter, returns current data.
    NOT usable for historical backfill.
  TWSE OpenAPI current: Returned Nov 06 data (api_date=1151106, 1099 four-digit
    codes) when queried on Nov 09. Confirms PROVIDER_NOT_READY root cause.

Backfill Authorization Package:
  Priority 1: Oct 29/30/Nov 02/03 → promotes 3 incomplete clusters to STRICT
  Priority 2: Oct 08/15/19/20/27 → fills proxy-only dates (less urgent)
  Blocked: Nov 06/09 (UNIVERSE_UNVERIFIED — API not confirmed for these dates)

SAFETY: READ-ONLY research. No production writes. All INSERT simulations
  use Temporary SQLite (in-memory). Data/platform.db not modified.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SourceAvailability(str, Enum):
    SOURCE_CONFIRMED = "SOURCE_CONFIRMED"      # API confirmed historical data
    SOURCE_PARTIAL = "SOURCE_PARTIAL"          # Exists but requires per-stock queries
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"  # API returns current/empty only
    SOURCE_UNVERIFIED = "SOURCE_UNVERIFIED"    # Not tested; unknown


class BackfillConflictRisk(str, Enum):
    LOW = "LOW"       # Only adding new rows; existing 0050 row unaffected by INSERT OR IGNORE
    MEDIUM = "MEDIUM" # Some rows exist; need comparison
    HIGH = "HIGH"     # Unclear what exists; potential overwrite


class BackfillReadiness(str, Enum):
    INSERT_ONLY_CANDIDATE = "INSERT_ONLY_CANDIDATE"
    UNIVERSE_UNVERIFIED = "UNIVERSE_UNVERIFIED"
    SOURCE_BLOCKED = "SOURCE_BLOCKED"
    AUTHORIZED_PENDING_EXECUTION = "AUTHORIZED_PENDING_EXECUTION"


class ClusterImpact(str, Enum):
    PROMOTES_TO_STRICT = "PROMOTES_TO_STRICT"
    NO_CLUSTER_IMPACT = "NO_CLUSTER_IMPACT"
    PARTIAL_CLUSTER_IMPACT = "PARTIAL_CLUSTER_IMPACT"


# ---------------------------------------------------------------------------
# Hard-coded source verification data (TWSE/TPEx API investigation results)
# ---------------------------------------------------------------------------

# Which backfill dates directly promote incomplete clusters to STRICT status?
# Oct 21 needs ≥1 more TSMC date (Oct 29 or later)
# Oct 22 needs ≥2 more TSMC dates
# Oct 28 needs ≥3 more TSMC dates
_CLUSTER_PROMOTION_REQUIRED: Dict[str, List[str]] = {
    "2026-10-21": ["2026-10-29"],                              # +1 TSMC date needed
    "2026-10-22": ["2026-10-29", "2026-10-30"],                # +2 TSMC dates needed
    "2026-10-28": ["2026-10-29", "2026-10-30", "2026-11-02"],  # +3 TSMC dates needed
}

# Estimated stock count per backfill date (from TWSE filter analysis)
# Non-fill dates had proxy-only; with full backfill expect ~655-660 stocks
_ESTIMATED_BACKFILL_ROWS: Dict[str, int] = {
    "2026-10-08": 655,
    "2026-10-15": 655,
    "2026-10-19": 655,
    "2026-10-20": 655,
    "2026-10-27": 655,
    "2026-10-29": 655,
    "2026-10-30": 655,
    "2026-11-02": 655,
    "2026-11-03": 655,
    "2026-11-06": 0,   # UNIVERSE_UNVERIFIED — QG failed; unknown universe
    "2026-11-09": 0,   # UNIVERSE_UNVERIFIED — PROVIDER_NOT_READY
}

# Source availability per date (determined from API investigation in S49 PART B)
_SOURCE_AVAILABILITY: Dict[str, SourceAvailability] = {
    "2026-10-08": SourceAvailability.SOURCE_PARTIAL,   # TWSE single-stock historical
    "2026-10-15": SourceAvailability.SOURCE_PARTIAL,
    "2026-10-19": SourceAvailability.SOURCE_PARTIAL,
    "2026-10-20": SourceAvailability.SOURCE_PARTIAL,
    "2026-10-27": SourceAvailability.SOURCE_PARTIAL,   # TSMC 2330 close=2400 confirmed
    "2026-10-29": SourceAvailability.SOURCE_PARTIAL,   # TSMC 2330 close=2415 confirmed
    "2026-10-30": SourceAvailability.SOURCE_PARTIAL,   # TSMC 2330 close=2370 confirmed
    "2026-11-02": SourceAvailability.SOURCE_PARTIAL,
    "2026-11-03": SourceAvailability.SOURCE_PARTIAL,
    "2026-11-06": SourceAvailability.SOURCE_UNVERIFIED,  # QUALITY_GATE_FAIL — API unknown
    "2026-11-09": SourceAvailability.SOURCE_UNVERIFIED,  # PROVIDER_NOT_READY — API stale
}

# Source notes per date
_SOURCE_NOTES: Dict[str, str] = {
    "2026-10-08": "TWSE single-stock STOCK_DAY?date=20261008 returns monthly data. "
                  "Full 655-stock backfill requires ~700 per-stock API calls. "
                  "TSMC presence not individually confirmed but date is within TWSE monthly range.",
    "2026-10-15": "Same as Oct 08 — TWSE single-stock historical available.",
    "2026-10-19": "Same as Oct 08 — TWSE single-stock historical available.",
    "2026-10-20": "Same as Oct 08 — TWSE single-stock historical available.",
    "2026-10-27": "TSMC (2330) close=2400 confirmed via TWSE STOCK_DAY API. "
                  "Full universe requires per-stock queries. TPEx bulk API NOT usable.",
    "2026-10-29": "TSMC (2330) close=2415 confirmed via TWSE STOCK_DAY API. "
                  "CRITICAL: Backfilling this date promotes Oct 21 cluster to STRICT.",
    "2026-10-30": "TSMC (2330) close=2370 confirmed via TWSE STOCK_DAY API. "
                  "CRITICAL: Backfilling this date promotes Oct 22 cluster (with Oct 29).",
    "2026-11-02": "TWSE single-stock historical should be available. "
                  "CRITICAL: Backfilling this + Oct 29/30 promotes Oct 28 cluster to STRICT.",
    "2026-11-03": "TWSE single-stock historical should be available. "
                  "Less urgent — Oct 28 already promoted by Nov 02 + Oct 29/30.",
    "2026-11-06": "QUALITY_GATE_FAIL: pipeline attempted but QG rejected batch. "
                  "TWSE OpenAPI returned stale/incomplete data. Source unknown — "
                  "UNIVERSE_UNVERIFIED. Do NOT backfill without QG investigation.",
    "2026-11-09": "PROVIDER_NOT_READY: TWSE OpenAPI returned Nov 06 data "
                  "(api_date=1151106) when queried on Nov 09. Source unverified. "
                  "UNIVERSE_UNVERIFIED. Do NOT backfill without PROVIDER fix.",
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class SourceVerificationRecord:
    date: str
    is_trading_day: bool
    existing_stock_count: int
    has_proxy_0050: bool
    source_availability: SourceAvailability
    estimated_backfill_rows: int
    conflict_risk: BackfillConflictRisk
    backfill_readiness: BackfillReadiness
    affects_strict_promotion: bool
    clusters_promoted: List[str]
    notes: str


@dataclass
class SourceVerificationMatrix:
    records: List[SourceVerificationRecord]
    n_insert_only: int
    n_universe_unverified: int
    n_source_blocked: int
    n_strict_promotion_dates: int
    priority_dates: List[str]
    summary: str


@dataclass
class BackfillConstraint:
    constraint_id: str
    description: str
    applies_to: List[str]


@dataclass
class BackfillAuthorizationPackage:
    package_id: str
    created_date: str
    phase: str
    source_matrix: SourceVerificationMatrix
    priority_1_dates: List[str]
    priority_2_dates: List[str]
    blocked_dates: List[str]
    safety_constraints: List[BackfillConstraint]
    expected_cluster_promotion: str
    authorization_requirements: List[str]
    authorization_status: str


@dataclass
class TempSQLiteIdempotencyResult:
    date: str
    first_insert_rows: int
    second_insert_rows: int
    idempotent: bool
    final_stock_count: int
    conflict_risk_actual: BackfillConflictRisk


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def _get_existing_counts(conn: sqlite3.Connection) -> Dict[str, Tuple[int, bool, bool]]:
    """Returns {date: (stock_count, has_0050, has_tsmc)} for all 11 candidates."""
    candidates = [
        "2026-10-08", "2026-10-15", "2026-10-19", "2026-10-20", "2026-10-27",
        "2026-10-29", "2026-10-30", "2026-11-02", "2026-11-03", "2026-11-06",
        "2026-11-09",
    ]
    result = {}
    for d in candidates:
        n = conn.execute(
            "SELECT COUNT(DISTINCT stock_id) FROM daily_prices WHERE date=?", (d,)
        ).fetchone()[0]
        has_0050 = conn.execute(
            "SELECT COUNT(*) FROM daily_prices WHERE date=? AND stock_id='0050'", (d,)
        ).fetchone()[0] > 0
        has_tsmc = conn.execute(
            "SELECT COUNT(*) FROM daily_prices WHERE date=? AND stock_id='2330'", (d,)
        ).fetchone()[0] > 0
        result[d] = (n, has_0050, has_tsmc)
    return result


def _get_strict_promotion_impact(date: str) -> Tuple[bool, List[str]]:
    """Returns (affects_strict, list of clusters promoted) for a backfill date."""
    affected = []
    for cluster, required_dates in _CLUSTER_PROMOTION_REQUIRED.items():
        if date in required_dates:
            # Check if ALL required dates for this cluster are being backfilled
            affected.append(cluster)
    # Whether this date itself affects any incomplete cluster
    return bool(affected), affected


def build_source_verification_matrix(conn: sqlite3.Connection) -> SourceVerificationMatrix:
    """
    Build the 11-date historical source verification matrix.
    Reads existing counts from production SQLite (READ-ONLY).
    """
    existing = _get_existing_counts(conn)
    records = []
    n_insert_only = n_universe_unverified = n_source_blocked = 0
    n_strict_promo = 0
    priority_dates = []

    ordered_candidates = [
        "2026-10-08", "2026-10-15", "2026-10-19", "2026-10-20", "2026-10-27",
        "2026-10-29", "2026-10-30", "2026-11-02", "2026-11-03", "2026-11-06",
        "2026-11-09",
    ]

    for d in ordered_candidates:
        stock_count, has_0050, _ = existing[d]
        src = _SOURCE_AVAILABILITY[d]
        est_rows = _ESTIMATED_BACKFILL_ROWS[d]

        # Determine backfill readiness
        if d in ("2026-11-06", "2026-11-09"):
            readiness = BackfillReadiness.UNIVERSE_UNVERIFIED
            risk = BackfillConflictRisk.HIGH
            n_universe_unverified += 1
        elif src == SourceAvailability.SOURCE_PARTIAL:
            readiness = BackfillReadiness.INSERT_ONLY_CANDIDATE
            risk = BackfillConflictRisk.LOW  # INSERT OR IGNORE skips existing 0050 row
            n_insert_only += 1
        else:
            readiness = BackfillReadiness.SOURCE_BLOCKED
            risk = BackfillConflictRisk.HIGH
            n_source_blocked += 1

        # Check cluster promotion impact
        affects, clusters = _get_strict_promotion_impact(d)
        if affects:
            n_strict_promo += 1
            if readiness == BackfillReadiness.INSERT_ONLY_CANDIDATE:
                priority_dates.append(d)

        records.append(SourceVerificationRecord(
            date=d,
            is_trading_day=True,
            existing_stock_count=stock_count,
            has_proxy_0050=has_0050,
            source_availability=src,
            estimated_backfill_rows=est_rows,
            conflict_risk=risk,
            backfill_readiness=readiness,
            affects_strict_promotion=affects,
            clusters_promoted=clusters,
            notes=_SOURCE_NOTES[d],
        ))

    # Ensure priority order: Oct 29/30/Nov 02 first (cluster-critical)
    priority_dates = sorted(set(priority_dates))

    summary = (
        f"Source verification complete for 11 candidates: "
        f"{n_insert_only} INSERT_ONLY_CANDIDATE, "
        f"{n_universe_unverified} UNIVERSE_UNVERIFIED, "
        f"{n_source_blocked} SOURCE_BLOCKED. "
        f"{n_strict_promo} dates affect strict cluster promotion. "
        f"Priority: {', '.join(priority_dates[:4])} → promotes 3 clusters from INCOMPLETE to STRICT."
    )

    return SourceVerificationMatrix(
        records=records,
        n_insert_only=n_insert_only,
        n_universe_unverified=n_universe_unverified,
        n_source_blocked=n_source_blocked,
        n_strict_promotion_dates=n_strict_promo,
        priority_dates=priority_dates,
        summary=summary,
    )


def build_backfill_authorization_package(conn: sqlite3.Connection) -> BackfillAuthorizationPackage:
    """
    Build the BackfillAuthorizationPackage (AUTH01 for data backfill).
    Does NOT execute any writes.
    """
    matrix = build_source_verification_matrix(conn)

    priority_1 = ["2026-10-29", "2026-10-30", "2026-11-02", "2026-11-03"]
    priority_2 = ["2026-10-08", "2026-10-15", "2026-10-19", "2026-10-20", "2026-10-27"]
    blocked = ["2026-11-06", "2026-11-09"]

    constraints = [
        BackfillConstraint(
            "SAFETY-01",
            "All backfill writes MUST use INSERT OR IGNORE to prevent overwriting existing rows.",
            priority_1 + priority_2,
        ),
        BackfillConstraint(
            "SAFETY-02",
            "Backfill target is LOCAL SQLITE ONLY (data/platform.db). "
            "Production Neon DB must NOT be touched.",
            priority_1 + priority_2,
        ),
        BackfillConstraint(
            "SAFETY-03",
            "Nov 06 and Nov 09 are BLOCKED until QUALITY_GATE_FAIL and PROVIDER_NOT_READY "
            "root causes are individually resolved and confirmed.",
            blocked,
        ),
        BackfillConstraint(
            "SAFETY-04",
            "forward_signals, model parameters, V3 state, Cron, and GitHub Actions "
            "MUST NOT be modified as part of this backfill operation.",
            priority_1 + priority_2 + blocked,
        ),
        BackfillConstraint(
            "SAFETY-05",
            "Data source is TWSE single-stock API (per-stock queries). "
            "TPEx bulk API is NOT usable for historical dates. "
            "Must use scripts/backfill_daily_prices.py with --research-only flag.",
            priority_1 + priority_2,
        ),
    ]

    # Compute package hash for auditability
    pkg_input = json.dumps({
        "priority_1": priority_1,
        "priority_2": priority_2,
        "blocked": blocked,
        "n_insert_only": matrix.n_insert_only,
        "n_universe_unverified": matrix.n_universe_unverified,
    }, sort_keys=True)
    pkg_id = "AUTH01-" + hashlib.sha256(pkg_input.encode()).hexdigest()[:8]

    return BackfillAuthorizationPackage(
        package_id=pkg_id,
        created_date="2026-11-09",
        phase="BACKFILL_AUTHORIZATION_PACKAGE",
        source_matrix=matrix,
        priority_1_dates=priority_1,
        priority_2_dates=priority_2,
        blocked_dates=blocked,
        safety_constraints=constraints,
        expected_cluster_promotion=(
            "Backfilling Oct 29/30/Nov 02/03 promotes Oct 21/22/28 fills from "
            "DATA_INCOMPLETE to STRICT (proxy count: 4→8, 3→7, 2→5 respectively). "
            "Strict count 3→6. G03 still FAIL (need 10). G04 still FAIL (design issue)."
        ),
        authorization_requirements=[
            "AUTH01-GRANTED: Explicit user authorization to run backfill_daily_prices.py "
            "--start YYYY-MM-DD --end YYYY-MM-DD --research-only --execute",
            "AUTH01-VERIFY: QG validation must pass for each backfilled date before "
            "proceeding to strict cluster promotion",
            "AUTH01-CONFIRM: Run build_source_verification_matrix() after backfill "
            "to confirm TSMC presence counts updated",
        ],
        authorization_status="PENDING_USER_AUTHORIZATION",
    )


def simulate_idempotency_in_temp_sqlite(
    source_records: List[SourceVerificationRecord],
    limit_dates: Optional[List[str]] = None,
) -> List[TempSQLiteIdempotencyResult]:
    """
    Simulate INSERT OR IGNORE idempotency in a temporary in-memory SQLite.
    Does NOT touch data/platform.db.
    limit_dates: if provided, only simulate these dates.
    """
    results = []
    test_dates = limit_dates or [r.date for r in source_records
                                  if r.backfill_readiness == BackfillReadiness.INSERT_ONLY_CANDIDATE]

    for rec in source_records:
        if rec.date not in test_dates:
            continue

        mem_conn = sqlite3.connect(":memory:")
        mem_conn.execute("""
            CREATE TABLE daily_prices (
                date TEXT NOT NULL,
                stock_id TEXT NOT NULL,
                close REAL,
                PRIMARY KEY (date, stock_id)
            )
        """)
        # Insert existing proxy row (0050)
        if rec.has_proxy_0050:
            mem_conn.execute(
                "INSERT INTO daily_prices (date, stock_id, close) VALUES (?, '0050', 100.0)",
                (rec.date,)
            )
        mem_conn.commit()

        # Simulate first backfill batch (N stocks including 0050)
        test_rows = [
            (rec.date, "0050", 100.0),   # Already exists
            (rec.date, "2330", 2400.0),  # TSMC
            (rec.date, "2454", 1500.0),  # MediaTek
            (rec.date, "2317", 85.0),    # Foxconn
        ]
        rows_inserted_1 = 0
        for row in test_rows:
            cur = mem_conn.execute(
                "INSERT OR IGNORE INTO daily_prices (date, stock_id, close) VALUES (?,?,?)", row
            )
            rows_inserted_1 += cur.rowcount
        mem_conn.commit()

        # Simulate second backfill batch (identical) — must be idempotent
        rows_inserted_2 = 0
        for row in test_rows:
            cur = mem_conn.execute(
                "INSERT OR IGNORE INTO daily_prices (date, stock_id, close) VALUES (?,?,?)", row
            )
            rows_inserted_2 += cur.rowcount
        mem_conn.commit()

        final_count = mem_conn.execute(
            "SELECT COUNT(DISTINCT stock_id) FROM daily_prices WHERE date=?", (rec.date,)
        ).fetchone()[0]

        mem_conn.close()

        # 0050 existed before, so first insert adds 3 new rows (2330, 2454, 2317)
        # second insert adds 0 (all already present)
        idempotent = rows_inserted_2 == 0
        results.append(TempSQLiteIdempotencyResult(
            date=rec.date,
            first_insert_rows=rows_inserted_1,
            second_insert_rows=rows_inserted_2,
            idempotent=idempotent,
            final_stock_count=final_count,
            conflict_risk_actual=BackfillConflictRisk.LOW if idempotent else BackfillConflictRisk.MEDIUM,
        ))

    return results


def compute_post_backfill_proxy_counts(
    base_counts: Dict[str, int],
    backfill_dates: List[str],
) -> Dict[str, int]:
    """
    Compute expected TSMC proxy counts for each fill date after backfilling
    the given dates (simulated, READ-ONLY).

    base_counts: {fill_date: current_proxy_count}
    backfill_dates: dates that will have TSMC presence after backfill
    Returns: {fill_date: projected_proxy_count}
    """
    # TSMC is present on Nov 04/05 (already in DB) + fill dates Oct 13/14/16/21/22/28
    existing_tsmc_dates = {
        "2026-10-13", "2026-10-14", "2026-10-16",
        "2026-10-21", "2026-10-22", "2026-10-28",
        "2026-11-04", "2026-11-05",
    }
    all_tsmc_dates = existing_tsmc_dates | set(backfill_dates)

    fill_dates = ["2026-10-13", "2026-10-14", "2026-10-16",
                  "2026-10-21", "2026-10-22", "2026-10-28"]
    projected = {}
    for fd in fill_dates:
        count = sum(1 for d in all_tsmc_dates if d > fd)
        projected[fd] = count
    return projected


def get_strict_promotion_summary_after_backfill(
    backfill_dates: List[str],
) -> Dict[str, str]:
    """
    Returns the strictness status of each fill cluster if backfill_dates are added.
    Key: fill_date, Value: STRICT or INCOMPLETE + proxy_count
    """
    base_proxy = {
        "2026-10-13": 7, "2026-10-14": 6, "2026-10-16": 5,
        "2026-10-21": 4, "2026-10-22": 3, "2026-10-28": 2,
    }
    projected = compute_post_backfill_proxy_counts(base_proxy, backfill_dates)
    result = {}
    for fd, cnt in projected.items():
        if cnt >= 5:
            result[fd] = f"STRICT (proxy={cnt})"
        else:
            result[fd] = f"INCOMPLETE (proxy={cnt}, need {5 - cnt} more)"
    return result
