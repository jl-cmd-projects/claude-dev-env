#!/usr/bin/env python3
"""Stop hook that holds a turn until it sets the session title.

A turn starts after the latest user prompt in the transcript. Tool results,
meta entries, sidechain entries and compaction summaries are not prompts, and
a Stop hook block lands as an attachment, so a held turn stays the same turn.
A title call on a sidechain entry belongs to a subagent and does not count.
The turn may end once a tool whose name ends in __set_session_title ran in it
and its result came back without an error. A title the format gate denied
does not count. A held turn (``stop_hook_active`` true) whose title call
failed may end, so a title tool that keeps failing cannot hold it forever. A
held turn with no title call stays held, whichever Stop gate held it.

The session has the title tool when a transcript record names it::

    attachment.tools[].name / attachment.entries[].name   (tool listing)
    attachment.addedNames / attachment.readdedNames       (deferred tools)
    assistant tool_use name                               (an earlier call)

A later ``removedNames`` entry takes the name away again. With no such record,
or with an unreadable transcript, the hook lets the turn end, so Codex,
Cursor and sessions without the tool keep working.

A block writes ``{"decision": "block", "reason": ...}`` to stdout. The reason
names the four status emoji and tells the model to close with one short
sentence, so the held turn neither ends empty nor repeats the reply.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)

from hooks_constants.hook_block_logger import log_hook_block
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
from hooks_constants.session_title_constants import (
    ALL_SKIPPED_PROMPT_FLAGS,
    ALL_TOOL_LISTING_NAME_KEYS,
    ALL_TOOL_LISTING_RECORD_KEYS,
    ALLOW_EXIT_CODE,
    ASSISTANT_ENTRY_TYPE,
    ATTACHMENT_KEY,
    BLOCK_DECISION,
    BLOCK_ID_KEY,
    BLOCK_NAME_KEY,
    CONTENT_KEY,
    DECISION_KEY,
    DECODE_ERRORS_POLICY,
    ENTRY_TYPE_KEY,
    IS_ERROR_KEY,
    MESSAGE_KEY,
    REASON_KEY,
    REMOVED_NAMES_KEY,
    SIDECHAIN_FLAG_KEY,
    STOP_HOOK_ACTIVE_KEY,
    TITLE_TOOL_DISPLAY_SEPARATOR,
    TITLE_TOOL_NAME_PATTERN,
    TOOL_RESULT_BLOCK_TYPE,
    TOOL_USE_BLOCK_TYPE,
    TOOL_USE_ID_KEY,
    TRANSCRIPT_PATH_KEY,
    TURN_BLOCK_REASON,
    TURN_GATE_EVENT_NAME,
    USER_ENTRY_TYPE,
    UTF8_ENCODING,
)


def _content_blocks(all_entry_fields: dict[str, object]) -> list[dict[str, object]]:
    message = all_entry_fields.get(MESSAGE_KEY)
    content = message.get(CONTENT_KEY) if isinstance(message, dict) else None
    if not isinstance(content, list):
        return []
    return [each_block for each_block in content if isinstance(each_block, dict)]


def _is_user_prompt(all_entry_fields: dict[str, object]) -> bool:
    if all_entry_fields.get(ENTRY_TYPE_KEY) != USER_ENTRY_TYPE:
        return False
    if any(all_entry_fields.get(each_flag) for each_flag in ALL_SKIPPED_PROMPT_FLAGS):
        return False
    message = all_entry_fields.get(MESSAGE_KEY)
    content = message.get(CONTENT_KEY) if isinstance(message, dict) else None
    if isinstance(content, str):
        return bool(content.strip())
    return any(
        each_block.get(ENTRY_TYPE_KEY) != TOOL_RESULT_BLOCK_TYPE
        for each_block in _content_blocks(all_entry_fields)
    )


def _tool_use_blocks(all_entry_fields: dict[str, object]) -> list[dict[str, object]]:
    if all_entry_fields.get(ENTRY_TYPE_KEY) != ASSISTANT_ENTRY_TYPE:
        return []
    return [
        each_block
        for each_block in _content_blocks(all_entry_fields)
        if each_block.get(ENTRY_TYPE_KEY) == TOOL_USE_BLOCK_TYPE
    ]


def _title_names(all_values: object) -> list[str]:
    if not isinstance(all_values, list):
        return []
    all_names = [
        each_value.get(BLOCK_NAME_KEY) if isinstance(each_value, dict) else each_value
        for each_value in all_values
    ]
    return [
        each_name
        for each_name in all_names
        if isinstance(each_name, str) and TITLE_TOOL_NAME_PATTERN.match(each_name)
    ]


def available_title_tools(all_entries: list[dict[str, object]]) -> list[str]:
    """Return the title tool names the session holds at the end of the transcript.

    ::

        attachment {"tools": [{"name": "mcp__x__set_session_title"}]}   -> ["mcp__x__set_session_title"]
        then attachment {"removedNames": ["mcp__x__set_session_title"]} -> []
        no listing and no call                                          -> []

    Args:
        all_entries: The transcript entries, oldest first.

    Returns:
        The title tool names, in the order the transcript first named them.
    """
    available_names: dict[str, None] = {}
    for each_entry in all_entries:
        attachment = each_entry.get(ATTACHMENT_KEY)
        if isinstance(attachment, dict):
            _apply_tool_listing(available_names, attachment)
        available_names.update(dict.fromkeys(_title_names(_tool_use_blocks(each_entry))))
    return list(available_names)


def _apply_tool_listing(
    all_available_names: dict[str, None], all_attachment_fields: dict[str, object]
) -> None:
    for each_key in (*ALL_TOOL_LISTING_NAME_KEYS, *ALL_TOOL_LISTING_RECORD_KEYS):
        all_available_names.update(
            dict.fromkeys(_title_names(all_attachment_fields.get(each_key)))
        )
    for each_removed_name in _title_names(all_attachment_fields.get(REMOVED_NAMES_KEY)):
        all_available_names.pop(each_removed_name, None)


def _turn_entries(all_entries: list[dict[str, object]]) -> list[dict[str, object]]:
    last_prompt_index = max(
        (
            each_index
            for each_index, each_entry in enumerate(all_entries)
            if _is_user_prompt(each_entry)
        ),
        default=-1,
    )
    return [
        each_entry
        for each_entry in all_entries[last_prompt_index + 1 :]
        if not each_entry.get(SIDECHAIN_FLAG_KEY)
    ]


def _title_call_ids(all_turn_entries: list[dict[str, object]]) -> set[object]:
    return {
        each_block.get(BLOCK_ID_KEY)
        for each_entry in all_turn_entries
        for each_block in _tool_use_blocks(each_entry)
        if TITLE_TOOL_NAME_PATTERN.match(str(each_block.get(BLOCK_NAME_KEY)))
    }


def title_attempted_this_turn(all_entries: list[dict[str, object]]) -> bool:
    """Return True when a title call ran after the latest prompt, whatever its result.

    Args:
        all_entries: The transcript entries, oldest first.

    Returns:
        True when this turn called the title tool.
    """
    return bool(_title_call_ids(_turn_entries(all_entries)))


def title_set_this_turn(all_entries: list[dict[str, object]]) -> bool:
    """Return True when a title call after the latest prompt came back without an error.

    ::

        prompt -> set_session_title -> ok result      -> True
        prompt -> set_session_title -> denied result  -> False
        set_session_title -> ok result -> prompt      -> False

    Args:
        all_entries: The transcript entries, oldest first.

    Returns:
        True when this turn set the title.
    """
    all_turn_entries = _turn_entries(all_entries)
    all_title_call_ids = _title_call_ids(all_turn_entries)
    return any(
        each_block.get(ENTRY_TYPE_KEY) == TOOL_RESULT_BLOCK_TYPE
        and each_block.get(TOOL_USE_ID_KEY) in all_title_call_ids
        and not each_block.get(IS_ERROR_KEY)
        for each_entry in all_turn_entries
        if each_entry.get(ENTRY_TYPE_KEY) == USER_ENTRY_TYPE
        for each_block in _content_blocks(each_entry)
    )


def turn_block_reason(
    all_entries: list[dict[str, object]], is_stop_hook_active: bool = False
) -> str | None:
    """Return the reason to hold the turn, or None when the turn may end.

    ::

        no title tool in the transcript                         -> None
        title set this turn                                     -> None
        held turn whose title call failed (stop_hook_active)    -> None
        no title call this turn                                 -> reason

    Args:
        all_entries: The transcript entries, oldest first.
        is_stop_hook_active: True when a Stop hook already held this turn.

    Returns:
        The block reason that names the title tool, or None.
    """
    all_title_tools = available_title_tools(all_entries)
    if not all_title_tools or title_set_this_turn(all_entries):
        return None
    if is_stop_hook_active and title_attempted_this_turn(all_entries):
        return None
    return TURN_BLOCK_REASON.format(tool_name=TITLE_TOOL_DISPLAY_SEPARATOR.join(all_title_tools))


def _parsed_entry(line: str) -> dict[str, object] | None:
    try:
        parsed_entry = json.loads(line)
    except json.JSONDecodeError:
        return None
    return parsed_entry if isinstance(parsed_entry, dict) else None


def read_transcript_entries(transcript_path: object) -> list[dict[str, object]]:
    """Return the transcript's JSON object entries, or an empty list when it cannot be read."""
    if not isinstance(transcript_path, str) or not transcript_path:
        return []
    try:
        all_lines = (
            Path(transcript_path)
            .read_text(encoding=UTF8_ENCODING, errors=DECODE_ERRORS_POLICY)
            .splitlines()
        )
    except OSError:
        return []
    all_parsed_entries = (_parsed_entry(each_line) for each_line in all_lines)
    return [each_entry for each_entry in all_parsed_entries if each_entry is not None]


def main() -> int:
    hook_input = read_hook_input_dictionary_from_stdin()
    if hook_input is None:
        return ALLOW_EXIT_CODE
    block_reason = turn_block_reason(
        read_transcript_entries(hook_input.get(TRANSCRIPT_PATH_KEY)),
        hook_input.get(STOP_HOOK_ACTIVE_KEY) is True,
    )
    if block_reason is None:
        return ALLOW_EXIT_CODE
    log_hook_block(Path(__file__).name, TURN_GATE_EVENT_NAME, block_reason)
    sys.stdout.write(json.dumps({DECISION_KEY: BLOCK_DECISION, REASON_KEY: block_reason}))
    return ALLOW_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())
