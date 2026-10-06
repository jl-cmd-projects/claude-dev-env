"""Measure the text a context-adding hook injects and hold it to its budget.

::

    command ["env", "A=1", "python3", "hooks/x.py"]
      runs  <current python> hooks/x.py  with A=1, PATH, and an empty home
    stdout {"hookSpecificOutput": {"additionalContext": "..."}}  -> its length
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from context_budget.model import BudgetPolicy, HookBudget
from hooks_constants.context_budget_constants import (
    ADDITIONAL_CONTEXT_KEY,
    ALL_HOME_ENVIRONMENT_NAMES,
    ALL_INHERITED_ENVIRONMENT_NAMES,
    ALL_PYTHON_COMMAND_NAMES,
    ENV_ASSIGNMENT_SEPARATOR,
    ENV_COMMAND_NAME,
    HOOK_FINDING_TEMPLATE,
    HOOK_GROWN_TEMPLATE,
    HOOK_SPECIFIC_OUTPUT_KEY,
    HOOK_TIMEOUT_SECONDS,
    SYSTEM_MESSAGE_KEY,
    UTF8_ENCODING,
)


def _text_length(raw_value: object) -> int:
    return len(raw_value) if isinstance(raw_value, str) else 0


def injected_character_count(hook_stdout: str) -> int:
    """Count the characters a hook injects into the session.

    Args:
        hook_stdout: The hook's standard output.

    Returns:
        The length of ``additionalContext`` plus ``systemMessage`` when the
        output is a JSON object, else the length of the output.
    """
    try:
        parsed_output = json.loads(hook_stdout)
    except json.JSONDecodeError:
        return len(hook_stdout)
    if not isinstance(parsed_output, dict):
        return len(hook_stdout)
    hook_specific_output = parsed_output.get(HOOK_SPECIFIC_OUTPUT_KEY)
    context_length = 0
    if isinstance(hook_specific_output, dict):
        context_length = _text_length(hook_specific_output.get(ADDITIONAL_CONTEXT_KEY))
    return context_length + _text_length(parsed_output.get(SYSTEM_MESSAGE_KEY))


def hook_findings(policy: BudgetPolicy, hook: HookBudget, character_count: int) -> tuple[str, ...]:
    """Check one hook's injected character count against its limit or baseline.

    Args:
        policy: Budget policy holding the hook baseline.
        hook: The measured hook.
        character_count: Characters the hook injected.

    Returns:
        A one-message tuple when the hook is over budget, else empty.
    """
    recorded_count = policy.baseline_characters_by_hook_name.get(hook.name)
    if recorded_count is not None:
        if character_count <= recorded_count:
            return ()
        return (
            HOOK_GROWN_TEMPLATE.format(
                name=hook.name, count=character_count, recorded=recorded_count
            ),
        )
    if character_count <= hook.char_limit:
        return ()
    return (
        HOOK_FINDING_TEMPLATE.format(name=hook.name, count=character_count, limit=hook.char_limit),
    )


def split_command_environment(
    all_command_parts: Sequence[str],
) -> tuple[dict[str, str], tuple[str, ...]]:
    """Lift a leading ``env NAME=value ...`` prefix out of a hook command.

    ::

        ["env", "A=1", "python3", "x.py"] -> ({"A": "1"}, ("python3", "x.py"))

    Args:
        all_command_parts: The policy's command vector.

    Returns:
        The environment pairs and the remaining argument vector.
    """
    if not all_command_parts or all_command_parts[0] != ENV_COMMAND_NAME:
        return {}, tuple(all_command_parts)
    value_by_name: dict[str, str] = {}
    remaining_index = 1
    for each_part in all_command_parts[1:]:
        name, separator, value = each_part.partition(ENV_ASSIGNMENT_SEPARATOR)
        if not separator or not name:
            break
        value_by_name[name] = value
        remaining_index += 1
    return value_by_name, tuple(all_command_parts[remaining_index:])


def _hook_environment(home_directory: str, value_by_name: dict[str, str]) -> dict[str, str]:
    environment = {
        each_name: os.environ[each_name]
        for each_name in ALL_INHERITED_ENVIRONMENT_NAMES
        if each_name in os.environ
    }
    environment.update(dict.fromkeys(ALL_HOME_ENVIRONMENT_NAMES, home_directory))
    environment.update(value_by_name)
    return environment


def run_hook_command(hook: HookBudget, repository_root: Path) -> str:
    """Run one hook from the repository root under a minimal environment.

    The environment holds the inherited executable-search names, a fresh empty
    home directory, and the command's own ``env`` pairs. A ``python`` or
    ``python3`` command runs under the current interpreter.

    Args:
        hook: The hook to run.
        repository_root: Directory the command runs from.

    Returns:
        The hook's standard output.
    """
    value_by_name, all_arguments = split_command_environment(hook.all_command_parts)
    if all_arguments and all_arguments[0] in ALL_PYTHON_COMMAND_NAMES:
        all_arguments = (sys.executable, *all_arguments[1:])
    with tempfile.TemporaryDirectory() as home_directory:
        completed_process = subprocess.run(
            list(all_arguments),
            input=hook.stdin_text,
            capture_output=True,
            text=True,
            encoding=UTF8_ENCODING,
            cwd=repository_root,
            env=_hook_environment(home_directory, value_by_name),
            timeout=HOOK_TIMEOUT_SECONDS,
            check=False,
        )
    return completed_process.stdout
