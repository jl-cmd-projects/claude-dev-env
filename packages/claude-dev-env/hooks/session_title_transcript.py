"""Read the session title tool and the shown title from a Claude Code transcript.

The prompt hooks use this module to learn two facts about a session::

    attachment.tools[].name / attachment.entries[].name   (tool listing)
    attachment.addedNames / attachment.readdedNames       (deferred tools)
    assistant tool_use name                               (an earlier call)
        -> the session has a ``mcp__*__set_session_title`` tool

    main-chain title call whose result came back without an error
        -> the title the session shows

A later ``removedNames`` entry takes a title tool away again. A title call on a
sidechain entry belongs to a subagent and does not count, and neither does a
title the format gate denied.
"""

from __future__ import annotations

import json
from pathlib import Path

from hooks_constants.session_title_constants import (
    ALL_TOOL_LISTING_NAME_KEYS,
    ALL_TOOL_LISTING_RECORD_KEYS,
    ASSISTANT_ENTRY_TYPE,
    ATTACHMENT_KEY,
    BLOCK_ID_KEY,
    BLOCK_INPUT_KEY,
    BLOCK_NAME_KEY,
    CONTENT_KEY,
    DECODE_ERRORS_POLICY,
    ENTRY_TYPE_KEY,
    IS_ERROR_KEY,
    MESSAGE_KEY,
    REMOVED_NAMES_KEY,
    SIDECHAIN_FLAG_KEY,
    STATUS_PREFIX_PATTERN,
    TITLE_INPUT_KEY,
    TITLE_TOOL_NAME_PATTERN,
    TOOL_RESULT_BLOCK_TYPE,
    TOOL_USE_BLOCK_TYPE,
    TOOL_USE_ID_KEY,
    USER_ENTRY_TYPE,
    UTF8_ENCODING,
)


def _content_blocks(all_entry_fields: dict[str, object]) -> list[dict[str, object]]:
    message = all_entry_fields.get(MESSAGE_KEY)
    content = message.get(CONTENT_KEY) if isinstance(message, dict) else None
    if not isinstance(content, list):
        return []
    return [each_block for each_block in content if isinstance(each_block, dict)]


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


def _apply_tool_listing(
    all_available_names: dict[str, None], all_attachment_fields: dict[str, object]
) -> None:
    for each_key in (*ALL_TOOL_LISTING_NAME_KEYS, *ALL_TOOL_LISTING_RECORD_KEYS):
        all_available_names.update(dict.fromkeys(_title_names(all_attachment_fields.get(each_key))))
    for each_removed_name in _title_names(all_attachment_fields.get(REMOVED_NAMES_KEY)):
        all_available_names.pop(each_removed_name, None)


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


def _main_chain(all_entries: list[dict[str, object]]) -> list[dict[str, object]]:
    return [each_entry for each_entry in all_entries if not each_entry.get(SIDECHAIN_FLAG_KEY)]


def _successful_title_call_ids(all_scoped_entries: list[dict[str, object]]) -> set[object]:
    all_title_call_ids = {
        each_block.get(BLOCK_ID_KEY)
        for each_entry in all_scoped_entries
        for each_block in _tool_use_blocks(each_entry)
        if TITLE_TOOL_NAME_PATTERN.match(str(each_block.get(BLOCK_NAME_KEY)))
    }
    return {
        each_block.get(TOOL_USE_ID_KEY)
        for each_entry in all_scoped_entries
        if each_entry.get(ENTRY_TYPE_KEY) == USER_ENTRY_TYPE
        for each_block in _content_blocks(each_entry)
        if each_block.get(ENTRY_TYPE_KEY) == TOOL_RESULT_BLOCK_TYPE
        and each_block.get(TOOL_USE_ID_KEY) in all_title_call_ids
        and not each_block.get(IS_ERROR_KEY)
    }


def _title_input(all_block_fields: dict[str, object]) -> str | None:
    all_input_fields = all_block_fields.get(BLOCK_INPUT_KEY)
    title = all_input_fields.get(TITLE_INPUT_KEY) if isinstance(all_input_fields, dict) else None
    return title if isinstance(title, str) else None


def shown_title(all_entries: list[dict[str, object]]) -> str | None:
    """Return the title of the last main-chain title call that came back without an error.

    ::

        "⏳ Export" ok, then "✅ Export" denied   -> "⏳ Export"
        no title call                                -> None

    Args:
        all_entries: The transcript entries, oldest first.

    Returns:
        The title the session shows, or None when no title call succeeded.
    """
    all_main_entries = _main_chain(all_entries)
    all_successful_ids = _successful_title_call_ids(all_main_entries)
    all_titles = [
        _title_input(each_block)
        for each_entry in all_main_entries
        for each_block in _tool_use_blocks(each_entry)
        if each_block.get(BLOCK_ID_KEY) in all_successful_ids
    ]
    all_text_titles = [each_title for each_title in all_titles if each_title is not None]
    return all_text_titles[-1] if all_text_titles else None


def title_status(title: str) -> str | None:
    """Return the status emoji the title starts with, without a variation selector, or None."""
    status_match = STATUS_PREFIX_PATTERN.match(title)
    return status_match.group(1) if status_match else None


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
