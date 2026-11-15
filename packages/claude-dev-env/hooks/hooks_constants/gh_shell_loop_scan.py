"""Find the shell loops that call gh, and read how long each pass sleeps.

::

    while :; do gh run view 1; sleep 30; done      one loop, 30 seconds of sleep
    while ($true) { gh run view 1 }                one endless loop, no sleep
    watch -n 5 gh run view 1                       a watch every 5 seconds

``blocking/gh_api_budget_gate.py`` refuses a loop or ``watch`` this module
reads as tight.
"""

from __future__ import annotations

import shlex
from itertools import pairwise

from hooks_constants.gh_api_budget_gate_constants import (
    ALL_BASH_LOOP_HEADER_KEYWORDS,
    ALL_CONDITION_LOOP_KEYWORDS,
    ALL_ENDLESS_CONDITIONS_BY_LOOP_KEYWORD,
    ALL_LEADING_SHELL_KEYWORDS,
    ALL_LOOP_KEYWORDS,
    ALL_SLEEP_PROGRAM_NAMES,
    BLOCK_CLOSER_CHARACTERS,
    BLOCK_END_CHARACTER,
    BLOCK_START_CHARACTER,
    COUNTED_LOOP_KEYWORD,
    ENDLESS_FOR_HEADER_MARKER,
    LOOP_BODY_KEYWORD,
    LOOP_END_KEYWORD,
    LOOP_HEADER_CHARACTERS,
    LOOP_HEADER_OPENER,
    ALL_SECONDS_BY_TIMESPAN_FIELD,
    ALL_SHELL_EXPANSION_MARKERS,
    MILLISECONDS_PER_SECOND,
    MINIMUM_POLL_INTERVAL_SECONDS,
    MINIMUM_START_SLEEP_DURATION_PARAMETER_LENGTH,
    MINIMUM_START_SLEEP_PARAMETER_LENGTH,
    OPTION_PREFIX,
    SECONDS_BY_SLEEP_UNIT,
    SLEEP_DURATION_AMOUNT_GROUP,
    SLEEP_DURATION_PATTERN,
    SLEEP_DURATION_UNIT_GROUP,
    SLEEP_PARAMETER_VALUE_SEPARATOR,
    SLEEP_TIMESPAN_FIELD_SEPARATOR,
    SLEEP_TIMESPAN_PATTERN,
    START_SLEEP_DURATION_PARAMETER,
    START_SLEEP_MILLISECONDS_PARAMETER,
    START_SLEEP_SECONDS_PARAMETER,
    WATCH_PROGRAM_NAME,
)
from hooks_constants.gh_argument_lists import (
    all_gh_call_argument_lists,
    brace_split_segments,
    watch_interval_and_command,
)
from hooks_constants.piped_pytest_blocker_constants import WRAPPED_COMMAND_TOKEN_JOIN
from hooks_constants.pytest_invocation import unquoted_token
from hooks_constants.shell_command_pipeline import (
    all_operator_aware_tokenizations,
    join_line_continuations,
    scannable_command_lines,
    segments_with_following_operator,
)
from hooks_constants.shell_command_wrappers import segment_program_and_arguments


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
        all_segments.extend(brace_split_segments([*all_block_openers, *each_segment]))
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
    return any(all_gh_call_argument_lists(each_text) for each_text in all_command_texts)


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

        sleep 30 / sleep 1m / sleep .5           30.0 / 60.0 / 0.5
        Start-Sleep -Seconds 30 -Verbose         30.0
        Start-Sleep -Milliseconds 500            0.5
        Start-Sleep -Duration 00:01:30           90.0
        sleep 5 2>/dev/null                      5.0
        sleep $delay                             None

    A parameter that names no time unit, such as ``-Verbose`` or
    ``-ErrorAction Stop``, is skipped together with its value. Any other
    word that is not a duration, such as a redirect, is skipped too. Only a
    shell expansion, a ``$`` or a backtick, makes the sleep unreadable.
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
        if seconds_per_unit is None or not argument:
            continue
        duration_seconds = _duration_seconds(argument)
        if duration_seconds is None:
            if any(each_marker in argument for each_marker in ALL_SHELL_EXPANSION_MARKERS):
                return None
            continue
        total_seconds += duration_seconds * seconds_per_unit
    return total_seconds


def _start_sleep_unit_seconds(parameter: str) -> float | None:
    """Return the seconds per unit a ``Start-Sleep`` parameter such as ``-Seconds``, ``-m`` or ``-Duration`` names.

    ``-Duration`` takes a ``hh:mm:ss`` value already in seconds, so its unit
    is one second. Any other parameter names no unit and returns None.
    """
    if len(parameter) < MINIMUM_START_SLEEP_PARAMETER_LENGTH:
        return None
    if START_SLEEP_MILLISECONDS_PARAMETER.startswith(parameter):
        return 1.0 / MILLISECONDS_PER_SECOND
    if START_SLEEP_SECONDS_PARAMETER.startswith(parameter):
        return 1.0
    if len(parameter) >= MINIMUM_START_SLEEP_DURATION_PARAMETER_LENGTH and (
        START_SLEEP_DURATION_PARAMETER.startswith(parameter)
    ):
        return 1.0
    return None


def _duration_seconds(duration_text: str) -> float | None:
    """Return the seconds a duration such as ``30``, ``.5``, ``1m`` or ``00:01:30`` waits, or None."""
    if SLEEP_TIMESPAN_PATTERN.fullmatch(duration_text):
        all_fields = duration_text.split(SLEEP_TIMESPAN_FIELD_SEPARATOR)
        return sum(
            float(each_field) * each_field_seconds
            for each_field, each_field_seconds in zip(all_fields, ALL_SECONDS_BY_TIMESPAN_FIELD, strict=False)
        )
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


def is_tight_gh_loop_text(command_text: str) -> bool:
    """Return True when one command text holds a loop that calls gh with too little sleep.

    ::

        while :; do gh run view 1; sleep 30; done    True
        while :; do gh run view 1; sleep 60; done    False

    Args:
        command_text: The shell command text, past any wrapper.
    """
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


def is_tight_gh_watch_segment(all_segment_tokens: list[str]) -> bool:
    """Return True when one segment runs ``watch`` on a gh call under 60 seconds apart.

    ::

        watch -n 5 gh run view 1     True
        watch -n 60 gh run view 1    False
        watch -n 5 date              False

    Args:
        all_segment_tokens: The tokens of one shell segment.
    """
    program_name, all_arguments = segment_program_and_arguments(all_segment_tokens)
    if program_name.lower() != WATCH_PROGRAM_NAME:
        return False
    interval_seconds, watched_command = watch_interval_and_command(all_arguments)
    if interval_seconds is None or interval_seconds >= MINIMUM_POLL_INTERVAL_SECONDS:
        return False
    return bool(all_gh_call_argument_lists(watched_command, True))
