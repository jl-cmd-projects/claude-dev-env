#!/usr/bin/env python3
"""PreToolUse gate: stop two Python invocations that fail on Windows.

``python -I`` turns on isolated mode, which ignores every ``PYTHON*``
environment variable, ``PYTHONUTF8`` included. On Windows the interpreter then
writes with the console code page, and non-ASCII output stops with
``UnicodeEncodeError: 'charmap'``. On a Windows host a command segment is
denied when it runs ``python``, ``python3`` or ``py`` with ``-I`` and without
``-X utf8``. The option scan reads clusters, so ``-IX utf8``, ``-IXutf8`` and
``-I -X utf8`` all pass. It stops at the script name, ``-c`` or ``-m``, so an
``-I`` meant for the script passes. Linux runs ``-I`` in UTF-8 already, so the
check stays quiet there.

Under the PowerShell tool a command is also denied when a ``python -c "..."``
argument holds ``\\"``. PowerShell reads the backslash as a plain character and
ends the string at that quote. The deny reason names a script file or a
single-quoted here-string. Bash reads ``\\"`` as an escaped quote, so the Bash
tool passes it.

Hosted by ``blocking/bash_pre_tool_use_dispatcher.py`` for the Bash and
PowerShell tools.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterator
from pathlib import Path

try:
    _hooks_root_directory = str(Path(__file__).resolve().parent.parent)
    if _hooks_root_directory not in sys.path:
        sys.path.insert(0, _hooks_root_directory)
    from hooks_constants.bash_pre_tool_use_dispatcher_constants import (
        ALL_BASH_AND_POWERSHELL_TOOL_NAMES,
        DENY_DECISION,
        HOOK_EVENT_NAME,
        POWERSHELL_TOOL_NAME,
        REASON_JOIN_SEPARATOR,
    )
    from hooks_constants.hook_block_logger import log_hook_block
    from hooks_constants.piped_pytest_blocker_constants import (
        PYTHON_INTERPRETER_BASENAME_PATTERN,
    )
    from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
    from hooks_constants.python_windows_invocation_gate_constants import (
        ALL_COMMAND_ENDING_OPTION_LETTERS,
        ALL_UTF8_MODE_OPTION_VALUES,
        ALL_VALUE_LONG_OPTIONS,
        ALL_VALUE_OPTION_LETTERS,
        END_OF_OPTIONS_MARKER,
        GATE_HOOK_NAME,
        IMPLEMENTATION_OPTION_LETTER,
        ISOLATED_MODE_OPTION_LETTER,
        ISOLATED_PYTHON_DENY_REASON,
        OPTION_PREFIX,
        POWERSHELL_BACKSLASH_QUOTE_DENY_REASON,
        PYTHON_CODE_ARGUMENT_BACKSLASH_QUOTE_PATTERN,
        WINDOWS_OS_NAME,
    )
    from hooks_constants.shell_command_wrappers import (
        all_wrapped_command_segments,
        segment_program_and_arguments,
    )
except ImportError as import_error:
    raise ImportError(
        "The Python Windows invocation gate cannot import its dependencies; "
        "ensure the hooks directory is importable."
    ) from import_error


def is_windows_host() -> bool:
    """Return True when the hook runs on Windows, where the shell commands run too."""
    return os.name == WINDOWS_OS_NAME


def _is_short_option_cluster(argument: str) -> bool:
    return (
        argument.startswith(OPTION_PREFIX)
        and not argument.startswith(END_OF_OPTIONS_MARKER)
        and argument != OPTION_PREFIX
    )


def _is_long_option(argument: str) -> bool:
    return argument.startswith(END_OF_OPTIONS_MARKER) and argument != END_OF_OPTIONS_MARKER


def _skip_long_option_value(argument: str, remaining_arguments: Iterator[str]) -> None:
    if argument in ALL_VALUE_LONG_OPTIONS:
        next(remaining_arguments, "")


def _cluster_options(
    cluster_letters: str, remaining_arguments: Iterator[str]
) -> list[tuple[str, str]]:
    """Return each option letter in one short-option cluster with its value.

    A letter that takes a value uses the rest of the cluster, or the next
    argument when the rest is empty, so ``-IXutf8`` and ``-IX utf8`` both read
    as ``I`` and ``X`` with the value ``utf8``.
    """
    all_options: list[tuple[str, str]] = []
    for each_index, each_letter in enumerate(cluster_letters):
        if each_letter not in ALL_VALUE_OPTION_LETTERS:
            all_options.append((each_letter, ""))
            continue
        inline_value = cluster_letters[each_index + 1 :]
        all_options.append((each_letter, inline_value or next(remaining_arguments, "")))
        return all_options
    return all_options


def _interpreter_options(all_arguments: list[str]) -> list[tuple[str, str]]:
    """Return the interpreter option letters and values ahead of the script, ``-c`` or ``-m``.

    Args:
        all_arguments: The tokens after the interpreter program name.
    """
    all_options: list[tuple[str, str]] = []
    remaining_arguments = iter(all_arguments)
    for each_argument in remaining_arguments:
        if _is_long_option(each_argument):
            _skip_long_option_value(each_argument, remaining_arguments)
            continue
        if not _is_short_option_cluster(each_argument):
            break
        all_options.extend(
            _cluster_options(each_argument[len(OPTION_PREFIX) :], remaining_arguments)
        )
        if all_options[-1][0] in ALL_COMMAND_ENDING_OPTION_LETTERS:
            break
    return all_options


def _isolated_without_utf8_mode(all_arguments: list[str]) -> bool:
    """Return True when the interpreter options set ``-I`` and leave out ``-X utf8``.

    Args:
        all_arguments: The tokens after the interpreter program name.
    """
    all_options = _interpreter_options(all_arguments)
    is_isolated = any(
        each_letter == ISOLATED_MODE_OPTION_LETTER for each_letter, _ in all_options
    )
    has_utf8_mode = any(
        each_letter == IMPLEMENTATION_OPTION_LETTER
        and each_value in ALL_UTF8_MODE_OPTION_VALUES
        for each_letter, each_value in all_options
    )
    return is_isolated and not has_utf8_mode


def runs_isolated_python_without_utf8_mode(command: str) -> bool:
    """Return True when any command segment runs Python with ``-I`` and without ``-X utf8``.

    ::

        python -I script.py             -> True
        py -3 -I -c pass                -> True
        python -IX utf8 script.py       -> False
        python -I -X utf8 script.py     -> False
        python script.py -I             -> False

    Args:
        command: The shell command text the agent is about to run.
    """
    for each_segment in all_wrapped_command_segments(command):
        program_name, all_arguments = segment_program_and_arguments(each_segment)
        if PYTHON_INTERPRETER_BASENAME_PATTERN.fullmatch(program_name.lower()) is None:
            continue
        if _isolated_without_utf8_mode(all_arguments):
            return True
    return False


def has_backslash_quote_in_python_code_argument(command: str) -> bool:
    """Return True when a ``python -c "..."`` argument holds ``\\"`` in the raw command text.

    ::

        python -c "print(\\"x\\")"     -> True
        python -c 'print("x")'        -> False

    Args:
        command: The shell command text the agent is about to run.
    """
    return PYTHON_CODE_ARGUMENT_BACKSLASH_QUOTE_PATTERN.search(command) is not None


def all_deny_reasons(command: str, tool_name: str) -> list[str]:
    """Return the deny reason for each Windows Python failure the command would hit.

    Args:
        command: The shell command text the agent is about to run.
        tool_name: The tool that runs the command, Bash or PowerShell.
    """
    all_reasons: list[str] = []
    if is_windows_host() and runs_isolated_python_without_utf8_mode(command):
        all_reasons.append(ISOLATED_PYTHON_DENY_REASON)
    if (
        tool_name == POWERSHELL_TOOL_NAME
        and has_backslash_quote_in_python_code_argument(command)
    ):
        all_reasons.append(POWERSHELL_BACKSLASH_QUOTE_DENY_REASON)
    return all_reasons


def _write_deny_decision(reason: str) -> None:
    sys.stdout.write(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": HOOK_EVENT_NAME,
                    "permissionDecision": DENY_DECISION,
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    sys.stdout.flush()


def main() -> None:
    """Deny a Python invocation that fails on Windows, or stay quiet."""
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
    if not isinstance(command, str):
        return
    all_reasons = all_deny_reasons(command, str(tool_name))
    if not all_reasons:
        return
    reason = REASON_JOIN_SEPARATOR.join(all_reasons)
    log_hook_block(GATE_HOOK_NAME, HOOK_EVENT_NAME, reason, str(tool_name), command)
    _write_deny_decision(reason)


if __name__ == "__main__":
    main()
