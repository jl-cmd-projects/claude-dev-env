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
from pathlib import Path

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
    LIST_ITEM_LINE_PATTERN,
    MESSAGE_ID_KEY,
    REPLY_PART_JOINER,
    SESSION_ATTENDED_ENVIRONMENT_VARIABLE,
    TOOL_RESULT_SCAN_TEXT,
    TOOL_USE_BLOCK_ID_KEY,
    TURN_ORIGIN_KEY,
    TURN_ORIGIN_SCAN_TEXT,
    USER_ROLE_SCAN_TEXT,
)
from hooks_constants.open_tasks_stop_gate_constants import (
    ALL_QUESTION_TOOL_NAMES,
    MESSAGE_KEY,
    RECORD_TYPE_KEY,
    STOP_HOOK_FEEDBACK_PREFIX,
    TEXT_KEY,
    TOOL_NAME_KEY,
    TOOL_RESULT_BLOCK_TYPE,
    TOOL_USE_BLOCK_TYPE,
    TOOL_USE_ID_KEY,
)
from closing_question_round_lines import before_deadline
from hooks_constants.user_step_wording_constants import LINE_BREAK
from hooks_constants.background_silence_prompt_constants import BACKGROUND_EVENT_PATTERN
from session.tracking_nudge import is_event_wake
from open_tasks_transcript_records import (
    _content_blocks,
    claude_prompt_text,
    is_assistant_record,
    parsed_object,
    stop_feedback_text,
)

def _message_id(all_record_fields: dict[str, object]) -> str | None:
    message_body = all_record_fields.get(MESSAGE_KEY)
    message_id = message_body.get(MESSAGE_ID_KEY) if isinstance(message_body, dict) else None
    return message_id if isinstance(message_id, str) and message_id else None


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


def _is_stop_feedback_line(transcript_line: str) -> bool:
    if STOP_HOOK_FEEDBACK_PREFIX not in transcript_line:
        return False
    each_record = _top_level_record(transcript_line)
    return each_record is not None and stop_feedback_text(each_record) is not None


def _is_typed_prompt_line(transcript_line: str) -> bool:
    if USER_ROLE_SCAN_TEXT not in transcript_line:
        return False
    each_record = parsed_object(transcript_line)
    prompt_text = claude_prompt_text(each_record) if each_record is not None else None
    return (
        prompt_text is not None
        and not is_event_wake(prompt_text)
        and BACKGROUND_EVENT_PATTERN.match(prompt_text.lstrip()) is None
    )


def _last_prompt_line_position(all_lines: list[str], deadline_at: float) -> int | None:
    all_positions = before_deadline(range(len(all_lines) - 1, -1, -1), deadline_at)
    return next(
        (each_position for each_position in all_positions if _is_typed_prompt_line(all_lines[each_position])),
        None,
    )


def last_typed_prompt_position(all_lines: list[str], deadline_at: float) -> int | None:
    """Return the line position of the last prompt a person typed, or None when no person started the session.

    ::

        {"turnOrigin": "human", "message": {"content": "Add the flag."}}  -> its position
        {"turnOrigin": "sdk", "message": {"content": "Add the flag."}}    -> None
        {"message": {"content": "Add the flag."}}, attended session      -> its position
        a task notification after it, no "turnOrigin", attended session -> the prompt's position
        "<task-notification> is broken. Fix it.", no "turnOrigin"      -> its position, no closing tag
        "<task-notification>...</task-notification> Why?", no "turnOrigin" -> its position, typed text follows

    A line is parsed only when it holds ``"turnOrigin"``. When no record
    carries that key, the last record that starts a turn and is no event
    wake, as ``tracking_nudge.is_event_wake`` reads one, and no system
    notification counts instead, and
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


def wake_counts(all_lines: list[str], deadline_at: float) -> list[int]:
    """Return how many prompts came before each record ``top_level_records`` keeps, then the total.

    ::

        reply, task notification, reply  -> [0, 1, 1]
        task notification, reply         -> [1, 1]
        no lines                         -> [0]

    The gate reads the lines after the last typed prompt, so each prompt
    there is a wake, such as a task notification. A stop that keeps a
    footer read from its payload notes the total, so a copy of that footer
    written after a later wake is not taken as the reply that stop sent.

    Args:
        all_lines: The lines to read, one JSON record per line.
        deadline_at: The monotonic clock reading at which the scan gives up.

    Returns:
        One count for each kept record, in order, and the count of every prompt last.

    Raises:
        TimeoutError: The deadline passed before the scan ended.
    """
    all_counts: list[int] = []
    wake_count = 0
    for each_line in before_deadline(all_lines, deadline_at):
        if _may_matter(each_line) and _top_level_record(each_line) is not None:
            all_counts.append(wake_count)
        if _is_prompt_line(each_line):
            wake_count += 1
    return [*all_counts, wake_count]


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


def last_written_reply(all_lines: list[str], deadline_at: float) -> str | None:
    """Return the text the transcript's last assistant message ends with, or None.

    ::

        prompt, reply "Done."                     -> "Done."
        "Done." and "In progress:" as two records of one message
                                                  -> "Done.\n\nIn progress:"
        "Done." and "In progress:" as two text blocks of one record
                                                  -> "Done.\n\nIn progress:"
        prompt, reply "Done.", a later prompt     -> None, a new turn started
        prompt, reply "Done.", an Edit call       -> None, the record ends with work
        a question call after "Done." in a record -> "Done.", the call is set aside
        reply "Done.", then a thinking-only record -> "Done.", a record with no text or call is skipped
        reply "Done.", then Stop hook feedback     -> None, the next reply is a new one

    Args:
        all_lines: The transcript, one JSON record per line.
        deadline_at: The monotonic clock reading at which the scan gives up.

    Returns:
        The reply the transcript ends with, or None when a prompt or work comes after it.

    Raises:
        TimeoutError: The deadline passed before the scan ended.
    """
    for each_position in before_deadline(range(len(all_lines) - 1, -1, -1), deadline_at):
        each_line = all_lines[each_position]
        if _is_prompt_line(each_line) or _is_stop_feedback_line(each_line):
            return None
        if ASSISTANT_SCAN_TEXT not in each_line:
            continue
        each_record = _top_level_record(each_line)
        if each_record is None or not is_assistant_record(each_record):
            continue
        all_blocks = _content_blocks(each_record)
        all_answer_blocks = [
            each_block
            for each_block in all_blocks
            if each_block.get(RECORD_TYPE_KEY) in (TEXT_KEY, TOOL_USE_BLOCK_TYPE)
        ]
        while all_answer_blocks and _is_question_block(all_answer_blocks[-1]):
            all_answer_blocks.pop()
        if all_blocks and not all_answer_blocks:
            continue
        last_block = all_answer_blocks[-1] if all_answer_blocks else {}
        last_text = last_block.get(TEXT_KEY) if last_block.get(RECORD_TYPE_KEY) == TEXT_KEY else None
        if not isinstance(last_text, str):
            return None
        all_record_texts = [
            each_block[TEXT_KEY]
            for each_block in all_answer_blocks
            if each_block.get(RECORD_TYPE_KEY) == TEXT_KEY and isinstance(each_block.get(TEXT_KEY), str)
        ]
        return joined_reply_parts(
            [*_earlier_message_texts(all_lines[:each_position], _message_id(each_record), deadline_at), *all_record_texts]
        )
    return None


def joined_reply_parts(all_parts: list[str]) -> str:
    """Return the text blocks of one message as one reply, a blank line between blocks.

    ::

        ["Done.", "In progress:\n- I am fixing it."] -> "Done.\n\nIn progress:\n- I am fixing it."
        ["- I am fixing it.", "  The tests run."]   -> "- I am fixing it.\n  The tests run."
        ["Run this:", "    echo done"]             -> "Run this:\n\n    echo done"

    A block that opens indented right after a list item, or after a line
    that goes on one, goes on the next line with no blank line, since it
    goes on that item, and a blank line there would make it a code block.
    Any other indented block keeps its blank line, so it stays a code block.
    """
    joined_text = ""
    for each_part in all_parts:
        if not joined_text:
            joined_text = each_part
            continue
        last_line = joined_text.rstrip().rsplit(LINE_BREAK, 1)[-1]
        is_item_line = last_line[:1].isspace() or LIST_ITEM_LINE_PATTERN.match(last_line) is not None
        part_joiner = LINE_BREAK if each_part[:1].isspace() and is_item_line else REPLY_PART_JOINER
        joined_text = f"{joined_text.rstrip()}{part_joiner}{each_part}"
    return joined_text


def is_same_reply(first_reply: str, second_reply: str) -> bool:
    """Return True when two replies hold the same lines, blank lines and trailing spaces aside.

    ::

        "Done.\n\nIn progress:\n- I am fixing it." and "Done.\n\nIn progress:\n\n- I am fixing it." -> True
        "This is out of\n\nscope." and "This is out of\nscope."                          -> False
        "In progress: - I am fixing it." and "In progress:\n- I am fixing it."              -> False
        "Done." and "Done.\n"                                                            -> True

    A footer is read line by line, so a reply whose heading and item share
    one line is another reply than one that puts them on two lines, and a
    line indented as an item's continuation differs from the same line
    unindented. The lines come from ``reply_lines``.
    """
    return reply_lines(first_reply) == reply_lines(second_reply)


def reply_lines(reply_text: str) -> list[str]:
    """Return the lines that decide how a reply reads, with each indent kept.

    ::

        "Done.\n\nIn progress:\n- I am fixing it." -> ["Done.", "", "In progress:", "- I am fixing it."]
        "In progress:\n\n- I am fixing it."        -> ["In progress:", "- I am fixing it."]
        "This is out of\n\n\nscope."               -> ["This is out of", "", "scope."]
        "Done.\n\n    TODO: add the flag."        -> ["Done.", "", "    TODO: add the flag."]

    A run of blank lines stays as one blank line, since it ends a paragraph
    and the open-item scan reads paragraphs. A blank line above a list item
    stays out unless that item is indented, since it changes neither the
    list nor the paragraph above it. So a footer whose heading and list are
    two records of one message gives the lines the payload's copy gives.
    """
    all_lines = [each_line.rstrip() for each_line in reply_text.strip().splitlines()]
    all_kept_lines: list[str] = []
    for each_position, each_line in enumerate(all_lines):
        if each_line:
            all_kept_lines.append(each_line)
            continue
        next_line = all_lines[each_position + 1] if each_position + 1 < len(all_lines) else ""
        is_before_list_item = LIST_ITEM_LINE_PATTERN.match(next_line) is not None
        if next_line and not is_before_list_item and all_kept_lines and all_kept_lines[-1]:
            all_kept_lines.append(each_line)
    return all_kept_lines


def _earlier_message_texts(all_lines: list[str], message_id: str | None, deadline_at: float) -> list[str]:
    all_texts: list[str] = []
    if message_id is None:
        return all_texts
    for each_line in before_deadline(reversed(all_lines), deadline_at):
        if ASSISTANT_SCAN_TEXT not in each_line:
            continue
        each_record = _top_level_record(each_line)
        if each_record is None or not is_assistant_record(each_record):
            continue
        if _message_id(each_record) != message_id:
            break
        all_texts[:0] = block_texts(each_record)
    return all_texts


def closing_reply_texts(
    all_hook_input_fields: dict[str, object], all_lines: list[str], deadline_at: float
) -> list[str]:
    """Return the payload's closing reply as a one-item list, or an empty list.

    ::

        "Both tests pass."  and the transcript ends with other text  -> ["Both tests pass."]
        "Both tests pass."  and the transcript ends with it          -> []
        "Both tests pass."  and a prompt came after that copy         -> ["Both tests pass."]
        "" or no string                                               -> []

    The transcript ends with the reply when its last top-level assistant
    record, question calls left aside, ends in a text block equal to it, with
    outer whitespace stripped, and no prompt comes after that record. A text
    before a later work call is not it, and a copy sent before the prompt
    that started this turn is an earlier reply.

    Args:
        all_hook_input_fields: The Stop payload.
        all_lines: The transcript, one JSON record per line.
        deadline_at: The monotonic clock reading at which the scan gives up.

    Returns:
        The closing reply to read, when the transcript does not hold it yet.

    Raises:
        TimeoutError: The deadline passed before the scan ended.
    """
    return payload_closing_texts(all_hook_input_fields, last_written_reply(all_lines, deadline_at))


def payload_closing_texts(all_hook_input_fields: dict[str, object], written_reply: str | None) -> list[str]:
    """Return the payload's closing reply as a one-item list, unless the transcript already ends with it.

    ::

        "Both tests pass." and written reply "Done."              -> ["Both tests pass."]
        "Both tests pass." and written reply "Both tests pass.\n" -> []
        "Done.\n\nIn progress:\n- I am fixing it." and written reply
            "Done.\n\nIn progress:\n\n- I am fixing it."                 -> [], the lines match
        "" or no string                                           -> []

    Args:
        all_hook_input_fields: The Stop payload.
        written_reply: The reply the transcript ends with, from ``last_written_reply``.

    Returns:
        The closing reply to read, when the transcript does not hold it yet.
    """
    closing_reply = all_hook_input_fields.get(LAST_ASSISTANT_MESSAGE_KEY)
    if not isinstance(closing_reply, str) or not closing_reply.strip():
        return []
    if written_reply is not None and is_same_reply(written_reply, closing_reply):
        return []
    return [closing_reply]
