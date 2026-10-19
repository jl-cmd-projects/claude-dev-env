#!/usr/bin/env python3
"""Stop hook that keeps a session working while its task list has unreported open items.

The session's task list comes from the first of these that exists::

    ~/.claude/tasks/<task list id>/*.json     (TaskCreate / TaskUpdate store)
    transcript TaskCreate / TaskUpdate calls   (replayed in order)
    transcript TodoWrite input.todos           (last call wins)
    transcript Codex update_plan arguments     (last call wins)

An item with status ``pending`` or ``in_progress`` is open. The turn may end
only when the closing reply names every open item on a report line::

    allow: Blocked: Rotate the deploy key - the owner must approve the org secret
    allow: - Open: #3 - waits on the release checks
    block: (reply never mentions "Rotate the deploy key")

A block sends the open items back as the reason, so the model keeps working or
reports them. Claude Code ends the turn after eight blocks in a row. Codex
turns the reason into a continuation prompt. A Cursor payload (it carries
``conversation_id``) also gets the reason as ``followup_message``, which
Cursor submits as the next user message; Cursor sends no closing reply, so
the gate reads the last assistant text from the transcript. A Cursor payload
whose ``status`` is ``aborted`` or ``error`` is allowed, because Cursor would
submit the follow-up after the user stopped the run. A TodoWrite call with
``merge`` set updates the earlier items by id, and a Cursor ``CallDynamicTool``
call that wraps TodoWrite counts as that TodoWrite call.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)
blocking_directory = str(Path(__file__).resolve().parent)
if blocking_directory not in sys.path:
    sys.path.insert(0, blocking_directory)

from hooks_constants.hook_block_logger import log_hook_block
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
from open_tasks_transcript import TaskItem, parsed_object, replayed_transcript
from hooks_constants.open_tasks_stop_gate_constants import (
    ALLOW_EXIT_CODE,
    BLOCK_DECISION,
    BLOCK_REASON_PREFIX,
    BLOCK_REASON_SUFFIX,
    CLAUDE_CONFIG_DIRECTORY_ENVIRONMENT_VARIABLE,
    CLAUDE_HOME_DIRECTORY_NAME,
    CURSOR_COMPLETED_STATUS,
    CURSOR_CONVERSATION_ID_KEY,
    CURSOR_FOLLOWUP_MESSAGE_KEY,
    CURSOR_STATUS_KEY,
    DECISION_KEY,
    HOOK_EVENT_NAME,
    INCOMPLETE_STATUSES,
    ITEM_LINE_TEMPLATE,
    LAST_ASSISTANT_MESSAGE_KEY,
    REASON_KEY,
    REPORT_LINE_PATTERN,
    REPORTED_TEXT_GROUP_INDEX,
    SESSION_ID_KEY,
    TASK_FILE_GLOB,
    TASK_ID_KEY,
    TASK_LIST_ID_ENVIRONMENT_VARIABLE,
    TASK_NUMBER_REFERENCE_TEMPLATE,
    TASK_STATUS_KEY,
    TASK_SUBJECT_KEY,
    TASKS_DIRECTORY_NAME,
    TRANSCRIPT_PATH_KEY,
    UTF8_ENCODING,
    WORD_BOUNDARY_PATTERN,
    WORD_SEPARATOR,
)


def _claude_home() -> Path:
    configured_directory = os.environ.get(CLAUDE_CONFIG_DIRECTORY_ENVIRONMENT_VARIABLE)
    if configured_directory:
        return Path(configured_directory)
    return Path.home() / CLAUDE_HOME_DIRECTORY_NAME


def _task_file_item(task_file: Path) -> TaskItem | None:
    try:
        task_text = task_file.read_text(encoding=UTF8_ENCODING)
    except OSError:
        return None
    all_task_fields = parsed_object(task_text)
    if all_task_fields is None:
        return None
    return TaskItem(
        str(all_task_fields.get(TASK_ID_KEY, task_file.stem)),
        str(all_task_fields.get(TASK_SUBJECT_KEY, "")),
        str(all_task_fields.get(TASK_STATUS_KEY, "")),
    )


def task_store_items(session_id: object) -> list[TaskItem] | None:
    """Return the task store items for the session, or None when no store exists."""
    task_list_id = os.environ.get(TASK_LIST_ID_ENVIRONMENT_VARIABLE) or session_id
    if not isinstance(task_list_id, str) or not task_list_id:
        return None
    task_directory = _claude_home() / TASKS_DIRECTORY_NAME / task_list_id
    if not task_directory.is_dir():
        return None
    all_items = (_task_file_item(each_file) for each_file in sorted(task_directory.glob(TASK_FILE_GLOB)))
    return [each_item for each_item in all_items if each_item is not None]


def _normalized(text: str) -> str:
    return WORD_SEPARATOR.join(text.lower().split())


def _reported_texts(reply_text: str) -> list[str]:
    all_matches = (re.match(REPORT_LINE_PATTERN, each_line, re.IGNORECASE) for each_line in reply_text.splitlines())
    return [_normalized(each_match.group(REPORTED_TEXT_GROUP_INDEX)) for each_match in all_matches if each_match]


def is_reported(task_item: TaskItem, reply_text: str) -> bool:
    """Return True when a Blocked: or Open: line of the reply names the item."""
    subject_text = _normalized(task_item.subject)
    number_pattern = re.escape(TASK_NUMBER_REFERENCE_TEMPLATE.format(task_id=task_item.item_id)) + WORD_BOUNDARY_PATTERN
    return any(
        (subject_text and subject_text in each_text) or re.search(number_pattern, each_text)
        for each_text in _reported_texts(reply_text)
    )


def unreported_open_items(all_hook_input_fields: dict[str, object]) -> list[TaskItem]:
    """Return the open task items the closing reply does not report."""
    replay = replayed_transcript(all_hook_input_fields.get(TRANSCRIPT_PATH_KEY))
    all_items = task_store_items(all_hook_input_fields.get(SESSION_ID_KEY))
    if all_items is None:
        all_items = replay.items() or []
    reply_value = all_hook_input_fields.get(LAST_ASSISTANT_MESSAGE_KEY)
    reply_text = reply_value if isinstance(reply_value, str) else replay.last_assistant_text
    return [
        each_item
        for each_item in all_items
        if each_item.status in INCOMPLETE_STATUSES and not is_reported(each_item, reply_text)
    ]


def block_reason_for(all_open_items: list[TaskItem]) -> str:
    """Return the block reason that lists each open item."""
    all_item_lines = (
        ITEM_LINE_TEMPLATE.format(subject=each_item.subject or TASK_NUMBER_REFERENCE_TEMPLATE.format(task_id=each_item.item_id))
        for each_item in all_open_items
    )
    return BLOCK_REASON_PREFIX + "".join(all_item_lines) + BLOCK_REASON_SUFFIX


def block_output_for(all_hook_input_fields: dict[str, object], block_reason: str) -> dict[str, str]:
    """Return the block output; a Cursor payload also gets the reason as ``followup_message``."""
    block_output = {DECISION_KEY: BLOCK_DECISION, REASON_KEY: block_reason}
    if all_hook_input_fields.get(CURSOR_CONVERSATION_ID_KEY):
        block_output[CURSOR_FOLLOWUP_MESSAGE_KEY] = block_reason
    return block_output


def is_unfinished_cursor_stop(all_hook_input_fields: dict[str, object]) -> bool:
    """Return True for a Cursor stop whose run was aborted or ended in an error."""
    if not all_hook_input_fields.get(CURSOR_CONVERSATION_ID_KEY):
        return False
    stop_status = all_hook_input_fields.get(CURSOR_STATUS_KEY)
    return stop_status is not None and stop_status != CURSOR_COMPLETED_STATUS


def main() -> int:
    hook_input = read_hook_input_dictionary_from_stdin()
    if hook_input is None or is_unfinished_cursor_stop(hook_input):
        return ALLOW_EXIT_CODE
    all_open_items = unreported_open_items(hook_input)
    if not all_open_items:
        return ALLOW_EXIT_CODE
    block_reason = block_reason_for(all_open_items)
    reply_value = hook_input.get(LAST_ASSISTANT_MESSAGE_KEY)
    log_hook_block(
        Path(__file__).name,
        HOOK_EVENT_NAME,
        block_reason,
        offending_input_preview=reply_value if isinstance(reply_value, str) else None,
    )
    sys.stdout.write(json.dumps(block_output_for(hook_input, block_reason)))
    return ALLOW_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())
