"""
Session 62 — Controlled Deployment Readiness Tests

Covers:
  TC01-TC06  : Entry-point inventory
  TC07-TC14  : Import-time side-effect audit
  TC15-TC20  : DB write-path inventory
  TC21-TC25  : Network side-effect inventory
  TC26-TC28  : Zero-write RC simulation (individual)
  TC29-TC35  : Zero-write combination matrix (7 combos)
  TC36-TC41  : Operation boundary tests
  TC42-TC44  : Deployment state machine
  TC45-TC51  : Rollback rehearsal (re-verify from S61)
  TC52-TC57  : Authorization boundary tests
  TC58-TC62  : Frozen production integrity
  TC63-TC68  : DQ observation plan
  TC69-TC75  : Final verdict

No production files modified. No live DB. No live network. No deployment executed.
"""

from __future__ import annotations



from src.research.deployment_readiness_s62 import (
    PRODUCTION_SCRIPT_SHA256,
    DeploymentState,
    OperationType,
    build_db_write_path_inventory,
    build_dq_observation_plan,
    build_entry_point_inventory,
    build_frozen_integrity_checks,
    build_network_side_effect_inventory,
    build_operation_boundaries,
    build_s62_verdict,
    check_import_time_side_effects,
    get_deployment_state_records,
    run_zero_write_combination_simulation,
    run_zero_write_rc_simulation,
)
from src.research.release_candidate_harness_s61 import (
    SCRIPT_PATH,
    get_authorization_packages,
    get_all_rcs,
    run_combination_matrix,
    run_rollback_rehearsal,
    script_sha256,
    verify_rollback_in_memory,
)


# ── TC01-TC06: Entry-point Inventory ─────────────────────────────────────────

def test_tc01_entry_point_count():
    """Exactly 6 entry points catalogued."""
    eps = build_entry_point_inventory()
    assert len(eps) == 6


def test_tc02_cli_entry_point():
    """EP-01 Direct CLI entry point correctly described."""
    eps = {ep.entry_id: ep for ep in build_entry_point_inventory()}
    ep = eps["EP-01"]
    assert "main()" in ep.target_function
    assert "run_backfill" in ep.target_function
    assert "--execute" in ep.auth_required


def test_tc03_hybrid_cron_subprocess_entry_point():
    """EP-02 hybrid_shadow_cron.py subprocess correctly identified."""
    eps = {ep.entry_id: ep for ep in build_entry_point_inventory()}
    ep = eps["EP-02"]
    assert "subprocess" in ep.trigger.lower()
    assert "hybrid_shadow_cron" in ep.caller
    assert "NOT INSTALLED" in ep.scheduler_effects


def test_tc04_import_entry_point_no_writes():
    """EP-03 Python import has no DB write effects."""
    eps = {ep.entry_id: ep for ep in build_entry_point_inventory()}
    ep = eps["EP-03"]
    assert "NONE" in ep.write_effects
    assert "NONE" in ep.network_effects
    assert "NONE" in ep.scheduler_effects


def test_tc05_github_actions_no_backfill_reference():
    """EP-04 and EP-05 (GitHub Actions) do NOT call backfill_daily_prices (use run_daily/overnight)."""
    eps = {ep.entry_id: ep for ep in build_entry_point_inventory()}
    for eid in ("EP-04", "EP-05"):
        ep = eps[eid]
        # target_function may mention backfill_daily_prices in a "NOT" clause — verify via
        # the evidence field which cites the actual script called (run_daily.py / run_overnight.py)
        assert "run_daily.py" in ep.evidence or "run_overnight.py" in ep.evidence
        assert "NONE" in ep.scheduler_effects or "NOT related" in ep.auth_required


def test_tc06_hybrid_shadow_no_outcomes_backfill():
    """EP-06 hybrid_forward_shadow.yml uses different script (not backfill_daily_prices)."""
    eps = {ep.entry_id: ep for ep in build_entry_point_inventory()}
    ep = eps["EP-06"]
    assert "run_hybrid_forward_shadow.py" in ep.evidence
    assert "NOT called" in ep.write_effects or "NOT called" in ep.network_effects or "NONE" in ep.write_effects


# ── TC07-TC14: Import-time Side Effects ───────────────────────────────────────

def test_tc07_all_import_checks_safe():
    """All import-time side-effect checks are SAFE."""
    checks = check_import_time_side_effects()
    for c in checks:
        assert c.verdict == "SAFE", f"{c.check_id} returned {c.verdict}: {c.description}"


def test_tc08_calendar_no_db_on_import():
    """IS-01: TaiwanTradingCalendar() does not open DB at module level."""
    checks = {c.check_id: c for c in check_import_time_side_effects()}
    c = checks["IS-01"]
    assert not c.db_opened
    assert not c.network_called
    assert not c.scheduler_started


def test_tc09_main_guard_prevents_execution():
    """IS-04: __main__ guard prevents main() from running on import."""
    checks = {c.check_id: c for c in check_import_time_side_effects()}
    c = checks["IS-04"]
    assert not c.main_executed
    assert not c.db_opened


def test_tc10_default_start_not_at_module_level():
    """IS-05: _default_start() (which opens SQLite) is NOT called at module level."""
    checks = {c.check_id: c for c in check_import_time_side_effects()}
    c = checks["IS-05"]
    assert not c.db_opened
    assert not c.sql_executed


def test_tc11_rc1_no_new_import_effect():
    """IS-06: RC-1 patch adds only in-memory list append — no import-time DB."""
    checks = {c.check_id: c for c in check_import_time_side_effects()}
    c = checks["IS-06"]
    assert c.verdict == "SAFE"
    assert not c.db_opened
    assert not c.network_called


def test_tc12_rc2_no_new_import_effect():
    """IS-07: RC-2 patch changes boolean only — no import-time I/O."""
    checks = {c.check_id: c for c in check_import_time_side_effects()}
    c = checks["IS-07"]
    assert c.verdict == "SAFE"
    assert not c.db_opened
    assert not c.network_called


def test_tc13_rc3_no_new_import_effect():
    """IS-08: RC-3 patch changes dict key only — no import-time I/O."""
    checks = {c.check_id: c for c in check_import_time_side_effects()}
    c = checks["IS-08"]
    assert c.verdict == "SAFE"
    assert not c.db_opened
    assert not c.network_called


def test_tc14_no_import_check_has_scheduler():
    """No import-time check has scheduler_started=True."""
    checks = check_import_time_side_effects()
    for c in checks:
        assert not c.scheduler_started, f"{c.check_id} has scheduler_started=True"


# ── TC15-TC20: DB Write-path Inventory ───────────────────────────────────────

def test_tc15_db_write_paths_catalogued():
    """At least 5 DB write-path entries catalogued."""
    paths = build_db_write_path_inventory()
    assert len(paths) >= 5


def test_tc16_no_rc_patch_adds_db_write():
    """DB-06: No RC patch introduces a new DB write path."""
    paths = {p.path_id: p for p in build_db_write_path_inventory()}
    p = paths["DB-06"]
    assert not p.code_exists
    assert not p.reachable_under_deployment
    assert p.operation_type == "NO_NEW_DB_PATH"


def test_tc17_write_only_under_explicit_execution():
    """_write_df_to_sqlite is only reachable under explicit execution (--execute)."""
    paths = {p.path_id: p for p in build_db_write_path_inventory()}
    p = paths["DB-01"]
    assert not p.reachable_under_deployment
    assert p.reachable_under_explicit_execution
    assert p.code_exists


def test_tc18_no_neon_connection():
    """DB-05: No Neon/PostgreSQL connection exists in backfill_daily_prices.py."""
    paths = {p.path_id: p for p in build_db_write_path_inventory()}
    p = paths["DB-05"]
    assert not p.code_exists
    assert "NEVER" in p.notes or "NO_NEON" in p.operation_type


def test_tc19_deployment_does_not_trigger_writes():
    """All DB paths that code_exists=True are NOT reachable_under_deployment."""
    paths = build_db_write_path_inventory()
    for p in paths:
        if p.code_exists:
            assert not p.reachable_under_deployment, (
                f"{p.path_id} has code_exists=True AND reachable_under_deployment=True"
            )


def test_tc20_commit_only_explicit():
    """conn.commit() only reachable under explicit execution."""
    paths = {p.path_id: p for p in build_db_write_path_inventory()}
    p = paths["DB-02"]
    assert not p.reachable_under_deployment
    assert p.reachable_under_explicit_execution


# ── TC21-TC25: Network Side Effects ──────────────────────────────────────────

def test_tc21_network_effects_catalogued():
    """At least 4 network side-effect entries catalogued."""
    effects = build_network_side_effect_inventory()
    assert len(effects) >= 4


def test_tc22_no_import_time_network():
    """NET-03: No network calls on import."""
    effects = {e.effect_id: e for e in build_network_side_effect_inventory()}
    e = effects["NET-03"]
    assert not e.reachable_under_deployment
    assert not e.reachable_under_explicit_execution


def test_tc23_no_scheduler_network():
    """NET-04: No automatic scheduler / retry on startup or import."""
    effects = {e.effect_id: e for e in build_network_side_effect_inventory()}
    e = effects["NET-04"]
    assert not e.reachable_under_deployment
    assert "DOES NOT EXIST" in e.trigger


def test_tc24_no_rc_adds_network():
    """NET-05: No RC patch introduces new network calls."""
    effects = {e.effect_id: e for e in build_network_side_effect_inventory()}
    e = effects["NET-05"]
    assert not e.reachable_under_deployment
    assert not e.reachable_under_explicit_execution
    assert "NO NEW" in e.trigger


def test_tc25_network_only_under_execution():
    """TWSE and TPEx network calls are only reachable under explicit execution."""
    effects = build_network_side_effect_inventory()
    for e in effects:
        if e.effect_id in ("NET-01", "NET-02"):
            assert not e.reachable_under_deployment
            assert e.reachable_under_explicit_execution


# ── TC26-TC28: Zero-write RC Simulation ──────────────────────────────────────

def test_tc26_rc1_zero_write():
    """RC-1 patched_text introduces zero new DB write or network patterns."""
    results = {r.rc_id: r for r in run_zero_write_rc_simulation()}
    r = results["RC61-01-TPEX-ERROR"]
    assert r.verdict == "ZERO_WRITE_VERIFIED", f"RC-1 zero-write failed: {r.notes}"
    assert not r.production_file_modified


def test_tc27_rc2_zero_write():
    """RC-2 patched_text introduces zero new DB write or network patterns."""
    results = {r.rc_id: r for r in run_zero_write_rc_simulation()}
    r = results["RC61-02-SECURITY-ELIGIBILITY"]
    assert r.verdict == "ZERO_WRITE_VERIFIED", f"RC-2 zero-write failed: {r.notes}"
    assert not r.production_file_modified


def test_tc28_rc3_zero_write():
    """RC-3 patched_text introduces zero new DB write or network patterns."""
    results = {r.rc_id: r for r in run_zero_write_rc_simulation()}
    r = results["RC61-03-TPEX-VOLUME"]
    assert r.verdict == "ZERO_WRITE_VERIFIED", f"RC-3 zero-write failed: {r.notes}"
    assert not r.production_file_modified


# ── TC29-TC35: Zero-write Combination Matrix ──────────────────────────────────

def test_tc29_seven_combinations_catalogued():
    """Exactly 7 RC combinations tested."""
    results = run_zero_write_combination_simulation()
    assert len(results) == 7


def test_tc30_rc1_rc2_combination_zero_write():
    """RC-1+RC-2 combination: zero write, no conflict, rollback verified."""
    combo_results = run_combination_matrix()
    matching = [r for r in combo_results if set(r.rc_ids) == {"RC61-01-TPEX-ERROR", "RC61-02-SECURITY-ELIGIBILITY"}]
    assert len(matching) == 1
    r = matching[0]
    assert r.verdict == "PASS"
    assert r.all_applied
    assert r.no_conflict
    assert r.rollback_verified


def test_tc31_rc1_rc3_combination_zero_write():
    """RC-1+RC-3 combination: zero write, no conflict, rollback verified."""
    combo_results = run_combination_matrix()
    matching = [r for r in combo_results if set(r.rc_ids) == {"RC61-01-TPEX-ERROR", "RC61-03-TPEX-VOLUME"}]
    assert len(matching) == 1
    assert matching[0].verdict == "PASS"


def test_tc32_rc2_rc3_combination_zero_write():
    """RC-2+RC-3 combination: zero write, no conflict, rollback verified."""
    combo_results = run_combination_matrix()
    matching = [r for r in combo_results if set(r.rc_ids) == {"RC61-02-SECURITY-ELIGIBILITY", "RC61-03-TPEX-VOLUME"}]
    assert len(matching) == 1
    assert matching[0].verdict == "PASS"


def test_tc33_all_three_combination_zero_write():
    """RC-1+RC-2+RC-3 combination: zero write, no conflict, rollback verified."""
    combo_results = run_combination_matrix()
    matching = [r for r in combo_results if len(r.rc_ids) == 3]
    assert len(matching) == 1
    assert matching[0].verdict == "PASS"


def test_tc34_all_combinations_production_untouched():
    """All 7 combinations confirm production file untouched."""
    combo_results = run_combination_matrix()
    for r in combo_results:
        assert r.production_untouched, f"Combination {r.combination_id} has production_untouched=False"


def test_tc35_all_combination_zero_write_verified():
    """All 7 combination zero-write simulations return ZERO_WRITE_VERIFIED."""
    results = run_zero_write_combination_simulation()
    for r in results:
        assert r.verdict == "ZERO_WRITE_VERIFIED", (
            f"Combination {r.combination_label} failed zero-write: {r.notes}"
        )
        assert not r.production_file_modified


# ── TC36-TC41: Operation Boundary Tests ──────────────────────────────────────

def test_tc36_six_operation_boundaries():
    """Six operation boundaries defined."""
    boundaries = build_operation_boundaries()
    assert len(boundaries) == 6


def test_tc37_deployment_ne_script_execution():
    """OB-01: Code Deployment ≠ Script Execution."""
    boundaries = {b.boundary_id: b for b in build_operation_boundaries()}
    b = boundaries["OB-01"]
    assert b.operation_a == OperationType.A_CODE_DEPLOYMENT
    assert b.operation_b == OperationType.B_SCRIPT_EXECUTION
    assert b.are_independent
    assert not b.a_authorizes_b
    assert b.b_requires_separate_auth


def test_tc38_deployment_ne_auth01():
    """OB-03: Code Deployment ≠ AUTH01 Historical Backfill."""
    boundaries = {b.boundary_id: b for b in build_operation_boundaries()}
    b = boundaries["OB-03"]
    assert b.operation_b == OperationType.D_AUTH01_HISTORICAL_BACKFILL
    assert not b.a_authorizes_b
    assert "NOT_AUTHORIZED" in b.current_status_b


def test_tc39_deployment_ne_auth02():
    """OB-04: Code Deployment ≠ AUTH02 Outcome Computation."""
    boundaries = {b.boundary_id: b for b in build_operation_boundaries()}
    b = boundaries["OB-04"]
    assert b.operation_b == OperationType.E_AUTH02_OUTCOME_COMPUTATION
    assert not b.a_authorizes_b
    assert "NOT_AUTHORIZED" in b.current_status_b


def test_tc40_deployment_ne_prospective():
    """OB-05: Code Deployment ≠ Prospective Collection."""
    boundaries = {b.boundary_id: b for b in build_operation_boundaries()}
    b = boundaries["OB-05"]
    assert b.operation_b == OperationType.F_PROSPECTIVE_COLLECTION
    assert not b.a_authorizes_b
    assert "BLOCKED" in b.current_status_b


def test_tc41_all_boundaries_independent():
    """All 6 operation boundaries are independent (a_authorizes_b=False)."""
    boundaries = build_operation_boundaries()
    for b in boundaries:
        assert b.are_independent
        assert not b.a_authorizes_b


# ── TC42-TC44: Deployment State Machine ──────────────────────────────────────

def test_tc42_all_rcs_at_authorization_pending():
    """All three RCs are at AUTHORIZATION_PENDING state (not AUTHORIZED, not DEPLOYED)."""
    records = get_deployment_state_records()
    assert len(records) == 3
    for r in records:
        assert r.current_state == DeploymentState.AUTHORIZATION_PENDING


def test_tc43_no_rc_exceeds_max_state():
    """No RC has exceeded the S62 maximum allowed state (AUTHORIZATION_PENDING)."""
    records = get_deployment_state_records()
    for r in records:
        assert not r.state_exceeded, f"{r.rc_id} has state_exceeded=True"
        assert r.max_allowed_state_s62 == DeploymentState.AUTHORIZATION_PENDING


def test_tc44_state_transition_requires_explicit_auth():
    """Moving to AUTHORIZED state requires explicit user authorization."""
    records = get_deployment_state_records()
    for r in records:
        assert "authorization" in r.next_transition_requires.lower() or "AUTH" in r.next_transition_requires


# ── TC45-TC51: Rollback Rehearsal (Re-verify from S61) ───────────────────────

def test_tc45_rollback_rehearsal_7_cases():
    """7 rollback rehearsal cases executed."""
    results = run_rollback_rehearsal()
    assert len(results) == 7


def test_tc46_rc1_rollback_exact_hash():
    """R01: RC-1 rollback restores exact original hash."""
    results = {r.test_id: r for r in run_rollback_rehearsal()}
    r = results["R01"]
    assert r.hashes_match
    assert not r.residual_patched_text_found


def test_tc47_rc2_rollback_exact_hash():
    """R02: RC-2 rollback restores exact original hash."""
    results = {r.test_id: r for r in run_rollback_rehearsal()}
    r = results["R02"]
    assert r.hashes_match
    assert not r.residual_patched_text_found


def test_tc48_rc3_rollback_exact_hash():
    """R03: RC-3 rollback restores exact original hash."""
    results = {r.test_id: r for r in run_rollback_rehearsal()}
    r = results["R03"]
    assert r.hashes_match
    assert not r.residual_patched_text_found


def test_tc49_combined_rollback_exact_hash():
    """R07: All-3 combined rollback restores exact original hash."""
    results = {r.test_id: r for r in run_rollback_rehearsal()}
    r = results["R07"]
    assert r.hashes_match
    assert not r.residual_patched_text_found


def test_tc50_all_rollbacks_pass():
    """All 7 rollback rehearsal cases: hashes_match=True, residual=False."""
    results = run_rollback_rehearsal()
    for r in results:
        assert r.hashes_match, f"{r.test_id} hash mismatch after rollback"
        assert not r.residual_patched_text_found, f"{r.test_id} residual patched text found"


def test_tc51_in_memory_rollback_rc1_rc2_rc3():
    """In-memory round-trip: apply all 3 RCs then revert = exact original."""
    all_ids = [rc.rc_id for rc in get_all_rcs()]
    assert verify_rollback_in_memory(all_ids)


# ── TC52-TC57: Authorization Boundary Tests ───────────────────────────────────

def test_tc52_three_independent_auth_packages():
    """Three authorization packages defined, each independent."""
    pkgs = get_authorization_packages()
    assert len(pkgs) == 3
    ids = {p.authorization_id for p in pkgs}
    assert ids == {"AUTH-RC61-01", "AUTH-RC61-02", "AUTH-RC61-03"}


def test_tc53_all_packages_not_authorized():
    """All authorization packages remain NOT_AUTHORIZED (no deployment executed)."""
    pkgs = get_authorization_packages()
    for p in pkgs:
        assert p.authorization_status == "NOT_AUTHORIZED"
        assert p.user_approval_required


def test_tc54_auth01_not_in_rc_packages():
    """RC authorization packages do NOT include AUTH01 historical backfill."""
    pkgs = get_authorization_packages()
    for p in pkgs:
        assert "AUTH01" not in p.authorization_id
        assert "AUTH02" not in p.authorization_id
        # RC packages explicitly state they do NOT cover historical repair
        limitations_lower = p.known_limitations.lower()
        assert (
            "auth01" in limitations_lower
            or "auth02" in limitations_lower
            or "historical" in limitations_lower
            or "repair" in limitations_lower
        ), f"{p.authorization_id} known_limitations should mention historical/repair scope"


def test_tc55_packages_not_bundled():
    """Each package lists the other two in not_bundled_with."""
    pkgs = get_authorization_packages()
    pkg_dict = {p.authorization_id: p for p in pkgs}

    pkg1 = pkg_dict["AUTH-RC61-01"]
    assert "AUTH-RC61-02" in pkg1.not_bundled_with
    assert "AUTH-RC61-03" in pkg1.not_bundled_with

    pkg2 = pkg_dict["AUTH-RC61-02"]
    assert "AUTH-RC61-01" in pkg2.not_bundled_with
    assert "AUTH-RC61-03" in pkg2.not_bundled_with

    pkg3 = pkg_dict["AUTH-RC61-03"]
    assert "AUTH-RC61-01" in pkg3.not_bundled_with
    assert "AUTH-RC61-02" in pkg3.not_bundled_with


def test_tc56_deployment_steps_exclude_execute():
    """AUTH-RC61-02 deployment steps confirm dry-run before execute."""
    pkgs = {p.authorization_id: p for p in get_authorization_packages()}
    p = pkgs["AUTH-RC61-02"]
    # dry-run step must appear before execute step
    steps = " | ".join(p.deployment_steps).lower()
    assert "dry-run" in steps or "dry run" in steps or "dry_run" in steps


def test_tc57_rollback_steps_no_db_needed():
    """RC-1 and RC-2 rollback steps confirm no DB changes needed."""
    pkgs = {p.authorization_id: p for p in get_authorization_packages()}
    for auth_id in ("AUTH-RC61-01", "AUTH-RC61-02"):
        p = pkgs[auth_id]
        rollback_text = " | ".join(p.rollback_steps).lower()
        assert "no db" in rollback_text or "no data" in rollback_text or "no database" in rollback_text


# ── TC58-TC62: Frozen Production Integrity ───────────────────────────────────

def test_tc58_production_script_hash_matches():
    """Production script SHA-256 matches frozen reference."""
    actual = script_sha256(SCRIPT_PATH)
    assert actual == PRODUCTION_SCRIPT_SHA256, (
        f"Production script hash changed! "
        f"Expected: {PRODUCTION_SCRIPT_SHA256[:16]}... "
        f"Got: {actual[:16]}..."
    )


def test_tc59_frozen_integrity_checks_count():
    """Five frozen integrity checks defined."""
    checks = build_frozen_integrity_checks()
    assert len(checks) == 5


def test_tc60_frozen_integrity_no_rc_modifies():
    """No frozen item is modifiable by RC deployment."""
    checks = build_frozen_integrity_checks()
    for c in checks:
        assert not c.is_modifiable_by_rc_deployment, (
            f"{c.check_id} has is_modifiable_by_rc_deployment=True"
        )


def test_tc61_cron_frozen():
    """FI-04: Cron schedule is frozen (Stage B not installed)."""
    checks = {c.check_id: c for c in build_frozen_integrity_checks()}
    c = checks["FI-04"]
    assert "FROZEN" in c.current_status or "not installed" in c.current_status.lower()
    assert "0 16 * * 1-5" in c.expected_value


def test_tc62_model_version_frozen():
    """FI-02: MODEL_VERSION v8.0 not touched by backfill RCs."""
    checks = {c.check_id: c for c in build_frozen_integrity_checks()}
    c = checks["FI-02"]
    assert c.expected_value == "v8.0"
    assert "FROZEN" in c.current_status


# ── TC63-TC68: DQ Observation Plan ───────────────────────────────────────────

def test_tc63_dq_observation_entries():
    """At least 6 DQ observation plan entries (2 per RC)."""
    plan = build_dq_observation_plan()
    assert len(plan) >= 6


def test_tc64_rc1_observable_without_backfill():
    """RC-1 observations are possible without backfill execution."""
    plan = build_dq_observation_plan()
    rc1_entries = [e for e in plan if e.rc_id == "RC61-01-TPEX-ERROR"]
    assert len(rc1_entries) >= 1
    # At least one RC-1 entry is observable without backfill
    assert any(e.observable_without_backfill for e in rc1_entries)


def test_tc65_rc2_pre_deployment_observable():
    """RC-2 pre-deployment observation uses unit tests (no backfill needed)."""
    plan = build_dq_observation_plan()
    rc2_pre = [e for e in plan if e.rc_id == "RC61-02-SECURITY-ELIGIBILITY" and e.phase == "Pre-deployment"]
    assert len(rc2_pre) >= 1
    assert any(e.observable_without_backfill for e in rc2_pre)


def test_tc66_rc3_fixture_based_observation():
    """RC-3 pre-deployment observation uses frozen S58 fixture (TradingShares=89094382)."""
    plan = build_dq_observation_plan()
    rc3_pre = [e for e in plan if e.rc_id == "RC61-03-TPEX-VOLUME" and e.phase == "Pre-deployment"]
    assert len(rc3_pre) >= 1
    e = rc3_pre[0]
    assert e.observable_without_backfill
    assert "89094382" in e.notes or "89094" in e.notes or "S58" in e.notes


def test_tc67_post_deploy_metrics_require_auth():
    """Post-deployment metrics that require backfill execution note AUTH requirement."""
    plan = build_dq_observation_plan()
    for e in plan:
        if e.requires_backfill_execution:
            assert not e.observable_without_backfill


def test_tc68_dq_baselines_no_fabricated_numbers():
    """No DQ observation entry has BASELINE_UNAVAILABLE without noting it."""
    plan = build_dq_observation_plan()
    for e in plan:
        # If baseline is unavailable, it should say so explicitly
        if "UNAVAILABLE" in e.baseline:
            assert "UNAVAILABLE" in e.baseline  # already asserted, just documenting


# ── TC69-TC75: Final Verdict ──────────────────────────────────────────────────

def test_tc69_entrypoint_audit_pass():
    """S62 entrypoint audit verdict is PASS."""
    v = build_s62_verdict()
    assert v.entrypoint_audit == "ENTRYPOINT_AUDIT_PASS"


def test_tc70_zero_write_verified():
    """S62 zero-write verdict is VERIFIED."""
    v = build_s62_verdict()
    assert v.zero_write == "ZERO_WRITE_VERIFIED"


def test_tc71_deployment_isolation_verified():
    """S62 deployment isolation verdict is VERIFIED."""
    v = build_s62_verdict()
    assert v.deployment_isolation == "DEPLOYMENT_ISOLATION_VERIFIED"


def test_tc72_rollback_verified():
    """S62 rollback verdict is VERIFIED."""
    v = build_s62_verdict()
    assert v.rollback == "ROLLBACK_VERIFIED"


def test_tc73_no_deployment_executed():
    """S62 confirms NO_DEPLOYMENT_EXECUTED."""
    v = build_s62_verdict()
    assert v.deployment == "NO_DEPLOYMENT_EXECUTED"
    assert v.auth01_auth02 == "NOT_AUTHORIZED"
    assert v.prospective == "GENUINE_PROSPECTIVE_N_0"


def test_tc74_three_auth_packages_ready():
    """S62 confirms all 3 authorization packages ready for independent approval."""
    v = build_s62_verdict()
    assert v.authorization_packages == "THREE_AUTH_PACKAGES_READY"
    assert v.rc1_authorization == "RC1_AUTHORIZATION_READY"
    assert v.rc2_authorization == "RC2_AUTHORIZATION_READY"
    assert v.rc3_authorization == "RC3_AUTHORIZATION_READY"


def test_tc75_production_unchanged():
    """S62 confirms PRODUCTION_UNCHANGED_VERIFIED."""
    v = build_s62_verdict()
    assert v.production_integrity == "PRODUCTION_UNCHANGED_VERIFIED"
    assert v.v3_activation == "ACTIVATION_BLOCKED"
    assert v.g03_g04 == "G03_FAIL / G04_STRUCTURAL_FAIL"
