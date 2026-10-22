#!/usr/bin/env python3
"""Stop hook that keeps the task list in step with the work an ask started.

The user follows a session's work in its task list. A turn that works on an ask
leaves a trace there: at least one tracker call after the prompt::

    TaskCreate / TaskUpdate        (Claude Code)
    TodoWrite                      (Claude Code and Cursor)
    update_plan                    (Codex)
    mcp__ccd_turn__update_plan     (Claude Code desktop plan)

The gate holds the turn once when all three hold::

    the prompt that started the turn asks for work   (open_task_asks.is_ask)
    the turn ran a work tool: any tool but a tracker call, the title tool,
        AskUserQuestion, ToolSearch, TaskList, TaskGet, or Codex request_user_input
    the turn made no tracker call

    block: "Export the APKs" -> Bash, Edit -> stop
    allow: "Export the APKs" -> TaskCreate, Bash, Edit -> stop
    allow: "did the export fail?" -> Bash -> stop
    allow: "Export the APKs" -> reply only -> stop
    allow: "Export the APKs" -> AskUserQuestion -> stop

The reply text is never checked. One tracker call releases the turn, and a
turn the gate already held ends on the next stop, so the gate costs at most one
extra step per turn.

Claude Code marks a held stop with ``stop_hook_active``. Codex turns the reason
into a continuation prompt. A Cursor payload (it carries ``conversation_id``)
gets the reason as ``followup_message``, which Cursor submits as the next user
message; a Cursor stop whose ``loop_count`` shows a follow-up already sent
passes, and so does one whose ``status`` is ``aborted`` or ``error``. A TodoWrite
call that a Cursor ``CallDynamicTool`` call wraps counts as a TodoWrite call.
"""

from __future__ import annotations

import json
import os
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
from open_task_asks import claude_home, is_ask
from open_tasks_transcript import TaskItem, TranscriptReplay, normalized_text, parsed_object, replayed_transcript
from hooks_constants.open_tasks_stop_gate_constants import (
    ALLOW_EXIT_CODE,
    BLOCK_DECISION,
    BLOCK_REASON,
    CURSOR_COMPLETED_STATUS,
    CURSOR_CONVERSATION_ID_KEY,
    CURSOR_FOLLOWUP_MESSAGE_KEY,
    CURSOR_LOOP_COUNT_KEY,
    CURSOR_STATUS_KEY,
    DECISION_KEY,
    HOOK_EVENT_NAME,
    REASON_KEY,
    STOP_HOOK_ACTIVE_KEY,
    TASK_FILE_GLOB,
    TASK_ID_KEY,
    TASK_LIST_ID_ENVIRONMENT_VARIABLE,
    TASK_NUMBER_REFERENCE_TEMPLATE,
    TASK_STATUS_KEY,
    TASK_SUBJECT_KEY,
    TASKS_DIRECTORY_NAME,
    TRANSCRIPT_PATH_KEY,
    UTF8_ENCODING,
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


def _subject_key(task_item: TaskItem) -> str:
    return normalized_text(task_item.subject) or TASK_NUMBER_REFERENCE_TEMPLATE.format(task_id=task_item.item_id)


def deduplicated_by_subject(all_sources: list[list[TaskItem]]) -> list[TaskItem]:
    """Drop an item whose subject an earlier source holds, so the task store wins over the transcript.

    The caller passes the task store and the whole transcript as two sources. Items inside one source all
    stay, so a pending task keeps its place beside a completed task of the same subject.
    """
    all_kept_items: list[TaskItem] = []
    all_earlier_keys: set[str] = set()
    for each_source in all_sources:
        all_kept_items.extend(each_item for each_item in each_source if _subject_key(each_item) not in all_earlier_keys)
        all_earlier_keys.update(_subject_key(each_item) for each_item in each_source)
    return all_kept_items


def session_task_items(session_id: object, replay: TranscriptReplay) -> list[TaskItem]:
    """Return the session's task list: the task store first, then transcript items it does not hold."""
    return deduplicated_by_subject([task_store_items(session_id) or [], replay.items() or []])


def is_untracked_work_turn(replay: TranscriptReplay) -> bool:
    """Return True when the turn worked on an ask and made no tracker call."""
    return replay.has_turn_work_tool and not replay.has_turn_tracker_write and is_ask(replay.turn_prompt_text)


def is_held_stop(all_hook_input_fields: dict[str, object]) -> bool:
    """Return True when a stop hook already held this turn once, or the Cursor run did not complete."""
    if all_hook_input_fields.get(STOP_HOOK_ACTIVE_KEY) is True:
        return True
    if not all_hook_input_fields.get(CURSOR_CONVERSATION_ID_KEY):
        return False
    stop_status = all_hook_input_fields.get(CURSOR_STATUS_KEY)
    loop_count = all_hook_input_fields.get(CURSOR_LOOP_COUNT_KEY)
    has_sent_followup = isinstance(loop_count, int) and loop_count > 0
    return has_sent_followup or (stop_status is not None and stop_status != CURSOR_COMPLETED_STATUS)


def block_output_for(all_hook_input_fields: dict[str, object], block_reason: str) -> dict[str, str]:
    """Return the block output; a Cursor payload also gets the reason as ``followup_message``."""
    block_output = {DECISION_KEY: BLOCK_DECISION, REASON_KEY: block_reason}
    if all_hook_input_fields.get(CURSOR_CONVERSATION_ID_KEY):
        block_output[CURSOR_FOLLOWUP_MESSAGE_KEY] = block_reason
    return block_output


def main() -> int:
    hook_input = read_hook_input_dictionary_from_stdin()
    if hook_input is None or is_held_stop(hook_input):
        return ALLOW_EXIT_CODE
    if not is_untracked_work_turn(replayed_transcript(hook_input.get(TRANSCRIPT_PATH_KEY))):
        return ALLOW_EXIT_CODE
    log_hook_block(Path(__file__).name, HOOK_EVENT_NAME, BLOCK_REASON)
    sys.stdout.write(json.dumps(block_output_for(hook_input, BLOCK_REASON)))
    return ALLOW_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())
