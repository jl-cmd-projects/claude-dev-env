"""Turn a hook payload's session id into a safe part of a temp file name."""

from __future__ import annotations

from hooks_constants.session_edit_stage_gate_constants import (
    SESSION_ID_UNSAFE_CHARACTERS_PATTERN,
    STATE_FILE_DEFAULT_SESSION_ID,
)

__all__ = ["session_file_id"]


def session_file_id(session_id: object) -> str:
    """Return the session id with unsafe characters stripped, or the default id when none remain."""
    raw_session_id = session_id if isinstance(session_id, str) else ""
    sanitized_session_id = SESSION_ID_UNSAFE_CHARACTERS_PATTERN.sub("", raw_session_id)
    return sanitized_session_id or STATE_FILE_DEFAULT_SESSION_ID
