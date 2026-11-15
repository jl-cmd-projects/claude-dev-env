"""Read the answered ``AskUserQuestion`` calls from a session transcript.

The refusal ledger matches each answer to a question record by exact text
and by where the call sits in the transcript::

    byte 0     {"type": "assistant", ... AskUserQuestion call toolu_1 ...}
    byte 812   {"type": "user", "toolUseResult": {"answers": {"Q?": "Allow it"}}}
        -> AskedQuestions(call_offset=0, answer_by_question={"Q?": "Allow it"})

A call whose result is error text has no ``answers`` object and is left out.
``read_tool_calls`` reads every finished call of any tool, with its input and
error flag, for the Stop gate's card and rule tool checks.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from hooks_constants.auto_mode_refusal_ledger_constants import ASK_TOOL_NAME

JsonObject = dict[str, object]


@dataclass(frozen=True)
class AskedQuestions:
    """One answered ``AskUserQuestion`` call read from the transcript.

    Attributes:
        call_offset: The byte offset where the call's transcript line starts.
        answer_by_question: Each asked question text mapped to the answer text.
    """

    call_offset: int
    answer_by_question: dict[str, str]


@dataclass(frozen=True)
class TranscriptCall:
    """One finished tool call read from the transcript.

    Attributes:
        call_offset: The byte offset where the call's transcript line starts.
        tool_name: The tool the call used.
        tool_input: The call's input as the transcript stores it.
        is_error: Whether the call's result is marked as an error.
    """

    call_offset: int
    tool_name: str
    tool_input: object
    is_error: bool


def _records_with_offsets(transcript_bytes: bytes) -> Iterator[tuple[int, JsonObject]]:
    line_start = 0
    for each_line in transcript_bytes.splitlines(keepends=True):
        current_offset = line_start
        line_start += len(each_line)
        try:
            record = json.loads(each_line)
        except ValueError:
            continue
        if isinstance(record, dict):
            yield current_offset, record


def _all_content_blocks(record: JsonObject) -> list[JsonObject]:
    message = record.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        return []
    return [each_block for each_block in content if isinstance(each_block, dict)]


def _ask_call_ids(record: JsonObject) -> list[str]:
    return [
        str(each_block.get("id"))
        for each_block in _all_content_blocks(record)
        if each_block.get("type") == "tool_use" and each_block.get("name") == ASK_TOOL_NAME
    ]


def _answered_call_ids(record: JsonObject) -> list[str]:
    return [
        str(each_block.get("tool_use_id"))
        for each_block in _all_content_blocks(record)
        if each_block.get("type") == "tool_result"
    ]


def _answers_of(record: JsonObject) -> dict[str, str] | None:
    tool_use_result = record.get("toolUseResult")
    all_answers = tool_use_result.get("answers") if isinstance(tool_use_result, dict) else None
    if not isinstance(all_answers, dict):
        return None
    return {
        str(each_question): str(each_answer) for each_question, each_answer in all_answers.items()
    }


def read_asked_questions(transcript_path: Path | None) -> list[AskedQuestions]:
    """Return every answered ``AskUserQuestion`` call in a transcript.

    Args:
        transcript_path: The session transcript JSONL file, or None.

    Returns:
        One item per call whose result holds an ``answers`` object, in the
        order the results appear.
    """
    if transcript_path is None:
        return []
    try:
        transcript_bytes = transcript_path.read_bytes()
    except OSError:
        return []
    call_offset_by_id: dict[str, int] = {}
    all_asked: list[AskedQuestions] = []
    for each_offset, each_record in _records_with_offsets(transcript_bytes):
        call_offset_by_id.update(dict.fromkeys(_ask_call_ids(each_record), each_offset))
        answer_by_question = _answers_of(each_record)
        if answer_by_question is None:
            continue
        all_asked.extend(
            AskedQuestions(call_offset_by_id[each_id], answer_by_question)
            for each_id in _answered_call_ids(each_record)
            if each_id in call_offset_by_id
        )
    return all_asked


def read_tool_calls(transcript_path: Path | None) -> list[TranscriptCall]:
    """Return every tool call in a transcript that has a result.

    ::

        byte 0    {"type": "assistant", ... Bash call toolu_1 {"command": "ls"} ...}
        byte 300  {"type": "user", ... tool_result toolu_1 ...}
            -> TranscriptCall(0, "Bash", {"command": "ls"}, is_error=False)
        a call with no result yet -> left out

    Args:
        transcript_path: The session transcript JSONL file, or None.

    Returns:
        One item per call whose result is in the transcript, in the order
        the results appear.
    """
    if transcript_path is None:
        return []
    try:
        transcript_bytes = transcript_path.read_bytes()
    except OSError:
        return []
    call_by_id: dict[str, tuple[int, str, object]] = {}
    all_calls: list[TranscriptCall] = []
    for each_offset, each_record in _records_with_offsets(transcript_bytes):
        all_blocks = _all_content_blocks(each_record)
        call_by_id.update(
            (str(each.get("id")), (each_offset, str(each.get("name")), each.get("input")))
            for each in all_blocks
            if each.get("type") == "tool_use"
        )
        all_calls.extend(
            TranscriptCall(
                *call_by_id[str(each.get("tool_use_id"))], is_error=each.get("is_error") is True
            )
            for each in all_blocks
            if each.get("type") == "tool_result" and str(each.get("tool_use_id")) in call_by_id
        )
    return all_calls
