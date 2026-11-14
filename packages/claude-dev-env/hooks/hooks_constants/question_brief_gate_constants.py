"""Constants for the question brief gate PreToolUse hook.

Groups: the brief limits, the transcript poll, the transcript shapes that
mark the user's own input and the end of a turn, the list line patterns, and
the refusal message.
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
