"""Let a hook show its fixed text once per session and once more after each compaction.

A compaction drops the earlier text from the agent's context, so the count of
compactions in the transcript is part of the marker name. A new compaction
gives a new name, and the next event shows the text again::

    session s1, first event                         -> True, writes the s1, 0 compactions marker
    session s1, later event                         -> False
    session s1, event after a compaction            -> True, writes the s1, 1 compaction marker
    subagent a1 in session s1, first event          -> True, its own marker
    payload with no session id                      -> True on every event
    marker cannot be written                        -> True on every event

Claude Code marks a compaction with a ``compact_boundary`` system entry, and a
Codex rollout with a ``compacted`` entry.

``claim_only_showing`` leaves the compaction count out of the marker name, so
its text shows once in the whole session, compactions included.
``claim_turn_showing`` puts a turn key in the marker name and reports a marker
it cannot keep as None, so a caller can fall back to its own behavior.
``is_turn_claimed`` reads whether that turn marker exists and creates nothing.
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Mapping
from pathlib import Path

from hooks_constants.once_per_session_constants import (
    AGENT_ID_KEY,
    ALL_COMPACTION_ENTRY_FIELDS,
    ALL_COMPACTION_LINE_MARKERS,
    EXCLUSIVE_CREATE_MODE,
    ONCE_MARKER_FILE_PREFIX,
    ONCE_MARKER_FILE_SUFFIX,
    ONCE_MARKER_NAME_SEPARATOR,
    SESSION_ID_KEY,
    WHOLE_SESSION_MARKER_PART,
    TRANSCRIPT_PATH_KEY,
    TRANSCRIPT_READ_MODE,
)
from hooks_constants.session_file_id import session_file_id

__all__ = [
    "claim_first_showing",
    "claim_only_showing",
    "claim_turn_showing",
    "clear_showings",
    "compaction_count",
    "is_turn_claimed",
]


def _is_compaction_entry(transcript_line: bytes) -> bool:
    if not any(each_marker in transcript_line for each_marker in ALL_COMPACTION_LINE_MARKERS):
        return False
    try:
        all_entry_fields = json.loads(transcript_line)
    except ValueError:
        return False
    return isinstance(all_entry_fields, dict) and any(
        all_entry_fields.get(each_field) == each_value
        for each_field, each_value in ALL_COMPACTION_ENTRY_FIELDS
    )


def compaction_count(transcript_path: object) -> int:
    """Return the number of compactions the transcript records, or 0 when it cannot be read."""
    if not isinstance(transcript_path, str) or not transcript_path:
        return 0
    try:
        with Path(transcript_path).open(TRANSCRIPT_READ_MODE) as transcript:
            return sum(1 for each_line in transcript if _is_compaction_entry(each_line))
    except OSError:
        return 0


def _marker_path(
    hook_name: str, session_id: str, all_hook_fields: Mapping[str, object], showing_part: str
) -> Path:
    all_name_parts = [hook_name, session_file_id(session_id)]
    agent_id = all_hook_fields.get(AGENT_ID_KEY)
    if isinstance(agent_id, str) and agent_id:
        all_name_parts.append(session_file_id(agent_id))
    all_name_parts.append(showing_part)
    marker_name = ONCE_MARKER_NAME_SEPARATOR.join(all_name_parts)
    return (
        Path(tempfile.gettempdir())
        / f"{ONCE_MARKER_FILE_PREFIX}{marker_name}{ONCE_MARKER_FILE_SUFFIX}"
    )


def claim_first_showing(hook_name: str, all_hook_fields: Mapping[str, object]) -> bool:
    """Return True when the hook should show its fixed text now, and record that it did.

    Args:
        hook_name: A short name that keeps each hook's marker apart.
        all_hook_fields: The hook payload, read for its session id, agent id,
            and transcript path.
    """
    showing_part = str(compaction_count(all_hook_fields.get(TRANSCRIPT_PATH_KEY)))
    return _claim_marker(hook_name, all_hook_fields, showing_part)


def claim_only_showing(hook_name: str, all_hook_fields: Mapping[str, object]) -> bool:
    """Return True the first time in the whole session, compactions included, and record it.

    ::

        session s1, first event                 -> True
        session s1, event after a compaction    -> False
        payload with no session id              -> True on every event

    Args:
        hook_name: A short name that keeps each hook's marker apart.
        all_hook_fields: The hook payload, read for its session id and agent id.
    """
    return _claim_marker(hook_name, all_hook_fields, WHOLE_SESSION_MARKER_PART)


def claim_turn_showing(hook_name: str, all_hook_fields: Mapping[str, object], turn_key: str) -> bool | None:
    """Return True the first time for this turn and record it, False after that, or None when no marker can be kept.

    ::

        session s1, turn t1, first claim        -> True
        session s1, turn t1, later claim        -> False
        session s1, turn t2, first claim        -> True
        payload with no session id              -> None
        marker cannot be written                -> None

    Args:
        hook_name: A short name that keeps each hook's marker apart.
        all_hook_fields: The hook payload, read for its session id and agent id.
        turn_key: A key that names the turn, such as the id of the prompt that started it.
    """
    session_id = all_hook_fields.get(SESSION_ID_KEY)
    if not isinstance(session_id, str) or not session_id:
        return None
    try:
        with _marker_path(hook_name, session_id, all_hook_fields, session_file_id(turn_key)).open(
            EXCLUSIVE_CREATE_MODE
        ):
            return True
    except FileExistsError:
        return False
    except OSError:
        return None


def is_turn_claimed(hook_name: str, all_hook_fields: Mapping[str, object], turn_key: str) -> bool | None:
    """Return whether ``claim_turn_showing`` already claimed this turn, without claiming it.

    ::

        session s1, turn t1, before any claim   -> False
        session s1, turn t1, after a claim      -> True
        payload with no session id              -> None
        marker cannot be read                   -> None

    Args:
        hook_name: The name the hook passes to ``claim_turn_showing``.
        all_hook_fields: The hook payload, read for its session id and agent id.
        turn_key: The turn key the hook passes to ``claim_turn_showing``.
    """
    session_id = all_hook_fields.get(SESSION_ID_KEY)
    if not isinstance(session_id, str) or not session_id:
        return None
    try:
        return _marker_path(hook_name, session_id, all_hook_fields, session_file_id(turn_key)).is_file()
    except OSError:
        return None


def _claim_marker(hook_name: str, all_hook_fields: Mapping[str, object], showing_part: str) -> bool:
    session_id = all_hook_fields.get(SESSION_ID_KEY)
    if not isinstance(session_id, str) or not session_id:
        return True
    try:
        with _marker_path(hook_name, session_id, all_hook_fields, showing_part).open(
            EXCLUSIVE_CREATE_MODE
        ):
            return True
    except FileExistsError:
        return False
    except OSError:
        return True


def clear_showings(session_id: object) -> None:
    """Delete every hook's markers for the session, its subagents included, at session end."""
    if not isinstance(session_id, str) or not session_id:
        return
    session_pattern = ONCE_MARKER_NAME_SEPARATOR.join(["*", session_file_id(session_id), "*"])
    for each_marker in Path(tempfile.gettempdir()).glob(
        f"{ONCE_MARKER_FILE_PREFIX}{session_pattern}{ONCE_MARKER_FILE_SUFFIX}"
    ):
        each_marker.unlink(missing_ok=True)
