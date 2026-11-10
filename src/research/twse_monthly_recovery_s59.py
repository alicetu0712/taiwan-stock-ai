"""
TWSE Monthly Recovery & 20D Readiness — Session 59

Part D: TWSE T2 compliance resolution
Part E: TWSE monthly recovery manifest (recalculated)
Part F: 20D data readiness per cluster

Key Findings (S59):
- T2_COMPLIANCE_UNVERIFIED unchanged from S58 (no new terms documentation found)
- PIT universe: 826 TWSE stocks in stocks table; 712 active 4-digit non-ETF in 2026+
- Monthly scope: 2 months (Oct + Nov) × ~712 stocks = ~1424 calls (corrected from S58's 1198)
- Oct13 cluster: execution_dates Oct13/14/16; exit date ~Nov12-16; DATA_BLOCKED (5+ TD missing)
- Oct21-22 cluster: exit ~Nov19-21; NOT_YET_MATURE
- Oct28 cluster: exit ~Nov26-Dec01; NOT_YET_MATURE
- fwd_return_20d = NULL for all 1977 Oct+ signals (no outcomes computed)
- AUTH02 NOT AUTHORIZED — no new computation permitted
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


# ── Enums ──────────────────────────────────────────────────────────────────────

class T2ComplianceVerdict(str, Enum):
    T2_COMPLIANCE_VERIFIED = "T2_COMPLIANCE_VERIFIED"
    T2_COMPLIANCE_PARTIAL = "T2_COMPLIANCE_PARTIAL"
    T2_COMPLIANCE_UNVERIFIED = "T2_COMPLIANCE_UNVERIFIED"
    T2_COMPLIANCE_BLOCKED = "T2_COMPLIANCE_BLOCKED"


class ManifestVerdict(str, Enum):
    T2_RECOVERY_MANIFEST_READY = "T2_RECOVERY_MANIFEST_READY"
    T2_RECOVERY_MANIFEST_PARTIAL = "T2_RECOVERY_MANIFEST_PARTIAL"
    T2_RECOVERY_MANIFEST_BLOCKED = "T2_RECOVERY_MANIFEST_BLOCKED"


class TwentyDReadiness(str, Enum):
    DATA_READY_FOR_AUTH02_REVIEW = "DATA_READY_FOR_AUTH02_REVIEW"
    MATURE_BUT_DATA_MISSING = "MATURE_BUT_DATA_MISSING"
    DATA_BLOCKED = "20D_DATA_BLOCKED"
    NOT_YET_MATURE = "20D_NOT_YET_MATURE"


class ComplianceEvidenceLevel(str, Enum):
    DIRECTLY_CONFIRMED = "DIRECTLY_CONFIRMED"
    VERIFIED_BY_PRACTICE = "VERIFIED_BY_PRACTICE"
    INFERRED_PUBLIC = "INFERRED_PUBLIC"
    UNVERIFIED = "UNVERIFIED"
    CONTRADICTED = "CONTRADICTED"


# ── TWSE T2 Compliance (Part D) ────────────────────────────────────────────────

@dataclass
class ComplianceEvidenceEntry:
    item: str
    finding: str
    url: Optional[str]
    access_date: Optional[str]
    http_status: Optional[str]
    evidence_level: ComplianceEvidenceLevel
    notes: str


def build_compliance_evidence() -> List[ComplianceEvidenceEntry]:
    return [
        ComplianceEvidenceEntry(
            item="TWSE copyright/terms page (English)",
            finding="404 Not Found",
            url="https://www.twse.com.tw/en/about/copyright.html",
            access_date="2026-11-10",
            http_status="404",
            evidence_level=ComplianceEvidenceLevel.UNVERIFIED,
            notes="Tested in S58. URL no longer exists or was never valid.",
        ),
        ComplianceEvidenceEntry(
            item="TWSE copyright/terms page (Chinese)",
            finding="404 Not Found",
            url="https://www.twse.com.tw/rwd/zh/copyright/index.html",
            access_date="2026-11-10",
            http_status="404",
            evidence_level=ComplianceEvidenceLevel.UNVERIFIED,
            notes="Tested in S58. URL not found.",
        ),
        ComplianceEvidenceEntry(
            item="TWSE OpenAPI Swagger UI",
            finding="Swagger UI returned — no policy text",
            url="https://openapi.twse.com.tw/",
            access_date="2026-11-10",
            http_status="200",
            evidence_level=ComplianceEvidenceLevel.UNVERIFIED,
            notes=(
                "Tested in S58. Returns API endpoint documentation. "
                "No terms of service, rate limit, or automated access policy found."
            ),
        ),
        ComplianceEvidenceEntry(
            item="TWSE single-stock endpoint accessibility",
            finding="HTTP 200, returns MONTHLY OHLCV data",
            url="https://www.twse.com.tw/exchangeReport/STOCK_DAY",
            access_date="2026-11-10",
            http_status="200",
            evidence_level=ComplianceEvidenceLevel.VERIFIED_BY_PRACTICE,
            notes=(
                "Confirmed by S50 and S58 pilot (5/5 probes PASS). "
                "Technically accessible ≠ Terms compliant. "
                "HTTP 200 does not constitute permission for bulk automated access."
            ),
        ),
        ComplianceEvidenceEntry(
            item="Rate limit policy",
            finding="UNVERIFIED — no rate limit headers observed",
            url=None,
            access_date="2026-11-10",
            http_status=None,
            evidence_level=ComplianceEvidenceLevel.UNVERIFIED,
            notes=(
                "5 pilot requests did not trigger rate-limit response. "
                "'No rate-limit error observed' ≠ 'No rate limit exists'. "
                "1424 recovery calls at 2s delay = ~48 minutes. "
                "Risk: unknown rate limit may block at scale."
            ),
        ),
        ComplianceEvidenceEntry(
            item="Automated bulk access policy",
            finding="UNVERIFIED",
            url=None,
            access_date="2026-11-10",
            http_status=None,
            evidence_level=ComplianceEvidenceLevel.UNVERIFIED,
            notes=(
                "No explicit policy text found. "
                "Public endpoint widely used by Taiwan fintech ecosystem (inferred). "
                "Formal terms not located. Contact TWSE market data team to confirm."
            ),
        ),
        ComplianceEvidenceEntry(
            item="Alternative acquisition channels",
            finding="Not evaluated in S59",
            url=None,
            access_date="2026-11-10",
            http_status=None,
            evidence_level=ComplianceEvidenceLevel.UNVERIFIED,
            notes=(
                "Options not investigated: official bulk download, licensed provider, "
                "TWSE Market Information System (MIS), government open data portal. "
                "These may offer better terms and reliability than per-stock API calls."
            ),
        ),
    ]


# ── TWSE Request Budget (Part D3) ─────────────────────────────────────────────

@dataclass
class RequestBudgetEntry:
    item: str
    s58_estimate: str
    s59_calculation: str
    source: str
    notes: str


@dataclass
class T2RequestBudget:
    eligible_stocks: int
    months_to_recover: int
    unique_stock_month_requests: int
    existing_cached_responses: int
    net_requests_needed: int
    retry_budget_per_request: int
    delay_seconds: float
    estimated_runtime_min: float
    concurrency: int
    rate_limit_risk: str
    s58_vs_s59_corrections: List[RequestBudgetEntry]


def build_t2_request_budget() -> T2RequestBudget:
    eligible = 712           # active 4-digit non-ETF TWSE in 2026 (from live DB query)
    months = 2               # October 2026 and November 2026
    total_requests = eligible * months   # 1,424
    # S58 had 599 (v8.0 research universe) × 2 = 1,198 → S59 uses 712 (more accurate current)
    # S58's 599 came from S50's sample; S59 uses actual DB count

    corrections = [
        RequestBudgetEntry(
            item="Eligible stock count",
            s58_estimate="599 (v8.0 research universe from S50 sample)",
            s59_calculation="712 (actual active 4-digit non-ETF TWSE stocks in 2026 from DB)",
            source="DB query: INNER JOIN stocks WHERE market=TWSE AND date >= 2026-08-01",
            notes=(
                "599 was S50's heuristic count of 4-digit numeric stocks. "
                "712 reflects the actual DB-verified active universe. "
                "Full TWSE ordinary stock count in stocks table: 826. "
                "712 = active in recent 90 days (Aug-Nov 2026)."
            ),
        ),
        RequestBudgetEntry(
            item="Total requests",
            s58_estimate="1,198 (599 × 2 months)",
            s59_calculation="1,424 (712 × 2 months)",
            source="S59 live DB query",
            notes="Still one request per stock-month. Monthly API semantics confirmed.",
        ),
        RequestBudgetEntry(
            item="Runtime estimate",
            s58_estimate="~40 min (1,198 × 2s / 60)",
            s59_calculation="~47 min (1,424 × 2s / 60)",
            source="S59 calculation",
            notes="Negligible difference. Both under 1 hour.",
        ),
        RequestBudgetEntry(
            item="Existing cached responses",
            s58_estimate="Not assessed",
            s59_calculation="23 records across 6 dates (from manifest, not cached API responses)",
            source="S58 recovery manifest",
            notes=(
                "23 manifest records represent parsed data from 10 API calls, "
                "not full month caches. No stock-month response cache exists."
            ),
        ),
    ]

    return T2RequestBudget(
        eligible_stocks=eligible,
        months_to_recover=months,
        unique_stock_month_requests=total_requests,
        existing_cached_responses=0,     # no full month caches
        net_requests_needed=total_requests,
        retry_budget_per_request=3,
        delay_seconds=2.0,
        estimated_runtime_min=round(total_requests * 2.0 / 60, 1),
        concurrency=1,
        rate_limit_risk=(
            "UNKNOWN — rate limit policy unverified. "
            "Stop condition: HTTP 429 / 5+ consecutive failures. "
            "1424 × 2s sequential = ~47 min. Well within typical daily API budgets."
        ),
        s58_vs_s59_corrections=corrections,
    )


# ── Monthly Recovery Manifest (Part E) ────────────────────────────────────────

@dataclass
class StockMonthRequest:
    stock_id: str
    exchange: str
    security_type: str
    request_month: str           # YYYYMM
    required_dates: List[str]
    existing_in_db: bool
    ohlcv_verified: bool
    volume_verified: bool
    source_session: Optional[str]
    authorization_status: str
    notes: str


def build_stock_month_manifest() -> List[StockMonthRequest]:
    """
    Minimal manifest: 10 known stock-month combinations with verified data from S50/S58.
    Full manifest (1424 entries) would require AUTH01-authorized full retrieval.
    """
    # Pilot-verified entries
    verified_entries = [
        # October month (Oct29/Oct30 targets)
        StockMonthRequest(
            stock_id="2330", exchange="TWSE", security_type="ordinary",
            request_month="202610",
            required_dates=["2026-10-29", "2026-10-30"],
            existing_in_db=False,
            ohlcv_verified=True, volume_verified=True,
            source_session="S58 P01 / S50",
            authorization_status="AUTH01_PENDING",
            notes="Oct29: O=2420/H=2425/L=2390/C=2415/V=18.4M; Oct30: O=2380/H=2380/L=2360/C=2370/V=36.6M",
        ),
        StockMonthRequest(
            stock_id="2454", exchange="TWSE", security_type="ordinary",
            request_month="202610",
            required_dates=["2026-10-29", "2026-10-30"],
            existing_in_db=False,
            ohlcv_verified=True, volume_verified=True,
            source_session="S58 P03",
            authorization_status="AUTH01_PENDING",
            notes="Oct29: O=4205/H=4225/L=4000/C=4045/V=6.9M; Oct30: O=3820/H=3990/L=3805/C=3915/V=13M",
        ),
        StockMonthRequest(
            stock_id="1301", exchange="TWSE", security_type="ordinary",
            request_month="202610",
            required_dates=["2026-10-29", "2026-10-30"],
            existing_in_db=False,
            ohlcv_verified=True, volume_verified=True,
            source_session="S58 P04",
            authorization_status="AUTH01_PENDING",
            notes="Oct29: O=75.3/H=76.1/L=73.8/C=73.9/V=19.1M; Oct30: O=72.2/H=72.8/L=70.3/C=72.5/V=25.2M",
        ),
        # November month (Nov02/03/06/09 targets)
        StockMonthRequest(
            stock_id="2317", exchange="TWSE", security_type="ordinary",
            request_month="202611",
            required_dates=["2026-11-02", "2026-11-03", "2026-11-06", "2026-11-09"],
            existing_in_db=False,
            ohlcv_verified=True, volume_verified=True,
            source_session="S58 P02",
            authorization_status="AUTH01_PENDING",
            notes="Nov03 close=245.5 CONFIRMED. Nov06/09 FULL OHLCV. Nov02: O=244.5/C=251/V=50M",
        ),
        StockMonthRequest(
            stock_id="2882", exchange="TWSE", security_type="ordinary",
            request_month="202611",
            required_dates=["2026-11-02", "2026-11-03", "2026-11-06", "2026-11-09"],
            existing_in_db=False,
            ohlcv_verified=True, volume_verified=True,
            source_session="S58 P05",
            authorization_status="AUTH01_PENDING",
            notes="Nov02: O=117/C=116/V=28M; Nov03: O=116/C=113/V=30M; Nov06/09: FULL OHLCV",
        ),
    ]

    # Representative unverified (would need actual retrieval)
    unverified_examples = [
        StockMonthRequest(
            stock_id="1101", exchange="TWSE", security_type="ordinary",
            request_month="202610",
            required_dates=["2026-10-29", "2026-10-30"],
            existing_in_db=False,
            ohlcv_verified=False, volume_verified=False,
            source_session=None,
            authorization_status="AUTH01_PENDING — retrieval not yet authorized",
            notes="In stocks table with market=TWSE. Has data for other dates. Gap dates missing.",
        ),
        StockMonthRequest(
            stock_id="2002", exchange="TWSE", security_type="ordinary",
            request_month="202611",
            required_dates=["2026-11-02", "2026-11-03", "2026-11-06", "2026-11-09"],
            existing_in_db=False,
            ohlcv_verified=False, volume_verified=False,
            source_session=None,
            authorization_status="AUTH01_PENDING — retrieval not yet authorized",
            notes="Representative of ~707 unverified TWSE stocks needing retrieval.",
        ),
    ]

    return verified_entries + unverified_examples


@dataclass
class CoverageEstimate:
    gap_date: str
    existing_rows: int           # from live DB (read-only query)
    manifest_verified_rows: int  # from S58 manifest
    universe_denominator: int
    coverage_before_pct: float
    coverage_after_manifest_pct: float
    full_t2_estimate_pct: float
    qg_before: str
    qg_after_full_t2: str
    authorization_needed: str


def build_coverage_estimates(db_path: str = "data/platform.db") -> List[CoverageEstimate]:
    gap_dates = [
        ("2026-10-29", 7), ("2026-10-30", 3), ("2026-11-02", 3),
        ("2026-11-03", 2), ("2026-11-06", 4), ("2026-11-09", 4),
    ]
    universe = 712  # active TWSE stocks (S59 corrected)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    results = []

    for d, manifest_rows in gap_dates:
        cur.execute(
            "SELECT COUNT(*) FROM daily_prices WHERE date=? AND stock_id!='0050'", (d,)
        )
        existing = cur.fetchone()[0]

        cov_before = round(existing / universe * 100, 2)
        cov_after_manifest = round((existing + manifest_rows) / universe * 100, 2)
        cov_full_t2 = 100.0  # full recovery covers all

        results.append(CoverageEstimate(
            gap_date=d,
            existing_rows=existing,
            manifest_verified_rows=manifest_rows,
            universe_denominator=universe,
            coverage_before_pct=cov_before,
            coverage_after_manifest_pct=cov_after_manifest,
            full_t2_estimate_pct=cov_full_t2,
            qg_before="FAIL" if cov_before < 95 else "PASS",
            qg_after_full_t2="PASS_LIKELY",
            authorization_needed="AUTH01",
        ))

    conn.close()
    return results


# ── 20D Data Readiness (Part F) ───────────────────────────────────────────────

@dataclass
class TwentyDClusterDetail:
    cluster_id: str
    trade_dates: List[str]
    execution_dates: List[str]
    signal_counts: dict            # execution_date → count
    total_signals: int
    exit_td: int
    exit_date_estimates: dict      # execution_date → estimated exit date
    earliest_exit: str
    latest_exit: str
    db_max_date: str
    td_in_db_from_earliest_exec: int
    td_missing: int
    entry_prices_available: bool
    exit_prices_in_db: bool
    benchmark_exit_in_db: bool
    fwd_return_computed: int       # count with non-NULL fwd_return_20d
    readiness: TwentyDReadiness
    authorization_status: str
    auth02_scope: str
    notes: str


def build_twenty_d_clusters_live(db_path: str = "data/platform.db") -> List[TwentyDClusterDetail]:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Get 0050 trading days for counting
    cur.execute("SELECT date FROM daily_prices WHERE stock_id='0050' ORDER BY date")
    all_trading_days = [r[0] for r in cur.fetchall()]
    day_index = {d: i for i, d in enumerate(all_trading_days)}

    db_max = all_trading_days[-1] if all_trading_days else "UNKNOWN"

    # Oct13 cluster
    cur.execute("""SELECT execution_date, COUNT(*) FROM forward_signals
                   WHERE execution_date IN ('2026-10-13','2026-10-14','2026-10-16')
                   GROUP BY execution_date""")
    oct13_counts = dict(cur.fetchall())

    cur.execute("""SELECT COUNT(*) FROM forward_signals
                   WHERE execution_date IN ('2026-10-13','2026-10-14','2026-10-16')
                   AND fwd_return_20d IS NOT NULL""")
    oct13_computed = cur.fetchone()[0]

    def td20_exit(exec_date: str) -> str:
        if exec_date in day_index:
            idx = day_index[exec_date]
            if idx + 20 < len(all_trading_days):
                return all_trading_days[idx + 20]
        return "UNKNOWN"

    oct13_exits = {d: td20_exit(d) for d in ["2026-10-13", "2026-10-14", "2026-10-16"]}
    known_oct13 = [v for v in oct13_exits.values() if v != "UNKNOWN"]
    earliest_oct13 = min(known_oct13) if known_oct13 else "UNKNOWN"
    latest_oct13 = max(known_oct13) if known_oct13 else "UNKNOWN"

    # Count TD available from earliest execution
    idx_first = day_index.get("2026-10-13", 0)
    td_avail = max(0, day_index.get(db_max, 0) - idx_first)

    oct13_cluster = TwentyDClusterDetail(
        cluster_id="Oct13-16",
        trade_dates=["2026-10-12", "2026-10-13", "2026-10-14"],
        execution_dates=["2026-10-13", "2026-10-14", "2026-10-16"],
        signal_counts=oct13_counts,
        total_signals=sum(oct13_counts.values()),
        exit_td=20,
        exit_date_estimates=oct13_exits,
        earliest_exit=earliest_oct13,
        latest_exit=latest_oct13,
        db_max_date=db_max,
        td_in_db_from_earliest_exec=td_avail,
        td_missing=max(0, 20 - td_avail),
        entry_prices_available=True,   # execution_price populated for all 1091
        exit_prices_in_db=(earliest_oct13 != "UNKNOWN" and earliest_oct13 <= db_max),
        benchmark_exit_in_db=(earliest_oct13 != "UNKNOWN" and db_max >= earliest_oct13),
        fwd_return_computed=oct13_computed,
        readiness=(
            TwentyDReadiness.DATA_BLOCKED
            if earliest_oct13 == "UNKNOWN" or earliest_oct13 > db_max
            else TwentyDReadiness.MATURE_BUT_DATA_MISSING
        ),
        authorization_status="AUTH02_NOT_AUTHORIZED",
        auth02_scope=(
            f"Eligible: {sum(oct13_counts.values())} signals "
            f"(exec_date in Oct13/14/16). "
            f"Exit dates: {oct13_exits}. "
            f"Entry prices: execution_price in forward_signals. "
            f"Exit prices: daily_prices.close at exit_date for each stock. "
            f"Benchmark: 0050 close at same exit_date. "
            f"Calculation: (exit_close - exec_price) / exec_price. "
            f"Alpha: signal_return - benchmark_return. "
            f"Output: fwd_return_20d, alpha_20d columns in forward_signals."
        ),
        notes=(
            f"db_max={db_max}. earliest_exit={earliest_oct13}. "
            f"Exit prices in DB: {earliest_oct13 != 'UNKNOWN' and earliest_oct13 <= db_max}. "
            f"TD available from Oct13: {td_avail}. "
            f"TD missing: {max(0, 20 - td_avail)}. "
            "Even with AUTH02, cannot compute until exit prices are in daily_prices."
        ),
    )

    # Oct21-22 cluster
    cur.execute("""SELECT execution_date, COUNT(*) FROM forward_signals
                   WHERE execution_date IN ('2026-10-21','2026-10-22')
                   GROUP BY execution_date""")
    oct22_counts = dict(cur.fetchall())
    oct22_exits = {d: td20_exit(d) for d in ["2026-10-21", "2026-10-22"]}
    known_oct22 = [v for v in oct22_exits.values() if v != "UNKNOWN"]
    earliest_oct22 = min(known_oct22) if known_oct22 else "UNKNOWN"
    latest_oct22 = max(known_oct22) if known_oct22 else "UNKNOWN"
    idx22 = day_index.get("2026-10-21", 0)
    td_avail22 = max(0, day_index.get(db_max, 0) - idx22)

    oct22_cluster = TwentyDClusterDetail(
        cluster_id="Oct21-22",
        trade_dates=["2026-10-20", "2026-10-21"],
        execution_dates=["2026-10-21", "2026-10-22"],
        signal_counts=oct22_counts,
        total_signals=sum(oct22_counts.values()),
        exit_td=20,
        exit_date_estimates=oct22_exits,
        earliest_exit=earliest_oct22,
        latest_exit=latest_oct22,
        db_max_date=db_max,
        td_in_db_from_earliest_exec=td_avail22,
        td_missing=max(0, 20 - td_avail22),
        entry_prices_available=True,
        exit_prices_in_db=(earliest_oct22 != "UNKNOWN" and earliest_oct22 <= db_max),
        benchmark_exit_in_db=False,
        fwd_return_computed=0,
        readiness=TwentyDReadiness.NOT_YET_MATURE,
        authorization_status="AUTH02_NOT_AUTHORIZED",
        auth02_scope=(
            f"{sum(oct22_counts.values())} signals. "
            f"Exit dates: {oct22_exits}. Exit prices NOT in DB."
        ),
        notes=f"Exit ~{earliest_oct22}. db_max={db_max}. {max(0, 20-td_avail22)} TD missing.",
    )

    # Oct28 cluster
    cur.execute("""SELECT execution_date, COUNT(*) FROM forward_signals
                   WHERE execution_date = '2026-10-28' GROUP BY execution_date""")
    oct28_counts = dict(cur.fetchall())
    oct28_exit = td20_exit("2026-10-28")
    idx28 = day_index.get("2026-10-28", 0)
    td_avail28 = max(0, day_index.get(db_max, 0) - idx28)

    oct28_cluster = TwentyDClusterDetail(
        cluster_id="Oct28",
        trade_dates=["2026-10-27"],
        execution_dates=["2026-10-28"],
        signal_counts=oct28_counts,
        total_signals=sum(oct28_counts.values()),
        exit_td=20,
        exit_date_estimates={"2026-10-28": oct28_exit},
        earliest_exit=oct28_exit,
        latest_exit=oct28_exit,
        db_max_date=db_max,
        td_in_db_from_earliest_exec=td_avail28,
        td_missing=max(0, 20 - td_avail28),
        entry_prices_available=True,
        exit_prices_in_db=(oct28_exit <= db_max if oct28_exit != "UNKNOWN" else False),
        benchmark_exit_in_db=False,
        fwd_return_computed=0,
        readiness=TwentyDReadiness.NOT_YET_MATURE,
        authorization_status="AUTH02_NOT_AUTHORIZED",
        auth02_scope=f"{sum(oct28_counts.values())} signals. Exit ~{oct28_exit}.",
        notes=f"Exit ~{oct28_exit}. db_max={db_max}. {max(0, 20-td_avail28)} TD missing.",
    )

    conn.close()
    return [oct13_cluster, oct22_cluster, oct28_cluster]


# ── 20D False Deadline Note ────────────────────────────────────────────────────

@dataclass
class TwentyDDeadlineAnalysis:
    is_nov12_a_hard_deadline: bool
    rationale: str
    what_happens_after_nov12: str
    recommendation: str


def build_deadline_analysis() -> TwentyDDeadlineAnalysis:
    return TwentyDDeadlineAnalysis(
        is_nov12_a_hard_deadline=False,
        rationale=(
            "Nov12 is the 20TD exit DATE, not an expiry date for the analysis. "
            "If exit prices for Nov12 are eventually backfilled into daily_prices, "
            "the 20D return computation can still be executed. "
            "The data quality concern is that more time has passed → "
            "more time for corporate actions, delistings, or index changes. "
            "These require additional corporate action adjustment. "
            "However, the fundamental computation is still valid."
        ),
        what_happens_after_nov12=(
            "After Nov12: exit dates are in the past. "
            "The 20D outcome is retrospective but was not known at the time of execution "
            "(NEXT_OPEN entry), so it retains forward-looking analytical value. "
            "The key governance requirement is AUTH02 — not the calendar date."
        ),
        recommendation=(
            "Do NOT skip data validation because Nov12 is approaching. "
            "AUTH02 authorization is the binding constraint, not Nov12. "
            "Prioritize: (1) pipeline recovery to populate Nov12 data, "
            "(2) AUTH02 authorization review, (3) execute with verified data."
        ),
    )


# ── Main Reports ───────────────────────────────────────────────────────────────

@dataclass
class T2ComplianceReport:
    compliance_evidence: List[ComplianceEvidenceEntry]
    request_budget: T2RequestBudget
    compliance_verdict: T2ComplianceVerdict
    not_authorized: bool
    next_steps: List[str]


@dataclass
class MonthlyRecoveryReport:
    stock_month_manifest: List[StockMonthRequest]
    coverage_estimates: List[CoverageEstimate]
    manifest_verdict: ManifestVerdict
    not_deployed: bool


@dataclass
class TwentyDReadinessReport:
    clusters: List[TwentyDClusterDetail]
    deadline_analysis: TwentyDDeadlineAnalysis
    overall_readiness: TwentyDReadiness
    auth02_not_authorized: bool
    genuine_prospective_n: int


def build_t2_compliance_report() -> T2ComplianceReport:
    return T2ComplianceReport(
        compliance_evidence=build_compliance_evidence(),
        request_budget=build_t2_request_budget(),
        compliance_verdict=T2ComplianceVerdict.T2_COMPLIANCE_UNVERIFIED,
        not_authorized=True,
        next_steps=[
            "Contact TWSE market data team directly for formal API terms",
            "Search TWSE website for 'API使用規範' or '資料使用授權'",
            "Evaluate official bulk download option (TWSE Market Information System)",
            "Consider licensed data provider for guaranteed compliance",
            "Obtain AUTH01 authorization from user AFTER compliance confirmation",
        ],
    )


def build_monthly_recovery_report(db_path: str = "data/platform.db") -> MonthlyRecoveryReport:
    manifest = build_stock_month_manifest()
    coverage = build_coverage_estimates(db_path)
    return MonthlyRecoveryReport(
        stock_month_manifest=manifest,
        coverage_estimates=coverage,
        manifest_verdict=ManifestVerdict.T2_RECOVERY_MANIFEST_PARTIAL,
        not_deployed=True,
    )


def build_twenty_d_readiness_report(db_path: str = "data/platform.db") -> TwentyDReadinessReport:
    clusters = build_twenty_d_clusters_live(db_path)
    deadline = build_deadline_analysis()
    return TwentyDReadinessReport(
        clusters=clusters,
        deadline_analysis=deadline,
        overall_readiness=TwentyDReadiness.DATA_BLOCKED,
        auth02_not_authorized=True,
        genuine_prospective_n=0,
    )
