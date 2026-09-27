from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIRECTORY = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIRECTORY))
TESTS_DIRECTORY = Path(__file__).resolve().parent
if str(TESTS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(TESTS_DIRECTORY))

from local_report_publisher import main
from pr_verification.model import StatusState
from test_local_report_publisher import (
    RecordingRequester,
    _advisory_replies,
    _assert_request_methods,
    _missing_key_arguments,
    _publish_report,
    _run_report,
)


def test_tampered_command_removes_pass_label_and_posts_error(tmp_path: Path) -> None:
    repository_path, manifest_path, base_sha, head_sha = _run_report(
        tmp_path, [sys.executable, "-c", "pass"]
    )
    report_path = tmp_path / "report.json"
    report_fields = json.loads(report_path.read_text(encoding="utf-8"))
    report_fields["checks"][0]["argv"] = [sys.executable, "-c", "raise SystemExit(9)"]
    report_path.write_text(json.dumps(report_fields), encoding="utf-8")
    requester = RecordingRequester(_advisory_replies(head_sha, base_sha))

    outcome = _publish_report(repository_path, manifest_path, report_path, requester)

    assert outcome.status == StatusState.ERROR
    assert outcome.publishable is False
    _assert_request_methods(requester, "GET GET GET DELETE POST")


def test_cli_reports_missing_key_without_network_access(tmp_path: Path) -> None:
    standard_output = io.StringIO()
    standard_error = io.StringIO()

    exit_code = main(
        _missing_key_arguments(tmp_path),
        stdout=standard_output,
        stderr=standard_error,
    )

    assert exit_code == 3
    assert standard_output.getvalue() == ""
    assert "missing.pem" in standard_error.getvalue()


def test_cli_rejects_malformed_repository_without_network_access(
    tmp_path: Path,
) -> None:
    all_arguments = _missing_key_arguments(tmp_path)
    repository_index = all_arguments.index("--repository") + 1
    all_arguments[repository_index] = "owner"
    standard_error = io.StringIO()

    exit_code = main(all_arguments, stderr=standard_error)

    assert exit_code == 3
    assert "owner/name" in standard_error.getvalue()
    assert "Traceback" not in standard_error.getvalue()


def test_publisher_script_displays_help_without_authentication() -> None:
    publisher_path = Path(__file__).resolve().parents[1] / "local_report_publisher.py"
    completed_process = subprocess.run(
        [sys.executable, str(publisher_path), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed_process.returncode == 0
    assert "usage:" in completed_process.stdout


def _token_arguments(tmp_path: Path, variable_name: str) -> list[str]:
    return [
        "--api-url",
        "http://127.0.0.1:9",
        "--token-environment",
        variable_name,
        "--repository",
        "owner/repository",
        "--pull-number",
        "7",
        "--local-repo",
        str(tmp_path),
        "--manifest",
        str(tmp_path / "manifest.json"),
        "--report",
        str(tmp_path / "report.json"),
    ]


def test_cli_names_missing_token_variable_without_network_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PUBLISHER_TEST_TOKEN", raising=False)
    standard_output = io.StringIO()
    standard_error = io.StringIO()

    exit_code = main(
        _token_arguments(tmp_path, "PUBLISHER_TEST_TOKEN"),
        stdout=standard_output,
        stderr=standard_error,
    )

    assert exit_code == 3
    assert standard_output.getvalue() == ""
    assert "PUBLISHER_TEST_TOKEN" in standard_error.getvalue()


def test_cli_token_path_reaches_the_api_without_app_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PUBLISHER_TEST_TOKEN", "token")
    standard_error = io.StringIO()

    exit_code = main(
        _token_arguments(tmp_path, "PUBLISHER_TEST_TOKEN"), stderr=standard_error
    )

    assert exit_code == 3
    assert "Missing publisher setting" not in standard_error.getvalue()
    assert "refused" in standard_error.getvalue().lower()
