#!/usr/bin/env python3
"""PreToolUse hook that keeps procedure steps out of the task list the user follows.

The gate reads each subject a TaskCreate or TaskUpdate call sets, and the
content of each item a TodoWrite call writes. It denies the call when a subject
carries one of these markers:

- It starts with a procedure step label: step, phase, stage, part, feature,
  bug fix, refactoring, or playbook, then a number or a range of one or two
  digits, then a colon, period, or closing parenthesis.
- It holds a backtick, the mark of a code-formatted name.

A call with no string subject passes, so a status-only TaskUpdate keeps working.
"""

from __future__ import annotations

import sys
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)

from hooks_constants.hook_block_logger import log_hook_block
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
from hooks_constants.task_subject_outcome_constants import (
    ALL_SUBJECT_TOOL_NAMES,
    ALLOW_EXIT_CODE,
    BLOCK_EXIT_CODE,
    CODE_SPAN_MARKER,
    CODE_SPAN_MESSAGE,
    GATE_EVENT_NAME,
    PROCEDURE_STEP_MESSAGE,
    PROCEDURE_STEP_PREFIX_PATTERN,
    RETRY_INSTRUCTION,
    TASK_SUBJECT_KEY,
    TODO_CONTENT_KEY,
    TODO_WRITE_TOOL_NAME,
    TODOS_KEY,
    TOOL_INPUT_KEY,
    TOOL_NAME_KEY,
)


def task_subject_violation(subject: str) -> str | None:
    """Return the message for the marker a task subject carries, or None when it reads as an outcome.

    >>> task_subject_violation("PR 2347 merged with checks green") is None
    True
    >>> task_subject_violation("Feature 3: Write the checkpoint").startswith("The task subject")
    True

    Args:
        subject: The wording the task list would show the user.

    Returns:
        The message for the marker, or None.
    """
    if PROCEDURE_STEP_PREFIX_PATTERN.match(subject):
        return PROCEDURE_STEP_MESSAGE.format(subject=subject)
    if CODE_SPAN_MARKER in subject:
        return CODE_SPAN_MESSAGE.format(subject=subject)
    return None


def _subjects_in_call(tool_name: str, all_tool_input_fields: dict[str, object]) -> list[str]:
    if tool_name in ALL_SUBJECT_TOOL_NAMES:
        subject = all_tool_input_fields.get(TASK_SUBJECT_KEY)
        return [subject] if isinstance(subject, str) else []
    if tool_name != TODO_WRITE_TOOL_NAME:
        return []
    all_todo_entries = all_tool_input_fields.get(TODOS_KEY)
    if not isinstance(all_todo_entries, list):
        return []
    return [
        each_entry[TODO_CONTENT_KEY]
        for each_entry in all_todo_entries
        if isinstance(each_entry, dict) and isinstance(each_entry.get(TODO_CONTENT_KEY), str)
    ]


def main() -> int:
    hook_input = read_hook_input_dictionary_from_stdin()
    if hook_input is None:
        return ALLOW_EXIT_CODE
    tool_name = hook_input.get(TOOL_NAME_KEY)
    tool_input = hook_input.get(TOOL_INPUT_KEY)
    if not isinstance(tool_name, str) or not isinstance(tool_input, dict):
        return ALLOW_EXIT_CODE
    for each_subject in _subjects_in_call(tool_name, tool_input):
        violation = task_subject_violation(each_subject)
        if violation is None:
            continue
        block_reason = violation + RETRY_INSTRUCTION
        log_hook_block(
            Path(__file__).name,
            GATE_EVENT_NAME,
            block_reason,
            tool_name=tool_name,
            offending_input_preview=each_subject,
        )
        sys.stderr.write(block_reason)
        return BLOCK_EXIT_CODE
    return ALLOW_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())
