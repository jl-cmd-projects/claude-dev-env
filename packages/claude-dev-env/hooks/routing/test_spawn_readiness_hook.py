import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import spawn_readiness_hook
from hooks_constants.spawn_readiness_hook_constants import (
    MISSING_INTERVIEW_REASON,
    MISSING_INVESTIGATION_REASON,
)

HOOK_SCRIPT = Path(__file__).resolve().parent / "spawn_readiness_hook.py"
THREAD_SPAWN_TOOL_NAME = "mcp__hearthbot__start_thread_session"
SETTLED_LINE = "Scope settled: the request names the file, the fix, and the test."


def _user(text: str) -> dict[str, object]:
    return {"type": "user", "message": {"role": "user", "content": text}}


def _tool_use(
    name: str, tool_input: dict[str, object], block_id: str = "toolu_x"
) -> dict[str, object]:
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": block_id, "name": name, "input": tool_input}],
        },
    }


def _tool_result(tool_use_id: str, is_error: bool = False) -> dict[str, object]:
    return {
        "type": "user",
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": "ok",
                    "is_error": is_error,
                }
            ],
        },
    }


def _queued(prompt: str) -> dict[str, object]:
    return {"type": "attachment", "attachment": {"type": "queued_command", "prompt": prompt}}


READ_STEP = _tool_use("Bash", {"command": "cat README.md"})
QUESTION_STEP = _tool_use(
    "mcp__hearthbot__post_message", {"text": "Which repo should this land in?"}
)
REPLY_STEP = _user("The public one.")
INTERVIEWED_TRANSCRIPT = [_user("Build the hook."), READ_STEP, QUESTION_STEP, REPLY_STEP]


def _spawn_input(tool_name: str, brief: str = "Do the task.") -> dict[str, object]:
    if tool_name == THREAD_SPAWN_TOOL_NAME:
        return {"title": "Task", "instructions": brief}
    return {"description": "Task", "prompt": brief}


def _write_transcript(tmp_path: Path, all_entries: list[dict[str, object]]) -> Path:
    transcript_path = tmp_path / "transcript.jsonl"
    transcript_path.write_text(
        "".join(json.dumps(each_entry) + "\n" for each_entry in all_entries), encoding="utf-8"
    )
    return transcript_path


def _run_hook(tmp_path: Path, hook_payload: dict[str, object]) -> str:
    completed = subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)],
        input=json.dumps(
            {"hook_event_name": "PreToolUse", "tool_use_id": "toolu_spawn", **hook_payload}
        ),
        capture_output=True,
        text=True,
        env={**os.environ, "HOME": str(tmp_path)},
        check=True,
    )
    return completed.stdout


def _spawn(
    tmp_path: Path,
    all_entries: list[dict[str, object]],
    tool_name: str = "Agent",
    brief: str = "Do the task.",
) -> str:
    return _run_hook(
        tmp_path,
        {
            "tool_name": tool_name,
            "tool_input": _spawn_input(tool_name, brief),
            "transcript_path": str(_write_transcript(tmp_path, all_entries)),
        },
    )


def _deny_reason(stdout: str) -> str:
    decision = json.loads(stdout)["hookSpecificOutput"]
    assert decision["hookEventName"] == "PreToolUse"
    assert decision["permissionDecision"] == "deny"
    return decision["permissionDecisionReason"]


def _decision_log(tmp_path: Path) -> list[dict[str, object]]:
    log_path = tmp_path / ".claude" / "logs" / "spawn-readiness.jsonl"
    return [
        json.loads(each_line) for each_line in log_path.read_text(encoding="utf-8").splitlines()
    ]


@pytest.mark.parametrize("tool_name", ["Agent", "Task", THREAD_SPAWN_TOOL_NAME])
def test_should_let_the_spawn_run_after_a_read_a_question_and_a_reply(
    tmp_path: Path, tool_name: str
) -> None:
    assert _spawn(tmp_path, INTERVIEWED_TRANSCRIPT, tool_name) == ""


def test_should_deny_a_spawn_with_no_read_since_the_request(tmp_path: Path) -> None:
    transcript = [_user("Build the hook."), QUESTION_STEP, REPLY_STEP]
    assert _deny_reason(_spawn(tmp_path, transcript)) == MISSING_INVESTIGATION_REASON


def test_should_deny_a_spawn_with_no_question_to_the_user(tmp_path: Path) -> None:
    transcript = [_user("Build the hook."), READ_STEP]
    assert _deny_reason(_spawn(tmp_path, transcript)) == MISSING_INTERVIEW_REASON


def test_should_deny_a_spawn_whose_question_has_no_reply_yet(tmp_path: Path) -> None:
    transcript = [_user("Build the hook."), READ_STEP, QUESTION_STEP]
    assert _deny_reason(_spawn(tmp_path, transcript)) == MISSING_INTERVIEW_REASON


def test_should_name_both_gaps_when_the_session_did_neither(tmp_path: Path) -> None:
    reason = _deny_reason(_spawn(tmp_path, [_user("Build the hook.")]))
    assert reason == f"{MISSING_INVESTIGATION_REASON} {MISSING_INTERVIEW_REASON}"


def test_should_count_a_posted_message_without_a_question_mark_as_no_question(
    tmp_path: Path,
) -> None:
    statement = _tool_use("mcp__hearthbot__post_message", {"text": "Starting on it."})
    transcript = [_user("Build the hook."), READ_STEP, statement, REPLY_STEP, READ_STEP]
    assert _deny_reason(_spawn(tmp_path, transcript)) == MISSING_INTERVIEW_REASON


def test_should_count_an_answered_ask_user_question_as_the_interview(tmp_path: Path) -> None:
    transcript = [
        _user("Build the hook."),
        _tool_use("Read", {"file_path": "README.md"}),
        _tool_use("AskUserQuestion", {"questions": []}, block_id="toolu_ask"),
        _tool_result("toolu_ask"),
    ]
    assert _spawn(tmp_path, transcript) == ""


def test_should_count_an_answered_decision_card_as_the_interview(tmp_path: Path) -> None:
    transcript = [
        _user("Build the hook."),
        _tool_use("mcp__hearthbot__fetch_thread", {"thread_id": "t"}),
        _tool_use("mcp__hearthbot__ask_decision", {"question": "Pick one"}),
        _queued('<wake reason="mention"><message from="human">Option one.</message></wake>'),
    ]
    assert _spawn(tmp_path, transcript, THREAD_SPAWN_TOOL_NAME) == ""


def test_should_skip_an_agent_relay_as_the_reply(tmp_path: Path) -> None:
    relay = _queued('<relay from="coordinator"><note>Keep going.</note></relay>')
    transcript = [_user("Build the hook."), READ_STEP, QUESTION_STEP, relay]
    assert _deny_reason(_spawn(tmp_path, transcript)) == MISSING_INTERVIEW_REASON


def test_should_require_a_new_interview_for_a_follow_up_request(tmp_path: Path) -> None:
    earlier_spawn = _tool_use("Agent", {"prompt": "Build the hook."})
    transcript = [*INTERVIEWED_TRANSCRIPT, earlier_spawn, _user("Now add a second hook."), READ_STEP]
    assert _deny_reason(_spawn(tmp_path, transcript)) == MISSING_INTERVIEW_REASON


def test_should_treat_two_messages_in_a_row_after_a_question_as_one_reply(
    tmp_path: Path,
) -> None:
    transcript = [*INTERVIEWED_TRANSCRIPT, _user("Also keep it short.")]
    assert _spawn(tmp_path, transcript) == ""


def test_should_pass_the_interview_on_a_scope_settled_line_and_log_it(tmp_path: Path) -> None:
    transcript = [_user("Fix the typo in README.md line 3."), READ_STEP]
    brief = f"Fix the typo.\n{SETTLED_LINE}"
    assert _spawn(tmp_path, transcript, THREAD_SPAWN_TOOL_NAME, brief) == ""
    [log_record] = _decision_log(tmp_path)
    assert log_record["outcome"] == "scope_settled"
    assert log_record["tool_name"] == THREAD_SPAWN_TOOL_NAME
    assert log_record["scope_settled_line"] == SETTLED_LINE


def test_should_still_require_the_read_with_a_scope_settled_line(tmp_path: Path) -> None:
    brief = f"Fix the typo.\n{SETTLED_LINE}"
    reason = _deny_reason(_spawn(tmp_path, [_user("Fix the typo.")], brief=brief))
    assert reason == MISSING_INVESTIGATION_REASON


def test_should_deny_a_scope_settled_line_with_no_reason(tmp_path: Path) -> None:
    transcript = [_user("Fix the typo."), READ_STEP]
    reason = _deny_reason(_spawn(tmp_path, transcript, brief="Fix it.\nScope settled:"))
    assert reason == MISSING_INTERVIEW_REASON


def test_should_let_a_read_only_subagent_run_without_checks(tmp_path: Path) -> None:
    stdout = _run_hook(
        tmp_path,
        {
            "tool_name": "Agent",
            "tool_input": {"subagent_type": "Explore", "prompt": "Find the hooks."},
            "transcript_path": str(_write_transcript(tmp_path, [_user("Build the hook.")])),
        },
    )
    assert stdout == ""


def test_should_count_a_read_only_subagent_as_the_investigation(tmp_path: Path) -> None:
    explore = _tool_use("Agent", {"subagent_type": "Explore", "prompt": "Find it."})
    transcript = [_user("Build the hook."), explore, QUESTION_STEP, REPLY_STEP]
    assert _spawn(tmp_path, transcript) == ""


def test_should_let_a_spawn_from_inside_a_subagent_run(tmp_path: Path) -> None:
    stdout = _run_hook(
        tmp_path,
        {
            "tool_name": "Agent",
            "agent_id": "agent_1",
            "tool_input": _spawn_input("Agent"),
            "transcript_path": str(_write_transcript(tmp_path, [_user("Build the hook.")])),
        },
    )
    assert stdout == ""


def test_should_let_the_spawn_run_and_log_when_the_transcript_is_unreadable(
    tmp_path: Path,
) -> None:
    stdout = _run_hook(
        tmp_path,
        {
            "tool_name": "Agent",
            "tool_input": _spawn_input("Agent"),
            "transcript_path": str(tmp_path / "absent.jsonl"),
        },
    )
    assert stdout == ""
    [log_record] = _decision_log(tmp_path)
    assert log_record["outcome"] == "transcript_unreadable"


def test_should_return_the_scope_settled_line_from_the_brief() -> None:
    tool_input = {"instructions": f"Do X.\n  {SETTLED_LINE}"}
    assert (
        spawn_readiness_hook.scope_settled_line(THREAD_SPAWN_TOOL_NAME, tool_input) == SETTLED_LINE
    )


def test_should_ignore_a_tool_it_does_not_check() -> None:
    assert spawn_readiness_hook.decide_hook_output({"tool_name": "Read", "tool_input": {}}) is None
