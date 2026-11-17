"""The per-session flag file that turns the closing question round Stop gate off.

The flag is a file in the temp folder named for the session id::

    session s1, no flag          -> is_bypass_on False
    toggle_bypass("s1")          -> True, flag written, gate off
    toggle_bypass("s1") again    -> False, flag removed, gate on
    session s2                   -> its own flag; s1's state stays

``session/closing_question_gate_bypass.py`` flips the flag on a prompt that
holds the keyword, and ``blocking/closing_question_round_gate.py`` allows every
stop of the session while the flag exists.
"""

from __future__ import annotations

import tempfile
from collections.abc import Mapping
from pathlib import Path

from hooks_constants.closing_question_round_gate_constants import (
    BYPASS_FLAG_CREATE_MODE,
    BYPASS_FLAG_FILE_PREFIX,
    BYPASS_FLAG_FILE_SUFFIX,
    SESSION_ID_KEY,
)
from hooks_constants.session_file_id import session_file_id

__all__ = ["bypass_flag_path", "is_bypass_on", "payload_session_id", "toggle_bypass"]


def bypass_flag_path(session_id: str) -> Path:
    """Return the path of the session's flag file in the temp folder."""
    return Path(tempfile.gettempdir()) / (
        f"{BYPASS_FLAG_FILE_PREFIX}{session_file_id(session_id)}{BYPASS_FLAG_FILE_SUFFIX}"
    )


def payload_session_id(all_hook_input_fields: Mapping[str, object]) -> str | None:
    """Return the payload's non-empty session id, or None."""
    session_id = all_hook_input_fields.get(SESSION_ID_KEY)
    return session_id if isinstance(session_id, str) and session_id else None


def is_bypass_on(all_hook_input_fields: Mapping[str, object]) -> bool:
    """Return True when the payload's session turned the closing question round gate off."""
    session_id = payload_session_id(all_hook_input_fields)
    if session_id is None:
        return False
    try:
        return bypass_flag_path(session_id).is_file()
    except OSError:
        return False


def toggle_bypass(session_id: str) -> bool | None:
    """Flip the session's flag and return True when the gate is now off, False when on, or None when the flag cannot change."""
    flag_path = bypass_flag_path(session_id)
    try:
        if flag_path.is_file():
            flag_path.unlink()
            return False
        with flag_path.open(BYPASS_FLAG_CREATE_MODE):
            return True
    except OSError:
        return None
