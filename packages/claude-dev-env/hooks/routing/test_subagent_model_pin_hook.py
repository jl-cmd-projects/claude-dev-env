import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK_SCRIPT = Path(__file__).resolve().parent / "subagent_model_pin_hook.py"
HOOKS_JSON = Path(__file__).resolve().parent.parent / "hooks.json"
CONSTANTS_DIRECTORY = Path(__file__).resolve().parent.parent / "hooks_constants"
SPAWN_INPUT = {"subagent_type": "pstack:poteto-agent", "prompt": "Do X.", "description": "d"}


def _run_hook(tool_input: object) -> str:
    completed = subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)],
        input=json.dumps({"tool_name": "Agent", "tool_input": tool_input}),
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout


@pytest.mark.parametrize(
    "requested_model",
    [None, "", "sonnet", "haiku", "claude-sonnet-5-5", "claude-sonnet-5-5[1m]", "claude-haiku-4-5-20251001"],
)
def test_should_move_the_spawn_to_opus(requested_model: object) -> None:
    tool_input = dict(SPAWN_INPUT)
    if requested_model is not None:
        tool_input["model"] = requested_model
    decision = json.loads(_run_hook(tool_input))["hookSpecificOutput"]
    assert decision["permissionDecision"] == "allow"
    assert decision["updatedInput"] == {**SPAWN_INPUT, "model": "opus"}


@pytest.mark.parametrize("requested_model", ["opus", "fable", "claude-opus-5-5", "claude-fable-5-1"])
def test_should_leave_an_opus_or_fable_spawn_alone(requested_model: str) -> None:
    assert _run_hook({**SPAWN_INPUT, "model": requested_model}) == ""


def test_should_pass_a_tool_input_that_is_not_an_object() -> None:
    assert _run_hook(["not", "an", "object"]) == ""


def test_should_register_the_pin_on_the_agent_and_task_matcher() -> None:
    all_agent_entries = [
        each_entry
        for each_entry in json.loads(HOOKS_JSON.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
        if each_entry["matcher"] == "Agent|Task"
    ]
    all_commands = [
        each_hook["command"] for each_entry in all_agent_entries for each_hook in each_entry["hooks"]
    ]
    assert any("subagent_model_pin_hook.py" in each_command for each_command in all_commands)


def test_should_keep_every_constant_free_of_a_sonnet_model_id() -> None:
    all_offending_files = [
        each_file.name
        for each_file in CONSTANTS_DIRECTORY.glob("*.py")
        if not each_file.name.startswith("test_")
        and each_file.name != "subagent_model_pin_hook_constants.py"
        and "claude-sonnet" in each_file.read_text(encoding="utf-8")
    ]
    assert all_offending_files == []
