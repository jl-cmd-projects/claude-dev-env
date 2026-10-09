#!/usr/bin/env python3
"""PreToolUse gate: start every headless Claude session through the account broker.

A command segment whose program is ``claude`` or a ``claude-<profile>``
launcher and that passes ``-p`` or ``--print`` is denied, and the deny reason
names the broker command to run instead. The program is read past wrappers,
so ``env -u NAME claude -p`` and ``bash -c "claude -p task"`` are denied too.
The broker form runs ``python``, so its ``-- claude -p ...`` tail passes.
Interactive ``claude`` and its subcommands, such as ``claude plugin eval`` or
``claude --version``, pass.

A Claude Code cloud session, where ``CLAUDE_CODE_REMOTE`` is ``true``, has one
account, so the gate passes every command there.

Hosted by ``blocking/bash_pre_tool_use_dispatcher.py`` for the Bash and
PowerShell tools.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

try:
    _hooks_root_directory = str(Path(__file__).resolve().parent.parent)
    if _hooks_root_directory not in sys.path:
        sys.path.insert(0, _hooks_root_directory)
    from hooks_constants.bash_pre_tool_use_dispatcher_constants import (
        ALL_BASH_AND_POWERSHELL_TOOL_NAMES,
        DENY_DECISION,
        HOOK_EVENT_NAME,
    )
    from hooks_constants.headless_claude_broker_gate_constants import (
        ALL_PRINT_MODE_FLAGS,
        ALL_WINDOWS_LAUNCHER_SUFFIXES,
        BROKER_COMMAND_DENY_REASON,
        CLAUDE_PROFILE_LAUNCHER_PREFIX,
        CLAUDE_PROGRAM_NAME,
        CLOUD_SESSION_ENV_TRUE_VALUE,
        CLOUD_SESSION_ENV_VAR,
        GATE_HOOK_NAME,
        PRINT_MODE_LONG_FLAG_WITH_VALUE_PREFIX,
    )
    from hooks_constants.hook_block_logger import log_hook_block
    from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
    from hooks_constants.shell_command_pipeline import pipeline_segments_for_command
    from hooks_constants.shell_command_wrappers import (
        all_wrapped_command_texts,
        segment_program_and_arguments,
    )
except ImportError as import_error:
    raise ImportError(
        "The headless Claude broker gate cannot import its dependencies; "
        "ensure the hooks directory is importable."
    ) from import_error


def _is_claude_program(program_name: str) -> bool:
    """Return True when the program name launches Claude Code or a Claude profile launcher.

    ::

        claude                   -> True
        claude-ev.cmd            -> True
        claude_account_worker.py -> False

    Args:
        program_name: A segment's program basename, read past its wrappers.
    """
    launcher_name = program_name
    for each_suffix in ALL_WINDOWS_LAUNCHER_SUFFIXES:
        launcher_name = launcher_name.removesuffix(each_suffix)
    if launcher_name == CLAUDE_PROGRAM_NAME:
        return True
    profile_name = launcher_name.removeprefix(CLAUDE_PROFILE_LAUNCHER_PREFIX)
    return profile_name != launcher_name and profile_name.replace("_", "").replace("-", "").isalnum()


def _is_print_mode_flag(argument: str) -> bool:
    """Return True when one argument turns on Claude's print mode.

    Args:
        argument: One argument after the segment's program.
    """
    return argument in ALL_PRINT_MODE_FLAGS or argument.startswith(PRINT_MODE_LONG_FLAG_WITH_VALUE_PREFIX)


def _runs_headless_claude(all_segment_tokens: list[str]) -> bool:
    """Return True when a segment's program is a Claude launcher in print mode.

    Args:
        all_segment_tokens: One command segment's shell tokens.
    """
    program_name, all_arguments = segment_program_and_arguments(all_segment_tokens)
    return _is_claude_program(program_name) and any(
        _is_print_mode_flag(each_argument) for each_argument in all_arguments
    )


def starts_unbrokered_headless_claude(command: str) -> bool:
    """Return True when a command segment starts headless Claude without the broker.

    ::

        claude -p "task"                                         -> True
        cd repo && env -u CLAUDECODE claude-ev -p "task"         -> True
        python account_broker.py run ... -- claude -p "task"     -> False
        git -C claude-dev-env log -p                             -> False

    Args:
        command: The shell command text the agent is about to run.
    """
    return any(
        _runs_headless_claude(each_segment)
        for each_text in all_wrapped_command_texts(command)
        for each_segment, _each_following_operator in pipeline_segments_for_command(each_text)
    )


def is_cloud_session() -> bool:
    """Return True when this hook runs inside a Claude Code cloud session."""
    return os.environ.get(CLOUD_SESSION_ENV_VAR, "").strip().lower() == CLOUD_SESSION_ENV_TRUE_VALUE


def main() -> None:
    """Deny a headless Claude start that skips the broker outside a cloud session, or stay quiet."""
    if is_cloud_session():
        return
    hook_payload = read_hook_input_dictionary_from_stdin()
    if hook_payload is None:
        return
    tool_name = hook_payload.get("tool_name")
    if tool_name not in ALL_BASH_AND_POWERSHELL_TOOL_NAMES:
        return
    tool_input = hook_payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return
    command = tool_input.get("command", "")
    if not isinstance(command, str) or not starts_unbrokered_headless_claude(command):
        return
    log_hook_block(GATE_HOOK_NAME, HOOK_EVENT_NAME, BROKER_COMMAND_DENY_REASON, str(tool_name), command)
    sys.stdout.write(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": HOOK_EVENT_NAME,
            "permissionDecision": DENY_DECISION,
            "permissionDecisionReason": BROKER_COMMAND_DENY_REASON,
        }
    }))
    sys.stdout.flush()


if __name__ == "__main__":
    main()
