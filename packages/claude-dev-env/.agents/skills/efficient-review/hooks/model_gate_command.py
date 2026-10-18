"""Find the model family named by an efficient-review command."""

from __future__ import annotations

import re

from hooks.config.model_gate_constants import (
    COMMAND_KEY,
    COMMAND_MODEL_PATTERN,
    EFFICIENT_REVIEW_RUN_PATTERN,
    INVOCATION_END_PATTERN,
    METHOD_KEY,
    MODEL_INPUT_KEY,
    OWNER_NAME_KEY,
    PYTHON_RUN_GROUP,
    REPOSITORY_NAME_KEY,
    RUN_WORKFLOW_METHOD,
    SHELL_REPOSITORY_PATTERN,
    UNREADABLE_INPUT_PATTERN,
    WORKFLOW_ID_KEY,
    WORKFLOW_INPUTS_KEY,
    ALTERNATION_SEPARATOR,
    TARGET_BOUNDARY_TEMPLATE,
)
from tools.config.efficient_review_settings import string_list


def requested_model_families(
    tool_name: object,
    all_tool_arguments: dict[str, object],
    all_settings: dict[str, object],
) -> tuple[str, ...]:
    """Return the requested review families in order, without duplicates.

    Args:
        tool_name: The guarded tool's name.
        all_tool_arguments: The call's tool_input.
        all_settings: The skill settings.

    Returns:
        The family names the call asks to run.
    """
    if tool_name == all_settings["hook_dispatch_tool"]:
        return _dispatch_model_families(all_tool_arguments, all_settings)
    if tool_name in string_list(all_settings, "hook_shell_tools"):
        return _shell_model_families(all_tool_arguments, all_settings)
    return ()


def _shell_model_families(
    all_tool_arguments: dict[str, object], all_settings: dict[str, object]
) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            each_model.group("family").lower()
            for each_arguments in _review_invocation_arguments(
                all_tool_arguments, all_settings
            )
            for each_model in re.finditer(
                COMMAND_MODEL_PATTERN, each_arguments, re.IGNORECASE
            )
        )
    )


def _dispatch_model_families(
    all_tool_arguments: dict[str, object], all_settings: dict[str, object]
) -> tuple[str, ...]:
    if not _is_review_dispatch(all_tool_arguments, all_settings):
        return ()
    all_inputs = all_tool_arguments.get(WORKFLOW_INPUTS_KEY)
    model = all_inputs.get(MODEL_INPUT_KEY) if isinstance(all_inputs, dict) else None
    if not isinstance(model, str) or not model.strip():
        return ()
    return (model.strip().lower(),)


def _is_review_dispatch(
    all_tool_arguments: dict[str, object], all_settings: dict[str, object]
) -> bool:
    workflow_name = str(all_tool_arguments.get(WORKFLOW_ID_KEY)).rsplit("/")[-1]
    if all_tool_arguments.get(METHOD_KEY) != RUN_WORKFLOW_METHOD:
        return False
    if workflow_name not in _workflow_names(all_settings):
        return False
    return _dispatch_repository_matches(all_tool_arguments, all_settings)


def _workflow_names(all_settings: dict[str, object]) -> set[str]:
    names = {str(all_settings["dispatch_workflow_file"])}
    workflow_id = str(all_settings.get("dispatch_workflow_id") or "")
    if workflow_id:
        names.add(workflow_id)
    return names


def _dispatch_repository_matches(
    all_tool_arguments: dict[str, object], all_settings: dict[str, object]
) -> bool:
    owner = str(all_settings.get("hook_owner") or "")
    repository = str(all_settings.get("hook_repository") or "")
    if not owner and not repository:
        return True
    return (
        str(all_tool_arguments.get(REPOSITORY_NAME_KEY)).lower() == repository.lower()
        and str(all_tool_arguments.get(OWNER_NAME_KEY)).lower() == owner.lower()
    )


def has_unreadable_inputs(
    tool_name: object,
    all_tool_arguments: dict[str, object],
    all_settings: dict[str, object],
) -> bool:
    """Return whether a shell efficient review hides its model input.

    Args:
        tool_name: The guarded tool's name.
        all_tool_arguments: The call's tool_input.
        all_settings: The skill settings.

    Returns:
        Whether the invocation uses a pipe, a file, or a shell variable for the model.
    """
    if tool_name not in string_list(all_settings, "hook_shell_tools"):
        return False
    return any(
        re.search(UNREADABLE_INPUT_PATTERN, each_arguments)
        for each_arguments in _review_invocation_arguments(
            all_tool_arguments, all_settings
        )
    )


def _review_invocation_arguments(
    all_tool_arguments: dict[str, object], all_settings: dict[str, object]
) -> list[str]:
    command = all_tool_arguments.get(COMMAND_KEY)
    if not isinstance(command, str):
        return []
    all_runs = [
        (
            each_run,
            re.split(INVOCATION_END_PATTERN, command[each_run.end() :], maxsplit=1)[0],
        )
        for each_run in re.finditer(
            EFFICIENT_REVIEW_RUN_PATTERN, command, re.IGNORECASE
        )
    ]
    return [
        each_arguments
        for each_run, each_arguments in all_runs
        if each_run.group(PYTHON_RUN_GROUP)
        or _is_review_dispatch_target(each_arguments, all_settings)
    ]


def _is_review_dispatch_target(arguments: str, all_settings: dict[str, object]) -> bool:
    if not re.search(_target_pattern(all_settings), arguments):
        return False
    return all(
        _named_repository_matches(each_target, all_settings)
        for each_target in re.finditer(SHELL_REPOSITORY_PATTERN, arguments)
    )


def _target_pattern(all_settings: dict[str, object]) -> str:
    names = [re.escape(str(all_settings["dispatch_workflow_file"]))]
    workflow_id = str(all_settings.get("dispatch_workflow_id") or "")
    if workflow_id:
        names.append(re.escape(workflow_id))
    joined = ALTERNATION_SEPARATOR.join(names)
    return TARGET_BOUNDARY_TEMPLATE.format(joined=joined)


def _named_repository_matches(each_target: re.Match[str], all_settings: dict[str, object]) -> bool:
    owner = str(all_settings.get("hook_owner") or "")
    repository = str(all_settings.get("hook_repository") or "")
    if not owner and not repository:
        return True
    return (
        each_target.group("owner").lower() == owner.lower()
        and each_target.group("repository").lower() == repository.lower()
    )
