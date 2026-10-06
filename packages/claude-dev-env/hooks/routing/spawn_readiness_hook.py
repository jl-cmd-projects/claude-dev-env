#!/usr/bin/env python3
"""PreToolUse hook: remind a session to read and ask before it spawns agents.

Registered on ``Agent``, ``Task``, ``mcp__hearthbot__start_thread_session``,
``multi_agent_v1__spawn_agent``, ``Workflow``, and a workflow dispatch whose
inputs carry a ``prompt``. It reads the session transcript and checks two
things since the user's request:

::

    no read step after the request              -> context: investigate first
    no interactive question, then an answer     -> context: interview first
    brief line "Scope settled: <reason>"        -> interview check passes, logged
    both found                                  -> no output
    Codex payload (turn_id), no settled line    -> context: the Codex reminder

The output is ``additionalContext`` alone, so the spawn runs and keeps its
normal permission flow. ``spawn_readiness_steps`` reads the transcript and
finds the request. Four cases pass without a check: a call from inside a
subagent, a read-only subagent type, a tool input that is not an object, and a
transcript the hook cannot read. The last one is logged.
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

from hooks_constants.pre_tool_use_context_runner import run_context_hook
from hooks_constants.spawn_readiness_hook_constants import (
    ADDITIONAL_CONTEXT_KEY,
    AGENT_ID_KEY,
    ALL_BRIEF_FIELDS_BY_SPAWN_TOOL_NAME,
    ALL_READ_ONLY_SUBAGENT_TYPES,
    CODEX_TRANSCRIPT_REMINDER,
    CODEX_TURN_ID_KEY,
    DECISION_LOG_RELATIVE_PATH,
    DISPATCH_INPUTS_KEY,
    DISPATCH_METHOD_INPUT_KEY,
    DISPATCH_PROMPT_INPUT_KEY,
    DISPATCH_RUN_WORKFLOW_METHOD,
    LOG_APPEND_MODE,
    LOG_LINE_END,
    LOG_OUTCOME_KEY,
    LOG_SCOPE_SETTLED_LINE_KEY,
    LOG_TIMESTAMP_KEY,
    LOG_TOOL_NAME_KEY,
    LOG_TOOL_USE_ID_KEY,
    MISSING_INTERVIEW_REASON,
    OUTCOME_REMINDED,
    OUTCOME_SCOPE_SETTLED,
    OUTCOME_TRANSCRIPT_UNREADABLE,
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
    WORKFLOW_DISPATCH_TOOL_NAME,
    WORKFLOW_SCRIPT_PATH_INPUT_KEY,
    WORKFLOW_TOOL_NAME,
)
from hooks_constants.hook_specific_output_keys import (
    HOOK_EVENT_NAME_KEY,
    HOOK_SPECIFIC_OUTPUT_KEY,
)
from spawn_readiness_steps import readiness_gaps, session_steps


def _workflow_script(all_tool_input_fields: dict[str, object]) -> str:
    script = all_tool_input_fields.get(ALL_BRIEF_FIELDS_BY_SPAWN_TOOL_NAME[WORKFLOW_TOOL_NAME])
    if isinstance(script, str):
        return script
    script_path = all_tool_input_fields.get(WORKFLOW_SCRIPT_PATH_INPUT_KEY)
    if not isinstance(script_path, str) or not script_path:
        return ""
    try:
        return Path(script_path).read_text(
            encoding=TRANSCRIPT_ENCODING, errors=TRANSCRIPT_DECODE_ERRORS
        )
    except OSError:
        return ""


def _dispatch_prompt(all_tool_input_fields: dict[str, object]) -> str | None:
    if all_tool_input_fields.get(DISPATCH_METHOD_INPUT_KEY) != DISPATCH_RUN_WORKFLOW_METHOD:
        return None
    workflow_inputs = all_tool_input_fields.get(DISPATCH_INPUTS_KEY)
    if not isinstance(workflow_inputs, dict):
        return None
    prompt = workflow_inputs.get(DISPATCH_PROMPT_INPUT_KEY)
    return prompt if isinstance(prompt, str) else None


def spawn_brief(tool_name: str, all_tool_input_fields: dict[str, object]) -> str | None:
    """Return the brief a spawn call hands its agents, or None when the call spawns none.

    ::

        Agent             {"prompt": "Do X."}                         -> "Do X."
        Workflow          {"scriptPath": "w.js"}                      -> the text of w.js
        actions trigger   {"method": "run_workflow",
                           "inputs": {"prompt": "Do X."}}             -> "Do X."
        actions trigger   {"method": "cancel_workflow_run"}           -> None
        Agent             {"subagent_type": "Explore", "prompt": ...} -> None

    Args:
        tool_name: The tool the session called.
        all_tool_input_fields: The tool input.
    """
    if tool_name == WORKFLOW_DISPATCH_TOOL_NAME:
        return _dispatch_prompt(all_tool_input_fields)
    if tool_name not in ALL_BRIEF_FIELDS_BY_SPAWN_TOOL_NAME:
        return None
    if all_tool_input_fields.get(SUBAGENT_TYPE_INPUT_KEY) in ALL_READ_ONLY_SUBAGENT_TYPES:
        return None
    if tool_name == WORKFLOW_TOOL_NAME:
        return _workflow_script(all_tool_input_fields)
    brief = all_tool_input_fields.get(ALL_BRIEF_FIELDS_BY_SPAWN_TOOL_NAME[tool_name])
    return brief if isinstance(brief, str) else ""


def scope_settled_line(brief: str) -> str | None:
    """Return the brief's "Scope settled:" line when it names a reason, else None.

    ::

        "Do X.\\nScope settled: the request names the file and the fix."
        -> "Scope settled: the request names the file and the fix."
        "Do X.\\nScope settled:"  -> None

    Args:
        brief: The text the spawn hands its agents.
    """
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


def _context_output(context: str) -> dict[str, object]:
    return {
        HOOK_SPECIFIC_OUTPUT_KEY: {
            HOOK_EVENT_NAME_KEY: PRE_TOOL_USE_EVENT_NAME,
            ADDITIONAL_CONTEXT_KEY: context,
        }
    }


def _transcript_gaps(
    all_hook_fields: dict[str, object], tool_use_id: str | None
) -> list[str] | None:
    if all_hook_fields.get(CODEX_TURN_ID_KEY):
        return [CODEX_TRANSCRIPT_REMINDER]
    all_transcript_lines = _transcript_lines(all_hook_fields.get(TRANSCRIPT_PATH_KEY))
    if all_transcript_lines is None:
        return None
    return readiness_gaps(session_steps(all_transcript_lines, tool_use_id))


def _gaps_after_scope_settled(
    all_gaps: list[str], brief: str, tool_name: str, tool_use_id: str | None
) -> list[str]:
    settled_line = scope_settled_line(brief)
    all_settled_gaps = {MISSING_INTERVIEW_REASON, CODEX_TRANSCRIPT_REMINDER}
    if settled_line is None or not all_settled_gaps.intersection(all_gaps):
        return all_gaps
    _log_decision(tool_name, tool_use_id, OUTCOME_SCOPE_SETTLED, settled_line)
    return [each_gap for each_gap in all_gaps if each_gap not in all_settled_gaps]


def decide_hook_output(all_hook_fields: dict[str, object]) -> dict[str, object] | None:
    """Choose the hook's output for one spawn call.

    Args:
        all_hook_fields: The parsed PreToolUse payload.

    Returns:
        None to stay quiet, else the reminder as additionalContext output.
    """
    tool_name = all_hook_fields.get(TOOL_NAME_KEY)
    tool_input = all_hook_fields.get(TOOL_INPUT_KEY)
    if not isinstance(tool_name, str) or not isinstance(tool_input, dict):
        return None
    if all_hook_fields.get(AGENT_ID_KEY):
        return None
    brief = spawn_brief(tool_name, tool_input)
    if brief is None:
        return None
    raw_tool_use_id = all_hook_fields.get(TOOL_USE_ID_KEY)
    tool_use_id = raw_tool_use_id if isinstance(raw_tool_use_id, str) else None
    all_gaps = _transcript_gaps(all_hook_fields, tool_use_id)
    if all_gaps is None:
        _log_decision(tool_name, tool_use_id, OUTCOME_TRANSCRIPT_UNREADABLE, None)
        return None
    all_gaps = _gaps_after_scope_settled(all_gaps, brief, tool_name, tool_use_id)
    if not all_gaps:
        return None
    _log_decision(tool_name, tool_use_id, OUTCOME_REMINDED, None)
    return _context_output(REASON_SEPARATOR.join(all_gaps))


def main() -> int:
    """Run the hook on the stdin payload; always 0."""
    return run_context_hook(decide_hook_output)


if __name__ == "__main__":
    sys.exit(main())
