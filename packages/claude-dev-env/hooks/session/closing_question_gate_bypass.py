#!/usr/bin/env python3
"""UserPromptSubmit hook that turns the closing question round Stop gate off and on for one session.

A prompt that holds the keyword flips the session's flag::

    session s1, "ship it --nocards", gate on     -> flag written, context "...now OFF"
    session s1, later "--NoCards", gate off      -> flag removed, context "...now ON"
    session s1, "ship it --no-cards", gate on    -> flag written, same as "--nocards"
    session s1, "ship it"                        -> nothing
    session s1, "!nocards"                       -> nothing
    session s2, "--nocards"                      -> s2's flag only; s1 keeps its state

The keyword is ``BYPASS_KEYWORD`` or ``BYPASS_KEYWORD_HYPHENATED``, matched as a whole word in any case after
the prompt's ``<system-reminder>`` blocks are removed. ``closing_question_gate_flag``
keeps the flag, and ``blocking/closing_question_round_gate.py`` allows every
stop of the session while it is set. A payload with no session id, or a flag
that cannot be written or removed, changes nothing and adds no context.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)

from closing_question_gate_flag import payload_session_id, toggle_bypass
from hooks_constants.closing_question_round_gate_constants import (
    ADDITIONAL_CONTEXT_KEY,
    BYPASS_KEYWORD_PATTERN,
    GATE_TURNED_OFF_CONTEXT,
    GATE_TURNED_ON_CONTEXT,
)
from hooks_constants.hook_specific_output_keys import (
    HOOK_EVENT_NAME_KEY,
    HOOK_SPECIFIC_OUTPUT_KEY,
)
from hooks_constants.open_tasks_stop_gate_constants import (
    ALLOW_EXIT_CODE,
    PROMPT_KEY,
    PROMPT_SUBMIT_EVENT_NAME,
)
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
from open_task_asks import prompt_without_reminders


def has_bypass_keyword(prompt_text: str) -> bool:
    """Return True when the prompt, without its ``<system-reminder>`` blocks, holds the keyword as a whole word."""
    return bool(BYPASS_KEYWORD_PATTERN.search(prompt_without_reminders(prompt_text)))


def toggle_context(all_hook_input_fields: Mapping[str, object]) -> str | None:
    """Flip the flag for a prompt that holds the keyword and return the state line, else None."""
    session_id = payload_session_id(all_hook_input_fields)
    prompt_value = all_hook_input_fields.get(PROMPT_KEY)
    if session_id is None or not isinstance(prompt_value, str):
        return None
    if not has_bypass_keyword(prompt_value):
        return None
    is_gate_off = toggle_bypass(session_id)
    if is_gate_off is None:
        return None
    return GATE_TURNED_OFF_CONTEXT if is_gate_off else GATE_TURNED_ON_CONTEXT


def main() -> int:
    """Read the UserPromptSubmit payload, flip the flag on the keyword, and print the state line."""
    try:
        hook_input = read_hook_input_dictionary_from_stdin()
        context_text = toggle_context(hook_input) if hook_input is not None else None
    except Exception:
        return ALLOW_EXIT_CODE
    if context_text is not None:
        hook_event_output = {
            HOOK_EVENT_NAME_KEY: PROMPT_SUBMIT_EVENT_NAME,
            ADDITIONAL_CONTEXT_KEY: context_text,
        }
        sys.stdout.write(json.dumps({HOOK_SPECIFIC_OUTPUT_KEY: hook_event_output}))
    return ALLOW_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())
