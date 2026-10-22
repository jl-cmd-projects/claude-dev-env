#!/usr/bin/env python3
"""PreToolUse hook: route an agent about to build an artifact page by scope.

Registered on ``Artifact|Skill``. It adds one paragraph of ``additionalContext``
when a session starts a new artifact page. A status or progress report
prefers the status flowchart from
``docs/templates/artifact-page/status-flowchart.html``, unless the person asks
for another shape. One flow or one comparison is an
inline SVG flowchart with minimal text. A multi-part plan or evidence is an
html-plan page from ``docs/templates/html-plan/README.md``, and
``docs/templates/artifact-page/README.md`` stays the alternative:

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
    HTML_PLAN_TEMPLATE_README_PATH,
    PACKAGE_ROOT_DIRECTORY,
    POINTER_TEXT_TEMPLATE,
    SKILL_NAME_INPUT_KEY,
    SKILL_TOOL_NAME,
    STATUS_FLOWCHART_TEMPLATE_PATH,
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
from open_task_asks import claude_home


def installed_template_path(package_template_path: Path) -> Path:
    """Return the template path that exists where this hook runs.

    A source checkout keeps ``docs`` beside ``hooks``. An install puts hooks
    under the agents home and docs under the Claude home, so the same relative
    path is read from the Claude home there::

        <checkout>/packages/claude-dev-env/docs/templates/x.md  -> kept
        ~/.agents/docs/templates/x.md (missing)                 -> ~/.claude/docs/templates/x.md

    Args:
        package_template_path: A template path under the package root.

    Returns:
        The package path when it exists, else the same relative path under the Claude home.
    """
    if package_template_path.exists():
        return package_template_path
    return claude_home() / package_template_path.relative_to(PACKAGE_ROOT_DIRECTORY)


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
            ADDITIONAL_CONTEXT_KEY: POINTER_TEXT_TEMPLATE.format(
                path_of_status_flowchart=installed_template_path(STATUS_FLOWCHART_TEMPLATE_PATH),
                path_of_plan_readme=installed_template_path(HTML_PLAN_TEMPLATE_README_PATH),
                path_of_page_readme=installed_template_path(ARTIFACT_TEMPLATE_PATH),
            ),
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
