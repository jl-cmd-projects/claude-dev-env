import pytest

from closing_question_round_footer import (
    footer_reason,
    left_out_tasks,
    split_footer,
    subject_key_words,
    task_key_words,
)
from hooks_constants.closing_question_round_gate_constants import (
    FOOTER_GAP_REASON_LEAD,
    FOOTER_INSTRUCTION,
    FOOTER_KEY_WORDS_INSTRUCTION,
    FOOTER_MISSING_REASON_LEAD,
)
from open_tasks_transcript import TaskItem

LIST_READER = TaskItem("28", "Fix list reader lint finding", "in_progress")
LEDGER = TaskItem("29", "Watch discount ledger scheduled wake", "in_progress")
LEDGER_PULL_REQUEST = TaskItem("30", "Open ledger PR", "pending")


@pytest.mark.parametrize(
    ("closing_reply", "expected_body", "expected_items"),
    [
        (
            "Done.\n\nIn progress:\n- I am fixing the list reader.\n- I am watching the ledger.",
            "Done.\n",
            ("I am fixing the list reader.", "I am watching the ledger."),
        ),
        ("Done.\n\n**In progress:**\n* I am fixing it.\n", "Done.\n", ("I am fixing it.",)),
        ("In progress:\n- I am fixing\n  the list reader.", "", ("I am fixing the list reader.",)),
        ("In progress:\n- I am fixing it.\n\nDone.", None, None),
        ("Done.\n\nIn progress:", None, None),
        ("Done.\n\nIn progress: the list reader.", None, None),
        ("Done.\n\n```\nIn progress:\n- I am fixing it.\n```", None, None),
        ("- In progress:\n- I am fixing it.", None, None),
    ],
)
def test_split_footer_should_cut_only_a_trailing_heading_and_list(
    closing_reply: str, expected_body: str | None, expected_items: tuple[str, ...] | None
) -> None:
    split_reply = split_footer(closing_reply)
    assert split_reply.footer_items == expected_items
    assert split_reply.body == (closing_reply if expected_body is None else expected_body)


def test_subject_key_words_should_drop_verbs_and_agent_only_words() -> None:
    assert subject_key_words(LIST_READER.subject) == ["list", "reader"]
    assert subject_key_words(LEDGER.subject) == ["discount", "ledger"]
    assert subject_key_words("Fix PR 8801 lint") == []


def test_task_key_words_should_keep_only_words_no_other_open_task_shares() -> None:
    all_open = [LIST_READER, LEDGER, LEDGER_PULL_REQUEST]
    assert task_key_words(LEDGER, all_open) == ["discount"]
    assert task_key_words(LEDGER, [LEDGER]) == ["discount", "ledger"]
    assert task_key_words(LEDGER_PULL_REQUEST, all_open) == ["ledger"]


def test_left_out_tasks_should_match_by_the_first_five_letters() -> None:
    all_open = [LIST_READER, LEDGER, LEDGER_PULL_REQUEST]
    all_in_progress = [LIST_READER, LEDGER]
    named_both = ["I am fixing the list reader.", "I am watching the discounts."]
    assert left_out_tasks(named_both, all_in_progress, all_open) == []
    named_shared_word = ["I am fixing the list reader.", "I am watching the ledger run."]
    assert left_out_tasks(named_shared_word, all_in_progress, all_open) == [LEDGER]
    assert left_out_tasks([], all_in_progress, all_open) == [LIST_READER, LEDGER]
    with_no_key_words = TaskItem("31", "Fix PR 8801", "in_progress")
    assert left_out_tasks([], [with_no_key_words], [with_no_key_words]) == []


def test_footer_reason_should_lead_list_the_tasks_and_end_with_the_guidance() -> None:
    all_open = [LIST_READER, LEDGER, LEDGER_PULL_REQUEST]
    gap_reason = footer_reason(FOOTER_GAP_REASON_LEAD, [LIST_READER, LEDGER], [LEDGER], all_open)
    assert gap_reason.split("\n") == [
        FOOTER_GAP_REASON_LEAD,
        "Left out of the footer:",
        f"- {LEDGER.subject} [discount]",
        "Work in progress, with the words that name each task in brackets:",
        f"- {LIST_READER.subject} [list reader]",
        f"- {LEDGER.subject} [discount]",
        FOOTER_KEY_WORDS_INSTRUCTION,
        FOOTER_INSTRUCTION,
    ]
    background_reason = footer_reason(FOOTER_MISSING_REASON_LEAD, [], [], [])
    assert background_reason.split("\n") == [FOOTER_MISSING_REASON_LEAD, FOOTER_INSTRUCTION]
    assert "brackets" not in background_reason
