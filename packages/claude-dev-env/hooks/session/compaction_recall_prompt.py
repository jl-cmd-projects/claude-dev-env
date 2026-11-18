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

import argparse
import json
import sys
from pathlib import Path

_hooks_directory = str(Path(__file__).resolve().parent.parent)
if _hooks_directory not in sys.path:
    sys.path.insert(0, _hooks_directory)
_session_directory = str(Path(__file__).resolve().parent)
if _session_directory not in sys.path:
    sys.path.insert(0, _session_directory)

from compaction_trim import recall_with_clipping
from compaction_user_messages import typed_user_messages
from hooks_constants.compaction_user_messages_constants import (
    ADDITIONAL_CONTEXT_KEY,
    CODEX_READER_HINT,
    CODEX_RECALL_FLAG,
    COMPACTION_SOURCE,
    HOOK_EVENT_NAME_INPUT_KEY,
    READ_USER_TURNS_FLAG,
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


def recall_context(all_hook_fields: dict[str, object], *, is_codex: bool = False) -> str | None:
    """Return the trimmed messages for a compaction, or None for any other start.

    ::

        {"hook_event_name": "SessionStart", "source": "compact",
         "transcript_path": "/t/abc.jsonl"}
        -> "The context was just compacted, ...\\n\\n#1 fix login bug\\n#3 ..."

    Args:
        all_hook_fields: The parsed hook input.
        is_codex: Whether the installer selected the Codex compact entry point.

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
    trimmed_messages, has_clipping = recall_with_clipping(all_messages)
    if trimmed_messages is None:
        return None
    context = RECALL_CONTEXT_TEMPLATE.format(lines=trimmed_messages)
    if is_codex and has_clipping:
        arguments = [sys.executable, "-IB", str(Path(__file__).resolve()), READ_USER_TURNS_FLAG,
                     str(Path(transcript_path).absolute()), "FIRST"]
        context += CODEX_READER_HINT.format(arguments=json.dumps(arguments, ensure_ascii=False))
    return context


def read_user_turns(transcript_path: Path, first: int, last: int | None) -> list[dict[str, object]]:
    """Read an inclusive range from the same user-turn ordering the hook displays.

    Args:
        transcript_path: Current transcript from the compact event.
        first: First requested user turn, counting from one.
        last: Last requested user turn, defaulting to the first.

    Returns:
        Positions and original text of the selected user turns.

    Raises:
        ValueError: A requested position falls outside the current transcript.
        OSError: The session transcript cannot be read.
    """
    with transcript_path.open(encoding=UTF8_ENCODING, errors=DECODE_ERRORS_POLICY) as transcript:
        all_turns = typed_user_messages(transcript, should_preserve_codex_text=True)
    final_position = first if last is None else last
    if not 1 <= first <= final_position <= len(all_turns):
        raise ValueError(f"Choose an inclusive range within turns 1 through {len(all_turns)}")
    return [{"position": turn.position, "text": turn.text} for turn in all_turns[first - 1:final_position]]


def main() -> None:
    """Print the trimmed messages as SessionStart additionalContext, or stay quiet."""
    arguments = sys.argv[1:]
    if arguments[:1] == [READ_USER_TURNS_FLAG]:
        parser = argparse.ArgumentParser(description=read_user_turns.__doc__)
        parser.add_argument("transcript", type=Path)
        parser.add_argument("first", type=int)
        parser.add_argument("last", type=int, nargs="?")
        selection = parser.parse_args(arguments[1:])
        try:
            turns = read_user_turns(selection.transcript, selection.first, selection.last)
        except (OSError, ValueError) as error:
            parser.error(str(error))
        json.dump(turns, sys.stdout)
        return
    hook_input = read_hook_input_dictionary_from_stdin()
    if hook_input is None:
        return
    context_text = recall_context(hook_input, is_codex=arguments == [CODEX_RECALL_FLAG])
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
