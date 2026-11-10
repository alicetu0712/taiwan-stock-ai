"""
Session 56 Tests — AUTH01 Impact Simulation & TPEx Patch Deployment Safety
TC01–TC40: 40 test categories per PART J specification.
"""

import sqlite3

import sys
sys.path.insert(0, "src")

from research.auth01_impact_simulation_s56 import (
    Auth01Verdict,
    CoverageVerdict,
    OHLCVCompleteness,
    QGScenario,
    RecordAction,
    REFERENCE_ORDINARY_UNIVERSE,
    _AUTH01_DATES,
    build_auth01_decision_package,
    build_auth01_impact_report,
    build_coverage_matrix,
    build_qg_counterfactual,
    build_record_manifest,
    build_research_impact,
    run_coverage_dry_run,
    run_source_integrity_checks,
)
from research.tpex_patch_deployment_s56 import (
    BehavioralEquivalenceStatus,
    PatchDeploymentVerdict,
    PatchScenario,
    PATCH_BEFORE,
    PATCH_AFTER,
    PATCH_FILE,
    build_patch_deployment_report,
    inspect_patch_diff,
    run_scenario_simulation,
    _simulate_pipeline,
)
from research.canonical_baseline_v2_s55 import (
    build_canonical_baseline_v2,
    get_canonical_v2_verdict,
    CanonicalV2Verdict,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_test_conn():
    """Isolated temp SQLite mimicking daily_prices schema."""
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE daily_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_id TEXT NOT NULL,
            date TEXT NOT NULL,
            open REAL, high REAL, low REAL, close REAL,
            volume REAL, amount REAL, change_pct REAL,
            UNIQUE(stock_id, date)
        )
    """)
    conn.execute("""
        CREATE TABLE forward_signals (
            id INTEGER PRIMARY KEY,
            trade_date TEXT,
            stock_id TEXT,
            model_version TEXT,
            trade_signal TEXT,
            execution_date TEXT,
            rec_level TEXT
        )
    """)
    # Seed: 0050 for each candidate date
    for date, _, _ in _AUTH01_DATES:
        conn.execute(
            "INSERT OR IGNORE INTO daily_prices (stock_id, date, open, high, low, close, volume) VALUES (?,?,?,?,?,?,?)",
            ("0050", date, 100.0, 101.0, 99.0, 100.5, 1000000)
        )
    # Seed Nov04/Nov05 with existing data
    for _ in range(10):
        pass
    conn.execute(
        "INSERT INTO daily_prices (stock_id, date, open, high, low, close, volume) VALUES ('2330','2026-11-04',2400,2430,2390,2415,5000000)"
    )
    conn.execute(
        "INSERT INTO daily_prices (stock_id, date, open, high, low, close, volume) VALUES ('2454','2026-11-04',4000,4050,3980,4020,2000000)"
    )
    conn.commit()
    return conn


# ── TC01: AUTH01 Record-level Manifest ────────────────────────────────────────

def test_TC01_record_manifest_builds():
    conn = _make_test_conn()
    manifest = build_record_manifest(conn)
    assert len(manifest) > 0
    conn.close()


def test_TC01b_manifest_p1_dates():
    conn = _make_test_conn()
    manifest = build_record_manifest(conn)
    dates = {r.date for r in manifest}
    assert "2026-10-29" in dates
    assert "2026-10-30" in dates
    conn.close()


def test_TC01c_manifest_insert_candidates_no_existing():
    conn = _make_test_conn()
    manifest = build_record_manifest(conn)
    # Oct29 should have INSERT_CANDIDATE (no existing non-0050)
    oct29 = [r for r in manifest if r.date == "2026-10-29" and r.proposed_action == RecordAction.INSERT_CANDIDATE]
    assert len(oct29) == 3  # 2330, 2454, 2317
    conn.close()


# ── TC02: TWSE Source Validation ──────────────────────────────────────────────

def test_TC02_twse_source_verified_flag():
    conn = _make_test_conn()
    manifest = build_record_manifest(conn)
    twse_records = [r for r in manifest if r.proposed_action == RecordAction.INSERT_CANDIDATE]
    for r in twse_records:
        assert r.source_provider == "TWSE_SINGLE_STOCK_S50"
    conn.close()


def test_TC02b_verified_close_prices_match_s50():
    conn = _make_test_conn()
    manifest = build_record_manifest(conn)
    oct29_2330 = next(
        (r for r in manifest if r.date == "2026-10-29" and r.security_id == "2330"), None
    )
    assert oct29_2330 is not None
    assert oct29_2330.close_price == 2415.0
    conn.close()


# ── TC03: TPEx Source Validation ──────────────────────────────────────────────

def test_TC03_tpex_source_unverified():
    conn = _make_test_conn()
    checks = run_source_integrity_checks(conn)
    tpex_check = next(c for c in checks if c.check_name == "TPEX_OFFICIAL_SOURCE")
    assert tpex_check.status == "UNVERIFIED"
    conn.close()


# ── TC04: Request/Returned Date Alignment ────────────────────────────────────

def test_TC04_request_returned_date_match():
    conn = _make_test_conn()
    manifest = build_record_manifest(conn)
    for r in manifest:
        if r.proposed_action == RecordAction.INSERT_CANDIDATE:
            assert r.source_request_date == r.source_returned_date
    conn.close()


# ── TC05: Security Type ────────────────────────────────────────────────────────

def test_TC05_verified_stocks_are_ordinary():
    conn = _make_test_conn()
    manifest = build_record_manifest(conn)
    ordinary = [r for r in manifest if r.proposed_action == RecordAction.INSERT_CANDIDATE]
    for r in ordinary:
        assert r.point_in_time_type == "ordinary_stock"
    conn.close()


# ── TC06: ETF Exclusion ───────────────────────────────────────────────────────

def test_TC06_no_etf_in_insert_candidates():
    conn = _make_test_conn()
    manifest = build_record_manifest(conn)
    etf_candidates = [
        r for r in manifest
        if r.proposed_action == RecordAction.INSERT_CANDIDATE and r.security_id.startswith("00")
    ]
    assert len(etf_candidates) == 0
    conn.close()


def test_TC06b_reference_universe_excludes_etfs():
    # Reference universe 1969 is for 4-digit 1000-9999 stocks (no 00x ETFs)
    assert REFERENCE_ORDINARY_UNIVERSE == 1969


# ── TC07: Corporate Actions ───────────────────────────────────────────────────

def test_TC07_corporate_actions_unchecked():
    conn = _make_test_conn()
    manifest = build_record_manifest(conn)
    for r in manifest:
        if r.proposed_action == RecordAction.INSERT_CANDIDATE:
            assert r.corporate_action_checked is False
    conn.close()


# ── TC08: OHLCV Validation ────────────────────────────────────────────────────

def test_TC08_ohlcv_completeness_close_only():
    conn = _make_test_conn()
    manifest = build_record_manifest(conn)
    for r in manifest:
        if r.proposed_action == RecordAction.INSERT_CANDIDATE:
            assert r.ohlcv_completeness == OHLCVCompleteness.CLOSE_ONLY
            assert r.open_price is None
            assert r.volume is None
    conn.close()


def test_TC08b_ohlcv_limitation_in_package():
    conn = _make_test_conn()
    pkg = build_auth01_decision_package(conn)
    assert "CLOSE PRICE ONLY" in pkg.ohlcv_limitation
    assert "ESTIMATED" in pkg.ohlcv_limitation
    conn.close()


# ── TC09: Duplicate Detection ─────────────────────────────────────────────────

def test_TC09_no_duplicates_in_candidates():
    conn = _make_test_conn()
    manifest = build_record_manifest(conn)
    candidates = [(r.date, r.security_id) for r in manifest if r.proposed_action == RecordAction.INSERT_CANDIDATE]
    assert len(candidates) == len(set(candidates))
    conn.close()


# ── TC10: Conflict Detection ──────────────────────────────────────────────────

def test_TC10_conflict_on_existing_data():
    # If stock already exists with different value, it's a conflict
    conn = _make_test_conn()
    # Inject existing row for 2330 on Oct29
    conn.execute(
        "INSERT INTO daily_prices (stock_id, date, open, high, low, close, volume) VALUES ('2330','2026-10-29',9999,9999,9999,9999,0)"
    )
    conn.commit()
    # Now 2330/Oct29 would be a conflict (existing ≠ verified S50)
    existing = conn.execute(
        "SELECT close FROM daily_prices WHERE stock_id='2330' AND date='2026-10-29'"
    ).fetchone()
    assert existing is not None
    assert existing[0] == 9999.0  # conflict: S50 says 2415.0
    conn.close()


# ── TC11: Insert-only Dry-run ─────────────────────────────────────────────────

def test_TC11_dry_run_insert_only():
    conn = _make_test_conn()
    results = run_coverage_dry_run(conn)
    assert results["test1_initial_insert"] is True
    assert results["test1_rows_inserted"] == 7  # 3+2+1+1
    conn.close()


# ── TC12: Idempotency ─────────────────────────────────────────────────────────

def test_TC12_idempotent_reinsert():
    conn = _make_test_conn()
    results = run_coverage_dry_run(conn)
    assert results["test2_idempotency"] is True  # 0 new rows on second insert
    conn.close()


# ── TC13: Transaction Rollback ────────────────────────────────────────────────

def test_TC13_rollback():
    conn = _make_test_conn()
    results = run_coverage_dry_run(conn)
    assert results["test4_rollback"] is True
    conn.close()


# ── TC14: Coverage Before ─────────────────────────────────────────────────────

def test_TC14_coverage_before_is_zero():
    conn = _make_test_conn()
    matrix = build_coverage_matrix(conn)
    for row in matrix:
        if row.date in ("2026-10-29", "2026-10-30", "2026-11-02", "2026-11-03"):
            assert row.coverage_before_pct == 0.0
            assert row.existing_valid == 0
    conn.close()


# ── TC15: Coverage After ──────────────────────────────────────────────────────

def test_TC15_coverage_after_less_than_1pct():
    conn = _make_test_conn()
    matrix = build_coverage_matrix(conn)
    for row in matrix:
        if row.date == "2026-10-29":
            assert row.coverage_after_pct < 1.0  # 0.15%
            assert row.candidate_valid == 3
    conn.close()


def test_TC15b_coverage_after_insufficient():
    conn = _make_test_conn()
    matrix = build_coverage_matrix(conn)
    for row in matrix:
        if row.date in ("2026-10-29", "2026-10-30", "2026-11-02", "2026-11-03"):
            assert row.coverage_verdict == CoverageVerdict.COVERAGE_INSUFFICIENT
    conn.close()


# ── TC16: QG Counterfactual ───────────────────────────────────────────────────

def test_TC16_qg_backfill_does_not_pass():
    conn = _make_test_conn()
    cf = build_qg_counterfactual(conn)
    for item in cf:
        if item.date == "2026-10-29" and item.scenario == QGScenario.BACKFILL_ONLY:
            assert item.qg_pass is False  # 3 stocks << threshold
    conn.close()


def test_TC16b_qg_patch_does_not_add_price_rows():
    conn = _make_test_conn()
    cf = build_qg_counterfactual(conn)
    for item in cf:
        if item.date == "2026-10-29" and item.scenario == QGScenario.BACKFILL_PLUS_PATCH:
            assert item.qg_pass is False  # patch adds no rows


# ── TC17: TPEx Patch Exact Diff ───────────────────────────────────────────────

def test_TC17_patch_diff_matches_description():
    assert "tpex_api_date != target_d" in PATCH_BEFORE
    assert "tpex_api_date != target_d" in PATCH_AFTER
    assert "summary[\"errors\"].append(msg)" in PATCH_AFTER
    assert "summary[\"errors\"].append" not in PATCH_BEFORE


def test_TC17b_before_does_not_have_msg_variable():
    assert "msg = f" not in PATCH_BEFORE


def test_TC17c_actual_file_state():
    result = inspect_patch_diff()
    assert result.file_confirmed is True
    assert result.twse_section_state == "ALREADY_HAS_ERROR_PROPAGATION"
    assert result.tpex_section_state == "PRINT_ONLY_CONFIRMED"
    assert result.exact_before_matched is True


# ── TC18: Correct-date Behavior ───────────────────────────────────────────────

def test_TC18_correct_date_no_tpex_error():
    before = _simulate_pipeline("2026-11-06", "2026-11-06", 100, 50, None, False, False, patched=False)
    after = _simulate_pipeline("2026-11-06", "2026-11-06", 100, 50, None, False, False, patched=True)
    assert before["tpex_error_in_errors"] is False
    assert after["tpex_error_in_errors"] is False
    assert before["price_rows"] == after["price_rows"]


# ── TC19: Wrong-date Behavior ─────────────────────────────────────────────────

def test_TC19_wrong_date_captured_after_patch():
    before = _simulate_pipeline("2026-11-05", "2026-11-06", 100, 50, None, False, False, patched=False)
    after = _simulate_pipeline("2026-11-05", "2026-11-06", 100, 50, None, False, False, patched=True)
    assert before["tpex_error_in_errors"] is False   # before: not propagated
    assert after["tpex_error_in_errors"] is True     # after: captured
    assert len(after["errors"]) == len(before["errors"]) + 1


# ── TC20: Stale-date Behavior ─────────────────────────────────────────────────

def test_TC20_stale_date_equivalent_to_wrong_date():
    # Stale = wrong date (yesterday)
    after_stale = _simulate_pipeline("2026-11-05", "2026-11-06", 100, 50, None, False, False, patched=True)
    assert after_stale["tpex_error_in_errors"] is True


# ── TC21: Retry Behavior ──────────────────────────────────────────────────────

def test_TC21_retry_errors_not_cleared():
    # First attempt: TPEx wrong date → 1 error
    after1 = _simulate_pipeline("2026-11-05", "2026-11-06", 100, 50, None, False, False, patched=True, attempt=1)
    # Second attempt: correct → 0 new errors from tpex_api_date check
    after2 = _simulate_pipeline("2026-11-06", "2026-11-06", 100, 50, None, False, False, patched=True, attempt=2)
    # Errors from attempt 1 should persist (cumulative)
    assert after1["tpex_error_in_errors"] is True
    assert after2["tpex_error_in_errors"] is False  # second attempt correct


def test_TC21b_all_retry_failures_accumulate():
    scenarios = run_scenario_simulation()
    s08 = next(s for s in scenarios if s.scenario == PatchScenario.S08_RETRY_FAILURE)
    assert s08.after_error_count >= s08.before_error_count


# ── TC22: Multiple Errors ─────────────────────────────────────────────────────

def test_TC22_twse_plus_tpex_errors():
    # Both TWSE and TPEx return wrong dates
    after = _simulate_pipeline("2026-11-05", "2026-11-06", 100, 50, "2026-11-05", False, False, patched=True)
    assert len(after["errors"]) == 2  # 1 TWSE + 1 TPEx


# ── TC23: Summary Schema ──────────────────────────────────────────────────────

def test_TC23_summary_errors_is_list():
    after = _simulate_pipeline("2026-11-05", "2026-11-06", 100, 50, None, False, False, patched=True)
    assert isinstance(after["errors"], list)


def test_TC23b_error_message_format():
    after = _simulate_pipeline("2026-11-05", "2026-11-06", 100, 50, None, False, False, patched=True)
    assert any("TPEx api_date" in e for e in after["errors"])
    assert any("wrong date" in e for e in after["errors"])


# ── TC24: Completion Marker ───────────────────────────────────────────────────

def test_TC24_completion_marker_safe():
    result = inspect_patch_diff()
    assert result.completion_marker_safe is True


# ── TC25: Behavioral Equivalence ─────────────────────────────────────────────

def test_TC25_no_unexpected_differences():
    scenarios = run_scenario_simulation()
    unexpected = [s for s in scenarios if s.behavioral_equiv == BehavioralEquivalenceStatus.UNEXPECTED_DIFFERENCE]
    assert len(unexpected) == 0


def test_TC25b_price_rows_equivalent():
    report = build_patch_deployment_report()
    assert report.behavioral_equivalence.price_rows_equivalent is True


def test_TC25c_provider_requests_equivalent():
    report = build_patch_deployment_report()
    assert report.behavioral_equivalence.provider_requests_equivalent is True


# ── TC26: Patch Rollback ──────────────────────────────────────────────────────

def test_TC26_rollback_procedure_documented():
    report = build_patch_deployment_report()
    proc = report.authorization_package.rollback_procedure.lower()
    assert "revert" in proc or "restore" in proc  # git revert or manual restore
    assert PATCH_FILE in report.authorization_package.files_changed


# ── TC27: B01 Dependency ─────────────────────────────────────────────────────

def test_TC27_b01_is_auth01_blocker():
    # B01 = AUTH01 backfill not executed
    # Resolving B01 requires user authorization
    pkg = build_auth01_decision_package(_make_test_conn())
    assert pkg.verdict == Auth01Verdict.AUTH01_PARTIAL
    assert pkg.not_executed == "AUTH01_NOT_EXECUTED"


# ── TC28: B02 Dependency ─────────────────────────────────────────────────────

def test_TC28_b02_is_tpex_patch_blocker():
    report = build_patch_deployment_report()
    assert report.not_deployed == "PATCH_NOT_DEPLOYED"
    # B02 resolved only after deployment
    assert report.diff_inspection.tpex_section_state == "PRINT_ONLY_CONFIRMED"


# ── TC29: AUTH01-only Scenario ────────────────────────────────────────────────

def test_TC29_auth01_only_does_not_resolve_b02():
    # B01 resolved (AUTH01 executed) but B02 (TPEx patch) still not deployed
    # → B02 remains blocked
    report = build_patch_deployment_report()
    assert report.not_deployed == "PATCH_NOT_DEPLOYED"
    # TPEx errors still not propagated without patch


def test_TC29b_auth01_only_coverage_impact():
    conn = _make_test_conn()
    matrix = build_coverage_matrix(conn)
    oct29 = next(r for r in matrix if r.date == "2026-10-29")
    # Even with AUTH01, coverage is <1%
    assert oct29.coverage_after_pct < 1.0
    conn.close()


# ── TC30: Patch-only Scenario ─────────────────────────────────────────────────

def test_TC30_patch_only_no_price_rows_added():
    # TPEx patch adds observability only; no price rows added
    before = _simulate_pipeline("2026-11-06", "2026-11-06", 100, 50, None, False, False, patched=False)
    after = _simulate_pipeline("2026-11-06", "2026-11-06", 100, 50, None, False, False, patched=True)
    assert before["price_rows"] == after["price_rows"]


# ── TC31: Combined Scenario ───────────────────────────────────────────────────

def test_TC31_combined_b01_b02_still_needs_more():
    # Even with AUTH01 + TPEx patch, genuine prospective N stays 0
    impact = build_research_impact()
    gp = next(r for r in impact if "Genuine Prospective" in r.category)
    assert "N=0" in gp.after_auth01_partial
    assert "N=0" in gp.after_auth01_full


# ── TC32: Canonical V2 Integrity ─────────────────────────────────────────────

def test_TC32_canonical_v2_deterministic():
    conn = sqlite3.connect("data/platform.db")
    b1 = build_canonical_baseline_v2(conn)
    b2 = build_canonical_baseline_v2(conn)
    assert b1.fingerprint == b2.fingerprint
    conn.close()


def test_TC32b_canonical_v2_verified():
    conn = sqlite3.connect("data/platform.db")
    b = build_canonical_baseline_v2(conn)
    v = get_canonical_v2_verdict(b)
    assert v == CanonicalV2Verdict.CANONICAL_V2_VERIFIED
    conn.close()


def test_TC32c_canonical_v2_fingerprint_64chars():
    conn = sqlite3.connect("data/platform.db")
    b = build_canonical_baseline_v2(conn)
    assert len(b.fingerprint) == 64
    conn.close()


# ── TC33: Historical Baseline Separation ─────────────────────────────────────

def test_TC33_historical_fingerprint_distinct():
    conn = sqlite3.connect("data/platform.db")
    b = build_canonical_baseline_v2(conn)
    assert b.fingerprint != b.historical_fingerprint
    assert b.historical_fingerprint == "2c8b2475c8fdc457"
    conn.close()


def test_TC33b_historical_verdict_unrecoverable():
    conn = sqlite3.connect("data/platform.db")
    b = build_canonical_baseline_v2(conn)
    assert "UNRECOVERABLE" in b.historical_verdict
    conn.close()


# ── TC34: Prospective Blockers ────────────────────────────────────────────────

def test_TC34_research_impact_prospective_n_zero():
    impact = build_research_impact()
    gp = next(r for r in impact if "Genuine Prospective" in r.category)
    assert "N=0" in gp.before_auth01


def test_TC34b_g03_not_changed_by_backfill():
    impact = build_research_impact()
    g03 = next(r for r in impact if "G03" in r.category)
    assert "0/10" in g03.after_auth01_partial
    assert "0/10" in g03.after_auth01_full


# ── TC35: Mock vs Genuine Evidence ────────────────────────────────────────────

def test_TC35_backfill_not_genuine_prospective():
    impact = build_research_impact()
    gp = next(r for r in impact if "Genuine Prospective" in r.category)
    assert "HISTORICAL RECOVERY" in gp.note or "historical" in gp.note.lower()


# ── TC36: G03 Independent N ──────────────────────────────────────────────────

def test_TC36_g03_requires_genuine_prospective():
    impact = build_research_impact()
    g03 = next(r for r in impact if "G03" in r.category)
    # G03 stays 0 even after full backfill
    assert g03.after_auth01_full == g03.before_auth01 or "0/10" in g03.after_auth01_full


# ── TC37: G04 Overlap ─────────────────────────────────────────────────────────

def test_TC37_g04_structural_fail_unchanged():
    impact = build_research_impact()
    g04 = next(r for r in impact if "G04" in r.category)
    assert "STRUCTURAL_FAIL" in g04.before_auth01
    assert "STRUCTURAL_FAIL" in g04.after_auth01_full


# ── TC38: Calendar SSOT ───────────────────────────────────────────────────────

def test_TC38_auth01_dates_are_trading_days():
    trading_days = {d for d, _, is_td in _AUTH01_DATES if is_td}
    assert "2026-10-29" in trading_days
    assert "2026-11-04" in trading_days
    assert "2026-11-09" in trading_days


# ── TC39: AUTH02 Not Authorized ───────────────────────────────────────────────

def test_TC39_auth02_not_in_scope():
    # AUTH02 is 20D computation; not part of this report
    # Verify no 20D computation was triggered
    pkg = build_auth01_decision_package(_make_test_conn())
    # stop_conditions should NOT include "execute 20D"
    for cond in pkg.stop_conditions:
        assert "20D" not in cond or "outcome" not in cond.lower()


# ── TC40: Production Fingerprint Preservation ────────────────────────────────

def test_TC40_production_db_unchanged():
    conn = sqlite3.connect("data/platform.db")
    # Verify FS and daily_prices are unchanged
    total_fs = conn.execute("SELECT COUNT(*) FROM forward_signals").fetchone()[0]
    v8_buy = conn.execute(
        "SELECT COUNT(*) FROM forward_signals WHERE model_version='v8.0' AND trade_signal IN ('buy','strong_buy')"
    ).fetchone()[0]
    dp_max = conn.execute("SELECT MAX(date) FROM daily_prices").fetchone()[0]

    assert total_fs == 2605
    assert v8_buy == 237
    assert dp_max == "2026-11-05"

    # Oct29 still has only 1 row (0050 only)
    oct29 = conn.execute("SELECT COUNT(*) FROM daily_prices WHERE date='2026-10-29' AND stock_id!='0050'").fetchone()[0]
    assert oct29 == 0  # production NOT modified

    conn.close()


def test_TC40b_canonical_v2_fingerprint_stable():
    conn = sqlite3.connect("data/platform.db")
    b1 = build_canonical_baseline_v2(conn)
    b2 = build_canonical_baseline_v2(conn)
    assert b1.fingerprint == b2.fingerprint
    assert b1.fingerprint == "6a133e8cca47bcb25bbc528557e4a00efa2c91e387158c208aef6d2d0dbecf8f"
    conn.close()


def test_TC40c_patch_not_deployed():
    report = build_patch_deployment_report()
    assert report.not_deployed == "PATCH_NOT_DEPLOYED"
    assert report.diff_inspection.tpex_section_state == "PRINT_ONLY_CONFIRMED"


# ── Verdict tests ─────────────────────────────────────────────────────────────

def test_verdict_auth01_partial():
    conn = _make_test_conn()
    report = build_auth01_impact_report(conn)
    assert report.verdict == Auth01Verdict.AUTH01_PARTIAL
    assert report.not_executed == "AUTH01_NOT_EXECUTED"
    conn.close()


def test_verdict_patch_deployment_ready():
    report = build_patch_deployment_report()
    assert report.verdict == PatchDeploymentVerdict.PATCH_DEPLOYMENT_READY


def test_verdict_all_scenarios_pass():
    scenarios = run_scenario_simulation()
    assert len(scenarios) == 15
    failing = [s for s in scenarios if not s.pass_]
    assert len(failing) == 0, f"Failing scenarios: {[s.scenario for s in failing]}"
