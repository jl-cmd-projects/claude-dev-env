"""Read the brief a spawn call hands its agents, for the spawn hooks that check it.

Each spawn tool keeps its brief in its own input field. A ``Workflow`` call
carries a script or a path to one, and a workflow dispatch carries the brief in
its ``prompt`` input.

::

    Agent             {"prompt": "Do X."}                         -> "Do X."
    Workflow          {"scriptPath": "w.js"}                      -> the text of w.js
    actions trigger   {"method": "run_workflow",
                       "inputs": {"prompt": "Do X."}}             -> "Do X."
    actions trigger   {"method": "cancel_workflow_run"}           -> None
    Bash              {"command": "ls"}                           -> None
"""

from __future__ import annotations

import sys
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)

from hooks_constants.spawn_readiness_hook_constants import (
    ALL_BRIEF_FIELDS_BY_SPAWN_TOOL_NAME,
    DISPATCH_INPUTS_KEY,
    DISPATCH_METHOD_INPUT_KEY,
    DISPATCH_PROMPT_INPUT_KEY,
    DISPATCH_RUN_WORKFLOW_METHOD,
    TRANSCRIPT_DECODE_ERRORS,
    TRANSCRIPT_ENCODING,
    WORKFLOW_DISPATCH_TOOL_NAME,
    WORKFLOW_SCRIPT_PATH_INPUT_KEY,
    WORKFLOW_TOOL_NAME,
)


def _workflow_script(all_tool_input_fields: dict[str, object]) -> str:
    script = all_tool_input_fields.get(ALL_BRIEF_FIELDS_BY_SPAWN_TOOL_NAME[WORKFLOW_TOOL_NAME])
    if isinstance(script, str):
        return script
    script_path = all_tool_input_fields.get(WORKFLOW_SCRIPT_PATH_INPUT_KEY)
    if not isinstance(script_path, str) or not script_path:
        return ""
    try:
        return Path(script_path).read_text(
            encoding=TRANSCRIPT_ENCODING, errors=TRANSCRIPT_DECODE_ERRORS
        )
    except OSError:
        return ""


def _dispatch_prompt(all_tool_input_fields: dict[str, object]) -> str | None:
    if all_tool_input_fields.get(DISPATCH_METHOD_INPUT_KEY) != DISPATCH_RUN_WORKFLOW_METHOD:
        return None
    workflow_inputs = all_tool_input_fields.get(DISPATCH_INPUTS_KEY)
    if not isinstance(workflow_inputs, dict):
        return None
    prompt = workflow_inputs.get(DISPATCH_PROMPT_INPUT_KEY)
    return prompt if isinstance(prompt, str) else None


def spawn_brief_text(tool_name: object, all_tool_input_fields: dict[str, object]) -> str | None:
    """Return the brief a spawn call hands its agents, or None when the call spawns none.

    A spawn tool whose brief field is missing or not a string gives "", so a
    hook can tell an empty brief from a call that spawns nothing.

    Args:
        tool_name: The tool the session called.
        all_tool_input_fields: The tool input.

    Returns:
        The brief text, "" for a spawn with no readable brief, or None.
    """
    if tool_name == WORKFLOW_DISPATCH_TOOL_NAME:
        return _dispatch_prompt(all_tool_input_fields)
    if not isinstance(tool_name, str) or tool_name not in ALL_BRIEF_FIELDS_BY_SPAWN_TOOL_NAME:
        return None
    if tool_name == WORKFLOW_TOOL_NAME:
        return _workflow_script(all_tool_input_fields)
    brief = all_tool_input_fields.get(ALL_BRIEF_FIELDS_BY_SPAWN_TOOL_NAME[tool_name])
    return brief if isinstance(brief, str) else ""
