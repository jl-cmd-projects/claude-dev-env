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
    FOOTER_CONTINUATION_LINE_PATTERN,
    FOOTER_GAP_LABEL,
    FOOTER_HEADING_PATTERN,
    FOOTER_INSTRUCTION,
    FOOTER_ITEM_LINE_PATTERN,
    FOOTER_KEY_WORDS_INSTRUCTION,
    FOOTER_STATUS_MARKER_PATTERN,
    FOOTER_STATUS_STAND_IN,
    FIRST_PERSON_ITEM_PATTERN,
    FOOTER_TASK_LINE_TEMPLATE,
    FOOTER_TASKS_LABEL,
    FOOTER_WORD_PATTERN,
    MATCH_PREFIX_LENGTH,
    POSSESSIVE_ENDING,
    REASON_PART_SEPARATOR,
    TASK_KEY_WORD_SEPARATOR,
)
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
    for each_position in range(len(all_lines) - 1, -1, -1):
        if FOOTER_HEADING_PATTERN.fullmatch(all_lines[each_position].strip()) is None:
            continue
        all_tail_lines = [
            each_line for each_line in all_lines[each_position + 1 :] if each_line.strip()
        ]
        all_items: list[str] = []
        for each_line in all_tail_lines:
            item_match = FOOTER_ITEM_LINE_PATTERN.match(each_line)
            if item_match is not None:
                all_items.append(item_match["item"])
            elif all_items and FOOTER_CONTINUATION_LINE_PATTERN.match(each_line):
                all_items[-1] = f"{all_items[-1]} {each_line.strip()}"
            else:
                return SplitReply(closing_reply, None)
        if not all_items:
            return SplitReply(closing_reply, None)
        return SplitReply(LINE_BREAK.join(all_lines[:each_position]), tuple(all_items))
    return SplitReply(closing_reply, None)


def list_check_text(closing_reply: str) -> str:
    """Return the part of the reply an open-item list check reads.

    ::

        "Done.\n\nIn progress:\n- I am shipping 8590."           -> "Done.\n"
        "Done.\n\nIn progress:\n- Should I merge 8590?"          -> the whole reply
        "Done.\n\nIn progress:\n- Approve the release."          -> the whole reply
        "Done."                                                  -> "Done."

    A footer that only says where work stands is required status, so the
    check reads the body above it. The rule writes each footer item in first
    person, so a footer counts as status only when every item starts with
    "I" and none holds an open-item line, such as a question or an ask of
    the user. The scan reads "pending", "blocked", "not done", and "not run"
    in a footer as status, as the closing round scan does. Any other footer
    stays in.

    Args:
        closing_reply: The reply the turn ends with.

    Returns:
        The body above a status-only footer, or the whole reply.
    """
    split_reply = split_footer(closing_reply)
    if split_reply.footer_items is None:
        return closing_reply
    all_status_items = [
        FOOTER_STATUS_MARKER_PATTERN.sub(FOOTER_STATUS_STAND_IN, each_item) for each_item in split_reply.footer_items
    ]
    is_first_person = all(FIRST_PERSON_ITEM_PATTERN.match(each_item) for each_item in split_reply.footer_items)
    if not is_first_person or marked_open_lines(all_status_items, math.inf):
        return closing_reply
    return split_reply.body


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
