"""Deny a message that states a pull request's status until this turn read that pull request's state.

The gate covers messages to a user or another session. A message that calls a
pull request ready, open, mergeable, or in need of a merge, an approval, or queueing passes when a
state read of the same pull request ran since the last user prompt::

    "PR 29 is ready to merge." after get_check_runs only   -> deny
    "PR 29 is ready to merge." after pull_request_read get -> pass
    "PR 29 merged at 13:22."                               -> pass
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Iterable
from pathlib import Path

hooks_directory = str(Path(__file__).resolve().parent.parent)
if hooks_directory not in sys.path:
    sys.path.insert(0, hooks_directory)

from blocking.pr_lifecycle_skill_gate import deny_decision, transcript_paths
from hooks_constants.pr_state_claim_gate_constants import (
    ALL_MESSAGE_TOOL_NAME_PATTERNS,
    ALL_SHELL_TOOL_NAMES,
    ALL_STATUS_CLAIM_PATTERNS,
    DIGIT_RUN_PATTERN,
    FENCED_BLOCK_PATTERN,
    MESSAGE_FIELD_SEPARATOR,
    MISSING_STATE_READ_REASON,
    OUTPUT_FILTER_FLAG_PATTERN,
    OWNER_INPUT_KEY,
    PR_VIEW_COMMAND_PATTERN,
    PR_VIEW_JSON_FLAG_PATTERN,
    PR_VIEW_REPOSITORY_FLAG_PATTERN,
    PR_VIEW_STATE_FIELDS_PATTERN,
    PULL_REQUEST_BACKREFERENCE_PATTERN,
    PULL_REQUEST_HASH_REFERENCE_PATTERN,
    PULL_REQUEST_LIST_SEPARATOR,
    PULL_REQUEST_NUMBER_INPUT_KEY,
    PULL_REQUEST_NUMBER_PATTERN_TEMPLATE,
    PULL_REQUEST_READ_METHOD_KEY,
    PULL_REQUEST_READ_STATE_METHOD,
    PULL_REQUEST_READ_TOOL_NAME_PATTERN,
    PULL_REQUEST_URL_PATTERN,
    PULL_REQUEST_WORD_REFERENCE_PATTERN,
    REPOSITORY_INPUT_KEY,
    REST_PULLS_COMMAND_PATTERN,
    SENTENCE_BOUNDARY_PATTERN,
    SHELL_COMMAND_KEY,
)
from hooks_constants.pre_tool_use_stdin import print_decision_from_stdin
from hooks_constants.setup_project_paths_constants import DECODE_ERRORS_POLICY, UTF8_ENCODING
from transcript_skill_scan import TranscriptToolCall, tool_calls_since_last_prompt

ClaimedPullRequest = tuple[int, str | None]


def is_message_tool(tool_name: object) -> bool:
    """Return whether a tool name sends a message to a user or another session.

    Args:
        tool_name: The tool name from a hook payload.
    """
    return isinstance(tool_name, str) and any(
        each_pattern.match(tool_name) is not None for each_pattern in ALL_MESSAGE_TOOL_NAME_PATTERNS
    )


def _pull_requests_in_sentence(sentence_text: str) -> list[ClaimedPullRequest]:
    all_references: list[ClaimedPullRequest] = []
    for each_url_match in PULL_REQUEST_URL_PATTERN.finditer(sentence_text):
        each_repository, each_number = each_url_match.groups()
        all_references.append((int(each_number), each_repository.lower()))
    for each_word_match in PULL_REQUEST_WORD_REFERENCE_PATTERN.finditer(sentence_text):
        all_references.extend((int(each_digits), None) for each_digits in DIGIT_RUN_PATTERN.findall(each_word_match.group(1)))
    all_references.extend(
        (int(each_hash_match.group(1)), None)
        for each_hash_match in PULL_REQUEST_HASH_REFERENCE_PATTERN.finditer(sentence_text)
    )
    all_linked_numbers = {each_number for each_number, each_repository in all_references if each_repository}
    return [
        (each_number, each_repository)
        for each_number, each_repository in dict.fromkeys(all_references)
        if each_repository or each_number not in all_linked_numbers
    ]


def _states_status(sentence_text: str) -> bool:
    return any(each_pattern.search(sentence_text) is not None for each_pattern in ALL_STATUS_CLAIM_PATTERNS)


def claimed_pull_requests(message_text: str) -> list[ClaimedPullRequest]:
    """Return each pull request the message gives a status, as a number and the repository its link names, or None.

    A sentence that states a status, names no pull request, and points back with a word such as
    ``it``, ``this`` or ``the PR`` takes the pull requests of the nearest earlier sentence that
    names one::

        "PR 29 is ready to merge."                          -> [(29, None)]
        "[PR 7](https://github.com/o/r/pull/7) is open."    -> [(7, "o/r")]
        "PR 29 landed. It is ready to merge."               -> [(29, None)]
        "PR 29 merged at 13:22."                            -> []
        "PR 29 merged. The build is ready."                 -> []

    Args:
        message_text: The prose of one message.
    """
    prose_text = FENCED_BLOCK_PATTERN.sub("", message_text)
    nearest_references: list[ClaimedPullRequest] = []
    all_claims: list[ClaimedPullRequest] = []
    for each_sentence in SENTENCE_BOUNDARY_PATTERN.split(prose_text):
        sentence_references = _pull_requests_in_sentence(each_sentence)
        is_backreference = PULL_REQUEST_BACKREFERENCE_PATTERN.search(each_sentence) is not None
        claimed_references = sentence_references or (nearest_references if is_backreference else [])
        nearest_references = sentence_references or nearest_references
        if _states_status(each_sentence):
            all_claims.extend(each_reference for each_reference in claimed_references if each_reference not in all_claims)
    return all_claims


def _string_values(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    all_children = value.values() if isinstance(value, dict) else value if isinstance(value, list) else []
    return [each_text for each_child in all_children for each_text in _string_values(each_child)]


def _is_state_read_by_tool(tool_call: TranscriptToolCall, claim: ClaimedPullRequest) -> bool:
    if PULL_REQUEST_READ_TOOL_NAME_PATTERN.match(tool_call.name) is None:
        return False
    all_fields = tool_call.tool_input
    if all_fields.get(PULL_REQUEST_READ_METHOD_KEY) != PULL_REQUEST_READ_STATE_METHOD:
        return False
    if str(all_fields.get(PULL_REQUEST_NUMBER_INPUT_KEY)) != str(claim[0]):
        return False
    return claim[1] is None or f"{all_fields.get(OWNER_INPUT_KEY)}/{all_fields.get(REPOSITORY_INPUT_KEY)}".lower() == claim[1]


def _names_pull_request(segment_text: str, number: int) -> bool:
    token_pattern = re.compile(PULL_REQUEST_NUMBER_PATTERN_TEMPLATE.format(number=number))
    return token_pattern.search(segment_text) is not None


def _filter_keeps_state(command_text: str) -> bool:
    return all(
        PR_VIEW_STATE_FIELDS_PATTERN.search(each_filter.group(1)) is not None
        for each_filter in OUTPUT_FILTER_FLAG_PATTERN.finditer(command_text)
    )


def _view_urls_match(segment_text: str, claim: ClaimedPullRequest) -> bool:
    return all(
        claim[1] is None or each_url.group(1).lower() == claim[1]
        for each_url in PULL_REQUEST_URL_PATTERN.finditer(segment_text)
    )


def _is_state_read_by_view(command_text: str, claim: ClaimedPullRequest) -> bool:
    for each_view_match in PR_VIEW_COMMAND_PATTERN.finditer(command_text):
        segment_text = each_view_match.group()
        if not _names_pull_request(segment_text, claim[0]):
            continue
        json_flag = PR_VIEW_JSON_FLAG_PATTERN.search(segment_text)
        if json_flag is not None and PR_VIEW_STATE_FIELDS_PATTERN.search(segment_text[json_flag.end() :]) is None:
            continue
        repository_flag = PR_VIEW_REPOSITORY_FLAG_PATTERN.search(segment_text)
        is_repository_match = (
            claim[1] is None or repository_flag is None or repository_flag.group(1).lower() == claim[1]
        )
        if (
            is_repository_match
            and _view_urls_match(segment_text, claim)
            and _filter_keeps_state(command_text[each_view_match.start() :])
        ):
            return True
    return False


def _is_state_read_by_rest(command_text: str, claim: ClaimedPullRequest) -> bool:
    return any(
        int(each_match.group(2)) == claim[0]
        and (claim[1] is None or each_match.group(1).lower() == claim[1])
        and _filter_keeps_state(command_text[each_match.start() :])
        for each_match in REST_PULLS_COMMAND_PATTERN.finditer(command_text)
    )


def is_state_read(tool_call: TranscriptToolCall, claim: ClaimedPullRequest) -> bool:
    """Return whether a successful tool call read the state of the claimed pull request.

    ::

        pull_request_read {"method": "get", "pullNumber": 29}    -> True
        pull_request_read {"method": "get_check_runs", ...}      -> False
        Bash "gh pr view 29 --json state,mergedAt"               -> True
        Bash "gh pr view 29 --json title"                        -> False
        Bash "gh api repos/o/r/pulls/29"                         -> True
        Bash "gh api repos/o/r/pulls/29/reviews"                 -> False

    Args:
        tool_call: One tool call read from the transcript.
        claim: The pull request number and the repository its link names, or None.
    """
    if not tool_call.succeeded:
        return False
    if _is_state_read_by_tool(tool_call, claim):
        return True
    command_text = tool_call.tool_input.get(SHELL_COMMAND_KEY)
    if tool_call.name not in ALL_SHELL_TOOL_NAMES or not isinstance(command_text, str):
        return False
    return _is_state_read_by_view(command_text, claim) or _is_state_read_by_rest(command_text, claim)


def unread_pull_requests(message_text: str, all_transcript_lines: Iterable[str]) -> list[int]:
    """Return the number of each pull request the message gives a status that no state read this turn covers.

    Args:
        message_text: The prose of one message.
        all_transcript_lines: JSON transcript entries, one per line.
    """
    all_claims = claimed_pull_requests(message_text)
    if not all_claims:
        return []
    all_calls = tool_calls_since_last_prompt(all_transcript_lines)
    return [
        each_claim[0]
        for each_claim in all_claims
        if not any(is_state_read(each_call, each_claim) for each_call in all_calls)
    ]


def missing_state_read_reason(all_pull_request_numbers: list[int]) -> str:
    """Return the deny reason that names each pull request left without a state read.

    Args:
        all_pull_request_numbers: The numbers of the pull requests with no state read this turn.
    """
    return MISSING_STATE_READ_REASON.format(
        pull_requests=PULL_REQUEST_LIST_SEPARATOR.join(f"PR {each_number}" for each_number in dict.fromkeys(all_pull_request_numbers))
    )


def message_violation(message_text: str, all_transcript_paths: list[str]) -> str | None:
    """Return the deny reason for a message with a status claim and no state read this turn, or None.

    A transcript that cannot be read lets the message pass. The calling agent's own transcript
    is the last path.

    Args:
        message_text: The prose of one message.
        all_transcript_paths: The transcript paths the hook payload names, the agent's own last.
    """
    if not all_transcript_paths or not claimed_pull_requests(message_text):
        return None
    try:
        with open(all_transcript_paths[-1], encoding=UTF8_ENCODING, errors=DECODE_ERRORS_POLICY) as transcript:
            all_unread_numbers = unread_pull_requests(message_text, transcript)
    except OSError:
        return None
    return missing_state_read_reason(all_unread_numbers) if all_unread_numbers else None


def decision_for(all_payload_fields: dict[str, object]) -> dict[str, object] | None:
    """Return a deny for a message with a pull request status claim and no state read this turn, else None.

    Args:
        all_payload_fields: The parsed PreToolUse input.
    """
    if not is_message_tool(all_payload_fields.get("tool_name")):
        return None
    message_text = MESSAGE_FIELD_SEPARATOR.join(_string_values(all_payload_fields.get("tool_input")))
    reason = message_violation(message_text, transcript_paths(all_payload_fields))
    return deny_decision(reason) if reason is not None else None


def main() -> int:
    """Read one payload, print a deny when needed, and exit zero."""
    return print_decision_from_stdin(decision_for)


if __name__ == "__main__":
    sys.exit(main())
