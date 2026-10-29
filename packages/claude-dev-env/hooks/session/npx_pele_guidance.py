#!/usr/bin/env python3
"""PreToolUse hook: tell an agent how to render Mermaid when it runs ``npx pele``.

Registered on ``Bash|PowerShell``. Pele is a library with no command, so
``npx pele`` fails. When the command matches, the hook adds one block of
``additionalContext`` that names the installed copy and a Node snippet that
renders with it. When no copy is installed, the block points to the pele.run
playground instead. A command gets the guidance when an argument equal to ``pele``
(or ``pele@<version>``) follows ``npx``, or follows ``exec`` or ``x`` after ``npm``.
The match is loose on purpose: a stray match shows a harmless hint, while a missed
flag fails silently. Every other command gets no output:

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
    ALL_NPM_PROGRAM_NAMES,
    ALL_NPX_PROGRAM_NAMES,
    ALL_PELE_ENTRY_PATH_PARTS,
    COMMAND_INPUT_KEY,
    INSTALLED_GUIDANCE_TEMPLATE,
    NODE_MODULES_DIRECTORY_NAME,
    OPTION_VALUE_SEPARATOR,
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


def installed_pele_version(manifest: dict) -> str | None:
    """Read the version from a parsed Pele package manifest.

    Args:
        manifest: The parsed Pele ``package.json``.

    Returns:
        The version string, or None when the manifest holds none.
    """
    version = manifest.get("version")
    return version if isinstance(version, str) and version else None


def installed_pele_manifest(package_directory: Path) -> dict:
    """Read the Pele package manifest as a dict.

    Args:
        package_directory: The folder that holds Pele's ``package.json``.

    Returns:
        The parsed manifest, or an empty dict when it is missing, unreadable, or not an object.
    """
    try:
        manifest = json.loads((package_directory / PACKAGE_MANIFEST_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return manifest if isinstance(manifest, dict) else {}


def is_npx_pele_command(tool_input: object) -> bool:
    """Return True when the shell command runs Pele through npx.

    Args:
        tool_input: The Bash or PowerShell ``tool_input``.

    Returns:
        True when a command segment runs ``npx`` with a ``pele`` argument
        anywhere after it, or ``npm`` with a ``pele`` argument after ``exec``
        or ``x``. The shared shell parser reads wrapper words, quotes,
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
    if program_name in ALL_NPX_PROGRAM_NAMES:
        return _has_pele_argument(all_arguments)
    if program_name not in ALL_NPM_PROGRAM_NAMES:
        return False
    exec_index = next(
        (
            each_index
            for each_index, each_argument in enumerate(all_arguments)
            if unquoted_token(each_argument) in ALL_NPM_EXEC_SUBCOMMANDS
        ),
        None,
    )
    return exec_index is not None and _has_pele_argument(all_arguments[exec_index + 1 :])


def _has_pele_argument(all_arguments: list[str]) -> bool:
    return any(
        _is_pele_package(each_word)
        for each_argument in all_arguments
        for each_word in unquoted_token(each_argument).split()
    )


def _is_pele_package(argument: str) -> bool:
    package_spec = unquoted_token(argument).rsplit(OPTION_VALUE_SEPARATOR, 1)[-1]
    package_name = package_spec.split(PACKAGE_VERSION_SEPARATOR, 1)[0]
    return package_name == PELE_PACKAGE_NAME


def installed_pele_entry(package_directory: Path, manifest: dict) -> Path:
    """Return the entry file the installed Pele manifest names.

    Args:
        package_directory: The folder that holds Pele's ``package.json``.
        manifest: The parsed Pele ``package.json``.

    Returns:
        The file at the manifest's ``main`` path, or ``dist/pele.js`` when the
        manifest names no usable ``main``.
    """
    main_path = manifest.get("main")
    if isinstance(main_path, str) and main_path:
        return package_directory / main_path
    return package_directory.joinpath(*ALL_PELE_ENTRY_PATH_PARTS)


def guidance_text() -> str:
    """Return the guidance for the Pele copy this machine has, or none.

    Returns:
        The installed-copy snippet when the Pele manifest names a version and
        its entry file exists, else the playground guidance.
    """
    package_directory = pele_package_directory_under(claude_home())
    manifest = installed_pele_manifest(package_directory)
    package_entry = installed_pele_entry(package_directory, manifest)
    version = installed_pele_version(manifest)
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
