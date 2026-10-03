"""Constants for the reply length gate PreToolUse hook."""

import re

MAXIMUM_SENTENCE_COUNT = 3
MAXIMUM_WORDS_PER_SENTENCE = 15
ALL_CHECKED_TOOL_NAMES = frozenset({"mcp__hearthbot__reply", "mcp__hearthbot__post_message"})
DECISION_CARD_TOOL_NAME = "mcp__hearthbot__ask_decision"
CARD_TEXT_SEPARATOR = "\n"
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
MARKDOWN_LINK_PATTERN = re.compile(r"\[[^\]\n]*\]\([^)\s]*\)")
UNLINKED_PULL_REQUEST_PATTERN = re.compile(
    r"\b(?:PRs?|pull requests?)\s*#?\d+|(?<![\w/&])#\d+", re.IGNORECASE
)
LINE_BREAK_PATTERN = re.compile(r"\n+")
SENTENCE_END_PATTERN = re.compile(r"(?<=[.!?])\s+")
WORD_PATTERN = re.compile(r"[A-Za-z0-9]+(?:['.,-][A-Za-z0-9]+)*")
SENTENCE_PREVIEW_WORD_COUNT = 6
WORD_SEPARATOR = " "
SENTENCE_PREVIEW_SUFFIX = "..."
RETRY_INSTRUCTION = " Cut the text and resend the call."
TOO_MANY_SENTENCES_MESSAGE = "Reply too long: {sentence_count} sentences, limit {sentence_limit}."
UNLINKED_PULL_REQUEST_MESSAGE = 'Pull request "{reference}" has no link. Write it as [PR N](https://github.com/<owner>/<repo>/pull/N).'
LONG_SENTENCE_MESSAGE = (
    'Sentence too long: {word_count} words, limit {word_limit}: "{sentence_preview}".'
)
HEDGE_MESSAGE = 'Unchecked claim: "{hedge}" in "{sentence_preview}". Check it and state the evidence, or leave the claim out.'
