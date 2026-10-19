#!/usr/bin/env python3
"""PreToolUse hook that keeps every session title in the '<emoji> <name>' shape.

The gate reads the title a tool whose name ends in __set_session_title is about
to set. It denies the call when the title breaks one of these rules:

- It starts with one status emoji (red flag, check mark or hourglass) and a space.
- It is one line.
- The name after the emoji has 1 to 25 characters.
- It ends without punctuation.
- The name starts with a capital letter.
- The name holds no run of three or more digits and no slash.

A call with no string title passes, so a tool with another schema keeps working.
"""

from __future__ import annotations

import sys
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)

from hooks_constants.hook_block_logger import log_hook_block
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
from hooks_constants.session_title_constants import (
    ALLOW_EXIT_CODE,
    BLOCK_EXIT_CODE,
    BRANCH_NAME_MESSAGE,
    FORMAT_GATE_EVENT_NAME,
    FORMAT_RETRY_INSTRUCTION,
    IDENTIFIER_DIGITS_PATTERN,
    IDENTIFIER_MESSAGE,
    MAXIMUM_NAME_LENGTH,
    NAME_LENGTH_MESSAGE,
    SENTENCE_CASE_MESSAGE,
    SINGLE_LINE_MESSAGE,
    STATUS_PREFIX_MESSAGE,
    STATUS_PREFIX_PATTERN,
    TITLE_INPUT_KEY,
    TITLE_TOOL_NAME_PATTERN,
    TOOL_INPUT_KEY,
    TOOL_NAME_KEY,
    TRAILING_PUNCTUATION,
    TRAILING_PUNCTUATION_MESSAGE,
)


def _name_violation(name: str) -> str | None:
    if name != name.strip() or not 1 <= len(name) <= MAXIMUM_NAME_LENGTH:
        return NAME_LENGTH_MESSAGE.format(maximum=MAXIMUM_NAME_LENGTH, length=len(name.strip()))
    if name[-1] in TRAILING_PUNCTUATION:
        return TRAILING_PUNCTUATION_MESSAGE
    if name[0].isalpha() and not name[0].isupper():
        return SENTENCE_CASE_MESSAGE
    if IDENTIFIER_DIGITS_PATTERN.search(name):
        return IDENTIFIER_MESSAGE
    if "/" in name:
        return BRANCH_NAME_MESSAGE
    return None


def title_format_violation(title: str) -> str | None:
    """Return the first rule a session title breaks, or None when it is well formed.

    >>> title_format_violation("\u23f3 Broker gate + replay rule") is None
    True
    >>> title_format_violation("Broker gate") == STATUS_PREFIX_MESSAGE
    True

    Args:
        title: The title the tool call would set.

    Returns:
        The message for the broken rule, or None.
    """
    if "\n" in title or "\r" in title:
        return SINGLE_LINE_MESSAGE
    status_prefix = STATUS_PREFIX_PATTERN.match(title)
    if status_prefix is None:
        return STATUS_PREFIX_MESSAGE
    return _name_violation(title[status_prefix.end() :])


def main() -> int:
    hook_input = read_hook_input_dictionary_from_stdin()
    if hook_input is None:
        return ALLOW_EXIT_CODE
    tool_name = hook_input.get(TOOL_NAME_KEY)
    if not isinstance(tool_name, str) or not TITLE_TOOL_NAME_PATTERN.match(tool_name):
        return ALLOW_EXIT_CODE
    tool_input = hook_input.get(TOOL_INPUT_KEY)
    title = tool_input.get(TITLE_INPUT_KEY) if isinstance(tool_input, dict) else None
    if not isinstance(title, str):
        return ALLOW_EXIT_CODE
    violation = title_format_violation(title)
    if violation is None:
        return ALLOW_EXIT_CODE
    block_reason = violation + FORMAT_RETRY_INSTRUCTION
    log_hook_block(
        Path(__file__).name,
        FORMAT_GATE_EVENT_NAME,
        block_reason,
        tool_name=tool_name,
        offending_input_preview=title,
    )
    sys.stderr.write(block_reason)
    return BLOCK_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())
