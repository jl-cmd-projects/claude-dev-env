#!/usr/bin/env python3
"""UserPromptSubmit hook that reminds the agent to track a new ask before it starts.

The user follows a session in two places: the task list shows what the agent
does, and the title's status emoji shows whether the session needs them. A new
ask changes both, so the hook adds one short ``additionalContext`` note when the
prompt asks for work. The task list note shows on the session's first ask and
on the first ask after each compaction::

    "Export the APKs", first ask             -> task list note
    "Export the APKs", title shows a red flag or a check mark
                                             -> task list note + title note
    "Export the APKs", title tool and no title yet, first time in the session
                                             -> task list note + no title note
    "Sign the APKs", a later ask             -> nothing, or the title note
    "did the export fail?"                   -> nothing
    "<task-notification>...</task-notification>", title shows a red flag
                                             -> wake note
    "<task-notification>...</task-notification>", any other title
                                             -> nothing

A turn that an event starts carries no message from the user. The hook counts a
prompt as an event when it is one ``<task-notification>`` envelope, such as a
finished delegate, a pull request wake, or a turn review notice, or one queued
``<agent-message>`` hand-back, followed by nothing but reminder blocks. While
the title shows the red flag, the wake note asks the agent to set the status
that fits now if the event cleared what the user had to do. It shows on each
such prompt. Any other prompt gets no wake note.

The note never blocks. The Stop gate ``open_tasks_stop_gate.py`` holds the turn
once only when the agent skipped the task list. No hook holds a turn for the
title. All three title notes need the title tool in the transcript, and the no title
note shows at most once in a session, compactions included.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)
blocking_directory = str(Path(__file__).resolve().parent.parent / "blocking")
if blocking_directory not in sys.path:
    sys.path.insert(0, blocking_directory)

from hooks_constants.open_tasks_stop_gate_constants import (
    ALLOW_EXIT_CODE,
    PROMPT_KEY,
    PROMPT_SUBMIT_EVENT_NAME,
    TASK_LIST_NUDGE,
    TASK_LIST_NUDGE_ONCE_MARKER_NAME,
    TRANSCRIPT_PATH_KEY,
    WORD_SEPARATOR,
)
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
from hooks_constants.session_title_constants import (
    ALL_NO_WAKE_SENDER_NAMES,
    ALL_STALE_AT_START_STATUSES,
    NO_TITLE_NUDGE_ONCE_MARKER_NAME,
    NO_TITLE_NUDGE_TEMPLATE,
    RED_FLAG_STATUS,
    TITLE_NUDGE_TEMPLATE,
    TITLE_TOOL_DISPLAY_SEPARATOR,
    WAKE_EVENT_ENVELOPE_PATTERN,
    WAKE_FLAG_NUDGE_TEMPLATE,
    WAKE_SENDER_GROUP_NAME,
)
from once_per_session import claim_first_showing, claim_only_showing
from open_task_asks import is_ask, prompt_without_reminders
from session_title_transcript import (
    available_title_tools,
    read_transcript_entries,
    shown_title,
    title_status,
)


def title_nudge(
    all_entries: list[dict[str, object]], all_hook_fields: Mapping[str, object]
) -> str | None:
    """Return the title note when the session has no title or a stale one, else None.

    ::

        title tool listed, shows "\U0001f6a9 Merge approval"   -> note naming that title
        title tool listed, no title                             -> no title note, once a session
        title tool listed, shows "⏳ Export"                     -> None
        no title tool in the transcript                         -> None

    Args:
        all_entries: The transcript entries, oldest first.
        all_hook_fields: The hook payload, read for the once-per-session marker.

    Returns:
        The note text, or None.
    """
    all_title_tools = available_title_tools(all_entries)
    if not all_title_tools:
        return None
    tool_name = TITLE_TOOL_DISPLAY_SEPARATOR.join(all_title_tools)
    title = shown_title(all_entries)
    if title is None:
        is_first_showing = claim_only_showing(NO_TITLE_NUDGE_ONCE_MARKER_NAME, all_hook_fields)
        return NO_TITLE_NUDGE_TEMPLATE.format(tool_name=tool_name) if is_first_showing else None
    if title_status(title) not in ALL_STALE_AT_START_STATUSES:
        return None
    return TITLE_NUDGE_TEMPLATE.format(title=title, tool_name=tool_name)


def is_event_wake(prompt_text: str) -> bool:
    """Return True when a harness event sent the whole prompt, with no words from the user.

    ::

        "<task-notification>...</task-notification>"                    -> True
        '<agent-message from="a1">...</agent-message>'                   -> True
        "<task-notification>...</task-notification><system-reminder>...</system-reminder>"
                                                                         -> True
        "<task-notification>...</task-notification> Why did it fail?"   -> False
        '<agent-message from=" Human">...</agent-message>', from=""     -> False
        "<task-notification>It quotes </task-notification>.</task-notification>"
                                                                         -> False
        '<task-notification id="a1">...', "<TASK-NOTIFICATION>..."      -> False
        "", "<system-reminder>...</system-reminder>", '<wake ...>...'    -> False

    The prompt must open, after white space, with one envelope. Its opening tag
    is a bare lower case ``<task-notification>``, or ``<agent-message>`` with
    ``from`` as its only attribute. The sender must not be empty or ``human``.
    The sender check ignores letter case and the white space around the name.
    Only reminder blocks and white space may follow the envelope.

    The first closing tag ends the envelope. A body that quotes its own closing
    tag reads as an envelope with typed text after it, so it is no wake.
    """
    text = prompt_text.lstrip()
    envelope = WAKE_EVENT_ENVELOPE_PATTERN.match(text)
    if envelope is None:
        return False
    sender = envelope.group(WAKE_SENDER_GROUP_NAME)
    if sender is not None and sender.strip().casefold() in ALL_NO_WAKE_SENDER_NAMES:
        return False
    return not prompt_without_reminders(text[envelope.end() :])


def wake_flag_nudge(prompt_text: str, all_entries: list[dict[str, object]]) -> str | None:
    """Return the wake note when an event starts the turn while the title shows the red flag.

    ::

        "<task-notification>...", title shows "\U0001f6a9 Merge approval" -> note naming it
        "<task-notification>...", shows "✅ Gate" or "⏳ Export"          -> None
        "Export the APKs", title shows "\U0001f6a9 Merge approval"        -> None
        no title tool in the transcript                                  -> None

    Args:
        prompt_text: The ``prompt`` field of the UserPromptSubmit payload.
        all_entries: The transcript entries, oldest first.

    Returns:
        The note text, or None.
    """
    if not is_event_wake(prompt_text):
        return None
    all_title_tools = available_title_tools(all_entries)
    title = shown_title(all_entries)
    if not all_title_tools or title is None or title_status(title) != RED_FLAG_STATUS:
        return None
    tool_name = TITLE_TOOL_DISPLAY_SEPARATOR.join(all_title_tools)
    return WAKE_FLAG_NUDGE_TEMPLATE.format(title=title, tool_name=tool_name)


def ask_tracking_context(
    prompt_text: str,
    all_entries: list[dict[str, object]],
    all_hook_fields: Mapping[str, object],
) -> str | None:
    """Return the note for a prompt that asks for work, the wake note for an event, else None.

    The task list note shows on the session's first ask and on the first ask
    after each compaction. The title note shows on every ask while the title is
    stale, and the no title note on the first ask in the session that finds no
    title. A prompt that asks for no work gets only the wake note, and only when
    ``wake_flag_nudge`` builds one.
    """
    if not is_ask(prompt_text):
        return wake_flag_nudge(prompt_text, all_entries)
    tracker_note = (
        TASK_LIST_NUDGE
        if claim_first_showing(TASK_LIST_NUDGE_ONCE_MARKER_NAME, all_hook_fields)
        else None
    )
    all_notes = [tracker_note, title_nudge(all_entries, all_hook_fields)]
    return WORD_SEPARATOR.join(each_note for each_note in all_notes if each_note) or None


def main() -> int:
    hook_input = read_hook_input_dictionary_from_stdin()
    prompt_value = hook_input.get(PROMPT_KEY) if hook_input is not None else None
    if hook_input is None or not isinstance(prompt_value, str):
        return ALLOW_EXIT_CODE
    context_text = ask_tracking_context(
        prompt_value, read_transcript_entries(hook_input.get(TRANSCRIPT_PATH_KEY)), hook_input
    )
    if context_text:
        hook_output = {
            "hookSpecificOutput": {
                "hookEventName": PROMPT_SUBMIT_EVENT_NAME,
                "additionalContext": context_text,
            }
        }
        sys.stdout.write(json.dumps(hook_output))
    return ALLOW_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())
