"""Constants for session_title_format_gate.py and session_title_stop_gate.py."""

import re

TITLE_TOOL_NAME_PATTERN = re.compile(r"^mcp__.+__set_session_title$")
REMOTE_SESSION_ENVIRONMENT_VARIABLE = "CLAUDE_CODE_REMOTE_SESSION_ID"
TITLE_INPUT_KEY = "title"
TOOL_NAME_KEY = "tool_name"
TOOL_INPUT_KEY = "tool_input"
TRANSCRIPT_PATH_KEY = "transcript_path"
STOP_HOOK_ACTIVE_KEY = "stop_hook_active"
FORMAT_GATE_EVENT_NAME = "PreToolUse"
STOP_GATE_EVENT_NAME = "Stop"
ALLOW_EXIT_CODE = 0
BLOCK_EXIT_CODE = 2
BLOCK_DECISION = "block"
DEFERRED_TOOL_ATTACHMENT_TYPES = frozenset({"deferred_tools_delta", "deferred_tools_record"})
HOOK_BLOCKING_ERROR_ATTACHMENT_TYPE = "hook_blocking_error"

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

STOP_BLOCK_REASON = (
    "Before you end this turn, set the session title to its current status."
    " Call the session title tool ({tool_name}); when it asks for a session id,"
    " get it from get_session with no session_id."
    " Use the shape '<emoji> <name>'."
    " Emoji: \U0001f6a9 when the user must act (a question, an approval, or a step only the user can do);"
    " \u2705 when the work is done (merged, or nothing left);"
    " \u23f3 while work, CI or a merge queue still runs and nothing waits on the user."
    " Name: 25 characters or fewer, the main change or outcome in concrete nouns,"
    " two parts joined with ' + ', sentence case, no end punctuation,"
    " no dates, IDs, branch names or filler words."
    " Rename it when the scope of the work has changed."
    " The title is a silent step: make the call and end the turn."
    " Say nothing to the user about the title, its emoji or this reminder."
    " When the user already has your answer this turn, end with no text."
    " Next time, set the title before your final reply."
)
REMOTE_TITLE_TOOL_NAME = "mcp__claude-code-remote__set_session_title"
REMOTE_SERVER_TOOL_PREFIX = "mcp__claude-code-remote__"
UNKNOWN_TITLE_TOOL_NAME = "its name ends in __set_session_title"
