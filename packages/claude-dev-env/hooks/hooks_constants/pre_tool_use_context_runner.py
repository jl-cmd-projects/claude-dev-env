"""Shared main loop for PreToolUse hooks that only add context.

Reads the payload from stdin, asks the hook's decide function for an output,
and writes it as JSON. Exit status is always 0, so the tool call runs.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable

from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin


def run_context_hook(
    decide_hook_output: Callable[[dict[str, object]], dict[str, object] | None],
) -> int:
    """Print the decided output for the stdin payload, or nothing.

    Args:
        decide_hook_output: Maps the parsed payload to an output or None.

    Returns:
        0 in every case; the context travels in the JSON output.
    """
    hook_payload = read_hook_input_dictionary_from_stdin()
    if hook_payload is None:
        return 0
    hook_output = decide_hook_output(hook_payload)
    if hook_output is not None:
        sys.stdout.write(json.dumps(hook_output))
        sys.stdout.flush()
    return 0
