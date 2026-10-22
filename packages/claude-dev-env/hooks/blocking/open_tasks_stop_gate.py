#!/usr/bin/env python3
"""Stop hook that keeps a session working while its task list has unreported open items.

The session's open items merge these sources, one item per subject::

    ~/.claude/tasks/<task list id>/*.json        (TaskCreate / TaskUpdate store)
    transcript TaskCreate / TaskUpdate calls      (replayed in order)
    transcript TodoWrite input.todos              (last call wins)
    transcript Codex update_plan arguments        (last call wins)
    transcript mcp__ccd_turn__update_plan calls   (unfinished items carry into a replacing list)
    ~/.claude/open-task-asks/<session id>.json    (each prompt that asks for work, as #ask-N)

An item with status ``pending`` or ``in_progress`` is open, and so is an ask
until a reply closes it. The turn may end only when the closing reply names
every open item on a report line::

    allow: Blocked: Rotate the deploy key - the owner must approve the org secret
    allow: - Open: #3 - waits on the release checks
    allow: Open: #ask-2 - the export job runs next
    block: (reply never mentions "Rotate the deploy key")

A report line releases only the current stop. Two lines in any assistant text
of the session close an item for good::

    Done: #ask-2                                    closes an ask; never a plan item
    Dropped: #ask-1 - "skip the APK export"         closes an ask
    Dropped: Submit both APKs - "skip the APK export"   closes a carried plan item

A ``Dropped:`` quote must appear in a prompt the user sent after that ask, or
after the last plan list that held the item.

A block sends the open items back as the reason, so the model keeps working or
reports them. Claude Code ends the turn after eight blocks in a row. Codex
turns the reason into a continuation prompt. A Cursor payload (it carries
``conversation_id``) also gets the reason as ``followup_message``, which
Cursor submits as the next user message; Cursor sends no closing reply, so
the gate reads the last assistant text from the transcript. A Cursor payload
whose ``status`` is ``aborted`` or ``error`` is allowed, because Cursor would
submit the follow-up after the user stopped the run, and so is one whose
``loop_count`` shows five follow-ups already sent. A TodoWrite call with
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
from open_task_asks import RecordedPrompt, claude_home, recorded_prompts
from open_tasks_transcript import TaskItem, normalized_text, parsed_object, replayed_transcript
from hooks_constants.open_tasks_stop_gate_constants import (
    ALLOW_EXIT_CODE,
    ASK_CLOSE_SUFFIX,
    ASK_ID_PREFIX,
    ASK_LINE_TEMPLATE,
    ASK_REFERENCE_PATTERN,
    ASK_SUBJECT_CHARACTER_LIMIT,
    ASK_SUBJECT_ELLIPSIS,
    BLOCK_DECISION,
    BLOCK_REASON_PREFIX,
    BLOCK_REASON_SUFFIX,
    CURSOR_COMPLETED_STATUS,
    CURSOR_CONVERSATION_ID_KEY,
    CURSOR_FOLLOWUP_LIMIT,
    CURSOR_FOLLOWUP_MESSAGE_KEY,
    CURSOR_LOOP_COUNT_KEY,
    CURSOR_STATUS_KEY,
    DECISION_KEY,
    DONE_LINE_PATTERN,
    DONE_TEXT_GROUP_INDEX,
    DROPPED_LINE_PATTERN,
    DROPPED_QUOTE_GROUP_INDEX,
    DROPPED_TARGET_GROUP_INDEX,
    HOOK_EVENT_NAME,
    INCOMPLETE_STATUSES,
    ITEM_LINE_TEMPLATE,
    LAST_ASSISTANT_MESSAGE_KEY,
    PENDING_STATUS,
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
)


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
    task_directory = claude_home() / TASKS_DIRECTORY_NAME / task_list_id
    if not task_directory.is_dir():
        return None
    all_items = (_task_file_item(each_file) for each_file in sorted(task_directory.glob(TASK_FILE_GLOB)))
    return [each_item for each_item in all_items if each_item is not None]


def _line_matches(line_pattern: str, all_texts: list[str]) -> list[re.Match[str]]:
    all_matches = (
        re.match(line_pattern, each_line, re.IGNORECASE) for each_text in all_texts for each_line in each_text.splitlines()
    )
    return [each_match for each_match in all_matches if each_match]


def _reported_texts(reply_text: str) -> list[str]:
    return [
        normalized_text(each_match.group(REPORTED_TEXT_GROUP_INDEX))
        for each_match in _line_matches(REPORT_LINE_PATTERN, [reply_text])
    ]


def is_reported(task_item: TaskItem, reply_text: str) -> bool:
    """Return True when a Blocked: or Open: line of the reply names the item."""
    subject_text = normalized_text(task_item.subject)
    number_pattern = re.escape(TASK_NUMBER_REFERENCE_TEMPLATE.format(task_id=task_item.item_id)) + WORD_BOUNDARY_PATTERN
    return any(
        (subject_text and subject_text in each_text) or re.search(number_pattern, each_text)
        for each_text in _reported_texts(reply_text)
    )


def _is_quoted_after(quote_text: str, all_later_prompts: list[RecordedPrompt]) -> bool:
    normalized_quote = normalized_text(quote_text)
    return bool(normalized_quote) and any(
        normalized_quote in normalized_text(each_prompt.text) for each_prompt in all_later_prompts
    )


def _ask_subject(prompt_text: str) -> str:
    first_line = prompt_text.strip().splitlines()[0]
    if len(first_line) <= ASK_SUBJECT_CHARACTER_LIMIT:
        return first_line
    return first_line[:ASK_SUBJECT_CHARACTER_LIMIT] + ASK_SUBJECT_ELLIPSIS


def open_ask_items(all_prompts: list[RecordedPrompt], all_closing_texts: list[str]) -> list[TaskItem]:
    """Return each recorded ask that no ``Done:`` line and no quoted ``Dropped:`` line closes."""
    all_done_ids = {
        each_reference
        for each_match in _line_matches(DONE_LINE_PATTERN, all_closing_texts)
        for each_reference in re.findall(ASK_REFERENCE_PATTERN, each_match.group(DONE_TEXT_GROUP_INDEX))
    }
    all_drop_matches = _line_matches(DROPPED_LINE_PATTERN, all_closing_texts)
    all_open_asks = []
    for each_position, each_prompt in enumerate(all_prompts):
        if not each_prompt.ask_id or each_prompt.ask_id in all_done_ids:
            continue
        is_dropped = any(
            each_prompt.ask_id in re.findall(ASK_REFERENCE_PATTERN, each_match.group(DROPPED_TARGET_GROUP_INDEX))
            and _is_quoted_after(each_match.group(DROPPED_QUOTE_GROUP_INDEX), all_prompts[each_position + 1 :])
            for each_match in all_drop_matches
        )
        if not is_dropped:
            all_open_asks.append(TaskItem(each_prompt.ask_id, _ask_subject(each_prompt.text), PENDING_STATUS))
    return all_open_asks


def is_dropped_carried_item(task_item: TaskItem, all_prompts: list[RecordedPrompt], all_closing_texts: list[str]) -> bool:
    """Return True when a ``Dropped:`` line names the carried item and quotes a prompt sent after its list."""
    listed_at = task_item.listed_at
    subject_text = normalized_text(task_item.subject)
    if not task_item.is_carried or listed_at is None or not subject_text:
        return False
    all_later_prompts = [each_prompt for each_prompt in all_prompts if each_prompt.recorded_at > listed_at]
    return any(
        subject_text in normalized_text(each_match.group(DROPPED_TARGET_GROUP_INDEX))
        and _is_quoted_after(each_match.group(DROPPED_QUOTE_GROUP_INDEX), all_later_prompts)
        for each_match in _line_matches(DROPPED_LINE_PATTERN, all_closing_texts)
    )


def deduplicated_by_subject(all_items: list[TaskItem]) -> list[TaskItem]:
    """Keep the first item for each subject, so the task store wins over the transcript and asks."""
    item_by_key: dict[str, TaskItem] = {}
    for each_item in all_items:
        item_key = normalized_text(each_item.subject) or TASK_NUMBER_REFERENCE_TEMPLATE.format(task_id=each_item.item_id)
        item_by_key.setdefault(item_key, each_item)
    return list(item_by_key.values())


def unreported_open_items(all_hook_input_fields: dict[str, object]) -> list[TaskItem]:
    """Return the open task items and asks the closing reply does not report."""
    replay = replayed_transcript(all_hook_input_fields.get(TRANSCRIPT_PATH_KEY))
    session_id = all_hook_input_fields.get(SESSION_ID_KEY)
    reply_value = all_hook_input_fields.get(LAST_ASSISTANT_MESSAGE_KEY)
    reply_text = reply_value if isinstance(reply_value, str) else replay.last_assistant_text
    all_closing_texts = [*replay.all_assistant_texts, reply_text]
    all_prompts = recorded_prompts(session_id)
    all_replayed_items = [
        each_item
        for each_item in replay.items() or []
        if not is_dropped_carried_item(each_item, all_prompts, all_closing_texts)
    ]
    all_items = deduplicated_by_subject(
        [*(task_store_items(session_id) or []), *all_replayed_items, *open_ask_items(all_prompts, all_closing_texts)]
    )
    return [
        each_item
        for each_item in all_items
        if each_item.status in INCOMPLETE_STATUSES and not is_reported(each_item, reply_text)
    ]


def _item_line(task_item: TaskItem) -> str:
    if task_item.item_id.startswith(ASK_ID_PREFIX):
        return ASK_LINE_TEMPLATE.format(ask_id=task_item.item_id, subject=task_item.subject)
    return ITEM_LINE_TEMPLATE.format(subject=task_item.subject or TASK_NUMBER_REFERENCE_TEMPLATE.format(task_id=task_item.item_id))


def block_reason_for(all_open_items: list[TaskItem]) -> str:
    """Return the block reason that lists each open item, and how to close an ask when one is open."""
    has_open_ask = any(each_item.item_id.startswith(ASK_ID_PREFIX) for each_item in all_open_items)
    all_item_lines = "".join(_item_line(each_item) for each_item in all_open_items)
    return BLOCK_REASON_PREFIX + all_item_lines + BLOCK_REASON_SUFFIX + (ASK_CLOSE_SUFFIX if has_open_ask else "")


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


def has_spent_cursor_followups(all_hook_input_fields: dict[str, object]) -> bool:
    """Return True for a Cursor stop that already sent the follow-up limit.

    Cursor caps native stop follow-ups at five per script, but a copy it imports
    from ``~/.claude/settings.json`` has no cap, so the gate stops at five itself.
    """
    if not all_hook_input_fields.get(CURSOR_CONVERSATION_ID_KEY):
        return False
    loop_count = all_hook_input_fields.get(CURSOR_LOOP_COUNT_KEY)
    return isinstance(loop_count, int) and loop_count >= CURSOR_FOLLOWUP_LIMIT


def main() -> int:
    hook_input = read_hook_input_dictionary_from_stdin()
    if hook_input is None or is_unfinished_cursor_stop(hook_input) or has_spent_cursor_followups(hook_input):
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
