"""Turn-one marker for the first-task deepen hook.

The marker records that a session already deepened its first task, so later
prompts stay untouched. A host can run two copies of the hook for one prompt:
Cursor runs its own ``beforeSubmitPrompt`` entry and the ``UserPromptSubmit``
entry it imports from the Claude Code settings, side by side. Each copy claims
the marker by creating the file only when it does not exist yet, so exactly
one copy wins and injects.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from hooks_constants.deepen_first_prompt_constants import (
    DEEPEN_MARKER,
    DEEPEN_SESSION_MARKER_PREFIX,
    DEEPEN_TURN_MARKER_SUFFIX,
    SESSION_ID_FIELD_NAME,
    TRANSCRIPT_PATH_FIELD_NAME,
    UTF8_ENCODING,
)


def _all_turn_marker_paths(all_hook_fields: dict[str, object]) -> list[Path]:
    all_marker_paths: list[Path] = []
    transcript_path = all_hook_fields.get(TRANSCRIPT_PATH_FIELD_NAME)
    if isinstance(transcript_path, str) and transcript_path:
        all_marker_paths.append(Path(transcript_path + DEEPEN_TURN_MARKER_SUFFIX))
    session_id = all_hook_fields.get(SESSION_ID_FIELD_NAME)
    if isinstance(session_id, str) and session_id:
        all_marker_paths.append(Path(tempfile.gettempdir()) / f"{DEEPEN_SESSION_MARKER_PREFIX}{session_id}")
    return all_marker_paths


def turn_marker_path(all_hook_fields: dict[str, object]) -> Path | None:
    """Return the marker path for this session, or None when the payload names none.

    The transcript path wins when the payload has one. Cursor sends no transcript
    path before the first reply, so the session id names a file in the system
    temp folder instead.
    """
    all_marker_paths = _all_turn_marker_paths(all_hook_fields)
    return all_marker_paths[0] if all_marker_paths else None


def turn_marker_exists(all_hook_fields: dict[str, object]) -> bool:
    """Return True when this session already deepened a task.

    Both marker locations count. Cursor's first prompt claims the session marker
    because it has no transcript path yet, and a later prompt carries one.
    """
    return any(each_marker_path.is_file() for each_marker_path in _all_turn_marker_paths(all_hook_fields))


def claim_turn_marker(all_hook_fields: dict[str, object]) -> bool:
    """Create the marker, and return False when another copy created it first.

    A payload with no transcript path or session id, or a marker that cannot be
    written, returns True: the hook then deepens without a guard, as before.
    """
    marker_path = turn_marker_path(all_hook_fields)
    if marker_path is None:
        return True
    try:
        marker_descriptor = os.open(marker_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    except OSError:
        return True
    with os.fdopen(marker_descriptor, "w", encoding=UTF8_ENCODING) as marker_file:
        marker_file.write(DEEPEN_MARKER)
    return True
