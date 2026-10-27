#!/usr/bin/env python3
"""Shell command search starts for the transcript root search gate.

Reads where each program in a Bash or PowerShell command starts reading and
whether it recurses. ``find``, ``grep``, ``rg``, ``ag``, ``ack``, ``fd``,
``ls``, ``tree``, ``Get-ChildItem`` and ``Select-String`` follow their own
option grammar; any other program reads its plain arguments without
recursion, so ``cat <root>/*/*.jsonl`` still counts as a walk.

Each tokenization of the command runs in order with its own state: variables
expand from the assignments before them, PowerShell names without regard to
case, and a relative path resolves from the session directory or the last
``cd`` or ``Set-Location`` before it, and ``popd`` or ``Pop-Location``
returns to the folder before the matching ``pushd`` or ``Push-Location``. A
search with no path starts there.
"""

from __future__ import annotations

import collections
import re
import sys
from collections.abc import Callable
from functools import partial
from pathlib import Path

try:
    _hooks_root_directory = str(Path(__file__).resolve().parent.parent)
    if _hooks_root_directory not in sys.path:
        sys.path.insert(0, _hooks_root_directory)
    from blocking.transcript_root_powershell_starts import (
        powershell_listing_search_starts,
        select_string_search_starts,
    )
    from blocking.transcript_root_search_starts import (
        OptionValue,
        SearchStart,
        is_option,
        is_recursive_unless_shallow,
        joined_path,
        next_value,
        starts_or_current_directory,
    )
    from hooks_constants import transcript_root_search_gate_constants as search_rules
    from hooks_constants import unscoped_search_blocker_constants as walk_flags
    from hooks_constants.destructive_command_segment_constants import FIND_PROGRAM_NAME
    from hooks_constants.pytest_invocation import unquoted_token
    from hooks_constants.shell_command_pipeline import (
        all_operator_aware_tokenizations,
        join_line_continuations,
        scannable_command_lines,
        segments_with_following_operator,
    )
    from hooks_constants.shell_command_wrappers import (
        all_wrapped_command_texts,
        segment_program_and_arguments,
    )
except ImportError as import_error:
    raise ImportError(
        "The transcript_root_shell_starts module cannot import its dependencies; "
        "ensure the hooks directory is importable."
    ) from import_error


def _assignment_from_segment(all_segment_tokens: list[str]) -> tuple[str, str] | None:
    """Return the name and value a segment assigns, such as ``p=x`` or ``$p = "x"``, else None."""
    prefix_word_count = 0
    while (
        prefix_word_count < len(all_segment_tokens)
        and all_segment_tokens[prefix_word_count].lower()
        in search_rules.ALL_ASSIGNMENT_PREFIX_WORDS
    ):
        prefix_word_count += 1
    all_tokens = all_segment_tokens[prefix_word_count:]
    if len(all_tokens) == 1:
        assignment_match = search_rules.SHELL_ASSIGNMENT_PATTERN.match(all_tokens[0])
        if assignment_match is not None:
            return assignment_match["name"], unquoted_token(assignment_match["value"])
    if (
        len(all_tokens) == search_rules.SPACED_ASSIGNMENT_TOKEN_COUNT
        and all_tokens[1] == search_rules.SPACED_ASSIGNMENT_OPERATOR
    ):
        name_match = search_rules.SPACED_ASSIGNMENT_NAME_PATTERN.match(all_tokens[0])
        if name_match is not None:
            return name_match["name"], unquoted_token(all_tokens[2])
    return None


def _expanded_token(token: str, all_bindings: dict[str, str]) -> str:
    if search_rules.SHELL_VARIABLE_SIGIL not in token:
        return token
    expanded_token = token
    for each_name, each_value in all_bindings.items():
        reference_pattern = search_rules.SHELL_VARIABLE_REFERENCE_TEMPLATE.format(
            name=re.escape(each_name)
        )
        expanded_token = re.sub(
            reference_pattern,
            each_value.replace("\\", "\\\\"),
            expanded_token,
            flags=re.IGNORECASE,
        )
    return expanded_token


def _long_option(
    grammar: search_rules.PosixSearchGrammar,
    bare_token: str,
    all_remaining: collections.deque[str],
) -> OptionValue:
    option_name, glued_separator, glued_value = bare_token.partition(
        search_rules.GLUED_OPTION_VALUE_SEPARATOR
    )
    if glued_separator:
        return option_name, unquoted_token(glued_value)
    if option_name in grammar.all_value_options:
        return option_name, next_value(all_remaining)
    return option_name, ""


def _short_option_cluster(
    grammar: search_rules.PosixSearchGrammar,
    bare_token: str,
    all_remaining: collections.deque[str],
) -> list[OptionValue]:
    """Return each option in a cluster such as ``-rC2``; a value letter takes the rest or the next token."""
    all_options: list[OptionValue] = []
    for each_index, each_letter in enumerate(bare_token[1:], start=1):
        option_name = search_rules.OPTION_PREFIX + each_letter
        if each_letter in grammar.all_value_letters:
            glued_value = bare_token[each_index + 1 :].removeprefix(
                search_rules.GLUED_OPTION_VALUE_SEPARATOR
            )
            all_options.append((option_name, glued_value or next_value(all_remaining)))
            return all_options
        all_options.append((option_name, ""))
    return all_options


def _options_in_token(
    grammar: search_rules.PosixSearchGrammar,
    bare_token: str,
    all_remaining: collections.deque[str],
) -> list[OptionValue]:
    if bare_token.startswith(search_rules.LONG_OPTION_PREFIX):
        return [_long_option(grammar, bare_token, all_remaining)]
    return _short_option_cluster(grammar, bare_token, all_remaining)


def _posix_arguments(
    grammar: search_rules.PosixSearchGrammar, all_arguments: list[str]
) -> tuple[list[str], list[OptionValue]]:
    all_positionals: list[str] = []
    all_options: list[OptionValue] = []
    all_remaining = collections.deque(all_arguments)
    while all_remaining:
        each_token = all_remaining.popleft()
        bare_token = unquoted_token(each_token)
        if bare_token == search_rules.END_OF_OPTIONS_TOKEN:
            all_positionals.extend(all_remaining)
            break
        if is_option(each_token):
            all_options.extend(_options_in_token(grammar, bare_token, all_remaining))
        else:
            all_positionals.append(each_token)
    return all_positionals, all_options


def _posix_search_starts(
    grammar: search_rules.PosixSearchGrammar, all_arguments: list[str]
) -> list[SearchStart]:
    all_positionals, all_options = _posix_arguments(grammar, all_arguments)
    all_option_names = {each_name for each_name, _each_value in all_options}
    is_recursive_by_option = (
        grammar.is_recursive_by_default
        or bool(all_option_names & grammar.all_recurse_options)
        or any(
            each_name in grammar.all_recurse_value_options
            and each_value == search_rules.RECURSE_DIRECTORIES_ACTION
            for each_name, each_value in all_options
        )
    )
    all_depth_values = [
        each_value
        for each_name, each_value in all_options
        if each_name in grammar.all_depth_options
    ]
    has_pattern_positional = grammar.takes_pattern_positional and not (
        all_option_names & grammar.all_pattern_options
    )
    return starts_or_current_directory(
        all_positionals[1:] if has_pattern_positional else all_positionals,
        is_recursive_unless_shallow(all_depth_values, is_recursive_by_option),
    )


def _find_search_starts(all_arguments: list[str]) -> list[SearchStart]:
    all_starting_points: list[str] = []
    all_remaining = collections.deque(all_arguments)
    while all_remaining:
        each_token = all_remaining.popleft()
        if each_token in walk_flags.ALL_FIND_GLOBAL_OPTION_FLAGS_TAKING_A_VALUE:
            next_value(all_remaining)
            continue
        if each_token in walk_flags.ALL_FIND_GLOBAL_OPTION_FLAGS_WITHOUT_VALUE or (
            each_token.startswith(walk_flags.FIND_OPTIMIZATION_LEVEL_OPTION_PREFIX)
        ):
            continue
        if each_token in walk_flags.ALL_FIND_EXPRESSION_INTRODUCER_TOKENS or is_option(each_token):
            break
        all_starting_points.append(each_token)
    all_depth_values = [
        unquoted_token(all_arguments[each_index + 1])
        for each_index, each_token in enumerate(all_arguments[:-1])
        if each_token == search_rules.FIND_MAXIMUM_DEPTH_OPTION
    ]
    return starts_or_current_directory(
        all_starting_points, is_recursive_unless_shallow(all_depth_values, True)
    )


def _plain_argument_starts(all_arguments: list[str]) -> list[SearchStart]:
    return [
        SearchStart(each_argument, False)
        for each_argument in all_arguments
        if not is_option(each_argument)
    ]


_SEARCH_STARTS_BY_PROGRAM: dict[str, Callable[[list[str]], list[SearchStart]]] = {
    FIND_PROGRAM_NAME: _find_search_starts,
    **dict.fromkeys(
        search_rules.ALL_GREP_PROGRAM_NAMES,
        partial(_posix_search_starts, search_rules.GREP_GRAMMAR),
    ),
    **dict.fromkeys(
        search_rules.ALL_INDEXED_SEARCH_PROGRAM_NAMES,
        partial(_posix_search_starts, search_rules.INDEXED_SEARCH_GRAMMAR),
    ),
    **dict.fromkeys(
        walk_flags.ALL_UNIX_LS_PROGRAM_BASENAMES,
        partial(_posix_search_starts, search_rules.UNIX_LS_GRAMMAR),
    ),
    search_rules.TREE_PROGRAM_NAME: partial(_posix_search_starts, search_rules.TREE_GRAMMAR),
    **dict.fromkeys(
        walk_flags.ALL_POWERSHELL_LISTING_PROGRAM_BASENAMES, powershell_listing_search_starts
    ),
    **dict.fromkeys(search_rules.ALL_SELECT_STRING_PROGRAM_NAMES, select_string_search_starts),
}


def _program_search_starts(
    program_name: str, all_arguments: list[str], is_powershell: bool
) -> list[SearchStart]:
    if is_powershell and program_name in walk_flags.ALL_UNIX_LS_PROGRAM_BASENAMES:
        return powershell_listing_search_starts(all_arguments)
    search_starts_for = _SEARCH_STARTS_BY_PROGRAM.get(program_name, _plain_argument_starts)
    return search_starts_for(all_arguments)


def _changed_directory(current_directory: str, program_name: str, all_arguments: list[str]) -> str:
    all_targets = [each_argument for each_argument in all_arguments if not is_option(each_argument)]
    if all_targets:
        return joined_path(current_directory, all_targets[0])
    if program_name in search_rules.ALL_HOME_DEFAULT_CHANGE_DIRECTORY_PROGRAM_NAMES:
        return search_rules.HOME_DIRECTORY
    return current_directory


def _moved_directory(
    current_directory: str,
    all_pushed_directories: list[str],
    program_name: str,
    all_arguments: list[str],
) -> str | None:
    """Return the folder a ``cd``, ``pushd`` or ``popd`` moves to, else None."""
    if program_name in search_rules.ALL_POP_DIRECTORY_PROGRAM_NAMES:
        return all_pushed_directories.pop() if all_pushed_directories else current_directory
    if program_name not in search_rules.ALL_CHANGE_DIRECTORY_PROGRAM_NAMES:
        return None
    if program_name in search_rules.ALL_PUSH_DIRECTORY_PROGRAM_NAMES:
        all_pushed_directories.append(current_directory)
    return _changed_directory(current_directory, program_name, all_arguments)


def _expanded_program_call(
    all_segment_tokens: list[str], all_bindings: dict[str, str]
) -> tuple[str, list[str]]:
    """Return a segment's lowercase program name and its arguments with variables expanded."""
    program_name, all_raw_arguments = segment_program_and_arguments(all_segment_tokens)
    return program_name.lower(), [
        _expanded_token(each_argument, all_bindings) for each_argument in all_raw_arguments
    ]


def _run_search_starts(
    all_segments: list[list[str]], cwd: str, is_powershell: bool
) -> list[SearchStart]:
    """Return the starts of one tokenization's segments, read in order with their own state."""
    all_bindings: dict[str, str] = {}
    current_directory = cwd
    all_pushed_directories: list[str] = []
    all_search_starts: list[SearchStart] = []
    for each_segment in all_segments:
        assignment = _assignment_from_segment(each_segment)
        if assignment is not None:
            all_bindings[assignment[0].lower()] = _expanded_token(assignment[1], all_bindings)
            continue
        program_name, all_arguments = _expanded_program_call(each_segment, all_bindings)
        moved_directory = _moved_directory(
            current_directory, all_pushed_directories, program_name, all_arguments
        )
        if moved_directory is not None:
            current_directory = moved_directory
            continue
        all_search_starts.extend(
            SearchStart(
                joined_path(current_directory, each_start.path_text), each_start.is_recursive
            )
            for each_start in _program_search_starts(program_name, all_arguments, is_powershell)
        )
    return all_search_starts


def _segments_in_mode(
    all_line_tokenizations: list[list[list[str]]], mode_index: int
) -> list[list[str]]:
    return [
        each_segment
        for each_tokenizations in all_line_tokenizations
        if each_tokenizations
        for each_segment, _following_operator in segments_with_following_operator(
            each_tokenizations[min(mode_index, len(each_tokenizations) - 1)]
        )
    ]


def _tokenization_runs(command: str) -> list[list[list[str]]]:
    """Return the segments of each command text once per tokenization mode, lines in order."""
    all_runs: list[list[list[str]]] = []
    for each_text in all_wrapped_command_texts(command):
        all_line_tokenizations = [
            all_operator_aware_tokenizations(each_line)
            for each_line in scannable_command_lines(join_line_continuations(each_text))
            if each_line.strip()
        ]
        mode_count = max(map(len, all_line_tokenizations), default=0)
        all_runs.extend(
            _segments_in_mode(all_line_tokenizations, each_mode) for each_mode in range(mode_count)
        )
    return all_runs


def shell_command_search_starts(command: str, cwd: str, is_powershell: bool) -> list[SearchStart]:
    """Return every search start the shell command's programs name.

    Args:
        command: The Bash or PowerShell command text the agent is about to run.
        cwd: The session working directory a relative path resolves from.
        is_powershell: True for the PowerShell tool, where ``ls`` is ``Get-ChildItem``.
    """
    if search_rules.TRANSCRIPT_ROOT_MARKER not in (command + cwd).lower():
        return []
    return [
        each_start
        for each_run in _tokenization_runs(command)
        for each_start in _run_search_starts(each_run, cwd, is_powershell)
    ]
