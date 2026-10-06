#!/usr/bin/env python3
"""PreToolUse hook that keeps a found defect with the issue that found it.

The gate reads GitHub issue comment and issue write calls. It denies a call
that closes an issue and, in the same text, routes a defect to another issue
or epic. A close comes from a closed state in the call or from closing words
in the text. The session that found the defect fixes it through a pull request
and closes the issue there.
"""

from __future__ import annotations

import sys
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)

from gh_post_body_texts import extract_mcp_body_texts
from hooks_constants.hook_block_logger import log_hook_block
from hooks_constants.issue_close_handoff_gate_constants import (
    ALL_HANDOFF_PATTERNS,
    ALL_ISSUE_TOOL_SUFFIXES,
    ALLOW_EXIT_CODE,
    BLOCK_EXIT_CODE,
    BODY_TEXT_SEPARATOR,
    CLOSE_DECLARATION_PATTERN,
    CLOSED_STATE,
    HANDOFF_CLOSE_MESSAGE,
    HOOK_EVENT_NAME,
    RETRY_INSTRUCTION,
    STATE_KEY,
    TOOL_INPUT_KEY,
    TOOL_NAME_KEY,
)
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin


def is_handoff_close(all_tool_input: dict[str, object]) -> bool:
    """Return True when the call closes an issue and routes a defect elsewhere."""
    body_text = BODY_TEXT_SEPARATOR.join(extract_mcp_body_texts(all_tool_input))
    if not any(each_pattern.search(body_text) for each_pattern in ALL_HANDOFF_PATTERNS):
        return False
    is_closed_state = all_tool_input.get(STATE_KEY) == CLOSED_STATE
    return is_closed_state or CLOSE_DECLARATION_PATTERN.search(body_text) is not None


def main() -> int:
    hook_input = read_hook_input_dictionary_from_stdin()
    if hook_input is None:
        return ALLOW_EXIT_CODE
    tool_name = hook_input.get(TOOL_NAME_KEY)
    if not isinstance(tool_name, str) or not tool_name.endswith(ALL_ISSUE_TOOL_SUFFIXES):
        return ALLOW_EXIT_CODE
    tool_input = hook_input.get(TOOL_INPUT_KEY)
    if not isinstance(tool_input, dict) or not is_handoff_close(tool_input):
        return ALLOW_EXIT_CODE
    block_reason = HANDOFF_CLOSE_MESSAGE + RETRY_INSTRUCTION
    log_hook_block(
        Path(__file__).name,
        HOOK_EVENT_NAME,
        block_reason,
        tool_name=tool_name,
        offending_input_preview=str(tool_input),
    )
    sys.stderr.write(block_reason)
    return BLOCK_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())
