"""Grade one headless session on whether it started a feature with build-eval."""

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from session_eval_support.config.constants import (
    ALL_EDIT_OR_SPAWN_TOOL_NAMES,
    ASSISTANT_EVENT_TYPE,
    BUILD_EVAL_ARGUMENT_WORD,
    BUILD_EVAL_SKILL_NAME,
    EXPECTED_BUILD_EVAL,
    LOCAL_BUILD_EVAL_SKILL_NAME,
    PLUGIN_SEPARATOR,
    SKILL_TOOL_NAME,
    TOOL_USE_BLOCK_TYPE,
    WILSON_Z,
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
    all_calls: list[ToolCall] = []
    for each_event in all_events:
        message = each_event.get("message")
        if each_event.get("type") != ASSISTANT_EVENT_TYPE or not isinstance(
            message, dict
        ):
            continue
        all_blocks = message.get("content")
        if not isinstance(all_blocks, list):
            continue
        for each_block in all_blocks:
            if (
                isinstance(each_block, dict)
                and each_block.get("type") == TOOL_USE_BLOCK_TYPE
            ):
                tool_input = each_block.get("input")
                all_calls.append(
                    ToolCall(
                        str(each_block.get("name")),
                        tool_input if isinstance(tool_input, dict) else {},
                    )
                )
    return all_calls


def _names_skill(call: ToolCall, skill_name: str) -> bool:
    invoked = call.tool_input.get("skill")
    return (
        call.name == SKILL_TOOL_NAME
        and isinstance(invoked, str)
        and (invoked == skill_name or invoked.endswith(PLUGIN_SEPARATOR + skill_name))
    )


def is_build_eval_call(call: ToolCall) -> bool:
    """Return whether a call invokes the claude-api skill's build-eval subcommand.

    ::

        Skill {"skill": "claude-api", "args": "build-eval"}       -> True
        Skill {"skill": "claude-api", "args": "build-eval report"} -> True
        Skill {"skill": "claude-api", "args": "migrate"}          -> False
        Skill {"skill": "build-eval"}                             -> False

    Args:
        call: One tool call from the session.
    """
    arguments = call.tool_input.get("args")
    all_words = arguments.split() if isinstance(arguments, str) else []
    return _names_skill(call, BUILD_EVAL_SKILL_NAME) and all_words[:1] == [
        BUILD_EVAL_ARGUMENT_WORD
    ]


def is_local_build_eval_call(call: ToolCall) -> bool:
    """Return whether a call invokes the separate build-eval skill.

    Args:
        call: One tool call from the session.
    """
    return _names_skill(call, LOCAL_BUILD_EVAL_SKILL_NAME)


def build_eval_came_first(all_calls: list[ToolCall]) -> bool:
    """Return whether build-eval ran before any file edit or subagent.

    ::

        [Read, Skill claude-api build-eval, Write] -> True
        [Write, Skill claude-api build-eval]       -> False
        [Read, Grep]                               -> False

    Args:
        all_calls: The session's tool calls in order.
    """
    for each_call in all_calls:
        if is_build_eval_call(each_call):
            return True
        if each_call.name in ALL_EDIT_OR_SPAWN_TOOL_NAMES:
            return False
    return False


def grade_case(expected: str, all_calls: list[ToolCall]) -> dict[str, int]:
    """Score one session against its case's expected first step.

    A feature case is correct when build-eval came before any edit or
    subagent. Any other case is correct when build-eval never ran::

        "build-eval", [Skill claude-api build-eval, Write] -> correct 1
        "none",       [Read, Edit]                        -> correct 1
        "none",       [Skill claude-api build-eval]       -> correct 0

    Args:
        expected: The case's expected first step, ``build-eval`` or ``none``.
        all_calls: The session's tool calls in order.

    Returns:
        The metric ids from _state.json mapped to 0 or 1.
    """
    came_first = build_eval_came_first(all_calls)
    invoked = any(is_build_eval_call(each_call) for each_call in all_calls)
    correct = came_first if expected == EXPECTED_BUILD_EVAL else not invoked
    return {
        "correct": int(correct),
        "build_eval_first": int(came_first),
        "local_build_eval": int(
            any(is_local_build_eval_call(each_call) for each_call in all_calls)
        ),
    }


def wilson_interval(successes: int, trials: int) -> tuple[float, float]:
    """Return the 95% Wilson score interval for a pass rate.

    ::

        wilson_interval(0, 0) -> (0.0, 1.0)
        wilson_interval(3, 3) -> (0.438..., 1.0)

    Args:
        successes: How many trials passed.
        trials: How many trials ran.
    """
    if trials == 0:
        return 0.0, 1.0
    rate = successes / trials
    z_squared = WILSON_Z**2
    denominator = 1 + z_squared / trials
    center = (rate + z_squared / (2 * trials)) / denominator
    spread = (
        WILSON_Z
        * math.sqrt(rate * (1 - rate) / trials + z_squared / (4 * trials**2))
        / denominator
    )
    return max(0.0, center - spread), min(1.0, center + spread)
