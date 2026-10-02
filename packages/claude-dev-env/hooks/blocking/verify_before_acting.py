#!/usr/bin/env python3
"""PostToolUse hook that blocks a mutating call made on an unchecked claim.

The hook reads the thinking text of the assistant message that made the call,
found in the session transcript by the call's ``tool_use_id``. When that
reasoning hedges, the hook blocks and quotes the hedge sentence::

    flag: The config probably lives in settings.json.   -> Write blocks
    ok:   The config lives in settings.json, as read.   -> Write passes
    ok:   The config probably lives in settings.json.   -> gh pr view passes

The tool has already run, so the block reason tells the model to check the
claim now with a read-only tool and to undo the change when the check
contradicts it.

A call counts as mutating when its tool always writes (Write, Edit, Agent),
when its shell command matches ALL_MUTATING_COMMAND_PATTERNS, or when an MCP
tool's last name segment holds a write verb as one of its words and no read
verb. Every other call is a check and passes with no log line.

Each mutating call writes one JSON line to DECISION_LOG_RELATIVE_PATH under
the home directory: blocked, allowed_clean, or reasoning_unseen when the
transcript record is missing or its thinking text is empty. A missing or
unreadable input always allows, so the hook never fails closed.
"""

from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)

from hooks_constants.bash_post_call_dispatcher_constants import (
    HOOK_EVENT_NAME_KEY,
    HOOK_SPECIFIC_OUTPUT_KEY,
    POST_TOOL_USE_HOOK_EVENT_NAME,
)
from hooks_constants.hook_block_logger import log_hook_block
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
from hooks_constants.verify_before_acting_constants import (
    ALL_ALWAYS_MUTATING_TOOL_NAMES,
    ALL_MCP_MUTATING_VERBS,
    ALL_MCP_READ_VERBS,
    ALL_MUTATING_COMMAND_PATTERNS,
    ALL_SHELL_TOOL_NAMES,
    ALLOW_EXIT_CODE,
    BLOCK_DECISION,
    BLOCK_ID_KEY,
    BLOCK_REASON_TEMPLATE,
    BLOCK_TYPE_KEY,
    COMMAND_KEY,
    CONTENT_KEY,
    DECISION_KEY,
    DECISION_LOG_RELATIVE_PATH,
    LOG_APPEND_MODE,
    LOG_LINE_END,
    HEDGE_PATTERN,
    LOG_HEDGE_SENTENCE_KEY,
    LOG_OUTCOME_KEY,
    LOG_TIMESTAMP_KEY,
    LOG_TOOL_NAME_KEY,
    LOG_TOOL_USE_ID_KEY,
    MAXIMUM_QUOTE_LENGTH,
    MCP_ACTION_WORD_SPLIT_PATTERN,
    MCP_SEGMENT_SEPARATOR,
    MCP_TOOL_PREFIX,
    MESSAGE_ID_KEY,
    MESSAGE_KEY,
    OUTCOME_ALLOWED_CLEAN,
    OUTCOME_BLOCKED,
    OUTCOME_REASONING_UNSEEN,
    QUOTE_LEAD_LENGTH,
    REASON_KEY,
    SENTENCE_SPLIT_PATTERN,
    THINKING_BLOCK_TYPE,
    THINKING_JOINER,
    THINKING_TEXT_KEY,
    TOOL_INPUT_KEY,
    TOOL_NAME_KEY,
    TOOL_USE_BLOCK_TYPE,
    TOOL_USE_ID_KEY,
    TRANSCRIPT_DECODE_ERRORS,
    TRANSCRIPT_ENCODING,
    TRANSCRIPT_PATH_KEY,
    TRIM_MARKER,
    WHITESPACE_RUN_PATTERN,
    WORD_SEPARATOR,
)

def is_mutating_call(tool_name: str, tool_input: object) -> bool:
    """Return True when the call writes, sends, or spawns rather than reads."""
    if tool_name in ALL_ALWAYS_MUTATING_TOOL_NAMES:
        return True
    if tool_name in ALL_SHELL_TOOL_NAMES:
        command = tool_input.get(COMMAND_KEY) if isinstance(tool_input, dict) else None
        return isinstance(command, str) and any(
            each_pattern.search(command) for each_pattern in ALL_MUTATING_COMMAND_PATTERNS
        )
    if tool_name.startswith(MCP_TOOL_PREFIX):
        last_segment = tool_name.rsplit(MCP_SEGMENT_SEPARATOR, maxsplit=1)[-1]
        all_action_words = {
            each_word.lower()
            for each_word in MCP_ACTION_WORD_SPLIT_PATTERN.split(last_segment)
            if each_word
        }
        return bool(all_action_words & ALL_MCP_MUTATING_VERBS) and not (
            all_action_words & ALL_MCP_READ_VERBS
        )
    return False


def _parsed_record(transcript_line: str) -> dict[str, object] | None:
    try:
        parsed_line = json.loads(transcript_line)
    except json.JSONDecodeError:
        return None
    return parsed_line if isinstance(parsed_line, dict) else None


def _message_of(all_record_fields: dict[str, object] | None) -> dict[str, object]:
    message = all_record_fields.get(MESSAGE_KEY) if all_record_fields is not None else None
    return message if isinstance(message, dict) else {}


def _content_blocks(all_record_fields: dict[str, object] | None) -> list[dict[str, object]]:
    all_content = _message_of(all_record_fields).get(CONTENT_KEY)
    if not isinstance(all_content, list):
        return []
    return [each_block for each_block in all_content if isinstance(each_block, dict)]


def _thinking_texts(all_blocks: list[dict[str, object]]) -> list[str]:
    all_thinking_values = [
        each_block.get(THINKING_TEXT_KEY)
        for each_block in all_blocks
        if each_block.get(BLOCK_TYPE_KEY) == THINKING_BLOCK_TYPE
    ]
    return [each_value for each_value in all_thinking_values if isinstance(each_value, str)]


def _tool_use_position(all_blocks: list[dict[str, object]], tool_use_id: str) -> int | None:
    for each_position, each_block in enumerate(all_blocks):
        if (
            each_block.get(BLOCK_TYPE_KEY) == TOOL_USE_BLOCK_TYPE
            and each_block.get(BLOCK_ID_KEY) == tool_use_id
        ):
            return each_position
    return None


def _earlier_thinking(all_earlier_lines: list[str], message_id: str) -> list[str]:
    all_texts: list[str] = []
    for each_line in all_earlier_lines:
        if message_id not in each_line:
            continue
        record = _parsed_record(each_line)
        if _message_of(record).get(MESSAGE_ID_KEY) == message_id:
            all_texts.extend(_thinking_texts(_content_blocks(record)))
    return all_texts


def acting_reasoning(all_transcript_lines: list[str], tool_use_id: str) -> str | None:
    """Return the thinking text of the message that made the call, or None when unfound.

    Scans from the end for the record whose ``tool_use`` block carries the id,
    then joins the thinking blocks of every earlier record sharing its
    ``message.id`` with the thinking that precedes the call in its own record.
    Only lines holding the id substring are parsed, so a long transcript stays
    inside the hook timeout.
    """
    for each_index in range(len(all_transcript_lines) - 1, -1, -1):
        transcript_line = all_transcript_lines[each_index]
        if tool_use_id not in transcript_line:
            continue
        record = _parsed_record(transcript_line)
        all_blocks = _content_blocks(record)
        tool_use_position = _tool_use_position(all_blocks, tool_use_id)
        if tool_use_position is None:
            continue
        message_id = _message_of(record).get(MESSAGE_ID_KEY)
        all_texts = (
            _earlier_thinking(all_transcript_lines[:each_index], message_id)
            if isinstance(message_id, str) and message_id
            else []
        )
        all_texts.extend(_thinking_texts(all_blocks[:tool_use_position]))
        return THINKING_JOINER.join(all_texts)
    return None


def _transcript_lines(transcript_path_value: object) -> list[str] | None:
    if not isinstance(transcript_path_value, str) or not transcript_path_value:
        return None
    try:
        transcript_text = Path(transcript_path_value).read_text(
            encoding=TRANSCRIPT_ENCODING, errors=TRANSCRIPT_DECODE_ERRORS
        )
    except (OSError, ValueError):
        return None
    return transcript_text.splitlines()


def _quoted_excerpt(sentence: str, hedge_start: int) -> str:
    if len(sentence) <= MAXIMUM_QUOTE_LENGTH:
        return sentence
    window_start = max(
        0, min(hedge_start - QUOTE_LEAD_LENGTH, len(sentence) - MAXIMUM_QUOTE_LENGTH)
    )
    window_end = window_start + MAXIMUM_QUOTE_LENGTH
    leading_marker = TRIM_MARKER if window_start > 0 else ""
    trailing_marker = TRIM_MARKER if window_end < len(sentence) else ""
    return leading_marker + sentence[window_start:window_end].strip() + trailing_marker


def first_hedge_sentence(reasoning: str) -> str | None:
    """Return the first hedge sentence, trimmed around its hedge phrase, or None."""
    for each_sentence in SENTENCE_SPLIT_PATTERN.split(reasoning):
        normalized_sentence = WHITESPACE_RUN_PATTERN.sub(WORD_SEPARATOR, each_sentence).strip()
        hedge_match = HEDGE_PATTERN.search(normalized_sentence)
        if hedge_match is not None:
            return _quoted_excerpt(normalized_sentence, hedge_match.start())
    return None


def _log_decision(
    tool_name: str, tool_use_id: object, outcome: str, hedge_sentence: str | None
) -> None:
    try:
        log_path = Path.home() / DECISION_LOG_RELATIVE_PATH
    except RuntimeError:
        return
    log_record: dict[str, object] = {
        LOG_TIMESTAMP_KEY: datetime.datetime.now().isoformat(),
        LOG_TOOL_NAME_KEY: tool_name,
        LOG_TOOL_USE_ID_KEY: tool_use_id if isinstance(tool_use_id, str) else None,
        LOG_OUTCOME_KEY: outcome,
    }
    if hedge_sentence is not None:
        log_record[LOG_HEDGE_SENTENCE_KEY] = hedge_sentence
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open(LOG_APPEND_MODE, encoding=TRANSCRIPT_ENCODING) as log_file:
            log_file.write(json.dumps(log_record) + LOG_LINE_END)
    except OSError:
        pass


def _call_reasoning(all_hook_fields: dict[str, object]) -> str | None:
    tool_use_id = all_hook_fields.get(TOOL_USE_ID_KEY)
    if not isinstance(tool_use_id, str) or not tool_use_id:
        return None
    all_transcript_lines = _transcript_lines(all_hook_fields.get(TRANSCRIPT_PATH_KEY))
    if all_transcript_lines is None:
        return None
    return acting_reasoning(all_transcript_lines, tool_use_id)


def _emit_block(tool_name: str, tool_use_id: object, hedge_sentence: str) -> None:
    block_reason = BLOCK_REASON_TEMPLATE.format(tool_name=tool_name, hedge_sentence=hedge_sentence)
    _log_decision(tool_name, tool_use_id, OUTCOME_BLOCKED, hedge_sentence)
    log_hook_block(
        Path(__file__).name,
        POST_TOOL_USE_HOOK_EVENT_NAME,
        block_reason,
        tool_name=tool_name,
        offending_input_preview=hedge_sentence,
    )
    block_payload = {
        DECISION_KEY: BLOCK_DECISION,
        REASON_KEY: block_reason,
        HOOK_SPECIFIC_OUTPUT_KEY: {HOOK_EVENT_NAME_KEY: POST_TOOL_USE_HOOK_EVENT_NAME},
    }
    sys.stdout.write(json.dumps(block_payload))


def main() -> int:
    hook_input = read_hook_input_dictionary_from_stdin()
    if hook_input is None:
        return ALLOW_EXIT_CODE
    tool_name = hook_input.get(TOOL_NAME_KEY)
    if not isinstance(tool_name, str) or not is_mutating_call(
        tool_name, hook_input.get(TOOL_INPUT_KEY)
    ):
        return ALLOW_EXIT_CODE
    tool_use_id = hook_input.get(TOOL_USE_ID_KEY)
    reasoning = _call_reasoning(hook_input)
    if reasoning is None or not reasoning.strip():
        _log_decision(tool_name, tool_use_id, OUTCOME_REASONING_UNSEEN, None)
        return ALLOW_EXIT_CODE
    hedge_sentence = first_hedge_sentence(reasoning)
    if hedge_sentence is None:
        _log_decision(tool_name, tool_use_id, OUTCOME_ALLOWED_CLEAN, None)
        return ALLOW_EXIT_CODE
    _emit_block(tool_name, tool_use_id, hedge_sentence)
    return ALLOW_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())
