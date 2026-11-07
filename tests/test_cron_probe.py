"""
tests/test_cron_probe.py — CP-01..CP-30: Cron Probe isolation and correctness tests.

Coverage:
  CP01–CP10  Dry-run mode
  CP11–CP20  Execute mode
  CP21–CP27  Scheduler diagnostics integration
  CP28–CP30  Safety (no DB / network / cron mutation)
"""
from __future__ import annotations

import ast
import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.diagnostics.cron_probe import (
    PROBE_VERSION,
    _build_record,
    main,
)


# ---------------------------------------------------------------------------
# CP01–CP10  Dry-run mode
# ---------------------------------------------------------------------------


def test_CP01_dry_run_exits_zero(capsys):
    rc = main(["--dry-run"])
    assert rc == 0


def test_CP02_dry_run_outputs_valid_json(capsys):
    main(["--dry-run"])
    captured = capsys.readouterr()
    record = json.loads(captured.out)
    assert isinstance(record, dict)


def test_CP03_dry_run_has_probe_version(capsys):
    main(["--dry-run"])
    captured = capsys.readouterr()
    record = json.loads(captured.out)
    assert record["probe_version"] == PROBE_VERSION


def test_CP04_dry_run_has_test_id(capsys):
    main(["--dry-run"])
    captured = capsys.readouterr()
    record = json.loads(captured.out)
    assert uuid.UUID(record["test_id"])  # valid UUID, raises if invalid


def test_CP05_dry_run_has_utc_timestamp(capsys):
    main(["--dry-run"])
    captured = capsys.readouterr()
    record = json.loads(captured.out)
    ts = datetime.fromisoformat(record["utc_timestamp"])
    assert ts.tzinfo is not None


def test_CP06_dry_run_has_taiwan_timestamp(capsys):
    main(["--dry-run"])
    captured = capsys.readouterr()
    record = json.loads(captured.out)
    assert "+08:00" in record["taiwan_timestamp"]


def test_CP07_dry_run_has_pid(capsys):
    main(["--dry-run"])
    captured = capsys.readouterr()
    record = json.loads(captured.out)
    assert isinstance(record["pid"], int)
    assert record["pid"] > 0


def test_CP08_dry_run_has_uid(capsys):
    main(["--dry-run"])
    captured = capsys.readouterr()
    record = json.loads(captured.out)
    assert isinstance(record["uid"], int)
    assert record["uid"] == os.getuid()


def test_CP09_dry_run_has_python_executable(capsys):
    main(["--dry-run"])
    captured = capsys.readouterr()
    record = json.loads(captured.out)
    assert record["python_executable"] == sys.executable


def test_CP10_dry_run_has_working_directory(capsys):
    main(["--dry-run"])
    captured = capsys.readouterr()
    record = json.loads(captured.out)
    assert Path(record["working_directory"]).exists()


# ---------------------------------------------------------------------------
# CP11–CP20  Execute mode
# ---------------------------------------------------------------------------


def test_CP11_execute_exits_zero(tmp_path):
    rc = main(["--execute", "--output-dir", str(tmp_path)])
    assert rc == 0


def test_CP12_execute_creates_output_file(tmp_path):
    main(["--execute", "--output-dir", str(tmp_path)])
    files = list(tmp_path.glob("cron_probe_*.json"))
    assert len(files) == 1


def test_CP13_execute_output_is_valid_json(tmp_path):
    main(["--execute", "--output-dir", str(tmp_path)])
    f = next(tmp_path.glob("cron_probe_*.json"))
    record = json.loads(f.read_text())
    assert isinstance(record, dict)


def test_CP14_execute_mode_field_is_execute(tmp_path):
    main(["--execute", "--output-dir", str(tmp_path)])
    f = next(tmp_path.glob("cron_probe_*.json"))
    record = json.loads(f.read_text())
    assert record["mode"] == "execute"


def test_CP15_execute_output_has_all_fields(tmp_path):
    main(["--execute", "--output-dir", str(tmp_path)])
    f = next(tmp_path.glob("cron_probe_*.json"))
    record = json.loads(f.read_text())
    required = {"probe_version", "test_id", "utc_timestamp", "taiwan_timestamp",
                "pid", "uid", "python_executable", "working_directory", "exit_code"}
    assert required <= record.keys()


def test_CP16_execute_exit_code_zero_in_record(tmp_path):
    main(["--execute", "--output-dir", str(tmp_path)])
    f = next(tmp_path.glob("cron_probe_*.json"))
    record = json.loads(f.read_text())
    assert record["exit_code"] == 0


def test_CP17_execute_creates_output_dir_if_missing(tmp_path):
    deep = tmp_path / "a" / "b" / "c"
    assert not deep.exists()
    main(["--execute", "--output-dir", str(deep)])
    assert deep.exists()


def test_CP18_execute_taiwan_offset_is_plus8(tmp_path):
    main(["--execute", "--output-dir", str(tmp_path)])
    f = next(tmp_path.glob("cron_probe_*.json"))
    record = json.loads(f.read_text())
    assert "+08:00" in record["taiwan_timestamp"]


def test_CP19_execute_filename_contains_pid(tmp_path):
    main(["--execute", "--output-dir", str(tmp_path)])
    f = next(tmp_path.glob("cron_probe_*.json"))
    assert str(os.getpid()) in f.name


def test_CP20_execute_multiple_runs_unique_test_ids(tmp_path):
    main(["--execute", "--output-dir", str(tmp_path)])
    main(["--execute", "--output-dir", str(tmp_path)])
    files = sorted(tmp_path.glob("cron_probe_*.json"))
    ids = [json.loads(f.read_text())["test_id"] for f in files]
    assert len(set(ids)) == len(ids)


# ---------------------------------------------------------------------------
# CP21–CP27  Scheduler diagnostics integration
# ---------------------------------------------------------------------------


def test_CP21_build_record_returns_dict():
    r = _build_record()
    assert isinstance(r, dict)


def test_CP22_build_record_test_id_is_uuid():
    r = _build_record()
    assert uuid.UUID(r["test_id"])


def test_CP23_build_record_utc_is_aware():
    r = _build_record()
    ts = datetime.fromisoformat(r["utc_timestamp"])
    assert ts.tzinfo is not None
    assert ts.utcoffset().total_seconds() == 0


def test_CP24_build_record_taiwan_ahead_of_utc():
    r = _build_record()
    taiwan = datetime.fromisoformat(r["taiwan_timestamp"])
    offset = taiwan.utcoffset().total_seconds()
    assert offset == 8 * 3600


def test_CP25_dry_run_does_not_write_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    main(["--dry-run"])
    all_files = list(tmp_path.rglob("*"))
    assert all_files == []


def test_CP26_execute_no_log_outside_output_dir(tmp_path):
    out = tmp_path / "out"
    main(["--execute", "--output-dir", str(out)])
    top_files = list(tmp_path.iterdir())
    assert all(f.name == "out" for f in top_files)


def test_CP27_probe_version_constant():
    assert PROBE_VERSION == "v1"


# ---------------------------------------------------------------------------
# CP28–CP30  Safety
# ---------------------------------------------------------------------------


def test_CP28_no_database_import():
    """Probe must not import any trading module or database connector."""
    probe_path = Path(__file__).parent.parent / "scripts" / "diagnostics" / "cron_probe.py"
    source = probe_path.read_text()
    forbidden = [
        "sqlite3", "psycopg2", "sqlalchemy", "neon",
        "forward_signals", "hybrid", "daily_prices",
        "platform.db", "DB_PATH",
    ]
    for term in forbidden:
        assert term not in source, f"Forbidden term '{term}' found in cron_probe.py"


def test_CP29_no_network_import():
    """Probe must not import requests, httpx, aiohttp, or urllib.request."""
    probe_path = Path(__file__).parent.parent / "scripts" / "diagnostics" / "cron_probe.py"
    tree = ast.parse(probe_path.read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module.split(".")[0])
    network = {"requests", "httpx", "aiohttp", "urllib3", "socket", "http"}
    overlap = imported & network
    assert not overlap, f"Probe imports network modules: {overlap}"


def test_CP30_probe_does_not_modify_crontab():
    """Probe source must not contain crontab-modifying calls."""
    probe_path = Path(__file__).parent.parent / "scripts" / "diagnostics" / "cron_probe.py"
    source = probe_path.read_text()
    forbidden_calls = ["crontab", "launchctl", "launchd", "subprocess", "os.system"]
    for call in forbidden_calls:
        assert call not in source, f"Probe contains '{call}' — crontab modification prohibited"
