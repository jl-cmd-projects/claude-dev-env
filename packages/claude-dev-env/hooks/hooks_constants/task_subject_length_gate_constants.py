"""Tool names, input keys, the subject limit and refusal text for the task_subject_length_gate hook."""

from __future__ import annotations

__all__ = [
    "TOOL_NAME_KEY",
    "TOOL_INPUT_KEY",
    "ALL_SUBJECT_TOOL_NAMES",
    "SUBJECT_INPUT_KEY",
    "TODO_WRITE_TOOL_NAME",
    "TODOS_INPUT_KEY",
    "TODO_CONTENT_KEY",
    "PRE_TOOL_USE_EVENT_NAME",
    "DENY_DECISION",
    "MAXIMUM_SUBJECT_CHARACTERS",
    "LONG_SUBJECT_REASON_TEMPLATE",
    "LONG_TODO_ITEM_REASON_TEMPLATE",
]

TOOL_NAME_KEY = "tool_name"
TOOL_INPUT_KEY = "tool_input"
ALL_SUBJECT_TOOL_NAMES = frozenset({"TaskCreate", "TaskUpdate"})
SUBJECT_INPUT_KEY = "subject"
TODO_WRITE_TOOL_NAME = "TodoWrite"
TODOS_INPUT_KEY = "todos"
TODO_CONTENT_KEY = "content"
PRE_TOOL_USE_EVENT_NAME = "PreToolUse"
DENY_DECISION = "deny"
MAXIMUM_SUBJECT_CHARACTERS = 80

_SHORTEN_INSTRUCTION = (
    " The user reads the task list to see where things stand and what is left."
    " Write a short subject: start with who acts (Me, You, or Handed off) and say what is left,"
    ' for example "You: one live try on your PC, then the pull request can merge".'
    " Put status detail, evidence and steps in the description."
)
LONG_SUBJECT_REASON_TEMPLATE = (
    "This task subject is {length} characters and the limit is {maximum}." + _SHORTEN_INSTRUCTION
)
LONG_TODO_ITEM_REASON_TEMPLATE = (
    'Task list item {position} ("{content}") is {length} characters and the limit is {maximum}.'
    + _SHORTEN_INSTRUCTION
)
