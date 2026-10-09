#!/usr/bin/env python3
"""Auto mode denial advisor: one approval phrase and one task card per denial.

On ``PermissionDenied`` the hook reads the classifier ``reason`` and writes a
plain-language approval phrase that names the program, the target and one
risk. Claude Code reads only ``retry`` from PermissionDenied output, so the
hook also stores the context in a per-session state file. On ``Stop`` and
``SubagentStop`` it replays the stored context as ``additionalContext``,
which Claude reads at the end of the turn, and removes the file.

The context tells the agent to show the phrase in a code block (a subagent
returns it to its parent unchanged) and to open a task card for a pull
request that adds an ``autoMode.allow`` rule to
``packages/claude-dev-env/settings.json``.
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

_hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if _hooks_root_directory not in sys.path:
    sys.path.insert(0, _hooks_root_directory)

from hooks_constants.auto_mode_denial_quick_fix_constants import (
    ALL_COMMAND_INPUT_KEYS,
    ALL_NO_VERDICT_REASON_PREFIXES,
    ALL_PROGRAM_GLOSSES,
    ALL_STOP_EVENT_NAMES,
    ALL_TOOL_GLOSSES,
    APPROVAL_PHRASE_TEMPLATE,
    CONTEXT_SEPARATOR,
    DEFAULT_GLOSS,
    DENIAL_CONTEXT_TEMPLATE,
    DENIAL_EVENT_NAME,
    MAIN_ACTOR,
    MAIN_AGENT_KEY,
    MAIN_RELAY_INSTRUCTION,
    MAXIMUM_ACTION_SUMMARY_CHARACTERS,
    MCP_GLOSS_TEMPLATE,
    MCP_NAME_SEPARATOR,
    MCP_TOOL_PREFIX,
    NO_VERDICT_CONTEXT_TEMPLATE,
    RISK_BY_RULE_LABEL,
    RULE_LABEL_PATTERN,
    STATE_DIRECTORY_NAME,
    SUMMARY_HEAD_SHARE_DIVISOR,
    SUMMARY_WORD_SEPARATOR,
    SUBAGENT_ACTOR,
    SUBAGENT_RELAY_INSTRUCTION,
    TRUNCATION_MARKER,
    UNSAFE_FILE_NAME_CHARACTERS,
    USER_MESSAGE_TEMPLATE,
    ProgramGloss,
)


def state_directory() -> Path:
    """Return the directory that holds pending denial contexts."""
    return Path(tempfile.gettempdir()) / STATE_DIRECTORY_NAME


def _state_file(all_event_fields: dict[str, object]) -> Path:
    session_key = str(all_event_fields.get("session_id") or "")
    agent_key = str(all_event_fields.get("agent_id") or MAIN_AGENT_KEY)
    file_stem = re.sub(UNSAFE_FILE_NAME_CHARACTERS, "_", f"{session_key}-{agent_key}")
    return state_directory() / f"{file_stem}.jsonl"


def _command_text(tool_input: object) -> str:
    all_input_fields = tool_input if isinstance(tool_input, dict) else {}
    all_command_values = [
        all_input_fields[each_key]
        for each_key in ALL_COMMAND_INPUT_KEYS
        if isinstance(all_input_fields.get(each_key), str)
    ]
    return all_command_values[0] if all_command_values else json.dumps(tool_input, sort_keys=True)


def action_summary_from(tool_input: object) -> str:
    """Return the denied command, URL, path or input on one short line.

    Args:
        tool_input: The denied call's ``tool_input``.

    Returns:
        The text with whitespace collapsed and backticks swapped for single
        quotes. Text over the summary length limit keeps its start and its
        end, where commands name the program and the target.
    """
    single_line_text = SUMMARY_WORD_SEPARATOR.join(_command_text(tool_input).split()).replace("`", "'")
    if len(single_line_text) <= MAXIMUM_ACTION_SUMMARY_CHARACTERS:
        return single_line_text
    kept_length = MAXIMUM_ACTION_SUMMARY_CHARACTERS - len(TRUNCATION_MARKER)
    head_length = kept_length // SUMMARY_HEAD_SHARE_DIVISOR
    tail_length = kept_length - head_length
    return single_line_text[:head_length] + TRUNCATION_MARKER + single_line_text[-tail_length:]


def gloss_for(tool_name: str, tool_input: object) -> ProgramGloss:
    """Return the plain-language gloss for the denied call.

    Args:
        tool_name: The denied tool's name.
        tool_input: The denied call's ``tool_input``.

    Returns:
        The tool's gloss, the first program gloss whose pattern matches the
        command, or the default gloss.
    """
    if tool_name in ALL_TOOL_GLOSSES:
        return ALL_TOOL_GLOSSES[tool_name]
    if tool_name.startswith(MCP_TOOL_PREFIX):
        server_and_tool_name = tool_name.removeprefix(MCP_TOOL_PREFIX)
        server_name, _, mcp_tool_name = server_and_tool_name.partition(MCP_NAME_SEPARATOR)
        return DEFAULT_GLOSS._replace(
            plain_action=MCP_GLOSS_TEMPLATE.format(tool=mcp_tool_name, server=server_name)
        )
    command_text = _command_text(tool_input)
    for each_gloss in ALL_PROGRAM_GLOSSES:
        if re.search(each_gloss.pattern, command_text):
            return each_gloss
    return DEFAULT_GLOSS._replace(
        plain_action=DEFAULT_GLOSS.plain_action.format(tool_name=tool_name)
    )


def risk_for(reason: str, gloss: ProgramGloss) -> str:
    """Return the risk clause for a denial.

    Args:
        reason: The classifier ``reason`` text.
        gloss: The denied call's gloss.

    Returns:
        The risk for the bracketed rule label when the table knows it, else
        the gloss risk.
    """
    label_match = re.search(RULE_LABEL_PATTERN, reason)
    rule_label = label_match.group(1).strip() if label_match else ""
    return RISK_BY_RULE_LABEL.get(rule_label, gloss.risk)


def denial_context(all_denial_fields: dict[str, object]) -> str:
    """Return the agent context for one PermissionDenied payload.

    Args:
        all_denial_fields: The hook input JSON.

    Returns:
        The phrase and task card instructions, or a short note when the
        classifier gave no verdict.
    """
    tool_name = str(all_denial_fields.get("tool_name") or "tool")
    reason = str(all_denial_fields.get("reason") or "")
    if reason.startswith(ALL_NO_VERDICT_REASON_PREFIXES):
        return NO_VERDICT_CONTEXT_TEMPLATE.format(tool_name=tool_name, reason=reason)
    tool_input = all_denial_fields.get("tool_input")
    gloss = gloss_for(tool_name, tool_input)
    is_subagent = bool(all_denial_fields.get("agent_id"))
    approval_phrase = APPROVAL_PHRASE_TEMPLATE.format(
        actor=SUBAGENT_ACTOR if is_subagent else MAIN_ACTOR,
        plain_action=gloss.plain_action,
        action_summary=action_summary_from(tool_input),
        risk=risk_for(reason, gloss),
    )
    return DENIAL_CONTEXT_TEMPLATE.format(
        tool_name=tool_name,
        reason=reason,
        relay_instruction=SUBAGENT_RELAY_INSTRUCTION if is_subagent else MAIN_RELAY_INSTRUCTION,
        approval_phrase=approval_phrase,
        plain_action=gloss.plain_action,
    )


def _hook_output(event_name: str, context_text: str) -> dict[str, object]:
    return {
        "hookSpecificOutput": {
            "hookEventName": event_name,
            "additionalContext": context_text,
        }
    }


def _record_denial(all_denial_fields: dict[str, object]) -> dict[str, object]:
    context_text = denial_context(all_denial_fields)
    state_file = _state_file(all_denial_fields)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    with state_file.open("a", encoding="utf-8", newline="\n") as state_stream:
        state_stream.write(json.dumps(context_text) + "\n")
    tool_name = str(all_denial_fields.get("tool_name") or "tool")
    return {
        **_hook_output(DENIAL_EVENT_NAME, context_text),
        "systemMessage": USER_MESSAGE_TEMPLATE.format(tool_name=tool_name),
    }


def _replay_denials(all_stop_fields: dict[str, object]) -> dict[str, object] | None:
    state_file = _state_file(all_stop_fields)
    if not state_file.is_file():
        return None
    all_contexts = [
        json.loads(each_line)
        for each_line in state_file.read_text(encoding="utf-8").splitlines()
        if each_line.strip()
    ]
    state_file.unlink()
    if not all_contexts:
        return None
    return _hook_output(
        str(all_stop_fields["hook_event_name"]), CONTEXT_SEPARATOR.join(all_contexts)
    )


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if not isinstance(payload, dict):
        return 0
    event_name = payload.get("hook_event_name")
    if event_name == DENIAL_EVENT_NAME:
        hook_output = _record_denial(payload)
    elif event_name in ALL_STOP_EVENT_NAMES:
        hook_output = _replay_denials(payload)
    else:
        hook_output = None
    if hook_output is not None:
        sys.stdout.write(json.dumps(hook_output))
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
