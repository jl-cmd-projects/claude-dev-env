"""Read a session transcript into the steps the spawn readiness hook checks.

::

    user "build X" ... Bash ... post_message "Which layout?" ... user "grid"
    -> [USER_MESSAGE, READ, QUESTION, USER_MESSAGE]
    -> readiness_gaps(...) == []

A read is a file read, a search, a shell command, a fetch, an MCP read, or a
read-only subagent. A question is an ``AskUserQuestion`` call, an
``ask_decision`` card, or a posted message or reply whose text holds a
question mark. A user message is typed text or a human wake; a harness
envelope with no human sender, such as an agent relay or a task notice, is
left out.
"""

from __future__ import annotations

import enum
import json
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)

from hooks_constants.spawn_readiness_hook_constants import (
    ALL_BRIEF_FIELDS_BY_SPAWN_TOOL_NAME,
    ALL_HARNESS_ENVELOPE_MARKERS,
    ALL_MCP_READ_VERB_PREFIXES,
    ALL_POSTING_TOOL_SUFFIXES,
    ALL_READ_ONLY_SUBAGENT_TYPES,
    ALL_READ_TOOL_NAMES,
    ASK_DECISION_TOOL_SUFFIX,
    ASK_USER_QUESTION_TOOL_NAME,
    ASSISTANT_ENTRY_TYPE,
    ATTACHMENT_ENTRY_TYPE,
    ATTACHMENT_KEY,
    BLOCK_ID_KEY,
    BLOCK_INPUT_KEY,
    BLOCK_NAME_KEY,
    BLOCK_TYPE_KEY,
    CONTENT_KEY,
    ENTRY_TYPE_KEY,
    HUMAN_SENDER_MARKER,
    IS_COMPACT_SUMMARY_KEY,
    IS_META_KEY,
    MCP_TOOL_NAME_PREFIX,
    MCP_TOOL_NAME_SEPARATOR,
    MESSAGE_KEY,
    MISSING_INTERVIEW_REASON,
    MISSING_INVESTIGATION_REASON,
    POSTED_TEXT_INPUT_KEY,
    QUESTION_MARK,
    QUEUED_COMMAND_ATTACHMENT_TYPE,
    QUEUED_PROMPT_KEY,
    RESULT_IS_ERROR_KEY,
    RESULT_TOOL_USE_ID_KEY,
    SUBAGENT_TYPE_INPUT_KEY,
    TEXT_BLOCK_TYPE,
    TEXT_KEY,
    TOOL_RESULT_BLOCK_TYPE,
    TOOL_USE_BLOCK_TYPE,
    USER_ENTRY_TYPE,
)


class SessionStep(enum.Enum):
    """One transcript step the readiness checks count."""

    USER_MESSAGE = "user_message"
    READ = "read"
    QUESTION = "question"
    OTHER_TOOL_CALL = "other_tool_call"


def _is_user_text(text: str) -> bool:
    if not text.strip():
        return False
    if any(each_marker in text for each_marker in ALL_HARNESS_ENVELOPE_MARKERS):
        return HUMAN_SENDER_MARKER in text
    return True


def _mcp_step(action_name: str, all_input_fields: dict[object, object]) -> SessionStep:
    if action_name == ASK_DECISION_TOOL_SUFFIX:
        return SessionStep.QUESTION
    if action_name in ALL_POSTING_TOOL_SUFFIXES:
        posted_text = all_input_fields.get(POSTED_TEXT_INPUT_KEY)
        is_question = isinstance(posted_text, str) and QUESTION_MARK in posted_text
        return SessionStep.QUESTION if is_question else SessionStep.OTHER_TOOL_CALL
    if action_name.startswith(ALL_MCP_READ_VERB_PREFIXES):
        return SessionStep.READ
    return SessionStep.OTHER_TOOL_CALL


def _tool_use_step(tool_name: str, tool_input: object) -> SessionStep:
    all_input_fields = tool_input if isinstance(tool_input, dict) else {}
    if tool_name == ASK_USER_QUESTION_TOOL_NAME:
        return SessionStep.QUESTION
    if tool_name in ALL_READ_TOOL_NAMES:
        return SessionStep.READ
    if (
        tool_name in ALL_BRIEF_FIELDS_BY_SPAWN_TOOL_NAME
        and all_input_fields.get(SUBAGENT_TYPE_INPUT_KEY) in ALL_READ_ONLY_SUBAGENT_TYPES
    ):
        return SessionStep.READ
    if tool_name.startswith(MCP_TOOL_NAME_PREFIX):
        return _mcp_step(tool_name.rsplit(MCP_TOOL_NAME_SEPARATOR, 1)[-1], all_input_fields)
    return SessionStep.OTHER_TOOL_CALL


def _content_of(all_entry_fields: dict[object, object]) -> object:
    message = all_entry_fields.get(MESSAGE_KEY)
    return message.get(CONTENT_KEY) if isinstance(message, dict) else None


def _assistant_steps(
    all_entry_fields: dict[object, object],
    all_question_tool_use_ids: set[str],
    spawn_tool_use_id: str | None,
) -> Iterator[SessionStep]:
    content = _content_of(all_entry_fields)
    all_blocks = content if isinstance(content, list) else []
    for each_block in all_blocks:
        if (
            not isinstance(each_block, dict)
            or each_block.get(BLOCK_TYPE_KEY) != TOOL_USE_BLOCK_TYPE
        ):
            continue
        block_id = each_block.get(BLOCK_ID_KEY)
        tool_name = each_block.get(BLOCK_NAME_KEY)
        if block_id == spawn_tool_use_id or not isinstance(tool_name, str):
            continue
        if tool_name == ASK_USER_QUESTION_TOOL_NAME and isinstance(block_id, str):
            all_question_tool_use_ids.add(block_id)
        yield _tool_use_step(tool_name, each_block.get(BLOCK_INPUT_KEY))


def _is_user_block(
    all_block_fields: dict[object, object], all_question_tool_use_ids: set[str]
) -> bool:
    block_type = all_block_fields.get(BLOCK_TYPE_KEY)
    if block_type == TEXT_BLOCK_TYPE:
        return _is_user_text(str(all_block_fields.get(TEXT_KEY, "")))
    return (
        block_type == TOOL_RESULT_BLOCK_TYPE
        and all_block_fields.get(RESULT_TOOL_USE_ID_KEY) in all_question_tool_use_ids
        and not all_block_fields.get(RESULT_IS_ERROR_KEY)
    )


def _user_steps(
    all_entry_fields: dict[object, object], all_question_tool_use_ids: set[str]
) -> Iterator[SessionStep]:
    if all_entry_fields.get(IS_META_KEY) or all_entry_fields.get(IS_COMPACT_SUMMARY_KEY):
        return
    content = _content_of(all_entry_fields)
    if isinstance(content, str):
        is_user_message = _is_user_text(content)
    else:
        all_blocks = content if isinstance(content, list) else []
        is_user_message = any(
            isinstance(each_block, dict) and _is_user_block(each_block, all_question_tool_use_ids)
            for each_block in all_blocks
        )
    if is_user_message:
        yield SessionStep.USER_MESSAGE


def _queued_steps(all_entry_fields: dict[object, object]) -> Iterator[SessionStep]:
    attachment = all_entry_fields.get(ATTACHMENT_KEY)
    if (
        not isinstance(attachment, dict)
        or attachment.get(ENTRY_TYPE_KEY) != QUEUED_COMMAND_ATTACHMENT_TYPE
    ):
        return
    queued_prompt = attachment.get(QUEUED_PROMPT_KEY)
    if isinstance(queued_prompt, str) and _is_user_text(queued_prompt):
        yield SessionStep.USER_MESSAGE


def _parsed_entry(transcript_line: str) -> dict[object, object]:
    try:
        parsed_entry = json.loads(transcript_line)
    except json.JSONDecodeError:
        return {}
    return parsed_entry if isinstance(parsed_entry, dict) else {}


def _entry_steps(
    transcript_line: str, all_question_tool_use_ids: set[str], spawn_tool_use_id: str | None
) -> Iterator[SessionStep]:
    parsed_entry = _parsed_entry(transcript_line)
    entry_type = parsed_entry.get(ENTRY_TYPE_KEY)
    if entry_type == ASSISTANT_ENTRY_TYPE:
        return _assistant_steps(parsed_entry, all_question_tool_use_ids, spawn_tool_use_id)
    if entry_type == USER_ENTRY_TYPE:
        return _user_steps(parsed_entry, all_question_tool_use_ids)
    if entry_type == ATTACHMENT_ENTRY_TYPE:
        return _queued_steps(parsed_entry)
    return iter(())


def session_steps(
    all_transcript_lines: Iterable[str], spawn_tool_use_id: str | None = None
) -> list[SessionStep]:
    """Read the transcript into the user messages and tool calls it holds, in order.

    A tool call that is neither a read nor a question is an OTHER_TOOL_CALL,
    so two user messages count as one only when nothing ran between them.

    Args:
        all_transcript_lines: The session transcript, one JSON entry per line.
        spawn_tool_use_id: The id of the spawn under check, left out of the steps.
    """
    all_question_tool_use_ids: set[str] = set()
    return [
        each_step
        for each_line in all_transcript_lines
        for each_step in _entry_steps(each_line, all_question_tool_use_ids, spawn_tool_use_id)
    ]


def _request_position(all_steps: list[SessionStep]) -> int | None:
    all_user_positions = [
        each_position
        for each_position, each_step in enumerate(all_steps)
        if each_step is SessionStep.USER_MESSAGE
        and (each_position == 0 or all_steps[each_position - 1] is not SessionStep.USER_MESSAGE)
    ]
    if not all_user_positions:
        return None
    for each_index in range(len(all_user_positions) - 1, 0, -1):
        previous_position = all_user_positions[each_index - 1]
        current_position = all_user_positions[each_index]
        if SessionStep.QUESTION not in all_steps[previous_position:current_position]:
            return current_position
    return all_user_positions[0]


def readiness_gaps(all_steps: list[SessionStep]) -> list[str]:
    """Return the deny reasons the session has not yet cleared, in order.

    ::

        [USER_MESSAGE, READ, QUESTION, USER_MESSAGE]   -> []
        [USER_MESSAGE, QUESTION, USER_MESSAGE]         -> [investigation reason]
        [USER_MESSAGE, READ]                           -> [interview reason]
        [USER_MESSAGE, READ, QUESTION]                 -> [interview reason]

    The span starts at the request: the latest user message that answers no
    question. The interview passes when a user message in that span answers
    a question.

    Args:
        all_steps: The steps from ``session_steps``.
    """
    request_position = _request_position(all_steps)
    span_steps = all_steps if request_position is None else all_steps[request_position:]
    all_gaps: list[str] = []
    if SessionStep.READ not in span_steps:
        all_gaps.append(MISSING_INVESTIGATION_REASON)
    has_reply = any(
        each_step is SessionStep.USER_MESSAGE and SessionStep.QUESTION in span_steps[:each_position]
        for each_position, each_step in enumerate(span_steps)
    )
    if not has_reply:
        all_gaps.append(MISSING_INTERVIEW_REASON)
    return all_gaps
