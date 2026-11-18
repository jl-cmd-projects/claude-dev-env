from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

import closing_reply_judge
import open_tasks_stop_gate
from open_tasks_transcript import TaskItem, replayed_transcript

if TYPE_CHECKING:
    from conftest import JudgeStub

GATE_PATH = Path(open_tasks_stop_gate.__file__)
SESSION_ID = "s-123"
WORK_PROMPT = "Export the APKs and submit them"


UNPINNED_WHICH = shutil.which


def _which_without_claude(command_name: str, *all_arguments: object, **all_options: object) -> str | None:
    if command_name == "claude":
        return None
    return UNPINNED_WHICH(command_name, *all_arguments, **all_options)


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    marker_directory = tmp_path / "markers"
    marker_directory.mkdir()
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(marker_directory))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_TASK_LIST_ID", raising=False)
    monkeypatch.delenv("CLAUDE_TURN_REVIEW_CHILD", raising=False)
    monkeypatch.setattr(shutil, "which", _which_without_claude)


def user_prompt_record(prompt_text: str) -> dict[str, object]:
    return {"type": "user", "message": {"role": "user", "content": prompt_text}}


def tool_call_record(tool_name: str, all_input_fields: dict[str, object] | None = None) -> dict[str, object]:
    tool_use = {"type": "tool_use", "id": f"id-{tool_name}", "name": tool_name, "input": all_input_fields or {}}
    return {"type": "assistant", "message": {"role": "assistant", "content": [tool_use]}}


def stop_feedback_record() -> dict[str, object]:
    return {"type": "user", "isMeta": True, "message": {"role": "user", "content": "Stop hook feedback: update the list"}}


def write_records(transcript_path: Path, all_records: list[dict[str, object]]) -> Path:
    transcript_path.write_text("\n".join(json.dumps(each_record) for each_record in all_records), encoding="utf-8")
    return transcript_path


def write_task_store(home_directory: Path, all_tasks: list[dict[str, str]]) -> None:
    task_directory = home_directory / ".claude" / "tasks" / SESSION_ID
    task_directory.mkdir(parents=True)
    for each_task in all_tasks:
        (task_directory / f"{each_task['id']}.json").write_text(json.dumps(each_task), encoding="utf-8")


def run_gate(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    transcript_path: Path | None,
    is_stop_hook_active: bool = False,
    reply_text: str = "Done.",
    working_directory: Path | None = None,
    all_extra_fields: dict[str, object] | None = None,
) -> dict[str, str]:
    hook_input: dict[str, object] = {
        "hook_event_name": "Stop",
        "session_id": SESSION_ID,
        "stop_hook_active": is_stop_hook_active,
        "last_assistant_message": reply_text,
        **(all_extra_fields or {}),
    }
    if working_directory is not None:
        hook_input["cwd"] = str(working_directory)
    if transcript_path is not None:
        hook_input["transcript_path"] = str(transcript_path)
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(json.dumps(hook_input).encode("utf-8"))))
    exit_code = open_tasks_stop_gate.main()
    captured = capsys.readouterr()
    block_output = json.loads(captured.out) if captured.out else {}
    assert exit_code == (2 if block_output else 0)
    assert captured.err == block_output.get("reason", "")
    return block_output


def test_should_block_a_work_turn_that_left_the_task_list_unchanged(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    transcript_path = write_records(tmp_path / "s.jsonl", [user_prompt_record(WORK_PROMPT), tool_call_record("Bash")])
    block_output = run_gate(monkeypatch, capsys, transcript_path)
    assert block_output["decision"] == "block"
    assert "task list" in block_output["reason"]
    assert "followup_message" not in block_output


def prompt_snapshot_record(all_tool_names: list[str]) -> dict[str, object]:
    all_tools = [{"name": each_name, "description": f"{each_name} tool"} for each_name in all_tool_names]
    return {"type": "attachment", "attachment": {"type": "prompt_snapshot", "systemPrompt": "TaskCreate", "tools": all_tools}}


def deferred_tools_delta_record(all_added_names: list[str]) -> dict[str, object]:
    return {
        "type": "attachment",
        "attachment": {"type": "deferred_tools_delta", "addedNames": all_added_names, "removedNames": [], "readdedNames": []},
    }


def deferred_tools_record(all_loaded_names: list[str]) -> dict[str, object]:
    all_entries = [{"name": each_name, "description": f"{each_name} tool"} for each_name in all_loaded_names]
    return {"type": "attachment", "attachment": {"type": "deferred_tools_record", "entries": all_entries}}


NO_TRACKER_TOOL_LISTING = [prompt_snapshot_record(["Bash", "Read", "Edit"]), deferred_tools_delta_record(["WebSearch", "TaskStop"])]


def test_should_allow_a_work_turn_in_a_session_that_lists_no_task_tool(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    transcript_path = write_records(
        tmp_path / "s.jsonl", [*NO_TRACKER_TOOL_LISTING, user_prompt_record(WORK_PROMPT), tool_call_record("Bash")]
    )
    assert run_gate(monkeypatch, capsys, transcript_path) == {}


@pytest.mark.parametrize(
    "all_listing_records",
    [
        [prompt_snapshot_record(["Bash"]), deferred_tools_delta_record(["WebSearch", "TaskCreate", "TaskUpdate"])],
        [prompt_snapshot_record(["Bash", "TodoWrite"]), deferred_tools_delta_record(["WebSearch"])],
        [prompt_snapshot_record(["Bash", "mcp__ccd_turn__update_plan"]), deferred_tools_delta_record(["WebSearch"])],
        [*NO_TRACKER_TOOL_LISTING, deferred_tools_record(["TaskCreate", "TaskUpdate"])],
        [*NO_TRACKER_TOOL_LISTING, user_prompt_record("Port the hook"), tool_call_record("TaskCreate", {"subject": "Port"})],
        [deferred_tools_delta_record(["WebSearch"])],
        [prompt_snapshot_record(["Bash"])],
    ],
    ids=[
        "deferred-task-tools",
        "inline-todowrite",
        "inline-desktop-plan",
        "task-tools-loaded-by-tool-search",
        "task-tool-called-in-an-earlier-turn",
        "no-inline-tool-listing",
        "no-deferred-tool-listing",
    ],
)
def test_should_block_an_untracked_work_turn_unless_the_session_lists_no_task_tool(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    all_listing_records: list[dict[str, object]],
) -> None:
    transcript_path = write_records(
        tmp_path / "s.jsonl", [*all_listing_records, user_prompt_record(WORK_PROMPT), tool_call_record("Bash")]
    )
    block_output = run_gate(monkeypatch, capsys, transcript_path)
    assert block_output["decision"] == "block"
    assert "left the task list unchanged" in block_output["reason"]


@pytest.mark.parametrize(
    "tracker_record",
    [
        tool_call_record("TaskCreate", {"subject": "Export the APKs"}),
        tool_call_record("TaskUpdate", {"taskId": "1", "status": "in_progress"}),
        tool_call_record("TodoWrite", {"todos": [{"content": "Export", "status": "in_progress"}]}),
        tool_call_record("mcp__ccd_turn__update_plan", {"items": [{"content": "Export", "status": "in_progress"}]}),
    ],
)
def test_should_allow_a_work_turn_that_made_a_tracker_call(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    tracker_record: dict[str, object],
) -> None:
    transcript_path = write_records(
        tmp_path / "s.jsonl", [user_prompt_record(WORK_PROMPT), tracker_record, tool_call_record("Bash")]
    )
    assert run_gate(monkeypatch, capsys, transcript_path) == {}


@pytest.mark.parametrize(
    "non_work_tool_name",
    ["AskUserQuestion", "ToolSearch", "TaskList", "TaskGet", "mcp__claude-code-remote__set_session_title"],
)
def test_should_allow_a_work_prompt_turn_that_only_asked_looked_up_or_set_the_title(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    non_work_tool_name: str,
) -> None:
    transcript_path = write_records(
        tmp_path / "s.jsonl", [user_prompt_record(WORK_PROMPT), tool_call_record(non_work_tool_name)]
    )
    assert run_gate(monkeypatch, capsys, transcript_path) == {}


def test_should_block_when_the_only_tracker_call_came_in_an_earlier_turn(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    transcript_path = write_records(
        tmp_path / "s.jsonl",
        [
            user_prompt_record("Port the hook"),
            tool_call_record("TaskCreate", {"subject": "Port the hook"}),
            user_prompt_record(WORK_PROMPT),
            tool_call_record("Bash"),
        ],
    )
    assert run_gate(monkeypatch, capsys, transcript_path)["decision"] == "block"


def test_should_count_a_tracker_call_made_after_stop_hook_feedback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    transcript_path = write_records(
        tmp_path / "s.jsonl",
        [
            user_prompt_record(WORK_PROMPT),
            tool_call_record("Bash"),
            stop_feedback_record(),
            tool_call_record("TaskCreate", {"subject": "Export the APKs"}),
        ],
    )
    assert run_gate(monkeypatch, capsys, transcript_path) == {}


@pytest.mark.parametrize(
    "prompt_text",
    ["did the export fail?", "thanks!", "<task-notification>\n<task-id>b1</task-id>\n</task-notification>"],
)
def test_should_allow_a_turn_whose_prompt_asks_for_no_work(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path, prompt_text: str
) -> None:
    transcript_path = write_records(tmp_path / "s.jsonl", [user_prompt_record(prompt_text), tool_call_record("Bash")])
    assert run_gate(monkeypatch, capsys, transcript_path) == {}


def test_should_allow_a_work_turn_that_ran_no_tool(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    text_record = {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "On it."}]}}
    transcript_path = write_records(tmp_path / "s.jsonl", [user_prompt_record(WORK_PROMPT), text_record])
    assert run_gate(monkeypatch, capsys, transcript_path) == {}


def test_should_allow_a_stop_the_gate_already_held(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    transcript_path = write_records(tmp_path / "s.jsonl", [user_prompt_record(WORK_PROMPT), tool_call_record("Bash")])
    assert run_gate(monkeypatch, capsys, transcript_path, is_stop_hook_active=True) == {}


def test_should_ignore_open_items_when_the_turn_updated_the_list(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    write_task_store(tmp_path, [{"id": "1", "subject": "Rotate the deploy key", "status": "pending"}])
    transcript_path = write_records(
        tmp_path / "s.jsonl",
        [user_prompt_record(WORK_PROMPT), tool_call_record("TaskUpdate", {"taskId": "1", "status": "in_progress"})],
    )
    assert run_gate(monkeypatch, capsys, transcript_path) == {}


def test_should_allow_malformed_stdin(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(b"not json")))
    assert (open_tasks_stop_gate.main(), capsys.readouterr().out) == (0, "")


def test_should_allow_a_session_with_no_transcript(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_gate(monkeypatch, capsys, None) == {}


def test_should_block_through_a_subprocess_with_the_documented_contract(tmp_path: Path) -> None:
    transcript_path = write_records(tmp_path / "s.jsonl", [user_prompt_record(WORK_PROMPT), tool_call_record("Edit")])
    hook_input = {"hook_event_name": "Stop", "session_id": SESSION_ID, "transcript_path": str(transcript_path)}
    completed_process = subprocess.run(
        [sys.executable, str(GATE_PATH)],
        input=json.dumps(hook_input),
        capture_output=True,
        text=True,
        env={"HOME": str(tmp_path), "USERPROFILE": str(tmp_path), "PATH": ""},
        check=False,
    )
    block_output = json.loads(completed_process.stdout)
    assert completed_process.returncode == 2
    assert block_output["decision"] == "block"
    assert completed_process.stderr == block_output["reason"]


def codex_record(payload: dict[str, object]) -> dict[str, object]:
    return {"type": "response_item", "payload": payload}


def codex_prompt(prompt_text: str) -> dict[str, object]:
    return codex_record({"type": "message", "role": "user", "content": [{"type": "input_text", "text": prompt_text}]})


def test_should_block_a_codex_work_turn_with_no_update_plan_call(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    shell_call = codex_record({"type": "function_call", "name": "shell", "arguments": "{}"})
    transcript_path = write_records(tmp_path / "rollout.jsonl", [codex_prompt(WORK_PROMPT), shell_call])
    assert run_gate(monkeypatch, capsys, transcript_path)["decision"] == "block"


def test_should_allow_a_codex_work_turn_with_an_update_plan_call(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    plan_arguments = json.dumps({"plan": [{"step": "Export the APKs", "status": "in_progress"}]})
    plan_call = codex_record({"type": "function_call", "name": "update_plan", "arguments": plan_arguments})
    shell_call = codex_record({"type": "function_call", "name": "shell", "arguments": "{}"})
    transcript_path = write_records(tmp_path / "rollout.jsonl", [codex_prompt(WORK_PROMPT), plan_call, shell_call])
    assert run_gate(monkeypatch, capsys, transcript_path) == {}


def cursor_record(content_blocks: list[dict[str, object]]) -> dict[str, object]:
    return {"role": "assistant", "message": {"content": content_blocks}}


def run_cursor_gate(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    transcript_path: Path,
    stop_status: str = "completed",
    loop_count: int = 0,
) -> dict[str, str]:
    hook_input = {
        "hook_event_name": "stop",
        "conversation_id": "c-1",
        "status": stop_status,
        "loop_count": loop_count,
        "transcript_path": str(transcript_path),
    }
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(json.dumps(hook_input).encode("utf-8"))))
    assert open_tasks_stop_gate.main() == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    return json.loads(captured.out) if captured.out else {}


def write_cursor_work_turn(tmp_path: Path, all_tool_blocks: list[dict[str, object]]) -> Path:
    cursor_prompt = {"role": "user", "message": {"content": [{"type": "text", "text": WORK_PROMPT}]}}
    return write_records(tmp_path / "cursor.jsonl", [cursor_prompt, cursor_record(all_tool_blocks)])


def test_should_send_a_cursor_followup_for_an_untracked_work_turn(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    transcript_path = write_cursor_work_turn(tmp_path, [{"type": "tool_use", "name": "Shell", "input": {}}])
    block_output = run_cursor_gate(monkeypatch, capsys, transcript_path)
    assert block_output["followup_message"] == block_output["reason"]


def test_should_count_a_todowrite_the_cursor_cli_wraps_in_call_dynamic_tool(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    dynamic_call = {
        "type": "tool_use",
        "name": "CallDynamicTool",
        "input": {"toolName": "TodoWrite", "arguments": {"todos": [{"id": "1", "content": "Export", "status": "in_progress"}]}},
    }
    transcript_path = write_cursor_work_turn(tmp_path, [dynamic_call, {"type": "tool_use", "name": "Shell", "input": {}}])
    assert run_cursor_gate(monkeypatch, capsys, transcript_path) == {}


@pytest.mark.parametrize(("stop_status", "loop_count"), [("aborted", 0), ("error", 0), ("completed", 1)])
def test_should_allow_a_cursor_stop_that_was_aborted_or_already_followed_up(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    stop_status: str,
    loop_count: int,
) -> None:
    transcript_path = write_cursor_work_turn(tmp_path, [{"type": "tool_use", "name": "Shell", "input": {}}])
    assert run_cursor_gate(monkeypatch, capsys, transcript_path, stop_status, loop_count) == {}


def test_should_read_the_task_store_items_for_the_session(tmp_path: Path) -> None:
    write_task_store(tmp_path, [{"id": "1", "subject": "Rotate the deploy key", "status": "pending"}])
    assert open_tasks_stop_gate.task_store_items(SESSION_ID) == [TaskItem("1", "Rotate the deploy key", "pending")]
    assert open_tasks_stop_gate.task_store_items("s-none") is None


def test_should_let_the_task_store_win_over_a_transcript_item_of_the_same_subject() -> None:
    store_item = TaskItem("1", "Export the APKs", "completed")
    transcript_item = TaskItem("plan-1", "export the  APKs", "pending")
    other_item = TaskItem("plan-2", "Submit", "pending")
    assert open_tasks_stop_gate.deduplicated_by_subject([[store_item], [transcript_item, other_item]]) == [
        store_item,
        other_item,
    ]


def test_should_merge_the_task_store_with_the_transcript_items(tmp_path: Path) -> None:
    write_task_store(tmp_path, [{"id": "1", "subject": "Export the APKs", "status": "completed"}])
    transcript_path = write_records(
        tmp_path / "s.jsonl",
        [tool_call_record("TodoWrite", {"todos": [{"id": "9", "content": "Submit", "status": "pending"}]})],
    )
    assert open_tasks_stop_gate.session_task_items(SESSION_ID, replayed_transcript(str(transcript_path))) == [
        TaskItem("1", "Export the APKs", "completed"),
        TaskItem("9", "Submit", "pending"),
    ]


def test_should_call_a_turn_untracked_only_for_work_without_a_tracker_call(tmp_path: Path) -> None:
    untracked_path = write_records(tmp_path / "a.jsonl", [user_prompt_record(WORK_PROMPT), tool_call_record("Bash")])
    question_path = write_records(tmp_path / "b.jsonl", [user_prompt_record("did it fail?"), tool_call_record("Bash")])
    assert open_tasks_stop_gate.is_untracked_work_turn(replayed_transcript(str(untracked_path))) is True
    assert open_tasks_stop_gate.is_untracked_work_turn(replayed_transcript(str(question_path))) is False


@pytest.mark.parametrize(
    ("hook_input", "is_expected_held"),
    [
        ({"stop_hook_active": True}, True),
        ({"stop_hook_active": False}, False),
        ({"conversation_id": "c-1", "status": "completed", "loop_count": 0}, False),
        ({"conversation_id": "c-1", "status": "completed", "loop_count": 1}, True),
        ({"conversation_id": "c-1", "status": "aborted", "loop_count": 0}, True),
    ],
)
def test_should_tell_a_held_stop_from_a_first_stop(hook_input: dict[str, object], is_expected_held: bool) -> None:
    assert open_tasks_stop_gate.is_held_stop(hook_input) is is_expected_held


STEP_REPLY = "Three items need you. The list is below."
READ_CALL = tool_call_record("mcp__github__pull_request_read", {"pullNumber": 12})
QUESTION_CALL = tool_call_record("AskUserQuestion", {"questions": [{"question": "Merge pull request 12 now?"}]})
TRACKER_CALL = tool_call_record("TaskUpdate", {"taskId": "2", "status": "in_progress"})
OPEN_TASK = {"id": "2", "subject": "Merge the docs pull request", "status": "pending"}
COMPLETED_TASK = {"id": "1", "subject": "Rotate the deploy key", "status": "completed"}


def test_should_block_a_turn_that_leaves_completed_items_beside_open_ones(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    write_task_store(tmp_path, [COMPLETED_TASK, OPEN_TASK])
    transcript_path = write_records(tmp_path / "s.jsonl", [user_prompt_record("did the export fail?")])
    block_output = run_gate(monkeypatch, capsys, transcript_path)
    assert block_output["decision"] == "block"
    assert "1 of 2 items are completed" in block_output["reason"]
    assert block_output["reason"].endswith("Leave the reply as it stands.")


@pytest.mark.parametrize("all_tasks", [[COMPLETED_TASK], [OPEN_TASK]])
def test_should_allow_a_task_list_that_is_all_completed_or_all_open(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    all_tasks: list[dict[str, str]],
) -> None:
    write_task_store(tmp_path, all_tasks)
    transcript_path = write_records(tmp_path / "s.jsonl", [user_prompt_record("did the export fail?")])
    assert run_gate(monkeypatch, capsys, transcript_path) == {}


def test_should_leave_a_task_list_shared_with_other_sessions_alone(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    write_task_store(tmp_path, [COMPLETED_TASK, OPEN_TASK])
    monkeypatch.setenv("CLAUDE_CODE_TASK_LIST_ID", SESSION_ID)
    transcript_path = write_records(tmp_path / "s.jsonl", [user_prompt_record("did the export fail?")])
    assert run_gate(monkeypatch, capsys, transcript_path) == {}


def test_should_read_completed_items_from_the_transcript_when_the_session_has_no_task_store(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_todos = [{"content": "Export", "status": "completed"}, {"content": "Submit", "status": "pending"}]
    transcript_path = write_records(
        tmp_path / "s.jsonl", [user_prompt_record(WORK_PROMPT), tool_call_record("TodoWrite", {"todos": all_todos})]
    )
    assert "1 of 2 items are completed" in run_gate(monkeypatch, capsys, transcript_path)["reason"]


def test_should_let_the_task_store_decide_what_the_user_sees(tmp_path: Path) -> None:
    all_todos = [{"content": "Export", "status": "completed"}, {"content": "Submit", "status": "pending"}]
    transcript_path = write_records(tmp_path / "s.jsonl", [tool_call_record("TodoWrite", {"todos": all_todos})])
    replay = replayed_transcript(str(transcript_path))
    assert [each_item.subject for each_item in open_tasks_stop_gate.shown_task_items(SESSION_ID, replay)] == [
        "Export",
        "Submit",
    ]
    write_task_store(tmp_path, [OPEN_TASK])
    assert open_tasks_stop_gate.shown_task_items(SESSION_ID, replay) == [
        TaskItem("2", "Merge the docs pull request", "pending")
    ]


def test_should_count_completed_items_only_beside_open_ones() -> None:
    completed_item = TaskItem("1", "Export", "completed")
    open_item = TaskItem("2", "Submit", "in_progress")
    deleted_item = TaskItem("3", "Sign", "deleted")
    mixed_reason = open_tasks_stop_gate.stale_list_reason([completed_item, completed_item, open_item, deleted_item])
    assert "2 of 3 items are completed" in (mixed_reason or "")
    assert open_tasks_stop_gate.stale_list_reason([completed_item, deleted_item]) is None
    assert open_tasks_stop_gate.stale_list_reason([open_item]) is None


@pytest.mark.parametrize(
    ("all_turn_calls", "expected_text", "absent_text"),
    [
        ([TRACKER_CALL], "ran no read call", "Leave the reply as it stands."),
        ([TRACKER_CALL, READ_CALL], "sent no question through the native question tool", "ran no read call"),
        ([TRACKER_CALL, QUESTION_CALL], "ran no read call", "sent no question"),
    ],
)
def test_should_block_a_reply_that_hands_the_user_a_step_without_a_read_or_a_question_call(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    all_turn_calls: list[dict[str, object]],
    expected_text: str,
    absent_text: str,
) -> None:
    transcript_path = write_records(tmp_path / "s.jsonl", [user_prompt_record("what needs me?"), *all_turn_calls])
    block_output = run_gate(monkeypatch, capsys, transcript_path, reply_text=STEP_REPLY)
    assert block_output["decision"] == "block"
    assert '"need you"' in block_output["reason"]
    assert expected_text in block_output["reason"]
    assert absent_text not in block_output["reason"]
    assert "read the live state of each item you show as open" in block_output["reason"]
    assert block_output["reason"].endswith("end the turn and leave the reply as it stands.")


def test_should_allow_a_step_reply_after_a_read_call_and_a_question_call(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    transcript_path = write_records(
        tmp_path / "s.jsonl", [user_prompt_record("what needs me?"), TRACKER_CALL, READ_CALL, QUESTION_CALL]
    )
    assert run_gate(monkeypatch, capsys, transcript_path, reply_text=STEP_REPLY) == {}


def test_should_not_count_a_read_or_a_question_call_from_an_earlier_turn(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    transcript_path = write_records(
        tmp_path / "s.jsonl", [user_prompt_record("status?"), READ_CALL, QUESTION_CALL, user_prompt_record("what needs me?")]
    )
    block_reason = run_gate(monkeypatch, capsys, transcript_path, reply_text=STEP_REPLY)["reason"]
    assert "ran no read call" in block_reason
    assert "sent no question" in block_reason


def test_should_block_a_sent_status_file_that_says_something_waits_on_the_user(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    status_path = tmp_path / "status.md"
    status_path.write_text("## What needs you\n\nSay when the demo sessions may be archived.", encoding="utf-8")
    send_call = tool_call_record("SendUserFile", {"files": [str(status_path)]})
    transcript_path = write_records(tmp_path / "s.jsonl", [user_prompt_record("what needs me?"), TRACKER_CALL, send_call])
    block_reason = run_gate(monkeypatch, capsys, transcript_path, reply_text="The status list is attached.")["reason"]
    assert '"needs you"' in block_reason
    assert open_tasks_stop_gate.turn_waiting_phrase(
        {"last_assistant_message": "The status list is attached."}, replayed_transcript(str(transcript_path))
    ) == "needs you"


def test_should_read_a_relative_sent_path_from_the_working_directory_of_the_stop(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    sent_directory = tmp_path / "reports"
    sent_directory.mkdir()
    (sent_directory / "status.md").write_text("Two items need you.", encoding="utf-8")
    send_call = tool_call_record("SendUserFile", {"files": ["status.md"]})
    transcript_path = write_records(tmp_path / "s.jsonl", [user_prompt_record("what needs me?"), TRACKER_CALL, send_call])
    block_output = run_gate(
        monkeypatch, capsys, transcript_path, reply_text="The status list is attached.", working_directory=sent_directory
    )
    assert '"need you"' in block_output["reason"]
    assert run_gate(monkeypatch, capsys, transcript_path, reply_text="The status list is attached.") == {}


def test_should_read_a_path_the_turn_sent_twice_once(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    status_path = tmp_path / "status.md"
    status_path.write_text("Both builds passed.", encoding="utf-8")
    send_call = tool_call_record("SendUserFile", {"files": [str(status_path), str(status_path)]})
    transcript_path = write_records(tmp_path / "s.jsonl", [user_prompt_record("status?"), send_call, send_call])
    all_read_paths: list[str] = []

    def record_read(file_path_text: str, working_directory: object) -> None:
        all_read_paths.append(file_path_text)

    monkeypatch.setattr(open_tasks_stop_gate, "file_waiting_phrase", record_read)
    assert open_tasks_stop_gate.turn_waiting_phrase(
        {"last_assistant_message": "The status list is attached."}, replayed_transcript(str(transcript_path))
    ) is None
    assert all_read_paths == [str(status_path)]


def test_should_read_a_task_file_that_holds_a_byte_outside_utf8(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    write_task_store(tmp_path, [OPEN_TASK])
    task_directory = tmp_path / ".claude" / "tasks" / SESSION_ID
    (task_directory / "1.json").write_bytes(b'{"id": "1", "subject": "caf\xe9", "status": "completed"}')
    transcript_path = write_records(tmp_path / "s.jsonl", [user_prompt_record("status?")])
    assert "1 of 2 items are completed" in run_gate(monkeypatch, capsys, transcript_path)["reason"]


def test_should_give_no_step_reason_when_the_transcript_cannot_be_read(tmp_path: Path) -> None:
    all_hook_input_fields = {"last_assistant_message": STEP_REPLY, "transcript_path": str(tmp_path / "missing.jsonl")}
    assert open_tasks_stop_gate.user_step_reasons(all_hook_input_fields, replayed_transcript(None)) == []
    assert open_tasks_stop_gate.turn_block_reason(all_hook_input_fields, replayed_transcript(None)) is None


def test_should_carry_every_finding_in_one_reason(tmp_path: Path) -> None:
    write_task_store(tmp_path, [COMPLETED_TASK, OPEN_TASK])
    transcript_path = write_records(tmp_path / "s.jsonl", [user_prompt_record(WORK_PROMPT), tool_call_record("Write")])
    all_hook_input_fields = {
        "session_id": SESSION_ID,
        "last_assistant_message": STEP_REPLY,
        "transcript_path": str(transcript_path),
    }
    replay = replayed_transcript(str(transcript_path))
    assert len(open_tasks_stop_gate.tracker_reasons(all_hook_input_fields, replay)) == 2
    assert len(open_tasks_stop_gate.user_step_reasons(all_hook_input_fields, replay)) == 3
    block_reason = open_tasks_stop_gate.turn_block_reason(all_hook_input_fields, replay) or ""
    assert block_reason.index("left the task list unchanged") < block_reason.index("1 of 2 items are completed")
    assert block_reason.index("1 of 2 items are completed") < block_reason.index("ran no read call")
    assert block_reason.index("ran no read call") < block_reason.index("sent no question")


def test_should_block_a_work_turn_whose_transcript_holds_an_undecodable_byte(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    transcript_path = write_records(tmp_path / "s.jsonl", [user_prompt_record(WORK_PROMPT), tool_call_record("Bash")])
    with transcript_path.open("ab") as transcript_file:
        transcript_file.write(b"\n\xff\n")
    assert run_gate(monkeypatch, capsys, transcript_path)["decision"] == "block"


BED_PROMPT = "heading out now. handle whatever the nightly job returns"
PROMISE_REPLY = (
    "Both fix runs are armed, and a wake is set for the end of CI."
    " The benchmark table will be posted when you get back."
)
DEFERRED_PROMPT = "You did a lot of work. I want to know what you put off."
DEFERRED_REPLY = (
    "What I deferred, checked against the build log:\n\n"
    "1. The retry budget for the sync job.\n"
    "2. The second fixture for the Windows path.\n"
    "3. The docs page for the new flag.\n"
    "4. The cleanup of the stale branch.\n"
    "5. The follow-up issue for the timeout."
)
THREE_BULLETS = "- The retry budget.\n- The docs page.\n- The stale branch."
WAKE_CALL = tool_call_record("mcp__scheduler__send_later", {"delay_minutes": 30})
PROMISE_REASON_START = "The closing reply promises the user a later report"
LIST_REASON_START = "The closing reply lists"
REWORKED_REPLY_INSTRUCTION = "Then send the reworked reply and end the turn."
SHORT_REPLY_INSTRUCTION = "Then send a short reply that names what you did and end the turn."
PROMISE_KEEP_CONDITION = (
    "Leave the promise as it is only when the reply already says that in one sentence, or when the user's"
    " typed words in this turn asked for a report later."
)
LIST_KEEP_START = "Leave the list as it is only when every listed item is finished work or plain status"
ASKED_ANSWER_SENTENCE = (
    'A question such as "what did you defer?" asks for an answer, and the open decisions in that answer'
    " still go out as question cards."
)
END_THE_TURN = "end the turn"


def closing_turn(prompt_text: str, *all_turn_calls: dict[str, object]) -> list[dict[str, object]]:
    return [user_prompt_record(prompt_text), TRACKER_CALL, *all_turn_calls]


@pytest.mark.parametrize(
    ("all_records", "reply_text", "reason_start"),
    [
        (closing_turn(BED_PROMPT, WAKE_CALL), PROMISE_REPLY, PROMISE_REASON_START),
        (closing_turn(WORK_PROMPT, READ_CALL), "I'll report back once CI ends.", PROMISE_REASON_START),
        (
            closing_turn(DEFERRED_PROMPT, tool_call_record("Bash"), tool_call_record("Read")),
            DEFERRED_REPLY,
            LIST_REASON_START,
        ),
        (closing_turn(WORK_PROMPT, READ_CALL), f"## Next steps\n\n{THREE_BULLETS}", LIST_REASON_START),
        (
            closing_turn(WORK_PROMPT, READ_CALL),
            "Open items:\n\n| Item | State |\n|---|---|\n| Retry | open |\n| Docs | open |\n| Branch | open |",
            LIST_REASON_START,
        ),
        (
            [user_prompt_record("<task-notification>summary: the run ended</task-notification>"), READ_CALL],
            PROMISE_REPLY,
            PROMISE_REASON_START,
        ),
        (
            closing_turn(
                "> The benchmark table will be posted when you get back.\n\n"
                "don't need this; just see the fixes through",
                READ_CALL,
            ),
            PROMISE_REPLY,
            PROMISE_REASON_START,
        ),
        (closing_turn("no report needed, just finish", READ_CALL), PROMISE_REPLY, PROMISE_REASON_START),
        (closing_turn("no list please, ask me instead", READ_CALL), DEFERRED_REPLY, LIST_REASON_START),
    ],
)
def test_should_hold_a_closing_reply_that_promises_a_report_or_lists_open_items(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    all_records: list[dict[str, object]],
    reply_text: str,
    reason_start: str,
) -> None:
    transcript_path = write_records(tmp_path / "s.jsonl", all_records)
    block_output = run_gate(monkeypatch, capsys, transcript_path, reply_text=reply_text)
    assert block_output["decision"] == "block"
    assert block_output["reason"].startswith(reason_start)
    assert block_output["reason"].lower().count(END_THE_TURN) == 1
    assert block_output["reason"].endswith((PROMISE_KEEP_CONDITION, ASKED_ANSWER_SENTENCE))


def test_should_quote_the_lead_and_the_item_count_in_the_list_reason(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    transcript_path = write_records(tmp_path / "s.jsonl", closing_turn(DEFERRED_PROMPT, READ_CALL))
    block_reason = run_gate(monkeypatch, capsys, transcript_path, reply_text=DEFERRED_REPLY)["reason"]
    assert 'lists 5 items under "What I deferred, checked' in block_reason
    assert "AskUserQuestion" in block_reason
    assert PROMISE_REASON_START not in block_reason


def test_should_quote_the_promise_in_the_report_reason(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    transcript_path = write_records(tmp_path / "s.jsonl", closing_turn(BED_PROMPT, WAKE_CALL))
    block_reason = run_gate(monkeypatch, capsys, transcript_path, reply_text=PROMISE_REPLY)["reason"]
    assert '("when you get back")' in block_reason
    assert LIST_REASON_START not in block_reason


def test_should_hold_a_codex_closing_reply_that_lists_open_items(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    plan_arguments = json.dumps({"plan": [{"step": "Report the deferred work", "status": "completed"}]})
    plan_call = codex_record({"type": "function_call", "name": "update_plan", "arguments": plan_arguments})
    shell_call = codex_record({"type": "function_call", "name": "shell", "arguments": "{}"})
    transcript_path = write_records(tmp_path / "rollout.jsonl", [codex_prompt(DEFERRED_PROMPT), plan_call, shell_call])
    block_output = run_gate(monkeypatch, capsys, transcript_path, reply_text=DEFERRED_REPLY)
    assert block_output["reason"].startswith(LIST_REASON_START)


@pytest.mark.parametrize(
    ("all_records", "reply_text"),
    [
        (closing_turn(DEFERRED_PROMPT, READ_CALL, QUESTION_CALL), DEFERRED_REPLY),
        (
            [
                codex_prompt(DEFERRED_PROMPT),
                codex_record({"type": "function_call", "name": "update_plan", "arguments": "{}"}),
                codex_record({"type": "function_call", "name": "request_user_input", "arguments": "{}"}),
            ],
            DEFERRED_REPLY,
        ),
        (closing_turn(WORK_PROMPT, READ_CALL), f"Changed files:\n\n{THREE_BULLETS}\n- The hook.\n- The test."),
        (closing_turn(WORK_PROMPT, READ_CALL), "Deferred:\n\n- The retry budget.\n- The docs page."),
        (closing_turn(WORK_PROMPT, READ_CALL), f"Nothing deferred.\n\n{THREE_BULLETS}"),
        (closing_turn("list the deferred items as bullets", READ_CALL), DEFERRED_REPLY),
        (closing_turn(WORK_PROMPT, READ_CALL), f"Deferred:\n\n```\n{THREE_BULLETS}\n```"),
        (closing_turn(WORK_PROMPT, READ_CALL), "No report will follow."),
        (closing_turn(WORK_PROMPT, READ_CALL), "> I'll report back once CI ends."),
        (closing_turn(WORK_PROMPT, READ_CALL), "The draft says `I'll report back once CI ends` today."),
        (closing_turn("report back when the run ends", WAKE_CALL), PROMISE_REPLY),
        (closing_turn(WORK_PROMPT, READ_CALL), f"Skipped, with reasons\n\n{THREE_BULLETS}\n- The hook."),
        (closing_turn(WORK_PROMPT, READ_CALL), "I'll merge each lint fix once the bots report back."),
        (closing_turn(WORK_PROMPT, READ_CALL), "Both checkers are running. I continue when they report."),
    ],
)
def test_should_pass_a_closing_reply_with_no_unasked_report_or_open_item_list(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    all_records: list[dict[str, object]],
    reply_text: str,
) -> None:
    transcript_path = write_records(tmp_path / "s.jsonl", all_records)
    assert run_gate(monkeypatch, capsys, transcript_path, reply_text=reply_text) == {}


def test_should_pass_a_promised_report_on_a_stop_the_gate_already_held(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    transcript_path = write_records(tmp_path / "s.jsonl", closing_turn(BED_PROMPT, WAKE_CALL))
    assert run_gate(monkeypatch, capsys, transcript_path, is_stop_hook_active=True, reply_text=PROMISE_REPLY) == {}


def test_should_pass_a_closing_reply_when_the_transcript_cannot_be_read(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    missing_path = tmp_path / "missing.jsonl"
    assert run_gate(monkeypatch, capsys, missing_path, reply_text=PROMISE_REPLY) == {}
    assert run_gate(monkeypatch, capsys, missing_path, reply_text=DEFERRED_REPLY) == {}
    hook_input = {"last_assistant_message": DEFERRED_REPLY, "transcript_path": str(missing_path)}
    assert open_tasks_stop_gate.closing_reply_findings(hook_input, replayed_transcript(None)) == []


def test_should_ask_for_a_reworked_reply_when_a_tracker_reason_and_a_closing_reason_combine(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    transcript_path = write_records(tmp_path / "s.jsonl", [user_prompt_record(BED_PROMPT), WAKE_CALL])
    block_reason = run_gate(monkeypatch, capsys, transcript_path, reply_text=PROMISE_REPLY)["reason"]
    assert block_reason.startswith("This turn worked on the user's ask and left the task list unchanged.")
    assert block_reason.index("left the task list unchanged") < block_reason.index(PROMISE_REASON_START)
    assert "Leave the reply as it stands" not in block_reason
    assert "leave the reply as it stands" not in block_reason
    assert block_reason.endswith(f"{REWORKED_REPLY_INSTRUCTION} {PROMISE_KEEP_CONDITION}")


def test_should_name_the_steps_then_end_the_turn_then_the_keep_condition_for_a_promise(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    transcript_path = write_records(tmp_path / "s.jsonl", closing_turn(BED_PROMPT, WAKE_CALL))
    block_reason = run_gate(monkeypatch, capsys, transcript_path, reply_text=PROMISE_REPLY)["reason"]
    assert block_reason == (
        'The closing reply promises the user a later report ("when you get back"), and no typed prompt in this'
        " turn asked for one. Drop the promise and carry the work to completion. If work is still open, do it"
        " now. If the turn waits on a run or a wake you armed, say in one sentence what runs and what you do"
        f" when it ends. {REWORKED_REPLY_INSTRUCTION} {PROMISE_KEEP_CONDITION}"
    )


def test_should_keep_question_cards_for_a_list_sent_in_answer_to_what_was_deferred(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    deferred_question = "Which parts of the work did you put off or skip?"
    transcript_path = write_records(tmp_path / "s.jsonl", closing_turn(deferred_question, READ_CALL))
    block_reason = run_gate(monkeypatch, capsys, transcript_path, reply_text=DEFERRED_REPLY)["reason"]
    assert block_reason.startswith('The closing reply lists 5 items under "What I deferred, checked')
    assert block_reason.lower().count(END_THE_TURN) == 1
    assert block_reason.index(SHORT_REPLY_INSTRUCTION) < block_reason.index(LIST_KEEP_START)
    assert "asked for the items as a list or a table in chat" in block_reason
    assert block_reason.endswith(ASKED_ANSWER_SENTENCE)


@pytest.mark.parametrize(
    ("all_records", "reply_text", "all_reason_parts"),
    [
        (
            closing_turn(WORK_PROMPT, READ_CALL),
            f"I'll report back once CI ends.\n\nWhat I deferred:\n{THREE_BULLETS}",
            (PROMISE_REASON_START, LIST_REASON_START, SHORT_REPLY_INSTRUCTION, PROMISE_KEEP_CONDITION, LIST_KEEP_START),
        ),
        (
            [user_prompt_record(BED_PROMPT), WAKE_CALL],
            f"What I deferred:\n{THREE_BULLETS}",
            ("left the task list unchanged", LIST_REASON_START, SHORT_REPLY_INSTRUCTION, LIST_KEEP_START),
        ),
        (
            closing_turn(WORK_PROMPT, tool_call_record("Edit")),
            f"Three items need you.\n\n{PROMISE_REPLY}",
            ("waits on them", "The turn ran no read call.", PROMISE_REASON_START, REWORKED_REPLY_INSTRUCTION, PROMISE_KEEP_CONDITION),
        ),
    ],
)
def test_should_end_the_turn_once_when_findings_combine(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    all_records: list[dict[str, object]],
    reply_text: str,
    all_reason_parts: tuple[str, ...],
) -> None:
    transcript_path = write_records(tmp_path / "s.jsonl", all_records)
    block_reason = run_gate(monkeypatch, capsys, transcript_path, reply_text=reply_text)["reason"]
    assert block_reason.lower().count(END_THE_TURN) == 1
    all_positions = [block_reason.index(each_part) for each_part in all_reason_parts]
    assert all_positions == sorted(all_positions)


def test_should_hold_a_wait_on_a_running_agent_with_the_keep_condition(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    notification = "<task-notification>the reuse agent finished</task-notification>"
    transcript_path = write_records(tmp_path / "s.jsonl", [user_prompt_record(notification), READ_CALL])
    reply_text = "The lint job is still running, and I'll report once it finishes."
    block_reason = run_gate(monkeypatch, capsys, transcript_path, reply_text=reply_text)["reason"]
    assert '("I\'ll report once")' in block_reason
    assert block_reason.endswith(PROMISE_KEEP_CONDITION)


OTHER_HOOK_FEEDBACK = {
    "type": "user",
    "isMeta": True,
    "uuid": "feedback-1",
    "message": {
        "role": "user",
        "content": "Stop hook feedback:\n[command hook 2]: The build cache is out of date.",
    },
}


def keyed_prompt_record(prompt_text: str, prompt_uuid: str) -> dict[str, object]:
    return {**user_prompt_record(prompt_text), "uuid": prompt_uuid}


def keyed_turn(prompt_uuid: str = "prompt-1") -> list[dict[str, object]]:
    return [keyed_prompt_record(BED_PROMPT, prompt_uuid), TRACKER_CALL, WAKE_CALL, OTHER_HOOK_FEEDBACK]


def test_should_hold_a_promise_once_after_another_stop_hook_held_the_turn(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    transcript_path = write_records(tmp_path / "s.jsonl", keyed_turn())
    all_outputs = [
        run_gate(monkeypatch, capsys, transcript_path, is_stop_hook_active=True, reply_text=PROMISE_REPLY)
        for _ in range(3)
    ]
    assert all_outputs[0]["reason"].startswith(PROMISE_REASON_START)
    assert all_outputs[0]["reason"].endswith(PROMISE_KEEP_CONDITION)
    assert all_outputs[1:] == [{}, {}]


def test_should_hold_again_after_a_new_prompt_in_the_same_session(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    first_path = write_records(tmp_path / "s.jsonl", keyed_turn("prompt-1"))
    assert run_gate(monkeypatch, capsys, first_path, is_stop_hook_active=True, reply_text=PROMISE_REPLY)
    second_path = write_records(tmp_path / "s.jsonl", [*keyed_turn("prompt-1"), *keyed_turn("prompt-2")])
    second_output = run_gate(monkeypatch, capsys, second_path, is_stop_hook_active=True, reply_text=PROMISE_REPLY)
    assert second_output["reason"].startswith(PROMISE_REASON_START)


def test_should_hold_a_list_once_after_another_stop_hook_held_the_turn(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_records = [keyed_prompt_record(DEFERRED_PROMPT, "prompt-1"), TRACKER_CALL, READ_CALL, OTHER_HOOK_FEEDBACK]
    transcript_path = write_records(tmp_path / "s.jsonl", all_records)
    first_output = run_gate(monkeypatch, capsys, transcript_path, is_stop_hook_active=True, reply_text=DEFERRED_REPLY)
    assert first_output["reason"].startswith(LIST_REASON_START)
    assert run_gate(monkeypatch, capsys, transcript_path, is_stop_hook_active=True, reply_text=DEFERRED_REPLY) == {}


def test_should_pass_a_held_stop_when_the_turn_marker_cannot_be_written(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path / "absent_directory"))
    transcript_path = write_records(tmp_path / "s.jsonl", keyed_turn())
    assert run_gate(monkeypatch, capsys, transcript_path, is_stop_hook_active=True, reply_text=PROMISE_REPLY) == {}


def test_should_pass_a_held_stop_after_this_gate_held_the_turn(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    unkept_path = tmp_path / "absent_directory"
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(unkept_path))
    transcript_path = write_records(tmp_path / "s.jsonl", keyed_turn()[:-1])
    first_reason = run_gate(monkeypatch, capsys, transcript_path, reply_text=PROMISE_REPLY)["reason"]
    own_feedback = {**OTHER_HOOK_FEEDBACK, "message": {"role": "user", "content": f"Stop hook feedback:\n{first_reason}"}}
    write_records(transcript_path, [*keyed_turn()[:-1], own_feedback])
    unkept_path.mkdir()
    assert run_gate(monkeypatch, capsys, transcript_path, is_stop_hook_active=True, reply_text=PROMISE_REPLY) == {}


def test_should_pass_a_held_stop_after_this_gate_held_the_first_stop(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    transcript_path = write_records(tmp_path / "s.jsonl", keyed_turn()[:-1])
    assert run_gate(monkeypatch, capsys, transcript_path, reply_text=PROMISE_REPLY)["decision"] == "block"
    assert run_gate(monkeypatch, capsys, transcript_path, is_stop_hook_active=True, reply_text=PROMISE_REPLY) == {}


def test_should_keep_skipping_a_held_codex_stop(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    plan_arguments = json.dumps({"plan": [{"step": "Report the run", "status": "in_progress"}]})
    plan_call = codex_record({"type": "function_call", "name": "update_plan", "arguments": plan_arguments})
    transcript_path = write_records(tmp_path / "rollout.jsonl", [codex_prompt(BED_PROMPT), plan_call])
    assert run_gate(monkeypatch, capsys, transcript_path, is_stop_hook_active=True, reply_text=PROMISE_REPLY) == {}


def test_should_leave_the_tracker_reasons_off_a_held_stop(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_records = [keyed_prompt_record(WORK_PROMPT, "prompt-1"), tool_call_record("Bash"), OTHER_HOOK_FEEDBACK]
    transcript_path = write_records(tmp_path / "s.jsonl", all_records)
    assert run_gate(monkeypatch, capsys, transcript_path, is_stop_hook_active=True) == {}
    block_reason = run_gate(monkeypatch, capsys, transcript_path, is_stop_hook_active=True, reply_text=PROMISE_REPLY)[
        "reason"
    ]
    assert "left the task list unchanged" not in block_reason


JUDGE_ONLY_PROMISE = "Once the soak test settles, the numbers go in this thread."
JUDGE_ONLY_PROMISE_REPLY = f"Both soak runs are armed. {JUDGE_ONLY_PROMISE}"
JUDGE_ONLY_LIST_LEAD = "Three calls are yours:"
JUDGE_ONLY_LIST_REPLY = f"{JUDGE_ONLY_LIST_LEAD}\n\n{THREE_BULLETS}"
JUDGE_LOG_NAME = Path(".claude") / "logs" / "closing-reply-judge.log"


def judge_answer(promise_span: str = "", list_span: str = "") -> dict[str, object]:
    return {
        "promised_report": bool(promise_span),
        "promise_span": promise_span,
        "decisions_as_list": bool(list_span),
        "list_span": list_span,
    }


def judged_turn(prompt_text: str = BED_PROMPT) -> list[dict[str, object]]:
    return [keyed_prompt_record(prompt_text, "prompt-1"), TRACKER_CALL, WAKE_CALL]


def assistant_text_record(reply_text: str) -> dict[str, object]:
    return {
        "type": "assistant",
        "message": {"id": "reply-1", "role": "assistant", "content": [{"type": "text", "text": reply_text}]},
    }


def test_should_hold_when_judge_reports_a_promised_report(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path, judge_stub: JudgeStub
) -> None:
    judge_stub.answer(verdict=judge_answer(promise_span=JUDGE_ONLY_PROMISE))
    transcript_path = write_records(tmp_path / "s.jsonl", judged_turn())
    block_reason = run_gate(monkeypatch, capsys, transcript_path, reply_text=JUDGE_ONLY_PROMISE_REPLY)["reason"]
    assert block_reason.startswith(PROMISE_REASON_START)
    assert f'("{JUDGE_ONLY_PROMISE}")' in block_reason
    assert block_reason.endswith(PROMISE_KEEP_CONDITION)
    assert len(judge_stub.calls()) == 1


def test_should_hold_when_judge_reports_decisions_as_a_list(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path, judge_stub: JudgeStub
) -> None:
    judge_stub.answer(verdict=judge_answer(list_span=JUDGE_ONLY_LIST_LEAD))
    transcript_path = write_records(tmp_path / "s.jsonl", judged_turn("Clean up the release branch"))
    block_reason = run_gate(monkeypatch, capsys, transcript_path, reply_text=JUDGE_ONLY_LIST_REPLY)["reason"]
    assert block_reason.startswith(f'The closing reply lists 3 items under "{JUDGE_ONLY_LIST_LEAD}"')
    assert SHORT_REPLY_INSTRUCTION in block_reason


def test_should_allow_the_stop_when_the_judge_times_out(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path, judge_stub: JudgeStub
) -> None:
    judge_stub.answer(verdict=judge_answer(promise_span=JUDGE_ONLY_PROMISE))
    judge_stub.sleep(5)
    monkeypatch.setattr(closing_reply_judge, "JUDGE_TIMEOUT_SECONDS", 0.5)
    transcript_path = write_records(tmp_path / "s.jsonl", judged_turn())
    assert run_gate(monkeypatch, capsys, transcript_path, reply_text=JUDGE_ONLY_PROMISE_REPLY) == {}
    assert "the child timed out" in (tmp_path / JUDGE_LOG_NAME).read_text()


def test_should_allow_the_stop_when_the_judge_answer_is_not_the_verdict_shape(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path, judge_stub: JudgeStub
) -> None:
    judge_stub.answer(result="The reply promises a report.")
    transcript_path = write_records(tmp_path / "s.jsonl", judged_turn())
    assert run_gate(monkeypatch, capsys, transcript_path, reply_text=JUDGE_ONLY_PROMISE_REPLY) == {}
    assert len(judge_stub.calls()) == 1


def test_should_allow_the_stop_when_the_span_is_not_in_the_reply(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path, judge_stub: JudgeStub
) -> None:
    judge_stub.answer(verdict=judge_answer(promise_span="The numbers go in this thread tomorrow."))
    transcript_path = write_records(tmp_path / "s.jsonl", judged_turn())
    assert run_gate(monkeypatch, capsys, transcript_path, reply_text=JUDGE_ONLY_PROMISE_REPLY) == {}


def test_should_use_the_phrase_checks_when_claude_is_missing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    transcript_path = write_records(tmp_path / "s.jsonl", judged_turn())
    assert run_gate(monkeypatch, capsys, transcript_path, reply_text=PROMISE_REPLY)["reason"].startswith(
        PROMISE_REASON_START
    )
    assert run_gate(monkeypatch, capsys, transcript_path, reply_text=JUDGE_ONLY_PROMISE_REPLY) == {}


def test_should_not_hold_on_phrases_when_the_judge_gives_no_verdict(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path, judge_stub: JudgeStub
) -> None:
    judge_stub.exit_code(1)
    transcript_path = write_records(tmp_path / "s.jsonl", judged_turn())
    assert run_gate(monkeypatch, capsys, transcript_path, reply_text=PROMISE_REPLY) == {}
    assert len(judge_stub.calls()) == 1


def test_should_hold_once_per_turn_when_the_judge_holds_twice(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path, judge_stub: JudgeStub
) -> None:
    judge_stub.answer(verdict=judge_answer(promise_span=JUDGE_ONLY_PROMISE))
    transcript_path = write_records(tmp_path / "s.jsonl", [*judged_turn(), OTHER_HOOK_FEEDBACK])
    all_outputs = [
        run_gate(monkeypatch, capsys, transcript_path, is_stop_hook_active=True, reply_text=JUDGE_ONLY_PROMISE_REPLY)
        for _ in range(3)
    ]
    assert all_outputs[0]["reason"].startswith(PROMISE_REASON_START)
    assert all_outputs[1:] == [{}, {}]
    assert len(judge_stub.calls()) == 1


def test_should_not_call_the_judge_after_this_turn_was_held(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path, judge_stub: JudgeStub
) -> None:
    judge_stub.answer(verdict=judge_answer(promise_span=JUDGE_ONLY_PROMISE))
    transcript_path = write_records(tmp_path / "s.jsonl", judged_turn())
    assert run_gate(monkeypatch, capsys, transcript_path, reply_text=JUDGE_ONLY_PROMISE_REPLY)["decision"] == "block"
    held_stop = run_gate(monkeypatch, capsys, transcript_path, is_stop_hook_active=True, reply_text=JUDGE_ONLY_PROMISE_REPLY)
    assert held_stop == {}
    assert len(judge_stub.calls()) == 1


def test_should_allow_the_stop_inside_a_judge_or_review_child(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path, judge_stub: JudgeStub
) -> None:
    judge_stub.answer(verdict=judge_answer(promise_span=JUDGE_ONLY_PROMISE))
    monkeypatch.setenv("CLAUDE_TURN_REVIEW_CHILD", "1")
    transcript_path = write_records(
        tmp_path / "s.jsonl", [keyed_prompt_record(WORK_PROMPT, "prompt-1"), tool_call_record("Bash")]
    )
    assert run_gate(monkeypatch, capsys, transcript_path, reply_text=JUDGE_ONLY_PROMISE_REPLY) == {}
    assert judge_stub.calls() == []


def test_should_not_call_the_judge_on_codex_or_cursor_payloads(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path, judge_stub: JudgeStub
) -> None:
    judge_stub.answer(verdict=judge_answer(promise_span=JUDGE_ONLY_PROMISE))
    plan_arguments = json.dumps({"plan": [{"step": "Report the run", "status": "in_progress"}]})
    plan_call = codex_record({"type": "function_call", "name": "update_plan", "arguments": plan_arguments})
    rollout_path = write_records(tmp_path / "rollout.jsonl", [codex_prompt(BED_PROMPT), plan_call])
    codex_output = run_gate(
        monkeypatch, capsys, rollout_path, reply_text=PROMISE_REPLY, all_extra_fields={"turn_id": "turn-1"}
    )
    assert codex_output["reason"].startswith(PROMISE_REASON_START)
    assert run_gate(monkeypatch, capsys, rollout_path, reply_text=PROMISE_REPLY)["reason"].startswith(
        PROMISE_REASON_START
    )
    cursor_path = write_records(tmp_path / "cursor.jsonl", judged_turn())
    cursor_output = run_gate(
        monkeypatch,
        capsys,
        cursor_path,
        reply_text=JUDGE_ONLY_PROMISE_REPLY,
        all_extra_fields={"conversation_id": "c-1", "status": "completed", "loop_count": 0},
    )
    assert cursor_output == {}
    assert judge_stub.calls() == []


def test_should_make_no_judge_call_when_the_transcript_cannot_be_read(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path, judge_stub: JudgeStub
) -> None:
    judge_stub.answer(verdict=judge_answer(promise_span=JUDGE_ONLY_PROMISE))
    assert run_gate(monkeypatch, capsys, tmp_path / "absent.jsonl", reply_text=JUDGE_ONLY_PROMISE_REPLY) == {}
    assert judge_stub.calls() == []
    assert "the transcript cannot be read" in (tmp_path / JUDGE_LOG_NAME).read_text()


def test_should_read_the_reply_from_the_transcript_when_the_payload_has_none(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path, judge_stub: JudgeStub
) -> None:
    judge_stub.answer(verdict=judge_answer(promise_span=JUDGE_ONLY_PROMISE))
    transcript_path = write_records(
        tmp_path / "s.jsonl", [*judged_turn(), assistant_text_record(JUDGE_ONLY_PROMISE_REPLY)]
    )
    block_reason = run_gate(monkeypatch, capsys, transcript_path, reply_text="")["reason"]
    assert block_reason.startswith(PROMISE_REASON_START)
    [judge_call] = judge_stub.calls()
    assert json.dumps(JUDGE_ONLY_PROMISE_REPLY) in judge_call["stdin"]


FOOTER_LEAD = "In progress:"
FOOTER_REPLY = (
    "The hold on pull request 8678 is off.\n\n"
    f"{FOOTER_LEAD}\n"
    "- I am shipping pull request 8590 once its automated tests pass.\n"
    "- I am shipping pull request 8693 once its automated tests pass.\n"
    "- I am shipping pull request 8678 once 8693 is in."
)


def test_should_drop_a_judged_list_that_is_the_in_progress_footer(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path, judge_stub: JudgeStub
) -> None:
    judge_stub.answer(verdict=judge_answer(list_span=FOOTER_LEAD))
    transcript_path = write_records(tmp_path / "s.jsonl", judged_turn("Lift the holds you need to"))
    assert run_gate(monkeypatch, capsys, transcript_path, reply_text=FOOTER_REPLY) == {}
    assert len(judge_stub.calls()) == 1


def test_should_hold_a_judged_promise_inside_the_in_progress_footer(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path, judge_stub: JudgeStub
) -> None:
    footer_promise = "I will report back once 8693 is in."
    judge_stub.answer(verdict=judge_answer(promise_span=footer_promise, list_span=FOOTER_LEAD))
    transcript_path = write_records(tmp_path / "s.jsonl", judged_turn("Lift the holds you need to"))
    block_reason = run_gate(
        monkeypatch, capsys, transcript_path, reply_text=f"{FOOTER_REPLY} {footer_promise}"
    )["reason"]
    assert block_reason.startswith(PROMISE_REASON_START)
    assert "The closing reply lists" not in block_reason
