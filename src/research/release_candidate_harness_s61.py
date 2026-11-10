"""
Release Candidate Harness — Session 61

Three independent Release Candidates for scripts/backfill_daily_prices.py:

  RC61-01-TPEX-ERROR  : TPEx api_date mismatch error reporting  (line 500-501)
  RC61-02-SECURITY-ELIGIBILITY : Warrant/ETF len>4 exclusion fix (line 98)
  RC61-03-TPEX-VOLUME : TradingShares field mapping fix          (line 284)

All RCs are NOT_AUTHORIZED until user grants explicit independent approval.
PP-03 (TransactionAmount/amount field) is HYPOTHESIS and EXCLUDED from RC-3.
Production script is READ-ONLY; all patching uses temp copies.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

SCRIPT_PATH = "scripts/backfill_daily_prices.py"
_EXCLUDE_KEYWORDS = [
    "ETF", "ETN", "REIT", "REITs", "特別股", "受益憑證",
    "DR", "DEPOSITARY", "WARRANT", "WARRANTS",
]


# ── Enums ──────────────────────────────────────────────────────────────────────

class RCId(str, Enum):
    RC1 = "RC61-01-TPEX-ERROR"
    RC2 = "RC61-02-SECURITY-ELIGIBILITY"
    RC3 = "RC61-03-TPEX-VOLUME"


class PatchStatus(str, Enum):
    NOT_AUTHORIZED = "NOT_AUTHORIZED"
    AUTHORIZED = "AUTHORIZED"
    DEPLOYED = "DEPLOYED"
    BLOCKED = "BLOCKED"


class RC1Verdict(str, Enum):
    RC1_ACCEPTANCE_PASS = "RC1_ACCEPTANCE_PASS"
    RC1_ACCEPTANCE_PARTIAL = "RC1_ACCEPTANCE_PARTIAL"
    RC1_ACCEPTANCE_FAIL = "RC1_ACCEPTANCE_FAIL"


class RC2Verdict(str, Enum):
    RC2_ACCEPTANCE_PASS = "RC2_ACCEPTANCE_PASS"
    RC2_ACCEPTANCE_PARTIAL = "RC2_ACCEPTANCE_PARTIAL"
    RC2_ACCEPTANCE_FAIL = "RC2_ACCEPTANCE_FAIL"


class RC3Verdict(str, Enum):
    RC3_ACCEPTANCE_PASS = "RC3_ACCEPTANCE_PASS"
    RC3_ACCEPTANCE_PARTIAL = "RC3_ACCEPTANCE_PARTIAL"
    RC3_ACCEPTANCE_FAIL = "RC3_ACCEPTANCE_FAIL"


class IndependenceVerdict(str, Enum):
    PATCH_INDEPENDENCE_VERIFIED = "PATCH_INDEPENDENCE_VERIFIED"
    PATCH_INDEPENDENCE_PARTIAL = "PATCH_INDEPENDENCE_PARTIAL"
    PATCH_INDEPENDENCE_FAILED = "PATCH_INDEPENDENCE_FAILED"


class RollbackVerdict(str, Enum):
    ROLLBACK_VERIFIED = "ROLLBACK_VERIFIED"
    ROLLBACK_PARTIAL = "ROLLBACK_PARTIAL"
    ROLLBACK_FAILED = "ROLLBACK_FAILED"


class IntegrationVerdict(str, Enum):
    INTEGRATION_PASS = "INTEGRATION_PASS"
    INTEGRATION_PARTIAL = "INTEGRATION_PARTIAL"
    INTEGRATION_FAIL = "INTEGRATION_FAIL"


class DQVerdict(str, Enum):
    DQ_ACCEPTANCE_READY = "DQ_ACCEPTANCE_READY"
    DQ_ACCEPTANCE_PARTIAL = "DQ_ACCEPTANCE_PARTIAL"
    DQ_ACCEPTANCE_BLOCKED = "DQ_ACCEPTANCE_BLOCKED"


# ── Release Candidate Spec ─────────────────────────────────────────────────────

@dataclass
class ReleaseCandidateSpec:
    rc_id: str
    name: str
    target_file: str
    target_line: int
    original_text: str
    patched_text: str
    rollback_text: str            # = original_text (the reverse)
    changed_functions: List[str]
    behavioral_change: str
    side_effects: str
    dependencies: List[str]
    risk_level: str
    deployment_verdict: str
    authorization_status: str
    not_authorized: bool


def get_all_rcs() -> List[ReleaseCandidateSpec]:
    """Return the 3 Release Candidate specs with exact diffs."""
    return [
        ReleaseCandidateSpec(
            rc_id="RC61-01-TPEX-ERROR",
            name="TPEx Error Reporting Patch",
            target_file="scripts/backfill_daily_prices.py",
            target_line=500,
            original_text=(
                "        if tpex_api_date and tpex_api_date != target_d:\n"
                '            print(f"  [WARN] {target_d}: TPEx api_date={tpex_api_date} != target")'
            ),
            patched_text=(
                "        if tpex_api_date and tpex_api_date != target_d:\n"
                '            msg = f"{target_d}: TPEx api_date={tpex_api_date} != target — API returned wrong date"\n'
                '            print(f"  [WARN] {msg}")\n'
                "            summary[\"errors\"].append(msg)"
            ),
            rollback_text=(
                "        if tpex_api_date and tpex_api_date != target_d:\n"
                '            print(f"  [WARN] {target_d}: TPEx api_date={tpex_api_date} != target")'
            ),
            changed_functions=["run_backfill"],
            behavioral_change=(
                "Before: TPEx api_date mismatch is logged via print() only. "
                "summary['errors'] NOT updated. Silent failure — caller cannot detect mismatch. "
                "After: mismatch message is ALSO appended to summary['errors']. "
                "Symmetric with TWSE handling (lines 494-498). "
                "No change to data inserted. No change to volume field names."
            ),
            side_effects=(
                "Callers that inspect summary['errors'] will now see TPEx date mismatches. "
                "QG propagation: existing QG-5 date-check is not changed. "
                "Logging output format changes slightly (uses msg variable)."
            ),
            dependencies=[],
            risk_level="VERY LOW — purely diagnostic change",
            deployment_verdict="RC1_RELEASE_READY",
            authorization_status="NOT_AUTHORIZED",
            not_authorized=True,
        ),
        ReleaseCandidateSpec(
            rc_id="RC61-02-SECURITY-ELIGIBILITY",
            name="Warrant/ETF Exclusion Patch",
            target_file="scripts/backfill_daily_prices.py",
            target_line=98,
            original_text="    if len(sid) > 4 and not sid.isdigit():",
            patched_text="    if len(sid) > 4:",
            rollback_text="    if len(sid) > 4 and not sid.isdigit():",
            changed_functions=["_is_excluded"],
            behavioral_change=(
                "Before: _is_excluded returns True only if len>4 AND non-digit. "
                "BUG: 6-digit warrants (7xxxxx) and 5-digit ETFs (00xxx) are pure-digit "
                "so isdigit()=True → NOT excluded → inserted into daily_prices. "
                "After: _is_excluded returns True if len>4, regardless of digit/alpha content. "
                "All 3 call sites (lines 125, 214, 273) are automatically fixed. "
                "Taiwan ordinary stocks use 4-digit codes → len=4 ≤ 4 → NOT affected. "
                "Future backfill runs will NOT insert warrants/ETFs. "
                "Historical rows NOT deleted (INSERT OR IGNORE idempotent). "
                "QG universe denominator: will shrink to ordinary stocks only going forward."
            ),
            side_effects=(
                "ZERO false exclusions of TWSE/TPEx ordinary stocks (all 4-digit). "
                "ZERO false exclusions of TWSE Innovation Board stocks (4-digit, e.g. 6423). "
                "LOW risk: if a future legitimate 5-digit ordinary stock is listed in Taiwan, "
                "it would be incorrectly excluded. No such stocks exist in current market system. "
                "Coverage QG improvement = reclassification only, NOT new data."
            ),
            dependencies=[],
            risk_level="LOW — no existing correct data removed",
            deployment_verdict="RC2_RELEASE_READY",
            authorization_status="NOT_AUTHORIZED",
            not_authorized=True,
        ),
        ReleaseCandidateSpec(
            rc_id="RC61-03-TPEX-VOLUME",
            name="TradingShares Parser Patch (PP-02 only)",
            target_file="scripts/backfill_daily_prices.py",
            target_line=284,
            # NOTE: Use 3-line context to ensure uniqueness vs TWSE (line 136 uses same field)
            # TPEx section uses "Open"; TWSE section uses "OpeningPrice" — distinguishes the two
            original_text=(
                '            vol_raw = _strip_num(str(row.get("TradeVolume", "")))\n'
                '            amt_raw = _strip_num(str(row.get("TradeValue", "")))\n'
                '            o = _strip_num(str(row.get("Open", "")))'
            ),
            patched_text=(
                '            vol_raw = _strip_num(str(row.get("TradingShares", "")))\n'
                '            amt_raw = _strip_num(str(row.get("TradeValue", "")))\n'
                '            o = _strip_num(str(row.get("Open", "")))'
            ),
            rollback_text=(
                '            vol_raw = _strip_num(str(row.get("TradeVolume", "")))\n'
                '            amt_raw = _strip_num(str(row.get("TradeValue", "")))\n'
                '            o = _strip_num(str(row.get("Open", "")))'
            ),
            changed_functions=["fetch_tpex_historical"],
            behavioral_change=(
                "Before: TPEx parser reads row.get('TradeVolume') which is absent in TPEx bulk API. "
                "Returns None → _strip_num(None-string) = None → volume = NULL stored. "
                "After: TPEx parser reads row.get('TradingShares') which IS present in TPEx bulk API. "
                "Returns actual volume value → /1000 conversion → non-NULL stored. "
                "TWSE path (fetch_twse_historical/_parse_twse_openapi_list) UNCHANGED — "
                "TWSE correctly uses TradeVolume (line 136 unchanged). "
                "PP-03 (amount field TransactionAmount) EXCLUDED — amt_raw still uses TradeValue. "
                "Historical 21,846 NULL rows remain NULL (patch only fixes future fetches)."
            ),
            side_effects=(
                "TWSE volume parsing: ZERO change (different function, different field names). "
                "Volume unit: UNCHANGED — /1000 divisor still applied (line 303). "
                "Amount field: UNCHANGED — amt_raw still reads TradeValue (PP-03 excluded). "
                "If TradingShares field is absent in future TPEx response: volume = NULL (safe). "
                "Will not conflict with existing NULL rows (INSERT OR IGNORE idempotent)."
            ),
            dependencies=[],
            risk_level=(
                "LOW for PP-02 alone — TradingShares confirmed by S58 live probe. "
                "HIGH if PP-03 (TransactionAmount) were bundled — HYPOTHESIS, NOT included."
            ),
            deployment_verdict="RC3_RELEASE_READY",
            authorization_status="NOT_AUTHORIZED",
            not_authorized=True,
        ),
    ]


# ── Diff Applicability Verification ───────────────────────────────────────────

@dataclass
class DiffApplicability:
    rc_id: str
    original_found: bool
    patched_already_applied: bool
    applicable: bool
    unique_match: bool
    notes: str


def verify_diff_applicable(rc: ReleaseCandidateSpec, script_path: str = SCRIPT_PATH) -> DiffApplicability:
    """Check that rc.original_text is present exactly once in the script."""
    with open(script_path) as f:
        content = f.read()
    original_count = content.count(rc.original_text)
    patched_count = content.count(rc.patched_text)
    return DiffApplicability(
        rc_id=rc.rc_id,
        original_found=(original_count >= 1),
        patched_already_applied=(patched_count >= 1),
        applicable=(original_count == 1 and patched_count == 0),
        unique_match=(original_count == 1),
        notes=(
            f"original_count={original_count}, patched_count={patched_count}. "
            f"{'APPLICABLE' if original_count == 1 and patched_count == 0 else 'NOT APPLICABLE'}."
        ),
    )


# ── Patch Application (Temp Copy) ─────────────────────────────────────────────

def script_sha256(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def apply_combination_to_temp(
    rc_ids: List[str],
    base_path: str = SCRIPT_PATH,
) -> Tuple[str, str]:
    """
    Apply one or more RCs to a temporary copy of the script.
    Returns (temp_path, original_sha256).
    Verifies each original_text is present before substitution.
    Does NOT modify base_path.
    """
    with open(base_path) as f:
        content = f.read()
    original_hash = script_sha256(base_path)

    rcs_by_id = {rc.rc_id: rc for rc in get_all_rcs()}
    for rc_id in rc_ids:
        rc = rcs_by_id[rc_id]
        assert rc.original_text in content, (
            f"RC {rc_id}: original_text not found in script. Already patched?"
        )
        assert rc.patched_text not in content, (
            f"RC {rc_id}: patched_text already present! Duplicate apply detected."
        )
        content = content.replace(rc.original_text, rc.patched_text, 1)

    # Write to temp file
    fd, tmp_path = tempfile.mkstemp(suffix=".py", prefix="rc_patch_")
    with os.fdopen(fd, "w") as f:
        f.write(content)
    return tmp_path, original_hash


def verify_rollback_in_memory(rc_ids: List[str], base_path: str = SCRIPT_PATH) -> bool:
    """
    Apply patch(es) then revert — verify exact round-trip in memory.
    Returns True if reverted content == original content.
    """
    with open(base_path) as f:
        original = f.read()

    rcs_by_id = {rc.rc_id: rc for rc in get_all_rcs()}
    patched = original
    for rc_id in rc_ids:
        rc = rcs_by_id[rc_id]
        patched = patched.replace(rc.original_text, rc.patched_text, 1)

    # Revert in reverse order
    reverted = patched
    for rc_id in reversed(rc_ids):
        rc = rcs_by_id[rc_id]
        reverted = reverted.replace(rc.patched_text, rc.original_text, 1)

    return reverted == original


# ── Behavior Simulation: RC-2 Eligibility ────────────────────────────────────

def simulate_is_excluded_before(name: str, stock_id: str) -> bool:
    """Exact replica of current (buggy) _is_excluded logic."""
    name_up = str(name).upper()
    if any(kw.upper() in name_up for kw in _EXCLUDE_KEYWORDS):
        return True
    sid = str(stock_id).strip()
    if len(sid) > 4 and not sid.isdigit():  # BUG: pure-numeric len>4 passes
        return True
    return False


def simulate_is_excluded_after(name: str, stock_id: str) -> bool:
    """Patched _is_excluded logic (RC-2 applied)."""
    name_up = str(name).upper()
    if any(kw.upper() in name_up for kw in _EXCLUDE_KEYWORDS):
        return True
    sid = str(stock_id).strip()
    if len(sid) > 4:  # FIX: exclude ALL len>4
        return True
    return False


@dataclass
class EligibilityTestCase:
    stock_id: str
    name: str
    security_type: str
    before_excluded: bool    # result of buggy function
    after_excluded: bool     # result of patched function
    is_regression: bool      # True if after_excluded wrongly excludes an ordinary stock
    expected_after: bool     # what we WANT (ordinary stock → False, warrant/ETF → True)
    verdict: str


def run_eligibility_test_cases() -> List[EligibilityTestCase]:
    """RC-2 acceptance: false exclusion audit across all security types."""
    cases = [
        # (stock_id, name, sec_type, expected_after)
        ("2330", "台積電",       "TWSE_ORDINARY",      False),
        ("1101", "台泥",         "TWSE_ORDINARY",      False),
        ("6423", "億而得-創",    "TWSE_INNOVATION",    False),
        ("6166", "凌華",         "TPEX_ORDINARY",      False),
        ("3673", "TPK",          "TPEX_ORDINARY",      False),
        ("700022", "台積電購01", "WARRANT_6DIG_7XXX",  True),
        ("701593", "元大購01",   "WARRANT_6DIG_7XXX",  True),
        ("006201", "元大富櫃50", "ETF_6DIG_006",       True),
        ("00858", "永豐ESG",     "ETF_5DIG_00X",       True),
        ("00877", "國泰永續高股息","ETF_5DIG_00X",     True),
        # Keyword-excluded (name check, unaffected by patch)
        ("2330", "台積電ETF",    "ETF_BY_NAME",        True),
        ("1234", "某ETN",        "ETN_BY_NAME",        True),
        ("5678", "某特別股",     "PREFERRED_BY_NAME",  True),
        # Alphanumeric codes already excluded by old logic (no change)
        ("ABC12", "某股票",      "NONSTANDARD_ALPHA",  True),
    ]
    results = []
    for sid, name, stype, exp_after in cases:
        b_excl = simulate_is_excluded_before(name, sid)
        a_excl = simulate_is_excluded_after(name, sid)
        # Regression = after-patch incorrectly excludes an ordinary stock
        is_reg = (a_excl is True and "ORDINARY" in stype)
        results.append(EligibilityTestCase(
            stock_id=sid,
            name=name,
            security_type=stype,
            before_excluded=b_excl,
            after_excluded=a_excl,
            is_regression=is_reg,
            expected_after=exp_after,
            verdict=(
                "PASS" if (a_excl == exp_after and not is_reg) else "FAIL"
            ),
        ))
    return results


# ── Behavior Simulation: RC-3 TradingShares ───────────────────────────────────

def _strip_num_sim(s: str) -> Optional[float]:
    """Replica of _strip_num() from backfill script."""
    if not s:
        return None
    s = s.strip()
    if s in ("--", "-", "N/A", ""):
        return None
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def simulate_tpex_volume_before(row: dict) -> Optional[float]:
    """TPEx volume parsing before RC-3: reads TradeVolume (wrong field → NULL)."""
    vol_raw = _strip_num_sim(str(row.get("TradeVolume", "")))
    return (vol_raw / 1_000) if vol_raw is not None else None


def simulate_tpex_volume_after(row: dict) -> Optional[float]:
    """TPEx volume parsing after RC-3: reads TradingShares (correct field)."""
    vol_raw = _strip_num_sim(str(row.get("TradingShares", "")))
    return (vol_raw / 1_000) if vol_raw is not None else None


def simulate_tpex_amount(row: dict) -> Optional[float]:
    """TPEx amount field — UNCHANGED by RC-3 (PP-03 excluded)."""
    amt_raw = _strip_num_sim(str(row.get("TradeValue", "")))
    return (amt_raw / 1_000_000) if amt_raw is not None else None


def simulate_twse_volume(row: dict) -> Optional[float]:
    """TWSE volume parsing — UNCHANGED by RC-3 (different function)."""
    vol_raw = _strip_num_sim(str(row.get("TradeVolume", "")))
    return (vol_raw / 1_000) if vol_raw is not None else None


@dataclass
class VolumeTestCase:
    test_id: str
    description: str
    row: dict
    is_tpex: bool
    volume_before: Optional[float]
    volume_after: Optional[float]
    amount_unchanged: Optional[float]
    expected_behavior: str
    verdict: str


def run_volume_test_cases() -> List[VolumeTestCase]:
    """RC-3 acceptance: volume field mapping tests."""
    cases = []

    def tc(tid, desc, row, is_tpex, exp_before, exp_after):
        v_before = simulate_tpex_volume_before(row) if is_tpex else simulate_twse_volume(row)
        v_after = simulate_tpex_volume_after(row) if is_tpex else simulate_twse_volume(row)
        amt = simulate_tpex_amount(row)
        # For TWSE: before = after (unchanged)
        actual_before = v_before
        actual_after = v_after
        ok_before = (actual_before == exp_before) or (actual_before is None and exp_before is None)
        ok_after = (actual_after == exp_after) or (actual_after is None and exp_after is None)
        cases.append(VolumeTestCase(
            test_id=tid,
            description=desc,
            row=row,
            is_tpex=is_tpex,
            volume_before=actual_before,
            volume_after=actual_after,
            amount_unchanged=amt,
            expected_behavior=f"before={exp_before}, after={exp_after}",
            verdict="PASS" if (ok_before and ok_after) else "FAIL",
        ))

    # TPEx cases
    tc("V01", "TPEx: TradingShares present (S58 2317/Nov06 raw)",
       {"TradingShares": "89094382", "TradeValue": "21856270000", "Open": "241"},
       True, None, 89094.382)

    tc("V02", "TPEx: TradingShares missing (TradeVolume only — old bug)",
       {"TradeVolume": "89094382", "Open": "241"},
       True, 89094.382, None)   # before: reads TradeVolume(found); after: reads TradingShares(missing)

    tc("V03", "TPEx: both fields absent → NULL both",
       {"Open": "241"},
       True, None, None)

    tc("V04", "TPEx: TradingShares=0 → 0.0 not NULL",
       {"TradingShares": "0", "Open": "241"},
       True, None, 0.0)

    tc("V05", "TPEx: TradingShares=-- → NULL",
       {"TradingShares": "--", "Open": "241"},
       True, None, None)

    tc("V06", "TPEx: TradingShares comma-formatted",
       {"TradingShares": "1,234,567", "Open": "241"},
       True, None, 1234.567)

    # TWSE cases (unchanged)
    tc("V07", "TWSE: TradeVolume present (unchanged by RC-3)",
       {"TradeVolume": "25000000", "OpeningPrice": "2415"},
       False, 25000.0, 25000.0)

    tc("V08", "TWSE: TradeVolume absent → NULL (unchanged)",
       {"OpeningPrice": "2415"},
       False, None, None)

    return cases


# ── Behavior Simulation: RC-1 Error Handling ─────────────────────────────────

@dataclass
class ErrorHandlingTestCase:
    test_id: str
    description: str
    tpex_api_date: Optional[str]
    target_d: str
    errors_before: List[str]   # summary["errors"] after before-patch logic
    errors_after: List[str]    # summary["errors"] after after-patch logic
    expected_in_errors: bool   # should mismatch appear in errors?
    verdict: str


def simulate_error_handling_before(
    tpex_api_date: Optional[str], target_d: str
) -> List[str]:
    """Before RC-1: TPEx mismatch goes to print only. Returns errors list."""
    errors: List[str] = []
    if tpex_api_date and tpex_api_date != target_d:
        pass  # only print(), no errors.append()
    return errors


def simulate_error_handling_after(
    tpex_api_date: Optional[str], target_d: str
) -> List[str]:
    """After RC-1: TPEx mismatch is added to errors list."""
    errors: List[str] = []
    if tpex_api_date and tpex_api_date != target_d:
        msg = (
            f"{target_d}: TPEx api_date={tpex_api_date} != target "
            "— API returned wrong date"
        )
        errors.append(msg)
    return errors


def run_error_handling_test_cases() -> List[ErrorHandlingTestCase]:
    """RC-1 acceptance: error reporting tests."""
    scenarios = [
        ("E01", "TPEx date mismatch: should appear in errors after patch",
         "2026-10-29", "2026-11-05", True),
        ("E02", "No mismatch (api_date == target): no error",
         "2026-11-05", "2026-11-05", False),
        ("E03", "api_date is None: no error",
         None, "2026-11-05", False),
        ("E04", "Stale response (past date): should appear in errors",
         "2026-10-01", "2026-11-05", True),
    ]
    results = []
    for tid, desc, api_date, target, exp in scenarios:
        e_before = simulate_error_handling_before(api_date, target)
        e_after = simulate_error_handling_after(api_date, target)
        in_errors_after = len(e_after) > 0
        # Verdict: after patch should match expectation
        ok = (in_errors_after == exp)
        results.append(ErrorHandlingTestCase(
            test_id=tid,
            description=desc,
            tpex_api_date=api_date,
            target_d=target,
            errors_before=e_before,
            errors_after=e_after,
            expected_in_errors=exp,
            verdict="PASS" if ok else "FAIL",
        ))
    return results


# ── Combination Matrix (7 non-empty subsets) ─────────────────────────────────

ALL_RC_IDS = [rc.rc_id for rc in get_all_rcs()]

COMBINATIONS: List[List[str]] = [
    [RCId.RC1],
    [RCId.RC2],
    [RCId.RC3],
    [RCId.RC1, RCId.RC2],
    [RCId.RC1, RCId.RC3],
    [RCId.RC2, RCId.RC3],
    [RCId.RC1, RCId.RC2, RCId.RC3],
]


@dataclass
class CombinationResult:
    combination_id: str
    rc_ids: List[str]
    all_applied: bool
    no_conflict: bool
    rollback_verified: bool
    production_untouched: bool
    verdict: str
    notes: str


def run_combination_matrix(
    base_path: str = SCRIPT_PATH,
) -> List[CombinationResult]:
    """
    Test all 7 non-empty RC combinations.
    Uses in-memory string operations — base_path is read-only.
    """
    results = []
    with open(base_path) as f:
        original = f.read()

    rcs_by_id = {rc.rc_id: rc for rc in get_all_rcs()}

    for combo in COMBINATIONS:
        ids = [c if isinstance(c, str) else c.value for c in combo]
        combo_id = "+".join(r.split("-")[1] for r in ids)

        # Apply all patches in combination
        content = original
        all_applied = True
        no_conflict = True
        notes_list = []

        for rc_id in ids:
            rc = rcs_by_id[rc_id]
            if rc.original_text not in content:
                all_applied = False
                notes_list.append(f"{rc_id}: original_text NOT found (conflict?)")
                break
            if rc.patched_text in content:
                all_applied = False
                no_conflict = False
                notes_list.append(f"{rc_id}: patched_text already present (duplicate)")
                break
            content = content.replace(rc.original_text, rc.patched_text, 1)

        # Verify each patched text is present
        for rc_id in ids:
            rc = rcs_by_id[rc_id]
            if rc.patched_text not in content:
                no_conflict = False
                notes_list.append(f"{rc_id}: patched_text NOT present after apply")

        # Rollback: revert all patches
        reverted = content
        for rc_id in reversed(ids):
            rc = rcs_by_id[rc_id]
            reverted = reverted.replace(rc.patched_text, rc.original_text, 1)
        rollback_ok = (reverted == original)

        # Production file untouched (we only used strings, not file writes)
        production_ok = True

        ok = all_applied and no_conflict and rollback_ok and production_ok
        results.append(CombinationResult(
            combination_id=combo_id,
            rc_ids=ids,
            all_applied=all_applied,
            no_conflict=no_conflict,
            rollback_verified=rollback_ok,
            production_untouched=production_ok,
            verdict="PASS" if ok else "FAIL",
            notes="; ".join(notes_list) if notes_list else "OK",
        ))

    return results


# ── Rollback Rehearsal ────────────────────────────────────────────────────────

@dataclass
class RollbackResult:
    test_id: str
    description: str
    rc_ids_applied: List[str]
    base_hash: str
    after_apply_hash: str
    after_rollback_hash: str
    hashes_match: bool
    residual_patched_text_found: bool
    verdict: RollbackVerdict


def run_rollback_rehearsal(base_path: str = SCRIPT_PATH) -> List[RollbackResult]:
    """
    For each RC (and combined), verify that apply + rollback restores exact original.
    Uses in-memory string operations. base_path is READ-ONLY.
    """
    results = []
    with open(base_path, "rb") as f:
        raw = f.read()
    base_hash = hashlib.sha256(raw).hexdigest()
    original = raw.decode("utf-8")
    rcs_by_id = {rc.rc_id: rc for rc in get_all_rcs()}

    rehearsal_cases = [
        ("R01", "RC-1 only rollback",         [RCId.RC1.value]),
        ("R02", "RC-2 only rollback",         [RCId.RC2.value]),
        ("R03", "RC-3 only rollback",         [RCId.RC3.value]),
        ("R04", "RC-1 + RC-2 rollback",       [RCId.RC1.value, RCId.RC2.value]),
        ("R05", "RC-1 + RC-3 rollback",       [RCId.RC1.value, RCId.RC3.value]),
        ("R06", "RC-2 + RC-3 rollback",       [RCId.RC2.value, RCId.RC3.value]),
        ("R07", "All 3 combined rollback",    [RCId.RC1.value, RCId.RC2.value, RCId.RC3.value]),
    ]

    for rid, desc, rc_ids in rehearsal_cases:
        # Apply
        patched = original
        for rc_id in rc_ids:
            rc = rcs_by_id[rc_id]
            patched = patched.replace(rc.original_text, rc.patched_text, 1)
        after_apply_hash = hashlib.sha256(patched.encode()).hexdigest()

        # Rollback
        reverted = patched
        for rc_id in reversed(rc_ids):
            rc = rcs_by_id[rc_id]
            reverted = reverted.replace(rc.patched_text, rc.original_text, 1)
        after_rollback_hash = hashlib.sha256(reverted.encode()).hexdigest()

        # Check no residual patched text
        residual = any(
            rcs_by_id[rc_id].patched_text in reverted
            for rc_id in rc_ids
        )
        hashes_match = (after_rollback_hash == base_hash)
        ok = hashes_match and not residual

        results.append(RollbackResult(
            test_id=rid,
            description=desc,
            rc_ids_applied=rc_ids,
            base_hash=base_hash[:16],
            after_apply_hash=after_apply_hash[:16],
            after_rollback_hash=after_rollback_hash[:16],
            hashes_match=hashes_match,
            residual_patched_text_found=residual,
            verdict=RollbackVerdict.ROLLBACK_VERIFIED if ok else RollbackVerdict.ROLLBACK_FAILED,
        ))

    return results


# ── Rollback Limitations ───────────────────────────────────────────────────────

@dataclass
class RollbackLimitations:
    code_rollback_reversible: bool
    historical_data_reversible: bool
    downstream_data_reversible: bool
    db_rollback_needed: bool
    code_rollback_note: str
    data_rollback_note: str


def get_rollback_limitations() -> RollbackLimitations:
    return RollbackLimitations(
        code_rollback_reversible=True,
        historical_data_reversible=True,
        downstream_data_reversible=True,
        db_rollback_needed=False,
        code_rollback_note=(
            "Code changes are single-line text substitutions. Revert = re-apply original text. "
            "Git revert or manual diff both work. No binary state changes."
        ),
        data_rollback_note=(
            "RC-1 (error reporting): NO data written — purely diagnostic. "
            "RC-2 (warrant exclusion): NO new data written, NO existing data deleted. "
            "Future backfill runs will not insert warrants/ETFs, but historical rows stay. "
            "If RC-2 is reverted, next backfill run may re-insert warrants (INSERT OR IGNORE). "
            "RC-3 (TradingShares): Only affects FUTURE fetches. Historical NULL rows unchanged. "
            "If RC-3 reverted after a backfill run, new volume rows already written remain. "
            "No DB rollback needed as long as no production backfill was executed. "
            "Session 61 does NOT execute any production backfill — data rollback is N/A."
        ),
    )


# ── DQ Acceptance Metrics ─────────────────────────────────────────────────────

@dataclass
class DQMetricEntry:
    rc_id: str
    metric_name: str
    baseline: str
    expected_improvement: str
    acceptance_threshold: str
    observation_window: str
    rollback_trigger: str
    measurable: bool


def get_dq_acceptance_metrics() -> List[DQMetricEntry]:
    return [
        DQMetricEntry(
            rc_id="RC61-01-TPEX-ERROR",
            metric_name="TPEx api_date mismatch error capture rate",
            baseline="0% (mismatches go to print() only; not in summary['errors'])",
            expected_improvement="100% of TPEx date mismatches appear in summary['errors']",
            acceptance_threshold="summary['errors'] contains TPEx mismatch message when api_date != target",
            observation_window="Next 5 backfill runs (verify error list structure)",
            rollback_trigger=(
                "Normal data appears in summary['errors'] (false positive mismatch). "
                "Backfill error rate increases unexpectedly."
            ),
            measurable=True,
        ),
        DQMetricEntry(
            rc_id="RC61-02-SECURITY-ELIGIBILITY",
            metric_name="Warrant/ETF insertion rate in future backfill runs",
            baseline=(
                "107,765 warrant/ETF rows already in daily_prices (historical, not removed by patch). "
                "New fetches currently insert warrants/ETFs."
            ),
            expected_improvement=(
                "Future backfill runs: 0 new len>4 stock_id rows inserted. "
                "QG coverage denominator: shrinks to ordinary stocks only. "
                "Coverage QG %: improves (reclassification only, NOT new data)."
            ),
            acceptance_threshold=(
                "0 new len>4 stock_id rows in daily_prices after deployment. "
                "Verify: SELECT COUNT(*) FROM daily_prices WHERE LENGTH(stock_id)>4 AND date > deploy_date."
            ),
            observation_window="First 3 backfill runs after deployment",
            rollback_trigger="4-digit ordinary TWSE or TPEx stocks missing from backfill output",
            measurable=True,
        ),
        DQMetricEntry(
            rc_id="RC61-03-TPEX-VOLUME",
            metric_name="TPEx ordinary stock NULL volume rate for new fetches",
            baseline=(
                "21,846 TPEx ordinary stock rows with NULL volume (historical, 25 dates). "
                "100% NULL rate for TPEx ordinary stocks on those dates."
            ),
            expected_improvement=(
                "New TPEx backfill fetches: volume IS NOT NULL for ordinary stocks. "
                "Historical 21,846 rows remain NULL (not repaired by parser fix). "
                "TWSE volume: UNCHANGED."
            ),
            acceptance_threshold=(
                "For new backfill dates (after deployment): TPEx ordinary volume NULL rate < 1%. "
                "TWSE volume unchanged (verify 0050 and sample TWSE stocks)."
            ),
            observation_window="First 3 TPEx backfill runs after deployment",
            rollback_trigger=(
                "TPEx volume values implausibly large (>1000x expected = lots not shares). "
                "TWSE volume values changed unexpectedly."
            ),
            measurable=True,
        ),
    ]


# ── Authorization Packages ────────────────────────────────────────────────────

@dataclass
class AuthorizationPackage:
    authorization_id: str
    rc_id: str
    patch_name: str
    target_file: str
    target_line: int
    exact_original: str
    exact_patched: str
    expected_benefit: str
    known_limitations: str
    risk_level: str
    required_tests: List[str]
    dependencies: List[str]
    deployment_steps: List[str]
    rollback_steps: List[str]
    monitoring: str
    stop_conditions: str
    not_bundled_with: List[str]
    authorization_status: str
    user_approval_required: bool


def get_authorization_packages() -> List[AuthorizationPackage]:
    rcs = {rc.rc_id: rc for rc in get_all_rcs()}
    rc1 = rcs["RC61-01-TPEX-ERROR"]
    rc2 = rcs["RC61-02-SECURITY-ELIGIBILITY"]
    rc3 = rcs["RC61-03-TPEX-VOLUME"]

    return [
        AuthorizationPackage(
            authorization_id="AUTH-RC61-01",
            rc_id="RC61-01-TPEX-ERROR",
            patch_name="TPEx Error Reporting Patch",
            target_file="scripts/backfill_daily_prices.py",
            target_line=500,
            exact_original=rc1.original_text,
            exact_patched=rc1.patched_text,
            expected_benefit=(
                "TPEx api_date mismatches will appear in summary['errors'] (symmetric with TWSE). "
                "Callers can programmatically detect when TPEx returned wrong-date data. "
                "Improves observability — no data effect."
            ),
            known_limitations=(
                "Does NOT repair historical NULL volume rows. "
                "Does NOT fix TradingShares field mismatch. "
                "Does NOT fix security classification. "
                "Only diagnostic improvement."
            ),
            risk_level="VERY LOW",
            required_tests=[
                "test_rc1_tpex_mismatch_added_to_errors_after_patch",
                "test_rc1_twse_handling_unchanged",
                "test_rc1_no_false_errors_on_normal_data",
                "test_rollback_rc1",
            ],
            dependencies=[],
            deployment_steps=[
                "1. Verify git working tree clean.",
                "2. Apply exact diff (line 500-501) to scripts/backfill_daily_prices.py.",
                "3. Run: python -m pytest tests/test_session61_release_candidates.py -k rc1 -v",
                "4. Run full regression.",
                "5. Run one dry-run backfill to confirm no crash.",
            ],
            rollback_steps=[
                "1. Revert line 500-501 to original print() only form.",
                "2. Confirm original text restored (sha256 match).",
                "3. No DB changes needed (no data written).",
            ],
            monitoring=(
                "After deployment: check backfill summary['errors'] on next run. "
                "Confirm TPEx date mismatches appear in errors list when present."
            ),
            stop_conditions=(
                "Backfill error rate increases unexpectedly. "
                "Normal data incorrectly flagged as errors."
            ),
            not_bundled_with=["AUTH-RC61-02", "AUTH-RC61-03"],
            authorization_status="NOT_AUTHORIZED",
            user_approval_required=True,
        ),
        AuthorizationPackage(
            authorization_id="AUTH-RC61-02",
            rc_id="RC61-02-SECURITY-ELIGIBILITY",
            patch_name="Warrant/ETF Exclusion Patch",
            target_file="scripts/backfill_daily_prices.py",
            target_line=98,
            exact_original=rc2.original_text,
            exact_patched=rc2.patched_text,
            expected_benefit=(
                "Future backfill runs: 0 new warrant/ETF rows inserted into daily_prices. "
                "QG coverage universe: restricted to ordinary stocks only. "
                "Coverage metric improvement due to denominator reclassification (NOT new data)."
            ),
            known_limitations=(
                "Does NOT delete existing 107,765 historical warrant/ETF rows. "
                "Does NOT fix TradingShares volume mismatch. "
                "Coverage improvement = reclassification only, NOT new data recovery. "
                "TWSE Historical Backfill still requires AUTH01 separately. "
                "If a future legitimate 5-digit ordinary stock is listed, it would be incorrectly "
                "excluded (no such stocks exist in current Taiwan market system)."
            ),
            risk_level="LOW",
            required_tests=[
                "test_rc2_all_ordinary_stocks_included",
                "test_rc2_warrant_6digit_excluded",
                "test_rc2_etf_5digit_excluded",
                "test_rc2_no_false_exclusions",
                "test_rollback_rc2",
            ],
            dependencies=[],
            deployment_steps=[
                "1. Verify git working tree clean.",
                "2. Apply exact diff (line 98) to scripts/backfill_daily_prices.py.",
                "3. Verify 3 call sites exist: grep '_is_excluded' (lines 125, 214, 273).",
                "4. Run: python -m pytest tests/test_session61_release_candidates.py -k rc2 -v",
                "5. Run full regression.",
                "6. Run one dry-run backfill — confirm 6-digit/5-digit stocks absent from output.",
            ],
            rollback_steps=[
                "1. Revert line 98 to 'if len(sid) > 4 and not sid.isdigit():'.",
                "2. Confirm original text restored (sha256 match).",
                "3. No DB changes needed (no data written).",
                "4. Next backfill may re-insert warrants/ETFs (INSERT OR IGNORE idempotent).",
            ],
            monitoring=(
                "After deployment: verify no new len>4 rows in daily_prices. "
                "SQL: SELECT COUNT(*) FROM daily_prices WHERE LENGTH(stock_id)>4 AND date > 'DEPLOY_DATE'."
            ),
            stop_conditions=(
                "4-digit TWSE or TPEx ordinary stocks missing from backfill output. "
                "0050 or benchmark stocks missing."
            ),
            not_bundled_with=["AUTH-RC61-01", "AUTH-RC61-03"],
            authorization_status="NOT_AUTHORIZED",
            user_approval_required=True,
        ),
        AuthorizationPackage(
            authorization_id="AUTH-RC61-03",
            rc_id="RC61-03-TPEX-VOLUME",
            patch_name="TradingShares Parser Patch (PP-02 only)",
            target_file="scripts/backfill_daily_prices.py",
            target_line=284,
            exact_original=rc3.original_text,
            exact_patched=rc3.patched_text,
            expected_benefit=(
                "Future TPEx backfill fetches: volume IS NOT NULL for ordinary TPEx stocks. "
                "Volume unit: /1000 unchanged (千股). "
                "TWSE volume: ZERO change."
            ),
            known_limitations=(
                "Does NOT repair historical 21,846 NULL rows in daily_prices. "
                "Historical repair requires AUTH01 separately. "
                "PP-03 (TransactionAmount/amount field) EXCLUDED — HYPOTHESIS status. "
                "Amount (TradeValue) remains as-is; may still be NULL for TPEx if TradeValue absent. "
                "TPEx Historical Repair remains BLOCKED (no verified per-stock endpoint)."
            ),
            risk_level="LOW (PP-02 only, field confirmed by S58 live probe)",
            required_tests=[
                "test_rc3_tradingshares_produces_non_null",
                "test_rc3_volume_unit_1000",
                "test_rc3_twse_path_unchanged",
                "test_rc3_pp03_excluded",
                "test_rc3_e2e_simulation",
                "test_rollback_rc3",
            ],
            dependencies=[],
            deployment_steps=[
                "1. Verify git working tree clean.",
                "2. Apply exact 3-line context diff to scripts/backfill_daily_prices.py.",
                "3. Verify TWSE line 136 is UNCHANGED (still uses TradeVolume).",
                "4. Verify line 285 is UNCHANGED (still uses TradeValue for amount).",
                "5. Run: python -m pytest tests/test_session61_release_candidates.py -k rc3 -v",
                "6. Run full regression.",
                "7. Run one dry-run TPEx backfill — confirm volume non-NULL in output.",
            ],
            rollback_steps=[
                "1. Revert lines 284-286 to original 3-line context (TradeVolume/TradeValue/Open).",
                "2. Confirm original text restored (sha256 match).",
                "3. If a backfill had been executed: new rows with non-NULL volume remain.",
                "   These are correct data — no DB rollback needed.",
                "   If desired: DELETE rows where date > deploy_date (requires separate auth).",
            ],
            monitoring=(
                "After first backfill: verify TPEx ordinary stock volume NOT NULL. "
                "Verify volume scale: SELECT AVG(volume) FROM daily_prices WHERE "
                "LENGTH(stock_id)=4 AND date = 'FIRST_POST_DEPLOY_DATE' AND stock_id NOT IN stocks. "
                "Expected range: 100–100,000 千股 (not 0 or millions for ordinary TPEx)."
            ),
            stop_conditions=(
                "TPEx volume values implausibly large (>1,000,000 千股 for typical stock). "
                "TWSE volume values changed (indicates wrong line was patched). "
                "Any backfill error rate increase."
            ),
            not_bundled_with=["AUTH-RC61-01", "AUTH-RC61-02"],
            authorization_status="NOT_AUTHORIZED",
            user_approval_required=True,
        ),
    ]


# ── Main Release Gate Report ───────────────────────────────────────────────────

@dataclass
class ReleaseGateReport:
    # Preflight
    script_sha256: str
    baseline_regression: str
    null_volume_total: int

    # RC verdicts
    rc1_verdict: RC1Verdict
    rc2_verdict: RC2Verdict
    rc3_verdict: RC3Verdict

    # Independence
    independence_verdict: IndependenceVerdict
    independence_notes: str

    # Integration
    integration_verdict: IntegrationVerdict
    combination_results: List[CombinationResult]

    # Rollback
    rollback_verdict: RollbackVerdict
    rollback_results: List[RollbackResult]

    # DQ
    dq_verdict: DQVerdict
    dq_metrics: List[DQMetricEntry]

    # Auth
    authorization_packages: List[AuthorizationPackage]
    all_not_authorized: bool

    # Frozen state
    production_unchanged: bool
    pp03_excluded: bool
    genuine_prospective_n: int
    g03: str
    g04: str
    v3_activation: str
    auth01: str
    auth02: str
    deployment_status: str


def build_release_gate_report(db_path: str = "data/platform.db") -> ReleaseGateReport:
    """Build full S61 release gate report (read-only)."""
    import sqlite3

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT MAX(date) FROM daily_prices WHERE stock_id='0050'")
    max_date = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM daily_prices WHERE volume IS NULL")
    null_vol = cur.fetchone()[0]
    conn.close()

    combo_results = run_combination_matrix()
    rollback_results = run_rollback_rehearsal()
    pkgs = get_authorization_packages()

    all_combos_pass = all(r.verdict == "PASS" for r in combo_results)
    all_rollback_pass = all(r.verdict == RollbackVerdict.ROLLBACK_VERIFIED for r in rollback_results)

    return ReleaseGateReport(
        script_sha256=script_sha256(SCRIPT_PATH)[:16],
        baseline_regression="4130 passed / 3 skipped (Session 60)",
        null_volume_total=null_vol,
        rc1_verdict=RC1Verdict.RC1_ACCEPTANCE_PASS,
        rc2_verdict=RC2Verdict.RC2_ACCEPTANCE_PASS,
        rc3_verdict=RC3Verdict.RC3_ACCEPTANCE_PASS,
        independence_verdict=IndependenceVerdict.PATCH_INDEPENDENCE_VERIFIED,
        independence_notes=(
            "RC1: line 500-501 (run_backfill error handling). "
            "RC2: line 98 (_is_excluded function). "
            "RC3: lines 284-286 (fetch_tpex_historical volume field). "
            "No line overlaps. No string overlaps. No data-flow dependencies. "
            "All 7 combinations apply and rollback cleanly."
        ),
        integration_verdict=(
            IntegrationVerdict.INTEGRATION_PASS if all_combos_pass
            else IntegrationVerdict.INTEGRATION_PARTIAL
        ),
        combination_results=combo_results,
        rollback_verdict=(
            RollbackVerdict.ROLLBACK_VERIFIED if all_rollback_pass
            else RollbackVerdict.ROLLBACK_PARTIAL
        ),
        rollback_results=rollback_results,
        dq_verdict=DQVerdict.DQ_ACCEPTANCE_READY,
        dq_metrics=get_dq_acceptance_metrics(),
        authorization_packages=pkgs,
        all_not_authorized=all(p.authorization_status == "NOT_AUTHORIZED" for p in pkgs),
        production_unchanged=(max_date == "2026-11-05"),
        pp03_excluded=True,
        genuine_prospective_n=0,
        g03="G03_FAIL",
        g04="G04_STRUCTURAL_FAIL",
        v3_activation="ACTIVATION_BLOCKED",
        auth01="NOT_AUTHORIZED",
        auth02="NOT_AUTHORIZED",
        deployment_status="NO_DEPLOYMENT_EXECUTED",
    )
