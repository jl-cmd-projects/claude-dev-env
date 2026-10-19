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
