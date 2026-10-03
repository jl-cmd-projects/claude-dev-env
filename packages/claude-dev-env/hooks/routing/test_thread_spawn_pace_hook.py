import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOK_SCRIPT = Path(__file__).resolve().parent / "thread_spawn_pace_hook.py"
SPAWN_INPUT = {
    "thread_id": "cmsg_example",
    "title": "Example thread",
    "ack": "Starting on the example first.",
    "instructions": "Do the example task.",
    "context_message_ids": ["cmsg_example"],
}


def _write_pace_stub(
    tmp_path: Path, exit_code: int, verdict: dict[str, object]
) -> Path:
    stub_path = tmp_path / f"pace_stub_{exit_code}.py"
    stub_path.write_text(
        f"import sys\nprint({json.dumps(json.dumps(verdict))})\nsys.exit({exit_code})\n",
        encoding="utf-8",
    )
    return stub_path


def _run_hook(pace_script: Path, tool_input: object) -> str:
    hook_payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "mcp__hearthbot__start_thread_session",
        "tool_input": tool_input,
    }
    completed = subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)],
        input=json.dumps(hook_payload),
        capture_output=True,
        text=True,
        env={**os.environ, "COORDINATOR_USAGE_PACE_SCRIPT": str(pace_script)},
        check=True,
    )
    return completed.stdout


def _hook_specific_output(stdout: str) -> dict[str, object]:
    return json.loads(stdout)["hookSpecificOutput"]


def _assert_reshaped(stdout: str) -> None:
    decision = _hook_specific_output(stdout)
    assert decision["hookEventName"] == "PreToolUse"
    assert decision["permissionDecision"] == "allow"
    assert decision["updatedInput"] == {
        **SPAWN_INPUT,
        "model": "opus",
        "effort": "low",
    }


def test_should_reshape_the_spawn_when_usage_is_over_pace(tmp_path: Path) -> None:
    _assert_reshaped(
        _run_hook(_write_pace_stub(tmp_path, 0, {"over_pace": True}), SPAWN_INPUT)
    )


def test_should_pass_the_spawn_through_unchanged_when_usage_is_under_pace(
    tmp_path: Path,
) -> None:
    assert (
        _run_hook(_write_pace_stub(tmp_path, 1, {"over_pace": False}), SPAWN_INPUT)
        == ""
    )


def test_should_reshape_the_spawn_when_usage_is_unreadable(tmp_path: Path) -> None:
    _assert_reshaped(
        _run_hook(
            _write_pace_stub(tmp_path, 2, {"over_pace": None, "error": "x"}),
            SPAWN_INPUT,
        )
    )


def test_should_reshape_the_spawn_when_the_pace_script_is_missing(
    tmp_path: Path,
) -> None:
    _assert_reshaped(_run_hook(tmp_path / "absent.py", SPAWN_INPUT))


def test_should_name_no_sonnet_model_in_the_reshaped_spawn(tmp_path: Path) -> None:
    stdout = _run_hook(_write_pace_stub(tmp_path, 0, {"over_pace": True}), SPAWN_INPUT)
    assert "sonnet" not in stdout.lower()


@pytest.mark.parametrize(
    ("tool_input", "reason"),
    [
        (["not", "an", "object"], "start_thread_session input is not a JSON object"),
    ],
)
def test_should_deny_a_spawn_it_cannot_reshape(
    tmp_path: Path, tool_input: object, reason: str
) -> None:
    decision = _hook_specific_output(
        _run_hook(_write_pace_stub(tmp_path, 0, {"over_pace": True}), tool_input)
    )
    assert decision["permissionDecision"] == "deny"
    assert decision["permissionDecisionReason"] == reason
    assert "updatedInput" not in decision
