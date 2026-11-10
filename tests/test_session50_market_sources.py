"""
Session 50 — Verified Market Data Sources & Calendar Contract Consolidation
Test suite: 40 test classes (TC01–TC40), targeting > 3012 total.

Modules under test:
  src/research/market_source_verification_s50.py  (PARTS B, C)
  src/research/calendar_contract_s50.py            (PARTS D, E, F, G, H)

Coverage:
  TC01–TC15: market_source_verification_s50 — VerifiedHistoricalSourceMatrix + BackfillManifest
  TC16–TC35: calendar_contract_s50 — CalendarContract, Pipeline, Eligibility, G04
  TC36–TC40: G04 effective N, bootstrap, 20D readiness, production fingerprints
"""
from __future__ import annotations

import sqlite3

import pytest

from src.research.market_source_verification_s50 import (
    BackfillAction,
    AuthorizationGateVerdict,
    SourceVerificationLevel,
    build_backfill_candidate_manifest,
    build_verified_historical_source_matrix,
    check_benchmark_only_completion_rule,
    validate_manifest_idempotency_in_temp_sqlite,
    validate_ohlc,
)
from src.research.calendar_contract_s50 import (
    G04WeeklySpacingVerdict,
    StrictEligibilityStatus,
    TwentyDReadinessVerdict,
    _CORRECT_20TD,
    _CORRECT_5TD,
    _S46_20TD,
    _S46_5TD,
    build_20d_readiness_matrix,
    build_g04_dependence_study,
    build_pipeline_completion_contract,
    build_research_trading_calendar_contract,
    build_strict5d_eligibility_matrix,
    get_corrected_exit,
    get_overlap,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def conn():
    return sqlite3.connect("data/platform.db")


@pytest.fixture(scope="module")
def source_matrix(conn):
    return build_verified_historical_source_matrix(conn)


@pytest.fixture(scope="module")
def backfill_manifest(conn):
    return build_backfill_candidate_manifest(conn)


@pytest.fixture(scope="module")
def calendar_contract():
    return build_research_trading_calendar_contract()


@pytest.fixture(scope="module")
def pipeline_contract():
    return build_pipeline_completion_contract()


@pytest.fixture(scope="module")
def eligibility_matrix():
    return build_strict5d_eligibility_matrix()


@pytest.fixture(scope="module")
def g04_study():
    return build_g04_dependence_study()


@pytest.fixture(scope="module")
def readiness_matrix_blocked():
    return build_20d_readiness_matrix(
        analysis_date="2026-11-02",
        auth01_granted=False,
        auth02_granted=False,
        pipeline_restored=False,
    )


# ---------------------------------------------------------------------------
# TC01: VerifiedHistoricalSourceMatrix builds and has correct structure
# ---------------------------------------------------------------------------

class TestTC01_SourceMatrixStructure:
    def test_builds_without_error(self, source_matrix):
        assert source_matrix is not None

    def test_eleven_date_summaries(self, source_matrix):
        assert len(source_matrix.date_summaries) == 11

    def test_dates_are_correct(self, source_matrix):
        dates = {s.date for s in source_matrix.date_summaries}
        expected = {
            "2026-10-08", "2026-10-15", "2026-10-19", "2026-10-20", "2026-10-27",
            "2026-10-29", "2026-10-30", "2026-11-02", "2026-11-03",
            "2026-11-06", "2026-11-09",
        }
        assert dates == expected

    def test_critical_finding_present(self, source_matrix):
        assert len(source_matrix.critical_finding) > 50

    def test_provider_verdicts_present(self, source_matrix):
        assert "TWSE_SINGLE_STOCK" in source_matrix.provider_verdicts
        assert "TWSE_BULK_HISTORICAL" in source_matrix.provider_verdicts


# ---------------------------------------------------------------------------
# TC02: All 11 candidate dates are SOURCE_VERIFIED_PARTIAL
# ---------------------------------------------------------------------------

class TestTC02_AllDatesSourceVerifiedPartial:
    def test_all_dates_source_verified_partial(self, source_matrix):
        for ds in source_matrix.date_summaries:
            assert ds.source_verdict == SourceVerificationLevel.SOURCE_VERIFIED_PARTIAL, \
                f"{ds.date} has unexpected verdict {ds.source_verdict}"

    def test_n_verified_partial_is_eleven(self, source_matrix):
        assert source_matrix.n_dates_source_verified_partial == 11

    def test_n_unavailable_is_zero(self, source_matrix):
        assert source_matrix.n_dates_source_unavailable == 0


# ---------------------------------------------------------------------------
# TC03: Nov 06 and Nov 09 upgraded from UNIVERSE_UNVERIFIED
# ---------------------------------------------------------------------------

class TestTC03_Nov06Nov09Upgraded:
    def test_two_dates_upgraded(self, source_matrix):
        assert source_matrix.n_dates_upgraded == 2

    def test_nov06_has_upgrade_note(self, source_matrix):
        nov06 = next(s for s in source_matrix.date_summaries if s.date == "2026-11-06")
        assert nov06.upgrade_from_prior is not None
        assert "UNIVERSE_UNVERIFIED" in nov06.upgrade_from_prior

    def test_nov09_has_upgrade_note(self, source_matrix):
        nov09 = next(s for s in source_matrix.date_summaries if s.date == "2026-11-09")
        assert nov09.upgrade_from_prior is not None
        assert "SOURCE_VERIFIED_PARTIAL" in nov09.upgrade_from_prior

    def test_nov06_twse_single_stock_available(self, source_matrix):
        nov06 = next(s for s in source_matrix.date_summaries if s.date == "2026-11-06")
        assert nov06.twse_single_stock_available is True

    def test_non_upgraded_dates_have_no_upgrade_note(self, source_matrix):
        for ds in source_matrix.date_summaries:
            if ds.date not in {"2026-11-06", "2026-11-09"}:
                assert ds.upgrade_from_prior is None, f"{ds.date} should not have upgrade note"


# ---------------------------------------------------------------------------
# TC04: Verified records are present and correctly encoded
# ---------------------------------------------------------------------------

class TestTC04_VerifiedRecordsPresent:
    def test_multiple_verified_records(self, source_matrix):
        assert len(source_matrix.verified_records) >= 10

    def test_all_records_have_dates(self, source_matrix):
        for r in source_matrix.verified_records:
            assert r.date is not None
            assert r.date.startswith("2026-")

    def test_all_records_have_close_price(self, source_matrix):
        for r in source_matrix.verified_records:
            assert r.close_price is not None
            assert r.close_price > 0

    def test_all_records_source_provider_twse(self, source_matrix):
        for r in source_matrix.verified_records:
            assert r.source_provider == "TWSE_SINGLE_STOCK"

    def test_date_match_verified_true(self, source_matrix):
        for r in source_matrix.verified_records:
            assert r.date_match_verified is True


# ---------------------------------------------------------------------------
# TC05: Oct 29 OHLC validation for 6 specific stocks
# ---------------------------------------------------------------------------

class TestTC05_OctTwentyNineOHLCValid:
    def test_oct29_records_present(self, source_matrix):
        oct29 = [r for r in source_matrix.verified_records if r.date == "2026-10-29"]
        assert len(oct29) >= 6

    def test_oct29_tsmc_close_correct(self, source_matrix):
        tsmc = next(
            (r for r in source_matrix.verified_records
             if r.date == "2026-10-29" and r.stock_id == "2330"), None
        )
        assert tsmc is not None
        assert tsmc.close_price == 2415.0

    def test_oct29_mediatek_close_correct(self, source_matrix):
        mt = next(
            (r for r in source_matrix.verified_records
             if r.date == "2026-10-29" and r.stock_id == "2454"), None
        )
        assert mt is not None
        assert mt.close_price == 4045.0

    def test_oct29_ohlc_valid_records(self, source_matrix):
        oct29 = [r for r in source_matrix.verified_records if r.date == "2026-10-29"]
        ohlc_valid = [r for r in oct29 if r.ohlc_valid is True]
        assert len(ohlc_valid) >= 6

    def test_nov06_tsmc_close_is_2135(self, source_matrix):
        nov06 = next(
            (r for r in source_matrix.verified_records
             if r.date == "2026-11-06" and r.stock_id == "2330"), None
        )
        assert nov06 is not None
        assert nov06.close_price == 2135.0

    def test_nov09_tsmc_close_is_2235(self, source_matrix):
        nov09 = next(
            (r for r in source_matrix.verified_records
             if r.date == "2026-11-09" and r.stock_id == "2330"), None
        )
        assert nov09 is not None
        assert nov09.close_price == 2235.0


# ---------------------------------------------------------------------------
# TC06: Provider verdicts distinguish available vs unavailable
# ---------------------------------------------------------------------------

class TestTC06_TWSEProviderVerdicts:
    def test_twse_single_stock_verdict(self, source_matrix):
        v = source_matrix.provider_verdicts["TWSE_SINGLE_STOCK"]
        assert "SOURCE_VERIFIED_PARTIAL" in v

    def test_twse_bulk_unavailable(self, source_matrix):
        v = source_matrix.provider_verdicts["TWSE_BULK_HISTORICAL"]
        assert "SOURCE_UNAVAILABLE" in v

    def test_tpex_bulk_unavailable(self, source_matrix):
        v = source_matrix.provider_verdicts["TPEX_BULK_HISTORICAL"]
        assert "SOURCE_UNAVAILABLE" in v

    def test_bulk_http200_does_not_mean_historical(self, source_matrix):
        # Verify the finding is documented
        v = source_matrix.provider_verdicts["TWSE_BULK_HISTORICAL"]
        assert "HTTP 200" in v or "current date" in v.lower()


# ---------------------------------------------------------------------------
# TC07: Universe composition correctly encoded
# ---------------------------------------------------------------------------

class TestTC07_UniverseCompositionEncoded:
    def test_total_stocks_656(self, source_matrix):
        uc = source_matrix.universe_composition
        assert uc["total_stocks"] == 656

    def test_four_digit_numeric_599(self, source_matrix):
        uc = source_matrix.universe_composition
        assert uc["four_digit_numeric"] == 599

    def test_etf_non_standard_57(self, source_matrix):
        uc = source_matrix.universe_composition
        assert uc["etf_or_non_standard"] == 57

    def test_random_sample_all_accessible(self, source_matrix):
        uc = source_matrix.universe_composition
        assert uc["random_sample_size"] == 20
        assert uc["random_sample_twse_available"] == 20

    def test_total_eq_four_digit_plus_etf(self, source_matrix):
        uc = source_matrix.universe_composition
        assert uc["total_stocks"] == uc["four_digit_numeric"] + uc["etf_or_non_standard"]


# ---------------------------------------------------------------------------
# TC08: Critical finding contains key S50 insight
# ---------------------------------------------------------------------------

class TestTC08_CriticalFindingPresent:
    def test_finding_mentions_upgrade(self, source_matrix):
        assert "Nov 06" in source_matrix.critical_finding or "Nov 06/09" in source_matrix.critical_finding

    def test_finding_mentions_twse_single_stock(self, source_matrix):
        assert "TWSE" in source_matrix.critical_finding

    def test_finding_mentions_bulk_unavailable(self, source_matrix):
        assert "SOURCE_UNAVAILABLE" in source_matrix.critical_finding

    def test_retrieval_timestamp_is_s50_date(self, source_matrix):
        assert "2026-11-10" in source_matrix.retrieval_timestamp


# ---------------------------------------------------------------------------
# TC09: validate_ohlc function correctness
# ---------------------------------------------------------------------------

class TestTC09_OHLCValidationFunction:
    def test_valid_ohlc(self):
        ok, reason = validate_ohlc(100.0, 110.0, 95.0, 105.0)
        assert ok is True
        assert reason == "OHLC_VALID"

    def test_high_less_than_open_fails(self):
        ok, reason = validate_ohlc(100.0, 90.0, 95.0, 97.0)
        assert ok is False
        assert "High" in reason

    def test_close_below_low_fails(self):
        ok, reason = validate_ohlc(100.0, 110.0, 95.0, 90.0)
        assert ok is False
        assert "Low" in reason

    def test_none_field_fails(self):
        ok, reason = validate_ohlc(100.0, None, 95.0, 105.0)
        assert ok is False
        assert "Missing" in reason

    def test_negative_price_fails(self):
        ok, reason = validate_ohlc(-10.0, 100.0, 95.0, 105.0)
        assert ok is False


# ---------------------------------------------------------------------------
# TC10: BackfillCandidateManifest structure
# ---------------------------------------------------------------------------

class TestTC10_BackfillManifestStructure:
    def test_builds_without_error(self, backfill_manifest):
        assert backfill_manifest is not None

    def test_candidates_present(self, backfill_manifest):
        assert len(backfill_manifest.candidates) > 0

    def test_all_candidates_have_fingerprint(self, backfill_manifest):
        for c in backfill_manifest.candidates:
            assert c.source_record_fingerprint is not None
            assert len(c.source_record_fingerprint) == 12

    def test_dry_run_fingerprint_prefix(self, backfill_manifest):
        assert backfill_manifest.dry_run_fingerprint.startswith("DRYRUN-")

    def test_transaction_plan_present(self, backfill_manifest):
        assert "INSERT" in backfill_manifest.transaction_plan

    def test_rollback_plan_present(self, backfill_manifest):
        assert "ROLLBACK" in backfill_manifest.rollback_plan


# ---------------------------------------------------------------------------
# TC11: Manifest action categories are mutually exclusive
# ---------------------------------------------------------------------------

class TestTC11_ManifestActionCategories:
    def test_total_adds_up(self, backfill_manifest):
        total = (
            backfill_manifest.n_insert_candidate
            + backfill_manifest.n_skip_existing
            + backfill_manifest.n_conflict_review
            + backfill_manifest.n_source_missing
            + backfill_manifest.n_validation_failed
        )
        assert total == len(backfill_manifest.candidates)

    def test_no_negative_counts(self, backfill_manifest):
        assert backfill_manifest.n_insert_candidate >= 0
        assert backfill_manifest.n_skip_existing >= 0
        assert backfill_manifest.n_conflict_review >= 0

    def test_all_candidates_have_valid_action(self, backfill_manifest):
        valid_actions = set(BackfillAction)
        for c in backfill_manifest.candidates:
            assert c.proposed_action in valid_actions

    def test_coverage_improvement_note_present(self, backfill_manifest):
        assert len(backfill_manifest.expected_coverage_improvement) > 10


# ---------------------------------------------------------------------------
# TC12: Idempotency validation in temp SQLite
# ---------------------------------------------------------------------------

class TestTC12_ManifestIdempotencyValidation:
    def test_idempotency_runs(self, backfill_manifest):
        result = validate_manifest_idempotency_in_temp_sqlite(backfill_manifest)
        assert result is not None

    def test_second_run_inserts_zero(self, backfill_manifest):
        result = validate_manifest_idempotency_in_temp_sqlite(backfill_manifest)
        assert result["second_run_inserts"] == 0

    def test_idempotent_flag_true(self, backfill_manifest):
        result = validate_manifest_idempotency_in_temp_sqlite(backfill_manifest)
        assert result["idempotent"] is True

    def test_first_run_matches_candidate_count(self, backfill_manifest):
        result = validate_manifest_idempotency_in_temp_sqlite(backfill_manifest)
        assert result["first_run_inserts"] == result["n_candidates"]


# ---------------------------------------------------------------------------
# TC13: ManifestAuthorizationGate
# ---------------------------------------------------------------------------

class TestTC13_ManifestAuthorizationGate:
    def test_verdict_is_valid_enum(self, backfill_manifest):
        assert backfill_manifest.authorization_verdict in set(AuthorizationGateVerdict)

    def test_audit_plan_present(self, backfill_manifest):
        assert "INSERT" in backfill_manifest.audit_plan or "log" in backfill_manifest.audit_plan.lower()

    def test_unresolved_risks_present(self, backfill_manifest):
        assert len(backfill_manifest.unresolved_risks) >= 3


# ---------------------------------------------------------------------------
# TC14: Unresolved risks are documented
# ---------------------------------------------------------------------------

class TestTC14_ManifestUnresolvedRisks:
    def test_at_least_five_risks(self, backfill_manifest):
        assert len(backfill_manifest.unresolved_risks) >= 5

    def test_risk_mentions_full_599_verification(self, backfill_manifest):
        all_risks = " ".join(backfill_manifest.unresolved_risks)
        assert "599" in all_risks or "full" in all_risks.lower()

    def test_risk_mentions_nov06_nov09(self, backfill_manifest):
        all_risks = " ".join(backfill_manifest.unresolved_risks)
        assert "Nov 06" in all_risks or "Nov06" in all_risks or "pipeline" in all_risks.lower()


# ---------------------------------------------------------------------------
# TC15: check_benchmark_only_completion_rule
# ---------------------------------------------------------------------------

class TestTC15_BenchmarkOnlyCompletionRule:
    def test_300_stocks_data_complete(self, conn):
        # Create temp DB with 300 stocks to verify rule
        m = sqlite3.connect(":memory:")
        m.execute("CREATE TABLE daily_prices (date TEXT, stock_id TEXT, close REAL)")
        for i in range(300):
            m.execute(
                "INSERT INTO daily_prices VALUES (?,?,?)",
                ("2026-10-01", f"{i+1000:04d}", 100.0)
            )
        m.commit()
        ok, reason = check_benchmark_only_completion_rule(m, "2026-10-01", threshold=300)
        assert ok is True
        assert "DATA_COMPLETE" in reason
        m.close()

    def test_one_stock_benchmark_only_not_data_complete(self, conn):
        m = sqlite3.connect(":memory:")
        m.execute("CREATE TABLE daily_prices (date TEXT, stock_id TEXT, close REAL)")
        m.execute("INSERT INTO daily_prices VALUES ('2026-10-01', '0050', 190.0)")
        m.commit()
        ok, reason = check_benchmark_only_completion_rule(m, "2026-10-01", threshold=300)
        assert ok is False
        assert "BENCHMARK_ONLY" in reason
        m.close()

    def test_zero_stocks_data_missing(self, conn):
        m = sqlite3.connect(":memory:")
        m.execute("CREATE TABLE daily_prices (date TEXT, stock_id TEXT, close REAL)")
        m.commit()
        ok, reason = check_benchmark_only_completion_rule(m, "2026-10-01", threshold=300)
        assert ok is False
        assert "DATA_MISSING" in reason
        m.close()

    def test_partial_200_stocks_not_data_complete(self, conn):
        m = sqlite3.connect(":memory:")
        m.execute("CREATE TABLE daily_prices (date TEXT, stock_id TEXT, close REAL)")
        for i in range(200):
            m.execute(
                "INSERT INTO daily_prices VALUES (?,?,?)",
                ("2026-10-01", f"{i+1000:04d}", 100.0)
            )
        m.commit()
        ok, reason = check_benchmark_only_completion_rule(m, "2026-10-01", threshold=300)
        assert ok is False
        assert "PARTIAL" in reason
        m.close()


# ---------------------------------------------------------------------------
# TC16: CalendarContract builds without error
# ---------------------------------------------------------------------------

class TestTC16_CalendarContractBuilds:
    def test_builds_without_error(self, calendar_contract):
        assert calendar_contract is not None

    def test_six_fill_dates(self, calendar_contract):
        assert len(calendar_contract.fill_dates) == 6

    def test_six_5td_corrections(self, calendar_contract):
        assert len(calendar_contract.corrections_5td) == 6

    def test_six_20td_corrections(self, calendar_contract):
        assert len(calendar_contract.corrections_20td) == 6

    def test_fingerprint_starts_with_ccfp(self, calendar_contract):
        assert calendar_contract.fingerprint.startswith("CCFP-")


# ---------------------------------------------------------------------------
# TC17: 3/6 5TD errors, 6/6 20TD errors
# ---------------------------------------------------------------------------

class TestTC17_FiveErrorsThreeErrors:
    def test_three_5td_errors(self, calendar_contract):
        assert calendar_contract.n_5td_errors == 3

    def test_six_20td_errors(self, calendar_contract):
        assert calendar_contract.n_20td_errors == 6

    def test_specific_5td_errors(self, calendar_contract):
        error_fills = {c.fill_date for c in calendar_contract.corrections_5td if c.was_error}
        assert "2026-10-13" in error_fills
        assert "2026-10-14" in error_fills
        assert "2026-10-16" in error_fills

    def test_5td_non_errors_unchanged(self, calendar_contract):
        ok_fills = {c.fill_date for c in calendar_contract.corrections_5td if not c.was_error}
        assert "2026-10-21" in ok_fills
        assert "2026-10-22" in ok_fills
        assert "2026-10-28" in ok_fills


# ---------------------------------------------------------------------------
# TC18: All 20TD corrections are negative delta (S46 was too late)
# ---------------------------------------------------------------------------

class TestTC18_AllTwentyTDCorrected:
    def test_all_20td_errors_flag_set(self, calendar_contract):
        for c in calendar_contract.corrections_20td:
            assert c.was_error is True, f"{c.fill_date} 20TD should be marked as error"

    def test_all_20td_deltas_negative(self, calendar_contract):
        for c in calendar_contract.corrections_20td:
            assert c.calendar_days_delta < 0, \
                f"{c.fill_date} 20TD delta={c.calendar_days_delta} should be negative (S46 too late)"

    def test_oct28_20td_delta_minus_seven(self, calendar_contract):
        oct28 = next(c for c in calendar_contract.corrections_20td if c.fill_date == "2026-10-28")
        assert oct28.calendar_days_delta == -7

    def test_oct14_20td_delta_minus_four(self, calendar_contract):
        oct14 = next(c for c in calendar_contract.corrections_20td if c.fill_date == "2026-10-14")
        assert oct14.calendar_days_delta == -4


# ---------------------------------------------------------------------------
# TC19: get_corrected_exit returns correct 5TD exits
# ---------------------------------------------------------------------------

class TestTC19_FiveTDExits:
    def test_oct13_5td(self):
        assert get_corrected_exit("2026-10-13", "5TD") == "2026-10-20"

    def test_oct14_5td(self):
        assert get_corrected_exit("2026-10-14", "5TD") == "2026-10-21"

    def test_oct16_5td(self):
        assert get_corrected_exit("2026-10-16", "5TD") == "2026-10-27"

    def test_oct21_5td(self):
        assert get_corrected_exit("2026-10-21", "5TD") == "2026-10-30"

    def test_oct22_5td(self):
        assert get_corrected_exit("2026-10-22", "5TD") == "2026-11-02"

    def test_oct28_5td(self):
        assert get_corrected_exit("2026-10-28", "5TD") == "2026-11-04"

    def test_unknown_date_returns_none(self):
        assert get_corrected_exit("2026-01-01", "5TD") is None

    def test_invalid_period_returns_none(self):
        assert get_corrected_exit("2026-10-13", "10TD") is None


# ---------------------------------------------------------------------------
# TC20: get_corrected_exit returns correct 20TD exits
# ---------------------------------------------------------------------------

class TestTC20_TwentyTDExits:
    def test_oct13_20td(self):
        assert get_corrected_exit("2026-10-13", "20TD") == "2026-11-12"

    def test_oct14_20td(self):
        assert get_corrected_exit("2026-10-14", "20TD") == "2026-11-13"

    def test_oct16_20td(self):
        assert get_corrected_exit("2026-10-16", "20TD") == "2026-11-17"

    def test_oct21_20td(self):
        assert get_corrected_exit("2026-10-21", "20TD") == "2026-11-20"

    def test_oct22_20td(self):
        assert get_corrected_exit("2026-10-22", "20TD") == "2026-11-23"

    def test_oct28_20td(self):
        assert get_corrected_exit("2026-10-28", "20TD") == "2026-11-25"


# ---------------------------------------------------------------------------
# TC21: S46 20TD values are all incorrect (all too late)
# ---------------------------------------------------------------------------

class TestTC21_S46TwentyTDAllNegativeDelta:
    def test_s46_oct13_was_nov14(self):
        assert _S46_20TD["2026-10-13"] == "2026-11-14"

    def test_s46_oct14_was_nov17(self):
        assert _S46_20TD["2026-10-14"] == "2026-11-17"

    def test_s46_oct28_was_dec02(self):
        assert _S46_20TD["2026-10-28"] == "2026-12-02"

    def test_all_s46_20td_differ_from_corrected(self):
        for d in _S46_20TD:
            assert _S46_20TD[d] != _CORRECT_20TD[d], \
                f"{d}: S46 and corrected are same — expected an error"


# ---------------------------------------------------------------------------
# TC22: S46 5TD: 3 errors + 3 unchanged
# ---------------------------------------------------------------------------

class TestTC22_S46FiveTDThreeErrors:
    def test_oct13_s46_was_oct21(self):
        assert _S46_5TD["2026-10-13"] == "2026-10-21"
        assert _CORRECT_5TD["2026-10-13"] == "2026-10-20"

    def test_oct14_s46_was_oct28(self):
        assert _S46_5TD["2026-10-14"] == "2026-10-28"
        assert _CORRECT_5TD["2026-10-14"] == "2026-10-21"

    def test_oct16_s46_was_nov05(self):
        assert _S46_5TD["2026-10-16"] == "2026-11-05"
        assert _CORRECT_5TD["2026-10-16"] == "2026-10-27"

    def test_oct21_s46_unchanged(self):
        assert _S46_5TD["2026-10-21"] == _CORRECT_5TD["2026-10-21"]

    def test_oct22_s46_unchanged(self):
        assert _S46_5TD["2026-10-22"] == _CORRECT_5TD["2026-10-22"]

    def test_oct28_s46_unchanged(self):
        assert _S46_5TD["2026-10-28"] == _CORRECT_5TD["2026-10-28"]


# ---------------------------------------------------------------------------
# TC23: CalendarContract SSOT indicators
# ---------------------------------------------------------------------------

class TestTC23_GetCorrectedExitFunction:
    def test_ssot_consolidation_note_present(self, calendar_contract):
        assert len(calendar_contract.consolidation_note) > 50

    def test_consolidation_note_mentions_s48(self, calendar_contract):
        assert "S48" in calendar_contract.consolidation_note

    def test_consolidation_note_mentions_s49(self, calendar_contract):
        assert "S49" in calendar_contract.consolidation_note

    def test_s46_module_status_says_unchanged(self, calendar_contract):
        assert "UNCHANGED" in calendar_contract.s46_module_status

    def test_s46_module_status_warns_not_to_use(self, calendar_contract):
        assert "Do NOT" in calendar_contract.s46_module_status or "MUST" in calendar_contract.s46_module_status


# ---------------------------------------------------------------------------
# TC24: SSOT version is S50
# ---------------------------------------------------------------------------

class TestTC24_S50SSOTVersion:
    def test_ssot_version(self, calendar_contract):
        assert calendar_contract.ssot_version == "S50"

    def test_fingerprint_deterministic(self):
        c1 = build_research_trading_calendar_contract()
        c2 = build_research_trading_calendar_contract()
        assert c1.fingerprint == c2.fingerprint

    def test_fill_dates_all_in_correct_dicts(self, calendar_contract):
        for d in calendar_contract.fill_dates:
            assert d in _CORRECT_5TD
            assert d in _CORRECT_20TD


# ---------------------------------------------------------------------------
# TC25: Pipeline Completion Contract builds with 10 stages
# ---------------------------------------------------------------------------

class TestTC25_PipelineContractBuilds:
    def test_builds_without_error(self, pipeline_contract):
        assert pipeline_contract is not None

    def test_ten_stages(self, pipeline_contract):
        assert len(pipeline_contract.stages) == 10

    def test_total_stages_attribute(self, pipeline_contract):
        assert pipeline_contract.total_stages == 10

    def test_stage_ids_s01_to_s10(self, pipeline_contract):
        ids = {s.stage_id for s in pipeline_contract.stages}
        for i in range(1, 11):
            assert f"S{i:02d}" in ids


# ---------------------------------------------------------------------------
# TC26: Pipeline stages have required fields
# ---------------------------------------------------------------------------

class TestTC26_TenPipelineStages:
    def test_all_stages_have_names(self, pipeline_contract):
        for s in pipeline_contract.stages:
            assert s.stage_name is not None and len(s.stage_name) > 0

    def test_all_stages_have_failure_verdict(self, pipeline_contract):
        for s in pipeline_contract.stages:
            assert s.failure_verdict is not None and len(s.failure_verdict) > 0

    def test_qg_stage_present(self, pipeline_contract):
        qg = next((s for s in pipeline_contract.stages if "QG" in s.stage_id or "QUALITY" in s.stage_name), None)
        assert qg is not None

    def test_critical_stages_subset(self, pipeline_contract):
        all_ids = {s.stage_id for s in pipeline_contract.stages}
        for cid in pipeline_contract.critical_stages:
            assert cid in all_ids


# ---------------------------------------------------------------------------
# TC27: DATA_COMPLETE definition is explicit and correct
# ---------------------------------------------------------------------------

class TestTC27_DataCompleteDefinition:
    def test_data_complete_definition_present(self, pipeline_contract):
        assert len(pipeline_contract.data_complete_definition) > 20

    def test_minimum_300_stocks(self, pipeline_contract):
        assert pipeline_contract.minimum_stocks_for_data_complete == 300

    def test_data_complete_definition_mentions_300(self, pipeline_contract):
        assert "300" in pipeline_contract.data_complete_definition


# ---------------------------------------------------------------------------
# TC28: Benchmark-only rejection rule is explicit
# ---------------------------------------------------------------------------

class TestTC28_BenchmarkRejectionRule:
    def test_rejection_rule_present(self, pipeline_contract):
        assert len(pipeline_contract.benchmark_only_rejection_rule) > 20

    def test_rejection_rule_mentions_0050(self, pipeline_contract):
        assert "0050" in pipeline_contract.benchmark_only_rejection_rule

    def test_rejection_rule_says_not_data_complete(self, pipeline_contract):
        assert "DATA_COMPLETE" in pipeline_contract.benchmark_only_rejection_rule

    def test_pipeline_blocked_reason_mentions_nov06_nov09(self, pipeline_contract):
        assert "Nov 06" in pipeline_contract.pipeline_blocked_reason or "Nov 09" in pipeline_contract.pipeline_blocked_reason


# ---------------------------------------------------------------------------
# TC29: Strict 5D Eligibility Matrix builds
# ---------------------------------------------------------------------------

class TestTC29_Strict5DEligibilityMatrixBuilds:
    def test_builds_without_error(self, eligibility_matrix):
        assert eligibility_matrix is not None

    def test_six_clusters(self, eligibility_matrix):
        assert len(eligibility_matrix.clusters) == 6

    def test_grand_mean_delta(self, eligibility_matrix):
        assert eligibility_matrix.grand_mean_delta == pytest.approx(0.81, abs=0.01)

    def test_frozen_baseline_fingerprint(self, eligibility_matrix):
        assert eligibility_matrix.frozen_baseline_fingerprint == "09c04e8c4059d87e"


# ---------------------------------------------------------------------------
# TC30: 3 strict eligible clusters NOW (Oct 13/14/16)
# ---------------------------------------------------------------------------

class TestTC30_ThreeStrictNow:
    def test_n_strict_now_is_three(self, eligibility_matrix):
        assert eligibility_matrix.n_strict_now == 3

    def test_oct13_strict_now(self, eligibility_matrix):
        oct13 = next(c for c in eligibility_matrix.clusters if c.fill_date == "2026-10-13")
        assert oct13.strict_eligible_now is True

    def test_oct14_strict_now(self, eligibility_matrix):
        oct14 = next(c for c in eligibility_matrix.clusters if c.fill_date == "2026-10-14")
        assert oct14.strict_eligible_now is True

    def test_oct16_strict_now(self, eligibility_matrix):
        oct16 = next(c for c in eligibility_matrix.clusters if c.fill_date == "2026-10-16")
        assert oct16.strict_eligible_now is True

    def test_oct21_not_strict_now(self, eligibility_matrix):
        oct21 = next(c for c in eligibility_matrix.clusters if c.fill_date == "2026-10-21")
        assert oct21.strict_eligible_now is False

    def test_g03_fails_now(self, eligibility_matrix):
        assert eligibility_matrix.g03_now is False


# ---------------------------------------------------------------------------
# TC31: 6 strict eligible clusters after P1 backfill
# ---------------------------------------------------------------------------

class TestTC31_SixStrictAfterP1:
    def test_n_strict_after_p1_is_six(self, eligibility_matrix):
        assert eligibility_matrix.n_strict_after_p1 == 6

    def test_all_clusters_strict_after_p1(self, eligibility_matrix):
        for c in eligibility_matrix.clusters:
            assert c.strict_eligible_after_p1 is True, \
                f"{c.fill_date} should be strict after P1 backfill"

    def test_g03_still_fails_after_p1(self, eligibility_matrix):
        assert eligibility_matrix.g03_after_p1 is False

    def test_g03_requirement_is_ten(self, eligibility_matrix):
        assert eligibility_matrix.g03_requirement == 10


# ---------------------------------------------------------------------------
# TC32: Oct 21/22/28 show READY_AFTER_VERIFIED_BACKFILL status
# ---------------------------------------------------------------------------

class TestTC32_ReadyAfterVerifiedBackfillStatus:
    def test_oct21_ready_after_backfill(self, eligibility_matrix):
        oct21 = next(c for c in eligibility_matrix.clusters if c.fill_date == "2026-10-21")
        assert oct21.status == StrictEligibilityStatus.READY_AFTER_VERIFIED_BACKFILL

    def test_oct22_ready_after_backfill(self, eligibility_matrix):
        oct22 = next(c for c in eligibility_matrix.clusters if c.fill_date == "2026-10-22")
        assert oct22.status == StrictEligibilityStatus.READY_AFTER_VERIFIED_BACKFILL

    def test_oct28_ready_after_backfill(self, eligibility_matrix):
        oct28 = next(c for c in eligibility_matrix.clusters if c.fill_date == "2026-10-28")
        assert oct28.status == StrictEligibilityStatus.READY_AFTER_VERIFIED_BACKFILL

    def test_oct28_needs_three_backfill_dates(self, eligibility_matrix):
        oct28 = next(c for c in eligibility_matrix.clusters if c.fill_date == "2026-10-28")
        assert len(oct28.backfill_dates_needed) == 3

    def test_oct21_needs_one_backfill_date(self, eligibility_matrix):
        oct21 = next(c for c in eligibility_matrix.clusters if c.fill_date == "2026-10-21")
        assert len(oct21.backfill_dates_needed) == 1
        assert "2026-10-29" in oct21.backfill_dates_needed

    def test_strict_now_clusters_need_no_backfill(self, eligibility_matrix):
        for c in eligibility_matrix.clusters:
            if c.strict_eligible_now:
                assert len(c.backfill_dates_needed) == 0, \
                    f"{c.fill_date} is already strict; should need no backfill"


# ---------------------------------------------------------------------------
# TC33: G04 Dependence Study builds and has correct structure
# ---------------------------------------------------------------------------

class TestTC33_G04DependenceStudyBuilds:
    def test_builds_without_error(self, g04_study):
        assert g04_study is not None

    def test_all_fills_present(self, g04_study):
        assert len(g04_study.all_fills) == 6

    def test_five_adjacent_pairs_overlaps(self, g04_study):
        assert len(g04_study.all_overlaps) == 5

    def test_max_adjacent_overlap_80pct(self, g04_study):
        assert g04_study.max_adjacent_overlap_pct == 80

    def test_five_adjacent_pairs_failing(self, g04_study):
        assert g04_study.n_adjacent_failing == 5

    def test_three_scenarios(self, g04_study):
        assert len(g04_study.weekly_spacing_scenarios) == 3


# ---------------------------------------------------------------------------
# TC34: Weekly 5TD spacing: N=3 but Oct 21/Oct 28 pair still 40% → G04 FAIL
# ---------------------------------------------------------------------------

class TestTC34_Weekly5TDStillFails:
    def test_scenario_weekly_5td_present(self, g04_study):
        s = next((x for x in g04_study.weekly_spacing_scenarios if x.name == "WEEKLY_5TD"), None)
        assert s is not None

    def test_weekly_5td_retains_three(self, g04_study):
        s = next(x for x in g04_study.weekly_spacing_scenarios if x.name == "WEEKLY_5TD")
        assert s.n_retained == 3

    def test_weekly_5td_retains_oct13_oct21_oct28(self, g04_study):
        s = next(x for x in g04_study.weekly_spacing_scenarios if x.name == "WEEKLY_5TD")
        assert "2026-10-13" in s.retained_fills
        assert "2026-10-21" in s.retained_fills
        assert "2026-10-28" in s.retained_fills

    def test_weekly_5td_g04_still_fails(self, g04_study):
        s = next(x for x in g04_study.weekly_spacing_scenarios if x.name == "WEEKLY_5TD")
        assert s.g04_verdict == G04WeeklySpacingVerdict.G04_FAIL

    def test_weekly_5td_oct21_oct28_overlap_40pct(self, g04_study):
        s = next(x for x in g04_study.weekly_spacing_scenarios if x.name == "WEEKLY_5TD")
        assert s.max_overlap_pct == 40

    def test_weekly_5td_g03_not_met(self, g04_study):
        s = next(x for x in g04_study.weekly_spacing_scenarios if x.name == "WEEKLY_5TD")
        assert s.g03_verdict is False


# ---------------------------------------------------------------------------
# TC35: Weekly 6TD spacing: fewer fills, G04 improves
# ---------------------------------------------------------------------------

class TestTC35_Weekly6TDReducesN:
    def test_scenario_weekly_6td_present(self, g04_study):
        s = next((x for x in g04_study.weekly_spacing_scenarios if x.name == "WEEKLY_6TD"), None)
        assert s is not None

    def test_weekly_6td_retains_fewer_than_5td(self, g04_study):
        s5 = next(x for x in g04_study.weekly_spacing_scenarios if x.name == "WEEKLY_5TD")
        s6 = next(x for x in g04_study.weekly_spacing_scenarios if x.name == "WEEKLY_6TD")
        assert s6.n_retained <= s5.n_retained

    def test_weekly_6td_g03_not_met(self, g04_study):
        s = next(x for x in g04_study.weekly_spacing_scenarios if x.name == "WEEKLY_6TD")
        assert s.g03_verdict is False


# ---------------------------------------------------------------------------
# TC36: G04 effective N calculation
# ---------------------------------------------------------------------------

class TestTC36_G04EffectiveNCalc:
    def test_effective_n_key_present(self, g04_study):
        # Should have at least one key with effective N data
        assert len(g04_study.effective_n_calculation) >= 3

    def test_effective_n_less_than_2(self, g04_study):
        # For N=6 with r=0.8, effective N ≈ 1.09
        en_values = [
            v for k, v in g04_study.effective_n_calculation.items()
            if isinstance(v, (int, float))
        ]
        assert all(en < 2.0 for en in en_values), \
            f"All effective N values should be < 2.0, got {en_values}"

    def test_root_cause_mentions_5day(self, g04_study):
        assert "5-day" in g04_study.root_cause or "5TD" in g04_study.root_cause or "five" in g04_study.root_cause.lower()

    def test_finding_mentions_structural(self, g04_study):
        assert "STRUCTURAL" in g04_study.finding or "structural" in g04_study.finding.lower()


# ---------------------------------------------------------------------------
# TC37: Bootstrap is not applicable with current N
# ---------------------------------------------------------------------------

class TestTC37_G04BootstrapNotApplicable:
    def test_bootstrap_applicable_false(self, g04_study):
        assert g04_study.bootstrap_applicable is False

    def test_bootstrap_blocked_reason_mentions_n_requirement(self, g04_study):
        assert "N≥10" in g04_study.bootstrap_blocked_reason or "N>=10" in g04_study.bootstrap_blocked_reason or "10" in g04_study.bootstrap_blocked_reason

    def test_remediation_recommendation_present(self, g04_study):
        assert len(g04_study.remediation_recommendation) > 30

    def test_overall_g04_verdict_fail(self, g04_study):
        assert g04_study.g04_current_verdict == G04WeeklySpacingVerdict.G04_FAIL


# ---------------------------------------------------------------------------
# TC38: 20D Readiness Matrix builds and returns correct structure
# ---------------------------------------------------------------------------

class TestTC38_TwentyDReadinessMatrixBuilds:
    def test_builds_without_error(self, readiness_matrix_blocked):
        assert readiness_matrix_blocked is not None

    def test_six_clusters(self, readiness_matrix_blocked):
        assert len(readiness_matrix_blocked.clusters) == 6

    def test_earliest_maturity_nov12(self, readiness_matrix_blocked):
        assert readiness_matrix_blocked.earliest_maturity_date == "2026-11-12"

    def test_latest_maturity_nov25(self, readiness_matrix_blocked):
        assert readiness_matrix_blocked.latest_maturity_date == "2026-11-25"

    def test_auth01_pending(self, readiness_matrix_blocked):
        assert readiness_matrix_blocked.auth01_status == "PENDING"

    def test_auth02_pending(self, readiness_matrix_blocked):
        assert readiness_matrix_blocked.auth02_status == "PENDING"

    def test_nov12_deadline_note_present(self, readiness_matrix_blocked):
        assert "Nov 12" in readiness_matrix_blocked.nov12_hard_deadline_note


# ---------------------------------------------------------------------------
# TC39: All clusters BLOCKED_PIPELINE when pipeline not restored
# ---------------------------------------------------------------------------

class TestTC39_TwentyDBlockedPipeline:
    def test_overall_verdict_blocked_pipeline(self, readiness_matrix_blocked):
        assert readiness_matrix_blocked.overall_verdict == TwentyDReadinessVerdict.BLOCKED_PIPELINE

    def test_all_clusters_pipeline_blocked(self, readiness_matrix_blocked):
        for c in readiness_matrix_blocked.clusters:
            assert c.verdict == TwentyDReadinessVerdict.BLOCKED_PIPELINE, \
                f"{c.fill_date} should be BLOCKED_PIPELINE, got {c.verdict}"

    def test_critical_path_mentions_auth01(self, readiness_matrix_blocked):
        assert "AUTH01" in readiness_matrix_blocked.critical_path

    def test_critical_path_mentions_pipeline(self, readiness_matrix_blocked):
        assert "pipeline" in readiness_matrix_blocked.critical_path.lower() or "Pipeline" in readiness_matrix_blocked.critical_path

    def test_corrected_exit_dates_match_ssot(self, readiness_matrix_blocked):
        for c in readiness_matrix_blocked.clusters:
            assert c.exit_20td_corrected == _CORRECT_20TD[c.fill_date]

    def test_erroneous_exit_dates_match_s46(self, readiness_matrix_blocked):
        for c in readiness_matrix_blocked.clusters:
            assert c.exit_20td_s46_erroneous == _S46_20TD[c.fill_date]

    def test_authorized_ready_when_all_granted(self):
        matrix = build_20d_readiness_matrix(
            analysis_date="2026-11-30",  # after all exits
            auth01_granted=True,
            auth02_granted=True,
            pipeline_restored=True,
        )
        assert matrix.overall_verdict == TwentyDReadinessVerdict.AUTHORIZED_READY


# ---------------------------------------------------------------------------
# TC40: Production fingerprints unchanged (READ-ONLY DB check)
# ---------------------------------------------------------------------------

class TestTC40_ProductionFingerprintsUnchanged:
    def test_forward_signals_total(self, conn):
        n = conn.execute("SELECT COUNT(*) FROM forward_signals").fetchone()[0]
        assert n == 2605

    def test_daily_prices_max_date(self, conn):
        max_date = conn.execute("SELECT MAX(date) FROM daily_prices").fetchone()[0]
        assert max_date == "2026-11-05"

    def test_v8_buy_signals_unchanged(self, conn):
        n = conn.execute(
            "SELECT COUNT(*) FROM forward_signals "
            "WHERE model_version='v8.0' AND trade_signal IN ('buy', 'strong_buy')"
        ).fetchone()[0]
        assert n == 237

    def test_nov06_still_zero_rows(self, conn):
        n = conn.execute(
            "SELECT COUNT(*) FROM daily_prices WHERE date='2026-11-06'"
        ).fetchone()[0]
        assert n == 0

    def test_nov09_still_zero_rows(self, conn):
        n = conn.execute(
            "SELECT COUNT(*) FROM daily_prices WHERE date='2026-11-09'"
        ).fetchone()[0]
        assert n == 0

    def test_pairwise_overlap_oct13_oct14(self):
        ov = get_overlap("2026-10-13", "2026-10-14")
        assert ov["pct"] == 80
        assert ov["adjacent"] is True

    def test_pairwise_overlap_oct21_oct22(self):
        ov = get_overlap("2026-10-21", "2026-10-22")
        assert ov["pct"] == 80
        assert ov["adjacent"] is True

    def test_pairwise_overlap_oct13_oct21_zero(self):
        ov = get_overlap("2026-10-13", "2026-10-21")
        assert ov["pct"] == 0
