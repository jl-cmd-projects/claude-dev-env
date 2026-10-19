"""Tests for compaction_user_messages: which transcript entries count as typed, and the file it writes."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_SESSION_DIR = Path(__file__).resolve().parent
_HOOKS_ROOT = _SESSION_DIR.parent
for each_sys_path_entry in (str(_SESSION_DIR), str(_HOOKS_ROOT)):
    if each_sys_path_entry not in sys.path:
        sys.path.insert(0, each_sys_path_entry)

import compaction_user_messages as extractor
from hooks_constants.compaction_user_messages_constants import (
    MAXIMUM_EXTRACT_CHARACTERS,
    MAXIMUM_MESSAGE_CHARACTERS,
    MESSAGES_HEADING,
)

EXTRACTOR_PATH = _SESSION_DIR / "compaction_user_messages.py"
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


def message(position: int, text: str) -> extractor.TypedMessage:
    return extractor.TypedMessage(position=position, timestamp="t", text=text)


def test_bounded_messages_should_keep_everything_that_fits() -> None:
    all_messages = [message(1, "a"), message(2, "b"), message(3, "c")]
    assert extractor.bounded_messages(all_messages) == all_messages


def test_bounded_messages_should_keep_the_first_and_the_newest_when_over_budget() -> None:
    long_text = "x" * (MAXIMUM_MESSAGE_CHARACTERS - 100)
    message_count = 2 * MAXIMUM_EXTRACT_CHARACTERS // MAXIMUM_MESSAGE_CHARACTERS
    all_messages = [message(each, long_text) for each in range(1, message_count + 1)]
    all_kept = extractor.bounded_messages(all_messages)
    kept_positions = [each.position for each in all_kept]
    assert kept_positions[0] == 1
    assert kept_positions[-1] == message_count
    assert kept_positions[1:] == list(range(kept_positions[1], message_count + 1))
    assert len(extractor.rendered_extract(all_messages)) <= MAXIMUM_EXTRACT_CHARACTERS + 200


def test_bounded_messages_should_return_nothing_for_no_messages() -> None:
    assert extractor.bounded_messages([]) == []


def test_rendered_extract_should_hold_only_the_numbered_messages() -> None:
    rendered = extractor.rendered_extract([message(1, "fix login"), message(2, "use /srv")])
    assert rendered.startswith(MESSAGES_HEADING)
    assert "caveman" not in rendered
    assert "## 1 | t\nfix login\n" in rendered
    assert "## 2 | t\nuse /srv\n" in rendered


def test_rendered_extract_should_cut_a_long_message_and_say_how_much() -> None:
    rendered = extractor.rendered_extract([message(1, "y" * (MAXIMUM_MESSAGE_CHARACTERS + 25))])
    assert "[25 more characters left out]" in rendered


def test_rendered_extract_should_name_how_many_messages_were_left_out() -> None:
    long_text = "x" * (MAXIMUM_MESSAGE_CHARACTERS - 100)
    message_count = 2 * MAXIMUM_EXTRACT_CHARACTERS // MAXIMUM_MESSAGE_CHARACTERS
    all_messages = [message(each, long_text) for each in range(1, message_count + 1)]
    left_out_count = message_count - len(extractor.bounded_messages(all_messages))
    assert left_out_count > 0
    assert f"[{left_out_count} earlier messages left out" in extractor.rendered_extract(
        all_messages
    )


def test_rendered_extract_should_say_when_there_are_no_messages() -> None:
    assert "No typed user messages" in extractor.rendered_extract([])


def test_output_path_for_should_name_the_file_after_the_session_under_the_claude_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    output_path = extractor.output_path_for(Path("/p/abc-123.jsonl"))
    assert output_path == tmp_path / ".claude" / "compaction-recall" / "abc-123.md"


def test_main_should_print_only_the_path_of_the_file_it_writes(tmp_path: Path) -> None:
    transcript_path = tmp_path / "session-xyz.jsonl"
    transcript_path.write_text(user_line("ship the deploy fix") + "\n", encoding="utf-8")
    home_directory = tmp_path / "home"
    completed = subprocess.run(
        [sys.executable, str(EXTRACTOR_PATH), str(transcript_path)],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "HOME": str(home_directory), "USERPROFILE": str(home_directory)},
    )
    printed_path = Path(completed.stdout.strip())
    assert printed_path == home_directory / ".claude" / "compaction-recall" / "session-xyz.md"
    assert "ship the deploy fix" not in completed.stdout
    assert "## 1 | 2026-10-19T10:00:00Z\nship the deploy fix" in printed_path.read_text()


def test_main_should_exit_with_usage_when_the_transcript_is_missing(tmp_path: Path) -> None:
    for all_arguments in ([], [str(tmp_path / "absent.jsonl")]):
        completed = subprocess.run(
            [sys.executable, str(EXTRACTOR_PATH), *all_arguments],
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 2
        assert completed.stdout == ""
