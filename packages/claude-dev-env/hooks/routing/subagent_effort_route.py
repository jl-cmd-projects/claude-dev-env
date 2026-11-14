"""Give a spawn an effort its Anthropic model family allows.

The allowed efforts and the default for each family come from the
hand-edited ``hooks_constants/subagent_effort_levels.json``. With the
shipped file::

    {"model": "opus", "effort": "max"}              -> effort "medium"
    {"model": "opus", "effort": "high"}             -> unchanged
    {"model": "claude-sonnet-5-5"}                  -> effort "high"
    {"model": "fable", "effort": "max"}             -> effort "high"
    {"model": "haiku", "effort": "max"}             -> unchanged
    {"subagent_type": "fork"}                       -> unchanged
    {} with the parent on Opus                      -> effort "medium"
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import NamedTuple

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)

from hooks_constants.subagent_effort_route_constants import (
    ALL_BUILT_IN_EFFORT_LEVELS_BY_FAMILY,
    ALL_KNOWN_EFFORT_NAMES,
    ALLOWED_EFFORTS_KEY,
    DEFAULT_EFFORT_KEY,
    EFFORT_INPUT_KEY,
    EFFORT_LEVELS_FALLBACK_DIAGNOSTIC,
    EFFORT_LEVELS_PATH,
    FORK_SUBAGENT_TYPE,
    MODEL_INPUT_KEY,
    SUBAGENT_TYPE_INPUT_KEY,
)


class FamilyEfforts(NamedTuple):
    """The efforts one model family may run at, and the one it gets otherwise."""

    allowed: tuple[str, ...]
    default: str


class EffortLevelsInvalid(ValueError):
    """Raised when an effort levels table does not hold the expected shape."""


def _family_efforts(family: object, family_fields: object) -> FamilyEfforts:
    if not isinstance(family, str) or not family or not isinstance(family_fields, Mapping):
        raise EffortLevelsInvalid(f"entry {family!r} is not a family name with an object")
    all_allowed = family_fields.get(ALLOWED_EFFORTS_KEY)
    default_effort = family_fields.get(DEFAULT_EFFORT_KEY)
    if (
        not isinstance(all_allowed, Sequence)
        or isinstance(all_allowed, str)
        or not all_allowed
        or not all(isinstance(each_effort, str) for each_effort in all_allowed)
    ):
        raise EffortLevelsInvalid(f"{family} {ALLOWED_EFFORTS_KEY} is not a list of effort names")
    for each_effort in all_allowed:
        if each_effort not in ALL_KNOWN_EFFORT_NAMES:
            raise EffortLevelsInvalid(f"{family} {ALLOWED_EFFORTS_KEY} holds unknown effort {each_effort!r}")
    if default_effort not in all_allowed:
        raise EffortLevelsInvalid(f"{family} {DEFAULT_EFFORT_KEY} is not in its {ALLOWED_EFFORTS_KEY} list")
    return FamilyEfforts(tuple(all_allowed), str(default_effort))


def parsed_effort_levels(levels_table: object) -> dict[str, FamilyEfforts]:
    """Return the effort levels a table holds, keyed by lowercase family.

    ::

        {"opus": {"allowed": ["medium", "high"], "default": "medium"}}
            -> {"opus": FamilyEfforts(("medium", "high"), "medium")}

    Args:
        levels_table: The parsed effort levels file, or the built-in table.

    Raises:
        EffortLevelsInvalid: The table is not an object, leaves out a built-in
            family, or holds a family whose allowed list is empty, names an
            effort outside ``ALL_KNOWN_EFFORT_NAMES``, or leaves out its default.
    """
    if not isinstance(levels_table, Mapping) or not levels_table:
        raise EffortLevelsInvalid("the file is not an object with at least one family")
    all_efforts_by_family = {
        str(each_family).lower(): _family_efforts(each_family, each_fields)
        for each_family, each_fields in levels_table.items()
    }
    for each_built_in_family in ALL_BUILT_IN_EFFORT_LEVELS_BY_FAMILY:
        if each_built_in_family not in all_efforts_by_family:
            raise EffortLevelsInvalid(f"family {each_built_in_family} is missing")
    return all_efforts_by_family


def load_effort_levels(levels_path: Path = EFFORT_LEVELS_PATH) -> dict[str, FamilyEfforts]:
    """Read the effort levels file, or fall back to the built-in levels.

    A missing, unreadable, or invalid file, a path that is not a regular
    file, or a file nested too deep to parse writes one diagnostic line naming the file and the fault to stderr and
    returns the built-in levels.

    Args:
        levels_path: The effort levels JSON file, the shipped one by default.
    """
    try:
        if not levels_path.is_file():
            raise EffortLevelsInvalid("the path is not a regular file")
        return parsed_effort_levels(json.loads(levels_path.read_text(encoding="utf-8")))
    except (OSError, ValueError, RecursionError) as load_error:
        sys.stderr.write(EFFORT_LEVELS_FALLBACK_DIAGNOSTIC.format(path=levels_path, problem=load_error))
        return parsed_effort_levels(ALL_BUILT_IN_EFFORT_LEVELS_BY_FAMILY)


def model_family(model: object, all_efforts_by_family: Mapping[str, FamilyEfforts]) -> str | None:
    """Return the Anthropic family a model name or alias belongs to.

    ::

        "opus" -> "opus"     "claude-fable-5-2" -> "fable"
        "inherit" -> None    None -> None

    Args:
        model: A model alias or full model id, or anything else.
        all_efforts_by_family: The effort levels by family.
    """
    if not isinstance(model, str):
        return None
    lowered_model = model.lower()
    for each_family in all_efforts_by_family:
        if each_family in lowered_model:
            return each_family
    return None


def routed_effort(family: str, effort: object, all_efforts_by_family: Mapping[str, FamilyEfforts]) -> str:
    """Return the effort a spawn of this family runs at.

    ::

        ("opus", "max") -> "medium"       ("fable", "low") -> "low"
        ("sonnet", None) -> "high"

    Args:
        family: An Anthropic model family.
        effort: The effort the spawn named, or None.
        all_efforts_by_family: The effort levels by family.
    """
    family_efforts = all_efforts_by_family[family]
    if effort in family_efforts.allowed:
        return str(effort)
    return family_efforts.default


def route_spawn_input(
    tool_input: object, parent_model: str | None, all_efforts_by_family: Mapping[str, FamilyEfforts]
) -> tuple[dict[str, object], str, str] | None:
    """Return the spawn input with an allowed effort, or None to leave it.

    A fork keeps its parent's model and effort. A spawn whose model resolves
    to no Anthropic family, from its own field or from the parent's model,
    is left as it is.

    Args:
        tool_input: The spawn tool's input.
        parent_model: The model of the session that spawns, when known.
        all_efforts_by_family: The effort levels by family, from ``load_effort_levels``.

    Returns:
        The updated input, the family, and the effort, or None when the
        input already holds an allowed effort or cannot be routed.
    """
    if not isinstance(tool_input, dict):
        return None
    if tool_input.get(SUBAGENT_TYPE_INPUT_KEY) == FORK_SUBAGENT_TYPE:
        return None
    family = model_family(tool_input.get(MODEL_INPUT_KEY), all_efforts_by_family) or model_family(
        parent_model, all_efforts_by_family
    )
    if family is None:
        return None
    current_effort = tool_input.get(EFFORT_INPUT_KEY)
    allowed_effort = routed_effort(family, current_effort, all_efforts_by_family)
    if allowed_effort == current_effort:
        return None
    return {**tool_input, EFFORT_INPUT_KEY: allowed_effort}, family, allowed_effort
