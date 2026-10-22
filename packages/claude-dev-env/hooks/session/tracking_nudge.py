#!/usr/bin/env python3
"""UserPromptSubmit hook that reminds the agent to track a new ask before it starts.

The user follows a session in two places: the task list shows what the agent
does, and the title's status emoji shows whether the session needs them. A new
ask changes both, so the hook adds one short ``additionalContext`` note when the
prompt asks for work::

    "Export the APKs"                        -> task list note
    "Export the APKs", title shows a red flag or a check mark
                                             -> task list note + title note
    "did the export fail?"                   -> nothing
    "<task-notification>...</task-notification>"
                                             -> nothing

The note never blocks. The Stop gates ``open_tasks_stop_gate.py`` and
``session_title_turn_gate.py`` hold the turn once only when the agent skipped it.
The title note needs the title tool in the transcript, as the title gate does.
"""

from __future__ import annotations

import json
import sys
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
    TRANSCRIPT_PATH_KEY,
    WORD_SEPARATOR,
)
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
from hooks_constants.session_title_constants import (
    ALL_STALE_AT_START_STATUSES,
    TITLE_NUDGE_TEMPLATE,
    TITLE_TOOL_DISPLAY_SEPARATOR,
)
from open_task_asks import is_ask
from session_title_turn_gate import (
    available_title_tools,
    read_transcript_entries,
    shown_title,
    title_status,
)


def title_nudge(all_entries: list[dict[str, object]]) -> str | None:
    """Return the title note when the shown title says the session waits or is done, else None.

    ::

        title tool listed, shows "\U0001f6a9 Merge approval"   -> note naming that title
        title tool listed, shows "⏳ Export"               -> None
        no title tool in the transcript                         -> None

    Args:
        all_entries: The transcript entries, oldest first.

    Returns:
        The note text, or None.
    """
    all_title_tools = available_title_tools(all_entries)
    title = shown_title(all_entries)
    if (
        not all_title_tools
        or title is None
        or title_status(title) not in ALL_STALE_AT_START_STATUSES
    ):
        return None
    return TITLE_NUDGE_TEMPLATE.format(
        title=title, tool_name=TITLE_TOOL_DISPLAY_SEPARATOR.join(all_title_tools)
    )


def ask_tracking_context(prompt_text: str, all_entries: list[dict[str, object]]) -> str | None:
    """Return the note for a prompt that asks for work, or None for any other prompt."""
    if not is_ask(prompt_text):
        return None
    all_notes = [TASK_LIST_NUDGE, title_nudge(all_entries)]
    return WORD_SEPARATOR.join(each_note for each_note in all_notes if each_note)


def main() -> int:
    hook_input = read_hook_input_dictionary_from_stdin()
    prompt_value = hook_input.get(PROMPT_KEY) if hook_input is not None else None
    if hook_input is None or not isinstance(prompt_value, str):
        return ALLOW_EXIT_CODE
    context_text = ask_tracking_context(
        prompt_value, read_transcript_entries(hook_input.get(TRANSCRIPT_PATH_KEY))
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
