#!/usr/bin/env python3
"""Stop hook that checks the closing chat reply for an unvalidated claim.

The reply length gate checks the chat tools. This gate checks the reply the
session ends its turn with, which reaches the user with no tool call::

    flag: My guess is one to two hours.
    flag: I didn't confirm this one.
    flag: Run 18239174012 passed.        (no tool result shows the run)
    ok:   Run 18239174012 took 39 minutes. (a tool result shows the run)

It applies the banned words, the unvalidated claim pattern, and the cited
run, job, check, and pull request numbers from ``reply_length_gate.py``. The
citation check is skipped when the transcript cannot be read. It also flags
a path outside code whose backslash the terminal drops, such as
``D:\\Reports\\.claude``. A block sends
the reason back so the model rewrites the reply. Claude Code ends the turn
after eight blocks in a row.
"""

from __future__ import annotations

import bisect
import json
import sys
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)

from reply_length_gate import (
    banned_word_violation,
    configured_banned_words,
    unseen_citation_violation,
    unvalidated_claim_violation,
)
from hooks_constants.hook_block_logger import log_hook_block
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
from hooks_constants.final_reply_gate_constants import (
    ALLOW_EXIT_CODE,
    BACKSLASH,
    BACKSLASHES_PER_LITERAL,
    BACKTICK_RUN_PATTERN,
    BLOCK_BOUNDARY_PATTERN,
    BLOCK_DECISION,
    CARRIAGE_RETURN_LINE_BREAK,
    DECISION_KEY,
    ESCAPED_PUNCTUATION_PATTERN,
    FENCED_CODE_PATTERN,
    HARD_BREAK_PATTERN,
    HEADING_AS_OWN_BLOCK,
    HEADING_LINE_PATTERN,
    HOOK_EVENT_NAME,
    LAST_ASSISTANT_MESSAGE_KEY,
    LINE_BREAK,
    MASKED_CODE_TEXT,
    NON_SPACE_TOKEN_PATTERN,
    PARAGRAPH_SEPARATOR,
    REASON_KEY,
    REWRITE_INSTRUCTION,
    TRANSCRIPT_PATH_KEY,
    WINDOWS_PATH_MESSAGE,
)


def _unescaped_start(paragraph_text: str, run_start: int) -> int:
    backslash_start = run_start
    while backslash_start > 0 and paragraph_text[backslash_start - 1] == BACKSLASH:
        backslash_start -= 1
    return run_start + (run_start - backslash_start) % BACKSLASHES_PER_LITERAL


def code_spans_masked(paragraph_text: str) -> str:
    """Return the paragraph with one space where each code span sat.

    A backtick run opens a span unless an odd run of backslashes escapes its
    first backtick. The span closes at the next run of the same length::

        >>> code_spans_masked("see `a\\\\.b` and \\\\`x")
        'see   and \\\\`x'
    """
    all_runs = [each_run.span() for each_run in BACKTICK_RUN_PATTERN.finditer(paragraph_text)]
    all_run_indexes_by_length: dict[int, list[int]] = {}
    for each_index, (each_run_start, each_run_end) in enumerate(all_runs):
        all_run_indexes_by_length.setdefault(each_run_end - each_run_start, []).append(each_index)
    all_masked_pieces: list[str] = []
    copied_up_to = 0
    run_index = 0
    while run_index < len(all_runs):
        run_start, run_end = all_runs[run_index]
        opener_start = _unescaped_start(paragraph_text, run_start)
        same_length_indexes = all_run_indexes_by_length.get(run_end - opener_start, [])
        closer_position = bisect.bisect_right(same_length_indexes, run_index)
        if opener_start == run_end or closer_position == len(same_length_indexes):
            run_index += 1
            continue
        closer_index = same_length_indexes[closer_position]
        all_masked_pieces.extend((paragraph_text[copied_up_to:opener_start], MASKED_CODE_TEXT))
        copied_up_to = all_runs[closer_index][1]
        run_index = closer_index + 1
    all_masked_pieces.append(paragraph_text[copied_up_to:])
    return "".join(all_masked_pieces)


def windows_path_violation(reply_text: str) -> str | None:
    """Return the block reason for a path the terminal renders wrong, or None.

    The terminal reads a backslash before punctuation as a markdown escape
    and drops it. A path outside a code span loses that backslash::

        flag: The report is at D:\\Reports\\.claude\\report.html now.
              (the terminal shows D:\\Reports.claude\\report.html)
        flag: Open D:\\Shared Files\\.claude\\x.html now.
        ok:   The report is at `D:\\Reports\\.claude\\report.html` now.
        ok:   The report is at D:\\Reports\\report.html now.
    """
    line_feed_text = reply_text.replace(CARRIAGE_RETURN_LINE_BREAK, LINE_BREAK)
    unfenced_text = HEADING_LINE_PATTERN.sub(
        HEADING_AS_OWN_BLOCK, FENCED_CODE_PATTERN.sub(MASKED_CODE_TEXT, line_feed_text)
    )
    prose_text = PARAGRAPH_SEPARATOR.join(
        code_spans_masked(each_paragraph)
        for each_paragraph in BLOCK_BOUNDARY_PATTERN.split(unfenced_text)
    )
    for each_token_match in NON_SPACE_TOKEN_PATTERN.finditer(prose_text):
        token_text = each_token_match.group()
        is_line_end = prose_text.startswith(LINE_BREAK, each_token_match.end())
        is_hard_break = is_line_end and HARD_BREAK_PATTERN.search(token_text) is not None
        if is_hard_break or ESCAPED_PUNCTUATION_PATTERN.search(token_text) is not None:
            return WINDOWS_PATH_MESSAGE.format(path=token_text)
    return None


def final_reply_violation(reply_text: str, transcript_path: object) -> str | None:
    """Return the block reason for the closing reply, or None when it passes."""
    return (
        banned_word_violation(reply_text, configured_banned_words())
        or unvalidated_claim_violation(reply_text)
        or unseen_citation_violation(reply_text, transcript_path)
        or windows_path_violation(reply_text)
    )


def main() -> int:
    hook_input = read_hook_input_dictionary_from_stdin()
    if hook_input is None:
        return ALLOW_EXIT_CODE
    reply_text = hook_input.get(LAST_ASSISTANT_MESSAGE_KEY)
    if not isinstance(reply_text, str):
        return ALLOW_EXIT_CODE
    violation = final_reply_violation(reply_text, hook_input.get(TRANSCRIPT_PATH_KEY))
    if violation is None:
        return ALLOW_EXIT_CODE
    block_reason = violation + REWRITE_INSTRUCTION
    log_hook_block(
        Path(__file__).name, HOOK_EVENT_NAME, block_reason, offending_input_preview=reply_text
    )
    sys.stdout.write(json.dumps({DECISION_KEY: BLOCK_DECISION, REASON_KEY: block_reason}))
    return ALLOW_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())
