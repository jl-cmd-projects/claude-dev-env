import time

import pytest

from closing_question_round_footer import (
    footer_reason,
    is_footer_ask,
    left_out_tasks,
    list_check_text,
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


def test_should_cut_only_a_status_footer_from_the_list_check_text() -> None:
    status_reply = "Done.\n\nIn progress:\n- I am shipping pull request 8590. Its tests are pending."
    question_reply = (
        "Done.\n\nIn progress:\n- Should I delete the backup?\n- Should I merge 8590?\n- Should I close 8693?"
    )
    assert list_check_text(status_reply).strip() == "Done."
    assert list_check_text(question_reply) == question_reply
    assert list_check_text("Done.") == "Done."


def test_should_keep_a_footer_of_asks_for_the_user_in_the_list_check_text() -> None:
    ask_reply = "Done.\n\nIn progress:\n- Approve the release.\n- Pick a price.\n- Confirm the date."
    mixed_reply = "Done.\n\nIn progress:\n- I am shipping 8590.\n- Pick a price."
    assert list_check_text(ask_reply) == ask_reply
    assert list_check_text(mixed_reply) == "Done.\n\nIn progress:\n- Pick a price."
    assert list_check_text("Done.\n\nIn progress:\n- I\u2019m shipping 8590.").strip() == "Done."


def test_should_keep_the_heading_and_ask_lines_as_the_reply_wrote_them_in_the_list_check_text() -> None:
    bold_reply = (
        "Done.\n\n**in progress:**\n- I am shipping 8590.\n* Pick a price\n  for the second plan."
    )
    kept_text = list_check_text(bold_reply)
    assert kept_text == "Done.\n\n**in progress:**\n* Pick a price\n  for the second plan."
    assert all(each_line in bold_reply for each_line in kept_text.splitlines())


def test_should_read_a_long_footer_item_in_one_pass() -> None:
    long_item = "I am waiting " + "for the want of a need " * 2000
    started_at = time.process_time()
    assert not is_footer_ask(long_item)
    assert time.process_time() - started_at < 0.2


def test_should_read_the_whole_reply_when_the_line_above_the_footer_asks_to_pick() -> None:
    choice_reply = "Pick which option I should ship.\n\nIn progress:\n- I can ship the export first."
    assert list_check_text(choice_reply) == choice_reply
    asked_reply = "Which one ships first?\n\nIn progress:\n- I am shipping 8590."
    assert list_check_text(asked_reply) == asked_reply
    status_reply = "Done.\n\nIn progress:\n- I am shipping 8590."
    assert list_check_text(status_reply) == "Done.\n"
    decision_reply = "Pending your decision:\n\nIn progress:\n- I can ship the export first."
    assert list_check_text(decision_reply) == decision_reply
    label_reply = "Shipped so far:\n\nIn progress:\n- I am shipping 8590."
    assert list_check_text(label_reply) == "Shipped so far:\n"
    wrapped_reply = (
        "Please choose which of these options\nI should ship for the release:\n\nIn progress:\n"
        "- I can ship the export.\n- I can ship the import.\n- I can ship the report."
    )
    assert list_check_text(wrapped_reply) == wrapped_reply
    paragraph_reply = "Please pick one.\n\nShipped so far:\n\nIn progress:\n- I am shipping 8590."
    assert list_check_text(paragraph_reply) == "Please pick one.\n\nShipped so far:\n"
    option_reply = (
        "Done.\n\nIn progress:\n- I need your approval to ship the new build.\n"
        "- I am watching the ledger.\n- I can keep the old build.\n- I could roll back the patch."
    )
    assert list_check_text(option_reply) == (
        "Done.\n\nIn progress:\n- I need your approval to ship the new build.\n"
        "- I can keep the old build.\n- I could roll back the patch."
    )
    assert list_check_text("Done.\n\nIn progress:\n- I can ship 8590.").strip() == "Done."
    need_reply = "I need a decision.\n\nIn progress:\n- I can ship it today.\n- I can ship it Friday.\n- I can ship it next week."
    assert list_check_text(need_reply) == need_reply
    yours_reply = "The release date is yours to set.\n\nIn progress:\n- I can ship on Monday.\n- I can ship on Friday.\n- I can ship on the 30th."
    assert list_check_text(yours_reply) == yours_reply
    would_reply = "The date is yours to set.\n\nIn progress:\n- I would ship Monday.\n- I would ship Friday.\n- I would ship the 30th."
    assert list_check_text(would_reply) == would_reply
    status_for_you_reply = "Your build is ready.\n\nIn progress:\n- I am shipping 8590."
    assert list_check_text(status_for_you_reply) == "Your build is ready.\n"


def test_should_keep_a_footer_line_that_waits_on_an_owner_decision_in_the_list_check_text() -> None:
    owner_reply = (
        "Done.\n\nIn progress:\n- I am shipping 8590.\n"
        "- I am holding the release until the owner approves the price."
    )
    assert list_check_text(owner_reply) == (
        "Done.\n\nIn progress:\n- I am holding the release until the owner approves the price."
    )


def test_should_keep_a_first_person_footer_that_waits_on_the_user_in_the_list_check_text() -> None:
    approval_reply = (
        "Done.\n\nIn progress:\n- I am shipping 8590.\n- I can proceed once you approve the release.\n"
        "- I am watching the ledger."
    )
    status_reply = "Done.\n\nIn progress:\n- I am watching the discount ledger so you see its next update."
    asking_reply = "Done.\n\nIn progress:\n- I am shipping 8590.\n- I am asking you to approve the release."
    holding_reply = (
        "Done.\n\nIn progress:\n- I am holding the release for your approval.\n"
        "- I am holding the price change for your approval.\n- I am holding the date for your approval."
    )
    assert list_check_text(approval_reply) == (
        "Done.\n\nIn progress:\n- I can proceed once you approve the release."
    )
    assert list_check_text(asking_reply) == "Done.\n\nIn progress:\n- I am asking you to approve the release."
    assert list_check_text(holding_reply) == holding_reply
    assert list_check_text(status_reply).strip() == "Done."


def test_should_tell_a_footer_ask_from_a_status_line() -> None:
    assert not is_footer_ask("I am shipping 8590.")
    assert not is_footer_ask("I am watching the discount ledger so you see its next update.")
    assert not is_footer_ask("I am shipping 8590. Its tests are pending.")
    assert is_footer_ask("I am merging 8790 once it has your approval.")
    assert is_footer_ask("Approve the release.")
    assert is_footer_ask("Should I merge 8590?")
    assert is_footer_ask("I will release version A only with an OK from you.")
    assert not is_footer_ask("I am running the automated tests so that you know it works.")
    assert not is_footer_ask("I am watching the ledger so you can see its next update.")
    assert is_footer_ask("I am holding the launch so you can approve it first.")
    assert is_footer_ask("I am putting the dates in one place so you can see the options and pick a release date.")
    assert not is_footer_ask("I am putting the dates in one place so you can see the options and track them.")
    assert is_footer_ask("I am listing the dates so you can see them and **pick** one.")
    assert not is_footer_ask("I am shipping **8590**.")
    assert is_footer_ask("I am holding the release until the owner approves the price.")
    assert is_footer_ask("I am waiting for a decision on the second vendor.")
    assert is_footer_ask("I am preparing the rollout. Pick a release date.")
    assert is_footer_ask("I need the owner to pick the release date.")
    assert is_footer_ask("I am holding the sale until the owner picks a date.")
    assert is_footer_ask("I am preparing the launch; please pick a date.")
    assert is_footer_ask("I need a date from the owner.")
    assert is_footer_ask("I am waiting for Jon to authorize the release.")
    assert is_footer_ask("I am waiting for Jon's OK on the release date.")
    assert is_footer_ask("I am waiting for Jon to give me a release date.")
    assert is_footer_ask("I am holding the release until Jon confirms the date.")
    assert is_footer_ask("I am holding the export until the lead reviews it.")
    assert is_footer_ask("I am holding the launch until Jon tells me the price.")
    assert not is_footer_ask("I am adding input validation.")
    assert not is_footer_ask("I am checking the permission rules.")
    assert not is_footer_ask("I am updating the decision log.")
    assert is_footer_ask("I am preparing the release. Would Friday work for launch? The build is ready.")
    assert is_footer_ask("I am preparing the launch: choose a date.")
    assert is_footer_ask("I cannot ship without a date from Jon.")
    assert not is_footer_ask("I am shipping without the old flag.")
    for each_status in ("I've started the build.", "I’ve started the build.", "I'll merge once the tests pass.", "I’ll merge once the tests pass.", "I'd queued the export."):
        assert not is_footer_ask(each_status)
    assert is_footer_ask("I am holding the export until the client sends the logo.")
    assert is_footer_ask("I am holding the rollout for a green light from the lead.")
    assert is_footer_ask("I am preparing the launch. Next, choose its date.")
    assert not is_footer_ask("I am preparing the launch. Next, it ships to the store.")
    assert not is_footer_ask("I need the rows from the export before the release.")
    assert not is_footer_ask("I am updating the discount ledger so your prices stay current.")
    assert is_footer_ask("I am holding the launch so your team can approve it.")
    assert not is_footer_ask("I need the build to finish before the release.")
    assert not is_footer_ask("I am fixing the list reader in pull request 8801. I am waiting for the last tests.")



def test_should_keep_every_option_when_the_lead_leaves_the_choice_to_the_user() -> None:
    choice_reply = (
        "The release date is yours to choose.\n\nIn progress:\n"
        "- I will ship Friday under option A.\n- I will ship Monday under option B.\n- I will ship Wednesday under option C."
    )
    assert list_check_text(choice_reply) == choice_reply
    status_reply = "The release is set.\n\nIn progress:\n- I will ship Friday.\n- I will ship the notes Monday."
    assert list_check_text(status_reply).strip() == "The release is set."


def test_should_keep_every_option_when_an_earlier_paragraph_asks_the_user_to_choose() -> None:
    choice_reply = (
        "Please choose a release date.\n\nThe build is ready.\n\nIn progress:\n"
        "- I will ship on Monday.\n- I will ship on Wednesday.\n- I will ship on Friday."
    )
    assert list_check_text(choice_reply) == choice_reply
