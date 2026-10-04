#!/usr/bin/env python3
"""PermissionDenied advisor: a proposed quick fix for each auto mode denial.

This hook never retries the denied call. It reads the denial, names the
classifier rule from the bracketed label in ``denial_reason``, drafts one
``autoMode.allow`` entry for the denied action, and adds a PowerShell 7 block
that writes the entry to ``~/.claude/settings.json`` with ``"$defaults"``
kept. The agent receives the proposal as ``additionalContext``; the user
receives a one-line ``systemMessage``.

A denial with no ``classifier_verdict`` gets a short note and no block,
because an allow entry cannot clear it.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if _hooks_root_directory not in sys.path:
    sys.path.insert(0, _hooks_root_directory)

from hooks_constants.auto_mode_denial_quick_fix_constants import (
    ALL_COMMAND_INPUT_KEYS,
    ALLOW_ENTRY_TEMPLATE,
    HOOK_EVENT_NAME,
    MAXIMUM_ACTION_SUMMARY_CHARACTERS,
    NO_VERDICT_CONTEXT_TEMPLATE,
    POWERSHELL_BLOCK_TEMPLATE,
    RULE_LABEL_PATTERN,
    TRUNCATION_MARKER,
    UNNAMED_RULE_LABEL,
    USER_MESSAGE_TEMPLATE,
    VERDICT_CONTEXT_TEMPLATE,
)


def rule_label_from(denial_reason: str) -> str:
    """Return the classifier rule name from a denial reason.

    Args:
        denial_reason: The ``denial_reason`` text, such as
            ``"[Security Weaken] lowers a guard"``.

    Returns:
        The first bracketed label, or the unnamed-rule label.
    """
    label_match = re.search(RULE_LABEL_PATTERN, denial_reason)
    return label_match.group(1).strip() if label_match else UNNAMED_RULE_LABEL


def action_summary_from(tool_input: object) -> str:
    """Return one short line that names the denied action.

    Args:
        tool_input: The denied call's ``tool_input``.

    Returns:
        The command, URL or path when the input has one, else the compact
        JSON input, cut to the summary length limit.
    """
    summary_text = json.dumps(tool_input, sort_keys=True)
    if isinstance(tool_input, dict):
        for each_key in ALL_COMMAND_INPUT_KEYS:
            if isinstance(tool_input.get(each_key), str):
                summary_text = tool_input[each_key]
                break
    single_line_text = " ".join(summary_text.split())
    if len(single_line_text) <= MAXIMUM_ACTION_SUMMARY_CHARACTERS:
        return single_line_text
    kept_length = MAXIMUM_ACTION_SUMMARY_CHARACTERS - len(TRUNCATION_MARKER)
    return single_line_text[:kept_length] + TRUNCATION_MARKER


def powershell_block_for(allow_entry: str) -> str:
    """Return the PowerShell 7 block that adds one allow entry.

    Args:
        allow_entry: The ``autoMode.allow`` entry text.

    Returns:
        The block, with the entry in a single-quoted PowerShell literal.
    """
    escaped_entry = allow_entry.replace("'", "''")
    return POWERSHELL_BLOCK_TEMPLATE.replace("{escaped_entry}", escaped_entry)


def build_hook_output(payload: dict[str, object]) -> dict[str, object]:
    """Return the PermissionDenied hook output for one denial payload.

    Args:
        payload: The hook input JSON.

    Returns:
        A ``hookSpecificOutput`` with ``additionalContext`` for the agent and
        a top-level ``systemMessage`` for the user.
    """
    tool_name = str(payload.get("tool_name") or "tool")
    denial_reason = str(payload.get("denial_reason") or "")
    action_summary = action_summary_from(payload.get("tool_input"))
    rule_label = rule_label_from(denial_reason)
    if payload.get("classifier_verdict"):
        allow_entry = ALLOW_ENTRY_TEMPLATE.format(
            rule_label=rule_label,
            tool_name=tool_name,
            action_summary=action_summary,
        )
        context_text = VERDICT_CONTEXT_TEMPLATE.format(
            tool_name=tool_name,
            rule_label=rule_label,
            denial_reason=denial_reason,
            action_summary=action_summary,
            powershell_block=powershell_block_for(allow_entry),
        )
    else:
        context_text = NO_VERDICT_CONTEXT_TEMPLATE.format(
            tool_name=tool_name,
            denial_reason=denial_reason,
            action_summary=action_summary,
        )
    return {
        "hookSpecificOutput": {
            "hookEventName": HOOK_EVENT_NAME,
            "additionalContext": context_text,
        },
        "systemMessage": USER_MESSAGE_TEMPLATE.format(tool_name=tool_name, rule_label=rule_label),
    }


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if not isinstance(payload, dict):
        return 0
    sys.stdout.write(json.dumps(build_hook_output(payload)))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
