import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

import open_tasks_stop_gate
from open_tasks_transcript import TaskItem, replayed_transcript

GATE_PATH = Path(open_tasks_stop_gate.__file__)
SESSION_ID = "s-123"
WORK_PROMPT = "Export the APKs and submit them"


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_TASK_LIST_ID", raising=False)


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
) -> dict[str, str]:
    hook_input: dict[str, object] = {
        "hook_event_name": "Stop",
        "session_id": SESSION_ID,
        "stop_hook_active": is_stop_hook_active,
        "last_assistant_message": "Done.",
    }
    if transcript_path is not None:
        hook_input["transcript_path"] = str(transcript_path)
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(json.dumps(hook_input).encode("utf-8"))))
    assert open_tasks_stop_gate.main() == 0
    printed_output = capsys.readouterr().out
    return json.loads(printed_output) if printed_output else {}


def test_should_block_a_work_turn_that_left_the_task_list_unchanged(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    transcript_path = write_records(tmp_path / "s.jsonl", [user_prompt_record(WORK_PROMPT), tool_call_record("Bash")])
    block_output = run_gate(monkeypatch, capsys, transcript_path)
    assert block_output["decision"] == "block"
    assert "task list" in block_output["reason"]
    assert "followup_message" not in block_output


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
    assert completed_process.returncode == 0
    assert json.loads(completed_process.stdout)["decision"] == "block"


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
    open_tasks_stop_gate.main()
    printed_output = capsys.readouterr().out
    return json.loads(printed_output) if printed_output else {}


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


def test_should_add_a_followup_message_only_for_a_cursor_payload() -> None:
    assert open_tasks_stop_gate.block_output_for({}, "why") == {"decision": "block", "reason": "why"}
    assert open_tasks_stop_gate.block_output_for({"conversation_id": "c-1"}, "why")["followup_message"] == "why"
