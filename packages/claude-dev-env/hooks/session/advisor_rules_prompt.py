#!/usr/bin/env python3
"""SessionStart hook: inject open advisor consult guidance when the advisor is on.

The built-in advisor tool brings its own guidance on when to call it. This hook
adds the team-advisor starting points, such as a consult on a design question,
and leaves each call to the session's judgment. It emits them only when the user settings carry an
``advisorModel`` value and ``CLAUDE_CODE_DISABLE_ADVISOR_TOOL`` is not set, so a
session without the advisor is never told to call it.
The hook writes nothing and runs no tools itself.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_hooks_directory = str(Path(__file__).resolve().parent.parent)
if _hooks_directory not in sys.path:
    sys.path.insert(0, _hooks_directory)

from hooks_constants.advisor_rules_prompt_constants import (
    ADVISOR_DISABLE_ENV_VAR,
    ADVISOR_MODEL_SETTINGS_KEY,
    ADVISOR_RULES_PROMPT,
    ALL_ADVISOR_DISABLE_ENV_TRUE_VALUES,
    CLAUDE_CONFIG_DIR_ENV_VAR,
    DEFAULT_CLAUDE_CONFIG_DIRECTORY_NAME,
    USER_SETTINGS_FILE_NAME,
)


def user_settings_path() -> Path:
    """Return the user settings file under the active Claude config directory."""
    configured_directory = os.environ.get(CLAUDE_CONFIG_DIR_ENV_VAR, "").strip()
    if configured_directory:
        return Path(configured_directory) / USER_SETTINGS_FILE_NAME
    return Path.home() / DEFAULT_CLAUDE_CONFIG_DIRECTORY_NAME / USER_SETTINGS_FILE_NAME


def is_advisor_disabled_by_environment() -> bool:
    """Return True when the environment turns the advisor tool off."""
    raw_value = os.environ.get(ADVISOR_DISABLE_ENV_VAR, "").strip().lower()
    return raw_value in ALL_ADVISOR_DISABLE_ENV_TRUE_VALUES


def is_advisor_configured(settings_path: Path) -> bool:
    """Return True when the settings file names a non-empty advisor model."""
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(settings, dict):
        return False
    advisor_model = settings.get(ADVISOR_MODEL_SETTINGS_KEY)
    return isinstance(advisor_model, str) and advisor_model.strip() != ""


def main() -> None:
    """Emit the advisor guidance as SessionStart additionalContext when the advisor is on."""
    if is_advisor_disabled_by_environment():
        return
    if not is_advisor_configured(user_settings_path()):
        return
    session_start_output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": ADVISOR_RULES_PROMPT,
        }
    }
    sys.stdout.write(json.dumps(session_start_output) + "\n")


if __name__ == "__main__":
    main()
