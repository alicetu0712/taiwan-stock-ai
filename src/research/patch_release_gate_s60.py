"""
Patch Release Gate & TWSE PIT Universe — Session 60

PART D: TradingShares parser patch
PART E: Independent patch release gate (3 patches)
PART F: TWSE 712→720 PIT universe correction + stock-month manifest

Key corrections vs S59:
- TWSE eligible stocks: 712 (S59 hardcoded) → 720 (Aug2026+ DB query) / 717 (Nov05 actual)
- Stock-month requests: 1,424 → 1,440 (720 × 2)
- 006xxx ETFs correctly classified as ETFs (not warrants)
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List


# ── Enums ──────────────────────────────────────────────────────────────────────

class PatchStatus(str, Enum):
    NOT_AUTHORIZED = "NOT_AUTHORIZED"
    NOT_DEPLOYED = "NOT_DEPLOYED"
    DEPLOYED = "DEPLOYED"
    BLOCKED = "BLOCKED"


class PatchVerdict(str, Enum):
    READY_FOR_AUTHORIZATION = "READY_FOR_AUTHORIZATION"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"


class ParserPatchVerdict(str, Enum):
    PARSER_PATCH_READY_FOR_AUTHORIZATION = "PARSER_PATCH_READY_FOR_AUTHORIZATION"
    PARSER_PATCH_PARTIAL = "PARSER_PATCH_PARTIAL"
    PARSER_PATCH_BLOCKED = "PARSER_PATCH_BLOCKED"


class ErrorPatchVerdict(str, Enum):
    ERROR_PATCH_READY_FOR_AUTHORIZATION = "ERROR_PATCH_READY_FOR_AUTHORIZATION"
    ERROR_PATCH_PARTIAL = "ERROR_PATCH_PARTIAL"
    ERROR_PATCH_BLOCKED = "ERROR_PATCH_BLOCKED"


class HistoricalRepairVerdict(str, Enum):
    VOLUME_REPAIR_READY_FOR_AUTHORIZATION = "VOLUME_REPAIR_READY_FOR_AUTHORIZATION"
    VOLUME_REPAIR_PARTIAL = "VOLUME_REPAIR_PARTIAL"
    VOLUME_REPAIR_BLOCKED = "VOLUME_REPAIR_BLOCKED"


class PitUniverseVerdict(str, Enum):
    TWSE_PIT_UNIVERSE_VERIFIED = "TWSE_PIT_UNIVERSE_VERIFIED"
    TWSE_PIT_UNIVERSE_PARTIAL = "TWSE_PIT_UNIVERSE_PARTIAL"
    TWSE_PIT_UNIVERSE_UNVERIFIED = "TWSE_PIT_UNIVERSE_UNVERIFIED"


class ManifestVerdict(str, Enum):
    T2_MANIFEST_READY = "T2_MANIFEST_READY"
    T2_MANIFEST_PARTIAL = "T2_MANIFEST_PARTIAL"
    T2_MANIFEST_BLOCKED = "T2_MANIFEST_BLOCKED"


class T2ComplianceVerdict(str, Enum):
    T2_COMPLIANCE_VERIFIED = "T2_COMPLIANCE_VERIFIED"
    T2_COMPLIANCE_PARTIAL = "T2_COMPLIANCE_PARTIAL"
    T2_COMPLIANCE_UNVERIFIED = "T2_COMPLIANCE_UNVERIFIED"
    T2_COMPLIANCE_BLOCKED = "T2_COMPLIANCE_BLOCKED"


# ── PART D: TradingShares Parser Patch ────────────────────────────────────────

@dataclass
class ParserPatch:
    patch_id: str
    file: str
    line_original: int
    original_line: str
    patched_line: str
    purpose: str
    evidence: str
    confidence: str
    side_effects: str
    affects_twse: bool
    affects_tpex: bool
    unresolved_assumptions: str
    test_coverage: str
    authorization_status: str


def build_parser_patches() -> List[ParserPatch]:
    """
    PP-01-REVISED: Warrant exclusion patch (covered in tpex_security_classification_s60)
    PP-02: TradingShares volume field fix
    PP-03: TransactionAmount field fix (HYPOTHESIS)
    """
    return [
        ParserPatch(
            patch_id="PP-02",
            file="scripts/backfill_daily_prices.py",
            line_original=284,
            original_line='            vol_raw = _strip_num(str(row.get("TradeVolume", "")))',
            patched_line='            vol_raw = _strip_num(str(row.get("TradingShares", "")))',
            purpose="Map TPEx TradingShares field to volume (DIRECTLY CONFIRMED from S58 WebFetch)",
            evidence=(
                "S58 P02 WebFetch of live TPEx bulk endpoint (Nov04 probe) explicitly returned "
                "'TradingShares' field name in the JSON payload. "
                "S59 forensics confirmed: 21,846 TPEx ordinary stock rows have OHLC present "
                "but volume=NULL (field returns None for missing 'TradeVolume' key). "
                "After fix: row.get('TradingShares') returns actual volume value."
            ),
            confidence="HIGH — DIRECTLY_CONFIRMED from live API probe",
            side_effects=(
                "Affects ONLY fetch_tpex_historical() path in backfill script. "
                "TWSE parser (fetch_twse_openapi) uses TradeVolume — correct for TWSE, unchanged. "
                "Volume unit unchanged: /1000 applied after field read. "
                "Will not update existing NULL rows — only affects future backfill runs."
            ),
            affects_twse=False,
            affects_tpex=True,
            unresolved_assumptions="None. Field name confirmed by direct API observation.",
            test_coverage="10 schema compatibility tests (PASS in S59). QG simulation on temp SQLite.",
            authorization_status="NOT_AUTHORIZED — requires explicit deployment authorization",
        ),
        ParserPatch(
            patch_id="PP-03",
            file="scripts/backfill_daily_prices.py",
            line_original=285,
            original_line='            amt_raw = _strip_num(str(row.get("TradeValue", "")))',
            patched_line='            amt_raw = _strip_num(str(row.get("TransactionAmount", "")))',
            purpose="Map TPEx TransactionAmount field to amount (HYPOTHESIS — not verified)",
            evidence=(
                "HYPOTHESIS only. S58 WebFetch focused on volume field (TradingShares). "
                "The amount field name for TPEx ('TransactionAmount') was NOT observed directly. "
                "The assumption is based on naming convention parallelism. "
                "EVIDENCE LEVEL: MEDIUM. NOT SAFE TO DEPLOY without verification."
            ),
            confidence="MEDIUM — HYPOTHESIS, not directly confirmed",
            side_effects=(
                "If 'TransactionAmount' is correct: amount column populated for TPEx stocks. "
                "If wrong: amount remains NULL (no data corruption). "
                "Risk: naming could be 'TradeValue', 'Amount', 'TurnoverValue', etc."
            ),
            affects_twse=False,
            affects_tpex=True,
            unresolved_assumptions=(
                "MUST verify actual TPEx API field name for transaction amount "
                "BEFORE including in deployment. "
                "Recommendation: probe live TPEx API and log raw payload field names. "
                "PP-03 must NOT be bundled with PP-01/PP-02 until verified."
            ),
            test_coverage="Schema compatibility test only (uses hardcoded 'TransactionAmount' assumption).",
            authorization_status="NOT_AUTHORIZED — HYPOTHESIS status blocks deployment",
        ),
    ]


# ── Volume Unit Contract ───────────────────────────────────────────────────────

@dataclass
class VolumeUnitContract:
    twse_api_field: str
    twse_divisor: float
    twse_unit: str
    tpex_api_field_original: str
    tpex_api_field_corrected: str
    tpex_divisor: float
    tpex_unit_evidence: str
    db_unit: str
    zero_volume_treatment: str
    null_handling: str
    rounding_rule: str


def build_volume_unit_contract() -> VolumeUnitContract:
    return VolumeUnitContract(
        twse_api_field="TradeVolume",
        twse_divisor=1_000.0,
        twse_unit="shares → stored as 千股 (thousands of shares)",
        tpex_api_field_original="TradeVolume (WRONG — returns None for TPEx)",
        tpex_api_field_corrected="TradingShares (DIRECTLY CONFIRMED from S58 WebFetch)",
        tpex_divisor=1_000.0,
        tpex_unit_evidence=(
            "S58 P02 probe: 2317/Nov06 TradingShares=89,094,382 raw shares → "
            "89,094.382 千股 (thousands of shares). "
            "Consistent with TWSE volume scale. "
            "Taiwan stock: 1 lot = 1,000 shares. 89M shares = 89,094 lots ≈ reasonable for active ETF."
        ),
        db_unit="千股 (thousands of shares) for both TWSE and TPEx",
        zero_volume_treatment="VALID — stored as 0.0",
        null_handling="NULL stored when field missing or returns empty/'-' string",
        rounding_rule="Float division (no explicit rounding). Python float precision.",
    )


# ── PART E: Independent Patch Release Gate ────────────────────────────────────

@dataclass
class IndependentPatch:
    patch_id: str
    name: str
    file: str
    exact_diff: str
    scope: str
    dependencies: List[str]
    behavioral_change: str
    risk: str
    rollback: str
    production_compatible: bool
    independent_authorization_required: bool
    post_deployment_verification: str
    stop_conditions: str
    deployment_verdict: str
    not_deployed: bool


def build_independent_patches() -> List[IndependentPatch]:
    return [
        IndependentPatch(
            patch_id="PATCH-1",
            name="TPEx Error Reporting Patch",
            file="scripts/backfill_daily_prices.py",
            exact_diff=(
                "Line ~500-501: change\n"
                "  print(f'  TPEx api_date mismatch ...')\n"
                "to:\n"
                "  summary['errors'].append(f'TPEx api_date mismatch ...')"
            ),
            scope="Diagnostic only — changes where api_date mismatch is logged. No data effect.",
            dependencies=[],
            behavioral_change=(
                "Mismatch errors moved from print() to summary['errors']. "
                "No change to data inserted. No change to volume field names."
            ),
            risk="VERY LOW — purely diagnostic change",
            rollback="Revert line 500-501 to print() statement",
            production_compatible=True,
            independent_authorization_required=True,
            post_deployment_verification=(
                "Run backfill for 1 date. Confirm mismatch appears in summary['errors']. "
                "Confirm no change in row counts or volume values."
            ),
            stop_conditions="Backfill error rate increases after deployment",
            deployment_verdict="ERROR_PATCH_READY_FOR_AUTHORIZATION",
            not_deployed=True,
        ),
        IndependentPatch(
            patch_id="PATCH-2",
            name="Warrant Exclusion Patch",
            file="scripts/backfill_daily_prices.py",
            exact_diff=(
                "Line 98: change\n"
                "  if len(sid) > 4 and not sid.isdigit():\n"
                "to:\n"
                "  if len(sid) > 4:"
            ),
            scope=(
                "Affects ALL three call sites of _is_excluded() "
                "(lines 125, 214, 273 in TWSE, TWSE-single-stock, and TPEx paths). "
                "Prevents future insertion of len>4 stock IDs (warrants, 5-digit ETFs, 6-digit ETFs)."
            ),
            dependencies=[],
            behavioral_change=(
                "Future backfill runs will NOT insert 7xxxxx warrants, 00xxx ETFs, 006xxx ETFs. "
                "Existing rows in daily_prices are NOT deleted. "
                "QG universe denominator will be smaller (ordinary stocks only) going forward."
            ),
            risk=(
                "LOW: No existing data removed. No existing signals changed. "
                "MONITORED: If a future legitimate 5-digit ordinary stock is listed, "
                "it would be incorrectly excluded."
            ),
            rollback="Restore 'and not sid.isdigit()' condition. No data to undo.",
            production_compatible=True,
            independent_authorization_required=True,
            post_deployment_verification=(
                "Run backfill for 1 date. Confirm 6-digit and 5-digit stocks absent from output. "
                "Confirm 4-digit stocks still present."
            ),
            stop_conditions="4-digit ordinary stocks missing from backfill output",
            deployment_verdict="WARRANT_PATCH_READY_FOR_AUTHORIZATION",
            not_deployed=True,
        ),
        IndependentPatch(
            patch_id="PATCH-3",
            name="TradingShares Parser Patch (PP-02 only)",
            file="scripts/backfill_daily_prices.py",
            exact_diff=(
                "Line 284: change\n"
                '  vol_raw = _strip_num(str(row.get("TradeVolume", "")))\n'
                "to:\n"
                '  vol_raw = _strip_num(str(row.get("TradingShares", "")))\n'
                "\n"
                "NOTE: PP-03 (line 285 amount field) is HYPOTHESIS and NOT included here."
            ),
            scope=(
                "Affects ONLY fetch_tpex_historical() volume parsing. "
                "PP-02 only (not PP-03). TWSE volume parsing unchanged."
            ),
            dependencies=[],
            behavioral_change=(
                "Future TPEx backfill fetches will populate volume (not NULL) "
                "for ordinary TPEx stocks. Historical rows remain NULL. "
                "Volume unit unchanged: /1000 applied."
            ),
            risk=(
                "LOW for PP-02 alone: field confirmed by direct S58 probe. "
                "HIGH if PP-03 (TransactionAmount) is bundled: unverified hypothesis."
            ),
            rollback=(
                "Restore row.get('TradeVolume') on line 284. "
                "Historical rows unaffected."
            ),
            production_compatible=True,
            independent_authorization_required=True,
            post_deployment_verification=(
                "Run backfill for 1 TPEx date. Confirm volume IS NOT NULL for ordinary TPEx stocks. "
                "Confirm TWSE stocks unaffected. "
                "Confirm /1000 unit consistent with TWSE volumes."
            ),
            stop_conditions=(
                "TPEx volume values implausible (e.g., 1000x higher than expected = lots instead of shares). "
                "TWSE volume values changed unexpectedly."
            ),
            deployment_verdict="PARSER_PATCH_READY_FOR_AUTHORIZATION",
            not_deployed=True,
        ),
    ]


@dataclass
class PatchIndependenceVerification:
    patch_1_affects_patch_2: bool
    patch_1_affects_patch_3: bool
    patch_2_affects_patch_3: bool
    shared_code_regions: List[str]
    independent_rollback_possible: bool
    safest_deployment_order: str
    combined_deployment_risk: str


def verify_patch_independence() -> PatchIndependenceVerification:
    return PatchIndependenceVerification(
        patch_1_affects_patch_2=False,
        patch_1_affects_patch_3=False,
        patch_2_affects_patch_3=False,
        shared_code_regions=[
            "All 3 patches modify scripts/backfill_daily_prices.py",
            "PATCH-1: line ~500 (TPEx loop error handling)",
            "PATCH-2: line 98 (_is_excluded function body)",
            "PATCH-3: line 284 (TPEx parser volume field name)",
            "These 3 regions are non-overlapping — independent edits",
        ],
        independent_rollback_possible=True,
        safest_deployment_order=(
            "1. PATCH-2 (warrant exclusion) — smallest blast radius, diagnostic-only effect on data. "
            "2. PATCH-1 (error reporting) — no data change, improves observability. "
            "3. PATCH-3 (TradingShares) — data-touching, deploy AFTER observing PATCH-2 output. "
            "PP-03 (amount field): NOT included until TransactionAmount field name verified."
        ),
        combined_deployment_risk=(
            "LOW if deployed separately with verification between each. "
            "MEDIUM if bundled (harder to debug if one causes unexpected output). "
            "NEVER bundle PP-03 with PP-01/PP-02 until TransactionAmount confirmed."
        ),
    )


@dataclass
class HistoricalRepairAnalysis:
    twse_ordinary_repair_possible: bool
    twse_ordinary_method: str
    twse_ordinary_rows: int
    tpex_ordinary_repair_possible: bool
    tpex_ordinary_method: str
    tpex_ordinary_rows: int
    warrant_repair_needed: bool
    warrant_preferred_fix: str
    verdict: HistoricalRepairVerdict
    not_authorized: bool


def build_historical_repair_analysis() -> HistoricalRepairAnalysis:
    return HistoricalRepairAnalysis(
        twse_ordinary_repair_possible=True,
        twse_ordinary_method=(
            "INSERT (not UPDATE) — these rows are MISSING from daily_prices for Oct29-Nov09. "
            "Source: TWSE single-stock monthly API. "
            "5 pilot-verified stocks (S58): 2330/2454/1301 Oct, 2317/2882 Nov. "
            "Full recovery: 720 stocks × 2 months = 1,440 API calls. "
            "Requires AUTH01 + T2 compliance confirmation."
        ),
        twse_ordinary_rows=0,
        tpex_ordinary_repair_possible=False,
        tpex_ordinary_method=(
            "BLOCKED — no verified per-stock historical endpoint for TPEx. "
            "Bulk endpoint: DATE_PARAM_IGNORED (RC-03, confirmed S57). "
            "Historical NULL rows (21,846) cannot be repaired without source."
        ),
        tpex_ordinary_rows=21_846,
        warrant_repair_needed=False,
        warrant_preferred_fix=(
            "Warrant rows should NOT be repaired. "
            "Preferred action: (1) Deploy PATCH-2 to prevent future warrant inserts. "
            "(2) Leave historical warrant rows as-is (they don't affect QG). "
            "(3) Optional: DELETE historical warrant rows after PATCH-2 is stable. "
            "No recovery of NULL volume needed — warrants excluded from research universe."
        ),
        verdict=HistoricalRepairVerdict.VOLUME_REPAIR_BLOCKED,
        not_authorized=True,
    )


# ── PART F: TWSE PIT Universe ──────────────────────────────────────────────────

@dataclass
class TWSEPITUniverse:
    s59_hardcoded: int
    s60_aug2026_query: int
    s60_nov05_actual: int
    s60_all_time: int
    recommended_denominator: int
    recommended_denominator_basis: str
    stock_month_requests_s59: int
    stock_month_requests_s60: int
    runtime_estimate_min: float
    discrepancy_explanation: str
    pit_per_gap_date: Dict[str, int]
    stocks_table_total: int


def build_twse_pit_universe(db_path: str = "data/platform.db") -> TWSEPITUniverse:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # S60 query: Aug2026+
    cur.execute("""
        SELECT COUNT(DISTINCT dp.stock_id) FROM daily_prices dp
        INNER JOIN stocks s ON s.stock_id=dp.stock_id
        WHERE s.market='TWSE' AND dp.date >= '2026-08-01'
        AND LENGTH(dp.stock_id)=4 AND dp.stock_id GLOB '[0-9][0-9][0-9][0-9]'
    """)
    aug2026 = cur.fetchone()[0]

    # S60 query: Nov05 (most recent full day)
    cur.execute("""
        SELECT COUNT(DISTINCT dp.stock_id) FROM daily_prices dp
        INNER JOIN stocks s ON s.stock_id=dp.stock_id
        WHERE s.market='TWSE' AND dp.date='2026-11-05'
        AND LENGTH(dp.stock_id)=4 AND dp.stock_id!='0050'
    """)
    nov05 = cur.fetchone()[0]

    # All-time
    cur.execute("""
        SELECT COUNT(DISTINCT dp.stock_id) FROM daily_prices dp
        INNER JOIN stocks s ON s.stock_id=dp.stock_id
        WHERE s.market='TWSE' AND LENGTH(dp.stock_id)=4
        AND dp.stock_id GLOB '[0-9][0-9][0-9][0-9]'
    """)
    all_time = cur.fetchone()[0]

    # stocks table total
    cur.execute("SELECT COUNT(*) FROM stocks WHERE market='TWSE'")
    stocks_total = cur.fetchone()[0]

    # PIT per gap date — expected 0 (gap dates = no data present)
    gap_dates = ["2026-10-29", "2026-10-30", "2026-11-02", "2026-11-03", "2026-11-06", "2026-11-09"]
    pit_per_date = {}
    for d in gap_dates:
        cur.execute("""
            SELECT COUNT(DISTINCT dp.stock_id) FROM daily_prices dp
            INNER JOIN stocks s ON s.stock_id=dp.stock_id
            WHERE dp.date=? AND s.market='TWSE' AND LENGTH(dp.stock_id)=4
        """, (d,))
        pit_per_date[d] = cur.fetchone()[0]

    conn.close()

    recommended = aug2026  # 720 (most accurate for recovery scope)
    runtime = round(recommended * 2 * 2.0 / 60, 1)  # 2 months × 2s delay

    return TWSEPITUniverse(
        s59_hardcoded=712,
        s60_aug2026_query=aug2026,
        s60_nov05_actual=nov05,
        s60_all_time=all_time,
        recommended_denominator=recommended,
        recommended_denominator_basis=(
            f"Aug2026+ active TWSE stocks (JOIN stocks WHERE market=TWSE, date>=2026-08-01): {aug2026}. "
            f"Nov05 actual (most recent full day, excludes 0050): {nov05}. "
            f"Conservative: use Nov05 ({nov05}) as lower-bound. "
            f"Upper-bound: Aug2026 ({aug2026}). "
            f"S60 uses {recommended} as primary estimate (Aug2026+)."
        ),
        stock_month_requests_s59=1_424,
        stock_month_requests_s60=recommended * 2,
        runtime_estimate_min=runtime,
        discrepancy_explanation=(
            f"S59 hardcoded 712 from an earlier estimation. "
            f"S60 live query returns {aug2026} (Aug2026+) or {nov05} (Nov05 actual). "
            f"Difference = {aug2026 - 712} stocks. "
            f"Likely caused by: S59 used a more restrictive threshold or subset. "
            f"Impact on request count: {aug2026*2 - 1424} additional requests. "
            f"Impact on runtime: +{(aug2026*2 - 1424)*2/60:.1f} min. Negligible difference."
        ),
        pit_per_gap_date=pit_per_date,
        stocks_table_total=stocks_total,
    )


@dataclass
class StockMonthManifestEntry:
    stock_id: str
    stock_month: str
    month_label: str
    source: str
    ohlcv_verified: bool
    volume_verified: bool
    authorization_status: str
    notes: str


def build_stock_month_manifest() -> List[StockMonthManifestEntry]:
    """
    Minimal pilot-verified manifest from S58.
    Full manifest (1440 entries) requires AUTH01 retrieval.
    """
    pilot = [
        ("2330", "202610", "October 2026", "S58 P01", True, True,
         "AUTH01_PENDING", "Oct29: O=2420/H=2425/L=2390/C=2415/V=18.4M; Oct30: O=2380/C=2370/V=36.6M"),
        ("2454", "202610", "October 2026", "S58 P03", True, True,
         "AUTH01_PENDING", "Oct29: O=4205/H=4225/L=4000/C=4045/V=6.9M"),
        ("1301", "202610", "October 2026", "S58 P04", True, True,
         "AUTH01_PENDING", "Oct29: O=75.3/H=76.1/L=73.8/C=73.9/V=19.1M"),
        ("2317", "202611", "November 2026", "S58 P02", True, True,
         "AUTH01_PENDING", "Nov03 close=245.5 CONFIRMED; Nov06/09 FULL OHLCV"),
        ("2882", "202611", "November 2026", "S58 P05", True, True,
         "AUTH01_PENDING", "Nov02: O=117/C=116/V=28M; Nov03: O=116/C=113/V=30M"),
    ]
    return [
        StockMonthManifestEntry(sid, sm, ml, src, ov, vv, auth, notes)
        for sid, sm, ml, src, ov, vv, auth, notes in pilot
    ]


@dataclass
class T2RequestBudget:
    eligible_stocks_s59: int
    eligible_stocks_s60: int
    months: int
    total_requests_s59: int
    total_requests_s60: int
    delay_seconds: float
    runtime_minutes_s59: float
    runtime_minutes_s60: float
    rate_limit_status: str
    compliance_status: str


def build_t2_request_budget(db_path: str = "data/platform.db") -> T2RequestBudget:
    pit = build_twse_pit_universe(db_path)
    s60_eligible = pit.recommended_denominator
    return T2RequestBudget(
        eligible_stocks_s59=712,
        eligible_stocks_s60=s60_eligible,
        months=2,
        total_requests_s59=1_424,
        total_requests_s60=s60_eligible * 2,
        delay_seconds=2.0,
        runtime_minutes_s59=round(1_424 * 2.0 / 60, 1),
        runtime_minutes_s60=round(s60_eligible * 2 * 2.0 / 60, 1),
        rate_limit_status="UNVERIFIED — no rate limit headers observed in 5 pilot probes",
        compliance_status="T2_COMPLIANCE_UNVERIFIED — TWSE terms pages returned 404/Swagger",
    )


# ── 20D Cluster Readiness (live query) ────────────────────────────────────────

@dataclass
class TwentyDCluster:
    cluster_id: str
    execution_dates: List[str]
    signal_count: int
    exit_td_estimate: str
    exit_td_in_db: str
    db_max_date: str
    td_available_from_first_exec: int
    td_missing: int
    fwd_return_computed: int
    readiness: str
    auth02_status: str
    blocker: str


def build_twenty_d_clusters(db_path: str = "data/platform.db") -> List[TwentyDCluster]:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("SELECT date FROM daily_prices WHERE stock_id='0050' ORDER BY date")
    tdays = [r[0] for r in cur.fetchall()]
    day_idx = {d: i for i, d in enumerate(tdays)}
    db_max = tdays[-1] if tdays else "UNKNOWN"

    def exit20(exec_date: str) -> str:
        if exec_date in day_idx:
            i = day_idx[exec_date]
            if i + 20 < len(tdays):
                return tdays[i + 20]
        return "UNKNOWN"

    clusters = []
    for exec_dates, cluster_id in [
        (["2026-10-13", "2026-10-14", "2026-10-16"], "Oct13-16"),
        (["2026-10-21", "2026-10-22"], "Oct21-22"),
        (["2026-10-28"], "Oct28"),
    ]:
        cur.execute(
            f"SELECT COUNT(*) FROM forward_signals WHERE execution_date IN ({','.join(['?']*len(exec_dates))})",
            exec_dates,
        )
        total_signals = cur.fetchone()[0]

        cur.execute(
            f"SELECT COUNT(*) FROM forward_signals WHERE execution_date IN ({','.join(['?']*len(exec_dates))}) AND fwd_return_20d IS NOT NULL",
            exec_dates,
        )
        computed = cur.fetchone()[0]

        exits = {d: exit20(d) for d in exec_dates}
        known = [v for v in exits.values() if v != "UNKNOWN"]
        earliest = min(known) if known else "UNKNOWN"

        first_exec = exec_dates[0]
        td_avail = max(0, day_idx.get(db_max, 0) - day_idx.get(first_exec, 0)) if first_exec in day_idx else 0
        td_missing = max(0, 20 - td_avail)

        if earliest == "UNKNOWN":
            readiness = "20D_DATA_BLOCKED"
            blocker = f"Exit dates unknown — {20 - td_avail} TD beyond DB max. AUTH02 not authorized."
        elif earliest > db_max:
            readiness = "20D_DATA_BLOCKED"
            blocker = f"Exit date {earliest} > db_max {db_max}. AUTH02 not authorized."
        elif computed > 0:
            readiness = "DATA_READY_AND_AUTHORIZED"
            blocker = "None"
        else:
            readiness = "MATURE_DATA_MISSING"
            blocker = "AUTH02 not authorized. Data may be available."

        clusters.append(TwentyDCluster(
            cluster_id=cluster_id,
            execution_dates=exec_dates,
            signal_count=total_signals,
            exit_td_estimate=str(exits),
            exit_td_in_db=earliest if earliest != "UNKNOWN" and earliest <= db_max else "NOT_IN_DB",
            db_max_date=db_max,
            td_available_from_first_exec=td_avail,
            td_missing=td_missing,
            fwd_return_computed=computed,
            readiness=readiness,
            auth02_status="AUTH02_NOT_AUTHORIZED",
            blocker=blocker,
        ))

    conn.close()
    return clusters


# ── Main Report ────────────────────────────────────────────────────────────────

@dataclass
class PatchReleaseGateReport:
    parser_patches: List[ParserPatch]
    volume_unit_contract: VolumeUnitContract
    independent_patches: List[IndependentPatch]
    independence_verification: PatchIndependenceVerification
    historical_repair: HistoricalRepairAnalysis
    twse_pit_universe: TWSEPITUniverse
    stock_month_manifest: List[StockMonthManifestEntry]
    t2_request_budget: T2RequestBudget
    twenty_d_clusters: List[TwentyDCluster]
    parser_patch_verdict: ParserPatchVerdict
    error_patch_verdict: ErrorPatchVerdict
    historical_repair_verdict: HistoricalRepairVerdict
    pit_universe_verdict: PitUniverseVerdict
    manifest_verdict: ManifestVerdict
    t2_compliance_verdict: T2ComplianceVerdict


def build_patch_release_gate_report(db_path: str = "data/platform.db") -> PatchReleaseGateReport:
    return PatchReleaseGateReport(
        parser_patches=build_parser_patches(),
        volume_unit_contract=build_volume_unit_contract(),
        independent_patches=build_independent_patches(),
        independence_verification=verify_patch_independence(),
        historical_repair=build_historical_repair_analysis(),
        twse_pit_universe=build_twse_pit_universe(db_path),
        stock_month_manifest=build_stock_month_manifest(),
        t2_request_budget=build_t2_request_budget(db_path),
        twenty_d_clusters=build_twenty_d_clusters(db_path),
        parser_patch_verdict=ParserPatchVerdict.PARSER_PATCH_READY_FOR_AUTHORIZATION,
        error_patch_verdict=ErrorPatchVerdict.ERROR_PATCH_READY_FOR_AUTHORIZATION,
        historical_repair_verdict=HistoricalRepairVerdict.VOLUME_REPAIR_BLOCKED,
        pit_universe_verdict=PitUniverseVerdict.TWSE_PIT_UNIVERSE_PARTIAL,
        manifest_verdict=ManifestVerdict.T2_MANIFEST_PARTIAL,
        t2_compliance_verdict=T2ComplianceVerdict.T2_COMPLIANCE_UNVERIFIED,
    )
