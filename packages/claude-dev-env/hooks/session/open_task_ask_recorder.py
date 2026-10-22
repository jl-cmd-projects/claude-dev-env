#!/usr/bin/env python3
"""UserPromptSubmit hook that records each prompt for the open tasks Stop gate.

A prompt that asks for work becomes ``#ask-N`` in
``~/.claude/open-task-asks/<session id>.json``. The gate then holds the turn
until a reply closes it with ``Done: #ask-N``, or with
``Dropped: #ask-N - "<the user's words>"`` quoting a later prompt. The hook
prints nothing and always exits 0.
"""

from __future__ import annotations

import sys
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)

from hooks_constants.open_tasks_stop_gate_constants import (
    ALLOW_EXIT_CODE,
    PROMPT_KEY,
    SESSION_ID_KEY,
)
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
from open_task_asks import record_prompt


def main() -> int:
    hook_input = read_hook_input_dictionary_from_stdin()
    prompt_value = hook_input.get(PROMPT_KEY) if hook_input is not None else None
    if hook_input is not None and isinstance(prompt_value, str):
        record_prompt(hook_input.get(SESSION_ID_KEY), prompt_value)
    return ALLOW_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())
