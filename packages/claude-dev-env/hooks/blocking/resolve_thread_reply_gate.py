"""Deny a review thread resolve until a reply on that thread posted after the last user prompt and its last resolve."""

from __future__ import annotations

import json
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

hooks_directory = str(Path(__file__).resolve().parent.parent)
if hooks_directory not in sys.path:
    sys.path.insert(0, hooks_directory)

from blocking.pr_lifecycle_skill_gate import deny_decision, transcript_paths
from hooks_constants.pr_lifecycle_skill_gate_constants import SHELL_TOOL_NAMES
from hooks_constants.pre_tool_use_stdin import print_decision_from_stdin
from hooks_constants.resolve_thread_reply_gate_constants import (
    ALL_REPLY_TOOL_NAME_SUFFIXES,
    ALL_THREAD_ID_INPUT_KEYS,
    COMMENT_ANCHOR_PATTERN,
    COMMENT_ID_INPUT_KEY,
    MISSING_REPLY_REASON,
    RESOLVE_TOOL_NAME_PATTERN,
    SHELL_COMMAND_KEY,
    SHELL_REPLY_COMMAND_PATTERN,
    SHELL_REPLY_COMMENT_ID_PATTERN,
    SHELL_RESOLVE_COMMAND_PATTERN,
    SHELL_RESOLVE_COMMENT_ID_PATTERN,
    TEXT_BLOCK_TYPE,
    TEXT_FIELD,
    THREAD_ID_PATTERN,
)
from hooks_constants.setup_project_paths_constants import DECODE_ERRORS_POLICY, UTF8_ENCODING
from hooks_constants.transcript_skill_scan_constants import IS_ERROR_FIELD, TOOL_RESULT_BLOCK_TYPE
from transcript_skill_scan import TranscriptToolCall, tool_calls_since_last_prompt


def is_resolve_call(tool_name: object) -> bool:
    """Return whether a tool name resolves a review thread, such as ``mcp__github__resolve_review_thread``.

    Args:
        tool_name: The tool name from a hook payload or transcript.
    """
    return isinstance(tool_name, str) and RESOLVE_TOOL_NAME_PATTERN.match(tool_name) is not None


def _shell_command(tool_name: object, all_tool_input_fields: dict[str, object]) -> str | None:
    command = all_tool_input_fields.get(SHELL_COMMAND_KEY)
    return command if tool_name in SHELL_TOOL_NAMES and isinstance(command, str) else None


def resolved_thread_ids(tool_name: object, all_tool_input_fields: dict[str, object]) -> frozenset[str] | None:
    """Return the thread ids or comment ids a call resolves, or None when the call resolves no review thread.

    ::

        mcp__github__resolve_review_thread {"threadID": "PRRT_a"}  -> {"PRRT_a"}
        Bash "gh api graphql ... resolveReviewThread ... PRRT_a"   -> {"PRRT_a"}
        Bash "gh api graphql ... resolveReviewThread ... $thread"  -> {}
        Bash "gh api -X POST .../pulls/7/ccr/comments/9/resolve"   -> {"9"}
        Bash "gh pr view 7"                                        -> None

    Args:
        tool_name: The tool name from a hook payload or transcript.
        all_tool_input_fields: The tool input from a hook payload or transcript.
    """
    if is_resolve_call(tool_name):
        return frozenset(
            each_value
            for each_value in (all_tool_input_fields.get(each_key) for each_key in ALL_THREAD_ID_INPUT_KEYS)
            if isinstance(each_value, str) and each_value
        )
    command = _shell_command(tool_name, all_tool_input_fields)
    if command is None:
        return None
    all_resolved_comment_ids = frozenset(SHELL_RESOLVE_COMMENT_ID_PATTERN.findall(command))
    if not all_resolved_comment_ids and SHELL_RESOLVE_COMMAND_PATTERN.search(command) is None:
        return None
    return frozenset(THREAD_ID_PATTERN.findall(command)) | all_resolved_comment_ids


def is_reply_call(tool_call: TranscriptToolCall) -> bool:
    """Return whether a transcript tool call replies on a review thread.

    ::

        mcp__github__add_reply_to_pull_request_comment               -> True
        Bash "gh api repos/o/r/pulls/7/comments/99/replies -f body=x" -> True
        Bash "gh api graphql" with addPullRequestReviewThreadReply    -> True
        mcp__github__add_issue_comment                                -> False

    Args:
        tool_call: One tool call read from the transcript.
    """
    if tool_call.name.endswith(ALL_REPLY_TOOL_NAME_SUFFIXES):
        return True
    command = _shell_command(tool_call.name, tool_call.tool_input)
    return command is not None and SHELL_REPLY_COMMAND_PATTERN.search(command) is not None


def _reply_comment_ids(all_tool_input_fields: dict[str, object]) -> frozenset[str]:
    comment_id = all_tool_input_fields.get(COMMENT_ID_INPUT_KEY)
    if isinstance(comment_id, (int, float)) and not isinstance(comment_id, bool):
        return frozenset({str(int(comment_id))})
    if isinstance(comment_id, str) and comment_id.isdigit():
        return frozenset({comment_id})
    return frozenset()


def _reply_targets(tool_call: TranscriptToolCall) -> tuple[frozenset[str], frozenset[str]]:
    command = _shell_command(tool_call.name, tool_call.tool_input)
    if command is None:
        return frozenset(), _reply_comment_ids(tool_call.tool_input)
    return frozenset(THREAD_ID_PATTERN.findall(command)), frozenset(SHELL_REPLY_COMMENT_ID_PATTERN.findall(command))


def _result_content_texts(result_content: object) -> list[str]:
    if isinstance(result_content, str):
        return [result_content]
    all_parts = result_content if isinstance(result_content, list) else []
    return [
        each_part[TEXT_FIELD]
        for each_part in all_parts
        if isinstance(each_part, dict)
        and each_part.get("type") == TEXT_BLOCK_TYPE
        and isinstance(each_part.get(TEXT_FIELD), str)
    ]


def _successful_result_texts(all_entry_fields: dict[str, object]) -> Iterator[str]:
    message = all_entry_fields.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    for each_block in content if isinstance(content, list) else []:
        if not isinstance(each_block, dict) or each_block.get("type") != TOOL_RESULT_BLOCK_TYPE:
            continue
        if each_block.get(IS_ERROR_FIELD) is not True:
            yield from _result_content_texts(each_block.get("content"))


def _thread_ids_by_comment_id_in_text(text: str) -> dict[str, str]:
    all_thread_matches = list(THREAD_ID_PATTERN.finditer(text))
    all_span_ends = [each_match.start() for each_match in all_thread_matches[1:]] + [len(text)]
    return {
        each_anchor.group(1): each_thread_match.group()
        for each_thread_match, each_span_end in zip(all_thread_matches, all_span_ends)
        for each_anchor in COMMENT_ANCHOR_PATTERN.finditer(text, each_thread_match.end(), each_span_end)
    }


def thread_ids_by_comment_id(all_transcript_lines: Iterable[str]) -> dict[str, str]:
    """Return each review comment id mapped to its thread id, read from successful tool results.

    ::

        get_review_comments {"id": "PRRT_a", "comments": [{"html_url": "...#discussion_r9"}]}  -> {"9": "PRRT_a"}
        gh api graphql {"id": "PRRT_a", "comments": {"nodes": [{"databaseId": 9}]}}           -> {"9": "PRRT_a"}

    A comment id belongs to the nearest thread id before it in the same result text.

    Args:
        all_transcript_lines: JSON transcript entries, one per line.
    """
    thread_id_by_comment_id: dict[str, str] = {}
    for each_line in all_transcript_lines:
        try:
            entry_fields = json.loads(each_line)
        except ValueError:
            continue
        if not isinstance(entry_fields, dict):
            continue
        for each_text in _successful_result_texts(entry_fields):
            thread_id_by_comment_id.update(_thread_ids_by_comment_id_in_text(each_text))
    return thread_id_by_comment_id


def _thread_keys(all_ids: Iterable[str], all_thread_ids_by_comment_id: dict[str, str]) -> set[str]:
    return {all_thread_ids_by_comment_id.get(each_id, each_id) for each_id in all_ids}


def _keys_after_call(
    all_answered_keys: set[str], tool_call: TranscriptToolCall, all_thread_ids_by_comment_id: dict[str, str]
) -> set[str]:
    if not tool_call.succeeded:
        return all_answered_keys
    spent_thread_ids = resolved_thread_ids(tool_call.name, tool_call.tool_input)
    if spent_thread_ids is not None:
        return all_answered_keys - _thread_keys(spent_thread_ids, all_thread_ids_by_comment_id)
    if not is_reply_call(tool_call):
        return all_answered_keys
    reply_thread_ids, reply_comment_ids = _reply_targets(tool_call)
    return all_answered_keys | _thread_keys(reply_thread_ids | reply_comment_ids, all_thread_ids_by_comment_id)


def _answered_thread_keys(
    all_calls: Iterable[TranscriptToolCall], all_thread_ids_by_comment_id: dict[str, str]
) -> set[str]:
    answered_thread_keys: set[str] = set()
    for each_call in all_calls:
        answered_thread_keys = _keys_after_call(answered_thread_keys, each_call, all_thread_ids_by_comment_id)
    return answered_thread_keys


def has_posted_reply_on_threads(all_transcript_lines: Iterable[str], all_thread_ids: frozenset[str]) -> bool:
    """Return whether each named thread has a reply that succeeded since the last user prompt and its last resolve.

    ::

        prompt, read, reply ok on thread A, resolve A pending            -> True
        prompt, read, reply ok on thread A, resolve B pending            -> False
        prompt, reply refused by a hook, resolve A                       -> False
        prompt, reply ok on A, resolve A ok, resolve A pending           -> False
        prompt, reply ok on A and on B, resolve A ok, resolve B pending  -> True
        no thread ids                                                    -> False

    A successful resolve spends the replies on its threads. A failed or denied
    resolve spends none, so a retry after a resolve error needs no second reply.
    A reply by comment id counts for the thread that a successful tool result,
    such as ``pull_request_read`` ``get_review_comments``, lists the comment under,
    and for a resolve that names the same comment id.

    Args:
        all_transcript_lines: JSON transcript entries, one per line.
        all_thread_ids: The thread ids, or comment ids, the pending resolve names.
    """
    all_lines = list(all_transcript_lines)
    thread_id_by_comment_id = thread_ids_by_comment_id(all_lines)
    answered_thread_keys = _answered_thread_keys(tool_calls_since_last_prompt(all_lines), thread_id_by_comment_id)
    return bool(all_thread_ids) and _thread_keys(all_thread_ids, thread_id_by_comment_id) <= answered_thread_keys


def _transcript_shows_reply(transcript_path: str, all_thread_ids: frozenset[str]) -> bool | None:
    try:
        with open(transcript_path, encoding=UTF8_ENCODING, errors=DECODE_ERRORS_POLICY) as transcript:
            return has_posted_reply_on_threads(transcript, all_thread_ids)
    except OSError:
        return None


def decision_for(all_payload_fields: dict[str, object]) -> dict[str, object] | None:
    """Return a deny for a review thread resolve with no posted reply on that thread before it, else None.

    ::

        resolve after a reply on the thread that posted  -> None
        resolve after a reply on another thread          -> MISSING_REPLY_REASON
        resolve after a reply a hook refused             -> MISSING_REPLY_REASON
        resolve with no reply this turn                  -> MISSING_REPLY_REASON
        second resolve after one reply                   -> MISSING_REPLY_REASON
        gh api graphql resolveReviewThread, no reply     -> MISSING_REPLY_REASON
        gh api .../ccr/comments/9/resolve, no reply      -> MISSING_REPLY_REASON
        resolve with an unreadable transcript            -> None
        any other tool or shell command                  -> None

    The gate reads the calling agent's own transcript: a subagent's file when
    the payload names one, else the session transcript.

    Args:
        all_payload_fields: The parsed PreToolUse input.
    """
    tool_input = all_payload_fields.get("tool_input")
    all_thread_ids = resolved_thread_ids(
        all_payload_fields.get("tool_name"), tool_input if isinstance(tool_input, dict) else {}
    )
    if all_thread_ids is None:
        return None
    all_paths = transcript_paths(all_payload_fields)
    if not all_paths:
        return None
    shows_reply = _transcript_shows_reply(all_paths[-1], all_thread_ids)
    if shows_reply is None or shows_reply:
        return None
    return deny_decision(MISSING_REPLY_REASON)


def main() -> int:
    """Read one payload, print a deny when needed, and exit zero."""
    return print_decision_from_stdin(decision_for)


if __name__ == "__main__":
    sys.exit(main())
