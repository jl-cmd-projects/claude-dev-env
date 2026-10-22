import json
from pathlib import Path

from open_tasks_transcript import TaskItem, parsed_object, replayed_transcript, unwrapped_tool_call


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


def test_should_replay_cursor_dynamic_todo_writes_and_the_last_reply(tmp_path: Path) -> None:
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
    assert replay.last_assistant_text == "Done."


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
