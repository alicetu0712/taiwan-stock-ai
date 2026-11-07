"""
src/research/scheduler_diagnostics.py — SD_VERSION = "v2"

Read-only macOS scheduler diagnostics for the Hybrid Shadow Cron pipeline.
No production writes. No crontab modification. No launchctl bootstrap.

Session 35 corrections from Sessions 32/33:
  - forks=0 is NOT evidence of execution failure (normal for all launchd services)
  - BTM entry PRESENT_NOT_NOTIFIED is distinct from NOT_REGISTERED
  - Root cause requires direct evidence; forks alone is insufficient

Evidence hierarchy:
  SD01  Crontab installation check
  SD02  Cron daemon process check
  SD03  launchd / BTM integration check
  SD04  BTM authorization check
  SD05  Runtime environment check
  SD06  Execution evidence check
  SD07  Failure classification
"""
from __future__ import annotations

import json as _json
import shutil
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

SD_VERSION = "v2"

EXPECTED_CRON_PYTHON = "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"
EXPECTED_CRON_HOUR = 16
EXPECTED_CRON_MINUTE = 0
EXPECTED_CRON_DOW = "1-5"
EXPECTED_SCRIPT_REL = "scripts/hybrid_shadow_cron.py"
EXPECTED_LOG_REL = "logs/hybrid_cron.log"
EXPECTED_CRON_STATE_REL = "data/.cron_state.json"

CRON_BINARY = "/usr/sbin/cron"
CRONTAB_BINARY = "/usr/bin/crontab"
BTM_TOOL = "sfltool"
LAUNCHD_LABEL = "com.vix.cron"


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class CrontabStatus(str, Enum):
    INSTALLED_VALID = "INSTALLED_VALID"
    INSTALLED_SUSPECT = "INSTALLED_SUSPECT"
    NOT_INSTALLED = "NOT_INSTALLED"
    INACCESSIBLE = "INACCESSIBLE"


class DaemonStatus(str, Enum):
    RUNNING = "RUNNING"
    NOT_RUNNING = "NOT_RUNNING"
    # RUNNING_IDLE kept for backward compatibility.
    # NOTE: Do NOT set this based on launchd forks=0.
    # forks=0 is normal for ALL macOS launchd services (posix_spawn, not fork()).
    # Only use RUNNING_IDLE when independent application-level evidence shows
    # the daemon is alive but has not processed any scheduled work.
    RUNNING_IDLE = "RUNNING_IDLE"


class BTMStatus(str, Enum):
    AUTHORIZED = "AUTHORIZED"               # enabled, allowed, notified (0xb)
    PRESENT_NOT_NOTIFIED = "PRESENT_NOT_NOTIFIED"  # enabled, allowed, NOT notified (0x3)
    NOT_REGISTERED = "NOT_REGISTERED"       # entry absent from BTM database
    BLOCKED = "BLOCKED"                     # entry present but explicitly blocked
    UNAVAILABLE = "UNAVAILABLE"             # sfltool not available


class SchedulerTriggerStatus(str, Enum):
    CONFIRMED = "SCHEDULER_TRIGGER_CONFIRMED"
    # Daemon running but no independent trigger evidence
    UNVERIFIED = "SCHEDULER_TRIGGER_UNVERIFIED"
    # No execution log / process spawn observed; does NOT mean trigger failed
    NOT_OBSERVED = "SCHEDULED_EXECUTION_NOT_OBSERVED"
    # Only with independent direct evidence (scheduler log, process audit)
    FAILURE_CONFIRMED = "SCHEDULER_TRIGGER_FAILURE_CONFIRMED"


class EvidenceConfidence(str, Enum):
    DIRECT = "DIRECT"               # First-hand system evidence (BTM denial log, process exit)
    CORROBORATED = "CORROBORATED"   # Multiple independent indirect sources agree
    INDIRECT = "INDIRECT"           # Single circumstantial source
    INSUFFICIENT = "INSUFFICIENT"   # Hypothesis only, no supporting evidence


class FailureClass(str, Enum):
    CRONTAB_NOT_INSTALLED = "CRONTAB_NOT_INSTALLED"
    CRONTAB_SYNTAX_ERROR = "CRONTAB_SYNTAX_ERROR"
    SCHEDULER_NOT_TRIGGERING = "SCHEDULER_NOT_TRIGGERING"
    BTM_AUTHORIZATION_MISSING = "BTM_AUTHORIZATION_MISSING"
    TCC_PERMISSION_DENIED = "TCC_PERMISSION_DENIED"
    EXECUTION_ENVIRONMENT_FAILURE = "EXECUTION_ENVIRONMENT_FAILURE"
    SCRIPT_RUNTIME_FAILURE = "SCRIPT_RUNTIME_FAILURE"
    LOGGING_FAILURE = "LOGGING_FAILURE"
    ROOT_CAUSE_INCONCLUSIVE = "ROOT_CAUSE_INCONCLUSIVE"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class RootCauseClaim:
    claim: str
    supporting_evidence: list[str]
    contradictory_evidence: list[str]
    confidence: EvidenceConfidence
    remaining_verification: str


@dataclass
class CronExecutionEvidenceReport:
    """
    Structured evidence for whether the cron job executed.

    Rules:
    - observed_process_start=False → NOT_OBSERVED (not FAILURE_CONFIRMED)
    - trigger_source from application self-report → UNVERIFIED (not CONFIRMED)
    - CONFIRMED/FAILURE_CONFIRMED require independent direct evidence (scheduler log,
      process audit entry, or controlled probe result)
    """
    scheduled_at: Optional[str]
    observed_process_start: bool
    observed_process_exit: Optional[int]
    scheduler_log: Optional[str]
    application_log: Optional[str]
    stdout_stderr: Optional[str]
    trigger_source: Optional[str]
    source_reliability: EvidenceConfidence
    evidence_confidence: EvidenceConfidence
    execution_verdict: SchedulerTriggerStatus


@dataclass
class CrontabAudit:
    raw_entry: Optional[str]
    line_count: int
    status: CrontabStatus
    has_crlf: bool
    has_percent: bool
    hour: Optional[str]
    minute: Optional[str]
    dow: Optional[str]
    python_path: Optional[str]
    script_path: Optional[str]
    log_path: Optional[str]
    issues: list[str] = field(default_factory=list)


@dataclass
class DaemonAudit:
    pid: Optional[int]
    status: DaemonStatus
    ppid: Optional[int]
    uid: Optional[int]
    start_time: Optional[str]
    elapsed: Optional[str]
    fork_count: int
    launchd_state: Optional[str]
    launchd_forks: int
    btm_linked: bool
    issues: list[str] = field(default_factory=list)
    # Session 35: trigger status is independent of forks count
    scheduler_trigger_status: SchedulerTriggerStatus = field(
        default=SchedulerTriggerStatus.UNVERIFIED
    )


@dataclass
class BTMAudit:
    tool_available: bool
    total_entries: int
    cron_entry_found: bool
    cron_disposition: Optional[str]
    status: BTMStatus
    issues: list[str] = field(default_factory=list)
    # Session 35: parsed from BTM output
    btm_generation: Optional[int] = None
    btm_entry_enabled: Optional[bool] = None
    btm_entry_allowed: Optional[bool] = None
    btm_entry_notified: Optional[bool] = None


@dataclass
class EnvironmentAudit:
    python_at_cron_path: bool
    python_version: Optional[str]
    script_exists: bool
    log_dir_writable: bool
    cron_path_env: str
    python_in_cron_path: bool
    execution_log_exists: bool = False   # hybrid_cron.log exists
    issues: list[str] = field(default_factory=list)


@dataclass
class FailureClassification:
    primary: FailureClass
    secondary: Optional[FailureClass]
    # 'confidence' kept as string for backward compat; maps to confidence_level
    confidence: str
    evidence: list[str]
    proposed_fix: str
    approval_required: bool
    confidence_level: EvidenceConfidence = field(default=EvidenceConfidence.INDIRECT)
    root_cause_claims: list[RootCauseClaim] = field(default_factory=list)


@dataclass
class SchedulerDiagnosticsReport:
    sd_version: str
    crontab: CrontabAudit
    daemon: DaemonAudit
    btm: BTMAudit
    environment: EnvironmentAudit
    classification: FailureClassification
    summary: str
    execution_evidence: Optional[CronExecutionEvidenceReport] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(cmd: list[str], timeout: int = 10) -> tuple[int, str, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except (subprocess.TimeoutExpired, FileNotFoundError, PermissionError) as e:
        return -1, "", str(e)


def _parse_btm_disposition(disposition: str) -> tuple[Optional[bool], Optional[bool], Optional[bool]]:
    """
    Parse BTM disposition string into (enabled, allowed, notified) booleans.

    Examples:
      "[enabled, allowed, notified] (0xb)"    → (True,  True,  True)
      "[enabled, allowed, not notified] (0x3)" → (True,  True,  False)
      "[disabled, blocked] (0x0)"              → (False, False, False)
    """
    d = disposition.lower()
    enabled = "enabled" in d and "not enabled" not in d
    allowed = "allowed" in d and "not allowed" not in d
    # "not notified" must be checked before "notified" to avoid false positive
    if "not notified" in d:
        notified = False
    else:
        notified = "notified" in d
    return enabled, allowed, notified


# ---------------------------------------------------------------------------
# Audit functions
# ---------------------------------------------------------------------------

def audit_crontab() -> CrontabAudit:
    rc, stdout, stderr = _run([CRONTAB_BINARY, "-l"])

    if rc != 0 or not stdout.strip():
        return CrontabAudit(
            raw_entry=None,
            line_count=0,
            status=CrontabStatus.NOT_INSTALLED,
            has_crlf=False,
            has_percent=False,
            hour=None,
            minute=None,
            dow=None,
            python_path=None,
            script_path=None,
            log_path=None,
            issues=["No crontab entry found"],
        )

    # Check for CRLF before splitlines() strips the \r
    has_crlf = "\r" in stdout

    lines = [ln for ln in stdout.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    if not lines:
        return CrontabAudit(
            raw_entry=stdout,
            line_count=0,
            status=CrontabStatus.NOT_INSTALLED,
            has_crlf=has_crlf,
            has_percent=False,
            hour=None,
            minute=None,
            dow=None,
            python_path=None,
            script_path=None,
            log_path=None,
            issues=["Crontab exists but all lines are comments"],
        )

    entry = lines[0]
    issues = []
    if has_crlf:
        issues.append("CRLF detected in cron entry")

    has_percent = "%" in entry
    if has_percent:
        issues.append("Unescaped % in cron entry (use \\%)")

    # Parse cron fields: min hour dom mon dow cmd
    parts = entry.split()
    minute_field = parts[0] if len(parts) > 0 else None
    hour_field = parts[1] if len(parts) > 1 else None
    dow_field = parts[4] if len(parts) > 4 else None

    if hour_field != str(EXPECTED_CRON_HOUR):
        issues.append(f"Unexpected hour: {hour_field} (expected {EXPECTED_CRON_HOUR})")
    if minute_field != str(EXPECTED_CRON_MINUTE):
        issues.append(f"Unexpected minute: {minute_field} (expected {EXPECTED_CRON_MINUTE})")
    if dow_field != EXPECTED_CRON_DOW:
        issues.append(f"Unexpected DOW: {dow_field} (expected {EXPECTED_CRON_DOW})")

    python_path = None
    script_path = None
    log_path = None
    if len(parts) >= 6:
        python_path = parts[5]
        if python_path != EXPECTED_CRON_PYTHON:
            issues.append(f"Python path mismatch: {python_path}")

    for p in parts:
        if p.endswith(".py") and "hybrid_shadow_cron" in p:
            script_path = p
        if p.endswith(".log") and "hybrid_cron" in p:
            log_path = p

    if not script_path:
        issues.append("hybrid_shadow_cron.py not found in cron command")
    if not log_path:
        issues.append("hybrid_cron.log redirect not found in cron command")

    status = CrontabStatus.INSTALLED_VALID if not issues else CrontabStatus.INSTALLED_SUSPECT

    return CrontabAudit(
        raw_entry=entry,
        line_count=len(lines),
        status=status,
        has_crlf=has_crlf,
        has_percent=has_percent,
        hour=hour_field,
        minute=minute_field,
        dow=dow_field,
        python_path=python_path,
        script_path=script_path,
        log_path=log_path,
        issues=issues,
    )


def audit_daemon() -> DaemonAudit:
    """
    Audit the cron daemon state.

    Session 35 correction: launchd_forks=0 is NOT evidence of execution failure.
    macOS uses posix_spawn() for all service launches; fork() is never called by
    launchd. ALL launchd services show forks=0 (confirmed: com.apple.logd,
    com.apple.notifyd). The forks counter is preserved as diagnostic metadata only.
    """
    rc, stdout, _ = _run(["pgrep", "-x", "cron"])
    pids = [int(p) for p in stdout.strip().splitlines() if p.strip()]
    pid = pids[0] if pids else None

    if not pid:
        return DaemonAudit(
            pid=None,
            status=DaemonStatus.NOT_RUNNING,
            ppid=None,
            uid=None,
            start_time=None,
            elapsed=None,
            fork_count=0,
            launchd_state=None,
            launchd_forks=0,
            btm_linked=False,
            issues=["cron daemon not running"],
            scheduler_trigger_status=SchedulerTriggerStatus.NOT_OBSERVED,
        )

    rc2, ps_out, _ = _run(["ps", "-p", str(pid), "-o", "pid,ppid,uid,stat,start,etime,command"])

    rc3, lc_out, _ = _run(["launchctl", "print", f"system/{LAUNCHD_LABEL}"])
    launchd_state = None
    launchd_forks = 0

    if lc_out:
        for line in lc_out.splitlines():
            line = line.strip()
            if line.startswith("state ="):
                launchd_state = line.split("=", 1)[1].strip()
            if line.startswith("forks ="):
                try:
                    launchd_forks = int(line.split("=", 1)[1].strip())
                except ValueError:
                    pass

    rc4, otool_out, _ = _run(["otool", "-L", CRON_BINARY])
    btm_linked = "BackgroundTaskManagement" in otool_out

    issues = []
    # Preserve forks as diagnostic metadata with correct interpretation
    issues.append(
        f"launchd forks_counter={launchd_forks} "
        "(metadata only — forks=0 is normal for all macOS launchd services using posix_spawn)"
    )
    if btm_linked:
        issues.append(
            "cron linked against BackgroundTaskManagement.framework — "
            "cronBTMCheck is called before each job fork"
        )

    ppid_val = None
    uid_val = None
    start_val = None
    elapsed_val = None
    if ps_out:
        ps_lines = ps_out.strip().splitlines()
        if len(ps_lines) >= 2:
            ps_parts = ps_lines[1].split(None, 6)
            if len(ps_parts) >= 2:
                try:
                    ppid_val = int(ps_parts[1])
                except ValueError:
                    pass
            if len(ps_parts) >= 3:
                try:
                    uid_val = int(ps_parts[2])
                except ValueError:
                    pass
            if len(ps_parts) >= 5:
                start_val = ps_parts[4]
            if len(ps_parts) >= 6:
                elapsed_val = ps_parts[5]

    # Session 35 correction: status is RUNNING when daemon is alive.
    # Do NOT use RUNNING_IDLE based solely on launchd_forks=0.
    status = DaemonStatus.RUNNING

    return DaemonAudit(
        pid=pid,
        status=status,
        ppid=ppid_val,
        uid=uid_val,
        start_time=start_val,
        elapsed=elapsed_val,
        fork_count=launchd_forks,
        launchd_state=launchd_state,
        launchd_forks=launchd_forks,
        btm_linked=btm_linked,
        issues=issues,
        scheduler_trigger_status=SchedulerTriggerStatus.UNVERIFIED,
    )


def audit_btm() -> BTMAudit:
    """
    Audit the BTM (Background Task Management) database for a cron entry.

    Uses Python string parsing (not shell grep) to avoid the Session 32 error
    where `grep -i "cron|hybrid"` without -E flag searched for a literal pipe
    character rather than performing OR alternation.

    Session 35: distinguishes PRESENT_NOT_NOTIFIED (0x3) from NOT_REGISTERED.
    """
    if not shutil.which(BTM_TOOL):
        return BTMAudit(
            tool_available=False,
            total_entries=0,
            cron_entry_found=False,
            cron_disposition=None,
            status=BTMStatus.UNAVAILABLE,
            issues=["sfltool not found"],
        )

    rc, stdout, stderr = _run(["sfltool", "dumpbtm"], timeout=15)
    if rc != 0 or not stdout:
        return BTMAudit(
            tool_available=True,
            total_entries=0,
            cron_entry_found=False,
            cron_disposition=None,
            status=BTMStatus.UNAVAILABLE,
            issues=[f"sfltool dumpbtm failed: {stderr[:100]}"],
        )

    total = stdout.count("Identifier:")

    cron_found = False
    cron_disposition = None
    btm_generation = None
    # Python string search (case-insensitive substring, NOT shell grep with | literal)
    cron_patterns = ["cron", "com.vix.cron", "hybrid_shadow", "hybrid-shadow"]

    sections = stdout.split("\n\n")
    for section in sections:
        section_lower = section.lower()
        if any(p in section_lower for p in cron_patterns):
            cron_found = True
            for line in section.splitlines():
                stripped = line.strip()
                if stripped.startswith("Disposition:"):
                    cron_disposition = stripped.split(":", 1)[1].strip()
                if stripped.startswith("Generation:"):
                    try:
                        btm_generation = int(stripped.split(":", 1)[1].strip())
                    except (ValueError, IndexError):
                        pass
            break

    enabled = allowed = notified = None
    issues = []

    if not cron_found:
        status = BTMStatus.NOT_REGISTERED
        issues.append(
            "No BTM entry found for cron or hybrid_shadow. "
            "crontab installed but BTM registration absent. "
            "cronBTMCheck behavior with missing entry is undocumented — "
            "controlled test required to confirm causality."
        )
    else:
        if cron_disposition:
            enabled, allowed, notified = _parse_btm_disposition(cron_disposition)

        if cron_disposition and ("block" in cron_disposition.lower() or "denied" in cron_disposition.lower()):
            status = BTMStatus.BLOCKED
            issues.append(f"BTM entry found but disposition is BLOCKED: {cron_disposition}")
        elif notified is False:
            # enabled + allowed but not notified
            status = BTMStatus.PRESENT_NOT_NOTIFIED
            issues.append(
                f"BTM entry present ({cron_disposition}) — enabled and allowed, "
                "but user was never shown the BTM notification (0x8 bit clear). "
                "Whether cronBTMCheck requires 0x8 bit is undocumented. "
                "Causality unverified — controlled probe test required."
            )
        else:
            status = BTMStatus.AUTHORIZED

    return BTMAudit(
        tool_available=True,
        total_entries=total,
        cron_entry_found=cron_found,
        cron_disposition=cron_disposition,
        status=status,
        issues=issues,
        btm_generation=btm_generation,
        btm_entry_enabled=enabled,
        btm_entry_allowed=allowed,
        btm_entry_notified=notified,
    )


def audit_environment(project_root: Optional[Path] = None) -> EnvironmentAudit:
    cron_path = "/usr/bin:/bin:/usr/sbin:/sbin"
    issues = []

    python_exists = Path(EXPECTED_CRON_PYTHON).exists()
    if not python_exists:
        issues.append(f"Python not found at {EXPECTED_CRON_PYTHON}")

    python_version = None
    if python_exists:
        rc, out, _ = _run([EXPECTED_CRON_PYTHON, "--version"])
        python_version = out.strip() or None

    python_in_cron_path = False
    for d in cron_path.split(":"):
        if Path(d, "python3").exists():
            python_in_cron_path = True
            break

    script_exists = False
    log_dir_writable = False
    execution_log_exists = False

    if project_root:
        script_path = project_root / EXPECTED_SCRIPT_REL
        script_exists = script_path.exists()
        if not script_exists:
            issues.append(f"Script not found: {script_path}")

        log_dir = project_root / "logs"
        if log_dir.exists():
            test_file = log_dir / ".scheduler_diag_test"
            try:
                test_file.touch()
                test_file.unlink()
                log_dir_writable = True
            except OSError:
                issues.append(f"Log directory not writable: {log_dir}")
        else:
            issues.append(f"Log directory does not exist: {log_dir}")

        log_file = project_root / EXPECTED_LOG_REL
        execution_log_exists = log_file.exists()

    return EnvironmentAudit(
        python_at_cron_path=python_exists,
        python_version=python_version,
        script_exists=script_exists,
        log_dir_writable=log_dir_writable,
        cron_path_env=cron_path,
        python_in_cron_path=python_in_cron_path,
        execution_log_exists=execution_log_exists,
        issues=issues,
    )


def audit_execution_evidence(project_root: Optional[Path] = None) -> CronExecutionEvidenceReport:
    """
    Build an execution evidence report from available filesystem artifacts.

    Rules (from PART D):
    - Absent log → NOT_OBSERVED (never FAILURE_CONFIRMED from absence alone)
    - App-reported trigger_source=cron_scheduled → UNVERIFIED (not CONFIRMED)
    - CONFIRMED/FAILURE_CONFIRMED require independent direct evidence
    """
    app_log = None
    execution_log_exists = False
    trigger_source = None
    source_reliability = EvidenceConfidence.INSUFFICIENT
    evidence_confidence = EvidenceConfidence.INSUFFICIENT
    verdict = SchedulerTriggerStatus.NOT_OBSERVED

    if project_root:
        log_path = project_root / EXPECTED_LOG_REL
        if log_path.exists():
            execution_log_exists = True
            try:
                app_log = log_path.read_text()[:500]
            except OSError:
                pass

        state_path = project_root / EXPECTED_CRON_STATE_REL
        if state_path.exists():
            try:
                state = _json.loads(state_path.read_text())
                trigger_source = state.get("trigger_source")
            except Exception:
                pass

    if execution_log_exists:
        # App log exists — application started, but trigger source from app is indirect
        if trigger_source == "cron_scheduled":
            # App self-reported trigger; not independent evidence of scheduler action
            source_reliability = EvidenceConfidence.INDIRECT
            evidence_confidence = EvidenceConfidence.INDIRECT
            verdict = SchedulerTriggerStatus.UNVERIFIED
        else:
            source_reliability = EvidenceConfidence.INDIRECT
            evidence_confidence = EvidenceConfidence.INDIRECT
            verdict = SchedulerTriggerStatus.UNVERIFIED
    else:
        # No execution log — scheduled execution not observed
        # This is NOT the same as confirmed trigger failure
        verdict = SchedulerTriggerStatus.NOT_OBSERVED
        evidence_confidence = EvidenceConfidence.INSUFFICIENT

    return CronExecutionEvidenceReport(
        scheduled_at=None,
        observed_process_start=execution_log_exists,
        observed_process_exit=None,
        scheduler_log=None,
        application_log=app_log,
        stdout_stderr=None,
        trigger_source=trigger_source,
        source_reliability=source_reliability,
        evidence_confidence=evidence_confidence,
        execution_verdict=verdict,
    )


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def classify_failure(
    crontab: CrontabAudit,
    daemon: DaemonAudit,
    btm: BTMAudit,
    env: EnvironmentAudit,
    execution_evidence: Optional[CronExecutionEvidenceReport] = None,
) -> FailureClassification:
    """
    Classify the most probable failure cause based on available evidence.

    Session 35 corrections:
    - forks=0 is NOT used as evidence in this function.
    - BTM classification is based on BTM entry state, not daemon fork count.
    - ROOT_CAUSE_INCONCLUSIVE is the correct classification when only indirect
      evidence is available.
    """
    evidence: list[str] = []

    # --- Crontab checks (direct evidence) ---
    if crontab.status == CrontabStatus.NOT_INSTALLED:
        return FailureClassification(
            primary=FailureClass.CRONTAB_NOT_INSTALLED,
            secondary=None,
            confidence="DIRECT",
            evidence=["crontab -l: no entries found"],
            proposed_fix="Run `crontab -e` to install the hybrid cron entry",
            approval_required=True,
            confidence_level=EvidenceConfidence.DIRECT,
        )

    if crontab.has_percent:
        return FailureClassification(
            primary=FailureClass.CRONTAB_SYNTAX_ERROR,
            secondary=None,
            confidence="DIRECT",
            evidence=["Unescaped % in cron entry"],
            proposed_fix="Escape all % as \\% in the crontab entry",
            approval_required=True,
            confidence_level=EvidenceConfidence.DIRECT,
        )

    if crontab.has_crlf:
        return FailureClassification(
            primary=FailureClass.CRONTAB_SYNTAX_ERROR,
            secondary=None,
            confidence="DIRECT",
            evidence=["CRLF line endings in crontab entry"],
            proposed_fix="Remove CRLF: `crontab -l | tr -d '\\r' | crontab -`",
            approval_required=True,
            confidence_level=EvidenceConfidence.DIRECT,
        )

    # --- Daemon check (direct evidence) ---
    if daemon.status == DaemonStatus.NOT_RUNNING:
        return FailureClassification(
            primary=FailureClass.SCHEDULER_NOT_TRIGGERING,
            secondary=None,
            confidence="DIRECT",
            evidence=["cron daemon process not found"],
            proposed_fix="Restart cron: install a valid crontab entry to trigger launchd activation",
            approval_required=True,
            confidence_level=EvidenceConfidence.DIRECT,
        )

    # --- BTM classification (independent of forks count) ---
    # Note: forks count is NOT checked here; see module docstring for why.

    if btm.status == BTMStatus.BLOCKED:
        # BTM explicitly blocking: direct evidence of authorization failure
        evidence.append(f"BTM entry found, disposition BLOCKED: {btm.cron_disposition}")
        evidence.append("cronBTMCheck will return 'not authorized' — job fork silently skipped")
        return FailureClassification(
            primary=FailureClass.BTM_AUTHORIZATION_MISSING,
            secondary=FailureClass.SCHEDULER_NOT_TRIGGERING,
            confidence="DIRECT",
            evidence=evidence,
            proposed_fix=(
                "In System Settings → General → Login Items & Extensions, "
                "find the cron entry and change from blocked to allowed."
            ),
            approval_required=True,
            confidence_level=EvidenceConfidence.DIRECT,
        )

    if btm.status == BTMStatus.NOT_REGISTERED:
        # Indirect: entry absent, but whether this blocks execution is undocumented
        evidence.append(f"BTM database: {btm.total_entries} entries, NO cron entry found")
        evidence.append(
            "cron binary calls cronBTMCheck before fork (confirmed from binary strings)"
        )
        evidence.append(
            "INDIRECT: absence of BTM entry does not directly confirm execution blocked; "
            "controlled probe test required"
        )
        return FailureClassification(
            primary=FailureClass.ROOT_CAUSE_INCONCLUSIVE,
            secondary=FailureClass.BTM_AUTHORIZATION_MISSING,
            confidence="INDIRECT",
            evidence=evidence,
            proposed_fix=(
                "1. Run isolated probe test (cron_probe.py) to verify scheduler trigger. "
                "2. If probe fails: check System Settings → General → Login Items & Extensions. "
                "3. If no cron entry appears: re-install crontab to trigger BTM registration."
            ),
            approval_required=True,
            confidence_level=EvidenceConfidence.INDIRECT,
        )

    if btm.status == BTMStatus.PRESENT_NOT_NOTIFIED:
        # Entry present and allowed, 0x8 (notified) bit clear
        evidence.append(
            f"BTM entry present: {btm.cron_disposition} "
            f"(Generation={btm.btm_generation})"
        )
        evidence.append(
            "enabled=True, allowed=True, notified=False — "
            "user was not shown BTM approval dialog"
        )
        evidence.append(
            "INDIRECT: whether cronBTMCheck requires notified bit is undocumented; "
            "causality unverified without controlled test"
        )
        return FailureClassification(
            primary=FailureClass.ROOT_CAUSE_INCONCLUSIVE,
            secondary=None,
            confidence="INDIRECT",
            evidence=evidence,
            proposed_fix=(
                "1. Run isolated probe test (cron_probe.py) to verify scheduler trigger. "
                "2. If probe fails and BTM is suspected: "
                "System Settings → General → Login Items & Extensions → "
                "find cron entry → toggle to Allow."
            ),
            approval_required=True,
            confidence_level=EvidenceConfidence.INDIRECT,
        )

    # --- Environment checks (direct evidence when reachable) ---
    if not env.python_at_cron_path:
        evidence.append(f"Python not found at {EXPECTED_CRON_PYTHON}")
        return FailureClassification(
            primary=FailureClass.EXECUTION_ENVIRONMENT_FAILURE,
            secondary=None,
            confidence="DIRECT",
            evidence=evidence,
            proposed_fix="Install Python 3.13 at the expected path or update crontab",
            approval_required=True,
            confidence_level=EvidenceConfidence.DIRECT,
        )

    if not env.script_exists:
        evidence.append(f"Script not found: {EXPECTED_SCRIPT_REL}")
        return FailureClassification(
            primary=FailureClass.EXECUTION_ENVIRONMENT_FAILURE,
            secondary=None,
            confidence="DIRECT",
            evidence=evidence,
            proposed_fix="Ensure hybrid_shadow_cron.py exists at the expected path",
            approval_required=False,
            confidence_level=EvidenceConfidence.DIRECT,
        )

    if not env.log_dir_writable:
        evidence.append("Log directory is not writable")
        return FailureClassification(
            primary=FailureClass.LOGGING_FAILURE,
            secondary=None,
            confidence="DIRECT",
            evidence=evidence,
            proposed_fix="Fix permissions on logs/ directory: `chmod 755 logs/`",
            approval_required=False,
            confidence_level=EvidenceConfidence.DIRECT,
        )

    # --- Execution evidence note (not a failure class by itself) ---
    if not env.execution_log_exists and daemon.status == DaemonStatus.RUNNING:
        evidence.append(
            "Execution log absent — SCHEDULED_EXECUTION_NOT_OBSERVED. "
            "Note: absence of log ≠ confirmed trigger failure."
        )

    return FailureClassification(
        primary=FailureClass.ROOT_CAUSE_INCONCLUSIVE,
        secondary=None,
        confidence="INSUFFICIENT",
        evidence=evidence or ["All checked preconditions pass; root cause not identified"],
        proposed_fix=(
            "Run isolated probe test (cron_probe.py --execute) to verify scheduler trigger."
        ),
        approval_required=True,
        confidence_level=EvidenceConfidence.INSUFFICIENT,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_diagnostics(project_root: Optional[Path] = None) -> SchedulerDiagnosticsReport:
    crontab = audit_crontab()
    daemon = audit_daemon()
    btm = audit_btm()
    env = audit_environment(project_root)
    execution_evidence = audit_execution_evidence(project_root)
    classification = classify_failure(crontab, daemon, btm, env, execution_evidence)

    all_issues = crontab.issues + daemon.issues + btm.issues + env.issues
    summary = (
        f"SchedulerDiagnostics[{classification.primary.value}] "
        f"confidence={classification.confidence_level.value} "
        f"issues={len(all_issues)}"
    )

    return SchedulerDiagnosticsReport(
        sd_version=SD_VERSION,
        crontab=crontab,
        daemon=daemon,
        btm=btm,
        environment=env,
        classification=classification,
        summary=summary,
        execution_evidence=execution_evidence,
    )
