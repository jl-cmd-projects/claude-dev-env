import pytest

from open_tasks_transcript_records import (
    claude_prompt_text,
    codex_prompt_text,
    is_assistant_record,
    is_codex_question_call,
    is_codex_read_call,
    is_codex_work_call,
    is_read_tool_name,
    is_work_tool_name,
    normalized_text,
    parsed_object,
    send_call_file_paths,
    stop_feedback_text,
)


def codex_record(payload: object) -> dict[str, object]:
    return {"type": "response_item", "payload": payload}


def test_should_lowercase_text_and_collapse_each_whitespace_run() -> None:
    assert normalized_text("  Fix\tThe\n\n  Login BUG ") == "fix the login bug"
    assert normalized_text("") == ""


def test_should_return_only_a_json_object_from_text() -> None:
    assert parsed_object('{"plan": [1, 2]}') == {"plan": [1, 2]}
    assert parsed_object('"just a string"') is None
    assert parsed_object('{"truncated": ') is None


@pytest.mark.parametrize(
    ("record", "expected_text"),
    [
        (
            {
                "role": "user",
                "message": {
                    "content": [
                        {"type": "text", "text": "Refactor"},
                        {"type": "text", "text": "the cache"},
                    ]
                },
            },
            "Refactor the cache",
        ),
        ({"message": {"role": "user", "content": "Port the parser"}}, "Port the parser"),
        (
            {
                "type": "user",
                "message": {
                    "content": [
                        {"type": "text", "text": "<system-reminder>r</system-reminder>"},
                        {"type": "image"},
                    ]
                },
            },
            "<system-reminder>r</system-reminder>",
        ),
        ({"type": "user", "isSidechain": True, "message": {"content": "Side task"}}, None),
        ({"type": "user", "isCompactSummary": True, "message": {"content": "Summary"}}, None),
        ({"type": "user", "message": {"content": "   "}}, None),
        ({"type": "user", "message": {"content": "  Stop hook feedback: hold"}}, None),
    ],
)
def test_should_read_prompt_text_from_each_user_record_shape(
    record: dict[str, object], expected_text: str | None
) -> None:
    assert claude_prompt_text(record) == expected_text


def test_should_read_codex_user_text_from_a_string_or_its_text_blocks() -> None:
    assert (
        codex_prompt_text(
            codex_record({"type": "message", "role": "user", "content": "Remove the flag"})
        )
        == "Remove the flag"
    )
    block_message = {
        "type": "message",
        "role": "user",
        "content": ["skip", {"type": "input_text", "text": "Ship"}, {"text": "it"}],
    }
    assert codex_prompt_text(codex_record(block_message)) == "Ship it"
    assert (
        codex_prompt_text(codex_record({"type": "function_call", "role": "user", "content": "x"}))
        is None
    )
    assert (
        codex_prompt_text(
            {"type": "event_msg", "payload": {"type": "message", "role": "user", "content": "x"}}
        )
        is None
    )


def test_should_count_each_codex_call_type_as_work_except_the_plan_and_question_calls() -> None:
    assert (
        is_codex_work_call(codex_record({"type": "custom_tool_call", "name": "apply_patch"}))
        is True
    )
    assert is_codex_work_call(codex_record({"type": "message", "name": "shell"})) is False
    assert (
        is_codex_work_call(codex_record({"type": "function_call", "name": "update_plan"})) is False
    )
    assert is_codex_work_call(codex_record("not a payload")) is False


def test_should_recognize_a_codex_question_card_call() -> None:
    assert (
        is_codex_question_call(
            codex_record({"type": "custom_tool_call", "name": "request_user_input"})
        )
        is True
    )
    assert (
        is_codex_question_call(
            codex_record({"type": "function_call", "name": "request_user_input_async"})
        )
        is True
    )
    assert is_codex_question_call(codex_record({"type": "function_call", "name": "shell"})) is False
    assert (
        is_codex_question_call(codex_record({"type": "message", "name": "request_user_input"}))
        is False
    )
    assert (
        is_codex_question_call(
            {"type": "user", "payload": {"type": "function_call", "name": "request_user_input"}}
        )
        is False
    )


def test_should_treat_lookup_tools_as_non_work_and_other_names_as_work() -> None:
    assert is_work_tool_name("TaskList") is False
    assert is_work_tool_name("TaskGet") is False
    assert is_work_tool_name("ToolSearch") is False
    assert is_work_tool_name("AskUserQuestion") is False
    assert is_work_tool_name("Edit") is True
    assert is_work_tool_name(7) is True


def test_should_find_the_assistant_role_on_the_message_when_the_record_says_user() -> None:
    assert is_assistant_record({"role": "user", "message": {"role": "assistant"}}) is True
    assert is_assistant_record({"message": "assistant"}) is False
    assert is_assistant_record({"type": "response_item", "role": "tool"}) is False


@pytest.mark.parametrize(
    ("tool_name", "expected_is_read"),
    [
        ("PowerShell", True),
        ("mcp__x__v2Read", True),
        ("mcp__get_server__publish", False),
        ("ToolSearch", False),
        ("mcp__drive__list_and_delete", False),
    ],
)
def test_should_judge_a_read_tool_by_the_words_after_the_server_name(tool_name: str, expected_is_read: bool) -> None:
    assert is_read_tool_name(tool_name) is expected_is_read


def test_should_keep_every_sent_path_in_order_and_ignore_a_call_without_files() -> None:
    assert send_call_file_paths("SendUserFile", {"files": ["b.md", "a.md", "b.md"]}) == ["b.md", "a.md", "b.md"]
    assert send_call_file_paths("SendUserFile", {"message": "here"}) == []


def test_should_count_a_codex_call_as_a_read_by_its_type_and_tool_name() -> None:
    assert is_codex_read_call(codex_record({"type": "custom_tool_call", "name": "view_image"})) is True
    assert is_codex_read_call(codex_record({"type": "function_call", "name": "apply_patch"})) is False
    assert is_codex_read_call(codex_record({"type": "message", "name": "shell"})) is False
    assert is_codex_read_call({"type": "event_msg", "payload": {"type": "local_shell_call"}}) is False


@pytest.mark.parametrize("is_meta", [True, False])
def test_should_read_the_text_of_a_stop_hook_feedback_record(is_meta: bool) -> None:
    feedback_text = "Stop hook feedback:\n[command hook 6]: There are uncommitted changes."
    feedback_record = {"type": "user", "isMeta": is_meta, "message": {"role": "user", "content": feedback_text}}
    assert stop_feedback_text(feedback_record) == feedback_text


def test_should_read_no_feedback_from_a_typed_prompt_or_an_assistant_record() -> None:
    assert stop_feedback_text({"type": "user", "message": {"role": "user", "content": "Fix the hook"}}) is None
    assistant_record = {"type": "assistant", "message": {"content": "Stop hook feedback: quoted"}}
    assert stop_feedback_text(assistant_record) is None
