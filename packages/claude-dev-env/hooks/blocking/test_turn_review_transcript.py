import json
import tempfile
from pathlib import Path

import pytest

from turn_review_transcript import _ReversedTranscript, _reply_text, _typed_user_messages


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home_directory = tmp_path / "home"
    home_directory.mkdir()
    state_directory = tmp_path / "state"
    state_directory.mkdir()
    monkeypatch.setenv("HOME", str(home_directory))
    monkeypatch.setenv("USERPROFILE", str(home_directory))
    monkeypatch.setattr(tempfile, "tempdir", str(state_directory))
    return home_directory


def assistant_entry(message_id: str, text: str) -> dict[str, object]:
    return {
        "type": "assistant",
        "message": {"id": message_id, "content": [{"type": "text", "text": text}]},
    }


def typed_entry(text: str, **all_extra_fields: object) -> dict[str, object]:
    return {
        "type": "user",
        "origin": {"kind": "human"},
        "message": {"content": text},
        **all_extra_fields,
    }


def tool_result_entry() -> dict[str, object]:
    return {
        "type": "user",
        "toolUseResult": {"stdout": "ok"},
        "message": {"content": [{"type": "tool_result", "content": "ok"}]},
    }


def stop_input(
    tmp_path: Path, all_entries: list[dict[str, object]], **all_extra_fields: object
) -> dict:
    transcript_path = tmp_path / "session.jsonl"
    transcript_path.write_text(
        "\n".join(json.dumps(each_entry) for each_entry in all_entries) + "\n"
    )
    return {"transcript_path": str(transcript_path), **all_extra_fields}


def test_should_take_the_reply_field_even_when_it_is_empty(tmp_path: Path) -> None:
    hook_input = stop_input(
        tmp_path, [assistant_entry("m1", "Dismiss TR-1: an older reply")], last_assistant_message=""
    )
    assert _reply_text(hook_input, _ReversedTranscript(hook_input)) == ""


def test_should_join_the_entries_of_the_last_assistant_message_oldest_first(tmp_path: Path) -> None:
    hook_input = stop_input(
        tmp_path,
        [
            assistant_entry("m1", "earlier reply"),
            typed_entry("next question"),
            assistant_entry("m2", "first part"),
            assistant_entry("m2", "second part"),
            tool_result_entry(),
        ],
    )
    assert _reply_text(hook_input, _ReversedTranscript(hook_input)) == "first part\nsecond part"


def test_should_still_see_every_entry_after_the_reply_read_part_of_the_transcript(
    tmp_path: Path,
) -> None:
    hook_input = stop_input(
        tmp_path, [typed_entry("first ask"), assistant_entry("m1", "the reply")]
    )
    transcript = _ReversedTranscript(hook_input)
    assert _reply_text(hook_input, transcript) == "the reply"
    assert _typed_user_messages(transcript) == ["first ask"]
    assert len(list(transcript)) == 2


def test_should_keep_the_last_five_typed_messages_oldest_first_and_cut_each(tmp_path: Path) -> None:
    hook_input = stop_input(
        tmp_path,
        [
            typed_entry("first"),
            typed_entry("second"),
            typed_entry("x" * 2500),
            typed_entry("<system-reminder>injected</system-reminder>"),
            typed_entry("meta words", isMeta=True),
            typed_entry("third"),
            {"type": "user", "origin": {"kind": "peer"}, "message": {"content": "peer words"}},
            typed_entry("fourth"),
            assistant_entry("m1", "a reply"),
            typed_entry("fifth"),
        ],
    )
    assert _typed_user_messages(_ReversedTranscript(hook_input)) == [
        "second",
        "x" * 2000,
        "third",
        "fourth",
        "fifth",
    ]


def test_should_log_a_line_that_nests_too_deep_and_read_the_lines_before_it(
    tmp_path: Path, isolated_home: Path
) -> None:
    hook_input = stop_input(tmp_path, [typed_entry("the ask")])
    with Path(hook_input["transcript_path"]).open("a") as transcript_file:
        transcript_file.write("[" * 100_000 + "]" * 100_000 + "\n")
    assert _typed_user_messages(_ReversedTranscript(hook_input)) == ["the ask"]
    log_text = (isolated_home / ".claude" / "logs" / "turn-review.log").read_text()
    assert (
        log_text.count("[turn_review_gate] a transcript line could not be read: it nests too deep")
        == 1
    )
