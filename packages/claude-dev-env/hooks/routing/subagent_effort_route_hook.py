#!/usr/bin/env python3
"""PreToolUse hook: give an Agent or Task spawn an allowed effort.

Registered on ``Agent|Task``. It applies the Subagent model and effort rule:
Opus runs at medium, Sonnet at high, Fable at low to high, and Haiku at any
effort. A spawn that names no model takes the family of the session's last
assistant model from the transcript.

::

    model "opus", effort "xhigh"        -> updatedInput with effort "medium"
    model "sonnet", no effort           -> updatedInput with effort "high"
    model "haiku", effort "max"         -> no output
    subagent_type "fork"                -> no output
    no model, unreadable transcript     -> no output
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)
routing_directory = str(Path(__file__).resolve().parent)
if routing_directory not in sys.path:
    sys.path.insert(0, routing_directory)

from hooks_constants.bash_pre_tool_use_dispatcher_constants import HOOK_EVENT_NAME
from hooks_constants.hook_specific_output_keys import (
    HOOK_EVENT_NAME_KEY,
    HOOK_SPECIFIC_OUTPUT_KEY,
    UPDATED_INPUT_KEY,
)
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
from hooks_constants.subagent_effort_route_constants import (
    ADDITIONAL_CONTEXT_KEY,
    MODEL_INPUT_KEY,
    ROUTED_CONTEXT_TEMPLATE,
    TOOL_INPUT_KEY,
    TRANSCRIPT_ASSISTANT_TYPE,
    TRANSCRIPT_ENTRY_TYPE_KEY,
    TRANSCRIPT_MESSAGE_KEY,
    TRANSCRIPT_PATH_KEY,
    TRANSCRIPT_TAIL_BYTES,
)
from subagent_effort_route import route_spawn_input


def last_assistant_model(transcript_path: object) -> str | None:
    """Return the model of the transcript's last assistant entry.

    Args:
        transcript_path: The payload's ``transcript_path``.

    Returns:
        The model id, or None when the file is missing, unreadable, or holds
        no assistant entry with a model.
    """
    if not isinstance(transcript_path, str) or not transcript_path:
        return None
    try:
        with open(transcript_path, "rb") as transcript_file:
            transcript_file.seek(0, 2)
            file_size = transcript_file.tell()
            transcript_file.seek(max(0, file_size - TRANSCRIPT_TAIL_BYTES))
            tail_text = transcript_file.read().decode("utf-8", errors="replace")
    except OSError:
        return None
    for each_line in reversed(tail_text.splitlines()):
        try:
            entry = json.loads(each_line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict) or entry.get(TRANSCRIPT_ENTRY_TYPE_KEY) != TRANSCRIPT_ASSISTANT_TYPE:
            continue
        message = entry.get(TRANSCRIPT_MESSAGE_KEY)
        if isinstance(message, dict) and isinstance(message.get(MODEL_INPUT_KEY), str):
            return message[MODEL_INPUT_KEY]
    return None


def decide_hook_output(hook_payload: dict[str, object] | None) -> dict[str, object] | None:
    """Choose the hook output for one spawn payload.

    Args:
        hook_payload: The PreToolUse payload, or None when stdin held no object.

    Returns:
        None to pass the call through unchanged, else the hook JSON output.
    """
    if hook_payload is None:
        return None
    routed = route_spawn_input(
        hook_payload.get(TOOL_INPUT_KEY),
        last_assistant_model(hook_payload.get(TRANSCRIPT_PATH_KEY)),
    )
    if routed is None:
        return None
    routed_input, family, effort = routed
    return {
        HOOK_SPECIFIC_OUTPUT_KEY: {
            HOOK_EVENT_NAME_KEY: HOOK_EVENT_NAME,
            UPDATED_INPUT_KEY: routed_input,
            ADDITIONAL_CONTEXT_KEY: ROUTED_CONTEXT_TEMPLATE.format(family=family, effort=effort),
        }
    }


def main() -> int:
    """Read the PreToolUse payload and print the routing decision.

    Returns:
        0 in every case.
    """
    hook_output = decide_hook_output(read_hook_input_dictionary_from_stdin())
    if hook_output is not None:
        sys.stdout.write(json.dumps(hook_output))
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
