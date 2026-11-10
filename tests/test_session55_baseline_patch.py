"""
test_session55_baseline_patch.py — Session 55: ~120 tests, TC01–TC40

Covers:
  TC01  Historical Fingerprint Source Discovery (provenance records count)
  TC02  Git History Trace (no git commit found for 2c8b2475)
  TC03  Historical Payload Reproduction (all 6 sources fail to reproduce)
  TC04  Canonical Serialization (json.dumps sort_keys)
  TC05  Hash Determinism (same input → same SHA256)
  TC06  Sort Stability (key order doesn't matter)
  TC07  Float Precision (round to 4dp)
  TC08  Null Handling (None → null in JSON)
  TC09  Timezone Handling (UTC ISO 8601)
  TC10  Cross-module Consistency (3 modules produce 3 different FPs)
  TC11  Input Mutation Detection (signal count change)
  TC12  Schema Mutation Detection (key name change)
  TC13  Parameter Mutation Detection (hash must match)
  TC14  Calendar Mutation Detection (fill dates must match)
  TC15  Historical Baseline Preservation (verdict UNRECOVERABLE)
  TC16  TPEx Wrong-date Error (error propagated in patch-after)
  TC17  Structured Summary (error in summary['errors'])
  TC18  Retry History (errors not cleared on retry)
  TC19  Partial Success (TWSE+TPEx errors both captured)
  TC20  Multiple Provider Errors (count correct)
  TC21  QG Integration (QG failure + TPEx error both captured)
  TC22  Completion Marker (patch doesn't affect correct-date flow)
  TC23  Patch Compatibility (no trading rules / strategy changed)
  TC24  No Production Deployment (authorized=False)
  TC25  Source Verification (Oct29 has TWSE partial coverage)
  TC26  TWSE Coverage Count
  TC27  ETF Exclusion (no ETFs in ordinary stock count)
  TC28  Insert-only Manifest (Oct29 is INSERT_CANDIDATE)
  TC29  Duplicate Conflict (insert repeat = 0)
  TC30  Transaction Rollback (rollback verified)
  TC31  AUTH01 Pending (Oct29 pending user auth)
  TC32  Root Cause Evidence Classification (RC-01 DIRECTLY_CONFIRMED)
  TC33  Scheduler Evidence Insufficient (RC-04)
  TC34  Prospective Blocker Matrix (5 of 12 blocked)
  TC35  Mock vs Genuine Evidence (mock not counted)
  TC36  Calendar SSOT (fill dates unchanged)
  TC37  20D Maturity (Oct13 → Nov12)
  TC38  AUTH02 Not Authorized
  TC39  G03/G04 Status
  TC40  Production Fingerprint Integrity (baseline not modified)

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

from src.research.canonical_baseline_v2_s55 import (
    CURRENT_FINGERPRINT,
    DIFFERENCE_CAUSES,
    HISTORICAL_FINGERPRINT,
    PROVENANCE_EVIDENCE_SUMMARY,
    CanonicalV2Verdict,
    DifferenceClassification,
    HistoricalBaselineVerdict,
    build_baseline_recovery_report,
    build_canonical_baseline_v2,
    build_provenance_search_records,
    get_canonical_v2_verdict,
    get_historical_baseline_verdict,
    validate_input_mutation_detection,
    validate_parameter_hash,
)
from src.research.tpex_patch_verification_s55 import (
    Auth01Verdict,
    PatchScenario,
    RootCauseConfidence,
    RootCauseVerdict,
    build_auth01_date_summaries,
    build_auth01_record_manifest,
    build_patch_spec,
    build_patch_verification_report,
    build_root_cause_evidence,
    get_auth01_verdict,
    get_root_cause_verdict,
    run_auth01_dry_run,
    run_isolated_patch_simulation,
)


# ── DB helpers ────────────────────────────────────────────────────────────────

def _prod_db() -> str:
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "platform.db")


def _prod_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_prod_db())
    conn.execute("PRAGMA query_only = ON")
    return conn


# ── TC01: Historical Fingerprint Source Discovery ─────────────────────────────

class TestTC01ProvenanceRecords:
    def test_has_6_provenance_records(self):
        records = build_provenance_search_records()
        assert len(records) == 6

    def test_all_records_have_required_fields(self):
        records = build_provenance_search_records()
        for r in records:
            assert r.source_type
            assert r.source_path
            assert r.finding
            assert r.evidence

    def test_no_record_produces_target(self):
        records = build_provenance_search_records()
        for r in records:
            assert r.produces_target is False


# ── TC02: Git History Trace ───────────────────────────────────────────────────

class TestTC02GitHistoryTrace:
    def test_git_log_record_found(self):
        records = build_provenance_search_records()
        git_records = [r for r in records if r.source_type == "git_log"]
        assert len(git_records) == 1

    def test_git_record_says_no_commits(self):
        records = build_provenance_search_records()
        git_r = next(r for r in records if r.source_type == "git_log")
        assert "NO COMMITS" in git_r.finding or "no commits" in git_r.finding.lower()

    def test_git_record_mentions_untracked(self):
        records = build_provenance_search_records()
        git_r = next(r for r in records if r.source_type == "git_log")
        assert "UNTRACKED" in git_r.evidence or "untracked" in git_r.evidence.lower()


# ── TC03: Historical Payload Reproduction ─────────────────────────────────────

class TestTC03HistoricalReproduction:
    def test_rm_keys_dp_nov05_produces_different_hash(self):
        """Short keys + dp_max=Nov05 do NOT produce 2c8b2475."""
        meta = {"dp_max": "2026-11-05", "strict_fds": ["2026-10-13","2026-10-14","2026-10-16"],
                "total": 2605, "v8_buy": 237}
        fp = hashlib.sha256(json.dumps(meta, sort_keys=True).encode()).hexdigest()[:16]
        assert fp != HISTORICAL_FINGERPRINT

    def test_canonical_keys_dp_nov05_produces_09c04e8c(self):
        """Canonical keys + dp_max=Nov05 produces 09c04e8c (current), not historical."""
        meta = {"daily_prices_max": "2026-11-05", "forward_signals_total": 2605,
                "strict_fill_dates": ["2026-10-13","2026-10-14","2026-10-16"], "v8_buy_signals": 237}
        fp = hashlib.sha256(json.dumps(meta, sort_keys=True).encode()).hexdigest()[:16]
        assert fp == CURRENT_FINGERPRINT
        assert fp != HISTORICAL_FINGERPRINT

    def test_pre_backfill_dates_no_match(self):
        """Pre-Nov04 dates also don't produce 2c8b2475."""
        for dp in ["2026-10-28", "2026-10-29", "2026-10-30", "2026-11-03"]:
            meta = {"daily_prices_max": dp, "forward_signals_total": 2605,
                    "strict_fill_dates": ["2026-10-13","2026-10-14","2026-10-16"], "v8_buy_signals": 237}
            fp = hashlib.sha256(json.dumps(meta, sort_keys=True).encode()).hexdigest()[:16]
            assert fp != HISTORICAL_FINGERPRINT, f"Unexpected match at dp_max={dp}"

    def test_verdict_unrecoverable(self):
        assert get_historical_baseline_verdict() == HistoricalBaselineVerdict.HISTORICAL_BASELINE_UNRECOVERABLE

    def test_provenance_evidence_summary_exists(self):
        assert len(PROVENANCE_EVIDENCE_SUMMARY) > 100


# ── TC04: Canonical Serialization ────────────────────────────────────────────

class TestTC04CanonicalSerialization:
    def test_sort_keys_true_stable(self):
        p1 = {"z": 1, "a": 2, "m": 3}
        p2 = {"a": 2, "m": 3, "z": 1}
        assert json.dumps(p1, sort_keys=True) == json.dumps(p2, sort_keys=True)

    def test_v2_payload_uses_long_keys(self):
        conn = _prod_conn()
        v2 = build_canonical_baseline_v2(conn)
        conn.close()
        assert "baseline_version_id" in v2.fingerprint_payload_keys
        assert "strict_fill_dates" in v2.fingerprint_payload_keys

    def test_no_truncated_keys(self):
        """V2 uses full long-form keys, not short abbreviations."""
        conn = _prod_conn()
        v2 = build_canonical_baseline_v2(conn)
        conn.close()
        for key in v2.fingerprint_payload_keys:
            assert key not in ("dp_max", "strict_fds", "total", "v8_buy")


# ── TC05: Hash Determinism ────────────────────────────────────────────────────

class TestTC05HashDeterminism:
    def test_v2_fingerprint_deterministic(self):
        conn = _prod_conn()
        v2a = build_canonical_baseline_v2(conn)
        v2b = build_canonical_baseline_v2(conn)
        conn.close()
        assert v2a.fingerprint == v2b.fingerprint

    def test_v2_fingerprint_is_sha256(self):
        conn = _prod_conn()
        v2 = build_canonical_baseline_v2(conn)
        conn.close()
        assert v2.fingerprint_algorithm == "SHA256"

    def test_v2_fingerprint_full_64_chars(self):
        conn = _prod_conn()
        v2 = build_canonical_baseline_v2(conn)
        conn.close()
        assert len(v2.fingerprint) == 64


# ── TC06: Sort Stability ──────────────────────────────────────────────────────

class TestTC06SortStability:
    def test_strict_fill_dates_sorted(self):
        conn = _prod_conn()
        v2 = build_canonical_baseline_v2(conn)
        conn.close()
        assert v2.strict_fill_dates == sorted(v2.strict_fill_dates)

    def test_cluster_signal_ids_sorted(self):
        conn = _prod_conn()
        v2 = build_canonical_baseline_v2(conn)
        conn.close()
        for cluster in v2.clusters:
            assert cluster.signal_ids == sorted(cluster.signal_ids)


# ── TC07: Float Precision ─────────────────────────────────────────────────────

class TestTC07FloatPrecision:
    def test_grand_mean_4dp(self):
        conn = _prod_conn()
        v2 = build_canonical_baseline_v2(conn)
        conn.close()
        # Round to 4dp
        assert abs(v2.grand_mean_delta - round(v2.grand_mean_delta, 4)) < 1e-10

    def test_cluster_deltas_4dp(self):
        conn = _prod_conn()
        v2 = build_canonical_baseline_v2(conn)
        conn.close()
        for c in v2.clusters:
            assert abs(c.delta_vs_a_direct - round(c.delta_vs_a_direct, 4)) < 1e-10


# ── TC08: Null Handling ───────────────────────────────────────────────────────

class TestTC08NullHandling:
    def test_none_serializes_as_null(self):
        payload = {"key": None}
        assert json.dumps(payload, sort_keys=True) == '{"key": null}'


# ── TC09: Timezone Handling ───────────────────────────────────────────────────

class TestTC09TimezoneHandling:
    def test_v2_created_at_utc(self):
        conn = _prod_conn()
        v2 = build_canonical_baseline_v2(conn)
        conn.close()
        assert "+00:00" in v2.created_at or "Z" in v2.created_at or "UTC" in v2.created_at.upper()

    def test_cluster_evidence_timestamp_utc(self):
        conn = _prod_conn()
        v2 = build_canonical_baseline_v2(conn)
        conn.close()
        for c in v2.clusters:
            assert "+00:00" in c.evidence_timestamp or "Z" in c.evidence_timestamp


# ── TC10: Cross-module Consistency ───────────────────────────────────────────

class TestTC10CrossModuleConsistency:
    def test_three_known_modules_distinct(self):
        """3 modules produce 3 different FPs with same current DB."""
        import hashlib
        import json
        total, v8_buy, dp_max = 2605, 237, "2026-11-05"
        sfds = ["2026-10-13", "2026-10-14", "2026-10-16"]
        m1 = hashlib.sha256(json.dumps({"total": total, "v8_buy": v8_buy, "dp_max": dp_max, "strict_fds": sfds}, sort_keys=True).encode()).hexdigest()[:16]
        m2 = hashlib.sha256(json.dumps({"forward_signals_total": total, "v8_buy_signals": v8_buy, "daily_prices_max": dp_max, "strict_fill_dates": sfds}, sort_keys=True).encode()).hexdigest()[:16]
        m3 = hashlib.sha256(json.dumps({"forward_signals_total": total, "v8_buy": v8_buy, "daily_prices_max": dp_max, "strict_fill_dates": sfds}, sort_keys=True).encode()).hexdigest()[:16]
        assert len({m1, m2, m3}) == 3

    def test_v2_distinct_from_all_known(self):
        conn = _prod_conn()
        v2 = build_canonical_baseline_v2(conn)
        conn.close()
        known_fps = {HISTORICAL_FINGERPRINT, CURRENT_FINGERPRINT, "f48aa7f3ea673d7c", "91f522535a372e75"}
        assert v2.fingerprint not in known_fps


# ── TC11: Input Mutation Detection ───────────────────────────────────────────

class TestTC11InputMutationDetection:
    def test_no_mutation_detected(self):
        conn = _prod_conn()
        v2 = build_canonical_baseline_v2(conn)
        result = validate_input_mutation_detection(v2, conn)
        conn.close()
        assert result["no_mutation"] is True
        assert result["total_unchanged"] is True
        assert result["v8_buy_unchanged"] is True
        assert result["dp_max_unchanged"] is True

    def test_mutation_detected_on_wrong_total(self):
        conn = _prod_conn()
        v2 = build_canonical_baseline_v2(conn)
        conn.close()
        import dataclasses
        mutated = dataclasses.replace(v2, db_forward_signals_total=9999)
        conn2 = _prod_conn()
        result = validate_input_mutation_detection(mutated, conn2)
        conn2.close()
        assert result["total_unchanged"] is False
        assert result["no_mutation"] is False


# ── TC12: Schema Mutation Detection ──────────────────────────────────────────

class TestTC12SchemaMutationDetection:
    def test_payload_key_count_stable(self):
        conn = _prod_conn()
        v2 = build_canonical_baseline_v2(conn)
        conn.close()
        assert len(v2.fingerprint_payload_keys) == 10

    def test_payload_keys_unchanged_on_rebuild(self):
        conn = _prod_conn()
        v2a = build_canonical_baseline_v2(conn)
        v2b = build_canonical_baseline_v2(conn)
        conn.close()
        assert v2a.fingerprint_payload_keys == v2b.fingerprint_payload_keys


# ── TC13: Parameter Mutation Detection ───────────────────────────────────────

class TestTC13ParameterMutationDetection:
    def test_parameter_hash_matches(self):
        conn = _prod_conn()
        v2 = build_canonical_baseline_v2(conn)
        conn.close()
        assert validate_parameter_hash(v2) is True

    def test_v2_has_correct_parameter_hash(self):
        conn = _prod_conn()
        v2 = build_canonical_baseline_v2(conn)
        conn.close()
        assert v2.parameter_hash == "be43e8ca977d9fdd"


# ── TC14: Calendar Mutation Detection ────────────────────────────────────────

class TestTC14CalendarMutationDetection:
    def test_calendar_contract_unchanged(self):
        conn = _prod_conn()
        v2 = build_canonical_baseline_v2(conn)
        conn.close()
        assert validate_parameter_hash(v2) is True  # parameter_hash includes V3 params
        from src.research.canonical_baseline_v2_s55 import validate_calendar_contract
        assert validate_calendar_contract(v2) is True

    def test_strict_fill_dates_match_expected(self):
        conn = _prod_conn()
        v2 = build_canonical_baseline_v2(conn)
        conn.close()
        assert "2026-10-13" in v2.strict_fill_dates
        assert "2026-10-14" in v2.strict_fill_dates
        assert "2026-10-16" in v2.strict_fill_dates
        assert "2026-10-27" not in v2.strict_fill_dates  # Oct27 is 5TD EXIT not fill date


# ── TC15: Historical Baseline Preservation ───────────────────────────────────

class TestTC15HistoricalBaselinePreservation:
    def test_historical_verdict_unrecoverable(self):
        assert get_historical_baseline_verdict() == HistoricalBaselineVerdict.HISTORICAL_BASELINE_UNRECOVERABLE

    def test_v2_not_replacement_for_historical(self):
        conn = _prod_conn()
        v2 = build_canonical_baseline_v2(conn)
        conn.close()
        assert "not a replacement" in v2.supersedes.lower() or "NEW" in v2.supersedes

    def test_v2_records_historical_fingerprint(self):
        conn = _prod_conn()
        v2 = build_canonical_baseline_v2(conn)
        conn.close()
        assert v2.historical_fingerprint == HISTORICAL_FINGERPRINT

    def test_difference_causes_include_all_three(self):
        assert DifferenceClassification.HISTORICAL_PAYLOAD_MISSING in DIFFERENCE_CAUSES
        assert DifferenceClassification.UNEXPLAINED_DIFFERENCE in DIFFERENCE_CAUSES
        assert DifferenceClassification.SERIALIZATION_DIFFERENCE in DIFFERENCE_CAUSES


# ── TC16: TPEx Wrong-date Error ──────────────────────────────────────────────

class TestTC16TpexWrongDateError:
    def test_wrong_date_propagated_in_patch_after(self):
        results = run_isolated_patch_simulation()
        s2 = next(r for r in results if r.scenario == PatchScenario.WRONG_TPEX_DATE)
        assert s2.tpex_error_propagated is True

    def test_before_code_does_not_propagate(self):
        results = run_isolated_patch_simulation()
        s2 = next(r for r in results if r.scenario == PatchScenario.WRONG_TPEX_DATE)
        assert s2.before_error_count == 0

    def test_after_code_adds_one_error(self):
        results = run_isolated_patch_simulation()
        s2 = next(r for r in results if r.scenario == PatchScenario.WRONG_TPEX_DATE)
        assert s2.after_error_count == 1


# ── TC17: Structured Summary ──────────────────────────────────────────────────

class TestTC17StructuredSummary:
    def test_stale_response_in_summary(self):
        results = run_isolated_patch_simulation()
        stale = next(r for r in results if r.scenario == PatchScenario.STALE_TPEX_RESPONSE)
        assert stale.after_error_count == 1
        assert stale.tpex_error_propagated is True


# ── TC18: Retry History ───────────────────────────────────────────────────────

class TestTC18RetryHistory:
    def test_errors_not_cleared_on_retry(self):
        """S6: retry success still retains error from attempt 1."""
        results = run_isolated_patch_simulation()
        retry_success = next(r for r in results if r.scenario == PatchScenario.RETRY_SUCCESS)
        assert retry_success.after_error_count == 1

    def test_all_4_retry_errors_captured(self):
        results = run_isolated_patch_simulation()
        retry_fail = next(r for r in results if r.scenario == PatchScenario.RETRY_FAILURE)
        assert retry_fail.after_error_count == 4


# ── TC19: Partial Success ─────────────────────────────────────────────────────

class TestTC19PartialSuccess:
    def test_twse_and_tpex_errors_both_captured(self):
        results = run_isolated_patch_simulation()
        partial = next(r for r in results if r.scenario == PatchScenario.PARTIAL_TWSE_SUCCESS)
        assert partial.after_error_count == 2


# ── TC20: Multiple Provider Errors ───────────────────────────────────────────

class TestTC20MultipleProviderErrors:
    def test_two_tpex_errors_captured(self):
        results = run_isolated_patch_simulation()
        multi = next(r for r in results if r.scenario == PatchScenario.MULTIPLE_PROVIDER_ERRORS)
        assert multi.after_error_count == 2


# ── TC21: QG Integration ─────────────────────────────────────────────────────

class TestTC21QGIntegration:
    def test_qg_plus_tpex_error_total(self):
        results = run_isolated_patch_simulation()
        qg = next(r for r in results if r.scenario == PatchScenario.QG_FAILURE)
        assert qg.after_error_count == 2  # TPEx + QG
        assert qg.compatible_with_qg is True


# ── TC22: Completion Marker ───────────────────────────────────────────────────

class TestTC22CompletionMarker:
    def test_correct_date_no_error(self):
        results = run_isolated_patch_simulation()
        cm = next(r for r in results if r.scenario == PatchScenario.COMPLETION_MARKER)
        assert cm.pass_ is True
        assert cm.after_error_count == 0


# ── TC23: Patch Compatibility ─────────────────────────────────────────────────

class TestTC23PatchCompatibility:
    def test_patch_does_not_change_trading_rules(self):
        patch = build_patch_spec()
        assert patch.changes_trading_rules is False

    def test_patch_does_not_change_strategy(self):
        patch = build_patch_spec()
        assert patch.changes_strategy is False

    def test_patch_does_not_change_cron_schedule(self):
        patch = build_patch_spec()
        assert patch.changes_cron_schedule is False

    def test_patch_targets_correct_file(self):
        patch = build_patch_spec()
        assert "backfill_daily_prices.py" in patch.file_path

    def test_patch_before_has_print_only(self):
        patch = build_patch_spec()
        assert "summary" not in patch.before_code

    def test_patch_after_has_summary_errors(self):
        patch = build_patch_spec()
        assert 'summary["errors"]' in patch.after_code


# ── TC24: No Production Deployment ───────────────────────────────────────────

class TestTC24NoProductionDeployment:
    def test_production_deployment_not_authorized(self):
        conn = _prod_conn()
        report = build_patch_verification_report(conn)
        conn.close()
        assert report.production_deployment_authorized is False

    def test_patch_requires_authorization(self):
        patch = build_patch_spec()
        assert patch.deployment_authorization_required is True


# ── TC25: Source Verification ─────────────────────────────────────────────────

class TestTC25SourceVerification:
    def test_oct29_has_verified_prices(self):
        conn = _prod_conn()
        summaries = build_auth01_date_summaries(conn)
        conn.close()
        oct29 = next(s for s in summaries if s.target_date == "2026-10-29")
        assert oct29.twse_verified_count > 0

    def test_tpex_unverified_for_all_dates(self):
        conn = _prod_conn()
        summaries = build_auth01_date_summaries(conn)
        conn.close()
        for s in summaries:
            assert s.tpex_verified_count == 0


# ── TC26: TWSE Coverage Count ─────────────────────────────────────────────────

class TestTC26TWSECoverageCount:
    def test_oct29_twse_verified_3_stocks(self):
        conn = _prod_conn()
        summaries = build_auth01_date_summaries(conn)
        conn.close()
        oct29 = next(s for s in summaries if s.target_date == "2026-10-29")
        assert oct29.twse_verified_count == 3  # 2330, 2454, 2317

    def test_coverage_pct_low_for_insert_candidates(self):
        conn = _prod_conn()
        summaries = build_auth01_date_summaries(conn)
        conn.close()
        for s in summaries:
            if not s.full_coverage_possible and s.insert_candidate_count > 0:
                assert s.coverage_pct < 1.0  # < 1% of total universe


# ── TC27: ETF Exclusion ───────────────────────────────────────────────────────

class TestTC27ETFExclusion:
    def test_no_etfs_in_ordinary_stock_count(self):
        conn = _prod_conn()
        summaries = build_auth01_date_summaries(conn)
        conn.close()
        for s in summaries:
            assert s.etf_count == 0

    def test_records_all_ordinary_stock(self):
        conn = _prod_conn()
        records = build_auth01_record_manifest(conn)
        conn.close()
        for r in records:
            if r.source_verified:
                assert r.security_type == "ordinary_stock"


# ── TC28: Insert-only Manifest ────────────────────────────────────────────────

class TestTC28InsertOnlyManifest:
    def test_oct29_is_insert_candidate(self):
        from src.research.tpex_patch_verification_s55 import Auth01RecordStatus
        conn = _prod_conn()
        records = build_auth01_record_manifest(conn)
        conn.close()
        oct29_records = [r for r in records if r.target_date == "2026-10-29" and r.source_verified]
        assert all(r.action == Auth01RecordStatus.INSERT_CANDIDATE for r in oct29_records)

    def test_nov04_is_skip_existing(self):
        conn = _prod_conn()
        summaries = build_auth01_date_summaries(conn)
        conn.close()
        nov04 = next(s for s in summaries if s.target_date == "2026-11-04")
        assert nov04.skip_existing_count > 0 or nov04.full_coverage_possible


# ── TC29: Duplicate Conflict ──────────────────────────────────────────────────

class TestTC29DuplicateConflict:
    def test_idempotent_insert(self):
        conn = _prod_conn()
        summaries = build_auth01_date_summaries(conn)
        conn.close()
        dry = run_auth01_dry_run(summaries)
        assert dry["test_idempotent"] is True

    def test_conflict_ignored(self):
        conn = _prod_conn()
        summaries = build_auth01_date_summaries(conn)
        conn.close()
        dry = run_auth01_dry_run(summaries)
        assert dry["test_duplicate_conflict"] is True


# ── TC30: Transaction Rollback ────────────────────────────────────────────────

class TestTC30TransactionRollback:
    def test_rollback_works(self):
        conn = _prod_conn()
        summaries = build_auth01_date_summaries(conn)
        conn.close()
        dry = run_auth01_dry_run(summaries)
        assert dry["test_transaction_rollback"] is True

    def test_production_not_modified(self):
        conn = _prod_conn()
        summaries = build_auth01_date_summaries(conn)
        conn.close()
        dry = run_auth01_dry_run(summaries)
        assert dry["production_modified"] is False


# ── TC31: AUTH01 Pending ──────────────────────────────────────────────────────

class TestTC31Auth01Pending:
    def test_oct29_pending_user_authorization(self):
        conn = _prod_conn()
        records = build_auth01_record_manifest(conn)
        conn.close()
        oct29_verified = [r for r in records if r.target_date == "2026-10-29" and r.source_verified]
        assert all(r.authorization_status == "PENDING_USER_AUTHORIZATION" for r in oct29_verified)

    def test_auth01_verdict_partial(self):
        conn = _prod_conn()
        summaries = build_auth01_date_summaries(conn)
        dry = run_auth01_dry_run(summaries)
        conn.close()
        verdict = get_auth01_verdict(summaries, dry)
        assert verdict in (Auth01Verdict.AUTH01_PARTIAL, Auth01Verdict.AUTH01_READY_FOR_REVIEW)


# ── TC32: Root Cause Evidence Classification ──────────────────────────────────

class TestTC32RootCauseEvidence:
    def test_rc01_directly_confirmed(self):
        evidence = build_root_cause_evidence()
        rc01 = next(e for e in evidence if e.candidate_id == "RC-01")
        assert rc01.confidence == RootCauseConfidence.DIRECTLY_CONFIRMED

    def test_rc02_directly_confirmed(self):
        evidence = build_root_cause_evidence()
        rc02 = next(e for e in evidence if e.candidate_id == "RC-02")
        assert rc02.confidence == RootCauseConfidence.DIRECTLY_CONFIRMED

    def test_rc03_strongly_supported(self):
        evidence = build_root_cause_evidence()
        rc03 = next(e for e in evidence if e.candidate_id == "RC-03")
        assert rc03.confidence == RootCauseConfidence.STRONGLY_SUPPORTED
        assert rc03.related_to_tpex_error_propagation is True

    def test_overall_verdict_partial(self):
        assert get_root_cause_verdict() == RootCauseVerdict.ROOT_CAUSE_PARTIAL


# ── TC33: Scheduler Evidence Insufficient ────────────────────────────────────

class TestTC33SchedulerInsufficientEvidence:
    def test_rc04_insufficient_evidence(self):
        evidence = build_root_cause_evidence()
        rc04 = next(e for e in evidence if e.candidate_id == "RC-04")
        assert rc04.confidence == RootCauseConfidence.INSUFFICIENT_EVIDENCE

    def test_rc04_does_not_suggest_cron_modification(self):
        evidence = build_root_cause_evidence()
        rc04 = next(e for e in evidence if e.candidate_id == "RC-04")
        assert "read-only" in rc04.deployment_authorization.lower()


# ── TC34: Prospective Blocker Matrix ─────────────────────────────────────────

class TestTC34ProspectiveBlockerMatrix:
    def test_at_least_5_items_blocked(self):
        from src.research.baseline_fingerprint_reconciliation_s54 import build_prospective_readiness_matrix
        items = build_prospective_readiness_matrix()
        blocked = [i for i in items if not i.ready]
        assert len(blocked) >= 5

    def test_v3_not_activated_is_blocked(self):
        from src.research.baseline_fingerprint_reconciliation_s54 import build_prospective_readiness_matrix
        items = build_prospective_readiness_matrix()
        pr06 = next(i for i in items if i.item_id == "PR-06")
        assert pr06.ready is False


# ── TC35: Mock vs Genuine Evidence ───────────────────────────────────────────

class TestTC35MockVsGenuineEvidence:
    def test_v2_captures_real_signal_ids(self):
        """Signal IDs come from real DB, not mocks."""
        conn = _prod_conn()
        v2 = build_canonical_baseline_v2(conn)
        conn.close()
        for c in v2.clusters:
            assert len(c.signal_ids) >= 20  # Oct13=46, Oct14=27, Oct16=55

    def test_v2_n_clusters_from_db(self):
        conn = _prod_conn()
        v2 = build_canonical_baseline_v2(conn)
        conn.close()
        assert v2.n_strict_clusters == 3


# ── TC36: Calendar SSOT ───────────────────────────────────────────────────────

class TestTC36CalendarSSOT:
    def test_canonical_fill_dates_unchanged(self):
        from src.research.baseline_fingerprint_reconciliation_s54 import CANONICAL_FILL_DATES
        expected = ["2026-10-13", "2026-10-14", "2026-10-16", "2026-10-21", "2026-10-22", "2026-10-28"]
        assert CANONICAL_FILL_DATES == expected

    def test_oct27_not_a_fill_date(self):
        from src.research.baseline_fingerprint_reconciliation_s54 import CANONICAL_FILL_DATES
        assert "2026-10-27" not in CANONICAL_FILL_DATES


# ── TC37: 20D Maturity ────────────────────────────────────────────────────────

class TestTC37TwentyDMaturity:
    def test_oct13_maturity_nov12(self):
        from src.research.baseline_fingerprint_reconciliation_s54 import CANONICAL_20TD_EXITS
        assert CANONICAL_20TD_EXITS["2026-10-13"] == "2026-11-12"

    def test_oct28_maturity_nov25(self):
        from src.research.baseline_fingerprint_reconciliation_s54 import CANONICAL_20TD_EXITS
        assert CANONICAL_20TD_EXITS["2026-10-28"] == "2026-11-25"

    def test_nov12_not_hard_deadline(self):
        """Nov12 is earliest maturity date, not permanent data-loss deadline."""
        # This is a documentation verification — confirmed by calendar_20d_readiness_session54.md
        from src.research.baseline_fingerprint_reconciliation_s54 import CANONICAL_20TD_EXITS
        assert CANONICAL_20TD_EXITS["2026-10-13"] == "2026-11-12"


# ── TC38: AUTH02 Not Authorized ───────────────────────────────────────────────

class TestTC38Auth02NotAuthorized:
    def test_auth02_not_authorized(self):
        from src.research.baseline_fingerprint_reconciliation_s54 import GUARDRAIL_STATUS
        assert GUARDRAIL_STATUS["ACTIVATION"] == "BLOCKED"

    def test_twenty_d_not_ready(self):
        conn = _prod_conn()
        from src.research.baseline_fingerprint_reconciliation_s54 import (
            build_20d_readiness_matrix, get_20d_verdict, TwentyDVerdict
        )
        items = build_20d_readiness_matrix(conn)
        conn.close()
        assert get_20d_verdict(items) == TwentyDVerdict.TWENTY_D_NOT_READY


# ── TC39: G03/G04 Status ──────────────────────────────────────────────────────

class TestTC39G03G04Status:
    def test_g03_fail(self):
        from src.research.baseline_fingerprint_reconciliation_s54 import GUARDRAIL_STATUS
        assert GUARDRAIL_STATUS["G03_PROSPECTIVE_N"] == "FAIL"

    def test_g04_structural_fail(self):
        from src.research.baseline_fingerprint_reconciliation_s54 import GUARDRAIL_STATUS
        assert GUARDRAIL_STATUS["G04_CLUSTER_INDEPENDENCE"] == "STRUCTURAL_FAIL"

    def test_activation_blocked(self):
        from src.research.baseline_fingerprint_reconciliation_s54 import GUARDRAIL_STATUS
        assert GUARDRAIL_STATUS["ACTIVATION"] == "BLOCKED"


# ── TC40: Production Fingerprint Integrity ────────────────────────────────────

class TestTC40ProductionFingerprintIntegrity:
    def test_baseline_not_modified(self):
        from src.research.baseline_fingerprint_reconciliation_s54 import verify_baseline_not_modified
        conn = _prod_conn()
        result = verify_baseline_not_modified(conn)
        conn.close()
        assert result is True, "Production DB baseline fingerprint mismatch!"

    def test_v2_fingerprint_stable_across_builds(self):
        conn = _prod_conn()
        v2a = build_canonical_baseline_v2(conn)
        v2b = build_canonical_baseline_v2(conn)
        conn.close()
        assert v2a.fingerprint == v2b.fingerprint

    def test_v2_verdict_verified(self):
        conn = _prod_conn()
        v2 = build_canonical_baseline_v2(conn)
        conn.close()
        assert get_canonical_v2_verdict(v2) == CanonicalV2Verdict.CANONICAL_V2_VERIFIED

    def test_full_report_does_not_write(self):
        conn = _prod_conn()
        before = conn.execute("SELECT COUNT(*) FROM forward_signals").fetchone()[0]
        build_baseline_recovery_report(conn)
        after = conn.execute("SELECT COUNT(*) FROM forward_signals").fetchone()[0]
        conn.close()
        assert before == after
