import json
import sys
import tempfile
from pathlib import Path

import pytest

from hooks_constants.turn_review_gate_constants import REVIEW_FAILURE_DIAGNOSTIC_TEMPLATE
from turn_review_child import (
    _child_stdout,
    _ChildRun,
    _judge_command,
    _review_command,
    _review_environment,
)

PARENT_SESSION_VARIABLES = (
    "CLAUDE_CODE_SESSION_ID",
    "CLAUDE_CODE_REMOTE_SESSION_ID",
    "CLAUDE_CODE_MESSAGING_SOCKET",
    "CLAUDE_CODE_MESSAGING_TOKEN",
    "CLAUDE_SESSION_INGRESS_TOKEN_FILE",
    "CLAUDE_CODE_POST_FOR_SESSION_INGRESS_V2",
    "CLAUDE_CODE_TEE_SDK_STDOUT",
)
CHILD_REPORT_SOURCE = """import json
import os
import sys

print(json.dumps({
    "cwd": os.getcwd(),
    "stdin": sys.stdin.read(),
    "marker": os.environ.get("CLAUDE_TURN_REVIEW_CHILD"),
    "parent_session": os.environ.get("CLAUDE_CODE_SESSION_ID"),
}))
"""
FAILING_CHILD_SOURCE = """import sys

print("partial review")
sys.exit(3)
"""
SLOW_CHILD_SOURCE = """import time

time.sleep(5)
print("late review")
"""


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home_directory = tmp_path / "home"
    home_directory.mkdir()
    state_directory = tmp_path / "state"
    state_directory.mkdir()
    monkeypatch.setenv("HOME", str(home_directory))
    monkeypatch.setenv("USERPROFILE", str(home_directory))
    monkeypatch.setattr(tempfile, "tempdir", str(state_directory))
    return home_directory


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    repository_root = tmp_path / "app"
    repository_root.mkdir()
    return repository_root


def child_run(
    tmp_path: Path, repository_root: Path, child_source: str, prompt_text: str | None
) -> _ChildRun:
    child_script = tmp_path / "child.py"
    child_script.write_text(child_source)
    return _ChildRun(
        repository_root,
        [sys.executable, str(child_script)],
        prompt_text,
        REVIEW_FAILURE_DIAGNOSTIC_TEMPLATE,
    )


def log_lines(home_directory: Path) -> list[str]:
    log_path = home_directory / ".claude" / "logs" / "turn-review.log"
    return log_path.read_text().splitlines() if log_path.exists() else []


def test_should_build_the_review_command_for_the_range_with_read_only_options(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_directory = tmp_path / "bin"
    stub_directory.mkdir()
    stub_claude = stub_directory / "claude"
    stub_claude.write_text("")
    stub_claude.chmod(0o755)
    monkeypatch.setenv("PATH", str(stub_directory))
    review_command = _review_command("aaa111", "bbb222")
    assert review_command[:7] == [
        str(stub_claude),
        "-p",
        "/code-review low aaa111..bbb222",
        "--model",
        "sonnet",
        "--effort",
        "high",
    ]
    assert review_command[review_command.index("--tools") + 1] == "Read,Grep,Glob,Bash"
    assert review_command[review_command.index("--permission-mode") + 1] == "dontAsk"
    assert json.loads(review_command[review_command.index("--settings") + 1]) == {
        "disableAllHooks": True
    }


def test_should_build_the_judge_command_with_no_prompt_argument(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    judge_command = _judge_command()
    assert judge_command[:6] == ["claude", "-p", "--model", "sonnet", "--effort", "high"]
    assert "--no-session-persistence" in judge_command


def test_should_drop_every_parent_session_variable_from_the_child_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for each_name in PARENT_SESSION_VARIABLES:
        monkeypatch.setenv(each_name, "parent-value")
    monkeypatch.setenv("TURN_REVIEW_KEPT_VARIABLE", "kept")
    child_environment = _review_environment()
    assert [
        each_name for each_name in PARENT_SESSION_VARIABLES if each_name in child_environment
    ] == []
    assert child_environment["CLAUDE_TURN_REVIEW_CHILD"] == "1"
    assert child_environment["TURN_REVIEW_KEPT_VARIABLE"] == "kept"


def test_should_run_the_child_in_the_checkout_with_the_prompt_on_stdin(
    tmp_path: Path, checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "parent-session")
    child_output = _child_stdout(
        child_run(tmp_path, checkout, CHILD_REPORT_SOURCE, "judge data"), 30
    )
    assert child_output is not None
    assert json.loads(child_output) == {
        "cwd": str(checkout.resolve()),
        "stdin": "judge data",
        "marker": "1",
        "parent_session": None,
    }


def test_should_give_no_output_and_log_a_child_that_exits_with_an_error(
    tmp_path: Path, checkout: Path, isolated_home: Path
) -> None:
    assert _child_stdout(child_run(tmp_path, checkout, FAILING_CHILD_SOURCE, None), 30) is None
    assert [each_line.split(" ", 1)[1] for each_line in log_lines(isolated_home)] == [
        "[turn_review_gate] review of app did not finish: exit 3"
    ]


def test_should_give_no_output_and_log_a_child_that_runs_out_of_time(
    tmp_path: Path, checkout: Path, isolated_home: Path
) -> None:
    assert _child_stdout(child_run(tmp_path, checkout, SLOW_CHILD_SOURCE, None), 0.5) is None
    assert [each_line.split(" ", 1)[1] for each_line in log_lines(isolated_home)] == [
        "[turn_review_gate] review of app did not finish: timed out"
    ]
