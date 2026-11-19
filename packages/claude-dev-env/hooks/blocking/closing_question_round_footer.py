"""Read the In progress footer of a closing reply and check that it names each task in progress.

A working reply ends with the footer::

    The list reader fix is pushed.

    In progress:
    - I am fixing the list reader in pull request 8801. I am waiting for the last tests.
    - I am watching the discount ledger run.

``split_footer`` cuts the footer off the reply, so the open-item marker scan
reads only the body above it. ``left_out_tasks`` matches each in-progress
task to the footer by the words of its subject that name the thing worked on,
and ``footer_reason`` writes the hold reason that teaches the plain-words
footer.
"""

from __future__ import annotations

import math
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)
blocking_directory = str(Path(__file__).resolve().parent)
if blocking_directory not in sys.path:
    sys.path.insert(0, blocking_directory)

from closing_question_round_open_items import marked_open_lines
from open_tasks_transcript import TaskItem

from hooks_constants.closing_question_round_gate_constants import (
    ALL_SUBJECT_SKIP_WORDS,
    DECISION_DEPENDENCY_PATTERN,
    DECISION_WORD_PATTERN,
    LEAD_LABEL_END,
    FOOTER_CONTINUATION_LINE_PATTERN,
    FOOTER_GAP_LABEL,
    FOOTER_HEADING_PATTERN,
    FOOTER_INSTRUCTION,
    FOOTER_ITEM_LINE_PATTERN,
    FOOTER_ITEM_PART_SEPARATOR,
    FOOTER_KEY_WORDS_INSTRUCTION,
    FOOTER_STATUS_MARKER_PATTERN,
    FOOTER_STATUS_STAND_IN,
    FIRST_PERSON_ITEM_PATTERN,
    FOOTER_TASK_LINE_TEMPLATE,
    OTHER_PARTY_REQUEST_PATTERN,
    COORDINATED_REQUEST_PATTERN,
    MARKDOWN_EMPHASIS_PATTERN,
    PURPOSE_CLAUSE_PATTERN,
    PURPOSE_CLAUSE_STAND_IN,
    REQUEST_OPENER_PATTERN,
    SENTENCE_BREAK_PATTERN,
    USER_MENTION_PATTERN,
    FOOTER_TASKS_LABEL,
    FOOTER_WORD_PATTERN,
    MATCH_PREFIX_LENGTH,
    POSSESSIVE_ENDING,
    REASON_PART_SEPARATOR,
    TASK_KEY_WORD_SEPARATOR,
)
from hooks_constants.final_reply_gate_constants import QUESTION_MARK
from hooks_constants.user_step_wording_constants import LINE_BREAK


class SplitReply(NamedTuple):
    """A closing reply cut at its In progress footer.

    Attributes:
        body: The reply above the footer, or the whole reply when it has no footer.
        footer_items: The text of each footer list item, or None when the reply has no footer.
    """

    body: str
    footer_items: tuple[str, ...] | None


def split_footer(closing_reply: str) -> SplitReply:
    """Return the reply's body and the items of the footer it ends with.

    ::

        "Done.\\n\\nIn progress:\\n- I am fixing the list reader."  -> ("Done.\\n", ("I am fixing the list reader.",))
        "Done.\\n\\n**In progress:**\\n- I am fixing it."           -> a footer, the bold heading counts
        "In progress:\\n- I am fixing it.\\n\\nDone."               -> no footer, prose follows it
        "Done.\\n\\nIn progress:"                                 -> no footer, it has no item

    The heading is the last line that holds only ``In progress:``, alone or
    in one bold mark, in any letter case. Every non-empty line after it must
    be a ``-``, ``*``, or ``+`` list item or an indented line that carries
    one on, and at least one item must follow.
    """
    all_lines = closing_reply.rstrip().split(LINE_BREAK)
    found_footer = _footer_item_lines(all_lines)
    if found_footer is None:
        return SplitReply(closing_reply, None)
    heading_position, all_item_lines = found_footer
    return SplitReply(
        LINE_BREAK.join(all_lines[:heading_position]),
        tuple(_item_text(each_item_lines) for each_item_lines in all_item_lines),
    )


def _footer_item_lines(all_lines: list[str]) -> tuple[int, list[list[str]]] | None:
    heading_position = next(
        (
            each_position
            for each_position in range(len(all_lines) - 1, -1, -1)
            if FOOTER_HEADING_PATTERN.fullmatch(all_lines[each_position].strip()) is not None
        ),
        None,
    )
    if heading_position is None:
        return None
    all_item_lines = _item_line_groups(all_lines[heading_position + 1 :])
    return (heading_position, all_item_lines) if all_item_lines else None


def _item_line_groups(all_tail_lines: list[str]) -> list[list[str]]:
    all_item_lines: list[list[str]] = []
    for each_line in all_tail_lines:
        if not each_line.strip():
            continue
        if FOOTER_ITEM_LINE_PATTERN.match(each_line) is not None:
            all_item_lines.append([each_line])
        elif all_item_lines and FOOTER_CONTINUATION_LINE_PATTERN.match(each_line):
            all_item_lines[-1].append(each_line)
        else:
            return []
    return all_item_lines


def _item_text(all_item_lines: list[str]) -> str:
    item_match = FOOTER_ITEM_LINE_PATTERN.match(all_item_lines[0])
    first_text = item_match["item"] if item_match is not None else all_item_lines[0].strip()
    return FOOTER_ITEM_PART_SEPARATOR.join([first_text, *(each_line.strip() for each_line in all_item_lines[1:])])


def is_footer_ask(footer_item: str) -> bool:
    """Return True when a footer item asks something of the user, so it is no plain status line.

    ::

        "I am shipping 8590."                          -> False
        "I am watching the ledger so you see it."      -> False
        "I am merging 8590 once it has your approval." -> True, it names the user
        "I will release it only with an OK from you."  -> True
        "I am holding it until the owner approves."    -> True, it waits on a decision
        "I am waiting for Jon to authorize the release." -> True, it waits on an authorization
        "I am waiting for Jon's OK on the release date." -> True, it waits on an OK
        "I need an answer on the price."               -> True, it waits on an answer
        "I need the owner to pick the release date."   -> True, it asks someone to pick
        "I am waiting for Jon to give me a release date." -> True, it asks someone to give
        "I am holding it until the owner picks a date." -> True, it waits on a choice
        "I need a date from the owner."                -> True, it waits on a person
        "I am updating the ledger so your prices stay current." -> False, a benefit clause
        "I am listing the dates so you can see them and pick one." -> True, a request after the benefit
        "I am listing the dates so you can see them and **pick** one." -> True, emphasis is read past
        "Approve the release."                         -> True, not first person
        "I am preparing it. Pick a release date."      -> True, its second sentence is a request
        "I am preparing the launch: choose a date."    -> True, a request after a colon
        "I am shipping 8590. Its tests are pending."   -> False
        "I am updating the decision log."              -> False, no wait before the word
        "I am holding the release until Jon confirms the date." -> True, it waits on a confirmation
        "Should I merge 8590?"                         -> True, a question
        "I am preparing it. Would Friday work? The build is ready." -> True, a question inside

    The rule writes each footer item in first person and says what the work
    gets the user, as "so you see its next update" does. Only such a benefit
    clause, "so you" or "so that you" with see, know, get, read, follow,
    have, hear, learn, find, watch, or track, or "so your" and one or two
    words with stays, remains, keeps, updates, shows, matches, loads, works,
    runs, arrives, is, or are, leaves the user unnamed, so "so you can
    approve it first" and "so your team can approve it" still name the user.
    A benefit clause followed by and, or, or then and a request word, as
    "so you can see the dates and pick one", counts as an ask, and so does
    an item with a sentence that ends with a question mark. Each word
    check reads the item with its asterisks, underscores, tildes, and
    backticks left out, so "**pick**" reads as pick. An item that is not
    first person, that names the user in any other way, that waits,
    needs, holds, or is blocked, until, once, or after, within 40
    characters before one of an approval, an authorization, a green light, a clearance, a decision, a sign-off, a go-ahead, permission, consent, an
    answer, input, a choice, or a confirmation from anyone, or that holds an open-item line other than the status markers
    "pending", "blocked", "not done", and "not run" may ask the user
    something, so it counts as an ask. A later sentence or clause after a
    semicolon that opens with a
    request word such as please, pick, choose, approve, or confirm, alone or
    after a word such as next, then, or finally, counts as an ask too, so a request after a status sentence is kept, and so does
    an item that needs, wants, waits for, or asks someone to pick, choose,
    approve, confirm, decide, answer, give, send, share, provide, or supply,
    or that holds until, once, when, after, unless, or before someone
    picks, chooses, approves, confirms, decides, answers, replies, reviews,
    tells, says, signs off, gives, sends, shares, provides, or supplies, or that needs or waits for something
    from a person such as the owner, a client, or a reviewer. Each such
    match looks at most 80 characters past its first word, so a long item
    costs one pass.
    """
    status_item = FOOTER_STATUS_MARKER_PATTERN.sub(FOOTER_STATUS_STAND_IN, footer_item)
    plain_item = MARKDOWN_EMPHASIS_PATTERN.sub("", footer_item)
    return (
        FIRST_PERSON_ITEM_PATTERN.match(plain_item) is None
        or any(
            REQUEST_OPENER_PATTERN.match(each_sentence) is not None
            for each_sentence in SENTENCE_BREAK_PATTERN.split(plain_item.strip())
        )
        or USER_MENTION_PATTERN.search(PURPOSE_CLAUSE_PATTERN.sub(PURPOSE_CLAUSE_STAND_IN, plain_item)) is not None
        or COORDINATED_REQUEST_PATTERN.search(plain_item) is not None
        or any(
            each_sentence.rstrip().endswith(QUESTION_MARK)
            for each_sentence in SENTENCE_BREAK_PATTERN.split(plain_item.strip())
        )
        or DECISION_DEPENDENCY_PATTERN.search(plain_item) is not None
        or OTHER_PARTY_REQUEST_PATTERN.search(plain_item) is not None
        or bool(marked_open_lines([status_item], math.inf))
    )


def list_check_text(closing_reply: str) -> str:
    """Return the part of the reply an open-item list check reads.

    ::

        "Done.\n\nIn progress:\n- I am shipping 8590."                -> "Done.\n"
        "Done.\n\nIn progress:\n- Pick a price.\n- Confirm the date."  -> the whole reply
        "Done.\n\nIn progress:\n- I am shipping 8590.\n- Pick a price." -> "Done.\n\nIn progress:\n- Pick a price."
        "Pick which option I should ship.\n\nIn progress:\n- I can ship A." -> the whole reply
        "Pending your decision:\n\nIn progress:\n- I can ship A."         -> the whole reply
        "Done."                                                       -> "Done."

    A footer line that only says where work stands is required status, so
    the check leaves it out and reads the body with the footer lines that ask
    the user something, as ``is_footer_ask`` finds them. The heading and
    each kept line stay as the reply wrote them, so a span the judge quotes
    from them is still found in the reply. When the last body line above
    the footer opens a sentence with a request word, ends with a
    question mark, or ends with a colon after a decision word or a word
    for the user, it gives the lines under it their meaning, so the
    whole reply is read.

    Args:
        closing_reply: The reply the turn ends with.

    Returns:
        The body with the footer's asks, or the whole reply when every item asks.
    """
    all_lines = closing_reply.rstrip().split(LINE_BREAK)
    found_footer = _footer_item_lines(all_lines)
    if found_footer is None:
        return closing_reply
    heading_position, all_item_lines = found_footer
    if _is_asking_lead(all_lines[:heading_position]):
        return closing_reply
    all_ask_lines = [
        each_item_lines for each_item_lines in all_item_lines if is_footer_ask(_item_text(each_item_lines))
    ]
    if len(all_ask_lines) == len(all_item_lines):
        return closing_reply
    all_body_lines = all_lines[:heading_position]
    if not all_ask_lines:
        return LINE_BREAK.join(all_body_lines)
    all_kept_lines = [each_line for each_item_lines in all_ask_lines for each_line in each_item_lines]
    return LINE_BREAK.join([*all_body_lines, all_lines[heading_position], *all_kept_lines])


def _is_asking_lead(all_body_lines: list[str]) -> bool:
    all_filled_lines = [each_line.strip() for each_line in all_body_lines if each_line.strip()]
    if not all_filled_lines:
        return False
    lead_line = MARKDOWN_EMPHASIS_PATTERN.sub("", all_filled_lines[-1])
    is_decision_label = lead_line.endswith(LEAD_LABEL_END) and (
        DECISION_WORD_PATTERN.search(lead_line) is not None or USER_MENTION_PATTERN.search(lead_line) is not None
    )
    return (
        is_decision_label
        or lead_line.endswith(QUESTION_MARK)
        or any(
            REQUEST_OPENER_PATTERN.match(each_sentence) is not None
            for each_sentence in SENTENCE_BREAK_PATTERN.split(lead_line)
        )
    )


def _stem(word: str) -> str:
    return word.removesuffix(POSSESSIVE_ENDING)[:MATCH_PREFIX_LENGTH]


def subject_key_words(subject: str) -> list[str]:
    """Return the words of a task subject that name the thing the task works on.

    ::

        "Fix list reader lint finding"          -> ["list", "reader"]
        "Watch discount ledger scheduled wake"  -> ["discount", "ledger"]
        "Open ledger PR"                        -> ["ledger"]

    Verbs such as fix and watch, words only an agent uses such as lint and
    wake, and short words such as the are dropped.
    """
    return [
        each_word
        for each_word in FOOTER_WORD_PATTERN.findall(subject.lower())
        if each_word not in ALL_SUBJECT_SKIP_WORDS
    ]


def task_key_words(task_item: TaskItem, all_open_items: Sequence[TaskItem]) -> list[str]:
    """Return the key words that tell this task apart from the other open tasks.

    ::

        "Watch discount ledger"  beside  "Open ledger PR"  -> ["discount"]
        "Watch discount ledger"  alone                     -> ["discount", "ledger"]

    A word another open task shares, read by its first five letters, is
    dropped. When every word is shared, all of them stay.
    """
    all_key_words = subject_key_words(task_item.subject)
    all_other_stems = {
        _stem(each_word)
        for each_other in all_open_items
        if each_other is not task_item
        for each_word in subject_key_words(each_other.subject)
    }
    all_unique_words = [
        each_word for each_word in all_key_words if _stem(each_word) not in all_other_stems
    ]
    return all_unique_words or all_key_words


def left_out_tasks(
    all_footer_items: Sequence[str],
    all_in_progress_items: Sequence[TaskItem],
    all_open_items: Sequence[TaskItem],
) -> list[TaskItem]:
    """Return each in-progress task the footer does not name.

    ::

        footer "I am fixing the list reader."  task "Fix list reader lint finding"  -> named
        footer "I am watching the discounts."  task "Watch discount ledger"         -> named, "disco"
        footer "I am watching the ledger run." tasks "Watch discount ledger" and
            "Open ledger PR"                                                         -> left out

    A task is named when one of its ``task_key_words`` matches a footer word
    by the first five letters. A task with no key words counts as named.

    Args:
        all_footer_items: The footer's list item texts.
        all_in_progress_items: The session's tasks with status ``in_progress``.
        all_open_items: Every task not yet completed, which sets the words a task shares.

    Returns:
        The in-progress tasks the footer leaves out, in task list order.
    """
    all_footer_stems = {
        _stem(each_word)
        for each_item in all_footer_items
        for each_word in FOOTER_WORD_PATTERN.findall(each_item.lower())
    }
    return [
        each_task
        for each_task in all_in_progress_items
        if (all_key_words := task_key_words(each_task, all_open_items))
        and not any(_stem(each_word) in all_footer_stems for each_word in all_key_words)
    ]


def _task_line(task_item: TaskItem, all_open_items: Sequence[TaskItem]) -> str:
    all_key_words = task_key_words(task_item, all_open_items) or [task_item.subject]
    return FOOTER_TASK_LINE_TEMPLATE.format(
        subject=task_item.subject, key_words=TASK_KEY_WORD_SEPARATOR.join(all_key_words)
    )


def footer_reason(
    reason_lead: str,
    all_in_progress_items: Sequence[TaskItem],
    all_left_out_items: Sequence[TaskItem],
    all_open_items: Sequence[TaskItem],
) -> str:
    """Return a footer hold reason: its lead, the tasks with their key words, and the plain-words guidance.

    The sentence that asks to keep the bracketed key words appears only when the reason lists tasks.

    ::

        This session's In progress footer leaves out work that is still in progress.
        Left out of the footer:
        - Watch discount ledger scheduled wake [discount]
        Work in progress, with the words that name each task in brackets:
        - Fix list reader lint finding [list reader]
        - Watch discount ledger scheduled wake [discount]
        Keep the words in brackets above, so the footer names each task.
        End the reply with the In progress footer: ...

    Args:
        reason_lead: The reason's fixed first sentence, which the hold count reads.
        all_in_progress_items: The session's tasks with status ``in_progress``.
        all_left_out_items: The tasks the footer leaves out, listed first when there are any.
        all_open_items: Every task not yet completed, which sets each task's key words.

    Returns:
        The reason, one part per line.
    """
    all_parts = [reason_lead]
    if all_left_out_items:
        all_parts.append(FOOTER_GAP_LABEL)
        all_parts.extend(_task_line(each_task, all_open_items) for each_task in all_left_out_items)
    if all_in_progress_items:
        all_parts.append(FOOTER_TASKS_LABEL)
        all_parts.extend(
            _task_line(each_task, all_open_items) for each_task in all_in_progress_items
        )
        all_parts.append(FOOTER_KEY_WORDS_INSTRUCTION)
    all_parts.append(FOOTER_INSTRUCTION)
    return REASON_PART_SEPARATOR.join(all_parts)
