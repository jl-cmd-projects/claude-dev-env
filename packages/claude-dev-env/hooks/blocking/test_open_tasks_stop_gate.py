import importlib
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
    reply_text = "Tests written.\nBlocked: Rotate the deploy key - the owner pastes the secret\n- Open: #2 - checks running"
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
                {"type": "text", "text": "Blocked: rotate the deploy key - the owner pastes the org secret"}
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


def ccd_plan_record(all_plan_input: dict[str, object]) -> dict[str, object]:
    tool_use = {"type": "tool_use", "id": "p1", "name": "mcp__ccd_turn__update_plan", "input": all_plan_input}
    return {"type": "assistant", "timestamp": "2026-01-01T00:00:00.000Z", "message": {"content": [tool_use]}}


def assistant_text_record(reply_text: str) -> dict[str, object]:
    return {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": reply_text}]}}


def write_records(transcript_path: Path, all_records: list[dict[str, object]]) -> Path:
    transcript_path.write_text("\n".join(json.dumps(each_record) for each_record in all_records), encoding="utf-8")
    return transcript_path


def block_reason(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    reply_text: str,
    transcript_path: Path | None = None,
) -> str:
    _, stdout_text = run_gate(monkeypatch, capsys, reply_text, transcript_path)
    return json.loads(stdout_text)["reason"] if stdout_text else ""


def record_ask(prompt_text: str) -> str | None:
    return importlib.import_module("open_task_asks").record_prompt(SESSION_ID, prompt_text)


def submit_and_replace_list(tmp_path: Path) -> Path:
    return write_records(
        tmp_path / "s.jsonl",
        [
            ccd_plan_record({"items": [{"content": "Submit both APKs", "status": "pending"}], "scope": "first_task"}),
            ccd_plan_record({"items": [{"content": "Set rows in Neon", "status": "completed"}], "scope": "continuation"}),
        ],
    )


def test_should_hold_an_interrupted_ask_after_the_user_redirects(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    assert record_ask("Export the OneUI8 and OneUI9 APKs and submit them") == "ask-1"
    assert record_ask("Set the 8 rows to Ready to Export in Neon") == "ask-2"
    transcript_path = write_records(
        tmp_path / "s.jsonl",
        [ccd_plan_record({"items": [{"content": "Set the 8 rows in Neon", "status": "completed"}], "scope": "continuation"})],
    )
    reason_text = block_reason(monkeypatch, capsys, "Rows set.\nDone: #ask-2", transcript_path)
    assert "#ask-1" in reason_text
    assert "OneUI9" in reason_text
    assert "#ask-2" not in reason_text


def test_should_hold_plan_items_a_continuation_list_dropped(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    first_items = [
        {"content": "Export the OneUI8 APK", "status": "in_progress"},
        {"content": "Submit both APKs", "status": "pending"},
    ]
    transcript_path = write_records(
        tmp_path / "s.jsonl",
        [
            ccd_plan_record({"items": first_items, "scope": "first_task"}),
            ccd_plan_record({"scope": "continuation", "items": [{"content": "Set rows in Neon", "status": "completed"}]}),
        ],
    )
    reason_text = block_reason(monkeypatch, capsys, "Rows set.", transcript_path)
    assert "Export the OneUI8 APK" in reason_text
    assert "Submit both APKs" in reason_text
    assert "Set rows in Neon" not in reason_text


def test_should_hold_an_ask_that_never_reached_a_plan(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    record_ask("Export the OneUI8 and OneUI9 APKs and submit them")
    reason_text = block_reason(monkeypatch, capsys, "Done.")
    assert "#ask-1: Export the OneUI8 and OneUI9 APKs and submit them" in reason_text
    assert "Done: #ask-N" in reason_text


def test_should_merge_the_task_store_with_the_ccd_plan(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    write_task_store(tmp_path, [{"id": "1", "subject": "Rotate the deploy key", "status": "pending"}])
    transcript_path = write_records(
        tmp_path / "s.jsonl",
        [ccd_plan_record({"items": [{"content": "Port the hook", "status": "in_progress"}], "scope": "first_task"})],
    )
    reason_text = block_reason(monkeypatch, capsys, "Done.", transcript_path)
    assert "Rotate the deploy key" in reason_text
    assert "Port the hook" in reason_text


def test_should_hold_an_ask_whose_subject_matches_a_completed_task(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    write_task_store(tmp_path, [{"id": "1", "subject": "Fix login", "status": "completed"}])
    assert record_ask("Fix login") == "ask-1"
    reason_text = block_reason(monkeypatch, capsys, "Done.")
    assert "#ask-1: Fix login" in reason_text


def test_should_hold_a_pending_task_that_shares_a_subject_with_a_completed_task(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    write_task_store(
        tmp_path,
        [
            {"id": "1", "subject": "Run tests", "status": "completed"},
            {"id": "2", "subject": "Run tests", "status": "pending"},
        ],
    )
    assert "Run tests" in block_reason(monkeypatch, capsys, "Done.")


def test_should_record_nothing_for_a_question_only_prompt(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert record_ask("wait, did the export fail?") is None
    assert record_ask("are you monitoring these? yes or no") is None
    assert run_gate(monkeypatch, capsys, "No, it passed.") == (0, "")


def test_should_not_close_a_plan_item_on_a_done_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    transcript_path = write_records(
        tmp_path / "s.jsonl",
        [ccd_plan_record({"items": [{"content": "Port the hook", "status": "in_progress"}], "scope": "first_task"})],
    )
    assert "Port the hook" in block_reason(monkeypatch, capsys, "Done: Port the hook", transcript_path)


def test_should_close_an_ask_and_a_carried_item_on_a_dropped_line_quoting_the_user(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    record_ask("Export the OneUI8 and OneUI9 APKs and submit them")
    transcript_path = submit_and_replace_list(tmp_path)
    record_ask("Skip the APK export for now, set the rows instead")
    reply_text = (
        "Rows set.\nDone: #ask-2\n"
        'Dropped: #ask-1 - "skip the APK export for now"\n'
        'Dropped: Submit both APKs - "Skip the APK export"'
    )
    assert run_gate(monkeypatch, capsys, reply_text, transcript_path) == (0, "")
    with transcript_path.open("a", encoding="utf-8") as transcript_handle:
        transcript_handle.write("\n" + json.dumps(assistant_text_record(reply_text)))
    assert run_gate(monkeypatch, capsys, "Nothing else.", transcript_path) == (0, "")


def test_should_hold_a_dropped_line_whose_quote_the_user_never_wrote(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    record_ask("Export the OneUI8 and OneUI9 APKs and submit them")
    transcript_path = submit_and_replace_list(tmp_path)
    record_ask("Set the rows next")
    reply_text = 'Dropped: #ask-1 - "the user cancelled the export"\nDropped: Submit both APKs - "skip it, it is done"'
    reason_text = block_reason(monkeypatch, capsys, reply_text, transcript_path)
    assert "#ask-1" in reason_text
    assert "Submit both APKs" in reason_text


def test_should_hold_a_dropped_line_quoting_the_ask_itself(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    record_ask("Export the OneUI8 and OneUI9 APKs and submit them")
    reason_text = block_reason(monkeypatch, capsys, 'Dropped: #ask-1 - "Export the OneUI8"')
    assert "#ask-1" in reason_text


def test_should_hold_an_ask_again_when_the_next_reply_omits_its_open_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    record_ask("Export the OneUI8 and OneUI9 APKs and submit them")
    first_reply = "Open: #ask-1 - the export job runs next"
    assert run_gate(monkeypatch, capsys, first_reply) == (0, "")
    transcript_path = write_records(tmp_path / "s.jsonl", [assistant_text_record(first_reply)])
    assert "#ask-1" in block_reason(monkeypatch, capsys, "Still running.", transcript_path)


def test_should_allow_the_stop_once_a_carried_item_is_listed_completed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    transcript_path = submit_and_replace_list(tmp_path)
    assert "Submit both APKs" in block_reason(monkeypatch, capsys, "Rows set.", transcript_path)
    with transcript_path.open("a", encoding="utf-8") as transcript_handle:
        relisted = ccd_plan_record({"items": [{"content": "Submit both APKs", "status": "completed"}], "scope": "continuation"})
        transcript_handle.write("\n" + json.dumps(relisted))
    assert run_gate(monkeypatch, capsys, "Both submitted.", transcript_path) == (0, "")


def test_should_mark_the_right_item_for_a_done_index_after_a_continuation(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    replacing_items = [
        {"content": "Read the schema", "status": "in_progress"},
        {"content": "Set rows in Neon", "status": "pending"},
    ]
    transcript_path = write_records(
        tmp_path / "s.jsonl",
        [
            ccd_plan_record({"items": [{"content": "Submit both APKs", "status": "pending"}], "scope": "first_task"}),
            ccd_plan_record({"items": replacing_items, "scope": "continuation"}),
            ccd_plan_record({"done": [1, 2]}),
        ],
    )
    reason_text = block_reason(monkeypatch, capsys, "Rows set.", transcript_path)
    assert "Submit both APKs" in reason_text
    assert "Read the schema" not in reason_text
    assert "Set rows in Neon" not in reason_text


DECISION_BLOCKED_REPLY = "Branch pushed.\nBlocked: #ask-1 - your OK to merge the app PR #7071 first."


def user_prompt_record(prompt_text: str) -> dict[str, object]:
    return {"type": "user", "message": {"role": "user", "content": prompt_text}}


def tool_call_record(tool_name: str) -> dict[str, object]:
    tool_use = {"type": "tool_use", "id": "q1", "name": tool_name, "input": {}}
    return {"type": "assistant", "message": {"role": "assistant", "content": [tool_use]}}


def test_should_block_a_decision_blocked_line_with_no_card_this_turn(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    record_ask("Merge the release branch")
    transcript_path = write_records(tmp_path / "s.jsonl", [user_prompt_record("Merge the release branch")])
    reason_text = block_reason(monkeypatch, capsys, DECISION_BLOCKED_REPLY, transcript_path)
    assert "AskUserQuestion" in reason_text
    assert "your OK to merge" in reason_text


@pytest.mark.parametrize(
    "card_tool_name",
    ["AskUserQuestion", "mcp__hearthbot__ask_decision", "mcp__hearthbot__request_decision"],
)
def test_should_allow_a_decision_blocked_line_after_a_card_this_turn(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path, card_tool_name: str
) -> None:
    record_ask("Merge the release branch")
    transcript_path = write_records(
        tmp_path / "s.jsonl", [user_prompt_record("Merge the release branch"), tool_call_record(card_tool_name)]
    )
    assert run_gate(monkeypatch, capsys, DECISION_BLOCKED_REPLY, transcript_path) == (0, "")


def test_should_block_a_decision_blocked_line_when_the_card_came_in_an_earlier_turn(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    record_ask("Merge the release branch")
    transcript_path = write_records(
        tmp_path / "s.jsonl",
        [
            tool_call_record("AskUserQuestion"),
            user_prompt_record("Merge the release branch"),
        ],
    )
    assert "AskUserQuestion" in block_reason(monkeypatch, capsys, DECISION_BLOCKED_REPLY, transcript_path)


def test_should_allow_a_blocked_line_for_an_input_the_user_supplies(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    record_ask("Rotate the deploy key")
    transcript_path = write_records(tmp_path / "s.jsonl", [user_prompt_record("Rotate the deploy key")])
    reply_text = "Key script ready.\nBlocked: #ask-1 - the new deploy key secret, pasted into the session"
    assert run_gate(monkeypatch, capsys, reply_text, transcript_path) == (0, "")


def test_should_keep_the_card_through_stop_hook_feedback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    record_ask("Merge the release branch")
    transcript_path = write_records(
        tmp_path / "s.jsonl",
        [
            user_prompt_record("Merge the release branch"),
            tool_call_record("AskUserQuestion"),
            {"type": "user", "isMeta": True, "message": {"content": "Stop hook feedback"}},
        ],
    )
    assert run_gate(monkeypatch, capsys, DECISION_BLOCKED_REPLY, transcript_path) == (0, "")


def test_should_allow_a_decision_blocked_line_after_a_codex_request_user_input_call(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    record_ask("Merge the release branch")
    user_message = {"type": "response_item", "payload": {"type": "message", "role": "user", "content": []}}
    card_call = {"type": "response_item", "payload": {"type": "function_call", "name": "request_user_input", "arguments": "{}"}}
    transcript_path = write_records(tmp_path / "rollout.jsonl", [user_message, card_call])
    assert run_gate(monkeypatch, capsys, DECISION_BLOCKED_REPLY, transcript_path) == (0, "")


def test_should_allow_a_blocked_line_for_a_device_step_the_user_takes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    record_ask("Install the runner")
    transcript_path = write_records(tmp_path / "s.jsonl", [user_prompt_record("Install the runner")])
    reply_text = "Installer built.\nBlocked: #ask-1 - run the installer on your PC and paste the log"
    assert run_gate(monkeypatch, capsys, reply_text, transcript_path) == (0, "")


def test_should_leave_a_cursor_decision_blocked_line_alone(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    transcript_path = write_cursor_transcript(
        tmp_path / "cursor.jsonl",
        [{"role": "assistant", "message": {"content": [{"type": "text", "text": DECISION_BLOCKED_REPLY}]}}],
    )
    assert run_cursor_gate(monkeypatch, capsys, transcript_path) == {}
