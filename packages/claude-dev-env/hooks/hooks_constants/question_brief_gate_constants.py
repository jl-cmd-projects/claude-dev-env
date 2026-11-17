"""Constants for the question brief gate PreToolUse hook.

Groups: the brief limits, the transcript poll, the transcript shapes that
mark the user's own input and the end of a turn, the list line patterns, the
value pattern and the tool input keys it reads, and the refusal
messages.
"""

from __future__ import annotations

import re

MAXIMUM_BRIEF_WORD_COUNT = 450
MAXIMUM_BRIEF_LIST_ITEM_COUNT = 15

TRANSCRIPT_POLL_INTERVAL_SECONDS = 0.05
TRANSCRIPT_POLL_LIMIT_SECONDS = 3.0

QUESTION_TOOL_NAME = "AskUserQuestion"
SUBAGENT_ID_PAYLOAD_KEY = "agent_id"
TOOL_USE_ID_PAYLOAD_KEY = "tool_use_id"
TRANSCRIPT_PATH_PAYLOAD_KEY = "transcript_path"
TOOL_NAME_PAYLOAD_KEY = "tool_name"
TOOL_INPUT_PAYLOAD_KEY = "tool_input"
QUESTIONS_INPUT_KEY = "questions"
OPTIONS_INPUT_KEY = "options"
LABEL_INPUT_KEY = "label"
DESCRIPTION_INPUT_KEY = "description"
MULTI_SELECT_INPUT_KEY = "multiSelect"

MINIMUM_VALUE_OPTION_COUNT = 2
MAY_MONTH_PATTERN_TEXT = "may"
ALL_MONTH_NAME_PATTERN_TEXTS = (
    r"jan(?:uary)?",
    r"feb(?:ruary)?",
    r"mar(?:ch)?",
    r"apr(?:il)?",
    MAY_MONTH_PATTERN_TEXT,
    r"june?",
    r"july?",
    r"aug(?:ust)?",
    r"sep(?:t(?:ember)?)?",
    r"oct(?:ober)?",
    r"nov(?:ember)?",
    r"dec(?:ember)?",
)
MONTH_NAME_PATTERN_TEXT = "(?:" + "|".join(ALL_MONTH_NAME_PATTERN_TEXTS) + ")"
MONTH_NAME_AFTER_DAY_PATTERN_TEXT = (
    "(?:"
    + "|".join(
        each_month
        for each_month in ALL_MONTH_NAME_PATTERN_TEXTS
        if each_month != MAY_MONTH_PATTERN_TEXT
    )
    + ")"
)
DATE_PATTERN = re.compile(
    rf"\b{MONTH_NAME_PATTERN_TEXT}\.?\s+\d{{1,2}}(?:st|nd|rd|th)?\b"
    rf"|\b\d{{1,2}}(?:st|nd|rd|th)?\s+{MONTH_NAME_AFTER_DAY_PATTERN_TEXT}\b"
    r"|\b\d{4}-\d{2}-\d{2}(?!\d)"
    r"|\b(?:1[0-2]|0?[1-9])/(?:0[1-9]|[12]\d|3[01])\b",
    re.IGNORECASE,
)
PERCENT_OR_PRICE_PATTERN = re.compile(r"\d+(?:\.\d+)?\s*(?:%|percent\b)|[$€£]\s?\d", re.IGNORECASE)
DURATION_PATTERN = re.compile(
    r"\b\d+(?:-|\s*)(?:minutes?|mins?|hours?|hrs?|h|days?|weeks?|months?|years?)\b",
    re.IGNORECASE,
)

ENTRY_TYPE_KEY = "type"
USER_ENTRY_TYPE = "user"
ASSISTANT_ENTRY_TYPE = "assistant"
SYSTEM_ENTRY_TYPE = "system"
ATTACHMENT_ENTRY_TYPE = "attachment"
ATTACHMENT_KEY = "attachment"
QUEUED_COMMAND_ATTACHMENT_TYPE = "queued_command"
QUEUED_PROMPT_KEY = "prompt"
MESSAGE_KEY = "message"
SUBTYPE_KEY = "subtype"
STOP_REASON_KEY = "stop_reason"
TURN_END_STOP_REASON = "end_turn"
ALL_TURN_END_SYSTEM_SUBTYPES = frozenset({"stop_hook_summary"})
BLOCK_TYPE_KEY = "type"
TEXT_BLOCK_TYPE = "text"
TEXT_KEY = "text"
TOOL_USE_BLOCK_TYPE = "tool_use"
TOOL_RESULT_BLOCK_TYPE = "tool_result"
BLOCK_ID_KEY = "id"
BLOCK_NAME_KEY = "name"
RESULT_TOOL_USE_ID_KEY = "tool_use_id"
ALL_NOT_TYPED_BY_USER_FLAGS = ("isMeta", "isSidechain", "isCompactSummary")
ALL_MACHINE_PROMPT_PREFIXES = ("<task-notification", "<agent-message", "Stop hook feedback")
ALL_HELD_STOP_PROMPT_PREFIXES = ("Stop hook feedback",)
PROMPT_TEXT_SEPARATOR = " "
BRIEF_TEXT_SEPARATOR = "\n"

LIST_ITEM_LINE_PATTERN = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+\S")
TABLE_ROW_LINE_PATTERN = re.compile(r"^\s*\|.*\|\s*$")
TABLE_SEPARATOR_LINE_PATTERN = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)*\|?\s*$")
CODE_FENCE_LINE_PATTERN = re.compile(r"^\s*(?:```|~~~)")

BLOCK_EXIT_CODE = 2
ALLOW_EXIT_CODE = 0
WORD_LIMIT_PART_TEMPLATE = "{count} words, over the {maximum}-word limit"
LIST_ITEM_LIMIT_PART_TEMPLATE = "{count} list or table items, over the {maximum}-item limit"
REFUSAL_LIMIT_PART_SEPARATOR = ", and "
REFUSAL_MESSAGE_TEMPLATE = (
    "Question refused: the chat text before this question in this turn runs {limit_parts}. "
    "That text has already posted, so do not repeat it. Shorten the brief to the context "
    "and each choice's effect, or split the question: ask about one item now and send each "
    "other item as its own question after the user answers this one."
)
VALUE_MENU_LABEL_SEPARATOR = '", "'
VALUE_MENU_REFUSAL_TEMPLATE = (
    'Question refused: its options ask the user to pick a value ("{labels}"). A percent, '
    "price, date, window, or duration for the work is a research and data output, so it is "
    "yours to settle. Look it up in published research and the user's own records, decide "
    "the value, and name its source. When the data leaves it open, take the default the "
    "research supports or a measured test, and report that call. Ask the user only to "
    "approve the one value you chose, with no other value in the card's other options, for "
    "a preference no data can settle, or for a step that needs their hands or eyes."
)
