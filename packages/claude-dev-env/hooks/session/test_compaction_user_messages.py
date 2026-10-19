"""Tests for compaction_user_messages: which Claude Code and Codex transcript entries count as typed."""

import json
import sys
from pathlib import Path

_SESSION_DIR = Path(__file__).resolve().parent
_HOOKS_ROOT = _SESSION_DIR.parent
for each_sys_path_entry in (str(_SESSION_DIR), str(_HOOKS_ROOT)):
    if each_sys_path_entry not in sys.path:
        sys.path.insert(0, each_sys_path_entry)

import compaction_user_messages as extractor

FIXTURE_DIRECTORY = _SESSION_DIR / "fixtures" / "compaction_user_messages"


def user_line(content: object, **all_extra_fields: object) -> str:
    return json.dumps(
        {
            "type": "user",
            "timestamp": "2026-10-19T10:00:00Z",
            "message": {"role": "user", "content": content},
            **all_extra_fields,
        }
    )


def texts_of(all_lines: list[str]) -> list[str]:
    return [each_message.text for each_message in extractor.typed_user_messages(all_lines)]


def test_should_keep_plain_typed_text_with_position_and_timestamp() -> None:
    all_messages = extractor.typed_user_messages(
        [user_line("fix the login bug"), user_line("  use /srv/app  ")]
    )
    assert [
        (each_message.position, each_message.timestamp, each_message.text)
        for each_message in all_messages
    ] == [
        (1, "2026-10-19T10:00:00Z", "fix the login bug"),
        (2, "2026-10-19T10:00:00Z", "use /srv/app"),
    ]


def test_should_show_a_slash_command_as_name_and_typed_arguments() -> None:
    command_text = (
        "<command-message>deepen</command-message>\n<command-name>/deepen</command-name>\n"
        "<command-args>make it faster</command-args>"
    )
    assert texts_of([user_line(command_text)]) == ["/deepen make it faster"]


def test_should_leave_out_harness_and_agent_entries() -> None:
    all_lines = [
        user_line("skill body", isMeta=True),
        user_line("summary", isCompactSummary=True),
        user_line("helper prompt", isSidechain=True),
        user_line("report", origin={"kind": "peer"}),
        user_line([{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]),
        user_line("<system-reminder>rules</system-reminder>"),
        user_line("<local-command-stdout>Compacted</local-command-stdout>"),
        json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "hi"}]}}),
        "not json",
        user_line("typed", origin={"kind": "human"}),
    ]
    assert texts_of(all_lines) == ["typed"]


def test_should_keep_typed_text_that_opens_with_markup() -> None:
    all_lines = [
        user_line("<Button> does not render"),
        user_line("<task-notification>done</task-notification>"),
    ]
    assert texts_of(all_lines) == ["<Button> does not render"]


def test_should_keep_an_interrupt_and_mark_an_image() -> None:
    all_lines = [
        user_line([{"type": "text", "text": "[Request interrupted by user]"}]),
        user_line([{"type": "image", "source": {}}, {"type": "text", "text": "here."}]),
    ]
    assert texts_of(all_lines) == ["[Request interrupted by user]", "[image] here."]


def test_should_count_a_queued_prompt_once_when_it_also_lands_as_a_user_entry() -> None:
    queued_line = json.dumps(
        {"type": "attachment", "attachment": {"type": "queued_command", "prompt": "check logs"}}
    )
    relay_line = json.dumps(
        {
            "type": "attachment",
            "attachment": {"type": "queued_command", "prompt": "<agent-message>x"},
        }
    )
    assert texts_of([queued_line, user_line("check logs"), relay_line]) == ["check logs"]


def test_should_keep_a_message_typed_again_after_the_assistant_replied() -> None:
    assistant_line = json.dumps({"type": "assistant", "message": {"content": "done"}})
    assert texts_of([user_line("yes"), assistant_line, user_line("yes")]) == ["yes", "yes"]


def test_should_read_a_claude_code_transcript_across_a_compaction() -> None:
    fixture_lines = (FIXTURE_DIRECTORY / "one_compaction.jsonl").read_text().splitlines()
    assert texts_of(fixture_lines) == [
        "Note these facts for later: the deploy path is /srv/alpha/release-42 and the "
        "retry limit is 17. Reply only: noted.",
        "/compact",
    ]


def test_should_converge_when_a_second_compaction_appends_to_the_transcript() -> None:
    first_lines = (FIXTURE_DIRECTORY / "one_compaction.jsonl").read_text().splitlines()
    second_lines = first_lines + [
        user_line("now set the retry limit to 9"),
        json.dumps({"type": "system", "subtype": "compact_boundary"}),
        user_line("summary two", isCompactSummary=True),
        user_line("<command-name>/compact</command-name>"),
    ]
    first_messages = extractor.typed_user_messages(first_lines)
    second_messages = extractor.typed_user_messages(second_lines)
    assert second_messages[: len(first_messages)] == first_messages
    assert [each_message.text for each_message in second_messages[len(first_messages) :]] == [
        "now set the retry limit to 9",
        "/compact",
    ]


def codex_line(payload: dict[str, object]) -> str:
    return json.dumps(
        {"timestamp": "2026-10-19T11:00:00Z", "type": "event_msg", "payload": payload}
    )


def test_should_keep_codex_user_messages_and_leave_out_injected_items() -> None:
    all_lines = [
        json.dumps({"type": "session_meta", "payload": {"cwd": "/w"}}),
        json.dumps(
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "<environment_context>"}],
                },
            }
        ),
        codex_line({"type": "user_message", "message": "port the hook to codex", "kind": "plain"}),
        codex_line({"type": "agent_message", "message": "on it"}),
        codex_line({"type": "user_message", "message": "see this", "images": ["data:image/png"]}),
        codex_line({"type": "user_message", "message": "", "images": ["data:image/png"]}),
    ]
    all_messages = extractor.typed_user_messages(all_lines)
    assert [each_message.text for each_message in all_messages] == [
        "port the hook to codex",
        "see this [image]",
        "[image]",
    ]
    assert all_messages[0].timestamp == "2026-10-19T11:00:00Z"


def test_should_keep_a_codex_message_typed_again_after_the_agent_replied() -> None:
    all_lines = [
        codex_line({"type": "user_message", "message": "go"}),
        codex_line({"type": "user_message", "message": "go"}),
        codex_line({"type": "agent_message", "message": "done"}),
        codex_line({"type": "user_message", "message": "go"}),
    ]
    assert texts_of(all_lines) == ["go", "go"]
