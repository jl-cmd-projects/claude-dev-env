"""Constants for session_title_format_gate.py and session_title_turn_gate.py."""

import re

TITLE_TOOL_NAME_PATTERN = re.compile(r"^mcp__.+__set_session_title$")
TITLE_INPUT_KEY = "title"
TOOL_NAME_KEY = "tool_name"
TOOL_INPUT_KEY = "tool_input"
FORMAT_GATE_EVENT_NAME = "PreToolUse"
ALLOW_EXIT_CODE = 0
BLOCK_EXIT_CODE = 2

STATUS_PREFIX_PATTERN = re.compile("^(\U0001f6a9|\U0001f6a7|\u2705|\u23f3)\ufe0f? (?=\\S)")
MAXIMUM_NAME_LENGTH = 25
TRAILING_PUNCTUATION = ".!?,;:"
IDENTIFIER_DIGITS_PATTERN = re.compile(r"\d{3,}")

STATUS_PREFIX_MESSAGE = (
    "The title must start with one status emoji and one space:"
    " \U0001f6a9 when the user must act, \U0001f6a7 when an outside dependency"
    " blocks the work, \u2705 when the work is done,"
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

TURN_GATE_EVENT_NAME = "Stop"
TRANSCRIPT_PATH_KEY = "transcript_path"
STOP_HOOK_ACTIVE_KEY = "stop_hook_active"
DECISION_KEY = "decision"
REASON_KEY = "reason"
BLOCK_DECISION = "block"
UTF8_ENCODING = "utf-8"
DECODE_ERRORS_POLICY = "replace"
ENTRY_TYPE_KEY = "type"
USER_ENTRY_TYPE = "user"
ASSISTANT_ENTRY_TYPE = "assistant"
ATTACHMENT_KEY = "attachment"
MESSAGE_KEY = "message"
CONTENT_KEY = "content"
TOOL_USE_BLOCK_TYPE = "tool_use"
TOOL_RESULT_BLOCK_TYPE = "tool_result"
BLOCK_ID_KEY = "id"
BLOCK_NAME_KEY = "name"
TOOL_USE_ID_KEY = "tool_use_id"
IS_ERROR_KEY = "is_error"
SIDECHAIN_FLAG_KEY = "isSidechain"
ALL_SKIPPED_PROMPT_FLAGS = ("isMeta", SIDECHAIN_FLAG_KEY, "isCompactSummary")
ALL_TOOL_LISTING_NAME_KEYS = ("addedNames", "readdedNames")
ALL_TOOL_LISTING_RECORD_KEYS = ("tools", "entries")
REMOVED_NAMES_KEY = "removedNames"
TITLE_TOOL_DISPLAY_SEPARATOR = " or "

TURN_BLOCK_REASON = (
    "This turn set no session title. Call {tool_name} now with '<emoji> <name>':"
    " \U0001f6a9 the user must act, \U0001f6a7 an outside dependency blocks the work,"
    " \u2705 the work is done, \u23f3 work runs and nothing waits on the user."
    " When it asks for a session id, get it from get_session with no session_id."
    " After the call, end the turn with one short closing sentence."
    " Leave the earlier reply as it stands and do not repeat it."
)
