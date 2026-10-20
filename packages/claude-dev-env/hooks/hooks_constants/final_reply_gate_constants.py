"""Constants for the final reply gate Stop hook."""

import re

HOOK_EVENT_NAME = "Stop"
LAST_ASSISTANT_MESSAGE_KEY = "last_assistant_message"
TRANSCRIPT_PATH_KEY = "transcript_path"
DECISION_KEY = "decision"
BLOCK_DECISION = "block"
REASON_KEY = "reason"
ALLOW_EXIT_CODE = 0
REWRITE_INSTRUCTION = " Rewrite the reply without it."
ESCAPED_PATH_TOKEN_PATTERN = re.compile(r"\S*?(?<!\\)\\[!-/:-@\[\]^_`{-~](?=\w)\S*")
CODE_SPAN_PATTERN = re.compile(r"(?<![\\`])(`+)(?!`)[^\n]*?(?<!`)\1(?!`)")
FENCED_CODE_PATTERN = re.compile(
    r"^ {0,3}(`{3,}|~{3,})[^\n]*\n.*?(?:^ {0,3}\1[^\n]*$|\Z)", re.MULTILINE | re.DOTALL
)
WINDOWS_PATH_MESSAGE = (
    'Path "{path}" sits outside a code span. The terminal renders'
    " markdown and drops a backslash before punctuation, so a copied path"
    " points nowhere. Wrap the path in backticks."
)
