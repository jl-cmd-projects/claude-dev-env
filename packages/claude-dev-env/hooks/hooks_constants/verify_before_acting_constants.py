"""Constants for the verify-before-acting PostToolUse hook."""

import re

from hooks_constants.tool_names import APPLY_PATCH_TOOL_NAME

ALLOW_EXIT_CODE = 0
TOOL_NAME_KEY = "tool_name"
TOOL_INPUT_KEY = "tool_input"
TOOL_USE_ID_KEY = "tool_use_id"
TRANSCRIPT_PATH_KEY = "transcript_path"
COMMAND_KEY = "command"
MESSAGE_KEY = "message"
MESSAGE_ID_KEY = "id"
CONTENT_KEY = "content"
BLOCK_TYPE_KEY = "type"
BLOCK_ID_KEY = "id"
THINKING_BLOCK_TYPE = "thinking"
THINKING_TEXT_KEY = "thinking"
TOOL_USE_BLOCK_TYPE = "tool_use"
TRANSCRIPT_ENCODING = "utf-8"
TRANSCRIPT_DECODE_ERRORS = "replace"
THINKING_JOINER = "\n"

ALL_ALWAYS_MUTATING_TOOL_NAMES = frozenset(
    {"Write", "Edit", "MultiEdit", "NotebookEdit", "Agent", "Task", APPLY_PATCH_TOOL_NAME}
)
ALL_SHELL_TOOL_NAMES = frozenset({"Bash", "PowerShell"})
MCP_TOOL_PREFIX = "mcp__"
MCP_SEGMENT_SEPARATOR = "__"
MCP_ACTION_WORD_SPLIT_PATTERN = re.compile(r"_+|(?<=[a-z0-9])(?=[A-Z])")
ALL_MCP_MUTATING_VERBS = frozenset(
    {
        "create",
        "update",
        "delete",
        "send",
        "post",
        "reply",
        "write",
        "merge",
        "set",
        "add",
        "remove",
        "edit",
        "trash",
        "archive",
    }
)
ALL_MCP_READ_VERBS = frozenset({"get", "list", "search", "read", "view", "fetch", "find", "query"})

GIT_PROGRAM_NAME = "git"
ALL_MUTATING_GIT_SUBCOMMAND_PREFIXES = frozenset(
    {
        ("commit",),
        ("push",),
        ("merge",),
        ("rebase",),
        ("reset",),
        ("checkout", "-b"),
        ("switch", "-c"),
        ("worktree", "add"),
    }
)
ALL_WRITE_REDIRECTION_OPERATORS = frozenset({">", ">>", "&>", "&>>", ">&"})
ALL_NON_FILE_REDIRECTION_TARGETS = frozenset({"/dev/null", "$null", "nul", "-"})
REDIRECTION_TARGET_QUOTES = "'\""

_HTTP_WRITE_METHODS = r"(?:POST|PATCH|PUT|DELETE)"
_EXPLICIT_GET_METHOD = r"(?![^\n;|&]*?\s(?:-X\s*|--method[\s=]+)GET\b)"
ALL_MUTATING_COMMAND_PATTERNS = (
    re.compile(r"\bgh\s+pr\s+(?:create|edit|merge|comment|ready|close)\b"),
    re.compile(r"\bgh\s+issue\s+(?:create|edit|comment|close)\b"),
    re.compile(
        r"\bgh\s+api\b"
        + _EXPLICIT_GET_METHOD
        + r"[^\n;|&]*?(?:\s-X\s*"
        + _HTTP_WRITE_METHODS
        + r"\b|\s--method[\s=]+"
        + _HTTP_WRITE_METHODS
        + r"\b|\s(?:-f|-F|--field|--raw-field)[\s=])",
        re.IGNORECASE,
    ),
    re.compile(r"\bpull_request\.py\b[^\n;|&]*?\s(?:create|edit|comment|review)\b"),
    re.compile(r"\bgh\s+run\s+rerun\b"),
    re.compile(r"\bgh\s+workflow\s+run\b"),
    re.compile(
        r"\b(?:Remove-Item|Set-Content|Add-Content|Out-File|Copy-Item|Move-Item|New-Item|Rename-Item)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:^|[;&|(\n`])\s*(?:sudo\s+)?(?:xargs(?:\s+-\S+)*\s+)?(?:\S*/)?"
        r"(?:rm|rmdir|unlink|touch|cp|mv|mkdir|tee|ln)(?=\s|$)"
    ),
    re.compile(r"\bsed\b[^\n;|&]*?\s(?:-[a-zA-Z]*i\S*|--in-place\b)"),
)

ALL_HEDGE_PHRASES = (
    "probably",
    "likely",
    "maybe",
    "perhaps",
    "presumably",
    "might be",
    "may be",
    "seems",
    "appears to",
    "i suspect",
    "i guess",
    "i believe",
    "my guess",
    "my theory",
    "not sure",
    "unsure",
)
HEDGE_PATTERN = re.compile(
    r"\b(?:"
    + "|".join(r"\s+".join(each_phrase.split()) for each_phrase in ALL_HEDGE_PHRASES)
    + r")\b",
    re.IGNORECASE,
)
SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+|\n+")
WHITESPACE_RUN_PATTERN = re.compile(r"\s+")
WORD_SEPARATOR = " "
MAXIMUM_QUOTE_LENGTH = 160
QUOTE_LEAD_LENGTH = MAXIMUM_QUOTE_LENGTH // 2
TRIM_MARKER = "..."

DECISION_KEY = "decision"
BLOCK_DECISION = "block"
REASON_KEY = "reason"
BLOCK_REASON_TEMPLATE = (
    'The reasoning behind this {tool_name} call hedges: "{hedge_sentence}" '
    "Check that claim now with a read-only tool, then continue. "
    "If the check contradicts it, undo this change first."
)

DECISION_LOG_RELATIVE_PATH = ".claude/logs/verify-before-acting.jsonl"
LOG_APPEND_MODE = "a"
LOG_LINE_END = "\n"
LOG_TIMESTAMP_KEY = "timestamp"
LOG_TOOL_NAME_KEY = "tool_name"
LOG_TOOL_USE_ID_KEY = "tool_use_id"
LOG_OUTCOME_KEY = "outcome"
LOG_HEDGE_SENTENCE_KEY = "hedge_sentence"
OUTCOME_BLOCKED = "blocked"
OUTCOME_ALLOWED_CLEAN = "allowed_clean"
OUTCOME_REASONING_UNSEEN = "reasoning_unseen"
