"""Tests for compaction_trim: the caveman trim, the overruled marks, and the recall budget."""

import sys
from pathlib import Path

_SESSION_DIR = Path(__file__).resolve().parent
_HOOKS_ROOT = _SESSION_DIR.parent
for each_sys_path_entry in (str(_SESSION_DIR), str(_HOOKS_ROOT)):
    if each_sys_path_entry not in sys.path:
        sys.path.insert(0, each_sys_path_entry)

import compaction_trim as trim
from compaction_user_messages import TypedMessage
from hooks_constants.compaction_user_messages_constants import (
    MAXIMUM_MESSAGE_CHARACTERS,
    MAXIMUM_RECALL_CHARACTERS,
)


def message(position: int, text: str) -> TypedMessage:
    return TypedMessage(position=position, timestamp="t", text=text)


def test_caveman_text_should_drop_filler_and_articles() -> None:
    assert (
        trim.caveman_text("Could you please just add the retry to a deploy script , basically.")
        == "add retry to deploy script."
    )


def test_caveman_text_should_keep_backtick_spans_and_path_tokens_as_typed() -> None:
    assert (
        trim.caveman_text("run `the just a tool` on just/the.py and the-a.md")
        == "run `the just a tool` on just/the.py and the-a.md"
    )


def test_caveman_text_should_keep_a_hedge() -> None:
    assert trim.caveman_text("I think the cache is stale") == "I think cache is stale"


def test_caveman_text_should_keep_a_capital_letter_label() -> None:
    assert trim.caveman_text("The plan A is good, an Option A or B") == "plan A is good, Option A or B"


def test_trimmed_lines_should_not_mark_a_line_a_reminder_repeats() -> None:
    all_messages = [
        message(1, "Set up the linter in CI"),
        message(2, "Don't forget the linter config too"),
    ]
    assert trim.trimmed_lines(all_messages) == [
        "#1 Set up linter in CI",
        "#2 Don't forget linter config too",
    ]


def test_trimmed_lines_should_not_read_a_cue_inside_a_longer_word() -> None:
    all_messages = [
        message(1, "Add docs for the API"),
        message(2, "Document the undocumented parts of the API"),
    ]
    assert trim.trimmed_lines(all_messages) == [
        "#1 Add docs for API",
        "#2 Document undocumented parts of API",
    ]


def test_trimmed_lines_should_drop_acknowledgments_and_interrupts() -> None:
    all_messages = [
        message(1, "ship it to staging"),
        message(2, "ok thanks"),
        message(3, "[Request interrupted by user]"),
        message(4, "yes, go ahead"),
        message(5, "ok but use port 8443"),
    ]
    assert trim.trimmed_lines(all_messages) == [
        "#1 ship it to staging",
        "#5 ok but use port 8443",
    ]


def test_trimmed_lines_should_mark_the_earlier_message_a_reversal_overrules() -> None:
    all_messages = [
        message(1, "Store the uploads in S3."),
        message(2, "Log every retry to logs/retry.csv"),
        message(3, "Change of plan, keep the uploads on local disk, not S3."),
    ]
    assert trim.trimmed_lines(all_messages) == [
        "#1 Store uploads in S3. (overruled by #3)",
        "#2 Log every retry to logs/retry.csv",
        "#3 Change of plan, keep uploads on local disk, not S3.",
    ]


ARTIFACT_COMMENT_TEXT = """[Artifact comment sent to Claude]
Artifact: https://claude.ai/code/artifact/e5f0
Comment thread: 02ec
I sent you this comment from the artifact's comment thread. Handle it in this session.
=== BEGIN ARTIFACT COMMENT df7f ===
> Can you show me this?
> How is the agent spawned?
=== END ARTIFACT COMMENT df7f ===
<comment-anchor-context source="artifact content">
Location: What happens when a session compacts
Element: rect
</comment-anchor-context>
Answer this comment in its thread, not here."""


def test_trimmed_lines_should_keep_only_the_link_anchor_and_quote_of_an_artifact_comment() -> None:
    assert trim.trimmed_lines([message(1, ARTIFACT_COMMENT_TEXT)]) == [
        "#1 Artifact comment on https://claude.ai/code/artifact/e5f0 at What happens when "
        "session compacts: show me this? How is agent spawned?"
    ]


def test_trimmed_lines_should_drop_html_comments_and_a_message_left_empty() -> None:
    assert trim.trimmed_lines(
        [message(1, "<!-- reply 1 --> use port 8443"), message(2, "<!-- draft -->")]
    ) == ["#1 use port 8443"]


def test_trimmed_lines_should_cut_a_long_message_and_say_how_much() -> None:
    long_text = "y" * (MAXIMUM_MESSAGE_CHARACTERS + 25)
    assert trim.trimmed_lines([message(1, long_text)]) == [
        "#1 " + "y" * MAXIMUM_MESSAGE_CHARACTERS + " [25 more characters left out]"
    ]


def test_recall_text_should_keep_the_first_and_the_newest_lines_within_budget() -> None:
    message_count = 3 * MAXIMUM_RECALL_CHARACTERS // MAXIMUM_MESSAGE_CHARACTERS
    all_messages = [
        message(each, f"m{each} " + "x" * (MAXIMUM_MESSAGE_CHARACTERS - 100))
        for each in range(1, message_count + 1)
    ]
    all_recall_lines = (trim.recall_text(all_messages) or "").splitlines()
    assert all_recall_lines[0].startswith("#1 m1 ")
    assert all_recall_lines[-1].startswith(f"#{message_count} m{message_count} ")
    kept_line_count = len(all_recall_lines) - 2
    left_out_count = message_count - 1 - kept_line_count
    assert left_out_count > 0
    assert all_recall_lines[1] == f"[{left_out_count} earlier messages left out to fit the budget]"
    recall_without_note = "\n".join([all_recall_lines[0], *all_recall_lines[2:]])
    assert len(recall_without_note) <= MAXIMUM_RECALL_CHARACTERS


def test_recall_text_should_return_none_when_nothing_carries_content() -> None:
    assert trim.recall_text([]) is None
    assert trim.recall_text([message(1, "ok"), message(2, "thanks")]) is None
