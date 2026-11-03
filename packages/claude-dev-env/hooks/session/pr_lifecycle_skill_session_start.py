#!/usr/bin/env python3
"""SessionStart hook that puts a summary of the pr-lifecycle skill into the session context.

The pull request lifecycle gate counts this context as a skill load, so a session
can commit, push, or open a pull request without calling the Skill tool first.

::

    SessionStart, source startup or compact   -> additionalContext: summary inside the loaded tag
    SessionStart, skill file missing          -> nothing; the gate still needs a Skill call
    payload with no source field              -> nothing
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_hooks_dir = str(Path(__file__).resolve().parent.parent)
if _hooks_dir not in sys.path:
    sys.path.insert(0, _hooks_dir)

from hooks_constants.pr_lifecycle_skill_gate_constants import (
    SKILL_FILE,
    SKILL_LOADED_CLOSING_TAG,
    SKILL_LOADED_MARKER,
    SKILL_CONTEXT_SUMMARY,
)
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
from hooks_constants.session_start_injector import (
    InjectorConfiguration,
    build_additional_context_payload,
    inject_session_start_context,
)
from hooks_constants.session_start_injector_constants import (
    ALL_KNOWN_SESSION_START_SOURCES,
    DEFAULT_INJECTOR_TIMEOUT_MILLISECONDS,
)


def skill_context(skill_file: Path = SKILL_FILE) -> str | None:
    """Return the summary inside the loaded tag, or None when the skill file is missing.

    ::

        skill file present -> '<skill-loaded name="pr-lifecycle">' + summary + '</skill-loaded>'
        skill file missing -> None

    Args:
        skill_file: Path to the packaged pr-lifecycle SKILL.md.
    """
    if not skill_file.is_file():
        return None
    return f"{SKILL_LOADED_MARKER}\n{SKILL_CONTEXT_SUMMARY}{SKILL_LOADED_CLOSING_TAG}"


def session_start_payload(
    payload_by_key: dict[str, object],
    skill_file: Path = SKILL_FILE,
) -> dict[str, object]:
    """Return the SessionStart stdout that carries the summary, or an empty dict.

    ::

        source startup, skill file present  -> {"hookSpecificOutput": {"additionalContext": ...}}
        source compact, skill file present  -> the same payload
        no source field                     -> {}
        source startup, skill file missing  -> {}

    Args:
        payload_by_key: The parsed SessionStart stdin payload.
        skill_file: Path to the packaged pr-lifecycle SKILL.md.
    """
    context_text = skill_context(skill_file)
    if context_text is None:
        return {}
    configuration = InjectorConfiguration(
        is_enabled=True,
        timeout_milliseconds=DEFAULT_INJECTOR_TIMEOUT_MILLISECONDS,
        context_by_source={each_source: context_text for each_source in ALL_KNOWN_SESSION_START_SOURCES},
    )
    return build_additional_context_payload(inject_session_start_context(payload_by_key, configuration))


def main() -> None:
    """Print the skill summary for a SessionStart payload, or stay silent."""
    payload_by_key = read_hook_input_dictionary_from_stdin()
    if payload_by_key is None:
        return
    payload = session_start_payload(payload_by_key)
    if payload:
        sys.stdout.write(json.dumps(payload) + "\n")


if __name__ == "__main__":
    main()
