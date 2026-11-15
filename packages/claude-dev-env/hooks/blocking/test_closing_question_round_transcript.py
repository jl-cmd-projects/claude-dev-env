import json
from pathlib import Path

import pytest

from closing_question_round_transcript import (
    assistant_texts,
    before_deadline,
    block_texts,
    closing_reply_texts,
    has_work_call,
    is_within_scan_cap,
    last_typed_prompt_position,
    stretch_start,
    top_level_records,
    transcript_lines,
)
from hooks_constants.closing_question_round_gate_constants import (
    MAXIMUM_SCANNED_BYTES,
    MAXIMUM_SCANNED_TEXT_BYTES,
    WORK_REASON_LEAD,
)

NO_DEADLINE = float("inf")
DEFERRAL_LINE = "I deferred the backoff setting to a later change."


@pytest.fixture(autouse=True)
def interactive_session(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ATTENDED", "1")


def typed_prompt_record(
    prompt_text: str = "Add the retry flag to the export job.",
) -> dict[str, object]:
    return {
        "type": "user",
        "turnOrigin": "human",
        "promptSource": "typed",
        "message": {"role": "user", "content": prompt_text},
    }


def machine_prompt_record(turn_origin: str) -> dict[str, object]:
    return {
        "type": "user",
        "turnOrigin": turn_origin,
        "promptSource": "system",
        "message": {"role": "user", "content": "Add the retry flag."},
    }


def reply_record(reply_text: str) -> dict[str, object]:
    return {
        "type": "assistant",
        "message": {"role": "assistant", "content": [{"type": "text", "text": reply_text}]},
    }


def tool_call_record(tool_name: object, tool_use_id: str | None = None) -> dict[str, object]:
    tool_use = {
        "type": "tool_use",
        "id": tool_use_id or f"id-{tool_name}",
        "name": tool_name,
        "input": {},
    }
    return {"type": "assistant", "message": {"role": "assistant", "content": [tool_use]}}


def tool_result_record(
    tool_name: str, result_text: str, tool_use_id: str | None = None
) -> dict[str, object]:
    tool_result = {
        "type": "tool_result",
        "tool_use_id": tool_use_id or f"id-{tool_name}",
        "content": result_text,
        "is_error": False,
    }
    return {"type": "user", "message": {"role": "user", "content": [tool_result]}}


def json_lines(all_records: list[dict[str, object]]) -> list[str]:
    return [json.dumps(each_record) for each_record in all_records]


def test_should_pass_each_text_through_before_the_deadline_and_raise_after_it() -> None:
    assert list(before_deadline(["one", "two"], NO_DEADLINE)) == ["one", "two"]
    with pytest.raises(TimeoutError):
        list(before_deadline(["one"], 0.0))


def test_should_split_a_readable_transcript_into_lines_and_return_an_empty_list_otherwise(
    tmp_path: Path,
) -> None:
    transcript_path = tmp_path / "s.jsonl"
    transcript_path.write_text('{"a": 1}\n{"b": 2}', encoding="utf-8")
    assert transcript_lines(str(transcript_path), NO_DEADLINE) == ['{"a": 1}', '{"b": 2}']
    assert transcript_lines(str(tmp_path / "missing.jsonl"), NO_DEADLINE) == []
    assert transcript_lines(None, NO_DEADLINE) == []
    with pytest.raises(TimeoutError):
        transcript_lines(str(transcript_path), 0.0)


def test_transcript_lines_reads_a_line_over_sixteen_mebibytes_as_an_empty_line(
    tmp_path: Path,
) -> None:
    transcript_path = tmp_path / "s.jsonl"
    oversized_line = "x" * (MAXIMUM_SCANNED_BYTES + 1)
    transcript_path.write_text(f'{{"a": 1}}\n{oversized_line}\n{{"b": 2}}', encoding="utf-8")
    assert transcript_lines(str(transcript_path), NO_DEADLINE) == ['{"a": 1}', "", '{"b": 2}']


def test_is_within_scan_cap_counts_utf8_bytes() -> None:
    assert is_within_scan_cap("x" * MAXIMUM_SCANNED_TEXT_BYTES)
    assert not is_within_scan_cap("x" * (MAXIMUM_SCANNED_TEXT_BYTES + 1))
    assert not is_within_scan_cap("é" * (MAXIMUM_SCANNED_TEXT_BYTES // 2 + 1))


def test_last_typed_prompt_position_returns_the_last_prompt_with_a_human_turn_origin() -> None:
    all_lines = json_lines(
        [
            machine_prompt_record("sdk"),
            typed_prompt_record(),
            reply_record("One."),
            typed_prompt_record("Rename it."),
            machine_prompt_record("task_notification"),
        ]
    )
    assert last_typed_prompt_position(all_lines, NO_DEADLINE) == 3
    machine_lines = json_lines([machine_prompt_record("sdk")])
    assert last_typed_prompt_position(machine_lines, NO_DEADLINE) is None
    meta_lines = json_lines([{**typed_prompt_record(), "isMeta": True}])
    assert last_typed_prompt_position(meta_lines, NO_DEADLINE) is None
    human_tool_result = {**tool_result_record("Bash", "ok"), "turnOrigin": "human"}
    assert last_typed_prompt_position(json_lines([human_tool_result]), NO_DEADLINE) is None


def test_last_typed_prompt_position_falls_back_to_the_attended_variable_without_a_turn_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    untagged_prompt = {"type": "user", "message": {"role": "user", "content": "Add the flag."}}
    all_lines = json_lines([untagged_prompt, reply_record(DEFERRAL_LINE), untagged_prompt])
    assert last_typed_prompt_position(all_lines, NO_DEADLINE) == 2
    reply_lines = json_lines([reply_record(DEFERRAL_LINE)])
    assert last_typed_prompt_position(reply_lines, NO_DEADLINE) is None
    machine_lines = json_lines([{**untagged_prompt, "turnOrigin": "sdk"}])
    assert last_typed_prompt_position(machine_lines, NO_DEADLINE) is None
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ATTENDED")
    assert last_typed_prompt_position(json_lines([untagged_prompt]), NO_DEADLINE) is None


def test_top_level_records_keeps_assistant_records_and_this_gates_holds() -> None:
    hold_record = {
        "type": "user",
        "isMeta": True,
        "message": {"role": "user", "content": f"Stop hook feedback:\n{WORK_REASON_LEAD}"},
    }
    first_reply = reply_record("One.")
    bash_call = tool_call_record("Bash")
    sidechain_reply = {**reply_record("Three."), "isSidechain": True}
    all_lines = json_lines(
        [
            typed_prompt_record(),
            first_reply,
            tool_result_record("Bash", "ok"),
            bash_call,
            hold_record,
            sidechain_reply,
        ]
    )
    assert top_level_records([*all_lines, "not json"], NO_DEADLINE) == [
        first_reply,
        bash_call,
        hold_record,
    ]


def test_has_work_call_counts_any_tool_call_but_a_question_call() -> None:
    assert has_work_call([tool_call_record("Edit")])
    assert has_work_call([tool_call_record(["AskUserQuestion"])])
    assert not has_work_call([tool_call_record("AskUserQuestion"), reply_record("One.")])
    assert not has_work_call([tool_call_record("mcp__hearthbot__ask_decision")])
    user_tool_use = {"type": "tool_use", "id": "id-user", "name": "Edit", "input": {}}
    user_record = {"type": "user", "message": {"role": "user", "content": [user_tool_use]}}
    assert not has_work_call([user_record])


def test_stretch_start_follows_the_last_call_that_reached_the_user() -> None:
    first_reply = reply_record("One.")
    second_reply = reply_record("Two.")
    sidechain_question = {
        **tool_call_record("AskUserQuestion", tool_use_id="id-side"),
        "isSidechain": True,
    }
    sidechain_answer = {
        **tool_result_record("AskUserQuestion", "ok", tool_use_id="id-side"),
        "isSidechain": True,
    }
    answered_call = tool_call_record("AskUserQuestion", tool_use_id="id-answered")
    answer = tool_result_record("AskUserQuestion", "The user chose A.", tool_use_id="id-answered")
    assert stretch_start(json_lines([first_reply, second_reply]), NO_DEADLINE) == 0
    all_lines = json_lines(
        [first_reply, answered_call, answer, second_reply, sidechain_question, sidechain_answer]
    )
    assert stretch_start(all_lines, NO_DEADLINE) == 2
    decision_call = tool_call_record("mcp__hearthbot__ask_decision", tool_use_id="id-decision")
    decision_answer = tool_result_record("Bash", "chose B", tool_use_id="id-decision")
    decision_lines = json_lines([first_reply, decision_call, decision_answer])
    assert stretch_start(decision_lines, NO_DEADLINE) == 2
    unanswered_call = tool_call_record("AskUserQuestion")
    assert stretch_start(json_lines([first_reply, unanswered_call]), NO_DEADLINE) == 0


def test_block_texts_returns_the_string_text_of_each_text_block() -> None:
    mixed_record = {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "One."},
                {"type": "thinking", "thinking": "Hidden."},
                {"type": "text", "text": 7},
                {"type": "text", "text": "Two."},
            ],
        },
    }
    assert block_texts(mixed_record) == ["One.", "Two."]


def test_assistant_texts_reads_only_assistant_records() -> None:
    all_stretch_records = [
        typed_prompt_record("The prompt is parked."),
        reply_record("One."),
        tool_result_record("Bash", "Two."),
        reply_record("Three."),
    ]
    assert assistant_texts(all_stretch_records) == ["One.", "Three."]


def test_closing_reply_texts_reads_a_closing_reply_the_transcript_does_not_end_with() -> None:
    all_lines = json_lines([typed_prompt_record(), reply_record("Both tests pass.")])
    assert closing_reply_texts(
        {"last_assistant_message": DEFERRAL_LINE}, all_lines, NO_DEADLINE
    ) == [DEFERRAL_LINE]
    assert (
        closing_reply_texts(
            {"last_assistant_message": "  Both tests pass.\n"}, all_lines, NO_DEADLINE
        )
        == []
    )
    assert closing_reply_texts({"last_assistant_message": "  "}, all_lines, NO_DEADLINE) == []
    assert closing_reply_texts({}, all_lines, NO_DEADLINE) == []
