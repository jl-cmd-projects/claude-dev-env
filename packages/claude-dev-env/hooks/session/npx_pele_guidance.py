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
    ALL_PELE_ENTRY_PATH_PARTS,
    COMMAND_INPUT_KEY,
    INSTALLED_GUIDANCE_TEMPLATE,
    NODE_MODULES_DIRECTORY_NAME,
    NPX_PELE_COMMAND_PATTERN,
    PACKAGE_MANIFEST_NAME,
    PELE_PACKAGE_NAME,
    PELE_TOOLS_DIRECTORY_NAME,
)
from hooks_constants.pre_tool_use_context_runner import run_context_hook
from hooks_constants.spawn_readiness_hook_constants import (
    ADDITIONAL_CONTEXT_KEY,
    PRE_TOOL_USE_EVENT_NAME,
    TOOL_INPUT_KEY,
)
from open_task_asks import claude_home


def pele_package_directory() -> Path:
    """Return the folder a Claude install keeps its Pele package in.

    Returns:
        ``<claude home>/tools/pele/node_modules/pele``, where the claude-dev-env
        installer places Pele.
    """
    return (
        claude_home()
        / PELE_TOOLS_DIRECTORY_NAME
        / PELE_PACKAGE_NAME
        / NODE_MODULES_DIRECTORY_NAME
        / PELE_PACKAGE_NAME
    )


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
    return version if isinstance(version, str) else None


def is_npx_pele_command(tool_input: object) -> bool:
    """Return True when the shell command runs Pele through npx.

    Args:
        tool_input: The Bash or PowerShell ``tool_input``.

    Returns:
        True when a command segment runs ``npx pele``, ``npx -y pele``,
        ``npm exec pele``, or a versioned form of those. Leading environment
        assignments and the words sudo, time, env, and nohup may precede them.
    """
    if not isinstance(tool_input, dict):
        return False
    command_text = tool_input.get(COMMAND_INPUT_KEY)
    if not isinstance(command_text, str):
        return False
    return NPX_PELE_COMMAND_PATTERN.search(command_text) is not None


def guidance_text() -> str:
    """Return the guidance for the Pele copy this machine has, or none.

    Returns:
        The installed-copy snippet when a Pele manifest reads, else the
        playground guidance.
    """
    package_directory = pele_package_directory()
    version = installed_pele_version(package_directory)
    if version is None:
        return ABSENT_GUIDANCE_TEMPLATE.format(package_directory=package_directory)
    package_entry = package_directory.joinpath(*ALL_PELE_ENTRY_PATH_PARTS)
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
