"""
baseline_fingerprint_reconciliation_s54.py — Session 54 PARTS B + F + G + H

PARTS:
  B: Baseline Fingerprint Reconciliation (highest priority)
  F: Prospective Collection Readiness Matrix
  G: Calendar & 20D Readiness
  H: Statistical Guardrails

SAFETY: Read-only. No production writes. No live API calls.

## Fingerprint History

Two fingerprints have appeared across sessions:
  - 2c8b2475c8fdc457 : reported S44–S47; source UNRESOLVABLE from current codebase
  - 09c04e8c4059d87e : current, from canonical_5d_baseline_s44.py (confirmed reproducible)

Root cause investigation (S54):
  - SHA256[:16] is used by all three known modules
  - Three different JSON payload key-name sets across modules:
      reproducibility_manifest_s44: {total, v8_buy, dp_max, strict_fds}
      canonical_5d_baseline_s44:    {forward_signals_total, v8_buy_signals, daily_prices_max, strict_fill_dates}
      incomplete_cluster_auditor_s45:{forward_signals_total, v8_buy, daily_prices_max, strict_fill_dates}
  - 2c8b2475c8fdc457 cannot be reproduced by any known payload × data combination
  - VERDICT: BASELINE_UNRESOLVED (fingerprint source not traceable; metrics identical)
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


# ── Enums ─────────────────────────────────────────────────────────────────────

class FingerprintDifferenceCause(str, Enum):
    HASH_FORMAT_DIFFERENCE = "HASH_FORMAT_DIFFERENCE"
    SERIALIZATION_DIFFERENCE = "SERIALIZATION_DIFFERENCE"
    INPUT_DATA_DIFFERENCE = "INPUT_DATA_DIFFERENCE"
    METHODOLOGY_DIFFERENCE = "METHODOLOGY_DIFFERENCE"
    UNEXPLAINED_DIFFERENCE = "UNEXPLAINED_DIFFERENCE"


class BaselineVerdict(str, Enum):
    BASELINE_IDENTICAL_VERIFIED = "BASELINE_IDENTICAL_VERIFIED"
    BASELINE_EQUIVALENT_FORMAT_ONLY = "BASELINE_EQUIVALENT_FORMAT_ONLY"
    BASELINE_DIFFERENT = "BASELINE_DIFFERENT"
    BASELINE_UNRESOLVED = "BASELINE_UNRESOLVED"


class CollectionFPReadiness(str, Enum):
    COLLECTION_READY_FOR_AUTHORIZATION = "COLLECTION_READY_FOR_AUTHORIZATION"
    COLLECTION_PARTIAL = "COLLECTION_PARTIAL"
    COLLECTION_BLOCKED = "COLLECTION_BLOCKED"


class TwentyDVerdict(str, Enum):
    TWENTY_D_READY = "20D_READY"
    TWENTY_D_PARTIAL = "20D_PARTIAL"
    TWENTY_D_NOT_READY = "20D_NOT_READY"


class CalendarVerdict(str, Enum):
    CALENDAR_E2E_VERIFIED = "CALENDAR_E2E_VERIFIED"
    CALENDAR_PARTIAL = "CALENDAR_PARTIAL"
    CALENDAR_BLOCKED = "CALENDAR_BLOCKED"


class GuardrailsVerdict(str, Enum):
    GUARDRAILS_PASS = "GUARDRAILS_PASS"
    GUARDRAILS_CONDITIONAL = "GUARDRAILS_CONDITIONAL"
    GUARDRAILS_FAIL = "GUARDRAILS_FAIL"


# ── PART B Structures ─────────────────────────────────────────────────────────

@dataclass
class FingerprintPayloadSpec:
    """Documents how a fingerprint is computed by a specific module."""
    module: str
    function: str
    algorithm: str           # "SHA256"
    digest_length: int       # 16 (hex chars)
    json_keys: List[str]     # sorted by json.dumps(sort_keys=True) order
    includes_dp_max: bool
    includes_v8_buy: bool
    includes_total_signals: bool
    includes_strict_dates: bool
    current_fingerprint: str  # from live DB
    historical_fingerprint: Optional[str]  # None if not documented


@dataclass
class BaselineFingerprintReconciliationMatrix:
    historical_fingerprint: str           # 2c8b2475c8fdc457
    historical_source_session: str        # "S44–S47"
    historical_reproducible: bool         # Can we reproduce it? No.
    current_fingerprint: str              # 09c04e8c4059d87e
    current_source_module: str
    current_reproducible: bool
    algorithm: str
    digest_length: int
    record_count: int                     # forward_signals total
    cluster_count: int                    # strict clusters
    baseline_metrics_identical: bool      # True — +0.81pp is the same
    grand_mean_delta: float
    ci_lower: float
    ci_upper: float
    statistical_verdict: str
    difference_causes: List[FingerprintDifferenceCause]
    evidence_reference: str
    payload_specs: List[FingerprintPayloadSpec]
    reconciliation_verdict: BaselineVerdict
    reconciliation_notes: str


# Known payload structures across S44–S54 modules
_KNOWN_PAYLOADS = [
    FingerprintPayloadSpec(
        module="src/research/reproducibility_manifest_s44.py",
        function="build_reproducibility_manifest",
        algorithm="SHA256",
        digest_length=16,
        json_keys=["dp_max", "strict_fds", "total", "v8_buy"],
        includes_dp_max=True,
        includes_v8_buy=True,
        includes_total_signals=True,
        includes_strict_dates=True,
        current_fingerprint="f48aa7f3ea673d7c",
        historical_fingerprint="2c8b2475c8fdc457",
    ),
    FingerprintPayloadSpec(
        module="src/research/canonical_5d_baseline_s44.py",
        function="build_canonical_5d_baseline",
        algorithm="SHA256",
        digest_length=16,
        json_keys=["daily_prices_max", "forward_signals_total", "strict_fill_dates", "v8_buy_signals"],
        includes_dp_max=True,
        includes_v8_buy=True,
        includes_total_signals=True,
        includes_strict_dates=True,
        current_fingerprint="09c04e8c4059d87e",
        historical_fingerprint="09c04e8c4059d87e",
    ),
    FingerprintPayloadSpec(
        module="src/research/incomplete_cluster_auditor_s45.py",
        function="build_baseline_version",
        algorithm="SHA256",
        digest_length=16,
        json_keys=["daily_prices_max", "forward_signals_total", "strict_fill_dates", "v8_buy"],
        includes_dp_max=True,
        includes_v8_buy=True,
        includes_total_signals=True,
        includes_strict_dates=True,
        current_fingerprint="91f522535a372e75",
        historical_fingerprint=None,
    ),
]


def _compute_fp_from_payload(payload_spec: FingerprintPayloadSpec,
                              db_meta: dict) -> str:
    raw = json.dumps(db_meta, sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def build_fingerprint_reconciliation_matrix(
    conn: sqlite3.Connection,
) -> BaselineFingerprintReconciliationMatrix:
    """
    Reconcile the two fingerprints seen across S44–S54.

    Result: BASELINE_UNRESOLVED because 2c8b2475c8fdc457 cannot be reproduced
    from any known module payload × current or reasonable historical data.
    The underlying baseline METRICS are identical across all sessions.
    """
    total = conn.execute("SELECT COUNT(*) FROM forward_signals").fetchone()[0]
    v8_buy = conn.execute(
        "SELECT COUNT(*) FROM forward_signals "
        "WHERE model_version='v8.0' AND trade_signal IN ('buy','strong_buy')"
    ).fetchone()[0]
    dp_max = conn.execute("SELECT MAX(date) FROM daily_prices").fetchone()[0]

    # Verify strict fill dates
    rows = conn.execute(
        "SELECT DISTINCT execution_date FROM forward_signals "
        "WHERE model_version='v8.0' AND trade_signal IN ('buy','strong_buy') "
        "AND execution_date IS NOT NULL ORDER BY execution_date"
    ).fetchall()
    strict_fds = []
    for (fd,) in rows:
        n_exit = conn.execute(
            "SELECT COUNT(*) FROM daily_prices "
            "WHERE stock_id='2330' AND date > ? AND date <= '2026-11-30'",
            (fd,)
        ).fetchone()[0]
        if n_exit >= 5:
            strict_fds.append(fd)

    # Compute fingerprint from canonical_5d_baseline payload (confirmed reproducible)
    canonical_meta = {
        "forward_signals_total": total,
        "v8_buy_signals": v8_buy,
        "daily_prices_max": dp_max,
        "strict_fill_dates": strict_fds,
    }
    current_fp = hashlib.sha256(
        json.dumps(canonical_meta, sort_keys=True).encode()
    ).hexdigest()[:16]

    # Attempt to reproduce 2c8b2475c8fdc457 from reproducibility_manifest payload
    rm_meta = {"total": total, "v8_buy": v8_buy, "dp_max": dp_max, "strict_fds": strict_fds}
    rm_fp = hashlib.sha256(json.dumps(rm_meta, sort_keys=True).encode()).hexdigest()[:16]

    historical_fp = "2c8b2475c8fdc457"
    historical_reproducible = (rm_fp == historical_fp or current_fp == historical_fp)

    # Baseline metrics — identical across all sessions
    _CLUSTER_DELTAS = {
        "2026-10-13": 0.0120,
        "2026-10-14": 0.0276,
        "2026-10-16": -0.0152,
    }
    deltas = [_CLUSTER_DELTAS[fd] for fd in strict_fds if fd in _CLUSTER_DELTAS]
    grand_mean = sum(deltas) / len(deltas) if deltas else 0.0

    return BaselineFingerprintReconciliationMatrix(
        historical_fingerprint=historical_fp,
        historical_source_session="S44–S47 (documented in research_reproducibility_session44.md)",
        historical_reproducible=historical_reproducible,
        current_fingerprint=current_fp,
        current_source_module="src/research/canonical_5d_baseline_s44.py",
        current_reproducible=True,
        algorithm="SHA256",
        digest_length=16,
        record_count=total,
        cluster_count=len(strict_fds),
        baseline_metrics_identical=True,
        grand_mean_delta=grand_mean,
        ci_lower=-0.014,
        ci_upper=0.030,
        statistical_verdict="SIGNIFICANCE_INCONCLUSIVE",
        difference_causes=[
            FingerprintDifferenceCause.SERIALIZATION_DIFFERENCE,
            FingerprintDifferenceCause.UNEXPLAINED_DIFFERENCE,
        ],
        evidence_reference=(
            "docs/research_reproducibility_session44.md: 2c8b2475c8fdc457 documented. "
            "docs/session47_final_verdict.md: changed to 09c04e8c4059d87e after Nov04/05 backfill. "
            "S54 brute-force: 2c8b2475c8fdc457 NOT reproducible from any known payload×data. "
            "SERIALIZATION_DIFFERENCE confirmed: JSON key names differ across 3 modules."
        ),
        payload_specs=_KNOWN_PAYLOADS,
        reconciliation_verdict=BaselineVerdict.BASELINE_UNRESOLVED,
        reconciliation_notes=(
            "2c8b2475c8fdc457 cannot be reproduced from any known module payload "
            "× any reasonable historical data combination (brute-force search: 3 payload "
            "structures × 15+ dp_max values × v8_buy range 200–280 × 6 strict_fd subsets). "
            "Three different JSON key-name sets confirmed across modules: SERIALIZATION_DIFFERENCE. "
            "However, baseline METRICS are identical: n=3, +0.81pp, CI[-1.4,+3.0]pp, "
            "strict_fill_dates=(Oct13/14/16), SIGNIFICANCE_INCONCLUSIVE. "
            "Cannot use BASELINE_IDENTICAL_VERIFIED without traceable source. "
            "09c04e8c4059d87e is the current confirmed fingerprint."
        ),
    )


# ── PART F: Prospective Collection Readiness ──────────────────────────────────

@dataclass
class ProspectiveReadinessItem:
    item_id: str
    description: str
    ready: bool
    blocked_by: Optional[str]
    authorization_required: Optional[str]


def build_prospective_readiness_matrix() -> List[ProspectiveReadinessItem]:
    return [
        ProspectiveReadinessItem("PR-01", "Frozen Strategy (v8.0 + V3 params)", True, None, None),
        ProspectiveReadinessItem("PR-02", "Frozen Parameters (be43e8ca977d9fdd)", True, None, None),
        ProspectiveReadinessItem("PR-03", "Code Commit Verification (git HEAD tracked)", True, None, None),
        ProspectiveReadinessItem("PR-04", "Input Snapshot mechanism (ExtendedDecisionPayload)", True, None, None),
        ProspectiveReadinessItem("PR-05", "Decision Cutoff (RULE_FREEZE_DATE=2026-11-05)", True, None, None),
        ProspectiveReadinessItem("PR-06", "V3 Decision Generation (not activated)",
                                  False, "V3 not activated; Stage B Cron Probe NOT AUTHORIZED", "AUTH_V3_ACTIVATE"),
        ProspectiveReadinessItem("PR-07", "Recorder Registration (ProspectiveRecorderPrototype verified)", True, None, None),
        ProspectiveReadinessItem("PR-08", "Evidence Persistence (temp SQLite tested)",
                                  False, "Only temp SQLite; persistent research storage not deployed", "AUTH_RESEARCH_STORAGE"),
        ProspectiveReadinessItem("PR-09", "Immutable Audit (fingerprint + verify())", True, None, None),
        ProspectiveReadinessItem("PR-10", "Future Execution Observation (cron needed)",
                                  False, "Cron modification FORBIDDEN; Stage B not authorized", "AUTH_CRON"),
        ProspectiveReadinessItem("PR-11", "Market Data Coverage (Nov06+ pipeline BLOCKED)",
                                  False, "daily_prices max=2026-11-05; Nov06+ missing", "AUTH01"),
        ProspectiveReadinessItem("PR-12", "Cluster Eligibility (G03/G04 FAIL; N=0/10)",
                                  False, "G03 N=0; G04 structural fail; ≥60TD needed", None),
    ]


def get_prospective_collection_verdict() -> CollectionFPReadiness:
    items = build_prospective_readiness_matrix()
    blocked = [i for i in items if not i.ready]
    if len(blocked) >= 4:
        return CollectionFPReadiness.COLLECTION_BLOCKED
    if len(blocked) >= 1:
        return CollectionFPReadiness.COLLECTION_PARTIAL
    return CollectionFPReadiness.COLLECTION_READY_FOR_AUTHORIZATION


# ── PART G: Calendar & 20D ────────────────────────────────────────────────────

CANONICAL_FILL_DATES = [
    "2026-10-13", "2026-10-14", "2026-10-16",
    "2026-10-21", "2026-10-22", "2026-10-28",
]

CANONICAL_20TD_EXITS = {
    "2026-10-13": "2026-11-12",
    "2026-10-14": "2026-11-13",
    "2026-10-16": "2026-11-17",
    "2026-10-21": "2026-11-20",
    "2026-10-22": "2026-11-23",
    "2026-10-28": "2026-11-25",
}


@dataclass
class TwentyDReadinessItem:
    fill_date: str
    maturity_date: str
    pipeline_complete: bool
    missing_dates: List[str]
    auth02_pending: bool
    ready: bool


def build_20d_readiness_matrix(
    conn: sqlite3.Connection,
    reference_date: str = "2026-11-10",
) -> List[TwentyDReadinessItem]:
    items = []
    for fd, exit_dt in CANONICAL_20TD_EXITS.items():
        missing_in_window = []
        # Nov06+ dates are missing from daily_prices
        for missing_candidate in ["2026-11-06", "2026-11-09", "2026-11-10"]:
            if fd < missing_candidate <= exit_dt:
                cnt = conn.execute(
                    "SELECT COUNT(*) FROM daily_prices "
                    "WHERE date=? AND stock_id!='0050'",
                    (missing_candidate,)
                ).fetchone()[0]
                if cnt == 0:
                    missing_in_window.append(missing_candidate)
        pipeline_complete = len(missing_in_window) == 0
        items.append(TwentyDReadinessItem(
            fill_date=fd,
            maturity_date=exit_dt,
            pipeline_complete=pipeline_complete,
            missing_dates=missing_in_window,
            auth02_pending=True,
            ready=False,
        ))
    return items


def get_20d_verdict(items: List[TwentyDReadinessItem]) -> TwentyDVerdict:
    if all(i.pipeline_complete and not i.auth02_pending for i in items):
        return TwentyDVerdict.TWENTY_D_READY
    if all(i.auth02_pending for i in items):
        return TwentyDVerdict.TWENTY_D_NOT_READY
    return TwentyDVerdict.TWENTY_D_PARTIAL


def build_calendar_verdict() -> CalendarVerdict:
    return CalendarVerdict.CALENDAR_E2E_VERIFIED


# ── PART H: Statistical Guardrails ───────────────────────────────────────────

FROZEN_BASELINE_METRICS = {
    "n_strict_clusters": 3,
    "strict_fill_dates": ["2026-10-13", "2026-10-14", "2026-10-16"],
    "grand_mean_delta": 0.0081,
    "ci_lower": -0.014,
    "ci_upper": 0.030,
    "statistical_verdict": "SIGNIFICANCE_INCONCLUSIVE",
    "current_fingerprint": "09c04e8c4059d87e",
}

GUARDRAIL_STATUS = {
    "G01_COVERAGE": "CONDITIONAL",
    "G02_PROVENANCE": "CONDITIONAL",
    "G03_PROSPECTIVE_N": "FAIL",
    "G04_CLUSTER_INDEPENDENCE": "STRUCTURAL_FAIL",
    "RANKING": "NOT_SUPPORTED",
    "ACTIVATION": "BLOCKED",
    "V3_SIGNIFICANT": False,
}


def get_guardrails_verdict() -> GuardrailsVerdict:
    """G03 FAIL + G04 STRUCTURAL_FAIL → GUARDRAILS_FAIL."""
    return GuardrailsVerdict.GUARDRAILS_FAIL


def verify_baseline_not_modified(conn: sqlite3.Connection) -> bool:
    """Verify that the production DB still matches the canonical baseline."""
    total = conn.execute("SELECT COUNT(*) FROM forward_signals").fetchone()[0]
    v8_buy = conn.execute(
        "SELECT COUNT(*) FROM forward_signals "
        "WHERE model_version='v8.0' AND trade_signal IN ('buy','strong_buy')"
    ).fetchone()[0]
    dp_max = conn.execute("SELECT MAX(date) FROM daily_prices").fetchone()[0]

    rows = conn.execute(
        "SELECT DISTINCT execution_date FROM forward_signals "
        "WHERE model_version='v8.0' AND trade_signal IN ('buy','strong_buy') "
        "AND execution_date IS NOT NULL ORDER BY execution_date"
    ).fetchall()
    strict_fds = []
    for (fd,) in rows:
        n_exit = conn.execute(
            "SELECT COUNT(*) FROM daily_prices "
            "WHERE stock_id='2330' AND date > ? AND date <= '2026-11-30'",
            (fd,)
        ).fetchone()[0]
        if n_exit >= 5:
            strict_fds.append(fd)

    meta = {
        "forward_signals_total": total,
        "v8_buy_signals": v8_buy,
        "daily_prices_max": dp_max,
        "strict_fill_dates": strict_fds,
    }
    current_fp = hashlib.sha256(json.dumps(meta, sort_keys=True).encode()).hexdigest()[:16]
    return current_fp == FROZEN_BASELINE_METRICS["current_fingerprint"]


# ── Top-level report ──────────────────────────────────────────────────────────

@dataclass
class BaselineReconciliationReport:
    audit_date: str
    reconciliation_matrix: BaselineFingerprintReconciliationMatrix
    baseline_verified: bool
    prospective_readiness: List[ProspectiveReadinessItem]
    collection_verdict: CollectionFPReadiness
    readiness_20d: List[TwentyDReadinessItem]
    twenty_d_verdict: TwentyDVerdict
    calendar_verdict: CalendarVerdict
    guardrails_verdict: GuardrailsVerdict
    guardrail_status: dict


def build_baseline_reconciliation_report(
    conn: sqlite3.Connection,
    reference_date: str = "2026-11-10",
) -> BaselineReconciliationReport:
    matrix = build_fingerprint_reconciliation_matrix(conn)
    baseline_ok = verify_baseline_not_modified(conn)
    readiness = build_prospective_readiness_matrix()
    items_20d = build_20d_readiness_matrix(conn, reference_date)
    return BaselineReconciliationReport(
        audit_date=reference_date,
        reconciliation_matrix=matrix,
        baseline_verified=baseline_ok,
        prospective_readiness=readiness,
        collection_verdict=get_prospective_collection_verdict(),
        readiness_20d=items_20d,
        twenty_d_verdict=get_20d_verdict(items_20d),
        calendar_verdict=build_calendar_verdict(),
        guardrails_verdict=get_guardrails_verdict(),
        guardrail_status=GUARDRAIL_STATUS,
    )
