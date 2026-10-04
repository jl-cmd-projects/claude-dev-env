from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

import claude_account_worker as worker
from dev_env_scripts_constants.account_broker_constants import (
    BrokerConfigurationError,
    JobOutcome,
    Product,
    WAIT_EXIT_CODE,
)
from dev_env_scripts_constants.claude_account_worker_constants import STDOUT_TAIL_CHARACTER_LIMIT


def _outcome(
    *,
    stdout: str = '{"result":"ready","is_error":false}',
    returncode: int = 0,
    account_name: str | None = "extra_2",
    status: str = "served",
    wait_reset_at: datetime | None = None,
) -> JobOutcome:
    return JobOutcome(
        returncode,
        stdout,
        "",
        account_name,
        ((account_name, status),) if account_name else (),
        status,
        None,
        wait_reset_at,
    )


def _run_worker(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    outcome: JobOutcome | Exception,
    *,
    model: str | None = None,
    permission_mode: str = "auto",
) -> tuple[int, dict[str, object], dict[str, object]]:
    prompt_file = tmp_path / "brief.md"
    prompt_file.write_text("standalone brief", encoding="utf-8")
    report_file = tmp_path / "report.json"
    captured: dict[str, object] = {}

    def run_job(product: Product, argv: list[str], **options: object) -> JobOutcome:
        captured.update(product=product, argv=argv, **options)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(worker, "worker_job_runner", run_job)
    exit_code = worker.run_worker(
        prompt_file=prompt_file,
        cwd=tmp_path,
        report_file=report_file,
        model=model,
        permission_mode=permission_mode,
        timeout_minutes=60,
    )
    return exit_code, json.loads(report_file.read_text(encoding="utf-8")), captured


def test_should_send_prompt_and_flags_to_broker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    exit_code, report, captured = _run_worker(
        monkeypatch, tmp_path, _outcome(), model="sonnet", permission_mode="plan"
    )

    assert exit_code == 0
    assert report["account"] == "extra_2"
    assert report["result"] == "ready"
    assert captured["product"] is Product.CLAUDE
    assert captured["argv"] == [
        "claude", "-p", "--output-format", "json", "--permission-mode", "plan", "--model", "sonnet"
    ]
    assert captured["stdin_text"] == "standalone brief"
    assert captured["cwd"] == tmp_path
    assert captured["timeout_seconds"] == 3600


def test_should_report_wait_with_reset_and_exit_three(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    reset_at = datetime(2026, 10, 4, 12, tzinfo=timezone.utc)
    exit_code, report, captured = _run_worker(
        monkeypatch,
        tmp_path,
        _outcome(stdout="", returncode=WAIT_EXIT_CODE, account_name=None, status="wait", wait_reset_at=reset_at),
    )

    assert exit_code == WAIT_EXIT_CODE
    assert report["account"] == "wait"
    assert report["wait_reset_at"] == reset_at.isoformat()
    assert report["reason"] == f"no account has room; next reset at {reset_at.isoformat()}"
    assert report["is_error"] is False
    assert captured["product"] is Product.CLAUDE


def test_should_preserve_exhausted_wait_exit_code(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    exit_code, report, _ = _run_worker(
        monkeypatch,
        tmp_path,
        _outcome(stdout="", returncode=WAIT_EXIT_CODE, account_name=None, status="exhausted"),
    )

    assert exit_code == WAIT_EXIT_CODE
    assert report["reason"] == "no account has room"


def test_should_copy_json_error_flag_into_report(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    exit_code, report, _ = _run_worker(
        monkeypatch, tmp_path, _outcome(stdout='{"result":"failed","is_error":true}')
    )

    assert exit_code == 0
    assert report["result"] == "failed"
    assert report["is_error"] is True


def test_should_keep_stdout_tail_when_output_is_not_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    stdout_text = "x" * (STDOUT_TAIL_CHARACTER_LIMIT + 4)
    exit_code, report, _ = _run_worker(monkeypatch, tmp_path, _outcome(stdout=stdout_text))

    assert exit_code == 0
    assert report["result"] == stdout_text[-STDOUT_TAIL_CHARACTER_LIMIT:]
    assert report["is_error"] is True


def test_should_preserve_served_failure_code(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    exit_code, report, _ = _run_worker(
        monkeypatch, tmp_path, _outcome(returncode=3, status="advisor_blocked")
    )

    assert exit_code == 3
    assert report["account"] == "extra_2"
    assert report["is_error"] is True


def test_should_write_report_for_unreadable_prompt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    report_file = tmp_path / "report.json"
    monkeypatch.setattr(worker, "worker_job_runner", lambda *args, **kwargs: pytest.fail("broker ran"))

    exit_code = worker.run_worker(
        prompt_file=tmp_path / "missing.md",
        cwd=tmp_path,
        report_file=report_file,
        model=None,
        permission_mode="auto",
        timeout_minutes=60,
    )

    report = json.loads(report_file.read_text(encoding="utf-8"))
    assert exit_code == report["exit_code"]
    assert report["reason"] == "prompt file is unreadable"


def test_should_report_broker_configuration_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    exit_code, report, _ = _run_worker(
        monkeypatch, tmp_path, BrokerConfigurationError("account list is invalid")
    )

    assert exit_code == 2
    assert report["reason"] == "account list is invalid"


def test_should_ignore_extra_profile_list(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "extra-profiles.json").write_text("{", encoding="utf-8")

    exit_code, report, _ = _run_worker(monkeypatch, tmp_path, _outcome())

    assert exit_code == 0
    assert report["account"] == "extra_2"


def test_should_require_prompt_and_report_flags() -> None:
    arguments = worker.build_argument_parser().parse_args(
        ["--prompt-file", "brief.md", "--report-file", "report.json"]
    )

    assert arguments.prompt_file == Path("brief.md")
    assert arguments.report_file == Path("report.json")
    assert arguments.permission_mode == "auto"
