import pytest
from pathlib import Path

from hooks_constants.closing_question_round_gate_constants import CLOSING_ROUND_REASON_LEAD
from test_closing_question_round_gate import (
    held_reason,
    reply_record,
    tool_call_record,
    tool_result_record,
    typed_prompt_record,
)

PULL_REQUEST_LINE = (
    "I updated the title and description of pull request 10037. It is waiting on you to approve it."
)
NEEDS_YOU_REPLY = (
    "The variable works. The run is at https://example.test/run/1.\n\n"
    "Needs you:\n"
    "- Approve pull request 10037, which is waiting on you.\n"
    "- Open the settings page and paste the new token."
)


def test_should_let_a_reply_that_lists_its_items_for_the_user_end_with_no_new_round(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_records = [
        typed_prompt_record(),
        reply_record(PULL_REQUEST_LINE),
        tool_call_record("Bash", {"command": "gh pr view 10037"}),
        tool_result_record("Bash", "open"),
        reply_record(NEEDS_YOU_REPLY),
    ]
    assert held_reason(monkeypatch, capsys, tmp_path, all_records) is None


def test_should_still_hold_when_the_closing_reply_lists_no_items_for_the_user(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_records = [
        typed_prompt_record(),
        reply_record(PULL_REQUEST_LINE),
        tool_call_record("Bash", {"command": "gh pr view 10037"}),
        tool_result_record("Bash", "open"),
        reply_record("The variable works."),
    ]
    reason = held_reason(monkeypatch, capsys, tmp_path, all_records)
    assert str(reason).startswith(CLOSING_ROUND_REASON_LEAD)
    assert PULL_REQUEST_LINE in str(reason)


@pytest.mark.parametrize(
    "heading", ["Needs you:", "**Needs you:**", "What I need from you:", "Waiting on you:", "Your turn:"]
)
def test_should_read_each_heading_that_opens_a_list_for_the_user(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    heading: str,
) -> None:
    all_records = [
        typed_prompt_record(),
        reply_record(PULL_REQUEST_LINE),
        reply_record(f"Done.\n\n{heading}\n- Approve it."),
    ]
    assert held_reason(monkeypatch, capsys, tmp_path, all_records) is None


@pytest.mark.parametrize(
    "closing_reply",
    ["Done.\n\nNeeds you:", "Done.\n\n`Needs you:`\n- Approve it.", "Done.\n\nNeeds you soon:\n- Approve it."],
)
def test_should_not_read_a_heading_with_no_list_a_code_span_or_another_wording(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    closing_reply: str,
) -> None:
    all_records = [typed_prompt_record(), reply_record(PULL_REQUEST_LINE), reply_record(closing_reply)]
    assert str(held_reason(monkeypatch, capsys, tmp_path, all_records)).startswith(
        CLOSING_ROUND_REASON_LEAD
    )


def test_should_not_quote_a_line_from_before_an_answered_card(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_records = [
        typed_prompt_record(),
        reply_record(PULL_REQUEST_LINE),
        tool_call_record("AskUserQuestion", tool_use_id="id-card"),
        tool_result_record("AskUserQuestion", "The user chose Approve.", tool_use_id="id-card"),
        reply_record("Thanks, approved."),
    ]
    assert held_reason(monkeypatch, capsys, tmp_path, all_records) is None


def test_should_not_quote_a_line_the_card_already_covered_when_the_reply_repeats_it(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_records = [
        typed_prompt_record(),
        reply_record(PULL_REQUEST_LINE),
        tool_call_record("AskUserQuestion", tool_use_id="id-card"),
        tool_result_record("AskUserQuestion", "The user chose Approve.", tool_use_id="id-card"),
        reply_record(PULL_REQUEST_LINE),
    ]
    assert held_reason(monkeypatch, capsys, tmp_path, all_records) is None


def test_should_not_quote_a_line_from_before_a_later_typed_prompt(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    all_records = [
        typed_prompt_record(),
        reply_record(PULL_REQUEST_LINE),
        typed_prompt_record("Go on."),
        reply_record("The variable works."),
    ]
    assert held_reason(monkeypatch, capsys, tmp_path, all_records) is None


@pytest.mark.parametrize(
    "own_steps",
    [
        "Next I will log the bug, run review round 2, and delete the branch.",
        "Steps left: the review rounds are pending, the cleanup is blocked, the retry is untested.",
        "I deferred the backoff setting and skipped the docs change.",
    ],
)
def test_should_not_treat_a_reply_that_lists_only_the_agents_own_steps_as_open_items(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    own_steps: str,
) -> None:
    all_records = [typed_prompt_record(), reply_record(own_steps)]
    assert held_reason(monkeypatch, capsys, tmp_path, all_records) is None
