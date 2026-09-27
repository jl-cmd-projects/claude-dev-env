#!/usr/bin/env python3
"""PreToolUse hook that keeps edit markers out of an edited chat message.

The gate reads the whole input of a tool whose name ends in
MESSAGE_EDIT_TOOL_SUFFIX, including the text and any replacement card. It
denies the call when the input holds strikethrough or an "[Edit:" note. The
reader of an edited message sees only its new text, so the model resends
that clean text.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)

from hooks_constants.edit_marker_gate_constants import (
    ALLOW_EXIT_CODE,
    BLOCK_EXIT_CODE,
    EDIT_NOTE_MESSAGE,
    EDIT_NOTE_PATTERN,
    HOOK_EVENT_NAME,
    MESSAGE_EDIT_TOOL_SUFFIX,
    RETRY_INSTRUCTION,
    STRIKETHROUGH_MESSAGE,
    STRIKETHROUGH_PATTERN,
    TOOL_INPUT_KEY,
    TOOL_NAME_KEY,
)
from hooks_constants.hook_block_logger import log_hook_block
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin


def edit_marker_violation(all_tool_input: dict[str, object]) -> str | None:
    """Return the deny reason for an edit that keeps old text, or None when clean."""
    serialized_input = json.dumps(all_tool_input, ensure_ascii=False)
    if STRIKETHROUGH_PATTERN.search(serialized_input):
        return STRIKETHROUGH_MESSAGE
    if EDIT_NOTE_PATTERN.search(serialized_input):
        return EDIT_NOTE_MESSAGE
    return None


def main() -> int:
    hook_input = read_hook_input_dictionary_from_stdin()
    if hook_input is None:
        return ALLOW_EXIT_CODE
    tool_name = hook_input.get(TOOL_NAME_KEY)
    if not isinstance(tool_name, str) or not tool_name.endswith(MESSAGE_EDIT_TOOL_SUFFIX):
        return ALLOW_EXIT_CODE
    tool_input = hook_input.get(TOOL_INPUT_KEY)
    if not isinstance(tool_input, dict):
        return ALLOW_EXIT_CODE
    violation = edit_marker_violation(tool_input)
    if violation is None:
        return ALLOW_EXIT_CODE
    block_reason = violation + RETRY_INSTRUCTION
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
