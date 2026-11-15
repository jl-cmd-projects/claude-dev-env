#!/usr/bin/env python3
"""PreToolUse gate: keep agents from draining the GitHub API limit.

The gate refuses three kinds of gh call, checked in this order::

    gh run watch 123                                   watch command
    gh pr checks 12 --watch                            watch command
    while :; do gh run view 1; sleep 10; done          tight polling loop
    watch -n 5 gh run view 1                           tight polling loop
    gh pr view 12   (core limit 4000 of 5000 used)     spent budget

A watch command polls every few seconds until a run ends. A polling loop is a
Bash ``while``, ``until`` or ``for`` loop, a PowerShell ``while``, ``do``,
``for`` or ``foreach`` loop or ``ForEach-Object`` or ``%`` pipeline loop, or
``watch``, that calls gh and sleeps under 60 seconds in total per pass. Each
outermost loop is read on its own, from its keyword through the ``done`` or
``}`` that closes it, and a loop nested inside it counts toward it. A brace
glued to a word, as in ``{gh run view 1}``, counts as its own token. An
endless loop such as ``while :`` or
``for (;;)``, or a ``while`` or ``until`` loop whose condition calls gh, is
refused when it calls gh with no sleep. Any other loop with no sleep passes,
and so does a loop whose sleep is a variable.

A gh read on the core REST limit is refused while ``used * 5 >= limit * 4``.
The reads are the ``gh api`` calls with no write method and no field or input
option, and the subcommands the constants table lists, such as ``pr view`` and
``run list``. Writes, local commands, ``gh api graphql`` and ``gh api
rate_limit`` pass. ``hooks_constants/gh_api_budget.py`` reads the limit and
caches it for five minutes, and a limit it cannot read lets the call through.

The program is read past wrappers, chained commands and a leading PowerShell
``$name =`` assignment, so ``bash -c "gh run watch 1"`` and ``$s = gh run
watch 1`` are refused, while quoted text such as ``echo "gh run watch"``
passes. A command with no gh call reads no cache and runs no query.

Hosted by ``blocking/bash_pre_tool_use_dispatcher.py`` for the Bash and
PowerShell tools.
"""

from __future__ import annotations

import json
import shlex
import sys
import time
from collections import deque
from itertools import pairwise
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
    from hooks_constants.cloud_graphql_gate_constants import (
        ALL_GH_HELP_FLAGS,
        GH_API_SUBCOMMAND,
        GH_ENDPOINT_PATH_SEPARATOR,
        GITHUB_GRAPHQL_ENDPOINT_PATTERN,
    )
    from hooks_constants.gh_api_budget import (
        CoreRateBudget,
        is_core_budget_spent,
        read_core_rate_budget,
    )
    from hooks_constants.gh_api_budget_gate_constants import (
        ALL_BASH_LOOP_HEADER_KEYWORDS,
        ALL_CONDITION_LOOP_KEYWORDS,
        ALL_ENDLESS_CONDITIONS_BY_LOOP_KEYWORD,
        ALL_QUOTE_CHARACTERS,
        ALL_GH_API_BODY_OPTIONS,
        ALL_GH_API_METHOD_OPTIONS,
        ALL_GH_API_READ_METHODS,
        ALL_GH_API_SHORT_BODY_OPTIONS,
        ALL_GH_API_UNBUDGETED_ENDPOINTS,
        ALL_GH_PR_CHECKS_COMMAND_WORDS,
        ALL_GH_READ_COMMAND_GROUPS,
        ALL_GH_READ_SUBCOMMANDS_BY_COMMAND_GROUP,
        ALL_GH_RUN_WATCH_COMMAND_WORDS,
        ALL_LEADING_SHELL_KEYWORDS,
        ALL_LOOP_KEYWORDS,
        ALL_POWERSHELL_ASSIGNMENT_OPERATORS,
        ALL_SLEEP_PROGRAM_NAMES,
        ALL_WATCH_INTERVAL_OPTIONS,
        ALL_WATCH_OPTIONS_WITH_A_VALUE,
        BLOCK_CLOSER_CHARACTERS,
        BLOCK_END_CHARACTER,
        BLOCK_START_CHARACTER,
        COUNTED_LOOP_KEYWORD,
        LOOP_BODY_KEYWORD,
        LOOP_END_KEYWORD,
        ENDLESS_FOR_HEADER_MARKER,
        GATE_HOOK_NAME,
        GH_API_SHORT_METHOD_OPTION,
        GH_COMMAND_PATH_LENGTH,
        GH_PROGRAM_NAME,
        GH_SHORT_OPTION_LENGTH,
        GH_WATCH_OPTION,
        LOOP_HEADER_CHARACTERS,
        LOOP_HEADER_OPENER,
        MILLISECONDS_PER_SECOND,
        MINIMUM_POLL_INTERVAL_SECONDS,
        MINIMUM_START_SLEEP_PARAMETER_LENGTH,
        OPTION_PREFIX,
        POWERSHELL_ASSIGNMENT_PREFIX_LENGTH,
        POWERSHELL_VARIABLE_PATTERN,
        RESET_TIME_FORMAT,
        SECONDS_BY_SLEEP_UNIT,
        SLEEP_DURATION_AMOUNT_GROUP,
        SLEEP_DURATION_PATTERN,
        SLEEP_DURATION_UNIT_GROUP,
        SLEEP_PARAMETER_VALUE_SEPARATOR,
        SPENT_BUDGET_DENY_REASON_TEMPLATE,
        SPENT_BUDGET_RESET_SENTENCE_TEMPLATE,
        START_SLEEP_MILLISECONDS_PARAMETER,
        START_SLEEP_SECONDS_PARAMETER,
        TIGHT_POLLING_LOOP_DENY_REASON,
        WATCH_COMMAND_DENY_REASON,
        WATCH_DEFAULT_INTERVAL_SECONDS,
        WATCH_LONG_INTERVAL_OPTION_PREFIX,
        WATCH_PROGRAM_NAME,
        WATCH_SHORT_INTERVAL_OPTION,
    )
    from hooks_constants.gh_command_words import gh_command_words_and_options
    from hooks_constants.gh_command_words_constants import GH_OPTION_VALUE_SEPARATOR
    from hooks_constants.hook_block_logger import log_hook_block
    from hooks_constants.piped_pytest_blocker_constants import WRAPPED_COMMAND_TOKEN_JOIN
    from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
    from hooks_constants.pytest_invocation import unquoted_token
    from hooks_constants.shell_command_pipeline import (
        all_operator_aware_tokenizations,
        join_line_continuations,
        scannable_command_lines,
        segments_with_following_operator,
    )
    from hooks_constants.shell_command_wrappers import (
        all_wrapped_command_segments,
        all_wrapped_command_texts,
        segment_program_and_arguments,
    )
except ImportError as import_error:
    raise ImportError(
        "The gh API budget gate cannot import its dependencies; "
        "ensure the hooks directory is importable."
    ) from import_error


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


def _watch_interval_and_command(all_arguments: list[str]) -> tuple[float | None, str]:
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


def _brace_split_segments(all_segment_tokens: list[str]) -> list[list[str]]:
    """Return one segment split at each glued ``{``, so ``{gh run view 1}`` runs gh.

    Each new segment starts with its ``{``, the way a ``{`` the pipeline
    parser splits at opens the next segment in ``_ordered_segments``.
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


def _all_gh_argument_lists(command: str, is_inside_watch: bool = False) -> list[list[str]]:
    """Return the arguments of each gh call the command runs, past wrappers, braces and ``watch``."""
    return [
        each_gh_arguments
        for each_wrapped_segment in all_wrapped_command_segments(command)
        for each_segment in _brace_split_segments(each_wrapped_segment)
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
    _interval, watched_command = _watch_interval_and_command(all_arguments)
    return _all_gh_argument_lists(watched_command, True)


def _is_gh_watch_call(all_gh_arguments: list[str]) -> bool:
    all_command_words, all_option_names = gh_command_words_and_options(all_gh_arguments)
    if any(each_option in ALL_GH_HELP_FLAGS for each_option in all_option_names):
        return False
    command_path = tuple(all_command_words[:GH_COMMAND_PATH_LENGTH])
    if command_path == ALL_GH_RUN_WATCH_COMMAND_WORDS:
        return True
    return command_path == ALL_GH_PR_CHECKS_COMMAND_WORDS and GH_WATCH_OPTION in all_option_names


def runs_gh_watch_command(command: str) -> bool:
    """Return True when the command runs ``gh run watch`` or ``gh pr checks --watch``.

    ::

        gh run watch 123                 -> True
        cd repo && gh pr checks --watch  -> True
        echo "gh run watch"              -> False

    Args:
        command: The shell command text the agent is about to run.
    """
    return any(_is_gh_watch_call(each) for each in _all_gh_argument_lists(command))


def _ordered_segments(command_text: str) -> list[list[str]]:
    """Return the command's segments in run order from one tokenization, repeats kept.

    The pipeline parser drops repeated segments and merges two tokenizations,
    so two ``sleep 30`` segments would read as one there. A segment that
    follows a ``{`` starts with that ``{``, so the loop reader can count
    PowerShell blocks.
    """
    all_segments: list[list[str]] = []
    for each_line in scannable_command_lines(join_line_continuations(command_text)):
        all_tokenizations = all_operator_aware_tokenizations(each_line) if each_line.strip() else []
        for each_tokenization in all_tokenizations[:1]:
            all_segments.extend(_block_opened_segments(each_tokenization))
    return all_segments


def _block_opened_segments(all_tokens: list[str]) -> list[list[str]]:
    """Return one tokenization's segments, each segment after a ``{`` starting with that ``{``."""
    all_segments: list[list[str]] = []
    all_block_openers: list[str] = []
    for each_segment, each_operator in segments_with_following_operator(all_tokens):
        all_segments.extend(_brace_split_segments([*all_block_openers, *each_segment]))
        is_block_opener = each_operator == BLOCK_START_CHARACTER
        all_block_openers = [BLOCK_START_CHARACTER] if is_block_opener else []
    return all_segments


def _keyword_split_tokens(all_tokens: list[str]) -> list[str]:
    """Return the tokens with a glued loop header such as ``while($true)`` split after its keyword."""
    all_split_tokens: list[str] = []
    for each_token in all_tokens:
        keyword, opener, header = each_token.partition(LOOP_HEADER_OPENER)
        if opener and keyword.lower() in ALL_LOOP_KEYWORDS:
            all_split_tokens.extend([keyword, opener + header])
            continue
        all_split_tokens.append(each_token)
    return all_split_tokens


def _leading_keywords(all_segment_tokens: list[str]) -> list[str]:
    """Return the shell and loop keywords that open a segment, lowercased."""
    all_keywords: list[str] = []
    for each_token in _keyword_split_tokens(all_segment_tokens):
        lowered_token = each_token.lower()
        if (
            lowered_token not in ALL_LOOP_KEYWORDS
            and lowered_token not in ALL_LEADING_SHELL_KEYWORDS
        ):
            break
        all_keywords.append(lowered_token)
    return all_keywords


def _is_endless_loop(all_segments: list[list[str]]) -> bool:
    """Return True when a loop header reads ``while :``, ``while ($true)``, ``until false`` or ``for (;;)``."""
    all_tokens = _keyword_split_tokens(
        [each for each_segment in all_segments for each in each_segment]
    )
    for each_token, each_next_token in pairwise(all_tokens):
        keyword = each_token.lower()
        all_endless_conditions = ALL_ENDLESS_CONDITIONS_BY_LOOP_KEYWORD.get(keyword, frozenset())
        if each_next_token.strip(LOOP_HEADER_CHARACTERS).lower() in all_endless_conditions:
            return True
        is_endless_for_header = (
            ENDLESS_FOR_HEADER_MARKER in each_next_token
            and not each_next_token.strip(LOOP_HEADER_CHARACTERS)
        )
        if keyword == COUNTED_LOOP_KEYWORD and is_endless_for_header:
            return True
    return False


def _has_gh_loop_condition(all_segments: list[list[str]]) -> bool:
    """Return True when a ``while`` or ``until`` condition calls gh."""
    for each_segment in all_segments:
        all_keywords = _leading_keywords(each_segment)
        if not set(all_keywords) & ALL_CONDITION_LOOP_KEYWORDS:
            continue
        if _segment_calls_gh(_keyword_split_tokens(each_segment)[len(all_keywords) :]):
            return True
    return False


def _segment_calls_gh(all_segment_tokens: list[str]) -> bool:
    """Return True when one segment runs gh, directly, through a wrapper, or in a ``$(...)``.

    The tokens are joined back into command text twice: shell-quoted, so the
    script of ``bash -c "gh run view 1"`` stays one argument, and plain, so a
    ``$(gh run view 1)`` token is read as a substitution.
    """
    all_command_texts = (
        shlex.join(all_segment_tokens),
        WRAPPED_COMMAND_TOKEN_JOIN.join(all_segment_tokens),
    )
    return any(_all_gh_argument_lists(each_text) for each_text in all_command_texts)


def _nesting_depth_steps(
    all_segment_tokens: list[str], all_previous_segment_tokens: list[str]
) -> list[int]:
    """Return the block depth step each token of one segment takes, in token order.

    ::

        { gh run view 1 }     [1, -1]
        do                    [1]      right after a Bash loop header
        Start-Sleep 5 }       [-1]

    A ``{`` or a Bash ``do`` opens a block, and a ``}`` or a ``done`` closes
    one. A ``do`` is a Bash body only when it starts the segment right after
    a ``while``, ``until`` or ``for`` header. Any other ``do`` opens a
    PowerShell ``do { } while`` loop, so only its ``{`` counts.
    """
    follows_bash_header = bool(
        set(_leading_keywords(all_previous_segment_tokens)) & ALL_BASH_LOOP_HEADER_KEYWORDS
    )
    all_steps = [
        _token_depth_step(
            each_token.lower(), each_index == 0 and follows_bash_header, each_index == 0
        )
        for each_index, each_token in enumerate(all_segment_tokens)
    ]
    return [each_step for each_step in all_steps if each_step]


def _token_depth_step(
    lowered_token: str, can_open_bash_body: bool, can_close_bash_body: bool
) -> int:
    """Return 1 for a token that opens a block, -1 for one that closes a block, else 0."""
    if lowered_token == BLOCK_START_CHARACTER:
        return 1
    if lowered_token == BLOCK_END_CHARACTER:
        return -1
    if can_open_bash_body and lowered_token == LOOP_BODY_KEYWORD:
        return 1
    if can_close_bash_body and lowered_token == LOOP_END_KEYWORD:
        return -1
    return 0


def _loop_spans(all_segments: list[list[str]]) -> list[list[list[str]]]:
    """Return the segments of each outermost loop, from its keyword through the block end that closes it.

    ::

        for i in 1 2; do gh pr view $i; done; while :; do sleep 5; done
            -> [for ... done], [while ... done]
        while :; do for i in 1 2; do gh run view $i; done; sleep 5; done
            -> one span, since the inner loop sits in the outer one

    A PowerShell ``do { } while (...)`` keeps the condition segment after
    its ``}``, and a loop that never closes runs to the last segment. Depth
    moves token by token, so a body that opens and closes inside one
    segment, as in ``while ($x) { gh run view 1 }``, still closes its span.
    """
    all_spans: list[list[list[str]]] = []
    depth = 0
    span_start_index: int | None = None
    span_start_depth = 0
    has_span_body_opened = False
    for each_index, each_segment in enumerate(all_segments):
        is_loop_header = bool(set(_leading_keywords(each_segment)) & ALL_LOOP_KEYWORDS)
        if span_start_index is None and is_loop_header:
            span_start_index, span_start_depth, has_span_body_opened = each_index, depth, False
        previous_segment = all_segments[each_index - 1] if each_index else []
        deepest_depth = depth
        for each_step in _nesting_depth_steps(each_segment, previous_segment):
            depth = max(0, depth + each_step)
            deepest_depth = max(deepest_depth, depth)
        if span_start_index is None:
            continue
        has_span_body_opened = has_span_body_opened or deepest_depth > span_start_depth
        if not has_span_body_opened or depth > span_start_depth:
            continue
        has_trailing_condition = bool(each_segment) and (
            each_segment[-1].lower() in ALL_CONDITION_LOOP_KEYWORDS
        )
        span_end_index = each_index + int(has_trailing_condition)
        all_spans.append(all_segments[span_start_index : span_end_index + 1])
        span_start_index = None
    if span_start_index is not None:
        all_spans.append(all_segments[span_start_index:])
    return all_spans


def _sleep_seconds(all_arguments: list[str]) -> float | None:
    """Return the seconds one ``sleep`` or ``Start-Sleep`` call waits, or None when unreadable.

    ::

        sleep 30 / sleep 1m / sleep 0.5          30.0 / 60.0 / 0.5
        Start-Sleep -Seconds 30                  30.0
        Start-Sleep -Milliseconds 500            0.5
        sleep $delay                             None
    """
    total_seconds = 0.0
    seconds_per_unit: float | None = 1.0
    for each_argument in all_arguments:
        argument = unquoted_token(each_argument).lower()
        if not argument.strip(BLOCK_CLOSER_CHARACTERS):
            break
        if argument.startswith(OPTION_PREFIX):
            parameter, _separator, argument = argument.partition(SLEEP_PARAMETER_VALUE_SEPARATOR)
            seconds_per_unit = _start_sleep_unit_seconds(parameter)
        duration_seconds = _duration_seconds(argument) if argument else 0.0
        if seconds_per_unit is None or duration_seconds is None:
            return None
        total_seconds += duration_seconds * seconds_per_unit
    return total_seconds


def _start_sleep_unit_seconds(parameter: str) -> float | None:
    """Return the seconds per unit a ``Start-Sleep`` parameter such as ``-Seconds`` or ``-m`` names."""
    if len(parameter) < MINIMUM_START_SLEEP_PARAMETER_LENGTH:
        return None
    if START_SLEEP_MILLISECONDS_PARAMETER.startswith(parameter):
        return 1.0 / MILLISECONDS_PER_SECOND
    if START_SLEEP_SECONDS_PARAMETER.startswith(parameter):
        return 1.0
    return None


def _duration_seconds(duration_text: str) -> float | None:
    """Return the seconds a ``sleep`` duration such as ``30``, ``0.5`` or ``1m`` waits, or None."""
    duration = SLEEP_DURATION_PATTERN.fullmatch(duration_text)
    if duration is None:
        return None
    unit_seconds = SECONDS_BY_SLEEP_UNIT[duration.group(SLEEP_DURATION_UNIT_GROUP)]
    return float(duration.group(SLEEP_DURATION_AMOUNT_GROUP)) * unit_seconds


def _total_sleep_seconds(all_segments: list[list[str]]) -> float | None:
    """Return the seconds every sleep in the segments waits in total, or None when one is unreadable."""
    total_seconds = 0.0
    for each_segment in all_segments:
        program_name, all_arguments = segment_program_and_arguments(each_segment)
        if program_name.lower() not in ALL_SLEEP_PROGRAM_NAMES:
            continue
        seconds = _sleep_seconds(all_arguments)
        if seconds is None:
            return None
        total_seconds += seconds
    return total_seconds


def _is_tight_gh_loop_text(command_text: str) -> bool:
    """Return True when one command text holds a loop that calls gh with too little sleep."""
    return any(
        _is_tight_gh_loop_span(each_span)
        for each_span in _loop_spans(_ordered_segments(command_text))
    )


def _is_tight_gh_loop_span(all_segments: list[list[str]]) -> bool:
    """Return True when one loop's segments call gh with too little sleep."""
    if not any(_segment_calls_gh(each_segment) for each_segment in all_segments):
        return False
    total_seconds = _total_sleep_seconds(all_segments)
    if total_seconds is None:
        return False
    if total_seconds == 0:
        return _is_endless_loop(all_segments) or _has_gh_loop_condition(all_segments)
    return total_seconds < MINIMUM_POLL_INTERVAL_SECONDS


def _is_tight_gh_watch_segment(all_segment_tokens: list[str]) -> bool:
    program_name, all_arguments = segment_program_and_arguments(all_segment_tokens)
    if program_name.lower() != WATCH_PROGRAM_NAME:
        return False
    interval_seconds, watched_command = _watch_interval_and_command(all_arguments)
    if interval_seconds is None or interval_seconds >= MINIMUM_POLL_INTERVAL_SECONDS:
        return False
    return bool(_all_gh_argument_lists(watched_command, True))


def runs_tight_gh_polling_loop(command: str) -> bool:
    """Return True when a shell loop or ``watch`` calls gh with under 60 seconds of sleep.

    ::

        while :; do gh run view 1; sleep 30; done      -> True
        while ($true) { gh run view 1 }                -> True
        watch -n 5 gh run view 1                       -> True
        while :; do gh run view 1; sleep 60; done      -> False
        for x in a b c; do gh pr view $x; done         -> False

    Args:
        command: The shell command text the agent is about to run.
    """
    if any(_is_tight_gh_watch_segment(each) for each in all_wrapped_command_segments(command)):
        return True
    return any(_is_tight_gh_loop_text(each) for each in all_wrapped_command_texts(command))


def _gh_api_method(all_gh_arguments: list[str]) -> str | None:
    """Return the HTTP method a ``gh api`` call names, uppercased, or None when it names none."""
    all_unquoted_arguments = [unquoted_token(each) for each in all_gh_arguments]
    for each_previous_argument, each_argument in pairwise(["", *all_unquoted_arguments]):
        if each_previous_argument in ALL_GH_API_METHOD_OPTIONS:
            return each_argument.upper()
        option, separator, attached_method = each_argument.partition(GH_OPTION_VALUE_SEPARATOR)
        if option in ALL_GH_API_METHOD_OPTIONS and separator:
            return attached_method.upper()
        is_glued_short_method = each_argument.startswith(GH_API_SHORT_METHOD_OPTION)
        if is_glued_short_method and len(each_argument) > GH_SHORT_OPTION_LENGTH:
            return each_argument[GH_SHORT_OPTION_LENGTH:].upper()
    return None


def _is_budgeted_api_call(
    all_gh_arguments: list[str], all_command_words: list[str], all_option_names: list[str]
) -> bool:
    endpoint = unquoted_token(all_command_words[1]) if len(all_command_words) > 1 else ""
    is_unbudgeted_endpoint = (
        endpoint.strip(GH_ENDPOINT_PATH_SEPARATOR).lower() in ALL_GH_API_UNBUDGETED_ENDPOINTS
        or GITHUB_GRAPHQL_ENDPOINT_PATTERN.search(endpoint) is not None
    )
    if not endpoint or is_unbudgeted_endpoint:
        return False
    method = _gh_api_method(all_gh_arguments)
    if method is not None:
        return method in ALL_GH_API_READ_METHODS
    return not any(
        each_option in ALL_GH_API_BODY_OPTIONS
        or each_option[:GH_SHORT_OPTION_LENGTH] in ALL_GH_API_SHORT_BODY_OPTIONS
        for each_option in all_option_names
    )


def _is_budgeted_gh_read(all_gh_arguments: list[str]) -> bool:
    all_command_words, all_option_names = gh_command_words_and_options(all_gh_arguments)
    if not all_command_words or any(each in ALL_GH_HELP_FLAGS for each in all_option_names):
        return False
    command_group = all_command_words[0]
    if command_group == GH_API_SUBCOMMAND:
        return _is_budgeted_api_call(all_gh_arguments, all_command_words, all_option_names)
    if command_group in ALL_GH_READ_COMMAND_GROUPS:
        return True
    all_read_subcommands = ALL_GH_READ_SUBCOMMANDS_BY_COMMAND_GROUP.get(command_group, frozenset())
    return len(all_command_words) > 1 and all_command_words[1] in all_read_subcommands


def runs_budgeted_gh_read(command: str) -> bool:
    """Return True when the command runs a gh read that draws on the core REST limit.

    ::

        gh pr view 12                          -> True
        gh api repos/o/r/pulls                 -> True
        gh api -X POST repos/o/r/issues        -> False
        gh api graphql -f query=@q.graphql     -> False
        gh auth status                         -> False

    Args:
        command: The shell command text the agent is about to run.
    """
    return any(_is_budgeted_gh_read(each) for each in _all_gh_argument_lists(command))


def _spent_budget_reason(budget: CoreRateBudget) -> str:
    reset_sentence = ""
    try:
        if budget.reset is not None:
            reset_time = time.strftime(RESET_TIME_FORMAT, time.gmtime(budget.reset))
            reset_sentence = SPENT_BUDGET_RESET_SENTENCE_TEMPLATE.format(reset_time=reset_time)
    except (OverflowError, OSError, ValueError):
        reset_sentence = ""
    return SPENT_BUDGET_DENY_REASON_TEMPLATE.format(
        used=budget.used, limit=budget.limit, reset_sentence=reset_sentence
    )


def _deny_reason(command: str, all_gh_argument_lists: list[list[str]]) -> str | None:
    """Return the first refusal's reason for a command that calls gh, or None when it passes."""
    if any(_is_gh_watch_call(each) for each in all_gh_argument_lists):
        return WATCH_COMMAND_DENY_REASON
    if runs_tight_gh_polling_loop(command):
        return TIGHT_POLLING_LOOP_DENY_REASON
    if not any(_is_budgeted_gh_read(each) for each in all_gh_argument_lists):
        return None
    budget = read_core_rate_budget()
    if budget is None or not is_core_budget_spent(budget):
        return None
    return _spent_budget_reason(budget)


def main() -> None:
    """Deny a gh watch command, a tight gh polling loop, or a gh read on a spent budget."""
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
    all_gh_argument_lists = _all_gh_argument_lists(command)
    if not all_gh_argument_lists:
        return
    deny_reason = _deny_reason(command, all_gh_argument_lists)
    if deny_reason is None:
        return
    log_hook_block(GATE_HOOK_NAME, HOOK_EVENT_NAME, deny_reason, str(tool_name), command)
    _write_deny_decision(deny_reason)


def _write_deny_decision(deny_reason: str) -> None:
    sys.stdout.write(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": HOOK_EVENT_NAME,
                    "permissionDecision": DENY_DECISION,
                    "permissionDecisionReason": deny_reason,
                }
            }
        )
    )
    sys.stdout.flush()


if __name__ == "__main__":
    main()
