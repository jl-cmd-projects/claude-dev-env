#!/usr/bin/env python3
"""Hook that holds plain chat replies to the reply length gate's rules.

``reply_length_gate.py`` checks only the chat tools that post to Slack.
A reply typed straight into the chat is no tool call, so this hook runs
the same checks on it::

    UserPromptSubmit                         -> additionalContext states the limit
    PostToolUse, text before the call fits   -> allow
    PostToolUse, text before the call breaks -> exit 2, reason sent back mid-turn
    Stop, last reply within the limit        -> allow
    Stop, last reply over the limit          -> block, reason sent back for a rewrite
    Stop, MAXIMUM_REWRITES_PER_TURN reached  -> allow, so a turn never loops
    SessionEnd                               -> delete the rewrite count file

On PostToolUse the hook reads the transcript and checks the text blocks
that sit between the last user entry and this call. Sibling calls in one
message share that text, so only the first call checks it. A subagent
call, and a call that does not appear in the transcript before the poll
limit, pass without a check.

The rewrite count lives in one temp file per session. Each user prompt
sets it back to zero, and so does each Stop whose ``stop_hook_active``
is not true, because that Stop ends a fresh reply and not a rewrite.

The checks come from ``reply_length_gate.reply_violation``: at most
MAXIMUM_SENTENCE_COUNT sentences of at most MAXIMUM_WORDS_PER_SENTENCE
words, no mid-sentence colon, no em dash, linked pull requests, a source
for each causal claim, and no banned word.
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)
blocking_directory = str(Path(__file__).resolve().parent)
if blocking_directory not in sys.path:
    sys.path.insert(0, blocking_directory)

from reply_length_gate import reply_violation
from step_note_gate import read_transcript_tail, tool_use_position, transcript_blocks
from hooks_constants.chat_reply_gate_constants import (
    AGENT_ID_KEY,
    HOOK_EVENT_NAME_INPUT_KEY,
    LAST_ASSISTANT_MESSAGE_KEY,
    MAXIMUM_REWRITES_PER_TURN,
    MID_TURN_INSTRUCTION,
    MID_TURN_TEXT_PREFIX,
    MID_TURN_TEXT_SEPARATOR,
    POST_TOOL_USE_EVENT_NAME,
    REPLY_LIMIT_REMINDER,
    REWRITE_COUNT_ENCODING,
    REWRITE_COUNT_FILE_PREFIX,
    REWRITE_COUNT_FILE_SUFFIX,
    REWRITE_INSTRUCTION,
    SESSION_END_EVENT_NAME,
    SESSION_ID_KEY,
    STOP_EVENT_NAME,
    STOP_HOOK_ACTIVE_KEY,
    TOOL_USE_ID_KEY,
    TRANSCRIPT_PATH_KEY,
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
from hooks_constants.step_note_gate_constants import (
    POLL_INTERVAL_SECONDS,
    POLL_LIMIT_SECONDS,
    TEXT_BLOCK_TYPE,
    TOOL_USE_BLOCK_TYPE,
    USER_ROLE,
)


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
    is_rewrite_of_blocked_reply = all_hook_input.get(STOP_HOOK_ACTIVE_KEY) is True
    rewrite_count = read_rewrite_count(count_path) if is_rewrite_of_blocked_reply else 0
    if rewrite_count >= MAXIMUM_REWRITES_PER_TURN:
        return None
    if not write_rewrite_count(count_path, rewrite_count + 1):
        return None
    return violation + REWRITE_INSTRUCTION


def text_before_call(all_entries: list[dict], tool_use_id: str) -> str | None:
    """Return the text that opens the step holding this call, or None when the call is not written.

    A sibling call later in the same message gets an empty string, since the
    first call of the message owns the text.
    """
    all_blocks = list(transcript_blocks(all_entries))
    call_position = tool_use_position(all_blocks, tool_use_id)
    if call_position is None:
        return None
    all_texts_newest_first: list[str] = []
    for each_role, each_block in reversed(all_blocks[:call_position]):
        if each_role == USER_ROLE or each_block.get("type") == TOOL_USE_BLOCK_TYPE:
            break
        if each_block.get("type") == TEXT_BLOCK_TYPE:
            all_texts_newest_first.append(str(each_block.get("text", "")))
    return MID_TURN_TEXT_SEPARATOR.join(reversed(all_texts_newest_first))


def wait_for_text_before_call(transcript_path: Path, tool_use_id: str) -> str | None:
    """Poll the transcript tail until this call is written, then return the text before it."""
    deadline = time.monotonic() + POLL_LIMIT_SECONDS
    while True:
        mid_turn_text = text_before_call(read_transcript_tail(transcript_path), tool_use_id)
        if mid_turn_text is not None or time.monotonic() >= deadline:
            return mid_turn_text
        time.sleep(POLL_INTERVAL_SECONDS)


def mid_turn_block_reason(all_hook_input: dict[str, object]) -> tuple[str, str] | None:
    """Return the block reason and the text that tripped it, or None when the call passes."""
    if all_hook_input.get(AGENT_ID_KEY):
        return None
    tool_use_id = all_hook_input.get(TOOL_USE_ID_KEY)
    transcript_path = all_hook_input.get(TRANSCRIPT_PATH_KEY)
    if not isinstance(tool_use_id, str) or not isinstance(transcript_path, str):
        return None
    if not tool_use_id or not transcript_path:
        return None
    mid_turn_text = wait_for_text_before_call(Path(transcript_path), tool_use_id)
    if not mid_turn_text:
        return None
    violation = reply_violation(mid_turn_text, None, None)
    if violation is None:
        return None
    return MID_TURN_TEXT_PREFIX + violation + MID_TURN_INSTRUCTION, mid_turn_text


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
        count_path = rewrite_count_path(hook_input.get(SESSION_ID_KEY))
        if not write_rewrite_count(count_path, 0):
            delete_rewrite_count(count_path)
        write_reply_limit_reminder()
        return ALLOW_EXIT_CODE
    if event_name == SESSION_END_EVENT_NAME:
        delete_rewrite_count(rewrite_count_path(hook_input.get(SESSION_ID_KEY)))
        return ALLOW_EXIT_CODE
    if event_name == POST_TOOL_USE_EVENT_NAME:
        mid_turn_block = mid_turn_block_reason(hook_input)
        if mid_turn_block is None:
            return ALLOW_EXIT_CODE
        block_reason, offending_preview = mid_turn_block
    elif event_name == STOP_EVENT_NAME:
        block_reason = stop_block_reason(hook_input)
        if block_reason is None:
            return ALLOW_EXIT_CODE
        offending_preview = str(hook_input.get(LAST_ASSISTANT_MESSAGE_KEY))
    else:
        return ALLOW_EXIT_CODE
    log_hook_block(
        Path(__file__).name,
        str(event_name),
        block_reason,
        offending_input_preview=offending_preview,
    )
    sys.stderr.write(block_reason)
    return BLOCK_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())
