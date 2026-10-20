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
NON_SPACE_TOKEN_PATTERN = re.compile(r"\S+")
ESCAPED_PUNCTUATION_PATTERN = re.compile(r"(?<!\\)(?:\\\\)*\\[!-/:-@\[\]^_`{-~]")
HARD_BREAK_PATTERN = re.compile(r"(?<!\\)(?:\\\\)*\\\Z")
CARRIAGE_RETURN_LINE_BREAK = "\r\n"
LINE_BREAK = "\n"
CODE_SPAN_PATTERN = re.compile(r"(?<![\\`])(`+)(?!`)(?:[^\n]|\n(?![ \t]*\n))*?(?<!`)\1(?!`)")
FENCED_CODE_PATTERN = re.compile(
    r"^ {0,3}(?:(`{3,})[^`\n]*|(~{3,})[^\n]*)\n.*?(?:^ {0,3}(?:\1`*|\2~*)[ \t]*$|\Z)",
    re.MULTILINE | re.DOTALL,
)
WINDOWS_PATH_MESSAGE = (
    'Path "{path}" sits outside a code span. The terminal renders'
    " markdown and drops a backslash before punctuation, so a copied path"
    " points nowhere. Wrap the path in backticks."
)
