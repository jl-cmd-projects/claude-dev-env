#!/usr/bin/env python3
"""Write every message the user typed in a session to a file, and print its path.

::

    python3 compaction_user_messages.py ~/.claude/projects/p/abc.jsonl
    -> /tmp/compaction-user-messages-abc.md

The agent runs this after a compaction. Only the path reaches its context.
A PostToolUse agent hook reads the file, condenses it, and returns the
condensed messages to the agent.

The file holds the trim rules, then each typed message with its number and
timestamp, oldest first. The whole transcript is read each time, so a second
compaction yields the same messages plus the newer ones.
"""

from __future__ import annotations

import json
import sys
import tempfile
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
    CONTENT_KEY,
    CUT_MESSAGE_SUFFIX_TEMPLATE,
    ENTRY_TYPE_KEY,
    HARNESS_TAG_OPENING_PATTERN,
    HUMAN_ORIGIN_KIND,
    IMAGE_BLOCK_TYPE,
    IMAGE_PLACEHOLDER,
    LEFT_OUT_MESSAGES_TEMPLATE,
    MAXIMUM_EXTRACT_CHARACTERS,
    MAXIMUM_MESSAGE_CHARACTERS,
    MESSAGE_HEADING_TEMPLATE,
    MESSAGE_KEY,
    MESSAGES_HEADING,
    NO_MESSAGES_TEXT,
    ORIGIN_KEY,
    ORIGIN_KIND_KEY,
    OUTPUT_ENCODING,
    OUTPUT_FILE_PREFIX,
    OUTPUT_FILE_SUFFIX,
    QUEUED_COMMAND_ATTACHMENT_TYPE,
    QUEUED_PROMPT_KEY,
    SLASH_COMMAND_ARGS_PATTERN,
    SLASH_COMMAND_NAME_PATTERN,
    TEXT_BLOCK_TYPE,
    TEXT_KEY,
    TIMESTAMP_KEY,
    TRANSCRIPT_ARGUMENT_COUNT,
    TRIM_INSTRUCTIONS,
    USAGE_EXIT_CODE,
    USAGE_TEXT,
    USER_ENTRY_TYPE,
)
from hooks_constants.session_file_id import session_file_id
from hooks_constants.setup_project_paths_constants import DECODE_ERRORS_POLICY, UTF8_ENCODING


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


def _entry_text(all_entry_fields: dict[str, object]) -> str | None:
    entry_type = all_entry_fields.get(ENTRY_TYPE_KEY)
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
        if all_entry_fields.get(ENTRY_TYPE_KEY) == ASSISTANT_ENTRY_TYPE:
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
        user "<command-name>/deepstack-mode</command-name>
              <command-args>speed it up</command-args>" -> "/deepstack-mode speed it up"
        user tool_result, isMeta skill body,
        isCompactSummary, isSidechain, origin peer     -> left out
        user "<system-reminder>...", "<local-command-stdout>" -> left out
        attachment queued_command "also check logs"    -> kept

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


def _capped_text(text: str) -> str:
    if len(text) <= MAXIMUM_MESSAGE_CHARACTERS:
        return text
    cut_count = len(text) - MAXIMUM_MESSAGE_CHARACTERS
    return text[:MAXIMUM_MESSAGE_CHARACTERS] + CUT_MESSAGE_SUFFIX_TEMPLATE.format(
        cut_count=cut_count
    )


def _rendered_message(message: TypedMessage) -> str:
    return MESSAGE_HEADING_TEMPLATE.format(
        position=message.position,
        timestamp=message.timestamp,
        text=_capped_text(message.text),
    )


def bounded_messages(all_messages: list[TypedMessage]) -> list[TypedMessage]:
    """Return the messages that fit the extract budget: the first, then the newest.

    ::

        5 short messages             -> all 5
        #1 plus 400 long messages    -> #1, then the newest that fit

    The first message keeps the session's original ask. The newest carry the
    latest corrections, which override older asks.

    Args:
        all_messages: Every typed message, oldest first.

    Returns:
        The kept messages, oldest first.
    """
    if not all_messages:
        return []
    first_message, *all_later_messages = all_messages
    remaining_characters = MAXIMUM_EXTRACT_CHARACTERS - len(_rendered_message(first_message))
    all_kept_later_messages: list[TypedMessage] = []
    for each_message in reversed(all_later_messages):
        message_size = len(_rendered_message(each_message))
        if message_size > remaining_characters:
            break
        remaining_characters -= message_size
        all_kept_later_messages.append(each_message)
    return [first_message, *reversed(all_kept_later_messages)]


def rendered_extract(all_messages: list[TypedMessage]) -> str:
    """Return the file text: the trim rules, then the kept messages.

    ::

        [#1 "fix login"]  -> TRIM_INSTRUCTIONS + "# User messages..." + "## 1 | <ts>\\nfix login"

    Args:
        all_messages: Every typed message, oldest first.

    Returns:
        The text the extractor writes to its output file.
    """
    if not all_messages:
        return TRIM_INSTRUCTIONS + MESSAGES_HEADING + NO_MESSAGES_TEXT
    all_kept_messages = bounded_messages(all_messages)
    left_out_count = len(all_messages) - len(all_kept_messages)
    rendered_parts = [TRIM_INSTRUCTIONS, MESSAGES_HEADING]
    for each_index, each_message in enumerate(all_kept_messages):
        if each_index == 1 and left_out_count:
            rendered_parts.append(LEFT_OUT_MESSAGES_TEMPLATE.format(left_out_count=left_out_count))
        rendered_parts.append(_rendered_message(each_message))
    return "".join(rendered_parts)


def output_path_for(transcript_path: Path) -> Path:
    """Return the temp file for one transcript, named after its session id.

    ::

        ~/.claude/projects/p/abc-123.jsonl -> /tmp/compaction-user-messages-abc-123.md

    Args:
        transcript_path: The session transcript.

    Returns:
        The path the extractor writes; a rerun overwrites it.
    """
    file_name = f"{OUTPUT_FILE_PREFIX}{session_file_id(transcript_path.stem)}{OUTPUT_FILE_SUFFIX}"
    return Path(tempfile.gettempdir()) / file_name


def main() -> int:
    """Write the extract for the transcript named on the command line and print its path."""
    if len(sys.argv) != TRANSCRIPT_ARGUMENT_COUNT:
        sys.stderr.write(USAGE_TEXT)
        return USAGE_EXIT_CODE
    transcript_path = Path(sys.argv[1])
    try:
        with transcript_path.open(
            encoding=UTF8_ENCODING, errors=DECODE_ERRORS_POLICY
        ) as transcript:
            all_messages = typed_user_messages(transcript)
    except OSError as read_error:
        sys.stderr.write(f"cannot read {transcript_path}: {read_error}\n")
        return USAGE_EXIT_CODE
    output_path = output_path_for(transcript_path)
    output_path.write_text(rendered_extract(all_messages), encoding=OUTPUT_ENCODING)
    sys.stdout.write(f"{output_path}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
