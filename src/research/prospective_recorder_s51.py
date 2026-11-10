"""
src/research/prospective_recorder_s51.py — S51 PARTS D, E, F, G

PART D: Prospective Evidence Protocol
  Classification hierarchy: V3_DECISION_PROSPECTIVE > BASE_SIGNAL_PROSPECTIVE >
  RETROSPECTIVE_RECONSTRUCTION > PROVENANCE_UNVERIFIED.

  Core principle: genuine Prospective Evidence requires the COMPLETE V3 decision
  (including V3-specific timing analysis) to be frozen BEFORE the fill/execution date.
  A v8.0 signal locked before execution_date achieves BASE_SIGNAL_PROSPECTIVE at best.

PART E: Independent Cluster Collection Protocol
  ProspectiveClusterCollectionPlan — pre-registration rules, spacing constraints,
  expected timeline for collecting N=10 independent prospective clusters.

PART F: Prospective Recorder Prototype
  ImmutableProspectiveRecorder — append-only research-only temp SQLite prototype.
  NEVER touches data/platform.db. Mutation detection via SHA-256 payload hash.

PART G: Backfill Authorization Readiness
  AUTH01 readiness assessment per fill date using S50 VerifiedSourceMatrix and
  the current DB state.

SAFETY CONSTRAINTS (unchanged from S44–S51):
  - ProspectiveRecorder writes ONLY to a temp/in-memory SQLite — NEVER platform.db.
  - No production writes to forward_signals, daily_prices, or Neon.
  - V3 parameters, hybrid P1–P4, and MODEL_VERSION v8.0 are frozen.
  - RULE_FREEZE_DATE = 2026-11-05: signals before this are RETROSPECTIVE_RECONSTRUCTION
    when assessed for V3 purposes.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import List, Optional, Tuple

# ── PART D: Evidence Classification ───────────────────────────────────────────

RULE_FREEZE_DATE = date(2026, 11, 5)
"""Signals before this date are RETROSPECTIVE_RECONSTRUCTION for V3 assessment."""

V3_PARAMETER_HASH = "be43e8ca977d9fdd"
"""Frozen V3 parameter hash. Must not change."""

MODEL_VERSION_FROZEN = "v8.0"
"""Frozen production model version."""


class DecisionClassification(str, Enum):
    V3_DECISION_PROSPECTIVE = "V3_DECISION_PROSPECTIVE"
    """
    Complete V3 decision (including V3-specific entry timing signal) was frozen
    BEFORE the fill/execution date. This is the gold standard for Prospective Evidence.
    Currently not achievable: V3 is not activated and no V3 decisions exist.
    """

    BASE_SIGNAL_PROSPECTIVE = "BASE_SIGNAL_PROSPECTIVE"
    """
    v8.0 signal was locked (locked_at < execution_date) but V3 decision was NOT
    frozen pre-fill. The base signal is prospective; the full V3 decision is not.
    This is the best achievable level for existing Oct 13–28 clusters.
    """

    RETROSPECTIVE_RECONSTRUCTION = "RETROSPECTIVE_RECONSTRUCTION"
    """
    Decision was constructed AFTER the fill/execution date, or for a date before
    RULE_FREEZE_DATE (2026-11-05). Cannot contribute to prospective evidence.
    All 21 hybrid_forward_decision rows (Nov 04) have this classification.
    """

    PROVENANCE_UNVERIFIED = "PROVENANCE_UNVERIFIED"
    """
    locked_at timestamp is missing, inconsistent, or could not be validated.
    """


class ProspectiveCollectionVerdict(str, Enum):
    ELIGIBLE_PROSPECTIVE = "ELIGIBLE_PROSPECTIVE"
    ELIGIBLE_BASE_SIGNAL = "ELIGIBLE_BASE_SIGNAL"
    BLOCKED_RULE_FREEZE = "BLOCKED_RULE_FREEZE"
    BLOCKED_NO_SIGNAL = "BLOCKED_NO_SIGNAL"
    BLOCKED_PROVENANCE = "BLOCKED_PROVENANCE"


class Auth01ReadinessVerdict(str, Enum):
    READY = "READY"
    PENDING_AUTHORIZATION = "PENDING_AUTHORIZATION"
    BLOCKED_NO_SOURCE = "BLOCKED_NO_SOURCE"
    ALREADY_COVERED = "ALREADY_COVERED"


# ── PART D: Dataclasses ────────────────────────────────────────────────────────

@dataclass
class FillClusterEvidence:
    """Evidence summary for a single fill cluster (execution_date)."""

    execution_date: str             # e.g. "2026-10-13"
    trade_date: str                 # signal generation date (day before execution)
    signal_count_v8: int            # number of v8.0 signals for this cluster
    first_locked_at: Optional[str]  # earliest locked_at among v8.0 signals
    locked_before_execution: bool   # first_locked_at < execution_date
    v3_decision_frozen: bool        # was a complete V3 decision frozen pre-fill?
    classification: DecisionClassification
    classification_reason: str


@dataclass
class ImmutableDecisionPayload:
    """
    Immutable record of a prospective decision. Used by ProspectiveRecorder.
    Computed SHA-256 fingerprint detects mutation.
    """
    fill_date: str            # execution_date in forward_signals
    signal_id: int            # forward_signals.id
    stock_id: str
    model_version: str        # must equal MODEL_VERSION_FROZEN
    locked_at: str            # forward_signals.locked_at
    trade_signal: str         # "buy" / "strong_buy" / "wait" / etc.
    v3_decision_snapshot: Optional[str]  # None until V3 is activated
    classification: DecisionClassification
    registered_at: str        # ISO timestamp of research registration
    research_fingerprint: str = field(default="")  # set by _compute_fingerprint()

    def __post_init__(self) -> None:
        if not self.research_fingerprint:
            self.research_fingerprint = _compute_fingerprint(self)

    def verify(self) -> bool:
        """Return True if the payload has not been mutated since creation."""
        expected = _compute_fingerprint(self)
        return self.research_fingerprint == expected


def _compute_fingerprint(payload: "ImmutableDecisionPayload") -> str:
    """SHA-256 fingerprint of immutable fields (excludes research_fingerprint itself)."""
    blob = json.dumps({
        "fill_date": payload.fill_date,
        "signal_id": payload.signal_id,
        "stock_id": payload.stock_id,
        "model_version": payload.model_version,
        "locked_at": payload.locked_at,
        "trade_signal": payload.trade_signal,
        "v3_decision_snapshot": payload.v3_decision_snapshot,
        "classification": payload.classification,
        "registered_at": payload.registered_at,
    }, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


# ── PART D: Cluster classification ────────────────────────────────────────────

def classify_fill_cluster(
    execution_date: str,
    first_locked_at: Optional[str],
    signal_count: int,
    v3_decision_frozen: bool = False,
) -> Tuple[DecisionClassification, str]:
    """
    Classify a fill cluster based on evidence.

    Returns (classification, reason_string).
    """
    if signal_count == 0:
        return (
            DecisionClassification.PROVENANCE_UNVERIFIED,
            f"No v8.0 signals found for execution_date={execution_date}.",
        )

    if first_locked_at is None:
        return (
            DecisionClassification.PROVENANCE_UNVERIFIED,
            f"locked_at is NULL for execution_date={execution_date} signals.",
        )

    exec_d = date.fromisoformat(execution_date)

    if exec_d < RULE_FREEZE_DATE:
        # Pre-freeze: check if locked_at < execution_date for base signal
        locked_d = date.fromisoformat(first_locked_at[:10])
        if locked_d >= exec_d:
            return (
                DecisionClassification.RETROSPECTIVE_RECONSTRUCTION,
                f"locked_at={first_locked_at[:10]} >= execution_date={execution_date}: "
                "signal was not frozen before execution.",
            )
        # locked_at is before execution_date AND before RULE_FREEZE_DATE
        # V3 is not activated → V3_DECISION_PROSPECTIVE is not achievable
        if v3_decision_frozen:
            return (
                DecisionClassification.V3_DECISION_PROSPECTIVE,
                f"Complete V3 decision frozen before execution_date={execution_date}.",
            )
        return (
            DecisionClassification.BASE_SIGNAL_PROSPECTIVE,
            f"v8.0 signal locked_at={first_locked_at[:10]} < execution_date={execution_date}. "
            "V3 decision was NOT frozen pre-fill (V3 not activated). "
            "BASE_SIGNAL_PROSPECTIVE is the best achievable level.",
        )

    # exec_d >= RULE_FREEZE_DATE — in principle eligible for V3
    if v3_decision_frozen:
        return (
            DecisionClassification.V3_DECISION_PROSPECTIVE,
            f"Complete V3 decision frozen before execution_date={execution_date} "
            f"(>= RULE_FREEZE_DATE {RULE_FREEZE_DATE}).",
        )

    locked_d = date.fromisoformat(first_locked_at[:10])
    if locked_d < exec_d:
        return (
            DecisionClassification.BASE_SIGNAL_PROSPECTIVE,
            f"v8.0 signal locked_at={first_locked_at[:10]} < execution_date={execution_date}. "
            "V3 not activated → V3_DECISION_PROSPECTIVE not achievable. "
            "BASE_SIGNAL_PROSPECTIVE.",
        )

    return (
        DecisionClassification.RETROSPECTIVE_RECONSTRUCTION,
        f"locked_at={first_locked_at[:10]} >= execution_date={execution_date}: "
        "not frozen before execution.",
    )


def build_fill_cluster_evidence(db_path: str) -> List[FillClusterEvidence]:
    """
    Query DB (read-only) to classify all 6 fill clusters.

    Returns list of FillClusterEvidence, one per execution_date.
    """
    fill_dates = [
        "2026-10-13", "2026-10-14", "2026-10-16",
        "2026-10-21", "2026-10-22", "2026-10-28",
    ]
    results: List[FillClusterEvidence] = []

    try:
        conn = sqlite3.connect(db_path)
        for fd in fill_dates:
            row = conn.execute("""
                SELECT COUNT(*), MIN(trade_date), MIN(locked_at)
                FROM forward_signals
                WHERE execution_date=? AND model_version='v8.0'
                AND is_valid=1
            """, (fd,)).fetchone()
            count = row[0] or 0
            trade_date = row[1] or ""
            first_locked = row[2]

            locked_before = (
                first_locked is not None
                and first_locked[:10] < fd
            )

            classification, reason = classify_fill_cluster(
                execution_date=fd,
                first_locked_at=first_locked,
                signal_count=count,
                v3_decision_frozen=False,  # V3 not activated
            )
            results.append(FillClusterEvidence(
                execution_date=fd,
                trade_date=trade_date,
                signal_count_v8=count,
                first_locked_at=first_locked,
                locked_before_execution=locked_before,
                v3_decision_frozen=False,
                classification=classification,
                classification_reason=reason,
            ))
        conn.close()
    except Exception:
        pass

    return results


# ── PART E: Collection Protocol ────────────────────────────────────────────────

@dataclass
class ProspectiveClusterSpec:
    """Specification for a single prospective cluster."""

    target_execution_date: str     # expected fill/execution date
    pre_registration_deadline: str # must register BEFORE market open on this date
    min_td_gap_from_prev: int      # minimum trading-day gap from previous cluster
    expected_stock_count_min: int  # minimum stocks for this date to count
    collection_verdict: ProspectiveCollectionVerdict
    notes: str = ""


@dataclass
class ProspectiveClusterCollectionPlan:
    """
    Pre-registration protocol for collecting N=10 independent prospective clusters.

    Design constraints:
      1. PRE-REGISTRATION: decision must be recorded BEFORE market open of execution_date.
      2. SPACING: minimum 6 TD gap between consecutive clusters to satisfy G04 (zero overlap).
      3. MIN_STOCKS: execution_date must have >= 300 stocks in daily_prices.
      4. COVERAGE_GATE: same threshold as check_benchmark_only_completion_rule (threshold=5000).
      5. V3_REQUIREMENT: V3 must be activated before any cluster can achieve V3_DECISION_PROSPECTIVE.
      6. G03_TARGET: N=10 independent clusters needed to pass G03.
      7. TIMELINE: at 6 TD per cluster, 10 clusters require ≥ 60 TD ≈ 12 calendar weeks.

    Current state (2026-11-10):
      - 0 V3_DECISION_PROSPECTIVE clusters (V3 not activated)
      - 0 BASE_SIGNAL_PROSPECTIVE clusters with ≥6 TD spacing from each other
        (Oct 13/14/16/21/22/28 all ≤5 TD apart — G04 fails)
      - Activation blocked by G03 and G04 failures
    """

    target_n: int = 10
    min_td_gap: int = 6
    min_stocks_per_date: int = 300
    coverage_threshold: int = 5000
    rule_freeze_date: str = "2026-11-05"
    v3_parameter_hash: str = V3_PARAMETER_HASH
    model_version: str = MODEL_VERSION_FROZEN
    planned_clusters: List[ProspectiveClusterSpec] = field(default_factory=list)
    current_v3_prospective: int = 0
    current_base_signal: int = 0
    g03_status: str = "FAIL"
    g04_status: str = "FAIL"
    collection_verdict: str = "FRAMEWORK_READY_COLLECTION_PENDING"

    def clusters_needed(self) -> int:
        return max(0, self.target_n - self.current_v3_prospective)

    def estimated_weeks_remaining(self) -> float:
        gaps_needed = self.clusters_needed() - 1
        if gaps_needed <= 0:
            return 0.0
        td_needed = gaps_needed * self.min_td_gap
        return td_needed / 5.0  # 5 TD per week


def build_prospective_collection_plan() -> ProspectiveClusterCollectionPlan:
    """
    Build the collection plan based on current state (2026-11-10).

    Current constraints:
      - V3 not activated → no V3_DECISION_PROSPECTIVE possible
      - G03 FAIL (0/10), G04 FAIL (structural)
      - Pipeline down since Nov 05 → no new fill dates available
      - Need pipeline restoration first (AUTH01 + pipeline fix)
    """
    plan = ProspectiveClusterCollectionPlan(
        current_v3_prospective=0,
        current_base_signal=0,
        g03_status="FAIL",
        g04_status="FAIL",
        collection_verdict="FRAMEWORK_READY_COLLECTION_PENDING",
    )

    # Pre-registration rules (append-only):
    plan.planned_clusters = [
        ProspectiveClusterSpec(
            target_execution_date="PENDING — pipeline must be restored first",
            pre_registration_deadline="Must be BEFORE market open of execution_date",
            min_td_gap_from_prev=6,
            expected_stock_count_min=300,
            collection_verdict=ProspectiveCollectionVerdict.BLOCKED_NO_SIGNAL,
            notes=(
                "Pipeline restoration required before any new fill dates. "
                "AUTH01 (backfill Oct 29/30/Nov 02/03) must be granted first. "
                "Then pipeline must run successfully for 1+ date."
            ),
        )
    ]

    return plan


# ── PART F: Prospective Recorder Prototype ─────────────────────────────────────

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS prospective_decisions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    fill_date        TEXT NOT NULL,
    signal_id        INTEGER NOT NULL,
    stock_id         TEXT NOT NULL,
    model_version    TEXT NOT NULL,
    locked_at        TEXT NOT NULL,
    trade_signal     TEXT NOT NULL,
    v3_snapshot      TEXT,
    classification   TEXT NOT NULL,
    registered_at    TEXT NOT NULL,
    fingerprint      TEXT NOT NULL,
    UNIQUE(fill_date, signal_id)
);

CREATE TABLE IF NOT EXISTS recorder_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class ProspectiveRecorderPrototype:
    """
    Append-only research-only prospective decision recorder.

    SAFETY:
      - Writes ONLY to a temp or provided SQLite path — NEVER to data/platform.db.
      - Mutations are detected via SHA-256 payload fingerprint.
      - No production imports, no Neon writes.
    """

    _PRODUCTION_PATH_MARKER = "platform.db"

    def __init__(self, db_path: Optional[str] = None) -> None:
        if db_path is None:
            # Create a named temp file (deleted on close)
            self._tmpfile = tempfile.NamedTemporaryFile(
                suffix=".db", prefix="prospective_recorder_s51_", delete=False
            )
            db_path = self._tmpfile.name
            self._tmpfile.close()
        else:
            self._tmpfile = None

        # Safety guard: refuse to write to production DB
        if self._PRODUCTION_PATH_MARKER in os.path.basename(db_path):
            raise ValueError(
                f"ProspectiveRecorder safety: refusing to write to production DB path={db_path!r}. "
                "Use a temp file or dedicated research path."
            )

        self._db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.executescript(_SCHEMA_SQL)
        self._conn.execute(
            "INSERT OR IGNORE INTO recorder_meta (key, value) VALUES (?, ?)",
            ("session", "S51"),
        )
        self._conn.execute(
            "INSERT OR IGNORE INTO recorder_meta (key, value) VALUES (?, ?)",
            ("v3_hash", V3_PARAMETER_HASH),
        )
        self._conn.commit()

    def register(self, payload: ImmutableDecisionPayload) -> bool:
        """
        Append a decision record.  Idempotent: same (fill_date, signal_id) is a no-op.
        Returns True if newly inserted, False if already present.
        """
        if not payload.verify():
            raise ValueError(
                f"Payload fingerprint mismatch — mutation detected: "
                f"fill_date={payload.fill_date}, signal_id={payload.signal_id}"
            )
        try:
            cur = self._conn.execute(
                """
                INSERT OR IGNORE INTO prospective_decisions
                (fill_date, signal_id, stock_id, model_version, locked_at,
                 trade_signal, v3_snapshot, classification, registered_at, fingerprint)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.fill_date, payload.signal_id, payload.stock_id,
                    payload.model_version, payload.locked_at, payload.trade_signal,
                    payload.v3_decision_snapshot, payload.classification,
                    payload.registered_at, payload.research_fingerprint,
                ),
            )
            self._conn.commit()
            # rowcount == 1 means newly inserted; 0 or -1 means IGNORE (duplicate)
            return cur.rowcount == 1
        except Exception as exc:
            raise RuntimeError(f"Register failed: {exc}") from exc

    def verify_all(self) -> Tuple[int, int]:
        """
        Verify all stored records against their fingerprints.
        Returns (valid_count, invalid_count).
        """
        rows = self._conn.execute(
            "SELECT fill_date, signal_id, stock_id, model_version, locked_at, "
            "trade_signal, v3_snapshot, classification, registered_at, fingerprint "
            "FROM prospective_decisions"
        ).fetchall()
        valid = invalid = 0
        for r in rows:
            payload = ImmutableDecisionPayload(
                fill_date=r[0], signal_id=r[1], stock_id=r[2],
                model_version=r[3], locked_at=r[4], trade_signal=r[5],
                v3_decision_snapshot=r[6], classification=r[7],
                registered_at=r[8], research_fingerprint=r[9],
            )
            if payload.verify():
                valid += 1
            else:
                invalid += 1
        return valid, invalid

    def count(self) -> int:
        return self._conn.execute(
            "SELECT COUNT(*) FROM prospective_decisions"
        ).fetchone()[0]

    def close(self) -> None:
        self._conn.close()
        if self._tmpfile is not None:
            try:
                os.unlink(self._db_path)
            except FileNotFoundError:
                pass

    def __enter__(self) -> "ProspectiveRecorderPrototype":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


# ── PART G: Backfill Authorization Readiness ──────────────────────────────────

@dataclass
class BackfillReadinessRecord:
    date: str
    tier: str
    current_stock_count: int
    target_stock_count: int
    source_verified: bool          # TWSE single-stock API confirmed available (S50)
    auth01_verdict: Auth01ReadinessVerdict
    notes: str = ""

    @property
    def gap(self) -> int:
        return max(0, self.target_stock_count - self.current_stock_count)


@dataclass
class BackfillAuthorizationReadiness:
    dates: List[BackfillReadinessRecord]
    auth01_overall: str  # "PENDING" / "GRANTED" / "NOT_REQUIRED"
    analysis_date: str = "2026-11-10"
    session: str = "S51"

    def pending_dates(self) -> List[str]:
        return [
            r.date for r in self.dates
            if r.auth01_verdict == Auth01ReadinessVerdict.PENDING_AUTHORIZATION
        ]

    def ready_dates(self) -> List[str]:
        return [
            r.date for r in self.dates
            if r.auth01_verdict == Auth01ReadinessVerdict.READY
        ]


def build_backfill_authorization_readiness(
    db_path: str,
) -> BackfillAuthorizationReadiness:
    """
    Assess AUTH01 readiness for each date needing recovery (read-only).

    Uses S50 VerifiedSourceMatrix findings:
      TIER_1_PROXY dates: TWSE single-stock API can provide ~600 stocks/date.
      Nov 06/09: TWSE single-stock API confirmed (S50 B2: TSMC C=2135/2235).
    """
    records: List[BackfillReadinessRecord] = []

    # Tier 1 proxy dates: 0050 only → need full market recovery
    tier1_dates = ["2026-10-29", "2026-10-30", "2026-11-02", "2026-11-03"]
    for d in tier1_dates:
        try:
            conn = sqlite3.connect(db_path)
            cnt = conn.execute(
                "SELECT COUNT(DISTINCT stock_id) FROM daily_prices WHERE date=?", (d,)
            ).fetchone()[0]
            conn.close()
        except Exception:
            cnt = 0
        records.append(BackfillReadinessRecord(
            date=d,
            tier="TIER_1_PROXY",
            current_stock_count=cnt,
            target_stock_count=600,
            source_verified=True,  # S50: TWSE single-stock confirmed
            auth01_verdict=Auth01ReadinessVerdict.PENDING_AUTHORIZATION,
            notes=(
                "TWSE single-stock API can provide ~600 stocks. "
                "Requires AUTH01 to execute recovery (~600 API calls). "
                "Currently: 0050 only (1 stock)."
            ),
        ))

    # Nov 06: BLOCKED_QG — quality gate failed, 0 rows
    try:
        conn = sqlite3.connect(db_path)
        cnt6 = conn.execute(
            "SELECT COUNT(DISTINCT stock_id) FROM daily_prices WHERE date='2026-11-06'"
        ).fetchone()[0]
        conn.close()
    except Exception:
        cnt6 = 0
    records.append(BackfillReadinessRecord(
        date="2026-11-06",
        tier="BLOCKED_QG",
        current_stock_count=cnt6,
        target_stock_count=600,
        source_verified=True,  # S50: TSMC C=2135 confirmed
        auth01_verdict=Auth01ReadinessVerdict.PENDING_AUTHORIZATION,
        notes=(
            "Quality gate previously failed for bulk approach. "
            "TWSE single-stock API confirmed available (S50 B2: TSMC C=2135). "
            "Individual stock recovery (~600 calls) pending AUTH01."
        ),
    ))

    # Nov 09: BLOCKED_STALE_DATA — TWSE stale, 0 rows
    try:
        conn = sqlite3.connect(db_path)
        cnt9 = conn.execute(
            "SELECT COUNT(DISTINCT stock_id) FROM daily_prices WHERE date='2026-11-09'"
        ).fetchone()[0]
        conn.close()
    except Exception:
        cnt9 = 0
    records.append(BackfillReadinessRecord(
        date="2026-11-09",
        tier="BLOCKED_STALE_DATA",
        current_stock_count=cnt9,
        target_stock_count=600,
        source_verified=True,  # S50: TSMC C=2235 confirmed
        auth01_verdict=Auth01ReadinessVerdict.PENDING_AUTHORIZATION,
        notes=(
            "TWSE bulk returned stale Nov 06 data for Nov 09 target. "
            "TWSE single-stock API confirmed available (S50 B2: TSMC C=2235). "
            "Individual stock recovery (~600 calls) pending AUTH01."
        ),
    ))

    # Nov 04/05: already well-covered (> 5000 stocks)
    for d_pair, tier in [("2026-11-04", "TIER_6957_BACKFILL"),
                          ("2026-11-05", "TIER_6957_BACKFILL")]:
        try:
            conn = sqlite3.connect(db_path)
            cnt = conn.execute(
                "SELECT COUNT(DISTINCT stock_id) FROM daily_prices WHERE date=?", (d_pair,)
            ).fetchone()[0]
            conn.close()
        except Exception:
            cnt = 0
        verdict = (
            Auth01ReadinessVerdict.ALREADY_COVERED
            if cnt >= 5000
            else Auth01ReadinessVerdict.PENDING_AUTHORIZATION
        )
        records.append(BackfillReadinessRecord(
            date=d_pair,
            tier=tier,
            current_stock_count=cnt,
            target_stock_count=5000,
            source_verified=True,
            auth01_verdict=verdict,
            notes=(
                f"{cnt} stocks in DB ({'✓ above' if cnt >= 5000 else '✗ below'} 5000 threshold). "
                "No auth required for already-covered dates."
                if cnt >= 5000
                else "Below threshold — may need additional backfill."
            ),
        ))

    pending = [r for r in records if r.auth01_verdict == Auth01ReadinessVerdict.PENDING_AUTHORIZATION]
    overall = "PENDING" if pending else "NOT_REQUIRED"

    return BackfillAuthorizationReadiness(
        dates=records,
        auth01_overall=overall,
    )
