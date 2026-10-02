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
TRANSCRIPT_POLL_INTERVAL_SECONDS = 0.05
TRANSCRIPT_POLL_LIMIT_SECONDS = 5.0

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
ALL_MCP_MUTATING_ACTION_NAMES = frozenset({"request_copilot_review"})

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
ALL_WRITE_REDIRECTION_OPERATORS = frozenset({">", ">>", "&>", "&>>", ">&", ">|"})
ALL_NON_FILE_REDIRECTION_TARGETS = frozenset({"/dev/null", "$null", "nul"})
DESCRIPTOR_DUPLICATION_OPERATOR = ">&"
DESCRIPTOR_CLOSE_TARGET = "-"
REDIRECTION_TARGET_QUOTES = "'\""

ALL_FILE_WRITING_PROGRAM_NAMES = frozenset(
    {"rm", "rmdir", "unlink", "touch", "cp", "mv", "mkdir", "tee", "ln"}
)
SED_PROGRAM_NAME = "sed"
SED_IN_PLACE_OPTION_PATTERN = re.compile(r"-[a-zA-Z]*i.*|--in-place(?:=.*)?")
GH_PROGRAM_NAME = "gh"
GH_SUBCOMMAND_DEPTH = 2
ALL_MUTATING_GH_SUBCOMMANDS = frozenset(
    {
        ("pr", "create"),
        ("pr", "edit"),
        ("pr", "merge"),
        ("pr", "comment"),
        ("pr", "ready"),
        ("pr", "close"),
        ("pr", "review"),
        ("issue", "create"),
        ("issue", "edit"),
        ("issue", "comment"),
        ("issue", "close"),
        ("run", "rerun"),
        ("workflow", "run"),
    }
)
GH_API_SUBCOMMAND = "api"
ALL_GH_API_METHOD_OPTIONS = frozenset({"-X", "--method"})
GH_API_ATTACHED_METHOD_PATTERN = re.compile(r"(?:-X|--method=)(?P<method>.+)")
GH_API_FIELD_OPTION_PATTERN = re.compile(r"-[fF].*|--(?:field|raw-field|input)(?:=.*)?")
ALL_HTTP_WRITE_METHODS = frozenset({"POST", "PATCH", "PUT", "DELETE"})
PULL_REQUEST_SCRIPT_NAME = "pull_request.py"
ALL_PULL_REQUEST_SCRIPT_WRITE_ACTIONS = frozenset({"create", "edit", "comment", "review"})
ALL_POWERSHELL_WRITE_CMDLET_NAMES = frozenset(
    {
        "remove-item",
        "set-content",
        "add-content",
        "out-file",
        "copy-item",
        "move-item",
        "new-item",
        "rename-item",
    }
)
POWERSHELL_WORD_BRACKETS = "{}();"
POWERSHELL_SCRIPT_BLOCK_OPENER = "{"

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
