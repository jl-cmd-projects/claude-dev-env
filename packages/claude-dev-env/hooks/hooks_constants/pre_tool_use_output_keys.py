"""JSON keys of the hookSpecificOutput object a PreToolUse hook writes to stdout."""

from __future__ import annotations

__all__ = [
    "HOOK_SPECIFIC_OUTPUT_KEY",
    "HOOK_EVENT_NAME_KEY",
    "PERMISSION_DECISION_KEY",
    "UPDATED_INPUT_KEY",
]

HOOK_SPECIFIC_OUTPUT_KEY: str = "hookSpecificOutput"
HOOK_EVENT_NAME_KEY: str = "hookEventName"
PERMISSION_DECISION_KEY: str = "permissionDecision"
UPDATED_INPUT_KEY: str = "updatedInput"
