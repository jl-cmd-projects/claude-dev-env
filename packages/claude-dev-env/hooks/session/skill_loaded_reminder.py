#!/usr/bin/env python3
"""Hook that restores poteto-mode after compaction and loads it for workflow helpers.

::

    Workflow script helper starts               -> "invoke poteto-mode now"
    compact SessionStart, skill invoked before   -> "invoke the skill again"
    compact SessionStart, no prior invocation
    or transcript unavailable                    -> nothing
    user turn, skill invoked then compacted      -> "invoke poteto-mode now"
    user turn, skill loaded, never invoked,
    or transcript unavailable                    -> nothing

A session that invoked the skill hears nothing more until a compaction drops it.
The hook prints its output and stops.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterable
from pathlib import Path

_hooks_dir = str(Path(__file__).resolve().parent.parent)
if _hooks_dir not in sys.path:
    sys.path.insert(0, _hooks_dir)

from hooks_constants.skill_loaded_reminder_constants import (
    COMPACTION_REMINDER,
    COMPACTION_SOURCE,
    NOT_LOADED_REMINDER,
    ALL_POTETO_MODE_SKILL_NAMES,
    SESSION_START_EVENT_NAME,
    ALL_SLASH_COMMAND_MARKERS,
    SUBAGENT_START_EVENT_NAME,
    USER_PROMPT_SUBMIT_EVENT_NAME,
    WORKFLOW_SUBAGENT_TYPE,
)
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
from hooks_constants.setup_project_paths_constants import DECODE_ERRORS_POLICY, UTF8_ENCODING
from transcript_skill_scan import skill_invocation_status


def poteto_mode_status(all_transcript_lines: Iterable[str]) -> tuple[bool, bool]:
    """Report whether the skill was invoked and whether it remains loaded.

    ::

        Skill(poteto-mode) ... Read                   -> (True, True)
        /poteto-mode ... compact_boundary             -> (True, False)
        Skill(poteto-mode) ... compact_boundary ... Skill(poteto-mode)
                                                      -> (True, True)
        Read ... Edit                                 -> (False, False)

    Only lines naming the skill or a compaction are parsed, so a long transcript
    reads fast.

    Args:
        all_transcript_lines: The session transcript, one JSON entry per line.

    Returns:
        Whether the skill was invoked at any point and whether it is loaded now.
    """
    return skill_invocation_status(
        all_transcript_lines, ALL_POTETO_MODE_SKILL_NAMES, ALL_SLASH_COMMAND_MARKERS
    )


def is_poteto_mode_loaded(all_transcript_lines: Iterable[str]) -> bool:
    """Return whether the transcript invoked the skill after its last compaction.

    Args:
        all_transcript_lines: The session transcript, one JSON entry per line.

    Returns:
        Whether the skill is loaded now.
    """
    return poteto_mode_status(all_transcript_lines)[1]


def _status_in_transcript(transcript_path: object) -> tuple[bool, bool]:
    if not isinstance(transcript_path, str):
        return False, False
    try:
        with open(
            transcript_path, encoding=UTF8_ENCODING, errors=DECODE_ERRORS_POLICY
        ) as transcript:
            return poteto_mode_status(transcript)
    except OSError:
        return False, False


def reminder_for(all_hook_fields: dict[str, object]) -> str | None:
    """Return a reminder only for helpers or sessions that need the skill restored.

    ::

        SessionStart, compact, skill invoked before      -> COMPACTION_REMINDER
        SessionStart, compact, no prior invocation
        or transcript unavailable                        -> None
        SubagentStart, workflow-subagent                 -> NOT_LOADED_REMINDER
        UserPromptSubmit, skill invoked then compacted   -> NOT_LOADED_REMINDER
        UserPromptSubmit, skill loaded, never invoked,
        or transcript unavailable                        -> None

    Args:
        all_hook_fields: The parsed hook input.

    Returns:
        The event's reminder, or None when no reminder is needed.
    """
    event_name = all_hook_fields.get("hook_event_name")
    if event_name == SESSION_START_EVENT_NAME:
        if all_hook_fields.get("source") != COMPACTION_SOURCE:
            return None
        was_invoked, _ = _status_in_transcript(all_hook_fields.get("transcript_path"))
        return COMPACTION_REMINDER if was_invoked else None
    if event_name == SUBAGENT_START_EVENT_NAME:
        is_workflow_helper = all_hook_fields.get("agent_type") == WORKFLOW_SUBAGENT_TYPE
        return NOT_LOADED_REMINDER if is_workflow_helper else None
    if event_name != USER_PROMPT_SUBMIT_EVENT_NAME:
        return None
    was_invoked, is_loaded = _status_in_transcript(all_hook_fields.get("transcript_path"))
    return NOT_LOADED_REMINDER if was_invoked and not is_loaded else None


def main() -> None:
    """Print the reminder its event needs, or stay quiet."""
    hook_payload = read_hook_input_dictionary_from_stdin()
    if hook_payload is None:
        return
    reminder = reminder_for(hook_payload)
    if reminder is None:
        return
    reminder_output = {
        "hookSpecificOutput": {
            "hookEventName": hook_payload["hook_event_name"],
            "additionalContext": reminder,
        }
    }
    sys.stdout.write(json.dumps(reminder_output) + "\n")


if __name__ == "__main__":
    main()
