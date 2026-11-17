"""The broker in a Claude Code cloud session: no meter read, the job runs on the session's own account."""

from __future__ import annotations

import io
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import account_broker
import account_broker_support
from account_broker import Account, Meters, Product, ProductAdapter
from dev_env_scripts_constants.account_broker_constants import (
    CLOUD_SESSION_RUN_REASON,
    CLOUD_SESSION_UNREAD_REASON,
    WAIT_EXIT_CODE,
)
from hooks_constants.cloud_session_constants import CLOUD_SESSION_ENV_TRUE_VALUE, CLOUD_SESSION_ENV_VAR

NOW = datetime(2026, 11, 17, tzinfo=timezone.utc)
CLAUDE_CONFIG_DIRECTORY_VARIABLE = "CLAUDE_CONFIG_DIR"
USAGE_LIMIT_SIGNATURE = "usage limit reached"
PROBE_FAILURE_TEXT = "usage probe failed: HTTP Error 403: Forbidden"


def _probing_claude_adapter(all_probed_names: list[str], home: Path) -> ProductAdapter:
    main = Account(Product.CLAUDE, "main", home / ".claude", True, "claude")
    extra = Account(Product.CLAUDE, "ev", home / ".claude-profiles" / "ev", command="ev")

    def read_meters(account: Account) -> Meters:
        all_probed_names.append(account.name)
        raise OSError(PROBE_FAILURE_TEXT)

    return ProductAdapter(lambda: (main, extra), read_meters, CLAUDE_CONFIG_DIRECTORY_VARIABLE, (USAGE_LIMIT_SIGNATURE,))


def _served_runner(all_seen_homes: list[str]):
    def runner(command: object, **options: object) -> subprocess.CompletedProcess[str]:
        all_seen_homes.append(options["env"][CLAUDE_CONFIG_DIRECTORY_VARIABLE])
        return subprocess.CompletedProcess(command, 0, "OK", "")

    return runner


@pytest.fixture
def probed_names(monkeypatch: pytest.MonkeyPatch, isolated_home: Path) -> list[str]:
    all_probed_names: list[str] = []
    monkeypatch.setattr(account_broker_support.time, "sleep", lambda _: None)
    monkeypatch.setitem(
        account_broker.all_product_adapters, Product.CLAUDE, _probing_claude_adapter(all_probed_names, isolated_home)
    )
    return all_probed_names


@pytest.fixture
def cloud_session(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CLOUD_SESSION_ENV_VAR, CLOUD_SESSION_ENV_TRUE_VALUE)


def test_should_run_the_job_on_the_session_account_in_a_cloud_session(
    cloud_session: None, probed_names: list[str], isolated_home: Path, tmp_path: Path
) -> None:
    all_seen_homes: list[str] = []
    report_path = tmp_path / "report.json"

    with account_broker.override_subprocess_runner(_served_runner(all_seen_homes)):
        outcome, report = account_broker._execute(Product.CLAUDE, ("claude", "-p", "task"), now=NOW)
    account_broker._write_report(report_path, report)

    written_report = json.loads(report_path.read_text(encoding="utf-8"))
    assert outcome.returncode == 0
    assert outcome.account_name == "main"
    assert probed_names == []
    assert all_seen_homes == [str((isolated_home / ".claude").resolve())]
    assert written_report["final_decision"]["action"] == "run"
    assert written_report["final_decision"]["account"] == "main"
    assert written_report["final_decision"]["reason"] == CLOUD_SESSION_RUN_REASON
    assert written_report["final_decision"]["resets_at"] is None
    assert written_report["final_decision"]["meter_unread"] == ["main"]


def test_should_exit_zero_from_the_run_command_in_a_cloud_session(
    cloud_session: None, probed_names: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report_path = tmp_path / "report.json"
    monkeypatch.setattr(account_broker.sys, "stdin", io.TextIOWrapper(io.BytesIO(b""), encoding="utf-8"))

    with account_broker.override_subprocess_runner(_served_runner([])):
        exit_code = account_broker.main(("run", "--product", "claude", "--report", str(report_path), "--", "claude", "-p", "task"))

    assert exit_code == 0
    assert probed_names == []
    assert json.loads(report_path.read_text(encoding="utf-8"))["final_decision"]["reason"] == CLOUD_SESSION_RUN_REASON


def test_should_choose_the_session_account_through_the_choose_command_in_a_cloud_session(
    cloud_session: None, probed_names: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = account_broker.main(("choose", "--product", "claude"))

    choice = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert probed_names == []
    assert choice["decision"]["action"] == "run"
    assert choice["decision"]["account"] == "main"
    assert choice["decision"]["reason"] == CLOUD_SESSION_RUN_REASON
    assert choice["accounts"][0]["unread_reason"] == CLOUD_SESSION_UNREAD_REASON


def test_should_wait_after_the_session_account_hits_its_usage_limit_in_a_cloud_session(
    cloud_session: None, probed_names: list[str]
) -> None:
    all_attempts: list[object] = []

    def limited_runner(command: object, **options: object) -> subprocess.CompletedProcess[str]:
        all_attempts.append(command)
        return subprocess.CompletedProcess(command, 1, "", USAGE_LIMIT_SIGNATURE)

    with account_broker.override_subprocess_runner(limited_runner):
        outcome, report = account_broker._execute(Product.CLAUDE, ("claude", "-p", "task"), now=NOW)

    assert len(all_attempts) == 1
    assert probed_names == []
    assert outcome.returncode == WAIT_EXIT_CODE
    assert report.final_decision.action == "wait"
    assert report.final_decision.resets_at == NOW + timedelta(hours=1)


@pytest.mark.parametrize("marker_text", [None, "", "false", "0"])
def test_should_keep_probing_each_account_outside_a_cloud_session(
    marker_text: str | None, probed_names: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    if marker_text is not None:
        monkeypatch.setenv(CLOUD_SESSION_ENV_VAR, marker_text)

    with account_broker.override_subprocess_runner(lambda command, **options: pytest.fail("a waiting job ran")):
        outcome, report = account_broker._execute(Product.CLAUDE, ("claude", "-p", "task"), now=NOW)

    assert sorted(set(probed_names)) == ["ev", "main"]
    assert outcome.returncode == WAIT_EXIT_CODE
    assert report.final_decision.reason.startswith(f"no account meter could be read (main ({PROBE_FAILURE_TEXT})")
