"""Decide whether a shell command writes, sends, or changes state.

Every command string a wrapper runs is scanned, and each segment is read as
its program plus arguments after the wrappers in front of it::

    sudo git push                      writes
    bash -c "gh pr merge 12"           writes
    pwsh -Command git push; echo done  writes
    rg 'gh pr merge' docs              reads
    grep "a|cp b" notes.md             reads

A write counts only when the POSIX tokenization and the raw tokenization of a
line agree on it, so a quoted literal never reads as a command.
"""

from __future__ import annotations

import itertools

from hooks_constants.pytest_invocation import unquoted_token
from hooks_constants.shell_command_pipeline import (
    all_operator_aware_tokenizations,
    join_line_continuations,
    scannable_command_lines,
    segments_with_following_operator,
)
from hooks_constants.shell_command_segments import git_subcommand_tokens, token_basename
from hooks_constants.shell_command_wrappers import (
    all_wrapped_command_texts,
    segment_program_and_arguments,
)
from hooks_constants.verify_before_acting_constants import (
    ALL_FILE_WRITING_PROGRAM_NAMES,
    ALL_GH_API_METHOD_OPTIONS,
    ALL_HTTP_WRITE_METHODS,
    ALL_MUTATING_GH_SUBCOMMANDS,
    ALL_MUTATING_GIT_SUBCOMMAND_PREFIXES,
    ALL_NON_FILE_REDIRECTION_TARGETS,
    ALL_POWERSHELL_WRITE_CMDLET_NAMES,
    ALL_PULL_REQUEST_SCRIPT_WRITE_ACTIONS,
    ALL_WRITE_REDIRECTION_OPERATORS,
    GH_API_ATTACHED_METHOD_PATTERN,
    GH_API_FIELD_OPTION_PATTERN,
    GH_API_SUBCOMMAND,
    GH_PROGRAM_NAME,
    GH_SUBCOMMAND_DEPTH,
    GIT_PROGRAM_NAME,
    POWERSHELL_WORD_BRACKETS,
    PULL_REQUEST_SCRIPT_NAME,
    REDIRECTION_TARGET_QUOTES,
    SED_IN_PLACE_OPTION_PATTERN,
    SED_PROGRAM_NAME,
)

__all__ = ["is_mutating_shell_command"]


def _is_mutating_git_arguments(all_arguments: list[str]) -> bool:
    all_subcommand_tokens = git_subcommand_tokens(all_arguments)
    return any(
        tuple(all_subcommand_tokens[: len(each_prefix)]) == each_prefix
        for each_prefix in ALL_MUTATING_GIT_SUBCOMMAND_PREFIXES
    )


def _gh_api_method(all_api_arguments: list[str]) -> str | None:
    for each_option, each_value in itertools.pairwise(all_api_arguments):
        if each_option in ALL_GH_API_METHOD_OPTIONS:
            return each_value.upper()
    for each_argument in all_api_arguments:
        attached_match = GH_API_ATTACHED_METHOD_PATTERN.fullmatch(each_argument)
        if attached_match is not None:
            return attached_match.group("method").upper()
    return None


def _is_mutating_gh_api(all_api_arguments: list[str]) -> bool:
    """Return True when ``gh api`` sends a write method, or fields with no method named."""
    method = _gh_api_method(all_api_arguments)
    if method is not None:
        return method in ALL_HTTP_WRITE_METHODS
    return any(
        GH_API_FIELD_OPTION_PATTERN.fullmatch(each_argument) for each_argument in all_api_arguments
    )


def _is_mutating_gh_arguments(all_arguments: list[str]) -> bool:
    if tuple(all_arguments[:GH_SUBCOMMAND_DEPTH]) in ALL_MUTATING_GH_SUBCOMMANDS:
        return True
    return all_arguments[:1] == [GH_API_SUBCOMMAND] and _is_mutating_gh_api(all_arguments[1:])


def _program_mutates(program_name: str, all_arguments: list[str]) -> bool:
    if program_name in ALL_FILE_WRITING_PROGRAM_NAMES:
        return True
    if program_name == SED_PROGRAM_NAME:
        return any(
            SED_IN_PLACE_OPTION_PATTERN.fullmatch(each_argument) for each_argument in all_arguments
        )
    if program_name == GIT_PROGRAM_NAME:
        return _is_mutating_git_arguments(all_arguments)
    return program_name == GH_PROGRAM_NAME and _is_mutating_gh_arguments(all_arguments)


def _runs_a_pull_request_script_write(all_segment_tokens: list[str]) -> bool:
    for each_index, each_token in enumerate(all_segment_tokens):
        if token_basename(unquoted_token(each_token)) == PULL_REQUEST_SCRIPT_NAME:
            return any(
                unquoted_token(each_later_token) in ALL_PULL_REQUEST_SCRIPT_WRITE_ACTIONS
                for each_later_token in all_segment_tokens[each_index + 1 :]
            )
    return False


def _names_a_powershell_write_cmdlet(all_segment_tokens: list[str]) -> bool:
    return any(
        each_token.strip(POWERSHELL_WORD_BRACKETS).lower() in ALL_POWERSHELL_WRITE_CMDLET_NAMES
        for each_token in all_segment_tokens
    )


def _segment_redirects_into_a_file(all_segment_tokens: list[str]) -> bool:
    for each_operator, each_target in itertools.pairwise(all_segment_tokens):
        if each_operator not in ALL_WRITE_REDIRECTION_OPERATORS:
            continue
        target_text = each_target.strip(REDIRECTION_TARGET_QUOTES).lower()
        if target_text not in ALL_NON_FILE_REDIRECTION_TARGETS and not target_text.isdigit():
            return True
    return False


def _segment_is_mutating(all_segment_tokens: list[str]) -> bool:
    program_name, all_arguments = segment_program_and_arguments(all_segment_tokens)
    return (
        _program_mutates(program_name, all_arguments)
        or _runs_a_pull_request_script_write(all_segment_tokens)
        or _names_a_powershell_write_cmdlet(all_segment_tokens)
        or _segment_redirects_into_a_file(all_segment_tokens)
    )


def _line_is_mutating(command_line: str) -> bool:
    """Return True when every quote-aware tokenization of the line has a mutating segment.

    The POSIX tokenization strips the quotes from ``rg 'Remove-Item' docs`` and
    the raw one splits ``--format='%h > %s'`` mid-quote, so a write counts only
    when both spellings agree on it.
    """
    all_tokenizations = all_operator_aware_tokenizations(command_line)
    return bool(all_tokenizations) and all(
        any(
            _segment_is_mutating(each_segment)
            for each_segment, _following_operator in segments_with_following_operator(
                each_tokenization
            )
        )
        for each_tokenization in all_tokenizations
    )


def is_mutating_shell_command(command: str) -> bool:
    """Return True when any line of the command, or of a command string it wraps, writes."""
    return any(
        _line_is_mutating(each_line)
        for each_command_text in all_wrapped_command_texts(command)
        for each_line in scannable_command_lines(join_line_continuations(each_command_text))
    )
