"""Constants for the reply length gate PreToolUse hook."""

import re

MAXIMUM_SENTENCE_COUNT = 3
MAXIMUM_WORDS_PER_SENTENCE = 15
ALL_CHECKED_TOOL_NAMES = frozenset({"mcp__hearthbot__reply", "mcp__hearthbot__post_message"})
DECISION_CARD_TOOL_NAME = "mcp__hearthbot__ask_decision"
CARD_TEXT_SEPARATOR = "\n"
ALL_DECISION_CARD_PROSE_KEYS = ("question", "context")
DECISION_CARD_OPTIONS_KEY = "options"
ALL_DECISION_OPTION_PROSE_KEYS = ("label", "consequence")
TOOL_NAME_KEY = "tool_name"
TOOL_INPUT_KEY = "tool_input"
TEXT_KEY = "text"
TRANSCRIPT_PATH_KEY = "transcript_path"
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
MID_SENTENCE_COLON_PATTERN = re.compile(r":[ \t]+\S")
EM_DASH_PATTERN = re.compile("\u2014")
LINE_BREAK_PATTERN = re.compile(r"\n+")
SENTENCE_END_PATTERN = re.compile(r"(?<=[.!?])\s+")
WORD_PATTERN = re.compile(r"[A-Za-z0-9]+(?:['.,-][A-Za-z0-9]+)*")
SENTENCE_PREVIEW_WORD_COUNT = 6
WORD_SEPARATOR = " "
SENTENCE_PREVIEW_SUFFIX = "..."
RETRY_INSTRUCTION = " Cut the text and resend the call."
TOO_MANY_SENTENCES_MESSAGE = "Reply too long: {sentence_count} sentences, limit {sentence_limit}."
UNLINKED_PULL_REQUEST_MESSAGE = 'Pull request "{reference}" has no link. Write it as [PR N](https://github.com/<owner>/<repo>/pull/N).'
MID_SENTENCE_COLON_MESSAGE = (
    "A colon joins two clauses on one line. Write two sentences, or end the line with the colon"
    " and put the list on the lines below."
)
EM_DASH_MESSAGE = "An em dash is in the text. Use a period or a comma."
ALL_DEFAULT_BANNED_WORDS = (
    "real",
    "really",
    "in reality",
    "genuine",
    "genuinely",
    "actual",
    "actually",
    "likely",
    "unlikely",
    "probably",
    "seems",
    "seem",
    "seemingly",
    "suspect",
    "guess",
    "my theory",
    "maybe",
    "perhaps",
    "presumably",
    "might be",
    "may be",
    "appears to",
    "i believe",
    "not sure",
    "unsure",
)
BANNED_WORD_PART_SEPARATOR = r"\s+"
BANNED_WORD_PATTERN_TEMPLATE = r"(?<![A-Za-z0-9]){word_pattern}(?![A-Za-z0-9])"
BANNED_WORDS_JSON_KEY = "banned_words"
BANNED_WORDS_FILE_NAME = "reply-banned-words.json"
BANNED_WORDS_PATH_ENV_VAR = "CLAUDE_REPLY_BANNED_WORDS_PATH"
CLAUDE_HOME_DIRECTORY_NAME = ".claude"
CONFIG_FILE_ENCODING = "utf-8"
BANNED_WORD_MESSAGE = 'Banned word "{banned_word}". Delete it and name the evidence: the log line, the check, the file and line.'
LONG_SENTENCE_MESSAGE = (
    'Sentence too long: {word_count} words, limit {word_limit}: "{sentence_preview}".'
)
