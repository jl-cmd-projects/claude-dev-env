"""Read the transcript stretch the closing question round gate checks.

The stretch is every top-level record after the last question card that
reached the user::

    reply, AskUserQuestion, its answer, reply  -> its answer, reply
    reply, AskUserQuestion, its refusal        -> all three
    reply, reply                               -> reply, reply

The transcript is read as bytes, a line over 16 MiB reads as an empty line,
and a line is JSON-parsed only when a substring scan says it can matter:
``"turnOrigin"`` or ``"user"`` for prompts, a quoted question tool name for
question calls, ``"tool_result"`` with a pending call id for their results,
``"assistant"`` or a reason's first sentence for stretch records and for
the last assistant text.

A question tool is a name in ``ALL_QUESTION_TOOL_NAMES``. A call reached the
user when a later ``tool_result`` carries its ``tool_use_id`` and has no truthy
``is_error``. A refused call, an errored call, a call with no result yet, and
a call whose name is no string do not count. The stretch is the whole
transcript when no call reached the user, and it spans turns. A record flagged
``isSidechain`` is never read. Any other tool call in the stretch is work.

Claude Code runs Stop hooks before it writes the closing reply. The payload's
``last_assistant_message``, when it is a non-empty string, is read as the
newest text of the stretch, once when the transcript already ends with it.
"""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import TypeVar

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)
blocking_directory = str(Path(__file__).resolve().parent)
if blocking_directory not in sys.path:
    sys.path.insert(0, blocking_directory)

from hooks_constants.closing_question_round_gate_constants import (
    ALL_QUESTION_TOOL_NAME_SCAN_TEXTS,
    ALL_REASON_LEADS,
    ASSISTANT_SCAN_TEXT,
    ATTENDED_SESSION_TEXT,
    HUMAN_TURN_ORIGIN,
    IS_ERROR_KEY,
    IS_SIDECHAIN_KEY,
    LAST_ASSISTANT_MESSAGE_KEY,
    LINE_FEED_BYTES,
    MAXIMUM_SCANNED_BYTES,
    MAXIMUM_SCANNED_TEXT_BYTES,
    SESSION_ATTENDED_ENVIRONMENT_VARIABLE,
    TOOL_RESULT_SCAN_TEXT,
    TOOL_USE_BLOCK_ID_KEY,
    TURN_ORIGIN_KEY,
    TURN_ORIGIN_SCAN_TEXT,
    USER_ROLE_SCAN_TEXT,
)
from hooks_constants.open_tasks_stop_gate_constants import (
    ALL_QUESTION_TOOL_NAMES,
    RECORD_TYPE_KEY,
    TEXT_KEY,
    TOOL_NAME_KEY,
    TOOL_RESULT_BLOCK_TYPE,
    TOOL_USE_BLOCK_TYPE,
    TOOL_USE_ID_KEY,
    UTF8_ENCODING,
)
from hooks_constants.setup_project_paths_constants import DECODE_ERRORS_POLICY
from open_tasks_transcript_records import (
    _content_blocks,
    claude_prompt_text,
    is_assistant_record,
    parsed_object,
)

ScannedItem = TypeVar("ScannedItem")


def before_deadline(all_items: Iterable[ScannedItem], deadline_at: float) -> Iterator[ScannedItem]:
    """Yield each text, line, or match in order, and raise TimeoutError once the monotonic clock reaches the deadline.

    The clock is read before each item is yielded.
    """
    for each_item in all_items:
        if time.monotonic() >= deadline_at:
            raise TimeoutError
        yield each_item


def is_within_scan_cap(scanned_text: str) -> bool:
    """Return True when the text holds 2 MiB or less once encoded as UTF-8."""
    return len(scanned_text) <= MAXIMUM_SCANNED_TEXT_BYTES and (
        len(scanned_text.encode(UTF8_ENCODING, DECODE_ERRORS_POLICY)) <= MAXIMUM_SCANNED_TEXT_BYTES
    )


def transcript_lines(transcript_path: object, deadline_at: float) -> list[str]:
    """Return the transcript file's lines, with each line over 16 MiB read as an empty line.

    ::

        b'{"a": 1}\\n{"b": 2}'            -> ['{"a": 1}', '{"b": 2}']
        a 200 MB line between two lines  -> [first line, "", last line]
        no string, or a missing file     -> []

    The file is read as bytes and cut at each line feed. Each line of 16 MiB or
    less is decoded as UTF-8 with bad bytes replaced, and the empty stand-in
    keeps the positions of the lines after it. The clock is read before each
    line, and TimeoutError is raised once it reaches ``deadline_at``.
    """
    if not isinstance(transcript_path, str):
        return []
    try:
        transcript_bytes = Path(transcript_path).read_bytes()
    except (OSError, ValueError):
        return []
    return [
        each_line.decode(UTF8_ENCODING, DECODE_ERRORS_POLICY)
        if len(each_line) <= MAXIMUM_SCANNED_BYTES
        else ""
        for each_line in before_deadline(transcript_bytes.split(LINE_FEED_BYTES), deadline_at)
    ]


def _top_level_record(transcript_line: str) -> dict[str, object] | None:
    each_record = parsed_object(transcript_line)
    if each_record is None or each_record.get(IS_SIDECHAIN_KEY):
        return None
    return each_record


def _is_prompt_line(transcript_line: str) -> bool:
    if USER_ROLE_SCAN_TEXT not in transcript_line:
        return False
    each_record = parsed_object(transcript_line)
    return each_record is not None and claude_prompt_text(each_record) is not None


def _last_prompt_line_position(all_lines: list[str], deadline_at: float) -> int | None:
    all_positions = before_deadline(range(len(all_lines) - 1, -1, -1), deadline_at)
    return next(
        (each_position for each_position in all_positions if _is_prompt_line(all_lines[each_position])),
        None,
    )


def last_typed_prompt_position(all_lines: list[str], deadline_at: float) -> int | None:
    """Return the line position of the last prompt a person typed, or None when no person started the session.

    ::

        {"turnOrigin": "human", "message": {"content": "Add the flag."}}  -> its position
        {"turnOrigin": "sdk", "message": {"content": "Add the flag."}}    -> None
        {"message": {"content": "Add the flag."}}, attended session      -> its position

    A line is parsed only when it holds ``"turnOrigin"``. When no record
    carries that key, the last record that starts a turn counts instead, and
    only when ``CLAUDE_CODE_SESSION_ATTENDED`` is ``1``; that second scan
    reads from the end and parses only the lines that hold ``"user"``. Both
    scans raise TimeoutError once the clock reaches ``deadline_at``.
    """
    has_turn_origin_key = False
    last_position: int | None = None
    for each_position, each_line in enumerate(before_deadline(all_lines, deadline_at)):
        if TURN_ORIGIN_SCAN_TEXT not in each_line:
            continue
        each_record = parsed_object(each_line)
        if each_record is None or TURN_ORIGIN_KEY not in each_record:
            continue
        has_turn_origin_key = True
        if (
            each_record.get(TURN_ORIGIN_KEY) == HUMAN_TURN_ORIGIN
            and claude_prompt_text(each_record) is not None
        ):
            last_position = each_position
    if has_turn_origin_key:
        return last_position
    if os.environ.get(SESSION_ATTENDED_ENVIRONMENT_VARIABLE) != ATTENDED_SESSION_TEXT:
        return None
    return _last_prompt_line_position(all_lines, deadline_at)


def _is_question_tool_name(tool_name: object) -> bool:
    return isinstance(tool_name, str) and tool_name in ALL_QUESTION_TOOL_NAMES


def _is_question_block(all_block_fields: dict[str, object]) -> bool:
    return (
        all_block_fields.get(RECORD_TYPE_KEY) == TOOL_USE_BLOCK_TYPE
        and _is_question_tool_name(all_block_fields.get(TOOL_NAME_KEY))
        and isinstance(all_block_fields.get(TOOL_USE_BLOCK_ID_KEY), str)
    )


def _question_call_ids(all_record_fields: dict[str, object] | None) -> list[str]:
    if all_record_fields is None or not is_assistant_record(all_record_fields):
        return []
    return [
        str(each_block[TOOL_USE_BLOCK_ID_KEY])
        for each_block in _content_blocks(all_record_fields)
        if _is_question_block(each_block)
    ]


def _tool_results(all_record_fields: dict[str, object] | None) -> list[tuple[str, bool]]:
    if all_record_fields is None:
        return []
    return [
        (str(each_block[TOOL_USE_ID_KEY]), bool(each_block.get(IS_ERROR_KEY)))
        for each_block in _content_blocks(all_record_fields)
        if each_block.get(RECORD_TYPE_KEY) == TOOL_RESULT_BLOCK_TYPE
        and isinstance(each_block.get(TOOL_USE_ID_KEY), str)
    ]


def _answered_call_positions(
    transcript_line: str, all_pending_call_positions: dict[str, int]
) -> list[int]:
    if not all_pending_call_positions or TOOL_RESULT_SCAN_TEXT not in transcript_line:
        return []
    if not any(each_id in transcript_line for each_id in all_pending_call_positions):
        return []
    all_answered_positions: list[int] = []
    for each_id, each_is_error in _tool_results(_top_level_record(transcript_line)):
        call_position = all_pending_call_positions.pop(each_id, None)
        if call_position is not None and not each_is_error:
            all_answered_positions.append(call_position)
    return all_answered_positions


def _asked_call_ids(transcript_line: str) -> list[str]:
    if not any(
        each_scan_text in transcript_line for each_scan_text in ALL_QUESTION_TOOL_NAME_SCAN_TEXTS
    ):
        return []
    return _question_call_ids(_top_level_record(transcript_line))


def stretch_start(all_lines: list[str], deadline_at: float) -> int:
    """Return the line position right after the last question call that reached the user, or 0.

    ::

        reply, AskUserQuestion, its answer, reply  -> 2, the answer's position
        reply, AskUserQuestion, its refusal        -> 0
        reply, reply                               -> 0

    A record flagged ``isSidechain`` is never a question call or its result.

    Args:
        all_lines: The transcript, one JSON record per line.
        deadline_at: The monotonic clock reading at which the scan gives up.

    Returns:
        The position of the first line of the stretch.

    Raises:
        TimeoutError: The deadline passed before the scan ended.
    """
    all_pending_call_positions: dict[str, int] = {}
    start_position = 0
    for each_position, each_line in enumerate(before_deadline(all_lines, deadline_at)):
        all_answered_positions = _answered_call_positions(each_line, all_pending_call_positions)
        start_position = max(
            [
                start_position,
                *(each_answered_position + 1 for each_answered_position in all_answered_positions),
            ]
        )
        all_pending_call_positions.update(dict.fromkeys(_asked_call_ids(each_line), each_position))
    return start_position


def _may_matter(transcript_line: str) -> bool:
    return ASSISTANT_SCAN_TEXT in transcript_line or any(
        each_lead in transcript_line for each_lead in ALL_REASON_LEADS
    )


def top_level_records(all_lines: list[str], deadline_at: float) -> list[dict[str, object]]:
    """Return the assistant records and this gate's hold records among the lines, in order.

    ::

        reply, tool result, Bash call, hold feedback  -> reply, Bash call, hold feedback
        a record flagged isSidechain                  -> left out

    A line is parsed only when it holds ``"assistant"`` or the first sentence
    of one of this gate's reasons. The records are not checked further here.

    Args:
        all_lines: The lines to read, one JSON record per line.
        deadline_at: The monotonic clock reading at which the scan gives up.

    Returns:
        The parsed top-level records.

    Raises:
        TimeoutError: The deadline passed before the scan ended.
    """
    all_records = (
        _top_level_record(each_line)
        for each_line in before_deadline(all_lines, deadline_at)
        if _may_matter(each_line)
    )
    return [each_record for each_record in all_records if each_record is not None]


def block_texts(all_record_fields: dict[str, object]) -> list[str]:
    """Return the string ``text`` of each text block the record's content holds, in order."""
    all_block_texts = (
        each_block.get(TEXT_KEY)
        for each_block in _content_blocks(all_record_fields)
        if each_block.get(RECORD_TYPE_KEY) == TEXT_KEY
    )
    return [each_text for each_text in all_block_texts if isinstance(each_text, str)]


def assistant_texts(all_stretch_records: list[dict[str, object]]) -> list[str]:
    """Return the text blocks of the assistant records in the stretch, in order."""
    return [
        each_text
        for each_record in all_stretch_records
        if is_assistant_record(each_record)
        for each_text in block_texts(each_record)
    ]


def has_work_call(all_stretch_records: list[dict[str, object]]) -> bool:
    """Return True when an assistant record in the stretch holds a tool call that is no question call.

    A call whose name is no string counts as work.
    """
    return any(
        each_block.get(RECORD_TYPE_KEY) == TOOL_USE_BLOCK_TYPE
        and not _is_question_tool_name(each_block.get(TOOL_NAME_KEY))
        for each_record in all_stretch_records
        if is_assistant_record(each_record)
        for each_block in _content_blocks(each_record)
    )


def _last_assistant_text(all_lines: list[str], deadline_at: float) -> str | None:
    for each_line in before_deadline(reversed(all_lines), deadline_at):
        if ASSISTANT_SCAN_TEXT not in each_line:
            continue
        each_record = _top_level_record(each_line)
        if each_record is None or not is_assistant_record(each_record):
            continue
        all_blocks = _content_blocks(each_record)
        if all_blocks and _is_question_block(all_blocks[-1]):
            continue
        all_record_texts = block_texts(each_record)
        ends_in_text = bool(all_blocks) and all_blocks[-1].get(RECORD_TYPE_KEY) == TEXT_KEY
        return all_record_texts[-1] if ends_in_text and all_record_texts else None
    return None


def closing_reply_texts(
    all_hook_input_fields: dict[str, object], all_lines: list[str], deadline_at: float
) -> list[str]:
    """Return the payload's closing reply as a one-item list, or an empty list.

    ::

        "Both tests pass."  and the transcript ends with other text  -> ["Both tests pass."]
        "Both tests pass."  and the transcript ends with it          -> []
        "" or no string                                               -> []

    The transcript ends with the reply when its last top-level assistant
    record, question calls left aside, ends in a text block equal to it, with
    outer whitespace stripped. A text before a later work call is not it.

    Args:
        all_hook_input_fields: The Stop payload.
        all_lines: The transcript, one JSON record per line.
        deadline_at: The monotonic clock reading at which the scan gives up.

    Returns:
        The closing reply to read, when the transcript does not hold it yet.

    Raises:
        TimeoutError: The deadline passed before the scan ended.
    """
    closing_reply = all_hook_input_fields.get(LAST_ASSISTANT_MESSAGE_KEY)
    if not isinstance(closing_reply, str) or not closing_reply.strip():
        return []
    last_written_text = _last_assistant_text(all_lines, deadline_at)
    if last_written_text is not None and last_written_text.strip() == closing_reply.strip():
        return []
    return [closing_reply]
