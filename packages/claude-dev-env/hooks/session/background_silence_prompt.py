#!/usr/bin/env python3
"""UserPromptSubmit hook that keeps a background event turn silent while the user asked for silence.

The user tells the session to stay quiet. A background event, such as a
finished delegate or a monitor line, still starts a turn, and each such turn
tends to end with a line like "No change." The hook adds one note to that turn::

    user said "silent unless something merges", prompt is a <task-notification>
                                                -> note quoting "unless something merges"
    same transcript, the prompt is user-typed   -> nothing
    the user later said "you can talk again"    -> nothing
    the user never asked for silence            -> nothing

The newest user-typed message that sets or lifts silence decides it. A prompt
that starts with an envelope such as ``<task-notification>`` or
``<agent-message>``, a ``[SYSTEM NOTIFICATION - NOT USER INPUT]`` prompt, a
compaction summary, and a quoted ``>`` line are not the user's words.

A Stop hook cannot hold this, because the reply is already on screen when Stop
runs.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)
blocking_directory = str(Path(__file__).resolve().parent.parent / "blocking")
if blocking_directory not in sys.path:
    sys.path.insert(0, blocking_directory)

from hooks_constants.background_silence_prompt_constants import (
    ALL_LIFT_PATTERNS,
    ALL_SET_PATTERNS,
    BACKGROUND_EVENT_MARKER,
    EXCEPTION_CLAUSE_PATTERN,
    HUMAN_ORIGIN_KIND,
    MAXIMUM_EXCEPTION_CHARACTERS,
    ORIGIN_KEY,
    ORIGIN_KIND_KEY,
    QUOTED_LINE_PATTERN,
    SILENCE_NOTE_TEMPLATE,
    SILENCE_NOTE_WITHOUT_EXCEPTION,
    TASK_NOTIFICATION_MARKER,
)
from hooks_constants.hook_specific_output_keys import (
    HOOK_EVENT_NAME_KEY,
    HOOK_SPECIFIC_OUTPUT_KEY,
)
from hooks_constants.open_tasks_stop_gate_constants import (
    ALL_ASK_ONLY_ENVELOPE_MARKERS,
    ALLOW_EXIT_CODE,
    PROMPT_KEY,
    PROMPT_SUBMIT_EVENT_NAME,
    SENTENCE_SPLIT_PATTERN,
    TRANSCRIPT_PATH_KEY,
)
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
from hooks_constants.reply_length_gate_constants import ADDITIONAL_CONTEXT_KEY
from hooks_constants.spawn_readiness_hook_constants import (
    ALL_HARNESS_ENVELOPE_MARKERS,
    HUMAN_SENDER_MARKER,
)
from open_task_asks import prompt_without_reminders
from open_tasks_transcript import claude_prompt_text
from session_title_turn_gate import read_transcript_entries


def _is_user_typed_text(prompt_text: str) -> bool:
    if BACKGROUND_EVENT_MARKER in prompt_text:
        return False
    stripped_text = prompt_without_reminders(prompt_text)
    if stripped_text.startswith((*ALL_HARNESS_ENVELOPE_MARKERS, *ALL_ASK_ONLY_ENVELOPE_MARKERS)):
        return HUMAN_SENDER_MARKER in stripped_text
    return bool(stripped_text)


def _user_words(all_record_fields: dict[str, object]) -> str | None:
    origin = all_record_fields.get(ORIGIN_KEY)
    if isinstance(origin, dict) and origin.get(ORIGIN_KIND_KEY) not in (None, HUMAN_ORIGIN_KIND):
        return None
    prompt_text = claude_prompt_text(all_record_fields)
    if prompt_text is None or not _is_user_typed_text(prompt_text):
        return None
    return QUOTED_LINE_PATTERN.sub("", prompt_without_reminders(prompt_text)).strip()


def _sets_silence(text: str) -> bool:
    return any(each_pattern.search(text) for each_pattern in ALL_SET_PATTERNS)


def is_background_event(prompt_text: str) -> bool:
    """Return True when the submitted prompt is a background event and not the user's own words.

    ::

        "<task-notification>...</task-notification>"                 -> True
        "<system-reminder>[SYSTEM NOTIFICATION - NOT USER INPUT]..." -> True
        "did PR 12 merge?"                                           -> False
        '<agent-message from="a1">Report</agent-message>'            -> False

    Args:
        prompt_text: The ``prompt`` field of the UserPromptSubmit payload.

    Returns:
        True for a prompt that starts with ``<task-notification>`` after its
        ``<system-reminder>`` blocks, or that holds the system notification marker.
    """
    if _is_user_typed_text(prompt_text):
        return False
    return BACKGROUND_EVENT_MARKER in prompt_text or prompt_without_reminders(
        prompt_text
    ).startswith(TASK_NOTIFICATION_MARKER)


def newest_silence_message(all_entries: list[dict[str, object]]) -> str | None:
    """Return the user's newest message that sets silence, or None once a newer one lifts it.

    ::

        "Silent on updates unless something merges"   -> that message
        ... then "ok you can talk again"               -> None
        ... then "stay silent unless blocked"          -> "stay silent unless blocked"
        no user message names silence                  -> None

    Args:
        all_entries: The transcript entries, oldest first.

    Returns:
        The message text with its quoted lines removed, or None.
    """
    for each_entry in reversed(all_entries):
        user_words = _user_words(each_entry)
        if not user_words:
            continue
        if any(each_pattern.search(user_words) for each_pattern in ALL_LIFT_PATTERNS):
            return None
        if _sets_silence(user_words):
            return user_words
    return None


def exception_clause(silence_message: str) -> str | None:
    """Return the exception the user gave, word for word, or None when they gave none.

    The clause runs from "unless" or "except" to the end of the sentence that
    sets silence::

        "Silent on updates unless something merges or youre blocked"
                                    -> "unless something merges or youre blocked"
        "Stay silent."              -> None

    Args:
        silence_message: The message ``newest_silence_message`` returned.

    Returns:
        The clause, cut to MAXIMUM_EXCEPTION_CHARACTERS, or None.
    """
    for each_sentence in re.split(SENTENCE_SPLIT_PATTERN, silence_message):
        if not _sets_silence(each_sentence):
            continue
        clause_match = EXCEPTION_CLAUSE_PATTERN.search(each_sentence)
        if clause_match is None:
            return None
        return clause_match.group(0).strip()[:MAXIMUM_EXCEPTION_CHARACTERS]
    return None


def silence_context(all_entries: list[dict[str, object]]) -> str | None:
    """Return the note for a background event turn while the user asked for silence, else None.

    Args:
        all_entries: The transcript entries, oldest first.

    Returns:
        The note that quotes the user's exception, the note with no exception, or None.
    """
    silence_message = newest_silence_message(all_entries)
    if silence_message is None:
        return None
    clause = exception_clause(silence_message)
    if clause is None:
        return SILENCE_NOTE_WITHOUT_EXCEPTION
    return SILENCE_NOTE_TEMPLATE.format(exception_clause=clause)


def main() -> int:
    hook_input = read_hook_input_dictionary_from_stdin()
    prompt_value = hook_input.get(PROMPT_KEY) if hook_input is not None else None
    if (
        hook_input is None
        or not isinstance(prompt_value, str)
        or not is_background_event(prompt_value)
    ):
        return ALLOW_EXIT_CODE
    context_text = silence_context(read_transcript_entries(hook_input.get(TRANSCRIPT_PATH_KEY)))
    if context_text:
        hook_event_output = {
            HOOK_EVENT_NAME_KEY: PROMPT_SUBMIT_EVENT_NAME,
            ADDITIONAL_CONTEXT_KEY: context_text,
        }
        sys.stdout.write(json.dumps({HOOK_SPECIFIC_OUTPUT_KEY: hook_event_output}))
    return ALLOW_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())
