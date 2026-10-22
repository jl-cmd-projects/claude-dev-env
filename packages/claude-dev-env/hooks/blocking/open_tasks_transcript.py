#!/usr/bin/env python3
"""Rebuild a session task list and what its current turn did from a transcript.

The open tasks Stop gate reads four transcript shapes, replayed in order::

    TaskCreate / TaskUpdate calls        (Claude Code)
    TodoWrite input.todos                (Claude Code and Cursor; ``merge`` updates by id)
    update_plan function_call arguments  (Codex rollout)
    mcp__ccd_turn__update_plan input     (Claude Code desktop plan)

A desktop plan call either lists items or moves the current list::

    {"items": [...], "scope": "continuation"}   -> new list, unfinished old items carried after it
    {"done": [2], "start": 3}                    -> 1-based positions in the tool's own items
    {"advance": true}                            -> complete the in_progress item, start the next pending

Only ``assistant`` records count for a desktop plan call, because Claude Code
also copies each call into ``api-request-blob`` records.

The replay also notes what the current turn did::

    turn_prompt_text         the text of the prompt that started the turn
    has_turn_tracker_write   a TaskCreate, TaskUpdate, TodoWrite, update_plan, or desktop plan call ran
    has_turn_work_tool       any other assistant tool call ran, except the title tool,
                             AskUserQuestion, a hearthbot decision card, ToolSearch,
                             TaskList, TaskGet, and the Codex request_user_input card

A turn starts at the last user prompt record. A tool result, a record flagged
``isMeta``, ``isSidechain`` or ``isCompactSummary``, and a ``Stop hook feedback``
message do not start a turn; these are the flags session_title_turn_gate.py
skips, and its tests model Stop hook feedback as an ``isMeta`` user record.
A Codex ``response_item`` user message starts a Codex turn.

The Cursor CLI can also reach TodoWrite through ``CallDynamicTool``, with the
TodoWrite input under ``arguments``; that call counts as the TodoWrite call.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)

from hooks_constants.open_tasks_stop_gate_constants import (
    ALL_SKIPPED_PROMPT_FLAGS,
    ASSISTANT_RECORD_TYPE,
    ALL_CODEX_TOOL_CALL_TYPES,
    ALL_NON_WORK_TOOL_NAMES,
    ALL_TRACKER_TOOL_NAMES,
    ASSISTANT_ROLE,
    CCD_PLAN_ADVANCE_KEY,
    CCD_PLAN_CONTENT_KEY,
    CCD_PLAN_DONE_KEY,
    CCD_PLAN_ITEM_ID_TEMPLATE,
    CCD_PLAN_ITEMS_KEY,
    CCD_PLAN_START_KEY,
    CCD_PLAN_TOOL_NAME,
    CODEX_ARGUMENTS_KEY,
    CODEX_FUNCTION_CALL_TYPE,
    CODEX_MESSAGE_TYPE,
    CODEX_PAYLOAD_KEY,
    CODEX_PLAN_KEY,
    CODEX_PLAN_TOOL_NAME,
    CODEX_RESPONSE_ITEM_TYPE,
    CODEX_STEP_KEY,
    COMPLETED_STATUS,
    CONTENT_KEY,
    CREATED_TASK_ID_GROUP_INDEX,
    DYNAMIC_TOOL_ARGUMENTS_KEY,
    DYNAMIC_TOOL_CALL_NAME,
    DYNAMIC_TOOL_NAME_KEY,
    FIRST_ITEM_NUMBER,
    INCOMPLETE_STATUSES,
    IN_PROGRESS_STATUS,
    MESSAGE_KEY,
    PENDING_STATUS,
    RECORD_TIMESTAMP_KEY,
    RECORD_TYPE_KEY,
    ROLE_KEY,
    STOP_HOOK_FEEDBACK_PREFIX,
    TASK_CREATED_PATTERN,
    TASK_CREATE_TOOL_NAME,
    TASK_ID_KEY,
    TASK_STATUS_KEY,
    TASK_SUBJECT_KEY,
    TASK_UPDATE_ID_KEY,
    SESSION_TITLE_TOOL_SUFFIX,
    TASK_UPDATE_TOOL_NAME,
    TEXT_KEY,
    TODOS_KEY,
    TODO_CONTENT_KEY,
    TODO_ID_KEY,
    TODO_MERGE_KEY,
    TODO_WRITE_TOOL_NAME,
    TOOL_INPUT_KEY,
    TOOL_NAME_KEY,
    TOOL_RESULT_BLOCK_TYPE,
    TOOL_USE_BLOCK_TYPE,
    TOOL_USE_ID_KEY,
    UTC_OFFSET_TEXT,
    UTC_SUFFIX,
    USER_RECORD_TYPE,
    USER_ROLE,
    UTF8_ENCODING,
    WORD_SEPARATOR,
)


class TaskItem(NamedTuple):
    """One task list item.

    Attributes:
        item_id: The task number or position, as text.
        subject: The item's wording.
        status: The item's status, such as ``pending`` or ``completed``.
        listed_at: For a desktop plan item, seconds since the epoch of the last list that held it.
        is_carried: True for a desktop plan item a replacing list left out.
    """

    item_id: str
    subject: str
    status: str
    listed_at: float | None = None
    is_carried: bool = False


def normalized_text(text: str) -> str:
    """Return the text lowercased with each run of whitespace collapsed to one space."""
    return WORD_SEPARATOR.join(text.lower().split())


def record_epoch(all_record_fields: dict[str, object]) -> float | None:
    """Return the record's ISO ``timestamp`` as seconds since the epoch, or None."""
    timestamp_value = all_record_fields.get(RECORD_TIMESTAMP_KEY)
    if not isinstance(timestamp_value, str):
        return None
    try:
        return datetime.fromisoformat(timestamp_value.replace(UTC_SUFFIX, UTC_OFFSET_TEXT)).timestamp()
    except ValueError:
        return None


def parsed_object(json_text: str) -> dict[str, object] | None:
    """Return the JSON object in the text, or None for anything else."""
    try:
        parsed_value = json.loads(json_text)
    except ValueError:
        return None
    return parsed_value if isinstance(parsed_value, dict) else None


def _transcript_records(transcript_path: object) -> list[dict[str, object]]:
    if not isinstance(transcript_path, str):
        return []
    try:
        all_lines = Path(transcript_path).read_text(encoding=UTF8_ENCODING).splitlines()
    except OSError:
        return []
    all_records = (parsed_object(each_line) for each_line in all_lines)
    return [each_record for each_record in all_records if each_record is not None]


def _content_blocks(all_record_fields: dict[str, object]) -> list[dict[str, object]]:
    message_body = all_record_fields.get(MESSAGE_KEY)
    content_value = message_body.get(CONTENT_KEY) if isinstance(message_body, dict) else None
    if not isinstance(content_value, list):
        return []
    return [each_block for each_block in content_value if isinstance(each_block, dict)]


def _result_text(all_block_fields: dict[str, object]) -> str:
    result_content = all_block_fields.get(CONTENT_KEY)
    if isinstance(result_content, str):
        return result_content
    if not isinstance(result_content, list):
        return ""
    return WORD_SEPARATOR.join(
        str(each_part.get(TEXT_KEY, "")) for each_part in result_content if isinstance(each_part, dict)
    )


def _text_of_blocks(all_blocks: list[dict[str, object]]) -> str:
    return WORD_SEPARATOR.join(
        str(each_block.get(TEXT_KEY, "")) for each_block in all_blocks if isinstance(each_block.get(TEXT_KEY), str)
    )


def claude_prompt_text(all_record_fields: dict[str, object]) -> str | None:
    """Return the prompt text of a record that starts a turn, or None for any other record."""
    message_body = all_record_fields.get(MESSAGE_KEY)
    message_role = message_body.get(ROLE_KEY) if isinstance(message_body, dict) else None
    if USER_RECORD_TYPE != all_record_fields.get(RECORD_TYPE_KEY) and USER_ROLE not in (all_record_fields.get(ROLE_KEY), message_role):
        return None
    if any(all_record_fields.get(each_flag) for each_flag in ALL_SKIPPED_PROMPT_FLAGS):
        return None
    content_value = message_body.get(CONTENT_KEY) if isinstance(message_body, dict) else None
    if isinstance(content_value, str):
        prompt_text = content_value
    else:
        all_blocks = _content_blocks(all_record_fields)
        if any(each_block.get(RECORD_TYPE_KEY) == TOOL_RESULT_BLOCK_TYPE for each_block in all_blocks):
            return None
        if any(each_block.get(RECORD_TYPE_KEY) != TEXT_KEY for each_block in all_blocks):
            return _text_of_blocks(all_blocks)
        prompt_text = _text_of_blocks(all_blocks)
    if not prompt_text.strip() or prompt_text.lstrip().startswith(STOP_HOOK_FEEDBACK_PREFIX):
        return None
    return prompt_text


def _codex_payload(all_record_fields: dict[str, object]) -> dict[str, object] | None:
    payload_body = all_record_fields.get(CODEX_PAYLOAD_KEY)
    if all_record_fields.get(RECORD_TYPE_KEY) != CODEX_RESPONSE_ITEM_TYPE or not isinstance(payload_body, dict):
        return None
    return payload_body


def codex_prompt_text(all_record_fields: dict[str, object]) -> str | None:
    """Return the text of a Codex user message record, or None for any other record."""
    payload_body = _codex_payload(all_record_fields)
    if payload_body is None or payload_body.get(RECORD_TYPE_KEY) != CODEX_MESSAGE_TYPE or payload_body.get(ROLE_KEY) != USER_ROLE:
        return None
    content_value = payload_body.get(CONTENT_KEY)
    if isinstance(content_value, str):
        return content_value
    all_blocks = [each_block for each_block in content_value if isinstance(each_block, dict)] if isinstance(content_value, list) else []
    return _text_of_blocks(all_blocks)


def is_codex_work_call(all_record_fields: dict[str, object]) -> bool:
    """Return True for a Codex tool call record other than ``update_plan`` or a question card call."""
    payload_body = _codex_payload(all_record_fields)
    if payload_body is None or payload_body.get(RECORD_TYPE_KEY) not in ALL_CODEX_TOOL_CALL_TYPES:
        return False
    tool_name = payload_body.get(TOOL_NAME_KEY)
    return tool_name != CODEX_PLAN_TOOL_NAME and is_work_tool_name(tool_name)


def is_work_tool_name(tool_name: object) -> bool:
    """Return True for a tool name other than a non-work tool or the session title tool."""
    return not (
        isinstance(tool_name, str)
        and (tool_name in ALL_NON_WORK_TOOL_NAMES or tool_name.endswith(SESSION_TITLE_TOOL_SUFFIX))
    )


def is_assistant_record(all_record_fields: dict[str, object]) -> bool:
    """Return True for a record the assistant wrote, by its type, its role, or its message role."""
    message_body = all_record_fields.get(MESSAGE_KEY)
    message_role = message_body.get(ROLE_KEY) if isinstance(message_body, dict) else None
    return ASSISTANT_ROLE in (all_record_fields.get(ROLE_KEY), all_record_fields.get(RECORD_TYPE_KEY), message_role)


def _numbered_items(all_entries: object, subject_key: str) -> list[TaskItem]:
    if not isinstance(all_entries, list):
        return []
    all_dictionaries = [each_entry for each_entry in all_entries if isinstance(each_entry, dict)]
    return [
        TaskItem(str(each_number), str(each_entry.get(subject_key, "")), str(each_entry.get(TASK_STATUS_KEY, "")))
        for each_number, each_entry in enumerate(all_dictionaries, start=FIRST_ITEM_NUMBER)
    ]


def _todo_items(all_todo_entries: object) -> list[TaskItem]:
    if not isinstance(all_todo_entries, list):
        return []
    all_dictionaries = [each_entry for each_entry in all_todo_entries if isinstance(each_entry, dict)]
    return [
        TaskItem(
            str(each_entry.get(TODO_ID_KEY, each_number)),
            str(each_entry.get(TODO_CONTENT_KEY, "")),
            str(each_entry.get(TASK_STATUS_KEY, "")),
        )
        for each_number, each_entry in enumerate(all_dictionaries, start=FIRST_ITEM_NUMBER)
    ]


def merged_todo_items(all_earlier_items: list[TaskItem], all_update_entries: object) -> list[TaskItem]:
    """Apply a ``merge`` TodoWrite call: update earlier items by id and append new ones."""
    item_by_id = {each_item.item_id: each_item for each_item in all_earlier_items}
    for each_update in _todo_items(all_update_entries):
        earlier_item = item_by_id.get(each_update.item_id)
        if earlier_item is None:
            item_by_id[each_update.item_id] = each_update
            continue
        item_by_id[each_update.item_id] = earlier_item._replace(
            subject=each_update.subject or earlier_item.subject,
            status=each_update.status or earlier_item.status,
        )
    return list(item_by_id.values())


def codex_plan_items(all_record_fields: dict[str, object]) -> list[TaskItem] | None:
    """Return the plan from a Codex rollout ``update_plan`` call record, or None for any other record."""
    payload_body = all_record_fields.get(CODEX_PAYLOAD_KEY)
    if all_record_fields.get(RECORD_TYPE_KEY) != CODEX_RESPONSE_ITEM_TYPE or not isinstance(payload_body, dict):
        return None
    if payload_body.get(RECORD_TYPE_KEY) != CODEX_FUNCTION_CALL_TYPE or payload_body.get(TOOL_NAME_KEY) != CODEX_PLAN_TOOL_NAME:
        return None
    all_plan_arguments = parsed_object(str(payload_body.get(CODEX_ARGUMENTS_KEY, "")))
    if all_plan_arguments is None:
        return None
    return _numbered_items(all_plan_arguments.get(CODEX_PLAN_KEY), CODEX_STEP_KEY)


def advanced_items(all_own_items: list[TaskItem]) -> list[TaskItem]:
    """Complete the in_progress item and start the next pending one after it, as ``advance`` does."""
    all_advanced_items = list(all_own_items)
    search_start = 0
    for each_position, each_item in enumerate(all_advanced_items):
        if each_item.status == IN_PROGRESS_STATUS:
            all_advanced_items[each_position] = each_item._replace(status=COMPLETED_STATUS)
            search_start = each_position + 1
            break
    for each_position in range(search_start, len(all_advanced_items)):
        if all_advanced_items[each_position].status == PENDING_STATUS:
            all_advanced_items[each_position] = all_advanced_items[each_position]._replace(status=IN_PROGRESS_STATUS)
            break
    return all_advanced_items


def unwrapped_tool_call(tool_name: str, all_input_fields: dict[str, object]) -> tuple[str, dict[str, object]]:
    """Return the inner tool name and arguments of a Cursor ``CallDynamicTool`` call, or the call itself.

    The Cursor CLI can reach TodoWrite through ``CallDynamicTool`` with
    ``{"toolName": "TodoWrite", "arguments": {"todos": [...], "merge": true}}``.
    """
    inner_name = all_input_fields.get(DYNAMIC_TOOL_NAME_KEY)
    all_inner_arguments = all_input_fields.get(DYNAMIC_TOOL_ARGUMENTS_KEY)
    if tool_name != DYNAMIC_TOOL_CALL_NAME or not isinstance(inner_name, str) or not isinstance(all_inner_arguments, dict):
        return tool_name, all_input_fields
    return inner_name, all_inner_arguments


class TranscriptReplay:
    """Fold transcript records into the newest task list they describe and what the current turn did."""

    def __init__(self) -> None:
        self.latest_items: list[TaskItem] | None = None
        self.created_by_id: dict[str, TaskItem] = {}
        self.subject_by_tool_use_id: dict[str, str] = {}
        self.plan_items: list[TaskItem] | None = None
        self.own_plan_count = 0
        self.turn_prompt_text = ""
        self.has_turn_tracker_write = False
        self.has_turn_work_tool = False

    def start_turn(self, prompt_text: str) -> None:
        self.turn_prompt_text = prompt_text
        self.has_turn_tracker_write = False
        self.has_turn_work_tool = False

    def apply_record(self, all_record_fields: dict[str, object]) -> None:
        prompt_text = codex_prompt_text(all_record_fields)
        if prompt_text is None:
            prompt_text = claude_prompt_text(all_record_fields)
        if prompt_text is not None:
            self.start_turn(prompt_text)
            return
        plan_items = codex_plan_items(all_record_fields)
        if plan_items is not None:
            self.latest_items = plan_items
            self.has_turn_tracker_write = True
            return
        if is_codex_work_call(all_record_fields):
            self.has_turn_work_tool = True
            return
        is_typed_assistant_record = all_record_fields.get(RECORD_TYPE_KEY) == ASSISTANT_RECORD_TYPE
        is_from_assistant = is_assistant_record(all_record_fields)
        for each_block in _content_blocks(all_record_fields):
            plan_input = each_block.get(TOOL_INPUT_KEY)
            if is_typed_assistant_record and each_block.get(TOOL_NAME_KEY) == CCD_PLAN_TOOL_NAME and isinstance(plan_input, dict):
                self.apply_desktop_plan(plan_input, record_epoch(all_record_fields))
                self.has_turn_tracker_write = True
            else:
                self.apply_block(each_block, is_from_assistant)

    def apply_desktop_plan(self, all_plan_fields: dict[str, object], listed_at: float | None) -> None:
        all_listed_entries = all_plan_fields.get(CCD_PLAN_ITEMS_KEY)
        if isinstance(all_listed_entries, list):
            self.replace_desktop_plan(all_listed_entries, listed_at)
            return
        all_own_items = (self.plan_items or [])[: self.own_plan_count]
        all_done_positions = all_plan_fields.get(CCD_PLAN_DONE_KEY)
        for each_position in all_done_positions if isinstance(all_done_positions, list) else []:
            if isinstance(each_position, int) and FIRST_ITEM_NUMBER <= each_position <= len(all_own_items):
                all_own_items[each_position - FIRST_ITEM_NUMBER] = all_own_items[each_position - FIRST_ITEM_NUMBER]._replace(status=COMPLETED_STATUS)
        start_position = all_plan_fields.get(CCD_PLAN_START_KEY)
        if isinstance(start_position, int) and FIRST_ITEM_NUMBER <= start_position <= len(all_own_items):
            all_own_items[start_position - FIRST_ITEM_NUMBER] = all_own_items[start_position - FIRST_ITEM_NUMBER]._replace(status=IN_PROGRESS_STATUS)
        if all_plan_fields.get(CCD_PLAN_ADVANCE_KEY) is True:
            all_own_items = advanced_items(all_own_items)
        self.plan_items = all_own_items + (self.plan_items or [])[self.own_plan_count :]

    def replace_desktop_plan(self, all_listed_entries: list[object], listed_at: float | None) -> None:
        all_own_items = [
            each_item._replace(item_id=CCD_PLAN_ITEM_ID_TEMPLATE.format(position=each_item.item_id), listed_at=listed_at)
            for each_item in _numbered_items(all_listed_entries, CCD_PLAN_CONTENT_KEY)
        ]
        all_listed_subjects = {normalized_text(each_item.subject) for each_item in all_own_items}
        all_carried_items = [
            each_item._replace(is_carried=True)
            for each_item in self.plan_items or []
            if each_item.status in INCOMPLETE_STATUSES and normalized_text(each_item.subject) not in all_listed_subjects
        ]
        self.plan_items = all_own_items + all_carried_items
        self.own_plan_count = len(all_own_items)

    def apply_block(self, all_block_fields: dict[str, object], is_from_assistant: bool) -> None:
        block_type = all_block_fields.get(RECORD_TYPE_KEY)
        tool_input = all_block_fields.get(TOOL_INPUT_KEY)
        if block_type == TOOL_USE_BLOCK_TYPE and isinstance(tool_input, dict):
            tool_name, all_tool_arguments = unwrapped_tool_call(str(all_block_fields.get(TOOL_NAME_KEY)), tool_input)
            self.apply_tool_use(tool_name, str(all_block_fields.get(TASK_ID_KEY)), all_tool_arguments)
            if is_from_assistant:
                self.note_turn_tool(tool_name)
        elif block_type == TOOL_RESULT_BLOCK_TYPE:
            self.apply_tool_result(all_block_fields)

    def note_turn_tool(self, tool_name: str) -> None:
        if tool_name in ALL_TRACKER_TOOL_NAMES:
            self.has_turn_tracker_write = True
        elif is_work_tool_name(tool_name):
            self.has_turn_work_tool = True

    def apply_tool_use(self, tool_name: str, tool_use_id: str, all_input_fields: dict[str, object]) -> None:
        if tool_name == TODO_WRITE_TOOL_NAME:
            all_todo_entries = all_input_fields.get(TODOS_KEY)
            is_merge = all_input_fields.get(TODO_MERGE_KEY) is True and self.latest_items is not None
            self.latest_items = (
                merged_todo_items(self.latest_items or [], all_todo_entries) if is_merge else _todo_items(all_todo_entries)
            )
            return
        if tool_name == TASK_CREATE_TOOL_NAME:
            self.subject_by_tool_use_id[tool_use_id] = str(all_input_fields.get(TASK_SUBJECT_KEY, ""))
            return
        if tool_name == TASK_UPDATE_TOOL_NAME:
            self.apply_task_update(all_input_fields)

    def apply_task_update(self, all_input_fields: dict[str, object]) -> None:
        task_id = str(all_input_fields.get(TASK_UPDATE_ID_KEY, ""))
        new_status = all_input_fields.get(TASK_STATUS_KEY)
        if task_id in self.created_by_id and new_status:
            self.created_by_id[task_id] = self.created_by_id[task_id]._replace(status=str(new_status))

    def apply_tool_result(self, all_block_fields: dict[str, object]) -> None:
        created_subject = self.subject_by_tool_use_id.pop(str(all_block_fields.get(TOOL_USE_ID_KEY)), None)
        created_match = re.search(TASK_CREATED_PATTERN, _result_text(all_block_fields))
        if created_subject is None or created_match is None:
            return
        created_id = created_match.group(CREATED_TASK_ID_GROUP_INDEX)
        self.created_by_id[created_id] = TaskItem(created_id, created_subject, PENDING_STATUS)

    def items(self) -> list[TaskItem] | None:
        all_sources = [
            list(self.created_by_id.values()) if self.created_by_id else None,
            self.latest_items,
            self.plan_items,
        ]
        all_present_sources = [each_source for each_source in all_sources if each_source is not None]
        if not all_present_sources:
            return None
        return [each_item for each_source in all_present_sources for each_item in each_source]


def replayed_transcript(transcript_path: object) -> TranscriptReplay:
    """Fold every transcript record into one replay of the task list and the current turn."""
    replay = TranscriptReplay()
    for each_record in _transcript_records(transcript_path):
        replay.apply_record(each_record)
    return replay
