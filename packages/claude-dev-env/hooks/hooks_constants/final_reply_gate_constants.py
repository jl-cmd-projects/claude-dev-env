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
BACKTICK_RUN_PATTERN = re.compile(r"`+")
BLOCK_BOUNDARY_PATTERN = re.compile(r"\n[ \t]*\n|\n(?=[ \t]*(?:(?:[-*+]|\d+[.)])[ \t]|>))")
HEADING_LINE_PATTERN = re.compile(r"^([ \t]*#{1,6}(?:[ \t][^\n]*)?)$", re.MULTILINE)
HEADING_AS_OWN_BLOCK = "\n\n\\1\n\n"
PARAGRAPH_SEPARATOR = "\n\n"
BACKSLASH = "\\"
BACKSLASHES_PER_LITERAL = 2
MASKED_CODE_TEXT = " "
FENCED_CODE_PATTERN = re.compile(
    r"^ {0,3}(?:(`{3,})[^`\n]*|(~{3,})[^\n]*)\n.*?(?:^ {0,3}(?:\1`*|\2~*)[ \t]*$|\Z)",
    re.MULTILINE | re.DOTALL,
)
WINDOWS_PATH_MESSAGE = (
    'Path "{path}" sits outside a code span. The terminal renders'
    " markdown and drops a backslash before punctuation, so a copied path"
    " points nowhere. Wrap the path in backticks."
)
