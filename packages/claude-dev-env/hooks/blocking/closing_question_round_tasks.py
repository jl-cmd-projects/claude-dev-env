"""Hold a closing declaration while the session's own task list holds work in progress.

The closing question round gate asks this module once the stretch holds no
open-item line::

    "Open items: none."  task #2 in_progress        -> the in-progress reason
    "Open items: none."  every task completed       -> None
    "Both tests pass."   task #2 in_progress        -> None, no declaration

The task list is the task store, ``<claude home>/tasks/<task list id>/*.json``,
with ``CLAUDE_CODE_TASK_LIST_ID`` or the payload's ``session_id`` as the id.
When no store exists, it is the transcript's TaskCreate, TaskUpdate,
TodoWrite, and plan calls. The reason names each ``in_progress`` task by
number and subject and tells the agent to report where each stands and keep
working on it.
"""

from __future__ import annotations

import sys
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)
blocking_directory = str(Path(__file__).resolve().parent)
if blocking_directory not in sys.path:
    sys.path.insert(0, blocking_directory)

from closing_question_round_open_items import declares_no_open_items
from open_tasks_stop_gate import task_store_items
from open_tasks_transcript import TaskItem, replayed_transcript

from hooks_constants.closing_question_round_gate_constants import (
    IN_PROGRESS_TASK_LINE_TEMPLATE,
    IN_PROGRESS_TASKS_INSTRUCTION,
    IN_PROGRESS_TASKS_LABEL,
    IN_PROGRESS_TASKS_REASON_LEAD,
    REASON_PART_SEPARATOR,
)
from hooks_constants.once_per_session_constants import SESSION_ID_KEY
from hooks_constants.open_tasks_stop_gate_constants import (
    IN_PROGRESS_STATUS,
    TRANSCRIPT_PATH_KEY,
)


def _in_progress_task_items(all_hook_input_fields: dict[str, object]) -> list[TaskItem]:
    all_store_items = task_store_items(all_hook_input_fields.get(SESSION_ID_KEY))
    if all_store_items is None:
        all_store_items = (
            replayed_transcript(all_hook_input_fields.get(TRANSCRIPT_PATH_KEY)).items() or []
        )
    return [each_item for each_item in all_store_items if each_item.status == IN_PROGRESS_STATUS]


def declared_tasks_reason(
    all_hook_input_fields: dict[str, object], all_texts: list[str], deadline_at: float
) -> str | None:
    """Return the in-progress reason when the newest text declares no open items beside work in progress.

    Args:
        all_hook_input_fields: The Stop payload, read for ``session_id`` and
            ``transcript_path``.
        all_texts: The stretch's texts, oldest first; the last is the closing reply.
        deadline_at: The monotonic time the declaration scan stops at.

    Returns:
        The reason that names each ``in_progress`` task, or None when the
        closing reply makes no declaration or no task is in progress.
    """
    if not all_texts or not declares_no_open_items(all_texts[-1], deadline_at):
        return None
    all_in_progress_items = _in_progress_task_items(all_hook_input_fields)
    if not all_in_progress_items:
        return None
    all_task_lines = [
        IN_PROGRESS_TASK_LINE_TEMPLATE.format(task_id=each_item.item_id, subject=each_item.subject)
        for each_item in all_in_progress_items
    ]
    return REASON_PART_SEPARATOR.join(
        [
            IN_PROGRESS_TASKS_REASON_LEAD,
            IN_PROGRESS_TASKS_LABEL,
            *all_task_lines,
            IN_PROGRESS_TASKS_INSTRUCTION,
        ]
    )
