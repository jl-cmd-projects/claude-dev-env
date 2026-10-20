"""Constants for the reply length gate PreToolUse hook."""

import re

MAXIMUM_SENTENCE_COUNT = 3
MAXIMUM_WORDS_PER_SENTENCE = 15
ALL_CHECKED_TOOL_NAMES = frozenset(
    {"mcp__hearthbot__reply", "mcp__hearthbot__post_message", "mcp__hearthbot__update_message"}
)
DECISION_CARD_TOOL_NAME = "mcp__hearthbot__ask_decision"
CARD_TEXT_SEPARATOR = "\n"
ALL_DECISION_CARD_PROSE_KEYS = ("question", "context")
DECISION_CARD_OPTIONS_KEY = "options"
ALL_DECISION_OPTION_PROSE_KEYS = ("label", "consequence")
DECISION_CARD_CONTEXT_KEY = "context"
MAXIMUM_CARD_CONTEXT_SENTENCE_COUNT = 2
ALL_DECISION_CARD_LENGTH_KEYS = ("question", "context", "reason")
ALL_DECISION_OPTION_LENGTH_KEYS = ("consequence",)
QUESTION_CARD_TOOL_NAME = "AskUserQuestion"
QUESTION_CARD_QUESTIONS_KEY = "questions"
ALL_QUESTION_CARD_PROSE_KEYS = ("question", "header")
ALL_QUESTION_OPTION_PROSE_KEYS = ("label", "description")
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
CARD_CONTEXT_TOO_LONG_MESSAGE = (
    "Card context too long: {sentence_count} sentences, limit {sentence_limit}."
)
CARD_CONTEXT_LIST_MESSAGE = "Card context holds a list of items, and a card cannot format a list."
CARD_LIST_ITEM_PATTERN = re.compile(r"^[ \t]*(?:[-*+]|\d+[.)])[ \t]+\S", re.MULTILINE)
CARD_FORMAT_FLOW_INSTRUCTION = (
    " For a list or several items, publish an Artifact page with a tap button per item"
    " and a Send button, with the capability that republishes its state so the watching"
    " session wakes. Then send a short reply that links the page."
)
UNLINKED_PULL_REQUEST_MESSAGE = 'Pull request "{reference}" has no link. Write it as [PR N](https://github.com/<owner>/<repo>/pull/N).'
MID_SENTENCE_COLON_MESSAGE = (
    "A colon joins two clauses on one line. Write two sentences, or end the line with the colon"
    " and put the list on the lines below."
)
EM_DASH_MESSAGE = "An em dash is in the text. Use a period or a comma."
CAUSAL_CLAIM_PATTERN = re.compile(
    r"(?:^|,)\s*so\b(?!\s+far\b)|\b(?:because|caused|causes|due to|therefore|which means|that means)\b",
    re.IGNORECASE,
)
ALL_EVIDENCE_PATTERNS = (INLINE_CODE_PATTERN, URL_PATTERN, MARKDOWN_LINK_PATTERN)
UNSOURCED_CAUSE_MESSAGE = (
    'Cause with no source: "{sentence}". Quote the log line or output in backticks,'
    " or link the run or file and line that shows it."
)
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
CURLY_APOSTROPHE = "\u2019"
STRAIGHT_APOSTROPHE = "'"
QUANTITY_PATTERN = (
    r"(?:\d+(?:\.\d+)?|an?|one|two|three|four|five|six|seven|eight|nine|ten"
    r"|eleven|twelve|(?:thir|four|fif|six|seven|eigh|nine)teen"
    r"|twenty|thirty|forty(?:-five)?|fifty|sixty|seventy|eighty|ninety"
    r"|(?:an?\s+|one\s+)?hundred|half an?|a couple(?: of)?|a few|several)"
)
DURATION_UNIT_PATTERN = r"(?:hours?|hrs?|minutes?|mins?|seconds?|secs?|days?|weeks?)"
NEGATION_PATTERN = (
    r"(?:(?:did|have|has|could|was|were|is|are)(?:\s+not|n't)|can(?:not|'t)|not\s+yet|never)"
)
FIRST_PERSON_PATTERN = r"(?:i|we)"
CHECK_VERB_PATTERN = r"(?:confirm|verif(?:y|ied)|validate|check|test)(?:ed)?"
CHECKED_PARTICIPLE_PATTERN = r"(?:confirmed|verified|validated|tested|checked(?!\s+(?:in|out)\b))"
PASSIVE_NEGATION_PATTERN = (
    r"(?:(?:has|have)(?:\s+not|n't)(?:\s+yet)?\s+been"
    r"|(?:was|were|is|are)(?:\s+not|n't)(?:\s+yet)?(?:\s+been)?"
    r"|can(?:not|'t)\s+be)"
)
FILLER_WORDS_PATTERN = r"(?:(?!(?:a|an|the|what|which|something|anything)\b)\w+\s+){0,2}"
UNVALIDATED_CLAIM_PATTERN = re.compile(
    r"\b(?:guess(?:es|ed|ing)?|estimat(?:e|es|ed|ing)|eta|ballpark"
    r"|assum(?:e|es|ed|ing)|i think|i expect"
    r"|un(?:confirmed|verified|validated|checked|tested))\b"
    rf"|\b{FIRST_PERSON_PATTERN}\s+{NEGATION_PATTERN}\s+{FILLER_WORDS_PATTERN}{CHECK_VERB_PATTERN}\b"
    rf"|\b{FIRST_PERSON_PATTERN}\s+{NEGATION_PATTERN}\s+{FILLER_WORDS_PATTERN}run\b(?!\s+(?:into|out)\b)"
    rf"|\b{PASSIVE_NEGATION_PATTERN}\s+(?:{CHECKED_PARTICIPLE_PATTERN}|run)\b",
    re.IGNORECASE,
)
DURATION_CLAIM_PATTERN = re.compile(
    rf"\btakes?\s+(?:about\s+)?{QUANTITY_PATTERN}\s+{DURATION_UNIT_PATTERN}\b"
    rf"|\b{QUANTITY_PATTERN}\s+(?:more\s+)?{DURATION_UNIT_PATTERN}\s+(?:left|remaining|to go)\b"
    rf"|\b(?:about|around|approximately|roughly|another)\s+{QUANTITY_PATTERN}\s+{DURATION_UNIT_PATTERN}\b"
    rf"|\b{QUANTITY_PATTERN}\s*(?:to|-|or)\s*{QUANTITY_PATTERN}\s+{DURATION_UNIT_PATTERN}\b",
    re.IGNORECASE,
)
UNVALIDATED_CLAIM_MESSAGE = (
    'No tool validated this: "{claim}". Run the check yourself or through a subagent,'
    " then state what the run, log line, output, or file and line shows, or leave the claim out."
)
CITED_NUMBER_PATTERN = re.compile(
    r"/actions/runs/(\d+)|/pull/(\d+)|\b(?:run|job|check)\s+#?(\d{5,})\b", re.IGNORECASE
)
CITED_NUMBER_IN_RESULT_TEMPLATE = r"(?<!\d){number}(?!\d)"
UNSEEN_CITATION_MESSAGE = (
    'The text cites "{citation}", and no tool result in this session shows it.'
    " Read it yourself or through a subagent first."
)

ADDITIONAL_CONTEXT_KEY = "additionalContext"
ALL_CHECKED_MCP_TOOL_NAMES = frozenset(
    {
        "mcp__github__add_issue_comment",
        "mcp__github__update_issue_comment",
        "mcp__github__add_reply_to_pull_request_comment",
        "mcp__github__add_comment_to_pending_review",
        "mcp__github__pull_request_review_write",
    }
)
BASH_TOOL_NAME = "Bash"
COMMAND_KEY = "command"
GH_COMMENT_COMMAND_PATTERN = re.compile(r"\A\s*(?:\w+=\S+\s+)*gh\s+(?:pr|issue)\s+(?:comment|review)\b")
DETAILS_BLOCK_PATTERN = re.compile(r"<details\b.*?</details>", re.IGNORECASE | re.DOTALL)
COMMENT_RETRY_INSTRUCTION = (
    " A comment on GitHub holds at most three short sentences."
    " Put detail in the pull request body, a code block, or a collapsed <details> block, then post again."
)
