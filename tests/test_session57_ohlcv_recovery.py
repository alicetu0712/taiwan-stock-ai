"""
Session 57 — OHLCV Source & Coverage Recovery Tests

40 test categories covering:
- Source contract definitions and classifications
- TPEx date mismatch root cause confirmation
- Data gap inventory classifications
- Root cause evidence ledger
- Recovery feasibility matrix
- Pipeline health check architecture
- Universe contamination report
- S50 data corrections (Nov03 close=245.5, Nov09 close=2235.0)
"""

from __future__ import annotations


from src.research.market_coverage_recovery_s57 import (
    AuthorizationStatus,
    GapClassification,
    RecoveryFeasibility,
    RecoveryTier,
    build_contamination_report,
    build_coverage_recovery_report,
    build_gap_inventory,
    build_pipeline_health_checks,
    build_recovery_feasibility_matrix,
    build_root_cause_ledger,
    compute_total_recovery_estimate,
)
from src.research.market_ohlcv_source_verification_s57 import (
    DateSemantics,
    HistoricalAvailability,
    OHLCVAvailability,
    SourceType,
    TPExSourceVerdict,
    TWSeSourceVerdict,
    analyze_tpex_date_mismatch,
    build_nov04_anomaly_report,
    build_ohlcv_source_report,
    build_source_contracts,
    build_twse_coverage_analysis,
    get_tpex_source_verdict,
    get_twse_source_verdict,
)


# ══════════════════════════════════════════════════════════════════════════════
# TC01 — Module Imports
# ══════════════════════════════════════════════════════════════════════════════

def test_TC01a_source_verification_module_importable():
    report = build_ohlcv_source_report()
    assert report is not None


def test_TC01b_coverage_recovery_module_importable():
    report = build_coverage_recovery_report()
    assert report is not None


# ══════════════════════════════════════════════════════════════════════════════
# TC02 — Source Contract Count
# ══════════════════════════════════════════════════════════════════════════════

def test_TC02a_source_contracts_count():
    contracts = build_source_contracts()
    assert len(contracts) == 5


def test_TC02b_source_contract_types_unique():
    contracts = build_source_contracts()
    types = [c.source_type for c in contracts]
    assert len(set(types)) == len(types), "Duplicate source types"


# ══════════════════════════════════════════════════════════════════════════════
# TC03 — TWSE Bulk Historical Contract
# ══════════════════════════════════════════════════════════════════════════════

def test_TC03a_twse_hist_url_historical_not_available():
    contracts = build_source_contracts()
    hist = next(c for c in contracts if c.source_type == SourceType.TWSE_BULK_HIST)
    assert hist.historical_availability == HistoricalAvailability.NOT_AVAILABLE


def test_TC03b_twse_hist_url_probe_evidence_contains_json_error():
    contracts = build_source_contracts()
    hist = next(c for c in contracts if c.source_type == SourceType.TWSE_BULK_HIST)
    assert "JSONDecodeError" in hist.probe_evidence or "Expecting value" in hist.probe_evidence


def test_TC03c_twse_hist_url_covers_twse_only():
    contracts = build_source_contracts()
    hist = next(c for c in contracts if c.source_type == SourceType.TWSE_BULK_HIST)
    assert hist.covers_twse is True
    assert hist.covers_tpex is False


# ══════════════════════════════════════════════════════════════════════════════
# TC04 — TWSE Bulk Latest Contract
# ══════════════════════════════════════════════════════════════════════════════

def test_TC04a_twse_latest_url_always_latest():
    contracts = build_source_contracts()
    latest = next(c for c in contracts if c.source_type == SourceType.TWSE_BULK_LATEST)
    assert latest.date_semantics == DateSemantics.ALWAYS_LATEST


def test_TC04b_twse_latest_url_latest_only():
    contracts = build_source_contracts()
    latest = next(c for c in contracts if c.source_type == SourceType.TWSE_BULK_LATEST)
    assert latest.historical_availability == HistoricalAvailability.LATEST_ONLY


def test_TC04c_twse_latest_url_full_ohlcv():
    contracts = build_source_contracts()
    latest = next(c for c in contracts if c.source_type == SourceType.TWSE_BULK_LATEST)
    assert latest.ohlcv_availability == OHLCVAvailability.FULL_OHLCV_WITH_VOLUME


def test_TC04d_twse_latest_url_stock_count():
    contracts = build_source_contracts()
    latest = next(c for c in contracts if c.source_type == SourceType.TWSE_BULK_LATEST)
    assert latest.typical_stock_count == 1241


# ══════════════════════════════════════════════════════════════════════════════
# TC05 — TWSE Single-Stock Contract
# ══════════════════════════════════════════════════════════════════════════════

def test_TC05a_twse_single_stock_historical_available():
    contracts = build_source_contracts()
    single = next(c for c in contracts if c.source_type == SourceType.TWSE_SINGLE_STOCK)
    assert single.historical_availability == HistoricalAvailability.AVAILABLE


def test_TC05b_twse_single_stock_honors_date():
    contracts = build_source_contracts()
    single = next(c for c in contracts if c.source_type == SourceType.TWSE_SINGLE_STOCK)
    assert single.date_semantics == DateSemantics.REQUESTED_DATE_HONORED


def test_TC05c_twse_single_stock_full_ohlcv():
    contracts = build_source_contracts()
    single = next(c for c in contracts if c.source_type == SourceType.TWSE_SINGLE_STOCK)
    assert single.ohlcv_availability == OHLCVAvailability.FULL_OHLCV_WITH_VOLUME


def test_TC05d_twse_single_stock_mentions_s50_verification():
    contracts = build_source_contracts()
    single = next(c for c in contracts if c.source_type == SourceType.TWSE_SINGLE_STOCK)
    assert "S50" in single.probe_evidence or "2330" in single.probe_evidence


# ══════════════════════════════════════════════════════════════════════════════
# TC06 — TPEx Bulk Contract
# ══════════════════════════════════════════════════════════════════════════════

def test_TC06a_tpex_bulk_date_param_ignored():
    contracts = build_source_contracts()
    tpex = next(c for c in contracts if c.source_type == SourceType.TPEX_BULK_HIST)
    assert tpex.date_semantics == DateSemantics.DATE_PARAM_IGNORED


def test_TC06b_tpex_bulk_latest_only():
    contracts = build_source_contracts()
    tpex = next(c for c in contracts if c.source_type == SourceType.TPEX_BULK_HIST)
    assert tpex.historical_availability == HistoricalAvailability.LATEST_ONLY


def test_TC06c_tpex_bulk_no_volume():
    contracts = build_source_contracts()
    tpex = next(c for c in contracts if c.source_type == SourceType.TPEX_BULK_HIST)
    assert tpex.ohlcv_availability == OHLCVAvailability.FULL_OHLCV_NO_VOLUME


def test_TC06d_tpex_bulk_stock_count():
    contracts = build_source_contracts()
    tpex = next(c for c in contracts if c.source_type == SourceType.TPEX_BULK_HIST)
    assert tpex.typical_stock_count == 5737


def test_TC06e_tpex_bulk_probe_evidence_mentions_mismatch():
    contracts = build_source_contracts()
    tpex = next(c for c in contracts if c.source_type == SourceType.TPEX_BULK_HIST)
    evidence = tpex.probe_evidence.lower()
    assert "2026-11-10" in tpex.probe_evidence
    assert "mismatch" in evidence or "ignored" in evidence or "1151029" in tpex.probe_evidence


# ══════════════════════════════════════════════════════════════════════════════
# TC07 — TPEx Date Mismatch Analysis
# ══════════════════════════════════════════════════════════════════════════════

def test_TC07a_tpex_mismatch_directly_confirmed():
    analysis = analyze_tpex_date_mismatch()
    assert analysis.confidence == "DIRECTLY_CONFIRMED"


def test_TC07b_tpex_mismatch_patch_impact_does_not_fix_data():
    analysis = analyze_tpex_date_mismatch()
    text = analysis.patch_impact.lower()
    assert "not fix" in text or "does not" in text or "cannot fix" in text


def test_TC07c_tpex_mismatch_implication_mentions_design():
    analysis = analyze_tpex_date_mismatch()
    text = analysis.implication.lower()
    assert "design" in text or "today" in text or "structural" in text.lower()


# ══════════════════════════════════════════════════════════════════════════════
# TC08 — Nov04 Anomaly Report
# ══════════════════════════════════════════════════════════════════════════════

def test_TC08a_nov04_total_rows():
    report = build_nov04_anomaly_report()
    assert report.total_rows == 6957


def test_TC08b_nov04_ordinary_rows():
    report = build_nov04_anomaly_report()
    assert report.ordinary_4d_1k_9k == 1969


def test_TC08c_nov04_warrant_rows():
    report = build_nov04_anomaly_report()
    assert report.warrants_7xx + report.warrants_02x == 4829


def test_TC08d_nov04_volume_null_rows():
    report = build_nov04_anomaly_report()
    assert report.volume_null_rows == 5715


def test_TC08e_nov04_etf_rows():
    report = build_nov04_anomaly_report()
    assert report.etf_00x == 159


def test_TC08f_nov04_root_cause_mentions_warrants():
    report = build_nov04_anomaly_report()
    text = report.root_cause.upper()
    assert "WARRANT" in text or "7XX" in text


# ══════════════════════════════════════════════════════════════════════════════
# TC09 — TWSE Verdict
# ══════════════════════════════════════════════════════════════════════════════

def test_TC09a_twse_verdict_partial():
    verdict = get_twse_source_verdict()
    assert verdict == TWSeSourceVerdict.TWSE_SOURCE_PARTIAL


def test_TC09b_tpex_verdict_not_feasible():
    verdict = get_tpex_source_verdict()
    assert verdict == TPExSourceVerdict.TPEX_SOURCE_NOT_FEASIBLE


# ══════════════════════════════════════════════════════════════════════════════
# TC10 — Gap Inventory Count and Classification
# ══════════════════════════════════════════════════════════════════════════════

def test_TC10a_gap_inventory_count():
    inventory = build_gap_inventory()
    assert len(inventory) == 13  # Oct08/15/19/20/27/29/30/Nov02/03/04/05/06/09


def test_TC10b_benchmark_only_dates():
    inventory = build_gap_inventory()
    benchmark_dates = [
        e.date for e in inventory
        if e.gap_classification == GapClassification.BENCHMARK_ONLY
    ]
    assert "2026-10-29" in benchmark_dates
    assert "2026-10-30" in benchmark_dates
    assert "2026-11-02" in benchmark_dates
    assert "2026-11-03" in benchmark_dates


def test_TC10c_date_missing_entries():
    inventory = build_gap_inventory()
    missing_dates = [
        e.date for e in inventory
        if e.gap_classification == GapClassification.DATE_MISSING
    ]
    assert "2026-11-06" in missing_dates
    assert "2026-11-09" in missing_dates


def test_TC10d_partial_coverage_entries():
    inventory = build_gap_inventory()
    partial_dates = [
        e.date for e in inventory
        if e.gap_classification == GapClassification.PARTIAL_COVERAGE
    ]
    assert "2026-11-04" in partial_dates
    assert "2026-11-05" in partial_dates


def test_TC10e_historical_backfill_entries():
    inventory = build_gap_inventory()
    hist_dates = [
        e.date for e in inventory
        if e.gap_classification == GapClassification.HISTORICAL_BACKFILL
    ]
    assert len(hist_dates) == 5
    assert "2026-10-08" in hist_dates


# ══════════════════════════════════════════════════════════════════════════════
# TC11 — S50 Record Corrections
# ══════════════════════════════════════════════════════════════════════════════

def test_TC11a_nov03_close_correction_245_5():
    inventory = build_gap_inventory()
    nov03 = next(e for e in inventory if e.date == "2026-11-03")
    assert "245.5" in nov03.notes, "Nov03 2317 close should be 245.5, not 245.0"


def test_TC11b_nov09_close_correction_2235():
    inventory = build_gap_inventory()
    nov09 = next(e for e in inventory if e.date == "2026-11-09")
    assert "2235" in nov09.notes, "Nov09 2330 close should be 2235.0, not 2200.0"


def test_TC11c_oct29_has_6_s50_records():
    inventory = build_gap_inventory()
    oct29 = next(e for e in inventory if e.date == "2026-10-29")
    assert oct29.s50_records_available == 6


# ══════════════════════════════════════════════════════════════════════════════
# TC12 — AUTH01 Authorization Status
# ══════════════════════════════════════════════════════════════════════════════

def test_TC12a_oct29_auth_pending():
    inventory = build_gap_inventory()
    entry = next(e for e in inventory if e.date == "2026-10-29")
    assert entry.authorization_status == AuthorizationStatus.PENDING


def test_TC12b_nov04_auth_not_requested():
    inventory = build_gap_inventory()
    entry = next(e for e in inventory if e.date == "2026-11-04")
    assert entry.authorization_status == AuthorizationStatus.NOT_REQUESTED


def test_TC12c_oct08_auth_not_requested():
    inventory = build_gap_inventory()
    entry = next(e for e in inventory if e.date == "2026-10-08")
    assert entry.authorization_status == AuthorizationStatus.NOT_REQUESTED


# ══════════════════════════════════════════════════════════════════════════════
# TC13 — Root Cause Ledger
# ══════════════════════════════════════════════════════════════════════════════

def test_TC13a_root_cause_count():
    ledger = build_root_cause_ledger()
    assert len(ledger) == 5


def test_TC13b_rc01_twse_hist_broken():
    ledger = build_root_cause_ledger()
    rc01 = next(rc for rc in ledger if rc.code == "RC-01")
    assert rc01.confidence == "DIRECTLY_CONFIRMED"
    assert "TWSE_HIST_URL" in rc01.hypothesis or "HIST_URL" in rc01.hypothesis


def test_TC13c_rc02_latest_url_rc02():
    ledger = build_root_cause_ledger()
    rc02 = next(rc for rc in ledger if rc.code == "RC-02")
    assert rc02.confidence == "DIRECTLY_CONFIRMED"
    assert "2026-11-09" in rc02.evidence_type


def test_TC13d_rc03_tpex_date_param_ignored():
    ledger = build_root_cause_ledger()
    rc03 = next(rc for rc in ledger if rc.code == "RC-03")
    assert rc03.confidence == "DIRECTLY_CONFIRMED"
    assert "1151029" in rc03.evidence_type or "DATE_PARAM_IGNORED" in rc03.hypothesis.upper()


def test_TC13e_rc04_scheduler_strongly_supported():
    ledger = build_root_cause_ledger()
    rc04 = next(rc for rc in ledger if rc.code == "RC-04")
    assert rc04.confidence == "STRONGLY_SUPPORTED"
    assert "SCHEDULER" in rc04.hypothesis.upper()


def test_TC13f_rc05_benchmark_only():
    ledger = build_root_cause_ledger()
    rc05 = next(rc for rc in ledger if rc.code == "RC-05")
    assert "BENCHMARK" in rc05.hypothesis.upper() or "0050" in rc05.hypothesis


# ══════════════════════════════════════════════════════════════════════════════
# TC14 — Recovery Feasibility Matrix
# ══════════════════════════════════════════════════════════════════════════════

def test_TC14a_recovery_matrix_covers_6_gap_dates():
    matrix = build_recovery_feasibility_matrix()
    dates = [r.date for r in matrix]
    assert "2026-10-29" in dates
    assert "2026-10-30" in dates
    assert "2026-11-02" in dates
    assert "2026-11-03" in dates
    assert "2026-11-06" in dates
    assert "2026-11-09" in dates
    assert len(dates) == 6


def test_TC14b_oct29_feasibility_verified():
    matrix = build_recovery_feasibility_matrix()
    oct29 = next(r for r in matrix if r.date == "2026-10-29")
    assert oct29.feasibility == RecoveryFeasibility.FEASIBLE_VERIFIED


def test_TC14c_nov06_feasibility_caution():
    matrix = build_recovery_feasibility_matrix()
    nov06 = next(r for r in matrix if r.date == "2026-11-06")
    assert nov06.feasibility == RecoveryFeasibility.FEASIBLE_WITH_CAUTION


def test_TC14d_all_tier2_recommendation():
    matrix = build_recovery_feasibility_matrix()
    for row in matrix:
        assert row.tier_recommendation == RecoveryTier.T2_TWSE_SINGLE_STOCK


def test_TC14e_request_count_per_date():
    matrix = build_recovery_feasibility_matrix()
    for row in matrix:
        assert row.request_count_estimate == 1969


# ══════════════════════════════════════════════════════════════════════════════
# TC15 — Recovery Time Estimate
# ══════════════════════════════════════════════════════════════════════════════

def test_TC15a_total_requests():
    matrix = build_recovery_feasibility_matrix()
    estimate = compute_total_recovery_estimate(matrix)
    assert estimate["total_requests"] == 6 * 1969  # 11814


def test_TC15b_total_hours_reasonable():
    matrix = build_recovery_feasibility_matrix()
    estimate = compute_total_recovery_estimate(matrix)
    # 6 dates × 1969 stocks × 2s / 3600 = ~6.56 hours
    assert 5.0 < estimate["total_hours"] < 10.0


def test_TC15c_risk_level_medium_high():
    matrix = build_recovery_feasibility_matrix()
    estimate = compute_total_recovery_estimate(matrix)
    assert "MEDIUM" in estimate["risk_level"].upper() or "HIGH" in estimate["risk_level"].upper()


def test_TC15d_recommendation_phased():
    matrix = build_recovery_feasibility_matrix()
    estimate = compute_total_recovery_estimate(matrix)
    assert "PHASED" in estimate["recommendation"].upper() or "PHASE" in estimate["recommendation"].upper()


# ══════════════════════════════════════════════════════════════════════════════
# TC16 — Pipeline Health Checks
# ══════════════════════════════════════════════════════════════════════════════

def test_TC16a_health_check_count():
    checks = build_pipeline_health_checks()
    assert len(checks) == 6


def test_TC16b_minimum_row_check_not_implemented():
    checks = build_pipeline_health_checks()
    hc01 = next(c for c in checks if c.check_id == "HC-01")
    assert hc01.currently_implemented is False


def test_TC16c_all_checks_not_implemented():
    checks = build_pipeline_health_checks()
    for check in checks:
        assert check.currently_implemented is False, f"{check.check_id} should not be implemented yet"


def test_TC16d_api_date_validation_check_exists():
    checks = build_pipeline_health_checks()
    ids = [c.check_id for c in checks]
    assert "HC-02" in ids


def test_TC16e_trading_day_calendar_check_exists():
    checks = build_pipeline_health_checks()
    hc05 = next(c for c in checks if c.check_id == "HC-05")
    assert "TaiwanTradingCalendar" in hc05.implementation_note or "calendar" in hc05.check_name.lower()


# ══════════════════════════════════════════════════════════════════════════════
# TC17 — Contamination Report
# ══════════════════════════════════════════════════════════════════════════════

def test_TC17a_contamination_total_rows():
    report = build_contamination_report()
    assert report.total_rows == 6957


def test_TC17b_contamination_pct_high():
    report = build_contamination_report()
    # (4816 + 13) / 6957 = 69.4%
    assert report.contamination_pct > 60.0


def test_TC17c_research_denominator():
    report = build_contamination_report()
    assert report.research_denominator == 1969


def test_TC17d_denominator_note_mentions_etf():
    report = build_contamination_report()
    note = report.research_denominator_note.upper()
    assert "ETF" in note or "ORDINARY" in note


# ══════════════════════════════════════════════════════════════════════════════
# TC18 — TWSE Coverage Analysis
# ══════════════════════════════════════════════════════════════════════════════

def test_TC18a_twse_coverage_has_three_approaches():
    analysis = build_twse_coverage_analysis()
    assert len(analysis) == 3


def test_TC18b_twse_hist_not_feasible():
    analysis = build_twse_coverage_analysis()
    hist = next(a for a in analysis if "HIST" in a.approach and "SINGLE" not in a.approach)
    assert "NOT_FEASIBLE" in hist.operational_feasibility.upper()


def test_TC18c_twse_single_stock_feasible_with_caution():
    analysis = build_twse_coverage_analysis()
    single = next(a for a in analysis if "SINGLE_STOCK" in a.approach)
    assert single.historical_works is True
    assert "FEASIBLE" in single.operational_feasibility.upper()


def test_TC18d_twse_latest_historical_not_feasible():
    analysis = build_twse_coverage_analysis()
    latest = next(a for a in analysis if "LATEST" in a.approach)
    assert latest.historical_works is False


# ══════════════════════════════════════════════════════════════════════════════
# TC19 — Full Report Consistency
# ══════════════════════════════════════════════════════════════════════════════

def test_TC19a_full_ohlcv_report_builds_without_error():
    report = build_ohlcv_source_report()
    assert report.twse_verdict == TWSeSourceVerdict.TWSE_SOURCE_PARTIAL
    assert report.tpex_verdict == TPExSourceVerdict.TPEX_SOURCE_NOT_FEASIBLE


def test_TC19b_full_coverage_report_builds_without_error():
    report = build_coverage_recovery_report()
    assert report.recovery_time_estimate is not None
    assert report.contamination_report is not None


def test_TC19c_gap_inventory_dates_sorted():
    inventory = build_gap_inventory()
    dates = [e.date for e in inventory]
    assert dates == sorted(dates), "Gap inventory should be in date order"


def test_TC19d_benchmark_only_dates_all_have_one_row():
    inventory = build_gap_inventory()
    benchmark_entries = [e for e in inventory if e.gap_classification == GapClassification.BENCHMARK_ONLY]
    for entry in benchmark_entries:
        assert entry.total_rows == 1, f"{entry.date} benchmark-only should have 1 row"


def test_TC19e_date_missing_entries_zero_rows():
    inventory = build_gap_inventory()
    missing_entries = [e for e in inventory if e.gap_classification == GapClassification.DATE_MISSING]
    for entry in missing_entries:
        assert entry.total_rows == 0, f"{entry.date} date-missing should have 0 rows"


def test_TC19f_nov04_nov05_have_rows():
    inventory = build_gap_inventory()
    nov04 = next(e for e in inventory if e.date == "2026-11-04")
    nov05 = next(e for e in inventory if e.date == "2026-11-05")
    assert nov04.total_rows == 6957
    assert nov05.total_rows == 6589


def test_TC19g_benchmark_only_dates_pit_universe_1969():
    inventory = build_gap_inventory()
    benchmark_entries = [e for e in inventory if e.gap_classification == GapClassification.BENCHMARK_ONLY]
    for entry in benchmark_entries:
        assert entry.pit_universe_estimate == 1969


def test_TC19h_tpex_verdict_not_feasible_in_full_report():
    report = build_ohlcv_source_report()
    assert report.tpex_verdict == TPExSourceVerdict.TPEX_SOURCE_NOT_FEASIBLE


def test_TC19i_audit_timestamp_present():
    report = build_coverage_recovery_report()
    assert report.audit_timestamp is not None
    assert len(report.audit_timestamp) > 0


def test_TC19j_root_cause_all_codes_unique():
    ledger = build_root_cause_ledger()
    codes = [rc.code for rc in ledger]
    assert len(codes) == len(set(codes))
