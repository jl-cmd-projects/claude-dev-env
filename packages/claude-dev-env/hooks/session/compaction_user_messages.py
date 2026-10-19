#!/usr/bin/env python3
"""Read every message the user typed from a Claude Code or Codex transcript.

::

    Claude Code entry {"type": "user", "message": {"content": "fix login"}}
    Codex entry {"type": "event_msg",
                 "payload": {"type": "user_message", "message": "fix login"}}
    -> TypedMessage(position=1, timestamp=..., text="fix login")

The compaction recall hook trims these messages and returns them to the
agent after a compaction. The whole transcript is read each time, so a second
compaction yields the same messages plus the newer ones.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

_hooks_directory = str(Path(__file__).resolve().parent.parent)
if _hooks_directory not in sys.path:
    sys.path.insert(0, _hooks_directory)

from hooks_constants.compaction_user_messages_constants import (
    ALL_SKIPPED_ENTRY_FLAGS,
    ASSISTANT_ENTRY_TYPE,
    ATTACHMENT_ENTRY_TYPE,
    ATTACHMENT_KEY,
    BLOCK_SEPARATOR,
    BLOCK_TYPE_KEY,
    CODEX_AGENT_MESSAGE_TYPE,
    CODEX_EVENT_ENTRY_TYPE,
    CODEX_IMAGES_KEY,
    CODEX_PAYLOAD_KEY,
    CODEX_USER_MESSAGE_TYPE,
    CONTENT_KEY,
    ENTRY_TYPE_KEY,
    HARNESS_TAG_OPENING_PATTERN,
    HUMAN_ORIGIN_KIND,
    IMAGE_BLOCK_TYPE,
    IMAGE_PLACEHOLDER,
    MESSAGE_KEY,
    ORIGIN_KEY,
    ORIGIN_KIND_KEY,
    QUEUED_COMMAND_ATTACHMENT_TYPE,
    QUEUED_PROMPT_KEY,
    SLASH_COMMAND_ARGS_PATTERN,
    SLASH_COMMAND_NAME_PATTERN,
    TEXT_BLOCK_TYPE,
    TEXT_KEY,
    TIMESTAMP_KEY,
    USER_ENTRY_TYPE,
)


@dataclass(frozen=True)
class TypedMessage:
    """One message the user typed, numbered by its place among all typed messages.

    Attributes:
        position: 1 for the first typed message, counting up.
        timestamp: The transcript timestamp, or an empty string.
        text: The message text, with a slash command shown as ``/name args``.
    """

    position: int
    timestamp: str
    text: str


def _parsed_entry(transcript_line: str) -> dict[str, object]:
    try:
        parsed_entry = json.loads(transcript_line)
    except json.JSONDecodeError:
        return {}
    return parsed_entry if isinstance(parsed_entry, dict) else {}


def _block_text(block: object) -> str | None:
    if not isinstance(block, dict):
        return None
    if block.get(BLOCK_TYPE_KEY) == TEXT_BLOCK_TYPE:
        return str(block.get(TEXT_KEY, ""))
    if block.get(BLOCK_TYPE_KEY) == IMAGE_BLOCK_TYPE:
        return IMAGE_PLACEHOLDER
    return None


def _content_text(content: object) -> str:
    if isinstance(content, str):
        return content
    all_blocks = content if isinstance(content, list) else []
    all_parts = [_block_text(each_block) for each_block in all_blocks]
    return BLOCK_SEPARATOR.join(each_part for each_part in all_parts if each_part is not None)


def _typed_text(raw_text: str) -> str | None:
    stripped_text = raw_text.strip()
    command_name = SLASH_COMMAND_NAME_PATTERN.search(stripped_text)
    if command_name:
        command_args = SLASH_COMMAND_ARGS_PATTERN.search(stripped_text)
        typed_args = command_args.group(1).strip() if command_args else ""
        return f"{command_name.group(1)} {typed_args}".strip()
    if not stripped_text or HARNESS_TAG_OPENING_PATTERN.match(stripped_text):
        return None
    return stripped_text


def _is_typed_by_a_person(all_entry_fields: dict[str, object]) -> bool:
    if any(all_entry_fields.get(each_flag) for each_flag in ALL_SKIPPED_ENTRY_FLAGS):
        return False
    origin = all_entry_fields.get(ORIGIN_KEY)
    return not isinstance(origin, dict) or origin.get(ORIGIN_KIND_KEY) == HUMAN_ORIGIN_KIND


def _codex_payload(all_entry_fields: dict[str, object]) -> dict[str, object]:
    if all_entry_fields.get(ENTRY_TYPE_KEY) != CODEX_EVENT_ENTRY_TYPE:
        return {}
    payload = all_entry_fields.get(CODEX_PAYLOAD_KEY)
    return payload if isinstance(payload, dict) else {}


def _codex_user_text(all_payload_fields: dict[str, object]) -> str | None:
    message = all_payload_fields.get(MESSAGE_KEY)
    typed_text = _typed_text(message) if isinstance(message, str) else None
    if not all_payload_fields.get(CODEX_IMAGES_KEY):
        return typed_text
    return BLOCK_SEPARATOR.join(
        each_part for each_part in (typed_text, IMAGE_PLACEHOLDER) if each_part
    )


def _is_assistant_turn(all_entry_fields: dict[str, object]) -> bool:
    if all_entry_fields.get(ENTRY_TYPE_KEY) == ASSISTANT_ENTRY_TYPE:
        return True
    return _codex_payload(all_entry_fields).get(ENTRY_TYPE_KEY) == CODEX_AGENT_MESSAGE_TYPE


def _entry_text(all_entry_fields: dict[str, object]) -> str | None:
    entry_type = all_entry_fields.get(ENTRY_TYPE_KEY)
    codex_payload = _codex_payload(all_entry_fields)
    if codex_payload.get(ENTRY_TYPE_KEY) == CODEX_USER_MESSAGE_TYPE:
        return _codex_user_text(codex_payload)
    if entry_type == USER_ENTRY_TYPE and _is_typed_by_a_person(all_entry_fields):
        message = all_entry_fields.get(MESSAGE_KEY)
        content = message.get(CONTENT_KEY) if isinstance(message, dict) else None
        return _typed_text(_content_text(content))
    if entry_type != ATTACHMENT_ENTRY_TYPE:
        return None
    attachment = all_entry_fields.get(ATTACHMENT_KEY)
    if not isinstance(attachment, dict):
        return None
    if attachment.get(ENTRY_TYPE_KEY) != QUEUED_COMMAND_ATTACHMENT_TYPE:
        return None
    queued_prompt = attachment.get(QUEUED_PROMPT_KEY)
    return _typed_text(queued_prompt) if isinstance(queued_prompt, str) else None


def _typed_texts(all_transcript_lines: Iterable[str]) -> Iterator[tuple[str, str]]:
    previous_text = None
    for each_line in all_transcript_lines:
        all_entry_fields = _parsed_entry(each_line)
        if _is_assistant_turn(all_entry_fields):
            previous_text = None
            continue
        entry_text = _entry_text(all_entry_fields)
        if entry_text is None or entry_text == previous_text:
            continue
        previous_text = entry_text
        yield str(all_entry_fields.get(TIMESTAMP_KEY, "")), entry_text


def typed_user_messages(all_transcript_lines: Iterable[str]) -> list[TypedMessage]:
    """Return the messages a person typed, in order, numbered from 1.

    ::

        user "fix the login bug"                       -> kept
        user "<command-name>/deepen</command-name>
              <command-args>speed it up</command-args>" -> "/deepen speed it up"
        user tool_result, isMeta skill body,
        isCompactSummary, isSidechain, origin peer     -> left out
        user "<system-reminder>...", "<local-command-stdout>" -> left out
        attachment queued_command "also check logs"    -> kept
        Codex event_msg user_message "fix it"          -> kept
        Codex event_msg user_message with images       -> text plus "[image]"

    A message repeated right after itself, such as a queued prompt that later
    lands as a user entry, counts once.

    Args:
        all_transcript_lines: The session transcript, one JSON entry per line.

    Returns:
        The typed messages, oldest first.
    """
    return [
        TypedMessage(position=each_position, timestamp=each_timestamp, text=each_text)
        for each_position, (each_timestamp, each_text) in enumerate(
            _typed_texts(all_transcript_lines), start=1
        )
    ]
