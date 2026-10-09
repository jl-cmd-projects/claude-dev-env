#!/usr/bin/env python3
"""PreToolUse gate: deny a Haiku agent spawned inside this session.

Registered on ``Agent|Task`` and ``mcp__hearthbot__start_thread_session``. An
in-session spawn shares this session's settings, plugins, MCP servers, and
CLAUDE.md files, so a Haiku agent started that way cannot run on the slim
profile. The deny reason gives the headless command that loads the profile.

::

    model "haiku"                       -> deny with the headless command
    model "claude-haiku-5-5"            -> deny with the headless command
    model "opus", "sonnet", or omitted  -> no output; the call runs unchanged

A spawn that names no model passes, even when the subagent's definition or
``CLAUDE_CODE_SUBAGENT_MODEL`` resolves it to Haiku.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)

from hooks_constants.bash_pre_tool_use_dispatcher_constants import HOOK_EVENT_NAME
from hooks_constants.haiku_spawn_slim_gate_constants import (
    DENY_DECISION,
    HAIKU_MODEL_FAMILY,
    MODEL_INPUT_KEY,
    PERMISSION_DECISION_REASON_KEY,
    SLIM_PROFILE_DENY_REASON,
    TOOL_INPUT_KEY,
)
from hooks_constants.hook_specific_output_keys import (
    HOOK_EVENT_NAME_KEY,
    HOOK_SPECIFIC_OUTPUT_KEY,
    PERMISSION_DECISION_KEY,
)
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin


def is_haiku_model(model: object) -> bool:
    """Return True when the spawn's model field names the Haiku family.

    ::

        "haiku" -> True     "claude-haiku-4-5-20251001" -> True
        "opus" -> False     None -> False

    Args:
        model: The ``model`` field of the spawn input.
    """
    return isinstance(model, str) and HAIKU_MODEL_FAMILY in model.lower()


def decide_hook_output(tool_input: object) -> dict[str, object] | None:
    """Choose the hook's output for one spawn.

    Args:
        tool_input: The ``tool_input`` of the PreToolUse payload.

    Returns:
        None to pass the call through unchanged, else the deny output.
    """
    if not isinstance(tool_input, dict) or not is_haiku_model(tool_input.get(MODEL_INPUT_KEY)):
        return None
    return {
        HOOK_SPECIFIC_OUTPUT_KEY: {
            HOOK_EVENT_NAME_KEY: HOOK_EVENT_NAME,
            PERMISSION_DECISION_KEY: DENY_DECISION,
            PERMISSION_DECISION_REASON_KEY: SLIM_PROFILE_DENY_REASON,
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
