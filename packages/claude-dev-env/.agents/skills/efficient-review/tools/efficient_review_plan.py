"""Choose haiku and the slim profile on Claude, and defer the model elsewhere."""

from __future__ import annotations

import importlib.util
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType

from tools.config import efficient_review_constants as c


class ReviewPlanFatal(RuntimeError):
    """The slim-profile constants module is not installed beside this skill."""


def plan_review(all_environment: Mapping[str, str]) -> dict[str, object]:
    """Return the runtime selection for one review.

    Args:
        all_environment: The process environment.

    Returns:
        Claude selects haiku and the slim profile. Every other runtime defers the model.
    """
    if _is_claude_runtime(all_environment):
        return _claude_plan(_load_gate_constants())
    return {
        "runtime": c.RUNTIME_OTHER,
        "model": c.MODEL_DEFERRED,
        "profile": c.PROFILE_DEFERRED,
    }


def _is_claude_runtime(all_environment: Mapping[str, str]) -> bool:
    if any(all_environment.get(each_name) for each_name in c.ALL_OTHER_HOST_VARIABLES):
        return False
    return any(all_environment.get(each_name) for each_name in c.ALL_CLAUDE_HOST_VARIABLES)


def _claude_plan(gate_constants: ModuleType) -> dict[str, object]:
    return {
        "runtime": c.RUNTIME_CLAUDE,
        "model": gate_constants.HAIKU_MODEL_FAMILY,
        "profile": gate_constants.SLIM_PROFILE_NAME,
        "command": [
            gate_constants.SLIM_PROFILE_EXECUTABLE,
            *gate_constants.ALL_SLIM_PROFILE_ARGUMENTS,
        ],
        "environment": list(gate_constants.ALL_SLIM_PROFILE_ENVIRONMENT),
    }


def _load_gate_constants() -> ModuleType:
    constants_path = _gate_constants_path()
    spec = importlib.util.spec_from_file_location(c.GATE_MODULE_NAME, constants_path)
    if spec is None or spec.loader is None:
        raise ReviewPlanFatal(f"cannot load slim profile constants from {constants_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _gate_constants_path() -> Path:
    for each_candidate in _candidate_paths(c.SKILL_ROOT):
        if each_candidate.is_file():
            return each_candidate
    raise ReviewPlanFatal(
        "the slim profile constants are missing; install the package hooks next to this skill"
    )


def _candidate_paths(skill_root: Path) -> tuple[Path, ...]:
    relative_parts = (
        c.HOOKS_DIRECTORY_NAME,
        c.HOOKS_CONSTANTS_DIRECTORY_NAME,
        c.GATE_CONSTANTS_FILENAME,
    )
    all_candidates = [
        skill_root.parents[each_step].joinpath(*relative_parts)
        for each_step in c.ALL_HOOKS_PARENT_STEPS
        if len(skill_root.parents) > each_step
    ]
    user_home = _parent_at(skill_root, c.USER_HOME_PARENT_STEP)
    if user_home is not None:
        all_candidates.append(
            user_home.joinpath(c.CLAUDE_HOME_DIRECTORY_NAME, *relative_parts)
        )
    return tuple(all_candidates)


def _parent_at(start: Path, steps: int) -> Path | None:
    if len(start.parents) <= steps:
        return None
    return start.parents[steps]
