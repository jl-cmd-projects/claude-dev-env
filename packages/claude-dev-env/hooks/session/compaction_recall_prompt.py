#!/usr/bin/env python3
"""SessionStart hook: after a compaction, tell the agent to recall the user's messages.

::

    SessionStart, source compact, transcript_path set -> run the extractor command
    any other source, or no transcript_path           -> nothing

The context names one Bash command that runs ``compaction_user_messages.py``
on this session's transcript. A PostToolUse agent hook in ``hooks.json``
matches that command and returns the user's messages, condensed.
"""

from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

_hooks_directory = str(Path(__file__).resolve().parent.parent)
if _hooks_directory not in sys.path:
    sys.path.insert(0, _hooks_directory)

from hooks_constants.compaction_user_messages_constants import (
    ADDITIONAL_CONTEXT_KEY,
    COMPACTION_SOURCE,
    EXTRACTOR_SCRIPT_NAME,
    HOOK_EVENT_NAME_INPUT_KEY,
    RECALL_CONTEXT_TEMPLATE,
    SESSION_START_EVENT_NAME,
    SOURCE_INPUT_KEY,
    TRANSCRIPT_PATH_INPUT_KEY,
)
from hooks_constants.hook_specific_output_keys import (
    HOOK_EVENT_NAME_KEY,
    HOOK_SPECIFIC_OUTPUT_KEY,
)
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin


def recall_context(all_hook_fields: dict[str, object]) -> str | None:
    """Return the recall instruction for a compaction, or None for any other start.

    ::

        {"hook_event_name": "SessionStart", "source": "compact",
         "transcript_path": "/t/abc.jsonl"}
        -> "...run this Bash command:\\n\\n'/usr/bin/python3' '.../compaction_user_messages.py' /t/abc.jsonl..."

    The command names the interpreter running this hook, so it works where
    ``python3`` is not on PATH.

    Args:
        all_hook_fields: The parsed hook input.

    Returns:
        The additionalContext text, or None.
    """
    if all_hook_fields.get(HOOK_EVENT_NAME_INPUT_KEY) != SESSION_START_EVENT_NAME:
        return None
    if all_hook_fields.get(SOURCE_INPUT_KEY) != COMPACTION_SOURCE:
        return None
    transcript_path = all_hook_fields.get(TRANSCRIPT_PATH_INPUT_KEY)
    if not isinstance(transcript_path, str) or not transcript_path:
        return None
    extractor_path = Path(__file__).resolve().parent / EXTRACTOR_SCRIPT_NAME
    command = shlex.join([sys.executable, str(extractor_path), transcript_path])
    return RECALL_CONTEXT_TEMPLATE.format(command=command)


def main() -> None:
    """Print the recall instruction as SessionStart additionalContext, or stay quiet."""
    hook_input = read_hook_input_dictionary_from_stdin()
    if hook_input is None:
        return
    context_text = recall_context(hook_input)
    if context_text is None:
        return
    hook_output = {
        HOOK_SPECIFIC_OUTPUT_KEY: {
            HOOK_EVENT_NAME_KEY: SESSION_START_EVENT_NAME,
            ADDITIONAL_CONTEXT_KEY: context_text,
        }
    }
    sys.stdout.write(json.dumps(hook_output) + "\n")


if __name__ == "__main__":
    main()
