#!/usr/bin/env python3
"""Stop hook that holds a turn only when the session title shows a stale status.

The title's emoji tells the user whether a session needs them. The gate leaves
a title alone while it still fits, and holds the turn once when it does not::

    no title set yet                                   -> hold
    red flag, and this turn's prompt asks for work     -> hold: the user acted on it
    check mark, and the task list has open items       -> hold: work is open again
    hourglass, and every task list item is completed   -> hold: nothing runs
    anything else                                      -> pass

A turn that set a title passes, because the agent's choice stands. So does a
turn that called no tool other than the title tool, and a held turn
(``stop_hook_active``). The gate adds at most one step to a turn.

A turn starts after the latest user prompt in the transcript. Tool results,
meta entries, sidechain entries and compaction summaries are not prompts, and
a Stop hook block lands as an attachment, so a held turn stays the same turn.
A title call on a sidechain entry belongs to a subagent and does not count.
A title the format gate denied does not count either.

The task list comes from ``open_tasks_stop_gate.session_task_items``. Whether
a prompt asks for work comes from ``open_task_asks.is_ask``.

The session has the title tool when a transcript record names it::

    attachment.tools[].name / attachment.entries[].name   (tool listing)
    attachment.addedNames / attachment.readdedNames       (deferred tools)
    assistant tool_use name                               (an earlier call)

A later ``removedNames`` entry takes the name away again. With no such record,
or with an unreadable transcript, the hook lets the turn end, so Codex,
Cursor and sessions without the tool keep working.

A block writes ``{"decision": "block", "reason": ...}`` to stdout. The reason
names the shown title, why it does not fit, and the four status emoji.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)
blocking_directory = str(Path(__file__).resolve().parent)
if blocking_directory not in sys.path:
    sys.path.insert(0, blocking_directory)

from hooks_constants.hook_block_logger import log_hook_block
from open_task_asks import is_ask
from open_tasks_stop_gate import session_task_items
from open_tasks_transcript import TaskItem, replayed_transcript
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
from hooks_constants.session_title_constants import (
    ALL_ITEMS_COMPLETED_REASON,
    ALL_SKIPPED_PROMPT_FLAGS,
    ALL_TOOL_LISTING_NAME_KEYS,
    ALL_TOOL_LISTING_RECORD_KEYS,
    ALLOW_EXIT_CODE,
    ASSISTANT_ENTRY_TYPE,
    ATTACHMENT_KEY,
    BLOCK_DECISION,
    BLOCK_ID_KEY,
    BLOCK_INPUT_KEY,
    BLOCK_NAME_KEY,
    CHECK_MARK_STATUS,
    COMPLETED_TASK_STATUS,
    CONTENT_KEY,
    DECISION_KEY,
    DECODE_ERRORS_POLICY,
    ENTRY_TYPE_KEY,
    HOURGLASS_STATUS,
    IS_ERROR_KEY,
    MESSAGE_KEY,
    NO_TITLE_REASON,
    OPEN_ITEMS_REASON,
    REASON_KEY,
    RED_FLAG_STATUS,
    REMOVED_NAMES_KEY,
    SESSION_ID_KEY,
    SIDECHAIN_FLAG_KEY,
    STALE_FLAG_REASON,
    STATUS_PREFIX_PATTERN,
    STOP_HOOK_ACTIVE_KEY,
    TITLE_INPUT_KEY,
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


def _last_prompt_index(all_entries: list[dict[str, object]]) -> int:
    return max(
        (
            each_index
            for each_index, each_entry in enumerate(all_entries)
            if _is_user_prompt(each_entry)
        ),
        default=-1,
    )


def _main_chain(all_entries: list[dict[str, object]]) -> list[dict[str, object]]:
    return [each_entry for each_entry in all_entries if not each_entry.get(SIDECHAIN_FLAG_KEY)]


def _turn_entries(all_entries: list[dict[str, object]]) -> list[dict[str, object]]:
    return _main_chain(all_entries[_last_prompt_index(all_entries) + 1 :])


def _title_call_ids(all_turn_entries: list[dict[str, object]]) -> set[object]:
    return {
        each_block.get(BLOCK_ID_KEY)
        for each_entry in all_turn_entries
        for each_block in _tool_use_blocks(each_entry)
        if TITLE_TOOL_NAME_PATTERN.match(str(each_block.get(BLOCK_NAME_KEY)))
    }


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
    return _title_succeeded_in(_turn_entries(all_entries))


def turn_ran_a_tool(all_entries: list[dict[str, object]]) -> bool:
    """Return True when this turn called any tool other than the title tool.

    Args:
        all_entries: The transcript entries, oldest first.

    Returns:
        True when the turn did work beyond answering in text.
    """
    return any(
        not TITLE_TOOL_NAME_PATTERN.match(str(each_block.get(BLOCK_NAME_KEY)))
        for each_entry in _turn_entries(all_entries)
        for each_block in _tool_use_blocks(each_entry)
    )


def _successful_title_call_ids(all_scoped_entries: list[dict[str, object]]) -> set[object]:
    all_title_call_ids = _title_call_ids(all_scoped_entries)
    return {
        each_block.get(TOOL_USE_ID_KEY)
        for each_entry in all_scoped_entries
        if each_entry.get(ENTRY_TYPE_KEY) == USER_ENTRY_TYPE
        for each_block in _content_blocks(each_entry)
        if each_block.get(ENTRY_TYPE_KEY) == TOOL_RESULT_BLOCK_TYPE
        and each_block.get(TOOL_USE_ID_KEY) in all_title_call_ids
        and not each_block.get(IS_ERROR_KEY)
    }


def _title_succeeded_in(all_scoped_entries: list[dict[str, object]]) -> bool:
    return bool(_successful_title_call_ids(all_scoped_entries))


def _title_input(all_block_fields: dict[str, object]) -> str | None:
    all_input_fields = all_block_fields.get(BLOCK_INPUT_KEY)
    title = all_input_fields.get(TITLE_INPUT_KEY) if isinstance(all_input_fields, dict) else None
    return title if isinstance(title, str) else None


def shown_title(all_entries: list[dict[str, object]]) -> str | None:
    """Return the title of the last main-chain title call that came back without an error.

    ::

        "\u23f3 Export" ok, then "\u2705 Export" denied   -> "\u23f3 Export"
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


def stale_status_reason(title: str, is_ask_turn: bool, all_task_items: list[TaskItem]) -> str | None:
    """Return why the shown title does not fit the session's state, or None when it fits.

    ::

        red flag, the prompt asks for work          -> reason
        check mark, an item is pending              -> reason
        hourglass, every item completed             -> reason
        hourglass, an item is in progress           -> None

    Args:
        title: The title the session shows.
        is_ask_turn: True when the prompt that started this turn asks for work.
        all_task_items: The session's task list.

    Returns:
        The reason the status is stale, with the title filled in, or None.
    """
    status = title_status(title)
    has_items = bool(all_task_items)
    is_all_completed = has_items and all(
        each_item.status == COMPLETED_TASK_STATUS for each_item in all_task_items
    )
    if status == RED_FLAG_STATUS and is_ask_turn:
        return STALE_FLAG_REASON.format(title=title)
    if status == CHECK_MARK_STATUS and has_items and not is_all_completed:
        return OPEN_ITEMS_REASON.format(title=title)
    if status == HOURGLASS_STATUS and is_all_completed:
        return ALL_ITEMS_COMPLETED_REASON.format(title=title)
    return None


def turn_block_reason(
    all_entries: list[dict[str, object]],
    is_stop_hook_active: bool,
    is_ask_turn: bool,
    all_task_items: list[TaskItem],
) -> str | None:
    """Return the reason to hold the turn, or None when the turn may end.

    ::

        no title tool in the transcript                  -> None
        held turn (stop_hook_active)                     -> None
        title set this turn                              -> None
        no tool other than the title tool this turn      -> None
        no title set in the session yet                  -> reason
        shown title has a stale status                   -> reason
        shown title still fits                           -> None

    Args:
        all_entries: The transcript entries, oldest first.
        is_stop_hook_active: True when a Stop hook already held this turn.
        is_ask_turn: True when the prompt that started this turn asks for work.
        all_task_items: The session's task list.

    Returns:
        The block reason that names the title tool, or None.
    """
    all_title_tools = available_title_tools(all_entries)
    if not all_title_tools or is_stop_hook_active or title_set_this_turn(all_entries):
        return None
    if not turn_ran_a_tool(all_entries):
        return None
    title = shown_title(all_entries)
    stale_reason = NO_TITLE_REASON if title is None else stale_status_reason(title, is_ask_turn, all_task_items)
    if stale_reason is None:
        return None
    return TURN_BLOCK_REASON.format(
        why=stale_reason, tool_name=TITLE_TOOL_DISPLAY_SEPARATOR.join(all_title_tools)
    )


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
    transcript_path = hook_input.get(TRANSCRIPT_PATH_KEY)
    replay = replayed_transcript(transcript_path)
    block_reason = turn_block_reason(
        read_transcript_entries(transcript_path),
        hook_input.get(STOP_HOOK_ACTIVE_KEY) is True,
        is_ask(replay.turn_prompt_text),
        session_task_items(hook_input.get(SESSION_ID_KEY), replay),
    )
    if block_reason is None:
        return ALLOW_EXIT_CODE
    log_hook_block(Path(__file__).name, TURN_GATE_EVENT_NAME, block_reason)
    sys.stdout.write(json.dumps({DECISION_KEY: BLOCK_DECISION, REASON_KEY: block_reason}))
    return ALLOW_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())
