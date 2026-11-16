from pathlib import Path

import pytest

from hooks_constants.closing_question_round_gate_constants import (
    CLOSING_ROUND_REASON_LEAD,
    MAXIMUM_SCANNED_BYTES,
    WORK_REASON_LEAD,
)
from test_closing_question_round_gate import (
    held_reason,
    machine_prompt_record,
    reply_record,
    run_gate,
    stop_feedback_record,
    tool_call_record,
    tool_result_record,
    typed_prompt_record,
    write_records,
)

DECLARATION = "Open items: none."


@pytest.fixture(autouse=True)
def scratch_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
WORK_FEEDBACK_TEXT = f"Stop hook feedback:\n{WORK_REASON_LEAD}\nRead the task list."


def edit_records() -> list[dict[str, object]]:
    return [
        tool_call_record("Edit", {"file_path": "jobs/export.py"}, tool_use_id="id-edit"),
        tool_result_record("Edit", "The file was updated.", tool_use_id="id-edit"),
    ]


def answered_card_records() -> list[dict[str, object]]:
    return [
        tool_call_record("AskUserQuestion", tool_use_id="id-card"),
        tool_result_record("AskUserQuestion", "The user chose Leave it.", tool_use_id="id-card"),
    ]


@pytest.mark.parametrize("closing_reply", ["Done.", "finished", "Open items: none.\n\nDone."])
def test_should_hold_work_that_ends_with_no_card_and_no_declaration(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    closing_reply: str,
) -> None:
    all_records = [typed_prompt_record(), *edit_records(), reply_record(closing_reply)]
    reason = held_reason(monkeypatch, capsys, tmp_path, all_records)
    assert str(reason).startswith(WORK_REASON_LEAD)
    assert '"' + closing_reply + '"' not in str(reason)


def test_should_hold_an_agent_call_that_ends_with_finished(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_records = [
        typed_prompt_record(),
        tool_call_record("Agent", {"prompt": "Check the export job."}),
        tool_result_record("Agent", "The export job is fine."),
        reply_record("finished"),
    ]
    assert str(held_reason(monkeypatch, capsys, tmp_path, all_records)).startswith(WORK_REASON_LEAD)


@pytest.mark.parametrize(
    "closing_reply",
    [
        f"The retry flag is in place.\n\n{DECLARATION}",
        f"The retry flag is in place.\n{DECLARATION}",
        f"The retry flag is in place.\n\n**{DECLARATION}**",
        f"The retry flag is in place.\n\n_{DECLARATION}_\n\n",
    ],
)
def test_should_allow_work_that_ends_with_the_declaration(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    closing_reply: str,
) -> None:
    all_records = [typed_prompt_record(), *edit_records(), reply_record(closing_reply)]
    assert held_reason(monkeypatch, capsys, tmp_path, all_records) is None


@pytest.mark.parametrize(
    "closing_reply",
    [
        f"`{DECLARATION}`",
        f"- {DECLARATION}",
        "Open items: none yet",
        f"{DECLARATION} Both tests pass.",
        f"> {DECLARATION}",
        f"```\n{DECLARATION}\n```",
        f"Done.\n\n    {DECLARATION}",
    ],
)
def test_should_hold_work_whose_last_line_is_no_plain_declaration(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    closing_reply: str,
) -> None:
    all_records = [typed_prompt_record(), *edit_records(), reply_record(closing_reply)]
    assert str(held_reason(monkeypatch, capsys, tmp_path, all_records)).startswith(WORK_REASON_LEAD)


def test_should_hold_a_marker_line_beside_the_declaration(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    closing_reply = f"The retry path is untested.\n\n{DECLARATION}"
    all_records = [typed_prompt_record(), *edit_records(), reply_record(closing_reply)]
    reason = str(held_reason(monkeypatch, capsys, tmp_path, all_records))
    assert reason.startswith(CLOSING_ROUND_REASON_LEAD)
    assert '"The retry path is untested."' in reason


def test_should_read_the_declaration_from_the_payload_closing_reply(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_records = [typed_prompt_record(), *edit_records(), reply_record("The flag is in place.")]
    closing_reply = f"The flag is in place.\n\n{DECLARATION}"
    assert (
        held_reason(
            monkeypatch, capsys, tmp_path, all_records, {"last_assistant_message": closing_reply}
        )
        is None
    )


@pytest.mark.parametrize(
    "closing_reply", ["I made no changes for either answer.", "The backoff setting stays as it is."]
)
def test_should_allow_an_answered_card_followed_only_by_prose(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    closing_reply: str,
) -> None:
    all_records = [
        typed_prompt_record(),
        *edit_records(),
        reply_record("Should the backoff setting change?"),
        *answered_card_records(),
        reply_record(closing_reply),
    ]
    assert held_reason(monkeypatch, capsys, tmp_path, all_records) is None


def test_should_hold_work_after_an_answered_card_until_the_declaration(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_records = [
        typed_prompt_record(),
        reply_record(DECLARATION),
        *answered_card_records(),
        *edit_records(),
        reply_record("The backoff setting is in place."),
    ]
    assert str(held_reason(monkeypatch, capsys, tmp_path, all_records)).startswith(WORK_REASON_LEAD)
    all_records[-1] = reply_record(f"The backoff setting is in place.\n\n{DECLARATION}")
    assert held_reason(monkeypatch, capsys, tmp_path, all_records) is None


def test_should_hold_a_chat_only_turn_after_an_earlier_turn_did_work(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_records = [
        typed_prompt_record(),
        *edit_records(),
        reply_record("The flag is in place."),
        typed_prompt_record("Thanks."),
        reply_record("You're welcome."),
    ]
    assert str(held_reason(monkeypatch, capsys, tmp_path, all_records)).startswith(WORK_REASON_LEAD)


@pytest.mark.parametrize(
    "all_extra_fields",
    [
        {"agent_id": "agent-1"},
        {"conversation_id": "conversation-1"},
        {"background_tasks": [{"id": "task-1"}]},
    ],
)
def test_should_allow_work_in_an_exempt_stop(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    all_extra_fields: dict[str, object],
) -> None:
    transcript_path = write_records(
        tmp_path / "s.jsonl", [typed_prompt_record(), *edit_records(), reply_record("Done.")]
    )
    assert run_gate(monkeypatch, capsys, transcript_path, all_extra_fields) == {}


def test_should_allow_work_in_a_headless_run_or_a_session_no_person_typed_into(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_machine_records = [machine_prompt_record("sdk"), *edit_records(), reply_record("Done.")]
    assert held_reason(monkeypatch, capsys, tmp_path, all_machine_records) is None
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ATTENDED", "0")
    all_typed_records = [typed_prompt_record(), *edit_records(), reply_record("Done.")]
    assert held_reason(monkeypatch, capsys, tmp_path, all_typed_records) is None


def test_should_count_both_reasons_toward_the_cap_of_two(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_records = [
        typed_prompt_record(),
        *edit_records(),
        reply_record("Done."),
        stop_feedback_record(WORK_FEEDBACK_TEXT),
        reply_record("The jitter option is parked."),
    ]
    assert held_reason(monkeypatch, capsys, tmp_path, all_records) is not None
    all_records += [stop_feedback_record(), reply_record("Done again.")]
    assert held_reason(monkeypatch, capsys, tmp_path, all_records) is None


def test_should_reset_the_cap_on_a_new_typed_prompt(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_records = [
        typed_prompt_record(),
        *edit_records(),
        reply_record("Done."),
        stop_feedback_record(WORK_FEEDBACK_TEXT),
        stop_feedback_record(WORK_FEEDBACK_TEXT),
        reply_record("Done again."),
    ]
    assert held_reason(monkeypatch, capsys, tmp_path, all_records) is None
    all_records += [typed_prompt_record("Rename the flag."), reply_record("Renamed.")]
    assert str(held_reason(monkeypatch, capsys, tmp_path, all_records)).startswith(WORK_REASON_LEAD)


def test_should_not_reset_the_cap_on_a_notification_prompt(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_records = [
        typed_prompt_record(),
        *edit_records(),
        reply_record("Done."),
        stop_feedback_record(WORK_FEEDBACK_TEXT),
        machine_prompt_record("task_notification", "<task-notification>done</task-notification>"),
        stop_feedback_record(WORK_FEEDBACK_TEXT),
        reply_record("Done again."),
    ]
    assert held_reason(monkeypatch, capsys, tmp_path, all_records) is None


def test_should_reset_the_cap_on_a_prompt_of_a_host_with_no_turn_origin(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    untagged_prompt = {"type": "user", "message": {"role": "user", "content": "Add the flag."}}
    all_records = [
        untagged_prompt,
        *edit_records(),
        stop_feedback_record(WORK_FEEDBACK_TEXT),
        stop_feedback_record(WORK_FEEDBACK_TEXT),
        reply_record("Done."),
    ]
    assert held_reason(monkeypatch, capsys, tmp_path, all_records) is None
    all_records += [untagged_prompt, reply_record("Done again.")]
    assert str(held_reason(monkeypatch, capsys, tmp_path, all_records)).startswith(WORK_REASON_LEAD)


def test_should_hold_a_marker_in_an_indented_list_continuation(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    closing_reply = "- The flag is in place.\n\n    - The retry path is untested."
    reason = held_reason(
        monkeypatch, capsys, tmp_path, [typed_prompt_record(), reply_record(closing_reply)]
    )
    assert '"- The retry path is untested."' in str(reason)


def test_should_skip_a_transcript_line_and_a_closing_reply_over_sixteen_mebibytes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    oversized_text = "The retry path is untested. " + "x" * MAXIMUM_SCANNED_BYTES
    all_records = [typed_prompt_record(), reply_record(oversized_text)]
    assert held_reason(monkeypatch, capsys, tmp_path, all_records) is None
    all_records = [typed_prompt_record(), reply_record("The flag is in place.")]
    assert (
        held_reason(
            monkeypatch, capsys, tmp_path, all_records, {"last_assistant_message": oversized_text}
        )
        is None
    )
    all_records = [
        typed_prompt_record(),
        reply_record(oversized_text),
        reply_record("The retry path is untested."),
    ]
    assert '"The retry path is untested."' in str(
        held_reason(monkeypatch, capsys, tmp_path, all_records)
    )


def test_should_allow_a_chat_only_turn_after_a_work_turn_that_declared(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_records = [
        typed_prompt_record(),
        *edit_records(),
        reply_record(f"The retry flag is in place.\n\n{DECLARATION}"),
        typed_prompt_record(),
        reply_record("Yes, the flag defaults to three tries."),
    ]
    assert held_reason(monkeypatch, capsys, tmp_path, all_records) is None


def test_should_hold_new_work_after_a_declared_turn(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_records = [
        typed_prompt_record(),
        *edit_records(),
        reply_record(f"The retry flag is in place.\n\n{DECLARATION}"),
        typed_prompt_record(),
        *edit_records(),
        reply_record("The default is now five tries."),
    ]
    assert str(held_reason(monkeypatch, capsys, tmp_path, all_records)).startswith(WORK_REASON_LEAD)


def test_should_keep_a_marker_line_written_before_a_declaration(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_records = [
        typed_prompt_record(),
        *edit_records(),
        reply_record(f"The retry path is untested.\n\n{DECLARATION}"),
        typed_prompt_record(),
        reply_record("Yes."),
    ]
    assert '"The retry path is untested."' in str(
        held_reason(monkeypatch, capsys, tmp_path, all_records)
    )
