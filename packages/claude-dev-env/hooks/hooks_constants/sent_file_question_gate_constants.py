"""Constants for the gate that keeps questions for the user out of sent files and pages."""

import re

__all__ = [
    "ALLOW_EXIT_CODE",
    "ALL_ANSWER_SAVING_CAPABILITIES",
    "ALL_BOLD_MARKS",
    "ALL_FULL_WIDTH_QUESTION_MARKS",
    "ALL_INDENTED_CODE_PREFIXES",
    "ALL_QUOTED_QUESTION_ENDINGS",
    "ALL_SKIPPED_PUBLISH_INPUT_KEYS",
    "ANSWER_LABEL_PATTERN",
    "ANSWER_OPENER_PATTERN",
    "ARTIFACT_ACTION_INPUT_KEY",
    "ARTIFACT_CAPABILITIES_INPUT_KEY",
    "ARTIFACT_FILE_PATH_INPUT_KEY",
    "ARTIFACT_PUBLISH_ACTION",
    "ARTIFACT_TOOL_NAME",
    "BINARY_READ_MODE",
    "BLOCK_EXIT_CODE",
    "BOLD_MARK_COUNT",
    "CWD_KEY",
    "EMPHASIS_CHARACTERS",
    "EMPHASIS_PATTERN",
    "FILE_PARTS_SEPARATOR",
    "FILE_PART_BYTES",
    "FILE_PATH_SEPARATOR",
    "GATE_EVENT_NAME",
    "HEADING_CLOSE_MARKS",
    "HEADING_MARK",
    "HEADING_OPENER_PATTERN",
    "LABEL_COLON",
    "LINE_BREAK",
    "LIST_MARKER_PATTERN",
    "MAXIMUM_CHOICE_WORDS",
    "MAXIMUM_QUOTED_CHARACTERS",
    "MAXIMUM_UTF8_CONTINUATION_BYTES",
    "MAXIMUM_WHOLE_FILE_BYTES",
    "NUL_BYTE",
    "OPEN_ASK_PATTERN",
    "PARTIAL_READ_MESSAGE",
    "PARTIAL_READ_NOTE",
    "QUESTION_FOUND_MESSAGE",
    "QUESTION_LABEL_PATTERN",
    "QUESTION_MARK",
    "QUESTION_SECTION_PATTERN",
    "QUOTED_SPAN_PATTERN",
    "QUOTE_CUT_MARK",
    "READER_ADDRESS_PATTERN",
    "READER_CHOICE_PATTERN",
    "READER_WISH_PATTERN",
    "REQUEST_OPENER_PATTERN",
    "RESPONSE_PROMPT_PATTERN",
    "SCAN_BUDGET_SECONDS",
    "SCAN_TIMEOUT_MESSAGE",
    "SENTENCE_PATTERN",
    "SPACE_RUN_PATTERN",
    "SYSTEM_MESSAGE_KEY",
    "TABLE_CELL_SEPARATOR",
    "TABLE_DIVIDER_CELL_PATTERN",
    "TABLE_ROW_PATTERN",
    "TASK_BOX_PATTERN",
    "TOOL_INPUT_KEY",
    "TOOL_NAME_KEY",
    "TRAILING_CLOSERS",
    "TRAILING_MARKS",
    "UNIT_START_PATTERN",
    "UTF8_CONTINUATION_BYTES",
    "UTF8_ENCODING",
    "WH_CHOICE_PATTERN",
]

ALLOW_EXIT_CODE = 0
BLOCK_EXIT_CODE = 2
GATE_EVENT_NAME = "PreToolUse"
TOOL_NAME_KEY = "tool_name"
TOOL_INPUT_KEY = "tool_input"
CWD_KEY = "cwd"
ARTIFACT_TOOL_NAME = "Artifact"
ARTIFACT_ACTION_INPUT_KEY = "action"
ARTIFACT_PUBLISH_ACTION = "publish"
ARTIFACT_FILE_PATH_INPUT_KEY = "file_path"
ARTIFACT_CAPABILITIES_INPUT_KEY = "capabilities"
ALL_SKIPPED_PUBLISH_INPUT_KEYS = ("asset", "type_url")
LINE_BREAK = "\n"
HEADING_MARK = "# "
QUESTION_MARK = "?"
TRAILING_MARKS = "*_\"'’”)] \t"
TABLE_CELL_SEPARATOR = "|"
TRAILING_CLOSERS = "*_)] \t"
ALL_QUOTED_QUESTION_ENDINGS = ('?"', "?'", "?’", "?”")
MAXIMUM_CHOICE_WORDS = 10
QUOTED_SPAN_PATTERN = re.compile(r'"[^"\n]{1,400}"|“[^”\n]{1,400}”')
HEADING_OPENER_PATTERN = re.compile(r"#{1,6}(?:[ \t]|$)")
HEADING_CLOSE_MARKS = "#"
ALL_BOLD_MARKS = ("**", "__")
EMPHASIS_CHARACTERS = "*_"
LABEL_COLON = ":"
ALL_INDENTED_CODE_PREFIXES = ("    ", "\t")
ALL_FULL_WIDTH_QUESTION_MARKS = ("\uff1f", "\ufe56")
ALL_ANSWER_SAVING_CAPABILITIES = frozenset({"artifact", "self", "db"})
FILE_PART_BYTES = 131072
MAXIMUM_WHOLE_FILE_BYTES = 262144
BOLD_MARK_COUNT = 2
BINARY_READ_MODE = "rb"
NUL_BYTE = b"\x00"
UTF8_ENCODING = "utf-8"
UTF8_CONTINUATION_BYTES = range(0x80, 0xC0)
MAXIMUM_UTF8_CONTINUATION_BYTES = 3
FILE_PARTS_SEPARATOR = "\n\n"
MAXIMUM_QUOTED_CHARACTERS = 160
QUOTE_CUT_MARK = "..."
TABLE_ROW_PATTERN = re.compile(r"^\s*\|")
TABLE_DIVIDER_CELL_PATTERN = re.compile(r"^:?-+:?$")
LIST_MARKER_PATTERN = re.compile(r"^\s*(?:[-*+]|\d{1,3}[.)])\s+(?:\[[ xX]\]\s+)?")
QUESTION_LABEL_PATTERN = re.compile(r"^(?:q|question)\s*\d*\s*[:.]\s+", re.IGNORECASE)
ANSWER_LABEL_PATTERN = re.compile(r"^(?:a|answer)\s*\d*\s*[:.]\s+", re.IGNORECASE)
UNIT_START_PATTERN = re.compile(
    r"^\s{0,3}#{1,6}\s|^\s*(?:\*\*|__)|^\s*\||^\s*(?:[-*+]|\d{1,3}[.)])\s+|^(?:q|question|a|answer)\s*\d*\s*[:.]\s+",
    re.IGNORECASE,
)
EMPHASIS_PATTERN = re.compile(r"(?<!\w)[*_]{1,3}|[*_]{1,3}(?!\w)")
SPACE_RUN_PATTERN = re.compile(r"\s+")
SENTENCE_PATTERN = re.compile(r"\S.*?(?:[.!?][\"'’”)\]*_]*(?=\s|$)|$)")
QUESTION_SECTION_PATTERN = re.compile(
    r"(?:open|pending|outstanding|unresolved|remaining|unanswered)\s+questions?(?:\s+.*)?"
    r"|questions?\s+(?:for|to|from)\b.*"
    r"|(?:open|pending|outstanding|unresolved|remaining)\s+decisions?(?:\s+.*)?"
    r"|decisions?\s+(?:needed|required|pending|to\s+make|for)\b.*"
    r"|(?:need|needs|needed)\s+(?:your|you\s+to)\b.*",
    re.IGNORECASE,
)
READER_ADDRESS_PATTERN = re.compile(r"\b(?:you|your|yours|yourself)\b", re.IGNORECASE)
READER_WISH_PATTERN = re.compile(
    r"\b(?:me|want|wants|prefer|like|approve|agree|think|mind|rather|ok|okay|happy|decide|choose|pick)\b",
    re.IGNORECASE,
)
READER_CHOICE_PATTERN = re.compile(r"\bor\b", re.IGNORECASE)
REQUEST_OPENER_PATTERN = re.compile(
    r"^(?:(?:so|and|also|then|now|ok|okay)\b,?\s+)?"
    r"(?:(?:should|shall)\s+(?:i|we)\b"
    r"|want\s+me\b"
    r"|(?:ok|okay|fine)\s+(?:to|if|with)\b"
    r"|(?:is|would)\s+(?:it|that|this)\s+(?:ok|okay|alright|fine)\b"
    r"|(?:any\s+)?(?:objections?|preferences?|thoughts)\b"
    r"|are\s+we\s+(?:good|ready|clear|ok|okay)\b"
    r"|would\s+it\s+(?:make\s+sense|help|be\s+better)\b"
    r"|(?:go\s+ahead|proceed|continue|merge|ship|approve|archive|delete|keep|drop|revert|rerun|retry)\b)",
    re.IGNORECASE,
)
ANSWER_OPENER_PATTERN = re.compile(r"^(?:yes|no|nope|yep)(?:[.,;:!]|$)", re.IGNORECASE)
WH_CHOICE_PATTERN = re.compile(
    r"^(?:which|what|when|who)\b.*?\b(?:works?\s+(?:best|better)|best|better|preferred|should\s+(?:i|we))\b",
    re.IGNORECASE,
)
TASK_BOX_PATTERN = re.compile(r"^\s*(?:[-*+]|\d{1,3}[.)])\s+\[[ xX]\]\s")
SCAN_BUDGET_SECONDS = 6
SYSTEM_MESSAGE_KEY = "systemMessage"
FILE_PATH_SEPARATOR = ", "
SCAN_TIMEOUT_MESSAGE = (
    "sent_file_question_gate could not finish reading {file_paths} within {budget_seconds} s, "
    "so it did not check them for questions for the user. "
    "Ask any question through AskUserQuestion (Codex: request_user_input), not inside the file."
)
PARTIAL_READ_NOTE = (
    " The gate read only the first and last 128 KB of {file_path}, which is over 256 KB."
)
PARTIAL_READ_MESSAGE = (
    "sent_file_question_gate read only the first and last 128 KB of {file_paths}, "
    "which is over 256 KB, and found no question for the user there. "
    "The middle of the file was not checked."
)
OPEN_ASK_PATTERN = re.compile(r"^(?:can|could|may)\s+(?:i|we)\b", re.IGNORECASE)
RESPONSE_PROMPT_PATTERN = re.compile(
    r"^(?:please\s+)?(?:reply|answer|respond|confirm|choose|pick|select|say|type|tell\s+me|let\s+me\s+know)\b",
    re.IGNORECASE,
)
QUESTION_FOUND_MESSAGE = (
    '{file_path} carries a question for the user: "{question}". '
    "A question inside a sent file or page reaches the user with no answer card, "
    "and the user may read only the question cards. "
    "Ask each question through AskUserQuestion (Codex: request_user_input), one question per card, "
    "with its context and each choice's effect in the card. "
    "Remove the questions from the file, keep its facts and context, and send it again. "
    "A page that collects the answer itself, such as option cards, declares the db or artifact "
    "capability that saves the answer, and this gate lets it through. "
    "When the line asks the user nothing, reword it as a statement."
)
