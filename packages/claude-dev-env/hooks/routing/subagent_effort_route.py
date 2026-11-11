"""Give a spawn an effort its Anthropic model family allows.

::

    {"model": "opus", "effort": "xhigh"}            -> effort "medium"
    {"model": "claude-sonnet-5-5"}                  -> effort "high"
    {"model": "fable", "effort": "max"}             -> effort "high"
    {"model": "haiku", "effort": "max"}             -> unchanged
    {"subagent_type": "fork"}                       -> unchanged
    {} with the parent on Opus                      -> effort "medium"
"""

from __future__ import annotations

import sys
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)

from hooks_constants.subagent_effort_route_constants import (
    ALL_ALLOWED_EFFORTS_BY_FAMILY,
    ALL_ROUTED_EFFORT_BY_FAMILY,
    EFFORT_INPUT_KEY,
    FORK_SUBAGENT_TYPE,
    MODEL_INPUT_KEY,
    SUBAGENT_TYPE_INPUT_KEY,
)


def model_family(model: object) -> str | None:
    """Return the Anthropic family a model name or alias belongs to.

    ::

        "opus" -> "opus"     "claude-fable-5-2" -> "fable"
        "inherit" -> None    None -> None

    Args:
        model: A model alias or full model id, or anything else.
    """
    if not isinstance(model, str):
        return None
    lowered_model = model.lower()
    for each_family in ALL_ALLOWED_EFFORTS_BY_FAMILY:
        if each_family in lowered_model:
            return each_family
    return None


def routed_effort(family: str, effort: object) -> str:
    """Return the effort a spawn of this family runs at.

    ::

        ("opus", "xhigh") -> "medium"     ("fable", "low") -> "low"
        ("sonnet", None) -> "high"

    Args:
        family: An Anthropic model family.
        effort: The effort the spawn named, or None.
    """
    if effort in ALL_ALLOWED_EFFORTS_BY_FAMILY[family]:
        return str(effort)
    return ALL_ROUTED_EFFORT_BY_FAMILY[family]


def route_spawn_input(
    tool_input: object, parent_model: str | None
) -> tuple[dict[str, object], str, str] | None:
    """Return the spawn input with an allowed effort, or None to leave it.

    A fork keeps its parent's model and effort. A spawn whose model resolves
    to no Anthropic family, from its own field or from the parent's model,
    is left as it is.

    Args:
        tool_input: The spawn tool's input.
        parent_model: The model of the session that spawns, when known.

    Returns:
        The updated input, the family, and the effort, or None when the
        input already holds an allowed effort or cannot be routed.
    """
    if not isinstance(tool_input, dict):
        return None
    if tool_input.get(SUBAGENT_TYPE_INPUT_KEY) == FORK_SUBAGENT_TYPE:
        return None
    family = model_family(tool_input.get(MODEL_INPUT_KEY)) or model_family(parent_model)
    if family is None:
        return None
    current_effort = tool_input.get(EFFORT_INPUT_KEY)
    allowed_effort = routed_effort(family, current_effort)
    if allowed_effort == current_effort:
        return None
    return {**tool_input, EFFORT_INPUT_KEY: allowed_effort}, family, allowed_effort
