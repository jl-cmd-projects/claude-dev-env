from pathlib import Path

import pytest

from hooks_constants.closing_question_round_gate_constants import (
    FOOTER_GAP_REASON_LEAD,
)
from test_closing_question_round_gate import (
    held_reason,
    reply_record,
    stop_feedback_record,
    tool_call_record,
    typed_prompt_record,
)
from test_closing_question_round_gate_work import (
    FOOTER,
    LEDGER_PULL_REQUEST_SUBJECT,
    LEDGER_SUBJECT,
    LIST_READER_SUBJECT,
    edit_records,
)

CARRIED_REASON_LEAD = "This session's task list dropped work that was still in progress, so the user no longer sees it."
RERUN_SUBJECT = "Run Codex rerun 2 on Sol (ends 11:05 PM ET)"
JUDGE_SUBJECT = "Judge rerun 2 against GitHub"
SUMMARY_SUBJECT = "Write the audit summary"


@pytest.fixture(autouse=True)
def no_task_store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ATTENDED", "1")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / ".claude"))
    monkeypatch.delenv("CLAUDE_CODE_TASK_LIST_ID", raising=False)


def plan_record(all_items: list[tuple[str, str]], scope: str = "continuation") -> dict[str, object]:
    return tool_call_record(
        "mcp__ccd_turn__update_plan",
        {
            "items": [
                {"content": each_subject, "status": each_status}
                for each_subject, each_status in all_items
            ],
            "scope": scope,
        },
        tool_use_id=f"plan-{len(all_items)}-{all_items[0][0]}",
    )


def dropped_rerun_records(all_later_items: list[tuple[str, str]]) -> list[dict[str, object]]:
    return [
        typed_prompt_record(),
        plan_record(
            [(RERUN_SUBJECT, "in_progress"), (JUDGE_SUBJECT, "pending")], scope="first_task"
        ),
        plan_record(all_later_items),
    ]


def test_should_hold_a_list_that_dropped_in_progress_work_and_not_ask_the_footer_for_it(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_records = [
        *dropped_rerun_records([(LIST_READER_SUBJECT, "in_progress")]),
        *edit_records(),
        reply_record(f"The retry flag is in place.\n\n{FOOTER}"),
    ]
    reason = str(held_reason(monkeypatch, capsys, tmp_path, all_records))
    assert reason.startswith(CARRIED_REASON_LEAD)
    assert f"\n- {RERUN_SUBJECT}\n" in reason
    assert "status completed, then send the list again without it" in reason
    assert "When the work is still open, put the item back on the list" in reason
    assert JUDGE_SUBJECT not in reason
    assert FOOTER_GAP_REASON_LEAD not in reason


def test_should_hold_dropped_in_progress_work_when_the_shown_list_has_nothing_in_progress(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_records = [
        *dropped_rerun_records([(SUMMARY_SUBJECT, "pending")]),
        *edit_records(),
        reply_record("Done."),
    ]
    reason = str(held_reason(monkeypatch, capsys, tmp_path, all_records))
    assert reason.startswith(CARRIED_REASON_LEAD)
    assert f"\n- {RERUN_SUBJECT}\n" in reason


def test_should_read_footer_key_words_from_the_shown_list_only(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_records = [
        typed_prompt_record(),
        plan_record([(LEDGER_PULL_REQUEST_SUBJECT, "pending")], scope="first_task"),
        plan_record([(LEDGER_SUBJECT, "in_progress")]),
        *edit_records(),
        reply_record("Done.\n\nIn progress:\n- I am watching the ledger run."),
    ]
    assert held_reason(monkeypatch, capsys, tmp_path, all_records) is None


def test_should_count_the_dropped_work_hold_toward_the_cap_of_two(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    carried_feedback = (
        f"Stop hook feedback:\n{CARRIED_REASON_LEAD}\nDropped from the list while in progress:"
    )
    all_records = [
        *dropped_rerun_records([(LIST_READER_SUBJECT, "in_progress")]),
        *edit_records(),
        reply_record(f"Done.\n\n{FOOTER}"),
        stop_feedback_record(carried_feedback),
        reply_record(f"Done.\n\n{FOOTER}"),
        stop_feedback_record(carried_feedback),
        reply_record(f"Done.\n\n{FOOTER}"),
    ]
    assert held_reason(monkeypatch, capsys, tmp_path, all_records) is None


def test_should_allow_the_footer_once_the_dropped_work_is_listed_completed_then_left_off(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_records = [
        *dropped_rerun_records([(LIST_READER_SUBJECT, "in_progress")]),
        plan_record([(LIST_READER_SUBJECT, "in_progress"), (RERUN_SUBJECT.lower(), "completed")]),
        plan_record([(LIST_READER_SUBJECT, "in_progress")]),
        *edit_records(),
        reply_record(f"Done.\n\n{FOOTER}"),
    ]
    assert held_reason(monkeypatch, capsys, tmp_path, all_records) is None


def test_should_ask_the_footer_for_dropped_work_that_is_listed_again(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_records = [
        *dropped_rerun_records([(LIST_READER_SUBJECT, "in_progress")]),
        plan_record([(LIST_READER_SUBJECT, "in_progress"), (RERUN_SUBJECT, "in_progress")]),
        *edit_records(),
        reply_record(f"Done.\n\n{FOOTER}"),
    ]
    reason = str(held_reason(monkeypatch, capsys, tmp_path, all_records))
    assert reason.startswith(FOOTER_GAP_REASON_LEAD)
    assert f"Left out of the footer:\n- {RERUN_SUBJECT} [" in reason
