"""Behavior tests for the task subject length gate."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

_BLOCKING_DIR = Path(__file__).resolve().parent
_HOOKS_ROOT = _BLOCKING_DIR.parent
for each_sys_path_entry in (str(_BLOCKING_DIR), str(_HOOKS_ROOT)):
    if each_sys_path_entry not in sys.path:
        sys.path.insert(0, each_sys_path_entry)

import task_subject_length_gate

HOOK_SCRIPT = _BLOCKING_DIR / "task_subject_length_gate.py"
HOOKS_CONFIG = _HOOKS_ROOT / "hooks.json"
SUBJECT_LIMIT = 80

LONG_STATUS_SUBJECT = (
    "Open the automation scripts pull request for the turn review quick eval tool after the"
    " third pre-PR passes run finishes and the separate checker confirms the pick rule repair"
    " on fifteen named cases and twenty thousand random ones"
)
ALL_SHORT_SUBJECTS = [
    "Me: open the automation scripts pull request (last check running)",
    "You: one live try on your PC, then claude-dev-env pull request 2345 can merge",
    "Worker: three end-of-reply checks left to build (card is ready)",
]


def _run_hook_text(stdin_text: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)],
        input=stdin_text,
        capture_output=True,
        text=True,
        check=False,
    )


def _run_hook(tool_name: str, tool_input: object) -> subprocess.CompletedProcess[str]:
    return _run_hook_text(
        json.dumps(
            {"hook_event_name": "PreToolUse", "tool_name": tool_name, "tool_input": tool_input}
        )
    )


def _deny_reason(completed: subprocess.CompletedProcess[str]) -> str:
    assert completed.returncode == 0
    specific_output = json.loads(completed.stdout)["hookSpecificOutput"]
    assert specific_output["hookEventName"] == "PreToolUse"
    assert specific_output["permissionDecision"] == "deny"
    return specific_output["permissionDecisionReason"]


def _assert_silent_pass(completed: subprocess.CompletedProcess[str]) -> None:
    assert completed.returncode == 0
    assert completed.stdout == ""
    assert completed.stderr == ""


def test_should_deny_a_task_create_subject_that_carries_status_detail() -> None:
    reason = _deny_reason(_run_hook("TaskCreate", {"subject": LONG_STATUS_SUBJECT}))

    assert f"{len(LONG_STATUS_SUBJECT)} characters" in reason
    assert str(SUBJECT_LIMIT) in reason
    for each_actor in ("Me", "You", "Worker"):
        assert each_actor in reason
    assert "description" in reason


@pytest.mark.parametrize("subject", ALL_SHORT_SUBJECTS)
def test_should_pass_a_short_subject_that_starts_with_who_acts(subject: str) -> None:
    _assert_silent_pass(_run_hook("TaskCreate", {"subject": subject, "description": "x" * 900}))


def test_should_pass_a_subject_at_the_limit() -> None:
    _assert_silent_pass(_run_hook("TaskCreate", {"subject": "Me: " + "x" * (SUBJECT_LIMIT - 4)}))


def test_should_deny_a_subject_one_character_over_the_limit() -> None:
    reason = _deny_reason(_run_hook("TaskCreate", {"subject": "Me: " + "x" * (SUBJECT_LIMIT - 3)}))

    assert f"{SUBJECT_LIMIT + 1} characters" in reason


def test_should_pass_a_task_update_that_only_changes_status() -> None:
    _assert_silent_pass(_run_hook("TaskUpdate", {"taskId": "3", "status": "completed"}))


def test_should_deny_a_task_update_that_sets_a_long_subject() -> None:
    reason = _deny_reason(_run_hook("TaskUpdate", {"taskId": "3", "subject": LONG_STATUS_SUBJECT}))

    assert f"{len(LONG_STATUS_SUBJECT)} characters" in reason


def test_should_deny_a_todo_write_with_one_long_item_and_name_it() -> None:
    reason = _deny_reason(
        _run_hook(
            "TodoWrite",
            {
                "todos": [
                    {"content": ALL_SHORT_SUBJECTS[0], "status": "completed"},
                    {"content": LONG_STATUS_SUBJECT, "status": "in_progress"},
                ]
            },
        )
    )

    assert LONG_STATUS_SUBJECT[:40] in reason
    assert ALL_SHORT_SUBJECTS[0] not in reason
    assert f"{len(LONG_STATUS_SUBJECT)} characters" in reason
    assert "item 2 " in reason
    for each_actor in ("Me", "You", "Worker"):
        assert each_actor in reason
    assert "description" in reason


def test_should_name_the_first_of_two_long_todo_items() -> None:
    first_long_item = "First " + "a" * SUBJECT_LIMIT
    second_long_item = "Second " + "b" * (SUBJECT_LIMIT + 20)
    reason = _deny_reason(
        _run_hook(
            "TodoWrite",
            {
                "todos": [
                    {"content": first_long_item, "status": "pending"},
                    {"content": second_long_item, "status": "pending"},
                ]
            },
        )
    )

    assert "item 1 " in reason
    assert f"{len(first_long_item)} characters" in reason
    assert "Second" not in reason


def test_should_pass_a_todo_item_at_the_limit() -> None:
    _assert_silent_pass(
        _run_hook(
            "TodoWrite", {"todos": [{"content": "c" * SUBJECT_LIMIT, "status": "pending"}]}
        )
    )


def test_should_deny_a_todo_item_one_character_over_the_limit() -> None:
    reason = _deny_reason(
        _run_hook(
            "TodoWrite", {"todos": [{"content": "c" * (SUBJECT_LIMIT + 1), "status": "pending"}]}
        )
    )

    assert f"{SUBJECT_LIMIT + 1} characters" in reason


def test_should_pass_a_todo_write_with_short_items() -> None:
    all_todos = [
        {"content": each_subject, "status": "pending"} for each_subject in ALL_SHORT_SUBJECTS
    ]
    _assert_silent_pass(_run_hook("TodoWrite", {"todos": all_todos}))


def test_should_pass_silently_for_another_tool() -> None:
    _assert_silent_pass(_run_hook("Write", {"subject": LONG_STATUS_SUBJECT}))


def test_should_pass_silently_for_stdin_that_is_not_json() -> None:
    _assert_silent_pass(_run_hook_text("not json {"))


@pytest.mark.parametrize("tool_input", ["subject text", ["a"], None])
def test_should_pass_silently_when_tool_input_is_not_an_object(tool_input: object) -> None:
    _assert_silent_pass(_run_hook("TaskCreate", tool_input))


@pytest.mark.parametrize(
    "tool_input",
    [
        {"subject": 42},
        {"todos": "not a list"},
        {"todos": ["plain string", {"content": 7}, {"status": "pending"}]},
    ],
)
def test_should_pass_silently_for_malformed_fields(tool_input: object) -> None:
    _assert_silent_pass(
        _run_hook("TodoWrite" if "todos" in tool_input else "TaskCreate", tool_input)
    )


def test_long_subject_decision_should_deny_a_long_subject_and_pass_a_short_one() -> None:
    decision = task_subject_length_gate.long_subject_decision(
        {"tool_name": "TaskCreate", "tool_input": {"subject": LONG_STATUS_SUBJECT}}
    )

    assert decision is not None
    assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert (
        task_subject_length_gate.long_subject_decision(
            {"tool_name": "TaskCreate", "tool_input": {"subject": ALL_SHORT_SUBJECTS[1]}}
        )
        is None
    )


def test_should_be_registered_before_each_task_list_tool() -> None:
    registrations = json.loads(HOOKS_CONFIG.read_text(encoding="utf-8"))
    all_gated_tool_names: set[str] = set()
    for each_group in registrations["hooks"]["PreToolUse"]:
        all_commands = [each_hook.get("command", "") for each_hook in each_group["hooks"]]
        if any(
            "hooks/blocking/task_subject_length_gate.py" in each_command
            for each_command in all_commands
        ):
            all_gated_tool_names.update(each_group["matcher"].split("|"))

    assert {"TaskCreate", "TaskUpdate", "TodoWrite"} <= all_gated_tool_names
