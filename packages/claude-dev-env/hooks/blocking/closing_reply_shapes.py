"""Find two closing-reply shapes the user corrected: a promised later report, and open items sent as a list.

The open tasks Stop gate reads the reply a turn ends with. Two shapes in it
leave work with the user that the agent could carry itself::

    flag: A full write-up will be here when you are back.
    flag: I'll report back once CI ends.
    flag: What I deferred:  followed by 3 or more list or table items
    ok:   No report will follow.
    ok:   I'll apply each finding once they report back.
    ok:   Changed files:  followed by 5 bullets
    ok:   Deferred:  followed by 2 bullets

The promise patterns are ``when you're / are / get / come back``; a report,
summary, write-up, recap, or result that "will be here / waiting / ready /
posted" or "will follow / land / arrive / come"; ``I'll`` or ``I will``
report, post, send, share, update you, let you know, follow up, circle back,
check back, or get back to you before when, once, after, later, tomorrow, or
in the morning; and ``I'll report back``. A match is skipped when no, not,
never, none, or nothing comes before it in its sentence.

An open-item list is a run of item lines: bullets, numbered lines, and table
body rows. A run goes on across blank lines, indented lines, and a table's
header and separator rows. Its lead is the nearest non-blank line above it.
The lead must name open work (deferred, sidestepped, remaining, outstanding,
still open, open items, next steps, follow-ups, to-dos, pending, parked, and
the like) and hold no no, none, nothing, nobody, or zero.

Fences, HTML blocks, quoted lines, and code spans are left out of both checks.

The typed prompt can ask for either shape. Before the ask check, the prompt
loses its ``<system-reminder>`` blocks, its ``>`` quoted lines, its code
spans, and any double-quoted text that holds a space. An ask counts unless a
negator (no, not, never, none, nothing, without, don't, do not, no need,
never mind) comes before it in its clause; clauses end at ``. ! ? ; ,``, a
line break, or the word "then". A prompt that opens with a harness envelope,
such as ``<task-notification>``, never asks::

    exempts the promise:  "report back when the run ends"
    exempts the promise:  "don't stop until it is merged, then give me a summary"
    exempts the list:     "list the deferred items as bullets"
    no exemption:         "no report needed, just finish"
    no exemption:         "no list please, ask me instead"
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import NamedTuple

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)
blocking_directory = str(Path(__file__).resolve().parent)
if blocking_directory not in sys.path:
    sys.path.insert(0, blocking_directory)

from final_reply_gate import blocks_masked, prose_paragraphs
from hooks_constants.final_reply_gate_constants import (
    ALL_HTML_BLOCK_CLOSER_PATTERNS,
    CARRIAGE_RETURN_LINE_BREAK,
    HTML_BLOCK_OPENER_PATTERN,
    LINE_BREAK,
)
from hooks_constants.open_tasks_stop_gate_constants import (
    ALL_ASK_ONLY_ENVELOPE_MARKERS,
    ALL_PROMISED_REPORT_PATTERNS,
    ASK_NEGATOR_PATTERN,
    BACKTICK_TEXT_PATTERN,
    ALL_INDENTED_LINE_PREFIXES,
    LEAD_NEGATOR_PATTERN,
    LIST_ASK_PATTERN,
    OPEN_ITEM_LEAD_PATTERN,
    OPEN_ITEM_LIST_MINIMUM,
    PROMISE_NEGATOR_PATTERN,
    PROMPT_CLAUSE_SPLIT_PATTERN,
    QUOTED_PROMPT_LINE_PATTERN,
    QUOTED_REPLY_LINE_PATTERN,
    REMOVED_PROMPT_TEXT,
    REPLY_SENTENCE_END_PATTERN,
    REPORT_ASK_PATTERN,
    SPACED_QUOTE_PATTERN,
)
from hooks_constants.question_brief_gate_constants import (
    TABLE_ROW_LINE_PATTERN,
    TABLE_SEPARATOR_LINE_PATTERN,
)
from hooks_constants.spawn_readiness_hook_constants import ALL_HARNESS_ENVELOPE_MARKERS
from open_task_asks import prompt_without_reminders
from question_brief_gate import is_item_line, lines_outside_code_fences


class OpenItemList(NamedTuple):
    """A run of open items in a closing reply: the lead line above it, and how many items it holds."""

    lead: str
    count: int


def _prompt_asks_for(prompt_text: str, ask_pattern: re.Pattern[str]) -> bool:
    stripped_text = prompt_without_reminders(prompt_text)
    if stripped_text.startswith((*ALL_HARNESS_ENVELOPE_MARKERS, *ALL_ASK_ONLY_ENVELOPE_MARKERS)):
        return False
    cleaned_text = QUOTED_PROMPT_LINE_PATTERN.sub(REMOVED_PROMPT_TEXT, stripped_text)
    cleaned_text = BACKTICK_TEXT_PATTERN.sub(REMOVED_PROMPT_TEXT, cleaned_text)
    cleaned_text = SPACED_QUOTE_PATTERN.sub(REMOVED_PROMPT_TEXT, cleaned_text)
    return any(
        ASK_NEGATOR_PATTERN.search(each_clause[: each_ask.start()]) is None
        for each_clause in PROMPT_CLAUSE_SPLIT_PATTERN.split(cleaned_text)
        for each_ask in ask_pattern.finditer(each_clause)
    )


def _sentence_before(paragraph_text: str, match_start: int) -> str:
    all_sentence_ends = list(REPLY_SENTENCE_END_PATTERN.finditer(paragraph_text, 0, match_start))
    sentence_start = all_sentence_ends[-1].end() if all_sentence_ends else 0
    return paragraph_text[sentence_start:match_start]


def promised_report_phrase(reply_text: str, prompt_text: str) -> str | None:
    """Return the words in the closing reply that promise the user a later report, or None.

    ::

        "A full write-up will be here when you are back."  -> "when you are back"
        "I'll report back once CI ends."                   -> "I'll report back"
        "No report will follow."                           -> None
        the promise, after the prompt "report back when the run ends" -> None

    Args:
        reply_text: The closing reply the turn ends with.
        prompt_text: The prompt that started the turn.

    Returns:
        The matched promise, or None when the reply holds none or the prompt asked for a report.
    """
    if _prompt_asks_for(prompt_text, REPORT_ASK_PATTERN):
        return None
    for each_paragraph in prose_paragraphs(reply_text):
        for each_pattern in ALL_PROMISED_REPORT_PATTERNS:
            for each_match in each_pattern.finditer(each_paragraph):
                if (
                    PROMISE_NEGATOR_PATTERN.search(
                        _sentence_before(each_paragraph, each_match.start())
                    )
                    is None
                ):
                    return each_match.group()
    return None


def _html_block_closer_for(opener: re.Match[str]) -> re.Pattern[str]:
    return ALL_HTML_BLOCK_CLOSER_PATTERNS[opener.lastgroup or ""]


def _is_run_line(line: str, next_line: str) -> bool:
    if QUOTED_REPLY_LINE_PATTERN.match(line):
        return False
    return is_item_line(line, next_line) or bool(
        TABLE_ROW_LINE_PATTERN.match(line) or TABLE_SEPARATOR_LINE_PATTERN.match(line)
    )


def _is_run_continuation(line: str) -> bool:
    return not line.strip() or line.startswith(ALL_INDENTED_LINE_PREFIXES)


def _item_run_at(all_lines: list[str], run_start: int) -> tuple[int, int]:
    item_count = 0
    line_index = run_start
    while line_index < len(all_lines):
        line = all_lines[line_index]
        next_line = all_lines[line_index + 1] if line_index + 1 < len(all_lines) else ""
        if _is_run_line(line, next_line):
            item_count += is_item_line(line, next_line)
        elif not _is_run_continuation(line):
            break
        line_index += 1
    return line_index, item_count


def _lead_above(all_lines: list[str], run_start: int) -> str:
    return next(
        (each_line.strip() for each_line in reversed(all_lines[:run_start]) if each_line.strip()),
        "",
    )


def _reply_lines(reply_text: str) -> list[str]:
    line_feed_text = reply_text.replace(CARRIAGE_RETURN_LINE_BREAK, LINE_BREAK)
    return lines_outside_code_fences(
        blocks_masked(line_feed_text, HTML_BLOCK_OPENER_PATTERN, _html_block_closer_for)
    )


def _is_open_item_lead(lead: str) -> bool:
    return (
        OPEN_ITEM_LEAD_PATTERN.search(lead) is not None
        and LEAD_NEGATOR_PATTERN.search(lead) is None
    )


def open_item_list(reply_text: str, prompt_text: str) -> OpenItemList | None:
    """Return the first run of 3 or more open items under an open-item lead in the closing reply, or None.

    ::

        "What I deferred:" over 5 numbered lines     -> OpenItemList("What I deferred:", 5)
        "Open items:" over a table with 3 body rows  -> OpenItemList("Open items:", 3)
        "Changed files:" over 5 bullets              -> None
        "Nothing deferred." over 3 bullets           -> None
        the list, after the prompt "list the deferred items as bullets" -> None

    Args:
        reply_text: The closing reply the turn ends with.
        prompt_text: The prompt that started the turn.

    Returns:
        The lead and the item count, or None when no run qualifies or the prompt asked for a list.
    """
    if _prompt_asks_for(prompt_text, LIST_ASK_PATTERN):
        return None
    all_lines = _reply_lines(reply_text)
    line_index = 0
    while line_index < len(all_lines):
        next_line = all_lines[line_index + 1] if line_index + 1 < len(all_lines) else ""
        if not _is_run_line(all_lines[line_index], next_line):
            line_index += 1
            continue
        run_end, item_count = _item_run_at(all_lines, line_index)
        lead = _lead_above(all_lines, line_index)
        if item_count >= OPEN_ITEM_LIST_MINIMUM and _is_open_item_lead(lead):
            return OpenItemList(lead, item_count)
        line_index = run_end
    return None
