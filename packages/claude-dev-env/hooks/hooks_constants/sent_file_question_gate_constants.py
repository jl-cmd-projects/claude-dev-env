"""Constants for the gate that keeps questions for the user out of sent files and pages."""

import re

__all__ = [
    "ALLOW_EXIT_CODE",
    "ALL_QUOTED_QUESTION_ENDINGS",
    "ALL_SKIPPED_PUBLISH_INPUT_KEYS",
    "ANSWER_LABEL_PATTERN",
    "ANSWER_OPENER_PATTERN",
    "ARTIFACT_ACTION_INPUT_KEY",
    "ARTIFACT_CAPABILITIES_INPUT_KEY",
    "ARTIFACT_FILE_PATH_INPUT_KEY",
    "ARTIFACT_PUBLISH_ACTION",
    "ARTIFACT_TOOL_NAME",
    "BLOCK_EXIT_CODE",
    "BOLD_LINE_PATTERN",
    "CWD_KEY",
    "EMPHASIS_PATTERN",
    "GATE_EVENT_NAME",
    "HEADING_MARK",
    "HEADING_LINE_PATTERN",
    "LINE_BREAK",
    "LIST_MARKER_PATTERN",
    "MAXIMUM_CHOICE_WORDS",
    "QUESTION_FOUND_MESSAGE",
    "QUESTION_LABEL_PATTERN",
    "QUESTION_MARK",
    "QUESTION_SECTION_PATTERN",
    "QUOTED_SPAN_PATTERN",
    "READER_ADDRESS_PATTERN",
    "READER_CHOICE_PATTERN",
    "REQUEST_OPENER_PATTERN",
    "SENTENCE_PATTERN",
    "SPACE_RUN_PATTERN",
    "TABLE_CELL_SEPARATOR",
    "TABLE_DIVIDER_CELL_PATTERN",
    "TABLE_ROW_PATTERN",
    "TOOL_INPUT_KEY",
    "TOOL_NAME_KEY",
    "TRAILING_CLOSERS",
    "TRAILING_MARKS",
    "UNIT_START_PATTERN",
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
HEADING_LINE_PATTERN = re.compile(r"^\s{0,3}#{1,6}\s+(?P<text>.*?)\s*#*\s*$")
BOLD_LINE_PATTERN = re.compile(r"^\s*(?P<mark>\*\*|__)(?P<text>[^*_].*?)(?P=mark)\s*:?\s*$")
TABLE_ROW_PATTERN = re.compile(r"^\s*\|")
TABLE_DIVIDER_CELL_PATTERN = re.compile(r"^:?-+:?$")
LIST_MARKER_PATTERN = re.compile(r"^\s*(?:[-*+]|\d{1,3}[.)])\s+")
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
    r"|decisions?\s+(?:needed|required|pending|to\s+make|for\b.*)",
    re.IGNORECASE,
)
READER_ADDRESS_PATTERN = re.compile(r"\b(?:you|your|yours|yourself)\b", re.IGNORECASE)
READER_CHOICE_PATTERN = re.compile(r"\bor\b", re.IGNORECASE)
REQUEST_OPENER_PATTERN = re.compile(
    r"^(?:(?:so|and|also|then|now|ok|okay)\b,?\s+)?"
    r"(?:(?:should|shall|may|can|could)\s+(?:i|we)\b"
    r"|want\s+me\b"
    r"|(?:ok|okay|fine)\s+(?:to|if|with)\b"
    r"|(?:is|would)\s+(?:it|that|this)\s+(?:ok|okay|alright|fine)\b"
    r"|any\s+(?:objections?|preferences?|thoughts)\b"
    r"|(?:go\s+ahead|proceed|continue|merge|ship|approve|archive|delete|keep|drop|revert|rerun|retry)\b)",
    re.IGNORECASE,
)
ANSWER_OPENER_PATTERN = re.compile(r"^(?:yes|no|nope|yep)\b", re.IGNORECASE)
QUESTION_FOUND_MESSAGE = (
    '{file_path} carries a question for the user: "{question}". '
    "A question inside a sent file or page reaches the user with no answer card, "
    "and the user may read only the question cards. "
    "Ask each question through AskUserQuestion (Codex: request_user_input), one question per card, "
    "with its context and each choice's effect in the card. "
    "Remove the questions from the file, keep its facts and context, and send it again. "
    "A page that collects the answer itself, such as option cards, declares a capability "
    "that saves the answer, and this gate lets it through. "
    "When the line asks the user nothing, reword it as a statement."
)
