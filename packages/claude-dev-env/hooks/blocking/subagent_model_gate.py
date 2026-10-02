#!/usr/bin/env python3
"""PreToolUse hook that denies a subagent spawn on a sonnet or fable model.

The gate reads the ``model`` field of an Agent or Task call. It denies the
call when the model is the ``sonnet`` or ``fable`` alias, or a full id that
starts with ``claude-sonnet`` or ``claude-fable``::

    deny:  {"model": "fable"}
    deny:  {"model": "claude-sonnet-5-5"}
    allow: {"model": "opus"}
    allow: {}

A call with no model inherits the parent session's model and passes.

The owner ruled out sonnet subagents on 2026-09-16 and fable subagents on
2026-10-02, and set opus at medium effort as the spawn default. Skill model
tables that name fable, such as the pstack role defaults, yield to this gate.
"""

from __future__ import annotations

import sys
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)

from hooks_constants.hook_block_logger import log_hook_block
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
from hooks_constants.subagent_model_gate_constants import (
    ALL_CHECKED_TOOL_NAMES,
    ALL_DENIED_MODEL_ALIASES,
    ALL_DENIED_MODEL_ID_PREFIXES,
    ALLOW_EXIT_CODE,
    BLOCK_EXIT_CODE,
    DENY_MESSAGE,
    HOOK_EVENT_NAME,
    MODEL_KEY,
    TOOL_INPUT_KEY,
    TOOL_NAME_KEY,
)


def is_denied_model(model: str) -> bool:
    """Return True for the sonnet or fable alias or a full claude-sonnet or claude-fable id."""
    normalized_model = model.strip().lower()
    return normalized_model in ALL_DENIED_MODEL_ALIASES or normalized_model.startswith(
        ALL_DENIED_MODEL_ID_PREFIXES
    )


def main() -> int:
    hook_input = read_hook_input_dictionary_from_stdin()
    if hook_input is None:
        return ALLOW_EXIT_CODE
    tool_name = hook_input.get(TOOL_NAME_KEY)
    if tool_name not in ALL_CHECKED_TOOL_NAMES:
        return ALLOW_EXIT_CODE
    tool_input = hook_input.get(TOOL_INPUT_KEY)
    if not isinstance(tool_input, dict):
        return ALLOW_EXIT_CODE
    model = tool_input.get(MODEL_KEY)
    if not isinstance(model, str) or not is_denied_model(model):
        return ALLOW_EXIT_CODE
    block_reason = DENY_MESSAGE.format(model=model)
    log_hook_block(
        Path(__file__).name,
        HOOK_EVENT_NAME,
        block_reason,
        tool_name=str(tool_name),
        offending_input_preview=model,
    )
    sys.stderr.write(block_reason)
    return BLOCK_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())
