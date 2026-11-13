"""Constants for the gate that holds a pull request status claim until the same turn read that pull request's state."""

import re

ALL_MESSAGE_TOOL_NAME_PATTERNS = (
    re.compile(r"^mcp__.+__(?:post_message|message_coordinator|message_thread|request_decision|edit_message)$"),
    re.compile(r"^SendMessage$"),
)
PULL_REQUEST_READ_TOOL_NAME_PATTERN = re.compile(r"^mcp__.+__pull_request_read$")
PULL_REQUEST_READ_METHOD_KEY = "method"
PULL_REQUEST_READ_STATE_METHOD = "get"
PULL_REQUEST_NUMBER_INPUT_KEY = "pullNumber"
OWNER_INPUT_KEY = "owner"
REPOSITORY_INPUT_KEY = "repo"
SHELL_COMMAND_KEY = "command"
SENTENCE_BOUNDARY_PATTERN = re.compile(r"(?<=[.!?])\s+|\n+")
FENCED_BLOCK_PATTERN = re.compile(r"```.*?```", re.DOTALL)
PULL_REQUEST_URL_PATTERN = re.compile(r"https?://github\.com/([\w.-]+/[\w.-]+)/pull/(\d+)", re.IGNORECASE)
PULL_REQUEST_WORD_REFERENCE_PATTERN = re.compile(
    r"\b(?:PRs?|pull\s+requests?)\s*#?(\d+(?:\s*(?:,|and|&)\s*#?\d+)*)", re.IGNORECASE
)
PULL_REQUEST_HASH_REFERENCE_PATTERN = re.compile(r"(?<![\w&#])#(\d+)\b")
DIGIT_RUN_PATTERN = re.compile(r"\d+")
ALL_STATUS_CLAIM_PATTERNS = (
    re.compile(
        r"(?<!not )(?<!yet )(?<!n't )\bready\s+(?:to|for)\s+(?:merge|merging|queue|queueing|queuing|land|landing)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:is|are|now|still)\s+ready\b(?!\s+(?:for|to)\s+(?!merg|queu|land))", re.IGNORECASE),
    re.compile(r"\bmergeable\b", re.IGNORECASE),
    re.compile(r"\b(?:is|are|still|remains|stays|now)\s+open\b", re.IGNORECASE),
    re.compile(r"\bneeds?\s+(?:your\s+|his\s+|their\s+)?(?:merg\w*|approv\w*|queu\w*)", re.IGNORECASE),
    re.compile(r"\bawaiting\s+(?:your\s+)?(?:merge|merging|approval|queue|queueing)\b", re.IGNORECASE),
    re.compile(
        r"\b(?:merge|queue|approve)\s+(?:it|this|that|(?:PR|pull\s+request)\s*#?\d+|#\d+)", re.IGNORECASE
    ),
)
PULL_REQUEST_LIST_SEPARATOR = ", "
MESSAGE_FIELD_SEPARATOR = "\n"
PULL_REQUEST_BACKREFERENCE_PATTERN = re.compile(
    r"\b(?:it|its|this|that|they|the\s+(?:PR|pull\s+request))\b", re.IGNORECASE
)
OUTPUT_FILTER_FLAG_PATTERN = re.compile(
    r"(?:--jq|--template|(?<=\s)-q|(?<=\s)-t)[\s=]+('[^']*'|\"[^\"]*\"|\S+)"
)
PIPE_PATTERN = re.compile(r"(?<!\|)\|(?!\|)(.*)", re.DOTALL)
ALL_PASSTHROUGH_COMMANDS = frozenset({"cat", "head", "tail", "less", "more", "tee"})
ALL_SHELL_TOOL_NAMES = ("Bash", "PowerShell")
PR_VIEW_COMMAND_PATTERN = re.compile(r"\bgh\s+pr\s+view\b[^|;&\n]*", re.IGNORECASE)
PR_VIEW_STATE_FIELDS_PATTERN = re.compile(r"\b(?:state|merged|mergedAt)\b", re.IGNORECASE)
PR_VIEW_JSON_FLAG_PATTERN = re.compile(r"--json\b")
PR_VIEW_REPOSITORY_FLAG_PATTERN = re.compile(r"(?:-R|--repo)[\s=]+([\w.-]+/[\w.-]+)")
REST_PULLS_COMMAND_PATTERN = re.compile(r"\bgh\s+api\b[^|;&\n]*?repos/([\w.-]+/[\w.-]+)/pulls/(\d+)(?![\d/])", re.IGNORECASE)
PULL_REQUEST_NUMBER_PATTERN_TEMPLATE = r"(?<![\w/-])(?:#)?{number}(?![\w-])|/pull/{number}(?!\d)"
MISSING_STATE_READ_REASON = (
    "This message states the status of {pull_requests} (ready, open, mergeable, or needing a merge, an"
    " approval, or queueing), and this turn has no read of that state. A check run, review, or comment"
    " read returns no state or merged field, and a state read from an earlier turn can be hours old."
    " Read it now with pull_request_read method get, gh pr view <number> --json state,mergedAt, or"
    " gh api repos/<owner>/<repo>/pulls/<number>, then write the state that read returned. A merged pull"
    " request is reported as merged."
)
