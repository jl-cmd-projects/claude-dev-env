#!/usr/bin/env python3
"""Hook that shows the user one short chat reply per message.

``reply_length_gate.py`` checks only the chat tools that post to Slack.
A reply typed straight into the chat is no tool call, so this hook runs
the same checks on it::

    UserPromptSubmit                       -> additionalContext states the rules
    MessageDisplay, batch before the last  -> hold the text, show nothing yet
    MessageDisplay, last batch, passes     -> show the whole message
    MessageDisplay, last batch, fails      -> show a draft from a small model that passes

A Stop hook would see the reply only after it is on screen, so each block
would add a second reply under the first. MessageDisplay changes the text
before it renders. The transcript keeps the original, so the next
UserPromptSubmit tells the agent the text the user saw.

The draft comes from ``claude -p`` on DEFAULT_DRAFTER_MODEL with no setting
sources and no tools. The draft must pass ``reply_violation``; after
MAXIMUM_DRAFT_ATTEMPTS failed drafts, the original shows.

The checks come from ``reply_length_gate.reply_violation``: at most
MAXIMUM_SENTENCE_COUNT sentences of at most MAXIMUM_WORDS_PER_SENTENCE
words, no mid-sentence colon, no em dash, linked pull requests, a source
for each causal claim, and no banned word.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)
blocking_directory = str(Path(__file__).resolve().parent)
if blocking_directory not in sys.path:
    sys.path.insert(0, blocking_directory)

from reply_length_gate import reply_violation
from hooks_constants.chat_reply_gate_constants import (
    CLAUDE_SESSION_ID_ENV_VAR,
    DEFAULT_DRAFTER_MODEL,
    DELTA_KEY,
    DISPLAY_CONTENT_KEY,
    DRAFTER_GUARD_ENV_VAR,
    DRAFTER_MODEL_ENV_VAR,
    DRAFTER_REQUEST_TEMPLATE,
    DRAFTER_ERROR_KEY,
    DRAFTER_RESULT_KEY,
    DRAFTER_RULES,
    DRAFTER_TIMEOUT_SECONDS,
    FINAL_KEY,
    HELD_TEXT_FILE_PREFIX,
    HOOK_EVENT_NAME_INPUT_KEY,
    MAXIMUM_DRAFT_ATTEMPTS,
    MESSAGE_DISPLAY_EVENT_NAME,
    MESSAGE_ID_KEY,
    REPLY_LIMIT_REMINDER,
    SESSION_END_EVENT_NAME,
    SESSION_ID_KEY,
    SHOWN_DRAFT_FILE_PREFIX,
    SHOWN_DRAFT_PREFIX,
    STATE_FILE_ENCODING,
    STATE_FILE_SUFFIX,
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
)
from hooks_constants.session_file_id import session_file_id


def state_file_path(file_prefix: str, state_key: object) -> Path:
    """Return the temp file that holds one message's held text or one session's shown draft."""
    file_name = f"{file_prefix}{session_file_id(state_key)}{STATE_FILE_SUFFIX}"
    return Path(tempfile.gettempdir()) / file_name


def read_state_text(state_path: Path) -> str:
    """Return the stored text, or an empty string when the file is absent or unreadable."""
    try:
        return state_path.read_text(encoding=STATE_FILE_ENCODING)
    except OSError:
        return ""


def write_state_text(state_path: Path, state_text: str) -> None:
    """Store the text; a failed write leaves the shown text unchanged."""
    try:
        state_path.write_text(state_text, encoding=STATE_FILE_ENCODING)
    except OSError:
        return


def drafter_command() -> list[str]:
    """Return the headless claude command that drafts with no settings and no tools."""
    return [
        "claude",
        "-p",
        "--model",
        os.environ.get(DRAFTER_MODEL_ENV_VAR, DEFAULT_DRAFTER_MODEL),
        "--setting-sources",
        "",
        "--tools",
        "",
        "--no-session-persistence",
        "--session-id",
        str(uuid.uuid4()),
        "--output-format",
        "json",
        "--system-prompt",
        DRAFTER_RULES,
    ]


def drafter_environment() -> dict[str, str]:
    """Return the drafter's environment, marked so this hook exits inside it."""
    environment = dict(os.environ)
    environment[DRAFTER_GUARD_ENV_VAR] = "1"
    environment.pop(CLAUDE_SESSION_ID_ENV_VAR, None)
    return environment


def ask_drafter(reply_text: str, violation: str) -> str | None:
    """Return one draft from the small model, or None when the call fails."""
    try:
        completed = subprocess.run(
            drafter_command(),
            input=DRAFTER_REQUEST_TEMPLATE.format(violation=violation, reply_text=reply_text),
            capture_output=True,
            text=True,
            timeout=DRAFTER_TIMEOUT_SECONDS,
            env=drafter_environment(),
            check=False,
        )
        drafter_output = json.loads(completed.stdout)
        draft_text = drafter_output.get(DRAFTER_RESULT_KEY)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError, AttributeError):
        return None
    if drafter_output.get(DRAFTER_ERROR_KEY) is True:
        return None
    if not isinstance(draft_text, str) or not draft_text.strip():
        return None
    return draft_text.strip()


def compliant_draft(reply_text: str, violation: str) -> str | None:
    """Return a draft that passes ``reply_violation``, or None after MAXIMUM_DRAFT_ATTEMPTS."""
    current_violation = violation
    for _ in range(MAXIMUM_DRAFT_ATTEMPTS):
        draft_text = ask_drafter(reply_text, current_violation)
        if draft_text is None:
            continue
        draft_violation = reply_violation(draft_text, None, None)
        if draft_violation is None:
            return draft_text
        current_violation = draft_violation
    return None


def shown_text(all_hook_input: dict[str, object]) -> str | None:
    """Return the text to show for this batch, or None to show the batch as it is."""
    message_id = all_hook_input.get(MESSAGE_ID_KEY)
    if not isinstance(message_id, str) or not message_id:
        return None
    held_path = state_file_path(HELD_TEXT_FILE_PREFIX, message_id)
    held_text = read_state_text(held_path)
    message_text = held_text + str(all_hook_input.get(DELTA_KEY) or "")
    if not all_hook_input.get(FINAL_KEY):
        write_state_text(held_path, message_text)
        return ""
    held_path.unlink(missing_ok=True)
    violation = reply_violation(message_text, None, None)
    if violation is None:
        return message_text if held_text else None
    draft_text = compliant_draft(message_text, violation)
    if draft_text is None:
        return message_text if held_text else None
    write_state_text(
        state_file_path(SHOWN_DRAFT_FILE_PREFIX, all_hook_input.get(SESSION_ID_KEY)), draft_text
    )
    log_hook_block(
        Path(__file__).name,
        MESSAGE_DISPLAY_EVENT_NAME,
        violation,
        offending_input_preview=message_text,
    )
    return draft_text


def write_hook_output(event_name: str, output_key: str, output_text: str) -> None:
    """Print one hookSpecificOutput field for the event."""
    hook_event_output = {HOOK_EVENT_NAME_KEY: event_name, output_key: output_text}
    sys.stdout.write(json.dumps({HOOK_SPECIFIC_OUTPUT_KEY: hook_event_output}))


def reply_limit_reminder(session_id: object) -> str:
    """Return the reply rules, plus the draft the user saw in place of the last reply."""
    shown_draft_path = state_file_path(SHOWN_DRAFT_FILE_PREFIX, session_id)
    shown_draft = read_state_text(shown_draft_path)
    if not shown_draft:
        return REPLY_LIMIT_REMINDER
    shown_draft_path.unlink(missing_ok=True)
    return REPLY_LIMIT_REMINDER + SHOWN_DRAFT_PREFIX + shown_draft


def main() -> int:
    if os.environ.get(DRAFTER_GUARD_ENV_VAR):
        return ALLOW_EXIT_CODE
    hook_input = read_hook_input_dictionary_from_stdin()
    if hook_input is None:
        return ALLOW_EXIT_CODE
    event_name = hook_input.get(HOOK_EVENT_NAME_INPUT_KEY)
    if event_name == USER_PROMPT_SUBMIT_EVENT_NAME:
        write_hook_output(
            USER_PROMPT_SUBMIT_EVENT_NAME,
            ADDITIONAL_CONTEXT_KEY,
            reply_limit_reminder(hook_input.get(SESSION_ID_KEY)),
        )
        return ALLOW_EXIT_CODE
    if event_name == SESSION_END_EVENT_NAME:
        state_file_path(SHOWN_DRAFT_FILE_PREFIX, hook_input.get(SESSION_ID_KEY)).unlink(missing_ok=True)
        return ALLOW_EXIT_CODE
    if event_name != MESSAGE_DISPLAY_EVENT_NAME:
        return ALLOW_EXIT_CODE
    display_text = shown_text(hook_input)
    if display_text is not None:
        write_hook_output(MESSAGE_DISPLAY_EVENT_NAME, DISPLAY_CONTENT_KEY, display_text)
    return ALLOW_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())
