"""Per-session record of the user's prompts, read by the open tasks Stop gate.

Every prompt lands in one file outside the task store::

    ~/.claude/open-task-asks/<session id>.json
    {"prompts": [{"text": "...", "recorded_at": 1761076800.0, "ask_id": "ask-1"}, ...]}

A prompt that asks for work gets the next ``ask-N`` id. A question-only
prompt, an acknowledgement such as ``thanks!``, an empty prompt, and a harness envelope such as
``<task-notification>`` get ``ask_id`` null, and the gate still reads their
text when it checks the quote on a ``Dropped:`` line.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import NamedTuple

from atomic_file_writer import write_text_atomically
from hooks_constants.open_tasks_stop_gate_constants import (
    ACKNOWLEDGEMENT_PATTERN,
    ASK_ID_TEMPLATE,
    ASK_PROMPT_ID_KEY,
    ASK_PROMPT_RECORDED_AT_KEY,
    ASK_PROMPT_TEXT_KEY,
    ASKS_DIRECTORY_NAME,
    ASKS_FILE_SUFFIX,
    ASKS_PROMPTS_KEY,
    ASKS_TEMPORARY_PREFIX,
    ASKS_TEMPORARY_SUFFIX,
    CLAUDE_CONFIG_DIRECTORY_ENVIRONMENT_VARIABLE,
    CLAUDE_HOME_DIRECTORY_NAME,
    INTERROGATIVE_START_PATTERN,
    POLITE_REQUEST_START_PATTERN,
    QUESTION_END_PATTERN,
    SAFE_SESSION_ID_PATTERN,
    SENTENCE_SPLIT_PATTERN,
    UTF8_ENCODING,
    YES_OR_NO_END_PATTERN,
)
from hooks_constants.spawn_readiness_hook_constants import ALL_HARNESS_ENVELOPE_MARKERS


class RecordedPrompt(NamedTuple):
    """One prompt the user sent.

    Attributes:
        text: The prompt as the user sent it.
        recorded_at: Seconds since the epoch when the recorder saw it.
        ask_id: ``ask-N`` for a prompt that asks for work, or None.
    """

    text: str
    recorded_at: float
    ask_id: str | None


def claude_home() -> Path:
    """Return the Claude home directory, honoring ``CLAUDE_CONFIG_DIR``."""
    configured_directory = os.environ.get(CLAUDE_CONFIG_DIRECTORY_ENVIRONMENT_VARIABLE)
    if configured_directory:
        return Path(configured_directory)
    return Path.home() / CLAUDE_HOME_DIRECTORY_NAME


def _asks_file(session_id: object) -> Path | None:
    if not isinstance(session_id, str) or not re.fullmatch(SAFE_SESSION_ID_PATTERN, session_id):
        return None
    return claude_home() / ASKS_DIRECTORY_NAME / (session_id + ASKS_FILE_SUFFIX)


def is_question_only(prompt_text: str) -> bool:
    """Return True when the prompt asks a question and asks for no work.

    ::

        "did the export fail?"                      -> True
        "are you monitoring these? yes or no"       -> True
        "can you check the release dates in neon?"  -> False
        "Export the APKs and submit them"           -> False
    """
    all_sentences = [
        each_part.strip()
        for each_part in re.split(SENTENCE_SPLIT_PATTERN, prompt_text.strip())
        if each_part.strip()
    ]
    if not all_sentences or re.search(POLITE_REQUEST_START_PATTERN, prompt_text, re.IGNORECASE):
        return False
    if all(re.search(QUESTION_END_PATTERN, each_sentence) for each_sentence in all_sentences):
        return True
    return bool(
        re.search(YES_OR_NO_END_PATTERN, all_sentences[-1], re.IGNORECASE)
        and re.search(INTERROGATIVE_START_PATTERN, all_sentences[0], re.IGNORECASE)
    )


def is_ask(prompt_text: str) -> bool:
    """Return True when the prompt asks for work the gate should hold the turn for."""
    stripped_text = prompt_text.strip()
    if not stripped_text or stripped_text.startswith(ALL_HARNESS_ENVELOPE_MARKERS):
        return False
    if re.fullmatch(ACKNOWLEDGEMENT_PATTERN, stripped_text, re.IGNORECASE):
        return False
    return not is_question_only(stripped_text)


def recorded_prompts(session_id: object) -> list[RecordedPrompt]:
    """Return every prompt recorded for the session, oldest first."""
    asks_file = _asks_file(session_id)
    if asks_file is None:
        return []
    try:
        all_file_fields = json.loads(asks_file.read_text(encoding=UTF8_ENCODING))
    except (OSError, ValueError):
        return []
    all_entries = (
        all_file_fields.get(ASKS_PROMPTS_KEY) if isinstance(all_file_fields, dict) else None
    )
    if not isinstance(all_entries, list):
        return []
    return [
        _parsed_prompt(each_entry) for each_entry in all_entries if isinstance(each_entry, dict)
    ]


def _parsed_prompt(all_entry_fields: dict[str, object]) -> RecordedPrompt:
    recorded_at = all_entry_fields.get(ASK_PROMPT_RECORDED_AT_KEY)
    ask_id = all_entry_fields.get(ASK_PROMPT_ID_KEY)
    return RecordedPrompt(
        str(all_entry_fields.get(ASK_PROMPT_TEXT_KEY, "")),
        float(recorded_at) if isinstance(recorded_at, (int, float)) else 0.0,
        ask_id if isinstance(ask_id, str) else None,
    )


def record_prompt(session_id: object, prompt_text: str) -> str | None:
    """Append the prompt to the session's file and return its ``ask-N`` id, or None for no ask."""
    asks_file = _asks_file(session_id)
    if asks_file is None:
        return None
    all_prompts = recorded_prompts(session_id)
    ask_count = sum(1 for each_prompt in all_prompts if each_prompt.ask_id)
    ask_id = ASK_ID_TEMPLATE.format(ask_number=ask_count + 1) if is_ask(prompt_text) else None
    all_prompts.append(RecordedPrompt(prompt_text, time.time(), ask_id))
    serialized_text = json.dumps(
        {ASKS_PROMPTS_KEY: [each_prompt._asdict() for each_prompt in all_prompts]}
    )
    try:
        write_text_atomically(
            asks_file,
            serialized_text,
            UTF8_ENCODING,
            ASKS_TEMPORARY_PREFIX,
            ASKS_TEMPORARY_SUFFIX,
            False,
        )
    except OSError:
        return None
    return ask_id
