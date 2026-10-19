"""Constants for the owned pull request merge Stop gate."""

import re

HOOK_EVENT_NAME = "Stop"
SESSION_ID_KEY = "session_id"
LAST_ASSISTANT_MESSAGE_KEY = "last_assistant_message"
DECISION_KEY = "decision"
BLOCK_DECISION = "block"
REASON_KEY = "reason"
ALLOW_EXIT_CODE = 0
GH_PROGRAM_NAME = "gh"
GH_API_SUBCOMMAND = "api"
GH_JQ_OPTION = "--jq"
PULL_REQUEST_ENDPOINT_TEMPLATE = "repos/{owner}/{repository}/pulls/{number}"
PULL_REQUEST_STATE_QUERY = ".state"
OPEN_PULL_REQUEST_STATE = "open"
STATE_QUERY_TIMEOUT_SECONDS = 8
BLOCKED_LINE_PATTERN: re.Pattern[str] = re.compile(
    r"^\s*(?:[-*]\s*)?blocked\b\s*[:\-]?(.*)$", re.IGNORECASE
)
BLOCKED_TEXT_GROUP_INDEX = 1
NAME_END_PATTERN = r"(?![0-9A-Za-z/])"
PULL_REQUEST_REFERENCE_TEMPLATE = "{owner}/{repository}#{number}"
PULL_REQUEST_LINE_TEMPLATE = "\n- {url}"
BLOCK_REASON_PREFIX = "You opened these owned pull requests and they are still open:"
BLOCK_REASON_SUFFIX = (
    "\nThe repository owner approves the whole owned PR loop, the merge included."
    " Keep working now: run /efficient-review until a pass is clean, mark the PR ready,"
    " babysit CI and review threads, then merge it and read it back as merged."
    " End the turn early only with one line per pull request:"
    " 'Blocked: <owner>/<repository>#<number> - <what only the owner can give>'."
)
