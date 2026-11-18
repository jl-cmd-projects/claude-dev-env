"""Read the session's own task list for the closing question round gate.

The gate reads the tasks to decide whether a working reply owes the In
progress footer and which tasks that footer must name::

    task #2 in_progress, task #3 pending, task #1 completed
        -> in progress: [#2]; open: [#2, #3]

The task list is the task store, ``<claude home>/tasks/<task list id>/*.json``,
with ``CLAUDE_CODE_TASK_LIST_ID`` or the payload's ``session_id`` as the id.
When no store exists, it is the transcript's TaskCreate, TaskUpdate,
TodoWrite, and plan calls.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import NamedTuple

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)
blocking_directory = str(Path(__file__).resolve().parent)
if blocking_directory not in sys.path:
    sys.path.insert(0, blocking_directory)

from open_tasks_stop_gate import task_store_items
from open_tasks_transcript import TaskItem, replayed_transcript

from hooks_constants.once_per_session_constants import SESSION_ID_KEY
from hooks_constants.open_tasks_stop_gate_constants import (
    INCOMPLETE_STATUSES,
    IN_PROGRESS_STATUS,
    TRANSCRIPT_PATH_KEY,
)


class SessionTasks(NamedTuple):
    """The session's tasks that still stand.

    Attributes:
        in_progress: The tasks with status ``in_progress``, in task list order.
        still_open: The tasks with status ``in_progress`` or ``pending``, in task list order.
    """

    in_progress: tuple[TaskItem, ...]
    still_open: tuple[TaskItem, ...]


def session_tasks(all_hook_input_fields: dict[str, object]) -> SessionTasks:
    """Return the session's in-progress and open tasks.

    Args:
        all_hook_input_fields: The Stop payload, read for ``session_id`` and
            ``transcript_path``.

    Returns:
        The tasks from the task store, or from the transcript's task calls
        when no store exists.
    """
    all_store_items = task_store_items(all_hook_input_fields.get(SESSION_ID_KEY))
    if all_store_items is None:
        all_store_items = (
            replayed_transcript(all_hook_input_fields.get(TRANSCRIPT_PATH_KEY)).items() or []
        )
    return SessionTasks(
        tuple(each_item for each_item in all_store_items if each_item.status == IN_PROGRESS_STATUS),
        tuple(each_item for each_item in all_store_items if each_item.status in INCOMPLETE_STATUSES),
    )
