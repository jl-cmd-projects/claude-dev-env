import io
import json
from pathlib import Path

import pytest

import subagent_model_gate

CORRECTIVE_MESSAGE = "Spawn subagents on opus and ask for medium effort in the brief."


def run_gate(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tool_input: dict[str, object],
    tool_name: str = "Agent",
) -> tuple[int, str]:
    hook_input = {
        "hook_event_name": "PreToolUse",
        "tool_name": tool_name,
        "tool_input": tool_input,
    }
    monkeypatch.setattr(
        "sys.stdin", io.TextIOWrapper(io.BytesIO(json.dumps(hook_input).encode("utf-8")))
    )
    exit_code = subagent_model_gate.main()
    return exit_code, capsys.readouterr().err


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))


def test_should_deny_a_fable_spawn_with_the_corrective_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, stderr_text = run_gate(
        monkeypatch, capsys, {"prompt": "Fix the bug.", "model": "fable"}
    )
    assert exit_code == 2
    assert CORRECTIVE_MESSAGE in stderr_text


def test_should_deny_a_sonnet_spawn_with_the_corrective_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, stderr_text = run_gate(
        monkeypatch, capsys, {"prompt": "Fix the bug.", "model": "sonnet"}
    )
    assert exit_code == 2
    assert CORRECTIVE_MESSAGE in stderr_text


@pytest.mark.parametrize("model_id", ["claude-fable-5-1", "claude-sonnet-5-5", "Claude-Fable-5"])
def test_should_deny_a_full_fable_or_sonnet_model_id(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], model_id: str
) -> None:
    exit_code, stderr_text = run_gate(monkeypatch, capsys, {"prompt": "Go.", "model": model_id})
    assert exit_code == 2
    assert model_id in stderr_text


def test_should_deny_a_fable_spawn_through_the_task_tool_name(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, _ = run_gate(monkeypatch, capsys, {"model": "fable"}, tool_name="Task")
    assert exit_code == 2


@pytest.mark.parametrize("model_id", ["opus", "claude-opus-5-5"])
def test_should_allow_an_opus_spawn(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], model_id: str
) -> None:
    exit_code, stderr_text = run_gate(monkeypatch, capsys, {"prompt": "Go.", "model": model_id})
    assert (exit_code, stderr_text) == (0, "")


def test_should_allow_a_spawn_that_omits_the_model(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, stderr_text = run_gate(monkeypatch, capsys, {"prompt": "Go."})
    assert (exit_code, stderr_text) == (0, "")


def test_should_allow_a_sonnet_model_on_a_tool_other_than_agent(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, _ = run_gate(monkeypatch, capsys, {"model": "sonnet"}, tool_name="Bash")
    assert exit_code == 0
