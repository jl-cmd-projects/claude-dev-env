#!/usr/bin/env python3
"""SessionStart hook — clean the Claude Code session-env directory on Windows.

Claude Code's Bash tool sets up a per-session sandbox at
``~/.claude/session-env/<session_id>/``. The mkdir call appears non-recursive,
so once the directory exists, later Bash invocations in the same session can
throw ``EEXIST`` and abort. PowerShell tool calls are unaffected.

This hook removes the current session's pre-existing directory at start and
prunes sibling entries whose mtime is older than the stale-age threshold so
the parent directory does not grow without bound.

Tracking: https://github.com/anthropics/claude-code/issues — Windows-only
mkdir bug separate from the EEXIST fixes in v2.1.70-v2.1.72.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

_hooks_dir = str(Path(__file__).resolve().parent.parent)
if _hooks_dir not in sys.path:
    sys.path.insert(0, _hooks_dir)

from hooks_constants.session_env_cleanup_constants import (
    SESSION_ENV_DIRECTORY,
    SESSION_ID_PATTERN,
    SESSION_ID_PAYLOAD_KEY,
    STALE_AGE_SECONDS,
    WINDOWS_PLATFORM_TAG,
)
from hooks_constants.windows_filesystem import force_rmtree


def prune_session_env(
    session_env_directory: str,
    session_id: str,
    stale_age_seconds: float,
) -> None:
    """Remove the current session's directory and prune stale siblings."""
    if session_id:
        current_session_path = os.path.join(session_env_directory, session_id)
        if os.path.isdir(current_session_path):
            force_rmtree(current_session_path)
    if not os.path.isdir(session_env_directory):
        return
    stale_cutoff_seconds = time.time() - stale_age_seconds
    try:
        all_entry_names = os.listdir(session_env_directory)
    except OSError:
        return
    for each_entry_name in all_entry_names:
        entry_path = os.path.join(session_env_directory, each_entry_name)
        try:
            entry_mtime_seconds = os.path.getmtime(entry_path)
        except OSError:
            continue
        if entry_mtime_seconds >= stale_cutoff_seconds:
            continue
        force_rmtree(entry_path)


def _read_session_id_from_stdin() -> str:
    session_id_pattern = SESSION_ID_PATTERN
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return ""
    if not isinstance(payload, dict):
        return ""
    raw_session_id = payload.get(SESSION_ID_PAYLOAD_KEY)
    if not isinstance(raw_session_id, str):
        return ""
    if not session_id_pattern.fullmatch(raw_session_id):
        return ""
    return raw_session_id


def main() -> None:
    windows_platform_tag = WINDOWS_PLATFORM_TAG
    if sys.platform != windows_platform_tag:
        return
    session_env_directory = SESSION_ENV_DIRECTORY
    stale_age_seconds = STALE_AGE_SECONDS
    session_id = _read_session_id_from_stdin()
    prune_session_env(
        session_env_directory=session_env_directory,
        session_id=session_id,
        stale_age_seconds=stale_age_seconds,
    )


if __name__ == "__main__":
    main()
