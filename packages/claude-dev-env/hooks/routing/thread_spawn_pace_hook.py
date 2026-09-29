#!/usr/bin/env python3
"""PreToolUse hook: reshape a thread spawn when usage runs over pace.

Registered on ``mcp__hearthbot__start_thread_session``. It runs ``usage_pace.py``
beside it, or the script ``COORDINATOR_USAGE_PACE_SCRIPT`` names.

::

    usage under pace (exit 1)          -> no output; the call runs unchanged
    over pace (exit 0) or unreadable   -> allow with updatedInput:
        model "claude-sonnet-5-5", effort "medium",
        instructions + the mandatory Fable advisor line
    input that cannot be reshaped      -> deny with a one-line reason

``updatedInput`` is the whole tool input the call runs with, so it carries
every original key.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)

from hooks_constants.bash_pre_tool_use_dispatcher_constants import (
    ALLOW_DECISION,
    HOOK_EVENT_NAME,
)
from hooks_constants.pre_tool_use_allow_output import (
    HOOK_EVENT_NAME_KEY,
    HOOK_SPECIFIC_OUTPUT_KEY,
    PERMISSION_DECISION_KEY,
    UPDATED_INPUT_KEY,
)
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
from hooks_constants.thread_spawn_pace_hook_constants import (
    ADDITIONAL_CONTEXT_KEY,
    EFFORT_INPUT_KEY,
    FABLE_ADVISOR_LINE,
    INSTRUCTIONS_ENCODING,
    INSTRUCTIONS_INPUT_KEY,
    INSTRUCTIONS_MAXIMUM_BYTES,
    INSTRUCTIONS_SEPARATOR,
    LAUNCH_FAILURE_ERROR_TEMPLATE,
    MODEL_INPUT_KEY,
    NO_INSTRUCTIONS_REASON,
    NOT_AN_OBJECT_REASON,
    OVER_BYTE_CAP_REASON_TEMPLATE,
    PACE_VERDICT_CONTEXT_MAXIMUM_CHARACTERS,
    PERMISSION_DECISION_REASON_KEY,
    PERMISSION_DENY,
    RESHAPE_CONTEXT_PREFIX,
    THREAD_EFFORT_WHEN_OVER_PACE,
    THREAD_MODEL_WHEN_OVER_PACE,
    TOOL_INPUT_KEY,
    USAGE_PACE_SCRIPT_ENV_VAR,
    USAGE_PACE_SCRIPT_FILE_NAME,
    USAGE_PACE_TIMEOUT_SECONDS,
)
from hooks_constants.usage_pace_constants import (
    EXIT_CODE_UNDER_PACE,
    EXIT_CODE_UNREADABLE,
    RESULT_KEY_ERROR,
    RESULT_KEY_OVER_PACE,
)


class SpawnNotReshapable(Exception):
    """The spawn input cannot carry the over-pace model, effort, and advisor line."""


def _instructions_with_advisor_line(instructions: str) -> str:
    reshaped_instructions = (
        instructions
        if FABLE_ADVISOR_LINE in instructions
        else f"{instructions}{INSTRUCTIONS_SEPARATOR}{FABLE_ADVISOR_LINE}"
    )
    reshaped_byte_count = len(reshaped_instructions.encode(INSTRUCTIONS_ENCODING))
    if reshaped_byte_count > INSTRUCTIONS_MAXIMUM_BYTES:
        raise SpawnNotReshapable(
            OVER_BYTE_CAP_REASON_TEMPLATE.format(
                reshaped_byte_count=reshaped_byte_count,
                maximum_bytes=INSTRUCTIONS_MAXIMUM_BYTES,
                excess_byte_count=reshaped_byte_count - INSTRUCTIONS_MAXIMUM_BYTES,
            )
        )
    return reshaped_instructions


def reshape_thread_spawn(tool_input: object) -> dict[str, object]:
    """Move a thread spawn to Sonnet at medium effort with a Fable advisor line.

    ::

        {"title": "t", "instructions": "Do X."}
        -> {"title": "t", "instructions": "Do X.\\n\\nMandatory Fable advisor: ...",
            "model": "claude-sonnet-5-5", "effort": "medium"}

    An instructions text that already carries the advisor line keeps one copy.

    Args:
        tool_input: The ``tool_input`` object of the start_thread_session call.

    Raises:
        SpawnNotReshapable: The input is not an object, has no instructions
            text, or would pass the server's instructions byte cap.
    """
    if not isinstance(tool_input, dict):
        raise SpawnNotReshapable(NOT_AN_OBJECT_REASON)
    instructions = tool_input.get(INSTRUCTIONS_INPUT_KEY)
    if not isinstance(instructions, str):
        raise SpawnNotReshapable(NO_INSTRUCTIONS_REASON)
    return {
        **tool_input,
        MODEL_INPUT_KEY: THREAD_MODEL_WHEN_OVER_PACE,
        EFFORT_INPUT_KEY: THREAD_EFFORT_WHEN_OVER_PACE,
        INSTRUCTIONS_INPUT_KEY: _instructions_with_advisor_line(instructions),
    }


def _hook_output(all_decision_fields: dict[str, object]) -> dict[str, object]:
    return {
        HOOK_SPECIFIC_OUTPUT_KEY: {
            HOOK_EVENT_NAME_KEY: HOOK_EVENT_NAME,
            **all_decision_fields,
        }
    }


def _deny_output(reason: str) -> dict[str, object]:
    return _hook_output(
        {PERMISSION_DECISION_KEY: PERMISSION_DENY, PERMISSION_DECISION_REASON_KEY: reason}
    )


def decide_hook_output(
    tool_input: object, pace_exit_code: int, pace_verdict_text: str
) -> dict[str, object] | None:
    """Choose the hook's output for one spawn and one pace reading.

    Args:
        tool_input: The ``tool_input`` of the PreToolUse payload, or None when
            stdin held no JSON object.
        pace_exit_code: The usage-pace exit code; anything but under pace
            counts as over pace.
        pace_verdict_text: The usage-pace stdout, quoted into the context.

    Returns:
        None to pass the call through unchanged, else the hook JSON output.
    """
    if pace_exit_code == EXIT_CODE_UNDER_PACE:
        return None
    try:
        reshaped_input = reshape_thread_spawn(tool_input)
    except SpawnNotReshapable as not_reshapable:
        return _deny_output(str(not_reshapable))
    verdict_excerpt = pace_verdict_text.strip()[:PACE_VERDICT_CONTEXT_MAXIMUM_CHARACTERS]
    return _hook_output(
        {
            PERMISSION_DECISION_KEY: ALLOW_DECISION,
            UPDATED_INPUT_KEY: reshaped_input,
            ADDITIONAL_CONTEXT_KEY: RESHAPE_CONTEXT_PREFIX + verdict_excerpt,
        }
    )


def run_usage_pace() -> tuple[int, str]:
    """Run the usage-pace script and return its exit code and stdout.

    Returns:
        The exit code and stdout. A missing script, a launch failure, or a
        timeout returns the unreadable exit code.
    """
    pace_script = os.environ.get(USAGE_PACE_SCRIPT_ENV_VAR) or str(
        Path(__file__).resolve().parent / USAGE_PACE_SCRIPT_FILE_NAME
    )
    try:
        completed = subprocess.run(
            [sys.executable, pace_script],
            capture_output=True,
            text=True,
            timeout=USAGE_PACE_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as launch_error:
        return EXIT_CODE_UNREADABLE, json.dumps(
            {
                RESULT_KEY_OVER_PACE: None,
                RESULT_KEY_ERROR: LAUNCH_FAILURE_ERROR_TEMPLATE.format(
                    failure_type=type(launch_error).__name__
                ),
            }
        )
    return completed.returncode, completed.stdout


def main() -> int:
    """Read the PreToolUse payload, read the pace, and print the decision.

    Returns:
        0 in every case; a deny travels in the JSON output.
    """
    hook_payload = read_hook_input_dictionary_from_stdin()
    tool_input = hook_payload.get(TOOL_INPUT_KEY) if hook_payload is not None else None
    pace_exit_code, pace_verdict_text = run_usage_pace()
    hook_output = decide_hook_output(tool_input, pace_exit_code, pace_verdict_text)
    if hook_output is not None:
        sys.stdout.write(json.dumps(hook_output))
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
