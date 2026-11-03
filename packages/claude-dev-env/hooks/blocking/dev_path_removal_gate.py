#!/usr/bin/env python3
"""PreToolUse gate: stop a Bash command that removes or replaces a file under /dev.

``rm``, ``unlink``, ``mv``, ``shred`` and ``truncate`` change the files they
name, and so does a destination attached to an option, such as
``mv --target-directory=/dev``. Under ``/dev`` those files are device nodes
such as ``/dev/null``, which other commands depend on. Each command segment is
read after its wrappers, so ``sudo rm -f /dev/null`` is denied. A redirect
target is not a command operand, so ``rm notes.txt > /dev/null`` passes, and so
does ``echo x > /dev/null``.

Hosted by ``blocking/bash_pre_tool_use_dispatcher.py`` for the Bash tool.
"""

from __future__ import annotations

import json
import posixpath
import sys
from pathlib import Path

try:
    _hooks_root_directory = str(Path(__file__).resolve().parent.parent)
    if _hooks_root_directory not in sys.path:
        sys.path.insert(0, _hooks_root_directory)
    from hooks_constants.bash_pre_tool_use_dispatcher_constants import (
        BASH_TOOL_NAME,
        DENY_DECISION,
        HOOK_EVENT_NAME,
    )
    from hooks_constants.dev_path_removal_gate_constants import (
        ALL_DEV_PATH_REMOVAL_PROGRAM_NAMES,
        DEV_DIRECTORY,
        DEV_DIRECTORY_PREFIX,
        DEV_PATH_REMOVAL_DENY_REASON,
        GATE_HOOK_NAME,
        LEADING_SLASH,
        LEADING_SLASHES_PATTERN,
        REDIRECTION_OPERATOR_PATTERN,
        SHORT_TARGET_DIRECTORY_OPTION_PATTERN,
        TARGET_DIRECTORY_LONG_OPTION_PREFIX,
    )
    from hooks_constants.hook_block_logger import log_hook_block
    from hooks_constants.hook_specific_output_keys import (
        HOOK_SPECIFIC_OUTPUT_KEY,
        HOOK_EVENT_NAME_KEY,
        PERMISSION_DECISION_KEY,
        PERMISSION_DECISION_REASON_KEY,
    )
    from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
    from hooks_constants.shell_command_wrappers import (
        all_wrapped_command_segments,
        segment_program_and_arguments,
    )
except ImportError as import_error:
    raise ImportError(
        "The dev path removal gate cannot import its dependencies; "
        "ensure the hooks directory is importable."
    ) from import_error


def _normalized_path(path_operand: str) -> str:
    """Return the path with leading double slashes folded and ``.`` or ``..`` parts resolved.

    ::

        "//dev//null"       -> "/dev/null"
        "/tmp/../dev/null"  -> "/dev/null"

    Args:
        path_operand: One command operand, already unquoted by the shell parser.

    Returns:
        The lexically normalized path text.
    """
    single_leading_slash = LEADING_SLASHES_PATTERN.sub(LEADING_SLASH, path_operand)
    return posixpath.normpath(single_leading_slash)


def is_dev_path(path_operand: str) -> bool:
    """Return True when the operand names ``/dev`` or a path under it.

    ::

        is_dev_path("/dev/null")         -> True
        is_dev_path("/tmp/../dev/null")  -> True
        is_dev_path("/devices/null")     -> False

    Args:
        path_operand: One command operand.

    Returns:
        True when the normalized path is ``/dev`` or starts with ``/dev/``.
    """
    normalized_path = _normalized_path(path_operand)
    return normalized_path == DEV_DIRECTORY or normalized_path.startswith(
        DEV_DIRECTORY_PREFIX
    )


def _attached_target_directory(argument: str) -> str | None:
    """Return the destination carried by a ``-t`` or ``--target-directory=`` token, or None.

    ::

        "--target-directory=/dev"  -> "/dev"
        "-t/dev"                   -> "/dev"
        "-ft/dev"                  -> "/dev"
        "-t"                       -> None

    Args:
        argument: One command token.

    Returns:
        The destination attached to the option, or None when the token attaches none.
    """
    if argument.startswith(TARGET_DIRECTORY_LONG_OPTION_PREFIX):
        return argument.removeprefix(TARGET_DIRECTORY_LONG_OPTION_PREFIX)
    short_option_match = SHORT_TARGET_DIRECTORY_OPTION_PATTERN.fullmatch(argument)
    if short_option_match is None:
        return None
    return short_option_match.group(1)


def _command_operands(all_arguments: list[str]) -> list[str]:
    """Return the arguments that are operands, leaving out each redirection and its target.

    A destination attached to an option, such as ``-t/dev``, is also returned as
    an operand of its own.

    ::

        ["foo", ">", "/dev/null"]    -> ["foo"]
        ["foo", "2", ">&", "1"]      -> ["foo", "2"]
        ["-t/dev"]                   -> ["-t/dev", "/dev"]

    Args:
        all_arguments: The tokens after the program name.

    Returns:
        The operand tokens in their original order.
    """
    all_operands: list[str] = []
    is_next_argument_redirection_target = False
    for each_argument in all_arguments:
        if is_next_argument_redirection_target:
            is_next_argument_redirection_target = False
            continue
        if REDIRECTION_OPERATOR_PATTERN.fullmatch(each_argument):
            is_next_argument_redirection_target = True
            continue
        all_operands.append(each_argument)
        attached_target_directory = _attached_target_directory(each_argument)
        if attached_target_directory is not None:
            all_operands.append(attached_target_directory)
    return all_operands


def segment_removes_dev_path(all_segment_tokens: list[str]) -> bool:
    """Return True when one command segment removes or replaces a path under ``/dev``.

    ::

        ["rm", "-f", "/dev/null"]           -> True
        ["rm", "notes.txt", ">", "/dev/null"] -> False
        ["cat", "/dev/null"]                -> False

    Args:
        all_segment_tokens: The tokens of one command segment.

    Returns:
        True when the segment's program is a removal or replacement command and
        one of its operands is a path under ``/dev``.
    """
    program_name, all_arguments = segment_program_and_arguments(all_segment_tokens)
    if program_name not in ALL_DEV_PATH_REMOVAL_PROGRAM_NAMES:
        return False
    return any(
        is_dev_path(each_operand) for each_operand in _command_operands(all_arguments)
    )


def runs_dev_path_removal(command: str) -> bool:
    """Return True when a segment of the command, or of a wrapped command, removes a path under ``/dev``.

    ::

        "rm -f /dev/null"            -> True
        "cat notes | head"           -> False
        "echo x > /dev/null"         -> False

    Args:
        command: The shell command text the agent is about to run.

    Returns:
        True when at least one command segment removes or replaces a path under ``/dev``.
    """
    return any(
        segment_removes_dev_path(each_segment)
        for each_segment in all_wrapped_command_segments(command)
    )


def _write_deny_decision(reason: str) -> None:
    sys.stdout.write(
        json.dumps(
            {
                HOOK_SPECIFIC_OUTPUT_KEY: {
                    HOOK_EVENT_NAME_KEY: HOOK_EVENT_NAME,
                    PERMISSION_DECISION_KEY: DENY_DECISION,
                    PERMISSION_DECISION_REASON_KEY: reason,
                }
            }
        )
    )
    sys.stdout.flush()


def main() -> None:
    """Deny a Bash command that removes or replaces a path under /dev, or stay quiet."""
    hook_payload = read_hook_input_dictionary_from_stdin()
    if hook_payload is None:
        return
    if hook_payload.get("tool_name") != BASH_TOOL_NAME:
        return
    tool_input = hook_payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return
    command = tool_input.get("command", "")
    if not isinstance(command, str):
        return
    if not runs_dev_path_removal(command):
        return
    log_hook_block(
        GATE_HOOK_NAME,
        HOOK_EVENT_NAME,
        DEV_PATH_REMOVAL_DENY_REASON,
        BASH_TOOL_NAME,
        command,
    )
    _write_deny_decision(DEV_PATH_REMOVAL_DENY_REASON)


if __name__ == "__main__":
    main()
