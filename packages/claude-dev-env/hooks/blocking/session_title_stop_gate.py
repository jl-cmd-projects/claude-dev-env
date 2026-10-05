#!/usr/bin/env python3
"""Stop hook that ends each turn only after the session title shows its status.

A turn starts at the latest user prompt in the transcript, skipping tool
results and meta entries. The turn may end once a tool whose name ends in
__set_session_title ran in it without error. Otherwise the hook blocks the
stop once and tells the model to set '<emoji> <name>'.

The hook stays silent when:

- the stop is already a retry after a block (stop_hook_active is true);
- the session shows no title tool: no title tool named anywhere in the
  transcript, and either no remote session id in the environment or a
  deferred tool listing that leaves the title tool out, or an earlier
  Stop block the session never met;
- the transcript cannot be read.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)

from hooks_constants.hook_block_logger import log_hook_block
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
from hooks_constants.session_title_constants import (
    ALLOW_EXIT_CODE,
    BLOCK_DECISION,
    DEFERRED_TOOL_ATTACHMENT_TYPES,
    HOOK_BLOCKING_ERROR_ATTACHMENT_TYPE,
    REMOTE_SESSION_ENVIRONMENT_VARIABLE,
    REMOTE_TITLE_TOOL_NAME,
    STOP_BLOCK_REASON,
    STOP_GATE_EVENT_NAME,
    STOP_HOOK_ACTIVE_KEY,
    TITLE_TOOL_NAME_PATTERN,
    TRANSCRIPT_PATH_KEY,
    UNKNOWN_TITLE_TOOL_NAME,
)
from hooks_constants.setup_project_paths_constants import DECODE_ERRORS_POLICY, UTF8_ENCODING


def _content_blocks(all_entry_fields: dict[str, object]) -> list[dict[str, object]]:
    message = all_entry_fields.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        return []
    return [each_block for each_block in content if isinstance(each_block, dict)]


def _is_user_prompt(all_entry_fields: dict[str, object]) -> bool:
    if all_entry_fields.get("type") != "user" or all_entry_fields.get("isMeta") is True:
        return False
    message = all_entry_fields.get("message")
    if isinstance(message, dict) and isinstance(message.get("content"), str):
        return True
    return any(each_block.get("type") == "text" for each_block in _content_blocks(all_entry_fields))


def _title_tool_names_in(all_entry_fields: dict[str, object]) -> list[str]:
    all_names: list[str] = []
    if all_entry_fields.get("type") == "assistant":
        all_names = [
            str(each_block.get("name"))
            for each_block in _content_blocks(all_entry_fields)
            if each_block.get("type") == "tool_use"
        ]
    attachment = all_entry_fields.get("attachment")
    if isinstance(attachment, dict) and attachment.get("type") in DEFERRED_TOOL_ATTACHMENT_TYPES:
        all_names += [str(each_name) for each_name in attachment.get("addedNames") or []]
        all_names += [
            str(each_record.get("name"))
            for each_record in attachment.get("entries") or []
            if isinstance(each_record, dict)
        ]
    return [each_name for each_name in all_names if TITLE_TOOL_NAME_PATTERN.match(each_name)]


def _lists_deferred_tools(all_entry_fields: dict[str, object]) -> bool:
    attachment = all_entry_fields.get("attachment")
    return isinstance(attachment, dict) and attachment.get("type") in DEFERRED_TOOL_ATTACHMENT_TYPES


def _is_stop_block(all_entry_fields: dict[str, object]) -> bool:
    attachment = all_entry_fields.get("attachment")
    return (
        isinstance(attachment, dict)
        and attachment.get("type") == HOOK_BLOCKING_ERROR_ATTACHMENT_TYPE
        and attachment.get("hookEvent") == STOP_GATE_EVENT_NAME
    )


def _is_title_call(entry_type: object, all_block_fields: dict[str, object]) -> bool:
    return (
        entry_type == "assistant"
        and all_block_fields.get("type") == "tool_use"
        and bool(TITLE_TOOL_NAME_PATTERN.match(str(all_block_fields.get("name"))))
    )


def _title_set_since(all_turn_entries: list[dict[str, object]]) -> bool:
    all_entry_blocks = [
        (each_entry.get("type"), each_block)
        for each_entry in all_turn_entries
        for each_block in _content_blocks(each_entry)
    ]
    all_title_call_ids = {
        str(each_block.get("id"))
        for each_entry_type, each_block in all_entry_blocks
        if _is_title_call(each_entry_type, each_block)
    }
    return any(
        each_block.get("type") == "tool_result"
        and str(each_block.get("tool_use_id")) in all_title_call_ids
        and not each_block.get("is_error")
        for _, each_block in all_entry_blocks
    )


def _turn_start_index(all_entries: list[dict[str, object]]) -> int:
    return max(
        (
            each_index
            for each_index, each_entry in enumerate(all_entries)
            if _is_user_prompt(each_entry)
        ),
        default=0,
    )


def stop_block_reason(all_entries: list[dict[str, object]], is_remote_session: bool) -> str | None:
    """Return the block reason when this turn has not set the title, else None.

    ::

        prompt -> set_session_title -> ok result   => None
        prompt -> work, no title call              => block reason
        no title tool anywhere, not remote         => None
        remote, tool list lacks the title tool     => None
        remote, earlier Stop block never met       => None

    Args:
        all_entries: The transcript entries, oldest first.
        is_remote_session: True when the session runs in a cloud session.

    Returns:
        The reason to send back to the model, or None to let the turn end.
    """
    all_seen_tool_names = [
        each_name for each_entry in all_entries for each_name in _title_tool_names_in(each_entry)
    ]
    if not all_seen_tool_names and (
        not is_remote_session
        or any(_lists_deferred_tools(each) or _is_stop_block(each) for each in all_entries)
    ):
        return None
    if _title_set_since(all_entries[_turn_start_index(all_entries) :]):
        return None
    if all_seen_tool_names:
        return STOP_BLOCK_REASON.format(tool_name=all_seen_tool_names[-1])
    tool_name = REMOTE_TITLE_TOOL_NAME if is_remote_session else UNKNOWN_TITLE_TOOL_NAME
    return STOP_BLOCK_REASON.format(tool_name=tool_name)


def _parsed_entry(line: str) -> dict[str, object] | None:
    try:
        parsed_entry = json.loads(line)
    except json.JSONDecodeError:
        return None
    return parsed_entry if isinstance(parsed_entry, dict) else None


def _read_entries(transcript_path: str) -> list[dict[str, object]]:
    with open(transcript_path, encoding=UTF8_ENCODING, errors=DECODE_ERRORS_POLICY) as transcript:
        all_lines = transcript.readlines()
    all_parsed_entries = [_parsed_entry(each_line) for each_line in all_lines]
    return [each_entry for each_entry in all_parsed_entries if each_entry is not None]


def main() -> int:
    hook_input = read_hook_input_dictionary_from_stdin()
    if hook_input is None or hook_input.get(STOP_HOOK_ACTIVE_KEY):
        return ALLOW_EXIT_CODE
    transcript_path = hook_input.get(TRANSCRIPT_PATH_KEY)
    if not isinstance(transcript_path, str) or not transcript_path:
        return ALLOW_EXIT_CODE
    try:
        all_entries = _read_entries(transcript_path)
    except OSError:
        return ALLOW_EXIT_CODE
    is_remote_session = bool(os.environ.get(REMOTE_SESSION_ENVIRONMENT_VARIABLE))
    block_reason = stop_block_reason(all_entries, is_remote_session)
    if block_reason is None:
        return ALLOW_EXIT_CODE
    log_hook_block(Path(__file__).name, STOP_GATE_EVENT_NAME, block_reason)
    sys.stdout.write(json.dumps({"decision": BLOCK_DECISION, "reason": block_reason}))
    return ALLOW_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())
