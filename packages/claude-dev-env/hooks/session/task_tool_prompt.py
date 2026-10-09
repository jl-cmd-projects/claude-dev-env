#!/usr/bin/env python3
"""SessionStart hook — direct the session to track work with its task tool.

At session start this hook emits an ``additionalContext`` directive asking
the session to track its work with the task or todo tracking tool its host
provides: create tasks at the start of the session, then update them as
work proceeds.
"""

from __future__ import annotations

import json
import sys

import _path_setup  # noqa: F401

from hooks_constants.mod_handoff import is_mod_plugin_enabled
from hooks_constants.mod_handoff_constants import SESSION_PROMPTS_PLUGIN_NAME
from hooks_constants.task_tool_prompt_constants import TASK_TOOL_DIRECTIVE


def build_session_directive() -> str:
    """Return the task-tool directive emitted at session start."""
    return TASK_TOOL_DIRECTIVE


def main() -> None:
    """Emit the task-tool directive as SessionStart additionalContext, unless the session-prompts mod is on."""
    if is_mod_plugin_enabled(SESSION_PROMPTS_PLUGIN_NAME):
        return
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": build_session_directive(),
        }
    }
    sys.stdout.write(json.dumps(payload) + "\n")


if __name__ == "__main__":
    main()
