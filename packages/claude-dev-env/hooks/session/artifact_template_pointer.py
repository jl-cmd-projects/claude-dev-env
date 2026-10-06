#!/usr/bin/env python3
"""PreToolUse hook: point an agent about to build an artifact page at the template.

Registered on ``Artifact|Skill``. It adds one line of ``additionalContext``
naming ``docs/templates/artifact-page/template.html`` when a session starts a
new artifact page:

::

    Artifact {"action": "quickstart", ...}   -> the pointer line
    Skill    {"skill": "artifact-design"}    -> the pointer line
    Artifact {"action": "publish", ...}      -> no output
    Skill    {"skill": "pr-lifecycle"}       -> no output

The call runs with its normal permission flow.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)

from hooks_constants.artifact_template_pointer_constants import (
    ALL_ARTIFACT_DESIGN_SKILL_NAMES,
    ARTIFACT_ACTION_INPUT_KEY,
    ARTIFACT_QUICKSTART_ACTION,
    ARTIFACT_TEMPLATE_PATH,
    ARTIFACT_TOOL_NAME,
    POINTER_TEXT_PREFIX,
    SKILL_NAME_INPUT_KEY,
    SKILL_TOOL_NAME,
)
from hooks_constants.hook_specific_output_keys import (
    HOOK_EVENT_NAME_KEY,
    HOOK_SPECIFIC_OUTPUT_KEY,
)
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
from hooks_constants.spawn_readiness_hook_constants import (
    ADDITIONAL_CONTEXT_KEY,
    PRE_TOOL_USE_EVENT_NAME,
    TOOL_INPUT_KEY,
    TOOL_NAME_KEY,
)


def starts_an_artifact_page(tool_name: object, tool_input: object) -> bool:
    """Return True when the call is the first step of building an artifact page.

    Args:
        tool_name: The tool the session called.
        tool_input: The tool input.
    """
    if not isinstance(tool_input, dict):
        return False
    if tool_name == ARTIFACT_TOOL_NAME:
        return tool_input.get(ARTIFACT_ACTION_INPUT_KEY) == ARTIFACT_QUICKSTART_ACTION
    if tool_name == SKILL_TOOL_NAME:
        return tool_input.get(SKILL_NAME_INPUT_KEY) in ALL_ARTIFACT_DESIGN_SKILL_NAMES
    return False


def decide_hook_output(all_hook_fields: dict[str, object]) -> dict[str, object] | None:
    """Return the pointer as additionalContext output, or None to stay quiet.

    Args:
        all_hook_fields: The parsed PreToolUse payload.
    """
    if not starts_an_artifact_page(
        all_hook_fields.get(TOOL_NAME_KEY), all_hook_fields.get(TOOL_INPUT_KEY)
    ):
        return None
    return {
        HOOK_SPECIFIC_OUTPUT_KEY: {
            HOOK_EVENT_NAME_KEY: PRE_TOOL_USE_EVENT_NAME,
            ADDITIONAL_CONTEXT_KEY: f"{POINTER_TEXT_PREFIX}{ARTIFACT_TEMPLATE_PATH}.",
        }
    }


def main() -> int:
    """Read the PreToolUse payload and print the pointer when the call starts a page.

    Returns:
        0 in every case; the pointer travels in the JSON output.
    """
    hook_payload = read_hook_input_dictionary_from_stdin()
    if hook_payload is None:
        return 0
    hook_output = decide_hook_output(hook_payload)
    if hook_output is not None:
        sys.stdout.write(json.dumps(hook_output))
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
