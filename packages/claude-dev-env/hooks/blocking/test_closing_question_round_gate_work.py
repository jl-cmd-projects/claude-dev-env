import json
from pathlib import Path

import pytest

from hooks_constants.closing_question_round_gate_constants import (
    CLOSING_ROUND_REASON_LEAD,
    FOOTER_GAP_REASON_LEAD,
    FOOTER_MISSING_REASON_LEAD,
    IN_PROGRESS_TASKS_REASON_LEAD,
    MAXIMUM_SCANNED_BYTES,
)
from test_closing_question_round_gate import (
    SESSION_ID,
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
LIST_READER_SUBJECT = "Fix list reader lint finding"
LEDGER_SUBJECT = "Watch discount ledger scheduled wake"
LEDGER_PULL_REQUEST_SUBJECT = "Open ledger PR"
LIST_READER_ITEM = "- I am fixing the list reader in pull request 8801. I am waiting for the last tests."
FOOTER = f"In progress:\n{LIST_READER_ITEM}"
FOOTER_FEEDBACK_TEXT = f"Stop hook feedback:\n{FOOTER_MISSING_REASON_LEAD}\nWork in progress:"


def write_tasks(home_path: Path, all_task_entries: list[dict[str, str]]) -> None:
    task_directory = home_path / ".claude" / "tasks" / SESSION_ID
    task_directory.mkdir(parents=True, exist_ok=True)
    for each_entry in all_task_entries:
        (task_directory / f"{each_entry['id']}.json").write_text(
            json.dumps(each_entry), encoding="utf-8"
        )


@pytest.fixture(autouse=True)
def task_in_progress(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / ".claude"))
    monkeypatch.delenv("CLAUDE_CODE_TASK_LIST_ID", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ATTENDED", "1")
    write_tasks(tmp_path, [{"id": "28", "subject": LIST_READER_SUBJECT, "status": "in_progress"}])


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


@pytest.mark.parametrize("closing_reply", ["Done.", "finished", f"{FOOTER}\n\nDone."])
def test_should_hold_work_with_a_task_in_progress_and_no_footer(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    closing_reply: str,
) -> None:
    all_records = [typed_prompt_record(), *edit_records(), reply_record(closing_reply)]
    reason = str(held_reason(monkeypatch, capsys, tmp_path, all_records))
    assert reason.startswith(FOOTER_MISSING_REASON_LEAD)
    assert f"- {LIST_READER_SUBJECT} [list reader]" in reason


def test_should_allow_work_with_nothing_in_progress_and_no_closing_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    write_tasks(tmp_path, [{"id": "28", "subject": LIST_READER_SUBJECT, "status": "completed"}])
    all_records = [typed_prompt_record(), *edit_records(), reply_record("Done.")]
    assert held_reason(monkeypatch, capsys, tmp_path, all_records) is None


def test_should_hold_an_agent_call_that_ends_with_finished(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_records = [
        typed_prompt_record(),
        tool_call_record("Agent", {"prompt": "Check the export job."}),
        tool_result_record("Agent", "The export job is fine."),
        reply_record("finished"),
    ]
    assert str(held_reason(monkeypatch, capsys, tmp_path, all_records)).startswith(
        FOOTER_MISSING_REASON_LEAD
    )


@pytest.mark.parametrize(
    "closing_reply",
    [
        f"The retry flag is in place.\n\n{FOOTER}",
        f"The retry flag is in place.\n{FOOTER}\n\n",
        f"The retry flag is in place.\n\n**In progress:**\n{LIST_READER_ITEM}",
        f"The retry flag is in place.\n\nIn progress:\n{LIST_READER_ITEM[:40]}\n  {LIST_READER_ITEM[40:]}",
    ],
)
def test_should_allow_work_that_ends_with_a_footer_naming_the_task(
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
        f"`{FOOTER}`",
        f"- {FOOTER}",
        "In progress:",
        f"{FOOTER}\nBoth tests pass.",
        f"```\n{FOOTER}\n```",
        f"In progress: {LIST_READER_ITEM}",
    ],
)
def test_should_hold_work_whose_reply_ends_with_no_footer(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    closing_reply: str,
) -> None:
    all_records = [typed_prompt_record(), *edit_records(), reply_record(closing_reply)]
    assert str(held_reason(monkeypatch, capsys, tmp_path, all_records)).startswith(
        FOOTER_MISSING_REASON_LEAD
    )


def test_should_hold_the_old_declaration_beside_a_task_in_progress(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_records = [typed_prompt_record(), reply_record(f"Nothing to add.\n\n{DECLARATION}")]
    reason = str(held_reason(monkeypatch, capsys, tmp_path, all_records))
    assert reason.startswith(IN_PROGRESS_TASKS_REASON_LEAD)
    assert "#28" not in reason


def test_should_hold_a_footer_that_leaves_out_a_task_in_progress(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    write_tasks(
        tmp_path,
        [
            {"id": "29", "subject": LEDGER_SUBJECT, "status": "in_progress"},
            {"id": "30", "subject": LEDGER_PULL_REQUEST_SUBJECT, "status": "pending"},
        ],
    )
    closing_reply = f"Done.\n\n{FOOTER}\n- I am also getting the ledger pull request ready."
    all_records = [typed_prompt_record(), *edit_records(), reply_record(closing_reply)]
    reason = str(held_reason(monkeypatch, capsys, tmp_path, all_records))
    assert reason.startswith(FOOTER_GAP_REASON_LEAD)
    assert f"Left out of the footer:\n- {LEDGER_SUBJECT} [discount]\n" in reason
    assert f"- {LIST_READER_SUBJECT} [list reader]" in reason


def test_should_check_a_footer_in_a_chat_only_turn(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    write_tasks(tmp_path, [{"id": "29", "subject": LEDGER_SUBJECT, "status": "in_progress"}])
    all_records = [typed_prompt_record(), reply_record(f"It waits for tests.\n\n{FOOTER}")]
    assert str(held_reason(monkeypatch, capsys, tmp_path, all_records)).startswith(
        FOOTER_GAP_REASON_LEAD
    )


def test_should_allow_a_chat_only_turn_with_no_footer(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_records = [typed_prompt_record(), reply_record("The fix waits for its last tests.")]
    assert held_reason(monkeypatch, capsys, tmp_path, all_records) is None


def test_should_hold_a_marker_line_above_the_footer_and_read_none_inside_it(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    closing_reply = f"The retry path is untested.\n\n{FOOTER}"
    all_records = [typed_prompt_record(), *edit_records(), reply_record(closing_reply)]
    reason = str(held_reason(monkeypatch, capsys, tmp_path, all_records))
    assert reason.startswith(CLOSING_ROUND_REASON_LEAD)
    assert '"The retry path is untested."' in reason
    all_records[-1] = reply_record(f"Done.\n\n{FOOTER} The docs change is blocked and pending.")
    assert held_reason(monkeypatch, capsys, tmp_path, all_records) is None


def test_should_read_the_footer_from_the_payload_closing_reply(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_records = [typed_prompt_record(), *edit_records(), reply_record("The flag is in place.")]
    closing_reply = f"The flag is in place.\n\n{FOOTER}"
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


def test_should_hold_work_after_an_answered_card_until_the_footer(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_records = [
        typed_prompt_record(),
        reply_record(FOOTER),
        *answered_card_records(),
        *edit_records(),
        reply_record("The backoff setting is in place."),
    ]
    assert str(held_reason(monkeypatch, capsys, tmp_path, all_records)).startswith(
        FOOTER_MISSING_REASON_LEAD
    )
    all_records[-1] = reply_record(f"The backoff setting is in place.\n\n{FOOTER}")
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
    assert str(held_reason(monkeypatch, capsys, tmp_path, all_records)).startswith(
        FOOTER_MISSING_REASON_LEAD
    )


@pytest.mark.parametrize(
    "all_extra_fields", [{"agent_id": "agent-1"}, {"conversation_id": "conversation-1"}]
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


def test_should_hold_work_while_background_work_runs_until_the_footer(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    write_tasks(tmp_path, [{"id": "28", "subject": LIST_READER_SUBJECT, "status": "completed"}])
    background_fields = {"background_tasks": [{"id": "task-1"}]}
    all_records = [typed_prompt_record(), *edit_records(), reply_record("Done.")]
    assert str(
        held_reason(monkeypatch, capsys, tmp_path, all_records, background_fields)
    ).startswith(FOOTER_MISSING_REASON_LEAD)
    all_records[-1] = reply_record("Done.\n\nIn progress:\n- I am waiting for the last tests.")
    assert held_reason(monkeypatch, capsys, tmp_path, all_records, background_fields) is None


def test_should_skip_the_open_item_round_while_background_work_runs(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    background_fields = {"background_tasks": [{"id": "task-1"}]}
    all_records = [typed_prompt_record(), reply_record(f"The jitter option is parked.\n\n{FOOTER}")]
    assert held_reason(monkeypatch, capsys, tmp_path, all_records, background_fields) is None


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
        stop_feedback_record(FOOTER_FEEDBACK_TEXT),
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
        stop_feedback_record(FOOTER_FEEDBACK_TEXT),
        stop_feedback_record(FOOTER_FEEDBACK_TEXT),
        reply_record("Done again."),
    ]
    assert held_reason(monkeypatch, capsys, tmp_path, all_records) is None
    all_records += [typed_prompt_record("Rename the flag."), reply_record("Renamed.")]
    assert str(held_reason(monkeypatch, capsys, tmp_path, all_records)).startswith(
        FOOTER_MISSING_REASON_LEAD
    )


def test_should_not_reset_the_cap_on_a_notification_prompt(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_records = [
        typed_prompt_record(),
        *edit_records(),
        reply_record("Done."),
        stop_feedback_record(FOOTER_FEEDBACK_TEXT),
        machine_prompt_record("task_notification", "<task-notification>done</task-notification>"),
        stop_feedback_record(FOOTER_FEEDBACK_TEXT),
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
        stop_feedback_record(FOOTER_FEEDBACK_TEXT),
        stop_feedback_record(FOOTER_FEEDBACK_TEXT),
        reply_record("Done."),
    ]
    assert held_reason(monkeypatch, capsys, tmp_path, all_records) is None
    all_records += [untagged_prompt, reply_record("Done again.")]
    assert str(held_reason(monkeypatch, capsys, tmp_path, all_records)).startswith(
        FOOTER_MISSING_REASON_LEAD
    )


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


def test_should_allow_a_chat_only_turn_after_a_work_turn_that_ended_with_the_footer(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_records = [
        typed_prompt_record(),
        *edit_records(),
        reply_record(f"The retry flag is in place.\n\n{FOOTER}"),
        typed_prompt_record(),
        reply_record("Yes, the flag defaults to three tries."),
    ]
    assert held_reason(monkeypatch, capsys, tmp_path, all_records) is None


def test_should_hold_new_work_after_a_turn_that_ended_with_the_footer(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_records = [
        typed_prompt_record(),
        *edit_records(),
        reply_record(f"The retry flag is in place.\n\n{FOOTER}"),
        typed_prompt_record(),
        *edit_records(),
        reply_record("The default is now five tries."),
    ]
    assert str(held_reason(monkeypatch, capsys, tmp_path, all_records)).startswith(
        FOOTER_MISSING_REASON_LEAD
    )


def test_should_keep_a_marker_line_written_before_a_footer(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_records = [
        typed_prompt_record(),
        *edit_records(),
        reply_record(f"The retry path is untested.\n\n{FOOTER}"),
        typed_prompt_record(),
        reply_record("Yes."),
    ]
    assert '"The retry path is untested."' in str(
        held_reason(monkeypatch, capsys, tmp_path, all_records)
    )


def test_should_read_no_marker_inside_a_footer_of_an_earlier_turn(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    blocked_footer = "In progress:\n- The list reader fix is blocked on the last tests."
    all_records = [
        typed_prompt_record(),
        *edit_records(),
        reply_record(f"The retry flag is in place.\n\n{blocked_footer}"),
        typed_prompt_record(),
        reply_record("You are welcome."),
    ]
    assert held_reason(monkeypatch, capsys, tmp_path, all_records) is None


@pytest.mark.parametrize(
    "question_item",
    [
        "- I am fixing the list reader. Should I also raise the timeout?",
        "- I am fixing the list reader. I need your input on the timeout.",
        "- I am fixing the list reader. I deferred the backoff setting to a later change.",
    ],
)
def test_should_hold_a_question_inside_the_footer(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    question_item: str,
) -> None:
    all_records = [
        typed_prompt_record(),
        *edit_records(),
        reply_record(f"Done.\n\nIn progress:\n{question_item}"),
    ]
    reason = str(held_reason(monkeypatch, capsys, tmp_path, all_records))
    assert reason.startswith(CLOSING_ROUND_REASON_LEAD)
    assert question_item.removeprefix("- ") in reason


@pytest.mark.parametrize("has_notification", [False, True])
def test_should_allow_later_work_when_a_footer_since_the_typed_prompt_names_every_task(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    has_notification: bool,
) -> None:
    all_notification_records = (
        [machine_prompt_record("task-notification", "<task-notification>The worker is waiting.</task-notification>")]
        if has_notification
        else []
    )
    all_records = [
        typed_prompt_record(),
        *edit_records(),
        reply_record(f"The retry flag is in place.\n\n{FOOTER}"),
        *all_notification_records,
        *edit_records(),
        reply_record("The task list now shows the retry flag as done."),
    ]
    assert held_reason(monkeypatch, capsys, tmp_path, all_records) is None


def test_should_hold_later_work_when_a_task_started_after_the_last_footer(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    write_tasks(
        tmp_path,
        [
            {"id": "28", "subject": LIST_READER_SUBJECT, "status": "in_progress"},
            {"id": "29", "subject": LEDGER_SUBJECT, "status": "in_progress"},
        ],
    )
    all_records = [
        typed_prompt_record(),
        *edit_records(),
        reply_record(f"The retry flag is in place.\n\n{FOOTER}"),
        *edit_records(),
        reply_record("I started on the ledger."),
    ]
    reason = str(held_reason(monkeypatch, capsys, tmp_path, all_records))
    assert reason.startswith(FOOTER_MISSING_REASON_LEAD)
    assert f"- {LEDGER_SUBJECT} [discount ledger]" in reason
