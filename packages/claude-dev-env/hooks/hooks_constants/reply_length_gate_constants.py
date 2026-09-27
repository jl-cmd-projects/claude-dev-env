"""Constants for the reply length gate PreToolUse hook."""

import re

MAXIMUM_SENTENCE_COUNT = 3
MAXIMUM_WORDS_PER_SENTENCE = 15
ALL_CHECKED_TOOL_NAMES = frozenset({"mcp__hearthbot__reply", "mcp__hearthbot__post_message"})
TOOL_NAME_KEY = "tool_name"
TOOL_INPUT_KEY = "tool_input"
TEXT_KEY = "text"
HOOK_EVENT_NAME = "PreToolUse"
ALLOW_EXIT_CODE = 0
BLOCK_EXIT_CODE = 2
FENCED_BLOCK_PATTERN = re.compile(r"```.*?(?:```|\Z)", re.DOTALL)
INLINE_CODE_PATTERN = re.compile(r"`[^`\n]*`")
LINK_TARGET_PATTERN = re.compile(r"\]\([^)\s]*\)")
URL_PATTERN = re.compile(r"(?:https?://|www\.)\S+")
LINE_BREAK_PATTERN = re.compile(r"\n+")
SENTENCE_END_PATTERN = re.compile(r"(?<=[.!?])\s+")
WORD_PATTERN = re.compile(r"[A-Za-z0-9]+(?:['.,-][A-Za-z0-9]+)*")
SENTENCE_PREVIEW_WORD_COUNT = 6
WORD_SEPARATOR = " "
SENTENCE_PREVIEW_SUFFIX = "..."
RETRY_INSTRUCTION = " Cut the text and resend the call."
TOO_MANY_SENTENCES_MESSAGE = "Reply too long: {sentence_count} sentences, limit {sentence_limit}."
LONG_SENTENCE_MESSAGE = (
    'Sentence too long: {word_count} words, limit {word_limit}: "{sentence_preview}".'
)
