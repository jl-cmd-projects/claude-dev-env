#!/usr/bin/env python3
"""Hook that holds plain chat replies to the reply length gate's rules.

``reply_length_gate.py`` checks only the chat tools that post to Slack.
A reply typed straight into the chat is no tool call, so this hook runs
the same checks on it::

    UserPromptSubmit                         -> additionalContext states the limit
    Stop, last reply within the limit        -> allow
    Stop, last reply over the limit          -> block, reason sent back for a rewrite
    Stop, stop_hook_active (rewrite already) -> allow, so a turn never loops

The checks come from ``reply_length_gate.reply_violation``: at most
MAXIMUM_SENTENCE_COUNT sentences of at most MAXIMUM_WORDS_PER_SENTENCE
words, no mid-sentence colon, no em dash, linked pull requests, a source
for each causal claim, and no banned word.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)
blocking_directory = str(Path(__file__).resolve().parent)
if blocking_directory not in sys.path:
    sys.path.insert(0, blocking_directory)

from reply_length_gate import reply_violation
from hooks_constants.chat_reply_gate_constants import (
    ALLOW_EXIT_CODE,
    BLOCK_EXIT_CODE,
    HOOK_EVENT_NAME_INPUT_KEY,
    LAST_ASSISTANT_MESSAGE_KEY,
    REPLY_LIMIT_REMINDER,
    REWRITE_INSTRUCTION,
    STOP_EVENT_NAME,
    STOP_HOOK_ACTIVE_KEY,
    USER_PROMPT_SUBMIT_EVENT_NAME,
)
from hooks_constants.hook_block_logger import log_hook_block
from hooks_constants.hook_specific_output_keys import (
    HOOK_EVENT_NAME_KEY,
    HOOK_SPECIFIC_OUTPUT_KEY,
)
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
from hooks_constants.reply_length_gate_constants import ADDITIONAL_CONTEXT_KEY


def stop_block_reason(all_hook_input: dict[str, object]) -> str | None:
    """Return the rewrite reason for the turn's last reply, or None when it passes."""
    if all_hook_input.get(STOP_HOOK_ACTIVE_KEY) is True:
        return None
    reply_text = all_hook_input.get(LAST_ASSISTANT_MESSAGE_KEY)
    if not isinstance(reply_text, str):
        return None
    violation = reply_violation(reply_text, None, None)
    return None if violation is None else violation + REWRITE_INSTRUCTION


def write_reply_limit_reminder() -> None:
    """Print the reply limit as UserPromptSubmit additionalContext."""
    hook_event_output = {
        HOOK_EVENT_NAME_KEY: USER_PROMPT_SUBMIT_EVENT_NAME,
        ADDITIONAL_CONTEXT_KEY: REPLY_LIMIT_REMINDER,
    }
    sys.stdout.write(json.dumps({HOOK_SPECIFIC_OUTPUT_KEY: hook_event_output}))


def main() -> int:
    hook_input = read_hook_input_dictionary_from_stdin()
    if hook_input is None:
        return ALLOW_EXIT_CODE
    event_name = hook_input.get(HOOK_EVENT_NAME_INPUT_KEY)
    if event_name == USER_PROMPT_SUBMIT_EVENT_NAME:
        write_reply_limit_reminder()
        return ALLOW_EXIT_CODE
    if event_name != STOP_EVENT_NAME:
        return ALLOW_EXIT_CODE
    block_reason = stop_block_reason(hook_input)
    if block_reason is None:
        return ALLOW_EXIT_CODE
    log_hook_block(
        Path(__file__).name,
        STOP_EVENT_NAME,
        block_reason,
        offending_input_preview=str(hook_input.get(LAST_ASSISTANT_MESSAGE_KEY)),
    )
    sys.stderr.write(block_reason)
    return BLOCK_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())
