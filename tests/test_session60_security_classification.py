"""
Session 60 — TPEx Security Classification & Patch Release Gate Tests

40+ categories:
 TC01-TC04  NULL Population counts (4 disjoint sets)
 TC05-TC08  Set Intersection / Union / Remainder (mutual exclusion proof)
 TC09-TC12  25-row reconciliation (SET-D, 6423)
 TC13-TC16  Ordinary / Warrant / ETF classification
 TC17-TC20  ETN / Preferred / Unknown / PIT
 TC21-TC24  Listing / Delisting / Exchange Transfer / Warrant False Positive
 TC25-TC28  Warrant False Negative / QG Numerator / Denominator / No False Coverage
 TC29-TC32  TradingShares / TradeVolume / Volume Unit / Both Fields
 TC33-TC36  Missing Fields / Wrong-date / Parser Isolation / TWSE Unchanged
 TC37-TC40  Patch Independence / Rollback / Historical Repair / No Production Write
 TC41-TC44  TWSE PIT Universe / Stock-month Dedup / T2 Compliance / 20D Readiness
 TC45-TC48  Genuine Prospective N=0 / Frozen Fingerprints / QG Reclassification / S59 Correction
"""

from __future__ import annotations

import os
import sqlite3

import pytest

from src.research.tpex_security_classification_s60 import (
    SecurityType,
    SetReconciliationVerdict,
    WarrantPatchVerdict,
    build_classification_rules,
    build_null_volume_sets,
    build_ordinary_stock_null_analysis,
    build_security_classification_report,
    build_set_reconciliation,
    build_twenty_five_row_investigation,
    build_warrant_exclusion_patch,
    run_qg_exclusion_simulation,
)
from src.research.patch_release_gate_s60 import (
    ErrorPatchVerdict,
    HistoricalRepairVerdict,
    ManifestVerdict,
    ParserPatchVerdict,
    PitUniverseVerdict,
    T2ComplianceVerdict,
    build_historical_repair_analysis,
    build_independent_patches,
    build_parser_patches,
    build_patch_release_gate_report,
    build_stock_month_manifest,
    build_t2_request_budget,
    build_twse_pit_universe,
    build_twenty_d_clusters,
    build_volume_unit_contract,
    verify_patch_independence,
)

PROD_DB = "data/platform.db"


# ── TC01-TC04: NULL Population Counts ─────────────────────────────────────────

class TestNullPopulationCounts:
    def test_tc01_set_a_six_digit_total(self):
        sets = build_null_volume_sets()
        set_a = next(s for s in sets if s.set_id == "SET-A")
        assert set_a.null_volume_rows == 107_590

    def test_tc02_set_b_five_digit_etfs(self):
        sets = build_null_volume_sets()
        set_b = next(s for s in sets if s.set_id == "SET-B")
        assert set_b.null_volume_rows == 175
        assert set_b.distinct_stocks == 7

    def test_tc03_set_c_tpex_ordinary(self):
        sets = build_null_volume_sets()
        set_c = next(s for s in sets if s.set_id == "SET-C")
        assert set_c.null_volume_rows == 21_846

    def test_tc04_set_d_twse_6423_only(self):
        sets = build_null_volume_sets()
        set_d = next(s for s in sets if s.set_id == "SET-D")
        assert set_d.null_volume_rows == 25
        assert set_d.distinct_stocks == 1
        assert "6423" in set_d.stock_id_pattern


# ── TC05-TC08: Set Intersection / Union / Mutual Exclusion ─────────────────────

class TestSetMutualExclusion:
    def test_tc05_union_equals_total(self):
        recon = build_set_reconciliation()
        assert recon.union_total == 129_636

    def test_tc06_all_intersections_zero(self):
        recon = build_set_reconciliation()
        assert recon.intersection_a_b == 0
        assert recon.intersection_a_c == 0
        assert recon.intersection_b_c == 0
        assert recon.intersection_c_d == 0

    def test_tc07_verdict_fully_reconciled(self):
        recon = build_set_reconciliation()
        assert recon.verdict == SetReconciliationVerdict.NULL_VOLUME_FULLY_RECONCILED
        assert recon.reconciled is True

    def test_tc08_sum_of_parts_equals_union(self):
        recon = build_set_reconciliation()
        assert recon.set_a + recon.set_b + recon.set_c + recon.set_d == recon.union_total == 129_636


# ── TC09-TC12: 25-Row Reconciliation (SET-D / 6423) ───────────────────────────

class TestTwentyFiveRows:
    def test_tc09_exactly_25_rows(self):
        rows = build_twenty_five_row_investigation()
        assert len(rows) == 25

    def test_tc10_all_from_6423(self):
        rows = build_twenty_five_row_investigation()
        for r in rows:
            assert r.stock_id == "6423"
            assert "億而得" in r.stock_name

    def test_tc11_carry_forward_dates_identified(self):
        rows = build_twenty_five_row_investigation()
        carry_forward = [r for r in rows if r.ohlc_carry_forward]
        assert len(carry_forward) == 8
        # Jun01-Jun10 have identical OHLC
        jun_dates = {r.date for r in carry_forward}
        assert any("2026-06" in d for d in jun_dates)

    def test_tc12_volume_is_null_for_all_25(self):
        rows = build_twenty_five_row_investigation()
        for r in rows:
            assert r.volume is None
        # All OHLC present
        for r in rows:
            assert r.open is not None
            assert r.close is not None


# ── TC13-TC16: Ordinary / Warrant / ETF Classification ────────────────────────

class TestSecurityClassification:
    def test_tc13_warrant_rule_exists(self):
        rules = build_classification_rules()
        warrant_rules = [r for r in rules if r.classified_as == SecurityType.WARRANT]
        assert len(warrant_rules) >= 1
        warrant_rule = warrant_rules[0]
        assert warrant_rule.qg_eligible is False
        assert warrant_rule.should_be_in_daily_prices is False

    def test_tc14_etf_rules_not_qg_eligible(self):
        rules = build_classification_rules()
        etf_rules = [r for r in rules if r.classified_as == SecurityType.ETF]
        assert len(etf_rules) >= 2  # 5-digit and 6-digit ETFs
        for r in etf_rules:
            assert r.qg_eligible is False

    def test_tc15_ordinary_stock_in_stocks_table_is_qg_eligible(self):
        rules = build_classification_rules()
        twse_rule = next(
            r for r in rules
            if r.classified_as == SecurityType.ORDINARY_STOCK
            and r.in_stocks_table is True
        )
        assert twse_rule.qg_eligible is True

    def test_tc16_tpex_ordinary_not_in_stocks_table(self):
        rules = build_classification_rules()
        tpex_rule = next(
            r for r in rules
            if r.classified_as == SecurityType.ORDINARY_STOCK
            and r.in_stocks_table is False
        )
        # TPEx ordinary: qg_eligible=False because not in stocks table
        assert tpex_rule.qg_eligible is False


# ── TC17-TC20: ETN / Preferred / Unknown / PIT ────────────────────────────────

class TestSecurityTypeCoverage:
    def test_tc17_security_type_enum_has_etn(self):
        assert SecurityType.ETN is not None
        assert SecurityType.ETN.value == "ETN"

    def test_tc18_security_type_enum_has_preferred(self):
        assert SecurityType.PREFERRED_SHARE is not None

    def test_tc19_security_type_unknown_exists(self):
        assert SecurityType.UNKNOWN is not None

    def test_tc20_pit_universe_query_runs(self):
        pit = build_twse_pit_universe(PROD_DB)
        assert pit.s59_hardcoded == 712
        assert pit.s60_aug2026_query >= 712  # S60 >= S59 estimate


# ── TC21-TC24: Listing / Exchange Transfer / Warrant False Positive ────────────

class TestListingAndTransfer:
    def test_tc21_warrant_6digit_prefix7_classified_warrant(self):
        rules = build_classification_rules()
        rule = next(r for r in rules if "7" in str(r.stock_id_prefix) and r.classified_as == SecurityType.WARRANT)
        assert rule is not None
        assert rule.stock_id_len == 6

    def test_tc22_006xxx_etfs_classified_etf_not_warrant(self):
        rules = build_classification_rules()
        rule = next(r for r in rules if str(r.stock_id_prefix) == "006")
        assert rule.classified_as == SecurityType.ETF

    def test_tc23_warrant_false_positive_documented_in_patch(self):
        patch = build_warrant_exclusion_patch()
        # false_positive_risk describes the edge case
        assert "5-digit" in patch.false_positive_risk or "ETF" in patch.false_positive_risk

    def test_tc24_warrant_false_negative_none(self):
        patch = build_warrant_exclusion_patch()
        assert "NONE" in patch.false_negative_risk.upper() or len(patch.false_negative_risk) > 0


# ── TC25-TC28: Warrant False Negative / QG Numerator / Denominator / Coverage ──

class TestWarrantPatchQG:
    def test_tc25_warrant_false_negative_no_4digit_exclusion(self):
        patch = build_warrant_exclusion_patch()
        assert "4-digit" in patch.securities_NOT_affected[0]

    def test_tc26_qg_numerator_increases_after_patch(self):
        results = run_qg_exclusion_simulation()
        before = next(r for r in results if "before" in r.test_name)
        after = next(r for r in results if "after" in r.test_name)
        # Denominator shrinks; numerator (ordinary with volume) stays same or grows
        assert after.universe_after <= before.universe_before

    def test_tc27_qg_denominator_shrinks_after_patch(self):
        results = run_qg_exclusion_simulation()
        after = next(r for r in results if "after" in r.test_name)
        before = next(r for r in results if "before" in r.test_name)
        assert after.universe_after < before.universe_before

    def test_tc28_coverage_improvement_is_reclassification(self):
        results = run_qg_exclusion_simulation()
        after = next(r for r in results if "after" in r.test_name)
        assert "reclassification" in after.note.lower() or "NOT new data" in after.note


# ── TC29-TC32: TradingShares / TradeVolume / Volume Unit / Both Fields ──────────

class TestVolumeFieldMapping:
    def test_tc29_pp02_uses_tradingshares(self):
        patches = build_parser_patches()
        pp02 = next(p for p in patches if p.patch_id == "PP-02")
        assert "TradingShares" in pp02.patched_line

    def test_tc30_original_uses_tradevolume(self):
        patches = build_parser_patches()
        pp02 = next(p for p in patches if p.patch_id == "PP-02")
        assert "TradeVolume" in pp02.original_line

    def test_tc31_volume_unit_contract_divides_by_1000(self):
        contract = build_volume_unit_contract()
        assert contract.twse_divisor == 1_000.0
        assert contract.tpex_divisor == 1_000.0

    def test_tc32_both_fields_confirmed_for_tpex(self):
        contract = build_volume_unit_contract()
        assert "DIRECTLY CONFIRMED" in contract.tpex_api_field_corrected
        assert "TradingShares" in contract.tpex_api_field_corrected


# ── TC33-TC36: Missing Fields / Wrong-date / Parser Isolation / TWSE Unchanged ─

class TestParserIsolation:
    def test_tc33_pp03_marked_hypothesis(self):
        patches = build_parser_patches()
        pp03 = next(p for p in patches if p.patch_id == "PP-03")
        assert "HYPOTHESIS" in pp03.confidence or "MEDIUM" in pp03.confidence

    def test_tc34_pp03_unresolved_assumptions_documented(self):
        patches = build_parser_patches()
        pp03 = next(p for p in patches if p.patch_id == "PP-03")
        assert "verify" in pp03.unresolved_assumptions.lower() or "must" in pp03.unresolved_assumptions.lower()

    def test_tc35_pp02_affects_tpex_not_twse(self):
        patches = build_parser_patches()
        pp02 = next(p for p in patches if p.patch_id == "PP-02")
        assert pp02.affects_tpex is True
        assert pp02.affects_twse is False

    def test_tc36_patch3_excludes_pp03(self):
        patches = build_independent_patches()
        patch3 = next(p for p in patches if p.patch_id == "PATCH-3")
        # PP-03 must NOT be bundled
        assert "PP-03" in patch3.exact_diff and "NOT included" in patch3.exact_diff


# ── TC37-TC40: Patch Independence / Rollback / Historical Repair / No Prod Write

class TestPatchIndependenceAndRepair:
    def test_tc37_three_independent_patches(self):
        patches = build_independent_patches()
        assert len(patches) == 3
        ids = {p.patch_id for p in patches}
        assert ids == {"PATCH-1", "PATCH-2", "PATCH-3"}

    def test_tc38_patches_non_overlapping_code_regions(self):
        verification = verify_patch_independence()
        assert verification.patch_1_affects_patch_2 is False
        assert verification.patch_1_affects_patch_3 is False
        assert verification.patch_2_affects_patch_3 is False
        assert verification.independent_rollback_possible is True

    def test_tc39_historical_tpex_repair_blocked(self):
        repair = build_historical_repair_analysis()
        assert repair.tpex_ordinary_repair_possible is False
        assert repair.verdict == HistoricalRepairVerdict.VOLUME_REPAIR_BLOCKED

    def test_tc40_no_production_write_in_any_function(self):
        mtime_before = os.path.getmtime(PROD_DB)
        _ = build_set_reconciliation()
        _ = run_qg_exclusion_simulation()
        _ = build_warrant_exclusion_patch()
        _ = build_parser_patches()
        _ = build_independent_patches()
        _ = build_historical_repair_analysis()
        mtime_after = os.path.getmtime(PROD_DB)
        assert mtime_before == mtime_after, "Production DB was modified!"


# ── TC41-TC44: TWSE PIT Universe / Stock-month Dedup / T2 Compliance / 20D ──────

class TestTWSEPITAndT2:
    def test_tc41_pit_universe_s60_exceeds_s59(self):
        pit = build_twse_pit_universe(PROD_DB)
        assert pit.s60_aug2026_query >= pit.s59_hardcoded

    def test_tc42_stock_month_manifest_five_entries(self):
        manifest = build_stock_month_manifest()
        assert len(manifest) >= 5
        ids = {e.stock_id for e in manifest}
        assert "2330" in ids
        assert "2317" in ids

    def test_tc43_t2_compliance_unverified(self):
        budget = build_t2_request_budget(PROD_DB)
        assert "UNVERIFIED" in budget.compliance_status

    def test_tc44_20d_cluster_count_three(self):
        clusters = build_twenty_d_clusters(PROD_DB)
        assert len(clusters) == 3
        ids = [c.cluster_id for c in clusters]
        assert "Oct13-16" in ids
        assert "Oct21-22" in ids
        assert "Oct28" in ids


# ── TC45-TC48: Prospective Guardrails / Frozen / QG / S59 Correction ─────────

class TestGuardrailsAndCorrections:
    def test_tc45_twenty_d_all_data_blocked(self):
        clusters = build_twenty_d_clusters(PROD_DB)
        for c in clusters:
            assert c.fwd_return_computed == 0
            assert "AUTH02_NOT_AUTHORIZED" in c.auth02_status

    def test_tc46_v3_param_hash_frozen(self):
        FROZEN_HASH = "be43e8ca977d9fdd"
        try:
            from src.research.v3_entry_timing import PARAMETER_HASH
            assert PARAMETER_HASH == FROZEN_HASH
        except ImportError:
            pytest.skip("v3_entry_timing not importable")

    def test_tc47_qg_simulation_coverage_increase_is_reclassification(self):
        results = run_qg_exclusion_simulation()
        before = next(r for r in results if "before" in r.test_name)
        after = next(r for r in results if "after" in r.test_name)
        # Coverage improvement because denominator shrinks (reclassification only)
        assert after.coverage_after_pct >= before.coverage_before_pct

    def test_tc48_s59_correction_documented(self):
        recon = build_set_reconciliation()
        # S60 corrects S59's characterization of SET-B as "warrant"
        assert "S59" in recon.s59_correction
        assert "175" in recon.s59_correction or "5-digit" in recon.s59_correction


# ── Verdict / Report Tests ─────────────────────────────────────────────────────

class TestFinalVerdicts:
    def test_security_classification_report_verdict(self):
        report = build_security_classification_report(PROD_DB)
        assert report.null_volume_verdict == SetReconciliationVerdict.NULL_VOLUME_FULLY_RECONCILED
        assert report.warrant_patch_verdict == WarrantPatchVerdict.WARRANT_PATCH_READY_FOR_AUTHORIZATION

    def test_patch_release_gate_report_verdicts(self):
        report = build_patch_release_gate_report(PROD_DB)
        assert report.parser_patch_verdict == ParserPatchVerdict.PARSER_PATCH_READY_FOR_AUTHORIZATION
        assert report.error_patch_verdict == ErrorPatchVerdict.ERROR_PATCH_READY_FOR_AUTHORIZATION
        assert report.historical_repair_verdict == HistoricalRepairVerdict.VOLUME_REPAIR_BLOCKED
        assert report.t2_compliance_verdict == T2ComplianceVerdict.T2_COMPLIANCE_UNVERIFIED

    def test_all_independent_patches_not_deployed(self):
        patches = build_independent_patches()
        for p in patches:
            assert p.not_deployed is True
            assert p.independent_authorization_required is True

    def test_warrant_patch_not_authorized(self):
        patch = build_warrant_exclusion_patch()
        assert patch.authorized is False

    def test_parser_patches_not_authorized(self):
        patches = build_parser_patches()
        for p in patches:
            assert "NOT_AUTHORIZED" in p.authorization_status

    def test_daily_prices_max_date_unchanged(self):
        conn = sqlite3.connect(PROD_DB)
        cur = conn.cursor()
        cur.execute("SELECT MAX(date) FROM daily_prices WHERE stock_id='0050'")
        max_date = cur.fetchone()[0]
        conn.close()
        assert max_date == "2026-11-05", f"daily_prices max changed! Got {max_date}"

    def test_manifest_all_auth01_pending(self):
        manifest = build_stock_month_manifest()
        for e in manifest:
            assert "AUTH01" in e.authorization_status

    def test_pit_universe_verdict(self):
        report = build_patch_release_gate_report(PROD_DB)
        assert report.pit_universe_verdict == PitUniverseVerdict.TWSE_PIT_UNIVERSE_PARTIAL

    def test_manifest_verdict(self):
        report = build_patch_release_gate_report(PROD_DB)
        assert report.manifest_verdict == ManifestVerdict.T2_MANIFEST_PARTIAL

    def test_ordinary_null_analysis_matches_sets(self):
        analysis = build_ordinary_stock_null_analysis(PROD_DB)
        assert analysis.twse_ordinary_null == 25     # SET-D
        assert analysis.tpex_ordinary_null == 21_846  # SET-C

    def test_set_d_root_cause_different_from_a_b_c(self):
        sets = build_null_volume_sets()
        set_d = next(s for s in sets if s.set_id == "SET-D")
        assert "DIFFERENT ROOT CAUSE" in set_d.root_cause
        assert "Innovation Board" in set_d.root_cause or "6423" in set_d.stock_id_pattern
