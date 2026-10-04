#!/usr/bin/env python3
"""PreToolUse hook: run every Agent and Task subagent on Opus.

Registered on ``Agent|Task``. Nested spawns pass through the same hook, so the
pin holds at every level.

::

    model omitted           -> allow with updatedInput model "opus"
    model sonnet or haiku   -> allow with updatedInput model "opus"
    model opus or fable     -> no output; the call runs unchanged

A model id counts by its family: ``claude-sonnet-5-5`` is sonnet. A fork
ignores the model field, so the rewrite leaves it unchanged.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)

from hooks_constants.bash_pre_tool_use_dispatcher_constants import (
    ALLOW_DECISION,
    HOOK_EVENT_NAME,
)
from hooks_constants.pre_tool_use_allow_output import (
    HOOK_EVENT_NAME_KEY,
    HOOK_SPECIFIC_OUTPUT_KEY,
    PERMISSION_DECISION_KEY,
    UPDATED_INPUT_KEY,
)
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
from hooks_constants.subagent_model_pin_hook_constants import (
    ADDITIONAL_CONTEXT_KEY,
    ALL_MOVED_MODEL_FAMILIES,
    CONTEXT_OMITTED_MODEL_TEXT,
    CONTEXT_PREFIX,
    CONTEXT_SUFFIX,
    MODEL_INPUT_KEY,
    SUBAGENT_MODEL_ALIAS,
    TOOL_INPUT_KEY,
)


def is_moved_model(model: object) -> bool:
    """Return True when the spawn names no model or a model family the pin moves.

    ::

        None -> True        "sonnet" -> True     "claude-haiku-4-5-20251001" -> True
        "opus" -> False     "claude-fable-5-1" -> False

    Args:
        model: The ``model`` field of the spawn input.
    """
    if model is None or model == "":
        return True
    if not isinstance(model, str):
        return False
    lowered_model = model.lower()
    return any(each_family in lowered_model for each_family in ALL_MOVED_MODEL_FAMILIES)


def decide_hook_output(tool_input: object) -> dict[str, object] | None:
    """Choose the hook's output for one subagent spawn.

    Args:
        tool_input: The ``tool_input`` of the PreToolUse payload.

    Returns:
        None to pass the call through unchanged, else the hook JSON output.
    """
    if not isinstance(tool_input, dict):
        return None
    requested_model = tool_input.get(MODEL_INPUT_KEY)
    if not is_moved_model(requested_model):
        return None
    previous_model_text = requested_model or CONTEXT_OMITTED_MODEL_TEXT
    return {
        HOOK_SPECIFIC_OUTPUT_KEY: {
            HOOK_EVENT_NAME_KEY: HOOK_EVENT_NAME,
            PERMISSION_DECISION_KEY: ALLOW_DECISION,
            UPDATED_INPUT_KEY: {**tool_input, MODEL_INPUT_KEY: SUBAGENT_MODEL_ALIAS},
            ADDITIONAL_CONTEXT_KEY: f"{CONTEXT_PREFIX}{previous_model_text}{CONTEXT_SUFFIX}",
        }
    }


def main() -> int:
    """Read the PreToolUse payload and print the decision.

    Returns:
        0 in every case.
    """
    hook_payload = read_hook_input_dictionary_from_stdin()
    tool_input = hook_payload.get(TOOL_INPUT_KEY) if hook_payload is not None else None
    hook_output = decide_hook_output(tool_input)
    if hook_output is not None:
        sys.stdout.write(json.dumps(hook_output))
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
