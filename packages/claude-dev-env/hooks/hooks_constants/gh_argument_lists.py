"""Find the gh calls a shell command runs, past wrappers, glued braces, assignments and ``watch``.

::

    gh pr view 12                  [["pr", "view", "12"]]
    $s = gh run watch 1            [["run", "watch", "1"]]
    {gh run view 1}                [["run", "view", "1"]]
    watch -n 5 gh run view 1       [["run", "view", "1"]]
    echo "gh run watch"            []

``blocking/gh_api_budget_gate.py`` and ``gh_shell_loop_scan`` read gh calls
through this module.
"""

from __future__ import annotations

from collections import deque

from hooks_constants.gh_api_budget_gate_constants import (
    ALL_POWERSHELL_ASSIGNMENT_OPERATORS,
    ALL_QUOTE_CHARACTERS,
    ALL_WATCH_INTERVAL_OPTIONS,
    ALL_WATCH_OPTIONS_WITH_A_VALUE,
    BLOCK_END_CHARACTER,
    BLOCK_START_CHARACTER,
    GH_PROGRAM_NAME,
    OPTION_PREFIX,
    POWERSHELL_ASSIGNMENT_PREFIX_LENGTH,
    POWERSHELL_VARIABLE_PATTERN,
    WATCH_DEFAULT_INTERVAL_SECONDS,
    WATCH_LONG_INTERVAL_OPTION_PREFIX,
    WATCH_PROGRAM_NAME,
    WATCH_SHORT_INTERVAL_OPTION,
)
from hooks_constants.piped_pytest_blocker_constants import WRAPPED_COMMAND_TOKEN_JOIN
from hooks_constants.pytest_invocation import unquoted_token
from hooks_constants.shell_command_wrappers import (
    all_wrapped_command_segments,
    segment_program_and_arguments,
)


def _watch_option_interval(option: str, all_remaining_arguments: deque[str]) -> str | None:
    """Return the interval text one ``watch`` option sets, taking its separate value when it has one.

    Returns None when the option sets no interval.
    """
    if option in ALL_WATCH_INTERVAL_OPTIONS or option in ALL_WATCH_OPTIONS_WITH_A_VALUE:
        option_value = all_remaining_arguments.popleft() if all_remaining_arguments else ""
        return option_value if option in ALL_WATCH_INTERVAL_OPTIONS else None
    if option.startswith(WATCH_LONG_INTERVAL_OPTION_PREFIX):
        return option.removeprefix(WATCH_LONG_INTERVAL_OPTION_PREFIX)
    if option.startswith(WATCH_SHORT_INTERVAL_OPTION):
        return option.removeprefix(WATCH_SHORT_INTERVAL_OPTION)
    return None


def watch_interval_and_command(all_arguments: list[str]) -> tuple[float | None, str]:
    """Return a ``watch`` call's interval in seconds, None when unreadable, and the command it runs."""
    interval_text: str | None = None
    all_remaining_arguments = deque(unquoted_token(each) for each in all_arguments)
    while all_remaining_arguments and all_remaining_arguments[0].startswith(OPTION_PREFIX):
        option = all_remaining_arguments.popleft()
        option_interval = _watch_option_interval(option, all_remaining_arguments)
        interval_text = interval_text if option_interval is None else option_interval
    watched_command = WRAPPED_COMMAND_TOKEN_JOIN.join(all_remaining_arguments)
    if interval_text is None:
        return WATCH_DEFAULT_INTERVAL_SECONDS, watched_command
    try:
        return float(interval_text), watched_command
    except ValueError:
        return None, watched_command


def _brace_split_tokens(token: str) -> list[str]:
    """Return one token with its glued PowerShell braces split off.

    ::

        {gh        ["{", "gh"]
        5}         ["5", "}"]
        {}         ["{", "}"]
        ${name}    ["${name}"]

    Quoted text, which holds a quote or a space, stays whole.
    """
    is_quoted_text = token.startswith(tuple(ALL_QUOTE_CHARACTERS)) or any(
        each_character.isspace() for each_character in token
    )
    if is_quoted_text:
        return [token]
    body = token.lstrip(BLOCK_START_CHARACTER)
    opening_count = len(token) - len(body)
    closing_count = 0
    while body.endswith(BLOCK_END_CHARACTER) and body.count(BLOCK_END_CHARACTER) > body.count(
        BLOCK_START_CHARACTER
    ):
        body = body.removesuffix(BLOCK_END_CHARACTER)
        closing_count += 1
    return [
        *[BLOCK_START_CHARACTER] * opening_count,
        *([body] if body else []),
        *[BLOCK_END_CHARACTER] * closing_count,
    ]


def brace_split_segments(all_segment_tokens: list[str]) -> list[list[str]]:
    """Return one segment split at each glued ``{``, so ``{gh run view 1}`` runs gh.

    Each new segment starts with its ``{``, the way a ``{`` the pipeline
    parser splits at opens the next segment in ``gh_shell_loop_scan``.
    """
    all_parts = [
        each_part
        for each_token in all_segment_tokens
        for each_part in _brace_split_tokens(each_token)
    ]
    all_segments: list[list[str]] = [[]]
    for each_part in all_parts:
        if each_part == BLOCK_START_CHARACTER:
            all_segments.append([])
        all_segments[-1].append(each_part)
    return [each_segment for each_segment in all_segments if each_segment]


def all_gh_call_argument_lists(command: str, is_inside_watch: bool = False) -> list[list[str]]:
    """Return the arguments of each gh call the command runs, past wrappers, braces and ``watch``."""
    return [
        each_gh_arguments
        for each_wrapped_segment in all_wrapped_command_segments(command)
        for each_segment in brace_split_segments(each_wrapped_segment)
        for each_gh_arguments in _segment_gh_argument_lists(each_segment, is_inside_watch)
    ]


def _tokens_past_assignment(all_segment_tokens: list[str]) -> list[str]:
    """Return a segment's tokens past a leading PowerShell ``$name =`` prefix.

    ::

        $s = gh run watch 1         ["gh", "run", "watch", "1"]
        $script:s += gh pr view 1   ["gh", "pr", "view", "1"]
        gh run view 1               ["gh", "run", "view", "1"]
    """
    assignment_prefix = all_segment_tokens[:POWERSHELL_ASSIGNMENT_PREFIX_LENGTH]
    is_assignment = (
        len(assignment_prefix) == POWERSHELL_ASSIGNMENT_PREFIX_LENGTH
        and POWERSHELL_VARIABLE_PATTERN.fullmatch(assignment_prefix[0]) is not None
        and assignment_prefix[1] in ALL_POWERSHELL_ASSIGNMENT_OPERATORS
    )
    if is_assignment:
        return all_segment_tokens[POWERSHELL_ASSIGNMENT_PREFIX_LENGTH:]
    return all_segment_tokens


def _segment_gh_argument_lists(
    all_segment_tokens: list[str], is_inside_watch: bool
) -> list[list[str]]:
    """Return the arguments of the gh call one segment runs, directly, as an assigned value, or through ``watch``."""
    program_name, all_arguments = segment_program_and_arguments(
        _tokens_past_assignment(all_segment_tokens)
    )
    normalized_program_name = program_name.lower()
    if normalized_program_name == GH_PROGRAM_NAME:
        return [all_arguments]
    if normalized_program_name != WATCH_PROGRAM_NAME or is_inside_watch:
        return []
    _interval, watched_command = watch_interval_and_command(all_arguments)
    return all_gh_call_argument_lists(watched_command, True)
