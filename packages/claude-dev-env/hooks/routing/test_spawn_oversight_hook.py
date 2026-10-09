import json
import subprocess
import sys
from pathlib import Path

import pytest

import spawn_oversight_hook
from hooks_constants.spawn_oversight_hook_constants import SPAWN_OVERSIGHT_DIRECTIVE

HOOK_SCRIPT = Path(__file__).resolve().parent / "spawn_oversight_hook.py"


def _expected_output() -> dict[str, object]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": SPAWN_OVERSIGHT_DIRECTIVE,
        }
    }


@pytest.mark.parametrize(
    "tool_name",
    [
        "Agent",
        "Task",
        "Workflow",
        "multi_agent_v1__spawn_agent",
        "mcp__hearthbot__start_thread_session",
        "mcp__hearthbot__start_rc_session",
    ],
)
def test_every_spawn_tool_gets_the_oversight_directive(tool_name: str) -> None:
    payload = {"tool_name": tool_name, "tool_input": {"prompt": "Do X."}}
    assert spawn_oversight_hook.decide_hook_output(payload) == _expected_output()


def test_a_subagent_spawning_its_own_agent_gets_the_directive() -> None:
    payload = {
        "tool_name": "Agent",
        "tool_input": {"prompt": "Do X."},
        "agent_id": "agent_child",
    }
    assert spawn_oversight_hook.decide_hook_output(payload) == _expected_output()


def test_a_read_only_helper_spawn_gets_the_directive() -> None:
    payload = {
        "tool_name": "Agent",
        "tool_input": {"subagent_type": "Explore", "prompt": "Find X."},
    }
    assert spawn_oversight_hook.decide_hook_output(payload) == _expected_output()


def test_a_workflow_dispatch_with_an_agent_prompt_gets_the_directive() -> None:
    payload = {
        "tool_name": "mcp__github__actions_run_trigger",
        "tool_input": {"method": "run_workflow", "inputs": {"prompt": "Do X."}},
    }
    assert spawn_oversight_hook.decide_hook_output(payload) == _expected_output()


@pytest.mark.parametrize(
    "payload",
    [
        {
            "tool_name": "mcp__github__actions_run_trigger",
            "tool_input": {"method": "cancel_workflow_run", "run_id": 1},
        },
        {
            "tool_name": "mcp__github__actions_run_trigger",
            "tool_input": {"method": "run_workflow", "inputs": {"head": "branch"}},
        },
        {"tool_name": "Bash", "tool_input": {"command": "ls"}},
        {"tool_name": "mcp__hearthbot__reply", "tool_input": {"text": "hi"}},
        {"tool_name": "Agent", "tool_input": "not an object"},
        {"tool_input": {"prompt": "Do X."}},
    ],
)
def test_other_calls_get_no_output(payload: dict[str, object]) -> None:
    assert spawn_oversight_hook.decide_hook_output(payload) is None


def test_script_prints_the_directive_for_a_spawn() -> None:
    completed = subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)],
        input=json.dumps({"tool_name": "Agent", "tool_input": {"prompt": "Do X."}}),
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(completed.stdout) == _expected_output()


def test_script_prints_nothing_for_empty_stdin() -> None:
    completed = subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)],
        input="",
        capture_output=True,
        text=True,
        check=True,
    )
    assert completed.stdout == ""
