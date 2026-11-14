"""Read the reply and the user's messages from a Stop input, for the turn review gate.

The reply comes from ``last_assistant_message`` in the Stop input, or from
the text of the last assistant message in ``transcript_path`` when that field
is missing::

    {"last_assistant_message": "Dismiss TR-1: the caller retries"}  ->  that text
    {"transcript_path": "session.jsonl"}  ->  the text of the last assistant message

The user's messages come from ``transcript_path``. Only entries with
``origin.kind`` ``human`` count, and text that starts with ``<`` is left out.
The last five are kept, each cut to 2000 characters. The transcript is read
from its newest line back, and each line is decoded once per stop.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from hooks_constants.turn_review_gate_constants import (
    ALL_TRANSCRIPT_NOT_TYPED_FLAGS,
    MAXIMUM_USER_MESSAGE_CHARACTERS,
    NESTED_TOO_DEEP_REASON,
    REPLY_TEXT_KEY,
    TRANSCRIPT_ASSISTANT_TYPE,
    TRANSCRIPT_BLOCK_TYPE_KEY,
    TRANSCRIPT_CONTENT_KEY,
    TRANSCRIPT_ENTRY_TYPE_KEY,
    TRANSCRIPT_HUMAN_ORIGIN_KIND,
    TRANSCRIPT_MARKUP_START,
    TRANSCRIPT_MESSAGE_ID_KEY,
    TRANSCRIPT_MESSAGE_KEY,
    TRANSCRIPT_ORIGIN_KEY,
    TRANSCRIPT_ORIGIN_KIND_KEY,
    TRANSCRIPT_PATH_KEY,
    TRANSCRIPT_TEXT_BLOCK_TYPE,
    TRANSCRIPT_TEXT_ENCODING,
    TRANSCRIPT_TEXT_KEY,
    TRANSCRIPT_TEXT_SEPARATOR,
    TRANSCRIPT_UNREADABLE_DIAGNOSTIC_TEMPLATE,
    TRANSCRIPT_USER_TYPE,
    USER_MESSAGE_COUNT,
)
from turn_review_state import _log


def _reversed_transcript_entries(hook_input: dict) -> Iterator[dict]:
    transcript_path = hook_input.get(TRANSCRIPT_PATH_KEY)
    if not isinstance(transcript_path, str) or not transcript_path:
        return
    try:
        all_transcript_lines = Path(transcript_path).read_text(
            encoding=TRANSCRIPT_TEXT_ENCODING, errors="replace"
        ).splitlines()
    except OSError:
        return
    for each_line in reversed(all_transcript_lines):
        try:
            transcript_entry = json.loads(each_line)
        except ValueError:
            continue
        except RecursionError:
            _log(TRANSCRIPT_UNREADABLE_DIAGNOSTIC_TEMPLATE.format(reason=NESTED_TOO_DEEP_REASON))
            continue
        if isinstance(transcript_entry, dict):
            yield transcript_entry


class _ReversedTranscript:
    """The transcript's entries, newest first, with each line decoded once per stop."""

    def __init__(self, hook_input: dict) -> None:
        self._unread_entries = _reversed_transcript_entries(hook_input)
        self._all_read_entries: list[dict] = []

    def __iter__(self) -> Iterator[dict]:
        yield from self._all_read_entries
        for each_entry in self._unread_entries:
            self._all_read_entries.append(each_entry)
            yield each_entry


def _entry_message(transcript_entry: dict) -> dict:
    message = transcript_entry.get(TRANSCRIPT_MESSAGE_KEY)
    return message if isinstance(message, dict) else {}


def _entry_text(transcript_entry: dict) -> str:
    content = _entry_message(transcript_entry).get(TRANSCRIPT_CONTENT_KEY)
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    return TRANSCRIPT_TEXT_SEPARATOR.join(
        each_block[TRANSCRIPT_TEXT_KEY]
        for each_block in content
        if isinstance(each_block, dict)
        and each_block.get(TRANSCRIPT_BLOCK_TYPE_KEY) == TRANSCRIPT_TEXT_BLOCK_TYPE
        and isinstance(each_block.get(TRANSCRIPT_TEXT_KEY), str)
    ).strip()


def _is_assistant_entry(transcript_entry: dict) -> bool:
    return transcript_entry.get(TRANSCRIPT_ENTRY_TYPE_KEY) == TRANSCRIPT_ASSISTANT_TYPE


def _last_assistant_message_text(transcript: _ReversedTranscript) -> str:
    all_text_parts: list[str] = []
    last_message_id: object = None
    for each_entry in transcript:
        is_first_assistant_entry = not all_text_parts and last_message_id is None
        if is_first_assistant_entry and not _is_assistant_entry(each_entry):
            continue
        message_id = _entry_message(each_entry).get(TRANSCRIPT_MESSAGE_ID_KEY)
        if not is_first_assistant_entry and (
            not _is_assistant_entry(each_entry) or message_id != last_message_id
        ):
            break
        all_text_parts.append(_entry_text(each_entry))
        if message_id is None:
            break
        last_message_id = message_id
    return TRANSCRIPT_TEXT_SEPARATOR.join(reversed(all_text_parts)).strip()


def _reply_text(hook_input: dict, transcript: _ReversedTranscript) -> str:
    reply_text = hook_input.get(REPLY_TEXT_KEY)
    if isinstance(reply_text, str):
        return reply_text
    return _last_assistant_message_text(transcript)


def _typed_user_text(transcript_entry: dict) -> str:
    if transcript_entry.get(TRANSCRIPT_ENTRY_TYPE_KEY) != TRANSCRIPT_USER_TYPE:
        return ""
    if any(transcript_entry.get(each_flag) for each_flag in ALL_TRANSCRIPT_NOT_TYPED_FLAGS):
        return ""
    origin = transcript_entry.get(TRANSCRIPT_ORIGIN_KEY)
    if (
        not isinstance(origin, dict)
        or origin.get(TRANSCRIPT_ORIGIN_KIND_KEY) != TRANSCRIPT_HUMAN_ORIGIN_KIND
    ):
        return ""
    typed_text = _entry_text(transcript_entry)
    return "" if typed_text.startswith(TRANSCRIPT_MARKUP_START) else typed_text


def _typed_user_messages(transcript: _ReversedTranscript) -> list[str]:
    all_messages: list[str] = []
    for each_entry in transcript:
        typed_text = _typed_user_text(each_entry)
        if typed_text:
            all_messages.append(typed_text[:MAXIMUM_USER_MESSAGE_CHARACTERS])
        if len(all_messages) == USER_MESSAGE_COUNT:
            break
    return list(reversed(all_messages))
