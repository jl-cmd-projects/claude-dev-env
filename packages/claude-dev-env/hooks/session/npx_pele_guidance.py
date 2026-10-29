#!/usr/bin/env python3
"""PreToolUse hook: tell an agent how to render Mermaid when it runs ``npx pele``.

Registered on ``Bash|PowerShell``. Pele is a library with no command, so
``npx pele`` fails. When the command matches, the hook adds one block of
``additionalContext`` that names the installed copy and a Node snippet that
renders with it. When no copy is installed, the block points to the pele.run
playground instead. Every other command gets no output:

::

    Bash {"command": "npx -y pele chain.mmd"}   -> the guidance block
    Bash {"command": "npm install pele"}        -> no output

The command runs with its normal permission flow.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)

from hooks_constants.hook_specific_output_keys import (
    HOOK_EVENT_NAME_KEY,
    HOOK_SPECIFIC_OUTPUT_KEY,
)
from hooks_constants.npx_pele_guidance_constants import (
    ABSENT_GUIDANCE_TEMPLATE,
    ALL_NPM_EXEC_SUBCOMMANDS,
    ALL_NPX_PROGRAM_NAMES,
    ALL_OPTIONS_WITH_SEPARATE_VALUE,
    ALL_PELE_ENTRY_PATH_PARTS,
    COMMAND_INPUT_KEY,
    FLAG_PREFIX,
    INSTALLED_GUIDANCE_TEMPLATE,
    NODE_MODULES_DIRECTORY_NAME,
    NPM_PROGRAM_NAME,
    PACKAGE_MANIFEST_NAME,
    PACKAGE_VERSION_SEPARATOR,
    PELE_PACKAGE_NAME,
    PELE_TOOLS_DIRECTORY_NAME,
)
from hooks_constants.pre_tool_use_context_runner import run_context_hook
from hooks_constants.pytest_invocation import unquoted_token
from hooks_constants.shell_command_wrappers import (
    all_wrapped_command_segments,
    segment_program_and_arguments,
)
from hooks_constants.spawn_readiness_hook_constants import (
    ADDITIONAL_CONTEXT_KEY,
    PRE_TOOL_USE_EVENT_NAME,
    TOOL_INPUT_KEY,
)
from open_task_asks import claude_home


def pele_package_directory_under(claude_root: Path) -> Path:
    """Return the folder a Claude root keeps its Pele package in.

    Args:
        claude_root: The Claude home, or the root an install was given.

    Returns:
        ``<claude_root>/tools/pele/node_modules/pele``, where the claude-dev-env
        installer places Pele.
    """
    return (
        claude_root
        / PELE_TOOLS_DIRECTORY_NAME
        / PELE_PACKAGE_NAME
        / NODE_MODULES_DIRECTORY_NAME
        / PELE_PACKAGE_NAME
    )


def pele_package_directory() -> Path:
    """Return the folder the Claude home keeps its Pele package in.

    Returns:
        The Pele package folder under the Claude home.
    """
    return pele_package_directory_under(claude_home())


def installed_pele_version(package_directory: Path) -> str | None:
    """Read the version from an installed Pele package manifest.

    Args:
        package_directory: The folder that holds Pele's ``package.json``.

    Returns:
        The version string, or None when the manifest is missing or unreadable.
    """
    manifest_path = package_directory / PACKAGE_MANIFEST_NAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(manifest, dict):
        return None
    version = manifest.get("version")
    return version if isinstance(version, str) and version else None


def is_npx_pele_command(tool_input: object) -> bool:
    """Return True when the shell command runs Pele through npx.

    Args:
        tool_input: The Bash or PowerShell ``tool_input``.

    Returns:
        True when a command segment runs ``npx`` or ``npm exec`` on the
        ``pele`` package. The shared shell parser reads wrapper words, quotes,
        substitutions, and heredocs.
    """
    if not isinstance(tool_input, dict):
        return False
    command_text = tool_input.get(COMMAND_INPUT_KEY)
    if not isinstance(command_text, str):
        return False
    return any(
        _segment_runs_npx_pele(each_segment)
        for each_segment in all_wrapped_command_segments(command_text)
    )


def _segment_runs_npx_pele(all_segment_tokens: list[str]) -> bool:
    program_name, all_arguments = segment_program_and_arguments(all_segment_tokens)
    all_package_arguments = _package_arguments_of(program_name, all_arguments)
    return bool(all_package_arguments) and _is_pele_package(all_package_arguments[0])


def _package_arguments_of(program_name: str, all_arguments: list[str]) -> list[str]:
    if program_name in ALL_NPX_PROGRAM_NAMES:
        return _arguments_after_options(all_arguments)
    if program_name != NPM_PROGRAM_NAME:
        return []
    all_npm_arguments = _arguments_after_options(all_arguments)
    npm_subcommand = unquoted_token(all_npm_arguments[0]) if all_npm_arguments else ""
    if npm_subcommand not in ALL_NPM_EXEC_SUBCOMMANDS:
        return []
    return _arguments_after_options(all_npm_arguments[1:])


def _arguments_after_options(all_arguments: list[str]) -> list[str]:
    all_remaining = list(all_arguments)
    while all_remaining and unquoted_token(all_remaining[0]).startswith(FLAG_PREFIX):
        takes_separate_value = unquoted_token(all_remaining[0]) in ALL_OPTIONS_WITH_SEPARATE_VALUE
        all_remaining = all_remaining[1:]
        if takes_separate_value:
            all_remaining = all_remaining[1:]
    return all_remaining


def _is_pele_package(argument: str) -> bool:
    package_name = unquoted_token(argument).split(PACKAGE_VERSION_SEPARATOR, 1)[0]
    return package_name == PELE_PACKAGE_NAME


def guidance_text() -> str:
    """Return the guidance for the Pele copy this machine has, or none.

    Returns:
        The installed-copy snippet when a Pele manifest reads and its entry
        file exists, else the playground guidance.
    """
    package_directory = pele_package_directory()
    package_entry = package_directory.joinpath(*ALL_PELE_ENTRY_PATH_PARTS)
    version = installed_pele_version(package_directory)
    if version is None or not package_entry.is_file():
        return ABSENT_GUIDANCE_TEMPLATE.format(package_directory=package_directory)
    return INSTALLED_GUIDANCE_TEMPLATE.format(
        version=version,
        package_directory=package_directory,
        package_entry=json.dumps(str(package_entry)),
    )


def decide_hook_output(all_hook_fields: dict[str, object]) -> dict[str, object] | None:
    """Return the guidance as additionalContext output, or None to stay quiet.

    Args:
        all_hook_fields: The parsed PreToolUse payload.

    Returns:
        The ``hookSpecificOutput`` object, or None when the command does not run Pele through npx.
    """
    if not is_npx_pele_command(all_hook_fields.get(TOOL_INPUT_KEY)):
        return None
    return {
        HOOK_SPECIFIC_OUTPUT_KEY: {
            HOOK_EVENT_NAME_KEY: PRE_TOOL_USE_EVENT_NAME,
            ADDITIONAL_CONTEXT_KEY: guidance_text(),
        }
    }


def main() -> int:
    """Read the PreToolUse payload and print the guidance when the command runs npx pele.

    Returns:
        0 in every case; the guidance travels in the JSON output.
    """
    return run_context_hook(decide_hook_output)


if __name__ == "__main__":
    sys.exit(main())
