"""Read whether the newest human message directs this review onto a model family."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from hooks.config.model_gate_constants import (
    BLOCK_TYPE_KEY,
    CLAUSE_SPLIT_PATTERN,
    CONTENT_KEY,
    DIRECTIVE_BEFORE_FAMILY_TEMPLATE,
    HUMAN_MESSAGE_PATTERN,
    HUMAN_SENDER_PATTERN,
    IS_META_RECORD_KEY,
    MESSAGE_KEY,
    NEGATION_PATTERN,
    QUESTION_END_PATTERN,
    RECORD_TYPE_KEY,
    REVIEW_CONTEXT_PATTERN,
    SENTENCE_SPLIT_PATTERN,
    SOURCE_TOOL_USE_ID_KEY,
    SPAWN_REASON_PATTERN,
    TEXT_BLOCK_TYPE,
    TEXT_KEY,
    TOOL_REPLY_BLOCK_TYPE,
    RECORD_LINE_SEPARATOR,
    TRANSCRIPT_DECODE_ERRORS,
    TRANSCRIPT_ENCODING,
    USER_RECORD_TYPE,
    WAKE_ENVELOPE_PATTERN,
)


@dataclass(frozen=True)
class WakeContent:
    human_text: str
    is_spawn_wake: bool


def is_model_directive(human_text: str, family: str) -> bool:
    """Return whether a non-question clause directs this review to a family.

    Args:
        human_text: The newest human message.
        family: The model family the command names.

    Returns:
        Whether that message directs this review onto the family.
    """
    directive_pattern = DIRECTIVE_BEFORE_FAMILY_TEMPLATE.format(
        family=re.escape(family)
    )
    return any(
        _clause_directs(each_clause, directive_pattern)
        for each_clause in _non_question_clauses(human_text)
    )


def _clause_directs(each_clause: str, directive_pattern: str) -> bool:
    if not re.search(REVIEW_CONTEXT_PATTERN, each_clause, re.IGNORECASE):
        return False
    if re.search(NEGATION_PATTERN, each_clause, re.IGNORECASE):
        return False
    return re.search(directive_pattern, each_clause, re.IGNORECASE) is not None


def _non_question_clauses(human_text: str) -> list[str]:
    return [
        each_clause
        for each_sentence in re.split(SENTENCE_SPLIT_PATTERN, human_text.strip())
        if not re.search(QUESTION_END_PATTERN, each_sentence)
        for each_clause in re.split(
            CLAUSE_SPLIT_PATTERN, each_sentence, flags=re.IGNORECASE
        )
    ]


def newest_human_text(transcript_path: Path) -> str:
    """Return the text of the newest human turn in the transcript.

    Args:
        transcript_path: The session transcript the hook payload names.

    Returns:
        The newest human message, or empty text when none remains.
    """
    with transcript_path.open(
        encoding=TRANSCRIPT_ENCODING, errors=TRANSCRIPT_DECODE_ERRORS
    ) as transcript_file:
        return _newest_human_turn_text(transcript_file)


def _newest_human_turn_text(all_record_lines: Iterable[str]) -> str:
    newest_text = ""
    for each_line in all_record_lines:
        human_text = _human_turn_text(each_line)
        if human_text is not None:
            newest_text = human_text
    return newest_text


def _human_turn_text(record_line: str) -> str | None:
    wake_content = wake_from_record_line(record_line)
    if wake_content is None or wake_content.is_spawn_wake:
        return None
    if wake_content.human_text.strip() or re.search(HUMAN_SENDER_PATTERN, record_line):
        return wake_content.human_text
    return None


def wake_from_record_line(record_line: str) -> WakeContent | None:
    """Return the human text of one transcript record.

    Args:
        record_line: One JSON line from the transcript.

    Returns:
        The wake content, or None when the line is not a user turn.
    """
    all_record = _json_object(record_line)
    if all_record is None or all_record.get(RECORD_TYPE_KEY) != USER_RECORD_TYPE:
        return None
    if all_record.get(SOURCE_TOOL_USE_ID_KEY) or all_record.get(IS_META_RECORD_KEY):
        return None
    return _wake_from_message(all_record.get(MESSAGE_KEY))


def _json_object(record_line: str) -> dict | None:
    try:
        all_record = json.loads(record_line)
    except json.JSONDecodeError:
        return None
    if isinstance(all_record, dict):
        return all_record
    return None


def _wake_from_message(all_message: object) -> WakeContent | None:
    if not isinstance(all_message, dict):
        return None
    return _wake_from_mapping(all_message)


def _wake_from_mapping(all_message: dict) -> WakeContent | None:
    content = all_message.get(CONTENT_KEY)
    if isinstance(content, str):
        return wake_from_text(content)
    if isinstance(content, list):
        return _wake_from_blocks(content)
    return None


def wake_from_text(content: str) -> WakeContent:
    """Return the human text inside one wake envelope, or the text itself.

    Args:
        content: One user message.

    Returns:
        The human text and whether the envelope is a spawn wake.
    """
    envelope_match = re.fullmatch(WAKE_ENVELOPE_PATTERN, content, re.DOTALL)
    if envelope_match is None:
        return WakeContent(human_text=content, is_spawn_wake=False)
    is_spawn_wake = re.search(SPAWN_REASON_PATTERN, envelope_match.group(1)) is not None
    return WakeContent(
        human_text=_human_text_from_envelope(content), is_spawn_wake=is_spawn_wake
    )


def _human_text_from_envelope(content: str) -> str:
    all_human_texts = [
        each_match.group("human_text") or each_match.group("cited_text") or ""
        for each_match in re.finditer(HUMAN_MESSAGE_PATTERN, content, re.DOTALL)
    ]
    if not all_human_texts:
        return ""
    return all_human_texts[-1]


def _wake_from_blocks(all_blocks: list[object]) -> WakeContent | None:
    all_block_records = [
        each_block for each_block in all_blocks if isinstance(each_block, dict)
    ]
    if any(
        each_block.get(BLOCK_TYPE_KEY) == TOOL_REPLY_BLOCK_TYPE
        for each_block in all_block_records
    ):
        return None
    all_texts = [
        each_block[TEXT_KEY]
        for each_block in all_block_records
        if each_block.get(BLOCK_TYPE_KEY) == TEXT_BLOCK_TYPE
        and isinstance(each_block.get(TEXT_KEY), str)
    ]
    return wake_from_text(RECORD_LINE_SEPARATOR.join(all_texts))
