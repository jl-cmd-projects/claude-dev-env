"""Find the open-item lines and the declaration line in the texts the closing question round gate reads.

An open-item line comes from a text block of an assistant record in the
stretch, or from the closing reply. Fences, HTML blocks, quoted paragraphs,
and code spans are left out first, as
``final_reply_gate.prose_paragraphs_with_code_as`` does, and indented code
blocks before that. Each paragraph is matched with its single line breaks
folded to spaces, so "out of" at a line end and "scope" on the next line is
one marker. The line, or the lines joined by a space, that a marker spans is
quoted. A line that ends with a question mark, after trailing markup, is an
open-item line too. The markers, read with case folding and as whole words::

    deferred, defer, defers, deferring, deferral, deferrals
    follow-up, followup, and their plurals
    a, the, another, or one, then "follow up" or "follow ups"
    "follow up", then pr, pull request, issue, task, ticket, change, or commit
    parked, out of scope or out-of-scope, not covered, for later
    later pull request, later pr, separate pr, separate pull request
    known gap, known limitation, and their plurals
    open question, open questions
    unresolved, uncertain, uncertainty, not sure, unsure, unclear
    I assumed, we assumed, I assume, we assume, assuming, assumption,
        assumptions
    unverified, could not verify, couldn't verify, did not verify
    untested, not tested, didn't test, did not test
    could not confirm, couldn't confirm, unable to confirm
    not yet implemented
    judgment call, judgement call, and their plurals
    your call, up to you, you may want to, your judgment, your judgement
    needs your decision, judgment, judgement, or approval
    need your input, needs your input, I need you to
    pending, TODO, TBD, skipped, skipping, not done, blocked
    not run, didn't run, could not reproduce, couldn't reproduce
    left it, this, that, them, or these, then "for you"
    for you to decide, waiting on you, waits on you

A straight or a curly apostrophe reads the same. The verb in "I will follow
up with the build" is no marker. A negation does not cancel a marker, so
"Nothing is deferred." is held; a wrong hold costs one card.

An indented code block is a run of lines indented by four spaces or a tab
that starts after a blank line, or at the start of the text, outside a list
item. A list item runs from its marker line until a line at the left margin
starts a paragraph after a blank line, so an indented paragraph inside it is
read as prose. Its lines read as blank. A text over 2 MiB is skipped.
Before matching, each run of two or more spaces, line breaks, or hyphens
reads as one character: a hyphen for a run of hyphens alone, a space for any
other run. No marker match is then longer than 128 characters. A paragraph
is matched in windows of 1 Mi characters that overlap by 128, so the clock
is read between windows. Each window also reads the 4 characters after it,
so the whole-word check sees past the window's end. A match that ends at the
end of a window before the paragraph's end is dropped, and the next window
reads it whole. A marker reads as a whole word, and one to three underscores
around it count as emphasis, so ``_untested_`` and ``__untested__`` are
markers, and ``retry_untested_flag`` and ``retry__untested__flag`` are none.
"""

from __future__ import annotations

import bisect
import itertools
import sys
from collections.abc import Iterator
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)
blocking_directory = str(Path(__file__).resolve().parent)
if blocking_directory not in sys.path:
    sys.path.insert(0, blocking_directory)

from closing_question_round_lines import before_deadline, is_within_scan_cap
from final_reply_gate import prose_paragraphs_with_code_as
from hooks_constants.closing_question_round_gate_constants import (
    DECLARATION_LINE_PATTERN,
    INDENTED_CODE_LINE_PATTERN,
    LIST_ITEM_LINE_PATTERN,
    HYPHEN_CHARACTER,
    MARKER_SCAN_LOOKAHEAD_CHARACTERS,
    MARKER_SCAN_OVERLAP_CHARACTERS,
    MARKER_SCAN_WINDOW_CHARACTERS,
    OPEN_ITEM_MARKER_PATTERN,
    SEPARATOR_RUN_PATTERN,
)
from hooks_constants.final_reply_gate_constants import QUESTION_MARK, TRAILING_MARKUP_CHARACTERS
from hooks_constants.open_tasks_stop_gate_constants import WORD_SEPARATOR
from hooks_constants.user_step_wording_constants import CODE_SPAN_STAND_IN, LINE_BREAK


def _is_list_context(each_line: str, was_list_context: bool, previous_line: str) -> bool:
    if LIST_ITEM_LINE_PATTERN.match(each_line):
        return True
    starts_a_paragraph = bool(each_line.strip()) and not previous_line.strip()
    return was_list_context and not (starts_a_paragraph and each_line == each_line.lstrip())


def indented_code_masked(reply_text: str, deadline_at: float) -> str:
    """Return the text with each line of an indented code block read as blank.

    ::

        "Run this:\\n\\n    retry --deferred\\n\\nDone."  -> "Run this:\\n\\n\\n\\nDone."
        "- Item\\n\\n    The retry is untested."           -> unchanged, a list continuation
        "One line\\n    more deferred text"               -> unchanged, no blank line before it

    A block starts at a line indented by four spaces or a tab after a blank
    line or the text start, outside a list, and runs over indented and blank
    lines. The clock is read before each line, and TimeoutError is raised
    once it reaches ``deadline_at``.
    """
    all_kept_lines: list[str] = []
    is_list_context = False
    is_inside_code = False
    previous_line = ""
    for each_line in before_deadline(reply_text.split(LINE_BREAK), deadline_at):
        is_indented = bool(INDENTED_CODE_LINE_PATTERN.match(each_line))
        is_blank = not each_line.strip()
        if is_inside_code:
            is_inside_code = is_indented or is_blank
        else:
            is_inside_code = is_indented and not previous_line.strip() and not is_list_context
        is_list_context = _is_list_context(each_line, is_list_context, previous_line)
        all_kept_lines.append("" if is_inside_code else each_line)
        previous_line = each_line
    return LINE_BREAK.join(all_kept_lines)


def _collapsed_separators(
    folded_text: str, deadline_at: float
) -> tuple[str, list[int], list[int]]:
    all_parts: list[str] = []
    all_collapsed_offsets: list[int] = []
    all_original_offsets: list[int] = []
    collapsed_length = 0
    copied_until = 0
    all_runs = SEPARATOR_RUN_PATTERN.finditer(folded_text)
    for each_run in before_deadline(all_runs, deadline_at):
        is_hyphen_run = not each_run.group().strip(HYPHEN_CHARACTER)
        all_parts.append(folded_text[copied_until : each_run.start()])
        collapsed_length += each_run.start() - copied_until
        all_parts.append(HYPHEN_CHARACTER if is_hyphen_run else WORD_SEPARATOR)
        all_collapsed_offsets.extend((collapsed_length, collapsed_length + 1))
        all_original_offsets.extend((each_run.start(), each_run.end()))
        collapsed_length += 1
        copied_until = each_run.end()
    all_parts.append(folded_text[copied_until:])
    return "".join(all_parts), all_collapsed_offsets, all_original_offsets


def _original_position(
    collapsed_position: int, all_collapsed_offsets: list[int], all_original_offsets: list[int]
) -> int:
    offset_index = bisect.bisect_right(all_collapsed_offsets, collapsed_position) - 1
    if offset_index < 0:
        return collapsed_position
    return all_original_offsets[offset_index] + collapsed_position - all_collapsed_offsets[offset_index]


def _collapsed_marker_spans(collapsed_text: str, deadline_at: float) -> Iterator[tuple[int, int]]:
    all_window_starts = range(0, max(len(collapsed_text), 1), MARKER_SCAN_WINDOW_CHARACTERS)
    for each_window_start in before_deadline(all_window_starts, deadline_at):
        window_end = each_window_start + MARKER_SCAN_WINDOW_CHARACTERS + MARKER_SCAN_OVERLAP_CHARACTERS
        scan_end = window_end + MARKER_SCAN_LOOKAHEAD_CHARACTERS
        all_window_matches = OPEN_ITEM_MARKER_PATTERN.finditer(
            collapsed_text, each_window_start, scan_end
        )
        yield from (
            each_match.span()
            for each_match in all_window_matches
            if each_match.end() < window_end or scan_end >= len(collapsed_text)
        )


def _marker_spans(folded_text: str, deadline_at: float) -> Iterator[tuple[int, int]]:
    collapsed_text, all_collapsed_offsets, all_original_offsets = _collapsed_separators(
        folded_text, deadline_at
    )
    for each_marker_start, each_marker_end in _collapsed_marker_spans(collapsed_text, deadline_at):
        yield (
            _original_position(each_marker_start, all_collapsed_offsets, all_original_offsets),
            _original_position(each_marker_end - 1, all_collapsed_offsets, all_original_offsets) + 1,
        )


def _paragraph_quotes(paragraph_text: str, deadline_at: float) -> list[str]:
    all_lines = paragraph_text.split(LINE_BREAK)
    all_line_starts = list(
        itertools.accumulate((len(each_line) + 1 for each_line in all_lines[:-1]), initial=0)
    )
    folded_text = paragraph_text.replace(LINE_BREAK, WORD_SEPARATOR)
    all_line_ranges = {
        (
            bisect.bisect_right(all_line_starts, marker_start) - 1,
            bisect.bisect_right(all_line_starts, marker_end - 1) - 1,
        )
        for marker_start, marker_end in _marker_spans(folded_text, deadline_at)
    }
    all_line_ranges.update(
        (each_position, each_position)
        for each_position, each_line in enumerate(before_deadline(all_lines, deadline_at))
        if each_line.rstrip(TRAILING_MARKUP_CHARACTERS).endswith(QUESTION_MARK)
    )
    return [
        WORD_SEPARATOR.join(each_line.strip() for each_line in all_lines[first : last + 1])
        for first, last in sorted(all_line_ranges)
    ]


def _prose_paragraphs(reply_text: str, deadline_at: float) -> list[str]:
    return prose_paragraphs_with_code_as(
        indented_code_masked(reply_text, deadline_at), CODE_SPAN_STAND_IN
    )


def _marked_lines(reply_text: str, deadline_at: float) -> list[str]:
    return [
        each_quote
        for each_paragraph in before_deadline(
            _prose_paragraphs(reply_text, deadline_at), deadline_at
        )
        for each_quote in _paragraph_quotes(each_paragraph, deadline_at)
    ]


def marked_open_lines(all_assistant_texts: list[str], deadline_at: float) -> list[str]:
    """Return each open-item line of the assistant texts, once, in order.

    ::

        "The flag is in place.\\nThe retry path is untested."  -> ["The retry path is untested."]
        "The cleanup is out of\\nscope."                        -> ["The cleanup is out of scope."]
        "Should the cache hold 64 entries?"                    -> ["Should the cache hold 64 entries?"]
        "Nothing is deferred."                                 -> ["Nothing is deferred."]
        "The status is `deferred`."                            -> []

    A marker that spans a line break is quoted as its lines joined by a
    space. Each code span in a returned line reads as U+FFFC. A text over 2
    MiB is skipped.

    Args:
        all_assistant_texts: The assistant text blocks of the stretch, then the closing reply.
        deadline_at: The monotonic clock reading at which the scan gives up.

    Returns:
        The open-item lines, without repeats.

    Raises:
        TimeoutError: The deadline passed before the scan ended, read before
            each text, paragraph, line, and marker scan window.
    """
    all_marked_lines = (
        each_line
        for each_text in before_deadline(all_assistant_texts, deadline_at)
        if is_within_scan_cap(each_text)
        for each_line in _marked_lines(each_text, deadline_at)
    )
    return list(dict.fromkeys(all_marked_lines))


def declares_no_open_items(closing_reply: str, deadline_at: float) -> bool:
    """Return True when the reply's last prose line is the declaration ``Open items: none.``.

    ::

        "Both tests pass.\\n\\nOpen items: none."      -> True
        "Both tests pass.\\n\\n**Open items: none.**"  -> True
        "Open items: none.\\n\\nBoth tests pass."      -> False
        "`Open items: none.`"                        -> False, a code span
        "- Open items: none."                        -> False, a list item
        "Open items: none"                           -> True, no period

    The reply is masked as ``marked_open_lines`` masks it. Its last non-empty
    line, with outer spaces stripped, must be the declaration alone or the
    declaration wrapped in one bold or italic mark. The final period may be
    left out. A ``* `` list item does not
    count. A reply over 2 MiB never declares. The masking
    raises TimeoutError once the clock reaches ``deadline_at``.
    """
    if not is_within_scan_cap(closing_reply):
        return False
    all_paragraphs = _prose_paragraphs(closing_reply, deadline_at)
    if not all_paragraphs:
        return False
    all_lines = [
        each_line for each_line in all_paragraphs[-1].split(LINE_BREAK) if each_line.strip()
    ]
    last_line = all_lines[-1].strip() if all_lines else ""
    return DECLARATION_LINE_PATTERN.fullmatch(last_line) is not None
