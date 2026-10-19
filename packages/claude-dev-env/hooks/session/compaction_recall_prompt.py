#!/usr/bin/env python3
"""SessionStart hook: after a compaction, return the user's typed messages, trimmed.

::

    SessionStart, source compact, transcript_path set -> the trimmed messages
    any other source, no transcript_path, no messages -> nothing

The hook reads the session transcript, keeps the messages a person typed,
trims each one to its substance in Python, and returns the lines as
additionalContext. It runs as a command hook, so Claude Code and Codex both
run it, and it calls no model.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_hooks_directory = str(Path(__file__).resolve().parent.parent)
if _hooks_directory not in sys.path:
    sys.path.insert(0, _hooks_directory)
_session_directory = str(Path(__file__).resolve().parent)
if _session_directory not in sys.path:
    sys.path.insert(0, _session_directory)

from compaction_trim import recall_text
from compaction_user_messages import typed_user_messages
from hooks_constants.compaction_user_messages_constants import (
    ADDITIONAL_CONTEXT_KEY,
    COMPACTION_SOURCE,
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
from hooks_constants.setup_project_paths_constants import DECODE_ERRORS_POLICY, UTF8_ENCODING


def recall_context(all_hook_fields: dict[str, object]) -> str | None:
    """Return the trimmed messages for a compaction, or None for any other start.

    ::

        {"hook_event_name": "SessionStart", "source": "compact",
         "transcript_path": "/t/abc.jsonl"}
        -> "The context was just compacted, ...\\n\\n#1 fix login bug\\n#3 ..."

    Args:
        all_hook_fields: The parsed hook input.

    Returns:
        The additionalContext text, or None when the start is no compaction,
        the transcript cannot be read, or it holds no typed message.
    """
    if all_hook_fields.get(HOOK_EVENT_NAME_INPUT_KEY) != SESSION_START_EVENT_NAME:
        return None
    if all_hook_fields.get(SOURCE_INPUT_KEY) != COMPACTION_SOURCE:
        return None
    transcript_path = all_hook_fields.get(TRANSCRIPT_PATH_INPUT_KEY)
    if not isinstance(transcript_path, str) or not transcript_path:
        return None
    try:
        with Path(transcript_path).open(
            encoding=UTF8_ENCODING, errors=DECODE_ERRORS_POLICY
        ) as transcript:
            all_messages = typed_user_messages(transcript)
    except OSError:
        return None
    trimmed_messages = recall_text(all_messages)
    if trimmed_messages is None:
        return None
    return RECALL_CONTEXT_TEMPLATE.format(lines=trimmed_messages)


def main() -> None:
    """Print the trimmed messages as SessionStart additionalContext, or stay quiet."""
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
