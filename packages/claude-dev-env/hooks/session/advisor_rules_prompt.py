#!/usr/bin/env python3
"""SessionStart hook: inject open advisor consult guidance when the advisor is on.

The built-in advisor tool brings its own guidance on when to call it. This hook
adds the team-advisor starting points, such as a consult on a design question,
and leaves each call to the session's judgment. It emits them only when the user settings carry an
``advisorModel`` value and ``CLAUDE_CODE_DISABLE_ADVISOR_TOOL`` is not set, so a
session without the advisor is never told to call it.
It also stays silent when the SessionStart payload's ``model`` is the
``advisorModel`` value or belongs to its model family, so a session is never
told to consult itself. When the payload has no ``model``, the guidance names the advisor model
so the session can tell for itself.
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
    ADVISOR_RULES_PROMPT_TEMPLATE,
    ALL_ADVISOR_DISABLE_ENV_TRUE_VALUES,
    ALL_MODEL_FAMILY_NAMES,
    CLAUDE_CONFIG_DIR_ENV_VAR,
    DEFAULT_CLAUDE_CONFIG_DIRECTORY_NAME,
    SESSION_MODEL_PAYLOAD_KEY,
    USER_SETTINGS_FILE_NAME,
)
from hooks_constants.mod_handoff import is_mod_plugin_enabled
from hooks_constants.mod_handoff_constants import SESSION_PROMPTS_PLUGIN_NAME
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin


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


def configured_advisor_model(settings_path: Path) -> str | None:
    """Return the settings file's non-empty advisor model, or None."""
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(settings, dict):
        return None
    advisor_model = settings.get(ADVISOR_MODEL_SETTINGS_KEY)
    if not isinstance(advisor_model, str) or not advisor_model.strip():
        return None
    return advisor_model.strip()


def model_family(model_name: str) -> str | None:
    """Return the family an alias or full model id names, or None.

    ::

        "fable" -> "fable"    "claude-fable-5-2" -> "fable"
        "claude-mythos-1" -> None
    """
    lowered_model_name = model_name.lower()
    for each_family_name in ALL_MODEL_FAMILY_NAMES:
        if each_family_name in lowered_model_name:
            return each_family_name
    return None


def runs_on_advisor_model(session_model: object, advisor_model: str) -> bool:
    """Return True when the session model is the advisor model or shares its known family.

    ::

        "claude-fable-5-2", "fable" -> True     "claude-mythos-1", "claude-mythos-1" -> True
        "claude-opus-5-5", "fable" -> False     "claude-mythos-1", "custom-advisor" -> False
    """
    if not isinstance(session_model, str):
        return False
    if session_model.strip().lower() == advisor_model.lower():
        return True
    session_family = model_family(session_model)
    return session_family is not None and session_family == model_family(advisor_model)


def main() -> None:
    """Emit the advisor guidance as SessionStart additionalContext when the advisor is on, the session runs on another model, and the session-prompts mod is off."""
    if is_mod_plugin_enabled(SESSION_PROMPTS_PLUGIN_NAME):
        return
    if is_advisor_disabled_by_environment():
        return
    advisor_model = configured_advisor_model(user_settings_path())
    if advisor_model is None:
        return
    session_start_payload = read_hook_input_dictionary_from_stdin() or {}
    if runs_on_advisor_model(session_start_payload.get(SESSION_MODEL_PAYLOAD_KEY), advisor_model):
        return
    session_start_output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": ADVISOR_RULES_PROMPT_TEMPLATE.format(advisor_model=advisor_model),
        }
    }
    sys.stdout.write(json.dumps(session_start_output) + "\n")


if __name__ == "__main__":
    main()
