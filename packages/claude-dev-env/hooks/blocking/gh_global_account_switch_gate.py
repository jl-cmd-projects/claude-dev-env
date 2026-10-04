#!/usr/bin/env python3
"""PreToolUse gate: keep agents from changing the global GitHub CLI account.

``gh auth switch``, ``gh auth login``, and ``gh auth logout`` write the shared
gh configuration, so they change the active account for every session on the
machine. A command segment whose program is ``gh`` and whose arguments start
with one of those subcommands is denied, and the deny reason names the
per-command ``GH_TOKEN`` form to run instead. The program is read past wrappers
and chained commands, so ``cd x && gh auth switch`` and ``bash -c "gh auth
logout"`` are denied too. ``gh auth status``, ``gh auth token``, and quoted text
that only mentions the words pass.

Hosted by ``blocking/bash_pre_tool_use_dispatcher.py`` for the Bash and
PowerShell tools.
"""

from __future__ import annotations

import json
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
    from hooks_constants.gh_global_account_switch_gate_constants import (
        ALL_GLOBAL_ACCOUNT_CHANGING_COMMAND_PATHS,
        GATE_HOOK_NAME,
        GH_COMMAND_PATH_LENGTH,
        GH_PROGRAM_NAME,
        GLOBAL_ACCOUNT_CHANGE_DENY_REASON,
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
        "The gh global account switch gate cannot import its dependencies; "
        "ensure the hooks directory is importable."
    ) from import_error


def _changes_global_gh_account(all_segment_tokens: list[str]) -> bool:
    """Return True when a segment runs gh auth switch, login, or logout.

    Args:
        all_segment_tokens: One command segment's shell tokens.
    """
    program_name, all_arguments = segment_program_and_arguments(all_segment_tokens)
    command_path = tuple(all_arguments[:GH_COMMAND_PATH_LENGTH])
    return program_name.lower() == GH_PROGRAM_NAME and command_path in ALL_GLOBAL_ACCOUNT_CHANGING_COMMAND_PATHS


def changes_global_gh_account(command: str) -> bool:
    """Return True when any command segment changes the machine-wide gh account.

    ::

        gh auth switch -u <account>                          -> True
        git fetch && gh auth login                           -> True
        GH_TOKEN=$(gh auth token -u <account>) gh repo list  -> False
        git commit -m "never run gh auth switch"             -> False

    Args:
        command: The shell command text the agent is about to run.
    """
    return any(
        _changes_global_gh_account(each_segment)
        for each_text in all_wrapped_command_texts(command)
        for each_segment, _each_following_operator in pipeline_segments_for_command(each_text)
    )


def main() -> None:
    """Deny a command that changes the global gh account, or stay quiet."""
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
    if not isinstance(command, str) or not changes_global_gh_account(command):
        return
    log_hook_block(
        GATE_HOOK_NAME, HOOK_EVENT_NAME, GLOBAL_ACCOUNT_CHANGE_DENY_REASON, str(tool_name), command
    )
    sys.stdout.write(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": HOOK_EVENT_NAME,
                    "permissionDecision": DENY_DECISION,
                    "permissionDecisionReason": GLOBAL_ACCOUNT_CHANGE_DENY_REASON,
                }
            }
        )
    )
    sys.stdout.flush()


if __name__ == "__main__":
    main()
