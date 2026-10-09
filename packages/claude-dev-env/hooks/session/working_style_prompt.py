#!/usr/bin/env python3
"""SessionStart hook — inject working-style guidance into the session.

At session start this hook emits an ``additionalContext`` line that points the
session at ``docs/references/working-style.md``, the guide for task records,
presentation, replies, scope, and questions.
The hook writes nothing and runs no tools itself.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_hooks_dir = str(Path(__file__).resolve().parent.parent)
if _hooks_dir not in sys.path:
    sys.path.insert(0, _hooks_dir)

from hooks_constants.mod_handoff import is_mod_plugin_enabled
from hooks_constants.mod_handoff_constants import SESSION_PROMPTS_PLUGIN_NAME
from hooks_constants.working_style_prompt_constants import (  # noqa: E402
    WORKING_STYLE_PROMPT,
)


def build_session_directive() -> str:
    """Return the working-style prompt emitted at session start."""
    return WORKING_STYLE_PROMPT


def main() -> None:
    """Emit the working-style prompt as SessionStart additionalContext, unless the session-prompts mod is on."""
    if is_mod_plugin_enabled(SESSION_PROMPTS_PLUGIN_NAME):
        return
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": build_session_directive(),
                }
            }
        )
    )


if __name__ == "__main__":
    main()
