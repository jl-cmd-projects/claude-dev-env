"""Names, limits, and texts for the compaction user-message recall hook.

Groups: the Claude Code and Codex transcript entry shapes the extractor reads,
the trim rules that condense each message, the bounds of the recall text, the
SessionStart context that carries it, and the offline eval of the trim.
"""

from __future__ import annotations

import re
from pathlib import Path

ENTRY_TYPE_KEY = "type"
USER_ENTRY_TYPE = "user"
ATTACHMENT_ENTRY_TYPE = "attachment"
ASSISTANT_ENTRY_TYPE = "assistant"
ATTACHMENT_KEY = "attachment"
QUEUED_COMMAND_ATTACHMENT_TYPE = "queued_command"
QUEUED_PROMPT_KEY = "prompt"
MESSAGE_KEY = "message"
CONTENT_KEY = "content"
TIMESTAMP_KEY = "timestamp"
ORIGIN_KEY = "origin"
ORIGIN_KIND_KEY = "kind"
HUMAN_ORIGIN_KIND = "human"
ALL_SKIPPED_ENTRY_FLAGS = ("isMeta", "isCompactSummary", "isSidechain")
BLOCK_TYPE_KEY = "type"
TEXT_BLOCK_TYPE = "text"
TEXT_KEY = "text"
IMAGE_BLOCK_TYPE = "image"
IMAGE_PLACEHOLDER = "[image]"
BLOCK_SEPARATOR = " "
HARNESS_TAG_OPENING_PATTERN = re.compile(r"<[a-z]+(?:-[a-z]+)+[\s>]")
SLASH_COMMAND_NAME_PATTERN = re.compile(r"<command-name>\s*(.*?)\s*</command-name>", re.DOTALL)
SLASH_COMMAND_ARGS_PATTERN = re.compile(r"<command-args>(.*?)</command-args>", re.DOTALL)

CODEX_EVENT_ENTRY_TYPE = "event_msg"
CODEX_PAYLOAD_KEY = "payload"
CODEX_USER_MESSAGE_TYPE = "user_message"
CODEX_AGENT_MESSAGE_TYPE = "agent_message"
CODEX_IMAGES_KEY = "images"

ALL_ACKNOWLEDGMENT_WORDS = frozenset(
    {
        "ok",
        "okay",
        "k",
        "yes",
        "yep",
        "yeah",
        "sure",
        "go",
        "ahead",
        "keep",
        "going",
        "continue",
        "great",
        "cool",
        "nice",
        "perfect",
        "thanks",
        "thank",
        "you",
        "thx",
        "ty",
        "makes",
        "sense",
        "sounds",
        "good",
        "lgtm",
        "got",
        "it",
        "done",
        "proceed",
        "on",
    }
)
MAXIMUM_ACKNOWLEDGMENT_WORDS = 4
ACKNOWLEDGMENT_WORD_PATTERN = re.compile(r"[a-z']+")
INTERRUPT_PATTERN = re.compile(r"^\[request interrupted by user[^\]]*\]$", re.IGNORECASE)
PATH_CHARACTERS = r"\w/.:`-"
PATH_FOLLOWING_CHARACTERS = r"\w/:`-"
ALL_FILLER_PHRASES = (
    "so basically",
    "basically",
    "just to be clear",
    "honestly",
    "I would like it if",
    "could you please make sure that",
    "could you please",
    "can you please",
    "could you",
    "can you",
    "please",
    "when you get a chance",
    "kind of",
    "sort of",
    "I mean",
)
FILLER_PATTERN = re.compile(
    rf"(?<![{PATH_CHARACTERS}])(?:"
    + "|".join(re.escape(each_phrase) for each_phrase in ALL_FILLER_PHRASES)
    + rf")(?![{PATH_FOLLOWING_CHARACTERS}]|\.\w),?",
    re.IGNORECASE,
)
ARTICLE_PATTERN = re.compile(
    rf"(?<![{PATH_CHARACTERS}])(?:[Tt]he|THE|a|[Aa]n|AN)\s+(?=\w)"
)
ARTIFACT_COMMENT_MARKER = "[Artifact comment sent to Claude]"
ARTIFACT_URL_PATTERN = re.compile(r"^Artifact: (\S+)", re.MULTILINE)
ARTIFACT_LOCATION_PATTERN = re.compile(r"^Location: (.+)$", re.MULTILINE)
ARTIFACT_QUOTE_PATTERN = re.compile(
    r"=== BEGIN ARTIFACT COMMENT (?P<marker>\w+) ===\n(?P<comment>.*?)\n"
    r"=== END ARTIFACT COMMENT (?P=marker) ===",
    re.DOTALL,
)
QUOTE_PREFIX_PATTERN = re.compile(r"^> ?", re.MULTILINE)
ARTIFACT_COMMENT_TEMPLATE = "Artifact comment on {url}{location}: {comment}"
ARTIFACT_LOCATION_TEMPLATE = " at {location}"
ARTIFACT_QUOTE_GROUP = "comment"
HTML_COMMENT_PATTERN = re.compile(r"<!--.*?-->", re.DOTALL)
CODE_SPAN_PATTERN = re.compile(r"(`[^`]*`)")
WHITESPACE_RUN_PATTERN = re.compile(r"\s+")
SPACE_BEFORE_PUNCTUATION_PATTERN = re.compile(r"\s+([,.;:])(?=\s|$)")
DANGLING_COMMA_PATTERN = re.compile(r",\s*(?=[,.;:](?:\s|$))")
TRIMMED_EDGE_CHARACTERS = " ,"
REVERSAL_PATTERN = re.compile(
    r"change of plan|change that|on second thought|scratch (?:that|the)|"
    r"(?<!n't )(?<!nt )forget\b|after all|"
    r"instead|\bswitch(?:ed)? to\b|vetoed|no longer|not anymore|\boverride\b|\brevert\b|\bundo\b|"
    r"don'?t (?:use|do)|stop using",
    re.IGNORECASE,
)
CONTENT_WORD_PATTERN = re.compile(r"[A-Za-z][\w./:-]+")
CONTENT_WORD_EDGE_PUNCTUATION = ".,:;"
ALL_STOP_WORDS = frozenset(
    {
        "to",
        "it",
        "is",
        "we",
        "of",
        "on",
        "in",
        "be",
        "so",
        "do",
        "no",
        "as",
        "at",
        "by",
        "or",
        "us",
        "me",
        "if",
        "an",
        "the",
        "and",
        "for",
        "use",
        "not",
        "with",
        "this",
        "that",
        "its",
        "from",
        "should",
        "instead",
        "drop",
        "after",
        "all",
        "change",
        "plan",
        "switch",
        "forget",
        "let's",
        "second",
        "thought",
        "scratch",
        "idea",
        "call",
        "update",
        "ops",
        "vetoed",
        "go",
    }
)
TRIMMED_LINE_TEMPLATE = "#{position} {text}"
OVERRULED_SUFFIX_TEMPLATE = " (overruled by #{later_position})"

MAXIMUM_MESSAGE_CHARACTERS = 1500
MAXIMUM_RECALL_CHARACTERS = 6000
CUT_MESSAGE_SUFFIX_TEMPLATE = " [{cut_count} more characters left out]"
LEFT_OUT_LINES_TEMPLATE = "[{left_out_count} earlier messages left out to fit the budget]"
LINE_SEPARATOR = "\n"

SESSION_START_EVENT_NAME = "SessionStart"
COMPACTION_SOURCE = "compact"
HOOK_EVENT_NAME_INPUT_KEY = "hook_event_name"
SOURCE_INPUT_KEY = "source"
TRANSCRIPT_PATH_INPUT_KEY = "transcript_path"
ADDITIONAL_CONTEXT_KEY = "additionalContext"
RECALL_CONTEXT_TEMPLATE = (
    "The context was just compacted, so the user's own words are gone from it. "
    "These are the messages the user typed in this session, oldest first, trimmed "
    "to their substance. A later message overrides an earlier one. A line that "
    "ends with (overruled by #N) is one that message N changes, so read the two "
    "together and follow message N where they differ. When message N was left "
    "out to fit the budget, treat the marked line as replaced. Hold them as the user's "
    "instructions next to the summary, then continue the work.\n\n{lines}"
)

EVAL_FIXTURE_DIRECTORY = Path(__file__).resolve().parent.parent / "session" / "fixtures" / (
    "compaction_user_messages"
)
EVAL_CASES_FILE_NAME = "trim_cases.json"
EVAL_CASE_TRANSCRIPT_KEY = "transcript"
EVAL_CASE_FACTS_KEY = "facts"
EVAL_CASE_OVERRULED_KEY = "overruled"
EVAL_CASE_EARLIER_KEY = "earlier"
EVAL_MESSAGE_LINE_PATTERN_TEMPLATE = r"^\W*#?{position}\b.*$"
EVAL_OVERRULED_MARKER = "overruled"
EVAL_FILE_ENCODING = "utf-8"
