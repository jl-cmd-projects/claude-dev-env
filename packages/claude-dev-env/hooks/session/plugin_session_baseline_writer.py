#!/usr/bin/env python3
"""SessionStart hook: record the plugin versions this session loads at start.

On ``startup``, and on any source when the session has no baseline yet, the
hook writes each plugin's ``version`` and ``installPath`` from
``installed_plugins.json`` to the session's baseline file. On ``resume``,
``clear``, and ``compact`` it leaves an existing baseline alone, because the
session keeps the plugin files it loaded at its first start. The
UserPromptSubmit hook ``plugin_change_warning.py`` compares against this file.
The hook prints nothing.
"""

from __future__ import annotations

import sys
from pathlib import Path

_hooks_directory = str(Path(__file__).resolve().parent.parent)
if _hooks_directory not in sys.path:
    sys.path.insert(0, _hooks_directory)

from hooks_constants.plugin_session_baseline_constants import (
    SESSION_ID_FIELD,
    SESSION_SOURCE_FIELD,
    STARTUP_SOURCE,
)
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
from plugin_session_baseline import (
    current_plugin_snapshot,
    installed_plugins_path,
    read_baseline_record,
    write_baseline_record,
)


def main() -> None:
    """Write the session's plugin baseline on startup or when none exists yet."""
    hook_payload = read_hook_input_dictionary_from_stdin()
    if hook_payload is None:
        return
    session_id = hook_payload.get(SESSION_ID_FIELD)
    if not isinstance(session_id, str) or not session_id:
        return
    is_startup = hook_payload.get(SESSION_SOURCE_FIELD) == STARTUP_SOURCE
    if not is_startup and read_baseline_record(session_id) is not None:
        return
    write_baseline_record(
        session_id, current_plugin_snapshot(installed_plugins_path()), []
    )


if __name__ == "__main__":
    main()
