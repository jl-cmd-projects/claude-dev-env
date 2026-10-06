"""Constants for the issue close handoff gate PreToolUse hook."""

import re

ALL_ISSUE_TOOL_SUFFIXES: tuple[str, ...] = (
    "add_issue_comment",
    "issue_write",
    "update_issue_comment",
)
TOOL_NAME_KEY = "tool_name"
TOOL_INPUT_KEY = "tool_input"
STATE_KEY = "state"
CLOSED_STATE = "closed"
HOOK_EVENT_NAME = "PreToolUse"
ALLOW_EXIT_CODE = 0
BLOCK_EXIT_CODE = 2
BODY_TEXT_SEPARATOR = "\n"
ISSUE_REFERENCE = r"(?:#|\bissue\s+)\d+"
CLOSE_DECLARATION_PATTERN = re.compile(
    r"\b(?:clos(?:e|es|ed|ing)\s+(?:this|the|it|on|now|issue)\b"
    r"|issue\s+(?:is\s+)?closed\b)",
    re.IGNORECASE,
)
ALL_HANDOFF_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(rf"\bbelongs?\s+(?:to|in|with|under)\s+{ISSUE_REFERENCE}", re.IGNORECASE),
    re.compile(
        rf"\b(?:rout(?:e|es|ed|ing)|hand(?:s|ed|ing)?\s+off|mov(?:e|es|ed|ing)"
        rf"|defer(?:s|red|ring)?|punt(?:s|ed|ing)?)\b[^.\n]{{0,80}}?\bto\s+{ISSUE_REFERENCE}",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\b(?:tracked|handled|owned|covered|continues)\s+(?:in|by|under)\s+{ISSUE_REFERENCE}",
        re.IGNORECASE,
    ),
    re.compile(r"\bseparate\s+finding\b", re.IGNORECASE),
)
HANDOFF_CLOSE_MESSAGE = (
    "This close hands a defect found in the issue's subject to another issue."
    " The session that found the defect owns it through the fix pull request."
    " Keep this issue open, fix the defect, and close the issue through that"
    " pull request."
)
RETRY_INSTRUCTION = (
    " When the other issue owned the work before this issue found it, link it"
    " as related in a post that does not close this issue."
)
