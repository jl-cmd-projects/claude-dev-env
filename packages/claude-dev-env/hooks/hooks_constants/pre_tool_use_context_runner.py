"""Shared main loop for PreToolUse hooks that print a decided JSON output.

Reads the payload from stdin, asks the hook's decide function for an output,
and writes it as JSON. The output may add context or deny the call. Exit
status is always 0. A decide function that raises leaves the call with no
output and writes one line to stderr that names the crash::

    spawn_oversight_hook.py: crashed, the call goes through: KeyError: 'prompt'
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Callable
from pathlib import Path

from hooks_constants.pre_tool_use_context_runner_constants import (
    CRASH_LINE_TEMPLATE,
    LINE_BREAK_PATTERN,
    LINE_BREAK_REPLACEMENT,
)
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin


def _write_crash_line(crash: Exception) -> None:
    sys.stderr.write(
        CRASH_LINE_TEMPLATE.format(
            hook_name=Path(sys.argv[0]).name,
            crash_type=type(crash).__name__,
            crash_text=re.sub(LINE_BREAK_PATTERN, LINE_BREAK_REPLACEMENT, str(crash)).strip(),
        )
    )


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
    try:
        hook_output = decide_hook_output(hook_payload)
    except Exception as crash:
        _write_crash_line(crash)
        return 0
    if hook_output is not None:
        sys.stdout.write(json.dumps(hook_output))
        sys.stdout.flush()
    return 0
