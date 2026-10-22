import json
from pathlib import Path

import pytest

from open_tasks_transcript import (
    TaskItem,
    claude_prompt_text,
    codex_prompt_text,
    is_assistant_record,
    is_codex_work_call,
    is_user_prompt_record,
    parsed_object,
    replayed_transcript,
    unwrapped_tool_call,
)


def write_transcript(transcript_path: Path, all_records: list[dict[str, object]]) -> Path:
    transcript_path.write_text("\n".join(json.dumps(each_record) for each_record in all_records), encoding="utf-8")
    return transcript_path


def dynamic_todo_record(all_todos: list[dict[str, str]], is_merge: bool) -> dict[str, object]:
    tool_use = {
        "type": "tool_use",
        "name": "CallDynamicTool",
        "input": {"namespace": "cursor", "toolName": "TodoWrite", "arguments": {"merge": is_merge, "todos": all_todos}},
    }
    return {"role": "assistant", "message": {"content": [tool_use]}}


def test_should_unwrap_a_call_dynamic_tool_todo_write_call() -> None:
    all_arguments = {"merge": False, "todos": []}
    wrapped_input = {"namespace": "cursor", "toolName": "TodoWrite", "arguments": all_arguments}
    assert unwrapped_tool_call("CallDynamicTool", wrapped_input) == ("TodoWrite", all_arguments)
    assert unwrapped_tool_call("Read", wrapped_input) == ("Read", wrapped_input)
    assert unwrapped_tool_call("CallDynamicTool", {"toolName": "TodoWrite"}) == ("CallDynamicTool", {"toolName": "TodoWrite"})


def test_should_replay_cursor_dynamic_todo_writes_as_tracker_calls(tmp_path: Path) -> None:
    all_first_todos = [
        {"id": "1", "content": "write hello.txt", "status": "in_progress"},
        {"id": "2", "content": "rotate the deploy key", "status": "pending"},
    ]
    transcript_path = write_transcript(
        tmp_path / "cursor.jsonl",
        [
            dynamic_todo_record(all_first_todos, False),
            dynamic_todo_record([{"id": "1", "content": "write hello.txt", "status": "completed"}], True),
            {"role": "assistant", "message": {"content": [{"type": "text", "text": "Done."}]}},
            {"type": "turn_ended", "status": "success"},
        ],
    )
    replay = replayed_transcript(str(transcript_path))
    assert replay.items() == [
        TaskItem("1", "write hello.txt", "completed"),
        TaskItem("2", "rotate the deploy key", "pending"),
    ]
    assert replay.has_turn_tracker_write is True
    assert replay.has_turn_work_tool is False


def test_should_start_a_new_turn_at_each_prompt_and_reset_its_flags(tmp_path: Path) -> None:
    bash_call = {"type": "tool_use", "id": "b1", "name": "Bash", "input": {"command": "ls"}}
    transcript_path = write_transcript(
        tmp_path / "claude.jsonl",
        [
            {"type": "user", "message": {"role": "user", "content": "Write the gate"}},
            dynamic_todo_record([{"id": "1", "content": "Write the gate", "status": "in_progress"}], False),
            {"type": "user", "message": {"role": "user", "content": "Export the APKs"}},
            {"type": "assistant", "message": {"content": [bash_call]}},
        ],
    )
    replay = replayed_transcript(str(transcript_path))
    assert replay.turn_prompt_text == "Export the APKs"
    assert replay.has_turn_work_tool is True
    assert replay.has_turn_tracker_write is False


def test_should_not_count_a_question_card_lookup_or_title_call_as_work(tmp_path: Path) -> None:
    all_non_work_calls = [
        {"type": "tool_use", "id": f"n{each_index}", "name": each_name, "input": {}}
        for each_index, each_name in enumerate(
            ["AskUserQuestion", "ToolSearch", "TaskList", "TaskGet", "mcp__claude-code-remote__set_session_title"]
        )
    ]
    transcript_path = write_transcript(
        tmp_path / "claude.jsonl",
        [
            {"type": "user", "message": {"role": "user", "content": "Export the APKs"}},
            {"type": "assistant", "message": {"content": all_non_work_calls}},
        ],
    )
    replay = replayed_transcript(str(transcript_path))
    assert replay.has_turn_work_tool is False
    assert replay.has_turn_tracker_write is False


@pytest.mark.parametrize(
    ("record", "expected_text"),
    [
        ({"type": "user", "message": {"role": "user", "content": "Export the APKs"}}, "Export the APKs"),
        ({"type": "user", "message": {"content": [{"type": "text", "text": "Fix it"}]}}, "Fix it"),
        ({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "b1"}]}}, None),
        ({"type": "user", "isMeta": True, "message": {"content": "Stop hook feedback: hold"}}, None),
        ({"type": "user", "message": {"content": "Stop hook feedback:\nhold"}}, None),
        ({"type": "assistant", "message": {"content": "Done."}}, None),
    ],
)
def test_should_read_prompt_text_only_from_a_record_that_starts_a_turn(
    record: dict[str, object], expected_text: str | None
) -> None:
    assert claude_prompt_text(record) == expected_text
    assert is_user_prompt_record(record) is (expected_text is not None)


def test_should_read_codex_user_message_text() -> None:
    user_message = {
        "type": "response_item",
        "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Ship it"}]},
    }
    assistant_message = {"type": "response_item", "payload": {"type": "message", "role": "assistant", "content": "ok"}}
    assert codex_prompt_text(user_message) == "Ship it"
    assert codex_prompt_text(assistant_message) is None


def test_should_count_codex_tool_calls_other_than_the_plan_as_work() -> None:
    def codex_call(call_type: str, tool_name: str) -> dict[str, object]:
        return {"type": "response_item", "payload": {"type": call_type, "name": tool_name}}

    assert is_codex_work_call(codex_call("function_call", "shell")) is True
    assert is_codex_work_call(codex_call("local_shell_call", "")) is True
    assert is_codex_work_call(codex_call("function_call", "update_plan")) is False
    assert is_codex_work_call({"type": "user", "payload": {"type": "function_call"}}) is False


def test_should_recognize_an_assistant_record_by_type_role_or_message_role() -> None:
    assert is_assistant_record({"type": "assistant"}) is True
    assert is_assistant_record({"role": "assistant"}) is True
    assert is_assistant_record({"message": {"role": "assistant"}}) is True
    assert is_assistant_record({"type": "user", "message": {"role": "user"}}) is False


def test_should_parse_only_json_objects() -> None:
    assert parsed_object('{"a": 1}') == {"a": 1}
    assert parsed_object("[1]") is None
    assert parsed_object("not json") is None


def ccd_plan_record(all_plan_input: dict[str, object], record_type: str = "assistant") -> dict[str, object]:
    tool_use = {"type": "tool_use", "id": "p1", "name": "mcp__ccd_turn__update_plan", "input": all_plan_input}
    return {"type": record_type, "timestamp": "2026-01-01T00:00:00.000Z", "message": {"content": [tool_use]}}


def plan_statuses(transcript_path: Path) -> list[tuple[str, str, bool]]:
    all_items = replayed_transcript(str(transcript_path)).items() or []
    return [(each_item.subject, each_item.status, each_item.is_carried) for each_item in all_items]


def test_should_replay_ccd_turn_advance_once_and_skip_request_blob_copies(tmp_path: Path) -> None:
    all_items = [
        {"content": "Read the gate", "status": "in_progress"},
        {"content": "Write the tests", "status": "pending"},
        {"content": "Open the PR", "status": "pending"},
    ]
    transcript_path = write_transcript(
        tmp_path / "ccd.jsonl",
        [
            ccd_plan_record({"items": all_items, "scope": "first_task"}),
            ccd_plan_record({"advance": True}),
            ccd_plan_record({"advance": True}, record_type="api-request-blob"),
        ],
    )
    assert plan_statuses(transcript_path) == [
        ("Read the gate", "completed", False),
        ("Write the tests", "in_progress", False),
        ("Open the PR", "pending", False),
    ]


def test_should_carry_unfinished_items_after_the_replacing_list(tmp_path: Path) -> None:
    first_items = [
        {"content": "Export the OneUI8 APK", "status": "in_progress"},
        {"content": "Submit both APKs", "status": "pending"},
        {"content": "Find the rows", "status": "completed"},
    ]
    transcript_path = write_transcript(
        tmp_path / "ccd.jsonl",
        [
            ccd_plan_record({"items": first_items, "scope": "first_task"}),
            ccd_plan_record({"scope": "continuation", "items": [{"content": "Set rows in Neon", "status": "in_progress"}]}),
        ],
    )
    assert plan_statuses(transcript_path) == [
        ("Set rows in Neon", "in_progress", False),
        ("Export the OneUI8 APK", "in_progress", True),
        ("Submit both APKs", "pending", True),
    ]


def test_should_point_done_and_start_indices_at_the_tools_own_items(tmp_path: Path) -> None:
    transcript_path = write_transcript(
        tmp_path / "ccd.jsonl",
        [
            ccd_plan_record({"items": [{"content": "Alpha", "status": "pending"}], "scope": "first_task"}),
            ccd_plan_record(
                {
                    "items": [{"content": "Beta", "status": "in_progress"}, {"content": "Gamma", "status": "pending"}],
                    "scope": "continuation",
                }
            ),
            ccd_plan_record({"done": [1, 3], "start": 2}),
        ],
    )
    assert plan_statuses(transcript_path) == [
        ("Beta", "completed", False),
        ("Gamma", "in_progress", False),
        ("Alpha", "pending", True),
    ]


def test_should_let_a_later_list_close_a_carried_item_by_subject(tmp_path: Path) -> None:
    transcript_path = write_transcript(
        tmp_path / "ccd.jsonl",
        [
            ccd_plan_record({"items": [{"content": "Alpha", "status": "pending"}], "scope": "first_task"}),
            ccd_plan_record({"items": [{"content": "Beta", "status": "pending"}], "scope": "continuation"}),
            ccd_plan_record(
                {
                    "items": [{"content": "Beta", "status": "completed"}, {"content": "alpha", "status": "completed"}],
                    "scope": "continuation",
                }
            ),
        ],
    )
    assert plan_statuses(transcript_path) == [("Beta", "completed", False), ("alpha", "completed", False)]
