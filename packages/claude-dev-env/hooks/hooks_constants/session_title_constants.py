"""Constants for session_title_format_gate.py."""

import re

TITLE_TOOL_NAME_PATTERN = re.compile(r"^mcp__.+__set_session_title$")
TITLE_INPUT_KEY = "title"
TOOL_NAME_KEY = "tool_name"
TOOL_INPUT_KEY = "tool_input"
FORMAT_GATE_EVENT_NAME = "PreToolUse"
ALLOW_EXIT_CODE = 0
BLOCK_EXIT_CODE = 2

STATUS_PREFIX_PATTERN = re.compile("^(\U0001f6a9|\u2705|\u23f3)\ufe0f? (?=\\S)")
MAXIMUM_NAME_LENGTH = 25
TRAILING_PUNCTUATION = ".!?,;:"
IDENTIFIER_DIGITS_PATTERN = re.compile(r"\d{3,}")

STATUS_PREFIX_MESSAGE = (
    "The title must start with one status emoji and one space:"
    " \U0001f6a9 when the user must act, \u2705 when the work is done,"
    " \u23f3 while work runs and nothing waits on the user."
)
SINGLE_LINE_MESSAGE = "The title must be one line."
NAME_LENGTH_MESSAGE = "The name after the emoji must be 1 to {maximum} characters; it has {length}."
TRAILING_PUNCTUATION_MESSAGE = "The title must end without punctuation."
SENTENCE_CASE_MESSAGE = "The name must start with a capital letter (sentence case)."
IDENTIFIER_MESSAGE = "The name must hold no dates, IDs or numbers of three or more digits."
BRANCH_NAME_MESSAGE = "The name must hold no branch names or paths (no '/')."
FORMAT_RETRY_INSTRUCTION = (
    " Call the title tool again with '<emoji> <name>', where the name names"
    " the main change or outcome in concrete nouns, such as"
    " '\u23f3 Broker gate + replay rule'."
)
