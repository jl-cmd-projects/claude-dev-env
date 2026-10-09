import json
import subprocess
import sys
from pathlib import Path

import pytest

import haiku_spawn_slim_gate
from hooks_constants.haiku_spawn_slim_gate_constants import SLIM_PROFILE_DENY_REASON

HOOK_SCRIPT = Path(__file__).resolve().parent / "haiku_spawn_slim_gate.py"


def _run_hook(payload: dict[str, object]) -> str:
    completed = subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout


@pytest.mark.parametrize(
    ("tool_name", "model"),
    [
        ("Agent", "haiku"),
        ("Task", "Haiku"),
        ("Agent", "claude-haiku-5-5"),
        ("Agent", "claude-haiku-4-5-20251001"),
        ("mcp__hearthbot__start_thread_session", "claude-haiku-5-5"),
    ],
)
def test_should_deny_a_haiku_spawn_with_the_headless_command(tool_name: str, model: str) -> None:
    payload = {"tool_name": tool_name, "tool_input": {"prompt": "Review.", "model": model}}
    hook_output = json.loads(_run_hook(payload))["hookSpecificOutput"]
    assert hook_output["hookEventName"] == "PreToolUse"
    assert hook_output["permissionDecision"] == "deny"
    assert hook_output["permissionDecisionReason"] == SLIM_PROFILE_DENY_REASON


@pytest.mark.parametrize("model", ["opus", "sonnet", "claude-opus-5-5", "fable", None, "", 7])
def test_should_pass_a_spawn_that_names_no_haiku_model(model: object) -> None:
    tool_input = {"prompt": "Review."}
    if model is not None:
        tool_input["model"] = model
    assert _run_hook({"tool_name": "Agent", "tool_input": tool_input}) == ""


def test_should_pass_a_payload_without_tool_input() -> None:
    assert haiku_spawn_slim_gate.decide_hook_output(None) is None


def test_should_name_every_slim_profile_flag_in_the_deny_reason() -> None:
    for each_flag in (
        "account_broker.py",
        "--model haiku",
        "--setting-sources local",
        "--strict-mcp-config",
        "--autocompact 100k",
        "CLAUDE_CODE_DISABLE_CLAUDE_MDS=1",
        "POSIX shell",
    ):
        assert each_flag in SLIM_PROFILE_DENY_REASON
