#!/usr/bin/env python3
"""PreToolUse hook: refuse a task list item whose name is longer than 80 characters.

The user reads the task list to see where things stand and what is left. A
subject that carries evidence and steps turns that list into a wall of words,
so the gate refuses it and says how to shorten it::

    TaskCreate subject of 220 characters          -> refused, names the length
    TaskCreate "Gate gaps: review left, then merge" -> allowed
    TaskUpdate with only taskId and status        -> allowed
    TodoWrite with one item over 80 characters    -> refused, names that item

Another tool, unreadable stdin, a tool_input that is not an object, and a
subject or item that is not a string all pass, so the hook never fails closed.
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
    PERMISSION_DECISION_KEY,
    PERMISSION_DECISION_REASON_KEY,
)
from hooks_constants.pre_tool_use_stdin import print_decision_from_stdin
from hooks_constants.task_subject_length_gate_constants import (
    ALL_SUBJECT_TOOL_NAMES,
    DENY_DECISION,
    LONG_SUBJECT_REASON_TEMPLATE,
    LONG_TODO_ITEM_REASON_TEMPLATE,
    MAXIMUM_SUBJECT_CHARACTERS,
    PRE_TOOL_USE_EVENT_NAME,
    SUBJECT_INPUT_KEY,
    TODO_CONTENT_KEY,
    TODO_WRITE_TOOL_NAME,
    TODOS_INPUT_KEY,
    TOOL_INPUT_KEY,
    TOOL_NAME_KEY,
)


def _long_subject_reason(all_tool_input: dict[object, object]) -> str | None:
    subject = all_tool_input.get(SUBJECT_INPUT_KEY)
    if not isinstance(subject, str) or len(subject) <= MAXIMUM_SUBJECT_CHARACTERS:
        return None
    return LONG_SUBJECT_REASON_TEMPLATE.format(
        length=len(subject), maximum=MAXIMUM_SUBJECT_CHARACTERS
    )


def _long_todo_item_reason(all_tool_input: dict[object, object]) -> str | None:
    all_todos = all_tool_input.get(TODOS_INPUT_KEY)
    if not isinstance(all_todos, list):
        return None
    for each_position, each_todo in enumerate(all_todos, start=1):
        content = each_todo.get(TODO_CONTENT_KEY) if isinstance(each_todo, dict) else None
        if isinstance(content, str) and len(content) > MAXIMUM_SUBJECT_CHARACTERS:
            return LONG_TODO_ITEM_REASON_TEMPLATE.format(
                position=each_position,
                content=content,
                length=len(content),
                maximum=MAXIMUM_SUBJECT_CHARACTERS,
            )
    return None


def long_subject_decision(all_hook_payload: dict[str, object]) -> dict[str, object] | None:
    """Return the deny decision for a task list item over the limit, else None.

    Args:
        all_hook_payload: The PreToolUse payload the hook read from stdin.
    """
    tool_name = all_hook_payload.get(TOOL_NAME_KEY)
    all_tool_input = all_hook_payload.get(TOOL_INPUT_KEY)
    if not isinstance(all_tool_input, dict):
        return None
    if tool_name in ALL_SUBJECT_TOOL_NAMES:
        refusal_reason = _long_subject_reason(all_tool_input)
    elif tool_name == TODO_WRITE_TOOL_NAME:
        refusal_reason = _long_todo_item_reason(all_tool_input)
    else:
        return None
    if refusal_reason is None:
        return None
    return {
        HOOK_SPECIFIC_OUTPUT_KEY: {
            HOOK_EVENT_NAME_KEY: PRE_TOOL_USE_EVENT_NAME,
            PERMISSION_DECISION_KEY: DENY_DECISION,
            PERMISSION_DECISION_REASON_KEY: refusal_reason,
        }
    }


def main() -> int:
    """Deny a task list item over the limit, or stay quiet.

    Returns:
        0 in every case; the decision travels in the JSON output.
    """
    return print_decision_from_stdin(long_subject_decision)


if __name__ == "__main__":
    sys.exit(main())
