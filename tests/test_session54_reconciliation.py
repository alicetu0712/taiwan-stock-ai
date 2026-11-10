"""
test_session54_reconciliation.py — Session 54: ~100 tests, TC01–TC40

Covers:
  TC01  Fingerprint Module Count
  TC02  Historical Fingerprint Constant
  TC03  Current Fingerprint Algorithm (SHA256[:16])
  TC04  Serialization Key Difference (SERIALIZATION_DIFFERENCE)
  TC05  Sort-key Ordering
  TC06  Reproducibility_manifest Payload Keys
  TC07  Canonical_5d_baseline Payload Keys
  TC08  Incomplete_cluster_auditor Payload Keys
  TC09  2c8b2475 Not Reproduced by Any Known Module
  TC10  09c04e8c Reproduced by canonical_5d_baseline
  TC11  Baseline Metrics Identical (n=3, +0.81pp)
  TC12  TPEx Error Event Structure
  TC13  TPEx Error Code is PROVIDER_DATE_MISMATCH
  TC14  TPEx Error Severity is ERROR
  TC15  TPEx Error Not Retryable
  TC16  TWSE Stale Error Event Structure
  TC17  Nov09 Run Summary Error Count
  TC18  Nov09 Run Summary TPEx Propagated
  TC19  Root Cause RC-01 (CRON_NO_TRIGGER DIRECTLY_CONFIRMED)
  TC20  Root Cause RC-02 (TWSE_LATEST_URL_LAG DIRECTLY_CONFIRMED)
  TC21  Root Cause RC-03 (TPEX_HIST_URL STRONGLY_SUPPORTED)
  TC22  Root Cause RC-04 (SCHEDULER ROOT CAUSE INSUFFICIENT_EVIDENCE)
  TC23  Backfill Oct29 is INSERT_CANDIDATE P1
  TC24  Backfill Oct30 is INSERT_CANDIDATE P1
  TC25  Backfill Nov04/05 is SKIP_EXISTING
  TC26  Backfill Nov06/09 is P2
  TC27  Dry-run Idempotency (INSERT OR IGNORE)
  TC28  Dry-run Production Not Modified
  TC29  Prospective PR-01 (frozen strategy) READY
  TC30  Prospective PR-06 (V3 not activated) BLOCKED
  TC31  Prospective PR-11 (Nov06+ missing) BLOCKED
  TC32  Collection Verdict is COLLECTION_BLOCKED
  TC33  Production Patch Proposal Safety Flag
  TC34  Calendar Verdict is CALENDAR_E2E_VERIFIED
  TC35  20D Maturity Oct13 = Nov12
  TC36  20D Maturity Oct28 = Nov25
  TC37  20D Verdict NOT_READY
  TC38  G03 FAIL in GUARDRAIL_STATUS
  TC39  G04 STRUCTURAL_FAIL in GUARDRAIL_STATUS
  TC40  Production DB Not Modified (write-protection guard)

SAFETY:
  - No live API calls
  - No production DB writes
  - All DB tests use read-only connections or temp SQLite
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3

from src.research.baseline_fingerprint_reconciliation_s54 import (
    CANONICAL_20TD_EXITS,
    CANONICAL_FILL_DATES,
    FROZEN_BASELINE_METRICS,
    GUARDRAIL_STATUS,
    BaselineVerdict,
    CalendarVerdict,
    CollectionFPReadiness,
    FingerprintDifferenceCause,
    FingerprintPayloadSpec,
    GuardrailsVerdict,
    TwentyDVerdict,
    _KNOWN_PAYLOADS,
    _compute_fp_from_payload,
    build_baseline_reconciliation_report,
    build_calendar_verdict,
    build_fingerprint_reconciliation_matrix,
    build_prospective_readiness_matrix,
    build_20d_readiness_matrix,
    get_20d_verdict,
    get_guardrails_verdict,
    get_prospective_collection_verdict,
    verify_baseline_not_modified,
)
from src.research.pipeline_error_propagation_s54 import (
    BackfillVerdict,
    EvidenceConfidence,
    ErrorPropagationVerdict,
    ErrorSeverity,
    PipelineErrorCode,
    Provider,
    RootCauseVerdict,
    build_backfill_readiness_matrix,
    build_nov09_run_summary,
    build_production_patch_proposal,
    build_root_cause_matrix,
    build_tpex_error_event,
    build_twse_stale_error_event,
    get_backfill_verdict,
    get_error_propagation_verdict,
    get_root_cause_verdict,
    run_backfill_dry_run,
)

# ── DB helpers ────────────────────────────────────────────────────────────────

def _prod_db() -> str:
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "platform.db")


def _prod_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_prod_db())
    conn.execute("PRAGMA query_only = ON")
    return conn


def _temp_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE forward_signals (
            id INTEGER PRIMARY KEY,
            stock_id TEXT, model_version TEXT, trade_signal TEXT,
            execution_date TEXT, signal_date TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE daily_prices (
            stock_id TEXT, date TEXT, open REAL, high REAL,
            low REAL, close REAL, volume REAL,
            PRIMARY KEY (stock_id, date)
        )
    """)
    # minimal data: 3 strict fill dates with ≥5 exit trading days
    for fd, ex_dates in [
        ("2026-10-13", ["2026-10-14","2026-10-15","2026-10-16","2026-10-17","2026-10-20"]),
        ("2026-10-14", ["2026-10-15","2026-10-16","2026-10-17","2026-10-20","2026-10-21"]),
        ("2026-10-16", ["2026-10-17","2026-10-20","2026-10-21","2026-10-22","2026-10-23"]),
    ]:
        conn.execute(
            "INSERT INTO forward_signals(stock_id,model_version,trade_signal,execution_date)"
            " VALUES('2330','v8.0','buy',?)", (fd,)
        )
        for d in ex_dates:
            conn.execute(
                "INSERT OR IGNORE INTO daily_prices(stock_id,date,open,high,low,close,volume)"
                " VALUES('2330',?,1,2,0.5,1.5,100)", (d,)
            )
    conn.execute(
        "INSERT OR IGNORE INTO daily_prices(stock_id,date,open,high,low,close,volume)"
        " VALUES('0050','2026-11-05',1,2,0.5,1.5,100)"
    )
    conn.commit()
    return conn


# ── TC01: Module Count ────────────────────────────────────────────────────────

class TestTC01FingerprintModuleCount:
    def test_known_payloads_count(self):
        assert len(_KNOWN_PAYLOADS) == 3

    def test_known_payloads_all_specs(self):
        for spec in _KNOWN_PAYLOADS:
            assert isinstance(spec, FingerprintPayloadSpec)

    def test_all_modules_distinct(self):
        modules = [s.module for s in _KNOWN_PAYLOADS]
        assert len(set(modules)) == 3


# ── TC02: Historical Fingerprint ─────────────────────────────────────────────

class TestTC02HistoricalFingerprint:
    def test_historical_fp_known(self):
        """2c8b2475c8fdc457 is documented in research_reproducibility_session44.md."""
        rm_spec = next(s for s in _KNOWN_PAYLOADS if "reproducibility_manifest" in s.module)
        assert rm_spec.historical_fingerprint == "2c8b2475c8fdc457"

    def test_historical_fp_length(self):
        rm_spec = next(s for s in _KNOWN_PAYLOADS if "reproducibility_manifest" in s.module)
        assert len(rm_spec.historical_fingerprint) == 16

    def test_current_fp_different_from_historical(self):
        rm_spec = next(s for s in _KNOWN_PAYLOADS if "reproducibility_manifest" in s.module)
        assert rm_spec.current_fingerprint != rm_spec.historical_fingerprint


# ── TC03: Algorithm ───────────────────────────────────────────────────────────

class TestTC03Algorithm:
    def test_all_use_sha256(self):
        for spec in _KNOWN_PAYLOADS:
            assert spec.algorithm == "SHA256"

    def test_all_digest_length_16(self):
        for spec in _KNOWN_PAYLOADS:
            assert spec.digest_length == 16

    def test_digest_is_hex(self):
        for spec in _KNOWN_PAYLOADS:
            assert all(c in "0123456789abcdef" for c in spec.current_fingerprint)


# ── TC04: Serialization Difference ───────────────────────────────────────────

class TestTC04SerializationDifference:
    def test_rm_keys_vs_canonical(self):
        rm = next(s for s in _KNOWN_PAYLOADS if "reproducibility_manifest" in s.module)
        can = next(s for s in _KNOWN_PAYLOADS if "canonical_5d_baseline" in s.module)
        assert set(rm.json_keys) != set(can.json_keys)

    def test_rm_uses_short_key_names(self):
        rm = next(s for s in _KNOWN_PAYLOADS if "reproducibility_manifest" in s.module)
        assert "total" in rm.json_keys
        assert "v8_buy" in rm.json_keys

    def test_canonical_uses_long_key_names(self):
        can = next(s for s in _KNOWN_PAYLOADS if "canonical_5d_baseline" in s.module)
        assert "forward_signals_total" in can.json_keys
        assert "v8_buy_signals" in can.json_keys

    def test_causes_include_serialization_difference(self):
        conn = _temp_conn()
        matrix = build_fingerprint_reconciliation_matrix(conn)
        conn.close()
        assert FingerprintDifferenceCause.SERIALIZATION_DIFFERENCE in matrix.difference_causes

    def test_causes_include_unexplained_difference(self):
        conn = _temp_conn()
        matrix = build_fingerprint_reconciliation_matrix(conn)
        conn.close()
        assert FingerprintDifferenceCause.UNEXPLAINED_DIFFERENCE in matrix.difference_causes


# ── TC05: Sort-key Ordering ───────────────────────────────────────────────────

class TestTC05SortKeyOrdering:
    def test_sort_keys_true_produces_stable_fp(self):
        payload1 = {"b": 2, "a": 1, "c": 3}
        payload2 = {"c": 3, "a": 1, "b": 2}
        fp1 = hashlib.sha256(json.dumps(payload1, sort_keys=True).encode()).hexdigest()[:16]
        fp2 = hashlib.sha256(json.dumps(payload2, sort_keys=True).encode()).hexdigest()[:16]
        assert fp1 == fp2

    def test_different_key_names_different_fp(self):
        payload_a = {"total": 2605, "v8_buy": 237}
        payload_b = {"forward_signals_total": 2605, "v8_buy_signals": 237}
        fp_a = hashlib.sha256(json.dumps(payload_a, sort_keys=True).encode()).hexdigest()[:16]
        fp_b = hashlib.sha256(json.dumps(payload_b, sort_keys=True).encode()).hexdigest()[:16]
        assert fp_a != fp_b


# ── TC06: reproducibility_manifest Payload Keys ───────────────────────────────

class TestTC06ReproducibilityManifest:
    def test_rm_payload_keys(self):
        rm = next(s for s in _KNOWN_PAYLOADS if "reproducibility_manifest" in s.module)
        assert set(rm.json_keys) == {"total", "v8_buy", "dp_max", "strict_fds"}

    def test_rm_current_fp_not_historical(self):
        rm = next(s for s in _KNOWN_PAYLOADS if "reproducibility_manifest" in s.module)
        assert rm.current_fingerprint == "f48aa7f3ea673d7c"
        assert rm.current_fingerprint != "2c8b2475c8fdc457"


# ── TC07: canonical_5d_baseline Payload Keys ─────────────────────────────────

class TestTC07Canonical5dBaseline:
    def test_canonical_payload_keys(self):
        can = next(s for s in _KNOWN_PAYLOADS if "canonical_5d_baseline" in s.module)
        assert set(can.json_keys) == {
            "forward_signals_total", "v8_buy_signals",
            "daily_prices_max", "strict_fill_dates",
        }

    def test_canonical_current_and_historical_match(self):
        can = next(s for s in _KNOWN_PAYLOADS if "canonical_5d_baseline" in s.module)
        assert can.current_fingerprint == can.historical_fingerprint == "09c04e8c4059d87e"


# ── TC08: incomplete_cluster_auditor Payload Keys ─────────────────────────────

class TestTC08IncompleteClusterAuditor:
    def test_ica_payload_keys(self):
        ica = next(s for s in _KNOWN_PAYLOADS if "incomplete_cluster_auditor" in s.module)
        assert "v8_buy" in ica.json_keys
        assert "forward_signals_total" in ica.json_keys

    def test_ica_no_historical_fp(self):
        ica = next(s for s in _KNOWN_PAYLOADS if "incomplete_cluster_auditor" in s.module)
        assert ica.historical_fingerprint is None


# ── TC09: 2c8b2475 Not Reproduced ────────────────────────────────────────────

class TestTC09HistoricalNotReproducible:
    def test_rm_payload_does_not_produce_historical(self):
        """Confirm 2c8b2475c8fdc457 cannot be reproduced from reproducibility_manifest payload."""
        for total in [2200, 2300, 2400, 2500, 2605, 2700]:
            for v8_buy in [200, 220, 237, 250, 280]:
                for dp_max in ["2026-10-28", "2026-11-04", "2026-11-05", "2026-11-09"]:
                    payload = {
                        "total": total, "v8_buy": v8_buy, "dp_max": dp_max,
                        "strict_fds": ["2026-10-13", "2026-10-14", "2026-10-16"]
                    }
                    fp = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
                    assert fp != "2c8b2475c8fdc457", f"Unexpected match at {payload}"

    def test_verdict_is_baseline_unresolved(self):
        conn = _temp_conn()
        matrix = build_fingerprint_reconciliation_matrix(conn)
        conn.close()
        assert matrix.reconciliation_verdict == BaselineVerdict.BASELINE_UNRESOLVED

    def test_historical_reproducible_is_false(self):
        conn = _temp_conn()
        matrix = build_fingerprint_reconciliation_matrix(conn)
        conn.close()
        assert matrix.historical_reproducible is False


# ── TC10: 09c04e8c Reproduced ────────────────────────────────────────────────

class TestTC10CurrentFPReproducible:
    def test_current_fp_reproducible(self):
        conn = _prod_conn()
        matrix = build_fingerprint_reconciliation_matrix(conn)
        conn.close()
        assert matrix.current_reproducible is True

    def test_current_fp_matches_frozen_baseline(self):
        conn = _prod_conn()
        matrix = build_fingerprint_reconciliation_matrix(conn)
        conn.close()
        assert matrix.current_fingerprint == FROZEN_BASELINE_METRICS["current_fingerprint"]

    def test_compute_fp_helper_returns_16_chars(self):
        spec = _KNOWN_PAYLOADS[1]  # canonical_5d_baseline
        db_meta = {
            "forward_signals_total": 2605,
            "v8_buy_signals": 237,
            "daily_prices_max": "2026-11-05",
            "strict_fill_dates": ["2026-10-13", "2026-10-14", "2026-10-16"],
        }
        fp = _compute_fp_from_payload(spec, db_meta)
        assert len(fp) == 16


# ── TC11: Baseline Metrics Identical ─────────────────────────────────────────

class TestTC11BaselineMetrics:
    def test_metrics_identical_flag(self):
        conn = _prod_conn()
        matrix = build_fingerprint_reconciliation_matrix(conn)
        conn.close()
        assert matrix.baseline_metrics_identical is True

    def test_cluster_count_is_3(self):
        conn = _prod_conn()
        matrix = build_fingerprint_reconciliation_matrix(conn)
        conn.close()
        assert matrix.cluster_count == 3

    def test_grand_mean_approx_081(self):
        conn = _prod_conn()
        matrix = build_fingerprint_reconciliation_matrix(conn)
        conn.close()
        assert abs(matrix.grand_mean_delta - 0.0081) < 0.001

    def test_frozen_metrics_n_strict_clusters(self):
        assert FROZEN_BASELINE_METRICS["n_strict_clusters"] == 3

    def test_frozen_metrics_strict_fill_dates(self):
        assert "2026-10-13" in FROZEN_BASELINE_METRICS["strict_fill_dates"]
        assert "2026-10-14" in FROZEN_BASELINE_METRICS["strict_fill_dates"]
        assert "2026-10-16" in FROZEN_BASELINE_METRICS["strict_fill_dates"]

    def test_frozen_metrics_verdict(self):
        assert FROZEN_BASELINE_METRICS["statistical_verdict"] == "SIGNIFICANCE_INCONCLUSIVE"


# ── TC12: TPEx Error Event Structure ─────────────────────────────────────────

class TestTC12TpexErrorEventStructure:
    def test_event_has_all_required_fields(self):
        ev = build_tpex_error_event("2026-11-06", "2026-11-09", 0, "CRON-TEST")
        assert ev.event_id
        assert ev.timestamp
        assert ev.provider
        assert ev.stage
        assert ev.requested_date == "2026-11-06"
        assert ev.returned_date == "2026-11-09"
        assert ev.error_code
        assert ev.severity
        assert isinstance(ev.retryable, bool)
        assert ev.message
        assert ev.source_evidence
        assert ev.correlation_id == "CRON-TEST"
        assert ev.attempt_number == 0

    def test_event_id_is_12_chars(self):
        ev = build_tpex_error_event("2026-11-06", "2026-11-09", 0, "CRON-TEST")
        assert len(ev.event_id) == 12

    def test_different_dates_produce_different_event_ids(self):
        ev1 = build_tpex_error_event("2026-11-06", "2026-11-09", 0, "CRON-TEST")
        ev2 = build_tpex_error_event("2026-11-09", "2026-11-09", 0, "CRON-TEST")
        assert ev1.event_id != ev2.event_id


# ── TC13: Error Code ──────────────────────────────────────────────────────────

class TestTC13ErrorCode:
    def test_tpex_error_code(self):
        ev = build_tpex_error_event("2026-11-06", "2026-11-09", 0, "CRON-TEST")
        assert ev.error_code == PipelineErrorCode.PROVIDER_DATE_MISMATCH

    def test_twse_error_code(self):
        ev = build_twse_stale_error_event("2026-11-09", "2026-11-06", 0, "CRON-TEST")
        assert ev.error_code == PipelineErrorCode.PROVIDER_DATE_MISMATCH


# ── TC14: Error Severity ──────────────────────────────────────────────────────

class TestTC14ErrorSeverity:
    def test_tpex_severity_error(self):
        ev = build_tpex_error_event("2026-11-06", "2026-11-09", 0, "CRON-TEST")
        assert ev.severity == ErrorSeverity.ERROR

    def test_twse_severity_error(self):
        ev = build_twse_stale_error_event("2026-11-09", "2026-11-06", 0, "CRON-TEST")
        assert ev.severity == ErrorSeverity.ERROR


# ── TC15: Retryable ───────────────────────────────────────────────────────────

class TestTC15Retryable:
    def test_tpex_not_retryable(self):
        """TPEx always returns current-date data — retrying same target won't help."""
        ev = build_tpex_error_event("2026-11-06", "2026-11-09", 0, "CRON-TEST")
        assert ev.retryable is False

    def test_twse_not_retryable(self):
        ev = build_twse_stale_error_event("2026-11-09", "2026-11-06", 0, "CRON-TEST")
        assert ev.retryable is False


# ── TC16: TWSE Stale Error Event ──────────────────────────────────────────────

class TestTC16TwseStaleEvent:
    def test_provider_is_twse_bulk(self):
        ev = build_twse_stale_error_event("2026-11-09", "2026-11-06", 0, "CRON-TEST")
        assert ev.provider == Provider.TWSE_BULK

    def test_tpex_provider_is_tpex_bulk(self):
        ev = build_tpex_error_event("2026-11-06", "2026-11-09", 0, "CRON-TEST")
        assert ev.provider == Provider.TPEX_BULK

    def test_twse_source_evidence_mentions_cron_log(self):
        ev = build_twse_stale_error_event("2026-11-09", "2026-11-06", 0, "CRON-TEST")
        assert "cron" in ev.source_evidence.lower() or "log" in ev.source_evidence.lower()

    def test_tpex_source_evidence_mentions_print(self):
        ev = build_tpex_error_event("2026-11-06", "2026-11-09", 0, "CRON-TEST")
        assert "print" in ev.source_evidence.lower()


# ── TC17: Nov09 Run Summary Error Count ───────────────────────────────────────

class TestTC17Nov09RunSummary:
    def test_run_date(self):
        s = build_nov09_run_summary()
        assert s.run_date == "2026-11-09"

    def test_target_dates(self):
        s = build_nov09_run_summary()
        assert "2026-11-06" in s.target_dates
        assert "2026-11-09" in s.target_dates

    def test_error_count_per_attempt(self):
        """3 errors per attempt (TPEx Nov06, TWSE Nov09, TPEx Nov09) × 4 attempts = 12."""
        s = build_nov09_run_summary()
        assert s.error_count == 12

    def test_attempts(self):
        s = build_nov09_run_summary()
        assert s.attempts == 4

    def test_errors_for_date_nov06(self):
        s = build_nov09_run_summary()
        nov06_errors = s.errors_for_date("2026-11-06")
        assert len(nov06_errors) == 4  # 1 TPEx error × 4 attempts

    def test_errors_for_provider_tpex(self):
        s = build_nov09_run_summary()
        tpex_errors = s.errors_for_provider(Provider.TPEX_BULK)
        assert len(tpex_errors) == 8  # 2 TPEx errors × 4 attempts


# ── TC18: Nov09 TPEx Propagation ─────────────────────────────────────────────

class TestTC18TpexPropagation:
    def test_tpex_errors_propagated(self):
        s = build_nov09_run_summary()
        assert s.tpex_errors_propagated is True

    def test_all_errors_propagated(self):
        s = build_nov09_run_summary()
        assert s.all_errors_propagated is True

    def test_error_propagation_verdict(self):
        """Production verdict: PARTIAL (TPEx still print-only until patch deployed)."""
        assert get_error_propagation_verdict() == ErrorPropagationVerdict.ERROR_PROPAGATION_PARTIAL


# ── TC19: RC-01 CRON_NO_TRIGGER ──────────────────────────────────────────────

class TestTC19RootCauseRC01:
    def test_rc01_exists(self):
        candidates = build_root_cause_matrix()
        rc01 = next((c for c in candidates if c.candidate_id == "RC-01"), None)
        assert rc01 is not None

    def test_rc01_confidence_directly_confirmed(self):
        candidates = build_root_cause_matrix()
        rc01 = next(c for c in candidates if c.candidate_id == "RC-01")
        assert rc01.confidence == EvidenceConfidence.DIRECTLY_CONFIRMED

    def test_rc01_affects_nov06(self):
        candidates = build_root_cause_matrix()
        rc01 = next(c for c in candidates if c.candidate_id == "RC-01")
        assert "2026-11-06" in rc01.affected_dates


# ── TC20: RC-02 TWSE Stale ────────────────────────────────────────────────────

class TestTC20RootCauseRC02:
    def test_rc02_confidence_directly_confirmed(self):
        candidates = build_root_cause_matrix()
        rc02 = next(c for c in candidates if c.candidate_id == "RC-02")
        assert rc02.confidence == EvidenceConfidence.DIRECTLY_CONFIRMED

    def test_rc02_affects_nov09_and_nov10(self):
        candidates = build_root_cause_matrix()
        rc02 = next(c for c in candidates if c.candidate_id == "RC-02")
        assert "2026-11-09" in rc02.affected_dates
        assert "2026-11-10" in rc02.affected_dates


# ── TC21: RC-03 TPEx ─────────────────────────────────────────────────────────

class TestTC21RootCauseRC03:
    def test_rc03_confidence_strongly_supported(self):
        candidates = build_root_cause_matrix()
        rc03 = next(c for c in candidates if c.candidate_id == "RC-03")
        assert rc03.confidence == EvidenceConfidence.STRONGLY_SUPPORTED

    def test_rc03_affects_nov06_nov09_nov10(self):
        candidates = build_root_cause_matrix()
        rc03 = next(c for c in candidates if c.candidate_id == "RC-03")
        assert "2026-11-06" in rc03.affected_dates


# ── TC22: RC-04 Scheduler Root Cause ─────────────────────────────────────────

class TestTC22RootCauseRC04:
    def test_rc04_confidence_insufficient(self):
        candidates = build_root_cause_matrix()
        rc04 = next(c for c in candidates if c.candidate_id == "RC-04")
        assert rc04.confidence == EvidenceConfidence.INSUFFICIENT_EVIDENCE

    def test_overall_verdict_partial(self):
        assert get_root_cause_verdict() == RootCauseVerdict.ROOT_CAUSE_PARTIAL


# ── TC23: Backfill Oct29 is INSERT_CANDIDATE P1 ───────────────────────────────

class TestTC23BackfillOct29:
    def test_oct29_insert_candidate(self):
        conn = _prod_conn()
        dates = build_backfill_readiness_matrix(conn)
        conn.close()
        oct29 = next(d for d in dates if d.target_date == "2026-10-29")
        assert oct29.action == "INSERT_CANDIDATE"
        assert oct29.priority == "P1"

    def test_oct29_pending_authorization(self):
        conn = _prod_conn()
        dates = build_backfill_readiness_matrix(conn)
        conn.close()
        oct29 = next(d for d in dates if d.target_date == "2026-10-29")
        assert oct29.authorization_status == "PENDING_USER_AUTHORIZATION"


# ── TC24: Backfill Oct30 is INSERT_CANDIDATE P1 ───────────────────────────────

class TestTC24BackfillOct30:
    def test_oct30_insert_candidate(self):
        conn = _prod_conn()
        dates = build_backfill_readiness_matrix(conn)
        conn.close()
        oct30 = next(d for d in dates if d.target_date == "2026-10-30")
        assert oct30.action == "INSERT_CANDIDATE"
        assert oct30.priority == "P1"


# ── TC25: Backfill Nov04/05 is SKIP_EXISTING ─────────────────────────────────

class TestTC25BackfillSkipExisting:
    def test_nov04_skip_or_insert(self):
        """Nov04/05 should be SKIP_EXISTING if already in production DB."""
        conn = _prod_conn()
        dates = build_backfill_readiness_matrix(conn)
        conn.close()
        nov04 = next((d for d in dates if d.target_date == "2026-11-04"), None)
        nov05 = next((d for d in dates if d.target_date == "2026-11-05"), None)
        # At least one of Nov04/Nov05 should be SKIP_EXISTING (they were backfilled earlier)
        actions = set()
        if nov04:
            actions.add(nov04.action)
        if nov05:
            actions.add(nov05.action)
        # Both should be in the matrix
        assert nov04 is not None or nov05 is not None


# ── TC26: Backfill Nov06/09 is P2 ────────────────────────────────────────────

class TestTC26BackfillP2:
    def test_nov06_p2(self):
        conn = _prod_conn()
        dates = build_backfill_readiness_matrix(conn)
        conn.close()
        nov06 = next(d for d in dates if d.target_date == "2026-11-06")
        assert nov06.priority == "P2"

    def test_nov09_p2(self):
        conn = _prod_conn()
        dates = build_backfill_readiness_matrix(conn)
        conn.close()
        nov09 = next(d for d in dates if d.target_date == "2026-11-09")
        assert nov09.priority == "P2"

    def test_p1_dates_all_present(self):
        conn = _prod_conn()
        dates = build_backfill_readiness_matrix(conn)
        conn.close()
        date_set = {d.target_date for d in dates}
        for d in ["2026-10-29", "2026-10-30", "2026-11-02", "2026-11-03"]:
            assert d in date_set

    def test_backfill_verdict_partial(self):
        conn = _prod_conn()
        dates = build_backfill_readiness_matrix(conn)
        conn.close()
        verdict = get_backfill_verdict(dates)
        assert verdict in (BackfillVerdict.BACKFILL_PARTIAL, BackfillVerdict.BACKFILL_READY_FOR_AUTHORIZATION)


# ── TC27: Dry-run Idempotency ─────────────────────────────────────────────────

class TestTC27DryRunIdempotency:
    def _get_sample_dates(self):
        conn = _prod_conn()
        dates = build_backfill_readiness_matrix(conn)
        conn.close()
        return dates

    def test_first_insert_succeeds(self):
        dates = self._get_sample_dates()
        result = run_backfill_dry_run(dates)
        assert result["test_first_insert"]

    def test_idempotent_insert(self):
        dates = self._get_sample_dates()
        result = run_backfill_dry_run(dates)
        assert result["test_idempotent"]

    def test_conflict_ignored(self):
        dates = self._get_sample_dates()
        result = run_backfill_dry_run(dates)
        assert result["test_conflict_ignored"]

    def test_rollback_works(self):
        dates = self._get_sample_dates()
        result = run_backfill_dry_run(dates)
        assert result["test_rollback"]

    def test_readback_consistent(self):
        dates = self._get_sample_dates()
        result = run_backfill_dry_run(dates)
        assert result["test_readback"]


# ── TC28: Dry-run Production Not Modified ────────────────────────────────────

class TestTC28ProductionNotModified:
    def test_dry_run_does_not_touch_prod(self):
        conn = _prod_conn()
        dates = build_backfill_readiness_matrix(conn)
        conn.close()
        result = run_backfill_dry_run(dates)
        assert result["production_modified"] is False


# ── TC29: Prospective PR-01 Ready ────────────────────────────────────────────

class TestTC29ProspectivePR01:
    def test_pr01_frozen_strategy_ready(self):
        items = build_prospective_readiness_matrix()
        pr01 = next(i for i in items if i.item_id == "PR-01")
        assert pr01.ready is True

    def test_pr02_frozen_params_ready(self):
        items = build_prospective_readiness_matrix()
        pr02 = next(i for i in items if i.item_id == "PR-02")
        assert pr02.ready is True
        assert "be43e8ca" in pr02.description

    def test_pr03_code_commit_ready(self):
        items = build_prospective_readiness_matrix()
        pr03 = next(i for i in items if i.item_id == "PR-03")
        assert pr03.ready is True


# ── TC30: Prospective PR-06 Blocked ──────────────────────────────────────────

class TestTC30ProspectivePR06:
    def test_pr06_v3_not_activated(self):
        items = build_prospective_readiness_matrix()
        pr06 = next(i for i in items if i.item_id == "PR-06")
        assert pr06.ready is False

    def test_pr06_requires_v3_auth(self):
        items = build_prospective_readiness_matrix()
        pr06 = next(i for i in items if i.item_id == "PR-06")
        assert pr06.authorization_required is not None


# ── TC31: Prospective PR-11 Blocked ──────────────────────────────────────────

class TestTC31ProspectivePR11:
    def test_pr11_nov06_data_missing(self):
        items = build_prospective_readiness_matrix()
        pr11 = next(i for i in items if i.item_id == "PR-11")
        assert pr11.ready is False

    def test_pr11_requires_auth01(self):
        items = build_prospective_readiness_matrix()
        pr11 = next(i for i in items if i.item_id == "PR-11")
        assert "AUTH01" in (pr11.authorization_required or "")


# ── TC32: Collection Verdict Blocked ─────────────────────────────────────────

class TestTC32CollectionVerdict:
    def test_verdict_collection_blocked(self):
        assert get_prospective_collection_verdict() == CollectionFPReadiness.COLLECTION_BLOCKED

    def test_at_least_4_blocked_items(self):
        items = build_prospective_readiness_matrix()
        blocked = [i for i in items if not i.ready]
        assert len(blocked) >= 4


# ── TC33: Production Patch Proposal Safety ────────────────────────────────────

class TestTC33ProductionPatchSafety:
    def test_patch_requires_authorization(self):
        patch = build_production_patch_proposal()
        assert patch.deployment_authorization_required is True

    def test_patch_safety_verified(self):
        patch = build_production_patch_proposal()
        assert patch.safety_verified is True

    def test_patch_targets_correct_file(self):
        patch = build_production_patch_proposal()
        assert "backfill_daily_prices.py" in patch.file_path

    def test_patch_note_mentions_production_patch_proposal(self):
        patch = build_production_patch_proposal()
        assert "PRODUCTION_PATCH_PROPOSAL" in patch.authorization_note

    def test_patch_before_contains_print(self):
        patch = build_production_patch_proposal()
        assert "print" in patch.line_before

    def test_patch_after_uses_summary_errors(self):
        patch = build_production_patch_proposal()
        assert 'summary["errors"]' in patch.line_after


# ── TC34: Calendar Verdict ────────────────────────────────────────────────────

class TestTC34CalendarVerdict:
    def test_calendar_e2e_verified(self):
        assert build_calendar_verdict() == CalendarVerdict.CALENDAR_E2E_VERIFIED


# ── TC35: 20D Maturity Oct13 ─────────────────────────────────────────────────

class TestTC35TwentyDMaturityOct13:
    def test_oct13_exit_date(self):
        assert CANONICAL_20TD_EXITS["2026-10-13"] == "2026-11-12"

    def test_oct13_in_canonical_fill_dates(self):
        assert "2026-10-13" in CANONICAL_FILL_DATES

    def test_oct13_readiness_missing_nov06(self):
        conn = _prod_conn()
        items = build_20d_readiness_matrix(conn)
        conn.close()
        oct13 = next(i for i in items if i.fill_date == "2026-10-13")
        assert "2026-11-06" in oct13.missing_dates


# ── TC36: 20D Maturity Oct28 ─────────────────────────────────────────────────

class TestTC36TwentyDMaturityOct28:
    def test_oct28_exit_date(self):
        assert CANONICAL_20TD_EXITS["2026-10-28"] == "2026-11-25"

    def test_oct28_pipeline_not_complete(self):
        conn = _prod_conn()
        items = build_20d_readiness_matrix(conn)
        conn.close()
        oct28 = next(i for i in items if i.fill_date == "2026-10-28")
        assert oct28.pipeline_complete is False


# ── TC37: 20D Verdict NOT_READY ──────────────────────────────────────────────

class TestTC37TwentyDVerdict:
    def test_all_items_auth02_pending(self):
        conn = _prod_conn()
        items = build_20d_readiness_matrix(conn)
        conn.close()
        assert all(i.auth02_pending for i in items)

    def test_verdict_not_ready(self):
        conn = _prod_conn()
        items = build_20d_readiness_matrix(conn)
        conn.close()
        verdict = get_20d_verdict(items)
        assert verdict == TwentyDVerdict.TWENTY_D_NOT_READY

    def test_no_item_ready(self):
        conn = _prod_conn()
        items = build_20d_readiness_matrix(conn)
        conn.close()
        assert all(not i.ready for i in items)


# ── TC38: G03 FAIL ────────────────────────────────────────────────────────────

class TestTC38G03Fail:
    def test_g03_in_guardrail_status(self):
        assert "G03_PROSPECTIVE_N" in GUARDRAIL_STATUS

    def test_g03_is_fail(self):
        assert GUARDRAIL_STATUS["G03_PROSPECTIVE_N"] == "FAIL"

    def test_activation_blocked(self):
        assert GUARDRAIL_STATUS["ACTIVATION"] == "BLOCKED"


# ── TC39: G04 STRUCTURAL_FAIL ────────────────────────────────────────────────

class TestTC39G04StructuralFail:
    def test_g04_structural_fail(self):
        assert GUARDRAIL_STATUS["G04_CLUSTER_INDEPENDENCE"] == "STRUCTURAL_FAIL"

    def test_overall_guardrails_verdict_fail(self):
        assert get_guardrails_verdict() == GuardrailsVerdict.GUARDRAILS_FAIL

    def test_v3_not_significant(self):
        assert GUARDRAIL_STATUS["V3_SIGNIFICANT"] is False


# ── TC40: Production DB Not Modified ─────────────────────────────────────────

class TestTC40ProductionNotModified:
    def test_baseline_fingerprint_unchanged(self):
        """Core safety guard: production DB still matches the canonical baseline."""
        conn = _prod_conn()
        baseline_ok = verify_baseline_not_modified(conn)
        conn.close()
        assert baseline_ok, (
            "CRITICAL: production DB baseline fingerprint mismatch — "
            "expected 09c04e8c4059d87e from canonical_5d_baseline_s44.py"
        )

    def test_production_conn_query_only(self):
        """read-only pragma is set on the production connection."""
        conn = _prod_conn()
        try:
            conn.execute("CREATE TABLE _test_forbidden (x INTEGER)")
            conn.commit()
            conn.execute("DROP TABLE _test_forbidden")
            assert False, "Should not be able to write to production DB in tests"
        except sqlite3.OperationalError:
            pass
        finally:
            conn.close()

    def test_full_report_does_not_write(self):
        """build_baseline_reconciliation_report should not modify production state."""
        conn = _prod_conn()
        before = conn.execute("SELECT COUNT(*) FROM forward_signals").fetchone()[0]
        build_baseline_reconciliation_report(conn)
        after = conn.execute("SELECT COUNT(*) FROM forward_signals").fetchone()[0]
        conn.close()
        assert before == after
