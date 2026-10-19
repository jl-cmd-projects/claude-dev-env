import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

import open_tasks_stop_gate

GATE_PATH = Path(open_tasks_stop_gate.__file__)
SESSION_ID = "s-123"


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_TASK_LIST_ID", raising=False)


def run_gate(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    reply_text: str,
    transcript_path: Path | None = None,
) -> tuple[int, str]:
    hook_input: dict[str, object] = {
        "hook_event_name": "Stop",
        "session_id": SESSION_ID,
        "stop_hook_active": False,
        "last_assistant_message": reply_text,
    }
    if transcript_path is not None:
        hook_input["transcript_path"] = str(transcript_path)
    monkeypatch.setattr(
        "sys.stdin", io.TextIOWrapper(io.BytesIO(json.dumps(hook_input).encode("utf-8")))
    )
    exit_code = open_tasks_stop_gate.main()
    return exit_code, capsys.readouterr().out


def write_task_store(home_directory: Path, all_tasks: list[dict[str, str]]) -> None:
    task_directory = home_directory / ".claude" / "tasks" / SESSION_ID
    task_directory.mkdir(parents=True)
    for each_task in all_tasks:
        (task_directory / f"{each_task['id']}.json").write_text(json.dumps(each_task), encoding="utf-8")


def write_todo_transcript(transcript_path: Path, all_todos: list[dict[str, str]]) -> Path:
    tool_use = {"type": "tool_use", "id": "t1", "name": "TodoWrite", "input": {"todos": all_todos}}
    transcript_path.write_text(
        json.dumps({"type": "assistant", "message": {"content": [tool_use]}}), encoding="utf-8"
    )
    return transcript_path


def test_should_block_when_a_pending_task_is_not_reported(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    write_task_store(tmp_path, [{"id": "1", "subject": "Rotate the deploy key", "status": "pending"}])
    exit_code, stdout_text = run_gate(monkeypatch, capsys, "All done.")
    decision = json.loads(stdout_text)
    assert exit_code == 0
    assert decision["decision"] == "block"
    assert "Rotate the deploy key" in decision["reason"]


def test_should_allow_when_every_open_task_is_reported_as_blocked_or_open(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    write_task_store(
        tmp_path,
        [
            {"id": "1", "subject": "Rotate the deploy key", "status": "pending"},
            {"id": "2", "subject": "Wait on checks", "status": "in_progress"},
            {"id": "3", "subject": "Write tests", "status": "completed"},
        ],
    )
    reply_text = "Tests written.\nBlocked: Rotate the deploy key - the owner approves the secret\n- Open: #2 - checks running"
    assert run_gate(monkeypatch, capsys, reply_text) == (0, "")


def test_should_block_when_the_item_is_only_mentioned_in_prose(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    write_task_store(tmp_path, [{"id": "1", "subject": "Rotate the deploy key", "status": "pending"}])
    _, stdout_text = run_gate(monkeypatch, capsys, "I will rotate the deploy key later.")
    assert json.loads(stdout_text)["decision"] == "block"


def test_should_allow_when_every_task_is_completed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    write_task_store(tmp_path, [{"id": "1", "subject": "Rotate the deploy key", "status": "completed"}])
    assert run_gate(monkeypatch, capsys, "Done.") == (0, "")


def test_should_read_todowrite_from_the_transcript_when_no_task_store_exists(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    transcript_path = write_todo_transcript(
        tmp_path / "s.jsonl",
        [{"content": "Ship the fix", "status": "in_progress"}, {"content": "Lint", "status": "completed"}],
    )
    _, stdout_text = run_gate(monkeypatch, capsys, "Done.", transcript_path)
    reason_text = json.loads(stdout_text)["reason"]
    assert "Ship the fix" in reason_text
    assert "Lint" not in reason_text


def test_should_replay_taskcreate_and_taskupdate_from_the_transcript(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    transcript_records = [
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "c1", "name": "TaskCreate", "input": {"subject": "Alpha"}}]}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "c1", "content": "Task #1 created successfully: Alpha"}]}},
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "c2", "name": "TaskCreate", "input": {"subject": "Beta"}}]}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "c2", "content": "Task #2 created successfully: Beta"}]}},
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "u1", "name": "TaskUpdate", "input": {"taskId": "1", "status": "completed"}}]}},
    ]
    transcript_path = tmp_path / "s.jsonl"
    transcript_path.write_text("\n".join(json.dumps(each) for each in transcript_records), encoding="utf-8")
    _, stdout_text = run_gate(monkeypatch, capsys, "Done.", transcript_path)
    reason_text = json.loads(stdout_text)["reason"]
    assert "Beta" in reason_text
    assert "Alpha" not in reason_text


def test_should_read_codex_update_plan_from_the_rollout(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    plan_arguments = json.dumps({"plan": [{"step": "Port the hook", "status": "pending"}]})
    rollout_record = {"type": "response_item", "payload": {"type": "function_call", "name": "update_plan", "arguments": plan_arguments}}
    transcript_path = tmp_path / "rollout.jsonl"
    transcript_path.write_text(json.dumps(rollout_record), encoding="utf-8")
    _, stdout_text = run_gate(monkeypatch, capsys, "Done.", transcript_path)
    assert "Port the hook" in json.loads(stdout_text)["reason"]


def test_should_allow_a_session_with_no_task_list(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_gate(monkeypatch, capsys, "Done.") == (0, "")


def test_should_allow_malformed_stdin(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(b"not json")))
    assert (open_tasks_stop_gate.main(), capsys.readouterr().out) == (0, "")


def test_should_block_through_a_subprocess_with_the_documented_contract(tmp_path: Path) -> None:
    write_task_store(tmp_path, [{"id": "1", "subject": "Rotate the deploy key", "status": "pending"}])
    hook_input = {"hook_event_name": "Stop", "session_id": SESSION_ID, "last_assistant_message": "Done."}
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


def write_cursor_transcript(transcript_path: Path, all_records: list[dict[str, object]]) -> Path:
    transcript_path.write_text("\n".join(json.dumps(each_record) for each_record in all_records), encoding="utf-8")
    return transcript_path


def cursor_todo_record(all_todos: list[dict[str, str]], is_merge: bool, reply_text: str) -> dict[str, object]:
    tool_use = {"type": "tool_use", "name": "TodoWrite", "input": {"todos": all_todos, "merge": is_merge}}
    return {"role": "assistant", "message": {"content": [{"type": "text", "text": reply_text}, tool_use]}}


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


def test_should_send_a_cursor_followup_when_a_merged_todo_stays_pending(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_first_todos = [
        {"id": "1", "content": "write hello.txt", "status": "in_progress"},
        {"id": "2", "content": "rotate the deploy key", "status": "pending"},
    ]
    transcript_path = write_cursor_transcript(
        tmp_path / "cursor.jsonl",
        [
            cursor_todo_record(all_first_todos, False, "Starting."),
            cursor_todo_record([{"id": "1", "status": "completed"}], True, "Done."),
        ],
    )
    block_output = run_cursor_gate(monkeypatch, capsys, transcript_path)
    assert "rotate the deploy key" in block_output["followup_message"]
    assert "write hello.txt" not in block_output["followup_message"]
    assert block_output["decision"] == "block"


@pytest.mark.parametrize("stop_status", ["aborted", "error"])
def test_should_allow_a_cursor_stop_the_user_aborted_or_that_errored(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path, stop_status: str
) -> None:
    all_todos = [{"id": "2", "content": "rotate the deploy key", "status": "pending"}]
    transcript_path = write_cursor_transcript(
        tmp_path / "cursor.jsonl", [cursor_todo_record(all_todos, False, "Stopping.")]
    )
    assert run_cursor_gate(monkeypatch, capsys, transcript_path, stop_status) == {}


def test_should_allow_cursor_when_the_last_assistant_text_reports_the_item(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_todos = [{"id": "2", "content": "rotate the deploy key", "status": "pending"}]
    transcript_path = write_cursor_transcript(
        tmp_path / "cursor.jsonl",
        [
            cursor_todo_record(all_todos, False, "Working."),
            {"role": "assistant", "message": {"content": [
                {"type": "text", "text": "Blocked: rotate the deploy key - the owner must approve the org secret"}
            ]}},
        ],
    )
    assert run_cursor_gate(monkeypatch, capsys, transcript_path) == {}


def test_should_leave_claude_block_output_without_a_followup_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    transcript_path = write_todo_transcript(
        tmp_path / "t.jsonl", [{"content": "rotate the deploy key", "status": "pending"}]
    )
    _, printed_output = run_gate(monkeypatch, capsys, "Done.", transcript_path)
    assert set(json.loads(printed_output)) == {"decision", "reason"}


def cursor_dynamic_todo_record(all_todos: list[dict[str, str]], is_merge: bool) -> dict[str, object]:
    tool_use = {
        "type": "tool_use",
        "name": "CallDynamicTool",
        "input": {"namespace": "cursor", "toolName": "TodoWrite", "arguments": {"merge": is_merge, "todos": all_todos}},
    }
    return {"role": "assistant", "message": {"content": [tool_use]}}


def test_should_read_todos_the_cursor_cli_writes_through_call_dynamic_tool(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_first_todos = [
        {"id": "1", "content": "write hello.txt", "status": "in_progress"},
        {"id": "2", "content": "rotate the deploy key", "status": "pending"},
    ]
    all_merged_todos = [
        {"id": "1", "content": "write hello.txt", "status": "completed"},
        {"id": "2", "content": "rotate the deploy key", "status": "pending"},
    ]
    transcript_path = write_cursor_transcript(
        tmp_path / "cursor.jsonl",
        [
            cursor_dynamic_todo_record(all_first_todos, False),
            cursor_dynamic_todo_record(all_merged_todos, True),
            {"role": "assistant", "message": {"content": [{"type": "text", "text": "Done."}]}},
            {"type": "turn_ended", "status": "success"},
        ],
    )
    block_output = run_cursor_gate(monkeypatch, capsys, transcript_path)
    assert "rotate the deploy key" in block_output["followup_message"]
    assert "write hello.txt" not in block_output["followup_message"]


def test_should_allow_a_cursor_stop_after_five_followups(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_todos = [{"id": "2", "content": "rotate the deploy key", "status": "pending"}]
    transcript_path = write_cursor_transcript(tmp_path / "cursor.jsonl", [cursor_todo_record(all_todos, False, "Done.")])
    assert "rotate the deploy key" in run_cursor_gate(monkeypatch, capsys, transcript_path, loop_count=4)["followup_message"]
    assert run_cursor_gate(monkeypatch, capsys, transcript_path, loop_count=5) == {}
