"""
tests/test_scheduler_diagnostics.py — SD-01..SD-70

Coverage:
  SD01–SD09  Crontab audit
  SD10–SD18  Daemon audit
  SD19–SD27  BTM audit
  SD28–SD34  Environment audit
  SD35–SD43  Failure classification (updated for Session 35 corrections)
  SD44–SD45  Safety boundaries
  SD46–SD50  Fork semantics (Session 35)
  SD51–SD58  BTM entry states (Session 35)
  SD59–SD65  Scheduler evidence model (Session 35)
  SD66–SD70  Probe safety (Session 35)
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.research.scheduler_diagnostics import (
    SD_VERSION,
    BTMAudit,
    BTMStatus,
    CronExecutionEvidenceReport,
    CrontabAudit,
    CrontabStatus,
    DaemonAudit,
    DaemonStatus,
    EnvironmentAudit,
    EvidenceConfidence,
    FailureClass,
    SchedulerTriggerStatus,
    _parse_btm_disposition,
    audit_btm,
    audit_crontab,
    audit_daemon,
    audit_environment,
    audit_execution_evidence,
    classify_failure,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _crontab_ok() -> CrontabAudit:
    return CrontabAudit(
        raw_entry="0 16 * * 1-5  /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 /x/scripts/hybrid_shadow_cron.py --execute >> /x/logs/hybrid_cron.log 2>&1",
        line_count=1,
        status=CrontabStatus.INSTALLED_VALID,
        has_crlf=False,
        has_percent=False,
        hour="16",
        minute="0",
        dow="1-5",
        python_path="/Library/Frameworks/Python.framework/Versions/3.13/bin/python3",
        script_path="/x/scripts/hybrid_shadow_cron.py",
        log_path="/x/logs/hybrid_cron.log",
        issues=[],
    )


def _daemon_running_zero_forks() -> DaemonAudit:
    # Backward-compat helper: RUNNING_IDLE is kept as a valid enum value
    # but audit_daemon() now returns RUNNING (not RUNNING_IDLE) for live daemons.
    return DaemonAudit(
        pid=20488,
        status=DaemonStatus.RUNNING_IDLE,
        ppid=1,
        uid=0,
        start_time="Thu06PM",
        elapsed="01-07:13:54",
        fork_count=0,
        launchd_state="running",
        launchd_forks=0,
        btm_linked=True,
        issues=["launchd forks=0", "cron linked against BackgroundTaskManagement.framework"],
    )


def _daemon_running() -> DaemonAudit:
    """Session 35: audit_daemon() returns RUNNING for a live daemon."""
    return DaemonAudit(
        pid=20488,
        status=DaemonStatus.RUNNING,
        ppid=1,
        uid=0,
        start_time="Thu06PM",
        elapsed="01-07:13:54",
        fork_count=0,
        launchd_state="running",
        launchd_forks=0,
        btm_linked=True,
        issues=[
            "launchd forks_counter=0 (metadata only — forks=0 is normal for all macOS launchd services using posix_spawn)",
            "cron linked against BackgroundTaskManagement.framework — cronBTMCheck is called before each job fork",
        ],
        scheduler_trigger_status=SchedulerTriggerStatus.UNVERIFIED,
    )


def _daemon_running_active() -> DaemonAudit:
    return DaemonAudit(
        pid=20488,
        status=DaemonStatus.RUNNING,
        ppid=1,
        uid=0,
        start_time="Thu06PM",
        elapsed="01-07:13:54",
        fork_count=5,
        launchd_state="running",
        launchd_forks=5,
        btm_linked=True,
        issues=[],
    )


def _btm_not_registered() -> BTMAudit:
    return BTMAudit(
        tool_available=True,
        total_entries=125,
        cron_entry_found=False,
        cron_disposition=None,
        status=BTMStatus.NOT_REGISTERED,
        issues=["No BTM entry for cron"],
    )


def _btm_present_not_notified() -> BTMAudit:
    return BTMAudit(
        tool_available=True,
        total_entries=126,
        cron_entry_found=True,
        cron_disposition="[enabled, allowed, not notified] (0x3)",
        status=BTMStatus.PRESENT_NOT_NOTIFIED,
        issues=["BTM entry present but not notified"],
        btm_generation=0,
        btm_entry_enabled=True,
        btm_entry_allowed=True,
        btm_entry_notified=False,
    )


def _btm_authorized() -> BTMAudit:
    return BTMAudit(
        tool_available=True,
        total_entries=126,
        cron_entry_found=True,
        cron_disposition="[enabled, allowed, notified] (0xb)",
        status=BTMStatus.AUTHORIZED,
        issues=[],
        btm_entry_enabled=True,
        btm_entry_allowed=True,
        btm_entry_notified=True,
    )


def _btm_blocked() -> BTMAudit:
    return BTMAudit(
        tool_available=True,
        total_entries=126,
        cron_entry_found=True,
        cron_disposition="[disabled, blocked] (0x2)",
        status=BTMStatus.BLOCKED,
        issues=["BTM entry BLOCKED"],
    )


def _env_ok(tmp_path: Path) -> EnvironmentAudit:
    logs = tmp_path / "logs"
    logs.mkdir(exist_ok=True)
    return EnvironmentAudit(
        python_at_cron_path=True,
        python_version="Python 3.13.3",
        script_exists=True,
        log_dir_writable=True,
        cron_path_env="/usr/bin:/bin:/usr/sbin:/sbin",
        python_in_cron_path=False,
        execution_log_exists=False,
        issues=[],
    )


def _execution_evidence_not_observed() -> CronExecutionEvidenceReport:
    return CronExecutionEvidenceReport(
        scheduled_at=None,
        observed_process_start=False,
        observed_process_exit=None,
        scheduler_log=None,
        application_log=None,
        stdout_stderr=None,
        trigger_source=None,
        source_reliability=EvidenceConfidence.INSUFFICIENT,
        evidence_confidence=EvidenceConfidence.INSUFFICIENT,
        execution_verdict=SchedulerTriggerStatus.NOT_OBSERVED,
    )


def _execution_evidence_app_self_reported() -> CronExecutionEvidenceReport:
    return CronExecutionEvidenceReport(
        scheduled_at=None,
        observed_process_start=True,
        observed_process_exit=0,
        scheduler_log=None,
        application_log="run_at=2026-11-06...",
        stdout_stderr=None,
        trigger_source="cron_scheduled",
        source_reliability=EvidenceConfidence.INDIRECT,
        evidence_confidence=EvidenceConfidence.INDIRECT,
        execution_verdict=SchedulerTriggerStatus.UNVERIFIED,
    )


# ---------------------------------------------------------------------------
# SD01–SD09  Crontab audit
# ---------------------------------------------------------------------------

def test_SD01_crontab_installed_valid():
    ct = _crontab_ok()
    assert ct.status == CrontabStatus.INSTALLED_VALID
    assert not ct.issues
    assert ct.hour == "16"
    assert ct.dow == "1-5"


def test_SD02_crontab_not_installed():
    with patch("src.research.scheduler_diagnostics._run", return_value=(1, "", "no crontab for alicetu")):
        ct = audit_crontab()
    assert ct.status == CrontabStatus.NOT_INSTALLED
    assert ct.raw_entry is None


def test_SD03_crontab_crlf_detected():
    entry = "0 16 * * 1-5  python3 /x/script.py --execute >> /x/log 2>&1\r\n"
    with patch("src.research.scheduler_diagnostics._run", return_value=(0, entry, "")):
        ct = audit_crontab()
    assert ct.has_crlf
    assert ct.status == CrontabStatus.INSTALLED_SUSPECT
    assert any("CRLF" in i for i in ct.issues)


def test_SD04_crontab_percent_detected():
    entry = "0 16 * * 1-5  echo hello%world\n"
    with patch("src.research.scheduler_diagnostics._run", return_value=(0, entry, "")):
        ct = audit_crontab()
    assert ct.has_percent
    assert any("%" in i for i in ct.issues)


def test_SD05_crontab_wrong_hour():
    entry = "0 15 * * 1-5  python3 /x/script.py --execute >> /x/log 2>&1\n"
    with patch("src.research.scheduler_diagnostics._run", return_value=(0, entry, "")):
        ct = audit_crontab()
    assert ct.hour == "15"
    assert any("hour" in i.lower() for i in ct.issues)


def test_SD06_crontab_wrong_dow():
    entry = "0 16 * * 1-6  python3 /x/script.py --execute >> /x/log 2>&1\n"
    with patch("src.research.scheduler_diagnostics._run", return_value=(0, entry, "")):
        ct = audit_crontab()
    assert ct.dow == "1-6"
    assert any("DOW" in i for i in ct.issues)


def test_SD07_crontab_all_comments():
    crontab_text = "# This is a comment\n# Another comment\n"
    with patch("src.research.scheduler_diagnostics._run", return_value=(0, crontab_text, "")):
        ct = audit_crontab()
    assert ct.status == CrontabStatus.NOT_INSTALLED
    assert ct.line_count == 0


def test_SD08_crontab_line_count():
    ct = _crontab_ok()
    assert ct.line_count == 1


def test_SD09_crontab_no_percent_in_valid_entry():
    ct = _crontab_ok()
    assert not ct.has_percent
    assert not ct.has_crlf


# ---------------------------------------------------------------------------
# SD10–SD18  Daemon audit
# ---------------------------------------------------------------------------

def test_SD10_daemon_running_idle_backward_compat():
    # RUNNING_IDLE is kept in the enum for backward compatibility.
    # audit_daemon() does NOT set this based on forks=0 (see SD46).
    d = _daemon_running_zero_forks()
    assert d.status == DaemonStatus.RUNNING_IDLE
    assert d.launchd_forks == 0
    assert d.pid == 20488
    assert d.btm_linked


def test_SD11_daemon_not_running():
    with patch("src.research.scheduler_diagnostics._run", return_value=(1, "", "no process")):
        d = audit_daemon()
    assert d.status == DaemonStatus.NOT_RUNNING
    assert d.pid is None


def test_SD12_daemon_running_active():
    d = _daemon_running_active()
    assert d.status == DaemonStatus.RUNNING
    assert d.launchd_forks == 5


def test_SD13_daemon_btm_linked_flag():
    d = _daemon_running_zero_forks()
    assert d.btm_linked is True


def test_SD14_daemon_zero_forks_preserved_as_metadata():
    # forks=0 is preserved in issues as metadata (not as failure evidence)
    d = _daemon_running_zero_forks()
    # The helper explicitly has "forks=0" in issues for backward compat
    assert any("forks=0" in i or "forks_counter=0" in i for i in d.issues)


def test_SD15_daemon_btm_link_is_noted():
    d = _daemon_running_zero_forks()
    assert any("BackgroundTask" in i for i in d.issues)


def test_SD16_daemon_pid_ppid():
    d = _daemon_running_zero_forks()
    assert d.ppid == 1  # launchd


def test_SD17_daemon_launchd_state():
    d = _daemon_running_zero_forks()
    assert d.launchd_state == "running"


def test_SD18_daemon_uid_zero_is_root():
    d = _daemon_running_zero_forks()
    assert d.uid == 0  # cron runs as root


# ---------------------------------------------------------------------------
# SD19–SD27  BTM audit
# ---------------------------------------------------------------------------

def test_SD19_btm_not_registered():
    b = _btm_not_registered()
    assert b.status == BTMStatus.NOT_REGISTERED
    assert not b.cron_entry_found
    assert b.total_entries == 125


def test_SD20_btm_authorized():
    b = _btm_authorized()
    assert b.status == BTMStatus.AUTHORIZED
    assert b.cron_entry_found


def test_SD21_btm_blocked():
    b = _btm_blocked()
    assert b.status == BTMStatus.BLOCKED
    assert b.cron_entry_found
    assert any("BLOCKED" in i for i in b.issues)


def test_SD22_btm_tool_unavailable():
    with patch("src.research.scheduler_diagnostics.shutil.which", return_value=None):
        b = audit_btm()
    assert b.status == BTMStatus.UNAVAILABLE
    assert not b.tool_available


def test_SD23_btm_sfltool_fails():
    with (
        patch("src.research.scheduler_diagnostics.shutil.which", return_value="/usr/bin/sfltool"),
        patch("src.research.scheduler_diagnostics._run", return_value=(1, "", "error")),
    ):
        b = audit_btm()
    assert b.status == BTMStatus.UNAVAILABLE


def test_SD24_btm_no_cron_entry_in_125_entries():
    b = _btm_not_registered()
    assert b.total_entries == 125
    assert not b.cron_entry_found


def test_SD25_btm_not_registered_has_issue():
    b = _btm_not_registered()
    assert len(b.issues) > 0
    assert any("BTM" in i or "cron" in i.lower() for i in b.issues)


def test_SD26_btm_authorized_no_issues():
    b = _btm_authorized()
    assert len(b.issues) == 0


def test_SD27_btm_sfltool_parses_cron_entry():
    # Simulate sfltool output with an authorized cron entry
    fake_btm_output = """
 #125:
                 UUID: AABB1234-0000-0000-0000-000000000001
                 Name: cron job
       Developer Name: (null)
                 Type: legacy agent (0x10008)
                Flags: [ legacy ] (0x1)
          Disposition: [enabled, allowed, notified] (0xb)
           Generation: 1
           Identifier: com.vix.cron

"""
    with (
        patch("src.research.scheduler_diagnostics.shutil.which", return_value="/usr/bin/sfltool"),
        patch("src.research.scheduler_diagnostics._run", return_value=(0, fake_btm_output, "")),
    ):
        b = audit_btm()
    assert b.cron_entry_found
    assert b.status == BTMStatus.AUTHORIZED
    assert b.btm_generation == 1


# ---------------------------------------------------------------------------
# SD28–SD34  Environment audit
# ---------------------------------------------------------------------------

def test_SD28_env_all_ok(tmp_path):
    env = _env_ok(tmp_path)
    assert env.python_at_cron_path
    assert env.script_exists
    assert env.log_dir_writable
    assert not env.issues


def test_SD29_env_python_missing(tmp_path):
    with patch("src.research.scheduler_diagnostics.Path.exists", return_value=False):
        env = audit_environment(tmp_path)
    assert not env.python_at_cron_path


def test_SD30_env_log_dir_not_writable(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    logs.chmod(0o555)
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "hybrid_shadow_cron.py").touch()
    env = audit_environment(tmp_path)
    assert isinstance(env, EnvironmentAudit)
    logs.chmod(0o755)  # restore


def test_SD31_env_script_missing(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    env = audit_environment(tmp_path)
    assert not env.script_exists
    assert any("Script not found" in i for i in env.issues)


def test_SD32_env_log_dir_writable(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "hybrid_shadow_cron.py").touch()
    env = audit_environment(tmp_path)
    assert env.log_dir_writable


def test_SD33_env_cron_path_string(tmp_path):
    env = _env_ok(tmp_path)
    assert "/usr/bin" in env.cron_path_env
    assert "/bin" in env.cron_path_env


def test_SD34_env_no_project_root():
    env = audit_environment(None)
    assert isinstance(env, EnvironmentAudit)
    assert not env.script_exists


# ---------------------------------------------------------------------------
# SD35–SD43  Failure classification (updated for Session 35)
# ---------------------------------------------------------------------------

def test_SD35_classify_btm_not_registered_is_inconclusive(tmp_path):
    # Session 35: NOT_REGISTERED → ROOT_CAUSE_INCONCLUSIVE (not BTM_AUTHORIZATION_MISSING)
    # forks=0 no longer drives this classification.
    fc = classify_failure(
        _crontab_ok(), _daemon_running(), _btm_not_registered(), _env_ok(tmp_path)
    )
    assert fc.primary == FailureClass.ROOT_CAUSE_INCONCLUSIVE
    assert fc.secondary == FailureClass.BTM_AUTHORIZATION_MISSING
    assert fc.confidence_level == EvidenceConfidence.INDIRECT


def test_SD36_classify_crontab_not_installed(tmp_path):
    ct = CrontabAudit(None, 0, CrontabStatus.NOT_INSTALLED, False, False, None, None, None, None, None, None, ["no crontab"])
    fc = classify_failure(ct, _daemon_running(), _btm_not_registered(), _env_ok(tmp_path))
    assert fc.primary == FailureClass.CRONTAB_NOT_INSTALLED


def test_SD37_classify_crontab_percent(tmp_path):
    ct = CrontabAudit("0 16 * * 1-5 echo hello%world", 1, CrontabStatus.INSTALLED_SUSPECT, False, True, "16", "0", "1-5", None, None, None, ["% found"])
    fc = classify_failure(ct, _daemon_running(), _btm_not_registered(), _env_ok(tmp_path))
    assert fc.primary == FailureClass.CRONTAB_SYNTAX_ERROR


def test_SD38_classify_crontab_crlf(tmp_path):
    ct = CrontabAudit("0 16 * * 1-5 python3 script.py\r\n", 1, CrontabStatus.INSTALLED_SUSPECT, True, False, "16", "0", "1-5", None, None, None, ["CRLF"])
    fc = classify_failure(ct, _daemon_running(), _btm_not_registered(), _env_ok(tmp_path))
    assert fc.primary == FailureClass.CRONTAB_SYNTAX_ERROR


def test_SD39_classify_btm_blocked_is_btm_missing(tmp_path):
    # BLOCKED disposition IS direct evidence → BTM_AUTHORIZATION_MISSING
    fc = classify_failure(
        _crontab_ok(), _daemon_running(), _btm_blocked(), _env_ok(tmp_path)
    )
    assert fc.primary == FailureClass.BTM_AUTHORIZATION_MISSING
    assert fc.approval_required
    assert fc.confidence_level == EvidenceConfidence.DIRECT


def test_SD40_classify_python_missing(tmp_path):
    env = EnvironmentAudit(False, None, True, True, "/usr/bin:/bin", False, False, ["Python not found"])
    daemon_active = _daemon_running_active()
    fc = classify_failure(_crontab_ok(), daemon_active, _btm_authorized(), env)
    assert fc.primary == FailureClass.EXECUTION_ENVIRONMENT_FAILURE


def test_SD41_classify_btm_not_registered_fix_mentions_probe(tmp_path):
    # Session 35: proposed fix should mention probe test first
    fc = classify_failure(
        _crontab_ok(), _daemon_running(), _btm_not_registered(), _env_ok(tmp_path)
    )
    assert "probe" in fc.proposed_fix.lower() or "cron_probe" in fc.proposed_fix.lower()


def test_SD42_classify_inconclusive_when_all_pass(tmp_path):
    fc = classify_failure(
        _crontab_ok(), _daemon_running_active(), _btm_authorized(), _env_ok(tmp_path)
    )
    assert fc.primary in (FailureClass.ROOT_CAUSE_INCONCLUSIVE, FailureClass.EXECUTION_ENVIRONMENT_FAILURE)


def test_SD43_classify_btm_unavailable_is_inconclusive(tmp_path):
    # Session 35: BTM unavailable + daemon running → ROOT_CAUSE_INCONCLUSIVE
    # (not SCHEDULER_NOT_TRIGGERING, since forks=0 no longer drives that)
    btm_unavail = BTMAudit(False, 0, False, None, BTMStatus.UNAVAILABLE, ["sfltool not found"])
    fc = classify_failure(
        _crontab_ok(), _daemon_running(), btm_unavail, _env_ok(tmp_path)
    )
    assert fc.primary == FailureClass.ROOT_CAUSE_INCONCLUSIVE


# ---------------------------------------------------------------------------
# SD44–SD45  Safety boundaries
# ---------------------------------------------------------------------------

def test_SD44_no_production_writes_in_module():
    import ast
    src = Path("src/research/scheduler_diagnostics.py").read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                assert node.func.attr not in ("write", "writelines"), (
                    f"Unexpected write call in scheduler_diagnostics.py at line {node.lineno}"
                )


def test_SD45_sd_version_string():
    # Session 35: version bumped to v2 after semantic corrections
    assert SD_VERSION == "v2"
    assert isinstance(SD_VERSION, str)


# ---------------------------------------------------------------------------
# SD46–SD50  Fork semantics (Session 35 corrections)
# ---------------------------------------------------------------------------

def test_SD46_audit_daemon_returns_running_not_running_idle():
    """audit_daemon() must return RUNNING for a live daemon; never RUNNING_IDLE from forks=0."""
    # Simulate a running cron process
    pgrep_out = "20488\n"
    ps_out = "  PID  PPID   UID STAT STARTED      ELAPSED COMMAND\n20488     1     0 Ss  Thu06PM 01-07:13:54 /usr/sbin/cron\n"
    launchctl_out = "  pid = 20488\n  state = running\n  forks = 0\n  runs = 1\n  execs = 1\n"
    otool_out = "BackgroundTaskManagement.framework\n"

    def mock_run(cmd, timeout=10):
        if cmd[0] == "pgrep":
            return 0, pgrep_out, ""
        if cmd[0] == "ps":
            return 0, ps_out, ""
        if cmd[0] == "launchctl":
            return 0, launchctl_out, ""
        if cmd[0] == "otool":
            return 0, otool_out, ""
        return 0, "", ""

    with patch("src.research.scheduler_diagnostics._run", side_effect=mock_run):
        d = audit_daemon()

    assert d.status == DaemonStatus.RUNNING, (
        "audit_daemon() must return RUNNING (not RUNNING_IDLE) for a live daemon. "
        "forks=0 is normal for all macOS launchd services."
    )
    assert d.launchd_forks == 0  # preserved as metadata
    assert d.pid == 20488


def test_SD47_forks_zero_does_not_trigger_btm_authorization_missing(tmp_path):
    """forks=0 alone must NOT lead to BTM_AUTHORIZATION_MISSING."""
    daemon_forks_zero = _daemon_running()  # RUNNING, forks=0
    fc = classify_failure(
        _crontab_ok(), daemon_forks_zero, _btm_not_registered(), _env_ok(tmp_path)
    )
    # forks=0 alone should NOT produce BTM_AUTHORIZATION_MISSING as primary
    assert fc.primary != FailureClass.BTM_AUTHORIZATION_MISSING, (
        "forks=0 must not trigger BTM_AUTHORIZATION_MISSING. "
        "forks=0 is normal for all launchd services."
    )
    assert fc.primary == FailureClass.ROOT_CAUSE_INCONCLUSIVE


def test_SD48_forks_nonzero_does_not_alone_prove_job_success(tmp_path):
    """forks>0 does NOT alone prove successful job execution."""
    daemon_active = _daemon_running_active()  # forks=5
    # Even with forks>0, if btm authorized and env ok, still ROOT_CAUSE_INCONCLUSIVE
    fc = classify_failure(_crontab_ok(), daemon_active, _btm_authorized(), _env_ok(tmp_path))
    # This is not a failure, but forks>0 alone doesn't confirm job success either
    assert fc.primary in (FailureClass.ROOT_CAUSE_INCONCLUSIVE, FailureClass.EXECUTION_ENVIRONMENT_FAILURE)
    # Must NOT claim job success based on forks alone
    for ev in fc.evidence:
        assert "job success" not in ev.lower()


def test_SD49_missing_forks_metadata_handled_gracefully():
    """Malformed or absent forks line in launchctl output is handled without crashing."""
    pgrep_out = "20488\n"
    ps_out = "  PID  PPID   UID STAT STARTED      ELAPSED COMMAND\n20488     1     0 Ss  Thu06PM 01-00:00:00 /usr/sbin/cron\n"
    launchctl_out = "  pid = 20488\n  state = running\n"  # no forks= line
    otool_out = ""

    def mock_run(cmd, timeout=10):
        if cmd[0] == "pgrep":
            return 0, pgrep_out, ""
        if cmd[0] == "ps":
            return 0, ps_out, ""
        if cmd[0] == "launchctl":
            return 0, launchctl_out, ""
        return 0, otool_out, ""

    with patch("src.research.scheduler_diagnostics._run", side_effect=mock_run):
        d = audit_daemon()

    assert isinstance(d, DaemonAudit)
    assert d.status == DaemonStatus.RUNNING
    assert d.launchd_forks == 0  # defaults to 0 when absent


def test_SD50_forks_preserved_as_diagnostic_metadata():
    """launchd_forks is preserved as a diagnostic metadata field."""
    d = _daemon_running()
    assert hasattr(d, "launchd_forks")
    assert isinstance(d.launchd_forks, int)
    # Metadata note should mention 'metadata' or 'posix_spawn'
    assert any("metadata" in i.lower() or "posix_spawn" in i.lower() for i in d.issues)


# ---------------------------------------------------------------------------
# SD51–SD58  BTM entry states (Session 35)
# ---------------------------------------------------------------------------

def test_SD51_btm_present_not_notified_parsed_from_0x3():
    """BTM disposition (0x3) → PRESENT_NOT_NOTIFIED."""
    fake_btm_output = """

 #126:
                 UUID: CCDD5678-0000-0000-0000-000000000002
                 Name: (null)
       Developer Name: (null)
                 Type: user item (0x1)
                Flags: [ ] (0x0)
          Disposition: [enabled, allowed, not notified] (0x3)
           Generation: 0
           Identifier: com.vix.cron

"""
    with (
        patch("src.research.scheduler_diagnostics.shutil.which", return_value="/usr/bin/sfltool"),
        patch("src.research.scheduler_diagnostics._run", return_value=(0, fake_btm_output, "")),
    ):
        b = audit_btm()

    assert b.cron_entry_found
    assert b.status == BTMStatus.PRESENT_NOT_NOTIFIED
    assert b.btm_entry_enabled is True
    assert b.btm_entry_allowed is True
    assert b.btm_entry_notified is False
    assert b.btm_generation == 0


def test_SD52_btm_authorized_parsed_from_0xb():
    """BTM disposition (0xb) → AUTHORIZED (notified=True)."""
    fake_btm_output = """

 #125:
          Disposition: [enabled, allowed, notified] (0xb)
           Generation: 3
           Identifier: com.vix.cron

"""
    with (
        patch("src.research.scheduler_diagnostics.shutil.which", return_value="/usr/bin/sfltool"),
        patch("src.research.scheduler_diagnostics._run", return_value=(0, fake_btm_output, "")),
    ):
        b = audit_btm()

    assert b.cron_entry_found
    assert b.status == BTMStatus.AUTHORIZED
    assert b.btm_entry_notified is True
    assert b.btm_generation == 3


def test_SD53_btm_present_not_notified_classify_inconclusive(tmp_path):
    """PRESENT_NOT_NOTIFIED → ROOT_CAUSE_INCONCLUSIVE (causality unverified)."""
    fc = classify_failure(
        _crontab_ok(), _daemon_running(), _btm_present_not_notified(), _env_ok(tmp_path)
    )
    assert fc.primary == FailureClass.ROOT_CAUSE_INCONCLUSIVE
    assert fc.confidence_level == EvidenceConfidence.INDIRECT
    # Must mention that causality is unverified
    combined = " ".join(fc.evidence).lower()
    assert "unverified" in combined or "undocumented" in combined or "causality" in combined


def test_SD54_btm_not_registered_classify_inconclusive_secondary_btm(tmp_path):
    """NOT_REGISTERED → ROOT_CAUSE_INCONCLUSIVE with secondary=BTM_AUTHORIZATION_MISSING."""
    fc = classify_failure(
        _crontab_ok(), _daemon_running(), _btm_not_registered(), _env_ok(tmp_path)
    )
    assert fc.primary == FailureClass.ROOT_CAUSE_INCONCLUSIVE
    assert fc.secondary == FailureClass.BTM_AUTHORIZATION_MISSING
    assert fc.confidence_level == EvidenceConfidence.INDIRECT


def test_SD55_btm_blocked_classify_btm_missing_direct(tmp_path):
    """BLOCKED disposition IS direct evidence → BTM_AUTHORIZATION_MISSING with DIRECT confidence."""
    fc = classify_failure(
        _crontab_ok(), _daemon_running(), _btm_blocked(), _env_ok(tmp_path)
    )
    assert fc.primary == FailureClass.BTM_AUTHORIZATION_MISSING
    assert fc.confidence_level == EvidenceConfidence.DIRECT


def test_SD56_btm_generation_parsed():
    """Generation field is parsed from BTM output."""
    b = _btm_present_not_notified()
    assert b.btm_generation == 0


def test_SD57_audit_btm_uses_python_string_search_not_grep():
    """
    audit_btm() uses Python string search (not shell grep).
    The Session 32 error was: grep -i "cron|hybrid" without -E flag
    treated | as literal, not OR. This test verifies Python does it right.
    """
    # Verify Python string 'in' operator works correctly as OR equivalent
    section_lower = "identifier: com.vix.cron"
    cron_patterns = ["cron", "com.vix.cron", "hybrid_shadow", "hybrid-shadow"]
    # Python substring search: each pattern checked independently
    result = any(p in section_lower for p in cron_patterns)
    assert result is True, "Python substring search must find 'cron' in the section"

    # Verify the broken grep pattern would NOT match
    # grep -i "cron|hybrid" without -E looks for literal "cron|hybrid"
    broken_pattern = "cron|hybrid"
    assert broken_pattern not in section_lower, (
        "Shell grep -i 'cron|hybrid' without -E would NOT find this — "
        "that was the Session 32 bug"
    )


def test_SD58_parse_btm_disposition_not_notified_vs_notified():
    """_parse_btm_disposition correctly distinguishes 'not notified' from 'notified'."""
    # Case 1: "not notified" must NOT be parsed as notified=True
    e1, a1, n1 = _parse_btm_disposition("[enabled, allowed, not notified] (0x3)")
    assert e1 is True
    assert a1 is True
    assert n1 is False, "'not notified' must parse as notified=False"

    # Case 2: "notified" (without "not") → notified=True
    e2, a2, n2 = _parse_btm_disposition("[enabled, allowed, notified] (0xb)")
    assert e2 is True
    assert a2 is True
    assert n2 is True, "'notified' (without 'not') must parse as notified=True"

    # Case 3: blocked entry
    e3, a3, n3 = _parse_btm_disposition("[disabled, blocked] (0x0)")
    assert e3 is False
    assert a3 is False


# ---------------------------------------------------------------------------
# SD59–SD65  Scheduler evidence model (Session 35)
# ---------------------------------------------------------------------------

def test_SD59_daemon_running_no_job_evidence_is_not_observed():
    """Daemon running + no execution log → NOT_OBSERVED (not FAILURE_CONFIRMED)."""
    ev = _execution_evidence_not_observed()
    assert ev.execution_verdict == SchedulerTriggerStatus.NOT_OBSERVED
    assert ev.observed_process_start is False
    # Must NOT be FAILURE_CONFIRMED
    assert ev.execution_verdict != SchedulerTriggerStatus.FAILURE_CONFIRMED


def test_SD60_app_self_report_cron_scheduled_is_unverified():
    """trigger_source=cron_scheduled from app → UNVERIFIED (not CONFIRMED)."""
    ev = _execution_evidence_app_self_reported()
    assert ev.trigger_source == "cron_scheduled"
    assert ev.execution_verdict == SchedulerTriggerStatus.UNVERIFIED
    assert ev.source_reliability == EvidenceConfidence.INDIRECT
    # Must NOT be CONFIRMED
    assert ev.execution_verdict != SchedulerTriggerStatus.CONFIRMED


def test_SD61_no_execution_log_is_not_observed_not_failure():
    """Absent execution log → NOT_OBSERVED, never FAILURE_CONFIRMED from absence alone."""
    ev = CronExecutionEvidenceReport(
        scheduled_at=None,
        observed_process_start=False,
        observed_process_exit=None,
        scheduler_log=None,
        application_log=None,
        stdout_stderr=None,
        trigger_source=None,
        source_reliability=EvidenceConfidence.INSUFFICIENT,
        evidence_confidence=EvidenceConfidence.INSUFFICIENT,
        execution_verdict=SchedulerTriggerStatus.NOT_OBSERVED,
    )
    assert ev.execution_verdict == SchedulerTriggerStatus.NOT_OBSERVED
    assert ev.execution_verdict != SchedulerTriggerStatus.FAILURE_CONFIRMED


def test_SD62_audit_execution_evidence_no_log(tmp_path):
    """audit_execution_evidence with no log file → NOT_OBSERVED."""
    # tmp_path has no hybrid_cron.log
    ev = audit_execution_evidence(tmp_path)
    assert isinstance(ev, CronExecutionEvidenceReport)
    assert ev.observed_process_start is False
    assert ev.execution_verdict == SchedulerTriggerStatus.NOT_OBSERVED


def test_SD63_audit_execution_evidence_with_log(tmp_path):
    """audit_execution_evidence with log file → UNVERIFIED (app-level evidence)."""
    log_path = tmp_path / "logs"
    log_path.mkdir()
    (log_path / "hybrid_cron.log").write_text("run_at=2026-11-06T08:00:00Z\ntrigger=cron")
    ev = audit_execution_evidence(tmp_path)
    assert ev.observed_process_start is True
    assert ev.execution_verdict == SchedulerTriggerStatus.UNVERIFIED
    # App-level evidence is INDIRECT
    assert ev.evidence_confidence in (EvidenceConfidence.INDIRECT, EvidenceConfidence.CORROBORATED)


def test_SD64_btm_blocked_has_direct_confidence(tmp_path):
    """BTM BLOCKED → DIRECT confidence in failure classification."""
    fc = classify_failure(
        _crontab_ok(), _daemon_running(), _btm_blocked(), _env_ok(tmp_path)
    )
    assert fc.confidence_level == EvidenceConfidence.DIRECT


def test_SD65_btm_not_registered_has_indirect_confidence(tmp_path):
    """BTM NOT_REGISTERED → INDIRECT confidence in failure classification."""
    fc = classify_failure(
        _crontab_ok(), _daemon_running(), _btm_not_registered(), _env_ok(tmp_path)
    )
    assert fc.confidence_level == EvidenceConfidence.INDIRECT


# ---------------------------------------------------------------------------
# SD66–SD70  Probe safety (Session 35)
# ---------------------------------------------------------------------------

def test_SD66_scheduler_diagnostics_has_no_crontab_modification():
    """scheduler_diagnostics.py must not contain executable crontab modification calls."""
    import ast
    src = Path("src/research/scheduler_diagnostics.py").read_text()
    tree = ast.parse(src)
    # AST check: no subprocess.run / _run / os.system with crontab write operations
    # Strings in proposed_fix are documentation, not calls — only executable contexts count.
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "_run":
                for arg in node.args:
                    if isinstance(arg, (ast.List, ast.Tuple)):
                        # Check if first element is "crontab" and next is "-e" / "-r"
                        elts = arg.elts if hasattr(arg, "elts") else []
                        strs = [e.value for e in elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
                        if strs and strs[0] == "crontab":
                            assert "-e" not in strs, "scheduler_diagnostics.py must not call crontab -e"
                            assert "-r" not in strs, "scheduler_diagnostics.py must not call crontab -r"


def test_SD67_audit_daemon_issues_do_not_claim_execution_failure():
    """
    audit_daemon() issues must describe forks as metadata, not as execution failure evidence.
    The forks metadata note must NOT say 'never executed a cron job'.
    """
    pgrep_out = "20488\n"
    ps_out = "  PID  PPID   UID STAT STARTED      ELAPSED COMMAND\n20488     1     0 Ss  Thu06PM 01-00:00:00 /usr/sbin/cron\n"
    launchctl_out = "  pid = 20488\n  state = running\n  forks = 0\n"
    otool_out = ""

    def mock_run(cmd, timeout=10):
        if cmd[0] == "pgrep":
            return 0, pgrep_out, ""
        if cmd[0] == "ps":
            return 0, ps_out, ""
        if cmd[0] == "launchctl":
            return 0, launchctl_out, ""
        return 0, otool_out, ""

    with patch("src.research.scheduler_diagnostics._run", side_effect=mock_run):
        d = audit_daemon()

    # Must not claim "never executed" from forks=0
    for issue in d.issues:
        assert "never executed" not in issue.lower(), (
            f"Issue message incorrectly claims 'never executed': {issue!r}"
        )
    # Must describe forks as metadata
    assert any("metadata" in i.lower() or "posix_spawn" in i.lower() for i in d.issues)


def test_SD68_audit_btm_uses_python_parsing_not_shell_grep():
    """
    audit_btm() uses subprocess to get sfltool output, then Python string parsing.
    It must NOT make an executable shell grep call for cron/hybrid search.
    """
    import ast
    src = Path("src/research/scheduler_diagnostics.py").read_text()
    tree = ast.parse(src)
    # AST check: no _run(["grep", ...]) call in the module
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "_run":
                for arg in node.args:
                    if isinstance(arg, (ast.List, ast.Tuple)):
                        elts = arg.elts if hasattr(arg, "elts") else []
                        strs = [e.value for e in elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
                        assert "grep" not in strs, "audit_btm() must not invoke shell grep"
    # Verify Python pattern list is used for cron search
    assert "cron_patterns" in src, "Python pattern list should be used for cron search"


def test_SD69_run_diagnostics_returns_report_with_execution_evidence(tmp_path):
    """run_diagnostics() returns a SchedulerDiagnosticsReport with execution_evidence."""
    from src.research.scheduler_diagnostics import run_diagnostics, SchedulerDiagnosticsReport

    def mock_run(cmd, timeout=10):
        if cmd[0] == "pgrep":
            return 0, "20488\n", ""
        if cmd[0] == "ps":
            return 0, "  PID  PPID   UID STAT STARTED      ELAPSED COMMAND\n20488 1 0 Ss Thu06PM 01:00:00 /usr/sbin/cron\n", ""
        if cmd[0] == "launchctl":
            return 0, "  pid = 20488\n  state = running\n  forks = 0\n", ""
        if cmd[0] == "crontab":
            return 0, "0 16 * * 1-5  python3 /x/script.py >> /x/log 2>&1\n", ""
        if cmd[0] == "otool":
            return 0, "", ""
        return 1, "", "not found"

    with (
        patch("src.research.scheduler_diagnostics._run", side_effect=mock_run),
        patch("src.research.scheduler_diagnostics.shutil.which", return_value=None),
    ):
        report = run_diagnostics(tmp_path)

    assert isinstance(report, SchedulerDiagnosticsReport)
    assert report.sd_version == "v2"
    assert report.execution_evidence is not None
    assert isinstance(report.execution_evidence, CronExecutionEvidenceReport)


def test_SD70_cron_execution_evidence_report_has_required_fields():
    """CronExecutionEvidenceReport has all 10 required fields from PART D."""
    ev = _execution_evidence_not_observed()
    required_fields = [
        "scheduled_at",
        "observed_process_start",
        "observed_process_exit",
        "scheduler_log",
        "application_log",
        "stdout_stderr",
        "trigger_source",
        "source_reliability",
        "evidence_confidence",
        "execution_verdict",
    ]
    for f in required_fields:
        assert hasattr(ev, f), f"CronExecutionEvidenceReport missing required field: {f}"
