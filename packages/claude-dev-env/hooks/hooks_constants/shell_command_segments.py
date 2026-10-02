"""Shared shell-command segment helpers for Bash PreToolUse blockers.

Tokenizes a command into simple-command segments on control operators and finds
each segment's effective leading program after env assignments and launcher
wrappers. NAS ssh enforcement and unscoped-search blocking both need this
shape, so one module owns it.

``split_into_segments`` is not quote-aware: a pipe inside ``-k "a|b"`` still
splits. Quote-aware pipeline parsing — operators as their own tokens, heredoc
bodies dropped, parenthesis groups joined — lives in
``shell_command_pipeline``.
"""

from __future__ import annotations

import re
import shlex

__all__ = [
    "ALL_LAUNCHER_WRAPPER_COMMANDS",
    "ALL_SHELL_CONTROL_OPERATOR_TOKENS",
    "ALL_GIT_GLOBAL_OPTIONS_WITH_VALUE",
    "ALL_POWERSHELL_PROGRAM_NAMES",
    "ALL_POWERSHELL_COMMAND_FLAGS",
    "CONTROL_OPERATOR_SPLIT_PATTERN",
    "LEADING_ASSIGNMENT_PATTERN",
    "LAUNCHER_DURATION_PATTERN",
    "token_basename",
    "split_into_segments",
    "effective_leading_program",
    "command_tokens",
    "segment_program_and_arguments",
    "git_subcommand_tokens",
    "all_wrapped_command_texts",
]

ALL_LAUNCHER_WRAPPER_COMMANDS: frozenset[str] = frozenset(
    {"timeout", "nohup", "nice", "stdbuf", "setsid", "env", "time"}
)
ALL_GIT_GLOBAL_OPTIONS_WITH_VALUE: frozenset[str] = frozenset(
    {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
)
ALL_POWERSHELL_PROGRAM_NAMES: frozenset[str] = frozenset(
    {"pwsh", "pwsh.exe", "powershell", "powershell.exe"}
)
ALL_POWERSHELL_COMMAND_FLAGS: frozenset[str] = frozenset({"-command", "-c"})
ALL_SHELL_CONTROL_OPERATOR_TOKENS: frozenset[str] = frozenset(
    {"&&", "||", ";", "|", "&", "|&"}
)
CONTROL_OPERATOR_SPLIT_PATTERN = re.compile(r"(&&|\|\||;|\|&|\||(?<!>)&(?!>))")
LEADING_ASSIGNMENT_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
LAUNCHER_DURATION_PATTERN = re.compile(r"^\d+[a-z]*$", re.IGNORECASE)


def token_basename(token: str) -> str:
    """Return the lowercased basename of a path-or-command token."""
    return token.replace("\\", "/").rsplit("/", 1)[-1].lower()


def split_into_segments(all_command_tokens: list[str]) -> list[list[str]]:
    """Split tokens into simple-command segments on shell control operators.

    Glued operators on a single token are exploded first, then the stream is
    cut on ``&&`` / ``||`` / ``;`` / ``|`` / ``&`` / ``|&``.
    """
    all_exploded_tokens: list[str] = []
    for each_token in all_command_tokens:
        for each_fragment in CONTROL_OPERATOR_SPLIT_PATTERN.split(each_token):
            if each_fragment:
                all_exploded_tokens.append(each_fragment)
    all_segments: list[list[str]] = []
    current_segment: list[str] = []
    for each_token in all_exploded_tokens:
        if each_token in ALL_SHELL_CONTROL_OPERATOR_TOKENS:
            all_segments.append(current_segment)
            current_segment = []
            continue
        current_segment.append(each_token)
    all_segments.append(current_segment)
    return all_segments


def effective_leading_program(all_segment_tokens: list[str]) -> str | None:
    """Return the effective program token after assignments and launcher wrappers.

    Skips ``VAR=value`` prefixes and known launchers (``timeout``, ``env``, …)
    plus their flags and duration arguments. Returns None when no program token
    remains.
    """
    has_seen_launcher_wrapper = False
    for each_token in all_segment_tokens:
        if LEADING_ASSIGNMENT_PATTERN.match(each_token):
            continue
        if token_basename(each_token) in ALL_LAUNCHER_WRAPPER_COMMANDS:
            has_seen_launcher_wrapper = True
            continue
        if has_seen_launcher_wrapper and (
            each_token.startswith("-") or LAUNCHER_DURATION_PATTERN.match(each_token)
        ):
            continue
        return each_token
    return None


def command_tokens(command: str) -> list[str]:
    """Return the POSIX shlex tokens of a command, or its whitespace split when quoting is unbalanced."""
    try:
        return shlex.split(command, posix=True)
    except ValueError:
        return command.split()


def segment_program_and_arguments(all_segment_tokens: list[str]) -> tuple[str, list[str]]:
    """Return a segment's program basename and the tokens after it, or an empty pair."""
    program_token = effective_leading_program(all_segment_tokens)
    if program_token is None:
        return "", []
    program_index = all_segment_tokens.index(program_token)
    return token_basename(program_token), all_segment_tokens[program_index + 1 :]


def git_subcommand_tokens(all_arguments: list[str]) -> list[str]:
    """Return git's subcommand and the tokens after it, past git's global options.

    ``git -C <path> push`` and ``git --git-dir <path> push`` carry an option
    value before the subcommand; ``--git-dir=<path>`` and ``--no-pager`` carry
    none. The first token left after those starts the result, so
    ``git stash push`` yields ``["stash", "push"]`` and ``git log --grep push``
    yields ``["log", "--grep", "push"]``. A command with no subcommand yields
    an empty list.
    """
    should_skip_next_token = False
    for each_index, each_argument in enumerate(all_arguments):
        if should_skip_next_token:
            should_skip_next_token = False
            continue
        if each_argument in ALL_GIT_GLOBAL_OPTIONS_WITH_VALUE:
            should_skip_next_token = True
            continue
        if each_argument.startswith("-"):
            continue
        return all_arguments[each_index:]
    return []


def all_wrapped_command_texts(command: str) -> list[str]:
    """Return the command plus the script every ``pwsh -Command "..."`` wrapper runs.

    Read from the raw shlex tokens, before segment splitting: the quoted
    script is one token here, and splitting it on ``;`` first would cut a
    ``git add -A; git push`` script in half. Nested wrappers unwrap in turn.
    """
    all_command_texts = [command]
    all_tokens = command_tokens(command)
    has_seen_powershell_program = False
    for each_token_index, each_token in enumerate(all_tokens[:-1]):
        if token_basename(each_token) in ALL_POWERSHELL_PROGRAM_NAMES:
            has_seen_powershell_program = True
            continue
        if has_seen_powershell_program and each_token.lower() in ALL_POWERSHELL_COMMAND_FLAGS:
            all_command_texts.extend(all_wrapped_command_texts(all_tokens[each_token_index + 1]))
            has_seen_powershell_program = False
    return all_command_texts
