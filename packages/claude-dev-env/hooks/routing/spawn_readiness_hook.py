#!/usr/bin/env python3
"""PreToolUse hook: hold an agent spawn until the session has read and asked.

Registered on ``Agent``, ``Task``, and ``mcp__hearthbot__start_thread_session``.
It reads the session transcript and checks two things since the user's request:

::

    no read step after the request              -> deny: investigate first
    no question to the user, then a reply       -> deny: interview first
    brief line "Scope settled: <reason>"        -> interview check passes, logged
    both found                                  -> no output; the call runs

``spawn_readiness_steps`` reads the transcript and finds the request. Four
cases pass without a check: a call from inside a subagent, a read-only
subagent type, a tool input that is not an object, and a transcript the hook
cannot read. The last one is logged.
"""

from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)
routing_directory = str(Path(__file__).resolve().parent)
if routing_directory not in sys.path:
    sys.path.insert(0, routing_directory)

from hooks_constants.hook_block_logger import log_hook_block
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
from hooks_constants.spawn_readiness_hook_constants import (
    AGENT_ID_KEY,
    ALL_BRIEF_FIELDS_BY_SPAWN_TOOL_NAME,
    ALL_READ_ONLY_SUBAGENT_TYPES,
    DECISION_LOG_RELATIVE_PATH,
    HOOK_EVENT_NAME_KEY,
    HOOK_SPECIFIC_OUTPUT_KEY,
    LOG_APPEND_MODE,
    LOG_LINE_END,
    LOG_OUTCOME_KEY,
    LOG_SCOPE_SETTLED_LINE_KEY,
    LOG_TIMESTAMP_KEY,
    LOG_TOOL_NAME_KEY,
    LOG_TOOL_USE_ID_KEY,
    MISSING_INTERVIEW_REASON,
    OUTCOME_SCOPE_SETTLED,
    OUTCOME_TRANSCRIPT_UNREADABLE,
    PERMISSION_DECISION_KEY,
    PERMISSION_DECISION_REASON_KEY,
    PERMISSION_DENY,
    PRE_TOOL_USE_EVENT_NAME,
    REASON_SEPARATOR,
    SCOPE_SETTLED_PREFIX,
    SUBAGENT_TYPE_INPUT_KEY,
    TOOL_INPUT_KEY,
    TOOL_NAME_KEY,
    TOOL_USE_ID_KEY,
    TRANSCRIPT_DECODE_ERRORS,
    TRANSCRIPT_ENCODING,
    TRANSCRIPT_PATH_KEY,
)
from spawn_readiness_steps import readiness_gaps, session_steps


def scope_settled_line(tool_name: str, all_tool_input_fields: dict[str, object]) -> str | None:
    """Return the brief's "Scope settled:" line when it names a reason, else None.

    ::

        "Do X.\\nScope settled: the request names the file and the fix."
        -> "Scope settled: the request names the file and the fix."
        "Do X.\\nScope settled:"  -> None

    Args:
        tool_name: The spawn tool, which decides the brief field.
        all_tool_input_fields: The spawn input.
    """
    brief = all_tool_input_fields.get(ALL_BRIEF_FIELDS_BY_SPAWN_TOOL_NAME.get(tool_name, ""))
    if not isinstance(brief, str):
        return None
    for each_line in brief.splitlines():
        stripped_line = each_line.strip()
        stated_reason = stripped_line.removeprefix(SCOPE_SETTLED_PREFIX).strip()
        if stripped_line.startswith(SCOPE_SETTLED_PREFIX) and stated_reason:
            return stripped_line
    return None


def _log_decision(
    tool_name: str, tool_use_id: str | None, outcome: str, settled_line: str | None
) -> None:
    try:
        log_path = Path.home() / DECISION_LOG_RELATIVE_PATH
    except RuntimeError:
        return
    log_record: dict[str, object] = {
        LOG_TIMESTAMP_KEY: datetime.datetime.now().isoformat(),
        LOG_TOOL_NAME_KEY: tool_name,
        LOG_TOOL_USE_ID_KEY: tool_use_id,
        LOG_OUTCOME_KEY: outcome,
    }
    if settled_line is not None:
        log_record[LOG_SCOPE_SETTLED_LINE_KEY] = settled_line
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open(LOG_APPEND_MODE, encoding=TRANSCRIPT_ENCODING) as log_file:
            log_file.write(json.dumps(log_record) + LOG_LINE_END)
    except OSError:
        pass


def _transcript_lines(transcript_path: object) -> list[str] | None:
    if not isinstance(transcript_path, str) or not transcript_path:
        return None
    try:
        return Path(transcript_path).read_text(
            encoding=TRANSCRIPT_ENCODING, errors=TRANSCRIPT_DECODE_ERRORS
        ).splitlines()
    except OSError:
        return None


def _deny_output(reason: str) -> dict[str, object]:
    return {
        HOOK_SPECIFIC_OUTPUT_KEY: {
            HOOK_EVENT_NAME_KEY: PRE_TOOL_USE_EVENT_NAME,
            PERMISSION_DECISION_KEY: PERMISSION_DENY,
            PERMISSION_DECISION_REASON_KEY: reason,
        }
    }


def _is_checked_spawn(all_hook_fields: dict[str, object]) -> bool:
    tool_input = all_hook_fields.get(TOOL_INPUT_KEY)
    return (
        all_hook_fields.get(TOOL_NAME_KEY) in ALL_BRIEF_FIELDS_BY_SPAWN_TOOL_NAME
        and isinstance(tool_input, dict)
        and not all_hook_fields.get(AGENT_ID_KEY)
        and tool_input.get(SUBAGENT_TYPE_INPUT_KEY) not in ALL_READ_ONLY_SUBAGENT_TYPES
    )


def decide_hook_output(all_hook_fields: dict[str, object]) -> dict[str, object] | None:
    """Choose the hook's output for one spawn call.

    Args:
        all_hook_fields: The parsed PreToolUse payload.

    Returns:
        None to let the call run, else the deny JSON output.
    """
    if not _is_checked_spawn(all_hook_fields):
        return None
    tool_name = str(all_hook_fields[TOOL_NAME_KEY])
    raw_tool_use_id = all_hook_fields.get(TOOL_USE_ID_KEY)
    tool_use_id = raw_tool_use_id if isinstance(raw_tool_use_id, str) else None
    all_transcript_lines = _transcript_lines(all_hook_fields.get(TRANSCRIPT_PATH_KEY))
    if all_transcript_lines is None:
        _log_decision(tool_name, tool_use_id, OUTCOME_TRANSCRIPT_UNREADABLE, None)
        return None
    all_gaps = readiness_gaps(session_steps(all_transcript_lines, tool_use_id))
    settled_line = scope_settled_line(tool_name, all_hook_fields[TOOL_INPUT_KEY])
    if settled_line is not None and MISSING_INTERVIEW_REASON in all_gaps:
        all_gaps.remove(MISSING_INTERVIEW_REASON)
        _log_decision(tool_name, tool_use_id, OUTCOME_SCOPE_SETTLED, settled_line)
    if not all_gaps:
        return None
    deny_reason = REASON_SEPARATOR.join(all_gaps)
    log_hook_block(Path(__file__).name, PRE_TOOL_USE_EVENT_NAME, deny_reason, tool_name=tool_name)
    return _deny_output(deny_reason)


def main() -> int:
    """Read the PreToolUse payload and print a deny when the spawn is not ready.

    Returns:
        0 in every case; a deny travels in the JSON output.
    """
    hook_payload = read_hook_input_dictionary_from_stdin()
    if hook_payload is None:
        return 0
    hook_output = decide_hook_output(hook_payload)
    if hook_output is not None:
        sys.stdout.write(json.dumps(hook_output))
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
