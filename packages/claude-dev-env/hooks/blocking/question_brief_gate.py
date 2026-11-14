#!/usr/bin/env python3
"""PreToolUse hook that refuses a question after a long chat brief.

Registered on ``AskUserQuestion``. The user reviews items one question at a
time. The hook measures the chat text Claude wrote in the current turn before
the question: the text after the latest of these marks.

- A prompt the user typed, or a message the user queued mid-turn.
- A result of an earlier question, refused or answered.
- The first input after an earlier turn ended with an ``end_turn`` message or
  a ``stop_hook_summary`` entry. A turn that a task notification or an agent
  message starts never counts the text before it. A Stop hook that holds the
  turn adds no input, so the text before a held stop still counts.

::

    40-word brief, then the question           -> exit 0
    a 30-row table, then the question          -> exit 2, reason on stderr
    600 words, refused question, short brief   -> exit 0 on the retry

Lines inside a code fence are not list items. A table's header and separator
rows are not items; each body row is one.

Claude Code writes the message holding the call to the transcript after this
hook starts, so the hook polls the transcript tail until its own tool_use
entry appears, up to ``TRANSCRIPT_POLL_LIMIT_SECONDS``. That wait is the only
poll. A payload or transcript the hook cannot read, a transcript path that
is not a regular file, a call that does not appear in time, a subagent call,
and any other tool pass with exit 0.

The hook reads only the last ``TAIL_WINDOW_BYTES`` (1 MB) of the transcript,
so a long review followed by more than 1 MB of tool output in the same turn
is not seen.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Iterable, Iterator
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)

from blocking.step_note_gate import entry_content_blocks, read_transcript_tail
from hooks_constants.ask_user_question_shape import count_prose_words
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
from hooks_constants.question_brief_gate_constants import (
    ALL_HELD_STOP_PROMPT_PREFIXES,
    ALL_MACHINE_PROMPT_PREFIXES,
    ALL_NOT_TYPED_BY_USER_FLAGS,
    ALL_TURN_END_SYSTEM_SUBTYPES,
    ALLOW_EXIT_CODE,
    ASSISTANT_ENTRY_TYPE,
    ATTACHMENT_ENTRY_TYPE,
    ATTACHMENT_KEY,
    BLOCK_EXIT_CODE,
    BLOCK_ID_KEY,
    BLOCK_NAME_KEY,
    BLOCK_TYPE_KEY,
    BRIEF_TEXT_SEPARATOR,
    CODE_FENCE_LINE_PATTERN,
    ENTRY_TYPE_KEY,
    LIST_ITEM_LIMIT_PART_TEMPLATE,
    LIST_ITEM_LINE_PATTERN,
    MAXIMUM_BRIEF_LIST_ITEM_COUNT,
    MAXIMUM_BRIEF_WORD_COUNT,
    MESSAGE_KEY,
    PROMPT_TEXT_SEPARATOR,
    QUESTION_TOOL_NAME,
    QUEUED_COMMAND_ATTACHMENT_TYPE,
    QUEUED_PROMPT_KEY,
    REFUSAL_LIMIT_PART_SEPARATOR,
    REFUSAL_MESSAGE_TEMPLATE,
    RESULT_TOOL_USE_ID_KEY,
    STOP_REASON_KEY,
    SUBAGENT_ID_PAYLOAD_KEY,
    SUBTYPE_KEY,
    SYSTEM_ENTRY_TYPE,
    TABLE_ROW_LINE_PATTERN,
    TABLE_SEPARATOR_LINE_PATTERN,
    TEXT_BLOCK_TYPE,
    TEXT_KEY,
    TOOL_NAME_PAYLOAD_KEY,
    TOOL_RESULT_BLOCK_TYPE,
    TOOL_USE_BLOCK_TYPE,
    TOOL_USE_ID_PAYLOAD_KEY,
    TRANSCRIPT_PATH_PAYLOAD_KEY,
    TRANSCRIPT_POLL_INTERVAL_SECONDS,
    TRANSCRIPT_POLL_LIMIT_SECONDS,
    TURN_END_STOP_REASON,
    USER_ENTRY_TYPE,
    WORD_LIMIT_PART_TEMPLATE,
)


def _content_blocks(entry: dict) -> list[dict]:
    if not isinstance(entry.get(MESSAGE_KEY), dict):
        return []
    return entry_content_blocks(entry)


def _is_typed_prompt(prompt_text: object) -> bool:
    return (
        isinstance(prompt_text, str)
        and bool(prompt_text.strip())
        and not prompt_text.lstrip().startswith(ALL_MACHINE_PROMPT_PREFIXES)
    )


def _is_earlier_question_result(result_block: dict, all_question_ids: set[str]) -> bool:
    result_tool_use_id = result_block.get(RESULT_TOOL_USE_ID_KEY)
    return isinstance(result_tool_use_id, str) and result_tool_use_id in all_question_ids


def _is_user_input(entry: dict, all_question_ids: set[str]) -> bool:
    entry_type = entry.get(ENTRY_TYPE_KEY)
    if entry_type == ATTACHMENT_ENTRY_TYPE:
        attachment = entry.get(ATTACHMENT_KEY)
        return (
            isinstance(attachment, dict)
            and attachment.get(ENTRY_TYPE_KEY) == QUEUED_COMMAND_ATTACHMENT_TYPE
            and _is_typed_prompt(attachment.get(QUEUED_PROMPT_KEY))
        )
    if entry_type != USER_ENTRY_TYPE or any(
        entry.get(each_flag) for each_flag in ALL_NOT_TYPED_BY_USER_FLAGS
    ):
        return False
    all_blocks = _content_blocks(entry)
    all_results = [
        each_block
        for each_block in all_blocks
        if each_block.get(BLOCK_TYPE_KEY) == TOOL_RESULT_BLOCK_TYPE
    ]
    if all_results:
        return any(
            _is_earlier_question_result(each_result, all_question_ids)
            for each_result in all_results
        )
    return _is_typed_prompt(
        PROMPT_TEXT_SEPARATOR.join(str(each_block.get(TEXT_KEY, "")) for each_block in all_blocks)
    )


def _is_turn_end(entry: dict) -> bool:
    if entry.get(ENTRY_TYPE_KEY) == SYSTEM_ENTRY_TYPE:
        subtype = entry.get(SUBTYPE_KEY)
        return isinstance(subtype, str) and subtype in ALL_TURN_END_SYSTEM_SUBTYPES
    message = entry.get(MESSAGE_KEY)
    return (
        entry.get(ENTRY_TYPE_KEY) == ASSISTANT_ENTRY_TYPE
        and isinstance(message, dict)
        and message.get(STOP_REASON_KEY) == TURN_END_STOP_REASON
    )


def _is_next_turn_input(entry: dict) -> bool:
    entry_type = entry.get(ENTRY_TYPE_KEY)
    if entry_type == ATTACHMENT_ENTRY_TYPE:
        attachment = entry.get(ATTACHMENT_KEY)
        return (
            isinstance(attachment, dict)
            and attachment.get(ENTRY_TYPE_KEY) == QUEUED_COMMAND_ATTACHMENT_TYPE
        )
    prompt_text = PROMPT_TEXT_SEPARATOR.join(
        str(each_block.get(TEXT_KEY, "")) for each_block in _content_blocks(entry)
    )
    is_held_stop_feedback = prompt_text.lstrip().startswith(ALL_HELD_STOP_PROMPT_PREFIXES)
    return entry_type == USER_ENTRY_TYPE and not is_held_stop_feedback


def _is_turn_ended_after(entry: dict, is_turn_ended: bool) -> bool:
    if _is_turn_end(entry):
        return True
    if entry.get(ENTRY_TYPE_KEY) == ASSISTANT_ENTRY_TYPE or _is_next_turn_input(entry):
        return False
    return is_turn_ended


def _assistant_blocks(entry: dict) -> list[dict]:
    if entry.get(ENTRY_TYPE_KEY) != ASSISTANT_ENTRY_TYPE:
        return []
    return _content_blocks(entry)


def _is_question_call(block: dict) -> bool:
    return (
        block.get(BLOCK_TYPE_KEY) == TOOL_USE_BLOCK_TYPE
        and block.get(BLOCK_NAME_KEY) == QUESTION_TOOL_NAME
    )


def _starts_new_count(entry: dict, all_question_ids: set[str], is_turn_ended: bool) -> bool:
    return _is_user_input(entry, all_question_ids) or (
        is_turn_ended and _is_next_turn_input(entry)
    )


def _counted_blocks(
    all_entries: Iterable[dict], all_question_ids: set[str]
) -> Iterator[dict | None]:
    is_turn_ended = False
    for each_entry in all_entries:
        if _starts_new_count(each_entry, all_question_ids, is_turn_ended):
            yield None
        yield from _assistant_blocks(each_entry)
        is_turn_ended = _is_turn_ended_after(each_entry, is_turn_ended)


def _question_call_id(block: dict) -> str | None:
    if not _is_question_call(block):
        return None
    return str(block.get(BLOCK_ID_KEY))


def _block_texts(block: dict) -> list[str]:
    block_text = block.get(TEXT_KEY)
    if block.get(BLOCK_TYPE_KEY) != TEXT_BLOCK_TYPE or not isinstance(block_text, str):
        return []
    return [block_text]


def brief_before_question(all_entries: Iterable[dict], tool_use_id: str) -> str | None:
    """Return the chat text Claude wrote this turn before this call.

    ::

        prompt, text "A.", tool result, text "B.", this call  -> "A.\\nB."
        prompt, text "A.", earlier question result, this call -> ""
        prompt, text "A." ending the turn, held stop, this call -> "A."

    Args:
        all_entries: Transcript entries, oldest first.
        tool_use_id: The id of the question call being checked.

    Returns:
        The text blocks joined by line breaks, or None before the call is written.
    """
    all_question_ids: set[str] = set()
    all_brief_texts: list[str] = []
    for each_block in _counted_blocks(all_entries, all_question_ids):
        if each_block is None:
            all_brief_texts = []
            continue
        question_id = _question_call_id(each_block)
        if question_id == tool_use_id:
            return BRIEF_TEXT_SEPARATOR.join(all_brief_texts)
        if question_id is not None:
            all_question_ids.add(question_id)
            continue
        all_brief_texts.extend(_block_texts(each_block))
    return None


def _lines_outside_code_fences(brief_text: str) -> list[str]:
    all_outside_lines: list[str] = []
    is_inside_fence = False
    for each_line in brief_text.splitlines():
        if CODE_FENCE_LINE_PATTERN.match(each_line):
            is_inside_fence = not is_inside_fence
            continue
        if not is_inside_fence:
            all_outside_lines.append(each_line)
    return all_outside_lines


def _is_item_line(line: str, next_line: str) -> bool:
    if LIST_ITEM_LINE_PATTERN.match(line):
        return True
    return bool(
        TABLE_ROW_LINE_PATTERN.match(line)
        and not TABLE_SEPARATOR_LINE_PATTERN.match(line)
        and not TABLE_SEPARATOR_LINE_PATTERN.match(next_line)
    )


def count_list_items(brief_text: str) -> int:
    """Return how many bullet, numbered, and table body lines the text holds.

    A table's header row and its separator row are not items, and lines
    inside a code fence are not items.

    ::

        "- a\\n- b"                       -> 2
        "| # | What |\\n|---|---|\\n| 1 | x |" -> 1
        "```\\n- a\\n- b\\n```"            -> 0
    """
    all_lines = _lines_outside_code_fences(brief_text)
    return sum(
        _is_item_line(each_line, each_next_line)
        for each_line, each_next_line in zip(all_lines, [*all_lines[1:], ""])
    )


def refusal_reason(brief_text: str) -> str | None:
    """Return the refusal text naming each limit the brief passed, or None when it fits."""
    word_count = count_prose_words(brief_text)
    list_item_count = count_list_items(brief_text)
    all_limit_parts: list[str] = []
    if word_count > MAXIMUM_BRIEF_WORD_COUNT:
        all_limit_parts.append(
            WORD_LIMIT_PART_TEMPLATE.format(count=word_count, maximum=MAXIMUM_BRIEF_WORD_COUNT)
        )
    if list_item_count > MAXIMUM_BRIEF_LIST_ITEM_COUNT:
        all_limit_parts.append(
            LIST_ITEM_LIMIT_PART_TEMPLATE.format(
                count=list_item_count, maximum=MAXIMUM_BRIEF_LIST_ITEM_COUNT
            )
        )
    if not all_limit_parts:
        return None
    return REFUSAL_MESSAGE_TEMPLATE.format(
        limit_parts=REFUSAL_LIMIT_PART_SEPARATOR.join(all_limit_parts)
    )


def _is_readable_file(transcript_path: Path) -> bool:
    try:
        if not transcript_path.is_file():
            return False
        with transcript_path.open("rb"):
            return True
    except OSError:
        return False


def _wait_for_brief(transcript_path: Path, tool_use_id: str) -> str | None:
    deadline = time.monotonic() + TRANSCRIPT_POLL_LIMIT_SECONDS
    while True:
        try:
            all_entries = read_transcript_tail(transcript_path)
        except RecursionError:
            return None
        brief_text = brief_before_question(all_entries, tool_use_id)
        if brief_text is not None or time.monotonic() >= deadline:
            return brief_text
        time.sleep(TRANSCRIPT_POLL_INTERVAL_SECONDS)


def _read_payload() -> dict[str, object] | None:
    try:
        return read_hook_input_dictionary_from_stdin()
    except RecursionError:
        return None


def main() -> int:
    """Read the PreToolUse payload and refuse a question after a long brief.

    Returns:
        2 with the reason on stderr to refuse, else 0.
    """
    hook_payload = _read_payload()
    if hook_payload is None or hook_payload.get(SUBAGENT_ID_PAYLOAD_KEY):
        return ALLOW_EXIT_CODE
    tool_use_id = hook_payload.get(TOOL_USE_ID_PAYLOAD_KEY)
    transcript_path_text = hook_payload.get(TRANSCRIPT_PATH_PAYLOAD_KEY)
    if (
        hook_payload.get(TOOL_NAME_PAYLOAD_KEY) != QUESTION_TOOL_NAME
        or not isinstance(tool_use_id, str)
        or not tool_use_id
        or not isinstance(transcript_path_text, str)
    ):
        return ALLOW_EXIT_CODE
    transcript_path = Path(transcript_path_text)
    if not _is_readable_file(transcript_path):
        return ALLOW_EXIT_CODE
    brief_text = _wait_for_brief(transcript_path, tool_use_id)
    if brief_text is None:
        return ALLOW_EXIT_CODE
    reason = refusal_reason(brief_text)
    if reason is None:
        return ALLOW_EXIT_CODE
    sys.stderr.write(reason)
    return BLOCK_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())
