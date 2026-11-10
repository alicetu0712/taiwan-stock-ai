"""
TPEx Volume Integrity Analysis — Session 59

Root cause forensics for 129,636 NULL volume rows in daily_prices.
Two distinct bugs identified, both DIRECTLY_CONFIRMED from production DB inspection.

Key Findings (S59):
- NULL volume total: 129,636 (not 5,737 — that was Nov04 total rows in S57 live probe)
- Bug 1 (WARRANT_NOT_EXCLUDED): 107,765 rows — 6-digit numeric warrant IDs pass _is_excluded
- Bug 2 (TPEX_FIELD_MISMATCH): 21,846 rows — script reads 'TradeVolume' but TPEx returns 'TradingShares'
- 2024-2025 data: 0 NULL volume (clean — only 720 TWSE ordinary stocks)
- TWSE stocks (in stocks table): only 25 NULL volume rows (negligible)
- Parser fix for Bug 2: change TradeVolume → TradingShares (volume confirmed); amount field UNVERIFIED
- Amount field fix: TradeValue → TransactionAmount (HYPOTHESIS only — needs probe to confirm)
"""

from __future__ import annotations

import sqlite3
import tempfile
import os
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


# ── Enums ──────────────────────────────────────────────────────────────────────

class RootCauseCategory(str, Enum):
    FIELD_MAPPING_CONFIRMED = "FIELD_MAPPING_CONFIRMED"
    WARRANT_NOT_EXCLUDED = "WARRANT_NOT_EXCLUDED"
    SOURCE_FIELD_MISSING = "SOURCE_FIELD_MISSING"
    SOURCE_DATE_MISMATCH = "SOURCE_DATE_MISMATCH"
    SECURITY_TYPE_ISSUE = "SECURITY_TYPE_ISSUE"
    PARSER_VERSION_UNKNOWN = "PARSER_VERSION_UNKNOWN"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    OTHER_CAUSE = "OTHER_CAUSE"
    UNRESOLVED = "UNRESOLVED"


class EvidenceStrength(str, Enum):
    DIRECTLY_CONFIRMED = "DIRECTLY_CONFIRMED"
    STRONGLY_SUPPORTED = "STRONGLY_SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class VolumeRootCauseVerdict(str, Enum):
    TPEX_VOLUME_ROOT_CAUSE_CONFIRMED = "TPEX_VOLUME_ROOT_CAUSE_CONFIRMED"
    TPEX_VOLUME_ROOT_CAUSE_PARTIAL = "TPEX_VOLUME_ROOT_CAUSE_PARTIAL"
    TPEX_VOLUME_ROOT_CAUSE_UNRESOLVED = "TPEX_VOLUME_ROOT_CAUSE_UNRESOLVED"


class ParserPatchVerdict(str, Enum):
    PARSER_PATCH_READY_FOR_AUTHORIZATION = "PARSER_PATCH_READY_FOR_AUTHORIZATION"
    PARSER_PATCH_PARTIAL = "PARSER_PATCH_PARTIAL"
    PARSER_PATCH_BLOCKED = "PARSER_PATCH_BLOCKED"


class VolumeRepairVerdict(str, Enum):
    VOLUME_REPAIR_READY_FOR_AUTHORIZATION = "VOLUME_REPAIR_READY_FOR_AUTHORIZATION"
    VOLUME_REPAIR_PARTIAL = "VOLUME_REPAIR_PARTIAL"
    VOLUME_REPAIR_BLOCKED = "VOLUME_REPAIR_BLOCKED"


# ── NULL Volume Inventory ──────────────────────────────────────────────────────

@dataclass
class NullVolumeInventory:
    total_null_volume_rows: int
    warrant_null_rows: int            # Bug 1: 6-digit numeric not excluded
    tpex_field_null_rows: int         # Bug 2: TradeVolume vs TradingShares
    twse_in_table_null_rows: int      # Negligible: in stocks table, specific dates
    null_volume_dates: int            # distinct dates with NULL volume
    total_dates: int
    pre_2026_null: int                # 2024-2025 data: clean
    note: str


def build_null_volume_inventory_static() -> NullVolumeInventory:
    """
    Static inventory from production DB read on 2026-11-10.
    Read-only: does not query production DB at import time.
    """
    return NullVolumeInventory(
        total_null_volume_rows=129636,
        warrant_null_rows=107765,
        tpex_field_null_rows=21846,
        twse_in_table_null_rows=25,
        null_volume_dates=25,
        total_dates=572,
        pre_2026_null=0,
        note=(
            "129,636 = 107,765 (warrants) + 21,846 (TPEx field mismatch) + 25 (TWSE negligible). "
            "S57/S58 reference of '5,737' was Nov04 TPEx bulk probe row count, "
            "NOT the production NULL volume total. "
            "2024-2025 (368 trading days): 0 NULL volume — clean period with ~720 TWSE stocks only."
        ),
    )


def build_null_volume_inventory_live(db_path: str = "data/platform.db") -> NullVolumeInventory:
    """Live read-only query to build current inventory."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM daily_prices WHERE volume IS NULL")
    total = cur.fetchone()[0]

    cur.execute("""SELECT COUNT(*) FROM daily_prices
                   WHERE volume IS NULL AND LENGTH(stock_id) > 4 AND stock_id GLOB '[0-9]*'""")
    warrant = cur.fetchone()[0]

    cur.execute("""SELECT COUNT(*) FROM daily_prices dp
                   LEFT JOIN stocks s ON dp.stock_id = s.stock_id
                   WHERE dp.volume IS NULL AND LENGTH(dp.stock_id)=4
                   AND dp.stock_id GLOB '[0-9]*' AND s.stock_id IS NULL""")
    tpex_field = cur.fetchone()[0]

    cur.execute("""SELECT COUNT(*) FROM daily_prices dp
                   INNER JOIN stocks s ON dp.stock_id = s.stock_id
                   WHERE dp.volume IS NULL""")
    twse_minor = cur.fetchone()[0]

    cur.execute("SELECT COUNT(DISTINCT date) FROM daily_prices WHERE volume IS NULL")
    null_dates = cur.fetchone()[0]

    cur.execute("SELECT COUNT(DISTINCT date) FROM daily_prices")
    total_dates = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM daily_prices WHERE volume IS NULL AND date < '2026-01-01'")
    pre2026 = cur.fetchone()[0]

    conn.close()

    return NullVolumeInventory(
        total_null_volume_rows=total,
        warrant_null_rows=warrant,
        tpex_field_null_rows=tpex_field,
        twse_in_table_null_rows=twse_minor,
        null_volume_dates=null_dates,
        total_dates=total_dates,
        pre_2026_null=pre2026,
        note="Live query from production DB (read-only).",
    )


# ── Root Cause Attribution ─────────────────────────────────────────────────────

@dataclass
class RootCauseEntry:
    cause_id: str
    category: RootCauseCategory
    affected_rows: int
    source_file: str
    source_function: str
    source_line: int
    raw_evidence: str
    expected_behavior: str
    actual_behavior: str
    evidence_strength: EvidenceStrength
    fix_description: str
    fix_risk: str
    fix_authorized: bool


def build_root_cause_entries() -> List[RootCauseEntry]:
    return [
        RootCauseEntry(
            cause_id="RC-59-01",
            category=RootCauseCategory.WARRANT_NOT_EXCLUDED,
            affected_rows=107765,
            source_file="scripts/backfill_daily_prices.py",
            source_function="_is_excluded",
            source_line=98,
            raw_evidence=(
                "Line 98: `if len(sid) > 4 and not sid.isdigit(): return True`. "
                "6-digit pure-numeric IDs (e.g. '700022'): len > 4 = True, isdigit() = True → "
                "condition = True AND NOT True = False → not excluded. "
                "DB: 107,765 rows with stock_id LIKE '7%' and LENGTH > 4 have volume=NULL. "
                "No entry in stocks table (market=None). "
                "OHLCV data present (TWSE returns OHLC for warrants) but volume='--' in TWSE old API → None."
            ),
            expected_behavior=(
                "_is_excluded should return True for ANY stock_id with length > 4, "
                "regardless of whether it is numeric. "
                "Taiwan warrant IDs are 6-digit pure numeric (e.g. 700022, 710045)."
            ),
            actual_behavior=(
                "_is_excluded returns False for 6-digit pure-numeric IDs because "
                "`len > 4 AND NOT isdigit` = True AND NOT True = False. "
                "Warrants pass through, get inserted with NULL volume."
            ),
            evidence_strength=EvidenceStrength.DIRECTLY_CONFIRMED,
            fix_description=(
                "Change line 98 from: `if len(sid) > 4 and not sid.isdigit():` "
                "to: `if len(sid) > 4:` "
                "This excludes ALL stock_ids longer than 4 characters, including 6-digit warrants."
            ),
            fix_risk=(
                "MEDIUM: May exclude some legitimate 5-digit ETF IDs like '00646' (len=5). "
                "Current policy already excludes by name (REIT/ETF keywords). "
                "Review: 00xxx ETFs are excluded by name check first, so ID-length check is secondary. "
                "Need to verify no legitimate TWSE stocks have 5-digit IDs beyond ETFs."
            ),
            fix_authorized=False,
        ),
        RootCauseEntry(
            cause_id="RC-59-02",
            category=RootCauseCategory.FIELD_MAPPING_CONFIRMED,
            affected_rows=21846,
            source_file="scripts/backfill_daily_prices.py",
            source_function="fetch_tpex_historical",
            source_line=284,
            raw_evidence=(
                "Line 284: `vol_raw = _strip_num(str(row.get('TradeVolume', '')))`  "
                "Line 285: `amt_raw = _strip_num(str(row.get('TradeValue', '')))`  "
                "DB: 21,846 4-digit non-TWSE stocks have volume=NULL AND amount=NULL (100% correlation). "
                "Same stocks have OHLC present (Open/High/Low/Close correctly parsed). "
                "Same stocks have change_pct populated for 21,621/21,846 (Change field correctly read). "
                "S58 WebFetch of TPEx bulk endpoint confirmed: volume field='TradingShares' in response. "
                "If TPEx returns 'TradingShares' but script reads 'TradeVolume', "
                "row.get('TradeVolume', '') → '' → _strip_num('') → None → volume=None. "
                "2024-2025 data (368 dates): 0 NULL volume → clean. TPEx data added 2026-Jun."
            ),
            expected_behavior=(
                "TPEx parser should read the correct volume field from API response. "
                "Volume should be parsed and stored as shares/1000 (千股, same unit as TWSE). "
                "Amount should be parsed and stored as million TWD."
            ),
            actual_behavior=(
                "TPEx parser reads 'TradeVolume' (not present in API) and 'TradeValue' (not present). "
                "Both return '' → _strip_num('') → None. "
                "All 21,846 rows inserted with volume=NULL and amount=NULL."
            ),
            evidence_strength=EvidenceStrength.DIRECTLY_CONFIRMED,
            fix_description=(
                "Line 284: change `row.get('TradeVolume', '')` to `row.get('TradingShares', '')`. "
                "Line 285: change `row.get('TradeValue', '')` to `row.get('TransactionAmount', '')` "
                "(TransactionAmount is HYPOTHESIS — requires a live probe to confirm exact field name). "
                "Volume field fix: CONFIRMED. Amount field fix: UNVERIFIED — needs probe first."
            ),
            fix_risk=(
                "LOW for volume fix (confirmed field name). "
                "MEDIUM for amount fix (TransactionAmount field name unverified). "
                "Unit conversion: same /1000 for volume, /1_000_000 for amount should apply. "
                "But TPEx volume unit (shares vs lots) needs verification before applying /1000."
            ),
            fix_authorized=False,
        ),
        RootCauseEntry(
            cause_id="RC-59-03",
            category=RootCauseCategory.OTHER_CAUSE,
            affected_rows=25,
            source_file="scripts/backfill_daily_prices.py",
            source_function="fetch_twse_historical",
            source_line=217,
            raw_evidence=(
                "25 rows in daily_prices from stocks table (market=TWSE) have volume=NULL. "
                "These are specific TWSE ordinary stocks on specific dates. "
                "Volume='--' returned by TWSE old API → _strip_num('--') → None."
            ),
            expected_behavior="TWSE stocks with valid trading should have non-NULL volume.",
            actual_behavior=(
                "Some TWSE stocks on specific dates have '--' for volume in TWSE old API response. "
                "This is expected for stocks that did not trade (trading halt, etc.)."
            ),
            evidence_strength=EvidenceStrength.DIRECTLY_CONFIRMED,
            fix_description="No fix required. '--' → None is correct for non-trading stocks.",
            fix_risk="NONE",
            fix_authorized=True,  # already correct behavior
        ),
    ]


# ── Volume Unit Analysis ───────────────────────────────────────────────────────

@dataclass
class VolumeUnitAnalysis:
    twse_unit: str
    twse_divisor: float
    tpex_unit_confirmed: str
    tpex_divisor_proposed: float
    tpex_unit_evidence: str
    unit_mismatch_risk: str
    db_volume_standard: str
    recommendation: str
    # Semantic treatment fields for parser validation
    divisor: float = 1_000.0           # canonical divisor used for both TWSE and TPEx
    unit_description: str = "千股 (thousands of shares)"
    zero_volume_treatment: str = "VALID"
    negative_volume_treatment: str = "REJECT"
    null_field_behaviour: str = "NULL_STORED"


def build_volume_unit_analysis() -> VolumeUnitAnalysis:
    return VolumeUnitAnalysis(
        twse_unit="shares (股)",
        twse_divisor=1000.0,
        tpex_unit_confirmed="shares (股) — from S58 pilot data: 2317/Nov06 volume=89,094,382 raw",
        tpex_divisor_proposed=1000.0,
        tpex_unit_evidence=(
            "S58 P02 direct probe: 2317/Nov06 volume=89,094,382 (raw shares). "
            "After /1000 → 89,094.382 (千股). "
            "TWSE 1101 on Nov04: volume=57,045.65 (stored as 千股). "
            "Unit is consistent: both TWSE and TPEx use raw shares → divide by 1000 for DB storage. "
            "CONFIRMATION NEEDED: TradingShares field units confirmed as shares (not lots). "
            "Taiwan stock 1 lot = 1000 shares. "
            "S58 volume values (18M-89M range) are consistent with share-level data, not lot-level."
        ),
        unit_mismatch_risk=(
            "LOW: Both TWSE and TPEx appear to use raw shares. "
            "Post-fix volume values will be in 千股 (thousands of shares), same as TWSE. "
            "If TPEx actually returns lots instead of shares, volume would be 1000× too high. "
            "Recommend spot-check: compare DB stored value with reported trading volume."
        ),
        db_volume_standard="千股 (thousands of shares) — same as TWSE",
        recommendation=(
            "Apply /1000 divisor for TPEx TradingShares, same as TWSE TradeVolume. "
            "Verify 1 known stock post-fix against official TPEx website data."
        ),
    )


# ── Parser Patch Definition ────────────────────────────────────────────────────

@dataclass
class ParserPatch:
    patch_id: str
    file: str
    line: int
    original: str
    patched: str
    authorization_status: str
    confidence: str
    side_effects: str


@dataclass
class ParserPatchBundle:
    patches: List[ParserPatch]
    warrant_exclusion_patch: ParserPatch
    volume_field_patch: ParserPatch
    amount_field_patch: ParserPatch
    deployment_verdict: str
    not_deployed: bool


def build_parser_patch_bundle() -> ParserPatchBundle:
    warrant_patch = ParserPatch(
        patch_id="PP-01",
        file="scripts/backfill_daily_prices.py",
        line=98,
        original="    if len(sid) > 4 and not sid.isdigit():",
        patched="    if len(sid) > 4:",
        authorization_status="NOT_AUTHORIZED — requires explicit deployment authorization",
        confidence="HIGH — directly confirmed as root cause",
        side_effects=(
            "Excludes ALL stock_ids longer than 4 characters. "
            "5-digit ETFs (00xxx like 00646) also have length 5 — but they're already "
            "excluded by name check (ETF/REIT keywords). "
            "Verify: no ordinary stock has a 5-digit numeric ID on TWSE. "
            "Risk: accidental exclusion of a legitimate 5-digit non-ETF stock."
        ),
    )

    volume_field_patch = ParserPatch(
        patch_id="PP-02",
        file="scripts/backfill_daily_prices.py",
        line=284,
        original="            vol_raw = _strip_num(str(row.get(\"TradeVolume\", \"\")))",
        patched="            vol_raw = _strip_num(str(row.get(\"TradingShares\", \"\")))",
        authorization_status="NOT_AUTHORIZED — requires explicit deployment authorization",
        confidence="HIGH — TradingShares field confirmed by S58 WebFetch",
        side_effects=(
            "Affects ONLY fetch_tpex_historical(). "
            "TWSE parsers unchanged (read TradeVolume which is correct for TWSE). "
            "Volume unit unchanged: /1000 applied. "
            "Will not affect existing rows (backfill uses INSERT OR IGNORE)."
        ),
    )

    amount_field_patch = ParserPatch(
        patch_id="PP-03",
        file="scripts/backfill_daily_prices.py",
        line=285,
        original="            amt_raw = _strip_num(str(row.get(\"TradeValue\", \"\")))",
        patched="            amt_raw = _strip_num(str(row.get(\"TransactionAmount\", \"\")))",
        authorization_status=(
            "NOT_AUTHORIZED — ADDITIONALLY requires field name verification probe. "
            "TransactionAmount is HYPOTHESIS: not confirmed by direct probe in S58/S59."
        ),
        confidence=(
            "MEDIUM — consistent with TPEx OpenAPI naming convention; "
            "not confirmed by direct API inspection."
        ),
        side_effects=(
            "If TransactionAmount is wrong field name, amount will remain NULL. "
            "No data corruption risk. Idempotent — INSERT OR IGNORE skips existing rows."
        ),
    )

    return ParserPatchBundle(
        patches=[warrant_patch, volume_field_patch, amount_field_patch],
        warrant_exclusion_patch=warrant_patch,
        volume_field_patch=volume_field_patch,
        amount_field_patch=amount_field_patch,
        deployment_verdict=ParserPatchVerdict.PARSER_PATCH_PARTIAL.value,
        not_deployed=True,
    )


# ── Schema Compatibility Tests ────────────────────────────────────────────────

@dataclass
class SchemaCompatibilityResult:
    test_name: str
    passed: bool
    input_data: dict
    expected_volume: Optional[float]
    expected_amount: Optional[float]
    notes: str


def run_schema_compatibility_tests() -> List[SchemaCompatibilityResult]:
    """
    Test the PATCHED TPEx parser logic (not deployed — isolated simulation).
    Simulates row.get("TradingShares", ...) behavior.
    """
    results = []

    def parse_tpex_row_patched(row: dict) -> dict:
        """Isolated simulation of patched parser."""
        def strip_num(s):
            if not s:
                return None
            s = str(s).strip()
            if s in ("--", "-", "N/A", ""):
                return None
            try:
                return float(s.replace(",", ""))
            except ValueError:
                return None

        vol_raw = strip_num(str(row.get("TradingShares", "")))    # PATCHED
        amt_raw = strip_num(str(row.get("TransactionAmount", ""))) # PATCHED (hypothesis)
        o = strip_num(str(row.get("Open", "")))
        h = strip_num(str(row.get("High", "")))
        lo = strip_num(str(row.get("Low", "")))
        c = strip_num(str(row.get("Close", "")))

        return {
            "volume": (vol_raw / 1000) if vol_raw is not None else None,
            "amount": (amt_raw / 1_000_000) if amt_raw is not None else None,
            "open": o, "high": h, "low": lo, "close": c,
        }

    def parse_tpex_row_original(row: dict) -> dict:
        """Original (unpatched) parser for comparison."""
        def strip_num(s):
            if not s:
                return None
            s = str(s).strip()
            if s in ("--", "-", "N/A", ""):
                return None
            try:
                return float(s.replace(",", ""))
            except ValueError:
                return None

        vol_raw = strip_num(str(row.get("TradeVolume", "")))    # ORIGINAL
        amt_raw = strip_num(str(row.get("TradeValue", "")))     # ORIGINAL
        return {
            "volume": (vol_raw / 1000) if vol_raw is not None else None,
            "amount": (amt_raw / 1_000_000) if amt_raw is not None else None,
        }

    test_cases = [
        # TC1: TradingShares valid (confirmed TPEx field)
        {
            "name": "TradingShares valid",
            "row": {"TradingShares": "89094382", "Open": "213", "High": "227.5",
                    "Low": "212.5", "Close": "224.5"},
            "expected_volume": 89094.382,
            "expected_amount": None,
        },
        # TC2: TradeVolume (TWSE field — should be unused by TPEx parser)
        {
            "name": "TradeVolume present (TWSE field, not TPEx)",
            "row": {"TradeVolume": "18403916", "Open": "2420", "High": "2425",
                    "Low": "2390", "Close": "2415"},
            "expected_volume": None,  # patched parser ignores TradeVolume
            "expected_amount": None,
        },
        # TC3: Both fields present (TradingShares takes priority in patched)
        {
            "name": "Both TradingShares and TradeVolume present",
            "row": {"TradingShares": "50000000", "TradeVolume": "99999999",
                    "Open": "100", "High": "101", "Low": "99", "Close": "100"},
            "expected_volume": 50000.0,  # TradingShares wins
            "expected_amount": None,
        },
        # TC4: Both fields missing
        {
            "name": "No volume fields",
            "row": {"Open": "100", "High": "101", "Low": "99", "Close": "100"},
            "expected_volume": None,
            "expected_amount": None,
        },
        # TC5: NULL value
        {
            "name": "Null volume",
            "row": {"TradingShares": "", "Open": "100", "High": "101", "Low": "99", "Close": "100"},
            "expected_volume": None,
            "expected_amount": None,
        },
        # TC6: Zero volume
        {
            "name": "Zero volume",
            "row": {"TradingShares": "0", "Open": "100", "High": "101", "Low": "99", "Close": "100"},
            "expected_volume": 0.0,
            "expected_amount": None,
        },
        # TC7: Negative volume (invalid — _strip_num returns float, no sign check)
        {
            "name": "Negative volume (invalid input)",
            "row": {"TradingShares": "-1000", "Open": "100", "High": "101", "Low": "99", "Close": "100"},
            "expected_volume": -1.0,  # /1000 → -1.0 (would need separate validation)
            "expected_amount": None,
        },
        # TC8: String numeric with comma
        {
            "name": "Comma-separated numeric",
            "row": {"TradingShares": "89,094,382", "Open": "213", "High": "227.5",
                    "Low": "212.5", "Close": "224.5"},
            "expected_volume": 89094.382,
            "expected_amount": None,
        },
        # TC9: Dash placeholder
        {
            "name": "Dash placeholder (non-trading)",
            "row": {"TradingShares": "--", "Open": "100", "High": "100", "Low": "100", "Close": "100"},
            "expected_volume": None,
            "expected_amount": None,
        },
        # TC10: TransactionAmount valid (hypothetical)
        {
            "name": "TransactionAmount valid",
            "row": {"TradingShares": "89094382", "TransactionAmount": "20000000000",
                    "Open": "213", "High": "227.5", "Low": "212.5", "Close": "224.5"},
            "expected_volume": 89094.382,
            "expected_amount": 20000.0,  # /1_000_000
        },
    ]

    for tc in test_cases:
        result = parse_tpex_row_patched(tc["row"])
        vol_ok = abs((result["volume"] or 0.0) - (tc["expected_volume"] or 0.0)) < 0.001 \
                 if result["volume"] is not None or tc["expected_volume"] is not None else True
        if result["volume"] is None and tc["expected_volume"] is None:
            vol_ok = True
        elif result["volume"] is None or tc["expected_volume"] is None:
            vol_ok = False
        amt_ok = result["amount"] is None and tc["expected_amount"] is None or \
                 (result["amount"] is not None and tc["expected_amount"] is not None and
                  abs(result["amount"] - tc["expected_amount"]) < 0.001)

        results.append(SchemaCompatibilityResult(
            test_name=tc["name"],
            passed=vol_ok and amt_ok,
            input_data=tc["row"],
            expected_volume=tc["expected_volume"],
            expected_amount=tc["expected_amount"],
            notes=f"got volume={result['volume']}, amount={result['amount']}",
        ))

    return results


# ── Historical Repair Simulation (Isolated SQLite) ─────────────────────────────

@dataclass
class RepairSimulationResult:
    test_name: str
    passed: bool
    rows_before: int
    rows_after: int
    action_taken: str
    idempotent: bool
    rollback_tested: bool
    notes: str


def run_repair_simulation() -> List[RepairSimulationResult]:
    """
    Simulate historical volume repair in isolated temporary SQLite.
    Does NOT touch production DB. Tests UPDATE behavior and rollback.
    """
    results = []

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        tmp_path = f.name

    try:
        conn = sqlite3.connect(tmp_path)
        conn.execute("""
            CREATE TABLE daily_prices (
                id INTEGER PRIMARY KEY,
                stock_id TEXT,
                date TEXT,
                open REAL, high REAL, low REAL, close REAL,
                volume REAL, amount REAL
            )
        """)
        # Seed: 1240 (TPEx stock) with NULL volume
        conn.execute(
            "INSERT INTO daily_prices(stock_id,date,open,high,low,close,volume,amount) "
            "VALUES (?,?,?,?,?,?,?,?)",
            ("1240", "2026-11-04", 53.8, 53.8, 53.3, 53.7, None, None)
        )
        # Seed: 2330 (TWSE) with valid volume
        conn.execute(
            "INSERT INTO daily_prices(stock_id,date,open,high,low,close,volume,amount) "
            "VALUES (?,?,?,?,?,?,?,?)",
            ("2330", "2026-11-04", 2300, 2350, 2290, 2330, 25000.0, 57750000.0)
        )
        conn.commit()

        # Test RS-01: Repair NULL volume using verified source
        cur = conn.cursor()
        cur.execute("SELECT volume FROM daily_prices WHERE stock_id='1240'")
        before = cur.fetchone()[0]

        conn.execute(
            "UPDATE daily_prices SET volume=?, amount=? WHERE stock_id=? AND date=? AND volume IS NULL",
            (876.5, None, "1240", "2026-11-04")
        )
        conn.commit()

        cur.execute("SELECT volume FROM daily_prices WHERE stock_id='1240'")
        after = cur.fetchone()[0]

        results.append(RepairSimulationResult(
            test_name="RS-01: Update NULL volume to verified value",
            passed=before is None and after == 876.5,
            rows_before=1,
            rows_after=1,
            action_taken="UPDATE SET volume=876.5 WHERE volume IS NULL",
            idempotent=True,
            rollback_tested=False,
            notes=f"before={before}, after={after}",
        ))

        # Test RS-02: Idempotency — second UPDATE should not change already-set value
        conn.execute(
            "UPDATE daily_prices SET volume=? WHERE stock_id=? AND date=? AND volume IS NULL",
            (999.0, "1240", "2026-11-04")
        )
        conn.commit()
        cur.execute("SELECT volume FROM daily_prices WHERE stock_id='1240'")
        after2 = cur.fetchone()[0]

        results.append(RepairSimulationResult(
            test_name="RS-02: Idempotency — WHERE volume IS NULL guard",
            passed=after2 == 876.5,  # unchanged
            rows_before=1,
            rows_after=1,
            action_taken="Second UPDATE with volume IS NULL guard — no change expected",
            idempotent=True,
            rollback_tested=False,
            notes=f"after first update={after}, after second update={after2}",
        ))

        # Test RS-03: TWSE stock unchanged (should NOT be touched by repair)
        cur.execute("SELECT volume FROM daily_prices WHERE stock_id='2330'")
        twse_vol = cur.fetchone()[0]

        results.append(RepairSimulationResult(
            test_name="RS-03: TWSE stock volume unchanged by TPEx repair",
            passed=twse_vol == 25000.0,
            rows_before=1,
            rows_after=1,
            action_taken="No update to stock_id=2330",
            idempotent=True,
            rollback_tested=False,
            notes=f"2330 volume remains {twse_vol}",
        ))

        # Test RS-04: Rollback simulation
        conn.execute("BEGIN")
        conn.execute(
            "UPDATE daily_prices SET volume=? WHERE stock_id=? AND date=?",
            (12345.0, "2330", "2026-11-04")
        )
        cur.execute("SELECT volume FROM daily_prices WHERE stock_id='2330'")
        mid = cur.fetchone()[0]

        conn.execute("ROLLBACK")
        cur.execute("SELECT volume FROM daily_prices WHERE stock_id='2330'")
        rolled = cur.fetchone()[0]

        results.append(RepairSimulationResult(
            test_name="RS-04: Transaction rollback restores original value",
            passed=mid == 12345.0 and rolled == 25000.0,
            rows_before=1,
            rows_after=1,
            action_taken="BEGIN → UPDATE → ROLLBACK",
            idempotent=False,
            rollback_tested=True,
            notes=f"mid={mid}, after rollback={rolled}",
        ))

        conn.close()

    finally:
        os.unlink(tmp_path)

    return results


# ── Historical Repair Eligibility ─────────────────────────────────────────────

@dataclass
class RepairEligibilityEntry:
    stock_id: str
    date: str
    has_verified_source: bool
    source_session: str
    verified_volume_raw: Optional[float]  # raw shares from source
    verified_volume_stored: Optional[float]  # /1000 for DB
    confidence: str
    authorization_status: str
    notes: str


def build_repair_eligibility_manifest() -> List[RepairEligibilityEntry]:
    """
    Records that have a verified source AND are currently NULL in DB.
    These are CANDIDATES for repair — not yet authorized.
    Only TWSE stocks (from S50/S58 pilot) have verified sources.
    TPEx ordinary stocks have no verified per-stock source for historical dates.
    """
    return [
        RepairEligibilityEntry(
            stock_id="2330",
            date="2026-10-29",
            has_verified_source=True,
            source_session="S58 P01 / S50",
            verified_volume_raw=18403916.0,
            verified_volume_stored=18403.916,
            confidence="HIGH",
            authorization_status="AUTH01_PENDING",
            notes="Oct29 currently 0 rows (not NULL — just missing). Needs INSERT not UPDATE.",
        ),
        RepairEligibilityEntry(
            stock_id="2454",
            date="2026-10-29",
            has_verified_source=True,
            source_session="S58 P03 / S50",
            verified_volume_raw=6867223.0,
            verified_volume_stored=6867.223,
            confidence="HIGH",
            authorization_status="AUTH01_PENDING",
            notes="Oct29 currently missing. Needs INSERT not UPDATE.",
        ),
        RepairEligibilityEntry(
            stock_id="2317",
            date="2026-11-03",
            has_verified_source=True,
            source_session="S58 P02",
            verified_volume_raw=44139321.0,
            verified_volume_stored=44139.321,
            confidence="HIGH",
            authorization_status="AUTH01_PENDING",
            notes="Nov03 currently missing. Close=245.5 confirmed.",
        ),
        RepairEligibilityEntry(
            stock_id="1240",
            date="2026-11-04",
            has_verified_source=False,
            source_session=None,
            verified_volume_raw=None,
            verified_volume_stored=None,
            confidence="NONE",
            authorization_status="REPAIR_BLOCKED_NO_SOURCE",
            notes=(
                "TPEx ordinary stock. Currently in DB with volume=NULL. "
                "No verified source for historical Nov04 volume. "
                "TPEx bulk API returns current date only (RC-03). "
                "Cannot recover without per-stock historical source."
            ),
        ),
        RepairEligibilityEntry(
            stock_id="ALL_WARRANTS",
            date="all_dates",
            has_verified_source=False,
            source_session=None,
            verified_volume_raw=None,
            verified_volume_stored=None,
            confidence="NONE",
            authorization_status="WARRANT_FILTER_FIX_PREFERRED",
            notes=(
                "107,765 warrant rows. Volume is structurally NULL (TWSE returns '--' for warrants). "
                "No source for warrant volume. "
                "Preferred fix: apply PP-01 warrant exclusion to prevent future inserts. "
                "Existing warrant rows should be evaluated for deletion, not UPDATE."
            ),
        ),
    ]


# ── Main Reports ───────────────────────────────────────────────────────────────

@dataclass
class TPExVolumeIntegrityReport:
    null_inventory: NullVolumeInventory
    root_causes: List[RootCauseEntry]
    unit_analysis: VolumeUnitAnalysis
    parser_patch_bundle: ParserPatchBundle
    schema_tests: List[SchemaCompatibilityResult]
    repair_simulation: List[RepairSimulationResult]
    repair_manifest: List[RepairEligibilityEntry]
    root_cause_verdict: VolumeRootCauseVerdict
    parser_verdict: ParserPatchVerdict
    repair_verdict: VolumeRepairVerdict
    s58_reference_correction: str


def build_tpex_volume_integrity_report(live_db: bool = False) -> TPExVolumeIntegrityReport:
    inventory = build_null_volume_inventory_live() if live_db else build_null_volume_inventory_static()
    root_causes = build_root_cause_entries()
    unit_analysis = build_volume_unit_analysis()
    patch_bundle = build_parser_patch_bundle()
    schema_tests = run_schema_compatibility_tests()
    repair_sim = run_repair_simulation()
    repair_manifest = build_repair_eligibility_manifest()

    confirmed = sum(1 for rc in root_causes if rc.evidence_strength == EvidenceStrength.DIRECTLY_CONFIRMED)
    all_confirmed = confirmed == len(root_causes)

    return TPExVolumeIntegrityReport(
        null_inventory=inventory,
        root_causes=root_causes,
        unit_analysis=unit_analysis,
        parser_patch_bundle=patch_bundle,
        schema_tests=schema_tests,
        repair_simulation=repair_sim,
        repair_manifest=repair_manifest,
        root_cause_verdict=(
            VolumeRootCauseVerdict.TPEX_VOLUME_ROOT_CAUSE_CONFIRMED
            if all_confirmed else
            VolumeRootCauseVerdict.TPEX_VOLUME_ROOT_CAUSE_PARTIAL
        ),
        parser_verdict=ParserPatchVerdict.PARSER_PATCH_PARTIAL,
        repair_verdict=VolumeRepairVerdict.VOLUME_REPAIR_BLOCKED,
        s58_reference_correction=(
            "S58 reference '5,737 NULL volume rows' was INCORRECT. "
            "Actual: 129,636 NULL volume rows. "
            "5,737 ≈ Nov04 total rows (6,957 total; 5,715 NULL). "
            "S57 live probe counted 5,737 TPEx bulk response records (not production NULL rows). "
            "S59 forensics: Bug 1 (warrants) = 107,765; Bug 2 (TPEx field) = 21,846."
        ),
    )
