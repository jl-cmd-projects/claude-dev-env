"""Grade one headless session on whether it took an eval step before changing a feature."""

import math
import posixpath
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from session_eval_support.config.constants import (
    ALL_EVAL_DIRECTORY_NAMES,
    ALL_FILE_EDIT_TOOL_NAMES,
    ALL_FILE_PATH_FIELDS,
    ALL_SPAWN_TOOL_NAMES,
    ALL_TEST_DIRECTORY_NAMES,
    ASSISTANT_EVENT_TYPE,
    BUILD_EVAL_ARGUMENT_WORD,
    BUILD_EVAL_SKILL_NAME,
    EVAL_FILE_NAME_WORD_PATTERN,
    EXPECTED_EVAL_FIRST,
    LOCAL_BUILD_EVAL_SKILL_NAME,
    PATH_SEPARATOR_PATTERN,
    PLUGIN_SEPARATOR,
    POSIX_SEPARATOR,
    SKILL_TOOL_NAME,
    TEST_FILE_NAME_PATTERN,
    TOOL_USE_BLOCK_TYPE,
    WILSON_CENTER_DIVISOR,
    WILSON_SPREAD_DIVISOR,
    WILSON_Z,
    WILSON_Z_SQUARED,
)


@dataclass(frozen=True)
class ToolCall:
    """One tool call a session made, in the order it made them."""

    name: str
    tool_input: Mapping[str, object]


def tool_calls(all_events: Iterable[Mapping[str, object]]) -> list[ToolCall]:
    """Return every tool call in a stream-json session, in order.

    ::

        assistant event with a Skill tool_use -> [ToolCall("Skill", {...})]
        result event                          -> []

    Args:
        all_events: The parsed lines of a ``--output-format stream-json`` run.

    Returns:
        One ToolCall per tool_use block of an assistant event.
    """
    return [
        _tool_call(each_block)
        for each_event in all_events
        for each_block in _tool_use_blocks(each_event)
    ]


def _tool_use_blocks(event_by_field: Mapping[str, object]) -> list[dict[str, object]]:
    message = event_by_field.get("message")
    if event_by_field.get("type") != ASSISTANT_EVENT_TYPE or not isinstance(message, dict):
        return []
    all_blocks = message.get("content")
    if not isinstance(all_blocks, list):
        return []
    return [
        each_block
        for each_block in all_blocks
        if isinstance(each_block, dict)
        and each_block.get("type") == TOOL_USE_BLOCK_TYPE
    ]


def _tool_call(block_by_field: Mapping[str, object]) -> ToolCall:
    tool_input = block_by_field.get("input")
    return ToolCall(
        str(block_by_field.get("name")),
        tool_input if isinstance(tool_input, dict) else {},
    )


def names_skill(call: ToolCall, skill_name: str) -> bool:
    """Return whether a call is a Skill call naming one skill, bare or plugin-qualified.

    ::

        Skill {"skill": "pr-lifecycle"}         -> True for "pr-lifecycle"
        Skill {"skill": "tools:pr-lifecycle"}   -> True for "pr-lifecycle"

    Args:
        call: One tool call from the session.
        skill_name: The skill's bare name.

    Returns:
        Whether the call invokes that skill.
    """
    invoked = call.tool_input.get("skill")
    return (
        call.name == SKILL_TOOL_NAME
        and isinstance(invoked, str)
        and (invoked == skill_name or invoked.endswith(PLUGIN_SEPARATOR + skill_name))
    )


def is_build_eval_call(call: ToolCall) -> bool:
    """Return whether a call invokes build-eval, as a claude-api subcommand or its own skill.

    ::

        Skill {"skill": "claude-api", "args": "build-eval"}        -> True
        Skill {"skill": "claude-api", "args": "build-eval report"} -> True
        Skill {"skill": "build-eval"}                              -> True
        Skill {"skill": "claude-api", "args": "migrate"}           -> False

    Args:
        call: One tool call from the session.

    Returns:
        Whether the call is a claude-api Skill call whose first argument word
        is build-eval, or a Skill call naming the build-eval skill.
    """
    arguments = call.tool_input.get("args")
    all_words = arguments.split() if isinstance(arguments, str) else []
    is_claude_api_build_eval = names_skill(call, BUILD_EVAL_SKILL_NAME) and all_words[:1] == [
        BUILD_EVAL_ARGUMENT_WORD
    ]
    return is_claude_api_build_eval or names_skill(call, LOCAL_BUILD_EVAL_SKILL_NAME)


def _path_segments(path: str) -> list[str]:
    slash_path = re.sub(PATH_SEPARATOR_PATTERN, POSIX_SEPARATOR, path.lower())
    return [each for each in posixpath.normpath(slash_path).split(POSIX_SEPARATOR) if each]


def is_eval_path(path: str) -> bool:
    """Return whether a path belongs to an eval: its cases, grader or runner.

    ::

        evals/cases.json                     -> True
        .claude/hillclimb/feature/run.py     -> True
        tools/eval_runner.py                 -> True
        tests/test_search.eval.json          -> True
        evals/../src/app.py                  -> False
        docs/features-start-with-an-eval.md  -> False
        tests/test_cleanup.py                -> False

    Args:
        path: The file path a tool edits.

    Returns:
        Whether a folder above the file is named eval, evals or hillclimb, or
        the file name starts with an eval word or carries an ``.eval.`` part.
    """
    all_segments = _path_segments(path)
    if not all_segments:
        return False
    if any(each in ALL_EVAL_DIRECTORY_NAMES for each in all_segments[:-1]):
        return True
    return re.search(EVAL_FILE_NAME_WORD_PATTERN, all_segments[-1]) is not None


def is_test_path(path: str) -> bool:
    """Return whether a path is a test file that is not an eval file.

    ::

        tests/test_cleanup.py   -> True
        jobs/report_test.py     -> True
        tests/conftest.py       -> True
        evals/test_cases.py     -> False
        jobs/report.py          -> False

    Args:
        path: The file path a tool edits.

    Returns:
        Whether the file sits under a test or tests folder or carries a test
        file name, and is_eval_path is False for it.
    """
    all_segments = _path_segments(path)
    if not all_segments or is_eval_path(path):
        return False
    if any(each in ALL_TEST_DIRECTORY_NAMES for each in all_segments[:-1]):
        return True
    return re.search(TEST_FILE_NAME_PATTERN, all_segments[-1]) is not None


def edited_paths(call: ToolCall) -> list[str]:
    """Return the file paths a file edit call writes, or an empty list for any other call.

    ::

        Write {"file_path": "a.py"}                  -> ["a.py"]
        NotebookEdit {"notebook_path": "n.ipynb"}    -> ["n.ipynb"]
        Bash {"command": "echo x > a.py"}            -> []

    Args:
        call: One tool call from the session.

    Returns:
        The non-empty path fields of a Write, Edit, MultiEdit or NotebookEdit call.
    """
    if call.name not in ALL_FILE_EDIT_TOOL_NAMES:
        return []
    return [
        path
        for path in (call.tool_input.get(each_field) for each_field in ALL_FILE_PATH_FIELDS)
        if isinstance(path, str) and path
    ]


def is_eval_step(call: ToolCall) -> bool:
    """Return whether a call builds an eval: an eval file edit or a build-eval call.

    ::

        Write evals/cases.json                     -> True
        Skill claude-api build-eval                -> True
        Write CLAUDE.md                            -> False
        Read evals/cases.json                      -> False

    Args:
        call: One tool call from the session.

    Returns:
        Whether the call is a build-eval call, or an edit whose every path is an eval path.
    """
    all_paths = edited_paths(call)
    return is_build_eval_call(call) or (
        bool(all_paths) and all(is_eval_path(each_path) for each_path in all_paths)
    )


def _is_change_step(call: ToolCall) -> bool:
    return call.name in ALL_SPAWN_TOOL_NAMES or (
        bool(edited_paths(call)) and not is_eval_step(call)
    )


def _first_step(all_calls: list[ToolCall]) -> ToolCall | None:
    return next(
        (
            each_call
            for each_call in all_calls
            if is_eval_step(each_call) or _is_change_step(each_call)
        ),
        None,
    )


def eval_came_first(all_calls: list[ToolCall]) -> bool:
    """Return whether an eval step came before any edit of a non-eval file or subagent.

    ::

        [Read, Write evals/cases.json, Write CLAUDE.md] -> True
        [Read, Skill build-eval, Write CLAUDE.md]       -> True
        [Write CLAUDE.md, Write evals/cases.json]       -> False
        [Agent, Write evals/cases.json]                 -> False
        [Read, Grep]                                    -> False

    Args:
        all_calls: The session's tool calls in order.

    Returns:
        Whether the first eval step or change step in the session is an eval step.
    """
    first_step = _first_step(all_calls)
    return first_step is not None and is_eval_step(first_step)


def first_step_edits_tests(all_calls: list[ToolCall]) -> bool:
    """Return whether the session's first eval or change step edited only test files.

    ::

        [Write tests/test_guard.py, Write .claude/settings.json] -> True
        [Write evals/cases.json, Write tests/test_guard.py]      -> False
        [Write CLAUDE.md, Write tests/test_claude_md.py]         -> False

    Args:
        all_calls: The session's tool calls in order.

    Returns:
        Whether the first eval step or change step is an edit whose every path
        is a test path.
    """
    first_step = _first_step(all_calls)
    all_paths = edited_paths(first_step) if first_step is not None else []
    return bool(all_paths) and all(is_test_path(each_path) for each_path in all_paths)


def grade_case(expected: str, all_calls: list[ToolCall]) -> dict[str, int]:
    """Score one session against its case's expected first step.

    An ``eval-first`` case is correct when its first eval step or change step
    is an eval step or an edit of test files only, since a test suite that
    holds cases, a runner and a grader counts as the feature's eval. It is
    also correct when the session read the project and then held the change,
    with no change step at all, since the guide has it stop for approval of
    the eval before any edit. Any other case is correct when the session took
    no eval step at all, so a plain code feature may still start with its
    tests::

        "eval-first", [Write evals/cases.json, Write CLAUDE.md]   -> correct 1
        "eval-first", [Skill build-eval, Write CLAUDE.md]         -> correct 1
        "eval-first", [Write tests/test_guard.py, Write settings] -> correct 1
        "eval-first", [Read, Glob]                                -> correct 1
        "eval-first", []                                          -> correct 0
        "eval-first", [Write CLAUDE.md]                           -> correct 0
        "none",       [Write tests/test_cli.py, Edit jobs/cli.py] -> correct 1
        "none",       [Skill claude-api build-eval]               -> correct 0

    Args:
        expected: The case's expected first step, ``eval-first`` or ``none``.
        all_calls: The session's tool calls in order.

    Returns:
        The metric ids from _state.json mapped to 0 or 1.
    """
    came_first = eval_came_first(all_calls)
    tests_came_first = first_step_edits_tests(all_calls)
    took_eval_step = any(is_eval_step(each_call) for each_call in all_calls)
    held_the_change = bool(all_calls) and not any(
        _is_change_step(each_call) for each_call in all_calls
    )
    correct = (
        came_first or tests_came_first or held_the_change
        if expected == EXPECTED_EVAL_FIRST
        else not took_eval_step
    )
    return {
        "correct": int(correct),
        "eval_first": int(came_first),
        "build_eval_call": int(any(is_build_eval_call(each_call) for each_call in all_calls)),
        "test_first": int(tests_came_first),
    }


def wilson_interval(successes: int, trials: int) -> tuple[float, float]:
    """Return the 95% Wilson score interval for a pass rate.

    ::

        wilson_interval(0, 0) -> (0.0, 1.0)
        wilson_interval(3, 3) -> (0.438..., 1.0)

    Args:
        successes: How many trials passed.
        trials: How many trials ran.

    Returns:
        The low and high bounds, clamped to the range 0 to 1.
    """
    if trials == 0:
        return 0.0, 1.0
    rate = successes / trials
    z_squared = WILSON_Z_SQUARED
    denominator = 1 + z_squared / trials
    center = (rate + z_squared / (WILSON_CENTER_DIVISOR * trials)) / denominator
    spread = (
        WILSON_Z
        * math.sqrt(
            rate * (1 - rate) / trials
            + z_squared / (WILSON_SPREAD_DIVISOR * trials * trials)
        )
        / denominator
    )
    return max(0.0, center - spread), min(1.0, center + spread)
