#!/usr/bin/env python3
"""Stop hook that keeps a session working until its owned pull requests merge.

The owned pull request review-loop hook records each pull request the agent
opens on an owned repository outside the preset list. At the end of a turn
this gate asks GitHub for the state of each recorded pull request::

    allow: every recorded pull request reads closed (merged or closed)
    allow: the reply has "Blocked: acme/widgets#42 - the owner must approve"
    block: acme/widgets#42 reads open and the reply names no blocker for it

A block sends the open pull requests back as the reason, so the model keeps
working the loop. Claude Code ends the turn after eight blocks in a row, and
Codex turns the reason into a continuation prompt. A state lookup that fails,
such as a missing ``gh`` or no network, counts as closed, so the gate never
holds a turn on a fact it could not read. The failure goes to stderr, where
the host shows it in the hook log.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

hooks_root_directory = str(Path(__file__).resolve().parent.parent)
if hooks_root_directory not in sys.path:
    sys.path.insert(0, hooks_root_directory)

from hooks_constants.hook_block_logger import log_hook_block
from hooks_constants.owned_pr_merge_stop_gate_constants import (
    ALLOW_EXIT_CODE,
    BLOCK_DECISION,
    BLOCK_REASON_PREFIX,
    BLOCK_REASON_SUFFIX,
    BLOCKED_LINE_PATTERN,
    BLOCKED_TEXT_GROUP_INDEX,
    DECISION_KEY,
    GH_API_SUBCOMMAND,
    GH_JQ_OPTION,
    GH_PROGRAM_NAME,
    HOOK_EVENT_NAME,
    LAST_ASSISTANT_MESSAGE_KEY,
    LOOKUP_FAILURE_TEMPLATE,
    NAME_END_PATTERN,
    OPEN_PULL_REQUEST_STATE,
    PULL_REQUEST_ENDPOINT_TEMPLATE,
    PULL_REQUEST_LINE_TEMPLATE,
    PULL_REQUEST_REFERENCE_TEMPLATE,
    PULL_REQUEST_STATE_QUERY,
    REASON_KEY,
    SESSION_ID_KEY,
    STATE_QUERY_TIMEOUT_SECONDS,
)
from hooks_constants.pre_tool_use_stdin import read_hook_input_dictionary_from_stdin
from owned_pr_session_record import all_recorded_pull_requests


def is_pull_request_open(all_pull_request_fields: dict[str, str]) -> bool:
    """Return True when GitHub reports the pull request as open.

    Args:
        all_pull_request_fields: The owner, repository, number, and url fields.
    """
    endpoint = PULL_REQUEST_ENDPOINT_TEMPLATE.format(**all_pull_request_fields)
    try:
        completed = subprocess.run(
            [GH_PROGRAM_NAME, GH_API_SUBCOMMAND, endpoint, GH_JQ_OPTION, PULL_REQUEST_STATE_QUERY],
            capture_output=True,
            text=True,
            timeout=STATE_QUERY_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as lookup_error:
        sys.stderr.write(LOOKUP_FAILURE_TEMPLATE.format(endpoint=endpoint, detail=lookup_error))
        return False
    if completed.returncode != 0:
        sys.stderr.write(LOOKUP_FAILURE_TEMPLATE.format(endpoint=endpoint, detail=completed.stderr.strip()))
    return completed.returncode == 0 and completed.stdout.strip() == OPEN_PULL_REQUEST_STATE


def is_reported_blocked(all_pull_request_fields: dict[str, str], reply_text: str) -> bool:
    """Return True when a Blocked: line of the reply names the pull request.

    The line names it by ``owner/repository#number`` or by its url.

    Args:
        all_pull_request_fields: The owner, repository, number, and url fields.
        reply_text: The closing reply of the turn.
    """
    all_names = (
        PULL_REQUEST_REFERENCE_TEMPLATE.format(**all_pull_request_fields).lower(),
        all_pull_request_fields["url"].lower(),
    )
    all_blocked_texts = (
        each_match.group(BLOCKED_TEXT_GROUP_INDEX).lower()
        for each_match in map(BLOCKED_LINE_PATTERN.match, reply_text.splitlines())
        if each_match
    )
    all_name_patterns = [re.escape(each_name) + NAME_END_PATTERN for each_name in all_names]
    return any(
        re.search(each_pattern, each_text)
        for each_text in all_blocked_texts
        for each_pattern in all_name_patterns
    )


def unfinished_pull_requests(all_hook_input_fields: dict[str, object]) -> list[dict[str, str]]:
    """Return the recorded pull requests that are open and not reported blocked.

    Args:
        all_hook_input_fields: The Stop hook payload.
    """
    reply_value = all_hook_input_fields.get(LAST_ASSISTANT_MESSAGE_KEY)
    reply_text = reply_value if isinstance(reply_value, str) else ""
    return [
        each_pull_request
        for each_pull_request in all_recorded_pull_requests(
            all_hook_input_fields.get(SESSION_ID_KEY)
        )
        if not is_reported_blocked(each_pull_request, reply_text)
        and is_pull_request_open(each_pull_request)
    ]


def block_reason_for(all_open_pull_requests: list[dict[str, str]]) -> str:
    """Return the block reason that lists each open pull request.

    Args:
        all_open_pull_requests: The pull requests that hold the turn.
    """
    all_lines = (PULL_REQUEST_LINE_TEMPLATE.format(**each) for each in all_open_pull_requests)
    return BLOCK_REASON_PREFIX + "".join(all_lines) + BLOCK_REASON_SUFFIX


def main() -> int:
    hook_input = read_hook_input_dictionary_from_stdin()
    if hook_input is None:
        return ALLOW_EXIT_CODE
    all_open_pull_requests = unfinished_pull_requests(hook_input)
    if not all_open_pull_requests:
        return ALLOW_EXIT_CODE
    block_reason = block_reason_for(all_open_pull_requests)
    log_hook_block(Path(__file__).name, HOOK_EVENT_NAME, block_reason)
    sys.stdout.write(json.dumps({DECISION_KEY: BLOCK_DECISION, REASON_KEY: block_reason}))
    return ALLOW_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())
