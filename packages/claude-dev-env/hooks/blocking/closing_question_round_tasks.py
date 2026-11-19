"""Read the session's own task list for the closing question round gate.

The gate reads the tasks to decide whether a working reply owes the In
progress footer and which tasks that footer must name::

    task #2 in_progress, task #3 pending, task #1 completed
        -> in progress: [#2]; open: [#2, #3]

The task list is the task store, ``<claude home>/tasks/<task list id>/*.json``,
with ``CLAUDE_CODE_TASK_LIST_ID`` or the payload's ``session_id`` as the id.
When no store exists, it is the transcript's TaskCreate, TaskUpdate,
TodoWrite, and plan calls, read only from a transcript of at most 64 MiB, so
the replay stays well inside the gate's deadline; a larger or unreadable
transcript reads as no tasks.

The user sees only the newest desktop plan list. A desktop plan item that a
later list left out while it was unfinished is carried, as
``open_tasks_transcript`` describes, and stays out of the in-progress and open
tasks::

    list 1: "Run the rerun" in_progress   list 2: "Fix the reader" in_progress
        -> in progress: ["Fix the reader"]; carried in progress: ["Run the rerun"]
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)
blocking_directory = str(Path(__file__).resolve().parent)
if blocking_directory not in sys.path:
    sys.path.insert(0, blocking_directory)

from open_tasks_stop_gate import task_store_items
from open_tasks_transcript import TaskItem, TranscriptReplay, replayed_transcript

from hooks_constants.closing_question_round_gate_constants import (
    CARRIED_TASKS_REASON_LINE_TEMPLATE,
    CARRIED_TASKS_INSTRUCTION,
    CARRIED_TASKS_LABEL,
    CARRIED_TASKS_REASON_LEAD,
    MAXIMUM_REPLAYED_TRANSCRIPT_BYTES,
    REASON_PART_SEPARATOR,
)
from hooks_constants.once_per_session_constants import SESSION_ID_KEY
from hooks_constants.open_tasks_stop_gate_constants import (
    INCOMPLETE_STATUSES,
    IN_PROGRESS_STATUS,
    TRANSCRIPT_PATH_KEY,
)


class SessionTasks(NamedTuple):
    """The session's tasks that still stand.

    Attributes:
        in_progress: The tasks the user sees with status ``in_progress``, in task list order.
        still_open: The tasks the user sees with status ``in_progress`` or ``pending``, in task list order.
        carried_in_progress: The desktop plan tasks with status ``in_progress`` that a later list
            left out, which the user's list does not show. Empty by default.
    """

    in_progress: tuple[TaskItem, ...]
    still_open: tuple[TaskItem, ...]
    carried_in_progress: tuple[TaskItem, ...] = ()


def _replay(transcript_path: object) -> TranscriptReplay | None:
    if not isinstance(transcript_path, str):
        return None
    try:
        transcript_size = Path(transcript_path).stat().st_size
    except (OSError, ValueError):
        return None
    if transcript_size > MAXIMUM_REPLAYED_TRANSCRIPT_BYTES:
        return None
    return replayed_transcript(transcript_path)


def session_tasks(all_hook_input_fields: dict[str, object]) -> SessionTasks:
    """Return the session's in-progress, open, and carried in-progress tasks.

    Args:
        all_hook_input_fields: The Stop payload, read for ``session_id`` and
            ``transcript_path``.

    Returns:
        The tasks from the task store, or from the transcript's task calls
        when no store exists and the transcript is at most 64 MiB. Only the
        transcript's desktop plan carries tasks.
    """
    all_shown_items = task_store_items(all_hook_input_fields.get(SESSION_ID_KEY))
    all_carried_items: list[TaskItem] = []
    if all_shown_items is None:
        replay = _replay(all_hook_input_fields.get(TRANSCRIPT_PATH_KEY))
        all_shown_items = (replay.shown_items() or []) if replay is not None else []
        all_carried_items = replay.carried_items() if replay is not None else []
    return SessionTasks(
        tuple(each_item for each_item in all_shown_items if each_item.status == IN_PROGRESS_STATUS),
        tuple(each_item for each_item in all_shown_items if each_item.status in INCOMPLETE_STATUSES),
        tuple(each_item for each_item in all_carried_items if each_item.status == IN_PROGRESS_STATUS),
    )


def carried_tasks_reason(all_carried_items: Sequence[TaskItem]) -> str:
    """Return the hold reason for in-progress work a later desktop plan list dropped.

    ::

        This session's task list dropped work that was still in progress, and the user's list does not show it.
        Dropped from the list while in progress:
        - Run the nightly export rerun
        The user sees only the newest list, ... put the item on the list once with status
        completed, then send the list again without it. ...

    Args:
        all_carried_items: The carried tasks with status ``in_progress``.

    Returns:
        The reason, one part per line.
    """
    return REASON_PART_SEPARATOR.join(
        [
            CARRIED_TASKS_REASON_LEAD,
            CARRIED_TASKS_LABEL,
            *(CARRIED_TASKS_REASON_LINE_TEMPLATE.format(subject=each_item.subject) for each_item in all_carried_items),
            CARRIED_TASKS_INSTRUCTION,
        ]
    )
