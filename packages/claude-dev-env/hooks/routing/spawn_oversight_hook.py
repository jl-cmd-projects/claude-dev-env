#!/usr/bin/env python3
"""PreToolUse hook: tell the spawning session it owns the work it delegates.

Registered on every tool that starts another agent: ``Agent``, ``Task``,
``Workflow``, ``multi_agent_v1__spawn_agent``,
``mcp__hearthbot__start_thread_session``, and
``mcp__hearthbot__start_rc_session``, plus a workflow dispatch whose inputs
carry a ``prompt`` for an agent. Each spawn gets the oversight directive
as ``additionalContext``, so the spawn runs and keeps its normal permission
flow. A subagent that spawns its own agents gets the same directive, so every
level of the tree oversees the level below it.

::

    Agent {"prompt": "Do X."}        -> additionalContext: the directive
    actions trigger {"method": "run_workflow",
                     "inputs": {"prompt": "Do X."}}
                                     -> additionalContext: the directive
    actions trigger {"method": "cancel_workflow_run"}
                                     -> no output
    Bash {"command": "ls"}           -> no output
    Agent "not an object"            -> no output
"""

from __future__ import annotations

import sys
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)

from hooks_constants.hook_specific_output_keys import (
    HOOK_EVENT_NAME_KEY,
    HOOK_SPECIFIC_OUTPUT_KEY,
)
from hooks_constants.pre_tool_use_context_runner import run_context_hook
from hooks_constants.spawn_oversight_hook_constants import (
    ADDITIONAL_CONTEXT_KEY,
    ALL_SPAWN_TOOL_NAMES,
    DISPATCH_INPUTS_KEY,
    DISPATCH_METHOD_INPUT_KEY,
    DISPATCH_PROMPT_INPUT_KEY,
    DISPATCH_RUN_WORKFLOW_METHOD,
    PRE_TOOL_USE_EVENT_NAME,
    SPAWN_OVERSIGHT_DIRECTIVE,
    TOOL_INPUT_KEY,
    TOOL_NAME_KEY,
    WORKFLOW_DISPATCH_TOOL_NAME,
)


def starts_an_agent(tool_name: object, all_tool_input_fields: dict[str, object]) -> bool:
    """Return True when the call starts an agent: a spawn tool or a prompt dispatch.

    Args:
        tool_name: The tool the session called.
        all_tool_input_fields: The tool input.
    """
    if tool_name in ALL_SPAWN_TOOL_NAMES:
        return True
    if tool_name != WORKFLOW_DISPATCH_TOOL_NAME:
        return False
    if all_tool_input_fields.get(DISPATCH_METHOD_INPUT_KEY) != DISPATCH_RUN_WORKFLOW_METHOD:
        return False
    workflow_inputs = all_tool_input_fields.get(DISPATCH_INPUTS_KEY)
    return isinstance(workflow_inputs, dict) and isinstance(
        workflow_inputs.get(DISPATCH_PROMPT_INPUT_KEY), str
    )


def decide_hook_output(all_hook_fields: dict[str, object]) -> dict[str, object] | None:
    """Return the oversight directive for a spawn call, else None.

    Args:
        all_hook_fields: The parsed PreToolUse payload.
    """
    all_tool_input_fields = all_hook_fields.get(TOOL_INPUT_KEY)
    if not isinstance(all_tool_input_fields, dict):
        return None
    if not starts_an_agent(all_hook_fields.get(TOOL_NAME_KEY), all_tool_input_fields):
        return None
    return {
        HOOK_SPECIFIC_OUTPUT_KEY: {
            HOOK_EVENT_NAME_KEY: PRE_TOOL_USE_EVENT_NAME,
            ADDITIONAL_CONTEXT_KEY: SPAWN_OVERSIGHT_DIRECTIVE,
        }
    }


def main() -> int:
    """Run the hook on the stdin payload; always 0."""
    return run_context_hook(decide_hook_output)


if __name__ == "__main__":
    sys.exit(main())
