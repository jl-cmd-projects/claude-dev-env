#!/usr/bin/env python3
"""UserPromptSubmit hook: tell the user to restart when a plugin changed after start.

A running Claude Code session keeps the plugin files it loaded at start. After
an install or update, ``installed_plugins.json`` names a new ``version`` or
``installPath``, or a plugin the session never loaded, and its new skills and
commands stay unavailable until a restart. The hook compares the live record
with the baseline that ``plugin_session_baseline_writer.py`` wrote at
SessionStart and names each changed plugin once per session, in a
``systemMessage`` for the user and in ``additionalContext`` for the agent.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_hooks_directory = str(Path(__file__).resolve().parent.parent)
if _hooks_directory not in sys.path:
    sys.path.insert(0, _hooks_directory)

from hooks_constants.plugin_session_baseline_constants import (
    BASELINE_PLUGINS_KEY,
    BASELINE_WARNED_KEY,
    PLUGIN_CHANGE_WARNING_TEMPLATE,
    PLUGIN_ID_SEPARATOR,
    SESSION_ID_FIELD,
    USER_PROMPT_SUBMIT_EVENT_NAME,
)
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
from plugin_session_baseline import (
    all_changed_plugin_ids,
    current_plugin_snapshot,
    installed_plugins_path,
    read_baseline_record,
    write_baseline_record,
)


def plugin_change_output(all_plugin_ids: list[str]) -> dict[str, object]:
    """Return the hook output that names each changed plugin and asks for a restart.

    Args:
        all_plugin_ids: The plugin ids to name, in order.
    """
    warning_text = PLUGIN_CHANGE_WARNING_TEMPLATE.format(
        plugin_ids=PLUGIN_ID_SEPARATOR.join(all_plugin_ids)
    )
    return {
        "systemMessage": warning_text,
        "hookSpecificOutput": {
            "hookEventName": USER_PROMPT_SUBMIT_EVENT_NAME,
            "additionalContext": warning_text,
        },
    }


def main() -> None:
    """Warn once per plugin when the live plugin record differs from the session baseline."""
    hook_payload = read_hook_input_dictionary_from_stdin()
    if hook_payload is None:
        return
    session_id = hook_payload.get(SESSION_ID_FIELD)
    if not isinstance(session_id, str) or not session_id:
        return
    baseline_record = read_baseline_record(session_id)
    if baseline_record is None:
        return
    baseline_snapshot = baseline_record[BASELINE_PLUGINS_KEY]
    all_warned_plugin_ids = [
        str(each_plugin_id) for each_plugin_id in baseline_record[BASELINE_WARNED_KEY]
    ]
    all_new_plugin_ids = [
        each_plugin_id
        for each_plugin_id in all_changed_plugin_ids(
            baseline_snapshot, current_plugin_snapshot(installed_plugins_path())
        )
        if each_plugin_id not in all_warned_plugin_ids
    ]
    if not all_new_plugin_ids:
        return
    write_baseline_record(
        session_id, baseline_snapshot, [*all_warned_plugin_ids, *all_new_plugin_ids]
    )
    sys.stdout.write(json.dumps(plugin_change_output(all_new_plugin_ids)) + "\n")


if __name__ == "__main__":
    main()
