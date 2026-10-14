#!/usr/bin/env python3
"""Hook that holds plain chat replies to the reply length gate's rules.

``reply_length_gate.py`` checks only the chat tools that post to Slack.
A reply typed straight into the chat is no tool call, so this hook runs
the same checks on it::

    UserPromptSubmit                         -> additionalContext states every rule
    Stop, last reply within the limit        -> allow
    Stop, last reply over the limit          -> block, reason sent back for a rewrite
    Stop, MAXIMUM_REWRITES_PER_TURN reached  -> allow, so a turn never loops
    SessionEnd                               -> delete the rewrite count file

The rewrite count lives in one temp file per session, and each user
prompt sets it back to zero.

The checks come from ``reply_length_gate.reply_violation``: at most
MAXIMUM_SENTENCE_COUNT sentences of at most MAXIMUM_WORDS_PER_SENTENCE
words, no mid-sentence colon, no em dash, linked pull requests, a source
for each causal claim, and no banned word.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)
blocking_directory = str(Path(__file__).resolve().parent)
if blocking_directory not in sys.path:
    sys.path.insert(0, blocking_directory)

from reply_length_gate import configured_banned_words, reply_violation
from hooks_constants.chat_reply_gate_constants import (
    HOOK_EVENT_NAME_INPUT_KEY,
    LAST_ASSISTANT_MESSAGE_KEY,
    MAXIMUM_REWRITES_PER_TURN,
    REPLY_LIMIT_REMINDER,
    REWRITE_COUNT_ENCODING,
    REWRITE_COUNT_FILE_PREFIX,
    REWRITE_COUNT_FILE_SUFFIX,
    REWRITE_INSTRUCTION,
    SESSION_END_EVENT_NAME,
    SESSION_ID_KEY,
    STOP_EVENT_NAME,
    USER_PROMPT_SUBMIT_EVENT_NAME,
)
from hooks_constants.hook_block_logger import log_hook_block
from hooks_constants.hook_specific_output_keys import (
    HOOK_EVENT_NAME_KEY,
    HOOK_SPECIFIC_OUTPUT_KEY,
)
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
from hooks_constants.reply_length_gate_constants import (
    ADDITIONAL_CONTEXT_KEY,
    ALLOW_EXIT_CODE,
    BLOCK_EXIT_CODE,
)
from hooks_constants.session_file_id import session_file_id


def rewrite_count_path(session_id: object) -> Path:
    """Return the temp file that holds this session's rewrite count for the turn."""
    file_name = f"{REWRITE_COUNT_FILE_PREFIX}{session_file_id(session_id)}{REWRITE_COUNT_FILE_SUFFIX}"
    return Path(tempfile.gettempdir()) / file_name


def read_rewrite_count(count_path: Path) -> int:
    """Return the stored rewrite count, or 0 when the file is absent or unreadable."""
    try:
        return int(count_path.read_text(encoding=REWRITE_COUNT_ENCODING).strip())
    except (OSError, ValueError):
        return 0


def write_rewrite_count(count_path: Path, rewrite_count: int) -> bool:
    """Store the rewrite count and return whether the write succeeded."""
    try:
        count_path.write_text(str(rewrite_count), encoding=REWRITE_COUNT_ENCODING)
    except OSError:
        return False
    return True


def delete_rewrite_count(count_path: Path) -> None:
    """Remove the session's rewrite count file; a failed delete leaves the session unaffected."""
    try:
        count_path.unlink(missing_ok=True)
    except OSError:
        return


def stop_block_reason(all_hook_input: dict[str, object]) -> str | None:
    """Return the rewrite reason for the turn's last reply, or None when it passes."""
    reply_text = all_hook_input.get(LAST_ASSISTANT_MESSAGE_KEY)
    if not isinstance(reply_text, str):
        return None
    violation = reply_violation(reply_text, None, None)
    if violation is None:
        return None
    count_path = rewrite_count_path(all_hook_input.get(SESSION_ID_KEY))
    rewrite_count = read_rewrite_count(count_path)
    if rewrite_count >= MAXIMUM_REWRITES_PER_TURN:
        return None
    if not write_rewrite_count(count_path, rewrite_count + 1):
        return None
    return violation + REWRITE_INSTRUCTION


def write_reply_limit_reminder() -> None:
    """Print every reply rule, with the configured banned words, as UserPromptSubmit additionalContext."""
    hook_event_output = {
        HOOK_EVENT_NAME_KEY: USER_PROMPT_SUBMIT_EVENT_NAME,
        ADDITIONAL_CONTEXT_KEY: REPLY_LIMIT_REMINDER.format(
            banned_words=", ".join(configured_banned_words())
        ),
    }
    sys.stdout.write(json.dumps({HOOK_SPECIFIC_OUTPUT_KEY: hook_event_output}))


def main() -> int:
    hook_input = read_hook_input_dictionary_from_stdin()
    if hook_input is None:
        return ALLOW_EXIT_CODE
    event_name = hook_input.get(HOOK_EVENT_NAME_INPUT_KEY)
    if event_name == USER_PROMPT_SUBMIT_EVENT_NAME:
        write_rewrite_count(rewrite_count_path(hook_input.get(SESSION_ID_KEY)), 0)
        write_reply_limit_reminder()
        return ALLOW_EXIT_CODE
    if event_name == SESSION_END_EVENT_NAME:
        delete_rewrite_count(rewrite_count_path(hook_input.get(SESSION_ID_KEY)))
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
