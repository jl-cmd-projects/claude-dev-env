"""Deny a review thread resolve until a reply posted after the last user prompt and the last resolve."""

from __future__ import annotations

import sys
from collections.abc import Iterable
from pathlib import Path

hooks_directory = str(Path(__file__).resolve().parent.parent)
if hooks_directory not in sys.path:
    sys.path.insert(0, hooks_directory)

from blocking.pr_lifecycle_skill_gate import deny_decision, transcript_paths
from hooks_constants.pr_lifecycle_skill_gate_constants import SHELL_TOOL_NAMES
from hooks_constants.pre_tool_use_stdin import print_decision_from_stdin
from hooks_constants.resolve_thread_reply_gate_constants import (
    ALL_REPLY_TOOL_NAME_SUFFIXES,
    MISSING_REPLY_REASON,
    RESOLVE_TOOL_NAME_PATTERN,
    SHELL_COMMAND_KEY,
    SHELL_REPLY_COMMAND_PATTERN,
)
from hooks_constants.setup_project_paths_constants import DECODE_ERRORS_POLICY, UTF8_ENCODING
from transcript_skill_scan import TranscriptToolCall, tool_calls_since_last_prompt


def is_resolve_call(tool_name: object) -> bool:
    """Return whether a tool name resolves a review thread, such as ``mcp__github__resolve_review_thread``.

    Args:
        tool_name: The tool name from a hook payload or transcript.
    """
    return isinstance(tool_name, str) and RESOLVE_TOOL_NAME_PATTERN.match(tool_name) is not None


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
    command = tool_call.tool_input.get(SHELL_COMMAND_KEY)
    return (
        tool_call.name in SHELL_TOOL_NAMES
        and isinstance(command, str)
        and SHELL_REPLY_COMMAND_PATTERN.search(command) is not None
    )


def has_posted_reply_since_last_resolve(all_transcript_lines: Iterable[str]) -> bool:
    """Return whether a reply that succeeded since the last user prompt is not yet spent on a successful resolve.

    ::

        prompt, reply ok, resolve pending                                 -> True
        prompt, reply refused by a hook, resolve                          -> False
        prompt, resolve                                                   -> False
        prompt, reply ok, resolve ok, resolve pending                     -> False
        prompt, reply ok, reply ok, resolve ok, resolve pending           -> True

    Each successful resolve spends one successful reply. A failed or denied
    resolve spends none, so a retry after a resolve error needs no second reply.

    Args:
        all_transcript_lines: JSON transcript entries, one per line.
    """
    unspent_reply_count = 0
    for each_call in tool_calls_since_last_prompt(all_transcript_lines):
        if not each_call.succeeded:
            continue
        if is_resolve_call(each_call.name):
            unspent_reply_count = max(0, unspent_reply_count - 1)
        elif is_reply_call(each_call):
            unspent_reply_count += 1
    return unspent_reply_count > 0


def _transcript_shows_reply(transcript_path: str) -> bool | None:
    try:
        with open(transcript_path, encoding=UTF8_ENCODING, errors=DECODE_ERRORS_POLICY) as transcript:
            return has_posted_reply_since_last_resolve(transcript)
    except OSError:
        return None


def decision_for(all_payload_fields: dict[str, object]) -> dict[str, object] | None:
    """Return a deny for a review thread resolve with no posted reply before it, else None.

    ::

        resolve after a reply that posted        -> None
        resolve after a reply a hook refused     -> MISSING_REPLY_REASON
        resolve with no reply this turn          -> MISSING_REPLY_REASON
        second resolve after one reply           -> MISSING_REPLY_REASON
        resolve with an unreadable transcript    -> None
        any other tool                           -> None

    The gate reads the calling agent's own transcript: a subagent's file when
    the payload names one, else the session transcript.

    Args:
        all_payload_fields: The parsed PreToolUse input.
    """
    if not is_resolve_call(all_payload_fields.get("tool_name")):
        return None
    all_paths = transcript_paths(all_payload_fields)
    if not all_paths:
        return None
    shows_reply = _transcript_shows_reply(all_paths[-1])
    if shows_reply is None or shows_reply:
        return None
    return deny_decision(MISSING_REPLY_REASON)


def main() -> int:
    """Read one payload, print a deny when needed, and exit zero."""
    return print_decision_from_stdin(decision_for)


if __name__ == "__main__":
    sys.exit(main())
