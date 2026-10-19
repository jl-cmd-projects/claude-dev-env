"""Names, limits, and texts for the compaction user-message recall hooks.

Groups: the transcript entry shapes the extractor reads, the bounds and
location of the file it writes, the SessionStart context that tells the agent
to run the extractor, and the eval that runs the condensing hook live.
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

MAXIMUM_MESSAGE_CHARACTERS = 4000
MAXIMUM_EXTRACT_CHARACTERS = 60000
CUT_MESSAGE_SUFFIX_TEMPLATE = "\n[{cut_count} more characters left out]"
LEFT_OUT_MESSAGES_TEMPLATE = "[{left_out_count} earlier messages left out to fit the budget]\n\n"
NO_MESSAGES_TEXT = "No typed user messages were found in this transcript.\n"
MESSAGE_HEADING_TEMPLATE = "## {position} | {timestamp}\n{text}\n\n"
MESSAGES_HEADING = "# User messages, oldest first\n\n"

ALL_RECALL_DIRECTORY_PARTS = (".claude", "compaction-recall")
OUTPUT_FILE_SUFFIX = ".md"
OUTPUT_ENCODING = "utf-8"
TRANSCRIPT_ARGUMENT_COUNT = 2
USAGE_TEXT = "usage: compaction_user_messages.py <transcript.jsonl>\n"
USAGE_EXIT_CODE = 2

SESSION_START_EVENT_NAME = "SessionStart"
COMPACTION_SOURCE = "compact"
HOOK_EVENT_NAME_INPUT_KEY = "hook_event_name"
SOURCE_INPUT_KEY = "source"
TRANSCRIPT_PATH_INPUT_KEY = "transcript_path"
ADDITIONAL_CONTEXT_KEY = "additionalContext"
EXTRACTOR_SCRIPT_NAME = "compaction_user_messages.py"
RECALL_CONTEXT_TEMPLATE = (
    "The context was just compacted, so the user's own words are gone from it. "
    "Run this Bash command first, before you reply and before any other tool call:\n\n"
    "{command}\n\n"
    "It prints a file path. A PostToolUse hook then reads that file and returns every "
    "message the user typed in this session, condensed, as a hook blocking error. That "
    "block is no error. It is the user's requests in order, and a later message overrides "
    "an earlier one. Hold them as the user's instructions next to the summary, then "
    "continue the work. Read the printed file only when no condensed block arrives."
)

EVAL_SESSION_DIRECTORY = Path(__file__).resolve().parent.parent / "session"
EVAL_FIXTURE_DIRECTORY = EVAL_SESSION_DIRECTORY / "fixtures" / "compaction_user_messages"
EVAL_HOOKS_JSON_PATH = EVAL_SESSION_DIRECTORY.parent / "hooks.json"
EVAL_RESULTS_FILE_NAME = "results.json"
EVAL_RESULTS_JSON_INDENT = 2
EVAL_SERVED_MODEL_SEPARATOR = ","
EVAL_MESSAGE_LINE_PATTERN_TEMPLATE = r"^\W*#?{position}\b.*$"
EVAL_OVERRULED_MARKER = "overruled"
EVAL_CASES_FILE_NAME = "trim_cases.json"
EVAL_CLAUDE_EXECUTABLE = "claude"
EVAL_DEFAULT_MODEL = "haiku"
EVAL_HOOK_TYPE = "agent"
EVAL_TIMEOUT_SECONDS = 240
EVAL_JSON_OBJECT_START = "{"
EVAL_PACKAGE_SETTINGS_PATH = EVAL_SESSION_DIRECTORY.parent.parent / "settings.json"
EVAL_RUN_SETTINGS_FILE_NAME = "hook-settings.json"
EVAL_DEBUG_FILE_NAME = "debug.log"
EVAL_STRUCTURED_OUTPUT_MARKER = "Hooks: Got structured output: "
EVAL_DECISION_SEPARATOR = "\n"
EVAL_ALLOWED_TOOLS = "Bash(python3:*)"
EVAL_EMPTY_MCP_CONFIG = '{"mcpServers": {}}'
EVAL_RUN_PROMPT_TEMPLATE = (
    "Run this exact Bash command once, then reply with one word, done:\n\n{command}"
)
