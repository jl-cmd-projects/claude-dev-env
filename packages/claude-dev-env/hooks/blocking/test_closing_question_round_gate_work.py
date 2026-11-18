import json
from pathlib import Path

import pytest

import closing_question_round_gate

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


def test_should_hold_later_work_when_a_task_the_last_footer_named_finished(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    write_tasks(
        tmp_path,
        [
            {"id": "28", "subject": LIST_READER_SUBJECT, "status": "in_progress"},
            {"id": "29", "subject": LEDGER_SUBJECT, "status": "completed"},
        ],
    )
    two_line_footer = f"{FOOTER}\n- I am watching the discount ledger so you see its next update."
    all_records = [
        typed_prompt_record(),
        *edit_records(),
        reply_record(f"The retry flag is in place.\n\n{two_line_footer}"),
        *edit_records(),
        reply_record("The ledger update landed."),
    ]
    assert str(held_reason(monkeypatch, capsys, tmp_path, all_records)).startswith(
        FOOTER_MISSING_REASON_LEAD
    )
    footer_end = len(edit_records()) + 2
    assert held_reason(monkeypatch, capsys, tmp_path, all_records[:footer_end], footer_stop_fields(["ledger"])) is None
    assert held_reason(monkeypatch, capsys, tmp_path, all_records, {"background_tasks": ["ledger"]}) is None


def test_should_hold_later_work_when_a_background_job_started_after_the_footer(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    write_tasks(tmp_path, [{"id": "28", "subject": LIST_READER_SUBJECT, "status": "in_progress"}])
    all_records = [
        typed_prompt_record(),
        *edit_records(),
        reply_record(f"The retry flag is in place.\n\n{FOOTER}"),
        *edit_records(),
        reply_record("The ledger job is started."),
    ]
    assert held_reason(monkeypatch, capsys, tmp_path, all_records) is None
    assert str(
        held_reason(monkeypatch, capsys, tmp_path, all_records, {"background_tasks": [{"id": "ledger"}]})
    ).startswith(FOOTER_MISSING_REASON_LEAD)


def notice_record(summary: str) -> dict[str, object]:
    notice_text = f"<task-notification><summary>{summary}</summary></task-notification>"
    return {
        "type": "user",
        "turnOrigin": "task-notification",
        "message": {"role": "user", "content": notice_text},
    }


LEDGER_FOOTER = f"{FOOTER}\n- I am watching the discount ledger so you see its next update."
LEDGER_FOOTER_REPLY = f"The retry flag is in place.\n\n{LEDGER_FOOTER}"


def footer_stop_fields(all_background_tasks: object) -> dict[str, object]:
    return {"background_tasks": all_background_tasks, "last_assistant_message": LEDGER_FOOTER_REPLY}


def _footer_then_work(*all_middle_records: dict[str, object]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    all_footer_records = [
        typed_prompt_record(),
        *edit_records(),
        reply_record(LEDGER_FOOTER_REPLY),
    ]
    return all_footer_records, [*all_footer_records, *all_middle_records, *edit_records(), reply_record("The flag reads well.")]


@pytest.mark.parametrize(
    "middle_record",
    [
        notice_record("Ledger job is still going"),
        tool_call_record("Agent", {"prompt": "Read the ledger log.", "run_in_background": False}, tool_use_id="id-fg"),
    ],
)
def test_should_allow_later_work_while_the_same_background_jobs_run(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    middle_record: dict[str, object],
) -> None:
    write_tasks(tmp_path, [{"id": "28", "subject": LIST_READER_SUBJECT, "status": "in_progress"}])
    all_footer_records, all_records = _footer_then_work(middle_record)
    assert held_reason(monkeypatch, capsys, tmp_path, all_footer_records, footer_stop_fields([{"id": "ledger"}])) is None
    assert held_reason(monkeypatch, capsys, tmp_path, all_records, {"background_tasks": [{"id": "ledger"}]}) is None


def test_should_hold_later_work_when_one_background_job_replaced_another_after_the_footer(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    write_tasks(tmp_path, [{"id": "28", "subject": LIST_READER_SUBJECT, "status": "in_progress"}])
    all_footer_records, all_records = _footer_then_work(notice_record("Ledger job ended"))
    assert held_reason(monkeypatch, capsys, tmp_path, all_footer_records, footer_stop_fields([{"id": "ledger"}])) is None
    assert str(
        held_reason(monkeypatch, capsys, tmp_path, all_records, {"background_tasks": [{"id": "tests"}]})
    ).startswith(FOOTER_MISSING_REASON_LEAD)


def test_should_hold_later_work_when_a_textless_stop_came_after_a_job_took_another_place(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    write_tasks(tmp_path, [{"id": "28", "subject": LIST_READER_SUBJECT, "status": "in_progress"}])
    all_footer_records, all_records = _footer_then_work(notice_record("Ledger job ended"))
    assert held_reason(monkeypatch, capsys, tmp_path, all_footer_records, footer_stop_fields([{"id": "ledger"}])) is None
    all_textless_records = [*all_footer_records, notice_record("Ledger job ended")]
    textless_fields = {"background_tasks": [{"id": "tests"}], "last_assistant_message": ""}
    held_reason(monkeypatch, capsys, tmp_path, all_textless_records, textless_fields)
    assert str(
        held_reason(monkeypatch, capsys, tmp_path, all_records, {"background_tasks": [{"id": "tests"}]})
    ).startswith(FOOTER_MISSING_REASON_LEAD)


def test_should_hold_later_work_when_the_jobs_of_an_older_footer_came_back(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    write_tasks(tmp_path, [{"id": "28", "subject": LIST_READER_SUBJECT, "status": "in_progress"}])
    tests_footer_reply = f"The tests started.\n\n{FOOTER}\n- I am running the automated tests so you know it works."
    all_ledger_records, _ = _footer_then_work()
    all_tests_records = [*all_ledger_records, *edit_records(), reply_record(tests_footer_reply)]
    all_records = [*all_tests_records, *edit_records(), reply_record("The flag reads well.")]
    assert held_reason(monkeypatch, capsys, tmp_path, all_ledger_records, footer_stop_fields([{"id": "ledger"}])) is None
    tests_fields = {"background_tasks": [{"id": "tests"}], "last_assistant_message": tests_footer_reply}
    assert held_reason(monkeypatch, capsys, tmp_path, all_tests_records, tests_fields) is None
    assert str(
        held_reason(monkeypatch, capsys, tmp_path, all_records, {"background_tasks": [{"id": "ledger"}]})
    ).startswith(FOOTER_MISSING_REASON_LEAD)


def test_should_hold_later_work_when_the_same_footer_went_out_with_more_jobs_since(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    write_tasks(tmp_path, [{"id": "28", "subject": LIST_READER_SUBJECT, "status": "in_progress"}])
    all_first_records, _ = _footer_then_work()
    all_second_records = [*all_first_records, *edit_records(), reply_record(LEDGER_FOOTER_REPLY)]
    all_records = [*all_second_records, *edit_records(), reply_record("The flag reads well.")]
    assert held_reason(monkeypatch, capsys, tmp_path, all_first_records, footer_stop_fields([{"id": "ledger"}])) is None
    both_jobs = [{"id": "ledger"}, {"id": "tests"}]
    assert held_reason(monkeypatch, capsys, tmp_path, all_second_records, footer_stop_fields(both_jobs)) is None
    assert str(
        held_reason(monkeypatch, capsys, tmp_path, all_records, {"background_tasks": [{"id": "ledger"}]})
    ).startswith(FOOTER_MISSING_REASON_LEAD)


def test_should_hold_later_work_when_a_footer_task_finished_while_a_job_runs(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_two_tasks = [
        {"id": "28", "subject": LIST_READER_SUBJECT, "status": "in_progress"},
        {"id": "29", "subject": LEDGER_SUBJECT, "status": "in_progress"},
    ]
    write_tasks(tmp_path, all_two_tasks)
    all_footer_records, all_records = _footer_then_work()
    assert held_reason(monkeypatch, capsys, tmp_path, all_footer_records, footer_stop_fields([{"id": "tests"}])) is None
    write_tasks(tmp_path, [all_two_tasks[0], {**all_two_tasks[1], "status": "completed"}])
    assert str(
        held_reason(monkeypatch, capsys, tmp_path, all_records, {"background_tasks": [{"id": "tests"}]})
    ).startswith(FOOTER_MISSING_REASON_LEAD)


def test_should_hold_later_work_when_the_job_a_one_line_footer_named_has_ended(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    write_tasks(tmp_path, [{"id": "28", "subject": LIST_READER_SUBJECT, "status": "in_progress"}])
    footer_reply = f"The retry flag is in place.\n\n{FOOTER}"
    all_footer_records = [typed_prompt_record(), *edit_records(), reply_record(footer_reply)]
    all_records = [*all_footer_records, *edit_records(), reply_record("The flag reads well.")]
    footer_fields = {"background_tasks": [{"id": "ledger"}], "last_assistant_message": footer_reply}
    assert held_reason(monkeypatch, capsys, tmp_path, all_footer_records, footer_fields) is None
    assert str(held_reason(monkeypatch, capsys, tmp_path, all_records)).startswith(FOOTER_MISSING_REASON_LEAD)


def test_should_hold_later_work_when_the_same_footer_went_out_again_with_no_reply_text(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    write_tasks(tmp_path, [{"id": "28", "subject": LIST_READER_SUBJECT, "status": "in_progress"}])
    all_first_records, _ = _footer_then_work()
    all_second_records = [*all_first_records, *edit_records(), reply_record(LEDGER_FOOTER_REPLY)]
    all_records = [*all_second_records, *edit_records(), reply_record("The flag reads well.")]
    assert held_reason(monkeypatch, capsys, tmp_path, all_first_records, footer_stop_fields([{"id": "ledger"}])) is None
    both_jobs = {"background_tasks": [{"id": "ledger"}, {"id": "tests"}]}
    held_reason(monkeypatch, capsys, tmp_path, all_second_records, both_jobs)
    assert str(
        held_reason(monkeypatch, capsys, tmp_path, all_records, {"background_tasks": [{"id": "ledger"}]})
    ).startswith(FOOTER_MISSING_REASON_LEAD)


def test_should_allow_later_work_when_the_footer_stop_ran_before_the_reply_was_written(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    write_tasks(tmp_path, [{"id": "28", "subject": LIST_READER_SUBJECT, "status": "in_progress"}])
    all_footer_records, all_records = _footer_then_work()
    all_unwritten_records = all_footer_records[:-1]
    assert held_reason(
        monkeypatch, capsys, tmp_path, all_unwritten_records, footer_stop_fields([{"id": "ledger"}])
    ) is None
    assert held_reason(monkeypatch, capsys, tmp_path, all_records, {"background_tasks": [{"id": "ledger"}]}) is None


@pytest.mark.parametrize("is_split_with_an_edit", [False, True])
def test_should_count_a_footer_only_when_no_record_of_its_message_called_a_tool(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    is_split_with_an_edit: bool,
) -> None:
    write_tasks(tmp_path, [{"id": "28", "subject": LIST_READER_SUBJECT, "status": "in_progress"}])
    footer_record = reply_record(f"The retry flag is in place.\n\n{FOOTER}")
    footer_record["message"]["id"] = "message-7"
    split_edit_record = tool_call_record("Edit", {"file_path": "jobs/export.py"}, tool_use_id="id-split")
    split_edit_record["message"]["id"] = "message-7" if is_split_with_an_edit else "message-8"
    all_records = [
        typed_prompt_record(),
        *edit_records(),
        footer_record,
        split_edit_record,
        tool_result_record("Edit", "The file was updated.", tool_use_id="id-split"),
        reply_record("The flag reads well."),
    ]
    reason = held_reason(monkeypatch, capsys, tmp_path, all_records)
    if is_split_with_an_edit:
        assert str(reason).startswith(FOOTER_MISSING_REASON_LEAD)
    else:
        assert reason is None


def test_should_read_the_task_list_once_when_a_footer_stop_keeps_its_snapshot(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    write_tasks(tmp_path, [{"id": "28", "subject": LIST_READER_SUBJECT, "status": "in_progress"}])
    all_task_reads: list[object] = []
    original_session_tasks = closing_question_round_gate.session_tasks

    def counted_session_tasks(all_hook_input_fields: dict[str, object]) -> object:
        all_task_reads.append(all_hook_input_fields)
        return original_session_tasks(all_hook_input_fields)

    monkeypatch.setattr(closing_question_round_gate, "session_tasks", counted_session_tasks)
    all_footer_records, _ = _footer_then_work()
    assert held_reason(monkeypatch, capsys, tmp_path, all_footer_records, footer_stop_fields([{"id": "ledger"}])) is None
    assert len(all_task_reads) == 1


def test_should_read_the_footer_snapshot_once_when_later_work_has_no_footer(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    write_tasks(tmp_path, [{"id": "28", "subject": LIST_READER_SUBJECT, "status": "in_progress"}])
    all_footer_records, all_records = _footer_then_work()
    assert held_reason(monkeypatch, capsys, tmp_path, all_footer_records, footer_stop_fields([{"id": "ledger"}])) is None
    all_snapshot_reads: list[object] = []
    original_read = closing_question_round_gate.kept_footer_snapshot

    def counted_read(all_hook_input_fields: dict[str, object]) -> object:
        all_snapshot_reads.append(all_hook_input_fields)
        return original_read(all_hook_input_fields)

    monkeypatch.setattr(closing_question_round_gate, "kept_footer_snapshot", counted_read)
    assert held_reason(monkeypatch, capsys, tmp_path, all_records, {"background_tasks": [{"id": "ledger"}]}) is None
    assert len(all_snapshot_reads) == 1


def test_should_allow_later_work_after_a_footer_that_sums_up_two_jobs_in_one_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    write_tasks(tmp_path, [{"id": "28", "subject": LIST_READER_SUBJECT, "status": "in_progress"}])
    two_jobs = [{"id": "ledger"}, {"id": "tests"}]
    all_footer_records, all_records = _footer_then_work()
    assert held_reason(monkeypatch, capsys, tmp_path, all_footer_records, footer_stop_fields(two_jobs)) is None
    assert held_reason(monkeypatch, capsys, tmp_path, all_records, {"background_tasks": two_jobs}) is None


def test_should_hold_later_work_when_the_footer_shared_its_record_with_a_question_call(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    write_tasks(tmp_path, [{"id": "28", "subject": LIST_READER_SUBJECT, "status": "in_progress"}])
    footer_and_question = reply_record(f"The retry flag is in place.\n\n{FOOTER}")
    question_call = tool_call_record("AskUserQuestion", {"questions": []}, tool_use_id="id-ask")
    footer_and_question["message"]["content"].append(question_call["message"]["content"][0])
    all_records = [
        typed_prompt_record(),
        *edit_records(),
        footer_and_question,
        *edit_records(),
        reply_record("The flag reads well."),
    ]
    assert str(held_reason(monkeypatch, capsys, tmp_path, all_records)).startswith(FOOTER_MISSING_REASON_LEAD)

