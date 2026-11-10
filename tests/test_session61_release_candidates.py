"""
Session 61 — Release Candidate Acceptance Tests

RC61-01-TPEX-ERROR  : TPEx error reporting patch  (line 500-501)
RC61-02-SECURITY-ELIGIBILITY : Warrant/ETF exclusion fix (line 98)
RC61-03-TPEX-VOLUME : TradingShares field mapping  (line 284)

Categories:
 TC01-TC06  RC-1 error reporting acceptance
 TC07-TC16  RC-2 security eligibility acceptance (false exclusion audit)
 TC17-TC24  RC-3 TradingShares volume acceptance
 TC25-TC31  Seven RC combination matrix
 TC32-TC38  Rollback rehearsal (apply + revert = exact original)
 TC39-TC44  Patch independence verification
 TC45-TC50  DQ acceptance metrics
 TC51-TC56  Authorization packages completeness
 TC57-TC62  Production safety / frozen state
"""

from __future__ import annotations

import hashlib
import os
import sqlite3

import pytest

from src.research.release_candidate_harness_s61 import (
    COMBINATIONS,
    SCRIPT_PATH,
    DQVerdict,
    IndependenceVerdict,
    IntegrationVerdict,
    RC1Verdict,
    RC2Verdict,
    RC3Verdict,
    RCId,
    RollbackVerdict,
    build_release_gate_report,
    get_all_rcs,
    get_authorization_packages,
    get_dq_acceptance_metrics,
    get_rollback_limitations,
    run_combination_matrix,
    run_eligibility_test_cases,
    run_error_handling_test_cases,
    run_rollback_rehearsal,
    run_volume_test_cases,
    simulate_error_handling_after,
    simulate_error_handling_before,
    simulate_is_excluded_after,
    simulate_is_excluded_before,
    simulate_tpex_amount,
    simulate_tpex_volume_after,
    simulate_tpex_volume_before,
    simulate_twse_volume,
    verify_diff_applicable,
    verify_rollback_in_memory,
)

PROD_DB = "data/platform.db"


# ── TC01-TC06: RC-1 Error Reporting Acceptance ─────────────────────────────────

class TestRC1ErrorReporting:
    def test_tc01_tpex_mismatch_not_in_errors_before_patch(self):
        errors = simulate_error_handling_before("2026-10-29", "2026-11-05")
        assert len(errors) == 0, "Before patch: mismatch should NOT be in errors"

    def test_tc02_tpex_mismatch_added_to_errors_after_patch(self):
        errors = simulate_error_handling_after("2026-10-29", "2026-11-05")
        assert len(errors) == 1
        assert "TPEx api_date" in errors[0]
        assert "2026-11-05" in errors[0]

    def test_tc03_no_mismatch_no_error(self):
        errors_b = simulate_error_handling_before("2026-11-05", "2026-11-05")
        errors_a = simulate_error_handling_after("2026-11-05", "2026-11-05")
        assert len(errors_b) == 0
        assert len(errors_a) == 0

    def test_tc04_none_api_date_no_error(self):
        errors = simulate_error_handling_after(None, "2026-11-05")
        assert len(errors) == 0

    def test_tc05_error_message_matches_twse_pattern(self):
        errors = simulate_error_handling_after("2026-10-01", "2026-11-05")
        assert len(errors) == 1
        assert "API returned wrong date" in errors[0]

    def test_tc06_exact_diff_in_script(self):
        rcs = {rc.rc_id: rc for rc in get_all_rcs()}
        rc1 = rcs["RC61-01-TPEX-ERROR"]
        result = verify_diff_applicable(rc1)
        assert result.original_found, f"RC-1 original text not found in script: {result.notes}"
        assert result.unique_match, f"RC-1 original text not unique: {result.notes}"
        assert not result.patched_already_applied, "RC-1 already applied!"
        assert result.applicable, f"RC-1 not applicable: {result.notes}"


# ── TC07-TC16: RC-2 Security Eligibility Acceptance ───────────────────────────

class TestRC2SecurityEligibility:
    def test_tc07_twse_ordinary_4digit_not_excluded(self):
        assert simulate_is_excluded_before("台積電", "2330") is False
        assert simulate_is_excluded_after("台積電", "2330") is False

    def test_tc08_tpex_ordinary_4digit_not_excluded(self):
        assert simulate_is_excluded_before("凌華", "6166") is False
        assert simulate_is_excluded_after("凌華", "6166") is False

    def test_tc09_innovation_board_4digit_not_excluded(self):
        assert simulate_is_excluded_before("億而得-創", "6423") is False
        assert simulate_is_excluded_after("億而得-創", "6423") is False

    def test_tc10_warrant_6digit_was_bug_now_fixed(self):
        # Before patch: 700022 passes through (BUG)
        assert simulate_is_excluded_before("台積電購01", "700022") is False
        # After patch: correctly excluded
        assert simulate_is_excluded_after("台積電購01", "700022") is True

    def test_tc11_etf_5digit_was_bug_now_fixed(self):
        # Before patch: 00858 passes through (BUG)
        assert simulate_is_excluded_before("永豐ESG", "00858") is False
        # After patch: correctly excluded
        assert simulate_is_excluded_after("永豐ESG", "00858") is True

    def test_tc12_etf_6digit_was_bug_now_fixed(self):
        assert simulate_is_excluded_before("元大富櫃50", "006201") is False
        assert simulate_is_excluded_after("元大富櫃50", "006201") is True

    def test_tc13_name_keyword_exclusion_unchanged(self):
        # Name-based exclusion unchanged regardless of patch
        assert simulate_is_excluded_before("台積電ETF", "2330") is True
        assert simulate_is_excluded_after("台積電ETF", "2330") is True

    def test_tc14_zero_false_exclusions_in_full_audit(self):
        cases = run_eligibility_test_cases()
        regressions = [c for c in cases if c.is_regression]
        assert len(regressions) == 0, (
            "RC-2 false exclusions detected: "
            + str([(c.stock_id, c.name) for c in regressions])
        )

    def test_tc15_all_audit_cases_pass(self):
        cases = run_eligibility_test_cases()
        failures = [c for c in cases if c.verdict == "FAIL"]
        assert len(failures) == 0, (
            "RC-2 eligibility audit failures: "
            + str([(c.stock_id, c.security_type, c.after_excluded, c.expected_after) for c in failures])
        )

    def test_tc16_exact_diff_in_script(self):
        rcs = {rc.rc_id: rc for rc in get_all_rcs()}
        rc2 = rcs["RC61-02-SECURITY-ELIGIBILITY"]
        result = verify_diff_applicable(rc2)
        assert result.applicable, f"RC-2 not applicable: {result.notes}"
        assert result.unique_match, f"RC-2 original text not unique: {result.notes}"


# ── TC17-TC24: RC-3 TradingShares Volume Acceptance ──────────────────────────

class TestRC3TradingShares:
    def test_tc17_tpex_tradevolume_null_before_patch(self):
        # TPEx row only has TradingShares, not TradeVolume
        row = {"TradingShares": "89094382", "TradeValue": "21856270000", "Open": "241"}
        v_before = simulate_tpex_volume_before(row)
        assert v_before is None, f"Before patch: volume should be NULL, got {v_before}"

    def test_tc18_tpex_tradingshares_non_null_after_patch(self):
        row = {"TradingShares": "89094382", "TradeValue": "21856270000", "Open": "241"}
        v_after = simulate_tpex_volume_after(row)
        assert v_after is not None
        assert abs(v_after - 89094.382) < 0.001

    def test_tc19_volume_unit_1000_divisor_confirmed(self):
        # S58 P02: 2317/Nov06 raw=89,094,382 → stored as 89,094.382 千股
        row = {"TradingShares": "89094382"}
        v = simulate_tpex_volume_after(row)
        assert v == pytest.approx(89094.382, abs=0.001)

    def test_tc20_twse_path_uses_tradevolume_unchanged(self):
        # TWSE row uses TradeVolume (correct), unchanged by RC-3
        row = {"TradeVolume": "25000000", "OpeningPrice": "2415"}
        v = simulate_twse_volume(row)
        assert v is not None
        assert abs(v - 25000.0) < 0.001

    def test_tc21_pp03_excluded_amount_uses_tradevalue(self):
        # Amount field NOT changed by RC-3 (PP-03 excluded)
        row = {"TradingShares": "89094382", "TradeValue": "21856270000", "Open": "241"}
        amt = simulate_tpex_amount(row)
        assert amt is not None  # TradeValue IS present in this row

    def test_tc22_zero_volume_valid(self):
        row = {"TradingShares": "0"}
        v = simulate_tpex_volume_after(row)
        assert v == 0.0

    def test_tc23_missing_tradingshares_null(self):
        row = {"Open": "241"}
        v = simulate_tpex_volume_after(row)
        assert v is None

    def test_tc24_all_volume_test_cases_pass(self):
        cases = run_volume_test_cases()
        failures = [c for c in cases if c.verdict == "FAIL"]
        assert len(failures) == 0, (
            "RC-3 volume test failures: "
            + str([(c.test_id, c.description, c.volume_before, c.volume_after, c.expected_behavior) for c in failures])
        )


# ── TC25-TC31: Seven RC Combination Matrix ────────────────────────────────────

class TestSevenCombinations:
    def _run_and_check(self, combo_ids):
        results = run_combination_matrix()
        id_set = set(c if isinstance(c, str) else c.value for c in combo_ids)
        for r in results:
            if set(r.rc_ids) == id_set:
                assert r.all_applied, f"{r.combination_id}: not all patches applied"
                assert r.no_conflict, f"{r.combination_id}: conflict detected"
                assert r.rollback_verified, f"{r.combination_id}: rollback failed"
                assert r.production_untouched, f"{r.combination_id}: production touched"
                assert r.verdict == "PASS", f"{r.combination_id}: verdict={r.verdict}"
                return
        pytest.fail(f"Combination {combo_ids} not found in results")

    def test_tc25_rc1_only(self):
        self._run_and_check([RCId.RC1])

    def test_tc26_rc2_only(self):
        self._run_and_check([RCId.RC2])

    def test_tc27_rc3_only(self):
        self._run_and_check([RCId.RC3])

    def test_tc28_rc1_rc2(self):
        self._run_and_check([RCId.RC1, RCId.RC2])

    def test_tc29_rc1_rc3(self):
        self._run_and_check([RCId.RC1, RCId.RC3])

    def test_tc30_rc2_rc3(self):
        self._run_and_check([RCId.RC2, RCId.RC3])

    def test_tc31_rc1_rc2_rc3(self):
        self._run_and_check([RCId.RC1, RCId.RC2, RCId.RC3])


# ── TC32-TC38: Rollback Rehearsal ─────────────────────────────────────────────

class TestRollbackRehearsal:
    def test_tc32_rc1_rollback_exact_hash(self):
        assert verify_rollback_in_memory([RCId.RC1.value])

    def test_tc33_rc2_rollback_exact_hash(self):
        assert verify_rollback_in_memory([RCId.RC2.value])

    def test_tc34_rc3_rollback_exact_hash(self):
        assert verify_rollback_in_memory([RCId.RC3.value])

    def test_tc35_combined_rollback_all_three(self):
        assert verify_rollback_in_memory([RCId.RC1.value, RCId.RC2.value, RCId.RC3.value])

    def test_tc36_all_rollback_results_verified(self):
        results = run_rollback_rehearsal()
        failures = [r for r in results if r.verdict != RollbackVerdict.ROLLBACK_VERIFIED]
        assert len(failures) == 0, (
            "Rollback failures: "
            + str([(r.test_id, r.description, r.hashes_match, r.residual_patched_text_found) for r in failures])
        )

    def test_tc37_rollback_hash_matches_base(self):
        results = run_rollback_rehearsal()
        for r in results:
            assert r.hashes_match, (
                f"{r.test_id}: after_rollback_hash={r.after_rollback_hash} "
                f"!= base_hash={r.base_hash}"
            )

    def test_tc38_rollback_limitations_documented(self):
        lims = get_rollback_limitations()
        assert lims.code_rollback_reversible is True
        assert lims.db_rollback_needed is False  # no production writes in S61
        assert "not" not in lims.code_rollback_note.lower()[:20]  # starts with positive claim


# ── TC39-TC44: Patch Independence ─────────────────────────────────────────────

class TestPatchIndependence:
    def test_tc39_rc1_rc2_no_overlap(self):
        rcs = {rc.rc_id: rc for rc in get_all_rcs()}
        rc1 = rcs["RC61-01-TPEX-ERROR"]
        rc2 = rcs["RC61-02-SECURITY-ELIGIBILITY"]
        assert rc1.original_text not in rc2.original_text
        assert rc2.original_text not in rc1.original_text
        assert rc1.patched_text not in rc2.patched_text

    def test_tc40_rc1_rc3_no_overlap(self):
        rcs = {rc.rc_id: rc for rc in get_all_rcs()}
        rc1 = rcs["RC61-01-TPEX-ERROR"]
        rc3 = rcs["RC61-03-TPEX-VOLUME"]
        assert rc1.original_text not in rc3.original_text
        assert rc3.original_text not in rc1.original_text

    def test_tc41_rc2_rc3_no_overlap(self):
        rcs = {rc.rc_id: rc for rc in get_all_rcs()}
        rc2 = rcs["RC61-02-SECURITY-ELIGIBILITY"]
        rc3 = rcs["RC61-03-TPEX-VOLUME"]
        assert rc2.original_text not in rc3.original_text
        assert rc3.original_text not in rc2.original_text

    def test_tc42_all_original_texts_unique_in_script(self):
        with open(SCRIPT_PATH) as f:
            src = f.read()
        for rc in get_all_rcs():
            count = src.count(rc.original_text)
            assert count == 1, f"{rc.rc_id}: original_text appears {count} times (expected 1)"

    def test_tc43_no_rc_already_patched(self):
        with open(SCRIPT_PATH) as f:
            src = f.read()
        for rc in get_all_rcs():
            assert rc.patched_text not in src, f"{rc.rc_id}: patch already applied!"

    def test_tc44_combination_count_is_seven(self):
        assert len(COMBINATIONS) == 7


# ── TC45-TC50: DQ Acceptance Metrics ─────────────────────────────────────────

class TestDQAcceptanceMetrics:
    def test_tc45_three_dq_metrics(self):
        metrics = get_dq_acceptance_metrics()
        assert len(metrics) == 3
        ids = {m.rc_id for m in metrics}
        assert "RC61-01-TPEX-ERROR" in ids
        assert "RC61-02-SECURITY-ELIGIBILITY" in ids
        assert "RC61-03-TPEX-VOLUME" in ids

    def test_tc46_all_metrics_measurable(self):
        for m in get_dq_acceptance_metrics():
            assert m.measurable is True

    def test_tc47_rc2_no_qg_threshold_lowering(self):
        metrics = get_dq_acceptance_metrics()
        rc2_m = next(m for m in metrics if m.rc_id == "RC61-02-SECURITY-ELIGIBILITY")
        assert "reclassification" in rc2_m.expected_improvement.lower()

    def test_tc48_rc3_historical_null_rows_acknowledged(self):
        metrics = get_dq_acceptance_metrics()
        rc3_m = next(m for m in metrics if m.rc_id == "RC61-03-TPEX-VOLUME")
        assert "21,846" in rc3_m.baseline or "historical" in rc3_m.baseline.lower()

    def test_tc49_rollback_triggers_defined(self):
        for m in get_dq_acceptance_metrics():
            assert len(m.rollback_trigger) > 0

    def test_tc50_dq_verdict_in_report(self):
        report = build_release_gate_report(PROD_DB)
        assert report.dq_verdict == DQVerdict.DQ_ACCEPTANCE_READY


# ── TC51-TC56: Authorization Packages ─────────────────────────────────────────

class TestAuthorizationPackages:
    def test_tc51_three_independent_packages(self):
        pkgs = get_authorization_packages()
        assert len(pkgs) == 3
        ids = {p.authorization_id for p in pkgs}
        assert "AUTH-RC61-01" in ids
        assert "AUTH-RC61-02" in ids
        assert "AUTH-RC61-03" in ids

    def test_tc52_all_not_authorized(self):
        for p in get_authorization_packages():
            assert p.authorization_status == "NOT_AUTHORIZED"
            assert p.user_approval_required is True
            assert p.not_bundled_with  # each lists the other two

    def test_tc53_each_has_exact_diff(self):
        for p in get_authorization_packages():
            assert len(p.exact_original) > 0
            assert len(p.exact_patched) > 0
            assert p.exact_original != p.exact_patched

    def test_tc54_each_has_rollback_steps(self):
        for p in get_authorization_packages():
            assert len(p.rollback_steps) >= 2

    def test_tc55_each_has_stop_conditions(self):
        for p in get_authorization_packages():
            assert len(p.stop_conditions) > 0

    def test_tc56_packages_list_other_two_as_unbundled(self):
        pkgs = {p.authorization_id: p for p in get_authorization_packages()}
        for auth_id, p in pkgs.items():
            others = [a for a in pkgs if a != auth_id]
            for other in others:
                assert other in p.not_bundled_with, (
                    f"{auth_id}: should list {other} in not_bundled_with"
                )


# ── TC57-TC62: Production Safety / Frozen State ───────────────────────────────

class TestProductionSafety:
    def test_tc57_production_script_unchanged(self):
        # Script SHA-256 must match Session 60 reference
        EXPECTED_HASH = "4bb88de209df6b82995f61dcae19eef0d313f18acc0fc77051a12f40f3fce9d9"
        with open(SCRIPT_PATH, "rb") as f:
            actual = hashlib.sha256(f.read()).hexdigest()
        assert actual == EXPECTED_HASH, (
            f"Production script modified! Expected {EXPECTED_HASH[:16]}..., got {actual[:16]}..."
        )

    def test_tc58_daily_prices_max_date_unchanged(self):
        conn = sqlite3.connect(PROD_DB)
        cur = conn.cursor()
        cur.execute("SELECT MAX(date) FROM daily_prices WHERE stock_id='0050'")
        max_date = cur.fetchone()[0]
        conn.close()
        assert max_date == "2026-11-05", f"daily_prices max changed! Got {max_date}"

    def test_tc59_v3_param_hash_frozen(self):
        FROZEN = "be43e8ca977d9fdd"
        try:
            from src.research.v3_entry_timing import PARAMETER_HASH
            assert PARAMETER_HASH == FROZEN
        except ImportError:
            pytest.skip("v3_entry_timing not importable")

    def test_tc60_no_production_writes_in_harness(self):
        mtime_before = os.path.getmtime(PROD_DB)
        _ = build_release_gate_report(PROD_DB)
        mtime_after = os.path.getmtime(PROD_DB)
        assert mtime_before == mtime_after

    def test_tc61_all_rcs_not_authorized_in_report(self):
        report = build_release_gate_report(PROD_DB)
        assert report.all_not_authorized is True
        assert report.deployment_status == "NO_DEPLOYMENT_EXECUTED"
        assert report.auth01 == "NOT_AUTHORIZED"
        assert report.auth02 == "NOT_AUTHORIZED"

    def test_tc62_frozen_state_preserved(self):
        report = build_release_gate_report(PROD_DB)
        assert report.genuine_prospective_n == 0
        assert report.g03 == "G03_FAIL"
        assert report.g04 == "G04_STRUCTURAL_FAIL"
        assert report.v3_activation == "ACTIVATION_BLOCKED"
        assert report.pp03_excluded is True


# ── Final Verdict Tests ────────────────────────────────────────────────────────

class TestFinalVerdicts:
    def test_rc_verdicts_all_pass(self):
        report = build_release_gate_report(PROD_DB)
        assert report.rc1_verdict == RC1Verdict.RC1_ACCEPTANCE_PASS
        assert report.rc2_verdict == RC2Verdict.RC2_ACCEPTANCE_PASS
        assert report.rc3_verdict == RC3Verdict.RC3_ACCEPTANCE_PASS

    def test_independence_verified(self):
        report = build_release_gate_report(PROD_DB)
        assert report.independence_verdict == IndependenceVerdict.PATCH_INDEPENDENCE_VERIFIED

    def test_integration_pass(self):
        report = build_release_gate_report(PROD_DB)
        assert report.integration_verdict == IntegrationVerdict.INTEGRATION_PASS

    def test_rollback_verified(self):
        report = build_release_gate_report(PROD_DB)
        assert report.rollback_verdict == RollbackVerdict.ROLLBACK_VERIFIED

    def test_all_combination_results_pass(self):
        results = run_combination_matrix()
        assert len(results) == 7
        for r in results:
            assert r.verdict == "PASS", f"Combination {r.combination_id} failed: {r.notes}"

    def test_error_handling_all_cases_pass(self):
        cases = run_error_handling_test_cases()
        failures = [c for c in cases if c.verdict == "FAIL"]
        assert len(failures) == 0

    def test_script_path_exists(self):
        assert os.path.exists(SCRIPT_PATH), f"Script not found: {SCRIPT_PATH}"
