import json
from pathlib import Path

import pytest

from closing_question_round_transcript import (
    assistant_texts,
    block_texts,
    closing_reply_texts,
    last_written_reply,
    payload_closing_texts,
    has_work_call,
    last_typed_prompt_position,
    stretch_start,
    top_level_records,
)
from hooks_constants.closing_question_round_gate_constants import (
    FOOTER_MISSING_REASON_LEAD,
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
        "message": {"role": "user", "content": f"Stop hook feedback:\n{FOOTER_MISSING_REASON_LEAD}"},
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


def test_last_written_reply_returns_the_reply_only_while_no_prompt_or_work_follows_it() -> None:
    all_lines = json_lines([typed_prompt_record(), reply_record("Both tests pass.")])
    assert last_written_reply(all_lines, NO_DEADLINE) == "Both tests pass."
    assert last_written_reply([*all_lines, *json_lines([typed_prompt_record("Run it again.")])], NO_DEADLINE) is None
    edit_call = {"type": "tool_use", "id": "id-edit", "name": "Edit", "input": {}}
    edit_record = {"type": "assistant", "message": {"role": "assistant", "content": [edit_call]}}
    assert last_written_reply([*all_lines, *json_lines([edit_record])], NO_DEADLINE) is None
    thinking_block = {"type": "thinking", "thinking": "Checking the ledger."}
    thinking_record = {"type": "assistant", "message": {"role": "assistant", "content": [thinking_block]}}
    assert last_written_reply([*all_lines, *json_lines([thinking_record])], NO_DEADLINE) == "Both tests pass."


def test_payload_closing_texts_leaves_out_a_reply_the_transcript_already_ends_with() -> None:
    reply_fields = {"last_assistant_message": "Both tests pass."}
    assert payload_closing_texts(reply_fields, "Done.") == ["Both tests pass."]
    assert payload_closing_texts(reply_fields, " Both tests pass.\n") == []
    assert payload_closing_texts(reply_fields, None) == ["Both tests pass."]
    assert payload_closing_texts({"last_assistant_message": " "}, None) == []


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
    all_later_lines = [*all_lines, *json_lines([typed_prompt_record("Run it again.")])]
    assert closing_reply_texts(
        {"last_assistant_message": "Both tests pass."}, all_later_lines, NO_DEADLINE
    ) == ["Both tests pass."]


def test_closing_reply_texts_sets_aside_the_question_calls_that_share_the_last_record() -> None:
    question_line = "Which cache size should I use?"
    question_call = {"type": "tool_use", "id": "id-card", "name": "AskUserQuestion", "input": {}}
    edit_call = {"type": "tool_use", "id": "id-edit", "name": "Edit", "input": {}}
    for all_blocks, all_expected_texts in [
        ([{"type": "text", "text": question_line}, question_call], []),
        ([{"type": "text", "text": question_line}, edit_call, question_call], [question_line]),
    ]:
        card_record = {"type": "assistant", "message": {"role": "assistant", "content": all_blocks}}
        all_lines = json_lines(
            [
                typed_prompt_record(),
                card_record,
                tool_result_record("AskUserQuestion", "The user chose 64.", tool_use_id="id-card"),
            ]
        )
        assert (
            closing_reply_texts({"last_assistant_message": question_line}, all_lines, NO_DEADLINE)
            == all_expected_texts
        )
